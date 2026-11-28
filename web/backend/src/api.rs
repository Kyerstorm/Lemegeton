use axum::{extract::{Path, Query, State}, http::{header, HeaderMap, HeaderValue, Method}, response::{IntoResponse, Response}, Json};
use serde::Deserialize;
use serde_json::{json, Value};
use std::{collections::HashMap, time::Instant};
use crate::state::{authorized_guild, bridge_json, cookie_consent_cookie, cookie_consent_cookie_name, cookie_value, is_bot_moderator, new_token, now_secs, session_from_headers, write_session, ApiError, ApiResult, AppState, COOKIE_CONSENT_TTL, COOKIE_CONSENT_VERSION};

mod atlas;
mod commands;
mod picker;

pub use atlas::atlas;
pub use commands::*;
pub use picker::custom_roles_proxy;



#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CookiePreferenceRequest {
    remember_server: bool,
}

fn cookie_consent_id(headers: &HeaderMap, state: &AppState) -> Option<String> {
    let value = cookie_value(headers, cookie_consent_cookie_name(state))?;
    (value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())).then_some(value)
}

pub async fn cookie_consent(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let consent_id = cookie_consent_id(&headers, &state).unwrap_or_default();
    let record = state.store.get_cookie_consent(&consent_id, now_secs()).await
        .map_err(|_| ApiError::unavailable())?;
    let current = record.filter(|value| value.consent_version.as_str() == COOKIE_CONSENT_VERSION);
    Ok(Json(json!({
        "saved": current.is_some(),
        "remember_server": current.as_ref().is_some_and(|value| value.remember_server),
        "consent_version": COOKIE_CONSENT_VERSION,
        "decided_at": current.as_ref().map(|value| value.decided_at),
        "expires_at": current.as_ref().map(|value| value.expires_at)
    })))
}

pub async fn save_cookie_preferences(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<CookiePreferenceRequest>,
) -> ApiResult<Response> {
    let origin = headers.get(header::ORIGIN).and_then(|value| value.to_str().ok()).unwrap_or("");
    if origin.trim_end_matches('/') != state.config.public_origin {
        return Err(ApiError::forbidden("The cookie preference request origin is not trusted."));
    }

    let now = now_secs();
    let consent_id = cookie_consent_id(&headers, &state).unwrap_or_else(new_token);
    state.store.save_cookie_consent(
        &consent_id,
        body.remember_server,
        COOKIE_CONSENT_VERSION,
        now,
        COOKIE_CONSENT_TTL,
    ).await.map_err(|_| ApiError::unavailable())?;

    let cookie = HeaderValue::from_str(&cookie_consent_cookie(&consent_id, &state))
        .map_err(|_| ApiError::new(axum::http::StatusCode::INTERNAL_SERVER_ERROR, "Could not create a cookie preference record."))?;
    let mut response = Json(json!({
        "saved": true,
        "remember_server": body.remember_server,
        "consent_version": COOKIE_CONSENT_VERSION,
        "decided_at": now,
        "expires_at": now.saturating_add(COOKIE_CONSENT_TTL)
    })).into_response();
    response.headers_mut().insert(header::SET_COOKIE, cookie);
    if state.config.secure_cookie {
        response.headers_mut().append(header::SET_COOKIE, HeaderValue::from_static(
            "lemegeton_cookie_consent=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Secure",
        ));
    }
    response.headers_mut().insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    Ok(response)
}

#[derive(Deserialize)]
pub struct ConsentAcceptance { accepted: bool }

pub async fn policy_consent(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    Ok(Json(bridge_json(
        &state,
        Method::GET,
        &format!("/users/{}/consent", session.user.id),
        None,
    ).await?))
}

pub async fn accept_policy_consent(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<ConsentAcceptance>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    if !body.accepted {
        return Err(ApiError::bad_request("Explicit acceptance of all current policies is required."));
    }
    Ok(Json(bridge_json(
        &state,
        Method::POST,
        &format!("/users/{}/consent", session.user.id),
        Some(json!({"accepted": true})),
    ).await?))
}

pub async fn system(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let _ = session_from_headers(&state, &headers).await?;
    match bridge_json(&state, Method::GET, "/health", None).await {
        Ok(mut current) => {
            current["observed_at"] = json!(crate::state::now_secs());
            *state.last_status.lock().await = Some(current.clone());
            Ok(Json(current))
        }
        Err(_) => {
            let cached = state.last_status.lock().await.clone();
            Ok(Json(json!({"status":"unknown","ready":false,"reason":"The bot status bridge is unreachable.",
                "observed_at":crate::state::now_secs(),"last_known":cached})))
        }
    }
}

pub async fn integrations(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_bot_moderator(&state, &session.user.id).await? {
        return Err(ApiError::forbidden("Only registered bot moderators can view bot-wide integration status."));
    }
    Ok(Json(bridge_json(&state, Method::GET, "/integrations", None).await?))
}

pub async fn overview(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/overview"), None).await?))
}

pub async fn server_settings(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !(17..=20).contains(&guild_id.len()) || !guild_id.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ApiError::bad_request("Invalid guild identifier."));
    }
    let path = format!("/guilds/{guild_id}/settings?actor_id={}", urlencoding::encode(&session.user.id));
    Ok(Json(bridge_json(&state, Method::GET, &path, None).await?))
}

pub async fn save_server_settings(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Json(mut body): Json<Value>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    if !(17..=20).contains(&guild_id.len()) || !guild_id.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ApiError::bad_request("Invalid guild identifier."));
    }
    let object = body.as_object_mut().ok_or_else(|| ApiError::bad_request("Server settings must be a JSON object."))?;
    object.insert("actor_id".to_string(), json!(session.user.id));
    Ok(Json(bridge_json(
        &state,
        Method::PUT,
        &format!("/guilds/{guild_id}/settings"),
        Some(body),
    ).await?))
}

pub async fn archive_settings(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/archive-settings"), None).await?))
}

pub async fn save_archive_settings(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Json(mut body): Json<Value>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    let object = body.as_object_mut().ok_or_else(|| ApiError::bad_request("Archive settings must be a JSON object."))?;
    object.insert("actor_id".to_string(), json!(session.user.id));
    Ok(Json(bridge_json(
        &state,
        Method::PUT,
        &format!("/guilds/{guild_id}/archive-settings"),
        Some(body),
    ).await?))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DashboardIssueRequest {
    component: String,
    path: String,
    message: String,
    stack: Option<String>,
}

pub async fn report_issue(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Json(body): Json<DashboardIssueRequest>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;

    let valid_component = !body.component.is_empty()
        && body.component.len() <= 80
        && body.component.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'));
    let valid_path = body.path.starts_with('/')
        && body.path.len() <= 512
        && !body.path.contains('?')
        && !body.path.contains('#');
    if !valid_component || !valid_path || body.message.trim().is_empty()
        || body.message.len() > 2_000
        || body.stack.as_ref().is_some_and(|stack| stack.len() > 12_000) {
        return Err(ApiError::bad_request("The diagnostic report contains invalid fields."));
    }

    let result = bridge_json(
        &state,
        Method::POST,
        "/issues",
        Some(json!({
            "guild_id": guild_id,
            "user_id": session.user.id,
            "username": session.user.global_name.as_deref().unwrap_or(&session.user.username),
            "component": body.component,
            "path": body.path,
            "message": body.message,
            "stack": body.stack,
        })),
    ).await?;
    let reference = result.get("issue_reference")
        .and_then(Value::as_str)
        .filter(|value| value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .ok_or_else(ApiError::unavailable)?;
    Ok(Json(json!({ "issue_reference": reference })))
}

pub async fn logs(State(state): State<AppState>, headers: HeaderMap, Query(query): Query<HashMap<String, String>>) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_bot_moderator(&state, &session.user.id).await? {
        return Err(ApiError::forbidden("Runtime logs are restricted to registered bot moderators."));
    }
    let filename = query.get("file").map(String::as_str).unwrap_or("bot.log");
    if !matches!(filename, "bot.log" | "dashboard.log") { return Err(ApiError::bad_request("That log file is not available.")); }
    Ok(Json(bridge_json(&state, Method::GET, &format!("/logs?file={}", urlencoding::encode(filename)), None).await?))
}


pub async fn public_status(State(state): State<AppState>) -> Response {
    // Coalesce concurrent status refreshes and keep the aggregate snapshot briefly for visitors.
    let mut cache = state.public_status_cache.lock().await;
    if let Some((updated_at, snapshot)) = cache.as_ref() {
        if updated_at.elapsed() < std::time::Duration::from_secs(10) {
            let mut response = Json(snapshot.clone()).into_response();
            response.headers_mut().insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
            return response;
        }
    }

    let (dashboard_store_health, bot_health) = tokio::join!(
        state.store.health(),
        bridge_json(&state, Method::GET, "/health", None),
    );
    let dashboard_store_ready = dashboard_store_health.is_ok();
    let bot_health = bot_health.ok();
    let runtime_status = bot_health.as_ref()
        .and_then(|health| health.get("status"))
        .and_then(Value::as_str);
    let bot_ready = bot_health.as_ref()
        .and_then(|health| health.get("ready"))
        .and_then(Value::as_bool);
    let gateway_latency = bot_health.as_ref()
        .and_then(|health| health.get("latency_ms"))
        .and_then(Value::as_u64);
    let bot_database_status = bot_health.as_ref()
        .and_then(|health| health.get("database"))
        .and_then(|database| database.get("status"))
        .and_then(Value::as_str);
    let bot_database_latency = bot_health.as_ref()
        .and_then(|health| health.get("database"))
        .and_then(|database| database.get("latency_ms"))
        .and_then(Value::as_u64);

    let bot_status = match (runtime_status, bot_ready) {
        (Some("online"), Some(true)) => "operational",
        (Some("offline"), _) => "major_outage",
        (Some("online" | "degraded" | "connecting"), _) => "degraded",
        _ => "unknown",
    };
    let gateway_status = match (bot_ready, runtime_status, gateway_latency) {
        (Some(true), _, Some(latency)) if latency >= 500 => "degraded",
        (Some(true), _, _) => "operational",
        (Some(false), Some("offline"), _) => "major_outage",
        (Some(false), Some(_), _) => "degraded",
        _ => "unknown",
    };
    let database_status = if !dashboard_store_ready || bot_database_status == Some("offline") {
        "major_outage"
    } else if dashboard_store_ready {
        "operational"
    } else {
        "unknown"
    };

    let component_statuses = [bot_status, gateway_status, database_status];
    let overall_status = if component_statuses.contains(&"major_outage") {
        "major_outage"
    } else if component_statuses.contains(&"degraded") {
        "degraded"
    } else if component_statuses.contains(&"unknown") {
        "unknown"
    } else {
        "operational"
    };

    let bot_detail = if bot_health.is_some() {
        "The bot health bridge responded."
    } else {
        "The bot health bridge could not be reached."
    };
    let gateway_detail = if bot_ready == Some(true) {
        "The Discord gateway connection is active."
    } else {
        "The Discord gateway connection has not been confirmed."
    };
    let database_detail = if database_status == "operational" {
        if bot_database_latency.is_some() {
            "Shared data-store health checks passed."
        } else {
            "Dashboard data-store health check passed."
        }
    } else {
        "A shared data-store health check failed."
    };

    let snapshot = json!({
        "status": overall_status,
        "observed_at": now_secs(),
        "components": [
            {
                "id": "dashboard",
                "name": "Dashboard API",
                "status": "operational",
                "detail": "The public status service is responding."
            },
            {
                "id": "bot",
                "name": "Bot runtime",
                "status": bot_status,
                "detail": bot_detail
            },
            {
                "id": "gateway",
                "name": "Discord gateway",
                "status": gateway_status,
                "detail": gateway_detail,
                "latency_ms": gateway_latency
            },
            {
                "id": "database",
                "name": "Shared data store",
                "status": database_status,
                "detail": database_detail,
                "latency_ms": bot_database_latency
            }
        ]
    });
    *cache = Some((Instant::now(), snapshot.clone()));
    let mut response = Json(snapshot).into_response();
    response.headers_mut().insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[cfg(test)]
mod tests;

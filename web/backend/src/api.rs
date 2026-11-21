use axum::{extract::{Path, Query, State}, http::{HeaderMap, Method}, Json};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use crate::state::{authorized_guild, bridge_json, is_owner, session_from_headers, write_session, ApiError, ApiResult, AppState};

mod atlas;
mod commands;
mod picker;

pub use atlas::atlas;
pub use commands::*;
pub use picker::custom_roles_proxy;


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
    if !is_owner(&state, &session.user.id) {
        return Err(ApiError::forbidden("Only configured dashboard owners can view bot-wide integration status."));
    }
    Ok(Json(bridge_json(&state, Method::GET, "/integrations", None).await?))
}

pub async fn overview(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/overview"), None).await?))
}

pub async fn logs(State(state): State<AppState>, headers: HeaderMap, Query(query): Query<HashMap<String, String>>) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_owner(&state, &session.user.id) { return Err(ApiError::forbidden("Runtime logs are restricted to configured dashboard owners.")); }
    let filename = query.get("file").map(String::as_str).unwrap_or("bot.log");
    if !matches!(filename, "bot.log" | "dashboard.log") { return Err(ApiError::bad_request("That log file is not available.")); }
    Ok(Json(bridge_json(&state, Method::GET, &format!("/logs?file={}", urlencoding::encode(filename)), None).await?))
}

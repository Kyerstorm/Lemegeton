use axum::{body::{to_bytes, Body}, extract::{Path, Query, State}, http::{header, HeaderMap, Method, Request, StatusCode}, response::{IntoResponse, Response}, Json};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use crate::state::{authorized_guild, bridge_json, is_owner, session_from_headers, write_session, protected_command, ApiError, ApiResult, AppState};

pub async fn system(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let _ = session_from_headers(&state, &headers).await?;
    match bridge_json(&state, Method::GET, "/health", None).await {
        Ok(mut current) => { current["observed_at"] = json!(crate::state::now_secs()); *state.last_status.lock().await = Some(current.clone()); Ok(Json(current)) }
        Err(_) => {
            let cached = state.last_status.lock().await.clone();
            Ok(Json(json!({"status":"unknown","ready":false,"reason":"The bot status bridge is unreachable.",
                "observed_at":crate::state::now_secs(),"last_known":cached})))
        }
    }
}
pub async fn integrations(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_owner(&state, &session.user.id) { return Err(ApiError::forbidden("Only configured dashboard owners can view bot-wide integration status.")); }
    Ok(Json(bridge_json(&state, Method::GET, "/integrations", None).await?))
}
pub async fn overview(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/overview"), None).await?))
}
pub async fn commands(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/commands"), None).await?))
}
#[derive(Deserialize)]
pub struct ToggleRequest { enabled: bool }
pub async fn set_command(State(state): State<AppState>, headers: HeaderMap, Path((guild_id, fullname)): Path<(String, String)>, Json(body): Json<ToggleRequest>) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    if fullname.trim().is_empty() || fullname.len() > 100 { return Err(ApiError::bad_request("Invalid command name.")); }
    let data = bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/commands"), None).await?;
    let item = data.get("commands").and_then(Value::as_array).into_iter().flatten()
        .find(|item| item.get("fullname").and_then(Value::as_str) == Some(fullname.as_str()))
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Command is not available for dashboard management."))?;
    if item.get("protected").and_then(Value::as_bool).unwrap_or(false)
        || item.get("name").and_then(Value::as_str).is_some_and(protected_command) {
        return Err(ApiError::forbidden("This system command is protected."));
    }
    let encoded = urlencoding::encode(&fullname);
    Ok(Json(bridge_json(&state, Method::PUT, &format!("/guilds/{guild_id}/commands/{encoded}"),
        Some(json!({"enabled":body.enabled,"actor_id":session.user.id}))).await?))
}
pub async fn sync_guild(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>, Json(_body): Json<Value>) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::POST, &format!("/guilds/{guild_id}/sync"), Some(json!({"actor_id":session.user.id}))).await?))
}
pub async fn reset_guild(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>, Json(_body): Json<Value>) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::POST, &format!("/guilds/{guild_id}/reset"), Some(json!({"actor_id":session.user.id}))).await?))
}
pub async fn audit(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/audit"), None).await?))
}
pub async fn database(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/database"), None).await?))
}
pub async fn logs(State(state): State<AppState>, headers: HeaderMap, Query(query): Query<HashMap<String, String>>) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_owner(&state, &session.user.id) { return Err(ApiError::forbidden("Runtime logs are restricted to configured dashboard owners.")); }
    let filename = query.get("file").map(String::as_str).unwrap_or("bot.log");
    if !matches!(filename, "bot.log" | "dashboard.log") { return Err(ApiError::bad_request("That log file is not available.")); }
    Ok(Json(bridge_json(&state, Method::GET, &format!("/logs?file={}", urlencoding::encode(filename)), None).await?))
}
pub async fn custom_roles_proxy(State(state): State<AppState>, request: Request<Body>) -> Response {
    let (parts, body) = request.into_parts();
    let path = parts.uri.path_and_query().map(|v| v.as_str()).unwrap_or("/custom-roles");
    if !path.starts_with("/custom-roles") || path.contains("..") { return ApiError::new(StatusCode::NOT_FOUND, "Route not found.").into_response(); }
    let body = match to_bytes(body, 12 * 1024 * 1024).await {
        Ok(body) => body, Err(_) => return ApiError::new(StatusCode::PAYLOAD_TOO_LARGE, "The uploaded request is too large.").into_response(),
    };
    let url = format!("{}{}", state.config.picker_url, path);
    // The picker uses its own short-lived bearer tokens; the dashboard session cookie is not forwarded.
    let mut headers = parts.headers;
    headers.remove(header::HOST); headers.remove(header::CONNECTION); headers.remove(header::COOKIE);
    let response = match state.client.request(parts.method, url).headers(headers).body(body).send().await {
        Ok(response) => response, Err(_) => return ApiError::unavailable().into_response(),
    };
    let status = StatusCode::from_u16(response.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let headers_in = response.headers().clone();
    let bytes = match response.bytes().await {
        Ok(bytes) => bytes, Err(_) => return ApiError::new(StatusCode::BAD_GATEWAY, "The picker response could not be read.").into_response(),
    };
    let mut builder = Response::builder().status(status);
    for name in ["content-type", "cache-control", "content-disposition", "content-security-policy", "referrer-policy", "x-frame-options", "x-content-type-options", "permissions-policy"] {
        if let Some(value) = headers_in.get(name) { builder = builder.header(name, value); }
    }
    builder.body(Body::from(bytes)).unwrap_or_else(|_| ApiError::new(StatusCode::BAD_GATEWAY, "The picker response could not be returned.").into_response())
}

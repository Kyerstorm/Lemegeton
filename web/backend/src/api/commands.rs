use axum::{extract::{Path, Query, State}, http::{HeaderMap, Method, StatusCode}, Json};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use crate::state::{authorized_guild, bridge_json, write_session, protected_command, ApiError, ApiResult, AppState};

pub async fn command_access(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/command-access"), None).await?))
}
pub async fn set_command_access(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path((guild_id, fullname)): Path<(String, String)>,
    Json(mut body): Json<Value>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    if fullname.trim().is_empty() || fullname.len() > 100 {
        return Err(ApiError::bad_request("Invalid command name."));
    }
    let data = bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/commands"), None).await?;
    let item = data.get("commands").and_then(Value::as_array).into_iter().flatten()
        .find(|item| item.get("fullname").and_then(Value::as_str) == Some(fullname.as_str()))
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Command is not available for access management."))?;
    if item.get("protected").and_then(Value::as_bool).unwrap_or(false)
        || item.get("name").and_then(Value::as_str).is_some_and(protected_command) {
        return Err(ApiError::forbidden("This system command is protected."));
    }
    if !body.is_object()
        || !body.get("expected_revision").is_some_and(Value::is_u64)
        || !body.get("role_mode").and_then(Value::as_str).is_some_and(|mode| ["everyone","include","exclude"].contains(&mode))
        || !body.get("channel_mode").and_then(Value::as_str).is_some_and(|mode| ["all","include","exclude"].contains(&mode))
        || !body.get("role_ids").and_then(Value::as_array).is_some_and(|ids| ids.len() <= 100 && ids.iter().all(Value::is_string))
        || !body.get("channel_ids").and_then(Value::as_array).is_some_and(|ids| ids.len() <= 100 && ids.iter().all(Value::is_string)) {
        return Err(ApiError::bad_request("Choose valid role and channel access rules."));
    }
    body["actor_id"] = json!(session.user.id);
    let encoded = urlencoding::encode(&fullname);
    Ok(Json(bridge_json(&state, Method::PUT, &format!("/guilds/{guild_id}/command-access/{encoded}"), Some(body)).await?))
}

pub async fn commands(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/commands"), None).await?))
}

#[derive(Deserialize)]
pub struct CommandSettingUpdate { fullname: String, enabled: bool }
#[derive(Deserialize)]
pub struct SaveCommandsRequest { expected_revision: String, updates: Vec<CommandSettingUpdate> }
pub async fn save_commands(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Json(body): Json<SaveCommandsRequest>,
) -> ApiResult<Json<Value>> {
    let (_, session) = write_session(&state, &headers).await?;
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    if !protected_revision(&body.expected_revision) || body.updates.len() > 7 {
        return Err(ApiError::bad_request("The command revision or update list is invalid."));
    }
    let live = bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/commands"), None).await?;
    let available = live.get("commands").and_then(Value::as_array).into_iter().flatten();
    let by_name: HashMap<&str, &Value> = available
        .filter_map(|item| item.get("fullname").and_then(Value::as_str).map(|name| (name, item)))
        .collect();
    let mut seen = HashSet::new();
    for update in &body.updates {
        if update.fullname.trim().is_empty() || update.fullname.len() > 100 || !seen.insert(update.fullname.as_str()) {
            return Err(ApiError::bad_request("A command name is invalid or appears more than once."));
        }
        let item = by_name.get(update.fullname.as_str())
            .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "A command is not available for dashboard management."))?;
        if item.get("protected").and_then(Value::as_bool).unwrap_or(false)
            || item.get("name").and_then(Value::as_str).is_some_and(protected_command) {
            return Err(ApiError::forbidden("A protected system command cannot be changed."));
        }
    }
    Ok(Json(bridge_json(
        &state,
        Method::PUT,
        &format!("/guilds/{guild_id}/commands"),
        Some(json!({
            "actor_id": session.user.id,
            "expected_revision": body.expected_revision,
            "updates": body.updates.iter().map(|update| json!({
                "fullname": update.fullname,
                "enabled": update.enabled
            })).collect::<Vec<_>>()
        })),
    ).await?))
}
fn protected_revision(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
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
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct AuditQuery {
    limit: Option<u16>,
    cursor: Option<String>,
}

fn valid_audit_limit(limit: u16) -> bool {
    (1..=100).contains(&limit)
}

fn valid_audit_cursor(cursor: &str) -> bool {
    !cursor.is_empty()
        && cursor.len() <= 19
        && cursor.bytes().all(|byte| byte.is_ascii_digit())
        && cursor.parse::<i64>().is_ok_and(|value| value > 0)
}

pub async fn audit(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Query(query): Query<AuditQuery>,
) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    let limit = query.limit.unwrap_or(25);
    if !valid_audit_limit(limit) {
        return Err(ApiError::bad_request("Audit page size must be between 1 and 100."));
    }

    let mut path = format!("/guilds/{guild_id}/audit?limit={limit}");
    if let Some(cursor) = query.cursor.as_deref() {
        if !valid_audit_cursor(cursor) {
            return Err(ApiError::bad_request("Audit pagination cursor is invalid."));
        }
        path.push_str("&cursor=");
        path.push_str(&urlencoding::encode(cursor));
    }
    Ok(Json(bridge_json(&state, Method::GET, &path, None).await?))
}
pub async fn database(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/database"), None).await?))
}

#[cfg(test)]
mod tests {
    use super::{valid_audit_cursor, valid_audit_limit};

    #[test]
    fn audit_page_size_is_bounded() {
        assert!(!valid_audit_limit(0));
        assert!(valid_audit_limit(1));
        assert!(valid_audit_limit(25));
        assert!(valid_audit_limit(100));
        assert!(!valid_audit_limit(101));
    }

    #[test]
    fn audit_cursor_accepts_only_positive_signed_database_ids() {
        assert!(valid_audit_cursor("1"));
        assert!(valid_audit_cursor("9223372036854775807"));
        assert!(!valid_audit_cursor(""));
        assert!(!valid_audit_cursor("0"));
        assert!(!valid_audit_cursor("-1"));
        assert!(!valid_audit_cursor("1.5"));
        assert!(!valid_audit_cursor("9223372036854775808"));
        assert!(!valid_audit_cursor("123456789012345678901"));
    }
}

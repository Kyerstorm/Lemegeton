use axum::{body::{to_bytes, Body}, extract::{Path, Query, State}, http::{HeaderMap, Method, Request, StatusCode}, response::{IntoResponse, Response}, Json};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use crate::state::{authorized_guild, atlas_bridge_json, bridge_json, is_owner, session_from_headers, write_session, protected_command, ApiError, ApiResult, AppState};

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
    if !protected_revision(&body.expected_revision) || body.updates.len() > 6 {
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
pub async fn audit(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/audit"), None).await?))
}
pub async fn database(State(state): State<AppState>, headers: HeaderMap, Path(guild_id): Path<String>) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    Ok(Json(bridge_json(&state, Method::GET, &format!("/guilds/{guild_id}/database"), None).await?))
}
#[derive(Deserialize, Default)]
pub struct AtlasQuery {
    title: String,
    category: String,
    url: Option<String>,
    provider: Option<String>,
    provider_id: Option<String>,
    query: Option<String>,
    filter_category: Option<String>,
    relationship_type: Option<String>,
    source_kind: Option<String>,
    provider_filter: Option<String>,
    provider_id_filter: Option<String>,
    evidence: Option<String>,
    target_title: Option<String>,
    target_category: Option<String>,
    target_url: Option<String>,
    target_provider: Option<String>,
    target_provider_id: Option<String>,
    max_depth: Option<u8>,
    max_nodes: Option<u8>,
    export: Option<String>,
}

fn valid_atlas_category(category: &str) -> bool {
    matches!(category,
        "ANIME" | "MANGA" | "LIGHT_NOVEL" | "WEBNOVEL" | "BOOK" | "MOVIE" | "TV" | "GAME"
        | "CREATOR" | "FRANCHISE" | "ARCHIVE_ENTRY" | "ARCHIVE_COLLECTION" | "DISCUSSION" | "ACTIVITY")
}

fn valid_atlas_provider(value: &str) -> bool {
    !value.is_empty() && value.len() <= 65
        && value.split(':').count() <= 2
        && value.split(':').all(|part| !part.is_empty() && part.len() <= 32
            && part.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')))
}

fn valid_atlas_provider_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128
        && value.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | ':' | '-'))
}

fn validate_atlas_public_url(raw_url: &str) -> ApiResult<()> {
    let url = reqwest::Url::parse(raw_url)
        .map_err(|_| ApiError::bad_request("The media source URL is invalid."))?;
    if url.scheme() != "https" || url.host_str().is_none()
        || !url.username().is_empty() || url.password().is_some() {
        return Err(ApiError::bad_request("The media source URL must be a public HTTPS URL without credentials."));
    }
    Ok(())
}

fn validate_atlas_identity(provider: &Option<String>, provider_id: &Option<String>) -> ApiResult<()> {
    match (provider.as_deref(), provider_id.as_deref()) {
        (None, None) => Ok(()),
        (Some(provider), Some(provider_id)) if valid_atlas_provider(provider) && valid_atlas_provider_id(provider_id) => Ok(()),
        _ => Err(ApiError::bad_request("A provider identity needs a valid provider namespace and stable provider ID.")),
    }
}

fn validate_atlas_query(query: &AtlasQuery) -> ApiResult<()> {
    if query.title.trim().is_empty() || query.title.chars().count() > 256 {
        return Err(ApiError::bad_request("Enter a media title between 1 and 256 characters."));
    }
    if !valid_atlas_category(&query.category) {
        return Err(ApiError::bad_request("Choose a supported Knowledge Atlas media category."));
    }
    if let Some(url) = query.url.as_deref() { validate_atlas_public_url(url)?; }
    validate_atlas_identity(&query.provider, &query.provider_id)?;
    validate_atlas_identity(&query.target_provider, &query.target_provider_id)?;
    if let Some(url) = query.target_url.as_deref() { validate_atlas_public_url(url)?; }
    match (query.target_title.as_deref(), query.target_category.as_deref()) {
        (None, None) => {}
        (Some(title), Some(category)) if !title.trim().is_empty() && title.chars().count() <= 256 && valid_atlas_category(category) => {}
        _ => return Err(ApiError::bad_request("The Atlas path target needs a valid title and category.")),
    }
    if query.filter_category.as_deref().is_some_and(|value| !valid_atlas_category(value)) {
        return Err(ApiError::bad_request("Unknown Atlas category filter."));
    }
    if query.source_kind.as_deref().is_some_and(|value| !matches!(value, "provider" | "recommendation" | "community")) {
        return Err(ApiError::bad_request("Unknown Atlas provenance filter."));
    }
    for (name, value, maximum) in [
        ("search", query.query.as_deref(), 200usize),
        ("relationship filter", query.relationship_type.as_deref(), 80),
        ("provider filter", query.provider_filter.as_deref(), 65),
        ("provider ID filter", query.provider_id_filter.as_deref(), 128),
        ("evidence filter", query.evidence.as_deref(), 200),
    ] {
        if value.is_some_and(|value| value.chars().count() > maximum) {
            return Err(ApiError::bad_request(format!("The Atlas {name} is too long.")));
        }
    }
    if query.provider_filter.as_deref().is_some_and(|value| !valid_atlas_provider(value)) {
        return Err(ApiError::bad_request("Invalid Atlas provider filter."));
    }
    if query.provider_id_filter.as_deref().is_some_and(|value| !valid_atlas_provider_id(value)) {
        return Err(ApiError::bad_request("Invalid Atlas provider ID filter."));
    }
    if query.max_depth.is_some_and(|value| !(1..=3).contains(&value))
        || query.max_nodes.is_some_and(|value| !(1..=40).contains(&value)) {
        return Err(ApiError::bad_request("Atlas graph depth is limited to 3 and graph size to 40 nodes."));
    }
    if query.export.as_deref().is_some_and(|value| !matches!(value, "json" | "svg" | "png")) {
        return Err(ApiError::bad_request("Atlas exports support JSON, SVG and PNG."));
    }
    Ok(())
}

pub async fn atlas(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Query(query): Query<AtlasQuery>,
) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    validate_atlas_query(&query)?;
    let mut path = format!(
        "/atlas?guild_id={}&title={}&category={}",
        urlencoding::encode(&guild_id),
        urlencoding::encode(query.title.trim()),
        urlencoding::encode(&query.category),
    );
    for (name, value) in [
        ("url", query.url.as_deref()),
        ("provider", query.provider.as_deref()),
        ("provider_id", query.provider_id.as_deref()),
        ("query", query.query.as_deref()),
        ("filter_category", query.filter_category.as_deref()),
        ("relationship_type", query.relationship_type.as_deref()),
        ("source_kind", query.source_kind.as_deref()),
        ("provider_filter", query.provider_filter.as_deref()),
        ("provider_id_filter", query.provider_id_filter.as_deref()),
        ("evidence", query.evidence.as_deref()),
        ("target_title", query.target_title.as_deref()),
        ("target_category", query.target_category.as_deref()),
        ("target_url", query.target_url.as_deref()),
        ("target_provider", query.target_provider.as_deref()),
        ("target_provider_id", query.target_provider_id.as_deref()),
    ] {
        if let Some(value) = value {
            path.push('&');
            path.push_str(name);
            path.push('=');
            path.push_str(&urlencoding::encode(value));
        }
    }
    for (name, value) in [("max_depth", query.max_depth), ("max_nodes", query.max_nodes)] {
        if let Some(value) = value {
            path.push('&');
            path.push_str(name);
            path.push('=');
            path.push_str(&value.to_string());
        }
    }
    if let Some(format) = query.export.as_deref() {
        path.push_str("&export=");
        path.push_str(format);
    }
    Ok(Json(atlas_bridge_json(&state, &path).await?))
}

pub async fn logs(State(state): State<AppState>, headers: HeaderMap, Query(query): Query<HashMap<String, String>>) -> ApiResult<Json<Value>> {
    let (_, session) = session_from_headers(&state, &headers).await?;
    if !is_owner(&state, &session.user.id) { return Err(ApiError::forbidden("Runtime logs are restricted to configured dashboard owners.")); }
    let filename = query.get("file").map(String::as_str).unwrap_or("bot.log");
    if !matches!(filename, "bot.log" | "dashboard.log") { return Err(ApiError::bad_request("That log file is not available.")); }
    Ok(Json(bridge_json(&state, Method::GET, &format!("/logs?file={}", urlencoding::encode(filename)), None).await?))
}
fn picker_forward_headers(incoming: &HeaderMap) -> HeaderMap {
    let mut outgoing = HeaderMap::new();
    for name in ["authorization", "content-type", "accept", "origin", "x-forwarded-for", "x-real-ip"] {
        if let Some(value) = incoming.get(name) {
            outgoing.insert(axum::http::header::HeaderName::from_static(name), value.clone());
        }
    }
    outgoing
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
    let headers = picker_forward_headers(&parts.headers);
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

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::header;
    #[test]
    fn atlas_query_accepts_supported_categories_and_public_https_urls() {
        let valid = AtlasQuery {
            title: "Frieren: Beyond Journey's End".to_string(),
            category: "ANIME".to_string(),
            url: Some("https://anilist.co/anime/1".to_string()),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&valid).is_ok());
    }

    #[test]
    fn atlas_query_rejects_unknown_categories_and_unsafe_urls() {
        let unknown = AtlasQuery { title: "Example".to_string(), category: "OTHER".to_string(), url: None, ..AtlasQuery::default() };
        assert!(validate_atlas_query(&unknown).is_err());
        let unsafe_url = AtlasQuery {
            title: "Example".to_string(), category: "ANIME".to_string(),
            url: Some("https://user:pass@example.com/".to_string()),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&unsafe_url).is_err());
        let oversized = AtlasQuery {
            title: "x".repeat(257), category: "ANIME".to_string(), url: None, ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&oversized).is_err());
    }


    #[test]
    fn atlas_query_accepts_dashboard_categories_filters_and_bounded_exports() {
        let collection = AtlasQuery {
            title: "Shared Collection".to_string(),
            category: "ARCHIVE_COLLECTION".to_string(),
            provider: Some("archive:collection".to_string()),
            provider_id: Some("12".to_string()),
            relationship_type: Some("adaptation".to_string()),
            source_kind: Some("community".to_string()),
            max_depth: Some(3),
            max_nodes: Some(40),
            export: Some("svg".to_string()),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&collection).is_ok());
    }

    #[test]
    fn atlas_query_rejects_unbounded_exports_partial_provider_ids_and_private_categories() {
        let oversized = AtlasQuery {
            title: "Example".to_string(), category: "ANIME".to_string(), max_nodes: Some(41),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&oversized).is_err());
        let partial_provider = AtlasQuery {
            title: "Example".to_string(), category: "ANIME".to_string(), provider: Some("anilist:anime".to_string()),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&partial_provider).is_err());
        let private_category = AtlasQuery {
            title: "Example".to_string(), category: "PRIVATE".to_string(), export: Some("png".to_string()),
            ..AtlasQuery::default()
        };
        assert!(validate_atlas_query(&private_category).is_err());
    }

    #[test]
    fn picker_proxy_forwards_only_required_headers() {
        let mut incoming = HeaderMap::new();
        incoming.insert(header::AUTHORIZATION, "Bearer picker-token".parse().unwrap());
        incoming.insert(header::CONTENT_TYPE, "application/json".parse().unwrap());
        incoming.insert(header::COOKIE, "lemegeton_session=secret".parse().unwrap());
        incoming.insert(header::HOST, "attacker.example".parse().unwrap());
        incoming.insert(header::CONNECTION, "keep-alive".parse().unwrap());
        incoming.insert("x-forwarded-host", "attacker.example".parse().unwrap());
        incoming.insert("x-forwarded-for", "198.51.100.4".parse().unwrap());
        let filtered = picker_forward_headers(&incoming);
        assert_eq!(filtered.get(header::AUTHORIZATION).unwrap(), "Bearer picker-token");
        assert_eq!(filtered.get(header::CONTENT_TYPE).unwrap(), "application/json");
        assert_eq!(filtered.get("x-forwarded-for").unwrap(), "198.51.100.4");
        assert!(!filtered.contains_key(header::COOKIE));
        assert!(!filtered.contains_key(header::HOST));
        assert!(!filtered.contains_key(header::CONNECTION));
        assert!(!filtered.contains_key("x-forwarded-host"));
    }
}

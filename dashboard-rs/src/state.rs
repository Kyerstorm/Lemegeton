use axum::{http::{header, HeaderMap, Method, StatusCode}, response::IntoResponse, Json};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{collections::{HashMap, HashSet, VecDeque}, env, sync::Arc, time::{Duration, SystemTime, UNIX_EPOCH}};
use subtle::ConstantTimeEq;
use tokio::sync::Mutex;
use uuid::Uuid;

pub const DISCORD_API: &str = "https://discord.com/api/v10";
pub const MANAGE_GUILD: u64 = 1 << 5;
pub const ADMINISTRATOR: u64 = 1 << 3;

#[derive(Clone)]
pub struct AppConfig {
    pub client_id: String, pub client_secret: String, pub redirect_uri: String, pub public_origin: String,
    pub bridge_url: String, pub bridge_secret: String, pub picker_url: String, pub bind_host: String,
    pub port: u16, pub secure_cookie: bool, pub session_ttl: u64, pub owner_ids: HashSet<String>, pub static_dir: String,
}
impl AppConfig {
    pub fn from_env() -> Self {
        let port = env::var("DASHBOARD_PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(8080);
        let client_id = env::var("DASHBOARD_CLIENT_ID").or_else(|_| env::var("CLIENT_ID"))
            .or_else(|_| env::var("BOT_ID")).unwrap_or_default();
        let redirect_uri = env::var("DASHBOARD_REDIRECT_URI").unwrap_or_else(|_| format!("http://localhost:{port}/oauth/callback"));
        let public_origin = env::var("DASHBOARD_PUBLIC_URL")
            .unwrap_or_else(|_| redirect_uri.strip_suffix("/oauth/callback").map(ToOwned::to_owned)
                .unwrap_or_else(|| format!("http://localhost:{port}")))
            .trim_end_matches('/').to_string();
        let secure_cookie = env_bool("DASHBOARD_COOKIE_SECURE", redirect_uri.starts_with("https://"));
        let mut owner_ids: HashSet<String> = env::var("DASHBOARD_OWNER_IDS").unwrap_or_default()
            .split(',').map(str::trim).filter(|s| !s.is_empty()).map(ToOwned::to_owned).collect();
        if let Ok(id) = env::var("ADMIN_DISCORD_ID") { if !id.trim().is_empty() { owner_ids.insert(id.trim().to_string()); } }
        Self {
            client_id, client_secret: env::var("DASHBOARD_CLIENT_SECRET").unwrap_or_default(), redirect_uri, public_origin,
            bridge_url: loopback_url(env::var("DASHBOARD_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:8091".to_string()), "http://127.0.0.1:8091"),
            bridge_secret: env::var("DASHBOARD_BRIDGE_SECRET").unwrap_or_default(),
            picker_url: loopback_url(env::var("DASHBOARD_PICKER_URL").unwrap_or_else(|_| "http://127.0.0.1:8092".to_string()), "http://127.0.0.1:8092"),
            bind_host: env::var("DASHBOARD_HOST").unwrap_or_else(|_| "0.0.0.0".to_string()), port,
            secure_cookie,
            session_ttl: env::var("DASHBOARD_SESSION_TTL").ok().and_then(|v| v.parse().ok()).unwrap_or(28_800).max(300),
            owner_ids, static_dir: env::var("DASHBOARD_STATIC_DIR").unwrap_or_else(|_| "web/static".to_string()),
        }
    }
    pub fn oauth_ready(&self) -> bool { !self.client_id.is_empty() && !self.client_secret.is_empty() && !self.redirect_uri.is_empty() }
}
fn loopback_url(value: String, fallback: &str) -> String {
    let allowed = ["http://127.0.0.1:", "http://localhost:", "http://[::1]:"].iter().any(|prefix| {
        value.strip_prefix(*prefix).and_then(|tail| tail.split('/').next())
            .is_some_and(|port| !port.is_empty() && port.bytes().all(|byte| byte.is_ascii_digit()))
    });
    if allowed { value.trim_end_matches('/').to_string() } else { fallback.to_string() }
}
fn env_bool(key: &str, default: bool) -> bool {
    env::var(key).ok().map(|v| matches!(v.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on")).unwrap_or(default)
}
#[derive(Clone, Serialize, Deserialize)]
pub struct DashboardUser { pub id: String, pub username: String, pub global_name: Option<String>, pub avatar: Option<String> }
#[derive(Clone)]
pub struct Session {
    pub user: DashboardUser, pub access_token: String, pub refresh_token: Option<String>,
    pub access_expires_at: u64, pub expires_at: u64, pub csrf: String,
}
#[derive(Clone, Serialize)]
pub struct DashboardGuild { pub id: String, pub name: String, pub icon: Option<String>, pub administrator: bool, pub member_count: Option<u64> }
#[derive(Clone)]
pub struct OAuthState { pub expires_at: u64 }
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>, pub client: reqwest::Client, pub sessions: Arc<Mutex<HashMap<String, Session>>>,
    pub oauth_states: Arc<Mutex<HashMap<String, OAuthState>>>, pub write_limits: Arc<Mutex<HashMap<String, VecDeque<u64>>>>,
    pub last_status: Arc<Mutex<Option<Value>>>,
}
impl AppState {
    pub fn new(config: AppConfig) -> Self {
        let client = reqwest::Client::builder().timeout(Duration::from_secs(12)).connect_timeout(Duration::from_secs(4))
            .redirect(reqwest::redirect::Policy::none()).user_agent("Lemegeton-Dashboard/2.0").build().expect("reqwest client configuration is valid");
        Self { config: Arc::new(config), client, sessions: Arc::new(Mutex::new(HashMap::new())),
            oauth_states: Arc::new(Mutex::new(HashMap::new())), write_limits: Arc::new(Mutex::new(HashMap::new())),
            last_status: Arc::new(Mutex::new(None)) }
    }
}
#[derive(Debug)]
pub struct ApiError { pub status: StatusCode, pub message: String }
impl ApiError {
    pub fn new(status: StatusCode, message: impl Into<String>) -> Self { Self { status, message: message.into() } }
    pub fn unauthorized() -> Self { Self::new(StatusCode::UNAUTHORIZED, "Please sign in with Discord again.") }
    pub fn unavailable() -> Self { Self::new(StatusCode::SERVICE_UNAVAILABLE, "The bot management service is unavailable. Please retry shortly.") }
    pub fn bad_request(message: impl Into<String>) -> Self { Self::new(StatusCode::BAD_REQUEST, message) }
    pub fn forbidden(message: impl Into<String>) -> Self { Self::new(StatusCode::FORBIDDEN, message) }
}
impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response { (self.status, Json(json!({"error":self.message}))).into_response() }
}
pub type ApiResult<T> = Result<T, ApiError>;
pub fn now_secs() -> u64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs() }
pub fn new_token() -> String { format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple()) }
pub fn is_owner(state: &AppState, user_id: &str) -> bool { state.config.owner_ids.contains(user_id) }
pub fn can_manage_guild(permissions: u64, owner: bool) -> bool { owner || permissions & (MANAGE_GUILD | ADMINISTRATOR) != 0 }
pub fn protected_command(name: &str) -> bool { matches!(name, "help" | "feedback") }

pub fn cookie_value(headers: &HeaderMap, key: &str) -> Option<String> {
    headers.get(header::COOKIE)?.to_str().ok()?.split(';').find_map(|pair| {
        let (name, value) = pair.trim().split_once('=')?;
        (name == key && !value.is_empty()).then(|| value.to_string())
    })
}
pub async fn session_from_headers(state: &AppState, headers: &HeaderMap) -> ApiResult<(String, Session)> {
    let id = cookie_value(headers, "lemegeton_session").ok_or_else(ApiError::unauthorized)?;
    let mut sessions = state.sessions.lock().await;
    if sessions.get(&id).map(|s| s.expires_at <= now_secs()).unwrap_or(true) {
        sessions.remove(&id); return Err(ApiError::unauthorized());
    }
    if let Some(session) = sessions.get_mut(&id) {
        session.expires_at = now_secs().saturating_add(state.config.session_ttl);
        return Ok((id, session.clone()));
    }
    Err(ApiError::unauthorized())
}
pub async fn write_session(state: &AppState, headers: &HeaderMap) -> ApiResult<(String, Session)> {
    let (id, session) = session_from_headers(state, headers).await?;
    let origin = headers.get(header::ORIGIN).and_then(|v| v.to_str().ok()).unwrap_or("");
    if origin.trim_end_matches('/') != state.config.public_origin { return Err(ApiError::forbidden("The request origin is not trusted.")); }
    let supplied = headers.get("x-csrf-token").and_then(|v| v.to_str().ok()).unwrap_or("");
    if supplied.is_empty() || supplied.as_bytes().ct_eq(session.csrf.as_bytes()).unwrap_u8() != 1 {
        return Err(ApiError::forbidden("The security token is missing or expired. Refresh the dashboard and try again."));
    }
    let now = now_secs();
    let mut limits = state.write_limits.lock().await;
    let events = limits.entry(id.clone()).or_default();
    while events.front().map(|t| now.saturating_sub(*t) >= 60).unwrap_or(false) { events.pop_front(); }
    if events.len() >= 30 { return Err(ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many changes were submitted. Wait a minute and try again.")); }
    events.push_back(now);
    if limits.len() > 5_000 { limits.retain(|_, values| values.back().map(|t| now.saturating_sub(*t) < 600).unwrap_or(false)); }
    Ok((id, session))
}
pub async fn discord_json(state: &AppState, path: &str, token: &str) -> ApiResult<Value> {
    let response = state.client.get(format!("{DISCORD_API}{path}")).bearer_auth(token).send().await
        .map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "Discord could not be reached. Please retry shortly."))?;
    if !response.status().is_success() { return Err(ApiError::new(StatusCode::UNAUTHORIZED, "Discord authorization expired. Please sign in again.")); }
    response.json::<Value>().await.map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "Discord returned an invalid response."))
}
pub async fn access_token(state: &AppState, session_id: &str) -> ApiResult<String> {
    let snapshot = state.sessions.lock().await.get(session_id).cloned().ok_or_else(ApiError::unauthorized)?;
    if snapshot.expires_at <= now_secs() { return Err(ApiError::unauthorized()); }
    if snapshot.access_expires_at > now_secs().saturating_add(15) { return Ok(snapshot.access_token); }
    let refresh = snapshot.refresh_token.clone().ok_or_else(ApiError::unauthorized)?;
    if !state.config.oauth_ready() { return Err(ApiError::unauthorized()); }
    let response = state.client.post(format!("{DISCORD_API}/oauth2/token"))
        .form(&[("client_id", state.config.client_id.as_str()), ("client_secret", state.config.client_secret.as_str()),
            ("grant_type", "refresh_token"), ("refresh_token", refresh.as_str())])
        .send().await.map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "Discord authorization refresh failed."))?;
    let status = response.status();
    let data = response.json::<Value>().await.unwrap_or(Value::Null);
    if !status.is_success() || data.get("access_token").and_then(Value::as_str).is_none() {
        if let Some(session) = state.sessions.lock().await.get_mut(session_id) { session.access_token.clear(); session.refresh_token = None; }
        return Err(ApiError::unauthorized());
    }
    let token = data["access_token"].as_str().unwrap_or_default().to_string();
    let new_refresh = data.get("refresh_token").and_then(Value::as_str).map(ToOwned::to_owned).or(snapshot.refresh_token);
    let expiry = data.get("expires_in").and_then(Value::as_u64).unwrap_or(3600);
    if let Some(session) = state.sessions.lock().await.get_mut(session_id) {
        session.access_token = token.clone(); session.refresh_token = new_refresh;
        session.access_expires_at = now_secs().saturating_add(expiry.saturating_sub(45).max(30));
    } else { return Err(ApiError::unauthorized()); }
    Ok(token)
}
pub async fn bridge_json(state: &AppState, method: Method, path: &str, body: Option<Value>) -> ApiResult<Value> {
    if state.config.bridge_secret.is_empty() { return Err(ApiError::unavailable()); }
    if !path.starts_with('/') || path.contains("..") { return Err(ApiError::bad_request("Invalid management operation.")); }
    let mut request = state.client.request(method, format!("{}{}", state.config.bridge_url, path))
        .header(header::AUTHORIZATION, format!("Bearer {}", state.config.bridge_secret));
    if let Some(data) = body { request = request.json(&data); }
    let response = request.send().await.map_err(|_| ApiError::unavailable())?;
    let status = response.status();
    let data = response.json::<Value>().await.map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "The bot returned an invalid response."))?;
    if !status.is_success() {
        let message = data.get("error").and_then(Value::as_str).unwrap_or("The bot could not complete this operation.").to_string();
        let safe_status = match status.as_u16() {
            400 => StatusCode::BAD_REQUEST, 401 => StatusCode::SERVICE_UNAVAILABLE, 403 => StatusCode::FORBIDDEN,
            404 => StatusCode::NOT_FOUND, 409 => StatusCode::CONFLICT, 429 => StatusCode::TOO_MANY_REQUESTS,
            502 => StatusCode::BAD_GATEWAY, _ => StatusCode::SERVICE_UNAVAILABLE,
        };
        return Err(ApiError::new(safe_status, message));
    }
    Ok(data)
}
pub async fn manageable_guilds(state: &AppState, session_id: &str, session: &Session) -> ApiResult<Vec<DashboardGuild>> {
    let token = access_token(state, session_id).await?;
    let user_guilds = discord_json(state, "/users/@me/guilds", &token).await?;
    let bot_guilds = bridge_json(state, Method::GET, "/guilds", None).await?;
    let bot_map: HashMap<String, Value> = bot_guilds.as_array().into_iter().flatten()
        .filter_map(|g| g.get("id").and_then(Value::as_str).map(|id| (id.to_string(), g.clone()))).collect();
    let owner = is_owner(state, &session.user.id);
    let mut result = Vec::new();
    for guild in user_guilds.as_array().into_iter().flatten() {
        let id = match guild.get("id").and_then(Value::as_str) { Some(id) => id, None => continue };
        let bot_guild = match bot_map.get(id) { Some(guild) => guild, None => continue };
        let permissions = guild.get("permissions").and_then(Value::as_str).and_then(|v| v.parse::<u64>().ok())
            .or_else(|| guild.get("permissions").and_then(Value::as_u64)).unwrap_or(0);
        let administrator = permissions & ADMINISTRATOR != 0;
        if !can_manage_guild(permissions, owner) { continue; }
        result.push(DashboardGuild { id: id.to_string(),
            name: bot_guild.get("name").and_then(Value::as_str).unwrap_or("Discord server").to_string(),
            icon: bot_guild.get("icon").and_then(Value::as_str).map(ToOwned::to_owned),
            member_count: bot_guild.get("member_count").and_then(Value::as_u64), administrator });
    }
    result.sort_by(|a,b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    Ok(result)
}
pub async fn authorized_guild(state: &AppState, headers: &HeaderMap, guild_id: &str) -> ApiResult<(String, Session, DashboardGuild)> {
    if guild_id.is_empty() || !guild_id.bytes().all(|c| c.is_ascii_digit()) { return Err(ApiError::bad_request("Invalid guild identifier.")); }
    let (id, session) = session_from_headers(state, headers).await?;
    let guilds = manageable_guilds(state, &id, &session).await?;
    let guild = guilds.into_iter().find(|g| g.id == guild_id)
        .ok_or_else(|| ApiError::forbidden("You no longer have permission to manage this server, or the bot is no longer a member."))?;
    Ok((id, session, guild))
}
#[derive(Deserialize)]
pub struct DiscordTokenResponse { pub access_token: Option<String>, pub refresh_token: Option<String>, pub expires_in: Option<u64> }
#[derive(Deserialize)]
pub struct DiscordUserResponse { pub id: String, pub username: String, pub global_name: Option<String>, pub avatar: Option<String> }
#[derive(Deserialize)]
pub struct OAuthCallback { pub code: Option<String>, pub state: Option<String>, pub error: Option<String> }
pub fn token_response_cookie(session_id: &str, state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_session={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age={}{}", state.config.session_ttl, secure)
}
pub fn expired_cookie(state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{}", secure)
}
#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    fn test_state() -> AppState {
        AppState::new(AppConfig {
            client_id: "client".to_string(), client_secret: "secret".to_string(),
            redirect_uri: "https://dashboard.example/oauth/callback".to_string(),
            public_origin: "https://dashboard.example".to_string(),
            bridge_url: "http://127.0.0.1:8091".to_string(), bridge_secret: "bridge".to_string(),
            picker_url: "http://127.0.0.1:8092".to_string(), bind_host: "127.0.0.1".to_string(),
            port: 8080, secure_cookie: true, session_ttl: 3600,
            owner_ids: HashSet::new(), static_dir: "web/static".to_string(),
        })
    }
    fn test_session(csrf: &str, expires_at: u64) -> Session {
        Session {
            user: DashboardUser { id: "123".to_string(), username: "operator".to_string(), global_name: None, avatar: None },
            access_token: "oauth-access-token".to_string(), refresh_token: Some("refresh".to_string()),
            access_expires_at: now_secs() + 600, expires_at, csrf: csrf.to_string(),
        }
    }
    fn session_headers(csrf: Option<&str>, origin: Option<&str>) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(header::COOKIE, HeaderValue::from_static("other=1; lemegeton_session=test-session"));
        if let Some(token) = csrf { headers.insert("x-csrf-token", HeaderValue::from_str(token).unwrap()); }
        if let Some(value) = origin { headers.insert(header::ORIGIN, HeaderValue::from_str(value).unwrap()); }
        headers
    }
    #[test]
    fn protected_commands_cannot_be_unlocked_from_the_dashboard() {
        assert!(protected_command("help"));
        assert!(protected_command("feedback"));
        assert!(!protected_command("browse"));
    }
    #[test]
    fn permission_check_requires_manage_server_admin_or_configured_owner() {
        assert!(!can_manage_guild(0, false));
        assert!(can_manage_guild(MANAGE_GUILD, false));
        assert!(can_manage_guild(ADMINISTRATOR, false));
        assert!(can_manage_guild(0, true));
        assert!(!can_manage_guild(1 << 10, false));
    }
    #[test]
    fn internal_service_targets_cannot_be_repointed_to_public_hosts() {
        let fallback = "http://127.0.0.1:8091";
        assert_eq!(loopback_url("http://127.0.0.1:8091".to_string(), fallback), fallback);
        assert_eq!(loopback_url("http://localhost:8091".to_string(), fallback), "http://localhost:8091");
        assert_eq!(loopback_url("https://attacker.example/steal".to_string(), fallback), fallback);
        assert_eq!(loopback_url("http://127.0.0.1.evil.test:8091".to_string(), fallback), fallback);
    }

    #[test]
    fn cookies_are_parsed_by_exact_name() {
        let headers = session_headers(None, None);
        assert_eq!(cookie_value(&headers, "lemegeton_session").as_deref(), Some("test-session"));
        assert_eq!(cookie_value(&headers, "session").as_deref(), None);
    }
    #[tokio::test]
    async fn writes_require_matching_origin_and_csrf_token() {
        let state = test_state();
        state.sessions.lock().await.insert("test-session".to_string(), test_session("csrf-secret", now_secs() + 600));
        assert!(matches!(write_session(&state, &session_headers(Some("csrf-secret"), None)).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(matches!(write_session(&state, &session_headers(Some("wrong"), Some("https://dashboard.example"))).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(matches!(write_session(&state, &session_headers(Some("csrf-secret"), Some("https://attacker.example"))).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(write_session(&state, &session_headers(Some("csrf-secret"), Some("https://dashboard.example"))).await.is_ok());
    }
    #[tokio::test]
    async fn expired_sessions_are_removed_and_rejected() {
        let state = test_state();
        state.sessions.lock().await.insert("test-session".to_string(), test_session("csrf-secret", now_secs().saturating_sub(1)));
        assert!(matches!(session_from_headers(&state, &session_headers(None, None)).await, Err(e) if e.status == StatusCode::UNAUTHORIZED));
        assert!(!state.sessions.lock().await.contains_key("test-session"));
    }
    #[tokio::test]
    async fn write_rate_limit_rejects_the_31st_change_in_a_minute() {
        let state = test_state();
        state.sessions.lock().await.insert("test-session".to_string(), test_session("csrf-secret", now_secs() + 600));
        let headers = session_headers(Some("csrf-secret"), Some("https://dashboard.example"));
        for _ in 0..30 { assert!(write_session(&state, &headers).await.is_ok()); }
        assert!(matches!(write_session(&state, &headers).await, Err(e) if e.status == StatusCode::TOO_MANY_REQUESTS));
    }
    #[test]
    fn session_cookie_is_http_only_same_site_and_secure_when_configured() {
        let state = test_state();
        let cookie = token_response_cookie("session-id", &state);
        assert!(cookie.contains("HttpOnly"));
        assert!(cookie.contains("SameSite=Lax"));
        assert!(cookie.contains("Secure"));
        assert!(cookie.contains("Max-Age=3600"));
        assert!(expired_cookie(&state).contains("Max-Age=0"));
    }
}

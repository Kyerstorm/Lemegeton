use axum::http::{header, HeaderMap, Method, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{sync::Arc, time::{Duration, SystemTime, UNIX_EPOCH}};
pub use crate::config::AppConfig;
pub use crate::errors::{ApiError, ApiResult};
pub use crate::guilds::{authorized_guild, manageable_guilds};
use subtle::ConstantTimeEq;
use tokio::sync::Mutex;
use crate::store::DashboardStore;
use uuid::Uuid;

pub const DISCORD_API: &str = "https://discord.com/api/v10";
pub const MANAGE_GUILD: u64 = 1 << 5;
pub const ADMINISTRATOR: u64 = 1 << 3;

#[derive(Clone, Serialize, Deserialize)]
pub struct DashboardUser { pub id: String, pub username: String, pub global_name: Option<String>, pub avatar: Option<String> }
#[derive(Clone, Serialize, Deserialize)]
pub struct Session {
    pub user: DashboardUser, pub access_token: String, pub refresh_token: Option<String>,
    pub access_expires_at: u64, pub expires_at: u64, pub csrf: String,
}
#[derive(Clone, Serialize)]
pub struct DashboardGuild {
    pub id: String,
    pub name: String,
    pub icon: Option<String>,
    pub administrator: bool,
    pub member_count: Option<u64>,
    pub bot_installed: bool,
    pub invite_url: Option<String>,
}
#[derive(Clone)]
pub struct OAuthState { pub expires_at: u64, pub browser_nonce: String }
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<AppConfig>,
    pub client: reqwest::Client,
    pub discord_api_base: String,
    pub store: DashboardStore,
    pub last_status: Arc<Mutex<Option<Value>>>,
}
impl AppState {
    pub fn try_new(config: AppConfig) -> Result<Self, String> {
        let store = DashboardStore::open(&config.session_db_path)?;
        let client = reqwest::Client::builder().timeout(Duration::from_secs(12)).connect_timeout(Duration::from_secs(4))
            .redirect(reqwest::redirect::Policy::none()).user_agent("Lemegeton-Dashboard/2.0").build()
            .map_err(|error| format!("Could not configure dashboard HTTP client: {error}"))?;
        Ok(Self { config: Arc::new(config), client, discord_api_base: DISCORD_API.to_string(), store,
            last_status: Arc::new(Mutex::new(None)) })
    }
    #[cfg(test)]
    pub fn new(config: AppConfig) -> Self {
        Self::try_new(config).expect("dashboard state and SQLite session store must initialize")
    }
}
pub fn now_secs() -> u64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs() }
pub fn new_token() -> String { format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple()) }
pub fn is_owner(state: &AppState, user_id: &str) -> bool { state.config.owner_ids.contains(user_id) }
pub fn can_manage_guild(permissions: u64) -> bool { permissions & (MANAGE_GUILD | ADMINISTRATOR) != 0 }
pub fn protected_command(name: &str) -> bool { matches!(name, "help" | "feedback" | "dashboard" | "privacy" | "language") }

pub fn cookie_value(headers: &HeaderMap, key: &str) -> Option<String> {
    headers.get(header::COOKIE)?.to_str().ok()?.split(';').find_map(|pair| {
        let (name, value) = pair.trim().split_once('=')?;
        (name == key && !value.is_empty()).then(|| value.to_string())
    })
}
pub async fn session_from_headers(state: &AppState, headers: &HeaderMap) -> ApiResult<(String, Session)> {
    let id = cookie_value(headers, "lemegeton_session").ok_or_else(ApiError::unauthorized)?;
    let session = state.store.get_session(&id, now_secs(), state.config.session_ttl).await
        .map_err(|_| ApiError::unavailable())?
        .ok_or_else(ApiError::unauthorized)?;
    Ok((id, session))
}
pub async fn write_session(state: &AppState, headers: &HeaderMap) -> ApiResult<(String, Session)> {
    let (id, session) = session_from_headers(state, headers).await?;
    let origin = headers.get(header::ORIGIN).and_then(|v| v.to_str().ok()).unwrap_or("");
    if origin.trim_end_matches('/') != state.config.public_origin { return Err(ApiError::forbidden("The request origin is not trusted.")); }
    let supplied = headers.get("x-csrf-token").and_then(|v| v.to_str().ok()).unwrap_or("");
    if supplied.is_empty() || supplied.as_bytes().ct_eq(session.csrf.as_bytes()).unwrap_u8() != 1 {
        return Err(ApiError::forbidden("The security token is missing or expired. Refresh the dashboard and try again."));
    }
    let allowed = state.store.allow_rate_event("write", &id, now_secs(), 60, 30).await
        .map_err(|_| ApiError::unavailable())?;
    if !allowed { return Err(ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many changes were submitted. Wait a minute and try again.")); }
    Ok((id, session))
}
pub async fn discord_json(state: &AppState, path: &str, token: &str) -> ApiResult<Value> {
    let response = state.client.get(format!("{}{path}", state.discord_api_base.trim_end_matches('/'))).bearer_auth(token).send().await
        .map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "Discord could not be reached. Please retry shortly."))?;
    if !response.status().is_success() { return Err(ApiError::new(StatusCode::UNAUTHORIZED, "Discord authorization expired. Please sign in again.")); }
    response.json::<Value>().await.map_err(|_| ApiError::new(StatusCode::BAD_GATEWAY, "Discord returned an invalid response."))
}
pub async fn access_token(state: &AppState, session_id: &str) -> ApiResult<String> {
    const REFRESH_LEASE_SECONDS: u64 = 30;
    const MAX_WAIT_ATTEMPTS: usize = 50;
    for attempt in 0..=MAX_WAIT_ATTEMPTS {
        let now = now_secs();
        let snapshot = state.store.get_session(session_id, now, state.config.session_ttl).await
            .map_err(|_| ApiError::unavailable())?
            .ok_or_else(ApiError::unauthorized)?;
        if snapshot.access_expires_at > now.saturating_add(15) {
            return Ok(snapshot.access_token);
        }
        let claim = state.store.claim_session_refresh(session_id, now, REFRESH_LEASE_SECONDS).await
            .map_err(|_| ApiError::unavailable())?;
        let Some((snapshot, lease_until)) = claim else {
            if attempt == MAX_WAIT_ATTEMPTS {
                return Err(ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Discord authorization is being refreshed by another dashboard instance. Retry shortly."));
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
            continue;
        };
        let Some(refresh) = snapshot.refresh_token.clone() else {
            state.store.invalidate_refreshed_tokens(session_id, lease_until).await
                .map_err(|_| ApiError::unavailable())?;
            return Err(ApiError::unauthorized());
        };
        if !state.config.oauth_ready() {
            state.store.release_session_refresh(session_id, lease_until).await
                .map_err(|_| ApiError::unavailable())?;
            return Err(ApiError::unauthorized());
        }
        let response = match state.client.post(format!("{DISCORD_API}/oauth2/token"))
            .form(&[("client_id", state.config.client_id.as_str()), ("client_secret", state.config.client_secret.as_str()),
                ("grant_type", "refresh_token"), ("refresh_token", refresh.as_str())])
            .send().await {
                Ok(response) => response,
                Err(_) => {
                    state.store.release_session_refresh(session_id, lease_until).await
                        .map_err(|_| ApiError::unavailable())?;
                    return Err(ApiError::new(StatusCode::BAD_GATEWAY, "Discord authorization refresh failed."));
                }
            };
        let status = response.status();
        let data = response.json::<Value>().await.unwrap_or(Value::Null);
        let token = data.get("access_token").and_then(Value::as_str).filter(|value| !value.is_empty()).map(ToOwned::to_owned);
        if !status.is_success() || token.is_none() {
            state.store.invalidate_refreshed_tokens(session_id, lease_until).await
                .map_err(|_| ApiError::unavailable())?;
            return Err(ApiError::unauthorized());
        }
        let token = token.unwrap_or_default();
        let new_refresh = data.get("refresh_token").and_then(Value::as_str).filter(|value| !value.is_empty())
            .map(ToOwned::to_owned).or(snapshot.refresh_token);
        let expiry = data.get("expires_in").and_then(Value::as_u64).unwrap_or(3600);
        let saved = state.store.save_refreshed_tokens(
            session_id, lease_until, token.clone(), new_refresh,
            now_secs().saturating_add(expiry.saturating_sub(45).max(30)), now_secs(),
        ).await.map_err(|_| ApiError::unavailable())?;
        return if saved { Ok(token) } else { Err(ApiError::unauthorized()) };
    }
    Err(ApiError::unavailable())
}

pub async fn allow_oauth_start(state: &AppState) -> Result<bool, String> {
    state.store.allow_rate_event("oauth", "global", now_secs(), 60, 60).await
}
pub async fn bridge_json(state: &AppState, method: Method, path: &str, body: Option<Value>) -> ApiResult<Value> {
    bridge_json_at(state, &state.config.bridge_url, method, path, body).await
}
pub async fn atlas_bridge_json(state: &AppState, path: &str) -> ApiResult<Value> {
    bridge_json_at(state, &state.config.atlas_bridge_url, Method::GET, path, None).await
}
async fn bridge_json_at(
    state: &AppState,
    base_url: &str,
    method: Method,
    path: &str,
    body: Option<Value>,
) -> ApiResult<Value> {
    if state.config.bridge_secret.len() < 32 { return Err(ApiError::unavailable()); }
    if !path.starts_with('/') || path.contains("..") { return Err(ApiError::bad_request("Invalid management operation.")); }
    let mut request = state.client.request(method, format!("{base_url}{path}"))
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
#[derive(Deserialize)]
pub struct DiscordTokenResponse { pub access_token: Option<String>, pub refresh_token: Option<String>, pub expires_in: Option<u64> }
#[derive(Deserialize)]
pub struct DiscordUserResponse { pub id: String, pub username: String, pub global_name: Option<String>, pub avatar: Option<String> }
#[derive(Deserialize)]
pub struct OAuthCallback { pub code: Option<String>, pub state: Option<String>, pub error: Option<String> }
pub fn oauth_state_cookie(nonce: &str, state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_oauth_state={nonce}; Path=/oauth/callback; HttpOnly; SameSite=Lax; Max-Age=600{secure}")
}
pub fn expired_oauth_state_cookie(state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_oauth_state=; Path=/oauth/callback; HttpOnly; SameSite=Lax; Max-Age=0{secure}")
}
pub fn token_response_cookie(session_id: &str, state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_session={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age={}{}", state.config.session_ttl, secure)
}
pub fn expired_cookie(state: &AppState) -> String {
    let secure = if state.config.secure_cookie { "; Secure" } else { "" };
    format!("lemegeton_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{}", secure)
}
#[cfg(test)]
mod tests;

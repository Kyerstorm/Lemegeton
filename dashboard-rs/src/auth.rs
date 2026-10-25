use axum::{extract::{Query, State}, http::{header, HeaderMap, HeaderValue, StatusCode}, response::{Html, IntoResponse, Redirect, Response}, Json};
use serde_json::{json, Value};
use crate::state::{access_token, cookie_value, manageable_guilds, new_token, now_secs, session_from_headers, token_response_cookie,
    expired_cookie, oauth_state_cookie, expired_oauth_state_cookie, ApiError, ApiResult, AppState, DashboardUser, DiscordTokenResponse, DiscordUserResponse, OAuthCallback, OAuthState, Session, DISCORD_API};
use subtle::ConstantTimeEq;

pub async fn home(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if session_from_headers(&state, &headers).await.is_ok() {
        return match page(&state, "dashboard.html") { Ok(value) => value.into_response(), Err(error) => error.into_response() };
    }
    Redirect::to("/login").into_response()
}
pub async fn login_page(State(state): State<AppState>) -> Response {
    match page(&state, "login.html") { Ok(value) => value.into_response(), Err(error) => error.into_response() }
}
fn page(state: &AppState, name: &str) -> ApiResult<Html<String>> {
    if !matches!(name, "dashboard.html" | "login.html") { return Err(ApiError::new(StatusCode::NOT_FOUND, "Page not found.")); }
    let content = std::fs::read_to_string(std::path::Path::new(&state.config.static_dir).join(name))
        .map_err(|_| ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "The dashboard interface could not be loaded."))?;
    Ok(Html(content))
}
pub async fn oauth_start(State(state): State<AppState>) -> Response {
    if !state.config.oauth_ready() {
        return ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Discord OAuth is not configured. Set DASHBOARD_CLIENT_ID, DASHBOARD_CLIENT_SECRET, and DASHBOARD_REDIRECT_URI.").into_response();
    }
    let state_token = new_token();
    let browser_nonce = new_token();
    {
        let now = now_secs();
        let mut states = state.oauth_states.lock().await;
        states.retain(|_, item| item.expires_at > now);
        if states.len() >= 5_000 { return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many sign-in attempts are pending. Try again shortly.").into_response(); }
        states.insert(state_token.clone(), OAuthState { expires_at: now.saturating_add(600), browser_nonce: browser_nonce.clone() });
    }
    let url = format!("https://discord.com/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope=identify%20guilds&state={}",
        urlencoding::encode(&state.config.client_id), urlencoding::encode(&state.config.redirect_uri), urlencoding::encode(&state_token));
    let mut response = Redirect::to(&url).into_response();
    match HeaderValue::from_str(&oauth_state_cookie(&browser_nonce, &state)) {
        Ok(cookie) => { response.headers_mut().insert(header::SET_COOKIE, cookie); }
        Err(_) => return ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "Could not create a sign-in state cookie.").into_response(),
    }
    response
}
pub async fn oauth_callback(State(state): State<AppState>, headers: HeaderMap, Query(query): Query<OAuthCallback>) -> Response {
    if query.error.is_some() {
        if let Some(value) = query.state.as_deref() { state.oauth_states.lock().await.remove(value); }
        let mut response = Redirect::to("/login?error=cancelled").into_response();
        if let Ok(cookie) = HeaderValue::from_str(&expired_oauth_state_cookie(&state)) {
            response.headers_mut().append(header::SET_COOKIE, cookie);
        }
        return response;
    }
    let code = match query.code { Some(code) if !code.is_empty() && code.len() <= 2_048 => code,
        _ => return ApiError::new(StatusCode::BAD_REQUEST, "Discord sign-in response is invalid. Start sign-in again.").into_response() };
    let state_value = match query.state { Some(value) if !value.is_empty() && value.len() <= 256 => value,
        _ => return ApiError::new(StatusCode::BAD_REQUEST, "Sign-in state is missing. Start sign-in again.").into_response() };
    let saved = state.oauth_states.lock().await.remove(&state_value);
    let browser_nonce = cookie_value(&headers, "lemegeton_oauth_state").unwrap_or_default();
    let state_matches_browser = saved.as_ref().is_some_and(|saved| {
        saved.expires_at > now_secs()
            && !browser_nonce.is_empty()
            && browser_nonce.as_bytes().ct_eq(saved.browser_nonce.as_bytes()).unwrap_u8() == 1
    });
    if !state_matches_browser {
        return ApiError::new(StatusCode::BAD_REQUEST, "Sign-in state expired, belongs to another browser session, or was already used. Start sign-in again.").into_response();
    }
    let response = state.client.post(format!("{DISCORD_API}/oauth2/token")).form(&[
        ("client_id", state.config.client_id.as_str()), ("client_secret", state.config.client_secret.as_str()),
        ("grant_type", "authorization_code"), ("code", code.as_str()), ("redirect_uri", state.config.redirect_uri.as_str()),
    ]).send().await;
    let response = match response { Ok(value) => value, Err(_) => return ApiError::new(StatusCode::BAD_GATEWAY, "Discord sign-in could not be completed. Try again.").into_response() };
    let status = response.status();
    let tokens = match response.json::<DiscordTokenResponse>().await {
        Ok(tokens) if status.is_success() && tokens.access_token.as_ref().is_some_and(|value| !value.is_empty()) => tokens,
        _ => return ApiError::new(StatusCode::UNAUTHORIZED, "Discord sign-in failed. Try again.").into_response(),
    };
    let access = tokens.access_token.unwrap_or_default();
    let response = state.client.get(format!("{DISCORD_API}/users/@me")).bearer_auth(&access).send().await;
    let response = match response {
        Ok(value) if value.status().is_success() => value,
        _ => return ApiError::new(StatusCode::UNAUTHORIZED, "Discord could not verify this account. Try again.").into_response(),
    };
    let user = match response.json::<DiscordUserResponse>().await {
        Ok(user) if !user.id.is_empty() => user,
        _ => return ApiError::new(StatusCode::BAD_GATEWAY, "Discord returned an invalid account response.").into_response(),
    };
    let session_id = new_token();
    let session = Session { user: DashboardUser { id: user.id, username: user.username, global_name: user.global_name, avatar: user.avatar },
        access_token: access, refresh_token: tokens.refresh_token,
        access_expires_at: now_secs().saturating_add(tokens.expires_in.unwrap_or(3600).saturating_sub(45).max(30)),
        expires_at: now_secs().saturating_add(state.config.session_ttl), csrf: new_token() };
    {
        let now = now_secs();
        let mut sessions = state.sessions.lock().await;
        sessions.retain(|_, existing| existing.expires_at > now);
        if sessions.len() >= 5_000 {
            return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many active dashboard sessions. Try again later.").into_response();
        }
        sessions.insert(session_id.clone(), session.clone());
    }
    match manageable_guilds(&state, &session_id, &session).await {
        Ok(guilds) if !guilds.is_empty() => {}
        Ok(_) => {
            state.sessions.lock().await.remove(&session_id);
            return ApiError::new(StatusCode::FORBIDDEN, "No manageable servers found. The bot must be present in a server where your account has Manage Server or Administrator permission.").into_response();
        }
        Err(error) => { state.sessions.lock().await.remove(&session_id); return error.into_response(); }
    }
    let mut response = Redirect::to("/").into_response();
    match HeaderValue::from_str(&token_response_cookie(&session_id, &state)) {
        Ok(value) => { response.headers_mut().insert(header::SET_COOKIE, value); }
        Err(_) => return ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "Could not create a secure session.").into_response(),
    }
    if let Ok(cookie) = HeaderValue::from_str(&expired_oauth_state_cookie(&state)) {
        response.headers_mut().append(header::SET_COOKIE, cookie);
    }
    response
}
pub async fn bootstrap(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let (session_id, session) = session_from_headers(&state, &headers).await?;
    access_token(&state, &session_id).await?;
    let guilds = manageable_guilds(&state, &session_id, &session).await?;
    let selected = guilds.first().map(|guild| guild.id.clone());
    Ok(Json(json!({"user":session.user,"guilds":guilds,"selected_guild_id":selected,"csrf_token":session.csrf})))
}
pub async fn logout(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Response> {
    let (session_id, _) = crate::state::write_session(&state, &headers).await?;
    state.sessions.lock().await.remove(&session_id);
    state.write_limits.lock().await.remove(&session_id);
    let mut response = Json(json!({"ok":true})).into_response();
    let cookie = HeaderValue::from_str(&expired_cookie(&state))
        .map_err(|_| ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "Could not clear the session cookie."))?;
    response.headers_mut().insert(header::SET_COOKIE, cookie);
    Ok(response)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    fn test_state() -> AppState {
        AppState::new(crate::state::AppConfig {
            client_id: String::new(), client_secret: String::new(),
            redirect_uri: "http://localhost:8080/oauth/callback".to_string(),
            public_origin: "http://localhost:8080".to_string(),
            bridge_url: "http://127.0.0.1:8091".to_string(), bridge_secret: String::new(),
            picker_url: "http://127.0.0.1:8092".to_string(), bind_host: "127.0.0.1".to_string(),
            port: 8080, secure_cookie: false, session_ttl: 3600,
            owner_ids: HashSet::new(), static_dir: "web/static".to_string(),
        })
    }
    #[tokio::test]
    async fn oauth_start_is_disabled_when_credentials_are_missing() {
        let response = oauth_start(State(test_state())).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn oauth_callback_rejects_state_from_another_browser_before_network_access() {
        let state = test_state();
        state.oauth_states.lock().await.insert("state-token".to_string(), OAuthState {
            expires_at: now_secs() + 600,
            browser_nonce: "browser-A".to_string(),
        });
        let mut headers = HeaderMap::new();
        headers.insert(header::COOKIE, HeaderValue::from_static("lemegeton_oauth_state=browser-B"));
        let response = oauth_callback(State(state.clone()), headers, Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: Some("state-token".to_string()), error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(!state.oauth_states.lock().await.contains_key("state-token"));
    }

    #[tokio::test]
    async fn oauth_callback_rejects_missing_browser_cookie_before_network_access() {
        let state = test_state();
        state.oauth_states.lock().await.insert("state-token".to_string(), OAuthState {
            expires_at: now_secs() + 600,
            browser_nonce: "browser-A".to_string(),
        });
        let response = oauth_callback(State(state), HeaderMap::new(), Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: Some("state-token".to_string()), error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn oauth_callback_rejects_missing_state_before_network_access() {
        let response = oauth_callback(State(test_state()), Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: None, error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}

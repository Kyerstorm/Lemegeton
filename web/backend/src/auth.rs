use axum::{extract::{Query, State}, http::{header, HeaderMap, HeaderValue, StatusCode}, response::{IntoResponse, Redirect, Response}, Json};
use serde_json::{json, Value};
use crate::ui;
use crate::state::{access_token, allow_oauth_start, cookie_value, is_owner, manageable_guilds, new_token, now_secs, session_from_headers, token_response_cookie,
    expired_cookie, oauth_state_cookie, expired_oauth_state_cookie, ApiError, ApiResult, AppState, DashboardUser, DiscordTokenResponse, DiscordUserResponse, OAuthCallback, OAuthState, Session};
use subtle::ConstantTimeEq;

pub async fn home(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if session_from_headers(&state, &headers).await.is_ok() {
        return ui::dashboard_html().await;
    }
    Redirect::to("/login").into_response()
}
pub async fn login_page() -> Response {
    ui::login_html().await
}
pub async fn oauth_start(State(state): State<AppState>) -> Response {
    if !state.config.oauth_ready() {
        return ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Discord OAuth is not configured. Set DASHBOARD_CLIENT_ID, DASHBOARD_CLIENT_SECRET, and DASHBOARD_REDIRECT_URI.").into_response();
    }
    if !allow_oauth_start(&state).await {
        return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many sign-in attempts. Wait a minute and try again.").into_response();
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
    let response = state.client.post(format!("{}/oauth2/token", state.discord_api_base.trim_end_matches('/'))).form(&[
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
    let response = state.client.get(format!("{}/users/@me", state.discord_api_base.trim_end_matches('/'))).bearer_auth(&access).send().await;
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
        Ok(guilds) if !guilds.is_empty() || is_owner(&state, &session.user.id) => {}
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
    let (session_id, session) = crate::state::write_session(&state, &headers).await?;
    state.sessions.lock().await.remove(&session_id);
    state.write_limits.lock().await.remove(&session_id);

    // Revoke the refresh token after removing the local session. Logout still succeeds if
    // Discord is unreachable; the server-side session is already invalidated.
    let revoke_token = session.refresh_token.as_deref().filter(|value| !value.is_empty())
        .unwrap_or(session.access_token.as_str());
    if state.config.oauth_ready() && !revoke_token.is_empty() {
        let revoke = state.client.post(format!("{}/oauth2/token/revoke", state.discord_api_base.trim_end_matches('/')))
            .form(&[
                ("client_id", state.config.client_id.as_str()),
                ("client_secret", state.config.client_secret.as_str()),
                ("token", revoke_token),
            ]);
        match tokio::time::timeout(std::time::Duration::from_secs(3), revoke.send()).await {
            Ok(Ok(response)) if response.status().is_success() => {}
            _ => tracing::warn!("Discord token revocation failed during dashboard logout; the local session was still invalidated."),
        }
    }

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
    async fn mock_discord_token() -> Json<Value> {
        Json(json!({"access_token":"mock-access-token","refresh_token":"mock-refresh-token","expires_in":3600}))
    }

    async fn mock_discord_user() -> Json<Value> {
        Json(json!({"id":"555555555555555555","username":"acceptance-user","global_name":"Acceptance User","avatar":null}))
    }

    async fn mock_discord_user_guilds() -> Json<Value> {
        Json(json!([
            {"id":"111111111111111111","name":"Manage Server","permissions":"32"},
            {"id":"222222222222222222","name":"Administrator","permissions":"8"},
            {"id":"333333333333333333","name":"No permission","permissions":"0"},
            {"id":"444444444444444444","name":"Bot not installed","permissions":"32"}
        ]))
    }

    async fn mock_bot_guilds() -> Json<Value> {
        Json(json!([
            {"id":"111111111111111111","name":"Manage Server"},
            {"id":"222222222222222222","name":"Administrator"},
            {"id":"333333333333333333","name":"No permission"}
        ]))
    }

    async fn mock_discord_server() -> (String, tokio::task::JoinHandle<()>) {
        use axum::{routing::{get, post}, Router};
        let app = Router::new()
            .route("/oauth2/token", post(mock_discord_token))
            .route("/users/@me", get(mock_discord_user))
            .route("/users/@me/guilds", get(mock_discord_user_guilds))
            .route("/guilds", get(mock_bot_guilds));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap(); });
        (format!("http://{address}"), task)
    }

    #[tokio::test]
    async fn oauth_callback_intersects_manageable_discord_guilds_with_bot_membership() {
        use axum::http::header;
        let (mock_url, server) = mock_discord_server().await;
        let config = crate::state::AppConfig {
            client_id: "acceptance-client".to_string(),
            client_secret: "acceptance-secret".to_string(),
            redirect_uri: "http://localhost:8080/oauth/callback".to_string(),
            public_origin: "http://localhost:8080".to_string(),
            bridge_url: mock_url.clone(),
            atlas_bridge_url: mock_url.clone(),
            bridge_secret: "acceptance-bridge-secret-with-32-bytes".to_string(),
            picker_url: "http://127.0.0.1:8092".to_string(),
            bind_host: "127.0.0.1".to_string(),
            port: 8080,
            secure_cookie: false,
            session_ttl: 3600,
            owner_ids: HashSet::new(),
        };
        let mut state = AppState::new(config);
        state.discord_api_base = mock_url;
        let state = state;

        let start = oauth_start(State(state.clone())).await;
        assert_eq!(start.status(), StatusCode::SEE_OTHER);
        let location = start.headers().get(header::LOCATION).unwrap().to_str().unwrap();
        let authorize_url = reqwest::Url::parse(location).unwrap();
        assert_eq!(authorize_url.scheme(), "https");
        assert_eq!(authorize_url.host_str(), Some("discord.com"));
        assert_eq!(authorize_url.path(), "/oauth2/authorize");
        assert_eq!(authorize_url.query_pairs().find(|(key, _)| key == "client_id").unwrap().1, "acceptance-client");
        assert_eq!(authorize_url.query_pairs().find(|(key, _)| key == "redirect_uri").unwrap().1, "http://localhost:8080/oauth/callback");
        assert_eq!(authorize_url.query_pairs().find(|(key, _)| key == "response_type").unwrap().1, "code");
        assert_eq!(authorize_url.query_pairs().find(|(key, _)| key == "scope").unwrap().1, "identify guilds");
        let oauth_state = authorize_url.query_pairs()
            .find(|(key, _)| key == "state").unwrap().1.to_string();
        assert_eq!(oauth_state.len(), 64);
        assert!(oauth_state.chars().all(|character| character.is_ascii_alphanumeric()));
        let oauth_cookie = start.headers().get(header::SET_COOKIE).unwrap().to_str().unwrap()
            .split(';').next().unwrap().to_string();

        let mut callback_headers = HeaderMap::new();
        callback_headers.insert(header::COOKIE, HeaderValue::from_str(&oauth_cookie).unwrap());
        let callback = oauth_callback(State(state.clone()), callback_headers.clone(), Query(OAuthCallback {
            code: Some("mock-authorization-code".to_string()),
            state: Some(oauth_state.clone()),
            error: None,
        })).await;
        assert_eq!(callback.status(), StatusCode::SEE_OTHER);
        assert_eq!(callback.headers().get(header::LOCATION).unwrap(), "/");
        let session_cookie = callback.headers().get(header::SET_COOKIE).unwrap().to_str().unwrap()
            .split(';').next().unwrap();
        let session_id = session_cookie.strip_prefix("lemegeton_session=").unwrap();
        let mut session_headers = HeaderMap::new();
        session_headers.insert(
            header::COOKIE,
            HeaderValue::from_str(&format!("lemegeton_session={session_id}")).unwrap(),
        );
        let (resolved_session_id, session) = session_from_headers(&state, &session_headers).await.unwrap();
        assert_eq!(resolved_session_id, session_id);
        assert_eq!(session.user.id, "555555555555555555");

        let guilds = manageable_guilds(&state, session_id, &session).await.unwrap();
        assert_eq!(guilds.len(), 2);
        assert!(guilds.iter().any(|guild| guild.id == "111111111111111111" && !guild.administrator));
        assert!(guilds.iter().any(|guild| guild.id == "222222222222222222" && guild.administrator));
        assert!(!guilds.iter().any(|guild| guild.id == "333333333333333333"));
        assert!(!guilds.iter().any(|guild| guild.id == "444444444444444444"));

        assert!(crate::state::authorized_guild(&state, &session_headers, "111111111111111111").await.is_ok());
        assert!(matches!(
            crate::state::authorized_guild(&state, &session_headers, "333333333333333333").await,
            Err(error) if error.status == StatusCode::FORBIDDEN
        ));

        let replay = oauth_callback(State(state.clone()), callback_headers, Query(OAuthCallback {
            code: Some("mock-authorization-code".to_string()),
            state: Some(oauth_state),
            error: None,
        })).await;
        assert_eq!(replay.status(), StatusCode::BAD_REQUEST);
        server.abort();
    }


    fn test_state() -> AppState {
        AppState::new(crate::state::AppConfig {
            client_id: String::new(), client_secret: String::new(),
            redirect_uri: "http://localhost:8080/oauth/callback".to_string(),
            public_origin: "http://localhost:8080".to_string(),
            bridge_url: "http://127.0.0.1:8091".to_string(), atlas_bridge_url: "http://127.0.0.1:8093".to_string(), bridge_secret: String::new(),
            picker_url: "http://127.0.0.1:8092".to_string(), bind_host: "127.0.0.1".to_string(),
            port: 8080, secure_cookie: false, session_ttl: 3600,
            owner_ids: HashSet::new(),
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
        let response = oauth_callback(State(test_state()), HeaderMap::new(), Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: None, error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}

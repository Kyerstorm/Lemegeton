use axum::{extract::{Path, Query, State}, http::{header, HeaderMap, HeaderValue, Method, StatusCode}, response::{IntoResponse, Redirect, Response}, Json};
use serde_json::{json, Value};
use crate::ui;
use crate::state::{access_token, allow_oauth_start, authorized_guild, bridge_json, cookie_value, is_bot_moderator, is_owner, manageable_guilds, new_token, now_secs, session_from_headers, token_response_cookie,
    expired_cookie, expired_legacy_oauth_state_cookie, expired_legacy_session_cookie, oauth_state_cookie_name, oauth_state_cookie, expired_oauth_state_cookie, ApiError, ApiResult, AppState, DashboardUser, DiscordTokenResponse, DiscordUserResponse, OAuthCallback, OAuthState, Session};
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
pub async fn oauth_start(State(state): State<AppState>, headers: HeaderMap) -> Response {
    #[cfg(bla_shield)]
    let _ = std::hint::black_box(crate::bla_shield::enclave_tarpit_0(headers.len() as u32, 0));
    #[cfg(not(bla_shield))]
    crate::touch_bla_shield(headers.len() as u32);
    let origin = headers.get(header::ORIGIN).and_then(|value| value.to_str().ok()).unwrap_or("");
    if origin.trim_end_matches('/') != state.config.public_origin {
        return ApiError::forbidden("The sign-in request origin is not trusted.").into_response();
    }
    if !state.config.oauth_ready() {
        return ApiError::new(StatusCode::SERVICE_UNAVAILABLE, "Discord OAuth is not configured. Set DASHBOARD_CLIENT_ID, DASHBOARD_CLIENT_SECRET, and DASHBOARD_REDIRECT_URI.").into_response();
    }
    match allow_oauth_start(&state).await {
        Ok(true) => {}
        Ok(false) => return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many sign-in attempts. Wait a minute and try again.").into_response(),
        Err(_) => return ApiError::unavailable().into_response(),
    }
    let state_token = new_token();
    let browser_nonce = new_token();
    let oauth_state = OAuthState { expires_at: now_secs().saturating_add(600), browser_nonce: browser_nonce.clone() };
    match state.store.insert_oauth_state(&state_token, &oauth_state, now_secs(), 5_000).await {
        Ok(true) => {}
        Ok(false) => return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many sign-in attempts are pending. Try again shortly.").into_response(),
        Err(_) => return ApiError::unavailable().into_response(),
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
    let shield_seed = (headers.len() as u32)
        .wrapping_add(query.state.as_deref().map_or(0, |value| value.len() as u32))
        .wrapping_add(query.code.as_deref().map_or(0, |value| value.len() as u32));
    #[cfg(bla_shield)]
    let _ = std::hint::black_box(crate::bla_shield::enclave_tarpit_0(shield_seed, 0));
    #[cfg(not(bla_shield))]
    crate::touch_bla_shield(shield_seed);
    if query.error.is_some() {
        if let Some(value) = query.state.as_deref() {
            if state.store.remove_oauth_state(value).await.is_err() { return ApiError::unavailable().into_response(); }
        }
        let mut response = Redirect::to("/login?error=cancelled").into_response();
        if let Ok(cookie) = HeaderValue::from_str(&expired_oauth_state_cookie(&state)) {
            response.headers_mut().append(header::SET_COOKIE, cookie);
        }
        if state.config.secure_cookie {
            if let Ok(cookie) = HeaderValue::from_str(&expired_legacy_oauth_state_cookie(&state)) {
                response.headers_mut().append(header::SET_COOKIE, cookie);
            }
        }
        return response;
    }
    let code = match query.code { Some(code) if !code.is_empty() && code.len() <= 2_048 => code,
        _ => return ApiError::new(StatusCode::BAD_REQUEST, "Discord sign-in response is invalid. Start sign-in again.").into_response() };
    let state_value = match query.state { Some(value) if !value.is_empty() && value.len() <= 256 => value,
        _ => return ApiError::new(StatusCode::BAD_REQUEST, "Sign-in state is missing. Start sign-in again.").into_response() };
    let saved = match state.store.take_oauth_state(&state_value, now_secs()).await {
        Ok(saved) => saved,
        Err(_) => return ApiError::unavailable().into_response(),
    };
    let browser_nonce = cookie_value(&headers, oauth_state_cookie_name(&state))
        .unwrap_or_default();
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
    match state.store.insert_session(&session_id, &session, now_secs(), 5_000).await {
        Ok(true) => {}
        Ok(false) => return ApiError::new(StatusCode::TOO_MANY_REQUESTS, "Too many active dashboard sessions. Try again later.").into_response(),
        Err(_) => return ApiError::unavailable().into_response(),
    }
    let guilds = match manageable_guilds(&state, &session_id, &session).await {
        Ok(guilds) => guilds,
        Err(error) => { let _ = state.store.remove_session(&session_id).await; return error.into_response(); }
    };
    let bot_moderator = match is_bot_moderator(&state, &session.user.id).await {
        Ok(value) => value,
        Err(error) => { let _ = state.store.remove_session(&session_id).await; return error.into_response(); }
    };
    if guilds.is_empty() && !is_owner(&state, &session.user.id) && !bot_moderator {
        let _ = state.store.remove_session(&session_id).await;
        return ApiError::new(StatusCode::FORBIDDEN, "No Discord servers were found where your account has Manage Server or Administrator permission, and this account is not a registered bot moderator.").into_response();
    }
    let consent_path = format!("/users/{}/consent", session.user.id);
    let consent = match bridge_json(&state, Method::GET, &consent_path, None).await {
        Ok(value) => value,
        Err(error) => { let _ = state.store.remove_session(&session_id).await; return error.into_response(); }
    };
    if consent.get("accepted").and_then(Value::as_bool) != Some(true) {
        if let Err(error) = bridge_json(&state, Method::POST, &consent_path, Some(json!({"accepted": true}))).await {
            let _ = state.store.remove_session(&session_id).await;
            return error.into_response();
        }
    }
    let mut response = Redirect::to("/").into_response();
    match HeaderValue::from_str(&token_response_cookie(&session_id, &state)) {
        Ok(value) => { response.headers_mut().insert(header::SET_COOKIE, value); }
        Err(_) => return ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "Could not create a secure session.").into_response(),
    }
    if let Ok(cookie) = HeaderValue::from_str(&expired_oauth_state_cookie(&state)) {
        response.headers_mut().append(header::SET_COOKIE, cookie);
    }
    if state.config.secure_cookie {
        for value in [expired_legacy_oauth_state_cookie(&state), expired_legacy_session_cookie(&state)] {
            if let Ok(cookie) = HeaderValue::from_str(&value) {
                response.headers_mut().append(header::SET_COOKIE, cookie);
            }
        }
    }
    response
}

fn is_dashboard_snowflake(value: &str) -> bool {
    (17..=20).contains(&value.len()) && value.bytes().all(|byte| byte.is_ascii_digit())
}

pub async fn guild_page(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path((user_id, guild_id)): Path<(String, String)>,
) -> Response {
    if !is_dashboard_snowflake(&user_id) || !is_dashboard_snowflake(&guild_id) {
        return ui::not_found_html().await;
    }
    let (_, session) = match session_from_headers(&state, &headers).await {
        Ok(session) => session,
        Err(_) => return Redirect::to("/login").into_response(),
    };
    if session.user.id != user_id {
        return Redirect::to("/login").into_response();
    }
    match authorized_guild(&state, &headers, &guild_id).await {
        Ok(_) => ui::dashboard_html().await,
        Err(error) if error.status == StatusCode::FORBIDDEN => Redirect::to("/").into_response(),
        Err(error) => error.into_response(),
    }
}

pub async fn bootstrap(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Json<Value>> {
    let (session_id, session) = session_from_headers(&state, &headers).await?;
    access_token(&state, &session_id).await?;
    let guilds = manageable_guilds(&state, &session_id, &session).await?;
    let bot_moderator = is_bot_moderator(&state, &session.user.id).await?;
    let selected = guilds.iter().find(|guild| guild.bot_installed).map(|guild| guild.id.clone());
    Ok(Json(json!({"user":session.user,"guilds":guilds,"selected_guild_id":selected,"csrf_token":session.csrf,"bot_moderator":bot_moderator})))
}
pub async fn logout(State(state): State<AppState>, headers: HeaderMap) -> ApiResult<Response> {
    let (session_id, session) = crate::state::write_session(&state, &headers).await?;
    state.store.remove_session(&session_id).await.map_err(|_| ApiError::unavailable())?;


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
    if state.config.secure_cookie {
        let legacy = HeaderValue::from_str(&expired_legacy_session_cookie(&state))
            .map_err(|_| ApiError::new(StatusCode::INTERNAL_SERVER_ERROR, "Could not clear the legacy session cookie."))?;
        response.headers_mut().append(header::SET_COOKIE, legacy);
    }
    Ok(response)
}

#[cfg(test)]
mod tests;

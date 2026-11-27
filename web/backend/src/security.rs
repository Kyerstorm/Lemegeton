use axum::{
    body::Body,
    extract::{ConnectInfo, State},
    http::{header, HeaderValue, Method, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use std::net::SocketAddr;

use crate::{rate_limit::{check_request, RateLimitError}, state::{bridge_json, session_from_headers, token_response_cookie, AppState}};

pub async fn security_headers(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Response {
    let is_picker = request.uri().path().starts_with("/custom-roles");
    let path = request.uri().path().to_string();
    let method = request.method().clone();
    let headers_in = request.headers().clone();
    let peer = request.extensions().get::<ConnectInfo<SocketAddr>>().map(|value| value.0.ip());

    let consent_exempt = matches!(path.as_str(), "/api/bootstrap" | "/api/consent" | "/api/cookies" | "/api/logout");
    let consent_required = (path.starts_with("/api/") && !consent_exempt)
        || path.starts_with("/custom-roles/api/");

    let mut response = match check_request(&state, &path, &method, &headers_in, peer).await {
        Err(RateLimitError::Unavailable) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({"error":"Rate limiting is temporarily unavailable."})),
        ).into_response(),
        Err(RateLimitError::Limited) => {
            let mut response = (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({"error":"Too many requests. Wait a minute and try again."})),
            ).into_response();
            response.headers_mut().insert(header::RETRY_AFTER, "60".parse().unwrap());
            response
        }
        Ok(()) if consent_required => {
            match session_from_headers(&state, &headers_in).await {
                Err(_) => next.run(request).await,
                Ok((_, session)) => {
                    match bridge_json(
                        &state,
                        Method::GET,
                        &format!("/users/{}/consent", session.user.id),
                        None,
                    ).await {
                        Ok(consent) if consent.get("accepted").and_then(serde_json::Value::as_bool) == Some(true) => next.run(request).await,
                        Ok(_) => (
                            StatusCode::PRECONDITION_REQUIRED,
                            Json(serde_json::json!({"error":"Review and accept the current Terms of Service, Privacy Policy and Community Guidelines before using the dashboard."})),
                        ).into_response(),
                        Err(_) => (
                            StatusCode::SERVICE_UNAVAILABLE,
                            Json(serde_json::json!({"error":"The current policy agreement could not be verified. Dashboard access is locked until verification is available."})),
                        ).into_response(),
                    }
                }
            }
        }
        Ok(()) => next.run(request).await,
    };

    if let Ok((session_id, _)) = session_from_headers(&state, &headers_in).await {
        refresh_session_cookie(&mut response, &session_id, &state);
    }

    let headers = response.headers_mut();
    headers.insert("x-content-type-options", "nosniff".parse().unwrap());
    headers.insert("x-frame-options", "DENY".parse().unwrap());
    if !headers.contains_key("referrer-policy") {
        headers.insert("referrer-policy", "no-referrer".parse().unwrap());
    }
    headers.insert("permissions-policy", "camera=(), microphone=(), geolocation=()".parse().unwrap());
    headers.insert("x-permitted-cross-domain-policies", "none".parse().unwrap());
    headers.insert("cross-origin-opener-policy", "same-origin".parse().unwrap());
    headers.insert("cross-origin-resource-policy", "same-origin".parse().unwrap());
    if state.config.secure_cookie {
        headers.insert("strict-transport-security", "max-age=31536000".parse().unwrap());
    }
    if !headers.contains_key("content-security-policy") {
        let policy = if is_picker {
            "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        } else {
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://cdn.discordapp.com; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        };
        headers.insert("content-security-policy", policy.parse().unwrap());
    }
    if !headers.contains_key(header::CACHE_CONTROL) {
        headers.insert(header::CACHE_CONTROL, "no-store".parse().unwrap());
    }
    response
}


fn refresh_session_cookie(response: &mut Response, session_id: &str, state: &AppState) {
    let name = if state.config.secure_cookie {
        "__Host-lemegeton_session"
    } else {
        "lemegeton_session"
    };
    let prefix = format!("{name}=");
    let already_set = response.headers().get_all(header::SET_COOKIE).iter().any(|value| {
        value.to_str().ok().is_some_and(|cookie| cookie.starts_with(&prefix))
    });
    if already_set {
        return;
    }

    if let Ok(cookie) = HeaderValue::from_str(&token_response_cookie(session_id, state)) {
        response.headers_mut().append(header::SET_COOKIE, cookie);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::AppConfig;
    use std::collections::HashSet;

    fn test_state() -> AppState {
        AppState::new(AppConfig {
            client_id: "client".to_string(),
            client_secret: "secret".to_string(),
            redirect_uri: "https://dashboard.example/oauth/callback".to_string(),
            public_origin: "https://dashboard.example".to_string(),
            bridge_url: "http://127.0.0.1:8091".to_string(),
            atlas_bridge_url: "http://127.0.0.1:8093".to_string(),
            bridge_secret: "bridge".to_string(),
            picker_url: "http://127.0.0.1:8092".to_string(),
            bind_host: "127.0.0.1".to_string(),
            port: 8080,
            secure_cookie: true,
            session_ttl: 3600,
            owner_ids: HashSet::new(),
            session_db_path: ":memory:".to_string(),
            legacy_session_db_path: None,
            trusted_proxy_ips: HashSet::new(),
        })
    }

    #[test]
    fn authenticated_session_cookie_refresh_uses_the_configured_security_attributes() {
        let state = test_state();
        let mut response = Response::new(Body::empty());

        refresh_session_cookie(&mut response, "session-id", &state);

        let cookie = response.headers().get(header::SET_COOKIE).unwrap().to_str().unwrap();
        assert!(cookie.starts_with("__Host-lemegeton_session=session-id;"));
        assert!(cookie.contains("HttpOnly"));
        assert!(cookie.contains("Secure"));
        assert!(cookie.contains("SameSite=Lax"));
        assert!(cookie.contains("Max-Age=3600"));
    }

    #[test]
    fn session_refresh_does_not_overwrite_an_explicit_session_cookie() {
        let state = test_state();
        let mut response = Response::new(Body::empty());
        response.headers_mut().append(
            header::SET_COOKIE,
            HeaderValue::from_static("__Host-lemegeton_session=; Path=/; HttpOnly; Secure; Max-Age=0"),
        );

        refresh_session_cookie(&mut response, "session-id", &state);

        let cookies = response.headers().get_all(header::SET_COOKIE).iter().collect::<Vec<_>>();
        assert_eq!(cookies.len(), 1);
        assert!(cookies[0].to_str().unwrap().contains("Max-Age=0"));
    }
}

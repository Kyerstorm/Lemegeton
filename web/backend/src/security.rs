use axum::{
    body::Body,
    extract::{ConnectInfo, State},
    http::{header, Method, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use std::net::SocketAddr;

use crate::{rate_limit::{check_request, RateLimitError}, state::{bridge_json, session_from_headers, AppState}};

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

    let consent_exempt = matches!(path.as_str(), "/api/bootstrap" | "/api/consent" | "/api/logout");
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

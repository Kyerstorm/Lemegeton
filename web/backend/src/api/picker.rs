use axum::{body::{to_bytes, Body}, extract::State, http::{HeaderMap, Method, Request, StatusCode}, response::{IntoResponse, Response}};
use crate::state::{ApiError, AppState};

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
    let request_path = parts.uri.path();
    let path = parts.uri.path_and_query().map(|v| v.as_str()).unwrap_or("/custom-roles");
    if parts.method == Method::GET && (request_path == "/custom-roles" || request_path == "/custom-roles/") {
        return crate::ui::custom_roles_html().await;
    }
    if !request_path.starts_with("/custom-roles/api/") || path.contains("..") {
        return ApiError::new(StatusCode::NOT_FOUND, "Route not found.").into_response();
    }
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

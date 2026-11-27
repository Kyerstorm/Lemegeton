use super::*;
use axum::{body::to_bytes, routing::get, Router};
use tokio::net::TcpListener;
use crate::state::AppConfig;
use axum::http::{header, HeaderMap, HeaderValue};
use std::collections::HashSet;

fn test_state() -> AppState {
    AppState::new(AppConfig {
        client_id: "client".to_string(),
        client_secret: "secret".to_string(),
        redirect_uri: "https://dashboard.example/oauth/callback".to_string(),
        public_origin: "https://dashboard.example".to_string(),
        bridge_url: "http://127.0.0.1:8091".to_string(),
        atlas_bridge_url: "http://127.0.0.1:8093".to_string(),
        bridge_secret: "bridge-secret-with-at-least-thirty-two-characters".to_string(),
        picker_url: "http://127.0.0.1:8092".to_string(),
        bind_host: "127.0.0.1".to_string(),
        port: 8080,
        secure_cookie: true,
        session_ttl: 3600,
        owner_ids: HashSet::new(),
        session_db_path: crate::store::temporary_database_path(),
        legacy_session_db_path: None,
        trusted_proxy_ips: HashSet::new(),
    })
}

#[tokio::test]
async fn cookie_preferences_are_anonymous_persistent_and_http_only() {
    let state = test_state();
    let before = cookie_consent(State(state.clone()), HeaderMap::new()).await.unwrap().0;
    assert_eq!(before["saved"], false);
    assert_eq!(before["remember_server"], false);

    let mut headers = HeaderMap::new();
    headers.insert(header::ORIGIN, HeaderValue::from_static("https://dashboard.example"));
    let response = save_cookie_preferences(
        State(state.clone()),
        headers,
        Json(CookiePreferenceRequest { remember_server: true }),
    ).await.unwrap();

    assert_eq!(response.status(), axum::http::StatusCode::OK);
    let set_cookie = response.headers().get_all(header::SET_COOKIE).iter()
        .filter_map(|value| value.to_str().ok())
        .find(|value| value.starts_with("__Host-lemegeton_cookie_consent=")).unwrap();
    assert!(set_cookie.starts_with("__Host-lemegeton_cookie_consent="));
    assert!(set_cookie.contains("Path=/"));
    assert!(set_cookie.contains("HttpOnly"));
    assert!(set_cookie.contains("SameSite=Lax"));
    assert!(set_cookie.contains("Secure"));
    assert!(set_cookie.contains("Max-Age=15552000"));

    let cookie_pair = set_cookie.split(';').next().unwrap();
    let mut saved_headers = HeaderMap::new();
    saved_headers.insert(header::COOKIE, HeaderValue::from_str(cookie_pair).unwrap());
    let after = cookie_consent(State(state), saved_headers).await.unwrap().0;
    assert_eq!(after["saved"], true);
    assert_eq!(after["remember_server"], true);
    assert_eq!(after["consent_version"], COOKIE_CONSENT_VERSION);
}

#[tokio::test]
async fn secure_cookie_preferences_reject_the_unprefixed_legacy_cookie() {
    let state = test_state();
    let consent_id = "a".repeat(64);
    state.store.save_cookie_consent(
        &consent_id, true, COOKIE_CONSENT_VERSION, now_secs(), COOKIE_CONSENT_TTL,
    ).await.unwrap();

    let mut headers = HeaderMap::new();
    headers.insert(header::COOKIE, HeaderValue::from_str(
        &format!("lemegeton_cookie_consent={consent_id}"),
    ).unwrap());
    let result = cookie_consent(State(state), headers).await.unwrap().0;
    assert_eq!(result["saved"], false);
}

#[tokio::test]
async fn localhost_cookie_preferences_keep_the_unprefixed_cookie_name() {
    let mut config = test_state().config.as_ref().clone();
    config.secure_cookie = false;
    let state = AppState::new(config);
    let consent_id = "b".repeat(64);
    state.store.save_cookie_consent(
        &consent_id, true, COOKIE_CONSENT_VERSION, now_secs(), COOKIE_CONSENT_TTL,
    ).await.unwrap();

    let mut headers = HeaderMap::new();
    headers.insert(header::COOKIE, HeaderValue::from_str(
        &format!("lemegeton_cookie_consent={consent_id}"),
    ).unwrap());
    let result = cookie_consent(State(state), headers).await.unwrap().0;
    assert_eq!(result["saved"], true);
    assert_eq!(result["remember_server"], true);
}

#[tokio::test]
async fn cookie_preference_changes_reject_cross_origin_requests() {
    let mut headers = HeaderMap::new();
    headers.insert(header::ORIGIN, HeaderValue::from_static("https://attacker.example"));
    let error = match save_cookie_preferences(
        State(test_state()),
        headers,
        Json(CookiePreferenceRequest { remember_server: true }),
    ).await {
        Err(error) => error,
        Ok(_) => panic!("cross-origin cookie preferences must be rejected"),
    };
    assert_eq!(error.status, axum::http::StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn public_status_is_read_only_and_exposes_only_safe_health_fields() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let mock = Router::new().route("/health", get(|| async {
        Json(json!({
            "status": "online",
            "ready": true,
            "latency_ms": 42,
            "database": { "status": "online", "latency_ms": 3 },
            "guild_count": 123,
            "command_count": 88,
            "commands": ["private-command"],
            "uptime_seconds": 600,
            "node_version": "v22",
            "bridge_secret": "must-not-leak"
        }))
    }));
    let server = tokio::spawn(async move {
        axum::serve(listener, mock).await.unwrap();
    });

    let mut config = test_state().config.as_ref().clone();
    config.bridge_url = format!("http://{address}");
    let response = public_status(State(AppState::new(config))).await;
    assert_eq!(
        response.headers().get(header::CACHE_CONTROL).unwrap(),
        "no-store",
    );
    let body = to_bytes(response.into_body(), 1024 * 1024).await.unwrap();
    let payload: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(payload["status"], "operational");
    assert_eq!(payload["components"][0]["id"], "dashboard");
    assert_eq!(payload["components"][1]["status"], "operational");
    assert_eq!(payload["components"][2]["latency_ms"], 42);
    assert_eq!(payload["components"][3]["status"], "operational");
    assert!(payload.get("guild_count").is_none());
    assert!(payload.get("commands").is_none());
    assert!(payload.get("uptime_seconds").is_none());
    assert!(!payload.to_string().contains("must-not-leak"));
    assert!(!payload.to_string().contains("private-command"));

    server.abort();
}

use super::*;
use axum::{response::IntoResponse, Json};
use serde_json::json;
use std::collections::HashSet;
    use axum::http::HeaderValue;
    async fn mock_dashboard_bridge(headers: HeaderMap) -> impl IntoResponse {
        let authorized = headers.get(header::AUTHORIZATION)
            .and_then(|value| value.to_str().ok())
            == Some("Bearer acceptance-bridge-secret-0123456789");
        if authorized {
            (StatusCode::OK, Json(json!({"guilds":[{"id":"12345678901234567","name":"Acceptance guild"}]}))).into_response()
        } else {
            (StatusCode::UNAUTHORIZED, Json(json!({"error":"Unauthorized"}))).into_response()
        }
    }

    #[tokio::test]
    async fn rust_dashboard_bridge_authenticates_to_the_node_bridge_with_the_shared_secret() {
        use axum::{routing::get, Router};

        let app = Router::new().route("/guilds", get(mock_dashboard_bridge));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        let mut config = test_state().config.as_ref().clone();
        config.bridge_url = format!("http://{address}");
        config.bridge_secret = "acceptance-bridge-secret-0123456789".to_string();
        let state = AppState::new(config);
        let result = bridge_json(&state, Method::GET, "/guilds", None).await.unwrap();
        assert_eq!(result["guilds"][0]["id"], "12345678901234567");

        let mut incorrect_config = state.config.as_ref().clone();
        incorrect_config.bridge_secret = "incorrect-bridge-secret-0123456789".to_string();
        let unauthorized = bridge_json(&AppState::new(incorrect_config), Method::GET, "/guilds", None)
            .await.unwrap_err();
        assert_eq!(unauthorized.status, StatusCode::SERVICE_UNAVAILABLE);

        server.abort();
    }


    fn test_state() -> AppState {
        AppState::new(AppConfig {
            client_id: "client".to_string(), client_secret: "secret".to_string(),
            redirect_uri: "https://dashboard.example/oauth/callback".to_string(),
            public_origin: "https://dashboard.example".to_string(),
            bridge_url: "http://127.0.0.1:8091".to_string(), atlas_bridge_url: "http://127.0.0.1:8093".to_string(), bridge_secret: "bridge".to_string(),
            picker_url: "http://127.0.0.1:8092".to_string(), bind_host: "127.0.0.1".to_string(),
            port: 8080, secure_cookie: true, session_ttl: 3600,
            owner_ids: HashSet::new(), session_db_path: ":memory:".to_string(), trusted_proxy_ips: HashSet::new(),
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
        assert!(protected_command("dashboard"));
        assert!(protected_command("privacy"));
        assert!(protected_command("language"));
        assert!(!protected_command("browse"));
    }
    #[test]
    fn permission_check_requires_manage_server_admin_or_configured_owner() {
        assert!(!can_manage_guild(0));
        assert!(can_manage_guild(MANAGE_GUILD));
        assert!(can_manage_guild(ADMINISTRATOR));
        assert!(!can_manage_guild(0));
        assert!(!can_manage_guild(1 << 10));
    }
    #[test]
    fn public_configuration_rejects_plain_http_for_non_loopback_hosts() {
        let mut config = test_state().config.as_ref().clone();
        config.public_origin = "http://dashboard.example".to_string();
        config.redirect_uri = "http://dashboard.example/oauth/callback".to_string();
        config.secure_cookie = false;
        assert!(config.validate_public_configuration().is_err());
    }

    #[test]
    fn public_configuration_requires_secure_cookies_for_https() {
        let mut config = test_state().config.as_ref().clone();
        config.secure_cookie = false;
        assert!(config.validate_public_configuration().is_err());
        config.secure_cookie = true;
        assert!(config.validate_public_configuration().is_ok());
    }

    #[test]
    fn callback_must_match_the_exact_public_origin_and_path() {
        let mut config = test_state().config.as_ref().clone();
        config.redirect_uri = "https://attacker.example/oauth/callback".to_string();
        assert!(config.validate_public_configuration().is_err());
        config.redirect_uri = "https://dashboard.example/not-oauth".to_string();
        assert!(config.validate_public_configuration().is_err());
    }

    #[tokio::test]
    async fn oauth_start_rate_limit_blocks_excessive_attempts() {
        let state = test_state();
        for _ in 0..60 {
            assert!(allow_oauth_start(&state).await.unwrap());
        }
        assert!(!allow_oauth_start(&state).await.unwrap());
    }

    #[test]
    fn internal_service_targets_cannot_be_repointed_to_public_hosts() {
        let fallback = "http://127.0.0.1:8091";
        assert_eq!(crate::config::loopback_url("http://127.0.0.1:8091".to_string(), fallback), fallback);
        assert_eq!(crate::config::loopback_url("http://localhost:8091".to_string(), fallback), "http://localhost:8091");
        assert_eq!(crate::config::loopback_url("https://attacker.example/steal".to_string(), fallback), fallback);
        assert_eq!(crate::config::loopback_url("http://127.0.0.1.evil.test:8091".to_string(), fallback), fallback);
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
        state.store.insert_session("test-session", &test_session("csrf-secret", now_secs() + 600), now_secs(), 100).await.unwrap();
        assert!(matches!(write_session(&state, &session_headers(Some("csrf-secret"), None)).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(matches!(write_session(&state, &session_headers(Some("wrong"), Some("https://dashboard.example"))).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(matches!(write_session(&state, &session_headers(Some("csrf-secret"), Some("https://attacker.example"))).await, Err(e) if e.status == StatusCode::FORBIDDEN));
        assert!(write_session(&state, &session_headers(Some("csrf-secret"), Some("https://dashboard.example"))).await.is_ok());
    }
    #[tokio::test]
    async fn expired_sessions_are_removed_and_rejected() {
        let state = test_state();
        state.store.insert_session("test-session", &test_session("csrf-secret", now_secs().saturating_sub(1)), now_secs().saturating_sub(2), 100).await.unwrap();
        assert!(matches!(session_from_headers(&state, &session_headers(None, None)).await, Err(e) if e.status == StatusCode::UNAUTHORIZED));
        assert!(state.store.get_session("test-session", now_secs(), 3600).await.unwrap().is_none());
    }
    #[tokio::test]
    async fn write_rate_limit_rejects_the_31st_change_in_a_minute() {
        let state = test_state();
        state.store.insert_session("test-session", &test_session("csrf-secret", now_secs() + 600), now_secs(), 100).await.unwrap();
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

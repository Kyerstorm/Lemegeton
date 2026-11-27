use super::*;
    use std::collections::HashSet;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static POLICY_ACCEPTANCE_WRITES: AtomicUsize = AtomicUsize::new(0);
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

    async fn mock_bot_moderator() -> Json<Value> {
        Json(json!({"moderator": false}))
    }

    async fn mock_invited_guilds() -> Json<Value> {
        Json(json!({"guild_ids": []}))
    }

    async fn mock_policy_consent() -> Json<Value> {
        Json(json!({"accepted": false}))
    }

    async fn mock_accept_policy_consent() -> Json<Value> {
        POLICY_ACCEPTANCE_WRITES.fetch_add(1, Ordering::SeqCst);
        Json(json!({"accepted": true}))
    }

    async fn mock_discord_server() -> (String, tokio::task::JoinHandle<()>) {
        use axum::{routing::{get, post}, Router};
        let app = Router::new()
            .route("/oauth2/token", post(mock_discord_token))
            .route("/users/@me", get(mock_discord_user))
            .route("/users/@me/guilds", get(mock_discord_user_guilds))
            .route("/guilds", get(mock_bot_guilds))
            .route("/moderators/{user_id}", get(mock_bot_moderator))
            .route("/invited-guilds/{user_id}", get(mock_invited_guilds))
            .route("/users/{user_id}/consent", get(mock_policy_consent).post(mock_accept_policy_consent));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap(); });
        (format!("http://{address}"), task)
    }

    #[tokio::test]
    async fn oauth_callback_lists_manageable_servers_and_records_policy_acceptance() {
        use axum::http::header;
        POLICY_ACCEPTANCE_WRITES.store(0, Ordering::SeqCst);
        let (mock_url, server) = mock_discord_server().await;
        let config = crate::state::AppConfig {
            client_id: "555555555555555555".to_string(),
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
            owner_ids: HashSet::new(), session_db_path: crate::store::temporary_database_path(), legacy_session_db_path: None, trusted_proxy_ips: HashSet::new(),
        };
        let mut state = AppState::new(config);
        state.discord_api_base = mock_url;
        let state = state;

        let mut start_headers = HeaderMap::new();
        start_headers.insert(header::ORIGIN, HeaderValue::from_static("http://localhost:8080"));
        let start = oauth_start(State(state.clone()), start_headers).await;
        assert_eq!(start.status(), StatusCode::SEE_OTHER);
        let location = start.headers().get(header::LOCATION).unwrap().to_str().unwrap();
        let authorize_url = reqwest::Url::parse(location).unwrap();
        assert_eq!(authorize_url.scheme(), "https");
        assert_eq!(authorize_url.host_str(), Some("discord.com"));
        assert_eq!(authorize_url.path(), "/oauth2/authorize");
        assert_eq!(authorize_url.query_pairs().find(|(key, _)| key == "client_id").unwrap().1, "555555555555555555");
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
        assert_eq!(POLICY_ACCEPTANCE_WRITES.load(Ordering::SeqCst), 1);
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
        assert_eq!(guilds.len(), 3);
        assert!(guilds.iter().any(|guild| guild.id == "111111111111111111" && !guild.administrator && guild.bot_installed));
        assert!(guilds.iter().any(|guild| guild.id == "222222222222222222" && guild.administrator && guild.bot_installed));
        assert!(!guilds.iter().any(|guild| guild.id == "333333333333333333"));
        let uninstalled = guilds.iter().find(|guild| guild.id == "444444444444444444").unwrap();
        assert!(!uninstalled.bot_installed);
        assert!(uninstalled.invite_url.as_deref().is_some_and(|url| url.contains("guild_id=444444444444444444")));

        assert!(crate::state::authorized_guild(&state, &session_headers, "111111111111111111").await.is_ok());
        assert!(matches!(
            crate::state::authorized_guild(&state, &session_headers, "333333333333333333").await,
            Err(error) if error.status == StatusCode::FORBIDDEN
        ));
        assert!(matches!(
            crate::state::authorized_guild(&state, &session_headers, "444444444444444444").await,
            Err(error) if error.status == StatusCode::FORBIDDEN && error.message.contains("not installed")
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
            owner_ids: HashSet::new(), session_db_path: crate::store::temporary_database_path(), legacy_session_db_path: None, trusted_proxy_ips: HashSet::new(),
        })
    }
    #[tokio::test]
    async fn oauth_start_is_disabled_when_credentials_are_missing() {
        let mut headers = HeaderMap::new();
        headers.insert(axum::http::header::ORIGIN, HeaderValue::from_static("http://localhost:8080"));
        let response = oauth_start(State(test_state()), headers).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn oauth_start_rejects_cross_origin_requests() {
        let mut headers = HeaderMap::new();
        headers.insert(axum::http::header::ORIGIN, HeaderValue::from_static("https://attacker.example"));
        let response = oauth_start(State(test_state()), headers).await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn secure_oauth_callback_rejects_the_unprefixed_legacy_browser_cookie() {
        let mut config = test_state().config.as_ref().clone();
        config.secure_cookie = true;
        let state = AppState::new(config);
        state.store.insert_oauth_state("state-token", &OAuthState {
            expires_at: now_secs() + 600,
            browser_nonce: "browser-A".to_string(),
        }, now_secs(), 5_000).await.unwrap();

        let mut headers = HeaderMap::new();
        headers.insert(header::COOKIE, HeaderValue::from_static("lemegeton_oauth_state=browser-A"));
        let response = oauth_callback(State(state.clone()), headers, Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: Some("state-token".to_string()), error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(!state.store.has_oauth_state("state-token").await.unwrap());
    }

    #[tokio::test]
    async fn oauth_callback_rejects_state_from_another_browser_before_network_access() {
        let state = test_state();
        state.store.insert_oauth_state("state-token", &OAuthState {
            expires_at: now_secs() + 600,
            browser_nonce: "browser-A".to_string(),
        }, now_secs(), 5_000).await.unwrap();
        let mut headers = HeaderMap::new();
        headers.insert(header::COOKIE, HeaderValue::from_static("lemegeton_oauth_state=browser-B"));
        let response = oauth_callback(State(state.clone()), headers, Query(OAuthCallback {
            code: Some("authorization-code".to_string()), state: Some("state-token".to_string()), error: None,
        })).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(!state.store.has_oauth_state("state-token").await.unwrap());
    }

    #[tokio::test]
    async fn oauth_callback_rejects_missing_browser_cookie_before_network_access() {
        let state = test_state();
        state.store.insert_oauth_state("state-token", &OAuthState {
            expires_at: now_secs() + 600,
            browser_nonce: "browser-A".to_string(),
        }, now_secs(), 5_000).await.unwrap();
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

#[test]
fn dashboard_guild_routes_accept_only_discord_snowflake_identifiers() {
    assert!(is_dashboard_snowflake("12345678901234567"));
    assert!(is_dashboard_snowflake("12345678901234567890"));
    assert!(!is_dashboard_snowflake("api"));
    assert!(!is_dashboard_snowflake("users"));
    assert!(!is_dashboard_snowflake("1234567890123456"));
    assert!(!is_dashboard_snowflake("123456789012345678901"));
    assert!(!is_dashboard_snowflake("1234567890123456x"));
}

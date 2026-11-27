use crate::state::OAuthState;

use super::*;
    use crate::state::{DashboardUser, Session};
    use uuid::Uuid;

    fn temporary_database() -> (String, std::path::PathBuf) {
        let directory = std::env::temp_dir().join(format!("lemegeton-dashboard-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&directory).unwrap();
        (directory.join("sessions.sqlite").to_string_lossy().to_string(), directory)
    }

    fn session() -> Session {
        Session {
            user: DashboardUser {
                id: "123456789012345678".to_string(),
                username: "dashboard-user".to_string(),
                global_name: None,
                avatar: None,
            },
            access_token: "access-token".to_string(),
            refresh_token: Some("refresh-token".to_string()),
            access_expires_at: 101,
            expires_at: 1_000,
            csrf: "csrf-token".to_string(),
        }
    }

    #[tokio::test]
    async fn separate_dashboard_process_stores_share_sessions_oauth_state_and_rate_limits() {
        let (path, directory) = temporary_database();
        let first = DashboardStore::open(&path, None).unwrap();
        let second = DashboardStore::open(&path, None).unwrap();

        assert!(first.insert_session("session-one", &session(), 1, 5).await.unwrap());
        let loaded = second.get_session("session-one", 10, 300).await.unwrap().unwrap();
        assert_eq!(loaded.user.id, "123456789012345678");
        assert_eq!(loaded.expires_at, 310);

        let oauth = OAuthState { expires_at: 600, browser_nonce: "nonce".to_string() };
        assert!(first.insert_oauth_state("one-time-state", &oauth, 1, 5).await.unwrap());
        assert_eq!(second.take_oauth_state("one-time-state", 2).await.unwrap().unwrap().browser_nonce, "nonce");
        assert!(first.take_oauth_state("one-time-state", 2).await.unwrap().is_none());

        for _ in 0..30 {
            assert!(first.allow_rate_event("write", "session-one", 100, 60, 30).await.unwrap());
        }
        assert!(!second.allow_rate_event("write", "session-one", 101, 60, 30).await.unwrap());
        let _ = first.remove_session("session-one").await;
        drop(first);
        drop(second);
        let _ = std::fs::remove_dir_all(directory);
    }

    #[tokio::test]
    async fn only_one_dashboard_instance_can_claim_a_discord_token_refresh() {
        let (path, directory) = temporary_database();
        let first = DashboardStore::open(&path, None).unwrap();
        let second = DashboardStore::open(&path, None).unwrap();
        let mut expired = session();
        expired.access_expires_at = 10;
        assert!(first.insert_session("session-two", &expired, 1, 5).await.unwrap());

        let first_claim = first.claim_session_refresh("session-two", 20, 30).await.unwrap();
        assert!(first_claim.is_some());
        assert!(second.claim_session_refresh("session-two", 21, 30).await.unwrap().is_none());
        let (snapshot, lease) = first_claim.unwrap();
        assert_eq!(snapshot.access_token, "access-token");
        assert!(first.save_refreshed_tokens("session-two", lease, "new-access".to_string(), Some("new-refresh".to_string()), 900, 21).await.unwrap());
        let updated = second.get_session("session-two", 22, 300).await.unwrap().unwrap();
        assert_eq!(updated.access_token, "new-access");
        assert_eq!(updated.refresh_token.as_deref(), Some("new-refresh"));
        assert!(second.claim_session_refresh("session-two", 23, 30).await.unwrap().is_none());
        drop(first);
        drop(second);
        let _ = std::fs::remove_dir_all(directory);
    }

    #[tokio::test]
    async fn session_cap_and_expired_rows_are_enforced_across_instances() {
        let (path, directory) = temporary_database();
        let first = DashboardStore::open(&path, None).unwrap();
        let second = DashboardStore::open(&path, None).unwrap();
        assert!(first.insert_session("expired", &session(), 1, 1).await.unwrap());
        assert!(!second.insert_session("new-session", &session(), 2, 1).await.unwrap());
        assert!(first.insert_session("new-session", &session(), 1_001, 1).await.unwrap());
        assert!(second.get_session("expired", 1_001, 300).await.unwrap().is_none());
        drop(first);
        drop(second);
        let _ = std::fs::remove_dir_all(directory);
    }

    #[tokio::test]
    async fn cookie_preferences_persist_across_dashboard_instances_and_expire() {
        let (path, directory) = temporary_database();
        let first = DashboardStore::open(&path, None).unwrap();
        let second = DashboardStore::open(&path, None).unwrap();

        assert!(first.get_cookie_consent("browser-choice", 100).await.unwrap().is_none());
        first.save_cookie_consent("browser-choice", true, "v1", 100, 100).await.unwrap();

        let saved = second.get_cookie_consent("browser-choice", 150).await.unwrap().unwrap();
        assert!(saved.remember_server);
        assert_eq!(saved.consent_version, "v1");
        assert_eq!(saved.decided_at, 100);
        assert_eq!(saved.expires_at, 200);

        assert!(first.get_cookie_consent("browser-choice", 200).await.unwrap().is_none());
        drop(first);
        drop(second);
        let _ = std::fs::remove_dir_all(directory);
    }

    #[tokio::test]
    async fn legacy_dashboard_database_is_imported_without_deleting_source() {
        use lemegeton_storage::LibSqlStore;
        use libsql::Value;

        let legacy_directory = std::env::temp_dir().join(format!("lemegeton-dashboard-legacy-{}", Uuid::new_v4()));
        let target_directory = std::env::temp_dir().join(format!("lemegeton-dashboard-target-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&legacy_directory).unwrap();
        std::fs::create_dir_all(&target_directory).unwrap();
        let legacy_path = legacy_directory.join("sessions.sqlite");
        let target_path = target_directory.join("bot.db");

        let legacy = LibSqlStore::open(legacy_path.to_str().unwrap()).await.unwrap();
        legacy.execute_batch(
            "CREATE TABLE dashboard_sessions (
                session_id TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at INTEGER NOT NULL,
                access_expires_at INTEGER NOT NULL, refresh_lease_until INTEGER
            );
            CREATE TABLE dashboard_oauth_states (state_token TEXT PRIMARY KEY, browser_nonce TEXT NOT NULL, expires_at INTEGER NOT NULL);
            CREATE TABLE dashboard_rate_events (scope TEXT NOT NULL, subject TEXT NOT NULL, occurred_at INTEGER NOT NULL);
            CREATE TABLE dashboard_cookie_consents (
                consent_id TEXT PRIMARY KEY, remember_server INTEGER NOT NULL, consent_version TEXT NOT NULL,
                decided_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
            );
            INSERT INTO dashboard_oauth_states VALUES ('state-legacy', 'nonce-legacy', 500);
            INSERT INTO dashboard_rate_events VALUES ('write', 'session-legacy', 100);
            INSERT INTO dashboard_cookie_consents VALUES ('consent-legacy', 1, 'v1', 100, 500);"
        ).await.unwrap();
        let mut legacy_session = session();
        legacy_session.expires_at = 500;
        legacy_session.access_expires_at = 400;
        legacy.query(
            "INSERT INTO dashboard_sessions VALUES (?1, ?2, ?3, ?4, ?5)",
            vec![
                Value::Text("session-legacy".to_string()),
                Value::Text(serde_json::to_string(&legacy_session).unwrap()),
                Value::Integer(500),
                Value::Integer(400),
                Value::Null,
            ],
        ).await.unwrap();
        drop(legacy);

        let store = DashboardStore::open(
            target_path.to_str().unwrap(),
            Some(legacy_path.to_str().unwrap()),
        ).unwrap();

        assert!(store.get_session("session-legacy", 200, 600).await.unwrap().is_some());
        assert!(store.take_oauth_state("state-legacy", 200).await.unwrap().is_some());
        assert!(!store.allow_rate_event("write", "session-legacy", 150, 60, 1).await.unwrap());
        assert!(store.get_cookie_consent("consent-legacy", 200).await.unwrap().unwrap().remember_server);
        assert!(legacy_path.is_file());
        store.health().await.unwrap();

        drop(store);
        std::fs::remove_dir_all(legacy_directory).unwrap();
        std::fs::remove_dir_all(target_directory).unwrap();
    }

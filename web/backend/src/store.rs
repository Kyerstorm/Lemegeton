use rusqlite::{params, Connection, OptionalExtension, TransactionBehavior};
use std::{
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};
use crate::state::{OAuthState, Session};

#[derive(Clone)]
pub struct DashboardStore {
    connection: Arc<Mutex<Connection>>,
}

impl DashboardStore {
    pub fn open(path: &str) -> Result<Self, String> {
        if path.trim().is_empty() {
            return Err("DASHBOARD_SESSION_DB_PATH cannot be empty.".to_string());
        }
        if path != ":memory:" {
            let database_path = Path::new(path);
            let parent = database_path.parent()
                .filter(|parent| !parent.as_os_str().is_empty())
                .ok_or_else(|| "The dashboard SQLite database must have a parent directory.".to_string())?;
            std::fs::create_dir_all(parent).map_err(|error| format!("Could not create dashboard SQLite directory: {error}"))?;
            #[cfg(unix)]
            if parent != Path::new(".") {
                use std::os::unix::fs::PermissionsExt;
                std::fs::set_permissions(parent, std::fs::Permissions::from_mode(0o700))
                    .map_err(|error| format!("Could not secure dashboard SQLite directory: {error}"))?;
            }
        }

        if Path::new(path).exists() {
            let metadata = std::fs::symlink_metadata(path)
                .map_err(|error| format!("Could not inspect dashboard SQLite database: {error}"))?;
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err("The dashboard SQLite path must refer to a regular file, not a symlink or directory.".to_string());
            }
        }
        let connection = Connection::open(path).map_err(|error| format!("Could not open dashboard SQLite database: {error}"))?;
        connection.busy_timeout(Duration::from_secs(10))
            .map_err(|error| format!("Could not configure dashboard SQLite lock timeout: {error}"))?;
        connection.pragma_update(None, "journal_mode", "WAL")
            .map_err(|error| format!("Could not enable dashboard SQLite WAL mode: {error}"))?;
        connection.pragma_update(None, "synchronous", "NORMAL")
            .map_err(|error| format!("Could not configure dashboard SQLite durability: {error}"))?;
        connection.pragma_update(None, "foreign_keys", "ON")
            .map_err(|error| format!("Could not enable dashboard SQLite foreign keys: {error}"))?;
        connection.execute_batch(
            "CREATE TABLE IF NOT EXISTS dashboard_sessions (
                session_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                access_expires_at INTEGER NOT NULL,
                refresh_lease_until INTEGER
            );
            CREATE INDEX IF NOT EXISTS dashboard_sessions_expiry_idx
                ON dashboard_sessions (expires_at);
            CREATE TABLE IF NOT EXISTS dashboard_oauth_states (
                state_token TEXT PRIMARY KEY,
                browser_nonce TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS dashboard_oauth_states_expiry_idx
                ON dashboard_oauth_states (expires_at);
            CREATE TABLE IF NOT EXISTS dashboard_rate_events (
                scope TEXT NOT NULL,
                subject TEXT NOT NULL,
                occurred_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS dashboard_rate_events_lookup_idx
                ON dashboard_rate_events (scope, subject, occurred_at);"
        ).map_err(|error| format!("Could not initialize dashboard SQLite schema: {error}"))?;

        if path != ":memory:" {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
                    .map_err(|error| format!("Could not secure dashboard SQLite database permissions: {error}"))?;
            }
        }
        Ok(Self { connection: Arc::new(Mutex::new(connection)) })
    }

    async fn run<T, F>(&self, operation: F) -> Result<T, String>
    where
        T: Send + 'static,
        F: FnOnce(&mut Connection) -> Result<T, String> + Send + 'static,
    {
        let connection = self.connection.clone();
        tokio::task::spawn_blocking(move || {
            let mut connection = connection.lock()
                .map_err(|_| "Dashboard SQLite connection lock is unavailable.".to_string())?;
            operation(&mut connection)
        }).await.map_err(|error| format!("Dashboard SQLite worker failed: {error}"))?
    }

    pub async fn health(&self) -> Result<(), String> {
        self.run(|connection| {
            connection.query_row("SELECT 1", [], |_| Ok(()))
                .map_err(|error| error.to_string())
        }).await
    }

    pub async fn insert_session(
        &self,
        session_id: &str,
        session: &Session,
        now: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let session_id = session_id.to_string();
        let payload = serde_json::to_string(session).map_err(|error| error.to_string())?;
        let expires_at = as_sqlite_integer(session.expires_at);
        let access_expires_at = as_sqlite_integer(session.access_expires_at);
        let now = as_sqlite_integer(now);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_sessions WHERE expires_at <= ?1", [now])
                .map_err(|error| error.to_string())?;
            let count: i64 = transaction.query_row("SELECT COUNT(*) FROM dashboard_sessions", [], |row| row.get(0))
                .map_err(|error| error.to_string())?;
            if count >= maximum as i64 {
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(false);
            }
            transaction.execute(
                "INSERT INTO dashboard_sessions (session_id,payload,expires_at,access_expires_at,refresh_lease_until)
                 VALUES (?1,?2,?3,?4,NULL)
                 ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at,
                   access_expires_at=excluded.access_expires_at, refresh_lease_until=NULL",
                params![session_id, payload, expires_at, access_expires_at],
            ).map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(true)
        }).await
    }

    pub async fn get_session(&self, session_id: &str, now: u64, ttl: u64) -> Result<Option<Session>, String> {
        let session_id = session_id.to_string();
        let next_expiry = as_sqlite_integer(now.saturating_add(ttl));
        let now = as_sqlite_integer(now);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            let payload: Option<String> = transaction.query_row(
                "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND expires_at > ?2",
                params![session_id, now],
                |row| row.get(0),
            ).optional().map_err(|error| error.to_string())?;
            let Some(payload) = payload else {
                transaction.execute("DELETE FROM dashboard_sessions WHERE session_id = ?1 AND expires_at <= ?2",
                    params![session_id, now]).map_err(|error| error.to_string())?;
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(None);
            };
            let mut session: Session = serde_json::from_str(&payload)
                .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
            session.expires_at = next_expiry as u64;
            let updated_payload = serde_json::to_string(&session).map_err(|error| error.to_string())?;
            transaction.execute(
                "UPDATE dashboard_sessions SET expires_at = ?1, payload = ?2 WHERE session_id = ?3 AND expires_at > ?4",
                params![next_expiry, updated_payload, session_id, now],
            ).map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(Some(session))
        }).await
    }

    pub async fn remove_session(&self, session_id: &str) -> Result<(), String> {
        let session_id = session_id.to_string();
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_sessions WHERE session_id = ?1", [&session_id])
                .map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_rate_events WHERE scope = 'write' AND subject = ?1", [&session_id])
                .map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())
        }).await
    }

    pub async fn insert_oauth_state(
        &self,
        state_token: &str,
        state: &OAuthState,
        now: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let state_token = state_token.to_string();
        let browser_nonce = state.browser_nonce.clone();
        let expires_at = as_sqlite_integer(state.expires_at);
        let now = as_sqlite_integer(now);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_oauth_states WHERE expires_at <= ?1", [now])
                .map_err(|error| error.to_string())?;
            let count: i64 = transaction.query_row("SELECT COUNT(*) FROM dashboard_oauth_states", [], |row| row.get(0))
                .map_err(|error| error.to_string())?;
            if count >= maximum as i64 {
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(false);
            }
            transaction.execute(
                "INSERT INTO dashboard_oauth_states (state_token,browser_nonce,expires_at) VALUES (?1,?2,?3)",
                params![state_token, browser_nonce, expires_at],
            ).map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(true)
        }).await
    }

    pub async fn take_oauth_state(&self, state_token: &str, now: u64) -> Result<Option<OAuthState>, String> {
        let state_token = state_token.to_string();
        let now = as_sqlite_integer(now);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            let saved: Option<(String, i64)> = transaction.query_row(
                "SELECT browser_nonce,expires_at FROM dashboard_oauth_states WHERE state_token = ?1",
                [&state_token],
                |row| Ok((row.get(0)?, row.get(1)?)),
            ).optional().map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_oauth_states WHERE state_token = ?1", [&state_token])
                .map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(saved.and_then(|(browser_nonce, expires_at)| (expires_at > now).then_some(OAuthState {
                expires_at: expires_at as u64,
                browser_nonce,
            })))
        }).await
    }

    pub async fn remove_oauth_state(&self, state_token: &str) -> Result<(), String> {
        let state_token = state_token.to_string();
        self.run(move |connection| {
            connection.execute("DELETE FROM dashboard_oauth_states WHERE state_token = ?1", [&state_token])
                .map(|_| ()).map_err(|error| error.to_string())
        }).await
    }

    #[cfg(test)]
    pub async fn has_oauth_state(&self, state_token: &str) -> Result<bool, String> {
        let state_token = state_token.to_string();
        self.run(move |connection| {
            connection.query_row(
                "SELECT EXISTS(SELECT 1 FROM dashboard_oauth_states WHERE state_token = ?1)",
                [&state_token],
                |row| row.get(0),
            ).map_err(|error| error.to_string())
        }).await
    }

    pub async fn allow_rate_event(
        &self,
        scope: &str,
        subject: &str,
        now: u64,
        window_seconds: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let scope = scope.to_string();
        let subject = subject.to_string();
        let now = as_sqlite_integer(now);
        let cutoff = now.saturating_sub(as_sqlite_integer(window_seconds));
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_rate_events WHERE scope = ?1 AND subject = ?2 AND occurred_at <= ?3",
                params![scope, subject, cutoff]).map_err(|error| error.to_string())?;
            transaction.execute("DELETE FROM dashboard_rate_events WHERE occurred_at <= ?1", [now.saturating_sub(86_400)])
                .map_err(|error| error.to_string())?;
            let count: i64 = transaction.query_row(
                "SELECT COUNT(*) FROM dashboard_rate_events WHERE scope = ?1 AND subject = ?2",
                params![scope, subject],
                |row| row.get(0),
            ).map_err(|error| error.to_string())?;
            if count >= maximum as i64 {
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(false);
            }
            transaction.execute(
                "INSERT INTO dashboard_rate_events (scope,subject,occurred_at) VALUES (?1,?2,?3)",
                params![scope, subject, now],
            ).map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(true)
        }).await
    }

    pub async fn claim_session_refresh(
        &self,
        session_id: &str,
        now: u64,
        lease_seconds: u64,
    ) -> Result<Option<(Session, u64)>, String> {
        let session_id = session_id.to_string();
        let now = as_sqlite_integer(now);
        let lease_until = now.saturating_add(as_sqlite_integer(lease_seconds));
        let required_expiry = now.saturating_add(15);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            let claimed = transaction.execute(
                "UPDATE dashboard_sessions SET refresh_lease_until = ?1
                 WHERE session_id = ?2 AND expires_at > ?3 AND access_expires_at <= ?4
                   AND (refresh_lease_until IS NULL OR refresh_lease_until <= ?3)",
                params![lease_until, session_id, now, required_expiry],
            ).map_err(|error| error.to_string())?;
            if claimed == 0 {
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(None);
            }
            let payload: String = transaction.query_row(
                "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND refresh_lease_until = ?2",
                params![session_id, lease_until],
                |row| row.get(0),
            ).map_err(|error| error.to_string())?;
            let session: Session = serde_json::from_str(&payload)
                .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(Some((session, lease_until as u64)))
        }).await
    }

    pub async fn save_refreshed_tokens(
        &self,
        session_id: &str,
        lease_until: u64,
        access_token: String,
        refresh_token: Option<String>,
        access_expires_at: u64,
        now: u64,
    ) -> Result<bool, String> {
        let session_id = session_id.to_string();
        let lease_until = as_sqlite_integer(lease_until);
        let access_expires_at = as_sqlite_integer(access_expires_at);
        let now = as_sqlite_integer(now);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            let payload: Option<String> = transaction.query_row(
                "SELECT payload FROM dashboard_sessions
                 WHERE session_id = ?1 AND refresh_lease_until = ?2 AND expires_at > ?3",
                params![session_id, lease_until, now],
                |row| row.get(0),
            ).optional().map_err(|error| error.to_string())?;
            let Some(payload) = payload else {
                transaction.commit().map_err(|error| error.to_string())?;
                return Ok(false);
            };
            let mut session: Session = serde_json::from_str(&payload)
                .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
            session.access_token = access_token;
            session.refresh_token = refresh_token;
            session.access_expires_at = access_expires_at as u64;
            let payload = serde_json::to_string(&session).map_err(|error| error.to_string())?;
            transaction.execute(
                "UPDATE dashboard_sessions SET payload = ?1, access_expires_at = ?2, refresh_lease_until = NULL
                 WHERE session_id = ?3 AND refresh_lease_until = ?4",
                params![payload, access_expires_at, session_id, lease_until],
            ).map_err(|error| error.to_string())?;
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(true)
        }).await
    }

    pub async fn invalidate_refreshed_tokens(&self, session_id: &str, lease_until: u64) -> Result<(), String> {
        let session_id = session_id.to_string();
        let lease_until = as_sqlite_integer(lease_until);
        self.run(move |connection| {
            let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
                .map_err(|error| error.to_string())?;
            let payload: Option<String> = transaction.query_row(
                "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND refresh_lease_until = ?2",
                params![session_id, lease_until],
                |row| row.get(0),
            ).optional().map_err(|error| error.to_string())?;
            if let Some(payload) = payload {
                let mut session: Session = serde_json::from_str(&payload)
                    .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
                session.access_token.clear();
                session.refresh_token = None;
                session.access_expires_at = 0;
                let updated = serde_json::to_string(&session).map_err(|error| error.to_string())?;
                transaction.execute(
                    "UPDATE dashboard_sessions SET payload = ?1, access_expires_at = 0, refresh_lease_until = NULL
                     WHERE session_id = ?2 AND refresh_lease_until = ?3",
                    params![updated, session_id, lease_until],
                ).map_err(|error| error.to_string())?;
            }
            transaction.commit().map_err(|error| error.to_string())?;
            Ok(())
        }).await
    }

    pub async fn release_session_refresh(&self, session_id: &str, lease_until: u64) -> Result<(), String> {
        let session_id = session_id.to_string();
        let lease_until = as_sqlite_integer(lease_until);
        self.run(move |connection| {
            connection.execute(
                "UPDATE dashboard_sessions SET refresh_lease_until = NULL
                 WHERE session_id = ?1 AND refresh_lease_until = ?2",
                params![session_id, lease_until],
            ).map(|_| ()).map_err(|error| error.to_string())
        }).await
    }
}

fn as_sqlite_integer(value: u64) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

#[cfg(test)]
mod tests {
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
        let first = DashboardStore::open(&path).unwrap();
        let second = DashboardStore::open(&path).unwrap();

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
        let first = DashboardStore::open(&path).unwrap();
        let second = DashboardStore::open(&path).unwrap();
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
        let first = DashboardStore::open(&path).unwrap();
        let second = DashboardStore::open(&path).unwrap();
        assert!(first.insert_session("expired", &session(), 1, 1).await.unwrap());
        assert!(!second.insert_session("new-session", &session(), 2, 1).await.unwrap());
        assert!(first.insert_session("new-session", &session(), 1_001, 1).await.unwrap());
        assert!(second.get_session("expired", 1_001, 300).await.unwrap().is_none());
        drop(first);
        drop(second);
        let _ = std::fs::remove_dir_all(directory);
    }
}

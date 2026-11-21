use rusqlite::Connection;
use std::{
    path::Path,
    sync::{Arc, Mutex},
    time::Duration,
};

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
}

mod oauth;
mod rate_limit;
mod refresh;
mod sessions;
#[cfg(test)]
mod tests;

fn as_sqlite_integer(value: u64) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

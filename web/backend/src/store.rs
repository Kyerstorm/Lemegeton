use lemegeton_storage::LibSqlStore;
use libsql::Value;
use serde_json::Value as JsonValue;
use std::{path::Path, sync::Arc};

#[derive(Clone)]
pub struct DashboardStore {
    database: Arc<LibSqlStore>,
}

impl DashboardStore {
    pub fn open(path: &str, legacy_path: Option<&str>) -> Result<Self, String> {
        if path.trim().is_empty() || path.contains("://") {
            return Err("LIBSQL_PATH must be a non-empty local database file path.".to_string());
        }

        let path = path.to_string();
        let legacy_path = legacy_path
            .map(str::trim)
            .filter(|legacy| !legacy.is_empty() && *legacy != path)
            .map(ToOwned::to_owned);

        let database = std::thread::spawn(move || {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .map_err(|error| format!("Could not initialize the dashboard libSQL runtime: {error}"))?;
            runtime.block_on(async move {
                let database = LibSqlStore::open(&path).await?;
                database.execute_batch(
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
                        ON dashboard_rate_events (scope, subject, occurred_at);
                    CREATE TABLE IF NOT EXISTS dashboard_cookie_consents (
                        consent_id TEXT PRIMARY KEY,
                        remember_server INTEGER NOT NULL CHECK (remember_server IN (0, 1)),
                        consent_version TEXT NOT NULL,
                        decided_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS dashboard_cookie_consents_expiry_idx
                        ON dashboard_cookie_consents (expires_at);
                    CREATE TABLE IF NOT EXISTS dashboard_storage_migrations (
                        source_path TEXT PRIMARY KEY,
                        migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );"
                ).await?;

                if let Some(old_path) = legacy_path.filter(|candidate| Path::new(candidate).is_file()) {
                    migrate_legacy_database(&database, &old_path).await?;
                }

                let integrity = database.integrity_check().await?;
                if integrity != "ok" {
                    return Err(format!("Dashboard libSQL integrity check failed: {integrity}"));
                }
                Ok(database)
            })
        })
        .join()
        .map_err(|_| "The dashboard libSQL initialization worker panicked.".to_string())??;

        Ok(Self { database: Arc::new(database) })
    }

    pub async fn health(&self) -> Result<(), String> {
        let result = self.database.query("SELECT 1 AS healthy", Vec::new()).await?;
        if result.rows.first().and_then(|row| row.get("healthy")).and_then(JsonValue::as_i64) == Some(1) {
            Ok(())
        } else {
            Err("Dashboard libSQL health check returned an unexpected result.".to_string())
        }
    }
}

async fn migrate_legacy_database(database: &LibSqlStore, legacy_path: &str) -> Result<(), String> {
    let migrated = database.query(
        "SELECT source_path FROM dashboard_storage_migrations WHERE source_path = ?1",
        vec![Value::Text(legacy_path.to_string())],
    ).await?;
    if !migrated.rows.is_empty() {
        return Ok(());
    }

    let legacy = LibSqlStore::open(legacy_path).await?;
    let tables = [
        ("dashboard_sessions", "session_id,payload,expires_at,access_expires_at,refresh_lease_until"),
        ("dashboard_oauth_states", "state_token,browser_nonce,expires_at"),
        ("dashboard_rate_events", "scope,subject,occurred_at"),
        ("dashboard_cookie_consents", "consent_id,remember_server,consent_version,decided_at,expires_at"),
    ];
    let transaction = database.begin().await?;
    for (table, columns) in tables {
        let exists = legacy.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?1",
            vec![Value::Text(table.to_string())],
        ).await?;
        if exists.rows.is_empty() {
            continue;
        }

        let rows = legacy.query(&format!("SELECT {columns} FROM {table}"), Vec::new()).await?;
        let column_names: Vec<&str> = columns.split(',').collect();
        let placeholders = (1..=column_names.len())
            .map(|index| format!("?{index}"))
            .collect::<Vec<_>>()
            .join(",");
        let insert = format!("INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})");
        for row in rows.rows {
            let parameters = column_names.iter()
                .map(|column| json_to_value(row.get(*column).unwrap_or(&JsonValue::Null)))
                .collect();
            transaction.query(&insert, parameters).await?;
        }
    }
    transaction.query(
        "INSERT OR IGNORE INTO dashboard_storage_migrations (source_path) VALUES (?1)",
        vec![Value::Text(legacy_path.to_string())],
    ).await?;
    transaction.commit().await?;
    Ok(())
}

fn json_to_value(value: &JsonValue) -> Value {
    match value {
        JsonValue::Null => Value::Null,
        JsonValue::Bool(value) => Value::Integer(if *value { 1 } else { 0 }),
        JsonValue::Number(value) => value.as_i64().map(Value::Integer)
            .or_else(|| value.as_f64().map(Value::Real)).unwrap_or(Value::Null),
        JsonValue::String(value) => Value::Text(value.clone()),
        JsonValue::Array(_) | JsonValue::Object(_) => {
            Value::Text(serde_json::to_string(value).unwrap_or_default())
        }
    }
}

pub(super) fn as_sqlite_integer(value: u64) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

pub(super) fn text(value: impl Into<String>) -> Value {
    Value::Text(value.into())
}

pub(super) fn integer(value: i64) -> Value {
    Value::Integer(value)
}

pub(super) fn bool_field(row: &serde_json::Map<String, JsonValue>, name: &str) -> Result<bool, String> {
    match row.get(name) {
        Some(JsonValue::Bool(value)) => Ok(*value),
        Some(JsonValue::Number(value)) => value.as_i64().map(|value| value != 0)
            .ok_or_else(|| format!("Dashboard libSQL result is missing boolean column '{name}'.")),
        _ => Err(format!("Dashboard libSQL result is missing boolean column '{name}'.")),
    }
}

pub(super) fn string_field(row: &serde_json::Map<String, JsonValue>, name: &str) -> Result<String, String> {
    let value = row.get(name)
        .ok_or_else(|| format!("Dashboard libSQL result is missing column '{name}'."))?;
    match value {
        JsonValue::String(value) => Ok(value.clone()),
        JsonValue::Object(_) | JsonValue::Array(_) => serde_json::to_string(value)
            .map_err(|error| format!("Could not serialize dashboard column '{name}': {error}")),
        _ => Err(format!("Dashboard libSQL result column '{name}' is not text.")),
    }
}

pub(super) fn integer_field(row: &serde_json::Map<String, JsonValue>, name: &str) -> Result<i64, String> {
    row.get(name).and_then(JsonValue::as_i64)
        .ok_or_else(|| format!("Dashboard libSQL result is missing integer column '{name}'."))
}

mod cookies;
mod oauth;
mod rate_limit;
mod refresh;
mod sessions;
#[cfg(test)]
mod tests;

#[cfg(test)]
pub(crate) fn temporary_database_path() -> String {
    std::env::temp_dir()
        .join(format!("lemegeton-dashboard-test-{}", uuid::Uuid::new_v4()))
        .join("dashboard.sqlite")
        .to_string_lossy()
        .into_owned()
}

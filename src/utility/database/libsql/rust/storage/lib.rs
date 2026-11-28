use libsql::{params_from_iter, Builder, Connection, Database, Transaction, TransactionBehavior, Value};
use serde_json::{Map, Number, Value as JsonValue};
use std::{collections::HashMap, path::Path, sync::{Arc, Mutex}};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

#[cfg(bla_shield)]
mod bla_shield;

fn run_bla_shield() {
    #[cfg(bla_shield)]
    let _ = std::hint::black_box(bla_shield::enclave_tarpit_0(std::process::id(), 0));
}

#[derive(Clone, Debug)]
pub struct QueryResult {
    pub rows: Vec<Map<String, JsonValue>>,
    pub row_count: u64,
    pub last_insert_rowid: String,
}

const CONNECTION_POOL_SIZE: usize = 8;

struct ConnectionPool {
    database: Database,
    idle: Mutex<Vec<Connection>>,
    permits: Arc<Semaphore>,
}

struct PooledConnection {
    pool: Arc<ConnectionPool>,
    connection: Option<Connection>,
    _permit: OwnedSemaphorePermit,
}

impl ConnectionPool {
    async fn acquire(self: &Arc<Self>) -> Result<PooledConnection, String> {
        let permit = Arc::clone(&self.permits)
            .acquire_owned()
            .await
            .map_err(|_| "The libSQL connection pool is unavailable.".to_string())?;
        let idle = self.idle.lock()
            .map_err(|_| "The libSQL connection pool is unavailable.".to_string())?
            .pop();
        let connection = match idle {
            Some(connection) => connection,
            None => {
                let connection = self.database.connect().map_err(|error| error.to_string())?;
                configure_connection(&connection).await?;
                connection
            }
        };
        Ok(PooledConnection {
            pool: Arc::clone(self),
            connection: Some(connection),
            _permit: permit,
        })
    }
}

impl PooledConnection {
    fn connection(&self) -> &Connection {
        self.connection.as_ref().expect("a checked-out connection remains available until it is returned")
    }
}

impl Drop for PooledConnection {
    fn drop(&mut self) {
        if let Some(connection) = self.connection.take() {
            if let Ok(mut idle) = self.pool.idle.lock() {
                idle.push(connection);
            }
        }
    }
}

pub struct LibSqlStore {
    pool: Arc<ConnectionPool>,
}

pub struct LibSqlTransaction {
    transaction: Transaction,
    _connection: PooledConnection,
}

#[cfg(unix)]
fn ensure_shared_permissions(path: &Path, expected_mode: u32, description: &str) -> Result<(), String> {
    use std::io::ErrorKind;
    use std::os::unix::fs::PermissionsExt;

    match std::fs::set_permissions(path, std::fs::Permissions::from_mode(expected_mode)) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == ErrorKind::PermissionDenied => {
            let metadata = std::fs::metadata(path)
                .map_err(|metadata_error| format!("Could not inspect {description}: {metadata_error}"))?;
            let actual_mode = metadata.permissions().mode() & 0o7777;
            if actual_mode == expected_mode {
                Ok(())
            } else {
                Err(format!(
                    "The shared {description} must have mode {expected_mode:o}; current mode is {actual_mode:o}. Configure the shared data group and permissions before starting both services."
                ))
            }
        }
        Err(error) => Err(format!("Could not secure {description}: {error}")),
    }
}

impl LibSqlStore {
    pub async fn open(path: &str) -> Result<Self, String> {
        run_bla_shield();
        if path.trim().is_empty() || path.contains("://") {
            return Err("LIBSQL_PATH must be a non-empty local database file path.".to_string());
        }
        if path != ":memory:" {
            let database_path = Path::new(path);
            if let Some(parent) = database_path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
                std::fs::create_dir_all(parent)
                    .map_err(|error| format!("Could not create the libSQL directory: {error}"))?;
                #[cfg(unix)]
                ensure_shared_permissions(parent, 0o2770, "libSQL directory")?;
            }
            if database_path.exists() {
                let metadata = std::fs::symlink_metadata(database_path)
                    .map_err(|error| format!("Could not inspect the libSQL database path: {error}"))?;
                if metadata.file_type().is_symlink() || !metadata.is_file() {
                    return Err("LIBSQL_PATH must refer to a regular database file, not a symlink or directory.".to_string());
                }
                #[cfg(unix)]
                ensure_shared_permissions(database_path, 0o660, "libSQL database file")?;
            }
        }

        let database = Builder::new_local(path)
            .build()
            .await
            .map_err(|error| format!("Could not open the libSQL database: {error}"))?;
        let store = Self {
            pool: Arc::new(ConnectionPool {
                database,
                idle: Mutex::new(Vec::new()),
                permits: Arc::new(Semaphore::new(CONNECTION_POOL_SIZE)),
            }),
        };
        let connection = store.pool.acquire().await?;
        let mut journal_mode = connection.connection().query("PRAGMA journal_mode = WAL", ())
            .await.map_err(|error| format!("Could not enable libSQL WAL mode: {error}"))?;
        while journal_mode.next().await
            .map_err(|error| format!("Could not confirm libSQL WAL mode: {error}"))?.is_some() {}

        if path != ":memory:" {
            #[cfg(unix)]
            ensure_shared_permissions(Path::new(path), 0o660, "libSQL database file")?;
        }
        Ok(store)
    }

    pub async fn connect(&self) -> Result<Connection, String> {
        let connection = self.pool.database.connect().map_err(|error| error.to_string())?;
        configure_connection(&connection).await?;
        Ok(connection)
    }

    pub async fn query(&self, sql: &str, params: Vec<Value>) -> Result<QueryResult, String> {
        let connection = self.pool.acquire().await?;
        query_connection(connection.connection(), sql, params).await
    }

    pub async fn execute_batch(&self, sql: &str) -> Result<(), String> {
        let connection = self.pool.acquire().await?;
        connection.connection().execute_transactional_batch(sql).await
            .map(|_| ())
            .map_err(|error| error.to_string())
    }

    pub async fn begin(&self) -> Result<LibSqlTransaction, String> {
        let connection = self.pool.acquire().await?;
        let transaction = connection.connection().transaction_with_behavior(TransactionBehavior::Immediate)
            .await.map_err(|error| error.to_string())?;
        Ok(LibSqlTransaction { transaction, _connection: connection })
    }

    pub async fn backup_to(&self, destination: &str) -> Result<(), String> {
        if destination.trim().is_empty() || destination == ":memory:" {
            return Err("A local libSQL backup destination is required.".to_string());
        }
        let target = Path::new(destination);
        if target.exists() {
            return Err("The libSQL backup destination already exists.".to_string());
        }
        if let Some(parent) = target.parent().filter(|parent| !parent.as_os_str().is_empty()) {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("Could not create the libSQL backup directory: {error}"))?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                std::fs::set_permissions(parent, std::fs::Permissions::from_mode(0o700))
                    .map_err(|error| format!("Could not secure the libSQL backup directory: {error}"))?;
            }
        }
        let connection = self.pool.acquire().await?;
        connection.connection().execute("VACUUM INTO ?1", [destination])
            .await.map_err(|error| format!("Could not create the libSQL snapshot: {error}"))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(target, std::fs::Permissions::from_mode(0o600))
                .map_err(|error| format!("Could not secure the libSQL backup file: {error}"))?;
        }
        Ok(())
    }

    pub async fn inspect(&self) -> Result<(String, u64), String> {
        let integrity = self.integrity_check().await?;
        let tables = self.query(
            "SELECT COUNT(*) AS table_count FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'",
            Vec::new(),
        ).await?;
        let table_count = tables.rows.first()
            .and_then(|row| row.get("table_count"))
            .and_then(JsonValue::as_i64)
            .unwrap_or(0)
            .max(0) as u64;
        Ok((integrity, table_count))
    }

    pub async fn integrity_check(&self) -> Result<String, String> {
        let connection = self.pool.acquire().await?;
        let mut rows = connection.connection().query("PRAGMA integrity_check", ())
            .await.map_err(|error| error.to_string())?;
        let mut checks = Vec::new();
        while let Some(row) = rows.next().await.map_err(|error| error.to_string())? {
            checks.push(row.get::<String>(0).map_err(|error| error.to_string())?);
        }
        if checks.is_empty() {
            return Err("libSQL integrity_check returned no result.".to_string());
        }
        Ok(checks.join("; "))
    }
}

async fn configure_connection(connection: &Connection) -> Result<(), String> {
    connection.busy_timeout(std::time::Duration::from_secs(10))
        .map_err(|error| format!("Could not configure the libSQL lock timeout: {error}"))?;
    connection.execute("PRAGMA foreign_keys = ON", ()).await
        .map_err(|error| format!("Could not enable libSQL foreign keys: {error}"))?;
    connection.execute("PRAGMA synchronous = NORMAL", ()).await
        .map_err(|error| format!("Could not configure libSQL durability: {error}"))?;
    Ok(())
}

impl LibSqlTransaction {
    pub async fn query(&self, sql: &str, params: Vec<Value>) -> Result<QueryResult, String> {
        query_connection(&self.transaction, sql, params).await
    }

    pub async fn commit(self) -> Result<(), String> {
        self.transaction.commit().await.map_err(|error| error.to_string())
    }

    pub async fn rollback(self) -> Result<(), String> {
        self.transaction.rollback().await.map_err(|error| error.to_string())
    }
}

async fn query_connection(
    connection: &Connection,
    sql: &str,
    params: Vec<Value>,
) -> Result<QueryResult, String> {
    let statement = connection.prepare(sql).await.map_err(|error| error.to_string())?;
    if statement.columns().is_empty() {
        let changed = statement.execute(params_from_iter(params)).await
            .map_err(|error| error.to_string())?;
        return Ok(QueryResult {
            rows: Vec::new(),
            row_count: u64::try_from(changed).unwrap_or(u64::MAX),
            last_insert_rowid: connection.last_insert_rowid().to_string(),
        });
    }

    let mut result = statement.query(params_from_iter(params)).await
        .map_err(|error| error.to_string())?;
    let mut output = Vec::new();
    let column_count = result.column_count();
    while let Some(row) = result.next().await.map_err(|error| error.to_string())? {
        let mut object = Map::new();
        for index in 0..column_count {
            let Some(name) = result.column_name(index).map(str::to_string) else {
                continue;
            };
            let value = row.get_value(index).map_err(|error| error.to_string())?;
            object.insert(name.clone(), value_to_json(value, &name));
        }
        output.push(object);
    }
    Ok(QueryResult {
        row_count: output.len() as u64,
        rows: output,
        last_insert_rowid: connection.last_insert_rowid().to_string(),
    })
}

fn value_to_json(value: Value, column: &str) -> JsonValue {
    match value {
        Value::Null => JsonValue::Null,
        Value::Integer(value) => {
            if is_identifier_column(column) {
                JsonValue::String(value.to_string())
            } else if is_boolean_column(column) {
                JsonValue::Bool(value != 0)
            } else {
                Number::from(value).into()
            }
        }
        Value::Real(value) => Number::from_f64(value).map(JsonValue::Number).unwrap_or(JsonValue::Null),
        Value::Text(value) => {
            if is_json_column(column) {
                serde_json::from_str(&value).unwrap_or(JsonValue::String(value))
            } else {
                JsonValue::String(value)
            }
        }
        Value::Blob(value) => {
            let mut object = Map::new();
            object.insert("$blob".to_string(), JsonValue::Array(
                value.into_iter().map(|byte| JsonValue::Number(Number::from(byte))).collect()
            ));
            JsonValue::Object(object)
        }
    }
}

fn is_identifier_column(column: &str) -> bool {
    matches!(column, "id" | "guild_id" | "user_id" | "discord_id" | "channel_id"
        | "message_id" | "role_id" | "actor_id" | "created_by" | "updated_by"
        | "added_by" | "reviewed_by" | "submitted_by" | "uploaded_by" | "invited_by"
        | "interaction_id" | "session_id" | "pack_id" | "question_id" | "nomination_id"
        | "target_id" | "source_id" | "media_asset_id" | "icon_source_asset_id")
        || column.ends_with("_id")
}

fn is_boolean_column(column: &str) -> bool {
    matches!(column, "enabled" | "active" | "visible" | "is_private" | "is_correct"
        | "remember_server" | "administrator" | "can_manage_server" | "verified"
        | "allow_uploads" | "include_anime" | "include_manga" | "include_movies"
        | "include_tv" | "include_games" | "is_global" | "is_public" | "required")
        || column.starts_with("is_")
        || column.starts_with("has_")
        || column.starts_with("include_")
        || column.starts_with("allow_")
}

fn is_json_column(column: &str) -> bool {
    matches!(column, "details" | "options" | "clues" | "snapshot" | "payload"
        | "user_ids" | "accepted_answers" | "allowed_role_ids" | "blocked_words"
        | "removed_default_words" | "categories" | "entity_types" | "entity_ids" | "providers" | "seen_ids"
        | "metadata" | "config" | "settings" | "channels"
        | "roles" | "permissions" | "question_ids" | "provider_data")
}

pub fn json_params(params: JsonValue) -> Result<Vec<Value>, String> {
    let values = params.as_array()
        .ok_or_else(|| "Database parameters must be a JSON array.".to_string())?;
    values.iter().map(json_to_sql_value).collect()
}

fn json_to_sql_value(value: &JsonValue) -> Result<Value, String> {
    match value {
        JsonValue::Null => Ok(Value::Null),
        JsonValue::Bool(value) => Ok(Value::Integer(if *value { 1 } else { 0 })),
        JsonValue::Number(value) => {
            if let Some(integer) = value.as_i64() {
                Ok(Value::Integer(integer))
            } else if let Some(unsigned) = value.as_u64() {
                Ok(i64::try_from(unsigned).map(Value::Integer)
                    .unwrap_or_else(|_| Value::Text(unsigned.to_string())))
            } else {
                value.as_f64().map(Value::Real)
                    .ok_or_else(|| "Unsupported numeric database parameter.".to_string())
            }
        }
        JsonValue::String(value) => Ok(Value::Text(value.clone())),
        JsonValue::Array(_) => Ok(Value::Text(
            serde_json::to_string(value).map_err(|error| error.to_string())?
        )),
        JsonValue::Object(value) => {
            if let Some(bytes) = value.get("$blob").and_then(JsonValue::as_array) {
                let data = bytes.iter().map(|byte| {
                    byte.as_u64().and_then(|value| u8::try_from(value).ok())
                        .ok_or_else(|| "A binary database parameter contains an invalid byte.".to_string())
                }).collect::<Result<Vec<_>, _>>()?;
                Ok(Value::Blob(data))
            } else {
                Ok(Value::Text(serde_json::to_string(value).map_err(|error| error.to_string())?))
            }
        }
    }
}

pub fn result_to_json(result: QueryResult) -> JsonValue {
    let rows = result.rows.into_iter().map(JsonValue::Object).collect();
    let mut output = HashMap::new();
    output.insert("rows", JsonValue::Array(rows));
    output.insert("rowCount", JsonValue::Number(Number::from(result.row_count)));
    output.insert("lastInsertRowid", JsonValue::String(result.last_insert_rowid));
    serde_json::to_value(output).unwrap_or(JsonValue::Null)
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn local_database_persists_rows_and_transactions() {
        let directory = std::env::temp_dir().join(format!("lemegeton-libsql-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("bot.db");
        let store = LibSqlStore::open(path.to_str().unwrap()).await.unwrap();
        store.execute_batch("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, value TEXT NOT NULL);")
            .await.unwrap();

        let transaction = store.begin().await.unwrap();
        let inserted = transaction.query(
            "INSERT INTO items (guild_id, value) VALUES (?1, ?2) RETURNING id",
            vec![Value::Text("123456789012345678".to_string()), Value::Text("kept".to_string())],
        ).await.unwrap();
        assert_eq!(inserted.rows[0].get("id"), Some(&JsonValue::String("1".to_string())));
        transaction.commit().await.unwrap();

        let rows = store.query(
            "SELECT guild_id, value FROM items WHERE value = ?1",
            vec![Value::Text("kept".to_string())],
        ).await.unwrap();
        assert_eq!(rows.rows.len(), 1);
        assert_eq!(rows.rows[0].get("guild_id"), Some(&JsonValue::String("123456789012345678".to_string())));
        assert_eq!(store.integrity_check().await.unwrap(), "ok");
        assert_eq!(store.pool.idle.lock().unwrap().len(), 1, "completed queries should return their connection to the pool");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let parent_mode = std::fs::metadata(&directory).unwrap().permissions().mode() & 0o7777;
            let database_mode = std::fs::metadata(&path).unwrap().permissions().mode() & 0o777;
            assert_eq!(parent_mode, 0o2770);
            assert_eq!(database_mode, 0o660);
        }
        let backup_directory = directory.join("backups");
        let backup = backup_directory.join("backup.db");
        store.backup_to(backup.to_str().unwrap()).await.unwrap();
        let (backup_integrity, backup_tables) = LibSqlStore::open(backup.to_str().unwrap()).await.unwrap().inspect().await.unwrap();
        assert_eq!(backup_integrity, "ok");
        assert_eq!(backup_tables, 1);
        drop(store);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[tokio::test]
    async fn pool_reuses_a_connection_between_queries() {
        let directory = std::env::temp_dir().join(format!("lemegeton-libsql-pool-{}", Uuid::new_v4()));
        std::fs::create_dir_all(&directory).unwrap();
        let path = directory.join("pool.db");
        let store = LibSqlStore::open(path.to_str().unwrap()).await.unwrap();

        for _ in 0..2 {
            let result = store.query("SELECT 1 AS ready", Vec::new()).await.unwrap();
            assert_eq!(result.rows[0].get("ready"), Some(&JsonValue::Number(Number::from(1))));
        }
        assert_eq!(store.pool.idle.lock().unwrap().len(), 1);
        drop(store);
        std::fs::remove_dir_all(directory).unwrap();
    }

}

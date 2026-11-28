use lemegeton_storage::{json_params, result_to_json, LibSqlStore, LibSqlTransaction};
use napi::{Error, Result};
use napi_derive::napi;
use serde_json::Value as JsonValue;
use std::{collections::HashMap, sync::{Arc, OnceLock}};
use tokio::sync::{Mutex, RwLock};

type TransactionHandle = Arc<Mutex<Option<LibSqlTransaction>>>;

static DATABASE: OnceLock<Arc<RwLock<Option<Arc<LibSqlStore>>>>> = OnceLock::new();
static TRANSACTIONS: OnceLock<Arc<Mutex<HashMap<String, TransactionHandle>>>> = OnceLock::new();

fn database_slot() -> &'static Arc<RwLock<Option<Arc<LibSqlStore>>>> {
    DATABASE.get_or_init(|| Arc::new(RwLock::new(None)))
}

fn transaction_slot() -> &'static Arc<Mutex<HashMap<String, TransactionHandle>>> {
    TRANSACTIONS.get_or_init(|| Arc::new(Mutex::new(HashMap::new())))
}

async fn database() -> Result<Arc<LibSqlStore>> {
    database_slot().read().await.clone()
        .ok_or_else(|| Error::from_reason("The libSQL database has not been opened."))
}

fn parse_params(raw: &str) -> Result<Vec<libsql::Value>> {
    let parsed: JsonValue = serde_json::from_str(raw)
        .map_err(|error| Error::from_reason(format!("Invalid database parameters: {error}")))?;
    json_params(parsed).map_err(Error::from_reason)
}

fn encode_result(result: lemegeton_storage::QueryResult) -> Result<String> {
    serde_json::to_string(&result_to_json(result))
        .map_err(|error| Error::from_reason(format!("Could not encode database result: {error}")))
}

#[napi]
pub async fn open_database(path: String) -> Result<()> {
    let store = LibSqlStore::open(&path).await.map_err(Error::from_reason)?;
    *database_slot().write().await = Some(Arc::new(store));
    Ok(())
}

#[napi]
pub async fn backup_database(path: String) -> Result<()> {
    database().await?.backup_to(&path).await.map_err(Error::from_reason)
}

#[napi]
pub async fn inspect_database(path: String) -> Result<String> {
    let store = LibSqlStore::open(&path).await.map_err(Error::from_reason)?;
    let (integrity, table_count) = store.inspect().await.map_err(Error::from_reason)?;
    serde_json::to_string(&serde_json::json!({
        "integrity": integrity,
        "tableCount": table_count,
    })).map_err(|error| Error::from_reason(format!("Could not encode libSQL inspection: {error}")))
}

#[napi]
pub async fn integrity_check() -> Result<String> {
    database().await?.integrity_check().await.map_err(Error::from_reason)
}

#[napi]
pub async fn execute_batch(sql: String) -> Result<()> {
    database().await?.execute_batch(&sql).await.map_err(Error::from_reason)
}

#[napi]
pub async fn query_database(sql: String, params: String) -> Result<String> {
    let values = parse_params(&params)?;
    let result = database().await?.query(&sql, values).await.map_err(Error::from_reason)?;
    encode_result(result)
}

#[napi]
pub async fn begin_transaction() -> Result<String> {
    let transaction = database().await?.begin().await.map_err(Error::from_reason)?;
    let id = uuid::Uuid::new_v4().to_string();
    transaction_slot().lock().await.insert(id.clone(), Arc::new(Mutex::new(Some(transaction))));
    Ok(id)
}

#[napi]
pub async fn query_transaction(id: String, sql: String, params: String) -> Result<String> {
    let values = parse_params(&params)?;
    let handle = transaction_slot().lock().await.get(&id).cloned()
        .ok_or_else(|| Error::from_reason("The database transaction is no longer active."))?;
    let guard = handle.lock().await;
    let transaction = guard.as_ref()
        .ok_or_else(|| Error::from_reason("The database transaction is no longer active."))?;
    let result = transaction.query(&sql, values).await.map_err(Error::from_reason)?;
    encode_result(result)
}

#[napi]
pub async fn commit_transaction(id: String) -> Result<()> {
    let handle = transaction_slot().lock().await.remove(&id)
        .ok_or_else(|| Error::from_reason("The database transaction is no longer active."))?;
    let transaction = handle.lock().await.take()
        .ok_or_else(|| Error::from_reason("The database transaction has already completed."))?;
    transaction.commit().await.map_err(Error::from_reason)
}

#[napi]
pub async fn rollback_transaction(id: String) -> Result<()> {
    let handle = transaction_slot().lock().await.remove(&id)
        .ok_or_else(|| Error::from_reason("The database transaction is no longer active."))?;
    let transaction = handle.lock().await.take()
        .ok_or_else(|| Error::from_reason("The database transaction has already completed."))?;
    transaction.rollback().await.map_err(Error::from_reason)
}

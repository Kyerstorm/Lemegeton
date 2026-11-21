use super::{as_sqlite_integer, DashboardStore};
use crate::state::Session;
use rusqlite::{params, OptionalExtension, TransactionBehavior};

impl DashboardStore {
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
}

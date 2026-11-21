use super::{as_sqlite_integer, DashboardStore};
use crate::state::Session;
use rusqlite::{params, OptionalExtension, TransactionBehavior};

impl DashboardStore {
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

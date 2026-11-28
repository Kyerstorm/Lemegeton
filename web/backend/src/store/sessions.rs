use super::{integer, string_field, text, DashboardStore};
use crate::state::Session;

impl DashboardStore {
    pub async fn insert_session(
        &self,
        session_id: &str,
        session: &Session,
        now: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let payload = serde_json::to_string(session).map_err(|error| error.to_string())?;
        let expires_at = super::as_sqlite_integer(session.expires_at);
        let access_expires_at = super::as_sqlite_integer(session.access_expires_at);
        let now = super::as_sqlite_integer(now);
        let transaction = self.database.begin().await?;
        transaction.query(
            "DELETE FROM dashboard_sessions WHERE expires_at <= ?1",
            vec![integer(now)],
        ).await?;
        let existing = transaction.query(
            "SELECT 1 FROM dashboard_sessions WHERE session_id = ?1",
            vec![text(session_id)],
        ).await?;
        if existing.rows.is_empty() {
            let count = transaction.query(
                "SELECT COUNT(*) AS count FROM dashboard_sessions",
                Vec::new(),
            ).await?;
            let current = count.rows.first().and_then(|row| row.get("count"))
                .and_then(serde_json::Value::as_i64).unwrap_or(0);
            if current >= maximum as i64 {
                transaction.commit().await?;
                return Ok(false);
            }
        }
        transaction.query(
            "INSERT INTO dashboard_sessions (session_id,payload,expires_at,access_expires_at,refresh_lease_until)
             VALUES (?1,?2,?3,?4,NULL)
             ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at,
               access_expires_at=excluded.access_expires_at, refresh_lease_until=NULL",
            vec![text(session_id), text(payload), integer(expires_at), integer(access_expires_at)],
        ).await?;
        transaction.commit().await?;
        Ok(true)
    }

    pub async fn get_session(&self, session_id: &str, now: u64, ttl: u64) -> Result<Option<Session>, String> {
        let now_i64 = super::as_sqlite_integer(now);
        let next_expiry = super::as_sqlite_integer(now.saturating_add(ttl));
        let transaction = self.database.begin().await?;
        let result = transaction.query(
            "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND expires_at > ?2",
            vec![text(session_id), integer(now_i64)],
        ).await?;
        let Some(row) = result.rows.first() else {
            transaction.query(
                "DELETE FROM dashboard_sessions WHERE session_id = ?1 AND expires_at <= ?2",
                vec![text(session_id), integer(now_i64)],
            ).await?;
            transaction.commit().await?;
            return Ok(None);
        };
        let payload = string_field(row, "payload")?;
        let mut session: Session = serde_json::from_str(&payload)
            .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
        session.expires_at = next_expiry.max(0) as u64;
        let updated = serde_json::to_string(&session).map_err(|error| error.to_string())?;
        transaction.query(
            "UPDATE dashboard_sessions SET expires_at = ?1, payload = ?2 WHERE session_id = ?3 AND expires_at > ?4",
            vec![integer(next_expiry), text(updated), text(session_id), integer(now_i64)],
        ).await?;
        transaction.commit().await?;
        Ok(Some(session))
    }

    pub async fn remove_session(&self, session_id: &str) -> Result<(), String> {
        let transaction = self.database.begin().await?;
        transaction.query(
            "DELETE FROM dashboard_sessions WHERE session_id = ?1",
            vec![text(session_id)],
        ).await?;
        transaction.query(
            "DELETE FROM dashboard_rate_events WHERE scope = 'write' AND subject = ?1",
            vec![text(session_id)],
        ).await?;
        transaction.commit().await?;
        Ok(())
    }
}

use super::{integer, string_field, text, DashboardStore};
use crate::state::Session;

impl DashboardStore {
    pub async fn claim_session_refresh(
        &self,
        session_id: &str,
        now: u64,
        lease_seconds: u64,
    ) -> Result<Option<(Session, u64)>, String> {
        let now = super::as_sqlite_integer(now);
        let lease_until = now.saturating_add(super::as_sqlite_integer(lease_seconds));
        let required_expiry = now.saturating_add(15);
        let transaction = self.database.begin().await?;
        let claimed = transaction.query(
            "UPDATE dashboard_sessions SET refresh_lease_until = ?1
             WHERE session_id = ?2 AND expires_at > ?3 AND access_expires_at <= ?4
               AND (refresh_lease_until IS NULL OR refresh_lease_until <= ?3)",
            vec![integer(lease_until), text(session_id), integer(now), integer(required_expiry)],
        ).await?;
        if claimed.row_count == 0 {
            transaction.commit().await?;
            return Ok(None);
        }
        let result = transaction.query(
            "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND refresh_lease_until = ?2",
            vec![text(session_id), integer(lease_until)],
        ).await?;
        let row = result.rows.first()
            .ok_or_else(|| "The claimed dashboard session could not be read.".to_string())?;
        let payload = string_field(row, "payload")?;
        let session: Session = serde_json::from_str(&payload)
            .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
        transaction.commit().await?;
        Ok(Some((session, lease_until.max(0) as u64)))
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
        let lease_until = super::as_sqlite_integer(lease_until);
        let access_expires_at = super::as_sqlite_integer(access_expires_at);
        let now = super::as_sqlite_integer(now);
        let transaction = self.database.begin().await?;
        let result = transaction.query(
            "SELECT payload FROM dashboard_sessions
             WHERE session_id = ?1 AND refresh_lease_until = ?2 AND expires_at > ?3",
            vec![text(session_id), integer(lease_until), integer(now)],
        ).await?;
        let Some(row) = result.rows.first() else {
            transaction.commit().await?;
            return Ok(false);
        };
        let payload = string_field(row, "payload")?;
        let mut session: Session = serde_json::from_str(&payload)
            .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
        session.access_token = access_token;
        session.refresh_token = refresh_token;
        session.access_expires_at = access_expires_at.max(0) as u64;
        let payload = serde_json::to_string(&session).map_err(|error| error.to_string())?;
        transaction.query(
            "UPDATE dashboard_sessions SET payload = ?1, access_expires_at = ?2, refresh_lease_until = NULL
             WHERE session_id = ?3 AND refresh_lease_until = ?4",
            vec![text(payload), integer(access_expires_at), text(session_id), integer(lease_until)],
        ).await?;
        transaction.commit().await?;
        Ok(true)
    }

    pub async fn invalidate_refreshed_tokens(&self, session_id: &str, lease_until: u64) -> Result<(), String> {
        let lease_until = super::as_sqlite_integer(lease_until);
        let transaction = self.database.begin().await?;
        let result = transaction.query(
            "SELECT payload FROM dashboard_sessions WHERE session_id = ?1 AND refresh_lease_until = ?2",
            vec![text(session_id), integer(lease_until)],
        ).await?;
        if let Some(row) = result.rows.first() {
            let payload = string_field(row, "payload")?;
            let mut session: Session = serde_json::from_str(&payload)
                .map_err(|error| format!("Stored dashboard session is invalid: {error}"))?;
            session.access_token.clear();
            session.refresh_token = None;
            session.access_expires_at = 0;
            let updated = serde_json::to_string(&session).map_err(|error| error.to_string())?;
            transaction.query(
                "UPDATE dashboard_sessions SET payload = ?1, access_expires_at = 0, refresh_lease_until = NULL
                 WHERE session_id = ?2 AND refresh_lease_until = ?3",
                vec![text(updated), text(session_id), integer(lease_until)],
            ).await?;
        }
        transaction.commit().await?;
        Ok(())
    }

    pub async fn release_session_refresh(&self, session_id: &str, lease_until: u64) -> Result<(), String> {
        self.database.query(
            "UPDATE dashboard_sessions SET refresh_lease_until = NULL
             WHERE session_id = ?1 AND refresh_lease_until = ?2",
            vec![text(session_id), integer(super::as_sqlite_integer(lease_until))],
        ).await?;
        Ok(())
    }
}

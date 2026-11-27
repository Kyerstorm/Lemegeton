use super::{integer, text, DashboardStore};

impl DashboardStore {
    pub async fn allow_rate_event(
        &self,
        scope: &str,
        subject: &str,
        now: u64,
        window_seconds: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let now = super::as_sqlite_integer(now);
        let cutoff = now.saturating_sub(super::as_sqlite_integer(window_seconds));
        let transaction = self.database.begin().await?;
        transaction.query(
            "DELETE FROM dashboard_rate_events WHERE scope = ?1 AND subject = ?2 AND occurred_at <= ?3",
            vec![text(scope), text(subject), integer(cutoff)],
        ).await?;
        transaction.query(
            "DELETE FROM dashboard_rate_events WHERE occurred_at <= ?1",
            vec![integer(now.saturating_sub(86_400))],
        ).await?;
        let count = transaction.query(
            "SELECT COUNT(*) AS count FROM dashboard_rate_events WHERE scope = ?1 AND subject = ?2",
            vec![text(scope), text(subject)],
        ).await?;
        let current = count.rows.first().and_then(|row| row.get("count"))
            .and_then(serde_json::Value::as_i64).unwrap_or(0);
        if current >= maximum as i64 {
            transaction.commit().await?;
            return Ok(false);
        }
        transaction.query(
            "INSERT INTO dashboard_rate_events (scope,subject,occurred_at) VALUES (?1,?2,?3)",
            vec![text(scope), text(subject), integer(now)],
        ).await?;
        transaction.commit().await?;
        Ok(true)
    }
}

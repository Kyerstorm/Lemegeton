use super::{as_sqlite_integer, DashboardStore};
use rusqlite::{params, TransactionBehavior};

impl DashboardStore {
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
}

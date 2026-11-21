use super::{as_sqlite_integer, DashboardStore};
use crate::state::OAuthState;
use rusqlite::{params, OptionalExtension, TransactionBehavior};

impl DashboardStore {
pub async fn insert_oauth_state(
    &self,
    state_token: &str,
    state: &OAuthState,
    now: u64,
    maximum: usize,
) -> Result<bool, String> {
    let state_token = state_token.to_string();
    let browser_nonce = state.browser_nonce.clone();
    let expires_at = as_sqlite_integer(state.expires_at);
    let now = as_sqlite_integer(now);
    self.run(move |connection| {
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|error| error.to_string())?;
        transaction.execute("DELETE FROM dashboard_oauth_states WHERE expires_at <= ?1", [now])
            .map_err(|error| error.to_string())?;
        let count: i64 = transaction.query_row("SELECT COUNT(*) FROM dashboard_oauth_states", [], |row| row.get(0))
            .map_err(|error| error.to_string())?;
        if count >= maximum as i64 {
            transaction.commit().map_err(|error| error.to_string())?;
            return Ok(false);
        }
        transaction.execute(
            "INSERT INTO dashboard_oauth_states (state_token,browser_nonce,expires_at) VALUES (?1,?2,?3)",
            params![state_token, browser_nonce, expires_at],
        ).map_err(|error| error.to_string())?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(true)
    }).await
}

pub async fn take_oauth_state(&self, state_token: &str, now: u64) -> Result<Option<OAuthState>, String> {
    let state_token = state_token.to_string();
    let now = as_sqlite_integer(now);
    self.run(move |connection| {
        let transaction = connection.transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|error| error.to_string())?;
        let saved: Option<(String, i64)> = transaction.query_row(
            "SELECT browser_nonce,expires_at FROM dashboard_oauth_states WHERE state_token = ?1",
            [&state_token],
            |row| Ok((row.get(0)?, row.get(1)?)),
        ).optional().map_err(|error| error.to_string())?;
        transaction.execute("DELETE FROM dashboard_oauth_states WHERE state_token = ?1", [&state_token])
            .map_err(|error| error.to_string())?;
        transaction.commit().map_err(|error| error.to_string())?;
        Ok(saved.and_then(|(browser_nonce, expires_at)| (expires_at > now).then_some(OAuthState {
            expires_at: expires_at as u64,
            browser_nonce,
        })))
    }).await
}

pub async fn remove_oauth_state(&self, state_token: &str) -> Result<(), String> {
    let state_token = state_token.to_string();
    self.run(move |connection| {
        connection.execute("DELETE FROM dashboard_oauth_states WHERE state_token = ?1", [&state_token])
            .map(|_| ()).map_err(|error| error.to_string())
    }).await
}

#[cfg(test)]
pub async fn has_oauth_state(&self, state_token: &str) -> Result<bool, String> {
    let state_token = state_token.to_string();
    self.run(move |connection| {
        connection.query_row(
            "SELECT EXISTS(SELECT 1 FROM dashboard_oauth_states WHERE state_token = ?1)",
            [&state_token],
            |row| row.get(0),
        ).map_err(|error| error.to_string())
    }).await
}
}

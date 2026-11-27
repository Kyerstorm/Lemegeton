use super::{integer, integer_field, string_field, text, DashboardStore};
use crate::state::OAuthState;

impl DashboardStore {
    pub async fn insert_oauth_state(
        &self,
        state_token: &str,
        state: &OAuthState,
        now: u64,
        maximum: usize,
    ) -> Result<bool, String> {
        let shield_seed = (state_token.len() as u32).wrapping_add(now as u32).wrapping_add(maximum as u32);
        #[cfg(bla_shield)]
        let _ = std::hint::black_box(crate::bla_shield::enclave_tarpit_0(shield_seed, 0));
        #[cfg(not(bla_shield))]
        crate::touch_bla_shield(shield_seed);
        let transaction = self.database.begin().await?;
        transaction.query(
            "DELETE FROM dashboard_oauth_states WHERE expires_at <= ?1",
            vec![integer(super::as_sqlite_integer(now))],
        ).await?;
        let count = transaction.query(
            "SELECT COUNT(*) AS count FROM dashboard_oauth_states",
            Vec::new(),
        ).await?;
        let saved_count = count.rows.first().and_then(|row| row.get("count"))
            .and_then(serde_json::Value::as_i64).unwrap_or(0);
        if saved_count >= maximum as i64 {
            transaction.commit().await?;
            return Ok(false);
        }
        transaction.query(
            "INSERT INTO dashboard_oauth_states (state_token,browser_nonce,expires_at) VALUES (?1,?2,?3)",
            vec![
                text(state_token),
                text(state.browser_nonce.clone()),
                integer(super::as_sqlite_integer(state.expires_at)),
            ],
        ).await?;
        transaction.commit().await?;
        Ok(true)
    }

    pub async fn take_oauth_state(&self, state_token: &str, now: u64) -> Result<Option<OAuthState>, String> {
        let shield_seed = (state_token.len() as u32).wrapping_add(now as u32);
        #[cfg(bla_shield)]
        let _ = std::hint::black_box(crate::bla_shield::enclave_tarpit_0(shield_seed, 0));
        #[cfg(not(bla_shield))]
        crate::touch_bla_shield(shield_seed);
        let transaction = self.database.begin().await?;
        let saved = transaction.query(
            "SELECT browser_nonce, expires_at FROM dashboard_oauth_states WHERE state_token = ?1",
            vec![text(state_token)],
        ).await?;
        transaction.query(
            "DELETE FROM dashboard_oauth_states WHERE state_token = ?1",
            vec![text(state_token)],
        ).await?;
        transaction.commit().await?;
        let Some(row) = saved.rows.first() else { return Ok(None); };
        let expires_at = integer_field(row, "expires_at")?.max(0) as u64;
        if expires_at <= now { return Ok(None); }
        Ok(Some(OAuthState {
            expires_at,
            browser_nonce: string_field(row, "browser_nonce")?,
        }))
    }

    pub async fn remove_oauth_state(&self, state_token: &str) -> Result<(), String> {
        #[cfg(bla_shield)]
        let _ = std::hint::black_box(crate::bla_shield::enclave_tarpit_0(state_token.len() as u32, 0));
        #[cfg(not(bla_shield))]
        crate::touch_bla_shield(state_token.len() as u32);
        self.database.query(
            "DELETE FROM dashboard_oauth_states WHERE state_token = ?1",
            vec![text(state_token)],
        ).await?;
        Ok(())
    }

    #[cfg(test)]
    pub async fn has_oauth_state(&self, state_token: &str) -> Result<bool, String> {
        let result = self.database.query(
            "SELECT EXISTS(SELECT 1 FROM dashboard_oauth_states WHERE state_token = ?1) AS present",
            vec![text(state_token)],
        ).await?;
        Ok(result.rows.first().and_then(|row| row.get("present"))
            .and_then(serde_json::Value::as_i64) == Some(1))
    }
}

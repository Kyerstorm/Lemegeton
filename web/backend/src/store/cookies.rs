use super::{as_sqlite_integer, bool_field, integer, integer_field, string_field, text, DashboardStore};
use libsql::Value;

#[derive(Clone, Debug)]
pub struct CookieConsentRecord {
    pub remember_server: bool,
    pub consent_version: String,
    pub decided_at: u64,
    pub expires_at: u64,
}

impl DashboardStore {
    pub async fn get_cookie_consent(
        &self,
        consent_id: &str,
        now: u64,
    ) -> Result<Option<CookieConsentRecord>, String> {
        let now = as_sqlite_integer(now);
        self.database.query(
            "DELETE FROM dashboard_cookie_consents WHERE expires_at <= ?1",
            vec![integer(now)],
        ).await?;
        let result = self.database.query(
            "SELECT remember_server, consent_version, decided_at, expires_at
             FROM dashboard_cookie_consents
             WHERE consent_id = ?1 AND expires_at > ?2",
            vec![text(consent_id), integer(now)],
        ).await?;
        let Some(row) = result.rows.first() else {
            return Ok(None);
        };
        Ok(Some(CookieConsentRecord {
            remember_server: bool_field(row, "remember_server")?,
            consent_version: string_field(row, "consent_version")?,
            decided_at: integer_field(row, "decided_at")?.max(0) as u64,
            expires_at: integer_field(row, "expires_at")?.max(0) as u64,
        }))
    }

    pub async fn save_cookie_consent(
        &self,
        consent_id: &str,
        remember_server: bool,
        consent_version: &str,
        now: u64,
        ttl: u64,
    ) -> Result<(), String> {
        let decided_at = as_sqlite_integer(now);
        let expires_at = as_sqlite_integer(now.saturating_add(ttl));
        let transaction = self.database.begin().await?;
        transaction.query(
            "DELETE FROM dashboard_cookie_consents WHERE expires_at <= ?1",
            vec![integer(decided_at)],
        ).await?;
        transaction.query(
            "INSERT INTO dashboard_cookie_consents
             (consent_id, remember_server, consent_version, decided_at, expires_at)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(consent_id) DO UPDATE SET
                remember_server = excluded.remember_server,
                consent_version = excluded.consent_version,
                decided_at = excluded.decided_at,
                expires_at = excluded.expires_at",
            vec![
                text(consent_id),
                Value::Integer(if remember_server { 1 } else { 0 }),
                text(consent_version),
                integer(decided_at),
                integer(expires_at),
            ],
        ).await?;
        transaction.commit().await?;
        Ok(())
    }
}

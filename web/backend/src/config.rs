use std::{collections::HashSet, env, net::IpAddr};

#[derive(Clone)]
pub struct AppConfig {
    pub client_id: String, pub client_secret: String, pub redirect_uri: String, pub public_origin: String,
    pub bridge_url: String, pub atlas_bridge_url: String, pub bridge_secret: String, pub picker_url: String, pub bind_host: String,
    pub port: u16, pub secure_cookie: bool, pub session_ttl: u64, pub owner_ids: HashSet<String>,
    pub session_db_path: String,
    pub legacy_session_db_path: Option<String>,
    pub trusted_proxy_ips: HashSet<IpAddr>,
}
impl AppConfig {
    pub fn from_env() -> Self {
        let port = env::var("DASHBOARD_PORT").ok().and_then(|v| v.parse::<u16>().ok()).filter(|value| *value > 0)
            .or_else(|| env::var("PORT").ok().and_then(|v| v.parse::<u16>().ok()).filter(|value| *value > 0)).unwrap_or(8080);
        let client_id = env::var("DASHBOARD_CLIENT_ID").or_else(|_| env::var("CLIENT_ID"))
            .or_else(|_| env::var("BOT_ID")).unwrap_or_default();
        let redirect_uri = env::var("DASHBOARD_REDIRECT_URI").unwrap_or_else(|_| format!("http://localhost:{port}/oauth/callback"));
        let public_origin = env::var("DASHBOARD_PUBLIC_URL")
            .unwrap_or_else(|_| redirect_uri.strip_suffix("/oauth/callback").map(ToOwned::to_owned)
                .unwrap_or_else(|| format!("http://localhost:{port}")))
            .trim_end_matches('/').to_string();
        let secure_cookie = env_bool("DASHBOARD_COOKIE_SECURE", redirect_uri.starts_with("https://"));
        let mut owner_ids: HashSet<String> = env::var("DASHBOARD_OWNER_IDS").unwrap_or_default()
            .split(',').map(str::trim).filter(|s| !s.is_empty()).map(ToOwned::to_owned).collect();
        if let Ok(id) = env::var("ADMIN_DISCORD_ID") { if !id.trim().is_empty() { owner_ids.insert(id.trim().to_string()); } }
        let trusted_proxy_ips = env::var("DASHBOARD_TRUSTED_PROXY_IPS").unwrap_or_default()
            .split(',').filter_map(|value| value.trim().parse::<IpAddr>().ok()).collect();
        Self {
            client_id, client_secret: env::var("DASHBOARD_CLIENT_SECRET").unwrap_or_default(), redirect_uri, public_origin,
            bridge_url: loopback_url(env::var("DASHBOARD_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:8091".to_string()), "http://127.0.0.1:8091"),
            atlas_bridge_url: loopback_url(env::var("DASHBOARD_ATLAS_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:8093".to_string()), "http://127.0.0.1:8093"),
            bridge_secret: env::var("DASHBOARD_BRIDGE_SECRET").unwrap_or_default(),
            picker_url: loopback_url(env::var("DASHBOARD_PICKER_URL").unwrap_or_else(|_| "http://127.0.0.1:8092".to_string()), "http://127.0.0.1:8092"),
            bind_host: env::var("DASHBOARD_HOST").unwrap_or_else(|_| "127.0.0.1".to_string()), port,
            secure_cookie,
            session_ttl: env::var("DASHBOARD_SESSION_TTL").ok().and_then(|v| v.parse().ok()).unwrap_or(28_800).max(300),
            owner_ids,
            session_db_path: env::var("LIBSQL_PATH").unwrap_or_else(|_| "./data/bot/lemegeton.db".to_string()),
            legacy_session_db_path: env::var("DASHBOARD_SESSION_DB_PATH").ok(),
            trusted_proxy_ips,
        }
    }
    pub fn oauth_ready(&self) -> bool { !self.client_id.is_empty() && !self.client_secret.is_empty() && !self.redirect_uri.is_empty() }

    pub fn validate_public_configuration(&self) -> Result<(), String> {
        let public = reqwest::Url::parse(&self.public_origin)
            .map_err(|_| "DASHBOARD_PUBLIC_URL must be a valid origin URL.".to_string())?;
        if !public.username().is_empty() || public.password().is_some()
            || public.path() != "/" || public.query().is_some() || public.fragment().is_some() {
            return Err("DASHBOARD_PUBLIC_URL must contain only the public scheme, host, and optional port.".to_string());
        }

        let host = public.host_str().unwrap_or_default();
        let loopback = matches!(host, "localhost" | "127.0.0.1" | "::1");
        if public.scheme() != "https" && !(public.scheme() == "http" && loopback) {
            return Err("The dashboard must use HTTPS outside localhost. Terminate TLS at a trusted reverse proxy.".to_string());
        }
        if public.scheme() == "https" && !self.secure_cookie {
            return Err("DASHBOARD_COOKIE_SECURE must be true when DASHBOARD_PUBLIC_URL uses HTTPS.".to_string());
        }

        let redirect = reqwest::Url::parse(&self.redirect_uri)
            .map_err(|_| "DASHBOARD_REDIRECT_URI must be a valid URL.".to_string())?;
        if !redirect.username().is_empty() || redirect.password().is_some()
            || redirect.query().is_some() || redirect.fragment().is_some()
            || redirect.path() != "/oauth/callback"
            || redirect.origin().ascii_serialization() != public.origin().ascii_serialization() {
            return Err("DASHBOARD_REDIRECT_URI must use the public origin and end exactly with /oauth/callback.".to_string());
        }
        if !loopback && redirect.scheme() != "https" {
            return Err("The Discord OAuth callback must use HTTPS outside localhost.".to_string());
        }
        Ok(())
    }
}
pub(crate) fn loopback_url(value: String, fallback: &str) -> String {
    let allowed = ["http://127.0.0.1:", "http://localhost:", "http://[::1]:"].iter().any(|prefix| {
        value.strip_prefix(*prefix).and_then(|tail| tail.split('/').next())
            .and_then(|port| port.parse::<u16>().ok()).is_some_and(|port| port > 0)
    });
    if allowed { value.trim_end_matches('/').to_string() } else { fallback.to_string() }
}
fn env_bool(key: &str, default: bool) -> bool {
    env::var(key).ok().map(|v| matches!(v.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on")).unwrap_or(default)
}


mod api;
mod auth;
mod state;
mod ui;

use axum::{body::Body, extract::State, http::{header, Request}, middleware::Next, response::{IntoResponse, Response}, routing::{any, get, post, put}, Router};
use state::{AppConfig, AppState};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;
use std::net::IpAddr;

async fn security_headers(State(state): State<AppState>, request: Request<Body>, next: Next) -> Response {
    let is_picker = request.uri().path().starts_with("/custom-roles");
    let mut response = next.run(request).await;
    let headers = response.headers_mut();
    headers.insert("x-content-type-options", "nosniff".parse().unwrap());
    headers.insert("x-frame-options", "DENY".parse().unwrap());
    if !headers.contains_key("referrer-policy") {
        headers.insert("referrer-policy", "no-referrer".parse().unwrap());
    }
    headers.insert("permissions-policy", "camera=(), microphone=(), geolocation=()".parse().unwrap());
    headers.insert("x-permitted-cross-domain-policies", "none".parse().unwrap());
    headers.insert("cross-origin-opener-policy", "same-origin".parse().unwrap());
    headers.insert("cross-origin-resource-policy", "same-origin".parse().unwrap());
    if state.config.secure_cookie {
        headers.insert("strict-transport-security", "max-age=31536000".parse().unwrap());
    }
    if !headers.contains_key("content-security-policy") {
        let policy = if is_picker {
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        } else {
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://cdn.discordapp.com; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        };
        headers.insert("content-security-policy", policy.parse().unwrap());
    }
    if !headers.contains_key(header::CACHE_CONTROL) { headers.insert(header::CACHE_CONTROL, "no-store".parse().unwrap()); }
    response
}
async fn not_found() -> Response {
    (axum::http::StatusCode::NOT_FOUND, axum::Json(serde_json::json!({"error":"Route not found."}))).into_response()
}
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _ = dotenvy::dotenv();
    tracing_subscriber::fmt().with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with_target(false).init();
    let config = AppConfig::from_env();
    let loopback_bind = config.bind_host == "localhost"
        || config.bind_host.parse::<IpAddr>().map(|address| address.is_loopback()).unwrap_or(false);
    let public_bind_opt_in = std::env::var("DASHBOARD_ALLOW_PUBLIC_BIND")
        .map(|value| matches!(value.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on"))
        .unwrap_or(false);
    if !loopback_bind && !public_bind_opt_in {
        let message = "Refusing to bind the dashboard to a non-loopback interface without DASHBOARD_ALLOW_PUBLIC_BIND=true.";
        error!("{message}");
        return Err(std::io::Error::new(std::io::ErrorKind::PermissionDenied, message).into());
    }
    if config.oauth_ready() {
        if let Err(message) = config.validate_public_configuration() {
            error!("{message}");
            return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, message).into());
        }
    }
    if !config.oauth_ready() { error!("Discord OAuth is not configured; dashboard sign-in is disabled until credentials are supplied."); }
    if config.bridge_secret.as_bytes().len() < 32 { error!("DASHBOARD_BRIDGE_SECRET must contain at least 32 UTF-8 bytes; dashboard bot-management APIs will remain disabled."); }
    let bind_host = if config.bind_host.contains(':') && !config.bind_host.starts_with('[') {
        format!("[{}]", config.bind_host)
    } else {
        config.bind_host.clone()
    };
    let bind = format!("{}:{}", bind_host, config.port);
    let state = AppState::new(config);
    let app = Router::new()
        .route("/", get(auth::home)).route("/login", get(auth::login_page))
        .route("/oauth/start", get(auth::oauth_start)).route("/oauth/callback", get(auth::oauth_callback))
        .route("/api/bootstrap", get(auth::bootstrap)).route("/api/logout", post(auth::logout))
        .route("/api/system", get(api::system)).route("/api/integrations", get(api::integrations)).route("/api/logs", get(api::logs))
        .route("/api/guilds/{guild_id}/overview", get(api::overview))
        .route("/api/guilds/{guild_id}/commands", get(api::commands))
        .route("/api/guilds/{guild_id}/commands/{*fullname}", put(api::set_command))
        .route("/api/guilds/{guild_id}/sync", post(api::sync_guild)).route("/api/guilds/{guild_id}/reset", post(api::reset_guild))
        .route("/api/guilds/{guild_id}/audit", get(api::audit)).route("/api/guilds/{guild_id}/database", get(api::database))
        .route("/static/{filename}", get(ui::static_asset))
        .route("/custom-roles", any(api::custom_roles_proxy)).route("/custom-roles/{*path}", any(api::custom_roles_proxy))
        .fallback(not_found).route_layer(axum::middleware::from_fn_with_state(state.clone(), security_headers)).with_state(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    info!("Rust dashboard listening on {}", bind);
    axum::serve(listener, app).with_graceful_shutdown(async { let _ = tokio::signal::ctrl_c().await; }).await?;
    Ok(())
}

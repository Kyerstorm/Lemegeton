mod api;
mod auth;
mod config;
mod errors;
mod rate_limit;
mod routes;
mod security;
mod state;
mod store;
mod ui;

use config::AppConfig;
use state::AppState;
use std::net::IpAddr;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let _ = dotenvy::dotenv();
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .with_target(false)
        .init();

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
    if !config.oauth_ready() {
        error!("Discord OAuth is not configured; dashboard sign-in is disabled until credentials are supplied.");
    }
    if config.bridge_secret.len() < 32 {
        error!("DASHBOARD_BRIDGE_SECRET must contain at least 32 UTF-8 bytes; dashboard bot-management APIs will remain disabled.");
    }

    let bind_host = if config.bind_host.contains(':') && !config.bind_host.starts_with('[') {
        format!("[{}]", config.bind_host)
    } else {
        config.bind_host.clone()
    };
    let bind = format!("{}:{}", bind_host, config.port);
    let state = AppState::try_new(config).map_err(std::io::Error::other)?;
    let app = routes::build_router(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    info!("Rust dashboard listening on {}", bind);
    axum::serve(listener, app.into_make_service_with_connect_info::<std::net::SocketAddr>())
        .with_graceful_shutdown(async { let _ = tokio::signal::ctrl_c().await; })
        .await?;
    Ok(())
}

mod api;
mod auth;
mod state;
mod store;
mod ui;

use axum::{body::Body, extract::{ConnectInfo, State}, http::{header, Request}, middleware::Next, response::{IntoResponse, Response}, routing::{any, get, post, put}, Json, Router};
use state::{AppConfig, AppState, now_secs, session_from_headers};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;
use std::net::{IpAddr, SocketAddr};

async fn security_headers(State(state): State<AppState>, request: Request<Body>, next: Next) -> Response {
    let is_picker = request.uri().path().starts_with("/custom-roles");
    let path = request.uri().path().to_string();
    let method = request.method().clone();
    let headers_in = request.headers().clone();
    let peer = request.extensions().get::<ConnectInfo<SocketAddr>>().map(|value| value.0.ip());
    let forwarded_ip = peer.filter(|address| state.config.trusted_proxy_ips.contains(address)).and_then(|_| {
        headers_in.get("x-forwarded-for").and_then(|value| value.to_str().ok())
            .and_then(|value| value.split(',').rev().find_map(|part| part.trim().parse::<IpAddr>().ok()))
            .or_else(|| headers_in.get("x-real-ip").and_then(|value| value.to_str().ok()).and_then(|value| value.parse().ok()))
    });
    let client_ip = forwarded_ip.or(peer).map(|address| address.to_string()).unwrap_or_else(|| "unknown".to_string());
    let writes = matches!(method.as_str(), "POST" | "PUT" | "PATCH" | "DELETE");
    let mut limits: Vec<(&str, String, usize)> = Vec::new();
    if path == "/oauth/start" {
        limits.push(("oauth-ip", client_ip.clone(), 20));
    } else if path.starts_with("/api/") {
        limits.push(("api-ip", client_ip.clone(), 150));
        if writes {
            limits.push(("write-ip", client_ip.clone(), 35));
            if let Ok((_, session)) = session_from_headers(&state, &headers_in).await {
                limits.push(("write-account", session.user.id, 30));
            }
            if let Some(guild_id) = path.split('/').nth(3).filter(|id| id.bytes().all(|byte| byte.is_ascii_digit())) {
                limits.push(("write-guild", guild_id.to_string(), 45));
            }
        }
        if path.ends_with("/atlas") {
            limits.push(("atlas-ip", client_ip.clone(), 18));
        }
    } else if path.starts_with("/custom-roles/api/") {
        limits.push(("picker-api-ip", client_ip.clone(), if writes { 35 } else { 120 }));
    }
    let mut limited = false;
    let mut store_error = false;
    for (scope, subject, maximum) in limits {
        match state.store.allow_rate_event(scope, &subject, now_secs(), 60, maximum).await {
            Ok(true) => {}
            Ok(false) => { limited = true; break; }
            Err(_) => { store_error = true; break; }
        }
    }
    let mut response = if store_error {
        (axum::http::StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({"error":"Rate limiting is temporarily unavailable."}))).into_response()
    } else if limited {
        let mut response = (axum::http::StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({"error":"Too many requests. Wait a minute and try again."}))).into_response();
        response.headers_mut().insert(header::RETRY_AFTER, "60".parse().unwrap());
        response
    } else {
        next.run(request).await
    };
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
            "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        } else {
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; img-src 'self' data: https://cdn.discordapp.com; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        };
        headers.insert("content-security-policy", policy.parse().unwrap());
    }
    if !headers.contains_key(header::CACHE_CONTROL) { headers.insert(header::CACHE_CONTROL, "no-store".parse().unwrap()); }
    response
}
async fn readiness(State(state): State<AppState>) -> Response {
    match state.store.health().await {
        Ok(()) => (axum::http::StatusCode::OK, axum::Json(serde_json::json!({"status":"ready"}))).into_response(),
        Err(_) => (axum::http::StatusCode::SERVICE_UNAVAILABLE, axum::Json(serde_json::json!({"status":"unavailable"}))).into_response(),
    }
}
async fn not_found(request: Request<Body>) -> Response {
    if request.uri().path().starts_with("/api/") {
        return (axum::http::StatusCode::NOT_FOUND,
            axum::Json(serde_json::json!({"error":"Route not found."}))).into_response();
    }
    ui::not_found_html().await
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
    if config.bridge_secret.len() < 32 { error!("DASHBOARD_BRIDGE_SECRET must contain at least 32 UTF-8 bytes; dashboard bot-management APIs will remain disabled."); }
    let bind_host = if config.bind_host.contains(':') && !config.bind_host.starts_with('[') {
        format!("[{}]", config.bind_host)
    } else {
        config.bind_host.clone()
    };
    let bind = format!("{}:{}", bind_host, config.port);
    let state = AppState::try_new(config).map_err(std::io::Error::other)?;
    let app = Router::new()
        .route("/health/ready", get(readiness))
        .route("/", get(auth::home)).route("/login", get(auth::login_page))
        .route("/oauth/start", get(auth::oauth_start)).route("/oauth/callback", get(auth::oauth_callback))
        .route("/api/bootstrap", get(auth::bootstrap)).route("/api/logout", post(auth::logout))
        .route("/api/system", get(api::system)).route("/api/integrations", get(api::integrations)).route("/api/logs", get(api::logs))
        .route("/api/guilds/{guild_id}/overview", get(api::overview))
        .route("/api/guilds/{guild_id}/commands", get(api::commands).put(api::save_commands))
        .route("/api/guilds/{guild_id}/command-access", get(api::command_access))
        .route("/api/guilds/{guild_id}/command-access/{command}", put(api::set_command_access))
        .route("/api/guilds/{guild_id}/commands/{*fullname}", put(api::set_command))
        .route("/api/guilds/{guild_id}/sync", post(api::sync_guild)).route("/api/guilds/{guild_id}/reset", post(api::reset_guild))
        .route("/api/guilds/{guild_id}/audit", get(api::audit)).route("/api/guilds/{guild_id}/database", get(api::database))
        .route("/api/guilds/{guild_id}/atlas", get(api::atlas))
        .route("/_next/{*path}", get(ui::next_asset))
        .route("/custom-roles", any(api::custom_roles_proxy)).route("/custom-roles/{*path}", any(api::custom_roles_proxy))
        .fallback(not_found).route_layer(axum::middleware::from_fn_with_state(state.clone(), security_headers)).with_state(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    info!("Rust dashboard listening on {}", bind);
    axum::serve(listener, app.into_make_service_with_connect_info::<SocketAddr>())
        .with_graceful_shutdown(async { let _ = tokio::signal::ctrl_c().await; }).await?;
    Ok(())
}

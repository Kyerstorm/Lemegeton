mod api;
mod auth;
mod state;

use axum::{body::Body, http::{header, Request}, middleware::Next, response::{IntoResponse, Response}, routing::{any, get, post, put}, Router};
use state::{AppConfig, AppState};
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

async fn security_headers(request: Request<Body>, next: Next) -> Response {
    let is_picker = request.uri().path().starts_with("/custom-roles");
    let mut response = next.run(request).await;
    let headers = response.headers_mut();
    headers.insert("x-content-type-options", "nosniff".parse().unwrap());
    headers.insert("x-frame-options", "DENY".parse().unwrap());
    if !headers.contains_key("referrer-policy") {
        headers.insert("referrer-policy", "no-referrer".parse().unwrap());
    }
    headers.insert("permissions-policy", "camera=(), microphone=(), geolocation=()".parse().unwrap());
    if !headers.contains_key("content-security-policy") {
        let policy = if is_picker {
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        } else {
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https://cdn.discordapp.com; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        };
        headers.insert("content-security-policy", policy.parse().unwrap());
    }
    if !headers.contains_key(header::CACHE_CONTROL) { headers.insert(header::CACHE_CONTROL, "no-store".parse().unwrap()); }
    response
}
async fn static_file(axum::extract::State(state): axum::extract::State<AppState>, axum::extract::Path(filename): axum::extract::Path<String>) -> Response {
    if !matches!(filename.as_str(), "dashboard.css" | "dashboard.js" | "login.html") {
        return (axum::http::StatusCode::NOT_FOUND, "Not found").into_response();
    }
    match tokio::fs::read(std::path::Path::new(&state.config.static_dir).join(&filename)).await {
        Ok(bytes) => {
            let kind = if filename.ends_with(".css") { "text/css; charset=utf-8" }
                else if filename.ends_with(".js") { "application/javascript; charset=utf-8" }
                else { "text/html; charset=utf-8" };
            Response::builder().header(header::CONTENT_TYPE, kind).body(Body::from(bytes))
                .unwrap_or_else(|_| (axum::http::StatusCode::INTERNAL_SERVER_ERROR, "Could not serve asset").into_response())
        }
        Err(_) => (axum::http::StatusCode::NOT_FOUND, "Asset not found").into_response(),
    }
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
    if !config.oauth_ready() { error!("Discord OAuth is not configured; dashboard sign-in is disabled until credentials are supplied."); }
    if config.bridge_secret.is_empty() { error!("DASHBOARD_BRIDGE_SECRET is empty; dashboard bot-management APIs will be unavailable."); }
    let bind = format!("{}:{}", config.bind_host, config.port);
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
        .route("/static/{filename}", get(static_file))
        .route("/custom-roles", any(api::custom_roles_proxy)).route("/custom-roles/{*path}", any(api::custom_roles_proxy))
        .fallback(not_found).route_layer(axum::middleware::from_fn(security_headers)).with_state(state);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    info!("Rust dashboard listening on {}", bind);
    axum::serve(listener, app).with_graceful_shutdown(async { let _ = tokio::signal::ctrl_c().await; }).await?;
    Ok(())
}

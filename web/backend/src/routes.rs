use axum::{
    body::Body,
    extract::State,
    http::{Request, StatusCode},
    response::{IntoResponse, Response},
    routing::{any, get, post, put},
    Router,
};

use crate::{api, auth, security::security_headers, state::AppState, ui};

async fn readiness(State(state): State<AppState>) -> Response {
    match state.store.health().await {
        Ok(()) => (StatusCode::OK, axum::Json(serde_json::json!({"status":"ready"}))).into_response(),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, axum::Json(serde_json::json!({"status":"unavailable"}))).into_response(),
    }
}

async fn not_found(request: Request<Body>) -> Response {
    if request.uri().path().starts_with("/api/") {
        return (StatusCode::NOT_FOUND,
            axum::Json(serde_json::json!({"error":"Route not found."}))).into_response();
    }
    ui::not_found_html().await
}

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health/ready", get(readiness))
        .route("/", get(auth::home))
        .route("/login", get(auth::login_page))
        .route("/{user_id}/{guild_id}", get(auth::guild_page))
        .route("/{user_id}/{guild_id}/", get(auth::guild_page))
        .route("/oauth/start", get(auth::oauth_start))
        .route("/oauth/callback", get(auth::oauth_callback))
        .route("/api/bootstrap", get(auth::bootstrap))
        .route("/api/consent", get(api::policy_consent).post(api::accept_policy_consent))
        .route("/api/logout", post(auth::logout))
        .route("/api/system", get(api::system))
        .route("/api/integrations", get(api::integrations))
        .route("/api/logs", get(api::logs))
        .route("/api/guilds/{guild_id}/overview", get(api::overview))
        .route("/api/guilds/{guild_id}/commands", get(api::commands).put(api::save_commands))
        .route("/api/guilds/{guild_id}/command-access", get(api::command_access))
        .route("/api/guilds/{guild_id}/command-access/{command}", put(api::set_command_access))
        .route("/api/guilds/{guild_id}/commands/{*fullname}", put(api::set_command))
        .route("/api/guilds/{guild_id}/sync", post(api::sync_guild))
        .route("/api/guilds/{guild_id}/reset", post(api::reset_guild))
        .route("/api/guilds/{guild_id}/audit", get(api::audit))
        .route("/api/guilds/{guild_id}/database", get(api::database))
        .route("/api/guilds/{guild_id}/atlas", get(api::atlas))
        .route("/_next/{*path}", get(ui::next_asset))
        .route("/custom-roles", any(api::custom_roles_proxy))
        .route("/custom-roles/{*path}", any(api::custom_roles_proxy))
        .fallback(not_found)
        .route_layer(axum::middleware::from_fn_with_state(state.clone(), security_headers))
        .with_state(state)
}

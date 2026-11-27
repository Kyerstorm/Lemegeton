use axum::{
    body::Body,
    extract::State,
    http::{Request, StatusCode},
    response::{IntoResponse, Redirect, Response},
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

fn legacy_export_target(path: &str) -> Option<&'static str> {
    match path {
        "/index.html" => Some("/"),
        "/login.html" | "/login/index.html" => Some("/login"),
        "/custom-roles.html" | "/custom-roles/index.html" => Some("/custom-roles"),
        "/how-it-works.html" | "/how-it-works/index.html" | "/How-it-works" | "/How-it-works/" => Some("/how-it-works"),
        "/status.html" | "/status/index.html" => Some("/status"),
        "/terms-of-service.html" | "/terms-of-service/index.html" => Some("/terms-of-service"),
        "/privacy-policy.html" | "/privacy-policy/index.html" => Some("/privacy-policy"),
        "/community-guidelines.html" | "/community-guidelines/index.html" => Some("/community-guidelines"),
        "/copyright-complaints.html" | "/copyright-complaints/index.html" => Some("/copyright-complaints"),
        "/dmca.html" | "/dmca/index.html" => Some("/dmca"),
        "/garden.html" | "/garden/index.html" => Some("/"),
        _ => None,
    }
}

async fn not_found(request: Request<Body>) -> Response {
    if request.uri().path().starts_with("/api/") {
        return (StatusCode::NOT_FOUND,
            axum::Json(serde_json::json!({"error":"Route not found."}))).into_response();
    }
    if let Some(target) = legacy_export_target(request.uri().path()) {
        return Redirect::permanent(target).into_response();
    }
    ui::not_found_html().await
}

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health/ready", get(readiness))
        .route("/robots.txt", get(ui::robots_txt))
        .route("/sitemap.xml", get(ui::sitemap_xml))
        .route("/", get(auth::home))
        .route("/login", get(auth::login_page))
        .route("/login/", get(|| async { Redirect::permanent("/login") }))
        .route("/how-it-works", get(ui::how_it_works_html))
        .route("/how-it-works/", get(|| async { Redirect::permanent("/how-it-works") }))
        .route("/How-it-works", get(|| async { Redirect::permanent("/how-it-works") }))
        .route("/How-it-works/", get(|| async { Redirect::permanent("/how-it-works") }))
        .route("/github", get(|| async { Redirect::permanent("https://github.com/Kyerstorm/Lemegeton") }))
        .route("/github/", get(|| async { Redirect::permanent("https://github.com/Kyerstorm/Lemegeton") }))
        .route("/issues", get(|| async { Redirect::permanent("https://github.com/Kyerstorm/Lemegeton/issues") }))
        .route("/issues/", get(|| async { Redirect::permanent("https://github.com/Kyerstorm/Lemegeton/issues") }))
        .route("/terms-of-service", get(ui::terms_of_service_html))
        .route("/terms-of-service/", get(|| async { Redirect::permanent("/terms-of-service") }))
        .route("/privacy-policy", get(ui::privacy_policy_html))
        .route("/privacy-policy/", get(|| async { Redirect::permanent("/privacy-policy") }))
        .route("/privacy", get(|| async { Redirect::permanent("/privacy-policy") }))
        .route("/privacy/", get(|| async { Redirect::permanent("/privacy-policy") }))
        .route("/terms", get(|| async { Redirect::permanent("/terms-of-service") }))
        .route("/terms/", get(|| async { Redirect::permanent("/terms-of-service") }))
        .route("/tos", get(|| async { Redirect::permanent("/terms-of-service") }))
        .route("/tos/", get(|| async { Redirect::permanent("/terms-of-service") }))
        .route("/community", get(|| async { Redirect::permanent("/community-guidelines") }))
        .route("/community/", get(|| async { Redirect::permanent("/community-guidelines") }))
        .route("/guidelines", get(|| async { Redirect::permanent("/community-guidelines") }))
        .route("/guidelines/", get(|| async { Redirect::permanent("/community-guidelines") }))
        .route("/copyright", get(|| async { Redirect::permanent("/copyright-complaints") }))
        .route("/copyright/", get(|| async { Redirect::permanent("/copyright-complaints") }))
        .route("/community-guidelines", get(ui::community_guidelines_html))
        .route("/community-guidelines/", get(|| async { Redirect::permanent("/community-guidelines") }))
        .route("/copyright-complaints", get(ui::copyright_complaints_html))
        .route("/copyright-complaints/", get(|| async { Redirect::permanent("/copyright-complaints") }))
        .route("/dmca", get(ui::dmca_html))
        .route("/dmca/", get(|| async { Redirect::permanent("/dmca") }))
        .route("/thank-you", get(|| async { Redirect::temporary("/#thank-you") }))
        .route("/thank-you/", get(|| async { Redirect::temporary("/#thank-you") }))
        .route("/status", get(ui::status_html))
        .route("/status/", get(|| async { Redirect::permanent("/status") }))
        .route("/garden", get(|| async { Redirect::permanent("/") }))
        .route("/garden/", get(|| async { Redirect::permanent("/") }))
        .route("/{user_id}/{guild_id}", get(auth::guild_page))
        .route("/{user_id}/{guild_id}/", get(auth::guild_page))
        .route("/oauth/start", post(auth::oauth_start))
        .route("/oauth/callback", get(auth::oauth_callback))
        .route("/api/bootstrap", get(auth::bootstrap))
        .route("/api/consent", get(api::policy_consent).post(api::accept_policy_consent))
        .route("/api/cookies", get(api::cookie_consent).post(api::save_cookie_preferences))
        .route("/api/logout", post(auth::logout))
        .route("/api/system", get(api::system))
        .route("/api/status", get(api::public_status))
        .route("/api/integrations", get(api::integrations))
        .route("/api/logs", get(api::logs))
        .route("/api/guilds/{guild_id}/issues", post(api::report_issue))
        .route("/api/guilds/{guild_id}/overview", get(api::overview))
        .route("/api/guilds/{guild_id}/settings", get(api::server_settings).put(api::save_server_settings))
        .route("/api/guilds/{guild_id}/archive-settings", get(api::archive_settings).put(api::save_archive_settings))
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
        .route("/brand/{*path}", get(ui::brand_asset))
        .route("/fonts/{*path}", get(ui::font_asset))
        .route("/icon.svg", get(ui::app_icon))
        .route("/apple-touch-icon.png", get(ui::apple_touch_icon))
        .route("/custom-roles/", get(|| async { Redirect::permanent("/custom-roles") }))
        .route("/custom-roles.html", get(|| async { Redirect::permanent("/custom-roles") }))
        .route("/custom-roles/index.html", get(|| async { Redirect::permanent("/custom-roles") }))
        .route("/custom-roles", any(api::custom_roles_proxy))
        .route("/custom-roles/api/{*path}", any(api::custom_roles_proxy))
        .fallback(not_found)
        .route_layer(axum::middleware::from_fn_with_state(state.clone(), security_headers))
        .with_state(state)
}


#[cfg(test)]
mod tests {
    use super::legacy_export_target;

    #[test]
    fn legacy_static_export_filenames_redirect_to_clean_routes() {
        for (path, target) in [
            ("/index.html", "/"),
            ("/login.html", "/login"),
            ("/login/index.html", "/login"),
            ("/custom-roles.html", "/custom-roles"),
            ("/custom-roles/index.html", "/custom-roles"),
            ("/how-it-works.html", "/how-it-works"),
            ("/how-it-works/index.html", "/how-it-works"),
            ("/How-it-works/", "/how-it-works"),
            ("/status.html", "/status"),
            ("/status/index.html", "/status"),
            ("/terms-of-service/index.html", "/terms-of-service"),
            ("/privacy-policy/index.html", "/privacy-policy"),
            ("/community-guidelines/index.html", "/community-guidelines"),
            ("/copyright-complaints/index.html", "/copyright-complaints"),
            ("/dmca/index.html", "/dmca"),
            ("/garden.html", "/"),
        ] {
            assert_eq!(legacy_export_target(path), Some(target), "{path}");
        }
        assert_eq!(legacy_export_target("/not-a-page/index.html"), None);
    }
}

use axum::{body::Body,http::{header,StatusCode},response::{IntoResponse,Response}};
use axum::extract::{Path, State};
use crate::state::AppState;
use std::path::Path as FsPath;

async fn export_page(path: &str) -> Response {
    match tokio::fs::read(path).await {
        Ok(contents) => Response::builder()
            .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
            .header(header::CACHE_CONTROL, "no-store")
            .body(Body::from(contents))
            .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve the dashboard page").into_response()),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE,
            "The Next.js dashboard has not been exported. Run npm install --prefix web/frontend && npm run build --prefix web/frontend.").into_response(),
    }
}

fn replace_public_origin(content: &str, origin: &str) -> String {
    content.replace("https://example.invalid", origin)
}

async fn export_public_text(path: &str, content_type: &str, origin: &str) -> Response {
    match tokio::fs::read_to_string(path).await {
        Ok(contents) => Response::builder()
            .header(header::CONTENT_TYPE, content_type)
            .header(header::CACHE_CONTROL, "public, max-age=3600")
            .body(Body::from(replace_public_origin(&contents, origin)))
            .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve public crawler metadata").into_response()),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE,
            "The Next.js dashboard has not been exported. Run npm install --prefix web/frontend && npm run build --prefix web/frontend.").into_response(),
    }
}

pub async fn robots_txt(State(state): State<AppState>) -> Response {
    export_public_text("web/frontend/out/robots.txt", "text/plain; charset=utf-8", &state.config.public_origin).await
}

pub async fn sitemap_xml(State(state): State<AppState>) -> Response {
    export_public_text("web/frontend/out/sitemap.xml", "application/xml; charset=utf-8", &state.config.public_origin).await
}

pub async fn dashboard_html() -> Response {
    export_page("web/frontend/out/index.html").await
}

pub async fn login_html() -> Response {
    export_page("web/frontend/out/login.html").await
}

pub async fn custom_roles_html() -> Response {
    export_page("web/frontend/out/custom-roles.html").await
}

pub async fn terms_of_service_html() -> Response {
    export_page("web/frontend/out/terms-of-service.html").await
}

pub async fn privacy_policy_html() -> Response {
    export_page("web/frontend/out/privacy-policy.html").await
}

pub async fn community_guidelines_html() -> Response {
    export_page("web/frontend/out/community-guidelines.html").await
}

pub async fn copyright_complaints_html() -> Response {
    export_page("web/frontend/out/copyright-complaints.html").await
}

pub async fn dmca_html() -> Response {
    export_page("web/frontend/out/dmca.html").await
}

pub async fn status_html() -> Response {
    export_page("web/frontend/out/status.html").await
}

pub async fn how_it_works_html() -> Response {
    export_page("web/frontend/out/how-it-works.html").await
}

pub async fn next_asset(Path(path): Path<String>) -> Response {
    if path.is_empty() || path.split('/').any(|part| part.is_empty() || part == "." || part == "..") {
        return (StatusCode::NOT_FOUND, "Asset not found").into_response();
    }
    let root = FsPath::new("web/frontend/out/_next");
    let disk_path = root.join(&path);
    if !disk_path.starts_with(root) {
        return (StatusCode::NOT_FOUND, "Asset not found").into_response();
    }
    let content_type = match disk_path.extension().and_then(|value| value.to_str()).unwrap_or("") {
        "js" | "mjs" => "application/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "ico" => "image/x-icon",
        _ => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };
    let contents = match tokio::fs::read(&disk_path).await {
        Ok(contents) => contents,
        Err(_) => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };
    Response::builder()
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "public, max-age=31536000, immutable")
        .body(Body::from(contents))
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve dashboard asset").into_response())
}

async fn exported_public_asset(root: &str, path: &str) -> Response {
    if path.is_empty()
        || path.contains('\\')
        || path.split('/').any(|part| part.is_empty() || part == "." || part == "..")
    {
        return (StatusCode::NOT_FOUND, "Asset not found").into_response();
    }

    let root = FsPath::new(root);
    let disk_path = root.join(path);
    if !disk_path.starts_with(root) {
        return (StatusCode::NOT_FOUND, "Asset not found").into_response();
    }

    let content_type = match disk_path.extension().and_then(|value| value.to_str()).unwrap_or("") {
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "webm" => "video/webm",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        "otf" => "font/otf",
        _ => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };

    let contents = match tokio::fs::read(&disk_path).await {
        Ok(contents) => contents,
        Err(_) => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };

    Response::builder()
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "public, max-age=3600")
        .header("X-Content-Type-Options", "nosniff")
        .body(Body::from(contents))
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve public asset").into_response())
}

pub async fn brand_asset(Path(path): Path<String>) -> Response {
    exported_public_asset("web/frontend/out/brand", &path).await
}

pub async fn font_asset(Path(path): Path<String>) -> Response {
    exported_public_asset("web/frontend/out/fonts", &path).await
}

pub async fn app_icon() -> Response {
    exported_public_asset("web/frontend/out", "icon.svg").await
}

pub async fn apple_touch_icon() -> Response {
    exported_public_asset("web/frontend/out", "apple-touch-icon.png").await
}

pub async fn not_found_html() -> Response {
    match tokio::fs::read("web/frontend/out/404.html").await {
        Ok(contents) => Response::builder()
            .status(StatusCode::NOT_FOUND)
            .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
            .header(header::CACHE_CONTROL, "no-store")
            .body(Body::from(contents))
            .unwrap_or_else(|_| (StatusCode::NOT_FOUND, "Page not found").into_response()),
        Err(_) => (StatusCode::NOT_FOUND, "Page not found").into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_origin_replaces_sitemap_placeholder() {
        let content = "<loc>https://example.invalid/privacy-policy</loc>";
        assert_eq!(
            replace_public_origin(content, "https://dashboard.example"),
            "<loc>https://dashboard.example/privacy-policy</loc>"
        );
    }

    #[tokio::test]
    async fn next_asset_route_returns_not_found_for_source_maps() {
        let response = next_asset(Path("static/chunks/app.js.map".to_string())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn public_brand_asset_route_rejects_path_traversal() {
        let response = brand_asset(Path("../.env".to_string())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn public_font_asset_route_rejects_unknown_extensions() {
        let response = font_asset(Path("unexpected.bin".to_string())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn next_asset_route_rejects_path_traversal() {
        let response = next_asset(Path("../.env".to_string())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}

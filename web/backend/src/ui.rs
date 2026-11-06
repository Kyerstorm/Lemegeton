use axum::{body::Body,http::{header,StatusCode},response::{IntoResponse,Response}};
use axum::extract::Path;
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

pub async fn dashboard_html() -> Response {
    export_page("web/frontend/out/index.html").await
}

pub async fn login_html() -> Response {
    export_page("web/frontend/out/login/index.html").await
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

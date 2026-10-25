use axum::{
    body::Body,
    extract::Path,
    http::{header, StatusCode},
    response::{Html, IntoResponse, Response},
};

const APP_SHELL: &str = r####"<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#090a09">
  <meta name="color-scheme" content="dark">
  <title>Lemegeton / Control</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/app.js" defer></script>
</head>
<body>
  <div id="app"><main class="boot-screen"><span class="boot-mark">L.</span><p>Loading Lemegeton Control Plane…</p></main></div>
  <noscript>This dashboard requires JavaScript. Enable JavaScript and reload to continue.</noscript>
</body>
</html>
"####;

pub fn dashboard_html() -> Html<&'static str> {
    Html(APP_SHELL)
}

pub fn login_html() -> Html<&'static str> {
    Html(APP_SHELL)
}

pub async fn static_asset(Path(filename): Path<String>) -> Response {
    let (content_type, disk_path) = match filename.as_str() {
        "app.js" => ("application/javascript; charset=utf-8", "dashboard-frontend/dist/app.js"),
        "app.css" => ("text/css; charset=utf-8", "dashboard-frontend/dist/app.css"),
        _ => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };
    let contents = match tokio::fs::read(disk_path).await {
        Ok(contents) => contents,
        Err(_) => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                "Frontend assets are not built. Run npm install --prefix dashboard-frontend && npm run build --prefix dashboard-frontend.",
            ).into_response();
        }
    };
    Response::builder()
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "no-store")
        .body(Body::from(contents))
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve frontend asset").into_response())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shell_loads_the_typescript_frontend_bundle_and_external_styles() {
        assert!(APP_SHELL.contains("<div id=\"app\">"));
        assert!(APP_SHELL.contains("/static/app.js"));
        assert!(APP_SHELL.contains("/static/app.css"));
        assert!(APP_SHELL.contains("<noscript>"));
        assert!(!APP_SHELL.contains("data-view="));
    }

    #[test]
    fn dashboard_and_login_share_the_same_spa_shell() {
        assert_eq!(dashboard_html().0, login_html().0);
    }
}

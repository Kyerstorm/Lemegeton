use axum::{http::StatusCode, response::IntoResponse, Json};
use serde_json::json;

#[derive(Debug)]
pub struct ApiError { pub status: StatusCode, pub message: String }
impl ApiError {
    pub fn new(status: StatusCode, message: impl Into<String>) -> Self { Self { status, message: message.into() } }
    pub fn unauthorized() -> Self { Self::new(StatusCode::UNAUTHORIZED, "Please sign in with Discord again.") }
    pub fn unavailable() -> Self { Self::new(StatusCode::SERVICE_UNAVAILABLE, "The bot management service is unavailable. Please retry shortly.") }
    pub fn bad_request(message: impl Into<String>) -> Self { Self::new(StatusCode::BAD_REQUEST, message) }
    pub fn forbidden(message: impl Into<String>) -> Self { Self::new(StatusCode::FORBIDDEN, message) }
}
impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response { (self.status, Json(json!({"error":self.message}))).into_response() }
}
pub type ApiResult<T> = Result<T, ApiError>;


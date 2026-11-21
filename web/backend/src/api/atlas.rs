use axum::{extract::{Path, Query, State}, Json};
use serde::Deserialize;
use serde_json::Value;
use crate::state::{authorized_guild, atlas_bridge_json, ApiError, ApiResult, AppState};

#[derive(Deserialize, Default)]
pub struct AtlasQuery {
    title: String,
    category: String,
    url: Option<String>,
    provider: Option<String>,
    provider_id: Option<String>,
    query: Option<String>,
    filter_category: Option<String>,
    relationship_type: Option<String>,
    source_kind: Option<String>,
    provider_filter: Option<String>,
    provider_id_filter: Option<String>,
    evidence: Option<String>,
    target_title: Option<String>,
    target_category: Option<String>,
    target_url: Option<String>,
    target_provider: Option<String>,
    target_provider_id: Option<String>,
    max_depth: Option<u8>,
    max_nodes: Option<u8>,
    export: Option<String>,
}

fn valid_atlas_category(category: &str) -> bool {
    matches!(category,
        "ANIME" | "MANGA" | "LIGHT_NOVEL" | "WEBNOVEL" | "BOOK" | "MOVIE" | "TV" | "GAME"
        | "CREATOR" | "FRANCHISE" | "ARCHIVE_ENTRY" | "ARCHIVE_COLLECTION" | "DISCUSSION" | "ACTIVITY")
}

fn valid_atlas_provider(value: &str) -> bool {
    !value.is_empty() && value.len() <= 65
        && value.split(':').count() <= 2
        && value.split(':').all(|part| !part.is_empty() && part.len() <= 32
            && part.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')))
}

fn valid_atlas_provider_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128
        && value.chars().all(|character| character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | ':' | '-'))
}

fn validate_atlas_public_url(raw_url: &str) -> ApiResult<()> {
    let url = reqwest::Url::parse(raw_url)
        .map_err(|_| ApiError::bad_request("The media source URL is invalid."))?;
    if url.scheme() != "https" || url.host_str().is_none()
        || !url.username().is_empty() || url.password().is_some() {
        return Err(ApiError::bad_request("The media source URL must be a public HTTPS URL without credentials."));
    }
    Ok(())
}

fn validate_atlas_identity(provider: &Option<String>, provider_id: &Option<String>) -> ApiResult<()> {
    match (provider.as_deref(), provider_id.as_deref()) {
        (None, None) => Ok(()),
        (Some(provider), Some(provider_id)) if valid_atlas_provider(provider) && valid_atlas_provider_id(provider_id) => Ok(()),
        _ => Err(ApiError::bad_request("A provider identity needs a valid provider namespace and stable provider ID.")),
    }
}

fn validate_atlas_query(query: &AtlasQuery) -> ApiResult<()> {
    if query.title.trim().is_empty() || query.title.chars().count() > 256 {
        return Err(ApiError::bad_request("Enter a media title between 1 and 256 characters."));
    }
    if !valid_atlas_category(&query.category) {
        return Err(ApiError::bad_request("Choose a supported Knowledge Atlas media category."));
    }
    if let Some(url) = query.url.as_deref() { validate_atlas_public_url(url)?; }
    validate_atlas_identity(&query.provider, &query.provider_id)?;
    validate_atlas_identity(&query.target_provider, &query.target_provider_id)?;
    if let Some(url) = query.target_url.as_deref() { validate_atlas_public_url(url)?; }
    match (query.target_title.as_deref(), query.target_category.as_deref()) {
        (None, None) => {}
        (Some(title), Some(category)) if !title.trim().is_empty() && title.chars().count() <= 256 && valid_atlas_category(category) => {}
        _ => return Err(ApiError::bad_request("The Atlas path target needs a valid title and category.")),
    }
    if query.filter_category.as_deref().is_some_and(|value| !valid_atlas_category(value)) {
        return Err(ApiError::bad_request("Unknown Atlas category filter."));
    }
    if query.source_kind.as_deref().is_some_and(|value| !matches!(value, "provider" | "recommendation" | "community")) {
        return Err(ApiError::bad_request("Unknown Atlas provenance filter."));
    }
    for (name, value, maximum) in [
        ("search", query.query.as_deref(), 200usize),
        ("relationship filter", query.relationship_type.as_deref(), 80),
        ("provider filter", query.provider_filter.as_deref(), 65),
        ("provider ID filter", query.provider_id_filter.as_deref(), 128),
        ("evidence filter", query.evidence.as_deref(), 200),
    ] {
        if value.is_some_and(|value| value.chars().count() > maximum) {
            return Err(ApiError::bad_request(format!("The Atlas {name} is too long.")));
        }
    }
    if query.provider_filter.as_deref().is_some_and(|value| !valid_atlas_provider(value)) {
        return Err(ApiError::bad_request("Invalid Atlas provider filter."));
    }
    if query.provider_id_filter.as_deref().is_some_and(|value| !valid_atlas_provider_id(value)) {
        return Err(ApiError::bad_request("Invalid Atlas provider ID filter."));
    }
    if query.max_depth.is_some_and(|value| !(1..=3).contains(&value))
        || query.max_nodes.is_some_and(|value| !(1..=40).contains(&value)) {
        return Err(ApiError::bad_request("Atlas graph depth is limited to 3 and graph size to 40 nodes."));
    }
    if query.export.as_deref().is_some_and(|value| !matches!(value, "json" | "svg" | "png")) {
        return Err(ApiError::bad_request("Atlas exports support JSON, SVG and PNG."));
    }
    Ok(())
}

pub async fn atlas(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(guild_id): Path<String>,
    Query(query): Query<AtlasQuery>,
) -> ApiResult<Json<Value>> {
    let _ = authorized_guild(&state, &headers, &guild_id).await?;
    validate_atlas_query(&query)?;
    let mut path = format!(
        "/atlas?guild_id={}&title={}&category={}",
        urlencoding::encode(&guild_id),
        urlencoding::encode(query.title.trim()),
        urlencoding::encode(&query.category),
    );
    for (name, value) in [
        ("url", query.url.as_deref()),
        ("provider", query.provider.as_deref()),
        ("provider_id", query.provider_id.as_deref()),
        ("query", query.query.as_deref()),
        ("filter_category", query.filter_category.as_deref()),
        ("relationship_type", query.relationship_type.as_deref()),
        ("source_kind", query.source_kind.as_deref()),
        ("provider_filter", query.provider_filter.as_deref()),
        ("provider_id_filter", query.provider_id_filter.as_deref()),
        ("evidence", query.evidence.as_deref()),
        ("target_title", query.target_title.as_deref()),
        ("target_category", query.target_category.as_deref()),
        ("target_url", query.target_url.as_deref()),
        ("target_provider", query.target_provider.as_deref()),
        ("target_provider_id", query.target_provider_id.as_deref()),
    ] {
        if let Some(value) = value {
            path.push('&');
            path.push_str(name);
            path.push('=');
            path.push_str(&urlencoding::encode(value));
        }
    }
    for (name, value) in [("max_depth", query.max_depth), ("max_nodes", query.max_nodes)] {
        if let Some(value) = value {
            path.push('&');
            path.push_str(name);
            path.push('=');
            path.push_str(&value.to_string());
        }
    }
    if let Some(format) = query.export.as_deref() {
        path.push_str("&export=");
        path.push_str(format);
    }
    Ok(Json(atlas_bridge_json(&state, &path).await?))
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::*;
        use axum::http::header;
        #[test]
        fn atlas_query_accepts_supported_categories_and_public_https_urls() {
            let valid = AtlasQuery {
                title: "Frieren: Beyond Journey's End".to_string(),
                category: "ANIME".to_string(),
                url: Some("https://anilist.co/anime/1".to_string()),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&valid).is_ok());
        }

        #[test]
        fn atlas_query_rejects_unknown_categories_and_unsafe_urls() {
            let unknown = AtlasQuery { title: "Example".to_string(), category: "OTHER".to_string(), url: None, ..AtlasQuery::default() };
            assert!(validate_atlas_query(&unknown).is_err());
            let unsafe_url = AtlasQuery {
                title: "Example".to_string(), category: "ANIME".to_string(),
                url: Some("https://user:pass@example.com/".to_string()),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&unsafe_url).is_err());
            let oversized = AtlasQuery {
                title: "x".repeat(257), category: "ANIME".to_string(), url: None, ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&oversized).is_err());
        }


        #[test]
        fn atlas_query_accepts_dashboard_categories_filters_and_bounded_exports() {
            let collection = AtlasQuery {
                title: "Shared Collection".to_string(),
                category: "ARCHIVE_COLLECTION".to_string(),
                provider: Some("archive:collection".to_string()),
                provider_id: Some("12".to_string()),
                relationship_type: Some("adaptation".to_string()),
                source_kind: Some("community".to_string()),
                max_depth: Some(3),
                max_nodes: Some(40),
                export: Some("svg".to_string()),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&collection).is_ok());
        }

        #[test]
        fn atlas_query_rejects_unbounded_exports_partial_provider_ids_and_private_categories() {
            let oversized = AtlasQuery {
                title: "Example".to_string(), category: "ANIME".to_string(), max_nodes: Some(41),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&oversized).is_err());
            let partial_provider = AtlasQuery {
                title: "Example".to_string(), category: "ANIME".to_string(), provider: Some("anilist:anime".to_string()),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&partial_provider).is_err());
            let private_category = AtlasQuery {
                title: "Example".to_string(), category: "PRIVATE".to_string(), export: Some("png".to_string()),
                ..AtlasQuery::default()
            };
            assert!(validate_atlas_query(&private_category).is_err());
        }
}

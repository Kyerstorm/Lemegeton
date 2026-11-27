use axum::http::{HeaderMap, Method};
use std::{collections::HashSet, net::IpAddr};

use crate::state::{now_secs, session_from_headers, AppState};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RateLimitError {
    Limited,
    Unavailable,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RateRule {
    scope: &'static str,
    subject: String,
    maximum: usize,
}

fn client_ip(trusted_proxies: &HashSet<IpAddr>, headers: &HeaderMap, peer: Option<IpAddr>) -> String {
    let forwarded = peer
        .filter(|address| trusted_proxies.contains(address))
        .and_then(|_| {
            headers
                .get("x-forwarded-for")
                .and_then(|value| value.to_str().ok())
                .and_then(|value| {
                    value
                        .split(',')
                        .rev()
                        .filter_map(|part| part.trim().parse::<IpAddr>().ok())
                        .find(|address| !trusted_proxies.contains(address))
                })
                .or_else(|| {
                    headers
                        .get("x-real-ip")
                        .and_then(|value| value.to_str().ok())
                        .and_then(|value| value.parse().ok())
                })
        });
    forwarded.or(peer).map(|address| address.to_string()).unwrap_or_else(|| "unknown".to_string())
}

async fn request_rules(
    state: &AppState,
    path: &str,
    method: &Method,
    headers: &HeaderMap,
    peer: Option<IpAddr>,
) -> Vec<RateRule> {
    let ip = client_ip(&state.config.trusted_proxy_ips, headers, peer);
    let writes = matches!(method.as_str(), "POST" | "PUT" | "PATCH" | "DELETE");
    let mut rules = Vec::new();

    if path == "/oauth/start" {
        rules.push(RateRule { scope: "oauth-ip", subject: ip, maximum: 20 });
    } else if path == "/oauth/callback" {
        rules.push(RateRule { scope: "oauth-callback-ip", subject: ip, maximum: 30 });
    } else if path.starts_with("/api/") {
        rules.push(RateRule { scope: "api-ip", subject: ip.clone(), maximum: 150 });
        if writes {
            rules.push(RateRule { scope: "write-ip", subject: ip.clone(), maximum: 35 });
            if let Ok((_, session)) = session_from_headers(state, headers).await {
                rules.push(RateRule { scope: "write-account", subject: session.user.id, maximum: 30 });
            }
            if let Some(guild_id) = path.split('/').nth(3).filter(|id| {
                !id.is_empty() && id.bytes().all(|byte| byte.is_ascii_digit())
            }) {
                rules.push(RateRule { scope: "write-guild", subject: guild_id.to_string(), maximum: 45 });
            }
        }
        if path.ends_with("/atlas") {
            rules.push(RateRule { scope: "atlas-ip", subject: ip, maximum: 18 });
        }
    } else if path.starts_with("/custom-roles/api/") {
        rules.push(RateRule {
            scope: "picker-api-ip",
            subject: ip,
            maximum: if writes { 35 } else { 120 },
        });
    }
    rules
}

pub async fn check_request(
    state: &AppState,
    path: &str,
    method: &Method,
    headers: &HeaderMap,
    peer: Option<IpAddr>,
) -> Result<(), RateLimitError> {
    let rules = request_rules(state, path, method, headers, peer).await;
    let now = now_secs();
    for rule in rules {
        match state.store.allow_rate_event(rule.scope, &rule.subject, now, 60, rule.maximum).await {
            Ok(true) => {}
            Ok(false) => return Err(RateLimitError::Limited),
            Err(_) => return Err(RateLimitError::Unavailable),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forwarded_ip_is_ignored_when_peer_is_not_trusted() {
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "198.51.100.42".parse().unwrap());
        assert_eq!(
            client_ip(&HashSet::new(), &headers, Some("203.0.113.4".parse().unwrap())),
            "203.0.113.4"
        );
    }

    #[test]
    fn trusted_proxy_chain_resolves_to_the_nearest_untrusted_address() {
        let trusted = HashSet::from([
            "10.0.0.1".parse().unwrap(),
            "10.0.0.2".parse().unwrap(),
        ]);
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "198.51.100.42, 10.0.0.2".parse().unwrap());
        assert_eq!(
            client_ip(&trusted, &headers, Some("10.0.0.1".parse().unwrap())),
            "198.51.100.42"
        );
    }
}

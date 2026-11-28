use std::collections::{HashMap, HashSet};

use axum::http::{HeaderMap, Method};
use serde_json::Value;

use crate::state::{
    access_token, bridge_json, can_manage_guild, discord_json, session_from_headers,
    ApiError, ApiResult, AppState, DashboardGuild, Session, ADMINISTRATOR,
};

const BOT_INVITE_PERMISSIONS: &str = "268823616";

pub fn can_list_guild(can_manage_server: bool, invited_by_user: bool) -> bool {
    can_manage_server || invited_by_user
}

pub fn bot_invite_url(client_id: &str, guild_id: &str) -> Option<String> {
    if client_id.is_empty()
        || !client_id.bytes().all(|byte| byte.is_ascii_digit())
        || guild_id.is_empty()
        || !guild_id.bytes().all(|byte| byte.is_ascii_digit())
    {
        return None;
    }

    let mut url = reqwest::Url::parse("https://discord.com/oauth2/authorize").ok()?;
    url.query_pairs_mut()
        .append_pair("client_id", client_id)
        .append_pair("scope", "bot applications.commands")
        .append_pair("permissions", BOT_INVITE_PERMISSIONS)
        .append_pair("guild_id", guild_id)
        .append_pair("disable_guild_select", "true");
    Some(url.to_string())
}

pub async fn manageable_guilds(
    state: &AppState,
    session_id: &str,
    _session: &Session,
) -> ApiResult<Vec<DashboardGuild>> {
    let token = access_token(state, session_id).await?;
    let user_guilds = discord_json(state, "/users/@me/guilds", &token).await?;
    let bot_guilds = bridge_json(state, Method::GET, "/guilds", None).await?;
    let invited = bridge_json(
        state,
        Method::GET,
        &format!("/invited-guilds/{}", _session.user.id),
        None,
    ).await?;
    let invited_guilds: HashSet<String> = invited.get("guild_ids")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(ToOwned::to_owned)
        .collect();
    let bot_map: HashMap<String, Value> = bot_guilds.as_array().into_iter().flatten()
        .filter_map(|guild| guild.get("id").and_then(Value::as_str)
            .map(|id| (id.to_string(), guild.clone())))
        .collect();

    let mut result = Vec::new();
    for guild in user_guilds.as_array().into_iter().flatten() {
        let id = match guild.get("id").and_then(Value::as_str) {
            Some(id) => id,
            None => continue,
        };
        let permissions = guild.get("permissions").and_then(Value::as_str)
            .and_then(|value| value.parse::<u64>().ok())
            .or_else(|| guild.get("permissions").and_then(Value::as_u64))
            .unwrap_or(0);
        let can_manage_server = can_manage_guild(permissions);
        if !can_list_guild(can_manage_server, invited_guilds.contains(id)) {
            continue;
        }

        let bot_guild = bot_map.get(id);
        let bot_installed = bot_guild.is_some();
        let name = guild.get("name").and_then(Value::as_str)
            .or_else(|| bot_guild.and_then(|item| item.get("name")).and_then(Value::as_str))
            .unwrap_or("Discord server")
            .to_string();
        let icon = guild.get("icon").and_then(Value::as_str)
            .or_else(|| bot_guild.and_then(|item| item.get("icon")).and_then(Value::as_str))
            .map(ToOwned::to_owned);

        result.push(DashboardGuild {
            id: id.to_string(),
            name,
            icon,
            administrator: permissions & ADMINISTRATOR != 0,
            can_manage_server,
            member_count: bot_guild.and_then(|item| item.get("member_count")).and_then(Value::as_u64),
            bot_installed,
            invite_url: if bot_installed { None } else { bot_invite_url(&state.config.client_id, id) },
        });
    }
    result.sort_by_key(|guild| guild.name.to_lowercase());
    Ok(result)
}

pub async fn authorized_guild(
    state: &AppState,
    headers: &HeaderMap,
    guild_id: &str,
) -> ApiResult<(String, Session, DashboardGuild)> {
    if guild_id.is_empty() || !guild_id.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(ApiError::bad_request("Invalid guild identifier."));
    }
    let (id, session) = session_from_headers(state, headers).await?;
    let guilds = manageable_guilds(state, &id, &session).await?;
    let guild = guilds.into_iter().find(|guild| guild.id == guild_id)
        .ok_or_else(|| ApiError::forbidden("You do not have permission to manage this server."))?;
    if !guild.can_manage_server {
        return Err(ApiError::forbidden("Manage Server or Administrator permission is required for this dashboard section."));
    }
    if !guild.bot_installed {
        return Err(ApiError::forbidden("Lemegeton is not installed in this server yet. Invite the bot before opening its configuration."));
    }
    Ok((id, session, guild))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inviters_can_reach_only_the_server_setup_entry() {
        assert!(can_list_guild(false, true));
        assert!(can_list_guild(true, false));
        assert!(!can_list_guild(false, false));
    }

    #[test]
    fn invite_urls_pin_the_target_server_and_request_the_bot_permissions() {
        let url = reqwest::Url::parse(
            &bot_invite_url("123456789012345678", "987654321098765432").unwrap()
        ).unwrap();
        let pairs: HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(url.host_str(), Some("discord.com"));
        assert_eq!(pairs.get("client_id").map(String::as_str), Some("123456789012345678"));
        assert_eq!(pairs.get("scope").map(String::as_str), Some("bot applications.commands"));
        assert_eq!(pairs.get("permissions").map(String::as_str), Some(BOT_INVITE_PERMISSIONS));
        assert_eq!(pairs.get("guild_id").map(String::as_str), Some("987654321098765432"));
        assert_eq!(pairs.get("disable_guild_select").map(String::as_str), Some("true"));
    }

    #[test]
    fn invite_urls_reject_non_discord_identifiers() {
        assert!(bot_invite_url("not-an-app-id", "987654321098765432").is_none());
        assert!(bot_invite_url("123456789012345678", "not-a-guild").is_none());
    }
}

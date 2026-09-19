"""
Discord Embed Helper Functions
Centralized functions for building Discord embeds for various content types
"""

import discord
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "embed_helper.log"

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("EmbedHelper")
logger.setLevel(logging.DEBUG)

# Clear handlers to avoid duplicates
logger.handlers.clear()

# Create file handler
file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)

logger.info("Embed Helper logging system initialized")


# ===== ANILIST ACTIVITY EMBEDS =====

def build_activity_embed(activity: dict, activity_type: str, user: dict, text: str, 
                        media_links: list, likes: int, comments: int = 0) -> discord.Embed:
    """
    Build embed for AniList activities (TextActivity, MessageActivity, ListActivity, Reply).
    """
    from helpers.anilist_helper import clean_anilist_text
    
    embed = discord.Embed(color=discord.Color.blurple())
    clean = clean_anilist_text(text)

    # TextActivity
    if activity_type == "TextActivity":
        embed.set_author(
            name=(user or {}).get("name", "Unknown"),
            url=(user or {}).get("siteUrl", ""),
            icon_url=((user or {}).get("avatar") or {}).get("large")
        )
        embed.description = clean or "*No content*"

    # MessageActivity
    elif activity_type == "MessageActivity":
        recipient = activity.get("recipient") or {}
        rec_name = (recipient or {}).get("name", "Unknown")
        embed.set_author(
            name=(user or {}).get("name", "Unknown"),
            url=(user or {}).get("siteUrl", ""),
            icon_url=((user or {}).get("avatar") or {}).get("large")
        )
        embed.description = f"To **{rec_name}**\n\n{clean or '*No message text*'}"

    # ListActivity
    elif activity_type == "ListActivity":
        media = activity.get("media") or {}
        progress = activity.get("progress") or activity.get("status") or ""
        title = (media.get("title") or {}).get("romaji", "Unknown")
        cover = (media.get("coverImage") or {}).get("large")
        url = media.get("siteUrl")
        embed.set_author(
            name=(user or {}).get("name", "Unknown"),
            url=(user or {}).get("siteUrl", ""),
            icon_url=((user or {}).get("avatar") or {}).get("large")
        )
        if progress:
            embed.title = f"Read Chapter {progress} of {title}"
        else:
            embed.title = f"{title}"
        if url:
            embed.url = url
        if clean:
            embed.description = clean
        else:
            embed.description = f"Read Chapter {progress} {title}" if progress else title
        if cover:
            embed.set_thumbnail(url=cover)

    # Reply
    elif activity_type == "Reply":
        embed.set_author(
            name=f"💬 {(user or {}).get('name', 'Unknown')}",
            url=(user or {}).get("siteUrl", ""),
            icon_url=((user or {}).get("avatar") or {}).get("large")
        )
        embed.description = clean or "*No reply text*"

    else:
        embed.set_author(
            name=(user or {}).get("name", "Unknown"),
            url=(user or {}).get("siteUrl", ""),
            icon_url=((user or {}).get("avatar") or {}).get("large")
        )
        embed.description = clean or "*No content*"

    # Stats
    stats = f"❤️ {likes or 0}"
    if comments:
        stats += f" | 💬 {comments}"
    embed.add_field(name="Stats", value=stats, inline=True)

    # Media attachments
    if media_links:
        first = media_links[0]
        if any(first.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
            embed.set_image(url=first)
        else:
            embed.add_field(name="🔗 Media", value=f"[Click here]({first})", inline=False)
        for extra in media_links[1:]:
            embed.add_field(name="🔗 Media", value=f"[Click here]({extra})", inline=False)

    embed.set_footer(text="Powered by AniList")
    return embed


# ===== ANILIST MEDIA EMBEDS =====

def build_media_embed(media: dict) -> discord.Embed:
    """
    Build summary embed for AniList media (anime/manga).
    """
    from helpers.anilist_helper import clean_anilist_text, format_date
    
    # Title construction
    title_romaji = (media.get("title") or {}).get("romaji")
    title_eng = (media.get("title") or {}).get("english")
    title_native = (media.get("title") or {}).get("native")
    title_line = title_romaji or title_eng or title_native or "Unknown Title"
    if title_eng and title_eng != title_romaji:
        title_line += f" ({title_eng})"
    if title_native and title_native not in (title_romaji, title_eng):
        title_line += f" | {title_native}"

    # Description
    desc_raw = media.get("description") or ""
    desc = clean_anilist_text(desc_raw)
    short_desc = desc[:800].rstrip()
    if len(desc) > 800:
        short_desc += "..."

    embed = discord.Embed(
        title=title_line, 
        url=media.get("siteUrl"), 
        description=short_desc or "*No synopsis available*", 
        color=discord.Color.blurple()
    )

    # Cover and banner
    cover = (media.get("coverImage") or {}).get("large")
    if cover:
        embed.set_thumbnail(url=cover)

    banner = media.get("bannerImage")
    if banner:
        embed.set_image(url=banner)

    # Basic meta info
    meta_lines = []
    if media.get("type"):
        meta_lines.append(f"**Type:** {media['type']}")
    if media.get("status"):
        meta_lines.append(f"**Status:** {media['status']}")
    if media.get("episodes") is not None:
        meta_lines.append(f"**Episodes:** {media.get('episodes')}")
    if media.get("chapters") is not None:
        meta_lines.append(f"**Chapters:** {media.get('chapters')}")
    if media.get("volumes") is not None:
        meta_lines.append(f"**Volumes:** {media.get('volumes')}")
    if media.get("startDate"):
        meta_lines.append(f"**Start:** {format_date(media.get('startDate'))}")
    if media.get("endDate"):
        meta_lines.append(f"**End:** {format_date(media.get('endDate'))}")

    if meta_lines:
        embed.add_field(name="Info", value="\n".join(meta_lines), inline=False)

    # Studios
    studios_nodes = (media.get("studios") or {}).get("nodes") or []
    if studios_nodes:
        studios_str = ", ".join(n.get("name") for n in studios_nodes if n.get("name"))
        embed.add_field(name="Studio", value=studios_str or "—", inline=True)

    # Stats
    stats_lines = []
    if media.get("popularity") is not None:
        stats_lines.append(f"🔥 Popularity: {media['popularity']}")
    if media.get("favourites") is not None:
        stats_lines.append(f"❤️ Favourites: {media['favourites']}")
    if media.get("source"):
        stats_lines.append(f"🔗 Source: {media['source']}")
    if stats_lines:
        embed.add_field(name="Stats", value="\n".join(stats_lines), inline=True)

    # Main characters
    char_edges = (media.get("characters") or {}).get("edges") or []
    main_chars = [e for e in char_edges if (e.get("role") or "").upper() == "MAIN"] or char_edges
    if main_chars:
        lines = []
        for e in main_chars[:6]:
            node = e.get("node") or {}
            name = (node.get("name") or {}).get("full") or "Unknown"
            cid = node.get("id")
            char_url = f"https://anilist.co/character/{cid}" if cid else ""
            lines.append(f"[{name}]({char_url})")
        embed.add_field(name="Main Characters", value=" • ".join(lines), inline=False)

    embed.set_footer(text="AniList Media")
    return embed


def build_relations_embed(media: dict) -> List[discord.Embed]:
    """Build embeds for media relations."""
    relations = (media.get("relations") or {}).get("edges") or []
    if not relations:
        return [discord.Embed(description="No relations found.", color=discord.Color.greyple())]

    embeds = []
    chunk_size = 6
    for i in range(0, len(relations), chunk_size):
        chunk = relations[i:i + chunk_size]
        em = discord.Embed(title="Relations", color=discord.Color.dark_blue())
        for edge in chunk:
            rel_type = edge.get("relationType") or ""
            node = edge.get("node") or {}
            node_title = (node.get("title") or {}).get("romaji") or (node.get("title") or {}).get("english") or "Unknown"
            url = node.get("siteUrl") or f"https://anilist.co/{node.get('type', '').lower()}/{node.get('id')}" if node.get("id") else None
            value = f"[{node_title}]({url})" if url else node_title
            field_name = rel_type if rel_type else (node.get("type") or "Related")
            em.add_field(name=field_name, value=value, inline=False)
        
        # Set thumbnail as first cover if present
        first_cover = (chunk[0].get("node") or {}).get("coverImage", {}).get("large")
        if first_cover:
            em.set_thumbnail(url=first_cover)
        embeds.append(em)
    return embeds


def build_characters_embed(media: dict, support: bool = False) -> List[discord.Embed]:
    """Build embeds for characters (main or support)."""
    char_edges = (media.get("characters") or {}).get("edges") or []
    if not char_edges:
        return [discord.Embed(description="No characters found.", color=discord.Color.greyple())]

    if support:
        selected = [e for e in char_edges if (e.get("role") or "").upper() != "MAIN"]
        title = "Support Cast"
    else:
        selected = [e for e in char_edges if (e.get("role") or "").upper() == "MAIN"]
        title = "Main Characters"
    
    if not selected:
        selected = char_edges[:10]

    embeds = []
    chunk_size = 6
    for i in range(0, len(selected), chunk_size):
        chunk = selected[i:i + chunk_size]
        em = discord.Embed(title=title, color=discord.Color.blurple())
        for e in chunk:
            node = e.get("node") or {}
            name = (node.get("name") or {}).get("full") or "Unknown"
            cid = node.get("id")
            url = f"https://anilist.co/character/{cid}" if cid else None
            value = f"[AniList]({url})" if url else "—"
            em.add_field(name=name, value=value, inline=False)
        
        # Thumbnail of first character if exists
        first_img = (chunk[0].get("node") or {}).get("image", {}).get("large")
        if first_img:
            em.set_thumbnail(url=first_img)
        embeds.append(em)
    return embeds


def build_staff_embed(media: dict) -> List[discord.Embed]:
    """Build embeds for staff."""
    staff_edges = (media.get("staff") or {}).get("edges") or []
    if not staff_edges:
        return [discord.Embed(description="No staff info found.", color=discord.Color.greyple())]
    
    embeds = []
    chunk_size = 8
    for i in range(0, len(staff_edges), chunk_size):
        chunk = staff_edges[i:i + chunk_size]
        em = discord.Embed(title="Staff", color=discord.Color.dark_teal())
        for edge in chunk:
            role = edge.get("role") or "Staff"
            node = edge.get("node") or {}
            name = (node.get("name") or {}).get("full") or "Unknown"
            sid = node.get("id")
            url = f"https://anilist.co/staff/{sid}" if sid else None
            value = f"{role}\n" + (f"[AniList]({url})" if url else "")
            em.add_field(name=name, value=value, inline=False)
        
        first_img = (chunk[0].get("node") or {}).get("image", {}).get("large")
        if first_img:
            em.set_thumbnail(url=first_img)
        embeds.append(em)
    return embeds


def build_stats_embed(media: dict) -> discord.Embed:
    """Build embed for stats distribution."""
    stats = media.get("stats") or {}
    em = discord.Embed(title="Stats Distribution", color=discord.Color.green())
    
    # Status distribution
    status_dist = stats.get("statusDistribution") or []
    if status_dist:
        lines = []
        for s in status_dist:
            st = s.get("status") or "Unknown"
            amt = s.get("amount") or 0
            lines.append(f"**{st.title()}** — {amt} users")
        em.add_field(name="Status Distribution", value="\n".join(lines), inline=False)
    
    # Score distribution
    score_dist = stats.get("scoreDistribution") or []
    if score_dist:
        sd_lines = []
        for s in sorted(score_dist, key=lambda x: int(x.get("score", 0))):
            sc = s.get("score")
            amt = s.get("amount")
            sd_lines.append(f"{sc}: {amt}")
        em.add_field(name="Score Distribution", value=" | ".join(sd_lines), inline=False)
    
    if not em.fields:
        em.description = "No statistical distribution data available."
    return em


def build_recommendations_embed(media: dict, max_items: int = 5) -> discord.Embed:
    """Build embed for recommendations."""
    recs = (media.get("recommendations") or {}).get("edges") or []
    em = discord.Embed(title="🎯 Recommendations", description="Top recommendations from AniList", color=discord.Color.gold())
    
    count = 0
    for e in recs:
        node = e.get("node") or {}
        rec = node.get("mediaRecommendation") or {}
        title = (rec.get("title") or {}).get("romaji") or (rec.get("title") or {}).get("english") or "Unknown"
        url = rec.get("siteUrl") or ""
        cover = (rec.get("coverImage") or {}).get("large")
        em.add_field(name=title, value=f"[AniList]({url})", inline=False)
        
        if cover:
            em.set_thumbnail(url=cover)
        count += 1
        if count >= max_items:
            break
    
    if count == 0:
        em.description = "No recommendations found."
    em.set_footer(text="AniList Recommendations")
    return em


def build_tags_embed(media: dict) -> discord.Embed:
    """Build embed for tags."""
    tags = media.get("tags") or []
    if not tags:
        return discord.Embed(description="No tags found.", color=discord.Color.greyple())
    
    em = discord.Embed(title="Tags", color=discord.Color.dark_purple())
    lines = []
    for t in tags:
        name = t.get("name") or "Unknown"
        rank = t.get("rank")
        disp = f"||{name}||"
        if rank is not None:
            disp += f" — #{rank}"
        lines.append(disp)
    em.description = "  \n".join(lines)
    return em


# ===== USER PROFILE EMBEDS =====

def build_user_profile_embed(user_data: dict, anime_stats: dict, manga_stats: dict) -> discord.Embed:
    """Build main user profile embed."""
    username = user_data.get("name", "Unknown User")
    avatar_url = (user_data.get("avatar") or {}).get("large", "")
    profile_url = user_data.get("siteUrl", "")
    banner_url = user_data.get("bannerImage", "")

    embed = discord.Embed(
        title=f"📊 {username}'s AniList Profile",
        url=profile_url,
        color=discord.Color.blue()
    )

    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    if banner_url:
        embed.set_image(url=banner_url)

    # Anime stats
    anime_count = anime_stats.get("count", 0)
    anime_score = anime_stats.get("meanScore", 0)
    episodes_watched = anime_stats.get("episodesWatched", 0)
    minutes_watched = anime_stats.get("minutesWatched", 0)
    
    anime_text = f"**Count:** {anime_count:,}\n**Mean Score:** {anime_score}/100\n**Episodes:** {episodes_watched:,}\n**Minutes:** {minutes_watched:,}"
    embed.add_field(name="🎬 Anime", value=anime_text, inline=True)

    # Manga stats
    manga_count = manga_stats.get("count", 0)
    manga_score = manga_stats.get("meanScore", 0)
    chapters_read = manga_stats.get("chaptersRead", 0)
    volumes_read = manga_stats.get("volumesRead", 0)
    
    manga_text = f"**Count:** {manga_count:,}\n**Mean Score:** {manga_score}/100\n**Chapters:** {chapters_read:,}\n**Volumes:** {volumes_read:,}"
    embed.add_field(name="📖 Manga", value=manga_text, inline=True)

    embed.set_footer(text="Fetched from AniList")
    return embed


def build_favorites_embed(user_data: dict, avatar_url: str, profile_url: str) -> discord.Embed:
    """Build favorites overview embed."""
    username = user_data.get("name", "Unknown User")
    favourites = user_data.get("favourites", {})

    embed = discord.Embed(
        title=f"❤️ {username}'s Favorites",
        url=profile_url,
        color=discord.Color.red()
    )

    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    # Count favorites
    anime_count = len(favourites.get("anime", {}).get("nodes", []))
    manga_count = len(favourites.get("manga", {}).get("nodes", []))
    character_count = len(favourites.get("characters", {}).get("nodes", []))
    staff_count = len(favourites.get("staff", {}).get("nodes", []))
    studio_count = len(favourites.get("studios", {}).get("nodes", []))

    embed.add_field(name="🎬 Anime", value=f"{anime_count} favorites", inline=True)
    embed.add_field(name="📖 Manga", value=f"{manga_count} favorites", inline=True)
    embed.add_field(name="👤 Characters", value=f"{character_count} favorites", inline=True)
    embed.add_field(name="🎭 Staff", value=f"{staff_count} favorites", inline=True)
    embed.add_field(name="🏢 Studios", value=f"{studio_count} favorites", inline=True)

    embed.set_footer(text="Use the buttons below to view specific categories")
    return embed


def build_steam_profile_embed(
    player: dict,
    steamid: str,
    level: int,
    total_games: int,
    friend_count: int,
    library_stats: Optional[dict],
    vac_status: Optional[dict],
    badge_count: Optional[int],
    summary_text: Optional[str],
    top_games: list,
    fallback_color: Optional[discord.Color] = None,
) -> discord.Embed:
    """Build the main /steam-profile embed (status, stats, bans, bio, top games)."""
    pstate = player.get("personastate", 0)
    if pstate == 1:
        color = discord.Color.green()
    elif pstate == 0:
        color = discord.Color.red()
    else:
        color = fallback_color or discord.Color.blurple()

    status_map = {
        0: "🔴 Offline",
        1: "🟢 Online",
        2: "⛔ Busy",
        3: "🌙 Away",
        4: "💤 Snooze",
        5: "🔄 Looking to trade",
        6: "🎮 Looking to play",
    }
    status_text = status_map.get(pstate, "❔ Unknown")

    embed = discord.Embed(
        title=f"{player.get('personaname', 'Unknown')} — {status_text}",
        url=player.get("profileurl"),
        color=color,
    )
    avatar_url = player.get("avatarfull")
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)

    embed.add_field(name="🆔 SteamID", value=f"`{steamid}`", inline=False)
    embed.add_field(name="⭐ Level", value=str(level), inline=True)
    embed.add_field(name="🎮 Games Owned", value=f"{total_games:,}", inline=True)
    embed.add_field(name="👥 Friends", value=f"{friend_count:,}", inline=True)

    if library_stats:
        total_hours = library_stats.get("total_playtime_hours", 0)
        never_played_count = library_stats.get("never_played", 0)
        never_played_pct = library_stats.get("never_played_percentage", 0)
        estimated_value = library_stats.get("estimated_value", 0)

        embed.add_field(name="⏱️ Total Playtime", value=f"{total_hours:,.0f} hours", inline=True)
        embed.add_field(
            name="📊 Unplayed Games",
            value=f"{never_played_count} ({never_played_pct:.1f}%)",
            inline=True,
        )
        embed.add_field(name="💰 Est. Library Value", value=f"~${estimated_value:,}", inline=True)

    if vac_status:
        vac_banned = vac_status.get("VACBanned", False)
        game_bans = vac_status.get("NumberOfGameBans", 0)
        days_since_ban = vac_status.get("DaysSinceLastBan", 0)

        if vac_banned or game_bans > 0:
            ban_info = []
            if vac_banned:
                ban_info.append("🚫 VAC Banned")
            if game_bans > 0:
                ban_info.append(f"🚫 {game_bans} Game Ban(s)")
            if days_since_ban > 0:
                ban_info.append(f"({days_since_ban} days ago)")

            embed.add_field(name="⚠️ Ban Status", value=" • ".join(ban_info), inline=False)
        else:
            embed.add_field(name="✅ Account Status", value="Good Standing", inline=False)

    embed.add_field(
        name="🏅 Badges",
        value=str(badge_count) if badge_count is not None else "Unknown",
        inline=True,
    )

    rn = player.get("realname")
    loc = player.get("loccountrycode")
    embed.add_field(name="🧑 Real Name", value=rn or "N/A", inline=True)
    embed.add_field(name="🌍 Location", value=loc or "N/A", inline=True)

    embed.add_field(
        name="📝 Bio",
        value=(
            (summary_text[:900] + "…" if summary_text and len(summary_text) > 900 else summary_text)
            if summary_text
            else "N/A"
        ),
        inline=False,
    )

    if top_games:
        preview = []
        for g in top_games[:3]:
            nm = g.get("name", "Unknown")
            hours = g.get("playtime_forever", 0) // 60
            preview.append(f"**{nm}** — {hours}h")
        embed.add_field(name="🏆 Top Games (preview)", value="\n".join(preview), inline=False)

    embed.set_footer(text="ℹ️ Details • 👁 Toggle Visibility to make private")
    return embed


def build_game_carousel_embed(
    game: dict,
    index: int,
    total_results: int,
    query: str,
    other_result_names: list,
    deck_badge: str = "",
    controller_badge: str = "",
) -> discord.Embed:
    """Build one page of the /steam-game search-results carousel."""
    from helpers.gaming_utils import get_protondb_url

    name = game.get("name", "Unknown")
    app_id = game.get("steam_appid")
    header_img = game.get("header_image")
    short_desc = game.get("short_description", "")
    if len(short_desc) > 200:
        short_desc = short_desc[:197] + "..."

    price_info = game.get("price_overview", {})
    is_free = game.get("is_free", False)
    if is_free:
        price = "Free to Play"
        color = discord.Color.green()
    elif price_info:
        final_price = price_info.get("final_formatted", "N/A")
        discount = price_info.get("discount_percent", 0)
        if discount > 0:
            original = price_info.get("initial_formatted")
            price = f"~~{original}~~ **{final_price}** (-{discount}%)"
            color = discord.Color.gold()
        else:
            price = final_price
            color = discord.Color.blue()
    else:
        price = "Price N/A"
        color = discord.Color.dark_gray()

    release_data = game.get("release_date", {})
    release = release_data.get("date", "Unknown")
    coming_soon = release_data.get("coming_soon", False)
    is_early_access = any(cat.get("description") == "Early Access" for cat in game.get("categories", []))

    genres = [g["description"] for g in game.get("genres", [])][:3]
    genre_str = ", ".join(genres) if genres else "Unknown"

    title_badges = []
    if coming_soon:
        title_badges.append("🔜 Coming Soon")
    elif is_early_access:
        title_badges.append("🚧 Early Access")
    title_suffix = f" ({' • '.join(title_badges)})" if title_badges else ""

    embed = discord.Embed(
        title=f"🎮 {name}{title_suffix}",
        description=short_desc,
        color=color,
        url=f"https://store.steampowered.com/app/{app_id}",
    )

    if header_img:
        embed.set_image(url=header_img)

    embed.add_field(name="💰 Price", value=price, inline=True)
    embed.add_field(name="📅 Release", value=release, inline=True)
    embed.add_field(name="🎯 Genres", value=genre_str, inline=True)

    compat_badges = [b for b in (deck_badge, controller_badge) if b]
    if compat_badges:
        embed.add_field(name="🎮 Compatibility", value="\n".join(compat_badges), inline=False)

    categories = [c.get("description", "") for c in game.get("categories", [])]
    multiplayer_types = []
    if any("Multi-player" in c for c in categories):
        multiplayer_types.append("Multiplayer")
    if any("Co-op" in c for c in categories):
        multiplayer_types.append("Co-op")
    if any("Online PvP" in c for c in categories):
        multiplayer_types.append("PvP")
    if any("Cross-Platform" in c for c in categories):
        multiplayer_types.append("Cross-Platform")
    if multiplayer_types:
        embed.add_field(name="👥 Play Modes", value=" • ".join(multiplayer_types), inline=True)

    if "Online Co-op" in categories or "Online PvP" in categories:
        embed.add_field(
            name="🔗 Links",
            value=f"[ProtonDB]({get_protondb_url(app_id)}) • [Steam Store](https://store.steampowered.com/app/{app_id})",
            inline=True,
        )

    if other_result_names:
        embed.add_field(
            name="Other Results:",
            value="\n".join(f"• {n}" for n in other_result_names),
            inline=False,
        )

    embed.set_footer(text=f"Result {index + 1} of {total_results} • Search: '{query}'")
    return embed


# ===== GENERAL UTILITY EMBEDS =====

def build_error_embed(title: str, description: str, color: discord.Color = discord.Color.red()) -> discord.Embed:
    """Build a standardized error embed."""
    embed = discord.Embed(
        title=f"❌ {title}",
        description=description,
        color=color
    )
    return embed


def build_success_embed(title: str, description: str, color: discord.Color = discord.Color.green()) -> discord.Embed:
    """Build a standardized success embed."""
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=color
    )
    return embed


def build_warning_embed(title: str, description: str, color: discord.Color = discord.Color.orange()) -> discord.Embed:
    """Build a standardized warning embed."""
    embed = discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=color
    )
    return embed


def build_info_embed(title: str, description: str, color: discord.Color = discord.Color.blue()) -> discord.Embed:
    """Build a standardized info embed."""
    embed = discord.Embed(
        title=f"ℹ️ {title}",
        description=description,
        color=color
    )
    return embed


def build_trending_embed(media_list: List[Dict], title: str, description: str) -> discord.Embed:
    """Build embed for trending media lists."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.gold()
    )
    
    for i, media in enumerate(media_list[:10], 1):
        media_title = (media.get("title") or {}).get("romaji") or (media.get("title") or {}).get("english") or "Unknown"
        score = media.get("averageScore", "N/A")
        url = media.get("siteUrl", "")
        
        value = f"Score: {score}%"
        if url:
            value = f"[{value}]({url})"
            
        embed.add_field(
            name=f"{i}. {media_title}",
            value=value,
            inline=False
        )
    
    embed.set_footer(text="Fetched from AniList")
    return embed
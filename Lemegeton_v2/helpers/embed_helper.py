"""
Discord Embed Helper Functions
Centralized functions for building Discord embeds for various content types
"""

import discord
import logging
from typing import List, Optional, Any
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


def build_media_search_result_embed(
    media: dict,
    real_type: str,
    description: str,
    genres: str,
    start_str: str,
    end_str: str,
    title: Optional[str] = None,
    footer_text: str = "Fetched from AniList",
    color: Optional[discord.Color] = None,
) -> discord.Embed:
    """
    Build the main AniList search-result embed shared by browse.py's /browse
    command and random.py's random-media result. Caller precomputes the
    truncated description, genre string, formatted date strings, and title
    text (the two cogs use different romaji/english precedence — pass yours
    explicitly rather than relying on this function's fallback).
    """
    if title is None:
        title = media['title']['english'] or media['title']['romaji']

    embed = discord.Embed(
        title=f"{'🎬' if real_type == 'ANIME' else '📖'} {title}",
        url=media.get("siteUrl"),
        description=description,
        color=color or discord.Color.random()
    )

    cover_url = media.get("coverImage", {}).get("medium") or media.get("coverImage", {}).get("large")
    if cover_url:
        embed.set_thumbnail(url=cover_url)

    banner_url = media.get("bannerImage")
    if banner_url:
        embed.set_image(url=banner_url)

    embed.add_field(name="⭐ Average Score", value=f"{media.get('averageScore', 'N/A')}%", inline=True)
    embed.add_field(name="📌 Status", value=media.get("status", "Unknown"), inline=True)

    if real_type == "ANIME":
        embed.add_field(name="📺 Episodes", value=media.get("episodes", '?'), inline=True)
    else:
        embed.add_field(name="📖 Chapters", value=media.get("chapters", '?'), inline=True)
        embed.add_field(name="📚 Volumes", value=media.get("volumes", '?'), inline=True)

    embed.add_field(name="🎭 Genres", value=genres, inline=False)
    embed.add_field(name="📅 Published", value=f"**Start:** {start_str}\n**End:** {end_str}", inline=False)

    mal_link = None
    for link in media.get("externalLinks", []):
        if link.get("site") == "MyAnimeList":
            mal_link = link.get("url")
            break
    if mal_link:
        embed.add_field(name="🔗 MyAnimeList", value=f"[View on MAL]({mal_link})", inline=False)

    embed.set_footer(text=footer_text)
    return embed


def build_google_books_result_embed(book: dict) -> discord.Embed:
    """Build the Google Books search-result embed used by browse.py's /browse command."""
    embed = discord.Embed(
        title=f"📚 {book.get('title', 'Unknown')}",
        url=book.get("infoLink"),
        description=book.get("description", "No description available."),
        color=discord.Color.random()
    )

    if "imageLinks" in book:
        embed.set_thumbnail(url=book["imageLinks"].get("thumbnail"))

    authors = ", ".join(book.get("authors", [])) if "authors" in book else "Unknown"
    embed.add_field(name="✍️ Authors", value=authors, inline=True)
    embed.add_field(name="📅 Published", value=book.get("publishedDate", "Unknown"), inline=True)
    embed.add_field(name="🏢 Publisher", value=book.get("publisher", "Unknown"), inline=True)
    embed.add_field(name="📄 Pages", value=book.get("pageCount", "Unknown"), inline=True)
    embed.add_field(name="⭐ Rating", value=str(book.get("averageRating", "?")) + "/5", inline=True)

    embed.set_footer(text="Fetched from Google Books")
    return embed


def build_recommendation_result_embed(
    media: dict,
    vote_count: int,
    category: str,
    index: int,
    total: int,
    username: str,
    description: str,
) -> discord.Embed:
    """
    Build the manga-recommendation result embed used by recommendations.py's
    create_embed(). Caller precomputes the truncated description (via its own
    truncate_description() helper) just like browse.py/random.py do.
    """
    title = media['title']['english'] or media['title']['romaji']

    embed = discord.Embed(
        title=f"📖 {title}",
        url=f"https://anilist.co/manga/{media['id']}",
        description=description,
        color=discord.Color.blue()
    )

    cover_url = media.get('coverImage', {}).get('large')
    if cover_url:
        embed.set_thumbnail(url=cover_url)

    embed.add_field(
        name="⭐ Average Score",
        value=f"{media.get('averageScore', 'N/A')}%" if media.get('averageScore') else "N/A",
        inline=True
    )
    embed.add_field(
        name="📌 Status",
        value=media.get('status', 'Unknown').replace('_', ' ').title(),
        inline=True
    )
    embed.add_field(
        name="👥 Recommendation Votes",
        value=f"{vote_count} votes",
        inline=True
    )

    if media.get('chapters'):
        embed.add_field(name="📖 Chapters", value=media.get('chapters', '?'), inline=True)
    if media.get('volumes'):
        embed.add_field(name="📚 Volumes", value=media.get('volumes', '?'), inline=True)

    format_type = (media.get('format') or '').replace('_', ' ').title()
    if format_type:
        embed.add_field(name="📋 Format", value=format_type, inline=True)

    genres = media.get('genres', [])
    if genres:
        genre_text = ', '.join(genres[:5])
        if len(genres) > 5:
            genre_text += f" +{len(genres) - 5} more"
        embed.add_field(name="🎭 Genres", value=genre_text, inline=False)

    start_date = media.get('startDate', {})
    if start_date and start_date.get('year'):
        embed.add_field(name="📅 Start Date", value=f"{start_date.get('year', '?')}", inline=True)

    embed.set_footer(
        text=f"{category.title()} Recommendation {index + 1}/{total} • Recommended for {username}",
        icon_url="https://anilist.co/img/icons/android-chrome-512x512.png"
    )
    return embed


def build_feedback_submission_embed(type_choice, description: str, user, image=None) -> discord.Embed:
    """
    Build the submission embed posted to the feedback channel by
    feedback.py's /feedback command.
    """
    color = discord.Color.green() if type_choice.value == "ideas" else discord.Color.red()
    embed = discord.Embed(
        title=f"New {type_choice.name} Submitted",
        description=description,
        color=color
    )
    embed.set_author(
        name=user.display_name,
        icon_url=user.avatar.url if user.avatar else None
    )
    embed.set_footer(text=f"Submitted by {user}")

    if image:
        embed.set_image(url=image.url)

    return embed


def build_affinity_comparison_embed(
    requester_name: str,
    target_name: str,
    score: float,
    breakdown: dict,
    cached: bool = False,
) -> discord.Embed:
    """
    Build the single-user affinity comparison embed used by affinity.py's
    /affinity command. Shared by the cached and freshly-calculated paths,
    which previously built this embed with duplicated inline code.
    """
    if score >= 80:
        color = discord.Color.gold()
    elif score >= 60:
        color = discord.Color.green()
    elif score >= 40:
        color = discord.Color.orange()
    else:
        color = discord.Color.red()

    embed = discord.Embed(
        title=f"💞 Affinity Between {requester_name} and {target_name}",
        color=color
    )
    embed.add_field(name="🎯 Affinity Score", value=f"**{score}%**", inline=True)
    embed.add_field(
        name="📊 Breakdown",
        value=(
            f"**Favorites:** {breakdown.get('favorites', 0):.1f}%\n"
            f"**Consumption:** {breakdown.get('consumption', 0):.1f}%\n"
            f"**Scoring:** {breakdown.get('scoring', 0):.1f}%\n"
            f"**Genres:** {breakdown.get('genres', 0):.1f}%\n"
            f"**Formats:** {breakdown.get('formats', 0):.1f}%\n"
            f"**Activity:** {breakdown.get('activity', 0):.1f}%\n"
            f"**Balance:** {breakdown.get('balance', 0):.1f}%"
        ),
        inline=True
    )
    footer = "Higher scores indicate better compatibility!"
    if cached:
        footer += " (Cached data)"
    embed.set_footer(text=footer)
    return embed


def build_login_status_embed(user_data: dict, display_name: str, guild_name: str) -> discord.Embed:
    """Build the /login command's account-status embed.

    Renders one of two layouts depending on whether the user has any
    connection at all: a green "connection status + available actions"
    embed when at least one service is connected, or an orange
    "welcome, here's how to connect" embed otherwise.
    """
    if user_data['anilist_connected'] or user_data['steam_connected']:
        embed = discord.Embed(
            title="🔐 Account Management",
            description=f"Welcome back, **{display_name}**!\n\n"
                       f"Here's your connection status in **{guild_name}**:",
            color=discord.Color.green()
        )

        status_lines = []
        if user_data['anilist_connected']:
            status_lines.append(f"📝 **AniList**: {user_data['anilist_username']}")
        else:
            status_lines.append("📝 **AniList**: Not connected")

        if user_data['steam_connected']:
            status_lines.append(f"🎮 **Steam**: {user_data['steam_vanity']}")
        else:
            status_lines.append("🎮 **Steam**: Not connected")

        embed.add_field(
            name="Connection Status",
            value="\n".join(status_lines),
            inline=False
        )

        embed.add_field(
            name="Available Actions",
            value="📝 **AniList** - Register or update your AniList username\n"
                  "🎮 **Steam** - Register or update your Steam profile\n"
                  "🗑️ **Unregister** - Remove specific service connections\n"
                  "ℹ️ **Status** - View detailed account information",
            inline=False
        )
    else:
        embed = discord.Embed(
            title="🔐 Welcome to the Bot!",
            description=f"Hello **{display_name}**!\n\n"
                       f"❌ **Status**: Not Connected in **{guild_name}**\n\n"
                       f"To use this bot's features, you can connect your accounts:\n"
                       f"• **AniList** - For anime/manga tracking features\n"
                       f"• **Steam** - For gaming features\n\n"
                       f"Use the buttons below to get started:",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="Available Actions",
            value="📝 **AniList** - Connect your AniList account\n"
                  "🎮 **Steam** - Connect your Steam profile\n"
                  "ℹ️ **Status** - View account information",
            inline=False
        )

    embed.set_footer(text="Your data is secure and can be removed anytime")
    return embed
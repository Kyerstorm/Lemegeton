# anilist.py

import re
import aiohttp
import asyncio
import discord
from discord.ext import commands
from discord import ui
import math
import logging
from typing import Optional, Dict, Any, List
from database import (
    get_all_users,
    get_all_users_guild_aware,
    get_all_paginator_states,
    set_paginator_state,
    delete_paginator_state,
    get_paginator_state
)
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("AniListCog")
logger.setLevel(logging.INFO)

ANILIST_API = "https://graphql.anilist.co"
ACTIVITY_URL_RE = re.compile(r"https?://anilist\.co/activity/(\d+)", re.IGNORECASE)
ANIME_URL_RE = re.compile(r"https?://anilist\.co/anime/(\d+)(?:/[^/\s]+)?/?", re.IGNORECASE)
MANGA_URL_RE = re.compile(r"https?://anilist\.co/manga/(\d+)(?:/[^/\s]+)?/?", re.IGNORECASE)

REVIEW_URL_RE = re.compile(r"https?://anilist\.co/review/(\d+)", re.IGNORECASE)

REPLIES_PER_PAGE = 5
HTML_TIMEOUT = 15  # seconds for parsing fallback HTTP requests

# DEFAULT EMBED COLOR requested by user
DEFAULT_EMBED_COLOR = 0x0F1720

# Enhanced Progress Filtering Options
class ProgressFilter(Enum):
    ALL = "all"  # Default: show all users
    ACTIVE_ONLY = "active_only"  # Users with >0 progress
    COMPLETED_ONLY = "completed_only"  # Users who completed the series
    HIGH_SCORERS = "high_scorers"  # Users with 8+ ratings
    RECENT_ACTIVITY = "recent_activity"  # Active within 30 days
    CUSTOM_RANGE = "custom_range"  # Progress between X-Y
    WATCHING_NOW = "watching_now"  # Currently watching/reading
    DROPPED = "dropped"  # Users who dropped the series

PROGRESS_FILTER_OPTIONS = {
    ProgressFilter.ALL: {
        "label": "🌟 All Users",
        "description": "Show all registered users",
        "emoji": "🌟"
    },
    ProgressFilter.ACTIVE_ONLY: {
        "label": "⚡ Active Users", 
        "description": "Users with progress > 0",
        "emoji": "⚡"
    },
    ProgressFilter.COMPLETED_ONLY: {
        "label": "✅ Completed Only",
        "description": "Users who finished the series", 
        "emoji": "✅"
    },
    ProgressFilter.HIGH_SCORERS: {
        "label": "⭐ High Scorers",
        "description": "Users with 8+ ratings",
        "emoji": "⭐"
    },
    ProgressFilter.WATCHING_NOW: {
        "label": "📺 Currently Active",
        "description": "Users actively watching/reading",
        "emoji": "📺"
    },
    ProgressFilter.DROPPED: {
        "label": "❌ Dropped",
        "description": "Users who dropped the series",
        "emoji": "❌"
    }
}


class AniListCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self._views_restored = False

    async def cog_unload(self):
        await self.session.close()


    # ---------------------
    # Enhanced User Progress System
    # ---------------------
    async def build_user_progress_embed(self, media: dict, media_type: str, guild_id: int, filter_type: ProgressFilter = ProgressFilter.ACTIVE_ONLY) -> Optional[discord.Embed]:
        """Build embed showing registered users' progress for a given media with enhanced filtering"""
        import time
        start_time = time.time()
        logger.info(f"Building user progress embed for media ID: {media.get('id')}, type: {media_type}, filter: {filter_type.value}")
        
        try:
            users = await get_all_users_guild_aware(guild_id)
            logger.info(f"Retrieved {len(users) if users else 0} users from database for guild {guild_id}")
            
            if not users:
                return discord.Embed(
                    title="👥 Registered Users' Progress",
                    description="No registered users found.",
                    color=discord.Color.red()
                )

            col_name = "Episodes" if media_type.upper() == "ANIME" else "Chapters"
            
            # Enhanced filtering with progress insights
            filtered_users_data = []
            total_users_checked = 0
            
            # Use a single session for all requests to improve performance
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                for user in users:
                    discord_name = user[3]  # Discord username (from username column)
                    anilist_username = user[4] if len(user) > 4 else None  # AniList username
                    
                    if not anilist_username:
                        logger.debug(f"Skipping user {discord_name} - no AniList username")
                        continue
                    
                    total_users_checked += 1
                    logger.debug(f"Fetching progress for {discord_name} (AniList: {anilist_username})")
                    
                    # Enhanced query to get more progress details for filtering
                    query = """
                    query($userName: String, $mediaId: Int, $type: MediaType) {
                        User(name: $userName) {
                            mediaListOptions { scoreFormat }
                        }
                        MediaList(userName: $userName, mediaId: $mediaId, type: $type) {
                            progress
                            score
                            status
                            updatedAt
                            startedAt { year month day }
                            completedAt { year month day }
                        }
                    }
                    """
                    variables = {"userName": anilist_username, "mediaId": media.get("id", 0), "type": media_type}

                    try:
                        async with session.post(ANILIST_API, 
                                              json={"query": query, "variables": variables},
                                              timeout=10) as resp:
                            if resp.status != 200:
                                logger.debug(f"API error {resp.status} for user {anilist_username}")
                                continue
                            payload = await resp.json()
                    except asyncio.TimeoutError:
                        logger.debug(f"Timeout fetching progress for {anilist_username}")
                        continue
                    except Exception as e:
                        logger.debug(f"Error fetching progress for {anilist_username}: {e}")
                        continue
                    
                    user_data = payload.get("data", {}).get("User")
                    media_list = payload.get("data", {}).get("MediaList")
                    
                    if not user_data:
                        logger.debug(f"No user data found for {anilist_username}")
                        continue
                    
                    # Collect comprehensive user progress data
                    progress = media_list.get("progress", 0) if media_list else 0
                    score = media_list.get("score", 0) if media_list else 0
                    status = media_list.get("status") if media_list else None
                    updated_at = media_list.get("updatedAt") if media_list else None
                    
                    # Calculate if user is recently active (within 30 days)
                    is_recent = False
                    if updated_at:
                        try:
                            updated_time = datetime.fromtimestamp(updated_at)
                            is_recent = (datetime.now() - updated_time) <= timedelta(days=30)
                        except:
                            is_recent = False
                    
                    # Create user data object for filtering
                    user_progress_data = {
                        "discord_name": discord_name,
                        "anilist_username": anilist_username,
                        "progress": progress,
                        "score": score,
                        "status": status,
                        "is_recent": is_recent,
                        "score_format": user_data.get("mediaListOptions", {}).get("scoreFormat", "POINT_10")
                    }
                    
                    # Apply filtering logic
                    should_include = self._apply_progress_filter(user_progress_data, filter_type, media)
                    
                    if should_include:
                        filtered_users_data.append(user_progress_data)
                    
                    if len(filtered_users_data) >= 20:  # Limit display to avoid embed size issues
                        break
            
            # Build the progress display with insights
            return self._build_filtered_progress_embed(filtered_users_data, media, media_type, filter_type, col_name, total_users_checked, time.time() - start_time)
            
        except Exception as e:
            logger.error(f"Error building user progress embed: {e}", exc_info=True)
            return discord.Embed(
                title="👥 Registered Users' Progress",
                description="❌ An error occurred while fetching user progress data.",
                color=discord.Color.red()
            )

    def _apply_progress_filter(self, user_data: dict, filter_type: ProgressFilter, media: dict) -> bool:
        """Apply filtering logic to determine if user should be included"""
        progress = user_data["progress"]
        score = user_data["score"]
        status = user_data["status"]
        is_recent = user_data["is_recent"]
        
        if filter_type == ProgressFilter.ALL:
            return True
        elif filter_type == ProgressFilter.ACTIVE_ONLY:
            return progress > 0
        elif filter_type == ProgressFilter.COMPLETED_ONLY:
            return status == "COMPLETED" or progress >= self._get_total_episodes_chapters(media)
        elif filter_type == ProgressFilter.HIGH_SCORERS:
            return score >= 8
        elif filter_type == ProgressFilter.RECENT_ACTIVITY:
            return is_recent and progress > 0
        elif filter_type == ProgressFilter.WATCHING_NOW:
            return status in ["CURRENT", "REPEATING"] or (progress > 0 and status != "COMPLETED")
        elif filter_type == ProgressFilter.DROPPED:
            return status == "DROPPED"
        else:
            return True  # Default to showing all
    
    def _get_total_episodes_chapters(self, media: dict) -> int:
        """Get total episodes or chapters for completion checking"""
        return media.get("episodes") or media.get("chapters") or float('inf')
    
    def _build_filtered_progress_embed(self, filtered_data: List[dict], media: dict, media_type: str, 
                                     filter_type: ProgressFilter, col_name: str, total_checked: int, elapsed_time: float) -> discord.Embed:
        """Build the final embed with filtered progress data and insights"""
        filter_info = PROGRESS_FILTER_OPTIONS[filter_type]
        
        if not filtered_data:
            return discord.Embed(
                title=f"{filter_info['emoji']} User Progress - {filter_info['label']}",
                description=f"No users found matching filter: {filter_info['description']}",
                color=discord.Color.orange()
            )
        
        # Build progress lines
        progress_lines = [f"`{'User':<20} {col_name:<10} {'Rating':<7} {'Status':<10}`"]
        progress_lines.append("`{:-<20} {:-<10} {:-<7} {:-<10}`".format("", "", "", ""))
        
        for user_data in filtered_data:
            progress = user_data["progress"]
            score = user_data["score"]
            status = user_data["status"] or "UNKNOWN"
            
            # Format score display - normalize all to /10 scale
            score_format = user_data["score_format"]
            if score == 0:
                score_display = "-"
            elif score_format == "POINT_100":
                # Convert 100-point to 10-point scale
                normalized_score = score / 10.0
                score_display = f"{normalized_score:.1f}/10"
            elif score_format == "POINT_10_DECIMAL":
                score_display = f"{score:.1f}/10"
            elif score_format == "POINT_5":
                # Convert 5-star to 10-point scale
                normalized_score = (score / 5.0) * 10.0
                score_display = f"{normalized_score:.1f}/10"
            elif score_format == "POINT_3":
                # Convert 3-point to 10-point scale  
                normalized_score = (score / 3.0) * 10.0
                score_display = f"{normalized_score:.1f}/10"
            else:  # POINT_10 or others
                score_display = f"{score:.1f}/10"
            
            # Format status display
            status_display = status[:9] if status else "-"
            
            progress_lines.append(f"`{user_data['anilist_username'][:19]:<20} {progress:<10} {score_display:<7} {status_display:<10}`")
        
        # Calculate insights
        avg_progress = sum(u["progress"] for u in filtered_data) / len(filtered_data) if filtered_data else 0
        avg_score = sum(u["score"] for u in filtered_data if u["score"] > 0) / max(1, sum(1 for u in filtered_data if u["score"] > 0))
        
        embed = discord.Embed(
            title=f"{filter_info['emoji']} User Progress - {filter_info['label']}",
            description="\n".join(progress_lines[:25]),  # Limit to prevent embed overflow
            color=discord.Color.blue()
        )
        
        # Add insights footer
        insights = []
        if filtered_data:
            insights.append(f"📊 Showing {len(filtered_data)}/{total_checked} users")
            insights.append(f"📈 Avg Progress: {avg_progress:.1f}")
            if avg_score > 0:
                insights.append(f"⭐ Avg Score: {avg_score:.1f}")
        
        embed.set_footer(text=" | ".join(insights) + f" | Fetched in {elapsed_time:.2f}s")
        
        return embed


    
    # ---------------------
    # Persistence helpers (using database)
    # ---------------------
    async def _load_state(self) -> Dict[str, Any]:
        """Load paginator state from database."""
        try:
            return await get_all_paginator_states()
        except Exception:
            logger.exception("Failed to load paginator state from database, starting fresh.")
            return {"messages": {}, "media_messages": {}}

    async def _save_state(self, state: Dict[str, Any]):
        """Save state is now handled by individual set_paginator_state calls."""
        pass  # No longer needed - state is saved per-message in database

    # Activity persistence (messages)
    async def _add_paginator_persistence(self, message_id: int, channel_id: int, activity_id: int, total_pages: int, current_page: int = 1):
        """Add activity paginator persistence to database."""
        guild_id = str(channel_id)  # We'll need to get guild_id properly in production
        await set_paginator_state(
            message_id=str(message_id),
            channel_id=str(channel_id),
            guild_id=guild_id,
            state_type='activity',
            total_pages=total_pages,
            current_page=current_page,
            activity_id=activity_id
        )
        view = self.Paginator(self, message_id, channel_id, activity_id, total_pages, current_page)
        try:
            self.bot.add_view(view, message_id=message_id)
        except Exception:
            logger.exception("Failed to add_view for activity paginator (non-fatal).")
        return view

    async def _remove_paginator_persistence(self, message_id: int):
        """Remove activity paginator persistence from database."""
        await delete_paginator_state(str(message_id))

    # Media persistence
    async def _add_media_persistence(self, message_id: int, channel_id: int, media_id: int, media_type: str, total_pages: int, current_page: int = 1):
        """Add media paginator persistence to database."""
        guild_id = str(channel_id)  # We'll need to get guild_id properly in production
        await set_paginator_state(
            message_id=str(message_id),
            channel_id=str(channel_id),
            guild_id=guild_id,
            state_type='media',
            total_pages=total_pages,
            current_page=current_page,
            media_id=media_id,
            media_type=media_type
        )
        view = self.MediaPaginator(self, message_id, channel_id, media_id, media_type, total_pages, current_page)
        try:
            self.bot.add_view(view, message_id=message_id)
        except Exception:
            logger.exception("Failed to add_view for media paginator (non-fatal).")
        return view

    async def _remove_media_persistence(self, message_id: int):
        """Remove media paginator persistence from database."""
        await delete_paginator_state(str(message_id))

    async def restore_persistent_views(self):
        """Restore paginator views from database on bot startup."""
        state = await self._load_state()
        # Restore activity paginators
        for mid, info in list(state.get("messages", {}).items()):
            try:
                view = self.Paginator(
                    self,
                    int(mid),
                    int(info.get("channel_id", 0)),
                    int(info.get("activity_id", 0)),
                    int(info.get("total_pages", 1)),
                    int(info.get("current_page", 1)),
                )
                self.bot.add_view(view, message_id=int(mid))
            except Exception:
                logger.exception("Failed to restore persistent paginator for message %s", mid)

        # Restore media paginators
        for mid, info in list(state.get("media_messages", {}).items()):
            try:
                view = self.MediaPaginator(
                    self,
                    int(mid),
                    int(info.get("channel_id", 0)),
                    int(info.get("media_id", 0)),
                    info.get("media_type", "ANIME"),
                    int(info.get("total_pages", 1)),
                    int(info.get("current_page", 1)),
                )
                self.bot.add_view(view, message_id=int(mid))
            except Exception:
                logger.exception("Failed to restore persistent media paginator for message %s", mid)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._views_restored:
            await self.restore_persistent_views()
            self._views_restored = True

    # ---------------------
    # Text cleaning / media extraction
    # ---------------------
    def clean_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        # convert <br> tags first
        text = re.sub(r"<br\s*/?>", "\n", text)
        # convert AniList style ~!(...)!~ spoilers to Discord spoilers
        text = re.sub(r"~!(.*?)!~", r"||\1||", text, flags=re.S)
        # convert ~[link](url)~ style to strikethrough of the link in Discord
        text = re.sub(r'~\[(.*?)\]\((https?://[^\s)]+)\)~', r'~~[\1](\2)~~', text)
        # convert general ~text~ to strikethrough (avoid the ones already converted to spoilers/strikethrough)
        # but only convert single-line non-markdown bracketed tildes
        text = re.sub(r'(?<!~)~([^!\[].*?)~(?!~)', r'~~\1~~', text, flags=re.S)
        # remove remaining HTML tags but keep link syntax [text](url)
        # preserve markdown links by not stripping inside brackets and parentheses
        # simple approach: remove tags
        text = re.sub(r"<[^>]+>", "", text)
        # remove weird AniList media placeholders we don't want in Discord
        text = re.sub(r"~+imgx?\((https?://[^\s)]+)\)~+", r"\1", text)
        text = re.sub(r"~+vid\((https?://[^\s)]+)\)~+", r"\1", text)
        # replace multiple consecutive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # headers to bold/underline where possible
        text = re.sub(r"^# (.+)$", r"__**\1**__", text, flags=re.M)
        text = re.sub(r"^## (.+)$", r"**\1**", text, flags=re.M)
        text = re.sub(r"^### (.+)$", r"_\1_", text, flags=re.M)
        return text.strip()

    def extract_media(self, text: Optional[str]):
        if not text:
            return [], ""
        media_links = []
        # explicit placeholders
        for m in re.finditer(r"(?:imgx?|vid)\((https?://[^\s)]+)\)", text):
            media_links.append(m.group(1))
        # plain direct image links
        for m in re.finditer(r"(https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.gif|\.webp))", text):
            url = m.group(1)
            if url not in media_links:
                media_links.append(url)
        # remove those links from the cleaned text so they don't appear twice
        cleaned = re.sub(r"(?:imgx?|vid)\((https?://[^\s)]+)\)", "", text)
        cleaned = re.sub(r"https?://[^\s]+(?:\.png|\.jpg|\.jpeg|\.gif|\.mp4|\.webm|\.webp)", "", cleaned)
        return media_links, cleaned.strip()

    # ---------------------
    # Activity-related code
    # ---------------------

    # Build embed for activity / replies
    def build_embed(self, activity: dict, activity_type: str, user: dict, text: str, media_links: list, likes: int, comments: int = 0):
        embed = discord.Embed(color=discord.Color.blurple())
        clean = self.clean_text(text)

        if activity_type == "TextActivity":
            embed.set_author(
                name=(user or {}).get("name", "Unknown"),
                url=(user or {}).get("siteUrl", ""),
                icon_url=((user or {}).get("avatar") or {}).get("large")
            )
            embed.description = clean or "*No content*"

        elif activity_type == "MessageActivity":
            recipient = activity.get("recipient", {}) if activity else {}
            rec_name = (recipient or {}).get("name", "Unknown")
            embed.set_author(
                name=(user or {}).get("name", "Unknown"),
                url=(user or {}).get("siteUrl", ""),
                icon_url=((user or {}).get("avatar") or {}).get("large")
            )
            embed.description = f"To **{rec_name}**\n\n{clean or '*No message text*'}"

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

        stats = f"❤️ {likes or 0}"
        if comments:
            stats += f" | 💬 {comments}"
        embed.add_field(name="Stats", value=stats, inline=True)

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

    async def fetch_activity(self, activity_id: int) -> Optional[dict]:
        query = """
        query($id: Int) {
          Activity(id: $id) {
            __typename
            ... on TextActivity {
              id
              text
              likeCount
              replyCount
              siteUrl
              user { id name siteUrl avatar { large } }
              replies { id text likeCount user { id name siteUrl avatar { large } } }
            }
            ... on MessageActivity {
              id
              message
              likeCount
              replyCount
              siteUrl
              messenger { id name siteUrl avatar { large } }
              recipient { id name siteUrl avatar { large } }
              replies { id text likeCount user { id name siteUrl avatar { large } } }
            }
            ... on ListActivity {
              id
              status
              progress
              likeCount
              replyCount
              siteUrl
              user { id name siteUrl avatar { large } }
              media { id siteUrl title { romaji } coverImage { large } bannerImage }
              replies { id text likeCount user { id name siteUrl avatar { large } } }
            }
          }
        }
        """
        try:
            async with self.session.post(ANILIST_API, json={"query": query, "variables": {"id": activity_id}}) as resp:
                text = await resp.text()
                try:
                    js = await resp.json()
                except Exception:
                    js = None

                if resp.status != 200:
                    logger.error("AniList API error %s: %s", resp.status, text)
                    return None

                if not js or "data" not in js or js["data"].get("Activity") is None:
                    logger.warning("AniList returned no Activity for id %s. Response: %s", activity_id, text)
                    return None

                return js["data"]["Activity"]
        except Exception:
            logger.exception("AniList API fetch failed.")
            return None

    async def render_page(self, activity: Optional[dict], page: int):
        embeds: List[discord.Embed] = []
        if not activity:
            e = discord.Embed(
                title="❌ Activity not found",
                description="This AniList activity is missing, deleted, or could not be retrieved.",
                color=discord.Color.red()
            )
            embeds.append(e)
            return embeds

        activity_type = activity.get("__typename", "Unknown")
        if activity_type == "MessageActivity":
            user = activity.get("messenger") or {}
            text = activity.get("message") or ""
        else:
            user = activity.get("user") or {}
            text = activity.get("text") or activity.get("status") or ""

        # Page 1 = main activity only
        if page == 1:
            media, _ = self.extract_media(text)
            likes = activity.get("likeCount", 0)
            comments = activity.get("replyCount", 0)
            embed = self.build_embed(activity, activity_type, user, text, media, likes, comments)
            embeds.append(embed)
            return embeds

        # Page >= 2 -> replies
        replies = activity.get("replies") or []
        start = (page - 2) * REPLIES_PER_PAGE
        end = start + REPLIES_PER_PAGE
        sliced = replies[start:end]
        for reply in sliced:
            r_user = reply.get("user") or {}
            r_text = reply.get("text") or ""
            media, _ = self.extract_media(r_text)
            r_likes = reply.get("likeCount", 0)
            reply_embed = self.build_embed(activity, "Reply", r_user, r_text, media, r_likes)
            embeds.append(reply_embed)
        if not embeds:
            embeds.append(discord.Embed(description="No replies on this page.", color=discord.Color.greyple()))
        return embeds

    # Activity paginator (persistent)
    class Paginator(ui.View):
        def __init__(self, cog: "AniListCog", message_id: int, channel_id: int, activity_id: int, total_pages: int, current_page: int = 1):
            super().__init__(timeout=None)
            self.cog = cog
            self.message_id = str(message_id)
            self.channel_id = int(channel_id)
            self.activity_id = int(activity_id)
            self.total_pages = max(1, int(total_pages))
            self.current_page = max(1, int(current_page))

            self.prev_btn = ui.Button(label="⬅ Prev", style=discord.ButtonStyle.primary, custom_id=f"anilist:prev:{self.message_id}")
            self.next_btn = ui.Button(label="Next ➡", style=discord.ButtonStyle.primary, custom_id=f"anilist:next:{self.message_id}")

            self.prev_btn.disabled = (self.current_page <= 1)
            self.next_btn.disabled = (self.current_page >= self.total_pages)

            self.prev_btn.callback = self.prev_page
            self.next_btn.callback = self.next_page

            self.add_item(self.prev_btn)
            self.add_item(self.next_btn)

        async def _load_message_state(self):
            """Load state for this specific message from the database."""
            return await get_paginator_state(str(self.message_id))

        async def _save_message_state(self, new_state: Dict[str, Any]):
            """Save state for this specific message to the database."""
            current_page = new_state.get("current_page", self.current_page)
            await set_paginator_state(
                message_id=str(self.message_id),
                channel_id=str(self.channel_id),
                guild_id=str(self.channel_id),  # Using channel_id as guild_id placeholder
                state_type='activity',
                total_pages=self.total_pages,
                current_page=current_page,
                activity_id=self.activity_id
            )

        def _update_buttons_disabled(self):
            self.prev_btn.disabled = (self.current_page <= 1)
            self.next_btn.disabled = (self.current_page >= self.total_pages)

        async def prev_page(self, interaction: discord.Interaction):
            try:
                msg_state = await self._load_message_state()
                if not msg_state:
                    await interaction.response.send_message("⚠️ Paginator state missing.", ephemeral=True)
                    return
                current = int(msg_state.get("current_page", self.current_page))
                if current <= 1:
                    await interaction.response.send_message("You are already on the first page.", ephemeral=True)
                    return
                new_page = current - 1
                activity = await self.cog.fetch_activity(self.activity_id)
                if not activity:
                    await interaction.response.send_message("⚠️ Could not fetch AniList activity.", ephemeral=True)
                    return
                embeds = await self.cog.render_page(activity, new_page)
                msg_state["current_page"] = new_page
                await self._save_message_state(msg_state)
                self.current_page = new_page
                self._update_buttons_disabled()
                try:
                    await interaction.response.edit_message(embeds=embeds, view=self)
                except discord.HTTPException:
                    await interaction.response.send_message("⚠️ Could not update the message (it may have been deleted).", ephemeral=True)
                    await self.cog._remove_paginator_persistence(int(self.message_id))
            except Exception:
                logger.exception("Paginator prev_page failure")
                try:
                    await interaction.response.send_message("⚠️ Failed to change page.", ephemeral=True)
                except Exception:
                    pass

        async def next_page(self, interaction: discord.Interaction):
            try:
                msg_state = await self._load_message_state()
                if not msg_state:
                    await interaction.response.send_message("⚠️ Paginator state missing.", ephemeral=True)
                    return
                current = int(msg_state.get("current_page", self.current_page))
                if current >= int(msg_state.get("total_pages", self.total_pages)):
                    await interaction.response.send_message("You are already on the last page.", ephemeral=True)
                    return
                new_page = current + 1
                activity = await self.cog.fetch_activity(self.activity_id)
                if not activity:
                    await interaction.response.send_message("⚠️ Could not fetch AniList activity.", ephemeral=True)
                    return
                embeds = await self.cog.render_page(activity, new_page)
                msg_state["current_page"] = new_page
                await self._save_message_state(msg_state)
                self.current_page = new_page
                self._update_buttons_disabled()
                try:
                    await interaction.response.edit_message(embeds=embeds, view=self)
                except discord.HTTPException:
                    await interaction.response.send_message("⚠️ Could not update the message (it may have been deleted).", ephemeral=True)
                    await self.cog._remove_paginator_persistence(int(self.message_id))
            except Exception:
                logger.exception("Paginator next_page failure")
                try:
                    await interaction.response.send_message("⚠️ Failed to change page.", ephemeral=True)
                except Exception:
                    pass

    # ---------------------
    # MEDIA: GraphQL fetch + Parsing fallback
    # ---------------------
    async def fetch_media_api(self, media_id: int, media_type: str) -> Optional[dict]:
        query = """
        query($id: Int, $type: MediaType) {
          Media(id: $id, type: $type) {
            id
            siteUrl
            title { romaji english native }
            description(asHtml: false)
            coverImage { large extraLarge }
            bannerImage
            episodes
            chapters
            volumes
            status
            startDate { year month day }
            endDate { year month day }
            studios(isMain: true) { nodes { name siteUrl } }
            popularity
            favourites
            source
            tags { name isAdult rank }
            staff(perPage: 50) {
              edges { role node { id name { full native } siteUrl image { large } } }
            }
            characters(perPage: 50) {
              edges { role node { id name { full native } siteUrl image { large } } }
            }
            relations { edges { relationType node { id type siteUrl title { romaji english native } coverImage { large } } } }
            stats { scoreDistribution { score amount } statusDistribution { status amount } }
            recommendations { edges { node { mediaRecommendation { id title { romaji english } coverImage { large } siteUrl } } } }
          }
        }
        """
        variables = {"id": media_id, "type": media_type}
        try:
            async with self.session.post(ANILIST_API, json={"query": query, "variables": variables}, timeout=30) as resp:
                text = await resp.text()
                try:
                    js = await resp.json()
                except Exception:
                    js = None
                if resp.status != 200:
                    logger.error("AniList media API error %s: %s", resp.status, text)
                    return None
                if not js or "data" not in js or js["data"].get("Media") is None:
                    logger.warning("AniList returned no Media for id %s. Response: %s", media_id, text)
                    return None
                return js["data"]["Media"]
        except Exception as e:
            logger.exception("AniList media API fetch failed.")
            return None

    async def fetch_media_parse_fallback(self, media_id: int, media_type: str) -> Optional[dict]:
        """
        Parsing fallback: attempt to fetch the AniList HTML page and extract key fields.
        This is a best-effort fallback and logs progress percentages.
        """
        base = "anime" if media_type.upper().startswith("ANIME") else "manga"
        url = f"https://anilist.co/{base}/{media_id}"
        logger.info("Parsing mode started: 0% — attempting HTML fallback for %s", url)
        progress = 0

        try:
            # Step 1: fetch HTML
            progress = 10
            logger.info("Parsing mode: %d%% — fetching HTML...", progress)
            async with self.session.get(url, timeout=HTML_TIMEOUT, headers={"User-Agent": "AniListBot/1.0"}) as resp:
                html = await resp.text()
        except Exception as e:
            logger.exception("Parsing fetch failed at 10%%")
            return None
        progress = 30
        logger.info("Parsing mode: %d%% — HTML fetched, extracting meta...", progress)

        try:
            # Step 2: extract Open Graph tags (og:title, og:description, og:image)
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html)
            og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', html)
            og_image = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
            title = og_title.group(1).strip() if og_title else None
            description = og_desc.group(1).strip() if og_desc else None
            banner = og_image.group(1).strip() if og_image else None
        except Exception:
            title = description = banner = None

        logger.info("Parsing mode: 50%% — parsed basic OG meta")
        progress = 50

        # Step 3: cover image — look for link rel image_src or specific coverImage JSON
        cover = None
        try:
            # search for cover in JSON LD or data-react-props blocks
            m_cover = re.search(r'coverImage["\']:\s*{\s*["\']large["\']:\s*["\']([^"\']+)["\']', html)
            if not m_cover:
                m_cover = re.search(r'<meta\s+property=["\']og:image:secure_url["\']\s+content=["\']([^"\']+)["\']', html)
            if m_cover:
                cover = m_cover.group(1).strip()
        except Exception:
            cover = None

        progress = 65
        logger.info("Parsing mode: %d%% — cover found? %s", progress, bool(cover))

        # Step 4: basic stats extraction (episodes/chapters/status/start/end/popularity/favs)
        episodes = chapters = volumes = None
        status = None
        start_date = end_date = None
        popularity = None
        favourites = None
        source = None
        try:
            # simple heuristics: look for "Episodes" label nearby numbers
            m_eps = re.search(r'Episodes</dt>\s*<dd[^>]*>\s*([0-9,]+)\s*</dd>', html)
            if m_eps:
                episodes = int(m_eps.group(1).replace(",", ""))
            m_ch = re.search(r'Chapters</dt>\s*<dd[^>]*>\s*([0-9,]+)\s*</dd>', html)
            if m_ch:
                chapters = int(m_ch.group(1).replace(",", ""))
            m_vol = re.search(r'Volumes</dt>\s*<dd[^>]*>\s*([0-9,]+)\s*</dd>', html)
            if m_vol:
                volumes = int(m_vol.group(1).replace(",", ""))
            m_status = re.search(r'Status</dt>\s*<dd[^>]*>\s*([^<]+)</dd>', html)
            if m_status:
                status = m_status.group(1).strip()
            # start / end dates
            m_start = re.search(r'Started airing</dt>.*?<dd[^>]*>\s*([^<]+)</dd>', html, re.S)
            if m_start:
                start_date = m_start.group(1).strip()
            m_start2 = re.search(r'Published</dt>.*?<dd[^>]*>\s*([^<]+)</dd>', html, re.S)
            if m_start2 and not start_date:
                start_date = m_start2.group(1).strip()
            # popularity/favs
            m_pop = re.search(r'Popularity</dt>\s*<dd[^>]*>\s*([0-9,]+)\s*</dd>', html)
            if m_pop:
                popularity = int(m_pop.group(1).replace(",", ""))
            m_fav = re.search(r'Favorites</dt>\s*<dd[^>]*>\s*([0-9,]+)\s*</dd>', html)
            if m_fav:
                favourites = int(m_fav.group(1).replace(",", ""))
            # source
            m_src = re.search(r'Source</dt>\s*<dd[^>]*>\s*([^<]+)</dd>', html)
            if m_src:
                source = m_src.group(1).strip()
        except Exception:
            logger.exception("Parsing stats extraction failed (non-fatal)")

        progress = 85
        logger.info("Parsing mode: %d%% — stats extracted (episodes/chapters/status/popularity)", progress)

        # Step 5: attempt to find studios or author
        studios = []
        try:
            for m in re.finditer(r'<a[^>]+href=["\']https?://anilist.co/[^"\']*studio/[^"\']+["\'][^>]*>([^<]+)</a>', html):
                name = m.group(1).strip()
                if name and name not in studios:
                    studios.append({"name": name})
        except Exception:
            pass

        progress = 95
        logger.info("Parsing mode: %d%% — studios parsed (%d found)", progress, len(studios))

        # Build fallback media dict with fields similar to API
        media = {
            "id": media_id,
            "siteUrl": url,
            "title": {"romaji": title or f"Media {media_id}", "english": None, "native": None},
            "description": description or "",
            "coverImage": {"large": cover} if cover else {},
            "bannerImage": banner or None,
            "episodes": episodes,
            "chapters": chapters,
            "volumes": volumes,
            "status": status,
            "startDate": {"year": None, "month": None, "day": None},
            "endDate": {"year": None, "month": None, "day": None},
            "studios": {"nodes": studios},
            "popularity": popularity,
            "favourites": favourites,
            "source": source,
            # minimal empty placeholders for other fields used by UI
            "tags": [],
            "relations": {"edges": []},
            "characters": {"edges": []},
            "staff": {"edges": []},
            "stats": {},
            "recommendations": {"edges": []},
        }

        progress = 100
        logger.info("Parsing mode: %d%% — completed fallback parse for %s", progress, url)
        return media

    async def fetch_media(self, media_id: int, media_type: str) -> Optional[dict]:
        """
        Primary: try GraphQL API. If that fails or returns None, fall back to parse fallback.
        Logs errors and announces parsing mode start in logs with percent progress.
        """
        api_resp = await self.fetch_media_api(media_id, media_type)
        if api_resp:
            return api_resp
        # API failed — log and start parsing fallback
        logger.warning("AniList API failed for media %s %s — starting parsing fallback", media_type, media_id)
        parsed = await self.fetch_media_parse_fallback(media_id, media_type)
        if parsed:
            logger.info("Parsing fallback succeeded for media %s %s", media_type, media_id)
        else:
            logger.error("Parsing fallback failed for media %s %s", media_type, media_id)
        return parsed

    # fetch_media_api delegates to the proper query (kept same as previous fetch_media_api)
    async def fetch_media_api(self, media_id: int, media_type: str) -> Optional[dict]:
        # (same GraphQL query used previously; using smaller page sizes to avoid big responses)
        query = """
        query($id: Int, $type: MediaType) {
          Media(id: $id, type: $type) {
            id
            siteUrl
            title { romaji english native }
            description(asHtml: false)
            coverImage { large extraLarge color }
            bannerImage
            episodes
            chapters
            volumes
            status
            startDate { year month day }
            endDate { year month day }
            studios(isMain: true) { nodes { id name siteUrl } }
            popularity
            favourites
            source
            tags { id name isAdult rank isMediaSpoiler }
            staff(perPage:50) { edges { role node { id name { full native } siteUrl image { large } } } }
            characters(perPage:50) { edges { role node { id name { full native } siteUrl image { large } } } }
            relations { edges { relationType node { id type siteUrl title { romaji english native } coverImage { large } } } }
            stats { scoreDistribution { score amount } statusDistribution { status amount } }
            recommendations { edges { node { mediaRecommendation { id title { romaji english } coverImage { large } siteUrl } } } }
          }
        }
        """
        variables = {"id": media_id, "type": media_type}
        try:
            async with self.session.post(ANILIST_API, json={"query": query, "variables": variables}, timeout=30) as resp:
                text = await resp.text()
                try:
                    js = await resp.json()
                except Exception:
                    js = None
                if resp.status != 200:
                    logger.error("AniList media API error %s: %s", resp.status, text)
                    return None
                if not js or "data" not in js or js["data"].get("Media") is None:
                    logger.warning("AniList API returned no Media for id %s. Response: %s", media_id, text)
                    return None
                return js["data"]["Media"]
        except Exception:
            logger.exception("AniList media API fetch failed (exception).")
            return None

    # ---------------------
    # Media embed builders and pages
    # ---------------------
    def _fmt_date(self, d: Dict[str, Any]) -> str:
        if not d:
            return "Unknown"
        y = d.get("year")
        m = d.get("month")
        day = d.get("day")
        if not y:
            return "Unknown"
        if not m:
            return f"{y}"
        if not day:
            return f"{y}-{m:02d}"
        return f"{y}-{m:02d}-{day:02d}"

    def build_media_embed(self, media: dict) -> discord.Embed:
        title_romaji = (media.get("title") or {}).get("romaji")
        title_eng = (media.get("title") or {}).get("english")
        title_native = (media.get("title") or {}).get("native")
        title_line = title_romaji or title_eng or title_native or "Unknown Title"
        if title_eng and title_eng != title_romaji:
            title_line += f" ({title_eng})"
        if title_native and title_native not in (title_romaji, title_eng):
            title_line += f" | {title_native}"

        desc_raw = media.get("description") or ""
        desc = self.clean_text(desc_raw)
        short_desc = (desc[:800] + "...") if len(desc) > 800 else desc

        embed = discord.Embed(title=title_line, url=media.get("siteUrl"), description=short_desc or "*No synopsis available*", color=discord.Color.blurple())

        cover = (media.get("coverImage") or {}).get("large")
        banner = media.get("bannerImage")
        if cover:
            embed.set_thumbnail(url=cover)
        if banner:
            embed.set_image(url=banner)

        meta_lines = []
        if media.get("type"):
            meta_lines.append(f"**Type:** {media.get('type')}")
        if media.get("status"):
            meta_lines.append(f"**Status:** {media.get('status')}")
        if media.get("episodes") is not None:
            meta_lines.append(f"🎬 Episodes: {media.get('episodes')}")
        if media.get("chapters") is not None:
            meta_lines.append(f"📖 Chapters: {media.get('chapters')}")
        if media.get("volumes") is not None:
            meta_lines.append(f"📚 Volumes: {media.get('volumes')}")
        if media.get("startDate"):
            meta_lines.append(f"Start: {self._fmt_date(media.get('startDate'))}")
        if media.get("endDate"):
            meta_lines.append(f"End: {self._fmt_date(media.get('endDate'))}")

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

        # Main characters preview (names link to AniList)
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

    def render_media_pages(self, media: dict, page: int, total_pages: int) -> List[discord.Embed]:
        embeds: List[discord.Embed] = []
        if not media:
            return [discord.Embed(description="Media not found.", color=discord.Color.red())]
        if page == 1:
            embeds.append(self.build_media_embed(media))
        else:
            raw = self.clean_text(media.get("description") or "")
            if not raw:
                embeds.append(discord.Embed(description="No description available.", color=discord.Color.greyple()))
                return embeds
            chunk_size = 1000
            chunks = [raw[i:i + chunk_size] for i in range(0, len(raw), chunk_size)]
            for idx, c in enumerate(chunks, start=1):
                em = discord.Embed(title=f"{(media.get('title') or {}).get('romaji', 'Description')} — Part {idx}", description=c, url=media.get("siteUrl"), color=discord.Color.green())
                embeds.append(em)
        return embeds

    # build relations / characters / staff / stats / recs / tags 
    def build_relations_embed(self, media: dict) -> List[discord.Embed]:
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
                url = node.get("siteUrl")
                value = f"[{node_title}]({url})" if url else node_title
                field_name = rel_type or node.get("type") or "Related"
                em.add_field(name=field_name, value=value, inline=False)
            first_cover = (chunk[0].get("node") or {}).get("coverImage", {}).get("large")
            if first_cover:
                em.set_thumbnail(url=first_cover)
            embeds.append(em)
        return embeds

    def build_characters_embed(self, media: dict, support: bool = False) -> List[discord.Embed]:
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
            first_img = (chunk[0].get("node") or {}).get("image", {}).get("large")
            if first_img:
                em.set_thumbnail(url=first_img)
            embeds.append(em)
        return embeds

    def build_staff_embed(self, media: dict) -> List[discord.Embed]:
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

    def build_stats_embed(self, media: dict) -> discord.Embed:
        stats = media.get("stats") or {}
        em = discord.Embed(title="Stats Distribution", color=discord.Color.green())
        status_dist = stats.get("statusDistribution") or []
        if status_dist:
            lines = []
            for s in status_dist:
                st = s.get("status") or "Unknown"
                amt = s.get("amount") or 0
                lines.append(f"**{st.title()}** — {amt} users")
            em.add_field(name="Status Distribution", value="\n".join(lines), inline=False)
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

    def build_recommendations_embed(self, media: dict, max_items: int = 5) -> discord.Embed:
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

    def build_tags_embed(self, media: dict) -> discord.Embed:
        tags = media.get("tags") or []
        if not tags:
            return discord.Embed(description="No tags found.", color=discord.Color.greyple())
        em = discord.Embed(title="Tags", color=discord.Color.dark_purple())
        lines = []
        for t in tags:
            name = t.get("name") or "Unknown"
            rank = t.get("rank")
            is_spoiler = t.get("isMediaSpoiler")
            disp = f"||{name}||"
            if rank is not None:
                disp += f" — #{rank}"
            lines.append(disp)
        em.description = "  \n".join(lines)
        return em

    # ---------------------
    # Media paginator (persistent) with dropdown/select
    # ---------------------
    

    class MediaPaginator(ui.View):
        def __init__(self, cog: "AniListCog", message_id: int, channel_id: int, media_id: int, media_type: str, total_pages: int, current_page: int = 1):
            super().__init__(timeout=None)
            self.cog = cog
            self.message_id = str(message_id)
            self.channel_id = int(channel_id)
            self.media_id = int(media_id)
            self.media_type = media_type
            self.total_pages = max(1, int(total_pages))
            self.current_page = max(1, int(current_page))

            # Buttons
            self.main_button = ui.Button(
                label="📖 Description",
                style=discord.ButtonStyle.primary,
                custom_id=f"media_next:{self.message_id}"
            )
            self.back_button = ui.Button(
                label="⬅ Back to Main Page",
                style=discord.ButtonStyle.secondary,
                custom_id=f"media_prev:{self.message_id}"
            )
            self.rec_button = ui.Button(
                label="🎯 Recommendations",
                style=discord.ButtonStyle.success,
                custom_id=f"media_rec:{self.message_id}"
            )
            # always available review button
            self.review_button = ui.Button(
                label="📝 Review",
                style=discord.ButtonStyle.secondary,
                custom_id=f"media_review:{self.message_id}"
            )

            self.main_button.callback = self.show_description
            self.back_button.callback = self.show_main
            self.rec_button.callback = self.show_recommendations
            self.review_button.callback = self.show_review_for_media
            self.add_item(self.main_button)
            self.add_item(self.rec_button)
            self.add_item(self.review_button)

            # Dropdown options
            options = [
                discord.SelectOption(label="🔗 Relations", value="relations", description="Show related media"),
                discord.SelectOption(label="🎭 Characters (Main)", value="characters_main", description="Main characters"),
                discord.SelectOption(label="🌟 Support Cast", value="characters_support", description="Support characters"),
                discord.SelectOption(label="🛡️ Staff", value="staff", description="All staff"),
                discord.SelectOption(label="📊 Stats Distribution", value="stats", description="Status & score distribution"),
                discord.SelectOption(label="🎯 Recommendations", value="recommendations", description="Top recommendations"),
                discord.SelectOption(label="🗂️ Tags", value="tags", description="All tags"),
                discord.SelectOption(label="👥 User Progress", value="user_progress", description="See registered users' progress"),
            ]
            select = ui.Select(
                placeholder="Choose details...",
                min_values=1,
                max_values=1,
                options=options,
                custom_id=f"media_select:{self.message_id}"
            )
            select.callback = self.select_callback
            self.add_item(select)

        async def show_description(self, interaction: discord.Interaction):
            try:
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    await interaction.response.send_message("❌ Could not fetch description.", ephemeral=True)
                    return
                embeds = self.cog.render_media_pages(media, page=2, total_pages=2)
                # Ensure review button and media main exist on all pages
                self.clear_items()
                self.add_item(self.back_button)
                self.add_item(self.rec_button)
                self.add_item(self.review_button)
                for item in self.children:
                    if isinstance(item, ui.Select):
                        self.add_item(item)
                await interaction.response.edit_message(embeds=embeds, view=self)
            except Exception:
                logger.exception("Failed to show description")
                try:
                    await interaction.response.send_message("⚠️ Could not load description.", ephemeral=True)
                except Exception:
                    pass

        async def show_main(self, interaction: discord.Interaction):
            try:
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    await interaction.response.send_message("❌ Could not fetch main page.", ephemeral=True)
                    return
                embeds = self.cog.render_media_pages(media, page=1, total_pages=2)
                self.clear_items()
                self.add_item(self.main_button)
                self.add_item(self.rec_button)
                self.add_item(self.review_button)
                for item in self.children:
                    if isinstance(item, ui.Select):
                        self.add_item(item)
                await interaction.response.edit_message(embeds=embeds, view=self)
            except Exception:
                logger.exception("Failed to show main page")
                try:
                    await interaction.response.send_message("⚠️ Could not load main page.", ephemeral=True)
                except Exception:
                    pass

        async def show_recommendations(self, interaction: discord.Interaction):
            try:
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    await interaction.response.send_message("❌ Could not fetch recommendations.", ephemeral=True)
                    return
                embed = self.cog.build_recommendations_embed(media)
                self.clear_items()
                self.add_item(self.back_button)
                self.add_item(self.main_button)
                self.add_item(self.review_button)
                self.add_item(self.rec_button)  # leave rec button too
                for item in self.children:
                    if isinstance(item, ui.Select):
                        self.add_item(item)
                await interaction.response.edit_message(embeds=[embed], view=self)
            except Exception:
                logger.exception("show_recommendations failed")
                try:
                    await interaction.response.send_message("⚠️ Failed to fetch recommendations.", ephemeral=True)
                except Exception:
                    pass

        async def show_review_for_media(self, interaction: discord.Interaction):
            """
            Try to fetch a top review for the media and show it using the review embedding/paginator.
            """
            # GraphQL: fetch some review ids for the media
            query = """
            query($mediaId: Int, $type: MediaType) {
              Media(id: $mediaId, type: $type) {
                reviews(perPage: 3, sort: RATING_DESC) {
                  nodes {
                    id
                  }
                }
              }
            }
            """
            variables = {"mediaId": self.media_id, "type": self.media_type}
            try:
                async with self.cog.session.post(ANILIST_API, json={"query": query, "variables": variables}, timeout=15) as resp:
                    js = await resp.json()
                    if resp.status == 200 and js.get("data") and js["data"].get("Media"):
                        rev_nodes = js["data"]["Media"].get("reviews", {}).get("nodes", [])
                    else:
                        rev_nodes = []
            except Exception:
                rev_nodes = []

            if not rev_nodes:
                await interaction.response.send_message("No reviews found for this media.", ephemeral=True)
                return

            rid = rev_nodes[0].get("id")
            if not rid:
                await interaction.response.send_message("No valid review found.", ephemeral=True)
                return

            review_data = await self.cog.fetch_review_api(rid)
            if not review_data:
                review_data = await self.cog.fetch_review_parse_fallback(rid)
                if not review_data:
                    await interaction.response.send_message("❌ Could not fetch review.", ephemeral=True)
                    return

            embeds = self.cog._make_review_embeds_from_data(review_data)
            # edit the current message to show the review's first page and attach paginator view for follow-ups
            self.clear_items()
            self.add_item(self.back_button)
            self.add_item(self.main_button)
            self.add_item(self.rec_button)
            self.add_item(self.review_button)
            await interaction.response.edit_message(embeds=[embeds[0]], view=self)
            if len(embeds) > 1:
                view = self.cog.ReviewPaginator(embeds=embeds, cog=self.cog)
                try:
                    # Keep the review paginator alive for message id
                    self.cog.bot.add_view(view, message_id=interaction.message.id)
                except Exception:
                    logger.exception("Failed to add ReviewPaginator view to bot (non-fatal).")

        async def select_callback(self, interaction: discord.Interaction):
            try:
                value = interaction.data.get("values", [None])[0]
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ Could not fetch media details.", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ Could not fetch media details.", ephemeral=True)
                    return

                if value == "user_progress":
                    # Show enhanced progress filtering options
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    
                    # Create enhanced user progress view with filtering
                    progress_view = self.UserProgressView(self.cog, media, self.media_type, self.message_id)
                    embed = await self.cog.build_user_progress_embed(media, self.media_type, interaction.guild.id, ProgressFilter.ACTIVE_ONLY)
                    
                    if embed:
                        await interaction.followup.edit_message(interaction.message.id, embeds=[embed], view=progress_view)
                    else:
                        await interaction.followup.send("❌ Could not fetch user progress data.", ephemeral=True)
                    return
                    
                # Handle other dropdown options
                embeds = None
                embed = None
                
                if value == "relations":
                    embeds = self.cog.build_relations_embed(media)
                elif value == "characters_main":
                    embeds = self.cog.build_characters_embed(media, support=False)
                elif value == "characters_support":
                    embeds = self.cog.build_characters_embed(media, support=True)
                elif value == "staff":
                    embeds = self.cog.build_staff_embed(media)
                elif value == "stats":
                    embed = self.cog.build_stats_embed(media)
                elif value == "recommendations":
                    embed = self.cog.build_recommendations_embed(media)
                elif value == "tags":
                    embed = self.cog.build_tags_embed(media)
                else:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("Unknown option.", ephemeral=True)
                    else:
                        await interaction.followup.send("Unknown option.", ephemeral=True)
                    return

                # Send the response
                if embeds:
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(embeds=embeds, view=self)
                    else:
                        await interaction.followup.edit_message(interaction.message.id, embeds=embeds, view=self)
                elif embed:
                    if not interaction.response.is_done():
                        await interaction.response.edit_message(embeds=[embed], view=self)
                    else:
                        await interaction.followup.edit_message(interaction.message.id, embeds=[embed], view=self)
                        
            except discord.NotFound:
                # Interaction expired or message was deleted
                logger.warning("Interaction expired or message deleted during select callback")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ This interaction has expired. Please try the command again.", ephemeral=True)
                except:
                    pass
            except Exception as e:
                logger.exception("Media select callback failed")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("⚠️ Failed to show details. Please try again.", ephemeral=True)
                    else:
                        await interaction.followup.send("⚠️ Failed to show details. Please try again.", ephemeral=True)
                except Exception:
                    logger.exception("Failed to send error message")

        class UserProgressView(ui.View):
            """Enhanced user progress view with filtering options"""
            def __init__(self, cog: "AniListCog", media: dict, media_type: str, original_message_id: int):
                super().__init__(timeout=300)
                self.cog = cog
                self.media = media
                self.media_type = media_type
                self.original_message_id = original_message_id
                self.current_filter = ProgressFilter.ACTIVE_ONLY
                
                # Add filter dropdown
                filter_options = []
                for filter_type, info in PROGRESS_FILTER_OPTIONS.items():
                    filter_options.append(discord.SelectOption(
                        label=info["label"],
                        description=info["description"],
                        value=filter_type.value,
                        emoji=info["emoji"]
                    ))
                
                self.filter_select = ui.Select(
                    placeholder="Choose filter...",
                    options=filter_options,
                    custom_id=f"progress_filter:{original_message_id}"
                )
                self.filter_select.callback = self.filter_callback
                self.add_item(self.filter_select)
                
                # Add back button
                self.back_button = ui.Button(
                    label="⬅ Back to Media", 
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"back_to_media:{original_message_id}"
                )
                self.back_button.callback = self.back_to_media
                self.add_item(self.back_button)
            
            async def filter_callback(self, interaction: discord.Interaction):
                """Handle filter selection"""
                try:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    
                    selected_filter = interaction.data.get("values", [None])[0]
                    if selected_filter:
                        self.current_filter = ProgressFilter(selected_filter)
                        
                        # Generate new embed with selected filter
                        embed = await self.cog.build_user_progress_embed(
                            self.media, self.media_type, interaction.guild.id, self.current_filter
                        )
                        
                        if embed:
                            await interaction.followup.edit_message(interaction.message.id, embeds=[embed], view=self)
                        else:
                            await interaction.followup.send("❌ Could not apply filter.", ephemeral=True)
                    
                except Exception as e:
                    logger.exception(f"Filter callback failed: {e}")
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.send_message("⚠️ Failed to apply filter.", ephemeral=True)
                        else:
                            await interaction.followup.send("⚠️ Failed to apply filter.", ephemeral=True)
                    except:
                        pass
            
            async def back_to_media(self, interaction: discord.Interaction):
                """Return to main media view"""
                try:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                    
                    # Create new MediaPaginator view
                    media_view = self.cog.MediaPaginator(
                        self.cog, self.original_message_id, interaction.channel.id, 
                        self.media["id"], self.media_type, 2, 1
                    )
                    
                    # Show main media page
                    embeds = self.cog.render_media_pages(self.media, page=1, total_pages=2)
                    await interaction.followup.edit_message(interaction.message.id, embeds=embeds, view=media_view)
                    
                except Exception as e:
                    logger.exception(f"Back to media failed: {e}")
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.send_message("⚠️ Failed to return to media view.", ephemeral=True)
                        else:
                            await interaction.followup.send("⚠️ Failed to return to media view.", ephemeral=True)
                    except:
                        pass



    # ---------------------
    # Listener (integrates activity + anime + manga handling)
    # ---------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots
        if message.author.bot:
            return

        # Activity link handling
        m = ACTIVITY_URL_RE.search(message.content)
        if m:
            activity_id = int(m.group(1))
            activity = await self.fetch_activity(activity_id)
            if not activity:
                await message.channel.send("❌ Failed to fetch activity.")
                return
            total_replies = len(activity.get("replies") or [])
            total_pages = 1 + math.ceil(max(0, total_replies) / REPLIES_PER_PAGE)
            embeds = await self.render_page(activity, page=1)
            try:
                sent = await message.channel.send(embeds=embeds)
            except Exception:
                logger.exception("Failed to send activity message")
                return
            try:
                view = await self._add_paginator_persistence(sent.id, sent.channel.id, activity_id, total_pages, current_page=1)
                try:
                    await sent.edit(view=view)
                except Exception:
                    logger.exception("Failed to attach paginator view to activity message (message.edit failed).")
            except Exception:
                logger.exception("Failed to persist activity paginator.")
            return

        # Anime link
        m = ANIME_URL_RE.search(message.content)
        if m:
            media_id = int(m.group(1))
            media = await self.fetch_media(media_id, "ANIME")
            if not media:
                await message.channel.send("❌ Failed to fetch anime info.")
                return
            total_pages = 2
            embeds = self.render_media_pages(media, page=1, total_pages=total_pages)
            try:
                sent = await message.channel.send(embeds=embeds)
            except Exception:
                logger.exception("Failed to send anime message")
                return
            try:
                view = await self._add_media_persistence(sent.id, sent.channel.id, media_id, "ANIME", total_pages, current_page=1)
                try:
                    await sent.edit(view=view)
                except Exception:
                    logger.exception("Failed to attach media view to anime message (message.edit failed).")
            except Exception:
                logger.exception("Failed to persist media paginator for anime.")
            return

        # Manga link
        m = MANGA_URL_RE.search(message.content)
        if m:
            media_id = int(m.group(1))
            media = await self.fetch_media(media_id, "MANGA")
            if not media:
                await message.channel.send("❌ Failed to fetch manga info.")
                return
            total_pages = 2
            embeds = self.render_media_pages(media, page=1, total_pages=total_pages)
            try:
                sent = await message.channel.send(embeds=embeds)
            except Exception:
                logger.exception("Failed to send manga message")
                return
            try:
                view = await self._add_media_persistence(sent.id, sent.channel.id, media_id, "MANGA", total_pages, current_page=1)
                try:
                    await sent.edit(view=view)
                except Exception:
                    logger.exception("Failed to attach media view to manga message (message.edit failed).")
            except Exception:
                logger.exception("Failed to persist media paginator for manga.")
            return

        # Reviews: separate handling for review links
        m = REVIEW_URL_RE.search(message.content)
        if m:
            review_id = int(m.group(1))
            # Try GraphQL API first
            review_data = await self.fetch_review_api(review_id)
            if not review_data:
                review_data = await self.fetch_review_parse_fallback(review_id)
                if not review_data:
                    await message.channel.send("❌ Failed to fetch review.")
                    return

            # Build embeds
            try:
                embeds = self._make_review_embeds_from_data(review_data)
                # send first embed and attach paginator view if multiple
                sent = await message.channel.send(embeds=[embeds[0]])
                if len(embeds) > 1:
                    view = self.ReviewPaginator(embeds=embeds, cog=self)
                    try:
                        self.bot.add_view(view, message_id=sent.id)
                    except Exception:
                        logger.exception("Failed to add ReviewPaginator view to bot (non-fatal).")
                    try:
                        await sent.edit(view=view)
                    except Exception:
                        logger.exception("Failed to attach review paginator view to message (message.edit failed).")
            except Exception:
                logger.exception("Failed to build/send review embed")
                try:
                    await message.channel.send("⚠️ Failed to render review.")
                except Exception:
                    pass
            return

    # ---------------------
    # NEW: REVIEW fetching + parsing + embed + pagination
    # ---------------------
    async def fetch_review_api(self, review_id: int) -> Optional[dict]:
        """
        Attempt to fetch review via AniList GraphQL API.
        Returns a dict with fields similar to the HTML fallback (id, siteUrl, user, body, rating, ratingAmount, images[])
        NOTE: removed invalid 'likes' field from query (AniList GraphQL doesn't expose it on Review)
        """
        query = """
        query($id: Int) {
          Review(id: $id) {
            id
            siteUrl
            summary
            body(asHtml: false)
            rating
            ratingAmount
            score
            user { id name siteUrl avatar { large } }
          }
        }
        """
        variables = {"id": review_id}
        try:
            async with self.session.post(ANILIST_API, json={"query": query, "variables": variables}, timeout=20) as resp:
                text = await resp.text()
                try:
                    js = await resp.json()
                except Exception:
                    js = None
                if resp.status != 200:
                    logger.warning("AniList review API returned non-200: %s - %s", resp.status, text)
                    return None
                if not js or "data" not in js or js["data"].get("Review") is None:
                    logger.info("AniList review API returned no Review for id %s. Response: %s", review_id, text)
                    return None
                r = js["data"]["Review"]
                # Normalize fields
                body = r.get("body") or r.get("summary") or ""
                # rating returned by API might be on a 100-scale or 10-scale; keep raw and normalize later
                rating = r.get("rating") or r.get("score") or None
                rating_amount = r.get("ratingAmount") or None  # best-effort: may represent number of people that voted on the review or not
                user = r.get("user") or {}
                site_url = r.get("siteUrl") or f"https://anilist.co/review/{review_id}"
                return {
                    "id": r.get("id"),
                    "siteUrl": site_url,
                    "user": user,
                    "body": body,
                    "rating": rating,
                    "ratingAmount": rating_amount,
                    "images": []  # API does not expose images in Review payload; HTML fallback may provide them
                }
        except Exception:
            logger.exception("fetch_review_api failed")
            return None

    async def fetch_review_parse_fallback(self, review_id: int) -> Optional[dict]:
        """
        Robust multilayered fallback: fetch the review HTML and parse out content, images, rating and votes.
        This function is intentionally defensive and attempts multiple heuristics.
        """
        url = f"https://anilist.co/review/{review_id}"
        logger.info("Review parsing fallback started for %s", url)
        try:
            async with self.session.get(url, timeout=HTML_TIMEOUT, headers={"User-Agent": "AniListBot/1.0"}) as resp:
                html = await resp.text()
        except Exception:
            logger.exception("Failed to fetch review page HTML")
            return None

        # Attempt to find JSON blobs first (data-react-props / ld+json)
        body_text = None
        images: List[str] = []
        rating = None
        likes = None
        rating_amount = None
        user = {"name": None, "siteUrl": None, "avatar": {"large": None}}

        try:
            # Look for <script type="application/ld+json"> or data-react-props containing review text
            m_ld = re.search(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I)
            if m_ld:
                try:
                    import json
                    ld = json.loads(m_ld.group(1))
                    # ld might contain review body
                    if isinstance(ld, dict):
                        body_text = ld.get("reviewBody") or ld.get("description") or body_text
                        if not images and ld.get("image"):
                            if isinstance(ld.get("image"), list):
                                images.extend(ld.get("image"))
                            else:
                                images.append(ld.get("image"))
                except Exception:
                    pass
        except Exception:
            pass

        # fallback: find review content container
        if not body_text:
            # AniList displays review text in <div class="markdown"...> often
            m_body = re.search(r'<div[^>]+class=["\'][^"\']*markdown[^"\']*["\'][^>]*>(.*?)</div>', html, re.S | re.I)
            if m_body:
                raw_html = m_body.group(1)
                # find img srcs inside
                for img in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html, re.I):
                    src = img.group(1)
                    if src and src not in images:
                        images.append(src)
                # remove tags
                body_text = re.sub(r'<[^>]+>', '', raw_html).strip()
        # Another heuristic
        if not body_text:
            m_main = re.search(r'<div[^>]+id=["\']review-body-[^"\']+["\'][^>]*>(.*?)</div>', html, re.S | re.I)
            if m_main:
                b = m_main.group(1)
                for img in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', b, re.I):
                    src = img.group(1)
                    if src and src not in images:
                        images.append(src)
                body_text = re.sub(r'<[^>]+>', '', b).strip()

        # Parse rating (various possible formats)
        try:
            # look for explicit X/100 patterns
            m_rate = re.search(r'([0-9]{1,3})\s*/\s*100', html, re.I)
            if m_rate:
                rating = int(m_rate.group(1))
            else:
                # pattern like "gave it 80/100" or "User gave it 8/10"
                m_rate2 = re.search(r'gave it\s*([0-9]{1,3})\s*/\s*([0-9]{1,3})', html, re.I)
                if m_rate2:
                    val = int(m_rate2.group(1))
                    denom = int(m_rate2.group(2))
                    # normalize to numerator as-is, keep denominator as detection later
                    # we'll store as tuple if denom is found
                    rating = (val, denom)
                else:
                    # fallback: "Rating: 80" nearby
                    m_rate3 = re.search(r'Rating[:\s]*</strong>\s*([0-9]{1,3})', html, re.I)
                    if m_rate3:
                        rating = int(m_rate3.group(1))
        except Exception:
            pass

        # Parse likes / helpful votes (e.g., "9 of 14 users found this helpful")
        try:
            m_help = re.search(r'([0-9]{1,4})\s*of\s*([0-9]{1,4})\s*users? found this helpful', html, re.I)
            if m_help:
                likes = int(m_help.group(1))
                rating_amount = int(m_help.group(2))
            else:
                # Another pattern: "18 found this helpful" or "18 people found this helpful"
                m_help2 = re.search(r'([0-9,]{1,7})\s*(?:people)?\s*(?:found this review helpful|found this helpful|found helpful)', html, re.I)
                if m_help2:
                    likes = int(m_help2.group(1).replace(",", ""))
        except Exception:
            pass

        # Parse author info
        try:
            m_user = re.search(r'<a[^>]+href=["\'](https?://anilist\.co/user/[^"\']+)["\'][^>]*>\s*<img[^>]+src=["\']([^"\']+)["\'][^>]*>\s*</a>\s*<a[^>]+href=["\'](https?://anilist\.co/user/[^"\']+)["\'][^>]*>([^<]+)</a>', html, re.S | re.I)
            if m_user:
                user["siteUrl"] = m_user.group(1)
                user["avatar"]["large"] = m_user.group(2)
                user["name"] = m_user.group(4).strip()
            else:
                # simpler
                m_user2 = re.search(r'<a[^>]+href=["\'](https?://anilist\.co/user/[^"\']+)["\'][^>]*>([^<]+)</a>', html, re.I)
                if m_user2:
                    user["siteUrl"] = m_user2.group(1)
                    user["name"] = m_user2.group(2).strip()
        except Exception:
            pass

        # Final cleanup
        body_text = body_text or ""
        images = [i for i in images if i]
        # If we found a "X of Y users found this helpful", but not likes, set likes to X
        if rating_amount and likes is None:
            likes = rating_amount

        # Attempt to extract direct image links embedded as markdown or http links in body_text
        try:
            for m in re.finditer(r'(https?://[^\s"\']+(?:png|jpe?g|gif|webp))', html, re.I):
                url_img = m.group(1)
                if url_img not in images:
                    images.append(url_img)
        except Exception:
            pass

        # Normalize rating tuple to integer value + denom if provided
        normalized_rating = None
        rating_denom = None
        if isinstance(rating, tuple):
            normalized_rating = rating[0]
            rating_denom = rating[1]
        elif isinstance(rating, int):
            normalized_rating = rating
            # denom unknown; we will decide later: >10 -> assume /100
            rating_denom = None

        return {
            "id": review_id,
            "siteUrl": url,
            "user": user,
            "body": body_text,
            "images": images,
            "rating": normalized_rating,
            "ratingDenom": rating_denom,
            "likes": likes,
            "ratingAmount": rating_amount
        }

    def _make_review_embeds_from_data(self, r: dict) -> List[discord.Embed]:
        """
        Convert review dict returned by fetch_review_api or fallback into one or more embeds.
        Handles media pagination (one image per embed) and converts AniList formatting to Discord-friendly formatting.
        This function:
          - places the Rating / Votes block at the top
          - normalizes user rating (detects /100 vs /10 where possible)
          - paginates images (one image per embed)
          - chunks long body text to avoid embed size overflow
          - converts AniList markup to Discord markup (spoilers, strikethrough on ~...~, link text preserved)
        """
        # raw text
        text_raw = r.get("body") or ""
        # convert AniList markup to Discord
        cleaned_full = self.clean_text(text_raw)

        # Extract explicit media links (image placeholders) and remove them from text
        media_links, cleaned_removed = self.extract_media(text_raw)
        # If fallback provided images, add them
        if not media_links and r.get("images"):
            media_links = r.get("images", [])

        # deduplicate media links while maintaining order
        seen = set()
        media_links_unique = []
        for u in media_links:
            if u not in seen:
                media_links_unique.append(u)
                seen.add(u)
        media_links = media_links_unique

        # author info
        user = r.get("user") or {}
        author_name = user.get("name") or "AniList User"
        author_url = user.get("siteUrl") or r.get("siteUrl") or ""
        avatar = (user.get("avatar") or {}).get("large") if isinstance(user.get("avatar"), dict) else None

        # Rating normalization: prefer 'rating' (numerical), 'ratingDenom' if present, or decide denom heuristically
        rating = r.get("rating")
        rating_denom = r.get("ratingDenom")  # may be None
        # also check 'ratingAmount' / 'likes' fields for votes
        positive_votes = r.get("likes") or None
        total_votes = r.get("ratingAmount") or None

        # If rating is None and API returned something else, try to use available fields
        # Decide displayed rating string
        display_rating = None
        if rating is None:
            display_rating = None
        else:
            # If denom exists as tuple numeric, use it
            if rating_denom:
                # present as X/Y (keep Y)
                display_rating = f"{rating}/{rating_denom}"
            else:
                # Heuristic: large numbers (>10) -> treat as /100; else treat as /10
                try:
                    if isinstance(rating, int) and rating > 10:
                        display_rating = f"{rating}/100"
                    else:
                        # show one decimal for /10 scale if needed
                        if isinstance(rating, float):
                            display_rating = f"{rating:.1f}/10"
                        else:
                            display_rating = f"{rating}/10"
                except Exception:
                    display_rating = f"{rating}"

        # Build the top rating block string
        rating_lines = []
        if display_rating:
            rating_lines.append(f"**User rating:** {display_rating}")
        # Convert available votes info into consistent positive/total if possible
        if positive_votes is not None and total_votes is not None:
            try:
                up = int(positive_votes)
                tot = int(total_votes)
                pct = (up / tot) * 100 if tot > 0 else 0
                rating_lines.append(f"**Total votes:** {tot}")
                rating_lines.append(f"**Positive:** {up}/{tot} ({pct:.0f}% positive)")
            except Exception:
                rating_lines.append(f"**Votes:** {positive_votes}/{total_votes}")
        elif total_votes is not None:
            # only total known
            try:
                tot = int(total_votes)
                rating_lines.append(f"**Total votes:** {tot}")
            except Exception:
                rating_lines.append(f"**Total votes:** {total_votes}")
        elif positive_votes is not None:
            rating_lines.append(f"**Helpful votes:** {positive_votes}")

        # Combine rating header
        rating_header = "\n".join(rating_lines) if rating_lines else None

        # To avoid Embed size overflow, chunk the cleaned text into safe lengths
        # discord embed description limit is 4096 but the full embed character limit is 6000, be conservative.
        SAFE_CHUNK = 1500  # conservative chunk size for body text per page
        # Use cleaned_full as the user-facing text (converted), but if extract_media removed some parts, prefer cleaned_full
        text_for_chunks = cleaned_full or cleaned_removed or ""
        text_chunks = [text_for_chunks[i:i + SAFE_CHUNK] for i in range(0, len(text_for_chunks), SAFE_CHUNK)] if text_for_chunks else []

        embeds: List[discord.Embed] = []
        # If there are no media_links -> create text pages only (one or multiple)
        if not media_links:
            if not text_chunks:
                # empty review
                em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=rating_header or "*No review text*", color=discord.Color(DEFAULT_EMBED_COLOR))
                if avatar:
                    em.set_author(name=author_name, url=author_url, icon_url=avatar)
                else:
                    em.set_author(name=author_name, url=author_url)
                if rating_header and text_for_chunks:
                    em.add_field(name="Rating / Votes", value=rating_header, inline=False)
                em.set_footer(text="AniList Review")
                embeds.append(em)
                return embeds

            # paginate text chunks
            for idx, chunk in enumerate(text_chunks, start=1):
                desc = ""
                # On first page, put rating header at top
                if idx == 1 and rating_header:
                    desc = f"{rating_header}\n\n{chunk}"
                else:
                    desc = chunk
                # limit description to 2048 to be safe (Discord desc limit)
                if len(desc) > 2048:
                    desc = desc[:2045] + "..."
                em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=desc, color=discord.Color(DEFAULT_EMBED_COLOR))
                if avatar:
                    em.set_author(name=author_name, url=author_url, icon_url=avatar)
                else:
                    em.set_author(name=author_name, url=author_url)
                # On first page, include a compact Rating field too
                if idx == 1 and rating_header:
                    em.add_field(name="Rating / Votes", value=rating_header, inline=False)
                em.set_footer(text=f"AniList Review — Page {idx}/{max(1, len(text_chunks))}")
                embeds.append(em)
            return embeds

        # If there are images: create pages that combine text chunks & images.
        # We'll create pages count = max(len(media_links), len(text_chunks))
        pages = max(len(media_links), len(text_chunks) if text_chunks else 1)

        for p in range(pages):
            # text for this page: first page gets chunk 0, page 1 => chunk 0 etc.
            page_text = text_chunks[p] if p < len(text_chunks) else ""
            # rating header on first page
            if p == 0 and rating_header:
                desc = (rating_header + "\n\n" + page_text) if page_text else rating_header
            else:
                desc = page_text if page_text else f"Image {p+1}/{len(media_links)}"
            # ensure desc length safe
            if len(desc) > 2048:
                desc = desc[:2045] + "..."
            em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=desc, color=discord.Color(DEFAULT_EMBED_COLOR))
            if avatar:
                em.set_author(name=author_name, url=author_url, icon_url=avatar)
            else:
                em.set_author(name=author_name, url=author_url)
            # attach image for this page if available
            if p < len(media_links):
                img = media_links[p]
                # check if it's an image extension
                if any(img.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    try:
                        em.set_image(url=img)
                    except Exception:
                        # if image URL invalid, fallback to field link
                        em.add_field(name="Media", value=f"[Link]({img})", inline=False)
                else:
                    em.add_field(name="Media", value=f"[Link]({img})", inline=False)
            # Add rating field only on the first page (already included in description), but we also add a compact field on the first page below description
            if p == 0 and rating_header:
                em.add_field(name="Rating / Votes", value=rating_header, inline=False)
            em.set_footer(text=f"AniList Review — Page {p+1}/{pages}")
            embeds.append(em)

        return embeds

    class ReviewPaginator(ui.View):
        """
        Simple paginator for review images/text pages: Prev | PageNum(disabled) | Next
        Not persisted to DB (non-persistent view). Buttons edit the message with the appropriate embed.
        """
        def __init__(self, embeds: List[discord.Embed], cog: "AniListCog"):
            super().__init__(timeout=None)
            self.embeds = embeds
            self.cog = cog
            self.current = 0
            total = len(embeds)
            # previous / next set to gray (secondary)
            self.prev_btn = ui.Button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
            self.page_btn = ui.Button(label=f"{self.current+1}/{total}", style=discord.ButtonStyle.secondary, disabled=True)
            self.next_btn = ui.Button(label="Next ➡", style=discord.ButtonStyle.secondary)
            self.prev_btn.callback = self.prev_cb
            self.next_btn.callback = self.next_cb
            self.add_item(self.prev_btn)
            self.add_item(self.page_btn)
            self.add_item(self.next_btn)
            self._update_buttons()

        def _update_buttons(self):
            self.prev_btn.disabled = (self.current <= 0)
            self.next_btn.disabled = (self.current >= len(self.embeds)-1)
            self.page_btn.label = f"{self.current+1}/{len(self.embeds)}"

        async def prev_cb(self, interaction: discord.Interaction):
            try:
                if self.current <= 0:
                    await interaction.response.send_message("You are already on the first page.", ephemeral=True)
                    return
                self.current -= 1
                self._update_buttons()
                await interaction.response.edit_message(embeds=[self.embeds[self.current]], view=self)
            except Exception:
                logger.exception("ReviewPaginator prev_cb failed")
                try:
                    await interaction.response.send_message("Failed to change page.", ephemeral=True)
                except:
                    pass

        async def next_cb(self, interaction: discord.Interaction):
            try:
                if self.current >= len(self.embeds)-1:
                    await interaction.response.send_message("You are already on the last page.", ephemeral=True)
                    return
                self.current += 1
                self._update_buttons()
                await interaction.response.edit_message(embeds=[self.embeds[self.current]], view=self)
            except Exception:
                logger.exception("ReviewPaginator next_cb failed")
                try:
                    await interaction.response.send_message("Failed to change page.", ephemeral=True)
                except:
                    pass

    # ---------------------
    # Cog setup
    # ---------------------
async def setup(bot: commands.Bot):
    cog = AniListCog(bot)
    await bot.add_cog(cog)

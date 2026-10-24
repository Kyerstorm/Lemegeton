from helpers.color_palette import PALETTE
# anilist.py

import re
import json
import html as html_lib
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
from helpers.embed_helper import build_error_embed, build_success_embed, build_info_embed, build_warning_embed
from helpers.anilist_helper import post_graphql

logger = logging.getLogger("AniListCog")
logger.setLevel(logging.INFO)

ACTIVITY_URL_RE = re.compile(r"https?://anilist\.co/activity/(\d+)", re.IGNORECASE)
ANIME_URL_RE = re.compile(r"https?://anilist\.co/anime/(\d+)(?:/[^/\s]+)?/?", re.IGNORECASE)
MANGA_URL_RE = re.compile(r"https?://anilist\.co/manga/(\d+)(?:/[^/\s]+)?/?", re.IGNORECASE)

REVIEW_URL_RE = re.compile(r"https?://anilist\.co/review/(\d+)", re.IGNORECASE)
CHARACTER_URL_RE = re.compile(r"https?://anilist\.co/character/(\d+)(?:/[^\s/?#]+)?/?", re.IGNORECASE)
STAFF_URL_RE = re.compile(r"https?://anilist\.co/staff/(\d+)(?:/[^\s/?#]+)?/?", re.IGNORECASE)
STUDIO_URL_RE = re.compile(r"https?://anilist\.co/studio/(\d+)(?:/[^\s/?#]+)?/?", re.IGNORECASE)

REPLIES_PER_PAGE = 5
HTML_TIMEOUT = 15  # seconds for parsing fallback HTTP requests

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
                return build_info_embed(
                    title="👥 Registered Users' Progress",
                    description="No registered users found."
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
                        payload = await post_graphql(session, query, variables, timeout=10)
                        if not payload:
                            logger.debug(f"API returned no data for user {anilist_username}")
                            continue
                    except asyncio.TimeoutError:
                        logger.debug(f"Timeout fetching progress for {anilist_username}")
                        continue
                    except Exception as e:
                        logger.debug(f"Error fetching progress for {anilist_username}: {e}")
                        continue
                    
                    user_data = payload.get("User")
                    media_list = payload.get("MediaList")
                    
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
            return build_error_embed(
                title="👥 Registered Users' Progress",
                description="An error occurred while fetching user progress data."
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
            return build_warning_embed(
                title=f"{filter_info['emoji']} User Progress - {filter_info['label']}",
                description=f"No users found matching filter: {filter_info['description']}"
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
            color=PALETTE.PRIMARY
        )
        
        # Add insights footer
        insights = []
        if filtered_data:
            insights.append(f"📊 Showing {len(filtered_data)}/{total_checked} users")
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
        embed = discord.Embed(color=PALETTE.PRIMARY)
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
            payload = await post_graphql(self.session, query, {"id": activity_id})
            if not payload:
                logger.warning(f"AniList returned no Activity for id {activity_id}")
                return None
            
            activity_data = payload.get("Activity")
            if not activity_data:
                logger.warning(f"AniList returned no Activity for id {activity_id}")
                return None
            
            return activity_data
        except Exception:
            logger.exception("AniList API fetch failed.", exc_info=True)
            return None

    async def render_page(self, activity: Optional[dict], page: int):
        embeds: List[discord.Embed] = []
        if not activity:
            e = build_error_embed(
                title="Activity not found",
                description="This AniList activity is missing, deleted, or could not be retrieved."
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
            embeds.append(build_info_embed(description="No replies on this page."))
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
                    await interaction.response.send_message(embed=build_warning_embed(description="Paginator state missing."), ephemeral=True)
                    return
                current = int(msg_state.get("current_page", self.current_page))
                if current <= 1:
                    await interaction.response.send_message(embed=build_info_embed(description="You are already on the first page."), ephemeral=True)
                    return
                new_page = current - 1
                activity = await self.cog.fetch_activity(self.activity_id)
                if not activity:
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not fetch AniList activity."), ephemeral=True)
                    return
                embeds = await self.cog.render_page(activity, new_page)
                msg_state["current_page"] = new_page
                await self._save_message_state(msg_state)
                self.current_page = new_page
                self._update_buttons_disabled()
                try:
                    await interaction.response.edit_message(embeds=embeds, view=self)
                except discord.HTTPException:
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not update the message (it may have been deleted)."), ephemeral=True)
                    await self.cog._remove_paginator_persistence(int(self.message_id))
            except Exception:
                logger.exception("Paginator prev_page failure")
                try:
                    await interaction.response.send_message(embed=build_warning_embed(description="Failed to change page."), ephemeral=True)
                except Exception:
                    pass

        async def next_page(self, interaction: discord.Interaction):
            try:
                msg_state = await self._load_message_state()
                if not msg_state:
                    await interaction.response.send_message(embed=build_warning_embed(description="Paginator state missing."), ephemeral=True)
                    return
                current = int(msg_state.get("current_page", self.current_page))
                if current >= int(msg_state.get("total_pages", self.total_pages)):
                    await interaction.response.send_message(embed=build_info_embed(description="You are already on the last page."), ephemeral=True)
                    return
                new_page = current + 1
                activity = await self.cog.fetch_activity(self.activity_id)
                if not activity:
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not fetch AniList activity."), ephemeral=True)
                    return
                embeds = await self.cog.render_page(activity, new_page)
                msg_state["current_page"] = new_page
                await self._save_message_state(msg_state)
                self.current_page = new_page
                self._update_buttons_disabled()
                try:
                    await interaction.response.edit_message(embeds=embeds, view=self)
                except discord.HTTPException:
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not update the message (it may have been deleted)."), ephemeral=True)
                    await self.cog._remove_paginator_persistence(int(self.message_id))
            except Exception:
                logger.exception("Paginator next_page failure")
                try:
                    await interaction.response.send_message(embed=build_warning_embed(description="Failed to change page."), ephemeral=True)
                except Exception:
                    pass

    # ---------------------
    # MEDIA: GraphQL fetch + Parsing fallback
    # ---------------------
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
        stats = {}
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

        # Step 5: recover linked entities and hydrated statistics from HTML.
        studios, character_edges, staff_edges = [], [], []
        try:
            for kind, destination in (("studio", studios), ("character", character_edges), ("staff", staff_edges)):
                pattern = r'<a\b[^>]+href=["\']https?://anilist\.co/' + kind + r'/(\d+)(?:/[^"\']*)?["\'][^>]*>(.*?)</a>'
                for match in re.finditer(pattern, html, re.I | re.S):
                    fragment = match.group(2)
                    raw_name = re.sub(r'<[^>]+>', '', fragment)
                    name = html_lib.unescape(raw_name).strip()
                    entity_id = int(match.group(1))
                    if not name or len(name) > 100:
                        continue
                    if kind == "studio":
                        if not any(item.get("id") == entity_id for item in destination):
                            destination.append({"id": entity_id, "name": name, "siteUrl": f"https://anilist.co/studio/{entity_id}"})
                    else:
                        if any((item.get("node") or {}).get("id") == entity_id for item in destination):
                            continue
                        image_match = re.search(r'<img[^>]+(?:src|data-src)=["\']([^"\']+)["\']', fragment, re.I)
                        node = {"id": entity_id, "name": {"full": name}, "siteUrl": f"https://anilist.co/{kind}/{entity_id}"}
                        if image_match:
                            node["image"] = {"large": image_match.group(1)}
                        destination.append({"role": "MAIN" if kind == "character" else "Staff", "node": node})
            for key in ("scoreDistribution", "statusDistribution"):
                match = re.search(r'["\']' + key + r'["\']\s*:\s*', html)
                if match:
                    array_start = html.find("[", match.end())
                    if array_start >= 0:
                        try:
                            value, _ = json.JSONDecoder().raw_decode(html[array_start:])
                            if isinstance(value, list):
                                stats[key] = value
                        except (ValueError, TypeError):
                            pass
        except Exception:
            logger.debug("Best-effort HTML entity/stat parsing failed", exc_info=True)

        # The dedicated /stats route may contain distributions omitted from the main page.
        if not stats.get("scoreDistribution") and not stats.get("statusDistribution"):
            try:
                async with self.session.get(f"{url.rstrip('/')}/stats", timeout=HTML_TIMEOUT,
                                            headers={"User-Agent": "Mozilla/5.0 (compatible; AniListBot/1.0)"}) as stats_resp:
                    if stats_resp.status == 200:
                        stats_html = await stats_resp.text()
                        for key in ("scoreDistribution", "statusDistribution"):
                            match = re.search(r'["\']' + key + r'["\']\s*:\s*', stats_html)
                            if not match:
                                continue
                            array_start = stats_html.find("[", match.end())
                            if array_start >= 0:
                                try:
                                    value, _ = json.JSONDecoder().raw_decode(stats_html[array_start:])
                                    if isinstance(value, list):
                                        stats[key] = value
                                except (ValueError, TypeError):
                                    pass
            except (aiohttp.ClientError, asyncio.TimeoutError):
                logger.debug("Could not fetch AniList stats HTML for %s", url)

        progress = 95
        logger.info("Parsing mode: %d%% — parsed %d studios, %d characters, %d staff", progress, len(studios), len(character_edges), len(staff_edges))

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
            "characters": {"edges": character_edges},
            "staff": {"edges": staff_edges},
            "stats": stats,
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
            logger.error("Parsing fallback failed for media %s %s", media_type, media_id, exc_info=True)
        return parsed

    async def fetch_media_api(self, media_id: int, media_type: str) -> Optional[dict]:
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
            studios { nodes { id name siteUrl isMain } }
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
            payload = await post_graphql(self.session, query, variables, timeout=30)
            if not payload:
                logger.warning(f"AniList API returned no Media for id {media_id}")
                return None
            
            media_data = payload.get("Media")
            if not media_data:
                logger.warning(f"AniList API returned no Media for id {media_id}")
                return None
            
            return media_data
        except Exception:
            logger.exception("AniList media API fetch failed.", exc_info=True)
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

        embed = discord.Embed(title=title_line, url=media.get("siteUrl"), description=short_desc or "*No synopsis available*", color=PALETTE.PRIMARY)

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
            return [build_error_embed(description="Media not found.")]
        if page == 1:
            embeds.append(self.build_media_embed(media))
        else:
            raw = self.clean_text(media.get("description") or "")
            if not raw:
                embeds.append(build_info_embed(description="No description available."))
                return embeds
            chunk_size = 1000
            chunks = [raw[i:i + chunk_size] for i in range(0, len(raw), chunk_size)]
            for idx, c in enumerate(chunks, start=1):
                em = discord.Embed(title=f"{(media.get('title') or {}).get('romaji', 'Description')} — Part {idx}", description=c, url=media.get("siteUrl"), color=PALETTE.SUCCESS)
                embeds.append(em)
        return embeds

    # build relations / characters / staff / stats / recs / tags 
    def build_relations_embed(self, media: dict) -> List[discord.Embed]:
        relations = (media.get("relations") or {}).get("edges") or []
        if not relations:
            return [build_info_embed(description="No relations found.")]
        embeds = []
        chunk_size = 6
        for i in range(0, len(relations), chunk_size):
            chunk = relations[i:i + chunk_size]
            em = discord.Embed(title="Relations", color=PALETTE.PRIMARY)
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
        """Build linked character credits with role labels and safe pagination."""
        char_edges = (media.get("characters") or {}).get("edges") or []
        if not char_edges:
            return [build_info_embed(title="🎭 Characters", description="AniList returned no character credits for this title.")]

        selected = [
            edge for edge in char_edges
            if ((edge.get("role") or "").upper() != "MAIN") == support
        ]
        title = "🌟 Support Cast" if support else "🎭 Main Characters"
        if not selected:
            return [build_info_embed(title=title, description="No characters in this category were returned. Try the other cast view.")]

        embeds = []
        chunk_size = 6
        total_pages = math.ceil(len(selected) / chunk_size)
        for page_index in range(total_pages):
            chunk = selected[page_index * chunk_size:(page_index + 1) * chunk_size]
            em = discord.Embed(title=title, color=PALETTE.PRIMARY)
            lines = []
            for edge in chunk:
                node = edge.get("node") or {}
                name_data = node.get("name") or {}
                name = name_data.get("full") or name_data.get("native") or "Unknown character"
                character_id = node.get("id")
                url = node.get("siteUrl") or (f"https://anilist.co/character/{character_id}" if character_id else None)
                role = " ".join(str(edge.get("role") or "Supporting").split()).title()
                label = f"[**{name[:180]}**]({url})" if url else f"**{name[:180]}**"
                lines.append(f"{label}\n`{role}`")
            em.description = "\n\n".join(lines)[:4000]
            first_node = (chunk[0].get("node") or {}) if chunk else {}
            first_img = (first_node.get("image") or {}).get("large")
            if first_img:
                em.set_thumbnail(url=first_img)
            em.set_footer(text=f"AniList • Character credits • Page {page_index + 1}/{total_pages}")
            embeds.append(em)
        return embeds

    def build_staff_embed(self, media: dict) -> List[discord.Embed]:
        """Render staff credits with each person's credited role and profile link."""
        staff_edges = (media.get("staff") or {}).get("edges") or []
        if not staff_edges:
            return [build_info_embed(title="🛡️ Staff", description="AniList returned no staff credits for this title.")]

        embeds = []
        chunk_size = 8
        total_pages = math.ceil(len(staff_edges) / chunk_size)
        for page_index in range(total_pages):
            chunk = staff_edges[page_index * chunk_size:(page_index + 1) * chunk_size]
            em = discord.Embed(
                title="🛡️ Production Staff",
                description="People credited on this title, as listed by AniList.",
                color=PALETTE.PRIMARY,
            )
            for edge in chunk:
                role = " ".join(str(edge.get("role") or "Staff").split()) or "Staff"
                node = edge.get("node") or {}
                name_data = node.get("name") or {}
                name = name_data.get("full") or name_data.get("native") or "Unknown staff member"
                staff_id = node.get("id")
                url = node.get("siteUrl") or (f"https://anilist.co/staff/{staff_id}" if staff_id else None)
                value = f"🎬 **{role[:900]}**"
                if url:
                    value += f"\n[View profile]({url})"
                em.add_field(name=name[:256], value=value[:1024], inline=True)
            first_node = (chunk[0].get("node") or {}) if chunk else {}
            first_img = (first_node.get("image") or {}).get("large")
            if first_img:
                em.set_thumbnail(url=first_img)
            em.set_footer(text=f"AniList • Staff credits • Page {page_index + 1}/{total_pages}")
            embeds.append(em)
        return embeds

    def build_studios_embed(self, media: dict) -> discord.Embed:
        """Show all returned studios and distinguish the main studio from other producers."""
        studios = (media.get("studios") or {}).get("nodes") or []
        em = discord.Embed(
            title="🏢 Studios & Production",
            url=media.get("siteUrl"),
            description="Production companies associated with this title.",
            color=PALETTE.PRIMARY,
        )
        if not studios:
            em.description = "AniList returned no studio information for this title."
            em.set_footer(text="AniList • Studio credits")
            return em

        # Deduplicate by AniList ID, falling back to the normalized name.
        unique_studios = []
        seen = set()
        for studio in studios:
            if not isinstance(studio, dict):
                continue
            name = (studio.get("name") or "").strip()
            studio_id = studio.get("id")
            key = ("id", studio_id) if studio_id is not None else ("name", name.casefold())
            if not name or key in seen:
                continue
            seen.add(key)
            unique_studios.append(studio)

        main_studios = [studio for studio in unique_studios if studio.get("isMain") is True]
        other_studios = [studio for studio in unique_studios if studio.get("isMain") is not True]
        ordered = main_studios + other_studios
        for studio in ordered[:25]:
            name = studio.get("name") or "Unknown studio"
            studio_id = studio.get("id")
            url = studio.get("siteUrl") or (f"https://anilist.co/studio/{studio_id}" if studio_id else None)
            role = "⭐ Main studio" if studio.get("isMain") is True else "🏭 Production"
            value = f"{role}\n[View on AniList]({url})" if url else role
            em.add_field(name=name[:256], value=value, inline=True)
        if len(ordered) > 25:
            em.add_field(name="➕ More studios", value=f"{len(ordered) - 25} additional studios omitted to fit Discord's embed limits.", inline=False)
        em.set_footer(text=f"AniList • {len(ordered)} studio{'s' if len(ordered) != 1 else ''}")
        return em

    def build_stats_embed(self, media: dict) -> discord.Embed:
        stats = media.get("stats") or {}
        media_title = (media.get("title") or {}).get("romaji") or (media.get("title") or {}).get("english") or "Media"
        media_url = media.get("siteUrl")
        em = discord.Embed(title=f"{media_title} — Statistics", url=media_url, color=discord.Color.from_rgb(72, 111, 190))
        status_dist = stats.get("statusDistribution") or []
        if status_dist:
            max_amount = max((int(item.get("amount") or 0) for item in status_dist), default=1) or 1
            lines = []
            for item in sorted(status_dist, key=lambda x: int(x.get("amount") or 0), reverse=True):
                status = str(item.get("status") or "Unknown").replace("_", " ").title()
                amount = int(item.get("amount") or 0)
                bar = "▰" * max(1, round(12 * amount / max_amount)) if amount else "·"
                lines.append(f"`{status[:12]:<12}` {bar} **{amount:,}**")
            em.add_field(name="Watching / Reading Status", value="\n".join(lines)[:1024], inline=False)
        score_dist = stats.get("scoreDistribution") or []
        if score_dist:
            max_amount = max((int(item.get("amount") or 0) for item in score_dist), default=1) or 1
            lines = []
            for item in sorted(score_dist, key=lambda x: int(x.get("score") or 0)):
                score = item.get("score", "?")
                amount = int(item.get("amount") or 0)
                bar = "▰" * max(1, round(12 * amount / max_amount)) if amount else "·"
                lines.append(f"`{str(score):>2}/100` {bar} **{amount:,}**")
            for idx in range(0, len(lines), 20):
                name = "Score Distribution" if idx == 0 else "Score Distribution (continued)"
                em.add_field(name=name, value="\n".join(lines[idx:idx + 20])[:1024], inline=False)
        if not em.fields:
            stats_url = f"{media_url.rstrip('/')}/stats" if media_url else "https://anilist.co"
            em.description = f"No statistics were exposed by the API or page HTML. [Open AniList statistics]({stats_url})"
        em.set_footer(text="AniList • Statistics | Bars scaled to the largest value in each chart")
        return em

    def build_recommendations_embed(self, media: dict, max_items: int = 5) -> discord.Embed:
        recs = (media.get("recommendations") or {}).get("edges") or []
        em = discord.Embed(title="🎯 Recommendations", description="Top recommendations from AniList", color=PALETTE.WARNING)
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
            return build_info_embed(description="No tags found.")
        em = discord.Embed(title="Tags", color=PALETTE.PRIMARY)
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
                discord.SelectOption(label="🏢 Studios", value="studios", description="Studios and production"),
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
                    await interaction.response.send_message(embed=build_error_embed(description="Could not fetch description."), ephemeral=True)
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
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not load description."), ephemeral=True)
                except Exception:
                    pass

        async def show_main(self, interaction: discord.Interaction):
            try:
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    await interaction.response.send_message(embed=build_error_embed(description="Could not fetch main page."), ephemeral=True)
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
                    await interaction.response.send_message(embed=build_warning_embed(description="Could not load main page."), ephemeral=True)
                except Exception:
                    pass

        async def show_recommendations(self, interaction: discord.Interaction):
            try:
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    await interaction.response.send_message(embed=build_error_embed(description="Could not fetch recommendations."), ephemeral=True)
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
                    await interaction.response.send_message(embed=build_warning_embed(description="Failed to fetch recommendations."), ephemeral=True)
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
                payload = await post_graphql(self.cog.session, query, variables, timeout=15)
                if payload and payload.get("Media"):
                    rev_nodes = payload["Media"].get("reviews", {}).get("nodes", [])
                else:
                    rev_nodes = []
            except Exception:
                rev_nodes = []

            if not rev_nodes:
                await interaction.response.send_message(embed=build_info_embed(description="No reviews found for this media."), ephemeral=True)
                return

            rid = rev_nodes[0].get("id")
            if not rid:
                await interaction.response.send_message(embed=build_info_embed(description="No valid review found."), ephemeral=True)
                return

            review_data = await self.cog.fetch_review_api(rid)
            if not review_data:
                review_data = await self.cog.fetch_review_parse_fallback(rid)
                if not review_data:
                    await interaction.response.send_message(embed=build_error_embed(description="Could not fetch review."), ephemeral=True)
                    return

            embeds = self.cog._make_review_embeds_from_data(review_data)
            # edit the current message to show the review's first page and attach paginator view for follow-ups
            self.clear_items()
            self.add_item(self.back_button)
            self.add_item(self.main_button)
            self.add_item(self.rec_button)
            self.add_item(self.review_button)
            # Attach the actual review paginator to the message. bot.add_view() only
            # registers callbacks; it does not update the components shown to users.
            view = self.cog.ReviewPaginator(embeds=embeds, cog=self.cog)
            await interaction.response.edit_message(embeds=[embeds[0]], view=view)

        async def select_callback(self, interaction: discord.Interaction):
            try:
                value = interaction.data.get("values", [None])[0]
                media = await self.cog.fetch_media(self.media_id, self.media_type)
                if not media:
                    error_embed = build_error_embed(description="Could not fetch media details.")
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=error_embed, ephemeral=True)
                    else:
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                        await interaction.followup.send(embed=build_error_embed(description="Could not fetch user progress data."), ephemeral=True)
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
                elif value == "studios":
                    embed = self.cog.build_studios_embed(media)
                elif value == "stats":
                    embed = self.cog.build_stats_embed(media)
                elif value == "recommendations":
                    embed = self.cog.build_recommendations_embed(media)
                elif value == "tags":
                    embed = self.cog.build_tags_embed(media)
                else:
                    error_embed = build_warning_embed(description="Unknown option.")
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=error_embed, ephemeral=True)
                    else:
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                        await interaction.response.send_message(embed=build_warning_embed(description="This interaction has expired. Please try the command again."), ephemeral=True)
                except:
                    pass
            except Exception as e:
                logger.exception("Media select callback failed")
                try:
                    error_embed = build_warning_embed(description="Failed to show details. Please try again.")
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=error_embed, ephemeral=True)
                    else:
                        await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                            await interaction.followup.send(embed=build_error_embed(description="Could not apply filter."), ephemeral=True)
                    
                except Exception as e:
                    logger.exception(f"Filter callback failed: {e}")
                    try:
                        error_embed = build_warning_embed(description="Failed to apply filter.")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(embed=error_embed, ephemeral=True)
                        else:
                            await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                        error_embed = build_warning_embed(description="Failed to return to media view.")
                        if not interaction.response.is_done():
                            await interaction.response.send_message(embed=error_embed, ephemeral=True)
                        else:
                            await interaction.followup.send(embed=error_embed, ephemeral=True)
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
                await message.channel.send(embed=build_error_embed(description="Failed to fetch activity."))
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
                await message.channel.send(embed=build_error_embed(description="Failed to fetch anime info."))
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
                await message.channel.send(embed=build_error_embed(description="Failed to fetch manga info."))
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

        # Character, staff, and studio profile links
        for entity_kind, pattern in (
            ("character", CHARACTER_URL_RE),
            ("staff", STAFF_URL_RE),
            ("studio", STUDIO_URL_RE),
        ):
            match = pattern.search(message.content)
            if not match:
                continue
            entity_id = int(match.group(1))
            entity = await self.fetch_entity(entity_kind, entity_id)
            if not entity:
                await message.channel.send(embed=build_error_embed(description=f"Failed to fetch AniList {entity_kind} profile."))
                return
            embeds = self.build_entity_embeds(entity_kind, entity)
            try:
                view = self.EntityPaginator(embeds, self) if len(embeds) > 1 else None
                sent = await message.channel.send(embed=embeds[0], view=view)
                if view:
                    view.message_id = sent.id
            except Exception:
                logger.exception("Failed to render AniList %s profile %s", entity_kind, entity_id)
                await message.channel.send(embed=build_warning_embed(description=f"Could not render this AniList {entity_kind} profile."))
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
                    await message.channel.send(embed=build_error_embed(description="Failed to fetch review."))
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
                    await message.channel.send(embed=build_warning_embed(description="Failed to render review."))
                except Exception:
                    pass
            return

    # ---------------------
    # NEW: REVIEW fetching + parsing + embed + pagination
    # ---------------------
    async def fetch_entity(self, entity_kind: str, entity_id: int) -> Optional[dict]:
        """Fetch an AniList character, staff member, or studio; use page HTML if GraphQL fails."""
        queries = {
            "character": """
                query($id: Int) {
                  Character(id: $id) {
                    id siteUrl name { full native alternative }
                    image { large }
                    description(asHtml: false)
                    gender age dateOfBirth { year month day }
                    favourites
                    media(perPage: 10, sort: POPULARITY_DESC) {
                      edges { characterRole node { id type siteUrl title { romaji english } coverImage { large } }
                      }
                    }
                  }
                }
            """,
            "staff": """
                query($id: Int) {
                  Staff(id: $id) {
                    id siteUrl name { full native alternative }
                    language: languageV2
                    image { large }
                    description(asHtml: false)
                    primaryOccupations yearsActive homeTown
                    favourites
                    staffMedia(perPage: 10, sort: POPULARITY_DESC) {
                      edges { staffRole node { id type siteUrl title { romaji english } coverImage { large } } }
                    }
                  }
                }
            """,
            "studio": """
                query($id: Int) {
                  Studio(id: $id) {
                    id siteUrl name isAnimationStudio favourites
                    media(perPage: 10, sort: POPULARITY_DESC) {
                      nodes { id type siteUrl title { romaji english } coverImage { large } }
                    }
                  }
                }
            """,
        }
        query = queries.get(entity_kind)
        if not query:
            return None
        try:
            payload = await post_graphql(self.session, query, {"id": entity_id}, timeout=20)
            entity = payload.get(entity_kind.title()) if payload else None
            if entity:
                entity["_entity_kind"] = entity_kind
                entity["_source"] = "api"
                return entity
        except Exception:
            logger.exception("AniList %s API fetch failed for id %s", entity_kind, entity_id)

        return await self.fetch_entity_html_fallback(entity_kind, entity_id)

    async def fetch_entity_html_fallback(self, entity_kind: str, entity_id: int) -> Optional[dict]:
        """Best-effort HTML fallback using OpenGraph metadata and embedded JSON on AniList pages."""
        url = f"https://anilist.co/{entity_kind}/{entity_id}"
        try:
            async with self.session.get(
                url,
                timeout=HTML_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Lemegeton/1.0)"},
            ) as response:
                if response.status != 200:
                    logger.warning("AniList HTML fallback returned HTTP %s for %s", response.status, url)
                    return None
                html_text = await response.text()
        except Exception:
            logger.exception("AniList HTML fallback request failed for %s", url)
            return None

        def meta_value(*properties):
            for prop in properties:
                pattern = r'<meta[^>]+(?:property|name)=["\\']' + re.escape(prop) + r'["\\'][^>]+content=["\\']([^"\\']*)["\\']'
                match = re.search(pattern, html_text, re.I | re.S)
                if not match:
                    pattern = r'<meta[^>]+content=["\\']([^"\\']*)["\\'][^>]+(?:property|name)=["\\']' + re.escape(prop) + r'["\\']'
                    match = re.search(pattern, html_text, re.I | re.S)
                if match:
                    return html_lib.unescape(match.group(1)).strip()
            return None

        title = meta_value("og:title", "twitter:title")
        description = meta_value("og:description", "description", "twitter:description")
        image = meta_value("og:image", "twitter:image")
        site_url = meta_value("og:url") or url
        name = re.sub(r"\\s*[-|]\\s*AniList.*$", "", title or "").strip()
        if not name:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
            name = html_lib.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""

        # Embedded JSON can retain structured profile fields when the page's meta tags are sparse.
        embedded_name = None
        embedded_description = None
        embedded_image = None
        for pattern in (
            r'<script[^>]+type=["\\']application/ld\\+json["\\'][^>]*>(.*?)</script>',
            r'<script[^>]+id=["\\']__NEXT_DATA__["\\'][^>]*>(.*?)</script>',
        ):
            for match in re.finditer(pattern, html_text, re.I | re.S):
                try:
                    data = json.loads(match.group(1))
                except (ValueError, TypeError):
                    continue
                stack = [data]
                while stack:
                    item = stack.pop()
                    if isinstance(item, dict):
                        embedded_name = embedded_name or item.get("name") or item.get("full")
                        embedded_description = embedded_description or item.get("description") or item.get("about")
                        embedded_image = embedded_image or item.get("image") or item.get("large")
                        stack.extend(item.values())
                    elif isinstance(item, list):
                        stack.extend(item)
        name = name or (embedded_name if isinstance(embedded_name, str) else None)
        description = description or (embedded_description if isinstance(embedded_description, str) else None)
        image = image or (embedded_image if isinstance(embedded_image, str) else None)
        if not name:
            logger.warning("AniList HTML fallback could not extract a name from %s", url)
            return None

        entity = {
            "id": entity_id,
            "siteUrl": site_url,
            "name": {"full": name, "native": None, "alternative": []},
            "description": description or "",
            "image": {"large": image} if image else {},
            "favourites": None,
            "_entity_kind": entity_kind,
            "_source": "html",
        }
        if entity_kind == "character":
            entity["media"] = {"edges": []}
        elif entity_kind == "staff":
            entity["staffMedia"] = {"edges": []}
        else:
            entity["media"] = {"nodes": []}
            entity["isAnimationStudio"] = None
        return entity

    def build_entity_embeds(self, entity_kind: str, entity: dict) -> List[discord.Embed]:
        """Build a profile overview followed by linked, paginated works when available."""
        name_data = entity.get("name") or {}
        name = (name_data.get("full") if isinstance(name_data, dict) else None) or entity.get("name") or "Unknown"
        if isinstance(name, dict):
            name = name.get("full") or name.get("native") or "Unknown"
        profile_url = entity.get("siteUrl") or f"https://anilist.co/{entity_kind}/{entity.get('id')}"
        descriptions = entity.get("description") or ""
        description = self.clean_text(descriptions)
        if len(description) > 1200:
            description = description[:1197].rstrip() + "..."
        icon = {"character": "🎭", "staff": "🛡️", "studio": "🏢"}[entity_kind]
        title = f"{icon} {name}"
        embed = discord.Embed(title=title[:256], url=profile_url, description=description or "*No description available.*", color=PALETTE.PRIMARY)
        image_data = entity.get("image") or {}
        image_url = image_data.get("large") if isinstance(image_data, dict) else image_data if isinstance(image_data, str) else None
        if image_url and str(image_url).startswith(("https://", "http://")):
            embed.set_thumbnail(url=image_url)
        meta = []
        favourites = entity.get("favourites")
        if favourites is not None:
            meta.append(f"⭐ **Favourites:** {favourites:,}" if isinstance(favourites, int) else f"⭐ **Favourites:** {favourites}")
        if entity_kind == "character":
            if entity.get("gender"):
                meta.append(f"⚧ **Gender:** {entity['gender']}")
            if entity.get("age"):
                meta.append(f"🎂 **Age:** {entity['age']}")
            dob = entity.get("dateOfBirth") or {}
            date_bits = [str(dob.get(key)) for key in ("year", "month", "day") if dob.get(key)]
            if date_bits:
                meta.append("📅 **Birthday:** " + "-".join(date_bits))
        elif entity_kind == "staff":
            language = entity.get("language")
            if language:
                meta.append(f"🗣️ **Language:** {language}")
            occupations = entity.get("primaryOccupations") or []
            if occupations:
                meta.append("🎬 **Occupations:** " + ", ".join(str(value) for value in occupations[:5]))
            years = entity.get("yearsActive") or []
            if years:
                meta.append("📆 **Active:** " + ", ".join(str(value) for value in years))
            if entity.get("homeTown"):
                meta.append(f"📍 **Hometown:** {entity['homeTown']}")
        else:
            meta.append("🎞️ **Animation studio:** " + ("Yes" if entity.get("isAnimationStudio") else "No" if entity.get("isAnimationStudio") is False else "Unknown"))
        if meta:
            embed.add_field(name="Profile", value="\\n".join(meta)[:1024], inline=False)
        source = "HTML fallback" if entity.get("_source") == "html" else "AniList GraphQL"
        embed.set_footer(text=f"AniList • {source} • ID {entity.get('id', '—')}")
        embeds = [embed]

        if entity_kind == "character":
            edges = ((entity.get("media") or {}).get("edges") or [])
        elif entity_kind == "staff":
            edges = ((entity.get("staffMedia") or {}).get("edges") or [])
        else:
            edges = []
            for media in ((entity.get("media") or {}).get("nodes") or []):
                edges.append({"node": media, "staffRole": "Studio"})
        works = []
        seen = set()
        for edge in edges:
            media = edge.get("node") or {}
            if not media or not media.get("id"):
                continue
            if media["id"] in seen:
                continue
            seen.add(media["id"])
            media_title = (media.get("title") or {}).get("romaji") or (media.get("title") or {}).get("english") or "Untitled"
            media_url = media.get("siteUrl") or f"https://anilist.co/{str(media.get('type') or 'anime').lower()}/{media['id']}"
            cover = (media.get("coverImage") or {}).get("large")
            role = edge.get("characterRole") or edge.get("staffRole") or ""
            works.append((media_title, media_url, cover, role))
        for offset in range(0, len(works), 5):
            chunk = works[offset:offset + 5]
            page_number = offset // 5 + 1
            works_embed = discord.Embed(
                title=f"📚 Notable Works • {name}"[:256],
                url=profile_url,
                color=PALETTE.PRIMARY,
                description="\\n".join(
                    f"{'🎭' if entity_kind == 'character' else '🎬'} [{title[:180]}]({url})" + (f" — {role}" if role else "")
                    for title, url, _, role in chunk
                )[:4000],
            )
            if chunk and chunk[0][2]:
                works_embed.set_thumbnail(url=chunk[0][2])
            works_embed.set_footer(text=f"AniList • Works • Page {page_number}/{math.ceil(len(works) / 5)}")
            embeds.append(works_embed)
        return embeds

    class EntityPaginator(ui.View):
        """In-memory paginator for entity profile and works embeds."""
        def __init__(self, embeds: List[discord.Embed], cog: "AniListCog"):
            super().__init__(timeout=900)
            self.embeds = embeds
            self.cog = cog
            self.current = 0
            self.message_id = None
            self.previous_button = ui.Button(label="⬅ Previous", style=discord.ButtonStyle.secondary)
            self.page_button = ui.Button(label=f"1/{len(embeds)}", style=discord.ButtonStyle.secondary, disabled=True)
            self.next_button = ui.Button(label="Next ➡", style=discord.ButtonStyle.primary)
            self.previous_button.callback = self.previous
            self.next_button.callback = self.next
            self.add_item(self.previous_button)
            self.add_item(self.page_button)
            self.add_item(self.next_button)
            self._refresh()

        def _refresh(self):
            self.previous_button.disabled = self.current <= 0
            self.next_button.disabled = self.current >= len(self.embeds) - 1
            self.page_button.label = f"{self.current + 1}/{len(self.embeds)}"

        async def previous(self, interaction: discord.Interaction):
            if self.current <= 0:
                await interaction.response.defer()
                return
            self.current -= 1
            self._refresh()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

        async def next(self, interaction: discord.Interaction):
            if self.current >= len(self.embeds) - 1:
                await interaction.response.defer()
                return
            self.current += 1
            self._refresh()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

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
            userRating
            user { id name siteUrl avatar { large } }
            media { id type siteUrl title { romaji english native } coverImage { large } }
          }
        }
        """
        variables = {"id": review_id}
        try:
            payload = await post_graphql(self.session, query, variables, timeout=20)
            if not payload:
                logger.warning(f"AniList review API returned no data for id {review_id}")
                return None
            
            r = payload.get("Review")
            if not r:
                logger.info(f"AniList review API returned no Review for id {review_id}")
                return None
            
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

        # Extract image links and placeholders, removing them from visible text.
        media_links, cleaned_removed = self.extract_media(text_raw)
        if r.get("images"):
            media_links.extend(r.get("images", []))

        # Deduplicate media URLs in order; query strings are valid image URL suffixes.
        seen = set()
        media_links_unique = []
        for u in media_links:
            if isinstance(u, str) and u.startswith(("https://", "http://")) and u not in seen:
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
        text_for_chunks = self.clean_text(cleaned_removed) or cleaned_full or ""
        text_chunks = [text_for_chunks[i:i + SAFE_CHUNK] for i in range(0, len(text_for_chunks), SAFE_CHUNK)] if text_for_chunks else []

        embeds: List[discord.Embed] = []
        # If there are no media_links -> create text pages only (one or multiple)
        if not media_links:
            if not text_chunks:
                # empty review
                em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=rating_header or "*No review text*", color=discord.Color.from_rgb(15, 23, 32))
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
                em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=desc, color=discord.Color.from_rgb(15, 23, 32))
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
            em = discord.Embed(title=f"Review by {author_name}", url=author_url, description=desc, color=discord.Color.from_rgb(15, 23, 32))
            if avatar:
                em.set_author(name=author_name, url=author_url, icon_url=avatar)
            else:
                em.set_author(name=author_name, url=author_url)
            # attach image for this page if available
            if p < len(media_links):
                img = media_links[p]
                # check if it's an image extension
                image_path = img.lower().split("?", 1)[0].split("#", 1)[0]
                if any(image_path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")) or "anilist.co" in image_path:
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
import asyncio
from typing import Optional, Dict, List
import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path
import aiohttp
import os
import logging
from datetime import datetime

from database import (
    execute_db_operation,
    get_challenge_rules,
    # Guild-aware functions
    set_user_manga_progress_guild_aware,
    upsert_user_manga_progress_guild_aware,
    get_user_manga_progress_guild_aware,
    get_challenge_role_ids_for_guild
)
from helpers.challenge_helper import assign_challenge_role, get_manga_difficulty, get_challenge_difficulty, calculate_manga_points, calculate_challenge_completion_bonus
from helpers.command_logger import log_command
from cogs_test.general_commands.dashboard import command_meta


# Logging Setup
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "challenge_progress.log"

logger = logging.getLogger("ChallengeProgress")
logger.setLevel(logging.INFO)

if not logger.handlers:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # Fallback to console if file logging fails
        stream_handler = logging.StreamHandler()
        logger.addHandler(stream_handler)

user_progress_cache = {}  # {(user_id, manga_id): {"title": str, "chapters_read": int, "status": str, "medium_type": str}}

# AniList API
ANILIST_API = "https://graphql.anilist.co"


# -----------------------------------------
# Helper Functions
# -----------------------------------------
def format_progress_bar(current: int, total: int, width: int = 10) -> str:
    """
    Create a visual progress bar.

    Args:
        current: Current progress value
        total: Total/max value
        width: Number of characters in bar

    Returns:
        Formatted string like "▰▰▰▰▰▱▱▱▱▱ 50%"
    """
    if total <= 0:
        return "▱" * width + " 0%"

    filled = int((current / total) * width)
    filled = max(0, min(filled, width))  # Clamp between 0 and width
    bar = "▰" * filled + "▱" * (width - filled)
    percentage = (current / total * 100) if total > 0 else 0
    return f"{bar} {percentage:.0f}%"

async def fetch_anilist_progress(anilist_id: int, manga_id: int):
    """Fetch AniList progress for a specific manga - includes media release status"""
    query = """
    query ($userId: Int, $mediaId: Int) {
      MediaList(userId: $userId, mediaId: $mediaId) {
        progress
        status
        repeat
        startedAt { year month day }
        media {
          status
        }
      }
    }
    """
    variables = {"userId": anilist_id, "mediaId": manga_id}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ANILIST_API, json={"query": query, "variables": variables}) as resp:
                if resp.status != 200:
                    logger.error(f"AniList API returned status {resp.status} for user {anilist_id}, manga {manga_id}")
                    return {"progress": 0, "status": "CURRENT", "repeat": 0, "started_at": None, "media_status": None}

                data = await resp.json()
                media_list = data.get("data", {}).get("MediaList")
                if not media_list:
                    logger.warning(f"No media list entry for user {anilist_id}, manga {manga_id}")
                    return {"progress": 0, "status": "CURRENT", "repeat": 0, "started_at": None, "media_status": None}

                progress = media_list.get("progress", 0)
                status = media_list.get("status", "CURRENT")
                repeat = media_list.get("repeat", 0)
                started = media_list.get("startedAt")
                started_at = None
                if started and started.get("year"):
                    started_at = f"{started['year']:04}-{started.get('month',1):02}-{started.get('day',1):02}"

                # Get manga release status (FINISHED, RELEASING, etc.)
                media = media_list.get("media", {})
                media_status = media.get("status") if media else None

                return {
                    "progress": progress,
                    "status": status,
                    "repeat": repeat,
                    "started_at": started_at,
                    "media_status": media_status
                }

    except Exception as e:
        logger.error(f"AniList fetch failed for user {anilist_id}, manga {manga_id}: {e}")
        return {"progress": 0, "status": "CURRENT", "repeat": 0, "started_at": None, "media_status": None}

# -----------------------------------------
# Fetch AniList info for a Discord user
# -----------------------------------------
async def get_anilist_info(discord_id: int) -> Optional[Dict]:
    """
    Fetch AniList account information for a Discord user.

    Args:
        discord_id: Discord user ID

    Returns:
        Dictionary with 'id' and 'username' keys, or None if not linked
    """
    row = await execute_db_operation(
        "get anilist info",
        "SELECT anilist_id, anilist_username FROM users WHERE discord_id = ?",
        (discord_id,),
        fetch_type='one'
    )

    if not row:
        return None

    anilist_id, anilist_username = row
    if not anilist_id and not anilist_username:
        return None

    return {"id": anilist_id, "username": anilist_username}

async def fetch_user_manga_progress(anilist_username: str, manga_id: int, db=None):
    query = """
    query ($username: String, $mediaId: Int) {
        MediaList(userName: $username, mediaId: $mediaId, type: MANGA) {
            progress
            status
            repeat
            startedAt {
                year
                month
                day
            }
            media {
                format
            }
        }
    }
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": {"username": anilist_username, "mediaId": manga_id}},
                timeout=10
            ) as resp:

                if resp.status != 200:
                    logger.warning(f"AniList API returned {resp.status} for {anilist_username} / {manga_id}")
                    return None, "Fetch Failed", 0, {}, None

                data = await resp.json()
                media_list = data.get("data", {}).get("MediaList")

                if media_list is None:
                    # User hasn't added this manga
                    return 0, "Not in List", 0, {}, None

                progress = media_list.get("progress", 0)
                status = media_list.get("status", "Not Started")
                repeat = media_list.get("repeat", 0)
                started_at = media_list.get("startedAt") or {}

                media_data = media_list.get("media", {})
                medium_type = media_data.get("format", "MANGA")
                if medium_type == "MANHWA":
                    medium_type = "Manhwa"
                elif medium_type == "MANHUA":
                    medium_type = "Manhua"
                else:
                    medium_type = "Manga"

                # ✅ Pull title from local guild-specific DB instead of AniList
                title_to_use = None
                if db:
                    cursor = await db.execute(
                        "SELECT title FROM guild_challenge_manga WHERE manga_id = ? LIMIT 1",
                        (manga_id,)
                    )
                    row = await cursor.fetchone()
                    await cursor.close()
                    if row:
                        title_to_use = row[0]

                return progress, status, repeat, started_at, title_to_use

    except Exception as e:
        logger.error(f"Failed to fetch AniList progress for {anilist_username} / {manga_id}: {e}")
        return None, "Fetch Failed", 0, {}, None


# -----------------------------------------
# Manga Challenges Cog
# -----------------------------------------
class MangaChallenges(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="challenge-progress",
        description="📚 View your progress in all guild manga challenges (optionally for another user)"
    )
    @command_meta(section="Social", name="Challenge Progress")
    @app_commands.describe(member="Discord member to view progress for (optional)")
    @app_commands.default_permissions(manage_guild=True)
    @log_command
    async def manga_challenges(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """
        Display user's progress across all guild challenges with live update functionality.

        Args:
            interaction: Discord interaction
            member: Optional member to view progress for (defaults to command invoker)
        """
        # Input validation
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in servers.",
                ephemeral=True
            )
            return

        if member and member.bot:
            await interaction.response.send_message(
                "❌ Cannot view progress for bots.",
                ephemeral=True
            )
            return

        logger.info(f"Challenge-progress command invoked by {interaction.user.display_name} ({interaction.user.id}) in guild {interaction.guild.id} ({interaction.guild.name})")
        await interaction.response.defer()

        # Allow viewing another user's progress by passing a member; defaults to the invoking user
        target = member or interaction.user
        target_id = target.id

        anilist_info = await get_anilist_info(target_id)
        if not anilist_info:
            if member:
                await interaction.followup.send(
                    f"⚠️ {target.mention} has not linked their AniList account.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "⚠️ You have not linked your AniList account. Use `/link_anilist` first.",
                    ephemeral=True
                )
            return

        anilist_username = anilist_info.get("username")
        anilist_id = anilist_info.get("id")

        # Fetch guild-specific challenges
        guild_id = interaction.guild.id
        logger.info(f"Fetching challenge progress for guild {guild_id}, user {target.display_name} ({target_id})")

        challenges = await execute_db_operation(
            "get guild challenges",
            "SELECT challenge_id, title FROM guild_challenges WHERE guild_id = ?",
            (guild_id,),
            fetch_type='all'
        )

        if not challenges:
            await interaction.followup.send(
                "⚠️ No challenges found for this server. Use `/challenge-manage` to create challenges.",
                ephemeral=True
            )
            return

        # Sort challenges alphabetically by title
        challenges.sort(key=lambda x: x[1].lower())

        embeds = []
        options = []
        embed_page_map = {}  # {embed_index: (challenge_id, start_idx, end_idx)}
        all_manga_data = {}  # {challenge_id: [(manga_id, title, total_chapters, medium_type), ...]}

        for challenge_id, title in challenges:
            manga_rows = await execute_db_operation(
                "get challenge manga",
                "SELECT manga_id, title, total_chapters FROM guild_challenge_manga WHERE guild_id = ? AND challenge_id = ?",
                (guild_id, challenge_id),
                fetch_type='all'
            )

            if not manga_rows:
                manga_rows = []

            manga_rows.sort(key=lambda x: x[1].lower())

            # Store manga data for updates (add default medium_type since guild table doesn't have it)
            manga_rows_with_type = [(mid, title_text, chapters, "manga") for mid, title_text, chapters in manga_rows]
            all_manga_data[challenge_id] = manga_rows_with_type

            # Process ALL manga for this challenge in a single embed
            description_lines = []
            for manga_id, manga_title, total_chapters, medium_type in manga_rows_with_type:
                # ✅ Always fetch from database first for persistence across bot restarts
                progress_row = await get_user_manga_progress_guild_aware(
                    target_id, interaction.guild.id, manga_id
                )

                if progress_row:
                    # Convert tuple to dict for easier access
                    # Table schema: discord_id, guild_id, manga_id, title, current_chapter, rating, status, points, repeat, started_at, updated_at
                    chapters_read = progress_row[4] if len(progress_row) > 4 else 0  # current_chapter
                    status = progress_row[6] if len(progress_row) > 6 and progress_row[6] else ("Not Started" if chapters_read == 0 else "In Progress")  # status
                    # Use persisted manga title if available
                    if len(progress_row) > 3 and progress_row[3]:
                        manga_title = progress_row[3]  # title
                    logger.debug(f"Loaded from DB: manga {manga_id}, {chapters_read}/{total_chapters} chapters, status: {status}")
                else:
                    # No persisted data - show as not started
                    chapters_read = 0
                    status = "Not Started"
                    logger.debug(f"No DB data for manga {manga_id}, showing as Not Started")

                # Update cache with database values
                cache_key = (target_id, manga_id)
                user_progress_cache[cache_key] = {
                    "title": manga_title,
                    "chapters_read": chapters_read,
                    "status": status,
                    "medium_type": medium_type
                }

                # Add progress bar for visual feedback
                progress_bar = format_progress_bar(chapters_read, total_chapters)
                description_lines.append(
                    f"[{manga_title}](https://anilist.co/manga/{manga_id})\n"
                    f"{progress_bar} `{chapters_read}/{total_chapters}` • {status}"
                )

            # Create single embed for this challenge with ALL manga
            description = "\n\n".join(description_lines) if description_lines else "_No manga added to this challenge yet._"

            # Check Discord's description limit (4096 chars) and truncate if needed
            if len(description) > 4096:
                description = description[:4090] + "..."
                logger.warning(f"Challenge '{title}' description truncated to fit Discord's 4096 character limit")

            embed = discord.Embed(
                title=f"📚 Guild Challenge: {title}",
                description=description,
                color=discord.Color.random()
            )
            # Indicate whose progress is being shown and which guild
            embed.set_author(name=f"Progress for {target.display_name} ({anilist_username}) | {interaction.guild.name}")
            embed.set_footer(text=f"Challenge ID: {challenge_id} | {len(manga_rows_with_type)} manga total")
            embeds.append(embed)
            embed_index = len(embeds) - 1
            embed_page_map[embed_index] = (challenge_id, 0, len(manga_rows_with_type))
            options.append(discord.SelectOption(label=title, value=str(embed_index)))


        # Discord dropdown limit: max 25 options
        total_challenges = len(options)
        if total_challenges > 25:
            options = options[:25]
            logger.info(f"Limited dropdown to 25 challenges (total: {total_challenges}). Users can use navigation buttons for remaining challenges.")
            # Add note to first embed
            if embeds:
                embeds[0].set_footer(text=f"ℹ️ Use ◀️ ▶️ buttons to navigate all {total_challenges} challenges. Dropdown shows first 25 only.")

        # -----------------------------------------
        # Challenge View with pagination and update button
        # -----------------------------------------
        class ChallengeView(discord.ui.View):
            def __init__(self, bot, embeds, options, page_to_challenge_id, target_id, anilist_username, anilist_id, all_manga_data):
                super().__init__(timeout=None)
                self.bot = bot
                self.embeds = embeds
                self.options = options
                self.page_to_challenge_id = page_to_challenge_id
                self.target_id = target_id
                self.anilist_username = anilist_username
                self.anilist_id = anilist_id
                self.all_manga_data = all_manga_data  # {challenge_id: [(manga_id, title, total_chapters, medium_type), ...]}
                self.current_page = 0
                self.message: Optional[discord.Message] = None

                # Update state tracking
                self.is_updating = False
                self.updating_page_index = None
                self.update_cancelled = False

                # Dropdown - only add if there are options
                if self.options:
                    self.select = discord.ui.Select(
                        placeholder="Select Challenge",
                        options=self.options
                    )
                    self.select.callback = self.select_callback
                    self.add_item(self.select)

            def determine_status(self, ani_progress, ani_status, ani_repeat, total_chapters, ani_started_at, challenge_start_date, media_status=None):
                """
                Determine manga status based on AniList data and challenge dates.

                Priority order:
                1. Skipped - Started before challenge with 25%+ progress (applies to ALL statuses: completed, caught up, paused, dropped, in progress)
                2. Reread - Completed with rereads >= 1
                3. Completed - User finished + manga is FINISHED + rereads == 0
                4. Caught Up - User finished + manga is RELEASING + rereads == 0
                5. In Progress - Currently reading, progress < total
                6. Paused - Paused status with >= 25 chapters
                7. Dropped - Dropped status
                8. Not Started - Default fallback
                """
                def _to_date(val):
                    """Parse date from various formats to date object."""
                    if not val:
                        return None
                    try:
                        from datetime import datetime, date
                        # If already a date object, return it
                        if isinstance(val, date):
                            return val
                        # If datetime object, convert to date
                        if isinstance(val, datetime):
                            return val.date()
                        # If string, parse it
                        if isinstance(val, str):
                            val = val.strip()
                            # Try ISO format YYYY-MM-DD (most common from AniList and SQLite)
                            if len(val) >= 10:
                                try:
                                    return datetime.strptime(val[:10], "%Y-%m-%d").date()
                                except ValueError:
                                    pass
                            # Try other common formats
                            formats = ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]
                            for fmt in formats:
                                try:
                                    parsed = datetime.strptime(val, fmt)
                                    return parsed.date()
                                except ValueError:
                                    continue
                    except Exception as e:
                        logger.warning(f"Failed to parse date '{val}' (type: {type(val).__name__}): {e}")
                    return None

                # Baseline total chapters
                effective_total = total_chapters if (isinstance(total_chapters, (int, float)) and total_chapters > 0) else 1

                # Normalize numeric inputs
                try:
                    ani_progress_num = max(0, int(ani_progress or 0))
                except Exception:
                    ani_progress_num = 0

                try:
                    ani_repeat_num = max(0, int(ani_repeat or 0))
                except Exception:
                    ani_repeat_num = 0

                status_upper = (ani_status or "").upper()
                media_status_upper = (media_status or "").upper()

                # Parse dates for skipped check
                started_at_val = _to_date(ani_started_at)
                challenge_start_date_val = _to_date(challenge_start_date)

                # Calculate progress percentage for skipped check
                pct_progress = (ani_progress_num / effective_total) if effective_total else 0.0

                # Validate date types before comparison
                from datetime import date as date_type
                both_dates_valid = (
                    started_at_val is not None 
                    and challenge_start_date_val is not None
                    and isinstance(started_at_val, date_type)
                    and isinstance(challenge_start_date_val, date_type)
                )

                logger.debug(
                    f"Status determination: progress={ani_progress_num}/{effective_total} ({pct_progress:.1%}), "
                    f"status={status_upper}, repeat={ani_repeat_num}, media_status={media_status_upper}, "
                    f"started_at_raw='{ani_started_at}', started_at_parsed={started_at_val} (type: {type(started_at_val).__name__}), "
                    f"challenge_start_raw='{challenge_start_date}', challenge_start_parsed={challenge_start_date_val} (type: {type(challenge_start_date_val).__name__}), "
                    f"dates_valid={both_dates_valid}"
                )

                # Priority 1: SKIPPED - Started before challenge with 25%+ progress
                # Applies to ALL statuses: completed, caught up, paused, dropped, in progress
                # This ensures titles started before challenge existence are marked as skipped
                # IMPORTANT: Only mark as skipped if started_at is BEFORE challenge_start_date
                if both_dates_valid:
                    date_comparison = started_at_val < challenge_start_date_val
                    logger.debug(
                        f"Date comparison: {started_at_val} < {challenge_start_date_val} = {date_comparison}"
                    )
                    
                    if date_comparison:  # Started BEFORE challenge
                        if pct_progress >= 0.25:
                            logger.info(
                                f"✅ Status: Skipped (started {started_at_val} BEFORE challenge {challenge_start_date_val} "
                                f"with {pct_progress:.1%} progress, AniList status: {status_upper})"
                            )
                            return "Skipped"
                        else:
                            logger.debug(
                                f"⚠️ Skipped check failed: progress {pct_progress:.1%} < 25% threshold "
                                f"(started {started_at_val} before challenge {challenge_start_date_val})"
                            )
                    else:  # Started AFTER or ON challenge date - NOT skipped
                        logger.debug(
                            f"✅ Skipped check passed: started {started_at_val} is AFTER or ON challenge {challenge_start_date_val} - proceeding to normal status checks"
                        )
                else:
                    missing_dates = []
                    if not challenge_start_date_val:
                        missing_dates.append(f"challenge_start_date (raw: '{challenge_start_date}')")
                    if not started_at_val:
                        missing_dates.append(f"started_at (raw: '{ani_started_at}')")
                    logger.debug(f"⚠️ Skipped check skipped: missing dates - {', '.join(missing_dates)}")

                # Priority 2: REREAD - Completed with multiple rereads
                if status_upper == "COMPLETED" and ani_progress_num >= effective_total and ani_repeat_num >= 1:
                    logger.debug(f"Status: Reread (repeat count: {ani_repeat_num})")
                    return "Reread"

                # Priority 3 & 4: COMPLETED vs CAUGHT UP - Finished reading, check manga status
                if ani_progress_num >= effective_total and ani_repeat_num == 0:
                    if status_upper == "COMPLETED":
                        # User marked as completed - check if manga is finished
                        if media_status_upper == "FINISHED":
                            logger.debug("Status: Completed (manga finished releasing)")
                            return "Completed"
                        else:
                            # Manga still releasing/hiatus/cancelled
                            logger.debug(f"Status: Caught Up (manga status: {media_status_upper})")
                            return "Caught Up"
                    elif status_upper == "CURRENT":
                        # User still has as "reading" but caught up
                        logger.debug(f"Status: Caught Up (current, caught up, manga: {media_status_upper})")
                        return "Caught Up"

                # Priority 5: IN PROGRESS - Currently reading
                if status_upper == "CURRENT" and 0 < ani_progress_num < effective_total:
                    logger.debug(f"Status: In Progress ({ani_progress_num}/{effective_total})")
                    return "In Progress"

                # Priority 6: PAUSED - Paused with sufficient progress
                if status_upper == "PAUSED" and ani_progress_num >= 25:
                    logger.debug(f"Status: Paused ({ani_progress_num} chapters)")
                    return "Paused"

                # Priority 7: DROPPED - Dropped status
                if status_upper == "DROPPED":
                    logger.debug("Status: Dropped")
                    return "Dropped"

                # Priority 8: NOT STARTED - Default fallback
                logger.debug("Status: Not Started (default)")
                return "Not Started"

            async def update_current_page(self, interaction: discord.Interaction):
                """Update only the manga on the current page with live progress updates"""
                logger.info(f"Updating challenge progress page for user {self.target_id} in guild {interaction.guild.id}")
                await interaction.response.defer()

                # Prevent multiple simultaneous updates
                if self.is_updating:
                    await interaction.followup.send("⚠️ An update is already in progress. Please wait...", ephemeral=True)
                    return

                if self.current_page not in self.page_to_challenge_id:
                    await interaction.followup.send("❌ Unable to determine current page data.", ephemeral=True)
                    return

                # Mark as updating and store which page
                self.is_updating = True
                self.updating_page_index = self.current_page
                self.update_cancelled = False

                challenge_id, start_idx, end_idx = self.page_to_challenge_id[self.current_page]

                try:
                    # Disable navigation buttons during update
                    self._disable_navigation(True)
                    await self._update_view()

                    # Get guild-specific challenge info
                    # Use COALESCE to fallback to created_at if start_date is NULL
                    challenge_row = await execute_db_operation(
                        "get challenge info",
                        "SELECT title, COALESCE(start_date, created_at) FROM guild_challenges WHERE guild_id = ? AND challenge_id = ?",
                        (interaction.guild.id, challenge_id),
                        fetch_type='one'
                    )
                    challenge_title = challenge_row[0] if challenge_row else f"Challenge {challenge_id}"
                    challenge_start_date = challenge_row[1] if challenge_row else None
                    
                    # Log for debugging
                    logger.debug(
                        f"Challenge '{challenge_title}' (ID: {challenge_id}): "
                        f"start_date={challenge_start_date}"
                    )

                    # Get manga for this page
                    manga_data = self.all_manga_data.get(challenge_id, [])
                    page_manga = manga_data[start_idx:end_idx]
                    total_manga = len(page_manga)

                    updated_count = 0
                    description_lines = []

                    for idx, (manga_id, manga_title, total_chapters, medium_type) in enumerate(page_manga):
                        # Check if update was cancelled (page changed)
                        if self.update_cancelled or self.current_page != self.updating_page_index:
                            logger.info(f"Update cancelled - page changed from {self.updating_page_index} to {self.current_page}")
                            await interaction.followup.send("⚠️ Update cancelled - page was changed", ephemeral=True)
                            return

                        # Fetch from AniList
                        ani_data = await fetch_anilist_progress(self.anilist_id, manga_id)
                        await asyncio.sleep(2.5)  # ✅ Rate limiting: 2.5s = 24 req/min

                        ani_progress = ani_data['progress']
                        ani_status = ani_data['status']
                        ani_repeat = ani_data['repeat']
                        ani_started_at = ani_data['started_at']
                        media_status = ani_data.get('media_status')

                        # Determine status
                        status = self.determine_status(
                            ani_progress, ani_status, ani_repeat,
                            total_chapters, ani_started_at, challenge_start_date, media_status
                        )

                        # Calculate points with rebalanced algorithm
                        difficulty = await get_manga_difficulty(total_chapters, medium_type)
                        points = calculate_manga_points(total_chapters, ani_progress, status, difficulty, ani_repeat)

                        # ✅ Persist to database for survival across bot restarts
                        await upsert_user_manga_progress_guild_aware(
                            self.target_id,
                            interaction.guild.id,
                            manga_id,
                            manga_title,
                            ani_progress,
                            points,
                            status,
                            ani_repeat,
                            ani_started_at
                        )
                        
                        logger.debug(f"Persisted progress for manga {manga_id}: {ani_progress}/{total_chapters} chapters, {points} points, status: {status}")

                        # Update cache
                        cache_key = (self.target_id, manga_id)
                        user_progress_cache[cache_key] = {
                            "title": manga_title,
                            "chapters_read": ani_progress,
                            "status": status,
                            "medium_type": medium_type
                        }

                        # Add to description with progress bar
                        progress_bar = format_progress_bar(ani_progress, total_chapters)
                        description_lines.append(
                            f"[{manga_title}](https://anilist.co/manga/{manga_id})\n"
                            f"{progress_bar} `{ani_progress}/{total_chapters}` • {status}"
                        )
                        updated_count += 1

                        # ✅ LIVE UPDATE: Update embed after each manga
                        # Check again before updating
                        if self.current_page == self.updating_page_index:
                            # Build current description with progress indicator
                            current_description = "\n\n".join(description_lines)
                            progress_text = f"\n\n⏳ **Updating... {updated_count}/{total_manga} manga processed**"

                            live_embed = discord.Embed(
                                title=f"📚 Guild Challenge: {challenge_title}",
                                description=current_description + progress_text,
                                color=discord.Color.orange()  # Orange while updating
                            )
                            target = self.bot.get_user(self.target_id) or f"User {self.target_id}"
                            live_embed.set_author(name=f"Progress for {target.display_name if hasattr(target, 'display_name') else target} ({self.anilist_username}) | {interaction.guild.name}")
                            live_embed.set_footer(
                                text=f"Page {self.current_page + 1} of {len(self.embeds)} | "
                                    f"Updating... {updated_count}/{total_manga} | Guild: {interaction.guild.name}"
                            )

                            try:
                                await interaction.followup.edit_message(
                                    message_id=self.message.id, embed=live_embed, view=self
                                )
                            except Exception as e:
                                logger.warning(f"Failed to update embed during live update: {e}")


                    # Final update - only if still on same page
                    if self.current_page == self.updating_page_index:
                        description = "\n\n".join(description_lines) if description_lines else "_No manga added to this challenge yet._"

                        final_embed = discord.Embed(
                            title=f"📚 Guild Challenge: {challenge_title}",
                            description=description,
                            color=discord.Color.green()  # Green when complete
                        )
                        target = self.bot.get_user(self.target_id) or f"User {self.target_id}"
                        final_embed.set_author(name=f"Progress for {target.display_name if hasattr(target, 'display_name') else target} ({self.anilist_username}) | {interaction.guild.name}")
                        final_embed.set_footer(
                            text=f"Page {self.current_page + 1} of {len(self.embeds)} | "
                                f"Guild Challenge ID: {challenge_id} | ✅ Updated {updated_count} manga | Guild: {interaction.guild.name}"
                        )

                        self.embeds[self.current_page] = final_embed

                        await interaction.followup.edit_message(
                            message_id=self.message.id, embed=final_embed, view=self
                        )
                        await interaction.followup.send(f"✅ Updated {updated_count} manga on this page!", ephemeral=True)
                    else:
                        logger.info(f"Skipped final update - page changed from {self.updating_page_index} to {self.current_page}")

                finally:
                    # Always re-enable navigation when done
                    self.is_updating = False
                    self.updating_page_index = None
                    self._disable_navigation(False)
                    await self._update_view()

            def _disable_navigation(self, disabled: bool):
                """Enable or disable navigation buttons"""
                for item in self.children:
                    if isinstance(item, discord.ui.Button):
                        if item.label in ["⬅️ Previous", "➡️ Next"]:
                            item.disabled = disabled
                    elif isinstance(item, discord.ui.Select):
                        item.disabled = disabled

            async def _update_view(self):
                """Update the view's buttons state"""
                try:
                    if self.message:
                        await self.message.edit(view=self)
                except Exception as e:
                    logger.warning(f"Failed to update view: {e}")

            async def update_message(self, interaction: discord.Interaction):
                embed = self.embeds[self.current_page]
                embed.set_footer(
                    text=f"Page {self.current_page + 1} of {len(self.embeds)} | "
                        f"Guild Challenge ID: {self.page_to_challenge_id[self.current_page][0]} | Guild: {interaction.guild.name}"
                )
                try:
                    await interaction.response.edit_message(embed=embed, view=self)
                except discord.errors.InteractionResponded:
                    await interaction.followup.edit_message(
                        message_id=self.message.id, embed=embed, view=self
                    )

            @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary, row=1)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Cancel any ongoing update when changing pages
                if self.is_updating:
                    self.update_cancelled = True
                    logger.info("Update cancelled by user navigation (Previous)")
                self.current_page = (self.current_page - 1) % len(self.embeds)
                await self.update_message(interaction)

            @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary, row=1)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Cancel any ongoing update when changing pages
                if self.is_updating:
                    self.update_cancelled = True
                    logger.info("Update cancelled by user navigation (Next)")
                self.current_page = (self.current_page + 1) % len(self.embeds)
                await self.update_message(interaction)

            @discord.ui.button(label="🔄 Update Page", style=discord.ButtonStyle.primary, row=1)
            async def update_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.update_current_page(interaction)

            @discord.ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, row=1)
            async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                """Show help information about challenge rules, scoring, and status definitions."""
                await interaction.response.defer(ephemeral=True)
                
                # Create comprehensive help embed
                embed = discord.Embed(
                    title="📚 Challenge Rules & Scoring Guide",
                    description="Learn how challenge statuses, scoring, and rules work!",
                    color=discord.Color.blue()
                )
                
                # Status Definitions
                embed.add_field(
                    name="📊 Status Definitions",
                    value=(
                        "**✅ Completed** - Finished reading (manga is finished releasing)\n"
                        "**📖 Caught Up** - Finished reading (manga still releasing)\n"
                        "**🔄 In Progress** - Currently reading, progress < 100%\n"
                        "**⏸️ Paused** - Paused with ≥25 chapters read\n"
                        "**❌ Dropped** - Dropped the manga\n"
                        "**⏭️ Skipped** - Started before challenge with ≥25% progress\n"
                        "**📚 Reread** - Completed with ≥1 reread\n"
                        "**⚪ Not Started** - Haven't started reading yet"
                    ),
                    inline=False
                )
                
                # Skipped Status Explanation (the key use case)
                embed.add_field(
                    name="⏭️ Understanding 'Skipped' Status",
                    value=(
                        "A title is marked **Skipped** if:\n"
                        "• You started reading it **before** the challenge was created\n"
                        "• AND you've read **≥25%** of total chapters\n\n"
                        "**Important Example:**\n"
                        "If you started a manga in 2021, and a challenge was created in 2025:\n"
                        "• With <25% progress → Status: **In Progress**\n"
                        "• With ≥25% progress → Status: **Skipped**\n\n"
                        "⚠️ **Note:** If you cross the 25% threshold while reading, your status will automatically change to 'Skipped' on the next update. This is intentional to ensure fairness for new challenge participants. It is recommended that you edit your start date on anilist to the date you actually started reading the manga to avoid being marked as skipped."
                    ),
                    inline=False
                )
                
                # Scoring System
                embed.add_field(
                    name="💯 Scoring System",
                    value=(
                        "Points are calculated using:\n"
                        "• **Base Points** - Based on total chapters (square root scaling)\n"
                        "• **Status Multiplier** - Depends on your status\n"
                        "• **Difficulty Factor** - Based on manga length/complexity\n"
                        "• **Completion Ratio** - For incomplete statuses (partial credit)\n\n"
                        "**Status Multipliers:**\n"
                        "• Completed/Caught Up: **1.2x**\n"
                        "• In Progress: **0.8x** (with partial credit)\n"
                        "• Paused: **0.5x** (with partial credit)\n"
                        "• Skipped: **0.3x** (with partial credit)\n"
                        "• Dropped: **0.3x** (with partial credit)\n"
                        "• Reread: **1.5x** (bonus for rereads!)"
                    ),
                    inline=False
                )
                
                # Challenge Rules
                embed.add_field(
                    name="📋 Challenge Rules",
                    value=(
                        "• Challenges are **server-specific** (each server has its own challenges)\n"
                        "• Progress is tracked from your **AniList account**\n"
                        "• Use **🔄 Update Page** to refresh your progress from AniList\n"
                        "• Your progress is **automatically saved** after updates\n"
                        "• **Start dates** are from AniList (when you first added the manga)\n"
                        "• Challenge start date = when the challenge was created\n"
                        "• Status priority: Skipped > Reread > Completed/Caught Up > In Progress > Paused > Dropped"
                    ),
                    inline=False
                )
                
                embed.set_footer(
                    text="💡 Tip: Keep reading! Statuses update automatically when you update progress."
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.debug(f"Help button clicked by {interaction.user.display_name} ({interaction.user.id})")

            async def select_callback(self, interaction: discord.Interaction):
                # Cancel any ongoing update when changing pages
                if self.is_updating:
                    self.update_cancelled = True
                    logger.info("Update cancelled by user navigation (Dropdown)")
                self.current_page = int(self.select.values[0])
                await self.update_message(interaction)


        # -----------------------------------------
        # Send the view
        # -----------------------------------------
        view = ChallengeView(
            self.bot,
            embeds,
            options,
            embed_page_map,  # page_to_challenge_id
            target_id,
            anilist_username,
            anilist_id,
            all_manga_data
        )
        msg = await interaction.followup.send(embed=embeds[0], view=view)
        view.message = msg
        
        logger.info(f"Challenge-progress displayed successfully for {target.display_name} in guild {guild_id} with {len(challenges)} challenges")


async def setup(bot: commands.Bot):
    await bot.add_cog(MangaChallenges(bot))
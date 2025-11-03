import asyncio
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from config import DB_PATH
from database import (
    get_challenge_rules,
    # Guild-aware functions
    set_user_manga_progress_guild_aware, 
    upsert_user_manga_progress_guild_aware,
    get_user_manga_progress_guild_aware,
    get_challenge_role_ids_for_guild
)
import aiohttp
import os
import logging
from datetime import datetime
from helpers.challenge_helper import assign_challenge_role, get_manga_difficulty, get_challenge_difficulty, calculate_manga_points, calculate_challenge_completion_bonus


logger = logging.getLogger("ChallengeProgress")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == os.path.abspath("logs/challenge_progress.log")
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler("logs/challenge_progress.log")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(stream_handler)
user_progress_cache = {}  # {(user_id, manga_id): (chapters_read, status)}

# AniList API
ANILIST_API = "https://graphql.anilist.co"

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
async def get_anilist_info(discord_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT anilist_id, anilist_username FROM users WHERE discord_id = ?", (discord_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
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
    @app_commands.describe(member="Discord member to view progress for (optional)")
    @app_commands.default_permissions(manage_guild=True)
    async def manga_challenges(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        logger.info(f"Challenge-progress command invoked by {interaction.user.display_name} ({interaction.user.id}) in guild {interaction.guild.id} ({interaction.guild.name})")
        await interaction.response.defer(ephemeral=True)

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
        
        async with aiosqlite.connect(DB_PATH) as db:
            challenges = await db.execute_fetchall(
                "SELECT challenge_id, title FROM guild_challenges WHERE guild_id = ?",
                (guild_id,)
            )
        if not challenges:
            await interaction.followup.send(f"⚠️ No challenges found for this server. Use `/challenge-manage` to create challenges.", ephemeral=True)
            return

        # Sort challenges alphabetically by title
        challenges.sort(key=lambda x: x[1].lower())

        embeds = []
        options = []
        embed_page_map = {}  # {embed_index: (challenge_id, start_idx, end_idx)}
        all_manga_data = {}  # {challenge_id: [(manga_id, title, total_chapters, medium_type), ...]}

        async with aiosqlite.connect(DB_PATH) as db:
            for challenge_id, title in challenges:

                manga_rows = await db.execute_fetchall(
                    "SELECT manga_id, title, total_chapters FROM guild_challenge_manga WHERE guild_id = ? AND challenge_id = ?",
                    (guild_id, challenge_id)
                )
                manga_rows.sort(key=lambda x: x[1].lower())
                
                # Store manga data for updates (add default medium_type since guild table doesn't have it)
                manga_rows_with_type = [(mid, title, chapters, "manga") for mid, title, chapters in manga_rows]
                all_manga_data[challenge_id] = manga_rows_with_type

                chunk_size = 10
                chunk_index = 0
                for i in range(0, len(manga_rows_with_type), chunk_size):
                    description_lines = []
                    for manga_id, manga_title, total_chapters, medium_type in manga_rows_with_type[i:i + chunk_size]:
                        cache_key = (target_id, manga_id)
                        if cache_key in user_progress_cache:
                            cache = user_progress_cache.get(cache_key)
                            if cache:
                                manga_title = cache["title"]
                                chapters_read = cache["chapters_read"]
                                status = cache["status"]
                        else:
                            # Use guild-aware function to get user progress
                            progress_data = await get_user_manga_progress_guild_aware(
                                target_id, manga_id, interaction.guild.id
                            )
                            
                            if progress_data:
                                chapters_read = progress_data['current_chapter']
                                status = progress_data['status'] if progress_data['status'] else ("Not Started" if chapters_read == 0 else "In Progress")
                            else:
                                chapters_read = 0
                                status = "Not Started"

                            user_progress_cache[cache_key] = {
                                "title": manga_title,
                                "chapters_read": chapters_read,
                                "status": status,
                                "medium_type": medium_type 
                            }

                        description_lines.append(
                            f"[{manga_title}](https://anilist.co/manga/{manga_id}) - `{chapters_read}/{total_chapters}` • Status: `{status}`"
                        )

                    description = "\n\n".join(description_lines) if description_lines else "_No manga added to this challenge yet._"
                    embed = discord.Embed(
                        title=f"� Guild Challenge: {title}",
                        description=description,
                        color=discord.Color.random()
                    )
                    # Indicate whose progress is being shown and which guild
                    embed.set_author(name=f"Progress for {target.display_name} ({anilist_username}) | {interaction.guild.name}")
                    embeds.append(embed)
                    embed_index = len(embeds) - 1
                    embed_page_map[embed_index] = (challenge_id, i, i + chunk_size)
                    options.append(discord.SelectOption(label=f"{title} - Page {chunk_index + 1}", value=str(embed_index)))
                    chunk_index += 1

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

                # Dropdown
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
                1. Skipped - Started before challenge (reading or completed status)
                2. Reread - Completed with rereads > 1
                3. Completed - User finished + manga is FINISHED + rereads == 0
                4. Caught Up - User finished + manga is RELEASING + rereads == 0
                5. In Progress - Currently reading, progress < total
                6. Paused - Paused status with >= 25 chapters
                7. Dropped - Dropped status
                8. Not Started - Default fallback
                """
                def _to_date(val):
                    if not val:
                        return None
                    try:
                        from datetime import datetime
                        if isinstance(val, str) and len(val) >= 10:
                            return datetime.strptime(val[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
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

                logger.debug(
                    f"Status determination: progress={ani_progress_num}/{effective_total} ({pct_progress:.1%}), "
                    f"status={status_upper}, repeat={ani_repeat_num}, media_status={media_status_upper}, "
                    f"started={started_at_val}, challenge_start={challenge_start_date_val}"
                )

                # Priority 1: SKIPPED - Started before challenge with reading/completed status and 25% progress
                if challenge_start_date_val and started_at_val and started_at_val < challenge_start_date_val:
                    if status_upper in ("CURRENT", "COMPLETED") and pct_progress >= 0.25:
                        logger.debug(f"Status: Skipped (started before challenge with {pct_progress:.1%} progress)")
                        return "Skipped"

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
                    async with aiosqlite.connect(DB_PATH) as db:
                        cursor = await db.execute("SELECT title, start_date FROM guild_challenges WHERE guild_id = ? AND challenge_id = ?", (interaction.guild.id, challenge_id))
                        challenge_row = await cursor.fetchone()
                        await cursor.close()
                        challenge_title = challenge_row[0] if challenge_row else f"Challenge {challenge_id}"
                        challenge_start_date = challenge_row[1] if challenge_row else None

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

                            # Calculate points
                            difficulty = await get_manga_difficulty(total_chapters, medium_type)
                            points = calculate_manga_points(total_chapters, ani_progress, status, difficulty, ani_repeat)

                            # Update database
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

                            # Update cache
                            cache_key = (self.target_id, manga_id)
                            user_progress_cache[cache_key] = {
                                "title": manga_title,
                                "chapters_read": ani_progress,
                                "status": status,
                                "medium_type": medium_type
                            }

                            # Add to description
                            description_lines.append(
                                f"[{manga_title}](https://anilist.co/manga/{manga_id}) - `{ani_progress}/{total_chapters}` • Status: `{status}`"
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

                        await db.commit()

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
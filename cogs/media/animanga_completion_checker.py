import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
import datetime
import asyncio
import logging
import aiohttp

from config import CHANNEL_ID
from database import (
    is_user_moderator,
    set_guild_manga_channel,
    get_guild_manga_channel,
    get_all_guild_manga_channels,
    get_scanned_media,
    save_scanned_media_batch,
    get_scan_metadata,
    set_scan_metadata
)

ANILIST_URL = "https://graphql.anilist.co"

# ---------------- Logging ----------------
LOG_DIR = "logs"
import os
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "animanga_completion.log")

logger = logging.getLogger("AnimangaCompletion")
logger.setLevel(logging.INFO)

# Avoid duplicate file handlers on reload
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(LOG_FILE)
           for h in logger.handlers):
    try:
        # Try to open file handler; if the file is locked, fall back to console
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(file_handler)
    except Exception:
        # Fall back to stream handler to avoid failing cog import
        stream_fallback = logging.StreamHandler()
        stream_fallback.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(stream_fallback)

# Console output
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(stream_handler)

query = """
query {
  Page(page: 1, perPage: 25) {
    media(type: MANGA, sort: END_DATE_DESC, status_in: [FINISHED, CANCELLED]) {
      id
      title { romaji english }
      status
            averageScore
      chapters
      format
      endDate { year month day }
      coverImage { large }
            genres
      siteUrl
    }
  }
}
"""

anime_query = """
query {
    Page(page: 1, perPage: 25) {
        media(type: ANIME, sort: END_DATE_DESC, status_in: [FINISHED, CANCELLED]) {
            id
            title { romaji english }
            status
            averageScore
            episodes
            format
            endDate { year month day }
            coverImage { large }
            genres
            siteUrl
        }
    }
}
"""


def mod_only():
    """App command check that allows only users with the configured guild mod role
    or users with administrative/manage permissions as a fallback.
    Use as: @mod_only() on an app command.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        try:
            member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(interaction.user.id)
            return await is_user_moderator(member, interaction.guild.id)
        except Exception:
            return False

    return app_commands.check(predicate)


class Finisher(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # use module-level logger configured above
        self.logger = logger
        self.logger.info("Finisher cog initialized")

    def cog_unload(self):
        self.daily_check.cancel()

    async def cog_load(self):
        """Called when the cog is loaded into the bot. Start scheduled task here so the client exists."""
        self.logger.info("Finisher cog loaded - scheduling start of daily_check task")
        # Start an asynchronous helper that will safely wait for the bot to be ready
        # and then start the scheduled task. Use create_task so cog_load returns
        # quickly and does not block/import-time behavior.
        try:
            asyncio.create_task(self._ensure_daily_check_started())
        except Exception:
            self.logger.exception("Failed to schedule daily_check starter task from cog_load")

    async def _ensure_daily_check_started(self):
        """Helper started from cog_load to wait safely for readiness and start daily_check once.
        This isolates any calls to wait_until_ready() so they don't run during import and
        centralizes the logic for starting the task only once.
        """
        try:
            # Reuse before_check's safer waiting logic by calling it; it will
            # attempt a bounded wait and then poll for readiness.
            await self.before_check()
            self.logger.debug("Bot readiness confirmed in _ensure_daily_check_started")
        except Exception as e:
            # Already logged inside before_check, but catch anything unexpected
            self.logger.debug(f"Error while waiting for bot readiness in _ensure_daily_check_started: {e}")

        try:
            if not self.daily_check.is_running():
                self.daily_check.start()
                self.logger.info("Finisher daily_check task started from _ensure_daily_check_started")
            else:
                self.logger.debug("Finisher daily_check task already running, skipping start")
        except Exception as e:
            self.logger.error(f"Failed to start daily_check task from _ensure_daily_check_started: {e}")

    # === Utilities ===
    async def fetch_manga(self):
        """Async fetch from AniList with timeout and basic error handling."""
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            self.logger.info("Fetching manga list from AniList")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(ANILIST_URL, json={"query": query}) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"AniList returned status {resp.status}")
                        return []
                    data = await resp.json()
                    media = data.get("data", {}).get("Page", {}).get("media", [])
                    self.logger.info(f"AniList returned {len(media)} media entries")
                    return media
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.exception(f"Error fetching AniList data: {e}")
            return []

    async def fetch_anime(self):
        """Async fetch anime list from AniList with timeout and basic error handling."""
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            self.logger.info("Fetching anime list from AniList")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(ANILIST_URL, json={"query": anime_query}) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"AniList returned status {resp.status} (anime)")
                        return []
                    data = await resp.json()
                    media = data.get("data", {}).get("Page", {}).get("media", [])
                    self.logger.info(f"AniList returned {len(media)} anime entries")
                    return media
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.exception(f"Error fetching AniList anime data: {e}")
            return []

    async def load_previous(self):
        """Load previous saved manga IDs from database."""
        result = await get_scanned_media('MANGA')
        try:
            self.logger.debug(f"Loaded {len(result)} previous manga ids from database")
        except Exception:
            self.logger.debug("Loaded previous manga ids from database")
        return result

    async def load_previous_anime(self):
        """Load previous saved anime IDs from database."""
        result = await get_scanned_media('ANIME')
        try:
            self.logger.debug(f"Loaded {len(result)} previous anime ids from database")
        except Exception:
            self.logger.debug("Loaded previous anime ids from database")
        return result

    async def save_current(self, data):
        """Save current manga IDs to database."""
        media_ids = [m.get("id") for m in data]
        await save_scanned_media_batch(media_ids, 'MANGA')
        try:
            self.logger.info(f"Saved {len(data)} current manga ids to database")
        except Exception:
            self.logger.info("Saved current manga ids to database")

    def filter_new_manga(self, manga_list, prev_ids):
        """Filter list: exclude one-shots, short series, and prefer newly finished today or not seen before."""
        # Use 'yesterday' so the command posts updates about items that finished the previous day
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        try:
            self.logger.debug(f"Filtering {len(manga_list)} manga entries against {len(prev_ids)} previous ids")
        except Exception:
            self.logger.debug("Filtering manga entries")
        new_manga = []
        for m in manga_list:
            try:
                if m.get("format") == "ONE_SHOT":
                    continue
                chapters = m.get("chapters") or 0
                if chapters < 40:
                    continue
                mid = m.get("id")
                # Add if unseen
                if mid not in prev_ids:
                    new_manga.append(m)
                    continue
                # Also add if ended today (guard missing endDate)
                end = m.get("endDate") or {}
                if all(k in end and isinstance(end[k], int) for k in ("year", "month", "day")):
                    # Check if item ended yesterday (not today)
                    if (end["year"], end["month"], end["day"]) == (yesterday.year, yesterday.month, yesterday.day):
                        new_manga.append(m)
            except Exception:
                # Don't let one bad entry break the loop
                self.logger.exception("Error filtering manga entry")
                continue
        return new_manga

    def filter_new_anime(self, anime_list, prev_ids):
        """Similar filtering for anime, excluding short series by episode count."""
        # Use 'yesterday' so the command posts updates about items that finished the previous day
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        new_items = []
        for m in anime_list:
            try:
                if m.get("format") == "OVA":
                    continue
                eps = m.get("episodes") or 0
                if eps < 8:
                    continue
                mid = m.get("id")
                # Determine end date presence
                end = m.get("endDate") or {}
                has_end = all(k in end and isinstance(end[k], int) for k in ("year", "month", "day"))

                # Include anime that ended yesterday (not today); skip ones that ended earlier
                if has_end:
                    if (end["year"], end["month"], end["day"]) == (yesterday.year, yesterday.month, yesterday.day):
                        new_items.append(m)
                    else:
                        # Ended prior to yesterday — don't include
                        continue
                else:
                    # Ongoing/unknown end date: only add if unseen
                    if mid not in prev_ids:
                        new_items.append(m)
                        continue
            except Exception:
                self.logger.exception("Error filtering anime entry")
                continue
        return new_items

    # === Channel configuration persistence ===
    async def load_defined_channel(self, guild_id: int):
        """Return configured channel_id for a specific guild (or None)."""
        try:
            result = await get_guild_manga_channel(guild_id)
            if result:
                self.logger.info(f"Loaded configured channel {result} for guild {guild_id}")
            else:
                self.logger.info(f"No configured channel for guild {guild_id}")
            return result
        except Exception as e:
            self.logger.error(f"Error loading defined channel for guild {guild_id}: {e}")
            return None

    async def save_current_anime(self, data):
        """Save current anime IDs to database."""
        media_ids = [m.get("id") for m in data]
        await save_scanned_media_batch(media_ids, 'ANIME')
        try:
            self.logger.info(f"Saved {len(data)} current anime ids to database")
        except Exception:
            self.logger.info("Saved current anime ids to database")

    async def load_all_defined_channels(self) -> dict:
        """Return the full mapping of guild_id -> channel_id or empty dict."""
        try:
            result = await get_all_guild_manga_channels()
            self.logger.info(f"Loaded channel mapping for {len(result)} guild(s)")
            return result
        except Exception as e:
            self.logger.error(f"Error loading all defined channels: {e}")
            return {}

    async def save_defined_channel(self, guild_id: int, channel_id: int):
        """Persist a guild -> channel mapping to database."""
        try:
            await set_guild_manga_channel(guild_id, channel_id)
            self.logger.info(f"Saved configured channel {channel_id} for guild {guild_id} to database")
        except Exception as e:
            self.logger.error(f"Error saving defined channel for guild {guild_id}: {e}")
            raise

    # === Last-run persistence (to ensure runs are once-per-24h) ===
    async def load_last_run(self) -> datetime.datetime | None:
        """Return the last run datetime from database or None."""
        try:
            metadata = await get_scan_metadata('manga')
            if metadata and metadata.get('last_run'):
                return datetime.datetime.fromisoformat(metadata['last_run'])
            return None
        except Exception:
            return None

    async def save_last_run(self, dt: datetime.datetime):
        """Persist the last run datetime to database."""
        await set_scan_metadata('manga', dt.isoformat())
        try:
            self.logger.info(f"Saved last run timestamp {dt.isoformat()} to database")
        except Exception:
            self.logger.debug("Saved last run timestamp to database")

    async def _user_is_mod(self, interaction: discord.Interaction) -> bool:
        """Return True if the invoking user should be considered a moderator.

        Uses the guild-specific mod role from database with permission fallback.
        """
        try:
            if interaction.guild is None:
                return False

            member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(interaction.user.id)
            return await is_user_moderator(member, interaction.guild.id)

        except Exception:
            self.logger.exception("Failed to determine mod permissions")
        return False

    # === Admin commands to configure channel ===
    @mod_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_animanga_completion_channel", description="Set channel to receive anime/manga updates (Mod only)")
    async def set_animanga_completion_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return
        self.logger.info(f"/set_animanga_completion_channel invoked by {interaction.user} in guild {interaction.guild.id} -> channel {channel.id}")
        # Permission check
        if not await self._user_is_mod(interaction):
            await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # Check bot can send messages in channel
            bot_member = interaction.guild.me
            perms = channel.permissions_for(bot_member) if bot_member else None
            if perms and not perms.send_messages:
                await interaction.followup.send("I don't have permission to send messages in that channel.", ephemeral=True)
                return

            await self.save_defined_channel(interaction.guild.id, channel.id)
            self.logger.info(f"Configured manga updates for guild {interaction.guild.id} -> channel {channel.id}")
            await interaction.followup.send(f"✅ Manga updates will be sent to {channel.mention}", ephemeral=True)
        except Exception:
            self.logger.exception("Failed to set manga channel")
            try:
                await interaction.followup.send("❌ Failed to set channel.", ephemeral=True)
            except Exception:
                pass

    @mod_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="show_manga_channel", description="Show currently configured manga update channel (Mod only)")
    async def show_manga_channel(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return
        # Permission check
        if not await self._user_is_mod(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return
        self.logger.info(f"/show_manga_channel invoked by {interaction.user} in guild {interaction.guild.id}")
        cid = await self.load_defined_channel(interaction.guild.id)
        if cid:
            ch = self.bot.get_channel(cid)
            if ch:
                await interaction.response.send_message(f"Current manga updates channel: {ch.mention}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Configured channel id {cid} is not visible to the bot.", ephemeral=True)
        else:
            await interaction.response.send_message("No channel configured for this server.", ephemeral=True)

    async def post_updates(self, channel, kind: str = "manga") -> int:
        """Post updates of a given kind ('manga' or 'anime') to a channel. Returns number posted."""
        if channel is None:
            self.logger.warning("post_updates called with None channel")
            return 0

        self.logger.info(f"Posting {kind} updates to channel {getattr(channel, 'name', getattr(channel, 'id', 'unknown'))}")
        if kind == "anime":
            prev_ids = await self.load_previous_anime()
            items = await self.fetch_anime()
            new_items = self.filter_new_anime(items, prev_ids)
        else:
            prev_ids = await self.load_previous()
            items = await self.fetch_manga()
            new_items = self.filter_new_manga(items, prev_ids)

        self.logger.info(f"Found {len(new_items)} new {kind} updates after filtering")

        if not new_items:
            await channel.send(f"📭 No new {kind} updates today!")
            # Still update saved state to prevent repeated alerts for the same list
            if kind == "anime":
                await self.save_current_anime(items)
            else:
                await self.save_current(items)
            # Wait a short time to avoid hitting rate limits when called in loops
            try:
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            return 0

        for m in new_items:
            title = (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or "Unknown Title"
            self.logger.info(f"Posting update for {kind} id={m.get('id')} title={title} status={m.get('status')}")
            end = m.get("endDate") or {}
            end_date = f"{end.get('day','?')}/{end.get('month','?')}/{end.get('year','?')}"
            # Build embed similar to browse.py: title, thumbnail, key fields, footer
            emoji = "✅" if m.get("status") == "FINISHED" else "❌"
            # Short description - use a small summary if available; otherwise leave blank
            desc = (m.get("description") or "").strip() if m.get("description") else ""

            # prefer a colored embed but keep status color for visibility
            color = 0x00FF00 if m.get("status") == "FINISHED" else 0xFF0000

            embed = discord.Embed(
                title=f"{emoji} {title}",
                url=m.get("siteUrl"),
                description=(desc[:400] + "...") if desc and len(desc) > 400 else desc,
                color=color
            )

            # thumbnail (cover)
            cover_url = (m.get("coverImage") or {}).get("medium") or (m.get("coverImage") or {}).get("large")
            if cover_url:
                embed.set_thumbnail(url=cover_url)

            # Add a couple of structured fields similar to browse.py
            embed.add_field(name="📌 Status", value=m.get("status", "Unknown"), inline=True)
            if kind == "anime":
                embed.add_field(name="📺 Episodes", value=str(m.get("episodes", "?")), inline=True)
            else:
                embed.add_field(name="📖 Chapters", value=str(m.get("chapters", "?")), inline=True)

            # Average score and genres
            avg = m.get("averageScore")
            if avg is not None:
                embed.add_field(name="⭐ Average Score", value=f"{avg}%", inline=True)

            genres = m.get("genres") or []
            if genres:
                embed.add_field(name="🎭 Genres", value=", ".join(genres[:6])[:1000], inline=False)

            # End date / published info
            embed.add_field(name="📅 End Date", value=end_date, inline=False)

            embed.set_footer(text="Fetched from AniList")

            # Add a simple link button to AniList entry
            try:
                view = View(timeout=None)
                btn = Button(label="View on AniList", url=m.get("siteUrl"))
                view.add_item(btn)
            except Exception:
                view = None

            if view:
                await channel.send(embed=embed, view=view)
            else:
                await channel.send(embed=embed)
            self.logger.debug(f"Sent embed for {kind} {m.get('id')} to channel {getattr(channel,'id',None)}")
            # small delay between sends to avoid rate limiting
            try:
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

        # after sending all new updates, persist the latest fetched list
        if kind == "anime":
            await self.save_current_anime(items)
        else:
            await self.save_current(items)

        try:
            self.logger.info(f"Post {kind} updates complete and state saved")
        except Exception:
            self.logger.debug(f"Post {kind} updates complete (unable to log details)")

        return len(new_items)

    # === Daily Scheduled Task ===
    # Run once per day at 23:50 (11:50 PM) server local time
    @tasks.loop(time=datetime.time(hour=23, minute=50))
    async def daily_check(self):
        # Enforce an at-most-once-per-24-hour run using a persisted timestamp.
        now = datetime.datetime.utcnow()
        try:
            last_run = await self.load_last_run()
        except Exception:
            last_run = None

        should_run = False
        if last_run is None:
            should_run = True
        else:
            elapsed = now - last_run
            if elapsed.total_seconds() >= 24 * 3600:
                should_run = True

        if not should_run:
            self.logger.debug("Skipping daily_check; last run was within 24 hours")
            return

        self.logger.info("Running daily_check scheduled task (23:50 daily)")
        # Load mapping and post to each configured guild channel
        try:
            mapping = await self.load_all_defined_channels()
            if mapping:
                for gid, cid in mapping.items():
                    try:
                        channel = self.bot.get_channel(cid) if cid else None
                        if channel:
                            await self.post_updates(channel, kind="manga")
                            await self.post_updates(channel, kind="anime")
                        else:
                            self.logger.warning(f"Configured channel {cid} for guild {gid} not visible to bot")
                    except Exception:
                        self.logger.exception(f"Failed to post updates for guild {gid}")
            else:
                # No per-guild mapping; try global fallback once
                channel = self.bot.get_channel(CHANNEL_ID)
                if channel:
                    await self.post_updates(channel, kind="manga")
                    await self.post_updates(channel, kind="anime")
                else:
                    self.logger.warning("No configured channels found and global CHANNEL_ID not available to bot")
        except Exception:
            self.logger.exception("Failed to load configured channels for daily_check")

        # Persist the run timestamp so we don't run again for 24h
        try:
            await self.save_last_run(now)
        except Exception:
            self.logger.exception("Failed to save last run timestamp after daily_check (manga)")
        try:
            # persist anime last run separately
            await set_scan_metadata('anime', now.isoformat())
        except Exception:
            self.logger.exception("Failed to save last run timestamp after daily_check (anime)")

    @daily_check.before_loop
    async def before_check(self):
        # Attempt a bounded wait for the client to become ready. In some start
        # scenarios calling wait_until_ready() may raise RuntimeError or block
        # indefinitely; use asyncio.wait_for to bound the wait and fall back to
        # a short polling loop if necessary.
        try:
            await asyncio.wait_for(self.bot.wait_until_ready(), timeout=30)
            self.logger.debug("Bot ready state achieved via wait_until_ready()")
            return
        except asyncio.TimeoutError:
            self.logger.debug("bot.wait_until_ready() timed out after 30s; falling back to polling for readiness")
        except RuntimeError:
            # This can happen if wait_until_ready() is called from an unexpected
            # context depending on how the bot was started. Fall back to polling.
            self.logger.debug("bot.wait_until_ready() raised RuntimeError; falling back to polling for readiness")
        except Exception as e:
            # Any other unexpected error — log and fall back to polling.
            self.logger.debug(f"Unexpected error while waiting for bot readiness ({e}); falling back to polling")

        # Poll for readiness for a shorter period (up to ~30 seconds)
        for i in range(30):
            try:
                if getattr(self.bot, 'is_ready', lambda: False)():
                    self.logger.debug(f"Bot ready state achieved via polling (attempt {i+1})")
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
        self.logger.warning("AnimangaCompletion.before_check: bot did not become ready after 30s polling; continuing anyway")

    # === Slash Command for Mods Only ===
    @mod_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="forceupdate", description="Force a manga completion update (Mod Only)")
    async def forceupdate(self, interaction: discord.Interaction):
        # Use defer to acknowledge interaction and update progress via edit_original_response
        # Permission check
        if not await self._user_is_mod(interaction):
            await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.edit_original_response(content="⏳ (1) **Starting Update** → `[0%]` Preparing request to AniList...")

            # Step 2: Fetch Data
            manga_list = await self.fetch_manga()
            await interaction.edit_original_response(content=f"📡 (2) **Fetching Data** → `[25%]` Retrieved **{len(manga_list)}** manga entries from AniList.")

            # Step 3: Load Previous
            prev_ids = await self.load_previous()
            await interaction.edit_original_response(content=f"🗂 (3) **Comparing Data** → `[50%]` Found **{len(prev_ids)}** previously tracked manga.")

            # Step 4: Filter
            new_manga = self.filter_new_manga(manga_list, prev_ids)
            await interaction.edit_original_response(content=f"⚖️ (4) **Filtering Results** → `[75%]` After filtering ➝ **{len(new_manga)}** new manga updates.")

            # Step 5: Post Updates (prefer configured channel)
            cid = await self.load_defined_channel(interaction.guild.id)
            channel = self.bot.get_channel(cid) if cid else self.bot.get_channel(CHANNEL_ID)
            # Run both manga and anime manual updates
            await self.post_updates(channel, kind="manga")
            await self.post_updates(channel, kind="anime")

            # Record that we just ran a manual/forced update (manga + anime)
            try:
                await self.save_last_run(datetime.datetime.utcnow())
            except Exception:
                self.logger.exception("Failed to persist last_run after forceupdate (manga)")
            try:
                await set_scan_metadata('anime', datetime.datetime.utcnow().isoformat())
            except Exception:
                self.logger.exception("Failed to persist last_run after forceupdate (anime)")

            if new_manga:
                target = channel.mention if channel else f"<#{CHANNEL_ID}>"
                await interaction.edit_original_response(content=f"✅ (5) **Completed!** → `[100%]` Successfully posted **{len(new_manga)}** manga updates to {target} 🎉")
            else:
                await interaction.edit_original_response(content=f"📭 (5) **Completed!** → `[100%]` No new manga updates to post today.")

            await interaction.followup.send("✅ Update posted!", ephemeral=True)

        except Exception as e:
            self.logger.exception("Error running forceupdate command")
            # Try to inform the user if possible
            try:
                await interaction.followup.send("❌ An error occurred while running the update.", ephemeral=True)
            except Exception:
                pass
            raise


    @forceupdate.error
    async def forceupdate_error(self, interaction: discord.Interaction, error):
        # Check for permission errors from app_commands checks
        from discord import app_commands as _app
        if isinstance(error, (_app.MissingRole, _app.MissingPermissions, _app.CheckFailure)):
            try:
                await interaction.response.send_message("❌ You don’t have permission to use this command.", ephemeral=True)
            except Exception:
                # If response already sent, try followup
                try:
                    await interaction.followup.send("❌ You don’t have permission to use this command.", ephemeral=True)
                except Exception:
                    pass
        else:
            raise error

async def setup(bot):
    cog = Finisher(bot)
    await bot.add_cog(cog)
    # The Finisher cog will start its scheduled task in its cog_load method.

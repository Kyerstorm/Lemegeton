
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
import traceback
import shutil
import os
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# local helpers
import helpers.anilist_helper as anilist_helper
from cache_helper import load_json_cache, save_json_cache, is_json_cache_valid, get_cache_file_path
from database import execute_db_operation

# Config fallback
try:
    import config
    DB_PATH = Path(config.DB_PATH)
except Exception:
    DB_PATH = Path("data/bot_database.db")

# Constants & UI config
COG_AUTHOR = "Vireon"
LOGS_DIR = Path("logs")
BACKUP_DIR = Path("data/backups")
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours for AniList cache
PER_PAGE = 8
ADD_SESSION_TIMEOUT = 90.0  # seconds waiting for paste batch
CONFIRM_TIMEOUT = 30.0
MORE_PROMPT_TIMEOUT = 30.0
MESSAGE_DELETE_SAFE = True  # attempt deletes but ignore Forbidden

# Ensure directories
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
Path("data").mkdir(parents=True, exist_ok=True)

# Logger for this cog
logger = logging.getLogger("LoliList")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOGS_DIR / "loli_list.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


# -------------------------
# Helper functions (DB)
# -------------------------
async def ensure_loli_tables():
    """Create loli_list and loli_audit tables if missing and add indexes/constraints."""
    # loli_list: unique constraint on (guild_id, anilist_id)
    create_query = """
    CREATE TABLE IF NOT EXISTS loli_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        added_by INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        anilist_id INTEGER,
        anilist_username TEXT NOT NULL,
        anilist_url TEXT NOT NULL,
        avatar_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    await execute_db_operation("create loli_list table", create_query)

    # add unique index if not present (safe with try/except)
    try:
        await execute_db_operation("add unique index", "CREATE UNIQUE INDEX IF NOT EXISTS idx_loli_guild_anilist ON loli_list(guild_id, anilist_id)")
    except Exception as e:
        logger.debug(f"ignore index create error: {e}")

    # audit table
    create_audit = """
    CREATE TABLE IF NOT EXISTS loli_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mod_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        batch_size INTEGER NOT NULL,
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """
    await execute_db_operation("create loli_audit table", create_audit)

    # index on created_at for loli_list for fast stats queries
    try:
        await execute_db_operation("create index created_at", "CREATE INDEX IF NOT EXISTS idx_loli_created_at ON loli_list(created_at)")
    except Exception:
        pass


async def log_audit(mod_id: int, guild_id: int, action: str, batch_size: int, details: Optional[str] = None):
    try:
        await execute_db_operation(
            "insert audit",
            "INSERT INTO loli_audit (mod_id, guild_id, action, batch_size, details) VALUES (?, ?, ?, ?, ?)",
            (mod_id, guild_id, action, batch_size, details)
        )
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# -------------------------
# Helper functions (cache)
# -------------------------
def get_anilist_cache_key(username_or_id: str) -> str:
    return f"anilist_user_{username_or_id}"


def load_anilist_cache(username_or_id: str) -> Optional[Dict[str, Any]]:
    key = get_anilist_cache_key(username_or_id)
    if is_json_cache_valid(key, CACHE_TTL_SECONDS):
        return load_json_cache(key)
    return None


def save_anilist_cache(username_or_id: str, data: Dict[str, Any]) -> bool:
    key = get_anilist_cache_key(username_or_id)
    return save_json_cache(key, data)


# -------------------------
# Utility helpers
# -------------------------
ANILIST_PROFILE_REGEX = re.compile(r"(?:https?://)?anilist\.co/(?:user|u)/(?:@?)(?P<username>[\w\-\._]+)", re.IGNORECASE)


def extract_username_from_link(link: str) -> Optional[str]:
    """Extract AniList username from common profile links or return None."""
    if not link:
        return None
    m = ANILIST_PROFILE_REGEX.search(link.strip())
    if m:
        return m.group("username")
    # also support bare usernames/ids
    if "/" not in link and " " not in link:
        return link.strip()
    return None


async def safe_delete_message(msg: discord.Message):
    try:
        await msg.delete()
    except Exception:
        pass


# -------------------------
# UI Views
# -------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, timeout: float = CONFIRM_TIMEOUT):
        super().__init__(timeout=timeout)
        self.confirmed: bool = False
        self.cancelled: bool = False

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.edit_message(content=None, embed=discord.Embed(description="Confirmed.", color=discord.Color.green()), view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cancelled = True
        await interaction.response.edit_message(content=None, embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)
        self.stop()


class MorePromptView(discord.ui.View):
    """Buttons for 'Add more' round control."""
    def __init__(self, timeout: float = MORE_PROMPT_TIMEOUT):
        super().__init__(timeout=timeout)
        self.add_more: bool = False
        self.finish: bool = False

    @discord.ui.button(label="➕ Add more", style=discord.ButtonStyle.blurple)
    async def add_more_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.add_more = True
        await interaction.response.edit_message(embed=discord.Embed(description="You chose to add more. Please paste links in chat when prompted.", color=discord.Color.blue()), view=None)
        self.stop()

    @discord.ui.button(label="✅ Finish", style=discord.ButtonStyle.gray)
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finish = True
        await interaction.response.edit_message(embed=discord.Embed(description="Finished adding.", color=discord.Color.green()), view=None)
        self.stop()


class PaginationView(discord.ui.View):
    def __init__(self, pages: List[List[Tuple]], current: int, make_embed_func, warning_text: str):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = current
        self.make_embed_func = make_embed_func
        self.warning_text = warning_text
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.gray)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current > 0:
            self.current -= 1
            embed = await self.make_embed_func(self.pages[self.current], self.current + 1, len(self.pages))
            # Send embed edit while keeping banner text
            await interaction.response.edit_message(content=self.warning_text, embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current < len(self.pages) - 1:
            self.current += 1
            embed = await self.make_embed_func(self.pages[self.current], self.current + 1, len(self.pages))
            await interaction.response.edit_message(content=self.warning_text, embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# -------------------------
# Core Cog
# -------------------------
class LoliList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.per_page = PER_PAGE
        self._active_sessions: Dict[int, bool] = {}  # mod_id -> bool to prevent parallel sessions per mod
        ensure_task = asyncio.create_task(ensure_loli_tables())
        ensure_task.add_done_callback(lambda t: logger.info("LoliList DB tables ensured."))
        self.autobackup_task.start()

    def cog_unload(self):
        self.autobackup_task.cancel()

    # -------------------------
    # BACKUP TASK (every 24 hours)
    # -------------------------
    @tasks.loop(hours=24)
    async def autobackup_task(self):
        try:
            await self._create_backup()
            logger.info("Auto backup created.")
        except Exception as e:
            logger.error(f"Auto backup error: {e}")

    @autobackup_task.before_loop
    async def before_autobackup(self):
        await self.bot.wait_until_ready()

    async def _create_backup(self):
        """Copy main DB file to data/backups with timestamp."""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            src = DB_PATH if isinstance(DB_PATH, Path) else Path(DB_PATH)
            if not src.exists():
                logger.warning("Source DB path does not exist for backup.")
                return None
            dest = BACKUP_DIR / f"{src.stem}_backup_{timestamp}.db"
            shutil.copy2(src, dest)
            logger.info(f"Backup created: {dest}")
            return str(dest)
        except Exception as e:
            logger.error(f"Failed to create DB backup: {e}")
            return None

    # -------------------------
    # Helper: moderator check
    # -------------------------
    async def _is_moderator(self, discord_id: int, guild_id: int) -> bool:
        try:
            res = await execute_db_operation(
                "check moderator",
                "SELECT discord_id FROM bot_is_moderator WHERE discord_id = ? AND guild_id = ?",
                (discord_id, guild_id),
                fetch_type="one"
            )
            return bool(res)
        except Exception as e:
            logger.error(f"Moderator check failed: {e}")
            return False

    # -------------------------
    # Prefix command: loliadd
    # -------------------------
    @commands.command(name="loliadd")
    async def loliadd(self, ctx: commands.Context, link: str):
        """
        Moderator-only prefix command.
        Interactive multi-link + multi-round flow.
        """
        try:
            # Try to delete invoking message
            try:
                await ctx.message.delete()
            except Exception:
                pass

            guild_id = getattr(ctx.guild, "id", None)
            author_id = ctx.author.id

            if not await self._is_moderator(author_id, guild_id):
                # silent skip
                logger.info(f"Non-mod attempted loliadd: {ctx.author} ({author_id}) - ignored.")
                return

            # Session lock: prevent multiple concurrent sessions per moderator
            if self._active_sessions.get(author_id):
                # respond ephemeral-style
                try:
                    await ctx.send("You already have an active add session. Finish it first.", ephemeral=True)
                except Exception:
                    pass
                return
            self._active_sessions[author_id] = True

            # Confirm first link using ephemeral confirm view
            confirm_view = ConfirmView(timeout=CONFIRM_TIMEOUT)
            try:
                # ephemeral argument is available for interactions; many bots accept it via ctx.send
                await ctx.send(embed=discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** to the list?", color=discord.Color.from_rgb(200, 225, 255)), view=confirm_view, ephemeral=True)
            except Exception:
                # fallback: DM if ephemeral not supported
                try:
                    dm = await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** to the list?", color=discord.Color.from_rgb(200, 225, 255)), view=confirm_view)
                except Exception:
                    logger.warning("Could not send ephemeral or DM confirmation.")
                    self._active_sessions.pop(author_id, None)
                    return

            await confirm_view.wait()

            if not confirm_view.confirmed:
                # user cancelled or timed out
                try:
                    await ctx.send(embed=discord.Embed(description="❌ Cancelled.", color=discord.Color.red()), ephemeral=True)
                except Exception:
                    pass
                self._active_sessions.pop(author_id, None)
                return

            # Process the first link (sync process for user feedback)
            added, skipped, failed = await self._process_links_batch([link], ctx, author_id, guild_id, silent=False)

            # Ask if they want more: use buttons (preferred) then fallback to typed reply
            more_loop = True
            total_added = added
            while more_loop:
                more_view = MorePromptView(timeout=MORE_PROMPT_TIMEOUT)
                try:
                    await ctx.send(embed=discord.Embed(title="➕ Add More?", description="Would you like to add more AniList links? Choose an option.", color=discord.Color.blurple()), view=more_view, ephemeral=True)
                except Exception:
                    # fallback to DM
                    try:
                        await ctx.author.send(embed=discord.Embed(title="➕ Add More?", description="Would you like to add more AniList links? Choose an option.", color=discord.Color.blurple()), view=more_view)
                    except Exception:
                        logger.warning("No ephemeral or DM for more prompt.")
                        break

                await more_view.wait()

                if more_view.finish:
                    more_loop = False
                    break

                if more_view.add_more:
                    # Prompt the moderator to paste links in chat (they will be deleted)
                    try:
                        await ctx.send(embed=discord.Embed(description="Paste all additional AniList links (space or newline separated). You have 90s.", color=discord.Color.yellow()), ephemeral=True)
                    except Exception:
                        try:
                            await ctx.author.send(embed=discord.Embed(description="Paste all additional AniList links (space or newline separated). You have 90s.", color=discord.Color.yellow()))
                        except Exception:
                            logger.warning("Cannot prompt for paste.")
                            break

                    def check_msg(m: discord.Message):
                        return m.author.id == author_id and (m.channel == ctx.channel)

                    try:
                        pasted_msg: discord.Message = await self.bot.wait_for("message", check=check_msg, timeout=ADD_SESSION_TIMEOUT)
                        # capture content then delete message
                        content = pasted_msg.content
                        try:
                            await pasted_msg.delete()
                        except Exception:
                            pass

                        # parse links
                        raw_links = [l.strip() for l in re.split(r"[\s,]+", content) if l.strip()]
                        if not raw_links:
                            await ctx.send(embed=discord.Embed(description="No valid links found in paste.", color=discord.Color.orange()), ephemeral=True)
                            continue

                        added2, skipped2, failed2 = await self._process_links_batch(raw_links, ctx, author_id, guild_id, silent=False)
                        total_added += added2

                        # summary message
                        await ctx.send(embed=discord.Embed(description=f"Batch complete — Added: {added2}, Skipped(dup/invalid): {skipped2}, Failed: {failed2}", color=discord.Color.green()), ephemeral=True)

                        # continue loop
                        continue

                    except asyncio.TimeoutError:
                        await ctx.send(embed=discord.Embed(description="⏰ Timeout waiting for pasted links. Ending add session.", color=discord.Color.orange()), ephemeral=True)
                        more_loop = False
                        break

                else:
                    # neither add_more nor finish (timeout or closed)
                    more_loop = False
                    break

            # final audit log & backup
            await log_audit(author_id, guild_id, "add", total_added, f"initial={link}")
            try:
                await self._create_backup()
            except Exception as e:
                logger.debug(f"Backup on add finished failed: {e}")

            # final message
            try:
                await ctx.send(embed=discord.Embed(description=f"Finished. Total added this session: {total_added}", color=discord.Color.green()), ephemeral=True)
            except Exception:
                pass

            self._active_sessions.pop(author_id, None)

        except Exception as e:
            logger.error(f"Unexpected error in loliadd: {e}\n{traceback.format_exc()}")
            try:
                await ctx.send(embed=discord.Embed(description="❌ Internal error occurred (logged).", color=discord.Color.red()), ephemeral=True)
            except Exception:
                pass
            self._active_sessions.pop(author_id, None)

    async def _process_links_batch(self, links: List[str], ctx: commands.Context, mod_id: int, guild_id: int, silent: bool = False) -> Tuple[int, int, int]:
        """
        Validate and insert a list of links. Returns (added_count, skipped_count, failed_count).
        Skipped = duplicates or invalid link formats
        """
        added = 0
        skipped = 0
        failed = 0

        # Normalize and remove obvious duplicates in input
        unique_links = []
        seen = set()
        for l in links:
            if not l:
                continue
            username = extract_username_from_link(l) or l.strip()
            if username.lower() in seen:
                continue
            seen.add(username.lower())
            unique_links.append((l, username))

        # Prepare async fetching tasks for efficiency
        tasks = []
        for raw, username in unique_links:
            # check cache first
            cached = load_anilist_cache(username)
            if cached:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=(raw, username, cached))))
            else:
                tasks.append(asyncio.create_task(self._fetch_anilist_user_task(raw, username)))

        # walkway: iterate results as they complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            # res is (raw_link, username, user_info_dict) or exception
            if isinstance(res, Exception):
                logger.error(f"Error fetching a link during batch: {res}")
                failed += 1
                continue

            raw_link, username, user_info = res
            # Validate user_info presence
            if not user_info:
                skipped += 1
                if not silent:
                    await ctx.send(embed=discord.Embed(description=f"❌ Invalid AniList user or not found: `{raw_link}`", color=discord.Color.red()), ephemeral=True)
                continue

            # Check duplicates in DB for this guild
            anilist_id = user_info.get("id")
            try:
                existing = await execute_db_operation(
                    "check duplicate",
                    "SELECT id FROM loli_list WHERE guild_id = ? AND anilist_id = ?",
                    (guild_id, anilist_id),
                    fetch_type="one"
                )
            except Exception as e:
                logger.error(f"DB error checking duplicate: {e}")
                existing = None

            if existing:
                skipped += 1
                if not silent:
                    await ctx.send(embed=discord.Embed(description=f"⚠️ Already listed (skipped): {user_info.get('name') or username}", color=discord.Color.orange()), ephemeral=True)
                continue

            # Insert into DB
            try:
                await execute_db_operation(
                    "insert loli",
                    "INSERT INTO loli_list (added_by, guild_id, anilist_id, anilist_username, anilist_url, avatar_url) VALUES (?, ?, ?, ?, ?, ?)",
                    (mod_id, guild_id, anilist_id, user_info.get("name") or username, user_info.get("siteUrl") or raw_link, user_info.get("avatar"))
                )
                added += 1
                # save to cache
                save_anilist_cache(username, {"id": anilist_id, "name": user_info.get("name"), "avatar": user_info.get("avatar"), "siteUrl": user_info.get("siteUrl")})
                if not silent:
                    await ctx.send(embed=discord.Embed(description=f"✅ Added **{user_info.get('name') or username}**", color=discord.Color.green()), ephemeral=True)
            except Exception as e:
                failed += 1
                logger.error(f"Failed to insert entry for {username}: {e}")
                if not silent:
                    await ctx.send(embed=discord.Embed(description=f"❌ Failed to add {username} due to DB error.", color=discord.Color.red()), ephemeral=True)
                continue

        return (added, skipped, failed)

    async def _fetch_anilist_user_task(self, raw_link: str, username: str):
        """
        Fetch AniList user info given username (or raw link). Returns (raw_link, username, dict) or raises.
        Uses cache_helper and anilist_helper.
        """
        try:
            # Try numeric id fetch path first if username is numeric
            user_info = None
            # Use AniList helper fetch_user_stats for comprehensive details
            try:
                stats = await anilist_helper.fetch_user_stats(username)
                if stats and "User" in stats:
                    node = stats["User"]
                    user_info = {
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "avatar": node.get("avatar", {}).get("large") if node.get("avatar") else None,
                        "siteUrl": node.get("siteUrl")
                    }
            except Exception:
                user_info = None

            return (raw_link, username, user_info)
        except Exception as e:
            logger.error(f"Fetch task failed for {username}: {e}")
            return (raw_link, username, None)

    # -------------------------
    # Prefix command: loli delete
    # -------------------------
    @commands.command(name="loli")
    async def loli_prefix_group(self, ctx: commands.Context, subcommand: str = None, *, rest: str = None):
        """
        Support prefix usage: !loli delete <link|username|id>
        (We implement only delete subcommand here.)
        """
        if subcommand != "delete":
            return  # silent skip for other usages
        await self._handle_delete_prefix(ctx, rest)

    async def _handle_delete_prefix(self, ctx: commands.Context, target: Optional[str]):
        try:
            # delete command message
            try:
                await ctx.message.delete()
            except Exception:
                pass

            guild_id = getattr(ctx.guild, "id", None)
            author_id = ctx.author.id

            if not await self._is_moderator(author_id, guild_id):
                logger.info(f"Non-mod attempted loli delete: {ctx.author} - ignored.")
                return

            if not target:
                try:
                    await ctx.send("Usage: `!loli delete <anilist link|username|id>`", ephemeral=True)
                except Exception:
                    pass
                return

            # Extract username or id
            username = extract_username_from_link(target) or target.strip()
            # fetch AniList info
            cached = load_anilist_cache(username)
            user_info = None
            if cached:
                user_info = cached
            else:
                try:
                    stats = await anilist_helper.fetch_user_stats(username)
                    if stats and "User" in stats:
                        node = stats["User"]
                        user_info = {"id": node.get("id"), "name": node.get("name"), "siteUrl": node.get("siteUrl")}
                except Exception:
                    user_info = None

            if not user_info:
                await ctx.send(embed=discord.Embed(description=f"❌ AniList user not found: `{target}`", color=discord.Color.red()), ephemeral=True)
                return

            # Check entry exists
            try:
                existing = await execute_db_operation(
                    "find loli entry",
                    "SELECT id, anilist_username FROM loli_list WHERE guild_id = ? AND anilist_id = ?",
                    (guild_id, user_info["id"]),
                    fetch_type="one"
                )
            except Exception as e:
                logger.error(f"DB error finding entry to delete: {e}")
                existing = None

            if not existing:
                await ctx.send(embed=discord.Embed(description=f"❌ Entry not found for {user_info.get('name')}", color=discord.Color.orange()), ephemeral=True)
                return

            # Confirm deletion with ephemeral ConfirmView
            confirm = ConfirmView(timeout=CONFIRM_TIMEOUT)
            try:
                await ctx.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm, ephemeral=True)
            except Exception:
                try:
                    await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                except Exception:
                    logger.warning("Could not send ephemeral confirm for delete.")
                    return

            await confirm.wait()
            if not confirm.confirmed:
                await ctx.send(embed=discord.Embed(description="❌ Cancelled.", color=discord.Color.red()), ephemeral=True)
                return

            # perform delete
            try:
                await execute_db_operation("delete loli entry", "DELETE FROM loli_list WHERE id = ?", (existing[0],))
                await log_audit(author_id, guild_id, "delete", 1, f"deleted {existing[1]}")
                try:
                    await ctx.send(embed=discord.Embed(description=f"✅ Deleted {existing[1]}.", color=discord.Color.green()), ephemeral=True)
                except Exception:
                    pass
                # backup after deletion
                try:
                    await self._create_backup()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"DB delete failed: {e}")
                await ctx.send(embed=discord.Embed(description="❌ Failed to delete entry (DB error).", color=discord.Color.red()), ephemeral=True)

        except Exception as e:
            logger.error(f"Error in delete prefix: {e}\n{traceback.format_exc()}")
            try:
                await ctx.send(embed=discord.Embed(description="❌ Internal error occurred (logged).", color=discord.Color.red()), ephemeral=True)
            except Exception:
                pass

    # -------------------------
    # Slash/hybrid command: lolilist
    # -------------------------
    @commands.hybrid_command(name="lolilist", description="View the Loli leaderboard and stats.")
    async def lolilist(self, ctx: commands.Context):
        """Hybrid so it works as slash and prefix; will try to send ephemeral responses when appropriate."""
        try:
            # always defer to avoid timeouts
            try:
                await ctx.defer()
            except Exception:
                pass

            # fetch stats
            stats = await self._fetch_stats(ctx.guild.id if ctx.guild else None)

            # fetch entries
            try:
                entries = await execute_db_operation(
                    "fetch loli entries",
                    "SELECT anilist_username, anilist_url, avatar_url, created_at FROM loli_list WHERE guild_id = ? ORDER BY created_at DESC",
                    (ctx.guild.id,),
                    fetch_type="all"
                )
            except Exception as e:
                logger.error(f"Failed to fetch entries: {e}")
                entries = []

            total_entries = len(entries)
            if total_entries == 0:
                await ctx.send("❌ No entries found.", ephemeral=True)
                return

            # Build pages
            pages = [entries[i:i + self.per_page] for i in range(0, total_entries, self.per_page)]
            current = 0

            # warning banner (non-embed) repeated on page changes
            warning_text = (
                "⚠️⚠️⚠️ **ABSOLUTELY DO NOT HARASS, CONTACT, TARGET, OR DISCUSS** ANY USERS LISTED BELOW. "
                "THIS LIST IS FOR DISPLAY PURPOSES ONLY. REPORT ANY MISUSE TO STAFF. ⚠️⚠️⚠️\n\n"
            )

            embed = await self._make_leaderboard_embed(pages[current], current + 1, len(pages), stats)
            view = PaginationView(pages, current, self._make_leaderboard_embed, warning_text)
            try:
                sent = await ctx.send(content=warning_text, embed=embed, view=view)
            except Exception:
                # fallback: DM the author with embed & banner
                try:
                    sent = await ctx.author.send(content=warning_text, embed=embed, view=view)
                except Exception:
                    logger.error("Failed to send leaderboard to user.")
                    return
            view.message = sent

        except Exception as e:
            logger.error(f"Error in lolilist: {e}\n{traceback.format_exc()}")
            try:
                await ctx.send("❌ Failed to load leaderboard (internal error).", ephemeral=True)
            except Exception:
                pass

    async def _fetch_stats(self, guild_id: int) -> Dict[str, Any]:
        """Return minimal stats: total_entries, added_today, most_recent_time (for footer)"""
        stats = {"total_entries": 0, "added_today": 0, "most_recent": None}
        try:
            row = await execute_db_operation(
                "stats total",
                "SELECT COUNT(*) FROM loli_list WHERE guild_id = ?",
                (guild_id,),
                fetch_type="one"
            )
            stats["total_entries"] = row[0] if row else 0

            row2 = await execute_db_operation(
                "stats today",
                "SELECT COUNT(*) FROM loli_list WHERE guild_id = ? AND created_at >= DATETIME('now','-1 day')",
                (guild_id,),
                fetch_type="one"
            )
            stats["added_today"] = row2[0] if row2 else 0

            row3 = await execute_db_operation(
                "most recent",
                "SELECT created_at FROM loli_list WHERE guild_id = ? ORDER BY created_at DESC LIMIT 1",
                (guild_id,),
                fetch_type="one"
            )
            if row3 and row3[0]:
                # preserve as string for formatting
                stats["most_recent"] = row3[0]
        except Exception as e:
            logger.error(f"Stats fetch error: {e}")
        return stats

    async def _make_leaderboard_embed(self, page_entries, page_num: int, total_pages: int, stats: Optional[Dict[str, Any]] = None):
        """Build the pastel/white embedded leaderboard page."""
        # pastel white embed
        embed = discord.Embed(title="Loli Leaderboard", color=discord.Color.from_rgb(245, 245, 248))
        # stats header inside embed as a compact block
        if stats:
            stats_text = f"**Total Entries:** {stats.get('total_entries', '?')} • **Added Today:** {stats.get('added_today', '?')}"
            embed.description = stats_text + "\n\n"

        # Build per-user mini "card" fields
        for idx, entry in enumerate(page_entries, start=1):
            name, url, avatar, created_at = entry
            # parse created_at if string
            added_text = created_at if isinstance(created_at, str) else (created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown")
            field_name = f"#{idx} — {name}"
            field_value = f"[Open AniList profile]({url}) • Added `{added_text}`"
            embed.add_field(name=field_name, value=field_value, inline=False)

        # rotating/representative thumbnail: pick first non-empty avatar in page
        thumbnail_url = None
        for e in page_entries:
            if e[2]:
                thumbnail_url = e[2]
                break
        if thumbnail_url:
            try:
                embed.set_thumbnail(url=thumbnail_url)
            except Exception:
                pass

        # footer: page and last updated
        updated = stats.get("most_recent") if stats and stats.get("most_recent") else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        embed.set_footer(text=f"📖 Page {page_num}/{total_pages} • Updated {updated}")

        return embed

    # -------------------------
    # Cog setup helper
    # -------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("LoliList cog ready.")


# -------------------------
# Cog setup for bot
# -------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(LoliList(bot))

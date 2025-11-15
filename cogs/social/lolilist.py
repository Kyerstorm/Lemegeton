import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import logging
import traceback
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# local helpers
from cache_helper import load_json_cache, save_json_cache, is_json_cache_valid
from database import execute_db_operation, is_user_bot_moderator

# config fallback for DB path
try:
    import config
    DB_PATH = Path(config.DB_PATH)
except Exception:
    DB_PATH = Path("data/bot_database.db")

# ---------- Constants ----------
COG_AUTHOR = "Vireon"
LOGS_DIR = Path("logs")
BACKUP_DIR = Path("data/backups")
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours
PER_PAGE = 5
ADD_SESSION_TIMEOUT = 90.0
CONFIRM_TIMEOUT = 30.0
MORE_PROMPT_TIMEOUT = 30.0
AUTO_DELETE_DELAY = 1.5  # seconds for temporary messages
ANILIST_GRAPHQL = "https://graphql.anilist.co"

# Ensure directories
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
Path("data").mkdir(parents=True, exist_ok=True)

# Logger
logger = logging.getLogger("LoliList")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOGS_DIR / "loli_list.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


# ---------- SQL / DB helpers ----------
async def ensure_loli_tables():
    """Create loli_list and loli_audit tables if missing."""
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

    try:
        await execute_db_operation("create unique index", "CREATE UNIQUE INDEX IF NOT EXISTS idx_loli_guild_anilist ON loli_list(guild_id, anilist_id)")
    except Exception:
        pass

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

    try:
        await execute_db_operation("create created_at index", "CREATE INDEX IF NOT EXISTS idx_loli_created_at ON loli_list(created_at)")
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


# ---------- Cache helpers ----------
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


# ---------- Utilities ----------
ANILIST_PROFILE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?anilist\.co/(?:user|u)/(?:@?)(?P<username>[\w\-\._]+|\d+)",
    re.IGNORECASE
)


def extract_username_from_link(link: str) -> Optional[str]:
    """Return bare username or numeric id (as string)."""
    if not link:
        return None
    m = ANILIST_PROFILE_REGEX.search(link.strip())
    if m:
        return m.group("username")
    # raw username or numeric id given
    if "/" not in link and " " not in link:
        return link.strip()
    return None


async def safe_delete_message(msg: discord.Message):
    try:
        await msg.delete()
    except Exception:
        pass


async def send_temp_ctx(ctx: commands.Context, embed: discord.Embed, delay: float = AUTO_DELETE_DELAY):
    """
    Send a temporary in-channel message that auto-deletes after `delay` seconds.
    If channel send fails, fallback to DM (no auto-delete).
    """
    try:
        m = await ctx.send(embed=embed)
        await asyncio.sleep(delay)
        try:
            await m.delete()
        except Exception:
            pass
    except Exception:
        try:
            await ctx.author.send(embed=embed)
        except Exception:
            logger.debug("Failed to send temp message or DM fallback.")


# ---------- AniList GraphQL fetcher ----------
ANILIST_USER_BY_NAME_QUERY = """
query ($name: String) {
  User(name: $name) {
    id
    name
    siteUrl
    avatar {
      large
    }
  }
}
"""

ANILIST_USER_BY_ID_QUERY = """
query ($id: Int) {
  User(id: $id) {
    id
    name
    siteUrl
    avatar {
      large
    }
  }
}
"""


async def fetch_anilist_user_via_graphql(identifier: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """
    identifier: may be numeric id string or username (may include @)
    If numeric -> query by id; else query by name (strip leading @).
    Returns dict {id, name, siteUrl, avatar} or None.
    """
    try:
        # numeric?
        ident = identifier.strip()
        if ident.isdigit():
            variables = {"id": int(ident)}
            payload = {"query": ANILIST_USER_BY_ID_QUERY, "variables": variables}
        else:
            variables = {"name": ident.lstrip("@")}
            payload = {"query": ANILIST_USER_BY_NAME_QUERY, "variables": variables}

        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        async with session.post(ANILIST_GRAPHQL, json=payload, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.debug(f"AniList GraphQL non-200 ({resp.status}): {text}")
                return None
            data = await resp.json()
            if not data:
                return None
            user = data.get("data", {}).get("User")
            if not user:
                return None
            return {
                "id": user.get("id"),
                "name": user.get("name"),
                "siteUrl": user.get("siteUrl"),
                "avatar": user.get("avatar", {}).get("large") if user.get("avatar") else None
            }
    except Exception as e:
        logger.debug(f"AniList GraphQL request failed for {identifier}: {e}")
        return None


# ---------- UI Views ----------
class PaginationView(discord.ui.View):
    """
    Prev [Page X/Y disabled button] Next
    When prev/next not available they are disabled.
    """

    def __init__(self, total_pages: int, current_index: int, make_embeds_func, warning_text: str):
        super().__init__(timeout=120)
        self.total_pages = total_pages
        self.current = current_index  # 0-based
        self.make_embeds_func = make_embeds_func
        self.warning_text = warning_text
        self.message: Optional[discord.Message] = None

        # Buttons are created here; we will update their disabled state on each interaction
        self.prev_button = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.gray)
        self.page_button = discord.ui.Button(label=f"Page {self.current+1}/{self.total_pages}", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_button = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.gray)

        # add to view in order
        self.add_item(self.prev_button)
        self.add_item(self.page_button)
        self.add_item(self.next_button)

        # Wire callbacks dynamically
        self.prev_button.callback = self._prev_callback
        self.next_button.callback = self._next_callback

        self._update_button_states()

    def _update_button_states(self):
        # disable prev if at first page
        self.prev_button.disabled = self.current <= 0
        # disable next if at last page
        self.next_button.disabled = self.current >= (self.total_pages - 1)
        # page button always updated label and disabled
        self.page_button.label = f"Page {self.current+1}/{self.total_pages}"
        self.page_button.disabled = True

    async def _prev_callback(self, interaction: discord.Interaction):
        if self.current <= 0:
            return
        self.current -= 1
        self._update_button_states()
        embeds = await self.make_embeds_func(self.current)
        try:
            await interaction.response.edit_message(content=self.warning_text, embeds=embeds, view=self)
        except Exception:
            try:
                # fallback
                await interaction.message.edit(content=self.warning_text, embeds=embeds, view=self)
            except Exception:
                pass

    async def _next_callback(self, interaction: discord.Interaction):
        if self.current >= (self.total_pages - 1):
            return
        self.current += 1
        self._update_button_states()
        embeds = await self.make_embeds_func(self.current)
        try:
            await interaction.response.edit_message(content=self.warning_text, embeds=embeds, view=self)
        except Exception:
            try:
                await interaction.message.edit(content=self.warning_text, embeds=embeds, view=self)
            except Exception:
                pass

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ---------- Core Cog ----------
class LoliList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.per_page = PER_PAGE
        self._active_sessions: Dict[int, bool] = {}
        ensure_task = asyncio.create_task(ensure_loli_tables())
        ensure_task.add_done_callback(lambda t: logger.info("LoliList DB tables ensured."))
        self.session = aiohttp.ClientSession()
        self.autobackup_task.start()

    def cog_unload(self):
        try:
            asyncio.create_task(self.session.close())
        except Exception:
            pass
        self.autobackup_task.cancel()

    # Auto-backup
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

    # Moderator check
    async def _is_moderator(self, user: discord.User) -> bool:
        try:
            return bool(await is_user_bot_moderator(user))
        except Exception as e:
            logger.error(f"Moderator check failed via is_user_bot_moderator: {e}")
            return False

    # ---------- Prefix command: loliadd ----------
    @commands.command(name="loliadd")
    async def loliadd(self, ctx: commands.Context, link: Optional[str] = None):
        """
        Moderator-only prefix command: interactive multi-link + multi-round flow.
        If 'link' omitted, shows usage temporarily.
        """
        try:
            try:
                await ctx.message.delete()
            except Exception:
                pass

            if not link:
                await send_temp_ctx(ctx, discord.Embed(description="Usage: `!loliadd <AniList profile URL or username>`", color=discord.Color.orange()))
                return

            guild_id = getattr(ctx.guild, "id", None)
            author = ctx.author

            if not await self._is_moderator(author):
                logger.info(f"Non-mod attempted loliadd: {author} - ignored.")
                return

            author_id = author.id

            if self._active_sessions.get(author_id):
                await send_temp_ctx(ctx, discord.Embed(description="You already have an active add session. Finish it first.", color=discord.Color.orange()))
                return
            self._active_sessions[author_id] = True

            # confirm
            confirm_view = discord.ui.View(timeout=CONFIRM_TIMEOUT)
            confirmed_flag = {"ok": False}

            async def _confirm_callback(interaction: discord.Interaction):
                confirmed_flag["ok"] = True
                await interaction.response.edit_message(embed=discord.Embed(description="Confirmed.", color=discord.Color.green()), view=None)

            async def _cancel_callback(interaction: discord.Interaction):
                confirmed_flag["ok"] = False
                await interaction.response.edit_message(embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)

            confirm_view.add_item(discord.ui.Button(label="✅ Confirm", style=discord.ButtonStyle.green, custom_id="confirm_add"))
            confirm_view.add_item(discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.red, custom_id="cancel_add"))

            confirm_view = None
            from types import SimpleNamespace
            confirm_view = SimpleNamespace()
            # Use existing ConfirmView class for clarity:
            confirm_view = discord.ui.View(timeout=CONFIRM_TIMEOUT)
            # Build a simple ConfirmView using the class defined earlier is cleaner, but to avoid duplication, we'll use ConfirmView-like logic:
            class _CF(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=CONFIRM_TIMEOUT)
                    self.confirmed = False

                @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
                async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = True
                    await interaction.response.edit_message(embed=discord.Embed(description="Confirmed.", color=discord.Color.green()), view=None)
                    self.stop()

                @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
                async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = False
                    await interaction.response.edit_message(embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)
                    self.stop()

            confirm_view = _CF()
            try:
                prompt = discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** to the list? Click a button to confirm or cancel.", color=discord.Color.from_rgb(200,225,255))
                prompt_msg = await ctx.send(embed=prompt, view=confirm_view)
                await confirm_view.wait()
                try:
                    await prompt_msg.delete()
                except Exception:
                    pass
            except Exception:
                try:
                    dm = await author.send(embed=discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** to the list? Use the buttons.", color=discord.Color.from_rgb(200,225,255)), view=confirm_view)
                    await confirm_view.wait()
                except Exception:
                    logger.warning("Confirm prompt could not be delivered (channel or DM).")
                    self._active_sessions.pop(author_id, None)
                    return

            if not confirm_view.confirmed:
                await send_temp_ctx(ctx, discord.Embed(description="❌ Cancelled.", color=discord.Color.red()))
                self._active_sessions.pop(author_id, None)
                return

            # process initial link
            added, skipped, failed = await self._process_links_batch([link], ctx, author_id, guild_id, silent=False)
            total_added = added

            # multi-round
            while True:
                more_view = discord.ui.View(timeout=MORE_PROMPT_TIMEOUT)
                class _MV(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=MORE_PROMPT_TIMEOUT)
                        self.add_more = False
                        self.finish = False

                    @discord.ui.button(label="➕ Add more", style=discord.ButtonStyle.blurple)
                    async def add_more_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                        self.add_more = True
                        await interaction.response.edit_message(embed=discord.Embed(description="You chose to add more. Paste links in chat when prompted.", color=discord.Color.blue()), view=None)
                        self.stop()

                    @discord.ui.button(label="✅ Finish", style=discord.ButtonStyle.gray)
                    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                        self.finish = True
                        await interaction.response.edit_message(embed=discord.Embed(description="Finished adding.", color=discord.Color.green()), view=None)
                        self.stop()

                mv = _MV()
                try:
                    prompt_msg = await ctx.send(embed=discord.Embed(title="➕ Add More?", description="Would you like to add more AniList links? Use the buttons.", color=discord.Color.blurple()), view=mv)
                    await mv.wait()
                    try:
                        await prompt_msg.delete()
                    except Exception:
                        pass
                except Exception:
                    try:
                        dm2 = await author.send(embed=discord.Embed(title="➕ Add More?", description="Would you like to add more AniList links? Use the buttons.", color=discord.Color.blurple()), view=mv)
                        await mv.wait()
                    except Exception:
                        logger.warning("Cannot send Add More prompt.")
                        break

                if mv.finish:
                    break

                if mv.add_more:
                    await send_temp_ctx(ctx, discord.Embed(description="Paste all additional AniList profile links (space/newline separated). You have 90s.", color=discord.Color.yellow()))
                    def check_msg(m: discord.Message):
                        return m.author.id == author_id and (m.channel == ctx.channel)
                    try:
                        pasted_msg: discord.Message = await self.bot.wait_for("message", check=check_msg, timeout=ADD_SESSION_TIMEOUT)
                        content = pasted_msg.content
                        try:
                            await pasted_msg.delete()
                        except Exception:
                            pass

                        raw_links = [l.strip() for l in re.split(r"[\s,]+", content) if l.strip()]
                        if not raw_links:
                            await send_temp_ctx(ctx, discord.Embed(description="No valid links found in paste.", color=discord.Color.orange()))
                            continue

                        added2, skipped2, failed2 = await self._process_links_batch(raw_links, ctx, author_id, guild_id, silent=False)
                        total_added += added2
                        await send_temp_ctx(ctx, discord.Embed(description=f"Batch complete — Added: {added2}, Skipped: {skipped2}, Failed: {failed2}", color=discord.Color.green()))
                        continue
                    except asyncio.TimeoutError:
                        await send_temp_ctx(ctx, discord.Embed(description="⏰ Timeout waiting for pasted links. Ending add session.", color=discord.Color.orange()))
                        break
                else:
                    break

            await log_audit(author_id, guild_id, "add", total_added, f"initial={link}")
            try:
                await self._create_backup()
            except Exception:
                pass

            await send_temp_ctx(ctx, discord.Embed(description=f"Finished. Total added this session: {total_added}", color=discord.Color.green()))
            self._active_sessions.pop(author_id, None)

        except Exception as e:
            logger.error(f"Unexpected error in loliadd: {e}\n{traceback.format_exc()}")
            try:
                await send_temp_ctx(ctx, discord.Embed(description="❌ Internal error occurred (logged).", color=discord.Color.red()))
            except Exception:
                pass
            try:
                self._active_sessions.pop(author.id, None)
            except Exception:
                pass

    async def _process_links_batch(self, links: List[str], ctx: commands.Context, mod_id: int, guild_id: int, silent: bool = False) -> Tuple[int, int, int]:
        """
        Validate and insert links. Returns (added_count, skipped_count, failed_count).
        """
        added = 0
        skipped = 0
        failed = 0

        unique_links = []
        seen = set()
        for l in links:
            if not l:
                continue
            username = extract_username_from_link(l) or l.strip()
            key = username.lower()
            if key in seen:
                continue
            seen.add(key)
            unique_links.append((l, username))

        tasks = []
        for raw, username in unique_links:
            cached = load_anilist_cache(username)
            if cached:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=(raw, username, cached))))
            else:
                tasks.append(asyncio.create_task(self._fetch_anilist_user_task(raw, username)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Error fetching a link during batch: {res}")
                failed += 1
                continue

            raw_link, username, user_info = res
            if not user_info:
                skipped += 1
                if not silent:
                    await send_temp_ctx(ctx, discord.Embed(description=f"❌ Invalid AniList user or not found: `{raw_link}`", color=discord.Color.red()))
                continue

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
                    await send_temp_ctx(ctx, discord.Embed(description=f"⚠️ Already listed (skipped): {user_info.get('name') or username}", color=discord.Color.orange()))
                continue

            try:
                await execute_db_operation(
                    "insert loli",
                    "INSERT INTO loli_list (added_by, guild_id, anilist_id, anilist_username, anilist_url, avatar_url) VALUES (?, ?, ?, ?, ?, ?)",
                    (mod_id, guild_id, anilist_id, user_info.get("name") or username, user_info.get("siteUrl") or raw_link, user_info.get("avatar"))
                )
                added += 1
                save_anilist_cache(username, {"id": anilist_id, "name": user_info.get("name"), "avatar": user_info.get("avatar"), "siteUrl": user_info.get("siteUrl")})
                if not silent:
                    await send_temp_ctx(ctx, discord.Embed(description=f"✅ Added **{user_info.get('name') or username}**", color=discord.Color.green()))
            except Exception as e:
                failed += 1
                logger.error(f"Failed to insert entry for {username}: {e}")
                if not silent:
                    await send_temp_ctx(ctx, discord.Embed(description=f"❌ Failed to add {username} due to DB error.", color=discord.Color.red()))
                continue

        return (added, skipped, failed)

    async def _fetch_anilist_user_task(self, raw_link: str, username: str):
        """
        Wrap GraphQL fetch: preserve casing and prefix '@' for non-numeric usernames.
        """
        try:
            api_identifier = username.strip()
            user_info = await fetch_anilist_user_via_graphql(api_identifier, self.session)
            return (raw_link, username, user_info)
        except Exception as e:
            logger.error(f"Fetch task failed for {username}: {e}")
            return (raw_link, username, None)

    # ---------- Prefix group for delete ----------
    @commands.command(name="loli")
    async def loli_prefix_group(self, ctx: commands.Context, subcommand: str = None, *, rest: str = None):
        if subcommand != "delete":
            return
        await self._handle_delete_prefix(ctx, rest)

    async def _handle_delete_prefix(self, ctx: commands.Context, target: Optional[str]):
        try:
            try:
                await ctx.message.delete()
            except Exception:
                pass

            guild_id = getattr(ctx.guild, "id", None)
            author = ctx.author

            if not await self._is_moderator(author):
                logger.info(f"Non-mod attempted loli delete: {author} - ignored.")
                return

            if not target:
                await send_temp_ctx(ctx, discord.Embed(description="Usage: `!loli delete <anilist link|username|id>`", color=discord.Color.orange()))
                return

            username = extract_username_from_link(target) or target.strip()
            cached = load_anilist_cache(username)
            user_info = None
            if cached:
                user_info = cached
            else:
                user_info = await fetch_anilist_user_via_graphql(username, self.session)

            if not user_info:
                await send_temp_ctx(ctx, discord.Embed(description=f"❌ AniList user not found: `{target}`", color=discord.Color.red()))
                return

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
                await send_temp_ctx(ctx, discord.Embed(description=f"❌ Entry not found for {user_info.get('name')}", color=discord.Color.orange()))
                return

            # confirm deletion
            class _DelConfirm(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=CONFIRM_TIMEOUT)
                    self.confirmed = False

                @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
                async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = True
                    await interaction.response.edit_message(embed=discord.Embed(description="Confirmed deletion.", color=discord.Color.green()), view=None)
                    self.stop()

                @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
                async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.confirmed = False
                    await interaction.response.edit_message(embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)
                    self.stop()

            confirm = _DelConfirm()
            try:
                prompt_msg = await ctx.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                await confirm.wait()
                try:
                    await prompt_msg.delete()
                except Exception:
                    pass
            except Exception:
                try:
                    dm = await author.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                    await confirm.wait()
                except Exception:
                    logger.warning("Could not deliver delete confirm prompt.")
                    return

            if not confirm.confirmed:
                await send_temp_ctx(ctx, discord.Embed(description="❌ Cancelled.", color=discord.Color.red()))
                return

            try:
                await execute_db_operation("delete loli entry", "DELETE FROM loli_list WHERE id = ?", (existing[0],))
                await log_audit(author.id, guild_id, "delete", 1, f"deleted {existing[1]}")
                await send_temp_ctx(ctx, discord.Embed(description=f"✅ Deleted {existing[1]}.", color=discord.Color.green()))
                try:
                    await self._create_backup()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"DB delete failed: {e}")
                await send_temp_ctx(ctx, discord.Embed(description="❌ Failed to delete entry (DB error).", color=discord.Color.red()))

        except Exception as e:
            logger.error(f"Error in delete prefix: {e}\n{traceback.format_exc()}")
            try:
                await send_temp_ctx(ctx, discord.Embed(description="❌ Internal error occurred (logged).", color=discord.Color.red()))
            except Exception:
                pass

    # ---------- Hybrid command: lolilist ----------
    @commands.hybrid_command(name="lolilist", description="View the Loli leaderboard and stats.")
    async def lolilist(self, ctx: commands.Context):
        try:
            try:
                await ctx.defer()
            except Exception:
                pass

            guild_id = getattr(ctx.guild, "id", None)
            stats = await self._fetch_stats(guild_id)

            try:
                entries = await execute_db_operation(
                    "fetch loli entries",
                    "SELECT anilist_username, anilist_url, avatar_url, created_at FROM loli_list WHERE guild_id = ? ORDER BY created_at DESC",
                    (guild_id,),
                    fetch_type="all"
                )
            except Exception as e:
                logger.error(f"Failed to fetch entries: {e}")
                entries = []

            total_entries = len(entries)
            if total_entries == 0:
                await ctx.send("❌ No entries found.", ephemeral=True)
                return

            # Build pages (list of slices). Each page contains up to PER_PAGE entries.
            pages = [entries[i:i + self.per_page] for i in range(0, total_entries, self.per_page)]
            total_pages = len(pages)

            # one-line warning (short)
            warning_text = "⚠️ DO NOT HARASS ANY USERS LISTED BELOW. REPORT MISUSE."

            # builder function returns list of embeds for a page index
            async def make_embeds_for_page(page_index: int) -> List[discord.Embed]:
                page_entries = pages[page_index]
                # header embed with emojis & stats
                header = discord.Embed(
                    title="🧸✨ Loli Leaderboard ✨🧸",
                    description=f"**Total Entries:** {stats.get('total_entries', '?')} • **Added Today:** {stats.get('added_today', '?')}",
                    color=discord.Color.from_rgb(245, 245, 248)
                )
                header.set_footer(text=f"Updated: {stats.get('most_recent') or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
                embeds: List[discord.Embed] = [header]

                # Add one embed per profile
                start_rank = page_index * self.per_page
                for idx, row in enumerate(page_entries, start=1):
                    rank = start_rank + idx
                    name, url, avatar, created_at = row
                    added_text = created_at if isinstance(created_at, str) else (created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "Unknown")
                    e = discord.Embed(title=f"#{rank} — {name}", color=discord.Color.from_rgb(255, 255, 255))
                    # neat description with link and added date
                    e.description = f"[Open AniList profile]({url}) •\nAdded: `{added_text}`"
                    # set thumbnail (avatar) if present so embed shows profile image
                    if avatar:
                        try:
                            e.set_thumbnail(url=avatar)
                        except Exception:
                            pass
                    # whitespace / aesthetics
                    e.set_author(name=name)
                    embeds.append(e)
                return embeds

            # initial embeds
            initial_embeds = await make_embeds_for_page(0)
            view = PaginationView(total_pages=total_pages, current_index=0, make_embeds_func=make_embeds_for_page, warning_text=warning_text)
            try:
                sent = await ctx.send(content=warning_text, embeds=initial_embeds, view=view)
            except Exception:
                try:
                    sent = await ctx.author.send(content=warning_text, embeds=initial_embeds, view=view)
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
        stats = {"total_entries": 0, "added_today": 0, "most_recent": None}
        try:
            row = await execute_db_operation("stats total", "SELECT COUNT(*) FROM loli_list WHERE guild_id = ?", (guild_id,), fetch_type="one")
            stats["total_entries"] = row[0] if row else 0

            row2 = await execute_db_operation("stats today", "SELECT COUNT(*) FROM loli_list WHERE guild_id = ? AND created_at >= DATETIME('now','-1 day')", (guild_id,), fetch_type="one")
            stats["added_today"] = row2[0] if row2 else 0

            row3 = await execute_db_operation("most recent", "SELECT created_at FROM loli_list WHERE guild_id = ? ORDER BY created_at DESC LIMIT 1", (guild_id,), fetch_type="one")
            if row3 and row3[0]:
                stats["most_recent"] = row3[0]
        except Exception as e:
            logger.error(f"Stats fetch error: {e}")
        return stats

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("LoliList cog ready.")


# ---------- Cog setup ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(LoliList(bot))

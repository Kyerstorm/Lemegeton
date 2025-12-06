# cogs/social/lolilist.py
"""
LoliList — Global cross-guild leaderboard cog
Features:
 - Global table: lolilist_entries (no guild_id) — adds are visible in all guilds.
 - Prefix moderator add/delete (aliases): !loliadd / !ladd, !loli delete / !ldel
 - Continuous intake mode for add sessions: bot accepts ALL messages you send during the session (until Finish or timeout).
 - !loli delete all — double-confirm wipe of the entire table.
 - /lolilist (slash-only) — header + up to 5 profile embeds per page (one embed per profile to allow avatar thumbnails).
 - Pagination with Prev | [Page X/Y disabled] | Next; timeout 10 minutes (600s).
 - AniList GraphQL via aiohttp; numeric id support and username support.
 - Caching via cache_helper; DB operations via execute_db_operation.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import logging
import traceback
import shutil
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# Project helpers 
from cache_helper import load_json_cache, save_json_cache, is_json_cache_valid
from database import execute_db_operation, is_user_bot_moderator
try:
    import config
    DB_PATH = Path(config.DB_PATH)
except Exception:
    DB_PATH = Path("data/bot_database.db")

# Constants
LOGS_DIR = Path("logs")
BACKUP_DIR = Path("data/backups")
ANILIST_GRAPHQL = "https://graphql.anilist.co"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours
PER_PAGE = 5
AUTO_DELETE_DELAY = 5.0
CONFIRM_TIMEOUT = 30.0
ADD_SESSION_TIMEOUT = 90.0  # session window for continuous intake
PAGINATION_TIMEOUT = 600.0 

# Ensure dirs
LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
Path("data").mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("LoliList")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOGS_DIR / "loli_list.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

# Regex supports username (with optional @), slug, or numeric ID
ANILIST_PROFILE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?anilist\.co/(?:user|u)/(?:@?)(?P<username>[\w\-\._]+|\d+)",
    re.IGNORECASE
)


def extract_username_from_link(link: str) -> Optional[str]:
    """Return bare username or numeric id (string) from an AniList URL, or raw input if looks like a username/id."""
    if not link:
        return None
    m = ANILIST_PROFILE_REGEX.search(link.strip())
    if m:
        return m.group("username")
    # if user provided a raw username or numeric id without slashes
    if "/" not in link and " " not in link:
        return link.strip()
    return None


def cache_key(identifier: str) -> str:
    return f"anilist_user_{identifier}"


async def send_temp(ctx: commands.Context, embed: discord.Embed, delay: float = AUTO_DELETE_DELAY):
    """
    Send an in-channel temporary message which auto-deletes after `delay` seconds.
    If cannot send in-channel, try DM fallback.
    """
    try:
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except Exception:
            pass
    except Exception:
        try:
            await ctx.author.send(embed=embed)
        except Exception:
            logger.debug("Failed to send temporary message (channel & DM).")


# AniList GraphQL queries
ANILIST_USER_BY_NAME_QUERY = """
query ($name: String) {
  User(name: $name) {
    id name siteUrl avatar { large }
  }
}
"""
ANILIST_USER_BY_ID_QUERY = """
query ($id: Int) {
  User(id: $id) {
    id name siteUrl avatar { large }
  }
}
"""


async def fetch_anilist_graphql(identifier: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """
    Query AniList GraphQL by numeric id (if identifier.isdigit()) or by name otherwise.
    Returns dict {id, name, siteUrl, avatar} or None if not found.
    """
    try:
        ident = identifier.strip()
        if ident.isdigit():
            payload = {"query": ANILIST_USER_BY_ID_QUERY, "variables": {"id": int(ident)}}
        else:
            payload = {"query": ANILIST_USER_BY_NAME_QUERY, "variables": {"name": ident.lstrip("@")}}
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        async with session.post(ANILIST_GRAPHQL, json=payload, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                txt = await resp.text()
                logger.debug(f"AniList GraphQL non-200 ({resp.status}) for {identifier}: {txt}")
                return None
            data = await resp.json()
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


# -------------------- UI Views --------------------

class ConfirmView(discord.ui.View):
    """Generic confirm/cancel view. .value will be True/False/None."""
    def __init__(self, timeout: float = CONFIRM_TIMEOUT):
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(embed=discord.Embed(description="Confirmed.", color=discord.Color.green()), view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(embed=discord.Embed(description="Cancelled.", color=discord.Color.red()), view=None)
        self.stop()


class PagingView(discord.ui.View):
    """
    Pagination view:
    Prev  [Page X/Y disabled]  Next
    Prev/Next are disabled at edges.
    Timeout is PAGINATION_TIMEOUT (10 minutes).
    """

    def __init__(self, total_pages: int, current: int, make_embeds_func, warning_text: str):
        super().__init__(timeout=PAGINATION_TIMEOUT)
        self.total_pages = max(1, total_pages)
        self.current = current
        self.make_embeds = make_embeds_func
        self.warning_text = warning_text
        # create buttons
        self.prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.gray)
        self.page_btn = discord.ui.Button(label=f"Page {self.current+1}/{self.total_pages}", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.gray)

        self.add_item(self.prev_btn)
        self.add_item(self.page_btn)
        self.add_item(self.next_btn)

        # bind callbacks
        self.prev_btn.callback = self._on_prev
        self.next_btn.callback = self._on_next

        self._refresh()

    def _refresh(self):
        self.prev_btn.disabled = (self.current <= 0)
        self.next_btn.disabled = (self.current >= (self.total_pages - 1))
        self.page_btn.label = f"Page {self.current+1}/{self.total_pages}"

    async def _on_prev(self, interaction: discord.Interaction):
        if self.current <= 0:
            return
        self.current -= 1
        self._refresh()
        embeds = await self.make_embeds(self.current)
        try:
            await interaction.response.edit_message(content=self.warning_text, embeds=embeds, view=self)
        except Exception:
            try:
                await interaction.message.edit(content=self.warning_text, embeds=embeds, view=self)
            except Exception:
                pass

    async def _on_next(self, interaction: discord.Interaction):
        if self.current >= (self.total_pages - 1):
            return
        self.current += 1
        self._refresh()
        embeds = await self.make_embeds(self.current)
        try:
            await interaction.response.edit_message(content=self.warning_text, embeds=embeds, view=self)
        except Exception:
            try:
                await interaction.message.edit(content=self.warning_text, embeds=embeds, view=self)
            except Exception:
                pass

    async def on_timeout(self):
        # disable all buttons when view times out
        for child in self.children:
            child.disabled = True
        if getattr(self, "message", None):
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# -------------------- Cog --------------------

class LoliList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.per_page = PER_PAGE
        self.session = aiohttp.ClientSession()
        self._active_sessions: Dict[int, Dict[str, Any]] = {}  # author_id -> session metadata
        asyncio.create_task(self._ensure_tables())
        self.autobackup_task.start()

    def cog_unload(self):
        try:
            asyncio.create_task(self.session.close())
        except Exception:
            pass
        self.autobackup_task.cancel()

    async def _ensure_tables(self):
        """
        Create global table: lolilist_entries and loli_audit
        """
        q_entries = """
        CREATE TABLE IF NOT EXISTS lolilist_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anilist_id INTEGER UNIQUE,
            anilist_username TEXT,
            anilist_url TEXT,
            avatar_url TEXT,
            added_by INTEGER,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        await execute_db_operation("ensure_lolilist_entries", q_entries)

        q_audit = """
        CREATE TABLE IF NOT EXISTS loli_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mod_id INTEGER,
            action TEXT,
            batch_size INTEGER,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        await execute_db_operation("ensure_loli_audit", q_audit)

    @tasks.loop(hours=24)
    async def autobackup(self):
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            if DB_PATH.exists():
                dest = BACKUP_DIR / f"{DB_PATH.stem}_backup_{ts}.db"
                shutil.copy2(DB_PATH, dest)
                logger.info(f"LoliList DB backup created: {dest}")
        except Exception as e:
            logger.error(f"autobackup error: {e}")

    async def _is_mod(self, user: discord.User) -> bool:
        try:
            return bool(await is_user_bot_moderator(user))
        except Exception as e:
            logger.error(f"Moderator check error: {e}")
            return False

#-----------------------------------
# Mod only Prefixes
#-----------------------------------

    
    # ---------- Prefix add  ----------
    @commands.command(name="loliadd", aliases=["ladd"])
    async def loliadd(self, ctx: commands.Context, first_link: Optional[str] = None):
        """
        Moderator-only prefix command to add globally.
        Continuous intake session: the moderator's messages in the same channel are processed
        as they arrive during the session window until the moderator types 'finish' or presses Finish.
        Usage: !loliadd <link|username|id>
        Aliases:!ladd
        """
        try:
            # delete invoking message
            try:
                await ctx.message.delete()
            except Exception:
                pass

            if not first_link:
                await send_temp(ctx, discord.Embed(description="Usage: `!loliadd <AniList URL | username | id>`", color=discord.Color.orange()))
                return

            if not await self._is_mod(ctx.author):
                logger.info(f"Non-mod attempted loliadd: {ctx.author}")
                return

            author_id = ctx.author.id
            if self._active_sessions.get(author_id):
                await send_temp(ctx, discord.Embed(description="You already have an active add session. Finish it first.", color=discord.Color.orange()))
                return

            # create session metadata and flag
            session_meta = {
                "channel": ctx.channel,
                "author": ctx.author,
                "start": datetime.utcnow(),
                "collected": [],  # list of (raw_message_content)
                "finished": False
            }
            self._active_sessions[author_id] = session_meta

            # confirm initial add
            confirm = ConfirmView()
            try:
                prompt = discord.Embed(title="⚠️ Confirm Add", description=f"Start add session and add **{first_link}** globally? Session will accept additional messages for {ADD_SESSION_TIMEOUT}s or until you finish.", color=discord.Color.from_rgb(200,225,255))
                prompt_msg = await ctx.send(embed=prompt, view=confirm)
                await confirm.wait()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except Exception:
                try:
                    dm = await ctx.author.send(embed=prompt, view=confirm)
                    await confirm.wait()
                except Exception:
                    logger.warning("Confirm prompt undeliverable.")
                    self._active_sessions.pop(author_id, None)
                    return

            if not confirm.value:
                await send_temp(ctx, discord.Embed(description="Cancelled.", color=discord.Color.red()))
                self._active_sessions.pop(author_id, None)
                return

            # Process the first link immediately
            collected_links = [first_link]

            # Start continuous intake: inform user
            start_embed = discord.Embed(title="🟢 Add Session Started", description=f"Paste AniList links/usernames/IDs in chat. Type `finish` to end. Session times out after {ADD_SESSION_TIMEOUT}s of inactivity.", color=discord.Color.green())
            try:
                notice = await ctx.send(embed=start_embed)
                # auto-delete notice after a few seconds so channel isn't spammy
                await asyncio.sleep(6)
                try:
                    await notice.delete()
                except Exception:
                    pass
            except Exception:
                pass

            # Now accept messages until finished or timeout: every message by author in the same channel is processed
            last_activity = datetime.utcnow()

            # Process immediate first link
            a, s, f = await self._process_links_batch(collected_links, ctx, ctx.author.id)
            total_added = a

            # Enter continuous loop: wait for messages from the same author in same channel
            while True:
                def _check(m: discord.Message):
                    return m.author.id == author_id and m.channel.id == ctx.channel.id

                try:
                    # wait for next message during session window (ADD_SESSION_TIMEOUT)
                    msg: discord.Message = await self.bot.wait_for("message", check=_check, timeout=ADD_SESSION_TIMEOUT)
                    last_activity = datetime.utcnow()
                    # delete the moderator message to keep channel clean
                    try:
                        await msg.delete()
                    except Exception:
                        pass

                    content = msg.content.strip()
                    if not content:
                        continue
                    # If user typed finish (case-insensitive), stop the session
                    if content.lower() in ("finish", "done", "stop"):
                        await send_temp(ctx, discord.Embed(description="Add session finished by user.", color=discord.Color.green()))
                        break

                    # Otherwise, treat the message content as 1..N links/names separated by whitespace/comma
                    raw_links = [l.strip() for l in re.split(r"[\s,]+", content) if l.strip()]
                    if not raw_links:
                        continue
                    a2, s2, f2 = await self._process_links_batch(raw_links, ctx, ctx.author.id)
                    total_added += a2
                    # notify quickly
                    await send_temp(ctx, discord.Embed(description=f"Batch processed — Added: {a2}, Skipped: {s2}, Failed: {f2}", color=discord.Color.green()))
                    # continue waiting until timeout or finish
                    continue

                except asyncio.TimeoutError:
                    # no new message in ADD_SESSION_TIMEOUT -> session ends due to inactivity
                    await send_temp(ctx, discord.Embed(description="Session timed out due to inactivity.", color=discord.Color.orange()))
                    break

            # session finished: audit + backup
            try:
                await execute_db_operation("insert_audit", "INSERT INTO loli_audit (mod_id, action, batch_size, details) VALUES (?, ?, ?, ?)", (ctx.author.id, "add_global_session", total_added, f"started_with={first_link}"))
            except Exception:
                pass
            try:
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                if DB_PATH.exists():
                    shutil.copy2(DB_PATH, BACKUP_DIR / f"{DB_PATH.stem}_backup_{ts}.db")
            except Exception:
                pass

            await send_temp(ctx, discord.Embed(description=f"Finished session. Total added this session: {total_added}", color=discord.Color.green()))
            # cleanup session
            self._active_sessions.pop(author_id, None)

        except Exception as e:
            logger.error(f"loliadd exception: {e}\n{traceback.format_exc()}")
            try:
                await send_temp(ctx, discord.Embed(description="Internal error (logged).", color=discord.Color.red()))
            except Exception:
                pass
            self._active_sessions.pop(ctx.author.id, None)

    async def _process_links_batch(self, links: List[str], ctx: commands.Context, mod_id: int) -> Tuple[int, int, int]:
        """
        Validate & insert a batch of links/names/ids. Returns (added, skipped, failed).
        Uses cache_helper and execute_db_operation (project helpers).
        """
        added = skipped = failed = 0
        unique = []
        seen = set()
        for l in links:
            if not l:
                continue
            uname = extract_username_from_link(l) or l.strip()
            key = uname.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append((l, uname))

        tasks = []
        for raw, uname in unique:
            k = cache_key(uname)
            cached = None
            try:
                if is_json_cache_valid(k, CACHE_TTL_SECONDS):
                    cached = load_json_cache(k)
            except Exception:
                cached = None
            if cached:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=(raw, uname, cached))))
            else:
                tasks.append(asyncio.create_task(self._fetch_user_task(raw, uname)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Fetch exception in batch: {res}")
                failed += 1
                continue
            raw, uname, info = res
            if not info:
                skipped += 1
                await send_temp(ctx, discord.Embed(description=f"Invalid or not found: `{raw}`", color=discord.Color.red()))
                continue
            anilist_id = info.get("id")
            try:
                exists = await execute_db_operation("check_existing", "SELECT id FROM lolilist_entries WHERE anilist_id = ?", (anilist_id,), fetch_type="one")
            except Exception as e:
                logger.error(f"DB check err: {e}")
                exists = None
            if exists:
                skipped += 1
                await send_temp(ctx, discord.Embed(description=f"Already exists globally: {info.get('name')}", color=discord.Color.orange()))
                continue
            try:
                await execute_db_operation("insert_entry",
                                          "INSERT INTO lolilist_entries (anilist_id, anilist_username, anilist_url, avatar_url, added_by) VALUES (?, ?, ?, ?, ?)",
                                          (anilist_id, info.get("name") or uname, info.get("siteUrl") or raw, info.get("avatar"), mod_id))
                added += 1
                # save to cache if possible
                try:
                    save_json_cache(cache_key(uname), info)
                except Exception:
                    pass
                await send_temp(ctx, discord.Embed(description=f"Added globally: **{info.get('name') or uname}**", color=discord.Color.green()))
            except Exception as e:
                failed += 1
                logger.error(f"DB insert error: {e}")
                await send_temp(ctx, discord.Embed(description=f"Failed to add {uname} (DB error).", color=discord.Color.red()))
        return added, skipped, failed

    async def _fetch_user_task(self, raw_link: str, username: str):
        """Fetch a single AniList user via GraphQL (numeric id or name)."""
        try:
            ident = username.strip()
            info = await fetch_anilist_graphql(ident, self.session)
            return (raw_link, username, info)
        except Exception as e:
            logger.error(f"_fetch_user_task err for {username}: {e}")
            return (raw_link, username, None)


    
    # ---------- Prefix delete ----------
    @commands.command(name="lolidelete", aliases=["ldel"])
    async def loli_prefix(self, ctx: commands.Context, subcommand: Optional[str] = None, *, rest: Optional[str] = None):
        """
        Prefix group. Use:
         - !loli delete <username|id|url>   (delete single)
         - !loli delete all                  (delete all entries globally; double confirm)
        Aliases:!ldel
        """
        if subcommand != "delete":
            return
        await self._handle_delete(ctx, rest)

    async def _handle_delete(self, ctx: commands.Context, target: Optional[str]):
        try:
            # delete invoking message
            try:
                await ctx.message.delete()
            except Exception:
                pass

            if not await self._is_mod(ctx.author):
                logger.info(f"Non-mod attempted delete: {ctx.author}")
                return

            if not target:
                await send_temp(ctx, discord.Embed(description="Usage: `!loli delete <username|id|url|all>`", color=discord.Color.orange()))
                return

            if target.strip().lower() in ("all", "everything", "wipe"):
                # double-confirm destructive action
                confirm1 = ConfirmView()
                try:
                    m1 = await ctx.send(embed=discord.Embed(title="⚠️ Confirm Delete ALL", description="This will **PERMANENTLY DELETE ALL** global entries. Proceed to 1st confirmation?", color=discord.Color.red()), view=confirm1)
                    await confirm1.wait()
                    try:
                        await m1.delete()
                    except Exception:
                        pass
                except Exception:
                    await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Delete ALL", description="This will **PERMANENTLY DELETE ALL** global entries. Proceed to 1st confirmation?", color=discord.Color.red()), view=confirm1)
                    await confirm1.wait()

                if not confirm1.value:
                    await send_temp(ctx, discord.Embed(description="Cancelled.", color=discord.Color.red()))
                    return

                # second confirm (extra safety) — require pressing Confirm again
                confirm2 = ConfirmView()
                try:
                    m2 = await ctx.send(embed=discord.Embed(title="⚠️ FINAL Confirm Delete ALL", description="This is the FINAL confirmation. This action is irreversible. Confirm to delete ALL entries.", color=discord.Color.red()), view=confirm2)
                    await confirm2.wait()
                    try:
                        await m2.delete()
                    except Exception:
                        pass
                except Exception:
                    await ctx.author.send(embed=discord.Embed(title="⚠️ FINAL Confirm Delete ALL", description="This is the FINAL confirmation. This action is irreversible. Confirm to delete ALL entries.", color=discord.Color.red()), view=confirm2)
                    await confirm2.wait()

                if not confirm2.value:
                    await send_temp(ctx, discord.Embed(description="Cancelled final.", color=discord.Color.red()))
                    return

                # perform deletion
                try:
                    await execute_db_operation("delete_all", "DELETE FROM lolilist_entries", ())
                    await execute_db_operation("insert_audit", "INSERT INTO loli_audit (mod_id, action, batch_size, details) VALUES (?, ?, ?, ?)",
                                              (ctx.author.id, "delete_all", 0, "deleted all entries"))
                    await send_temp(ctx, discord.Embed(description="✅ All entries deleted globally.", color=discord.Color.green()))
                    # backup
                    try:
                        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                        if DB_PATH.exists():
                            shutil.copy2(DB_PATH, BACKUP_DIR / f"{DB_PATH.stem}_backup_{ts}.db")
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"delete_all error: {e}")
                    await send_temp(ctx, discord.Embed(description="❌ Failed to delete all entries (DB error).", color=discord.Color.red()))
                return

            # single delete flow
            uname = extract_username_from_link(target) or target.strip()
            # try cache first
            cached = None
            try:
                if is_json_cache_valid(cache_key(uname), CACHE_TTL_SECONDS):
                    cached = load_json_cache(cache_key(uname))
            except Exception:
                cached = None

            if cached:
                info = cached
            else:
                info = await fetch_anilist_graphql(uname, self.session)

            if not info:
                await send_temp(ctx, discord.Embed(description=f"AniList user not found: `{target}`", color=discord.Color.red()))
                return
            # find entry global
            try:
                existing = await execute_db_operation("find_entry", "SELECT id, anilist_username FROM lolilist_entries WHERE anilist_id = ?", (info["id"],), fetch_type="one")
            except Exception as e:
                logger.error(f"DB find err: {e}")
                existing = None
            if not existing:
                await send_temp(ctx, discord.Embed(description=f"Entry not found for {info.get('name')}", color=discord.Color.orange()))
                return

            confirm = ConfirmView()
            try:
                m = await ctx.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete global entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                await confirm.wait()
                try:
                    await m.delete()
                except Exception:
                    pass
            except Exception:
                await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete global entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                await confirm.wait()

            if not confirm.value:
                await send_temp(ctx, discord.Embed(description="Cancelled.", color=discord.Color.red()))
                return
            try:
                await execute_db_operation("delete_entry", "DELETE FROM lolilist_entries WHERE id = ?", (existing[0],))
                await execute_db_operation("insert_audit", "INSERT INTO loli_audit (mod_id, action, batch_size, details) VALUES (?, ?, ?, ?)",
                                          (ctx.author.id, "delete_single", 1, existing[1]))
                await send_temp(ctx, discord.Embed(description=f"✅ Deleted {existing[1]}.", color=discord.Color.green()))
            except Exception as e:
                logger.error(f"delete single err: {e}")
                await send_temp(ctx, discord.Embed(description="❌ Failed to delete (DB error).", color=discord.Color.red()))

        except Exception as e:
            logger.error(f"_handle_delete exception: {e}\n{traceback.format_exc()}")
            try:
                await send_temp(ctx, discord.Embed(description="Internal error (logged).", color=discord.Color.red()))
            except Exception:
               pass

    
#---------------------------
# The Main Command
#---------------------------

    
    @app_commands.command(name="lolilist", description="Shows the Loli List.")
    async def lolilist(self, interaction: discord.Interaction):
        """
        Slash-only global leaderboard: header + up to PER_PAGE profile embeds per page.
        Pagination timeout: PAGINATION_TIMEOUT (10 minutes).
        """
        await interaction.response.defer()
        # global stats
        stats = {"total_entries": 0, "added_today": 0, "most_recent": None}
        try:
            r = await execute_db_operation("stats_total", "SELECT COUNT(*) FROM lolilist_entries", (), fetch_type="one")
            stats["total_entries"] = r[0] if r else 0
            r2 = await execute_db_operation("stats_today", "SELECT COUNT(*) FROM lolilist_entries WHERE added_at >= DATETIME('now','-1 day')", (), fetch_type="one")
            stats["added_today"] = r2[0] if r2 else 0
            r3 = await execute_db_operation("most_recent", "SELECT added_at FROM lolilist_entries ORDER BY added_at DESC LIMIT 1", (), fetch_type="one")
            stats["most_recent"] = r3[0] if r3 else None
        except Exception as e:
            logger.error(f"stats fetch error: {e}")

        # fetch global rows
        try:
            rows = await execute_db_operation("fetch_all", "SELECT anilist_username, anilist_url, avatar_url, added_at FROM lolilist_entries ORDER BY added_at DESC", (), fetch_type="all")
        except Exception as e:
            logger.error(f"fetch_all error: {e}")
            rows = []

        if not rows:
            await interaction.followup.send("❌ No entries found.", ephemeral=True)
            return

        # paginate
        pages = [rows[i:i + self.per_page] for i in range(0, len(rows), self.per_page)]
        total_pages = len(pages)
        warning_line = "⚠️ DO NOT HARASS LISTED USERS."

        async def make_embeds_for_page(page_index: int) -> List[discord.Embed]:
            page = pages[page_index]
            header = discord.Embed(title="🧸✨ Loli Leaderboard ✨🧸",
                                   description=f"**Total Entries:** {stats.get('total_entries','?')} • **Added Today:** {stats.get('added_today','?')}",
                                   color=discord.Color.from_rgb(245, 245, 248))
            header.set_footer(text=f"Updated: {stats.get('most_recent') or datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            embeds: List[discord.Embed] = [header]
            start_rank = page_index * self.per_page
            for idx, r in enumerate(page, start=1):
                rank = start_rank + idx
                name, url, avatar, added_at = r
                added_text = added_at if isinstance(added_at, str) else (added_at.strftime("%Y-%m-%d %H:%M:%S") if added_at else "Unknown")
                e = discord.Embed(title=f"#{rank} — {name}", color=discord.Color.from_rgb(255, 255, 255))
                e.description = f"[Open AniList profile]({url}) •\nAdded: `{added_text}`"
                if avatar:
                    try:
                        e.set_thumbnail(url=avatar)
                    except Exception:
                        pass
                e.set_author(name=name)
                embeds.append(e)
            return embeds

        initial_embeds = await make_embeds_for_page(0)
        view = PagingView(total_pages=total_pages, current=0, make_embeds_func=make_embeds_for_page, warning_text=warning_line)
        try:
            sent = await interaction.followup.send(content=warning_line, embeds=initial_embeds, view=view)
        except Exception as e:
            logger.error(f"send leaderboard err: {e}")
            await interaction.followup.send("Failed to send leaderboard (missing permission?).", ephemeral=True)
            return
        view.message = sent

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("LoliList cog loaded.")


# Cog setup
async def setup(bot: commands.Bot):
    await bot.add_cog(LoliList(bot))

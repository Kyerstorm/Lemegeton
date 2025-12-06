"""

Behavior summary:
 - Global DB table: lolilist_entries (no guild_id). Adds are global (visible in all guilds).
 - Prefix moderator commands (message deleted, ephemeral-style in-channel replies):
    !loliadd <link|username|id>
    !loli delete <link|username|id>
 - /lolilist is slash-only (app_commands) and shows a header + up to 5 profile embeds per page.
 - Pagination: Prev | [Page X/Y disabled] | Next (buttons disabled appropriately).
 - AniList lookups done with aiohttp GraphQL (supports numeric id and username).
 - Caching: cache_helper functions (load_json_cache, save_json_cache, is_json_cache_valid).
 - DB operations: execute_db_operation(...) and is_user_bot_moderator(user) from your database helper.
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
from helpers.cache_helper import load_json_cache, save_json_cache, is_json_cache_valid
from database import execute_db_operation, is_user_bot_moderator

# Try to reuse config DB path if present in your project
try:
    import config
    DB_PATH = Path(config.DB_PATH)
except Exception:
    DB_PATH = Path("data/bot_database.db")

# Constants / config
LOGS_DIR = Path("logs")
BACKUP_DIR = Path("data/backups")
ANILIST_GRAPHQL = "https://graphql.anilist.co"
CACHE_TTL_SECONDS = 6 * 3600
PER_PAGE = 5
AUTO_DELETE_DELAY = 6.0
CONFIRM_TIMEOUT = 120.0
ADD_SESSION_TIMEOUT = 90.0

LOGS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
Path("data").mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("LoliList")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    fh = logging.FileHandler(LOGS_DIR / "loli_list.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

# Regex supports username (including @), slug, and numeric ID
ANILIST_PROFILE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?anilist\.co/(?:user|u)/(?:@?)(?P<username>[\w\-\._]+|\d+)",
    re.IGNORECASE
)


def extract_username_from_link(link: str) -> Optional[str]:
    if not link:
        return None
    m = ANILIST_PROFILE_REGEX.search(link.strip())
    if m:
        return m.group("username")
    # raw input (username or numeric id)
    if "/" not in link and " " not in link:
        return link.strip()
    return None


def cache_key(identifier: str) -> str:
    return f"anilist_user_{identifier}"


async def send_temp(ctx: commands.Context, embed: discord.Embed, delay: float = AUTO_DELETE_DELAY):
    """Send an in-channel message that auto-deletes after delay. DM fallback."""
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
    identifier: username (maybe with @) OR numeric id string.
    Returns: dict {id, name, siteUrl, avatar} or None.
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


# -- UI Views --
class ConfirmView(discord.ui.View):
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
    Prev | [Page X/Y disabled] | Next
    Prev/Next disabled at edges.
    """

    def __init__(self, total_pages: int, current: int, make_embeds_func, warning_text: str):
        super().__init__(timeout=120)
        self.total_pages = max(1, total_pages)
        self.current = current
        self.make_embeds = make_embeds_func
        self.warning_text = warning_text
        # create buttons and bind callbacks
        self.prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.gray)
        self.page_btn = discord.ui.Button(label=f"Page {self.current+1}/{self.total_pages}", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.gray)

        self.add_item(self.prev_btn)
        self.add_item(self.page_btn)
        self.add_item(self.next_btn)

        self.prev_btn.callback = self._on_prev
        self.next_btn.callback = self._on_next

        self._refresh()

    def _refresh(self):
        self.prev_btn.disabled = self.current <= 0
        self.next_btn.disabled = self.current >= (self.total_pages - 1)
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
        for c in self.children:
            c.disabled = True
        if getattr(self, "message", None):
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# -- The Cog (global table: lolilist_entries) --
class LoliList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.per_page = PER_PAGE
        self.session = aiohttp.ClientSession()
        self._active_sessions: Dict[int, bool] = {}
        # ensure global table(s)
        asyncio.create_task(self._ensure_tables())
        self.autobackup.start()

    def cog_unload(self):
        try:
            asyncio.create_task(self.session.close())
        except Exception:
            pass
        self.autobackup.cancel()

    async def _ensure_tables(self):
        """
        Create global table 'lolilist_entries' and audit table 'loli_audit' if missing.
        This is the global (cross-guild) store.
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
                logger.info(f"LoliList DB backup: {dest}")
        except Exception as e:
            logger.error(f"autobackup error: {e}")

    async def _is_moderator(self, user: discord.User) -> bool:
        try:
            return bool(await is_user_bot_moderator(user))
        except Exception as e:
            logger.error(f"Moderator check failed: {e}")
            return False

    # -------- Prefix add (global) --------
    @commands.command(name="loliadd")
    async def loliadd(self, ctx: commands.Context, link: Optional[str] = None):
        """
        Moderator-only prefix: add a user globally.
        Usage: !loliadd <AniList URL | username | id>
        """
        try:
            try:
                await ctx.message.delete()
            except Exception:
                pass

            if not link:
                await send_temp(ctx, discord.Embed(description="Usage: `!loliadd <AniList URL | username | id>`", color=discord.Color.orange()))
                return

            if not await self._is_moderator(ctx.author):
                logger.info(f"Non-mod attempted loliadd: {ctx.author}")
                return

            if self._active_sessions.get(ctx.author.id):
                await send_temp(ctx, discord.Embed(description="You have an active add session. Finish it first.", color=discord.Color.orange()))
                return
            self._active_sessions[ctx.author.id] = True

            # confirm
            confirm = ConfirmView()
            try:
                msg = await ctx.send(embed=discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** globally?", color=discord.Color.from_rgb(200,225,255)), view=confirm)
                await confirm.wait()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except Exception:
                # DM fallback
                dm = await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Add", description=f"Add **{link}** globally?", color=discord.Color.from_rgb(200,225,255)), view=confirm)
                await confirm.wait()

            if not confirm.value:
                await send_temp(ctx, discord.Embed(description="Cancelled.", color=discord.Color.red()))
                self._active_sessions.pop(ctx.author.id, None)
                return

            # process initial link
            added, skipped, failed = await self._process_links([link], ctx, ctx.author.id)
            total_added = added

            # optionally allow multiple rounds
            while True:
                more_view = discord.ui.View(timeout=CONFIRM_TIMEOUT)
                class MV(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=CONFIRM_TIMEOUT)
                        self.add_more = False
                        self.finish = False

                    @discord.ui.button(label="➕ Add more", style=discord.ButtonStyle.blurple)
                    async def add_more_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                        self.add_more = True
                        await interaction.response.edit_message(embed=discord.Embed(description="Paste links in chat (space/newline separated).", color=discord.Color.blue()), view=None)
                        self.stop()

                    @discord.ui.button(label="✅ Finish", style=discord.ButtonStyle.gray)
                    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                        self.finish = True
                        await interaction.response.edit_message(embed=discord.Embed(description="Finished adding.", color=discord.Color.green()), view=None)
                        self.stop()

                mv = MV()
                try:
                    pm = await ctx.send(embed=discord.Embed(title="➕ Add More?", description="Add more entries globally?", color=discord.Color.blurple()), view=mv)
                    await mv.wait()
                    try:
                        await pm.delete()
                    except Exception:
                        pass
                except Exception:
                    try:
                        dm = await ctx.author.send(embed=discord.Embed(title="➕ Add More?", description="Add more entries globally?", color=discord.Color.blurple()), view=mv)
                        await mv.wait()
                    except Exception:
                        break

                if mv.finish:
                    break
                if mv.add_more:
                    await send_temp(ctx, discord.Embed(description="Paste additional links now (you have 90s).", color=discord.Color.yellow()))
                    def check_msg(m: discord.Message):
                        return m.author.id == ctx.author.id and (m.channel == ctx.channel)
                    try:
                        pasted: discord.Message = await self.bot.wait_for("message", check=check_msg, timeout=ADD_SESSION_TIMEOUT)
                        content = pasted.content
                        try:
                            await pasted.delete()
                        except Exception:
                            pass
                        raw_links = [s.strip() for s in re.split(r"[\s,]+", content) if s.strip()]
                        if not raw_links:
                            await send_temp(ctx, discord.Embed(description="No valid links found.", color=discord.Color.orange()))
                            continue
                        a2, s2, f2 = await self._process_links(raw_links, ctx, ctx.author.id)
                        total_added += a2
                        await send_temp(ctx, discord.Embed(description=f"Batch complete — Added: {a2}, Skipped: {s2}, Failed: {f2}", color=discord.Color.green()))
                        continue
                    except asyncio.TimeoutError:
                        await send_temp(ctx, discord.Embed(description="Timeout waiting for paste. Ending session.", color=discord.Color.orange()))
                        break
                else:
                    break

            # audit + backup
            try:
                await execute_db_operation("insert_audit", "INSERT INTO loli_audit (mod_id, action, batch_size, details) VALUES (?, ?, ?, ?)", (ctx.author.id, "add_global", total_added, link))
            except Exception:
                pass
            try:
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                if DB_PATH.exists():
                    shutil.copy2(DB_PATH, BACKUP_DIR / f"{DB_PATH.stem}_backup_{ts}.db")
            except Exception:
                pass

            await send_temp(ctx, discord.Embed(description=f"Finished. Added {total_added} entries globally.", color=discord.Color.green()))
            self._active_sessions.pop(ctx.author.id, None)

        except Exception as e:
            logger.error(f"loliadd exception: {e}\n{traceback.format_exc()}")
            try:
                await send_temp(ctx, discord.Embed(description="Internal error (logged).", color=discord.Color.red()))
            except Exception:
                pass
            self._active_sessions.pop(ctx.author.id, None)

    async def _process_links(self, links: List[str], ctx: commands.Context, mod_id: int) -> Tuple[int, int, int]:
        """Process list of link strings; insert into global table lolilist_entries"""
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
            # cache check
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
                logger.error(f"Exception during fetch batch: {res}")
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
                logger.error(f"DB check existing err: {e}")
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
                # cache write
                try:
                    save_json_cache(cache_key(uname), info)
                except Exception:
                    pass
                await send_temp(ctx, discord.Embed(description=f"Added globally: **{info.get('name') or uname}**", color=discord.Color.green()))
            except Exception as e:
                failed += 1
                logger.error(f"DB insert err: {e}")
                await send_temp(ctx, discord.Embed(description=f"Failed to add {uname} (DB error).", color=discord.Color.red()))
        return added, skipped, failed

    async def _fetch_user_task(self, raw_link: str, username: str):
        """Fetch a single AniList user via GraphQL (preserve casing; numeric id allowed)"""
        try:
            ident = username.strip()
            info = await fetch_anilist_graphql(ident, self.session)
            return (raw_link, username, info)
        except Exception as e:
            logger.error(f"_fetch_user_task err for {username}: {e}")
            return (raw_link, username, None)

    # -------- Prefix delete global ----------
    @commands.command(name="loli")
    async def loli_prefix(self, ctx: commands.Context, subcommand: Optional[str] = None, *, rest: Optional[str] = None):
        if subcommand != "delete":
            return
        await self._handle_delete(ctx, rest)

    async def _handle_delete(self, ctx: commands.Context, target: Optional[str]):
        try:
            try:
                await ctx.message.delete()
            except Exception:
                pass

            if not await self._is_moderator(ctx.author):
                logger.info(f"Non-mod attempted global delete: {ctx.author}")
                return

            if not target:
                await send_temp(ctx, discord.Embed(description="Usage: `!loli delete <username|id|url>`", color=discord.Color.orange()))
                return

            uname = extract_username_from_link(target) or target.strip()
            # try cache
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
                existing = await execute_db_operation("find_global", "SELECT id, anilist_username FROM lolilist_entries WHERE anilist_id = ?", (info["id"],), fetch_type="one")
            except Exception as e:
                logger.error(f"DB find err: {e}")
                existing = None
            if not existing:
                await send_temp(ctx, discord.Embed(description=f"Entry not found for {info.get('name')}", color=discord.Color.orange()))
                return
            # confirm deletion
            confirm = ConfirmView()
            try:
                m = await ctx.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete global entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                await confirm.wait()
                try:
                    await m.delete()
                except Exception:
                    pass
            except Exception:
                dm = await ctx.author.send(embed=discord.Embed(title="⚠️ Confirm Deletion", description=f"Delete global entry for **{existing[1]}**?", color=discord.Color.yellow()), view=confirm)
                await confirm.wait()
            if not confirm.value:
                await send_temp(ctx, discord.Embed(description="Cancelled.", color=discord.Color.red()))
                return
            try:
                await execute_db_operation("delete_global_entry", "DELETE FROM lolilist_entries WHERE id = ?", (existing[0],))
                await execute_db_operation("insert_audit", "INSERT INTO loli_audit (mod_id, action, batch_size, details) VALUES (?, ?, ?, ?)", (ctx.author.id, "delete_global", 1, existing[1]))
                await send_temp(ctx, discord.Embed(description=f"Deleted global entry: {existing[1]}", color=discord.Color.green()))
            except Exception as e:
                logger.error(f"delete global db err: {e}")
                await send_temp(ctx, discord.Embed(description="Failed to delete (DB error).", color=discord.Color.red()))
        except Exception as e:
            logger.error(f"_handle_delete err: {e}\n{traceback.format_exc()}")

    # -------- Slash-only /lolilist (global leaderboard) --------
    @app_commands.command(name="lolilist", description="Show the global Loli leaderboard (slash only).")
    async def lolilist(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # gather global stats
        stats = {"total_entries": 0, "added_today": 0, "most_recent": None}
        try:
            row = await execute_db_operation("stats_total", "SELECT COUNT(*) FROM lolilist_entries", (), fetch_type="one")
            stats["total_entries"] = row[0] if row else 0
            row2 = await execute_db_operation("stats_today", "SELECT COUNT(*) FROM lolilist_entries WHERE added_at >= DATETIME('now','-1 day')", (), fetch_type="one")
            stats["added_today"] = row2[0] if row2 else 0
            row3 = await execute_db_operation("most_recent", "SELECT added_at FROM lolilist_entries ORDER BY added_at DESC LIMIT 1", (), fetch_type="one")
            stats["most_recent"] = row3[0] if row3 else None
        except Exception as e:
            logger.error(f"stats fetch err: {e}")

        # fetch all entries global
        try:
            rows = await execute_db_operation("fetch_all", "SELECT anilist_username, anilist_url, avatar_url, added_at FROM lolilist_entries ORDER BY added_at DESC", (), fetch_type="all")
        except Exception as e:
            logger.error(f"fetch_all err: {e}")
            rows = []

        if not rows:
            await interaction.followup.send("❌ No entries found.", ephemeral=True)
            return

        # paginate global rows into pages of PER_PAGE
        pages = [rows[i:i + self.per_page] for i in range(0, len(rows), self.per_page)]
        total_pages = len(pages)
        warning_single_line = "⚠️ DO NOT HARASS LISTED USERS — REPORT MISUSE."

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
        view = PagingView(total_pages=total_pages, current=0, make_embeds_func=make_embeds_for_page, warning_text=warning_single_line)
        try:
            sent = await interaction.followup.send(content=warning_single_line, embeds=initial_embeds, view=view)
        except Exception as e:
            logger.error(f"send leaderboard err: {e}")
            await interaction.followup.send("Failed to send leaderboard (missing permission?).", ephemeral=True)
            return
        view.message = sent

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("LoliList cog loaded (global).")


async def setup(bot: commands.Bot):
    await bot.add_cog(LoliList(bot))

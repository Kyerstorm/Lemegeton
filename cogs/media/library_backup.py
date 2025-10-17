# library_backup.py
import discord
from discord import app_commands
from discord.ext import commands
import io
import csv
import json
import datetime
import yaml
import asyncio
import aiohttp
import aiosqlite
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable, List, Dict
from config import DB_PATH

# -----------------------------
# Logging Setup
# -----------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "library_backup.log"

logger = logging.getLogger("LibraryBackup")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG)
        sh.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                          datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(sh)

logger.info("Library backup logging initialized")

# -----------------------------
# Type for progress callback
# -----------------------------
ProgressCallback = Optional[Callable[[int, Optional[str]], Awaitable[None]]]

# -----------------------------
# DB Helper (placeholder)
# -----------------------------
async def get_anilist_username_from_db(discord_id: int, guild_id: Optional[int] = None) -> Optional[str]:
    """
    Returns AniList username for a discord user if stored in DB.
    Checks guild-specific then global fallback.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if guild_id:
                cur = await db.execute(
                    "SELECT anilist_username FROM users WHERE discord_id = ? AND guild_id = ? AND anilist_username IS NOT NULL",
                    (discord_id, guild_id)
                )
                row = await cur.fetchone()
                if row:
                    logger.debug(f"Found guild-specific AniList username for {discord_id} in {guild_id}: {row[0]}")
                    return row[0]

            cur = await db.execute(
                "SELECT anilist_username FROM users WHERE discord_id = ? AND anilist_username IS NOT NULL LIMIT 1",
                (discord_id,)
            )
            row = await cur.fetchone()
            if row:
                logger.debug(f"Found AniList username for {discord_id}: {row[0]}")
                return row[0]

        logger.debug(f"No AniList username found for {discord_id}")
        return None
    except Exception as e:
        logger.error(f"DB error while fetching AniList username for {discord_id}: {e}", exc_info=True)
        return None

# -----------------------------
# Status maps & emoji
# -----------------------------
_STATUS_MAP = {
    "CURRENT": "watching",
    "PLANNING": "planned",
    "COMPLETED": "completed",
    "DROPPED": "dropped",
    "PAUSED": "paused",
    "REPEATING": "watching",
}

# For human-readable TXT exports / embeds
_STATUS_EMOJI = {
    "watching": "🎬",
    "reading": "📖",
    "completed": "🏁",
    "dropped": "❌",
    "paused": "⏸",
    "planned": "📝",
}

# -----------------------------
# AniList API helper
# -----------------------------
async def fetch_anilist_library(username: str, media_type: str, extended: bool = False) -> List[Dict]:
    """
    Fetches a user's MediaListCollection from AniList via GraphQL.
    Deduplicates by media id (keeps the entry with the latest updatedAt).
    Returns normalized entries with keys:
      anilist_id, title, status, progress, rating, tags, start_date, finish_date,
      rewatch_count, last_updated, updated_ts, (plus extended fields if requested)
    """
    logger.debug(f"Fetching AniList library: user={username}, type={media_type}, extended={extended}")
    query = """
    query ($username: String, $type: MediaType) {
      MediaListCollection(userName: $username, type: $type) {
        lists {
          entries {
            media {
              id
              title { romaji english native }
              type
              episodes
              chapters
              volumes
              siteUrl
            }
            status
            progress
            score
            repeat
            startedAt { year month day }
            completedAt { year month day }
            updatedAt
          }
        }
      }
    }
    """
    variables = {"username": username, "type": media_type.upper()}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://graphql.anilist.co", json={"query": query, "variables": variables}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"AniList API non-200 ({resp.status}) for {username}: {text[:200]}")
                    return []
                data = await resp.json()
    except Exception as e:
        logger.error(f"HTTP error during AniList fetch for {username}: {e}", exc_info=True)
        return []

    # defensive checks
    mlc = (data.get("data") or {}).get("MediaListCollection")
    if not mlc:
        logger.warning(f"AniList returned no MediaListCollection for {username}: {data}")
        return []

    seen: Dict[int, Dict] = {}  # media_id -> entry
    try:
        lists = mlc.get("lists", [])
        for media_list in lists:
            for entry in media_list.get("entries", []):
                media = entry.get("media") or {}
                media_id = media.get("id")
                if not media_id:
                    continue

                title_block = media.get("title") or {}
                title = title_block.get("romaji") or title_block.get("english") or title_block.get("native") or "Unknown Title"

                status_raw = (entry.get("status") or "").upper()
                status_norm = _STATUS_MAP.get(status_raw, status_raw.lower() or "unknown")

                progress_raw = entry.get("progress") or 0
                # choose episodes/chapters/volumes as appropriate later; here just build a generic "done/total"
                if media.get("type") == "MANGA":
                    prog_str = f"{progress_raw}/{media.get('chapters') or media.get('volumes') or '?'}"
                else:
                    prog_str = f"{progress_raw}/{media.get('episodes') or '?'}"

                start = entry.get("startedAt") or {}
                start_date = f"{start.get('year')}-{start.get('month')}-{start.get('day')}" if start.get('year') else None
                finish = entry.get("completedAt") or {}
                finish_date = f"{finish.get('year')}-{finish.get('month')}-{finish.get('day')}" if finish.get('year') else None

                updated_ts = int(entry.get("updatedAt") or 0)

                item = {
                    "anilist_id": media_id,
                    "title": title,
                    "status": status_norm,
                    "progress": prog_str,
                    "rating": entry.get("score"),
                    "tags": [],  # DB placeholder (fill after if you store user tags)
                    "start_date": start_date or "0000-00-00",
                    "finish_date": finish_date or "0000-00-00",
                    "rewatch_count": entry.get("repeat", 0),
                    "last_updated": datetime.datetime.fromtimestamp(updated_ts if updated_ts else int(datetime.datetime.now().timestamp())).strftime("%Y-%m-%d"),
                    "updated_ts": updated_ts,
                }

                if extended:
                    item.update({
                        "type": media.get("type"),
                        "episodes": media.get("episodes"),
                        "chapters": media.get("chapters"),
                        "volumes": media.get("volumes"),
                        "site_url": media.get("siteUrl"),
                    })

                # dedupe: keep latest updated_ts
                existing = seen.get(media_id)
                if not existing or item["updated_ts"] > existing.get("updated_ts", 0):
                    seen[media_id] = item
    except Exception as e:
        logger.error(f"Error parsing AniList response for {username}: {e}", exc_info=True)
        return []

    entries = list(seen.values())
    logger.info(f"Fetched {len(entries)} deduplicated entries for {username}")
    return entries

# -----------------------------
# Utilities & Exporter
# -----------------------------
def _safe_str(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v))
    return str(v)

def deduplicate_entries_by_id(entries: List[Dict]) -> List[Dict]:
    """Safe dedupe by anilist_id keeping latest updated_ts if present."""
    seen: Dict[int, Dict] = {}
    for e in entries:
        mid = e.get("anilist_id")
        if mid is None:
            # include items without id as-is
            key = id(e)
            seen[key] = e
            continue
        if mid not in seen:
            seen[mid] = e
        else:
            #keep one with larger updated_ts
            if e.get("updated_ts", 0) > seen[mid].get("updated_ts", 0):
                seen[mid] = e
    return list(seen.values())

async def generate_export_file(
    data: list,
    fmt: str,
    progress_cb: ProgressCallback = None,
    username: str = "Unknown",
    media_type: str = "anime"
):
    """
    Create in-memory export file.
    progress_cb(percent:int, message:str) will be called during writing.
    media_type: 'anime' | 'manga' | 'novel'
    """
    fmt = (fmt or "json").lower()
    filename = f"library_backup.{fmt}"
    buffer = io.BytesIO()

    # dedupe once more just in case
    data = deduplicate_entries_by_id(data)

    if not data:
        # produce minimal empties
        if fmt == "json":
            buffer.write(json.dumps([], indent=4).encode("utf-8"))
        elif fmt == "csv":
            buffer.write("title,status,progress,score\n".encode("utf-8"))
        elif fmt == "yaml":
            buffer.write(yaml.dump([], default_flow_style=False).encode("utf-8"))
        elif fmt == "xml":
            buffer.write(b'<?xml version="1.0" encoding="utf-8"?><myanimelist />')
        else:
            buffer.write("No entries.\n".encode("utf-8"))
        buffer.seek(0)
        if progress_cb:
            await progress_cb(100, "File generation complete (empty).")
        return buffer, filename

    # JSON & YAML: chunked write to allow progress updates for large exports
    if fmt in ("json", "yaml"):
        raw = (json.dumps(data, indent=4, ensure_ascii=False).encode("utf-8")
               if fmt == "json"
               else yaml.dump(data, sort_keys=False, allow_unicode=True).encode("utf-8"))
        total = len(raw)
        chunk = max(32_768, total // 20)
        written = 0
        while written < total:
            nxt = raw[written:written + chunk]
            buffer.write(nxt)
            written += len(nxt)
            if progress_cb:
                pct = min(100, int(written / total * 100))
                await progress_cb(pct, f"Writing {fmt.upper()} data...")
            # tiny yield
            await asyncio.sleep(0)
        buffer.seek(0)
        if progress_cb:
            await progress_cb(100, "File generation complete.")
        return buffer, filename

    # CSV: union headers and iterative rows with throttled progress updates
    if fmt == "csv":
        # union of keys (stable order: common keys first)
        keys = []
        for d in data:
            for k in d.keys():
                if k not in keys:
                    keys.append(k)
        csv_io = io.StringIO()
        writer = csv.DictWriter(csv_io, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        total = len(data)
        update_interval = max(1, total // 40)  # ~2.5% steps
        for i, row in enumerate(data):
            safe_row = {k: _safe_str(row.get(k, "")) for k in keys}
            writer.writerow(safe_row)
            if progress_cb and ((i + 1) % update_interval == 0 or i == total - 1):
                pct = min(100, int((i + 1) / total * 100))
                await progress_cb(pct, f"Writing CSV rows ({i+1}/{total})...")
            await asyncio.sleep(0)  # yield
        buffer.write(csv_io.getvalue().encode("utf-8"))
        buffer.seek(0)
        if progress_cb:
            await progress_cb(100, "CSV file complete.")
        return buffer, filename

    # TXT: simple human-readable file
    if fmt == "txt":
        header = "─────────────────────────────\nExported via /library_backup\nStay organized. Stay inspired.\n─────────────────────────────\n\n"
        buffer.write(header.encode("utf-8"))
        total = len(data)
        update_interval = max(1, total // 40)
        for i, e in enumerate(data):
            emoji = _STATUS_EMOJI.get(e.get("status", ""), "")
            line = f"{emoji} {e.get('title','')} | {e.get('status','')} | {e.get('progress','')}\n"
            buffer.write(line.encode("utf-8"))
            if progress_cb and ((i + 1) % update_interval == 0 or i == total - 1):
                pct = min(100, int((i + 1) / total * 100))
                await progress_cb(pct, f"Writing TXT entries ({i+1}/{total})...")
            await asyncio.sleep(0)
        buffer.seek(0)
        if progress_cb:
            await progress_cb(100, "TXT file complete.")
        return buffer, filename

    # Minimal AniList-valid MAL XML
    if fmt == "xml":
        total = len(data)
        node_name = "anime" if media_type == "anime" else ("novel" if media_type == "novel" else "manga")
        buffer.write(b'<?xml version="1.0" encoding="utf-8" ?>\n<myanimelist>\n')
        update_interval = max(1, total // 40)

        for i, e in enumerate(data):
            series_id = e.get("anilist_id", 0)
            status_norm = (e.get("status") or "planned").lower()
            # Map normalized status -> MAL expected label
            if media_type == "anime":
                mal_status_map = {
                    "watching": "Watching",
                    "completed": "Completed",
                    "paused": "On-Hold",
                    "dropped": "Dropped",
                    "planned": "Plan to Watch",
                }
            else:  # manga/novel: use reading/plan to read label
                mal_status_map = {
                    "watching": "Reading",
                    "completed": "Completed",
                    "paused": "On-Hold",
                    "dropped": "Dropped",
                    "planned": "Plan to Read",
                }
            status_str = mal_status_map.get(status_norm, mal_status_map.get("planned"))

            score = e.get("rating") or 0
            repeat = e.get("rewatch_count") or 0
            start_date = e.get("start_date") or "0000-00-00"
            finish_date = e.get("finish_date") or "0000-00-00"
            notes = ",".join(e.get("tags", []))

            # parse progress
            prog_parts = str(e.get("progress", "0/0")).split("/")
            done = prog_parts[0] if len(prog_parts) >= 1 else "0"
            total_val = prog_parts[1] if len(prog_parts) >= 2 else "0"

            if media_type == "anime":
                block = (
                    f"  <anime>\n"
                    f"    <series_animedb_id>{series_id}</series_animedb_id>\n"
                    f"    <my_watched_episodes>{done}</my_watched_episodes>\n"
                    f"    <my_score>{score}</my_score>\n"
                    f"    <my_status>{status_str}</my_status>\n"
                    f"    <my_times_rewatched>{repeat}</my_times_rewatched>\n"
                    f"    <my_start_date>{start_date}</my_start_date>\n"
                    f"    <my_finish_date>{finish_date}</my_finish_date>\n"
                    f"    <my_tags>{notes}</my_tags>\n"
                    f"  </anime>\n"
                )
            else:              
                if media_type == "manga":
                    tag_name = "manga"
                    id_tag = "series_mangadb_id"
                else:
                    tag_name = "novel"
                    id_tag = "series_mangadb_id"

                block = (
                    f"  <{tag_name}>\n"
                    f"    <{id_tag}>{series_id}</{id_tag}>\n"
                    f"    <my_read_chapters>{done}</my_read_chapters>\n"
                    f"    <my_read_volumes>{0}</my_read_volumes>\n"
                    f"    <my_score>{score}</my_score>\n"
                    f"    <my_status>{status_str}</my_status>\n"
                    f"    <my_times_reread>{repeat}</my_times_reread>\n"
                    f"    <my_start_date>{start_date}</my_start_date>\n"
                    f"    <my_finish_date>{finish_date}</my_finish_date>\n"
                    f"    <my_tags>{notes}</my_tags>\n"
                    f"  </{tag_name}>\n"
                )

            buffer.write(block.encode("utf-8"))

            # Throttled progress updates (every ~2.5% or so)
            if progress_cb and ((i + 1) % update_interval == 0 or i == total - 1):
                pct = min(100, int((i + 1) / total * 100))
                await progress_cb(pct, f"Writing {node_name} entries ({i+1}/{total})...")
            await asyncio.sleep(0)  # yield for responsiveness

        buffer.write(b"</myanimelist>")
        buffer.seek(0)
        if progress_cb:
            await progress_cb(100, "XML file complete.")
        return buffer, filename

    # fallback (shouldn't get here)
    buffer.write(json.dumps(data, indent=4).encode("utf-8"))
    buffer.seek(0)
    if progress_cb:
        await progress_cb(100, "File generation complete (fallback).")
    return buffer, filename

# -----------------------------
# Cog
# -----------------------------
class LibraryBackup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="library_backup",
        description="📚✨ Export your AniList library into JSON / CSV / XML (MAL-valid) / TXT / YAML"
    )
    @app_commands.describe(
        username="AniList username (optional if you've linked your account)",
        format="Choose export format",
        scope="Filter entries to export",
        media_type="Pick Anime, Manga, or Novel",
        delivery="How to deliver the file",
        extended="Include extended metadata?"
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="📝 JSON", value="json"),
            app_commands.Choice(name="📊 CSV", value="csv"),
            app_commands.Choice(name="🗂 XML (AniList/MAL minimal)", value="xml"),
            app_commands.Choice(name="📜 TXT", value="txt"),
            app_commands.Choice(name="🐍 YAML", value="yaml"),
        ],
        scope=[
            app_commands.Choice(name="🌐 Full Library", value="full"),
            app_commands.Choice(name="🏁 Completed", value="completed"),
            app_commands.Choice(name="🎬 Watching / Reading", value="watching"),
            app_commands.Choice(name="❌ Dropped", value="dropped"),
            app_commands.Choice(name="⏸ Paused", value="paused"),
            app_commands.Choice(name="📝 Planned", value="planned"),
        ],
        media_type=[
            app_commands.Choice(name="🎬 Anime", value="anime"),
            app_commands.Choice(name="📖 Manga", value="manga"),
            app_commands.Choice(name="📚 Novel", value="novel"),
        ],
        delivery=[
            app_commands.Choice(name="📩 DM (Private)", value="dm"),
            app_commands.Choice(name="💬 Channel (Public)", value="channel"),
        ],
        extended=[
            app_commands.Choice(name="✨ Yes (detailed)", value="yes"),
            app_commands.Choice(name="⚡ No (faster)", value="no"),
        ],
    )
    async def library_backup(
        self,
        interaction: discord.Interaction,
        format: app_commands.Choice[str],
        scope: app_commands.Choice[str],
        media_type: app_commands.Choice[str],
        delivery: app_commands.Choice[str],
        extended: app_commands.Choice[str],
        username: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        # Log call
        guild_id = interaction.guild.id if interaction.guild else None
        logger.info(f"/library_backup invoked by {interaction.user} ({interaction.user.id}) in guild {guild_id}")
        logger.debug(f"params: username={username} format={format.value} scope={scope.value} media={media_type.value} delivery={delivery.value} extended={extended.value} tag={tag}")

        # If username not provided, try DB lookup
        auto_detected = False
        if not username:
            username = await get_anilist_username_from_db(interaction.user.id, guild_id)
            if not username:
                # show register guidance view
                class RegisterView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=300)

                    @discord.ui.button(label="📝 Register / Link AniList", style=discord.ButtonStyle.green, emoji="🔗")
                    async def register(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != interaction.user.id:
                            await button_interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
                            return
                        await button_interaction.response.send_message("🔎 Use `/login` to link your AniList account (or provide `username` parameter).", ephemeral=True)

                    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red, emoji="❌")
                    async def cancel(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        if button_interaction.user.id != interaction.user.id:
                            await button_interaction.response.send_message("❌ This button is not for you.", ephemeral=True)
                            return
                        await button_interaction.response.edit_message(embed=discord.Embed(title="Cancelled", description="Library backup cancelled.", color=discord.Color.red()), view=None)

                embed = discord.Embed(
                    title="❌ AniList Username Required",
                    description=(
                        "I couldn't find your linked AniList account.\n\n"
                        "• Use `/login` to link your AniList account\n"
                        "• Or run this command again and provide the `username` parameter\n\n"
                        "*Once linked, you won't need to enter your username again.*"
                    ),
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Tip: Link your account once and forget it ✨")
                await interaction.response.send_message(embed=embed, view=RegisterView(), ephemeral=True)
                return
            auto_detected = True

        # send initial ephemeral progress embed
        initial_embed = discord.Embed(
            title="📚✨ Generating Library Backup...",
            description="⏳ Fetching data from AniList...\n\nProgress: `░░░░░░░░░░░░░░░░░░░░ 0%`",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=initial_embed, ephemeral=True)
        try:
            progress_msg = await interaction.original_response()
        except Exception:
            # fallback: send a followup ephemeral message
            progress_msg = await interaction.followup.send(embed=initial_embed, ephemeral=True, wait=True)

        # progress editor (20-step bar). throttles updates to when percent changes.
        last_percent = -1

        async def edit_progress(percent: int, sub_msg: Optional[str] = None):
            nonlocal last_percent
            pct = max(0, min(100, int(percent)))
            if pct == last_percent:
                return
            last_percent = pct
            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = "▓" * filled + "░" * (bar_len - filled)
            desc = f"{sub_msg or 'Working...'}\n\nProgress: `{bar} {pct}%`"
            embed = discord.Embed(title="📚✨ Generating Library Backup...", description=desc, color=discord.Color.blurple())
            embed.set_footer(text="Every story you’ve tracked, now archived in your hands ✨")
            try:
                await progress_msg.edit(embed=embed)
            except Exception:
                # if edit fails silently ignore (user might have closed message)
                logger.debug("Failed to edit progress message (may be missing).")

        # 1) Fetch AniList data
        await edit_progress(3, "Fetching AniList data...")
        try:
            user_library = await fetch_anilist_library(username, media_type.value, extended=(extended.value == "yes"))
        except Exception as e:
            logger.error(f"Error fetching AniList data for {username}: {e}", exc_info=True)
            await edit_progress(0, "Failed to fetch AniList data.")
            await progress_msg.edit(embed=discord.Embed(title="❌ Error", description="Failed to fetch AniList data. Try again later.", color=discord.Color.red()))
            return

        if not user_library:
            await progress_msg.edit(embed=discord.Embed(title="❌ No Data", description="Your AniList library is empty or private.", color=discord.Color.orange()))
            return

        await edit_progress(12, "Processing entries...")

        # 2) Optional tag filter (DB-powered placeholder)
        if tag:
            # If you store per-entry tags in DB, filter here. Placeholder: no-op for now.
            logger.debug(f"Filtering by tag requested ({tag}) but tag filtering is DB-backed and not implemented.")

        # 3) Scope filter
        if scope.value != "full":
            filtered = [e for e in user_library if e.get("status", "").lower() == scope.value]
        else:
            filtered = user_library

        # 4) Deduplicate by anilist id (keeps latest updated_ts). fetch already dedupes, but be defensive
        filtered = deduplicate_entries_by_id(filtered)

        if not filtered:
            await progress_msg.edit(embed=discord.Embed(
                title="📝 No Data Found",
                description=(f"No entries matched your criteria for **{username}** in **{scope.name}**."),
                color=discord.Color.orange()
            ))
            return

        # final prep before writing
        await edit_progress(28, "Preparing file writer...")

        try:
            file_buf, filename = await generate_export_file(
                filtered,
                format.value,
                progress_cb=edit_progress,
                username=username,
                media_type=media_type.value
            )
        except Exception as e:
            logger.error(f"Error generating file for {username}: {e}", exc_info=True)
            await progress_msg.edit(embed=discord.Embed(title="❌ Export Failed", description="An error occurred while generating the file.", color=discord.Color.red()))
            return

        # Build final confirmation embed
        confirm = discord.Embed(
            title="✅ Backup Ready!",
            description=(
                f"**User:** `{username}`\n"
                f"**File:** `{filename}`\n"
                f"**Format:** {format.name}\n"
                f"**Scope:** {scope.name}\n"
                f"**Type:** {media_type.name}\n"
                f"**Entries:** {len(filtered)}"
            ),
            color=discord.Color.green()
        )
        confirm.set_footer(text="Exported via /library_backup • Keep your library yours ✨")

        file = discord.File(fp=file_buf, filename=filename)

        # Deliver file
        if delivery.value == "dm":
            try:
                await interaction.user.send(embed=confirm, file=file)
                await progress_msg.edit(embed=discord.Embed(title="📬 Sent!", description="Your backup was delivered to your DMs.", color=discord.Color.green()))
                logger.info(f"Backup DM sent to {interaction.user.id}: {filename} ({len(filtered)} entries)")
            except discord.Forbidden:
                logger.warning(f"Failed to DM {interaction.user.id} (for backup).")
                await progress_msg.edit(embed=discord.Embed(title="❌ DM Failed", description="I couldn't send the DM. Please allow direct messages or choose Channel delivery.", color=discord.Color.red()))
        else:
            # show confirmation in ephemeral message and post file to channel (public)
            try:
                await progress_msg.edit(embed=confirm)
                await interaction.followup.send(file=file, ephemeral=False)
                logger.info(f"Backup sent in channel by {interaction.user.id}: {filename} ({len(filtered)} entries)")
            except Exception as e:
                logger.error(f"Failed to send backup in channel for {interaction.user.id}: {e}", exc_info=True)
                await progress_msg.edit(embed=discord.Embed(title="❌ Send Failed", description="Could not send file to channel. Check permissions.", color=discord.Color.red()))

# -----------------------------
# Cog Setup
# -----------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(LibraryBackup(bot))
    logger.info("Library Backup cog loaded successfully")

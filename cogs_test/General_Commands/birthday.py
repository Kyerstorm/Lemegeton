# birthday.py
# Multi-guild Birthday Cog (single-file)
# - /birthday group: set/view/remove/list
# - /birthday admin (dashboard): single dropdown select; live-updating embed
# - SQLite backend
# - Uses a provided PNG card (downloaded & cached) instead of on-the-fly image generation
# - 50 randomized generous message templates for previews/announcements

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import asyncio
import random
import os
import io
import re
import typing
import logging
import aiohttp

# ------------------------
# Config & logging
# ------------------------
logger = logging.getLogger("birthday_cog")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)

DB_PATH = os.getenv("BIRTHDAY_DB_PATH", "birthdays.db")
CHECK_INTERVAL_SECONDS = 60
DEFAULT_TZ_OFFSET = 0.0

CARD_URL = "https://i.postimg.cc/rFtH6FM0/Pink-Watercolor-Floral-Happy-Birthday-Greeting-Card.png"
CARD_FILENAME = "birthday_card.png"

CELEB_EMOJIS = ["🎉", "🎂", "🥳", "🎈", "🍰", "🧁", "✨", "🌟", "🎁", "💫"]
PINK_COLOR = discord.Color.from_rgb(240, 182, 210)  # soft pink to match the card

# 50 generous/random templates (short examples; you can edit them)
MESSAGE_TEMPLATES = [
    "Wishing you a day filled with laughter and cake — happiest birthday!",
    "Another year of greatness. Celebrate like a legend!",
    "Warm wishes and huge hugs — may this year be your best yet.",
    "Turn the music up — today’s about you. Enjoy every moment!",
    "Candles, wishes, and all the good vibes. Happy birthday!",
    "To many more wins, laughs, and late-night snacks. Have a blast!",
    "You deserve every slice of joy today. Happy birthday!",
    "May your day be bright, sweet, and unforgettable.",
    "Here’s to you — another trip around the sun. Shine on!",
    "Big cheers for you today — keep being incredible.",
    "Hope your birthday sparkles as much as you do!",
    "From small joys to big adventures — may this year bring both.",
    "Celebrate wildly — the world’s better with you in it.",
    "Warm cake, warm hearts, and a warm day — happy birthday!",
    "Make a wish, then make it happen. Happy birthday!",
    "You’re a masterpiece — enjoy your special day.",
    "Blessings, cake, and hilarious memories — have them all.",
    "Keep slaying — this year is yours.",
    "Birthday hugs and a little chaos — enjoy it all.",
    "Wishing you sunshine, smiles, and a table full of cake.",
    "Another year bolder, wiser, and even more awesome.",
    "May your day be as bright and lovely as you are.",
    "Celebrate loud, rest later — happy birthday!",
    "A toast to you: health, joy, and ridiculous fun.",
    "Dance until the candles melt. Happy birthday!",
    "Good vibes only today — you earned them.",
    "Sweets, friends, and mischief. Enjoy every bit.",
    "Here’s to new dreams and fresh starts — happiest birthday.",
    "Wrapped in love and sprinkled with confetti — cheers!",
    "Have cake, will party. Make this day legendary.",
    "May surprises be kind and memories plentiful.",
    "You’re the main character today — act accordingly.",
    "So much love for everything you are. Happy birthday!",
    "May your inbox be full of adoration and gifts.",
    "Birthday energy: maximum. Have the best one yet.",
    "Wishing you small moments of peace and huge moments of joy.",
    "Another year, another reason to celebrate you.",
    "Live it up, laugh hard, and love loudly today.",
    "May your cup overflow with good things this year.",
    "Rise, shine, and eat cake. Repeat.",
    "Today’s forecast: 100% celebration with a chance of cake.",
    "You make the world sweeter — enjoy your day.",
    "Keep that sparkle — happy birthday, superstar!",
    "May this year bring new chances and wicked fun.",
    "Hug big, laugh loud, love always — happy birthday!",
    "You are cherished. Celebrate like royalty today.",
    "All the best things to you today and always."
]

# ------------------------
# Utilities
# ------------------------
def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def now_utc():
    return datetime.datetime.utcnow()

def pretty_date(month: int, day: int):
    try:
        d = datetime.date(2000, month, day)
        return d.strftime("%B %d")
    except Exception:
        return f"{month}/{day}"

def parse_tz_offset(s: str) -> float:
    s = str(s).strip().lower().replace("utc", "").strip()
    m = re.match(r"([+-])?(\d{1,2})(?::(\d{2}))?(?:\.(\d+))?", s)
    if not m:
        try:
            return float(s)
        except Exception:
            return DEFAULT_TZ_OFFSET
    sign = -1 if m.group(1) == "-" else 1
    hours = int(m.group(2) or 0)
    mins = int(m.group(3) or 0)
    frac = float("0." + m.group(4)) if m.group(4) else 0.0
    return sign * (hours + mins / 60 + frac)

# Date parsing tolerant (keeps earlier logic)
DATE_REGEXES = [
    (re.compile(r"^(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})$"), "ymd"),
    (re.compile(r"^(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{2,4})$"), "mdy"),
    (re.compile(r"^(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})$"), "dmy"),
    (re.compile(r"^(?P<mn>[A-Za-z]+)\s+(?P<d>\d{1,2})(?:,?\s*(?P<y>\d{4}))?$"), "mn_d_y"),
]
MONTHS = {k: i for i, k in enumerate(["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])}

def parse_date_fuzzy(s: str) -> typing.Optional[datetime.date]:
    s0 = (s or "").strip()
    if not s0:
        return None
    for pat, kind in DATE_REGEXES:
        m = pat.match(s0)
        if not m:
            continue
        gd = m.groupdict()
        try:
            if kind == "ymd":
                return datetime.date(int(gd["y"]), int(gd["m"]), int(gd["d"]))
            if kind in ("mdy", "dmy"):
                y = int(gd.get("y") or 1900)
                if y < 100:
                    y = 2000 + y if y < 70 else 1900 + y
                mth = int(gd["m"])
                d = int(gd["d"])
                if kind == "dmy":
                    mth, d = d, mth
                return datetime.date(y, mth, d)
            if kind == "mn_d_y":
                mn = gd.get("mn").lower()
                mth = None
                for i in range(1, 13):
                    if MONTHS[i].lower().startswith(mn[:3]):
                        mth = i
                        break
                if not mth:
                    continue
                d = int(gd["d"])
                y = int(gd.get("y") or 1900)
                if y < 100:
                    y = 2000 + y if y < 70 else 1900 + y
                return datetime.date(y, mth, d)
        except Exception:
            continue
    # fallback attempt via dateutil if available
    try:
        from dateutil import parser as _p
        dt = _p.parse(s0, default=datetime.datetime(2000, 1, 1))
        return dt.date()
    except Exception:
        pass
    return None

# ------------------------
# Database
# ------------------------
class BirthdayDB:
    def __init__(self, path=DB_PATH):
        ensure_dir(path)
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL,
                year INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(guild_id, user_id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                tz_offset REAL DEFAULT 0,
                mention_mode TEXT DEFAULT 'none',
                mention_role_id INTEGER,
                enabled INTEGER DEFAULT 1,
                template TEXT,
                check_hour INTEGER DEFAULT -1,
                last_triggered TEXT
            );
        """)
        self.conn.commit()

    # birthdays
    def upsert(self, guild_id: int, user_id: int, month: int, day: int, year: typing.Optional[int] = None):
        now = datetime.datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute("""INSERT INTO birthdays (guild_id,user_id,month,day,year,created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(guild_id,user_id) DO UPDATE SET month=excluded.month,day=excluded.day,year=excluded.year,created_at=excluded.created_at
        """, (guild_id, user_id, month, day, year, now))
        self.conn.commit()

    def remove(self, guild_id: int, user_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        self.conn.commit()
        return cur.rowcount

    def get(self, guild_id: int, user_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        r = cur.fetchone()
        return dict(r) if r else None

    def by_month_day(self, guild_id: int, month: int, day: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? AND month=? AND day=?", (guild_id, month, day))
        return [dict(x) for x in cur.fetchall()]

    def list_for_guild(self, guild_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? ORDER BY month,day", (guild_id,))
        return [dict(x) for x in cur.fetchall()]

    # config
    def set_config(self, guild_id: int, **kwargs):
        existing = self.get_config(guild_id)
        cur = self.conn.cursor()
        if existing is None:
            cur.execute("""INSERT INTO guild_config (guild_id, channel_id, tz_offset, mention_mode, mention_role_id, enabled, template, check_hour, last_triggered)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                guild_id,
                kwargs.get("channel_id"),
                kwargs.get("tz_offset", DEFAULT_TZ_OFFSET),
                kwargs.get("mention_mode", "none"),
                kwargs.get("mention_role_id"),
                1 if kwargs.get("enabled", True) else 0,
                kwargs.get("template"),
                kwargs.get("check_hour", -1),
                kwargs.get("last_triggered"),
            ))
        else:
            parts = []
            vals = []
            for k in ("channel_id", "tz_offset", "mention_mode", "mention_role_id", "enabled", "template", "check_hour", "last_triggered"):
                if k in kwargs:
                    parts.append(f"{k}=?")
                    v = kwargs[k]
                    if k == "enabled":
                        v = 1 if v else 0
                    vals.append(v)
            if parts:
                vals.append(guild_id)
                cur.execute("UPDATE guild_config SET " + ",".join(parts) + " WHERE guild_id=?", tuple(vals))
        self.conn.commit()

    def get_config(self, guild_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def all_configs(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM guild_config")
        return [dict(x) for x in cur.fetchall()]

    def set_last_triggered(self, guild_id: int, iso_str: str):
        self.set_config(guild_id, last_triggered=iso_str)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

# ------------------------
# Admin UI components (single select + live embed updates)
# ------------------------
class AdminSelect(discord.ui.Select):
    def __init__(self, cog: "BirthdayCog", guild: discord.Guild):
        options = [
            discord.SelectOption(label="Set Channel", value="set_channel", description="Set channel to post birthday announcements", emoji="📣"),
            discord.SelectOption(label="Set Timezone", value="set_tz", description="Set timezone offset like +3 or -04:30", emoji="🌐"),
            discord.SelectOption(label="Set Mention Mode", value="set_mention", description="None / Mention users / Mention role", emoji="🔔"),
            discord.SelectOption(label="Set Role", value="set_role", description="Role to ping when mention-mode=role", emoji="🛡️"),
            discord.SelectOption(label="Set Template", value="set_template", description="Customize announcement message", emoji="📝"),
            discord.SelectOption(label="Toggle Enable", value="toggle_enabled", description="Enable or disable announcements", emoji="⏯️"),
            discord.SelectOption(label="Set Check Hour", value="set_check_hour", description="Set local hour 0-23 or -1 = every minute", emoji="⏰"),
            discord.SelectOption(label="Preview", value="preview", description="Send a birthday preview DM", emoji="👀"),
            discord.SelectOption(label="Force Run Today", value="force_run", description="Send today's announcements now", emoji="🚨"),
            discord.SelectOption(label="Export CSV", value="export_csv", description="Export birthdays as CSV to your DMs", emoji="📤"),
            discord.SelectOption(label="Import CSV Hint", value="import_csv", description="How to import birthdays via /birthday import_csv", emoji="📥"),
        ]
        super().__init__(placeholder="Choose an admin action...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
            return
        val = self.values[0]
        try:
            if val == "set_channel":
                await self._set_channel_modal(interaction)
            elif val == "set_tz":
                await self._set_tz_modal(interaction)
            elif val == "set_mention":
                await self._choose_mention_mode(interaction)
            elif val == "set_role":
                await self._set_role_modal(interaction)
            elif val == "set_template":
                await self._set_template_modal(interaction)
            elif val == "toggle_enabled":
                await self._toggle_enabled(interaction)
            elif val == "set_check_hour":
                await self._set_check_hour_modal(interaction)
            elif val == "preview":
                await self._preview(interaction)
            elif val == "force_run":
                await self._force_run(interaction)
            elif val == "export_csv":
                await self._export_csv(interaction)
            elif val == "import_csv":
                await self._show_import_hint(interaction)
            else:
                await interaction.response.send_message("Unknown action.", ephemeral=True)
        except Exception as e:
            logger.exception("AdminSelect callback failed: %s", e)
            try:
                await interaction.response.send_message(f"Action failed: {e}", ephemeral=True)
            except Exception:
                pass

    # Modal & action implementations
    async def _set_channel_modal(self, interaction: discord.Interaction):
        class ChannelModal(discord.ui.Modal, title="Set birthday channel"):
            channel = discord.ui.TextInput(label="Channel", placeholder="#birthdays or 123456789012345678", required=True, max_length=128)
            async def on_submit(self_, modal_interaction: discord.Interaction):
                raw = modal_interaction.channel.value.strip()
                ch = None
                mm = re.match(r'^<#?(\d+)>?$', raw)
                try:
                    if mm:
                        cid = int(mm.group(1))
                        ch = interaction.guild.get_channel(cid) or await interaction.guild.fetch_channel(cid)
                    elif raw.isdigit():
                        cid = int(raw)
                        ch = interaction.guild.get_channel(cid) or await interaction.guild.fetch_channel(cid)
                    else:
                        name = raw.lstrip('#')
                        for c in interaction.guild.text_channels:
                            if c.name == name:
                                ch = c
                                break
                except Exception:
                    ch = None
                if not ch:
                    await modal_interaction.response.send_message("Could not resolve channel. Check the name/ID and that I can see it.", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, channel_id=ch.id)
                await modal_interaction.response.send_message(f"✅ Birthday channel set to {ch.mention}.", ephemeral=True)
                # update the dashboard embed in-place
                await update_dashboard_message(interaction, self.cog)

        await interaction.response.send_modal(ChannelModal())

    async def _set_tz_modal(self, interaction: discord.Interaction):
        class TZModal(discord.ui.Modal, title="Set timezone"):
            tz = discord.ui.TextInput(label="Offset", placeholder="+3 or -04:30", required=True, max_length=16)
            async def on_submit(self_, modal_interaction: discord.Interaction):
                raw = modal_interaction.tz.value.strip()
                parsed = parse_tz_offset(raw)
                self.cog.db.set_config(self.guild.id, tz_offset=parsed)
                await modal_interaction.response.send_message(f"✅ Timezone set to UTC{parsed:+g}.", ephemeral=True)
                await update_dashboard_message(interaction, self.cog)
        await interaction.response.send_modal(TZModal())

    async def _choose_mention_mode(self, interaction: discord.Interaction):
        class MentionView(discord.ui.View):
            @discord.ui.select(placeholder="Mention mode", min_values=1, max_values=1, options=[
                discord.SelectOption(label="None", value="none", description="No pings"),
                discord.SelectOption(label="Mention users", value="mention", description="Ping birthday users"),
                discord.SelectOption(label="Mention role", value="role", description="Ping configured role"),
            ])
            async def select_callback(self_, select_interaction: discord.Interaction):
                mode = select_interaction.data["values"][0]
                self.cog.db.set_config(self.guild.id, mention_mode=mode)
                await select_interaction.response.send_message(f"✅ Mention mode set to `{mode}`.", ephemeral=True)
                await update_dashboard_message(interaction, self.cog)
        await interaction.response.send_message("Choose mention mode:", view=MentionView(), ephemeral=True)

    async def _set_role_modal(self, interaction: discord.Interaction):
        class RoleModal(discord.ui.Modal, title="Set role to mention"):
            role = discord.ui.TextInput(label="Role", placeholder="@Birthdays or 123456789012345678", required=True, max_length=128)
            async def on_submit(self_, modal_interaction: discord.Interaction):
                raw = modal_interaction.role.value.strip()
                role = None
                mm = re.match(r'^<@&?(\d+)>?$', raw)
                try:
                    if mm:
                        rid = int(mm.group(1))
                        role = interaction.guild.get_role(rid)
                    elif raw.isdigit():
                        role = interaction.guild.get_role(int(raw))
                    else:
                        name = raw.lstrip('@')
                        for r in interaction.guild.roles:
                            if r.name == name:
                                role = r
                                break
                except Exception:
                    role = None
                if not role:
                    await modal_interaction.response.send_message("Could not resolve role. Make sure I can see it and you typed it correctly.", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, mention_role_id=role.id)
                await modal_interaction.response.send_message(f"✅ Mention role set to {role.mention}.", ephemeral=True)
                await update_dashboard_message(interaction, self.cog)
        await interaction.response.send_modal(RoleModal())

    async def _set_template_modal(self, interaction: discord.Interaction):
        class TemplateModal(discord.ui.Modal, title="Set announcement template"):
            tmpl = discord.ui.TextInput(label="Template", style=discord.TextStyle.long, placeholder="Use placeholders: {emoji} {users} {guild} {age_map} {card}", required=True, max_length=1500)
            async def on_submit(self_, modal_interaction: discord.Interaction):
                tx = modal_interaction.tmpl.value.strip()
                if len(tx) > 2000:
                    await modal_interaction.response.send_message("Template too long (2000 char limit).", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, template=tx)
                await modal_interaction.response.send_message("✅ Template saved.", ephemeral=True)
                await update_dashboard_message(interaction, self.cog)
        await interaction.response.send_modal(TemplateModal())

    async def _toggle_enabled(self, interaction: discord.Interaction):
        cfg = self.cog.db.get_config(self.guild.id) or {}
        cur = bool(cfg.get("enabled", 1))
        self.cog.db.set_config(self.guild.id, enabled=(not cur))
        await interaction.response.send_message(f"✅ Birthdays enabled: {not cur}", ephemeral=True)
        await update_dashboard_message(interaction, self.cog)

    async def _set_check_hour_modal(self, interaction: discord.Interaction):
        class HourModal(discord.ui.Modal, title="Set check hour"):
            hour = discord.ui.TextInput(label="Hour", placeholder="-1 (every minute) or 0-23", required=True, max_length=4)
            async def on_submit(self_, modal_interaction: discord.Interaction):
                try:
                    h = int(modal_interaction.hour.value.strip())
                    if h < -1 or h > 23:
                        raise ValueError()
                except Exception:
                    await modal_interaction.response.send_message("Invalid hour. Must be -1..23", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, check_hour=h)
                await modal_interaction.response.send_message(f"✅ Check hour set to {h}.", ephemeral=True)
                await update_dashboard_message(interaction, self.cog)
        await interaction.response.send_modal(HourModal())

    async def _preview(self, interaction: discord.Interaction):
        # Build preview: pick up to 3 sample users (or the command user)
        cfg = self.cog.db.get_config(self.guild.id) or {}
        rows = self.cog.db.list_for_guild(self.guild.id)[:3] or [{"user_id": interaction.user.id, "month": now_utc().month, "day": now_utc().day, "year": None}]
        members = []
        mentions = []
        for r in rows:
            try:
                m = interaction.guild.get_member(int(r['user_id']))
            except Exception:
                m = None
            if m:
                members.append(m)
                mentions.append(m.mention)
            else:
                mentions.append(f"<@{r['user_id']}>")
        # choose a random generous template
        template = random.choice(MESSAGE_TEMPLATES)
        emoji = "🎂"
        users_str = ", ".join(mentions)
        # prepare embed
        em = discord.Embed(title=f"{emoji} Birthday Preview {emoji}", description=f"{template}\n\n{users_str}", color=PINK_COLOR)
        em.add_field(name="When", value=pretty_date(now_utc().month, now_utc().day), inline=True)
        em.set_footer(text=f"Preview for {interaction.guild.name}")
        # fetch image bytes and attach
        img_bytes = await self.cog.get_card_bytes()
        files = []
        if img_bytes:
            files = [discord.File(io.BytesIO(img_bytes), filename=CARD_FILENAME)]
            em.set_image(url=f"attachment://{CARD_FILENAME}")
        try:
            dm = await interaction.user.create_dm()
            await dm.send(embed=em, files=files)
            await interaction.response.send_message("✅ Preview sent to your DMs.", ephemeral=True)
        except Exception:
            # fallback: show ephemeral with embed (can't attach file in ephemeral message), so send embed without image
            await interaction.response.send_message("Could not DM you (maybe DMs closed). Showing preview here (no image).", ephemeral=True)
            await interaction.followup.send(embed=em, ephemeral=True)

    async def _force_run(self, interaction: discord.Interaction):
        cfg = self.cog.db.get_config(self.guild.id) or {}
        tz = float(cfg.get("tz_offset") or DEFAULT_TZ_OFFSET)
        local = now_utc() + datetime.timedelta(hours=tz)
        rows = self.cog.db.by_month_day(self.guild.id, local.month, local.day)
        if not rows:
            await interaction.response.send_message("No birthdays found for today in this server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.cog._announce_birthdays(self.guild, cfg, rows, local)
            await interaction.followup.send("Announcements sent (or attempted).", ephemeral=True)
            await update_dashboard_message(interaction, self.cog)
        except Exception as e:
            logger.exception("Force run failed: %s", e)
            await interaction.followup.send("Error while trying to announce.", ephemeral=True)

    async def _export_csv(self, interaction: discord.Interaction):
        rows = self.cog.db.list_for_guild(self.guild.id)
        if not rows:
            await interaction.response.send_message("No birthdays to export.", ephemeral=True)
            return
        out = io.StringIO()
        out.write("user_id,month,day,year,created_at\n")
        for r in rows:
            out.write(f"{r['user_id']},{r['month']},{r['day']},{r.get('year') or ''},{r.get('created_at')}\n")
        out.seek(0)
        try:
            dm = await interaction.user.create_dm()
            await dm.send(file=discord.File(io.BytesIO(out.getvalue().encode('utf-8')), filename="birthdays_export.csv"))
            await interaction.response.send_message("✅ CSV exported to your DMs.", ephemeral=True)
        except Exception as e:
            logger.exception("Export DM failed: %s", e)
            await interaction.response.send_message("Could not send DM with CSV.", ephemeral=True)

    async def _show_import_hint(self, interaction: discord.Interaction):
        await interaction.response.send_message("To import birthdays: use `/birthday import_csv` and attach a CSV file with columns `user_id,month,day,year`.", ephemeral=True)

class AdminView(discord.ui.View):
    def __init__(self, cog: "BirthdayCog", guild: discord.Guild):
        super().__init__(timeout=600)
        self.add_item(AdminSelect(cog, guild))

# ------------------------
# Helper to update dashboard embed live
# ------------------------
async def build_dashboard_embed(cog: "BirthdayCog", guild: discord.Guild) -> discord.Embed:
    cfg = cog.db.get_config(guild.id) or {}
    enabled = bool(cfg.get("enabled", 1))
    channel = None
    if cfg.get("channel_id"):
        try:
            channel = guild.get_channel(int(cfg["channel_id"]))
        except Exception:
            channel = None
    tz = float(cfg.get("tz_offset") or DEFAULT_TZ_OFFSET)
    mention_mode = cfg.get("mention_mode") or "none"
    role = None
    if cfg.get("mention_role_id"):
        try:
            role = guild.get_role(int(cfg["mention_role_id"]))
        except Exception:
            role = None
    template_set = bool(cfg.get("template"))
    check_hour = int(cfg.get("check_hour", -1) or -1)
    em = discord.Embed(title="🎂 Birthday Admin Dashboard 🎂", color=PINK_COLOR, description=f"Manage birthday announcements for **{guild.name}**")
    em.add_field(name="📣 Channel", value=(channel.mention if channel else "Not set"), inline=True)
    em.add_field(name="🌐 Timezone", value=f"UTC{tz:+g}", inline=True)
    em.add_field(name="🔔 Mention Mode", value=f"{mention_mode}" + (f" • {role.name}" if role else ""), inline=True)
    em.add_field(name="📝 Template", value=("Custom" if template_set else "Default"), inline=True)
    em.add_field(name="⏯️ Enabled", value=str(enabled), inline=True)
    em.add_field(name="⏰ Check Hour", value=str(check_hour), inline=True)
    em.set_footer(text="Use the dropdown to modify settings. Changes update this panel live.")
    # attach the card as thumbnail if available (can't attach file here, but we can set an icon emoji)
    em.set_thumbnail(url="https://i.postimg.cc/rFtH6FM0/Pink-Watercolor-Floral-Happy-Birthday-Greeting-Card.png")
    return em

async def update_dashboard_message(interaction: discord.Interaction, cog: "BirthdayCog"):
    try:
        em = await build_dashboard_embed(cog, interaction.guild)
        # edit original message (select's parent message is interaction.message)
        try:
            await interaction.message.edit(embed=em, view=AdminView(cog, interaction.guild))
        except Exception:
            # fallback: reply with updated embed ephemeral
            await interaction.followup.send("Dashboard updated (couldn't edit original).", embed=em, ephemeral=True)
    except Exception as e:
        logger.exception("Failed to update dashboard embed: %s", e)

# ------------------------
# Birthday Cog
# ------------------------
class BirthdayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = BirthdayDB()
        # Defer creating the aiohttp session and starting background tasks
        # until the cog is loaded in an async context.
        self._card_bytes = None
        self._card_last_fetch = None
        self._aio = None
        logger.info("BirthdayCog initialized with DB at %s", self.db.path)

    async def cog_load(self):
        # create session and start background checker in async lifecycle
        self._aio = aiohttp.ClientSession()
        try:
            self._checker.start()
        except Exception:
            # if already running or cannot start, ignore
            pass

    def cog_unload(self):
        self._checker.cancel()
        try:
            asyncio.create_task(self._aio.close())
        except Exception:
            pass
        self.db.close()

    async def get_card_bytes(self) -> typing.Optional[bytes]:
        # cache card bytes in memory for 10 minutes
        now = datetime.datetime.utcnow()
        if self._card_bytes and self._card_last_fetch and (now - self._card_last_fetch).total_seconds() < 600:
            return self._card_bytes
        try:
            async with self._aio.get(CARD_URL, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    self._card_bytes = data
                    self._card_last_fetch = now
                    return data
                else:
                    logger.warning("Card download failed: status %s", resp.status)
                    return None
        except Exception as e:
            logger.exception("Card download failed: %s", e)
            return None

    # Background checker
    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def _checker(self):
        try:
            configs = {int(row['guild_id']): row for row in self.db.all_configs()}
            for g in self.bot.guilds:
                if g.id not in configs:
                    self.db.set_config(g.id, tz_offset=DEFAULT_TZ_OFFSET, enabled=True, check_hour=-1)
                    configs[g.id] = self.db.get_config(g.id)
        except Exception as e:
            logger.exception("Error loading configs: %s", e)
            return

        now = now_utc()
        for guild in list(self.bot.guilds):
            cfg = configs.get(guild.id) or self.db.get_config(guild.id)
            if not cfg:
                continue
            if not cfg.get("enabled", 1):
                continue
            tz = float(cfg.get("tz_offset") or DEFAULT_TZ_OFFSET)
            local = now + datetime.timedelta(hours=tz)
            local_date = local.date()
            check_hour = int(cfg.get("check_hour", -1) or -1)
            if check_hour >= 0 and local.hour != check_hour:
                continue
            last = cfg.get("last_triggered")
            iso = local_date.isoformat()
            if last == iso:
                continue
            rows = self.db.by_month_day(guild.id, local_date.month, local_date.day)
            if not rows:
                if check_hour >= 0:
                    self.db.set_last_triggered(guild.id, iso)
                continue
            try:
                await self._announce_birthdays(guild, cfg, rows, local)
                self.db.set_last_triggered(guild.id, iso)
            except Exception as e:
                logger.exception("Failed to announce in guild %s: %s", guild.id, e)

    @_checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()
        logger.info("Birthday checker started.")

    async def _announce_birthdays(self, guild: discord.Guild, cfg: dict, rows: list, local_dt: datetime.datetime):
        # determine channel
        channel = None
        if cfg.get("channel_id"):
            try:
                channel = guild.get_channel(int(cfg["channel_id"])) or await self.bot.fetch_channel(int(cfg["channel_id"]))
            except Exception:
                channel = None
        if not channel:
            channel = guild.system_channel
        if not channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if not channel:
            logger.warning("No channel to send birthday announcement for guild %s", guild.id)
            return

        mentions = []
        members = []
        ages = {}
        for r in rows:
            uid = int(r['user_id'])
            try:
                m = guild.get_member(uid) or await guild.fetch_member(uid)
            except Exception:
                m = None
            if m:
                members.append(m)
                mentions.append(m.mention)
            else:
                mentions.append(f"<@{uid}>")
            if r.get("year"):
                try:
                    ages[uid] = (local_dt.date().year - int(r["year"]))
                except Exception:
                    pass

        users_str = ", ".join(mentions)
        emoji = random.choice(CELEB_EMOJIS)
        # pick a random generous template
        template = random.choice(MESSAGE_TEMPLATES)
        subtitle = f"{pretty_date(local_dt.month, local_dt.day)}"
        # prepare embed
        em = discord.Embed(title=f"{emoji} Happy Birthday! {emoji}", description=f"{template}\n\n{users_str}", color=PINK_COLOR)
        if ages:
            age_str = ", ".join(f"<@{uid}>: {a}" for uid, a in ages.items())
            em.add_field(name="Ages", value=age_str, inline=False)
        em.add_field(name="When", value=subtitle, inline=True)
        mention_mode = cfg.get("mention_mode") or "none"
        ping_text = ""
        if mention_mode == "mention":
            ping_text = " ".join(mentions)
        elif mention_mode == "role" and cfg.get("mention_role_id"):
            ping_text = f"<@&{int(cfg['mention_role_id'])}>"

        # attach card
        card_bytes = await self.get_card_bytes()
        try:
            if card_bytes:
                f = discord.File(io.BytesIO(card_bytes), filename=CARD_FILENAME)
                em.set_image(url=f"attachment://{CARD_FILENAME}")
                await channel.send(content=(ping_text + "\n" if ping_text else ""), embed=em, file=f)
            else:
                await channel.send(content=(ping_text + "\n" if ping_text else ""), embed=em)
        except discord.Forbidden:
            logger.warning("No permission to send birthday in %s", channel)
        except Exception as e:
            logger.exception("Error sending birthday announcement: %s", e)

    # ------------------------
    # Slash command group
    # ------------------------
    birthday = app_commands.Group(name="birthday", description="Birthday commands")

    @birthday.command(name="set", description="Set your birthday (e.g. 1996-03-21 or Mar 3)")
    @app_commands.describe(date="Date like 1996-03-21 or Mar 3")
    async def cmd_set(self, interaction: discord.Interaction, date: str):
        await interaction.response.defer(ephemeral=True)
        parsed = parse_date_fuzzy(date)
        if not parsed:
            await interaction.followup.send("Couldn't parse that date. Try formats like `1996-03-21`, `Mar 3`, or `03/21/96`.", ephemeral=True)
            return
        year = parsed.year if parsed.year and parsed.year != 1900 else None
        if not re.search(r'\d{4}', date):
            year = None
        self.db.upsert(interaction.guild.id, interaction.user.id, parsed.month, parsed.day, year)
        template = random.choice(MESSAGE_TEMPLATES)
        em = discord.Embed(title="🎉 Birthday saved!", description=template, color=PINK_COLOR)
        em.add_field(name="When", value=f"{pretty_date(parsed.month, parsed.day)}" + (f" • {year}" if year else ""), inline=True)
        em.set_footer(text="Use /birthday view to check or /birthday remove to delete.")
        card_bytes = await self.get_card_bytes()
        files = []
        if card_bytes:
            files = [discord.File(io.BytesIO(card_bytes), filename=CARD_FILENAME)]
            em.set_image(url=f"attachment://{CARD_FILENAME}")
        try:
            await interaction.followup.send(embed=em, files=files, ephemeral=True)
        except Exception:
            await interaction.followup.send("Saved, but couldn't attach preview image.", ephemeral=True)

    @birthday.command(name="view", description="View your or another user's birthday")
    @app_commands.describe(user="Optional user to view")
    async def cmd_view(self, interaction: discord.Interaction, user: typing.Optional[discord.Member] = None):
        target = user or interaction.user
        row = self.db.get(interaction.guild.id, target.id)
        if not row:
            if target == interaction.user:
                await interaction.response.send_message("You have no birthday saved. Use `/birthday set <date>`.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{target.mention} has no birthday saved.", ephemeral=True)
            return
        em = discord.Embed(title=f"🎂 {target.display_name}'s Birthday", color=PINK_COLOR)
        em.add_field(name="Date", value=f"{pretty_date(row['month'], row['day'])}" + (f" • {row['year']}" if row['year'] else ""), inline=True)
        await interaction.response.send_message(embed=em, ephemeral=True)

    @birthday.command(name="remove", description="Remove your saved birthday (confirmation required)")
    @app_commands.describe(confirm="Type 'confirm' to delete")
    async def cmd_remove(self, interaction: discord.Interaction, confirm: typing.Optional[str] = None):
        if not (confirm and confirm.strip().lower() in ("confirm", "true", "yes", "y")):
            await interaction.response.send_message("Are you sure? To delete your birthday use `/birthday remove confirm`.", ephemeral=True)
            return
        removed = self.db.remove(interaction.guild.id, interaction.user.id)
        if removed:
            await interaction.response.send_message("✅ Your birthday was removed.", ephemeral=True)
        else:
            await interaction.response.send_message("I didn't find a birthday to remove.", ephemeral=True)

    @birthday.command(name="list", description="List saved birthdays in this server (first 50 shown)")
    async def cmd_list(self, interaction: discord.Interaction):
        rows = self.db.list_for_guild(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("No birthdays saved for this server.", ephemeral=True)
            return
        lines = []
        for r in rows[:50]:
            uid = int(r['user_id'])
            try:
                m = interaction.guild.get_member(uid)
                name = m.display_name if m else f"<@{uid}>"
            except Exception:
                name = f"<@{uid}>"
            lines.append(f"{name} — {pretty_date(r['month'], r['day'])}" + (f" • {r['year']}" if r.get('year') else ""))
        em = discord.Embed(title=f"🎁 Birthdays in {interaction.guild.name}", description="\n".join(lines[:1024]), color=PINK_COLOR)
        await interaction.response.send_message(embed=em, ephemeral=True)

    @birthday.command(name="admin", description="Open the admin dashboard (Manage Server required)")
    async def cmd_admin(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        em = await build_dashboard_embed(self, interaction.guild)
        view = AdminView(self, interaction.guild)
        await interaction.response.send_message(embed=em, view=view, ephemeral=True)

    @birthday.command(name="import_csv", description="Import birthdays from CSV (user_id,month,day,year) - admin only")
    @app_commands.describe(file="CSV file to import")
    async def cmd_import_csv(self, interaction: discord.Interaction, file: discord.Attachment):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            data = await file.read()
            s = data.decode('utf-8').splitlines()
            count = 0
            for line in s:
                if not line or line.lower().startswith("user_id"):
                    continue
                parts = re.split(r"[,\t]+", line.strip())
                if len(parts) < 3:
                    continue
                try:
                    uid = int(parts[0]); month = int(parts[1]); day = int(parts[2]); year = int(parts[3]) if len(parts) > 3 and parts[3] else None
                except Exception:
                    continue
                self.db.upsert(interaction.guild.id, uid, month, day, year)
                count += 1
            await interaction.followup.send(f"✅ Imported {count} birthdays.", ephemeral=True)
        except Exception as e:
            logger.exception("Import failed: %s", e)
            await interaction.followup.send("Import failed: " + str(e), ephemeral=True)

# ------------------------
# Setup
# ------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(BirthdayCog(bot))

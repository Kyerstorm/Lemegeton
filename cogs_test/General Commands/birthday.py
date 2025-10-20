# birthday.py
#
# Features:
# - /birthday register yyyy-mm-dd  (or mm/dd or dd-mm)
# - /birthday view
# - /birthday remove
# - Admin slash commands for guild config (channel, timezone offset, mention mode, template)
# - Stores data in SQLite: users table, guild config table
# - Background task checks every minute and posts birthday messages (pings all matched users)
# - Aesthetic embeds and optional generated greeting cards (Pillow)
# - Windows batch scripts included at bottom as comments
# -----------------------------------------------------------------------------

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import asyncio
import datetime
import re
import os
import io
import math
import random
import typing
import logging

# Optional Pillow import for image generation
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# --------------------------
# Logging
# --------------------------
logger = logging.getLogger("birthday_cog")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)

# --------------------------
# Constants and aesthetics
# --------------------------
DB_PATH = os.getenv("BIRTHDAY_DB_PATH", "birthdays.db")
DEFAULT_TIMEZONE_OFFSET = 0  # UTC by default; per-guild override possible (hours offset)
CHECK_INTERVAL_SECONDS = 60  # check every minute

# Emoji and aesthetics library
CELEBRATION_EMOJIS = [
    "🎉", "🎂", "🥳", "🎈", "🍰", "🧁", "✨", "💫", "🌟", "🎁", "❤️"
]

BORDER_EMOJIS = [
    "🌸", "🌼", "🌻", "🌺", "💮", "🌷", "❇️"
]

BIRTHDAY_ASCII = r"""
  _____  _   _  _____  ____   ____   _   _  __   __
 |  __ \| \ | |/ ____|/ __ \ / __ \ | \ | | \ \ / /
 | |__) |  \| | |  __| |  | | |  | ||  \| |  \ V / 
 |  ___/| . ` | | |_ | |  | | |  | || . ` |   > <  
 | |    | |\  | |__| | |__| | |__| || |\  |  / . \ 
 |_|    |_| \_|\_____| \____/ \____/ |_| \_| /_/ \_\
"""

# helpful human-friendly date regexes
DATE_PATTERNS = [
    # yyyy-mm-dd
    (re.compile(r"^(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})$"), "ymd"),
    # mm/dd/yyyy or mm/dd/yy
    (re.compile(r"^(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{2,4})$"), "mdy"),
    # dd-mm-yyyy or dd-mm-yy
    (re.compile(r"^(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})$"), "dmy"),
    # month name day, year   e.g. March 3 1999
    (re.compile(r"^(?P<mn>[A-Za-z]+)\s+(?P<d>\d{1,2})(?:,?\s*(?P<y>\d{4}))?$"), "mn_d_y"),
]

MONTHS = {
    "jan":1, "january":1,
    "feb":2, "february":2,
    "mar":3, "march":3,
    "apr":4, "april":4,
    "may":5,
    "jun":6, "june":6,
    "jul":7, "july":7,
    "aug":8, "august":8,
    "sep":9, "september":9,
    "oct":10, "october":10,
    "nov":11, "november":11,
    "dec":12, "december":12
}

# Default message template (supports {users}, {guild}, {age_map}, {emoji})
DEFAULT_TEMPLATE = (
    "{emoji} **Happy Birthday!** {emoji}\n\n"
    "Today we celebrate: {users}\n\n"
    "{card}\n"
    "Wishing you all the best from everyone in **{guild}**! {emoji}"
)

# ----------- Utilities -----------
def ensure_dir_exists(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def normalize_date_input(s: str) -> typing.Optional[datetime.date]:
    """
    Try to parse many casual formats into a datetime.date.
    Accepts:
    - yyyy-mm-dd
    - mm/dd/yyyy or mm/dd/yy
    - dd-mm-yyyy
    - MonthName day [year]
    - If year omitted, assume year 1900 (we store month/day primarily)
    """
    s = s.strip()
    for (pat, kind) in DATE_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        gd = m.groupdict()
        try:
            if kind == "ymd":
                y = int(gd["y"])
                mth = int(gd["m"])
                d = int(gd["d"])
                return datetime.date(y, mth, d)
            if kind in ("mdy", "dmy"):
                y = gd.get("y")
                if y is None:
                    y = 1900
                else:
                    y = int(y)
                    if y < 100:
                        # two-digit year -> assume 2000-2099 if < 70 else 1900+
                        y = 2000 + y if y < 70 else 1900 + y
                mth = int(gd["m"])
                d = int(gd["d"])
                if kind == "dmy":
                    # swap
                    mth, d = int(gd["m"]), int(gd["d"])
                return datetime.date(y, mth, d)
            if kind == "mn_d_y":
                mn = gd.get("mn", "").lower()
                mth = MONTHS.get(mn[:3], None) if mn else None
                if not mth:
                    # try full name
                    mth = MONTHS.get(mn, None)
                d = int(gd["d"])
                y = gd.get("y")
                if y is None:
                    y = 1900
                else:
                    y = int(y)
                return datetime.date(y, mth, d)
        except Exception:
            continue
    return None


def today_in_offset(offset_hours: float = 0.0) -> datetime.date:
    """Return today's date in UTC+offset"""
    now_utc = datetime.datetime.utcnow()
    created = now_utc + datetime.timedelta(hours=offset_hours)
    return created.date()


def parse_timezone_offset(s: str) -> float:
    """
    Parse timezone offset strings like:
    - +3
    - -04:30
    - +5.5
    - UTC+3
    Returns float hours
    """
    s = s.strip()
    s = s.lower().replace("utc", "")
    m = re.match(r"([+-]?)\s*(\d{1,2})(?::(\d{2}))?(?:\.(\d+))?", s)
    if not m:
        # try plain number
        try:
            return float(s)
        except Exception:
            return DEFAULT_TIMEZONE_OFFSET
    sign = -1 if m.group(1) == "-" else 1
    hours = int(m.group(2)) if m.group(2) else 0
    mins = int(m.group(3)) if m.group(3) else 0
    frac = float("0." + m.group(4)) if m.group(4) else 0.0
    return sign * (hours + mins/60 + frac)


def human_date_for_month_day(month:int, day:int):
    try:
        dt = datetime.date(2000, month, day)  # dummy year
        return dt.strftime("%B %d")
    except Exception:
        return f"{month}/{day}"


# ---------------------------
# Database helper
# ---------------------------
class BirthdayDB:
    def __init__(self, path=DB_PATH):
        ensure_dir_exists(path)
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        # users: id (PK autoinc), guild_id, user_id, month, day, year_nullable, created
        c.execute(
            """
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
            """
        )
        # guild config
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                tz_offset REAL,
                mention_mode TEXT DEFAULT 'none',  -- 'none', 'mention', 'role'
                mention_role_id INTEGER,
                enabled INTEGER DEFAULT 1,
                template TEXT,
                check_hour INTEGER DEFAULT -1,  -- -1 means check every minute
                last_triggered_date TEXT
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                k TEXT PRIMARY KEY,
                v TEXT
            );
            """
        )
        self.conn.commit()

    # user operations
    def upsert_birthday(self, guild_id:int, user_id:int, month:int, day:int, year:typing.Optional[int]=None):
        now = datetime.datetime.utcnow().isoformat()
        c = self.conn.cursor()
        c.execute(
            """
            INSERT INTO birthdays (guild_id, user_id, month, day, year, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET month=excluded.month, day=excluded.day, year=excluded.year, created_at=excluded.created_at;
            """, (guild_id, user_id, month, day, year, now)
        )
        self.conn.commit()

    def remove_birthday(self, guild_id:int, user_id:int):
        c = self.conn.cursor()
        c.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        self.conn.commit()
        return c.rowcount

    def get_birthday(self, guild_id:int, user_id:int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        r = c.fetchone()
        return dict(r) if r else None

    def get_birthdays_by_month_day(self, guild_id:int, month:int, day:int):
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM birthdays WHERE guild_id=? AND month=? AND day=?", (guild_id, month, day)
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]

    def list_birthdays_for_guild(self, guild_id:int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM birthdays WHERE guild_id=? ORDER BY month, day", (guild_id,))
        return [dict(r) for r in c.fetchall()]

    def list_upcoming_for_guild(self, guild_id:int, days:int=30, tz_offset:float=0.0):
        """Return upcoming birthdays in next `days` days relative to now+tz_offset."""
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=tz_offset)
        results = []
        c = self.conn.cursor()
        # naive approach: fetch all and compute
        c.execute("SELECT * FROM birthdays WHERE guild_id=?", (guild_id,))
        for row in c.fetchall():
            r = dict(row)
            year = now.year
            try:
                b_date = datetime.date(year, r["month"], r["day"])
            except Exception:
                continue
            delta = (b_date - now.date()).days
            if delta < 0:
                # next year
                b_date = datetime.date(year+1, r["month"], r["day"])
                delta = (b_date - now.date()).days
            if 0 <= delta <= days:
                r["days_until"] = delta
                results.append(r)
        results.sort(key=lambda x: x["days_until"])
        return results

    # guild config
    def set_guild_config(self, guild_id:int, **kwargs):
        # kwargs can include channel_id, tz_offset, mention_mode, mention_role_id, enabled, template, check_hour
        existing = self.get_guild_config(guild_id)
        c = self.conn.cursor()
        if existing is None:
            # create
            c.execute(
                """
                INSERT INTO guild_config (guild_id, channel_id, tz_offset, mention_mode, mention_role_id, enabled, template, check_hour, last_triggered_date)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    guild_id,
                    kwargs.get("channel_id"),
                    kwargs.get("tz_offset", DEFAULT_TIMEZONE_OFFSET),
                    kwargs.get("mention_mode", "none"),
                    kwargs.get("mention_role_id"),
                    1 if kwargs.get("enabled", True) else 0,
                    kwargs.get("template"),
                    kwargs.get("check_hour", -1),
                    kwargs.get("last_triggered_date"),
                ),
            )
        else:
            # update only provided
            set_fragments = []
            params = []
            for key in ("channel_id", "tz_offset", "mention_mode", "mention_role_id", "enabled", "template", "check_hour", "last_triggered_date"):
                if key in kwargs:
                    set_fragments.append(f"{key}=?")
                    if key == "enabled":
                        params.append(1 if kwargs[key] else 0)
                    else:
                        params.append(kwargs[key])
            if set_fragments:
                params.append(guild_id)
                q = "UPDATE guild_config SET " + ", ".join(set_fragments) + " WHERE guild_id=?"
                c.execute(q, tuple(params))
        self.conn.commit()

    def get_guild_config(self, guild_id:int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
        r = c.fetchone()
        return dict(r) if r else None

    def get_all_guilds_config(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM guild_config")
        return [dict(r) for r in c.fetchall()]

    def set_last_triggered(self, guild_id:int, date_iso:str):
        self.set_guild_config(guild_id, last_triggered_date=date_iso)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

# ---------------------------
# Image generation (Pillow)
# ---------------------------

def generate_birthday_card(username: str, age: typing.Optional[int], message_line: str = "", size=(1200, 675)) -> typing.Optional[bytes]:
    """
    Returns PNG bytes of a generated card using PIL if available, else None.
    """
    if not PIL_AVAILABLE:
        return None

    width, height = size
    # choose random palette
    palettes = [
        ("#ff8a80", "#ffd180", "#ffd180", "#ffffff"),
        ("#ffecb3", "#ffe082", "#ffe082", "#3e2723"),
        ("#e1bee7", "#d1c4e9", "#b39ddb", "#311b92"),
        ("#b2ebf2", "#80deea", "#26c6da", "#006064"),
        ("#c8e6c9", "#a5d6a7", "#81c784", "#1b5e20"),
    ]
    bg1, bg2, accent, textc = random.choice(palettes)

    # create base
    img = Image.new("RGB", (width, height), bg1)
    draw = ImageDraw.Draw(img)

    # gradient overlay
    try:
        base = Image.new("RGB", (width, height), bg1)
        overlay = Image.new("RGB", (width, height), bg2)
        mask = Image.new("L", (width, height))
        md = ImageDraw.Draw(mask)
        for i in range(height):
            intensity = int(255 * (i/height)**1.2)
            md.line([(0,i),(width,i)], fill=intensity)
        img = Image.composite(base, overlay, mask)
        draw = ImageDraw.Draw(img)
    except Exception:
        pass

    # optional confetti (circles)
    for _ in range(80):
        rx = random.randint(0, width)
        ry = random.randint(0, height)
        rsize = random.randint(6, 40)
        color = tuple(int(accent.lstrip("#")[i:i+2], 16) for i in (0,2,4))
        alpha = random.randint(80, 200)
        try:
            circle = Image.new("RGBA", (rsize*2, rsize*2), (0,0,0,0))
            cd = ImageDraw.Draw(circle)
            cd.ellipse((0,0,rsize*2,rsize*2), fill=color+(alpha,))
            img.paste(circle, (rx-rsize, ry-rsize), circle)
        except Exception:
            pass

    # headline text
    try:
        # try common fonts
        fonts_to_try = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]
        title_font = None
        sub_font = None
        for fpath in fonts_to_try:
            try:
                title_font = ImageFont.truetype(fpath, 72)
                sub_font = ImageFont.truetype(fpath, 36)
                break
            except Exception:
                continue
        if not title_font:
            title_font = ImageFont.load_default()
            sub_font = ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()

    # central text layout
    title_text = f"Happy Birthday, {username}!"
    y = int(height * 0.18)
    x = int(width * 0.08)
    # shadow
    shadow_offset = 3
    draw.text((x+shadow_offset, y+shadow_offset), title_text, font=title_font, fill=(0,0,0,120))
    draw.text((x, y), title_text, font=title_font, fill=textc)

    # optional age badge
    if age is not None and isinstance(age, int):
        badge_text = f"{age}"
        bw = int(width*0.17)
        bh = int(height*0.17)
        badge = Image.new("RGBA", (bw, bh), (255,255,255,0))
        bd = ImageDraw.Draw(badge)
        # circle with gradient
        bd.ellipse((0,0,bw,bh), fill=accent)
        # age text
        try:
            bf = ImageFont.truetype("arial.ttf", int(bh*0.45))
        except Exception:
            bf = ImageFont.load_default()
        w, h = bd.textsize(badge_text, font=bf)
        bd.text(((bw-w)/2, (bh-h)/2), badge_text, font=bf, fill=(255,255,255))
        img.paste(badge, (width - bw - 40, 40), badge)

    # message_line
    if message_line:
        try:
            # wrap message
            max_w = width - x*2
            lines = []
            words = message_line.split()
            cur = ""
            for w0 in words:
                t = cur + (" " if cur else "") + w0
                wsize = draw.textsize(t, font=sub_font)[0]
                if wsize <= max_w:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w0
            if cur:
                lines.append(cur)
            ty = y + 110
            for ln in lines[:6]:
                draw.text((x, ty), ln, font=sub_font, fill=textc)
                ty += 42
        except Exception:
            pass

    # frame border
    frame_w = 18
    draw.rectangle([0,0,width,frame_w], fill=accent)
    draw.rectangle([0,height-frame_w,width,height], fill=accent)
    draw.rectangle([0,0,frame_w,height], fill=accent)
    draw.rectangle([width-frame_w,0,width,height], fill=accent)

    # small signature
    try:
        sig = "Made with ❤️"
        sfont = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        sfont = ImageFont.load_default()
    draw.text((x, height - 40), sig, font=sfont, fill=textc)

    # finalize: apply slight blur for dreaminess
    try:
        img = img.filter(ImageFilter.SMOOTH)
    except Exception:
        pass

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.read()

# ---------------------------
# The Cog
# ---------------------------

class BirthdayCog(commands.Cog):
    """
    Multi-guild Birthday Cog
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = BirthdayDB()
        logger.info("BirthdayDB initialized at %s", self.db.path)
        # tasks
        self._birthday_checker.start()

        # A cache to avoid double-sending in the same minute
        self._recent_sent = {}  # guild_id -> date_iso

    def cog_unload(self):
        self._birthday_checker.cancel()
        try:
            self.db.close()
        except Exception:
            pass

    # -----------------------
    # Background task
    # -----------------------
    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def _birthday_checker(self):
        """
        Runs every CHECK_INTERVAL_SECONDS (default 60). For each guild with enabled config,
        compute the local date (UTC + tz_offset) and if the date has not been triggered yet for that guild,
        find birthdays and send greetings.
        """
        # We iterate through guilds the bot is in for which we have config or data
        # gather guilds from DB config and from bot guilds
        try:
            config_rows = self.db.get_all_guilds_config()
            configs = {int(r["guild_id"]): r for r in config_rows}
            # ensure every guild the bot is in has an entry (but only if needed)
            for g in list(self.bot.guilds):
                gid = g.id
                if gid not in configs:
                    # create default config quietly
                    self.db.set_guild_config(gid, tz_offset=DEFAULT_TIMEZONE_OFFSET, enabled=True, template=None, check_hour=-1)
                    configs[gid] = self.db.get_guild_config(gid)
        except Exception as e:
            logger.exception("Error preparing guild configs: %s", e)
            return

        now_utc = datetime.datetime.utcnow()

        for guild in list(self.bot.guilds):
            gid = guild.id
            cfg = configs.get(gid) or self.db.get_guild_config(gid)
            if not cfg:
                continue
            if not cfg.get("enabled", 1):
                continue
            tz_offset = float(cfg.get("tz_offset") or DEFAULT_TIMEZONE_OFFSET)
            local_now = now_utc + datetime.timedelta(hours=tz_offset)
            local_date = local_now.date()
            # check hour enforcement
            check_hour = int(cfg.get("check_hour", -1) or -1)
            if check_hour >= 0:
                # only run when local hour equals check_hour
                if local_now.hour != check_hour:
                    continue
            # Avoid double send: ensure last_triggered_date not equal to iso date
            last = cfg.get("last_triggered_date")
            this_iso = local_date.isoformat()
            if last == this_iso:
                continue

            # find birthdays
            try:
                rows = self.db.get_birthdays_by_month_day(gid, local_date.month, local_date.day)
            except Exception:
                rows = []

            if not rows:
                # set last_triggered_date to avoid repeated checking if check_hour >=0
                if check_hour >= 0:
                    self.db.set_last_triggered(gid, this_iso)
                continue

            # send celebration
            try:
                await self._send_birthday_message_for_guild(guild, cfg, rows, local_now)
                # update last triggered
                self.db.set_last_triggered(gid, this_iso)
            except Exception as e:
                logger.exception("Failed sending birthday message for guild %s: %s", gid, e)

    @_birthday_checker.before_loop
    async def before_birthday_checker(self):
        await self.bot.wait_until_ready()
        logger.info("Birthday checker is starting...")

    # -----------------------
    # Helper: compose and send message
    # -----------------------
    async def _send_birthday_message_for_guild(self, guild: discord.Guild, cfg: dict, rows: list, local_now: datetime.datetime):
        """
        rows: list of dicts from db for users who have birthday today
        """
        channel_id = cfg.get("channel_id")
        target_channel = None

        if channel_id:
            try:
                target_channel = guild.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
            except Exception:
                target_channel = None

        # fallback to system channel or first text channel bot can send in
        if not target_channel:
            target_channel = guild.system_channel
        if not target_channel:
            # find a channel where the bot has send_messages permission
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    target_channel = ch
                    break

        if not target_channel:
            logger.warning("No channel found to send birthday message for guild %s (%s)", guild.id, guild.name)
            return

        # collect users; fetch Member objects
        member_map = {}
        mention_texts = []
        age_map = {}
        for r in rows:
            uid = int(r["user_id"])
            try:
                m = guild.get_member(uid) or await guild.fetch_member(uid)
            except Exception:
                m = None
            if m:
                member_map[uid] = m
                mention_texts.append(m.mention)
            else:
                # fallback to mention by id (this generates a ping if user shares guild)
                mention_texts.append(f"<@{uid}>")

            # compute age if year present
            if r.get("year"):
                try:
                    birth_year = int(r["year"])
                    age = local_now.year - birth_year
                    # adjust if birthday not yet reached within the year; since we're on the birthday date, age is correct
                    age_map[uid] = age
                except Exception:
                    pass

        users_str = ", ".join(mention_texts)
        emoji = random.choice(CELEBRATION_EMOJIS)
        # craft card: if multiple users, we'll create a collage for up to 4 avatars if PIL available
        card_bytes = None
        card_text = ""
        if PIL_AVAILABLE:
            # attempt to generate a celebratory card image featuring usernames/avatars
            # For multiple users, we'll include their display names
            title_names = " & ".join([m.display_name for m in member_map.values()][:4]) or users_str
            # if a single user and year known, compute age
            single_age = None
            if len(rows) == 1 and rows[0].get("year"):
                try:
                    single_age = local_now.year - int(rows[0].get("year"))
                except Exception:
                    single_age = None
            card_text = "Happy Birthday!"
            try:
                # generate generic card
                card_bytes = generate_birthday_card(title_names, single_age, message_line="Have a spectacular day!")
            except Exception:
                card_bytes = None

        # format template
        template = cfg.get("template") or DEFAULT_TEMPLATE
        # build age_map string
        age_map_str = ", ".join(f"{member_map[uid].mention}: {age}" for uid, age in age_map.items()) if age_map else ""
        card_placeholder = ""
        if card_bytes:
            # upload as file
            file = discord.File(io.BytesIO(card_bytes), filename="birthday_card.png")
            card_placeholder = f"[image attached]"
        else:
            # ASCII fallback
            card_placeholder = f"```\n{BIRTHDAY_ASCII}\n```"

        message_text = template.format(
            emoji=emoji,
            users=users_str,
            guild=guild.name,
            age_map=age_map_str,
            card=card_placeholder
        )

        # mention behavior: 'none' -> just text, 'mention' -> mention users, 'role' -> mention configured role
        mention_mode = cfg.get("mention_mode") or "none"
        mention_role_id = cfg.get("mention_role_id")

        # build embeds
        embed = discord.Embed(
            title=f"{emoji} Birthday Celebration!",
            description=f"Today: {human_date_for_month_day(local_now.month, local_now.day)}",
            color=discord.Color.random()
        )
        embed.set_thumbnail(url="https://i.imgur.com/1Xg6RjL.png")  # decorative cake (public img); optional
        embed.add_field(name="Who", value=users_str or "No users found", inline=False)
        if age_map_str:
            embed.add_field(name="Ages", value=age_map_str, inline=False)
        embed.set_footer(text=f"Timezone: UTC{cfg.get('tz_offset', DEFAULT_TIMEZONE_OFFSET):+g} • Celebrations by {self.bot.user.display_name}")

        # try to ping intelligently
        ping_text = ""
        if mention_mode == "role" and mention_role_id:
            ping_text = f"<@&{mention_role_id}>"
        elif mention_mode == "mention":
            # ping all users explicitly
            ping_text = " ".join(mention_texts)
        else:
            ping_text = ""

        # finally send
        try:
            if card_bytes:
                await target_channel.send(content=ping_text or None, embed=embed, file=discord.File(io.BytesIO(card_bytes), filename="birthday_card.png"))
            else:
                await target_channel.send(content=(ping_text + "\n" if ping_text else "") + message_text, embed=embed)
        except discord.Forbidden:
            logger.warning("Missing permissions to post birthday message in %s for guild %s", target_channel, guild.id)
        except Exception as e:
            logger.exception("Error sending birthday message for guild %s: %s", guild.id, e)

    # -----------------------
    # Slash commands
    # -----------------------
    @app_commands.command(name="birthday", description="Register / view / remove your birthday")
    @app_commands.describe(action="action: set/view/remove", date="date in yyyy-mm-dd or mm/dd or 'Mar 3' format")
    async def birthday(self, interaction: discord.Interaction, action: str, date: typing.Optional[str] = None):
        """
        A top-level command, but we'll route to sub-actions inside.
        action: set | view | remove
        """
        action = (action or "").strip().lower()
        if action in ("set", "add", "register"):
            if not date:
                await interaction.response.send_message("Please include a date (e.g. `1996-03-21` or `Mar 3`).", ephemeral=True)
                return
            parsed = normalize_date_input(date)
            if not parsed:
                await interaction.response.send_message("I couldn't parse that date. Try `YYYY-MM-DD` or `MM/DD/YYYY` or `Mar 3`.", ephemeral=True)
                return
            # store only month/day and year optional
            month = parsed.month
            day = parsed.day
            year = parsed.year if parsed.year != 1900 else None
            self.db.upsert_birthday(interaction.guild.id, interaction.user.id, month, day, year)
            # nice embed
            em = discord.Embed(title="Birthday recorded 🎉", color=discord.Color.green())
            em.add_field(name="User", value=interaction.user.mention, inline=True)
            em.add_field(name="Birthday", value=f"{human_date_for_month_day(month, day)}" + (f" • {year}" if year else ""), inline=True)
            em.set_footer(text="You can change it any time with /birthday set <date>")
            await interaction.response.send_message(embed=em, ephemeral=True)
            return

        if action in ("view", "get", "show"):
            data = self.db.get_birthday(interaction.guild.id, interaction.user.id)
            if not data:
                await interaction.response.send_message("I don't have a birthday saved for you. Use `/birthday set <date>` to register one.", ephemeral=True)
                return
            month = data["month"]
            day = data["day"]
            year = data["year"]
            em = discord.Embed(title=f"{interaction.user.display_name}'s birthday", color=discord.Color.blue())
            em.add_field(name="Date", value=f"{human_date_for_month_day(month, day)}" + (f" • {year}" if year else ""), inline=True)
            created = data.get("created_at")
            if created:
                em.set_footer(text=f"Saved: {created}")
            await interaction.response.send_message(embed=em, ephemeral=True)
            return

        if action in ("remove", "delete"):
            removed = self.db.remove_birthday(interaction.guild.id, interaction.user.id)
            if removed:
                await interaction.response.send_message("Your birthday was removed. Use `/birthday set <date>` to add it again.", ephemeral=True)
            else:
                await interaction.response.send_message("I didn't find a birthday to remove.", ephemeral=True)
            return

        # fallback: list all birthdays in the guild (if user requested 'list')
        if action in ("list", "all"):
            # permission check: guild visible
            if not interaction.permissions_in(interaction.channel).manage_guild:
                # show user's only
                data = self.db.get_birthday(interaction.guild.id, interaction.user.id)
                if data:
                    await interaction.response.send_message(f"Your birthday: {human_date_for_month_day(data['month'], data['day'])}", ephemeral=True)
                else:
                    await interaction.response.send_message("I don't have your birthday saved.", ephemeral=True)
                return
            # else list
            rows = self.db.list_birthdays_for_guild(interaction.guild.id)
            if not rows:
                await interaction.response.send_message("No birthdays saved in this server yet.", ephemeral=True)
                return
            description = "\n".join([f"<@{r['user_id']}> — {human_date_for_month_day(r['month'], r['day'])}" for r in rows])
            em = discord.Embed(title="Birthdays in this server", description=description, color=discord.Color.purple())
            await interaction.response.send_message(embed=em, ephemeral=True)
            return

        await interaction.response.send_message("Unknown action. Valid: `set`, `view`, `remove`, `list`.", ephemeral=True)

    # Provide nicer autocompletion for action
    @birthday.autocomplete('action')
    async def birthday_action_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = ["set","view","remove","list"]
        return [app_commands.Choice(name=c, value=c) for c in choices if current.lower() in c.lower()][:25]

    # -----------------------
    # Admin configuration group
    # -----------------------
    admin_group = app_commands.Group(name="birthday_admin", description="Configuration for birthday messages")

    @admin_group.command(name="set_channel", description="Set the channel where birthday messages will be posted")
    @app_commands.describe(channel="Text channel to post birthday messages in")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server permission to configure birthdays.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, channel_id=channel.id)
        await interaction.response.send_message(f"Birthday channel set to {channel.mention}.", ephemeral=True)

    @admin_group.command(name="set_timezone", description="Set the timezone offset for this server's birthday checks (e.g. +3, -04:30)")
    @app_commands.describe(offset="Timezone offset from UTC in hours, e.g. +3, -4, +5.5")
    async def set_timezone(self, interaction: discord.Interaction, offset: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server permission to configure birthdays.", ephemeral=True)
            return
        parsed = parse_timezone_offset(offset)
        self.db.set_guild_config(interaction.guild.id, tz_offset=parsed)
        await interaction.response.send_message(f"Timezone offset set to UTC{parsed:+g}.", ephemeral=True)

    @admin_group.command(name="set_mention_mode", description="Set how users are notified: none / mention / role")
    @app_commands.describe(mode="none | mention | role")
    async def set_mention_mode(self, interaction: discord.Interaction, mode: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        mode = (mode or "").lower()
        if mode not in ("none", "mention", "role"):
            await interaction.response.send_message("Invalid mode. Pick `none`, `mention`, or `role`.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, mention_mode=mode)
        await interaction.response.send_message(f"Mention mode set to `{mode}`.", ephemeral=True)

    @admin_group.command(name="set_mention_role", description="Set the role to ping on birthdays (requires mention_mode=role)")
    @app_commands.describe(role="Role to mention when birthdays occur")
    async def set_mention_role(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, mention_role_id=role.id)
        await interaction.response.send_message(f"Configured to mention role {role.mention} when mention mode is `role`.", ephemeral=True)

    @admin_group.command(name="enable", description="Enable birthday announcements for this server")
    async def enable(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, enabled=True)
        await interaction.response.send_message("Birthday announcements enabled for this server.", ephemeral=True)

    @admin_group.command(name="disable", description="Disable birthday announcements for this server")
    async def disable(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, enabled=False)
        await interaction.response.send_message("Birthday announcements disabled for this server.", ephemeral=True)

    @admin_group.command(name="set_template", description="Set the message template for birthday announcements")
    @app_commands.describe(template="Use placeholders: {users}, {guild}, {age_map}, {emoji}, {card}")
    async def set_template(self, interaction: discord.Interaction, template: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        # limit length
        if len(template) > 2000:
            await interaction.response.send_message("Template too long (max 2000 chars).", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, template=template)
        await interaction.response.send_message("Template updated. Preview will be used on next birthday.", ephemeral=True)

    @admin_group.command(name="set_check_hour", description="Set a local hour (0-23) to run birthday checks. -1 disables hourly gating (default: every minute)")
    @app_commands.describe(hour="Hour of day in server timezone to run the birthday check (0-23), or -1 to check every minute")
    async def set_check_hour(self, interaction: discord.Interaction, hour: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return
        if hour < -1 or hour > 23:
            await interaction.response.send_message("Hour must be between -1 and 23.", ephemeral=True)
            return
        self.db.set_guild_config(interaction.guild.id, check_hour=hour)
        await interaction.response.send_message(f"Check hour set to {hour}. If -1, checks run every minute.", ephemeral=True)

    @admin_group.command(name="preview", description="Preview a birthday message for the specified user(s)")
    @app_commands.describe(users="Users to include in preview (optional)")
    async def preview(self, interaction: discord.Interaction, users: typing.Optional[typing.Sequence[discord.Member]] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True)
            return

        guild = interaction.guild
        cfg = self.db.get_guild_config(guild.id) or {}
        # Build fake rows
        if users:
            rows = []
            for m in users:
                b = self.db.get_birthday(guild.id, m.id)
                if b:
                    rows.append(b)
                else:
                    rows.append({"user_id": m.id, "month": datetime.datetime.utcnow().month, "day": datetime.datetime.utcnow().day, "year": None})
        else:
            # pick first up to 3
            rows = []
            birthdays = self.db.list_birthdays_for_guild(guild.id)[:3]
            if birthdays:
                rows = birthdays
            else:
                # create placeholders for preview
                rows = [
                    {"user_id": interaction.user.id, "month": datetime.datetime.utcnow().month, "day": datetime.datetime.utcnow().day, "year": 1990}
                ]

        # call send function but make it ephemeral by sending to the invoker as DM
        local_now = datetime.datetime.utcnow() + datetime.timedelta(hours=float(cfg.get("tz_offset") or DEFAULT_TIMEZONE_OFFSET))
        # Reuse internal formatting to craft message and embed
        member_map = {}
        for r in rows:
            try:
                m = guild.get_member(int(r["user_id"]))
            except Exception:
                m = None
            if m:
                member_map[int(r["user_id"])] = m

        users_str = ", ".join([m.mention for m in member_map.values()]) or ", ".join([f"<@{r['user_id']}>" for r in rows])
        emoji = random.choice(CELEBRATION_EMOJIS)

        template = cfg.get("template") or DEFAULT_TEMPLATE
        card_bytes = None
        # generate sample card if possible
        if PIL_AVAILABLE:
            try:
                card_bytes = generate_birthday_card(", ".join([m.display_name for m in member_map.values()][:3]), None, message_line="Preview card")
            except Exception:
                card_bytes = None

        card_placeholder = "[image attached]" if card_bytes else f"```\n{BIRTHDAY_ASCII}\n```"

        message_text = template.format(emoji=emoji, users=users_str, guild=guild.name, age_map="", card=card_placeholder)

        em = discord.Embed(title="Birthday preview", description=message_text[:2048], color=discord.Color.blurple())
        if card_bytes:
            # send DM with file
            try:
                dm = await interaction.user.create_dm()
                await dm.send(embed=em, file=discord.File(io.BytesIO(card_bytes), filename="preview_card.png"))
                await interaction.response.send_message("Preview sent to your DMs.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message("Couldn't send DM preview: " + str(e), ephemeral=True)
        else:
            await interaction.response.send_message(embed=em, ephemeral=True)

# ---------------------------
# Setup function for Cog
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(BirthdayCog(bot))

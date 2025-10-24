# birthday.py
# - /birthday group: set/view/remove/list
# - /birthday admin (dashboard): interactive UI (buttons, selects, modals)
# - SQLite backend
# - ~30 randomized card styles using PIL (fallback to ASCII)
# - Many aesthetics and features

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import asyncio
import random
import math
import os
import io
import re
import typing
import logging
from collections import defaultdict

# Optional Pillow (PIL) support
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ------------------------
# Logging
# ------------------------
logger = logging.getLogger("birthday_cog")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)

# ------------------------
# Config
# ------------------------
DB_PATH = os.getenv("BIRTHDAY_DB_PATH", "birthdays.db")
CHECK_INTERVAL_SECONDS = 60
DEFAULT_TZ_OFFSET = 0.0

CELEB_EMOJIS = ["🎉","🎂","🥳","🎈","🍰","🧁","✨","🌟","🎁","💫"]
BORDER_EMOJIS = ["🌸","🌼","🌻","🌺","🌷","❇️","💮","🎊"]
ASCII_CARD = r"""
  _____  _   _  _____  ____   ____   _   _  __   __
 |  __ \| \ | |/ ____|/ __ \ / __ \ | \ | | \ \ / /
 | |__) |  \| | |  __| |  | | |  | ||  \| |  \ V /
 |  ___/| . ` | | |_ | |  | | |  | || . ` |   > <
 | |    | |\  | |__| | |__| | |__| || |\  |  / . \
 |_|    |_| \_|\_____| \____/ \____/ |_| \_| /_/ \_\
"""

# ------------------------
# Utility functions
# ------------------------
def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def now_utc():
    return datetime.datetime.utcnow()

def today_with_offset(offset_hours: float):
    return (now_utc() + datetime.timedelta(hours=offset_hours)).date()

def parse_tz_offset(s: str) -> float:
    # Accepts +3, -04:30, +5.5, UTC+3, etc.
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
    return sign * (hours + mins/60 + frac)

def pretty_date(month:int, day:int):
    try:
        d = datetime.date(2000, month, day)
        return d.strftime("%B %d")
    except Exception:
        return f"{month}/{day}"

def humanize_age(birth_year:int, reference:datetime.date):
    try:
        age = reference.year - int(birth_year)
        return age
    except Exception:
        return None

# Date parsing tolerant
DATE_REGEXES = [
    (re.compile(r"^(?P<y>\d{4})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})$"), "ymd"),
    (re.compile(r"^(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{2,4})$"), "mdy"),
    (re.compile(r"^(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{2,4})$"), "dmy"),
    (re.compile(r"^(?P<mn>[A-Za-z]+)\s+(?P<d>\d{1,2})(?:,?\s*(?P<y>\d{4}))?$"), "mn_d_y"),
]
MONTHS = {k:i for i,k in enumerate(["","January","February","March","April","May","June","July","August","September","October","November","December"])}

def parse_date_fuzzy(s: str) -> typing.Optional[datetime.date]:
    s0 = s.strip()
    if not s0:
        return None
    # try direct parse first
    try:
        dt = datetime.datetime.fromisoformat(s0)
        return dt.date()
    except Exception:
        pass
    for pat, kind in DATE_REGEXES:
        m = pat.match(s0)
        if not m:
            continue
        gd = m.groupdict()
        try:
            if kind == "ymd":
                return datetime.date(int(gd["y"]), int(gd["m"]), int(gd["d"]))
            if kind in ("mdy","dmy"):
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
                # try find month by prefix
                mth = None
                for i in range(1,13):
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
    # fallback: try parsing "Mar 3" or "3 Mar" without year
    try:
        from dateutil import parser as _p
        dt = _p.parse(s0, default=datetime.datetime(2000,1,1))
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
        c = self.conn.cursor()
        c.execute("""
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
        c.execute("""
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
    def upsert(self, guild_id:int, user_id:int, month:int, day:int, year:typing.Optional[int]=None):
        now = datetime.datetime.utcnow().isoformat()
        cur = self.conn.cursor()
        cur.execute("""INSERT INTO birthdays (guild_id,user_id,month,day,year,created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(guild_id,user_id) DO UPDATE SET month=excluded.month,day=excluded.day,year=excluded.year,created_at=excluded.created_at
        """, (guild_id,user_id,month,day,year,now))
        self.conn.commit()

    def remove(self, guild_id:int, user_id:int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id,user_id))
        self.conn.commit()
        return cur.rowcount

    def get(self, guild_id:int, user_id:int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? AND user_id=?", (guild_id,user_id))
        r = cur.fetchone()
        return dict(r) if r else None

    def by_month_day(self, guild_id:int, month:int, day:int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? AND month=? AND day=?", (guild_id,month,day))
        return [dict(x) for x in cur.fetchall()]

    def list_for_guild(self, guild_id:int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM birthdays WHERE guild_id=? ORDER BY month,day", (guild_id,))
        return [dict(x) for x in cur.fetchall()]

    # config
    def set_config(self, guild_id:int, **kwargs):
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
            # build update
            parts = []
            vals = []
            for k in ("channel_id","tz_offset","mention_mode","mention_role_id","enabled","template","check_hour","last_triggered"):
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

    def get_config(self, guild_id:int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
        r = cur.fetchone()
        return dict(r) if r else None

    def all_configs(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM guild_config")
        return [dict(x) for x in cur.fetchall()]

    def set_last_triggered(self, guild_id:int, iso_str:str):
        self.set_config(guild_id, last_triggered=iso_str)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

# ------------------------
# Card generator: ~30 styles
# ------------------------
# (kept most of your original styles — trimmed some comments)
def load_font_sz(size:int):
    candidates = [
        "arial.ttf", "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None

# gradient background
def gradient_background(size, color1, color2, direction='vertical'):
    w,h = size
    base = Image.new('RGB', (w,h), color1)
    top = Image.new('RGB', (w,h), color2)
    mask = Image.new('L', (w,h))
    mask_draw = ImageDraw.Draw(mask)
    if direction == 'vertical':
        for y in range(h):
            mask_draw.line([(0,y),(w,y)], fill=int(255 * (y/h)))
    else:
        for x in range(w):
            mask_draw.line([(x,0),(x,h)], fill=int(255 * (x/w)))
    return Image.composite(top, base, mask)

PALETTES = [
    ("#ff9a9e","#fad0c4"),
    ("#a18cd1","#fbc2eb"),
    ("#fbc2eb","#a6c1ee"),
    ("#84fab0","#8fd3f4"),
    ("#f6d365","#fda085"),
    ("#f093fb","#f5576c"),
    ("#cfe9ff","#ffffff"),
    ("#f3e7e9","#e3eeff"),
    ("#e0c3fc","#8ec5fc"),
    ("#ffecd2","#fcb69f")
]

def random_palette():
    return random.choice(PALETTES)

# A subset of your style functions (kept names/behavior)
def style_confetti_card(username:str, subtitle:str, age:typing.Optional[int], size=(1200,675)):
    w,h = size
    pal = random_palette()
    img = gradient_background((w,h), pal[0], pal[1])
    draw = ImageDraw.Draw(img)
    for _ in range(200):
        x = random.randint(0,w)
        y = random.randint(0,h)
        r = random.randint(4,18)
        col = tuple(random.randint(50,255) for _ in range(3))
        draw.ellipse([x-r,y-r,x+r,y+r], fill=col, outline=None)
    title_font = load_font_sz(64)
    sub_font = load_font_sz(36)
    t = f"Happy Birthday, {username}!"
    try:
        w_t, h_t = draw.textsize(t, font=title_font)
        draw.text(((w-w_t)/2, h*0.18), t, font=title_font, fill="white")
        if subtitle:
            ws, hs = draw.textsize(subtitle, font=sub_font)
            draw.text(((w-ws)/2, h*0.18 + h_t + 12), subtitle, font=sub_font, fill="white")
    except Exception:
        draw.text((60, int(h*0.18)), t, fill="white")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.read()

def style_cake_pastel(username:str, subtitle:str, age, size=(1200,675)):
    w,h = size
    img = Image.new("RGB",(w,h), "#fff6f0")
    draw = ImageDraw.Draw(img)
    cake_w, cake_h = 700, 300
    cx, cy = (w-cake_w)//2, int(h*0.35)
    draw.rounded_rectangle([cx,cy,cx+cake_w,cy+cake_h], radius=40, fill="#ffcfda")
    draw.rectangle([cx+20, cy+100, cx+cake_w-20, cy+cake_h-20], fill="#fff")
    for i in range(6):
        x = cx+80 + i*90
        y = cy-40
        draw.rectangle([x,y,x+8,y+40], fill=random.choice(["#ff8a80","#ffd180","#ffd740","#82b1ff"]))
        draw.ellipse([x-6,y-18,x+14,y-6], fill="#ffd54f")
    tfont = load_font_sz(64)
    sf = load_font_sz(28)
    t = f"Happy Birthday, {username}!"
    try:
        w_t, h_t = draw.textsize(t, font=tfont)
        draw.text(((w-w_t)/2, cy + cake_h + 20), t, font=tfont, fill="#6d214f")
        if subtitle:
            ws, hs = draw.textsize(subtitle, font=sf)
            draw.text(((w-ws)/2, cy + cake_h + 20 + h_t + 6), subtitle, font=sf, fill="#6d214f")
    except Exception:
        draw.text((60, cy + cake_h + 20), t, fill="#6d214f")
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.read()

def style_balloon_burst(username, subtitle, age, size=(1200,675)):
    w,h = size
    pal = random_palette()
    img = gradient_background((w,h), pal[0], pal[1], direction='horizontal')
    draw = ImageDraw.Draw(img)
    for i in range(18):
        bx = random.randint(60,w-60)
        by = random.randint(60,h-160)
        r = random.randint(40,90)
        color = tuple(random.randint(80,255) for _ in range(3))
        draw.ellipse([bx-r,by-r,bx+r,by+r], fill=color)
        draw.line([(bx,by+r),(bx,by+r+40)], fill="#444", width=2)
    tfont = load_font_sz(72)
    t = f"Happy Birthday, {username}!"
    try:
        w_t,h_t = draw.textsize(t,font=tfont)
        draw.text(((w-w_t)/2, h*0.12), t, font=tfont, fill="white")
    except Exception:
        draw.text((60, int(h*0.12)), t, fill="white")
    bio=io.BytesIO(); img.save(bio,"PNG"); bio.seek(0); return bio.read()

def style_neon_username(username, subtitle, age, size=(1200,675)):
    w,h = size
    img = Image.new("RGB",(w,h),"#020024")
    draw = ImageDraw.Draw(img)
    tfont = load_font_sz(100)
    t = username.upper()
    x = 80; y = int(h*0.3)
    for i in range(10,0,-2):
        draw.text((x,y+i), t, font=tfont, fill=(20,20,30))
    draw.text((x,y), t, font=tfont, fill=(255,255,255))
    if subtitle:
        sf = load_font_sz(36)
        draw.text((x,y+110), subtitle, font=sf, fill=(200,200,255))
    bio=io.BytesIO(); img.save(bio,"PNG"); bio.seek(0); return bio.read()

# Build style list and variants
STYLE_FUNCTIONS = [
    style_confetti_card,
    style_cake_pastel,
    style_balloon_burst,
    style_neon_username,
]

for i in range(20):
    def gen(seed):
        def inner(username, subtitle, age, size=(1200,675)):
            random.seed(seed + (hash(username) & 0xFFFF))
            pal = random_palette()
            img = Image.new("RGB", size, pal[0])
            draw = ImageDraw.Draw(img)
            tf = load_font_sz(64)
            try:
                draw.text((60,80), f"Happy Birthday, {username}!", font=tf, fill="white")
            except Exception:
                draw.text((60,80), f"Happy Birthday, {username}!")
            bio=io.BytesIO(); img.save(bio,"PNG"); bio.seek(0); return bio.read()
        return inner
    STYLE_FUNCTIONS.append(gen(i*11+7))

TOTAL_STYLES = len(STYLE_FUNCTIONS)

async def generate_card(username:str, subtitle:str="", age:typing.Optional[int]=None, members_for_collage:typing.List[discord.Member]=None) -> typing.Optional[bytes]:
    if not PIL_AVAILABLE:
        return None
    idx = random.randrange(TOTAL_STYLES)
    style_fn = STYLE_FUNCTIONS[idx]
    try:
        avatars_imgs = []
        if members_for_collage:
            for m in members_for_collage[:4]:
                try:
                    avatar = m.display_avatar
                    data = await avatar.read()
                    im = Image.open(io.BytesIO(data)).convert("RGBA")
                    avatars_imgs.append(im)
                except Exception:
                    pass
        result = style_fn(username, subtitle, age)
        return result
    except Exception as e:
        logger.exception("Card style generation failed: %s", e)
        return None

# ------------------------
# Birthday Cog
# ------------------------

class AdminDashboardView(discord.ui.View):
    """
    Interactive dashboard View presented by /birthday admin.
    Buttons open modals or trigger selects. All actions check Manage Guild permission.
    """

    def __init__(self, cog:"BirthdayCog", guild:discord.Guild, *, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild = guild

    async def interaction_check(self, interaction:discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server to use this dashboard.", ephemeral=True)
            return False
        # ensure same guild
        if interaction.guild.id != self.guild.id:
            await interaction.response.send_message("This dashboard is for a different server.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set Channel", style=discord.ButtonStyle.secondary, custom_id="bd_set_channel")
    async def set_channel_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        # show a modal to enter channel mention or ID
        class ChannelModal(discord.ui.Modal, title="Set birthday channel"):
            channel_input = discord.ui.TextInput(label="Channel (mention or ID)", placeholder="#birthdays or 123456789012345678", required=True, max_length=64)

            async def on_submit(self_, modal_interaction:discord.Interaction):
                raw = modal_interaction.channel_input.value.strip()
                ch = None
                # mention form <#id>
                mm = re.match(r'^<#?(\d+)>?$', raw)
                try:
                    if mm:
                        cid = int(mm.group(1))
                        ch = interaction.guild.get_channel(cid) or await interaction.guild.fetch_channel(cid)
                    elif raw.isdigit():
                        cid = int(raw)
                        ch = interaction.guild.get_channel(cid) or await interaction.guild.fetch_channel(cid)
                    else:
                        # try find by name
                        name = raw.lstrip('#')
                        for c in interaction.guild.text_channels:
                            if c.name == name:
                                ch = c
                                break
                except Exception:
                    ch = None
                if not ch:
                    await modal_interaction.response.send_message("Could not resolve channel. Make sure I can view it and you typed it correctly.", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, channel_id=ch.id)
                await modal_interaction.response.send_message(f"Birthday channel set to {ch.mention}.", ephemeral=True)

        await interaction.response.send_modal(ChannelModal())

    @discord.ui.button(label="Set Timezone", style=discord.ButtonStyle.secondary, custom_id="bd_set_tz")
    async def set_tz_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        class TZModal(discord.ui.Modal, title="Set timezone offset"):
            tz_input = discord.ui.TextInput(label="Offset (e.g. +3, -04:30, 5.5)", placeholder="+3 or -04:00", required=True, max_length=16)

            async def on_submit(self_, modal_interaction:discord.Interaction):
                raw = modal_interaction.tz_input.value.strip()
                parsed = parse_tz_offset(raw)
                self.cog.db.set_config(self.guild.id, tz_offset=parsed)
                await modal_interaction.response.send_message(f"Timezone set to UTC{parsed:+g}.", ephemeral=True)

        await interaction.response.send_modal(TZModal())

    @discord.ui.button(label="Mention Mode", style=discord.ButtonStyle.primary, custom_id="bd_mention_mode")
    async def mention_mode_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        # show a select menu for mention mode
        class MentionSelect(discord.ui.View):
            @discord.ui.select(placeholder="Choose mention mode", min_values=1, max_values=1, options=[
                discord.SelectOption(label="None", value="none", description="No pings"),
                discord.SelectOption(label="Mention users", value="mention", description="Ping birthday users"),
                discord.SelectOption(label="Mention role", value="role", description="Ping configured role"),
            ])
            async def select_callback(self_, select_interaction:discord.Interaction):
                mode = select_interaction.data["values"][0]
                self.cog.db.set_config(self.guild.id, mention_mode=mode)
                await select_interaction.response.send_message(f"Mention mode set to `{mode}`.", ephemeral=True)
        await interaction.response.send_message("Choose mention mode:", view=MentionSelect(), ephemeral=True)

    @discord.ui.button(label="Set Role", style=discord.ButtonStyle.secondary, custom_id="bd_set_role")
    async def set_role_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        class RoleModal(discord.ui.Modal, title="Set mention role")
            # grammar: create role input
        try:
            # create modal dynamically (python <3.11 safety)
            class RoleModal(discord.ui.Modal, title="Set mention role"):
                role_input = discord.ui.TextInput(label="Role (mention or ID)", placeholder="@Birthdays or 123456789012345678", required=True, max_length=64)
                async def on_submit(self_, modal_interaction:discord.Interaction):
                    raw = modal_interaction.role_input.value.strip()
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
                    await modal_interaction.response.send_message(f"Mention role set to {role.mention}.", ephemeral=True)
            await interaction.response.send_modal(RoleModal())
        except Exception as e:
            logger.exception("Role modal create failed: %s", e)
            await interaction.response.send_message("Failed to open role modal.", ephemeral=True)

    @discord.ui.button(label="Set Template", style=discord.ButtonStyle.secondary, custom_id="bd_set_template")
    async def set_template_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        class TemplateModal(discord.ui.Modal, title="Set announcement template"):
            tmpl = discord.ui.TextInput(label="Template (placeholders: {emoji},{users},{guild},{age_map},{card})", style=discord.TextStyle.long, required=True, max_length=1500)
            async def on_submit(self_, modal_interaction:discord.Interaction):
                tx = modal_interaction.tmpl.value.strip()
                if len(tx) > 2000:
                    await modal_interaction.response.send_message("Template too long (2000 char limit).", ephemeral=True)
                    return
                self.cog.db.set_config(self.guild.id, template=tx)
                await modal_interaction.response.send_message("Template saved. It will be used at next announcement.", ephemeral=True)
        await interaction.response.send_modal(TemplateModal())

    @discord.ui.button(label="Enable / Disable", style=discord.ButtonStyle.success, custom_id="bd_toggle_enabled")
    async def toggle_enabled_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        cfg = self.cog.db.get_config(self.guild.id) or {}
        cur = bool(cfg.get("enabled", 1))
        self.cog.db.set_config(self.guild.id, enabled=(not cur))
        await interaction.response.send_message(f"Birthdays enabled: {not cur}", ephemeral=True)

    @discord.ui.button(label="Preview", style=discord.ButtonStyle.primary, custom_id="bd_preview")
    async def preview_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        # open a short modal for sample users or use the top 3 birthdays as sample
        cfg = self.cog.db.get_config(self.guild.id) or {}
        rows = self.cog.db.list_for_guild(self.guild.id)[:3] or [{"user_id":interaction.user.id,"month":now_utc().month,"day":now_utc().day,"year":1996}]
        members=[]
        mentions=[]
        for r in rows:
            try:
                m = self.guild.get_member(int(r['user_id']))
            except Exception:
                m = None
            if m:
                members.append(m); mentions.append(m.mention)
            else:
                mentions.append(f"<@{r['user_id']}>")
        users_str = ", ".join(mentions)
        emoji = random.choice(CELEB_EMOJIS)
        subtitle = f"{pretty_date(now_utc().month, now_utc().day)}"
        try:
            card_bytes = await generate_card(", ".join([m.display_name for m in members][:3]) or "friend", "Preview", None, members_for_collage=members)
        except Exception:
            card_bytes = None
        card_placeholder = "[image attached]" if card_bytes else f"```\n{ASCII_CARD}\n```"
        template = cfg.get("template") or ("{emoji} **Happy Birthday!** {emoji}\n\n{users}\n\n{card}\n")
        final = template.format(emoji=emoji, users=users_str, guild=self.guild.name, age_map="", card=card_placeholder)
        em = discord.Embed(title="Birthday Preview", description=final[:2048], color=discord.Color.blurple())
        try:
            dm = await interaction.user.create_dm()
            if card_bytes:
                await dm.send(embed=em, file=discord.File(io.BytesIO(card_bytes), filename="preview.png"))
            else:
                await dm.send(embed=em)
            await interaction.response.send_message("Preview sent to your DMs.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Could not send DM. Showing preview here.", ephemeral=True, embed=em)

    @discord.ui.button(label="Force Run Today", style=discord.ButtonStyle.danger, custom_id="bd_force_run")
    async def force_run_button(self, button:discord.ui.Button, interaction:discord.Interaction):
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
        except Exception as e:
            logger.exception("Force run failed: %s", e)
            await interaction.followup.send("Error while trying to announce.", ephemeral=True)

    @discord.ui.button(label="Export CSV", style=discord.ButtonStyle.secondary, custom_id="bd_export")
    async def export_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        rows = self.cog.db.list_for_guild(self.guild.id)
        if not rows:
            await interaction.response.send_message("No birthdays to export.", ephemeral=True); return
        out = io.StringIO()
        out.write("user_id,month,day,year,created_at\n")
        for r in rows:
            out.write(f"{r['user_id']},{r['month']},{r['day']},{r.get('year') or ''},{r.get('created_at')}\n")
        out.seek(0)
        try:
            dm = await interaction.user.create_dm()
            await dm.send(file=discord.File(io.BytesIO(out.getvalue().encode('utf-8')), filename="birthdays_export.csv"))
            await interaction.response.send_message("CSV exported to your DMs.", ephemeral=True)
        except Exception as e:
            logger.exception("Export DM failed: %s", e)
            await interaction.response.send_message("Could not send DM with CSV.", ephemeral=True)

    @discord.ui.button(label="Import CSV", style=discord.ButtonStyle.primary, custom_id="bd_import")
    async def import_button(self, button:discord.ui.Button, interaction:discord.Interaction):
        await interaction.response.send_message("To import, use `/birthday admin import_csv` with a file attachment (CSV).", ephemeral=True)

class BirthdayCog(commands.Cog):
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.db = BirthdayDB()
        self._checker.start()
        logger.info("BirthdayCog initialized with DB at %s", self.db.path)

    def cog_unload(self):
        self._checker.cancel()
        self.db.close()

    # Background task
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
            if not cfg.get("enabled",1):
                continue
            tz = float(cfg.get("tz_offset") or DEFAULT_TZ_OFFSET)
            local = now + datetime.timedelta(hours=tz)
            local_date = local.date()
            check_hour = int(cfg.get("check_hour",-1) or -1)
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

    async def _announce_birthdays(self, guild:discord.Guild, cfg:dict, rows:list, local_dt:datetime.datetime):
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
                ages[uid] = humanize_age(r["year"], local_dt.date())

        users_str = ", ".join(mentions)
        age_str = ", ".join(f"<@{uid}>: {a}" for uid,a in ages.items()) if ages else ""
        emoji = random.choice(CELEB_EMOJIS)
        template = cfg.get("template") or ("{emoji} **Happy Birthday!** {emoji}\n\n{users}\n\n{card}\n\n— {guild}")

        subtitle = f"{pretty_date(local_dt.month, local_dt.day)}"
        try:
            card_bytes = await generate_card(", ".join([m.display_name for m in members][:3]) or "friend", subtitle, None, members_for_collage=members)
        except Exception:
            card_bytes = None

        card_placeholder = "[image attached]" if card_bytes else f"```\n{ASCII_CARD}\n```"
        final_text = template.format(emoji=emoji, users=users_str, guild=guild.name, age_map=age_str, card=card_placeholder)

        mention_mode = cfg.get("mention_mode") or "none"
        ping_text = ""
        if mention_mode == "mention":
            ping_text = " ".join(mentions)
        elif mention_mode == "role" and cfg.get("mention_role_id"):
            ping_text = f"<@&{int(cfg['mention_role_id'])}>"

        embed = discord.Embed(title=f"{emoji} Birthday Celebration!", description=f"Today: {subtitle}", color=discord.Color.random())
        embed.add_field(name="Who", value=users_str or "No users", inline=False)
        if age_str:
            embed.add_field(name="Ages", value=age_str, inline=False)
        embed.set_footer(text=f"Timezone: UTC{(cfg.get('tz_offset') or 0):+g} • powered by your friendly bot")

        try:
            if card_bytes:
                f = discord.File(io.BytesIO(card_bytes), filename="birthday_card.png")
                await channel.send(content=(ping_text+"\n" if ping_text else "") , embed=embed, file=f)
            else:
                await channel.send(content=(ping_text + "\n" if ping_text else "") + final_text, embed=embed)
        except discord.Forbidden:
            logger.warning("No permission to send birthday in %s", channel)
        except Exception as e:
            logger.exception("Error sending birthday announcement: %s", e)

    # ------------------------
    # Command group: /birthday <subcommand>
    # ------------------------
    birthday_group = app_commands.Group(name="birthday", description="Birthday commands")

    @birthday_group.command(name="set", description="Set your birthday (e.g. 1996-03-21 or Mar 3)")
    @app_commands.describe(date="Date like 1996-03-21 or Mar 3")
    async def birthday_set(self, interaction:discord.Interaction, date:str):
        await interaction.response.defer(ephemeral=True)
        # parse fuzzy
        parsed = parse_date_fuzzy(date)
        if not parsed:
            await interaction.followup.send("Couldn't parse that date. Try formats like `1996-03-21`, `Mar 3`, or `03/21/96`.", ephemeral=True)
            return
        # store year optionally (if year is 1900 used as default earlier; but our parse_date_fuzzy will try to use year from input)
        year = parsed.year if parsed.year and parsed.year != 1900 else None
        # If user provided just month/day without year, keep year None
        # Our parse_date_fuzzy may set 2000 if no year; detect that by checking original string for any 4-digit year
        if not re.search(r'\d{4}', date):
            year = None
        self.db.upsert(interaction.guild.id, interaction.user.id, parsed.month, parsed.day, year)
        em = discord.Embed(title="Birthday saved", color=discord.Color.green())
        em.add_field(name="Date", value=f"{pretty_date(parsed.month, parsed.day)}" + (f" • {year}" if year else ""), inline=True)
        em.set_footer(text="Use /birthday view to check or /birthday remove to delete.")
        # try to generate a small card preview to attach
        try:
            card_bytes = await generate_card(interaction.user.display_name, pretty_date(parsed.month, parsed.day), humanize_age(year, datetime.date.today()) if year else None, members_for_collage=[interaction.user])
        except Exception:
            card_bytes = None
        try:
            if card_bytes:
                await interaction.followup.send(embed=em, file=discord.File(io.BytesIO(card_bytes), filename="birthday_saved.png"), ephemeral=True)
            else:
                await interaction.followup.send(embed=em, ephemeral=True)
        except Exception:
            await interaction.followup.send("Saved, but couldn't attach preview.", ephemeral=True)

    @birthday_group.command(name="view", description="View your or another user's birthday")
    @app_commands.describe(user="Optional user to view")
    async def birthday_view(self, interaction:discord.Interaction, user:typing.Optional[discord.Member]=None):
        target = user or interaction.user
        row = self.db.get(interaction.guild.id, target.id)
        if not row:
            if target == interaction.user:
                await interaction.response.send_message("You have no birthday saved. Use `/birthday set <date>`.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{target.mention} has no birthday saved.", ephemeral=True)
            return
        em = discord.Embed(title=f"{target.display_name}'s Birthday", color=discord.Color.blurple())
        em.add_field(
            name="Date",
            value=f"{pretty_date(row['month'], row['day'])}" + (f" • {row['year']}" if row['year'] else ""),
            inline=True
        )
        if target != interaction.user:
            em.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.response.send_message(embed=em, ephemeral=True)

    @birthday_group.command(name="remove", description="Remove your saved birthday (confirmation required)")
    @app_commands.describe(confirm="Type 'confirm' to delete")
    async def birthday_remove(self, interaction:discord.Interaction, confirm:typing.Optional[str]=None):
        if not (confirm and confirm.strip().lower() in ("confirm","true","yes","y")):
            await interaction.response.send_message("Are you sure? To delete your birthday use `/birthday remove confirm`.", ephemeral=True)
            return
        removed = self.db.remove(interaction.guild.id, interaction.user.id)
        if removed:
            await interaction.response.send_message("Your birthday was removed.", ephemeral=True)
        else:
            await interaction.response.send_message("I didn't find a birthday to remove.", ephemeral=True)

    @birthday_group.command(name="list", description="List saved birthdays in this server (first 50 shown)")
    async def birthday_list(self, interaction:discord.Interaction):
        rows = self.db.list_for_guild(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("No birthdays saved for this server.", ephemeral=True)
            return
        lines=[]
        for r in rows[:50]:
            uid = int(r['user_id'])
            try:
                m = interaction.guild.get_member(uid)
                name = m.display_name if m else f"<@{uid}>"
            except Exception:
                name = f"<@{uid}>"
            lines.append(f"{name} — {pretty_date(r['month'], r['day'])}" + (f" • {r['year']}" if r.get('year') else ""))
        em = discord.Embed(title=f"Birthdays in {interaction.guild.name}", description="\n".join(lines[:2048]), color=discord.Color.blurple())
        await interaction.response.send_message(embed=em, ephemeral=True)

    # Admin "dashboard" command (uses UI)
    @birthday_group.command(name="admin", description="Open the admin dashboard (Manage Server required)")
    async def birthday_admin(self, interaction:discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        cfg = self.db.get_config(interaction.guild.id) or {}
        enabled = bool(cfg.get("enabled",1))
        ch = None
        if cfg.get("channel_id"):
            try:
                ch = interaction.guild.get_channel(int(cfg["channel_id"]))
            except Exception:
                ch = None
        template = cfg.get("template") or "Not set (default will be used)"
        desc = f"Enabled: **{enabled}**\nChannel: **{ch.mention if ch else 'Not set'}**\nTimezone: **UTC{(cfg.get('tz_offset') or 0):+g}**\nMention: **{cfg.get('mention_mode') or 'none'}**\nTemplate: {('Set' if cfg.get('template') else 'Default')}"
        em = discord.Embed(title=f"Birthday Admin — {interaction.guild.name}", description=desc, color=discord.Color.blurple())
        view = AdminDashboardView(self, interaction.guild)
        await interaction.response.send_message(embed=em, view=view, ephemeral=True)

    # Additional admin-style import command (attachment)
    @birthday_group.command(name="import_csv", description="Import birthdays from CSV (user_id,month,day,year) - admin only")
    @app_commands.describe(file="CSV file to import")
    async def birthday_import_csv(self, interaction:discord.Interaction, file:discord.Attachment):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
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
            await interaction.followup.send(f"Imported {count} birthdays.", ephemeral=True)
        except Exception as e:
            logger.exception("Import failed: %s", e)
            await interaction.followup.send("Import failed: " + str(e), ephemeral=True)

# ------------------------
# Setup
# ------------------------
async def setup(bot:commands.Bot):
    await bot.add_cog(BirthdayCog(bot))

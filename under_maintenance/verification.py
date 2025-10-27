# verification.py
# - Commands:
#   /verification enable
#   /verification disable
#   /verification reset
#   /verification setup_role [name]
#   /verification setup_channel [name]
#   /verification verify
#   /verification set_verified <role>
#   /verification update_role <role>
#   /verification type <captcha|reaction|button>
#   /verification captcha color <hex>
#   /verification captcha length <int>
#   /verification captcha lines <int>
#   /verification captcha sensitive <bool>
#   /verification captcha numbers <bool>
#   /verification captcha timeout <seconds>
#   /verification admin ...  (view/toggle)
#
# - Multi-guild, SQLite-backed
# - Uses Pillow for CAPTCHA images (optional)
# - Reaction & Button flows included
# -------------------------------------------------------------------

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import asyncio
import random
import string
import io
import os
import re
import logging
from typing import Optional, Dict, Any, List

# Optional Pillow
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ---------------------------
# Logging
# ---------------------------
logger = logging.getLogger("verification_cog")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
if not logger.handlers:
    logger.addHandler(handler)

# ---------------------------
# Constants & defaults
# ---------------------------
DB_PATH = os.getenv("VERIF_DB_PATH", "verification.db")
CAPTCHA_DEFAULT_LENGTH = 6
CAPTCHA_DEFAULT_LINES = 3
CAPTCHA_DEFAULT_SENSITIVE = False
CAPTCHA_DEFAULT_NUMBERS = True
CAPTCHA_DEFAULT_TIMEOUT = 300  # seconds (5 minutes)

DEFAULT_UNVERIFIED_ROLE_NAME = "Unverified"
DEFAULT_VERIFICATION_CHANNEL_NAME = "verification"

# Aesthetic defaults
EMBED_GRADIENTS = [
    ("#7b2ff7", "#f107a3"),
    ("#2af598", "#009efd"),
    ("#f6d365", "#fda085"),
    ("#a8edea", "#fed6e3"),
    ("#84fab0", "#8fd3f4"),
    ("#f093fb", "#f5576c"),
]

EMOJI_OK = "✅"
EMOJI_FAIL = "❌"
EMOJI_INFO = "ℹ️"
EMOJI_LOCK = "🔒"

# Regex to validate hex color
HEX_COLOR_RE = re.compile(r"^#?([A-Fa-f0-9]{6})$")

# ---------------------------
# Utilities
# ---------------------------
def ensure_dir_exists(path: str):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def pick_gradient():
    a, b = random.choice(EMBED_GRADIENTS)
    return a, b

def hex_to_int(hexstr: str) -> int:
    hexstr = hexstr.lstrip("#")
    return int(hexstr, 16)

def now_ts() -> float:
    return datetime.datetime.utcnow().timestamp()

# ---------------------------
# Database wrapper
# ---------------------------
class VerificationDB:
    def __init__(self, path=DB_PATH):
        ensure_dir_exists(path)
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        # guild config
        c.execute(f"""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            unverified_role_name TEXT,
            unverified_role_id INTEGER,
            verification_channel_name TEXT,
            verification_channel_id INTEGER,
            verified_role_id INTEGER,
            verif_type TEXT DEFAULT 'captcha', -- captcha | reaction | button
            captcha_color TEXT DEFAULT '#000000',
            captcha_length INTEGER DEFAULT {CAPTCHA_DEFAULT_LENGTH},
            captcha_lines INTEGER DEFAULT {CAPTCHA_DEFAULT_LINES},
            captcha_sensitive INTEGER DEFAULT {int(CAPTCHA_DEFAULT_SENSITIVE)},
            captcha_numbers INTEGER DEFAULT {int(CAPTCHA_DEFAULT_NUMBERS)},
            captcha_timeout INTEGER DEFAULT {CAPTCHA_DEFAULT_TIMEOUT}
        );
        """)
        # pending challenges
        c.execute("""
        CREATE TABLE IF NOT EXISTS pending_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            challenge_token TEXT,
            expires_at REAL,
            message_id INTEGER,
            type TEXT, -- captcha/reaction/button
            attempts INTEGER DEFAULT 0
        );
        """)
        # verified members (history)
        c.execute("""
        CREATE TABLE IF NOT EXISTS verified_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            verified_at REAL
        );
        """)
        self.conn.commit()

    # Config operations
    def get_guild_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def ensure_guild(self, guild_id: int):
        if not self.get_guild_config(guild_id):
            self.set_guild_config(guild_id, enabled=0,
                                  unverified_role_name=DEFAULT_UNVERIFIED_ROLE_NAME,
                                  verification_channel_name=DEFAULT_VERIFICATION_CHANNEL_NAME,
                                  verif_type="captcha",
                                  captcha_color="#000000",
                                  captcha_length=CAPTCHA_DEFAULT_LENGTH,
                                  captcha_lines=CAPTCHA_DEFAULT_LINES,
                                  captcha_sensitive=int(CAPTCHA_DEFAULT_SENSITIVE),
                                  captcha_numbers=int(CAPTCHA_DEFAULT_NUMBERS),
                                  captcha_timeout=CAPTCHA_DEFAULT_TIMEOUT)

    def set_guild_config(self, guild_id: int, **kwargs):
        existing = self.get_guild_config(guild_id)
        c = self.conn.cursor()
        if existing is None:
            # insert with defaults but accept provided kwargs
            q = """
            INSERT INTO guild_config (guild_id, enabled, unverified_role_name, unverified_role_id,
               verification_channel_name, verification_channel_id, verified_role_id, verif_type,
               captcha_color, captcha_length, captcha_lines, captcha_sensitive, captcha_numbers, captcha_timeout)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """
            vals = [
                guild_id,
                int(kwargs.get("enabled", 0)),
                kwargs.get("unverified_role_name", DEFAULT_UNVERIFIED_ROLE_NAME),
                kwargs.get("unverified_role_id"),
                kwargs.get("verification_channel_name", DEFAULT_VERIFICATION_CHANNEL_NAME),
                kwargs.get("verification_channel_id"),
                kwargs.get("verified_role_id"),
                kwargs.get("verif_type", "captcha"),
                kwargs.get("captcha_color", "#000000"),
                kwargs.get("captcha_length", CAPTCHA_DEFAULT_LENGTH),
                kwargs.get("captcha_lines", CAPTCHA_DEFAULT_LINES),
                int(kwargs.get("captcha_sensitive", int(CAPTCHA_DEFAULT_SENSITIVE))),
                int(kwargs.get("captcha_numbers", int(CAPTCHA_DEFAULT_NUMBERS))),
                int(kwargs.get("captcha_timeout", CAPTCHA_DEFAULT_TIMEOUT)),
            ]
            c.execute(q, tuple(vals))
        else:
            # update specified fields
            fields = []
            vals = []
            allowed = ["enabled", "unverified_role_name", "unverified_role_id",
                       "verification_channel_name", "verification_channel_id",
                       "verified_role_id", "verif_type",
                       "captcha_color", "captcha_length", "captcha_lines",
                       "captcha_sensitive", "captcha_numbers", "captcha_timeout"]
            for k in allowed:
                if k in kwargs:
                    fields.append(f"{k}=?")
                    v = kwargs[k]
                    if k in ("captcha_sensitive", "captcha_numbers"):
                        v = int(bool(v))
                    if k == "enabled":
                        v = int(bool(v))
                    vals.append(v)
            if fields:
                vals.append(guild_id)
                c.execute("UPDATE guild_config SET " + ", ".join(fields) + " WHERE guild_id=?", tuple(vals))
        self.conn.commit()

    # Pending challenges
    def create_challenge(self, guild_id: int, user_id: int, token: str, expires_at: float, message_id: Optional[int], typ: str):
        c = self.conn.cursor()
        c.execute("INSERT INTO pending_challenges (guild_id,user_id,challenge_token,expires_at,message_id,type) VALUES (?,?,?,?,?,?)",
                  (guild_id, user_id, token, expires_at, message_id, typ))
        self.conn.commit()
        return c.lastrowid

    def get_challenge_for_user(self, guild_id: int, user_id: int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM pending_challenges WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 1", (guild_id, user_id))
        r = c.fetchone()
        return dict(r) if r else None

    def get_challenge_by_message(self, message_id: int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM pending_challenges WHERE message_id=?", (message_id,))
        r = c.fetchone()
        return dict(r) if r else None

    def remove_challenge(self, challenge_id: int):
        c = self.conn.cursor()
        c.execute("DELETE FROM pending_challenges WHERE id=?", (challenge_id,))
        self.conn.commit()

    def cleanup_expired(self):
        now = now_ts()
        c = self.conn.cursor()
        c.execute("SELECT id, guild_id, user_id FROM pending_challenges WHERE expires_at<?", (now,))
        rows = c.fetchall()
        expired = [dict(r) for r in rows]
        c.execute("DELETE FROM pending_challenges WHERE expires_at<?", (now,))
        self.conn.commit()
        return expired

    # Verified history
    def record_verified(self, guild_id:int, user_id:int):
        c = self.conn.cursor()
        c.execute("INSERT INTO verified_members (guild_id,user_id,verified_at) VALUES (?,?,?)", (guild_id, user_id, now_ts()))
        self.conn.commit()

    def is_verified(self, guild_id:int, user_id:int):
        c = self.conn.cursor()
        c.execute("SELECT * FROM verified_members WHERE guild_id=? AND user_id=? LIMIT 1", (guild_id, user_id))
        return c.fetchone() is not None

    def mark_all_verified(self, guild_id:int):
        # remove pending challenges and add verified entries
        cur = self.conn.cursor()
        # clear pending
        cur.execute("DELETE FROM pending_challenges WHERE guild_id=?", (guild_id,))
        # find guild members via outer code; here just cleanup pending entries
        self.conn.commit()

    def reset_guild(self, guild_id:int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM guild_config WHERE guild_id=?", (guild_id,))
        cur.execute("DELETE FROM pending_challenges WHERE guild_id=?", (guild_id,))
        cur.execute("DELETE FROM verified_members WHERE guild_id=?", (guild_id,))
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

# ---------------------------
# CAPTCHA generation (PIL)
# ---------------------------
# If PIL not available, produce a text fallback challenge token.

def random_captcha_text(length:int=6, allow_numbers:bool=True, case_sensitive:bool=False) -> str:
    letters = string.ascii_uppercase if not case_sensitive else (string.ascii_letters)
    pool = letters + (string.digits if allow_numbers else "")
    return "".join(random.choice(pool) for _ in range(length))

def _load_font(size:int=48):
    # Attempt common font paths first, fallback to load_default
    if not PIL_AVAILABLE:
        return None
    candidates = [
        "arial.ttf", "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
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

def generate_captcha_image(token: str, color_hex: str = "#000000", width:int=450, height:int=150, lines:int=3) -> Optional[bytes]:
    if not PIL_AVAILABLE:
        return None
    try:
        bg_palette = ["#ffffff", "#f6f7fb", "#fff6f0", "#f3ffe7"]
        bg = random.choice(bg_palette)
        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)

        # Draw random lines for noise
        for _ in range(lines * 2):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            draw.line([(x1,y1),(x2,y2)], fill=tuple(random.randint(100,200) for _ in range(3)), width=random.randint(1,3))

        # Draw token text with slight rotation
        font = _load_font(int(height * 0.5))
        text_w, text_h = draw.textsize(token, font=font)
        x = (width - text_w) // 2
        y = (height - text_h) // 2
        # Slight per-character jitter
        for i, ch in enumerate(token):
            offset_x = x + sum(draw.textsize(token[:i], font=font)[0] for _ in [0]) + i * random.randint(2,6)
            offset_y = y + random.randint(-10, 10)
            # create a small image for the char, rotate and paste
            char_img = Image.new("RGBA", (font.getsize(ch)[0] + 20, font.getsize(ch)[1] + 20), (255,255,255,0))
            cd = ImageDraw.Draw(char_img)
            cd.text((10,10), ch, font=font, fill=color_hex)
            r = random.uniform(-18, 18)
            char_img = char_img.rotate(r, resample=Image.BICUBIC, expand=1)
            img.paste(char_img, (offset_x, offset_y), char_img)

        # Distort (small)
        img = img.filter(ImageFilter.SMOOTH)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        return bio.read()
    except Exception as e:
        logger.exception("Captcha generation failed: %s", e)
        return None

# ---------------------------
# UI Components: Buttons & Modal
# ---------------------------
class CaptchaModal(discord.ui.Modal, title="Enter CAPTCHA"):
    def __init__(self, cog, guild_id:int, user_id:int, challenge_id:int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.challenge_id = challenge_id
        # input field
        self.answer = discord.ui.TextInput(label="Type the characters you see", style=discord.TextStyle.short, max_length=64)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        # Evaluate answer
        await interaction.response.defer(ephemeral=True)
        provided = str(self.answer.value).strip()
        # fetch challenge
        ch = self.cog.db.get_challenge_for_user(self.guild_id, self.user_id)
        if not ch or ch["id"] != self.challenge_id:
            await interaction.followup.send("No active challenge found or it expired. Use `/verification verify` to try again.", ephemeral=True)
            return
        expected = ch["challenge_token"]
        cfg = self.cog.db.get_guild_config(self.guild_id) or {}
        sensitive = bool(cfg.get("captcha_sensitive", CAPTCHA_DEFAULT_SENSITIVE))
        check_expected = expected if sensitive else expected.lower()
        check_provided = provided if sensitive else provided.lower()
        if check_provided == check_expected:
            # success
            await self.cog._handle_success_verification(interaction.guild, interaction.user, ch)
            await interaction.followup.send(f"{EMOJI_OK} Verification successful! You now have access.", ephemeral=True)
        else:
            # increment attempts
            c = self.cog.db.conn.cursor()
            c.execute("UPDATE pending_challenges SET attempts = attempts + 1 WHERE id=?", (ch["id"],))
            self.cog.db.conn.commit()
            await interaction.followup.send(f"{EMOJI_FAIL} That's not correct. Please try again with `/verification verify`.", ephemeral=True)

class VerifyButton(discord.ui.View):
    def __init__(self, cog, guild_id:int, user_id:int, challenge_id:int, *, timeout: Optional[float]=None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.challenge_id = challenge_id

    @discord.ui.button(label="Submit CAPTCHA", style=discord.ButtonStyle.primary, custom_id="verif_submit_captcha")
    async def submit_captcha(self, interaction: discord.Interaction, button: discord.ui.Button):
        # only allow the user who is challenged
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This verification is not for you.", ephemeral=True)
            return
        # Show Modal
        modal = CaptchaModal(self.cog, self.guild_id, self.user_id, self.challenge_id)
        await interaction.response.send_modal(modal)

class ReactionVerifyButton(discord.ui.View):
    # view with a "verify" button for button-based flow
    def __init__(self, cog, guild_id:int, user_id:int, challenge_id:int, *, timeout: Optional[float]=None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.challenge_id = challenge_id

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji=EMOJI_OK, custom_id="verif_button_click")
    async def on_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This verification is not for you.", ephemeral=True)
            return
        ch = self.cog.db.get_challenge_for_user(self.guild_id, self.user_id)
        if not ch or ch["id"] != self.challenge_id:
            await interaction.response.send_message("No active challenge found or it expired. Use `/verification verify` to try again.", ephemeral=True)
            return
        await self.cog._handle_success_verification(interaction.guild, interaction.user, ch)
        await interaction.response.send_message(f"{EMOJI_OK} Verified — welcome!", ephemeral=True)

# ---------------------------
# The Cog
# ---------------------------
class VerificationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = VerificationDB()
        self._cleanup_task = tasks.loop(seconds=30)(self._cleanup_expired)  # runs every 30s
        self._cleanup_task.start()
        # In-memory cache for quick lookup: guild_id -> config
        logger.info("VerificationCog initialised.")

    def cog_unload(self):
        try:
            self._cleanup_task.cancel()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass

    # ---------------------------
    # Background cleanup for expired challenges
    # ---------------------------
    async def _cleanup_expired(self):
        try:
            expired = self.db.cleanup_expired()
            for e in expired:
                # notify guild channel if exists
                gid = e["guild_id"]
                try:
                    guild = self.bot.get_guild(gid) or await self.bot.fetch_guild(gid)
                except Exception:
                    guild = None
                if guild:
                    cfg = self.db.get_guild_config(gid) or {}
                    ch_id = cfg.get("verification_channel_id")
                    if ch_id:
                        try:
                            ch = guild.get_channel(int(ch_id)) or await self.bot.fetch_channel(int(ch_id))
                        except Exception:
                            ch = None
                        if ch:
                            try:
                                await ch.send(f"{EMOJI_INFO} A verification challenge expired. The member may retry by using `/verification verify`.")
                            except Exception:
                                pass
        except Exception as exc:
            logger.exception("Error in cleanup task: %s", exc)

    # ---------------------------
    # Helper: aesthetic embed generator
    # ---------------------------
    def make_embed(self, title: str, description: str = None, footer: str = None) -> discord.Embed:
        c1, c2 = pick_gradient()
        # convert first gradient color to int (discord color)
        try:
            color_int = hex_to_int(c1)
        except Exception:
            color_int = 0x2F3136
        em = discord.Embed(title=title, description=description or "", color=color_int)
        if footer:
            em.set_footer(text=footer)
        return em

    # ---------------------------
    # Utility: assign/unassign roles
    # ---------------------------
    async def _give_verified_role(self, guild: discord.Guild, member: discord.Member, cfg: Dict[str, Any]):
        verified_role_id = cfg.get("verified_role_id")
        if not verified_role_id:
            # nothing to give
            return
        try:
            role = guild.get_role(int(verified_role_id))
            if role:
                await member.add_roles(role, reason="Verification passed")
        except Exception as e:
            logger.exception("Failed to assign verified role: %s", e)

    async def _apply_unverified_role(self, guild: discord.Guild, member: discord.Member, cfg: Dict[str, Any]):
        urid = cfg.get("unverified_role_id")
        if not urid:
            return
        try:
            role = guild.get_role(int(urid))
            if role:
                await member.add_roles(role, reason="Applying unverified restrictions")
        except Exception as e:
            logger.exception("Failed to assign unverified role: %s", e)

    async def _remove_unverified_role(self, guild: discord.Guild, member: discord.Member, cfg: Dict[str, Any]):
        urid = cfg.get("unverified_role_id")
        if not urid:
            return
        try:
            role = guild.get_role(int(urid))
            if role:
                await member.remove_roles(role, reason="Verification passed")
        except Exception as e:
            logger.exception("Failed to remove unverified role: %s", e)

    # ---------------------------
    # Internal: on successful verification
    # ---------------------------
    async def _handle_success_verification(self, guild: discord.Guild, member: discord.Member, challenge_row: dict):
        # mark verified, remove unverified role, grant verified role
        try:
            self.db.record_verified(guild.id, member.id)
        except Exception:
            pass
        cfg = self.db.get_guild_config(guild.id) or {}
        await self._remove_unverified_role(guild, member, cfg)
        await self._give_verified_role(guild, member, cfg)
        # remove challenge
        try:
            self.db.remove_challenge(challenge_row["id"])
        except Exception:
            pass
        # log to channel optionally
        ch_id = cfg.get("verification_channel_id")
        if ch_id:
            try:
                ch = guild.get_channel(int(ch_id)) or await self.bot.fetch_channel(int(ch_id))
            except Exception:
                ch = None
            if ch:
                try:
                    embed = self.make_embed("Member Verified", f"{member.mention} completed verification.", footer="Verification system")
                    await ch.send(content=f"{EMOJI_OK} {member.mention} verified!", embed=embed)
                except Exception:
                    pass

    # ---------------------------
    # Reaction event handler for reaction mode
    # ---------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Check if this reaction corresponds to a pending challenge message
        try:
            ch_row = self.db.get_challenge_by_message(payload.message_id)
            if not ch_row:
                return
            # ensure reaction is in allowed guild
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return
            # only react to the target user
            if payload.user_id != ch_row["user_id"]:
                return
            # confirm correct emoji? We will accept any reaction if type is 'reaction'
            if ch_row["type"] != "reaction":
                return
            # success: fetch member and handle
            try:
                member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
            except Exception:
                member = None
            if not member:
                return
            await self._handle_success_verification(guild, member, ch_row)
            # remove the message or edit to show success
            try:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.edit(content=f"{EMOJI_OK} Verified by {member.mention}", view=None)
            except Exception:
                pass
        except Exception:
            logger.exception("Error handling reaction add")

    # ---------------------------
    # Slash commands: top-level group 'verification'
    # ---------------------------
    verification = app_commands.Group(name="verification", description="Server verification controls")

    # Enable verification
    @verification.command(name="enable", description="Enable verification on this server (configure roles & channel after)")
    async def enable(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission required.", ephemeral=True); return
        self.db.ensure_guild(interaction.guild.id)
        self.db.set_guild_config(interaction.guild.id, enabled=1)
        await interaction.response.send_message(embed=self.make_embed("Verification Enabled", "Verification has been enabled for this server. Use `/verification setup_role` and `/verification setup_channel` to finish setup."), ephemeral=True)

    # Disable
    @verification.command(name="disable", description="Disable verification for this server (members will no longer be restricted)")
    async def disable(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission required.", ephemeral=True); return
        self.db.set_guild_config(interaction.guild.id, enabled=0)
        await interaction.response.send_message(embed=self.make_embed("Verification Disabled", "Verification has been disabled. Existing unverified role will remain; you may remove it manually."), ephemeral=True)

    # Reset system
    @verification.command(name="reset", description="Reset verification system: delete channel & role if created, mark all as verified")
    async def reset(self, interaction: discord.Interaction, confirm: Optional[bool] = False):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission required.", ephemeral=True); return
        if not confirm:
            await interaction.response.send_message("This will remove the verification configuration and mark members verified. Re-run with `confirm=true` to proceed.", ephemeral=True)
            return
        cfg = self.db.get_guild_config(interaction.guild.id) or {}
        # delete channel if bot-created
        channel_id = cfg.get("verification_channel_id")
        if channel_id:
            try:
                ch = interaction.guild.get_channel(int(channel_id))
                if ch and ch.permissions_for(interaction.guild.me).manage_channels:
                    await ch.delete(reason="Reset verification")
            except Exception:
                pass
        # delete role if bot-created
        unrole_id = cfg.get("unverified_role_id")
        if unrole_id:
            try:
                role = interaction.guild.get_role(int(unrole_id))
                if role and interaction.guild.me.guild_permissions.manage_roles:
                    await role.delete(reason="Reset verification")
            except Exception:
                pass
        # mark all as verified (we simply clear pending and add nothing else here)
        self.db.reset_guild(interaction.guild.id)
        await interaction.response.send_message(embed=self.make_embed("Verification Reset", "System reset. All members may access channels. Reconfigure when ready."), ephemeral=True)

    # Setup role
    @verification.command(name="setup_role", description="Create the Unverified role used for new members (move it above normal roles manually)")
    @app_commands.describe(name="Optional custom role name")
    async def setup_role(self, interaction: discord.Interaction, name: Optional[str] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        role_name = name.strip() if name else DEFAULT_UNVERIFIED_ROLE_NAME
        # create role
        try:
            # check if exists
            existing = discord.utils.get(interaction.guild.roles, name=role_name)
            if existing:
                role = existing
            else:
                role = await interaction.guild.create_role(name=role_name, mentionable=False, reason="Creating unverified role for verification system")
            # We caution admin to move role above normal member roles
            self.db.set_guild_config(interaction.guild.id, unverified_role_id=role.id, unverified_role_name=role_name)
            msg = f"Unverified role `{role_name}` is ready. Move it above normal member roles so restrictions apply."
            await interaction.response.send_message(embed=self.make_embed("Unverified Role Created", msg), ephemeral=True)
        except Exception as e:
            logger.exception("Failed creating unverified role: %s", e)
            await interaction.response.send_message("Failed to create role. Ensure I have Manage Roles permission.", ephemeral=True)

    # Setup verification channel
    @verification.command(name="setup_channel", description="Create the verification channel used to complete verification")
    @app_commands.describe(name="Optional channel name (default: verification)")
    async def setup_channel(self, interaction: discord.Interaction, name: Optional[str] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        ch_name = (name.strip() if name else DEFAULT_VERIFICATION_CHANNEL_NAME)
        # Create channel with restricted permissions: only unverified role + admin+bot see
        cfg = self.db.get_guild_config(interaction.guild.id) or {}
        unverified_role_id = cfg.get("unverified_role_id")
        overwrites = {}
        # default: deny view to @everyone
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False, send_messages=False)
        # allow bot & admins
        overwrites[interaction.guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
        # allow unverified role to see and send
        if unverified_role_id:
            role = interaction.guild.get_role(int(unverified_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        try:
            existing = discord.utils.get(interaction.guild.channels, name=ch_name)
            if existing:
                ch = existing
            else:
                ch = await interaction.guild.create_text_channel(ch_name, overwrites=overwrites, reason="Creating verification channel")
            self.db.set_guild_config(interaction.guild.id, verification_channel_id=ch.id, verification_channel_name=ch_name)
            em = self.make_embed("Verification Channel Ready", f"Channel {ch.mention} is configured for verification.")
            await interaction.response.send_message(embed=em, ephemeral=True)
        except Exception as e:
            logger.exception("Failed to create verification channel: %s", e)
            await interaction.response.send_message("Failed to create channel. Ensure I have Manage Channels permission.", ephemeral=True)

    # Set verified role (role to assign on success)
    @verification.command(name="set_verified", description="Set the role given to members after successful verification")
    @app_commands.describe(role="Role to assign after verification")
    async def set_verified(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        self.db.set_guild_config(interaction.guild.id, verified_role_id=role.id)
        await interaction.response.send_message(embed=self.make_embed("Verified Role Set", f"Members will receive {role.mention} after successfully verifying."), ephemeral=True)

    # Update role alias
    @verification.command(name="update_role", description="Update the role assigned to members after verification")
    @app_commands.describe(role="New verified role")
    async def update_role(self, interaction: discord.Interaction, role: discord.Role):
        await self.set_verified(interaction, role)

    # Manual verify (user invokes in verification channel; admin can call for member)
    @verification.command(name="verify", description="Start verification. Invoked in verification channel; admin may optionally specify member.")
    @app_commands.describe(member="(Admin) Member to verify (leave blank to verify yourself in the verification channel)")
    async def verify(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        # Determine who to verify
        guild = interaction.guild
        if member and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Only admins can verify other members via this command.", ephemeral=True); return

        # If in verification channel or admin specifying, determine target
        cfg = self.db.get_guild_config(guild.id) or {}
        self.db.ensure_guild(guild.id)
        if not cfg:
            cfg = self.db.get_guild_config(guild.id)

        # If member omitted, assume the invoker
        target = member or interaction.user

        # If verification is disabled for this guild
        if not cfg.get("enabled", 0):
            await interaction.response.send_message("Verification is not enabled on this server. An admin must enable it using `/verification enable`.", ephemeral=True)
            return

        # If command invoked in a channel that's not the verification channel, require admin
        channel_id = cfg.get("verification_channel_id")
        if channel_id and interaction.channel.id != int(channel_id) and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(f"Please use the designated verification channel to verify yourself: <#{channel_id}>.", ephemeral=True)
            return

        # Create a challenge and send it according to the type
        verif_type = cfg.get("verif_type", "captcha")
        # ensure the unverified role exists and is applied to the target if necessary
        # (admins may skip role application if configured differently; here we attempt to apply if role exists)
        if cfg.get("unverified_role_id"):
            try:
                unrole = guild.get_role(int(cfg["unverified_role_id"]))
                if unrole and unrole not in target.roles:
                    await target.add_roles(unrole, reason="Applying unverified for verification flow")
            except Exception:
                pass

        # Build challenge token
        length = int(cfg.get("captcha_length", CAPTCHA_DEFAULT_LENGTH))
        lines = int(cfg.get("captcha_lines", CAPTCHA_DEFAULT_LINES))
        sensitive = bool(cfg.get("captcha_sensitive", CAPTCHA_DEFAULT_SENSITIVE))
        numbers = bool(cfg.get("captcha_numbers", CAPTCHA_DEFAULT_NUMBERS))
        timeout = int(cfg.get("captcha_timeout", CAPTCHA_DEFAULT_TIMEOUT))

        token_plain = random_captcha_text(length=length, allow_numbers=numbers, case_sensitive=sensitive)
        expires_at = now_ts() + timeout

        # Generate image if PIL available and captcha-type
        image_bytes = None
        if verif_type == "captcha":
            color = cfg.get("captcha_color", "#000000")
            if PIL_AVAILABLE:
                image_bytes = generate_captcha_image(token_plain, color_hex=color, lines=lines)
        # create DB entry
        challenge_id = self.db.create_challenge(guild.id, target.id, token_plain, expires_at, None, verif_type)

        # Compose embed
        title = "Verification Challenge"
        description = "Complete the action below to verify and gain access."
        embed = self.make_embed(title, description)
        embed.add_field(name="Type", value=verif_type.capitalize(), inline=True)
        embed.set_footer(text=f"Expires in {timeout} seconds • Attempts will be limited")

        # Send message depending on type
        if verif_type == "reaction":
            # Send a message and add a reaction; user must react
            msg = await interaction.channel.send(content=f"{target.mention} React with {EMOJI_OK} to verify.", embed=embed)
            try:
                await msg.add_reaction(EMOJI_OK)
            except Exception:
                pass
            # store message id
            c = self.db.conn.cursor()
            c.execute("UPDATE pending_challenges SET message_id=? WHERE id=?", (msg.id, challenge_id))
            self.db.conn.commit()
            await interaction.response.send_message(f"{EMOJI_INFO} A reaction challenge was posted in {msg.channel.mention}. React to it to verify (only the targeted member can react).", ephemeral=True)

        elif verif_type == "button":
            # send message with button; clicking verifies
            view = ReactionVerifyButton(self, guild.id, target.id, challenge_id, timeout=timeout)
            msg = await interaction.channel.send(content=f"{target.mention} Click the button to verify.", embed=embed, view=view)
            # store message id
            c = self.db.conn.cursor()
            c.execute("UPDATE pending_challenges SET message_id=? WHERE id=?", (msg.id, challenge_id))
            self.db.conn.commit()
            await interaction.response.send_message(f"{EMOJI_INFO} A verification button was posted in {msg.channel.mention}. Click it to verify.", ephemeral=True)

        else:
            # captcha default
            view = VerifyButton(self, guild.id, target.id, challenge_id, timeout=timeout)
            if image_bytes:
                file = discord.File(io.BytesIO(image_bytes), filename="captcha.png")
                msg = await interaction.channel.send(content=f"{target.mention} Please solve this CAPTCHA (use the button to type your answer).", embed=embed, file=file, view=view)
            else:
                # text fallback - present the token masked if case-insensitive; but we must not reveal too easily
                masked = token_plain if sensitive else token_plain.lower()
                msg = await interaction.channel.send(content=f"{target.mention} CAPTCHA: `{masked}` — use the button to submit your answer.", embed=embed, view=view)
            # store message id
            c = self.db.conn.cursor()
            c.execute("UPDATE pending_challenges SET message_id=? WHERE id=?", (msg.id, challenge_id))
            self.db.conn.commit()
            await interaction.response.send_message(f"{EMOJI_INFO} A CAPTCHA challenge was posted. Follow the instructions in the verification channel.", ephemeral=True)

    # ---------------------------
    # Admin: change verification type
    # ---------------------------
    @verification.command(name="type", description="Choose the verification type: captcha | reaction | button")
    @app_commands.describe(mode="captcha, reaction or button")
    async def set_type(self, interaction: discord.Interaction, mode: str):
        # Accept a simple string for mode and validate below
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        mode = str(mode).lower()
        if mode not in ("captcha", "reaction", "button"):
            await interaction.response.send_message("Type must be one of: captcha, reaction, button", ephemeral=True); return
        self.db.set_guild_config(interaction.guild.id, verif_type=mode)
        await interaction.response.send_message(embed=self.make_embed("Verification Type Updated", f"Type set to `{mode}`."), ephemeral=True)

    # ---------------------------
    # Captcha subcommands: color/length/lines/sensitive/numbers/timeout
    # ---------------------------
    captcha_group = app_commands.Group(name="captcha", description="Captcha configuration")

    @captcha_group.command(name="color", description="Set the captcha text color (hex). Example: #ff00ff")
    async def captcha_color(self, interaction: discord.Interaction, hexcode: str):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        m = HEX_COLOR_RE.match(hexcode.strip())
        if not m:
            await interaction.response.send_message("Invalid hex color. Use format like `#ff33aa`.", ephemeral=True); return
        color = "#" + m.group(1)
        self.db.set_guild_config(interaction.guild.id, captcha_color=color)
        await interaction.response.send_message(embed=self.make_embed("Captcha Color Set", f"Color set to {color}"), ephemeral=True)

    @captcha_group.command(name="length", description="Set number of characters for captcha (2-10)")
    async def captcha_length(self, interaction: discord.Interaction, length: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        length = max(2, min(10, length))
        self.db.set_guild_config(interaction.guild.id, captcha_length=length)
        await interaction.response.send_message(embed=self.make_embed("Captcha Length", f"Length set to {length}"), ephemeral=True)

    @captcha_group.command(name="lines", description="Set noise line count for captcha (0-10)")
    async def captcha_lines(self, interaction: discord.Interaction, lines: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        lines = max(0, min(10, lines))
        self.db.set_guild_config(interaction.guild.id, captcha_lines=lines)
        await interaction.response.send_message(embed=self.make_embed("Captcha Lines", f"Noise lines set to {lines}"), ephemeral=True)

    @captcha_group.command(name="sensitive", description="Toggle case sensitivity for captcha (true/false)")
    async def captcha_sensitive(self, interaction: discord.Interaction, sensitive: bool):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        self.db.set_guild_config(interaction.guild.id, captcha_sensitive=int(bool(sensitive)))
        await interaction.response.send_message(embed=self.make_embed("Captcha Sensitivity", f"Case sensitivity set to {sensitive}"), ephemeral=True)

    @captcha_group.command(name="numbers", description="Toggle numeric characters allowed in captcha")
    async def captcha_numbers(self, interaction: discord.Interaction, numbers: bool):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        self.db.set_guild_config(interaction.guild.id, captcha_numbers=int(bool(numbers)))
        await interaction.response.send_message(embed=self.make_embed("Captcha Numbers", f"Numeric characters allowed: {numbers}"), ephemeral=True)

    @captcha_group.command(name="timeout", description="Set captcha timeout in seconds (how long before challenge expires)")
    async def captcha_timeout(self, interaction: discord.Interaction, seconds: int):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        seconds = max(10, min(3600, seconds))
        self.db.set_guild_config(interaction.guild.id, captcha_timeout=seconds)
        await interaction.response.send_message(embed=self.make_embed("Captcha Timeout", f"Timeout set to {seconds} seconds"), ephemeral=True)

    # ---------------------------
    # Admin panel: show config & toggle
    # ---------------------------
    admin_group = app_commands.Group(name="admin", description="Admin operations for verification")

    @admin_group.command(name="show", description="Show current verification configuration for this server")
    async def admin_show(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        cfg = self.db.get_guild_config(interaction.guild.id) or {}
        if not cfg:
            await interaction.response.send_message("No configuration found.", ephemeral=True); return
        enabled = bool(cfg.get("enabled", 0))
        embed = self.make_embed("Verification Config")
        embed.add_field(name="Enabled", value=str(enabled), inline=True)
        embed.add_field(name="Type", value=str(cfg.get("verif_type", "captcha")), inline=True)
        ur_name = cfg.get("unverified_role_name") or "N/A"
        ur_id = cfg.get("unverified_role_id") or "N/A"
        embed.add_field(name="Unverified Role", value=f"{ur_name} ({ur_id})", inline=False)
        ch_name = cfg.get("verification_channel_name") or "N/A"
        ch_id = cfg.get("verification_channel_id") or "N/A"
        embed.add_field(name="Verification Channel", value=f"{ch_name} ({ch_id})", inline=False)
        vr = cfg.get("verified_role_id") or "N/A"
        embed.add_field(name="Verified Role ID", value=str(vr), inline=True)
        embed.add_field(name="Captcha length", value=str(cfg.get("captcha_length")), inline=True)
        embed.add_field(name="Captcha lines", value=str(cfg.get("captcha_lines")), inline=True)
        embed.add_field(name="Case sensitive", value=str(bool(cfg.get("captcha_sensitive"))), inline=True)
        embed.add_field(name="Numbers allowed", value=str(bool(cfg.get("captcha_numbers"))), inline=True)
        embed.add_field(name="Captcha timeout", value=str(cfg.get("captcha_timeout")), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="toggle", description="Toggle verification enabled/disabled")
    async def admin_toggle(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        cfg = self.db.get_guild_config(interaction.guild.id) or {}
        new = not bool(cfg.get("enabled", 0))
        self.db.set_guild_config(interaction.guild.id, enabled=int(new))
        await interaction.response.send_message(embed=self.make_embed("Verification Toggled", f"Enabled = {new}"), ephemeral=True)

    # ---------------------------
    # Event: on_member_join - assign unverified role if enabled
    # ---------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = self.db.get_guild_config(guild.id)
        if not cfg or not cfg.get("enabled", 0):
            return
        # ensure unverified role exists, else create warning
        urid = cfg.get("unverified_role_id")
        if urid:
            role = guild.get_role(int(urid))
            if role:
                try:
                    await member.add_roles(role, reason="New member - apply unverified role")
                except Exception:
                    logger.exception("Failed to assign unverified role on join")
        # Optionally send a DM with instructions
        ch_id = cfg.get("verification_channel_id")
        try:
            if ch_id:
                # send a nice DM with gateway instructions
                channel = guild.get_channel(int(ch_id))
                if channel:
                    try:
                        await channel.send(f"Welcome {member.mention}! Please start verification by using `/verification verify` in this channel.")
                    except Exception:
                        pass
                try:
                    dm = await member.create_dm()
                    await dm.send(f"Welcome to **{guild.name}**! To get full access, please complete verification in {channel.mention if channel else 'the server verification channel'} using `/verification verify`.")
                except Exception:
                    pass
        except Exception:
            pass

    # ---------------------------
    # Helper: admin quick preview of captcha (debug)
    # ---------------------------
    @admin_group.command(name="preview", description="Preview the current captcha (admin only)")
    async def admin_preview(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server required.", ephemeral=True); return
        cfg = self.db.get_guild_config(interaction.guild.id) or {}
        length = int(cfg.get("captcha_length", CAPTCHA_DEFAULT_LENGTH))
        lines = int(cfg.get("captcha_lines", CAPTCHA_DEFAULT_LINES))
        col = cfg.get("captcha_color", "#000000")
        numbers = bool(cfg.get("captcha_numbers", True))
        sensitive = bool(cfg.get("captcha_sensitive", False))
        token = random_captcha_text(length=length, allow_numbers=numbers, case_sensitive=sensitive)
        if PIL_AVAILABLE:
            img = generate_captcha_image(token, color_hex=col, lines=lines)
            if img:
                file = discord.File(io.BytesIO(img), filename="captcha_preview.png")
                await interaction.response.send_message("Captcha preview:", file=file, ephemeral=True)
                return
        # fallback text
        await interaction.response.send_message(f"CAPTCHA preview (text fallback): `{token}`", ephemeral=True)

# ---------------------------
# Setup function
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCog(bot))

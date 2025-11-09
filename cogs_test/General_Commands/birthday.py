"""
Birthday Management Cog
Handles user birthdays, announcements, DM notifications, and guild-level settings.
"""

import os
import asyncio
import aiosqlite
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging

# ------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------
CARD_URL = "https://i.postimg.cc/rFtH6FM0/Pink-Watercolor-Floral-Happy-Birthday-Greeting-Card.png"
DB_PATH = os.getenv("BIRTHDAY_DB_PATH", "data/birthdays.db")
CHECK_INTERVAL_SECONDS = 60
DEFAULT_TZ_OFFSET = 0.0
LOG_FILE = Path("logs/birthday_cog.log")

# ------------------------------------------------------
# LOGGING
# ------------------------------------------------------
LOG_FILE.parent.mkdir(exist_ok=True)
logger = logging.getLogger("BirthdayCog")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.info("🎂 Birthday Cog Logging Initialized")

# ------------------------------------------------------
# BIRTHDAY COG
# ------------------------------------------------------
class BirthdayCog(commands.Cog):
    """🎉 Birthday tracking and announcement system"""

    def __init__(self, bot):
        self.bot = bot
        self._announce_locks = set()
        self.check_birthdays.start()

    # --------------------------------------------------
    # DATABASE INITIALIZATION
    # --------------------------------------------------
    async def setup_db(self):
        Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    timezone_offset REAL DEFAULT 0.0,
                    dm_optin INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, guild_id)
                );

                CREATE TABLE IF NOT EXISTS birthday_settings (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    role_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS birthday_announcements (
                    guild_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    PRIMARY KEY (guild_id, date)
                );
            """)
            await db.commit()

    # --------------------------------------------------
    # UTILITY HELPERS
    # --------------------------------------------------
    async def mark_announced(self, guild_id: int, date: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO birthday_announcements (guild_id, date) VALUES (?, ?)",
                (guild_id, date),
            )
            await db.commit()

    async def has_announced_today(self, guild_id: int, date: str) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM birthday_announcements WHERE guild_id = ? AND date = ?",
                (guild_id, date),
            )
            return await cur.fetchone() is not None

    async def cleanup_left_members(self):
        """Remove birthday records of users who left their guild."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT DISTINCT guild_id, user_id FROM birthdays")
            rows = await cursor.fetchall()
        for guild_id, user_id in rows:
            guild = self.bot.get_guild(guild_id)
            if guild and not guild.get_member(user_id):
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "DELETE FROM birthdays WHERE user_id = ? AND guild_id = ?",
                        (user_id, guild_id),
                    )
                    await db.commit()
                    logger.info(f"Removed stale birthday entry for user {user_id} in guild {guild_id}")

    # --------------------------------------------------
    # BIRTHDAY GROUP COMMANDS
    # --------------------------------------------------
    @commands.group(name="birthday", invoke_without_command=True)
    async def birthday_group(self, ctx):
        await ctx.send(
            "🎂 **Birthday Commands:**\n"
            "• `/birthday set YYYY-MM-DD [tz_offset]`\n"
            "• `/birthday view [user]`\n"
            "• `/birthday remove`\n"
            "• `/birthday list`\n"
            "• `/birthday optout`\n"
            "• `/birthday optin`"
        )

    @birthday_group.command(name="set")
    async def set_birthday(self, ctx, date: str, tz_offset: float = DEFAULT_TZ_OFFSET):
        """Set your birthday (format: YYYY-MM-DD)."""
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return await ctx.send("❌ Invalid date format. Use `YYYY-MM-DD`.")
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR REPLACE INTO birthdays (user_id, guild_id, date, timezone_offset)
                VALUES (?, ?, ?, ?)
            """, (ctx.author.id, ctx.guild.id, date, tz_offset))
            await db.commit()
        await ctx.send(f"✅ Birthday saved for {ctx.author.mention}: `{date}` (UTC{tz_offset:+})")

    @birthday_group.command(name="view")
    async def view_birthday(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT date, timezone_offset FROM birthdays WHERE user_id = ? AND guild_id = ?",
                (member.id, ctx.guild.id),
            )
            row = await cur.fetchone()
        if row:
            await ctx.send(f"🎉 {member.mention}'s birthday is `{row[0]}` (UTC{row[1]:+})")
        else:
            await ctx.send(f"❌ No birthday found for {member.mention}.")

    @birthday_group.command(name="remove")
    async def remove_birthday(self, ctx):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM birthdays WHERE user_id = ? AND guild_id = ?", (ctx.author.id, ctx.guild.id))
            await db.commit()
        await ctx.send(f"🗑️ Birthday removed for {ctx.author.mention}.")

    @birthday_group.command(name="list")
    async def list_birthdays(self, ctx):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT user_id, date FROM birthdays WHERE guild_id = ? ORDER BY date",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("📅 No birthdays set yet.")
        msg = "\n".join(f"<@{r[0]}> — `{r[1]}`" for r in rows)
        await ctx.send(f"🎂 **Birthday List:**\n{msg}")

    @birthday_group.command(name="optout")
    async def optout_dm(self, ctx):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE birthdays SET dm_optin = 0 WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            )
            await db.commit()
        await ctx.send("🔕 You will no longer receive birthday DMs.")

    @birthday_group.command(name="optin")
    async def optin_dm(self, ctx):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE birthdays SET dm_optin = 1 WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            )
            await db.commit()
        await ctx.send("📩 You will now receive a private DM on your birthday!")

    # --------------------------------------------------
    # MODERATOR COMMANDS
    # --------------------------------------------------
    @commands.group(name="birthdaymod", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def birthday_mod_group(self, ctx):
        await ctx.send("🛠️ `/birthdaymod setchannel`, `/birthdaymod setrole`, `/birthdaymod push`, `/birthdaymod summary`")

    @birthday_mod_group.command(name="setchannel")
    async def set_channel(self, ctx, channel: discord.TextChannel):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO birthday_settings (guild_id, channel_id, role_id)
                VALUES (?, ?, COALESCE((SELECT role_id FROM birthday_settings WHERE guild_id=?), NULL))
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """, (ctx.guild.id, channel.id, ctx.guild.id))
            await db.commit()
        await ctx.send(f"✅ Birthday channel set to {channel.mention}")

    @birthday_mod_group.command(name="setrole")
    async def set_role(self, ctx, role: discord.Role):
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO birthday_settings (guild_id, role_id, channel_id)
                VALUES (?, ?, COALESCE((SELECT channel_id FROM birthday_settings WHERE guild_id=?), NULL))
                ON CONFLICT(guild_id) DO UPDATE SET role_id = excluded.role_id
            """, (ctx.guild.id, role.id, ctx.guild.id))
            await db.commit()
        await ctx.send(f"✅ Birthday ping role set to {role.mention}")

    @birthday_mod_group.command(name="push")
    async def push_today(self, ctx):
        count = await self.send_birthdays_today(ctx.guild, force=True)
        await ctx.send(f"🎂 Manually pushed {count} birthday message(s)!")

    @birthday_mod_group.command(name="summary")
    async def summary(self, ctx):
        """Show quick birthday summary."""
        await self.setup_db()
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT COUNT(*) FROM birthdays WHERE guild_id=?", (ctx.guild.id,))
            total = (await cur.fetchone())[0]
        await ctx.send(f"📊 This server has **{total}** registered birthdays 🎉")

    # --------------------------------------------------
    # BACKGROUND LOOP
    # --------------------------------------------------
    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_birthdays(self):
        await self.cleanup_left_members()
        await self.setup_db()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        today_md = datetime.utcnow().strftime("%m-%d")

        for guild in self.bot.guilds:
            if guild.id in self._announce_locks:
                continue
            if await self.has_announced_today(guild.id, today_str):
                continue

            count = await self.send_birthdays_today(guild)
            if count > 0:
                await self.mark_announced(guild.id, today_str)
                self._announce_locks.add(guild.id)
                asyncio.create_task(self._release_lock(guild.id))

    async def _release_lock(self, guild_id: int):
        await asyncio.sleep(86400)
        self._announce_locks.discard(guild_id)

    # --------------------------------------------------
    # ANNOUNCEMENT HANDLER
    # --------------------------------------------------
    async def send_birthdays_today(self, guild: discord.Guild, force: bool = False) -> int:
        await self.setup_db()
        today_md = datetime.utcnow().strftime("%m-%d")

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("""
                SELECT user_id, dm_optin FROM birthdays
                WHERE guild_id = ? AND strftime('%m-%d', date) = ?
            """, (guild.id, today_md))
            rows = await cur.fetchall()

            settings = await db.execute_fetchone(
                "SELECT channel_id, role_id FROM birthday_settings WHERE guild_id = ?", (guild.id,)
            )

        if not rows:
            return 0

        channel_id, role_id = settings if settings else (None, None)
        channel = guild.get_channel(channel_id) if channel_id else None
        role_mention = f"<@&{role_id}>" if role_id else ""

        count = 0
        for user_id, dm_optin in rows:
            member = guild.get_member(user_id)
            if not member:
                continue

            # Server Announcement
            if channel:
                content = f"{role_mention} 🎉 Happy Birthday {member.mention}! 🎂"
                embed = discord.Embed(
                    title="Happy Birthday!",
                    description=f"🎈 Wishing you all the best, **{member.display_name}**! 🎈",
                    color=discord.Color.pink(),
                )
                embed.set_image(url=CARD_URL)
                embed.set_footer(text=f"Sent by {guild.name}")
                try:
                    await channel.send(content=content, embed=embed)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to send in {guild.name}: {e}")

            # DM Notification
            if dm_optin:
                try:
                    dm_embed = discord.Embed(
                        title="🎂 Happy Birthday!",
                        description="We hope your day is filled with joy, laughter, and cake! 🍰",
                        color=discord.Color.from_rgb(255, 182, 193),
                    )
                    dm_embed.set_image(url=CARD_URL)
                    dm_embed.set_footer(text=f"From {guild.name} server 💌")
                    await member.send(embed=dm_embed)
                except Exception:
                    logger.info(f"DM disabled or failed for {member}")

        if count and not force:
            await self.mark_announced(guild.id, datetime.utcnow().strftime("%Y-%m-%d"))
        return count


# ------------------------------------------------------
# SETUP
# ------------------------------------------------------
async def setup(bot):
    await bot.add_cog(BirthdayCog(bot))

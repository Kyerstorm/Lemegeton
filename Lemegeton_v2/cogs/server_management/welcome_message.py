"""
Welcome Message Cog
Handles sending setup guides when the bot joins a new server
"""

import discord
from discord.ext import commands
import logging
from pathlib import Path
from typing import Optional
from helpers.embed_helper import build_info_embed

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "welcome_message.log"

logger = logging.getLogger("WelcomeMessage")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                                      datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(stream_handler)

logger.info("Welcome message logging initialized")


class WelcomeMessage(commands.Cog):
    """Handles welcome messages when bot joins new servers"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("WelcomeMessage cog initialized")

    def _find_welcome_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Resolve the best available channel to post the welcome message to.

        Priority: system channel -> a common general-purpose channel -> first
        available text channel the bot can post in.
        """
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            logger.info(f"Using system channel: #{guild.system_channel.name}")
            return guild.system_channel

        for channel in guild.text_channels:
            if channel.name.lower() in ['general', 'main', 'chat', 'lounge'] and channel.permissions_for(guild.me).send_messages:
                logger.info(f"Using general channel: #{channel.name}")
                return channel

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                logger.info(f"Using first available channel: #{channel.name}")
                return channel

        return None

    def _build_welcome_embed(self) -> discord.Embed:
        """Build the setup-guide embed sent when the bot joins a new server."""
        embed = build_info_embed(
            title="Welcome to Lemegeton!",
            description="Thank you for adding me to your server! I'm your anime/manga tracking companion with AniList integration, AI-powered recommendations, and much more."
        )

        embed.add_field(
            name="📋 Quick Setup Guide",
            value="""
**1. Server Configuration**
• Use `/server-config` to set up channels and roles
• Configure moderator permissions and notification channels

**2. User Setup**
• Users can link their AniList accounts with `/login`
• This enables personalized recommendations and tracking

**3. Essential Channels to Configure:**
• **Bot Updates Channel**: `/server-config` → Bot Updates
• **Anime/Manga Completion Channel**: `/server-config` → Completion Notifications
• **Invite Tracking Channel**: `/server-config` → Invite Tracking

**4. Bot Moderators**
• Use `/admin-moderator-manage` to add server administrators
• These users can access advanced configuration options
            """,
            inline=False
        )

        embed.add_field(
            name="🚀 Popular Features",
            value="""
• **Anime/Manga Tracking**: Browse, search, and get recommendations
• **AI Recommendations**: Get personalized suggestions based on your tastes
• **Steam Integration**: Game recommendations and free game notifications
• **Challenge System**: Create reading challenges for your community
            """,
            inline=False
        )

        embed.add_field(
            name="📚 Getting Started",
            value="""
• **Help Command**: `/help` for a full list of commands
• **Profile Setup**: `/login` to connect your AniList account
• **Browse Content**: `/browse` to explore anime and manga
• **Get Recommendations**: `/recommendations` for personalized suggestions
            """,
            inline=False
        )

        embed.set_footer(text="Need help? Use /help or contact server administrators • Bot created by Kyerstorm")
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        return embed

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Send a welcome message with setup guide when bot joins a server"""
        try:
            logger.info(f"Sending welcome message to {guild.name} (ID: {guild.id})")

            welcome_channel = self._find_welcome_channel(guild)
            if not welcome_channel:
                logger.warning(f"No suitable channel found to send welcome message in {guild.name}")
                return

            embed = self._build_welcome_embed()

            await welcome_channel.send(embed=embed)
            logger.info(f"Welcome message sent successfully to #{welcome_channel.name} in {guild.name}")

        except Exception as e:
            logger.error(f"Error sending welcome message to {guild.name}: {e}", exc_info=True)

    async def cog_load(self):
        """Called when the cog loads"""
        logger.info("WelcomeMessage cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog unloads"""
        logger.info("WelcomeMessage cog unloaded")


async def setup(bot: commands.Bot):
    """Setup function required for cog loading"""
    await bot.add_cog(WelcomeMessage(bot))
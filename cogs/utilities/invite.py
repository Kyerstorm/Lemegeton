import discord
from discord import app_commands
from discord.ext import commands
import logging
from pathlib import Path
from config import BOT_ID

# ------------------------------------------------------
# Logging Setup - Safe handling
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "invite.log"

# Setup logger
logger = logging.getLogger("invite")
logger.setLevel(logging.INFO)

# Only add a file handler if not already present; fall back to stream handler on failure
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(stream_handler)

logger.info("Invite cog logging initialized")

class InviteCog(commands.Cog):
    """A cog for generating bot invite links."""

    def __init__(self, bot):
        self.bot = bot
        logger.info("Invite cog initialized")

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("Invite cog loaded successfully")

    @app_commands.command(name="invite", description="Add Lemegeton bot to your server - your ultimate AniList companion!")
    async def invite(self, interaction: discord.Interaction):
        """Generate an invite link for the bot with appropriate permissions."""
        
        try:
            logger.info(f"Invite command requested by {interaction.user.display_name} (ID: {interaction.user.id})")
            
            # Define the permissions the bot needs
            permissions = discord.Permissions(
                send_messages=True,
                manage_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                use_external_emojis=True,
                add_reactions=True,
                manage_roles=True,  # For challenge roles
                view_channel=True,
                connect=True,  # For voice channels if needed
                speak=True,    # For voice channels if needed
            )
            
            # Generate the invite URL
            invite_url = discord.utils.oauth_url(
                client_id=BOT_ID,
                permissions=permissions,
                scopes=['bot', 'applications.commands']
            )
            
            # Create an embed for the response
            embed = discord.Embed(
                title="🤖 Invite Lemegeton Bot",
                description="Click the link below to add this bot to your server!",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="✨ What Lemegeton can do:",
                value=(
                    "• **AniList Integration** - Link your account & track progress\n"
                    "• **Smart Recommendations** - Personal, mood & social suggestions\n"
                    "• **User Profiles** - View detailed stats & achievements\n"
                    "• **Browse & Search** - Find anime, manga & novels easily\n"
                    "• **Leaderboards** - Server rankings & competitions\n"
                    "• **Comparison Tools** - Check compatibility with friends\n"
                    "• **Challenge System** - Reading challenges & goals\n"
                    "• **Steam Integration** - Gaming recommendations too!\n"
                    "• **Timezone Support** - Automatic timestamp conversion"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔒 Required Permissions:",
                value=(
                    "• Send/Read Messages\n"
                    "• Embed Links & Attach Files\n"
                    "• Manage Messages & Roles\n"
                    "• View Channels & Message History"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🌟 Get Started:",
                value=(
                    "After adding the bot, you'll receive an automatic setup guide in your server! "
                    "Use `/login` to connect your AniList account and start tracking your anime/manga journey!"
                ),
                inline=False
            )
            
            embed.set_footer(
                text="Bot developed for anime/manga enthusiasts",
                icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
            )
            
            # Create a view with the invite button
            view = InviteView(invite_url)
            
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True  # Make invite response private to the requester
            )
            
            logger.info(f"Invite link generated successfully for {interaction.user.display_name}")
            
        except Exception as e:
            logger.error(f"Error generating invite link: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to generate invite link. Please try again later.",
                color=discord.Color.red()
            )
            
            await interaction.response.send_message(
                embed=error_embed,
                ephemeral=True
            )


class InviteView(discord.ui.View):
    """View with invite button."""
    
    def __init__(self, invite_url):
        super().__init__(timeout=None)  # No timeout for invite links
        self.invite_url = invite_url
        
        # Add the invite button
        self.add_item(
            discord.ui.Button(
                label="🔗 Add Bot to Server",
                style=discord.ButtonStyle.link,
                url=invite_url
            )
        )


async def setup(bot):
    """Setup function for the cog."""
    await bot.add_cog(InviteCog(bot))
    logger.info("Invite cog successfully loaded")
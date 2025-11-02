import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from pathlib import Path
from datetime import datetime

from database import (
    set_guild_challenge_role, get_guild_challenge_roles, remove_guild_challenge_role,
    set_guild_mod_role, get_guild_mod_role, remove_guild_mod_role,
    add_bot_moderator, remove_bot_moderator, get_all_bot_moderators, is_user_bot_moderator,
    is_user_moderator
)

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "guild_config.log"

# Create logger
logger = logging.getLogger("GuildConfig")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream_handler)

logger.info("Guild Config cog logging initialized - file or stream fallback in use")


class GuildConfig(commands.Cog):
    """Guild configuration management for multi-guild support."""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("GuildConfig cog initialized")
    
    # ============================================================================
    # DEPRECATED COMMANDS - USE /challenge-manage INSTEAD
    # These commands have been consolidated into the /challenge-manage interface
    # Located in: cogs/challenges/challenge_manage.py
    # Kept here commented for reference only
    # ============================================================================
    
    # @app_commands.command(name="setup_challenge_role", description="⚠️ DEPRECATED - Use /challenge-manage instead")
    # @app_commands.describe(
    #     challenge_id="The challenge ID (1-13)",
    #     role="The role to assign when threshold is met", 
    #     threshold="The points threshold to earn the role (default: 1.0)"
    # )
    # async def setup_challenge_role(self, interaction: discord.Interaction, challenge_id: int, role: discord.Role, threshold: float = 1.0):
    #     """DEPRECATED: Set up a challenge role. Use /challenge-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/challenge-manage` and click the **� Manage Roles** button.\n"
    #         "You can set up, view, and remove challenge roles there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="list_challenge_roles", description="⚠️ DEPRECATED - Use /challenge-manage instead")
    # async def list_challenge_roles(self, interaction: discord.Interaction):
    #     """DEPRECATED: List all challenge roles. Use /challenge-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/challenge-manage` and click the **🎭 Manage Roles** button.\n"
    #         "You can set up, view, and remove challenge roles there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="remove_challenge_role", description="⚠️ DEPRECATED - Use /challenge-manage instead")
    # @app_commands.describe(
    #     challenge_id="The challenge ID to remove role for",
    #     threshold="The specific threshold to remove (leave empty to remove all thresholds)"
    # )
    # async def remove_challenge_role(self, interaction: discord.Interaction, challenge_id: int, threshold: float = None):
    #     """DEPRECATED: Remove a challenge role configuration. Use /challenge-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/challenge-manage` and click the **🎭 Manage Roles** button.\n"
    #         "You can set up, view, and remove challenge roles there.",
    #         ephemeral=True
    #     )
    
    # ============================================================================
    # END DEPRECATED COMMANDS
    # ============================================================================

    # ============================================================================
    # DEPRECATED COMMANDS - USE /server-config INSTEAD
    # These commands have been consolidated into the unified /server-config interface
    # Located in: cogs/server_management/server_config.py
    # Kept here commented for reference only
    # ============================================================================
    
    # @app_commands.command(name="set_mod_role", description="⚠️ DEPRECATED - Use /server-config instead")
    # @app_commands.describe(role="The role to designate as moderator role")
    # @app_commands.default_permissions(manage_guild=True)
    # async def set_mod_role(self, interaction: discord.Interaction, role: discord.Role):
    #     """DEPRECATED: Set the moderator role for the guild. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can manage moderator roles, channels, and all server settings there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="show_mod_role", description="⚠️ DEPRECATED - Use /server-config instead")
    # @app_commands.default_permissions(manage_guild=True)
    # async def show_mod_role(self, interaction: discord.Interaction):
    #     """DEPRECATED: Show the current moderator role. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can view moderator roles, channels, and all server settings there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="remove_mod_role", description="⚠️ DEPRECATED - Use /server-config instead")
    # @app_commands.default_permissions(manage_guild=True)
    # async def remove_mod_role(self, interaction: discord.Interaction):
    #     """DEPRECATED: Remove the moderator role configuration. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can manage moderator roles, channels, and all server settings there.",
    #         ephemeral=True
    #     )
    
    # ============================================================================
    # END DEPRECATED COMMANDS
    # ============================================================================
    
    # Note: If you need to restore these commands temporarily, uncomment the code above
    # and comment out the deprecation messages. However, the new /server-config interface
    # is recommended for better UX and consistency.
    
    # Leftover code from deprecated commands above - commented out
    # if not current_role_id:
    #     await interaction.response.send_message(
    #         "📝 **No Moderator Role Configuration**\n"
    #         "There is no moderator role currently set for this server.",
    #         ephemeral=True
    #     )
    #     return
    # 
    # # Remove the mod role configuration
    # success = await remove_guild_mod_role(interaction.guild.id)
    # 
    # if success:
    #     current_role = interaction.guild.get_role(current_role_id)
    #     role_mention = current_role.mention if current_role else f"<@&{current_role_id}>"
    #     
    #     await interaction.response.send_message(
    #         f"✅ **Moderator Role Configuration Removed!**\n"
    #         f"🗑️ Removed: {role_mention}\n"
    #         f"🔄 Moderator commands will now fall back to checking Discord permissions.",
    #         ephemeral=True
    #     )
    #     logger.info(f"Removed mod role configuration for guild {interaction.guild.id}")
    # else:
    #     await interaction.response.send_message("❌ Failed to remove moderator role configuration. Please try again.", ephemeral=True)
    # 
    # except Exception as e:
    #     logger.error(f"Error removing mod role: {e}", exc_info=True)
    #     await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)

    # ============================================================================
    # DEPRECATED COMMANDS - USE /admin-moderator-manage INSTEAD
    # These commands have been consolidated into the unified /admin-moderator-manage interface
    # Located in: cogs/bot_management/bot_moderators.py
    # Kept here commented for reference only
    # ============================================================================
    
    # @app_commands.command(name="add_bot_moderator", description="⚠️ DEPRECATED - Use /admin-moderator-manage instead")
    # @app_commands.describe(user="The user to add as a bot moderator")
    # async def remove_bot_moderator_cmd(self, interaction: discord.Interaction, user: discord.User):
    #     """DEPRECATED: Remove a bot moderator. Use /admin-moderator-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/admin-moderator-manage` for a unified management interface.\n"
    #         "You can add, remove, and view bot moderators there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="remove_bot_moderator", description="⚠️ DEPRECATED - Use /admin-moderator-manage instead")
    # @app_commands.describe(user="The user to remove as a bot moderator")
    # async def add_bot_moderator_cmd(self, interaction: discord.Interaction, user: discord.User):
    #     """DEPRECATED: Add a bot moderator. Use /admin-moderator-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/admin-moderator-manage` for a unified management interface.\n"
    #         "You can add, remove, and view bot moderators there.",
    #         ephemeral=True
    #     )
    
    # @app_commands.command(name="list_bot_moderators", description="⚠️ DEPRECATED - Use /admin-moderator-manage instead")
    # async def list_bot_moderators_cmd(self, interaction: discord.Interaction):
    #     """DEPRECATED: List all bot moderators. Use /admin-moderator-manage instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/admin-moderator-manage` for a unified management interface.\n"
    #         "You can add, remove, and view bot moderators there.",
    #         ephemeral=True
    #     )
    
    # ============================================================================
    # END DEPRECATED COMMANDS
    # ============================================================================


async def setup(bot):
    await bot.add_cog(GuildConfig(bot))
    logger.info("GuildConfig cog loaded successfully")
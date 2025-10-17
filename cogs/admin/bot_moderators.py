"""
Unified Bot Moderators Management Interface
Consolidates bot moderator commands into a single interactive interface
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from pathlib import Path
from datetime import datetime

from database import (
    add_bot_moderator, remove_bot_moderator, get_all_bot_moderators, 
    is_user_bot_moderator
)

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "bot_moderators.log"

logger = logging.getLogger("BotModerators")
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

logger.info("Bot moderators logging initialized")


class BotModeratorsMainView(discord.ui.View):
    """Main menu view for bot moderators management"""
    
    def __init__(self, cog):
        super().__init__(timeout=300.0)
        self.cog = cog
    
    @discord.ui.button(label="👥 View Moderators", style=discord.ButtonStyle.primary, row=0)
    async def view_moderators(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View all bot moderators"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            moderators = await get_all_bot_moderators()
            
            if not moderators:
                embed = discord.Embed(
                    title="👥 Bot Moderators",
                    description="There are currently no bot moderators configured.\n\nUse the **Add Moderator** button to add bot moderators.",
                    color=0xED4245
                )
                embed.set_footer(text="Bot moderators can publish changelogs and manage bot-wide settings")
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Displayed empty bot moderators list to {interaction.user.id}")
                return
            
            embed = discord.Embed(
                title="👑 Bot Moderators",
                description="Users who can perform bot-wide actions (changelog publishing, bot management, etc.)",
                color=0x9B59B6
            )
            
            moderator_list = []
            for discord_id, username, added_by, created_at in moderators:
                user = self.cog.bot.get_user(discord_id)
                user_mention = user.mention if user else f"<@{discord_id}>"
                
                # Get who added them
                added_by_user = self.cog.bot.get_user(added_by)
                added_by_mention = added_by_user.display_name if added_by_user else f"ID: {added_by}"
                
                # Parse timestamp
                try:
                    if isinstance(created_at, str):
                        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                        timestamp = int(dt.timestamp())
                    elif hasattr(created_at, 'timestamp'):
                        timestamp = int(created_at.timestamp())
                    else:
                        timestamp = int(created_at)
                    date_display = f"<t:{timestamp}:R>"
                except (ValueError, TypeError):
                    date_display = str(created_at)
                
                moderator_list.append(
                    f"👑 {user_mention} (`{username}`)\n"
                    f"   └ Added by: {added_by_mention} • {date_display}"
                )
            
            embed.add_field(
                name=f"📊 Total Moderators: {len(moderators)}",
                value="\n\n".join(moderator_list),
                inline=False
            )
            
            embed.set_footer(text="Bot moderators can publish changelogs and manage bot-wide settings")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Displayed {len(moderators)} bot moderators to {interaction.user.id}")
        
        except Exception as e:
            logger.error(f"Error viewing bot moderators: {e}", exc_info=True)
            await interaction.followup.send("❌ Error loading bot moderators list.", ephemeral=True)
    
    @discord.ui.button(label="➕ Add Moderator", style=discord.ButtonStyle.success, row=0)
    async def add_moderator(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add a bot moderator"""
        modal = AddBotModeratorModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➖ Remove Moderator", style=discord.ButtonStyle.danger, row=0)
    async def remove_moderator(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove a bot moderator"""
        modal = RemoveBotModeratorModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="ℹ️ About Bot Moderators", style=discord.ButtonStyle.secondary, row=1)
    async def about_moderators(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show information about bot moderators"""
        embed = discord.Embed(
            title="ℹ️ About Bot Moderators",
            description="Bot moderators have elevated permissions for bot-wide actions.",
            color=0x5865F2
        )
        
        embed.add_field(
            name="🔑 Permissions",
            value=(
                "• **Changelog Publishing** - Post update announcements to all servers\n"
                "• **Bot-Wide Management** - Configure bot settings across all guilds\n"
                "• **Moderator Management** - Add or remove other bot moderators\n"
                "• **View Moderator List** - See all users with elevated permissions"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🛡️ Security Notes",
            value=(
                "• Bot moderators have **global permissions** across all servers\n"
                "• Only grant this role to **highly trusted** users\n"
                "• Actions are logged with timestamps and attribution\n"
                "• The bot owner always has full permissions"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔄 Management",
            value=(
                "• Use **Add Moderator** to grant permissions\n"
                "• Use **Remove Moderator** to revoke permissions\n"
                "• View current moderators with **View Moderators**"
            ),
            inline=False
        )
        
        embed.set_footer(text="Bot Moderator System | Manage with care")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"Displayed bot moderator info to {interaction.user.id}")


class AddBotModeratorModal(discord.ui.Modal):
    """Modal for adding a bot moderator"""
    
    def __init__(self, cog):
        super().__init__(title="Add Bot Moderator")
        self.cog = cog
    
    user_id = discord.ui.TextInput(
        label="User ID or User Mention",
        placeholder="Enter user ID (e.g., 123456789) or mention (e.g., @username)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse user ID from input
            user_id_str = self.user_id.value.strip()
            
            # Remove mention formatting if present
            user_id_str = user_id_str.replace("<@", "").replace("!", "").replace(">", "")
            
            # Convert to int
            user_id = int(user_id_str)
            
            # Get the user
            user = self.cog.bot.get_user(user_id)
            
            if not user:
                # Try to fetch user if not in cache
                try:
                    user = await self.cog.bot.fetch_user(user_id)
                except discord.NotFound:
                    await interaction.followup.send("❌ User not found. Please check the user ID.", ephemeral=True)
                    return
            
            # Check if user is a bot
            if user.bot:
                await interaction.followup.send("❌ Cannot add bots as bot moderators.", ephemeral=True)
                return
            
            # Add the bot moderator
            success = await add_bot_moderator(user.id, user.display_name, interaction.user.id)
            
            if success:
                embed = discord.Embed(
                    title="✅ Bot Moderator Added",
                    description=f"**User:** {user.mention}\n**Name:** {user.display_name}\n\nThis user can now perform bot-wide actions.",
                    color=0x57F287
                )
                embed.add_field(
                    name="🔑 Granted Permissions",
                    value="• Changelog publishing\n• Bot-wide management\n• Moderator management",
                    inline=False
                )
                embed.set_footer(text=f"Added by {interaction.user.display_name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Added bot moderator: {user.display_name} ({user.id}) by {interaction.user.display_name} ({interaction.user.id})")
            else:
                await interaction.followup.send("❌ Failed to add bot moderator. They may already be a moderator.", ephemeral=True)
        
        except ValueError:
            await interaction.followup.send("❌ Invalid user ID format. Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error adding bot moderator: {e}", exc_info=True)
            await interaction.followup.send("❌ Error adding bot moderator.", ephemeral=True)


class RemoveBotModeratorModal(discord.ui.Modal):
    """Modal for removing a bot moderator"""
    
    def __init__(self, cog):
        super().__init__(title="Remove Bot Moderator")
        self.cog = cog
    
    user_id = discord.ui.TextInput(
        label="User ID or User Mention",
        placeholder="Enter user ID (e.g., 123456789) or mention (e.g., @username)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse user ID from input
            user_id_str = self.user_id.value.strip()
            
            # Remove mention formatting if present
            user_id_str = user_id_str.replace("<@", "").replace("!", "").replace(">", "")
            
            # Convert to int
            user_id = int(user_id_str)
            
            # Get the user (for display purposes)
            user = self.cog.bot.get_user(user_id)
            
            if not user:
                # Try to fetch user if not in cache
                try:
                    user = await self.cog.bot.fetch_user(user_id)
                except discord.NotFound:
                    # User not found, but we can still remove them from database
                    pass
            
            # Remove the bot moderator
            success = await remove_bot_moderator(user_id)
            
            if success:
                user_display = user.mention if user else f"<@{user_id}>"
                user_name = user.display_name if user else f"User ID: {user_id}"
                
                embed = discord.Embed(
                    title="✅ Bot Moderator Removed",
                    description=f"**User:** {user_display}\n**Name:** {user_name}\n\nThis user can no longer perform bot-wide actions.",
                    color=0x57F287
                )
                embed.add_field(
                    name="🚫 Revoked Permissions",
                    value="• Changelog publishing\n• Bot-wide management\n• Moderator management",
                    inline=False
                )
                embed.set_footer(text=f"Removed by {interaction.user.display_name}")
                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(f"Removed bot moderator: {user_name} ({user_id}) by {interaction.user.display_name} ({interaction.user.id})")
            else:
                await interaction.followup.send("❌ Failed to remove bot moderator. They may not be a moderator.", ephemeral=True)
        
        except ValueError:
            await interaction.followup.send("❌ Invalid user ID format. Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error removing bot moderator: {e}", exc_info=True)
            await interaction.followup.send("❌ Error removing bot moderator.", ephemeral=True)


class BotModerators(commands.Cog):
    """Unified bot moderators management interface"""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("BotModerators cog initialized")
    
    @app_commands.command(name="admin-moderator-manage", description="👑 Manage bot moderators (bot-wide permissions)")
    async def moderators(self, interaction: discord.Interaction):
        """Unified bot moderators management interface"""
        
        # Check if user is admin or existing bot moderator
        if not await is_user_bot_moderator(interaction.user):
            await interaction.response.send_message(
                "❌ **Access Denied**\n\n"
                "Only bot administrators and existing moderators can manage bot moderators.\n\n"
                "Bot moderators have **global permissions** across all servers. "
                "If you need server-specific moderation, use `/server-config` instead.",
                ephemeral=True
            )
            return
        
        try:
            logger.info(f"Bot moderators interface opened by {interaction.user.display_name} ({interaction.user.id})")
            
            embed = discord.Embed(
                title="👑 Bot Moderators Management",
                description=(
                    "Manage users with **bot-wide permissions** for global actions.\n\n"
                    "⚠️ **Important:** Bot moderators have elevated permissions across **all servers**. "
                    "Only grant this role to highly trusted users."
                ),
                color=0x9B59B6
            )
            
            embed.add_field(
                name="🔑 What Bot Moderators Can Do",
                value=(
                    "• **Publish Changelogs** to all configured servers\n"
                    "• **Manage Bot-Wide Settings** across all guilds\n"
                    "• **Add/Remove Bot Moderators** (moderator management)\n"
                    "• **View Bot Moderator List** and audit logs"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🎯 Quick Actions",
                value=(
                    "• **View Moderators** - See all current bot moderators\n"
                    "• **Add Moderator** - Grant bot-wide permissions\n"
                    "• **Remove Moderator** - Revoke bot-wide permissions\n"
                    "• **About** - Learn more about bot moderators"
                ),
                inline=False
            )
            
            embed.set_footer(text="Bot Moderator System | Manage with care")
            
            view = BotModeratorsMainView(self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Bot moderators main menu sent to {interaction.user.id}")
        
        except Exception as e:
            logger.error(f"Error in bot moderators command: {e}", exc_info=True)
            await interaction.response.send_message("❌ Error opening bot moderators management. Please try again.", ephemeral=True)


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(BotModerators(bot))
    logger.info("BotModerators cog loaded successfully")

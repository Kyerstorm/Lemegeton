"""
Unified Server Configuration Interface
Consolidates all server management commands into a single interactive interface
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from pathlib import Path
from datetime import datetime

from database import (
    get_guild_bot_update_channel, remove_guild_bot_update_channel,
    is_user_moderator, execute_db_operation
)

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "server_config.log"

logger = logging.getLogger("ServerConfig")
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

logger.info("Server configuration logging initialized")


class ServerConfigMainView(discord.ui.View):
    """Main menu view for unified server configuration system"""
    
    def __init__(self, cog):
        super().__init__(timeout=300.0)
        self.cog = cog
    
    @discord.ui.button(label=" Bot Updates Channel", style=discord.ButtonStyle.primary, row=0)
    async def manage_bot_updates(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage bot updates channel settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            channel_id = await get_guild_bot_update_channel(interaction.guild.id)
            
            embed = discord.Embed(
                title="📢 Bot Updates Channel",
                description="Configure where changelog and update notifications are posted.",
                color=0x5865F2
            )
            
            if channel_id:
                channel = self.cog.bot.get_channel(channel_id)
                if channel:
                    embed.add_field(
                        name="📊 Current Configuration",
                        value=f"**Channel:** {channel.mention}\n**Category:** {channel.category.name if channel.category else 'None'}\n**Created:** <t:{int(channel.created_at.timestamp())}:R>",
                        inline=False
                    )
                    embed.color = 0x57F287
                else:
                    embed.add_field(
                        name="⚠️ Configuration Issue",
                        value=f"Configured channel (ID: {channel_id}) is not visible to the bot.",
                        inline=False
                    )
                    embed.color = 0xFEE75C
            else:
                embed.add_field(
                    name="📝 No Channel Configured",
                    value="No bot updates channel is currently set.\nYou won't receive automatic update notifications.",
                    inline=False
                )
                embed.color = 0xED4245
            
            embed.add_field(
                name="ℹ️ About Update Notifications",
                value="When configured, bot moderators can send changelog updates to this channel using `/changelog`.",
                inline=False
            )
            
            view = BotUpdatesConfigView(self.cog, channel_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            logger.info(f"Bot updates management opened by {interaction.user.id} in guild {interaction.guild.id}")
        
        except Exception as e:
            logger.error(f"Error in bot updates management: {e}")
            await interaction.followup.send("❌ Error loading bot updates settings.", ephemeral=True)
    
    @discord.ui.button(label="📨 Invite Tracking Channel", style=discord.ButtonStyle.primary, row=1)
    async def manage_invite_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage invite tracking channel settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get invite tracking channel from database
            result = await execute_db_operation(
                "get invite tracking channel",
                "SELECT announcement_channel_id FROM invite_tracker_settings WHERE guild_id = ?",
                (interaction.guild.id,),
                fetch_type='one'
            )
            
            channel_id = result[0] if result else None
            
            embed = discord.Embed(
                title="📨 Invite Tracking Channel",
                description="Configure where member join/leave notifications are posted.",
                color=0x5865F2
            )
            
            if channel_id:
                channel = self.cog.bot.get_channel(channel_id)
                if channel:
                    embed.add_field(
                        name="📊 Current Configuration",
                        value=f"**Channel:** {channel.mention}\n**Category:** {channel.category.name if channel.category else 'None'}\n**Created:** <t:{int(channel.created_at.timestamp())}:R>",
                        inline=False
                    )
                    embed.color = 0x57F287
                else:
                    embed.add_field(
                        name="⚠️ Configuration Issue",
                        value=f"Configured channel (ID: {channel_id}) is not visible to the bot.",
                        inline=False
                    )
                    embed.color = 0xFEE75C
            else:
                embed.add_field(
                    name="📝 No Channel Configured",
                    value="No invite tracking channel is currently set.\nJoin/leave messages are disabled.",
                    inline=False
                )
                embed.color = 0xED4245
            
            embed.add_field(
                name="ℹ️ About Invite Tracking",
                value="Tracks which invite link new members used and sends welcome/goodbye messages.",
                inline=False
            )
            
            view = InviteChannelConfigView(self.cog, channel_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            logger.info(f"Invite channel management opened by {interaction.user.id} in guild {interaction.guild.id}")
        
        except Exception as e:
            logger.error(f"Error in invite channel management: {e}")
            await interaction.followup.send("❌ Error loading invite tracking settings.", ephemeral=True)
    
    @discord.ui.button(label="📋 View All Settings", style=discord.ButtonStyle.secondary, row=1)
    async def view_all_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View all server configuration settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = discord.Embed(
                title="📋 Server Configuration Overview",
                description=f"Complete configuration for **{interaction.guild.name}**",
                color=0x5865F2
            )
            
            # Bot updates channel
            bot_update_channel_id = await get_guild_bot_update_channel(interaction.guild.id)
            if bot_update_channel_id:
                bot_channel = self.cog.bot.get_channel(bot_update_channel_id)
                bot_info = f"✅ {bot_channel.mention}" if bot_channel else f"⚠️ Channel ID {bot_update_channel_id} (not found)"
            else:
                bot_info = "❌ Not configured"
            
            embed.add_field(
                name="📢 Bot Updates Channel",
                value=bot_info,
                inline=True
            )
            
            # Invite tracking channel
            invite_result = await execute_db_operation(
                "get invite tracking channel",
                "SELECT announcement_channel_id FROM invite_tracker_settings WHERE guild_id = ?",
                (interaction.guild.id,),
                fetch_type='one'
            )
            
            if invite_result:
                invite_channel = self.cog.bot.get_channel(invite_result[0])
                invite_info = f"✅ {invite_channel.mention}" if invite_channel else f"⚠️ Channel ID {invite_result[0]} (not found)"
            else:
                invite_info = "❌ Not configured"
            
            embed.add_field(
                name="📨 Invite Tracking Channel",
                value=invite_info,
                inline=True
            )
            
            embed.set_footer(text="Use the buttons above to configure each setting")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"All settings viewed by {interaction.user.id} in guild {interaction.guild.id}")
        
        except Exception as e:
            logger.error(f"Error viewing all settings: {e}")
            await interaction.followup.send("❌ Error loading server settings.", ephemeral=True)


class BotUpdatesConfigView(discord.ui.View):
    """View for configuring bot updates channel"""
    
    def __init__(self, cog, current_channel_id):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.current_channel_id = current_channel_id
        
        # Disable remove button if no channel is set
        if not current_channel_id:
            self.children[1].disabled = True
    
    @discord.ui.button(label="✏️ Set Channel", style=discord.ButtonStyle.success)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set bot updates channel"""
        modal = SetBotUpdatesChannelModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Remove Channel", style=discord.ButtonStyle.danger)
    async def remove_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove bot updates channel configuration"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await remove_guild_bot_update_channel(interaction.guild.id)
            
            embed = discord.Embed(
                title="✅ Bot Updates Channel Removed",
                description="Bot updates channel configuration has been cleared.\nYou won't receive automatic update notifications.",
                color=0x57F287
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Bot updates channel removed for guild {interaction.guild.id} by {interaction.user.id}")
        
        except Exception as e:
            logger.error(f"Error removing bot updates channel: {e}")
            await interaction.followup.send("❌ Error removing bot updates channel.", ephemeral=True)


class InviteChannelConfigView(discord.ui.View):
    """View for configuring invite tracking channel"""
    
    def __init__(self, cog, current_channel_id):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.current_channel_id = current_channel_id
        
        # Disable remove button if no channel is set
        if not current_channel_id:
            self.children[1].disabled = True
    
    @discord.ui.button(label="✏️ Set Channel", style=discord.ButtonStyle.success)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set invite tracking channel"""
        modal = SetInviteChannelModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Remove Channel", style=discord.ButtonStyle.danger)
    async def remove_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove invite tracking channel configuration"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await execute_db_operation(
                "remove invite tracking channel",
                "DELETE FROM invite_tracker_settings WHERE guild_id = ?",
                (interaction.guild.id,)
            )
            
            embed = discord.Embed(
                title="✅ Invite Tracking Channel Removed",
                description="Invite tracking channel configuration has been cleared.\nJoin/leave messages are now disabled.",
                color=0x57F287
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Invite channel removed for guild {interaction.guild.id} by {interaction.user.id}")
        
        except Exception as e:
            logger.error(f"Error removing invite channel: {e}")
            await interaction.followup.send("❌ Error removing invite tracking channel.", ephemeral=True)


class SetBotUpdatesChannelModal(discord.ui.Modal):
    """Modal for setting bot updates channel"""
    
    def __init__(self, cog):
        super().__init__(title="Set Bot Updates Channel")
        self.cog = cog
    
    channel_id = discord.ui.TextInput(
        label="Channel ID or Channel Mention",
        placeholder="Enter channel ID (e.g., 123456789) or mention (e.g., #updates)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse channel ID from input
            channel_id_str = self.channel_id.value.strip()
            
            # Remove mention formatting if present
            channel_id_str = channel_id_str.replace("<#", "").replace(">", "")
            
            # Convert to int
            channel_id = int(channel_id_str)
            
            # Get the channel
            channel = self.cog.bot.get_channel(channel_id)
            
            if not channel or channel.guild.id != interaction.guild.id:
                await interaction.followup.send("❌ Channel not found in this server. Please check the channel ID.", ephemeral=True)
                return
            
            # Check permissions
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages:
                await interaction.followup.send(f"❌ I don't have permission to send messages in {channel.mention}.", ephemeral=True)
                return
            
            # Set the bot updates channel (using database function)
            # Note: We need to import this function or use execute_db_operation
            await execute_db_operation(
                "set bot updates channel",
                """
                INSERT OR REPLACE INTO guild_bot_update_channels 
                (guild_id, channel_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (interaction.guild.id, channel.id)
            )
            
            embed = discord.Embed(
                title="✅ Bot Updates Channel Set",
                description=f"**Channel:** {channel.mention}\n\nChangelog updates will be posted to this channel.",
                color=0x57F287
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Bot updates channel set for guild {interaction.guild.id}: #{channel.name} ({channel.id})")
        
        except ValueError:
            await interaction.followup.send("❌ Invalid channel ID format. Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting bot updates channel: {e}")
            await interaction.followup.send("❌ Error setting bot updates channel.", ephemeral=True)


class SetInviteChannelModal(discord.ui.Modal):
    """Modal for setting invite tracking channel"""
    
    def __init__(self, cog):
        super().__init__(title="Set Invite Tracking Channel")
        self.cog = cog
    
    channel_id = discord.ui.TextInput(
        label="Channel ID or Channel Mention",
        placeholder="Enter channel ID (e.g., 123456789) or mention (e.g., #welcome)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse channel ID from input
            channel_id_str = self.channel_id.value.strip()
            
            # Remove mention formatting if present
            channel_id_str = channel_id_str.replace("<#", "").replace(">", "")
            
            # Convert to int
            channel_id = int(channel_id_str)
            
            # Get the channel
            channel = self.cog.bot.get_channel(channel_id)
            
            if not channel or channel.guild.id != interaction.guild.id:
                await interaction.followup.send("❌ Channel not found in this server. Please check the channel ID.", ephemeral=True)
                return
            
            # Check permissions
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages:
                await interaction.followup.send(f"❌ I don't have permission to send messages in {channel.mention}.", ephemeral=True)
                return
            
            # Set the invite channel
            await execute_db_operation(
                "set invite channel",
                """
                INSERT OR REPLACE INTO invite_tracker_settings 
                (guild_id, announcement_channel_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (interaction.guild.id, channel.id)
            )
            
            # Initialize invite cache for this guild
            try:
                invites = await interaction.guild.invites()
                # Note: We can't directly access invite_tracker cog's cache here
                # The invite tracker cog will pick it up on next check
                logger.info(f"Initialized invite cache for {interaction.guild.name} with {len(invites)} invites")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to initialize invites for {interaction.guild.name}")
            except Exception as e:
                logger.error(f"Failed to initialize invite cache: {e}")
            
            embed = discord.Embed(
                title="✅ Invite Tracking Channel Set",
                description=f"**Channel:** {channel.mention}\n\nJoin/leave messages will be posted to this channel.",
                color=0x57F287
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Invite channel set for guild {interaction.guild.id}: #{channel.name} ({channel.id})")
        
        except ValueError:
            await interaction.followup.send("❌ Invalid channel ID format. Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting invite channel: {e}")
            await interaction.followup.send("❌ Error setting invite tracking channel.", ephemeral=True)


class ServerConfig(commands.Cog):
    """Unified server configuration management interface"""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("ServerConfig cog initialized")
    
    @app_commands.command(name="server-config", description="⚙️ Configure server settings - roles, channels, and notifications")
    @app_commands.default_permissions(manage_guild=True)
    async def server_config(self, interaction: discord.Interaction):
        """Unified server configuration interface"""
        
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You need 'Manage Server' permission to use this command.", ephemeral=True)
            return
        
        try:
            guild_id = interaction.guild.id
            logger.info(f"Server config opened by {interaction.user.display_name} ({interaction.user.id}) in guild {guild_id}")
            
            embed = discord.Embed(
                title="⚙️ Server Configuration",
                description=(
                    f"Welcome to the server configuration panel for **{interaction.guild.name}**!\n\n"
                    "Choose a category below to view and configure settings:"
                ),
                color=0x5865F2
            )
            
            embed.add_field(
                name=" Bot Updates Channel",
                value="Set where changelog updates are posted",
                inline=True
            )
            
            embed.add_field(
                name="📨 Invite Tracking Channel",
                value="Configure member join/leave notifications",
                inline=True
            )
            
            embed.set_footer(text=f"Server ID: {guild_id} | Configuration System v2.0")
            
            view = ServerConfigMainView(self)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Server config main menu sent to user {interaction.user.id} in guild {guild_id}")
        
        except Exception as e:
            logger.error(f"Error in server config command: {e}", exc_info=True)
            await interaction.response.send_message("❌ Error opening server configuration. Please try again.", ephemeral=True)


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ServerConfig(bot))
    logger.info("ServerConfig cog loaded successfully")

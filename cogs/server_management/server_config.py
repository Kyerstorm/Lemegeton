"""
Unified Server Configuration Interface
Consolidates all server management commands into a single interactive interface
"""

import discord
from helpers.command_error_handler import FeedbackAwareModal, FeedbackAwareView
from discord.ext import commands
from discord import app_commands
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from database import (
    get_guild_bot_update_channel, remove_guild_bot_update_channel,
    is_user_moderator, execute_db_operation
)
from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_success_embed, build_info_embed, build_warning_embed

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


def validate_config_channel(channel, guild_id: int, bot_member, is_text_channel: bool) -> Optional[str]:
    """Return a clear validation error or None for a sendable, guild-local text channel."""
    channel_guild_id = getattr(getattr(channel, "guild", None), "id", None)
    if channel is None or channel_guild_id != guild_id or not is_text_channel:
        return "Choose a text or announcement channel belonging to this server and accessible to the bot."
    if bot_member is None:
        return "I could not resolve my server member to verify its channel permissions."
    permissions = channel.permissions_for(bot_member)
    missing = [
        name for name, allowed in (
            ("View Channel", permissions.view_channel),
            ("Send Messages", permissions.send_messages),
            ("Embed Links", permissions.embed_links),
        ) if not allowed
    ]
    if missing:
        return f"I cannot use {channel.mention}. Missing bot permissions: {', '.join(missing)}."
    return None


class ServerConfigMainView(FeedbackAwareView):
    """Main menu view for unified server configuration system"""
    
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Permission Denied",
                    "These controls are only available to users with Manage Server in the server where they were opened.",
                ),
                ephemeral=True,
            )
            return False
        return True
    
    @discord.ui.button(label=" Bot Updates Channel", style=discord.ButtonStyle.primary, row=0)
    async def manage_bot_updates(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage bot updates channel settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            channel_id = await get_guild_bot_update_channel(interaction.guild.id)
            
            if channel_id:
                channel = self.cog.bot.get_channel(channel_id)
                if channel:
                    embed = build_success_embed(
                        title="Bot Updates Channel",
                        description="Configure where changelog and update notifications are posted."
                    )
                    embed.add_field(
                        name="📊 Current Configuration",
                        value=f"**Channel:** {channel.mention}\n**Category:** {channel.category.name if channel.category else 'None'}\n**Created:** <t:{int(channel.created_at.timestamp())}:R>",
                        inline=False
                    )
                else:
                    embed = build_warning_embed(
                        title="Bot Updates Channel",
                        description="Configure where changelog and update notifications are posted."
                    )
                    embed.add_field(
                        name="⚠️ Configuration Issue",
                        value=f"Configured channel (ID: {channel_id}) is not visible to the bot.",
                        inline=False
                    )
            else:
                embed = build_info_embed(
                    title="Bot Updates Channel",
                    description="Configure where changelog and update notifications are posted."
                )
                embed.add_field(
                    name="📝 No Channel Configured",
                    value="No bot updates channel is currently set.\nYou won't receive automatic update notifications.",
                    inline=False
                )
            
            embed.add_field(
                name="ℹ️ About Update Notifications",
                value="When configured, bot moderators can send changelog updates to this channel using `/changelog`.",
                inline=False
            )
            
            view = BotUpdatesConfigView(self.cog, channel_id, interaction.guild.id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            logger.info(f"Bot updates management opened by {interaction.user.id} in guild {interaction.guild.id}")
        
        except Exception as e:
            logger.error(f"Error in bot updates management: {e}", exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to load bot updates settings. Please try again."
                ),
                ephemeral=True
            )
    
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
            
            if channel_id:
                channel = self.cog.bot.get_channel(channel_id)
                if channel:
                    embed = build_success_embed(
                        title="Invite Tracking Channel",
                        description="Configure where member join/leave notifications are posted."
                    )
                    embed.add_field(
                        name="📊 Current Configuration",
                        value=f"**Channel:** {channel.mention}\n**Category:** {channel.category.name if channel.category else 'None'}\n**Created:** <t:{int(channel.created_at.timestamp())}:R>",
                        inline=False
                    )
                else:
                    embed = build_warning_embed(
                        title="Invite Tracking Channel",
                        description="Configure where member join/leave notifications are posted."
                    )
                    embed.add_field(
                        name="⚠️ Configuration Issue",
                        value=f"Configured channel (ID: {channel_id}) is not visible to the bot.",
                        inline=False
                    )
            else:
                embed = build_info_embed(
                    title="Invite Tracking Channel",
                    description="Configure where member join/leave notifications are posted."
                )
                embed.add_field(
                    name="📝 No Channel Configured",
                    value="No invite tracking channel is currently set.\nJoin/leave messages are disabled.",
                    inline=False
                )
            
            embed.add_field(
                name="ℹ️ About Invite Tracking",
                value="Tracks which invite link new members used and sends welcome/goodbye messages.",
                inline=False
            )
            
            view = InviteChannelConfigView(self.cog, channel_id, interaction.guild.id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            logger.info(f"Invite channel management opened by {interaction.user.id} in guild {interaction.guild.id}")
        
        except Exception as e:
            logger.error(f"Error in invite channel management: {e}", exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to load invite tracking settings. Please try again."
                ),
                ephemeral=True
            )
    
    @discord.ui.button(label="📋 View All Settings", style=discord.ButtonStyle.secondary, row=1)
    async def view_all_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View all server configuration settings"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = build_info_embed(
                title="Server Configuration Overview",
                description=f"Complete configuration for **{interaction.guild.name}**"
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
            logger.error(f"Error viewing all settings: {e}", exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to load server settings. Please try again."
                ),
                ephemeral=True
            )


    @discord.ui.button(label="🩺 Run Diagnostics", style=discord.ButtonStyle.secondary, row=2)
    async def diagnose_configuration(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Check this guild's configured channels and bot permissions without changing settings."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=build_error_embed("Invalid Context", "Diagnostics can only run inside a server."),
                ephemeral=True,
            )
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server permission to run diagnostics."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            updates_id = await get_guild_bot_update_channel(guild.id)
            invite_row = await execute_db_operation(
                "diagnose invite tracking channel",
                "SELECT announcement_channel_id FROM invite_tracker_settings WHERE guild_id = ?",
                (guild.id,),
                fetch_type="one",
            )
            settings = [
                ("Bot Updates Channel", updates_id),
                ("Invite Tracking Channel", invite_row[0] if invite_row else None),
            ]
            embed = build_info_embed(
                "Server Configuration Diagnostics",
                f"Read-only checks for **{guild.name}**. No settings were changed.",
            )
            for label, channel_id in settings:
                if not channel_id:
                    result = "⚠️ Not configured"
                else:
                    channel = guild.get_channel(channel_id)
                    if channel is None:
                        result = f"❌ Configured channel ID {channel_id} is missing or inaccessible in this server."
                    elif guild.me is None:
                        result = f"⚠️ {channel.mention} found; bot permissions could not be verified."
                    else:
                        permissions = channel.permissions_for(guild.me)
                        missing = [
                            name for name, allowed in (
                                ("View Channel", permissions.view_channel),
                                ("Send Messages", permissions.send_messages),
                                ("Embed Links", permissions.embed_links),
                            ) if not allowed
                        ]
                        result = (
                            f"✅ {channel.mention} — required permissions available"
                            if not missing
                            else f"⚠️ {channel.mention} — missing: {', '.join(missing)}"
                        )
                embed.add_field(name=label, value=result[:1024], inline=False)
            embed.set_footer(text=f"Guild-scoped diagnostics • Server ID {guild.id}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            logger.error("Server-config diagnostics failed in guild %s: %s", guild.id, exc, exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    "Diagnostics Failed",
                    "Could not read all settings. Check bot/database logs and try again.",
                ),
                ephemeral=True,
            )


class ConfirmChannelRemovalView(FeedbackAwareView):
    """Require an explicit, guild-scoped confirmation before clearing a channel setting."""

    def __init__(self, cog, guild_id: int, setting: str):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.guild_id = guild_id
        self.setting = setting

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server in this server to confirm this change."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm removal", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            if self.setting == "bot_updates":
                await remove_guild_bot_update_channel(self.guild_id)
                description = "Bot update notifications are now disabled for this server."
            elif self.setting == "invite_tracking":
                await execute_db_operation(
                    "remove invite tracking channel",
                    "DELETE FROM invite_tracker_settings WHERE guild_id = ?",
                    (self.guild_id,),
                )
                description = "Invite tracking announcements are now disabled for this server."
            else:
                await interaction.edit_original_response(
                    embed=build_error_embed("Unknown Setting", "No setting was removed."),
                    view=None,
                )
                return
            await interaction.edit_original_response(
                embed=build_success_embed("Configuration Removed", description),
                view=None,
            )
        except Exception as exc:
            logger.error("Channel setting removal failed in guild %s: %s", self.guild_id, exc, exc_info=True)
            await interaction.edit_original_response(
                embed=build_error_embed("Removal Failed", "The setting was not confirmed as removed. Check the database logs."),
                view=None,
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_info_embed("Removal Cancelled", "The existing channel configuration was left unchanged."),
            view=None,
        )


class BotUpdatesConfigView(FeedbackAwareView):
    """View for configuring bot updates channel"""
    
    def __init__(self, cog, current_channel_id, guild_id: int):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.current_channel_id = current_channel_id
        self.guild_id = guild_id
        if not current_channel_id:
            self.children[1].disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server in this server to change these settings."),
                ephemeral=True,
            )
            return False
        return True
        
    
    @discord.ui.button(label="✏️ Set Channel", style=discord.ButtonStyle.success)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set bot updates channel"""
        modal = SetBotUpdatesChannelModal(self.cog, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Remove Channel", style=discord.ButtonStyle.danger)
    async def remove_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ask for confirmation before removing the bot updates channel."""
        await interaction.response.send_message(
            embed=build_warning_embed(
                title="Remove Bot Updates Channel?",
                description="This disables update notifications for this server. The stored channel will remain unchanged unless you confirm.",
            ),
            view=ConfirmChannelRemovalView(self.cog, self.guild_id, "bot_updates"),
            ephemeral=True,
        )


    @discord.ui.button(label="↩ Main Menu", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_main_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to the configuration root without making any additional changes."""
        embed = build_info_embed(
            title="Server Configuration",
            description=(
                f"Configuration panel for **{interaction.guild.name}**. "
                "Settings are saved only when a valid channel is submitted; no unsaved edits are pending."
            ),
        )
        embed.add_field(name="Bot Updates Channel", value="Set where GitHub updates are posted.", inline=True)
        embed.add_field(name="Invite Tracking Channel", value="Set where join/leave announcements are posted.", inline=True)
        embed.set_footer(text=f"Server ID: {self.guild_id}")
        await interaction.response.edit_message(
            embed=embed,
            view=ServerConfigMainView(self.cog, self.guild_id),
        )

class InviteChannelConfigView(FeedbackAwareView):
    """View for configuring invite tracking channel"""
    
    def __init__(self, cog, current_channel_id, guild_id: int):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.current_channel_id = current_channel_id
        self.guild_id = guild_id
        if not current_channel_id:
            self.children[1].disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server in this server to change these settings."),
                ephemeral=True,
            )
            return False
        return True
        
    
    @discord.ui.button(label="✏️ Set Channel", style=discord.ButtonStyle.success)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Set invite tracking channel"""
        modal = SetInviteChannelModal(self.cog, self.guild_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Remove Channel", style=discord.ButtonStyle.danger)
    async def remove_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ask for confirmation before removing invite tracking announcements."""
        await interaction.response.send_message(
            embed=build_warning_embed(
                title="Remove Invite Tracking Channel?",
                description="This disables join/leave announcements for this server. The stored channel will remain unchanged unless you confirm.",
            ),
            view=ConfirmChannelRemovalView(self.cog, self.guild_id, "invite_tracking"),
            ephemeral=True,
        )


    @discord.ui.button(label="↩ Main Menu", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_main_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to the configuration root without making any additional changes."""
        embed = build_info_embed(
            title="Server Configuration",
            description=(
                f"Configuration panel for **{interaction.guild.name}**. "
                "Settings are saved only when a valid channel is submitted; no unsaved edits are pending."
            ),
        )
        embed.add_field(name="Bot Updates Channel", value="Set where GitHub updates are posted.", inline=True)
        embed.add_field(name="Invite Tracking Channel", value="Set where join/leave announcements are posted.", inline=True)
        embed.set_footer(text=f"Server ID: {self.guild_id}")
        await interaction.response.edit_message(
            embed=embed,
            view=ServerConfigMainView(self.cog, self.guild_id),
        )

class SetBotUpdatesChannelModal(FeedbackAwareModal):
    """Modal for setting bot updates channel"""
    
    def __init__(self, cog, guild_id: int):
        super().__init__(title="Set Bot Updates Channel")
        self.cog = cog
        self.guild_id = guild_id
    
    channel_id = discord.ui.TextInput(
        label="Channel ID or Channel Mention",
        placeholder="Enter channel ID (e.g., 123456789) or mention (e.g., #updates)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if (interaction.guild is None or interaction.guild_id != self.guild_id
                or not interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server in the original server to save this setting."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse channel ID from input
            channel_id_str = self.channel_id.value.strip()
            
            # Remove mention formatting if present
            channel_id_str = channel_id_str.replace("<#", "").replace(">", "")
            
            # Convert to int
            channel_id = int(channel_id_str)
            
            # Resolve channels not currently cached, then validate this guild's sendable text channel.
            channel = self.cog.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    channel = None

            validation_error = validate_config_channel(
                channel,
                self.guild_id,
                interaction.guild.me,
                isinstance(channel, discord.TextChannel),
            )
            if validation_error:
                await interaction.followup.send(
                    embed=build_error_embed("Invalid Configuration Channel", validation_error),
                    ephemeral=True,
                )
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
            
            embed = build_success_embed(
                title="Bot Updates Channel Set",
                description=f"**Channel:** {channel.mention}\n\nChangelog updates will be posted to this channel."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Bot updates channel set for guild {interaction.guild.id}: #{channel.name} ({channel.id})")
        
        except ValueError:
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Invalid Format",
                    description="Invalid channel ID format. Please enter a valid number."
                ),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting bot updates channel: {e}", exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to set bot updates channel. Please try again."
                ),
                ephemeral=True
            )


class SetInviteChannelModal(FeedbackAwareModal):
    """Modal for setting invite tracking channel"""
    
    def __init__(self, cog, guild_id: int):
        super().__init__(title="Set Invite Tracking Channel")
        self.cog = cog
        self.guild_id = guild_id
    
    channel_id = discord.ui.TextInput(
        label="Channel ID or Channel Mention",
        placeholder="Enter channel ID (e.g., 123456789) or mention (e.g., #welcome)",
        required=True,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if (interaction.guild is None or interaction.guild_id != self.guild_id
                or not interaction.user.guild_permissions.manage_guild):
            await interaction.response.send_message(
                embed=build_error_embed("Permission Denied", "You need Manage Server in the original server to save this setting."),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse channel ID from input
            channel_id_str = self.channel_id.value.strip()
            
            # Remove mention formatting if present
            channel_id_str = channel_id_str.replace("<#", "").replace(">", "")
            
            # Convert to int
            channel_id = int(channel_id_str)
            
            # Resolve channels not currently cached, then validate this guild's sendable text channel.
            channel = self.cog.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    channel = None

            validation_error = validate_config_channel(
                channel,
                self.guild_id,
                interaction.guild.me,
                isinstance(channel, discord.TextChannel),
            )
            if validation_error:
                await interaction.followup.send(
                    embed=build_error_embed("Invalid Configuration Channel", validation_error),
                    ephemeral=True,
                )
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
                logger.error(f"Failed to initialize invite cache: {e}", exc_info=True)
            
            embed = build_success_embed(
                title="Invite Tracking Channel Set",
                description=f"**Channel:** {channel.mention}\n\nJoin/leave messages will be posted to this channel."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"Invite channel set for guild {interaction.guild.id}: #{channel.name} ({channel.id})")
        
        except ValueError:
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Invalid Format",
                    description="Invalid channel ID format. Please enter a valid number."
                ),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting invite channel: {e}", exc_info=True)
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to set invite tracking channel. Please try again."
                ),
                ephemeral=True
            )


class ServerConfig(commands.Cog):
    """Unified server configuration management interface"""
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("ServerConfig cog initialized")
    
    @app_commands.command(name="server-config", description="⚙️ Configure server settings - roles, channels, and notifications")
    @command_meta(section="Server Management", name="Server Config")
    @app_commands.default_permissions(manage_guild=True)
    async def server_config(self, interaction: discord.Interaction):
        """Unified server configuration interface"""
        
        if not interaction.guild:
            await interaction.response.send_message(
                embed=build_error_embed(
                    title="Invalid Context",
                    description="This command can only be used in a server."
                ),
                ephemeral=True
            )
            return
        
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=build_error_embed(
                    title="Permission Denied",
                    description="You need 'Manage Server' permission to use this command."
                ),
                ephemeral=True
            )
            return
        
        try:
            guild_id = interaction.guild.id
            logger.info(f"Server config opened by {interaction.user.display_name} ({interaction.user.id}) in guild {guild_id}")
            
            embed = build_info_embed(
                title="Server Configuration",
                description=(
                    f"Welcome to the server configuration panel for **{interaction.guild.name}**!\n\n"
                    "Choose a category to configure channels, review settings, or run read-only diagnostics."
                )
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
            embed.add_field(
                name="🎛️ Command Availability",
                value="Use `/dashboard` to manage guild-scoped command/category availability and audit recent changes; these settings are shared with the optional web dashboard.",
                inline=False,
            )

            embed.set_footer(text=f"Server ID: {guild_id} | Configuration System v2.0")
            
            view = ServerConfigMainView(self, guild_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.info(f"Server config main menu sent to user {interaction.user.id} in guild {guild_id}")
        
        except Exception as e:
            logger.error(f"Error in server config command: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=build_error_embed(
                    title="Error",
                    description="Failed to open server configuration. Please try again."
                ),
                ephemeral=True
            )


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ServerConfig(bot))
    logger.info("ServerConfig cog loaded successfully")

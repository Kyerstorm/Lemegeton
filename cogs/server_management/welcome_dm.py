import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import aiohttp
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from cogs_test.general_commands.dashboard import command_meta

logger = logging.getLogger("WelcomeDM")

class WelcomeDM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_file = Path("data") / "welcome_dm.json"
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        
    async def cog_load(self):
        """Initialize the welcome_dm JSON file when the cog loads."""
        await self.init_data_file()
        
    async def init_data_file(self):
        """Create the welcome_dm.json file if it doesn't exist."""
        try:
            if not self.data_file.exists():
                self.data_file.write_text("{}")
                logger.info("Welcome DM JSON file initialized successfully")
            else:
                logger.info("Welcome DM JSON file already exists")
        except Exception as e:
            logger.error(f"Failed to initialize welcome DM JSON file: {e}")
    
    def _load_data(self) -> Dict[str, Any]:
        """Load data from the JSON file."""
        try:
            if self.data_file.exists():
                return json.loads(self.data_file.read_text())
            return {}
        except Exception as e:
            logger.error(f"Failed to load welcome DM data: {e}")
            return {}
    
    def _save_data(self, data: Dict[str, Any]) -> bool:
        """Save data to the JSON file."""
        try:
            self.data_file.write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save welcome DM data: {e}")
            return False
    
    async def get_welcome_message(self, guild_id: int) -> Optional[str]:
        """Get the welcome message for a specific guild."""
        try:
            data = self._load_data()
            guild_data = data.get(str(guild_id))
            if guild_data and guild_data.get("enabled", True):
                return guild_data.get("message_content")
            return None
        except Exception as e:
            logger.error(f"Failed to get welcome message for guild {guild_id}: {e}")
            return None
    
    async def set_welcome_message(self, guild_id: int, message_content: str) -> bool:
        """Set or update the welcome message for a specific guild."""
        try:
            data = self._load_data()
            current_time = datetime.utcnow().isoformat()
            
            guild_key = str(guild_id)
            if guild_key not in data:
                data[guild_key] = {
                    "message_content": message_content,
                    "enabled": True,
                    "created_at": current_time,
                    "updated_at": current_time
                }
            else:
                data[guild_key]["message_content"] = message_content
                data[guild_key]["updated_at"] = current_time
            
            success = self._save_data(data)
            if success:
                logger.info(f"Welcome message updated for guild {guild_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to set welcome message for guild {guild_id}: {e}")
            return False
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send welcome DM to new members."""
        if member.bot:
            return  # Don't send welcome messages to bots
            
        guild_id = member.guild.id
        welcome_message = await self.get_welcome_message(guild_id)
        
        if not welcome_message:
            logger.debug(f"No welcome message configured for guild {guild_id}")
            return
            
        try:
            # Replace placeholders in the message
            formatted_message = welcome_message.replace("{user}", member.display_name)
            formatted_message = formatted_message.replace("{server}", member.guild.name)
            formatted_message = formatted_message.replace("{mention}", member.mention)
            
            # Send the welcome DM
            await member.send(formatted_message)
            logger.info(f"Welcome DM sent to {member.display_name} ({member.id}) in guild {member.guild.name}")
            
        except discord.Forbidden:
            logger.warning(f"Could not send welcome DM to {member.display_name} - DMs disabled")
        except Exception as e:
            logger.error(f"Failed to send welcome DM to {member.display_name}: {e}")
    
    @app_commands.command(
        name="set-welcome-dm",
        description="Set the welcome DM message by uploading a text file (Admin only)"
    )
    @command_meta(section="Server Management", name="Set Welcome DM")
    @app_commands.describe(
        text_file="Upload a .txt file containing the welcome message"
    )
    async def set_welcome_dm(self, interaction: discord.Interaction, text_file: discord.Attachment):
        """Admin command to set welcome DM message from uploaded text file."""
        
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ **Access Denied**\n\nYou need Administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        # Validate file type
        if not text_file.filename.lower().endswith('.txt'):
            await interaction.response.send_message(
                "❌ **Invalid File Type**\n\nPlease upload a `.txt` file containing your welcome message.",
                ephemeral=True
            )
            return
        
        # Check file size (limit to 1MB)
        if text_file.size > 1024 * 1024:  # 1MB
            await interaction.response.send_message(
                "❌ **File Too Large**\n\nThe text file must be smaller than 1MB.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Download and read the file content
            async with aiohttp.ClientSession() as session:
                async with session.get(text_file.url) as response:
                    if response.status == 200:
                        file_content = await response.text(encoding='utf-8')
                    else:
                        await interaction.followup.send(
                            "❌ **Download Failed**\n\nCould not download the uploaded file.",
                            ephemeral=True
                        )
                        return
            
            # Validate content length
            if len(file_content.strip()) == 0:
                await interaction.followup.send(
                    "❌ **Empty File**\n\nThe uploaded text file is empty.",
                    ephemeral=True
                )
                return
            
            if len(file_content) > 2000:
                await interaction.followup.send(
                    "❌ **Message Too Long**\n\nThe welcome message must be 2000 characters or less for Discord DM limits.",
                    ephemeral=True
                )
                return
            
            # Save the welcome message
            success = await self.set_welcome_message(interaction.guild_id, file_content.strip())
            
            if success:
                # Show preview with placeholder replacements
                preview_content = file_content.strip()
                preview_content = preview_content.replace("{user}", "NewUser")
                preview_content = preview_content.replace("{server}", interaction.guild.name)
                preview_content = preview_content.replace("{mention}", "@NewUser")
                
                # Build the response message
                response = (
                    "✅ **Welcome DM Updated Successfully!**\n\n"
                    "**Preview:**\n"
                    f"{preview_content}\n\n"
                    "**Available Placeholders:**\n"
                    "• `{user}` - Member's display name\n"
                    "• `{server}` - Server name\n"
                    "• `{mention}` - Mention the user\n\n"
                    "_New members will receive this message when they join the server._"
                )
                
                await interaction.followup.send(response, ephemeral=True)
            else:
                await interaction.followup.send(
                    "❌ **Database Error**\n\nFailed to save the welcome message. Please try again.",
                    ephemeral=True
                )
                
        except UnicodeDecodeError:
            await interaction.followup.send(
                "❌ **Encoding Error**\n\nThe file must be a valid UTF-8 encoded text file.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error processing welcome DM file upload: {e}")
            await interaction.followup.send(
                "❌ **Unexpected Error**\n\nAn error occurred while processing your file. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="welcome-dm-status",
        description="Check the current welcome DM configuration (Admin only)"
    )
    @command_meta(section="Server Management", name="Welcome DM Status")
    async def welcome_dm_status(self, interaction: discord.Interaction):
        """Admin command to check current welcome DM status."""
        
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ **Access Denied**\n\nYou need Administrator permissions to use this command.",
                ephemeral=True
            )
            return
        
        welcome_message = await self.get_welcome_message(interaction.guild_id)
        
        if welcome_message:
            # Show preview with placeholder replacements
            preview_content = welcome_message
            preview_content = preview_content.replace("{user}", "NewUser")
            preview_content = preview_content.replace("{server}", interaction.guild.name)
            preview_content = preview_content.replace("{mention}", "@NewUser")
            
            # Build the response message
            response = (
                "📨 **Welcome DM Configuration**\n\n"
                "Welcome DM is currently **enabled** for this server.\n\n"
                "**Current Message:**\n"
                f"{preview_content}\n\n"
                "**Available Placeholders:**\n"
                "• `{user}` - Member's display name\n"
                "• `{server}` - Server name\n"
                "• `{mention}` - Mention the user\n\n"
                "_Use /set-welcome-dm to update the message._"
            )
        else:
            response = (
                "📨 **Welcome DM Configuration**\n\n"
                "Welcome DM is currently **disabled** for this server.\n\n"
                "Use `/set-welcome-dm` to configure a welcome message."
            )
        
        await interaction.response.send_message(response, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeDM(bot))
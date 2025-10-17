import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import aiohttp
import io
from typing import Optional
import logging
import config

from database import (
    set_guild_bot_update_channel, 
    get_guild_bot_update_channel,
    get_all_guild_bot_update_channels,
    remove_guild_bot_update_channel,
    is_user_bot_moderator,
    is_bot_moderator
)

# Setup logger
logger = logging.getLogger("changelog")


def changelog_only():
    """App command check that allows only bot moderators and users with administrative/manage permissions as a fallback.
    Updated to use bot moderator system instead of hardcoded role IDs.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        try:
            # First check if user is a bot moderator
            if await is_user_bot_moderator(interaction.user):
                return True
            
            # Fallback to permission checks for server admins
            member = interaction.user if isinstance(interaction.user, discord.Member) else await interaction.guild.fetch_member(interaction.user.id)
            perms = getattr(member, "guild_permissions", None)
            if perms:
                return perms.manage_roles or perms.manage_guild or perms.administrator
        except Exception:
            return False
        return False

    return app_commands.check(predicate)


def bot_moderator_only():
    """App command check that allows only bot moderators and admins.
    Used for bot-wide actions like publishing changelogs to all servers.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            return await is_user_bot_moderator(interaction.user)
        except Exception:
            return False

    return app_commands.check(predicate)


class Changelog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def get_notification_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Get the bot update notification role for a guild (auto-creates if needed)."""
        role_name = "bot-updates"
        
        # If BOT_UPDATE_ROLE_ID is configured, try to get that specific role
        if config.BOT_UPDATE_ROLE_ID:
            role = guild.get_role(config.BOT_UPDATE_ROLE_ID)
            if role:
                return role
        
        # Try to find role by name
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            return role
        
        # Create the role if it doesn't exist and we have permissions
        try:
            role = await guild.create_role(
                name=role_name,
                mentionable=True,
                reason="Auto-created for changelog notifications",
                color=discord.Color.blue()
            )
            logger.info(f"Created notification role '{role.name}' in guild {guild.id} for changelog")
            return role
        except discord.Forbidden:
            logger.warning(f"No permission to create notification role in guild {guild.id}")
            return None
        except Exception as e:
            logger.error(f"Error creating notification role in guild {guild.id}: {e}")
            return None
    
    async def mention_role_safely(self, role: discord.Role) -> tuple[str, bool]:
        """Safely mention a role by temporarily making it mentionable if needed.
        Returns: (mention_string, was_modified)
        """
        if role.mentionable:
            return (role.mention, False)
        
        # Try to temporarily make role mentionable
        try:
            if role.guild.me.guild_permissions.manage_roles:
                await role.edit(mentionable=True)
                return (role.mention, True)
            else:
                return (f"@{role.name}", False)
        except (discord.Forbidden, discord.HTTPException):
            return (f"@{role.name}", False)

    def _parse_color(self, color_input: str, changelog_type: str) -> discord.Color:
        """Parse color input and return appropriate discord.Color."""
        if color_input:
            color_input = color_input.strip()
            # Handle hex colors
            if color_input.startswith('#'):
                try:
                    return discord.Color(int(color_input[1:], 16))
                except ValueError:
                    pass
            # Handle named colors
            color_map = {
                'red': discord.Color.red(),
                'green': discord.Color.green(),
                'blue': discord.Color.blue(),
                'yellow': discord.Color.yellow(),
                'orange': discord.Color.orange(),
                'purple': discord.Color.purple(),
                'gold': discord.Color.gold(),
                'dark_red': discord.Color.dark_red(),
                'dark_green': discord.Color.dark_green(),
                'dark_blue': discord.Color.dark_blue(),
            }
            if color_input.lower() in color_map:
                return color_map[color_input.lower()]
        
        # Default colors based on type
        type_colors = {
            'bugfix': discord.Color.red(),
            'feature': discord.Color.green(),
            'update': discord.Color.blue(),
            'announcement': discord.Color.gold(),
            'maintenance': discord.Color.orange(),
            'general': discord.Color.blurple(),
        }
        return type_colors.get(changelog_type, discord.Color.blurple())

    def _get_type_config(self, changelog_type: str) -> dict:
        """Get configuration for different changelog types."""
        type_configs = {
            'bugfix': {
                'emoji': '🐛',
                'title': 'Bug Fix',
                'footer': '🔧 Bug Fix Update'
            },
            'feature': {
                'emoji': '✨',
                'title': 'New Feature',
                'footer': '🚀 Feature Update'
            },
            'update': {
                'emoji': '🔄',
                'title': 'Update',
                'footer': '⬆️ System Update'
            },
            'announcement': {
                'emoji': '📢',
                'title': 'Announcement',
                'footer': '📣 Important Announcement'
            },
            'maintenance': {
                'emoji': '🔧',
                'title': 'Maintenance',
                'footer': '🛠️ Maintenance Update'
            },
            'general': {
                'emoji': '📝',
                'title': 'Changelog',
                'footer': '📋 General Update'
            }
        }
        return type_configs.get(changelog_type, type_configs['general'])

    def _format_markdown(self, text: str) -> str:
        """Enhanced markdown formatting for changelog text."""
        if not text:
            return text
            
        # Support for bullet points
        text = text.replace('- ', '• ')
        text = text.replace('* ', '• ')
        
        # Support for numbered lists (basic)
        lines = text.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith(tuple(f'{i}.' for i in range(1, 10))):
                # Add emoji numbers for visual appeal
                number = line[0]
                rest = line[2:].strip()
                emoji_numbers = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
                if int(number) <= 9:
                    formatted_lines.append(f"{emoji_numbers[int(number)-1]} {rest}")
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        
        # Ensure proper line spacing for readability
        result = '\n'.join(formatted_lines)
        
        # Handle double line breaks for paragraph separation
        result = result.replace('\n\n\n', '\n\n')  # Prevent too many empty lines
        
        return result

    async def _validate_image_url(self, url: str) -> bool:
        """Validate if the URL points to a valid image."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=5) as response:
                    if response.status == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        return content_type.startswith('image/')
                    return False
        except Exception:
            return False

    async def _process_image(self, image_input: str) -> Optional[discord.File]:
        """Process image input - download and convert to Discord file."""
        if not image_input:
            return None
            
        try:
            # If it's a URL
            if image_input.startswith(('http://', 'https://')):
                if not await self._validate_image_url(image_input):
                    return None
                    
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_input) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            # Get file extension from content-type or URL
                            content_type = response.headers.get('content-type', '')
                            if 'png' in content_type:
                                ext = 'png'
                            elif 'jpeg' in content_type or 'jpg' in content_type:
                                ext = 'jpg'
                            elif 'gif' in content_type:
                                ext = 'gif'
                            elif 'webp' in content_type:
                                ext = 'webp'
                            else:
                                ext = 'png'  # Default
                                
                            return discord.File(
                                io.BytesIO(image_data),
                                filename=f"changelog_image.{ext}"
                            )
            return None
        except Exception:
            return None



    async def role_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for role parameter - shows all roles with search."""
        if not interaction.guild:
            return []
        
        # Get all roles (excluding @everyone)
        roles = [role for role in interaction.guild.roles if role.name != "@everyone"]
        
        # Filter by current input (case-insensitive)
        if current:
            roles = [role for role in roles if current.lower() in role.name.lower()]
        
        # Sort by position (highest first) and limit to 25 (Discord's limit)
        roles.sort(key=lambda r: r.position, reverse=True)
        roles = roles[:25]
        
        return [
            app_commands.Choice(name=role.name, value=str(role.id))
            for role in roles
        ]

    @bot_moderator_only()
    @app_commands.command(name="changelog", description="Create and publish a changelog from an uploaded text file (Bot Moderator only)")
    @app_commands.describe(
        file="Text file to convert into changelog",
        publish_to="Where to publish the changelog",
        changelog_type="Type of changelog update",
        color="Embed color (hex code like #FF5733 or color name)",
        role="Optional role to ping (only pings when specified)",
        image_url="Optional image URL to embed",
        title_override="Override the auto-detected title"
    )
    @app_commands.autocomplete(role=role_autocomplete)
    @app_commands.choices(
        publish_to=[
            app_commands.Choice(name="📡 All Servers (Bot Update)", value="all_servers"),
            app_commands.Choice(name="🏠 Current Server Only", value="current_server")
        ],
        changelog_type=[
            app_commands.Choice(name="🐛 Bug Fix", value="bugfix"),
            app_commands.Choice(name="✨ New Feature", value="feature"),
            app_commands.Choice(name="🔄 Update", value="update"),
            app_commands.Choice(name="📢 Announcement", value="announcement"),
            app_commands.Choice(name="🔧 Maintenance", value="maintenance"),
            app_commands.Choice(name="📝 General", value="general")
        ]
    )
    async def changelog(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        publish_to: str = "current_server",
        changelog_type: str = "general",
        color: str = None,
        role: str = None,
        image_url: str = None,
        title_override: str = None
    ):
        """Create a changelog from an uploaded text file with automatic formatting."""
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate file
            if not file.filename.lower().endswith(('.txt', '.md')):
                await interaction.followup.send("❌ Please upload a .txt or .md file.", ephemeral=True)
                return
                
            if file.size > 1024 * 1024:  # 1MB limit
                await interaction.followup.send("❌ File is too large. Maximum size is 1MB.", ephemeal=True)
                return
            
            # Download and read file content
            try:
                file_content = await file.read()
                text_content = file_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    text_content = file_content.decode('latin-1')
                except:
                    await interaction.followup.send("❌ Could not decode file. Please ensure it's a text file with UTF-8 or Latin-1 encoding.", ephemeral=True)
                    return
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to read file: {str(e)}", ephemeral=True)
                return
            
            # Parse the text content
            parsed_data = self._parse_text_file(text_content, title_override)
            
            # Determine embed color
            embed_color = self._parse_color(color, changelog_type)
            type_config = self._get_type_config(changelog_type)
            
            embed = discord.Embed(
                title=f"{type_config['emoji']} {type_config['title']}",
                color=embed_color
            )
            
            # Add title
            if parsed_data['title']:
                embed.add_field(
                    name="📝 **Title**",
                    value=f"**{parsed_data['title']}**",
                    inline=False
                )
            
            # Add main content sections
            for section in parsed_data['sections']:
                # Limit field values to Discord's 1024 character limit
                content = section['content']
                if len(content) > 1020:
                    content = content[:1017] + "..."
                
                embed.add_field(
                    name=section['name'],
                    value=content,
                    inline=False
                )
            
            # Author info
            embed.set_author(
                name=f"Published by {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url
            )
            
            # Footer
            embed.set_footer(
                text=f"{type_config['footer']} • Published on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} • From: {file.filename}"
            )
            
            # Process image if provided
            image_file = None
            if image_url:
                image_file = await self._process_image(image_url)
                if image_file:
                    embed.set_image(url=f"attachment://{image_file.filename}")
            
            # Determine where to publish based on user choice
            if publish_to == "all_servers":
                # Publish to all servers with configured bot update channels
                update_channels = await get_all_guild_bot_update_channels()
                
                if not update_channels:
                    await interaction.followup.send("❌ No servers have configured bot update channels.", ephemeral=True)
                    return
                
                # Send to all configured channels (no role mentions by default)
                success_count = 0
                failed_guilds = []
                
                for guild_id, channel_id in update_channels.items():
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if not channel:
                            failed_guilds.append(f"Guild {guild_id} (Channel {channel_id} not found)")
                            continue
                        
                        guild = channel.guild
                        
                        # No automatic role mentioning for all servers
                        content_msg = None
                        
                        # Send the message
                        if image_file:
                            # Create a new file object for each send
                            new_image_file = discord.File(
                                io.BytesIO(image_file.fp.getvalue()),
                                filename=image_file.filename
                            ) if hasattr(image_file, 'fp') else None
                            if new_image_file:
                                await channel.send(content=content_msg, embed=embed, file=new_image_file)
                            else:
                                await channel.send(content=content_msg, embed=embed)
                        else:
                            await channel.send(content=content_msg, embed=embed)
                        
                        success_count += 1
                        
                    except Exception as e:
                        failed_guilds.append(f"Guild {guild_id}: {str(e)}")
                        logger.error(f"Error publishing to guild {guild_id}: {e}")
                
                # Send summary
                summary = f"✅ {type_config['title']} published to {success_count}/{len(update_channels)} configured servers."
                if failed_guilds:
                    summary += f"\n\n❌ Failed to send to:\n" + "\n".join(f"• {failure}" for failure in failed_guilds[:5])
                    if len(failed_guilds) > 5:
                        summary += f"\n• ... and {len(failed_guilds) - 5} more"
                
                await interaction.followup.send(summary, ephemeral=True)
            
            else:
                # Publish to current server only
                if not interaction.guild:
                    await interaction.followup.send("❌ This command must be used in a server for current server publishing.", ephemeral=True)
                    return
                    
                channel_id = await get_guild_bot_update_channel(interaction.guild.id)
                if not channel_id:
                    await interaction.followup.send(
                        "❌ No bot updates channel configured for this server. Use `/set_bot_updates_channel` to configure one.", 
                        ephemeral=True
                    )
                    return
                    
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    await interaction.followup.send(
                        "❌ Configured bot updates channel not found. Please reconfigure with `/set_bot_updates_channel`.", 
                        ephemeral=True
                    )
                    return
                
                content_msg = None
                role_to_mention = None
                
                # Only mention role if explicitly provided
                if role:
                    try:
                        role_to_mention = interaction.guild.get_role(int(role))
                        if not role_to_mention:
                            await interaction.followup.send(f"⚠️ Could not find the specified role. No role will be mentioned.", ephemeral=True)
                        else:
                            # Use the safe mention method
                            mention_text, was_modified = await self.mention_role_safely(role_to_mention)
                            content_msg = mention_text
                            
                            # Restore role if we modified it
                            if was_modified:
                                try:
                                    await role_to_mention.edit(mentionable=False)
                                except Exception as e:
                                    logger.warning(f"Failed to restore role mentionability: {e}")
                    except (ValueError, TypeError):
                        await interaction.followup.send(f"⚠️ Invalid role ID. No role will be mentioned.", ephemeral=True)
                
                if image_file:
                    await channel.send(content=content_msg, embed=embed, file=image_file)
                else:
                    await channel.send(content=content_msg, embed=embed)
                
                mention_info = ""
                if role_to_mention:
                    mention_info = f" and mentioned {role_to_mention.name}"
                await interaction.followup.send(f"✅ {type_config['title']} created from file **{file.filename}** and published to {channel.mention}{mention_info}!", ephemeral=True)
            
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Failed to process file and publish changelog: {str(e)}", ephemeral=True)
            except:
                pass
            raise e

    def _parse_text_file(self, content: str, title_override: str = None) -> dict:
        """Parse text file content into structured changelog data."""
        lines = content.strip().split('\n')
        sections = []
        current_section_name = "📖 **Details**"
        current_section_content = []
        title = title_override
        
        # Try to detect title from first line if not overridden
        if not title and lines:
            first_line = lines[0].strip()
            # Check if first line looks like a title (short, no markdown lists, etc.)
            if (len(first_line) < 100 and 
                not first_line.startswith(('- ', '* ', '1. ', '2. ')) and
                not first_line.startswith('#') and
                first_line):
                title = first_line
                lines = lines[1:]  # Remove title from content
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines at the start of sections
            if not line and not current_section_content:
                i += 1
                continue
            
            # Detect section headers (lines that end with : or are all caps/markdown headers)
            is_section_header = False
            if line:
                # Check for markdown headers
                if line.startswith('#'):
                    is_section_header = True
                    line = line.lstrip('#').strip()
                # Check for lines ending with colon
                elif line.endswith(':') and len(line.split()) <= 5:
                    is_section_header = True
                    line = line[:-1].strip()
                # Check for all caps short lines (likely headers)
                elif (line.isupper() and len(line.split()) <= 4 and 
                      len(line) > 2 and not line.startswith(('- ', '* ', '1. '))):
                    is_section_header = True
            
            if is_section_header:
                # Save previous section if it has content
                if current_section_content:
                    formatted_content = self._format_markdown('\n'.join(current_section_content).strip())
                    if formatted_content:
                        sections.append({
                            'name': current_section_name,
                            'content': formatted_content
                        })
                
                # Start new section
                current_section_name = f"📌 **{line.title()}**"
                current_section_content = []
            else:
                # Add line to current section
                if line or current_section_content:  # Keep empty lines if we have content
                    current_section_content.append(line)
            
            i += 1
        
        # Add final section
        if current_section_content:
            formatted_content = self._format_markdown('\n'.join(current_section_content).strip())
            if formatted_content:
                sections.append({
                    'name': current_section_name,
                    'content': formatted_content
                })
        
        # If no sections were created, put everything in one section
        if not sections and content.strip():
            sections.append({
                'name': "📖 **Details**",
                'content': self._format_markdown(content.strip())
            })
        
        return {
            'title': title or "Update",
            'sections': sections
        }

    @changelog_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.command(name="set_bot_updates_channel", description="Set channel to receive bot updates and announcements (Admin only)")
    async def set_bot_updates_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel where bot updates and announcements will be published."""
        if interaction.guild is None:
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        try:
            # Check bot can send messages in channel
            bot_member = interaction.guild.me
            perms = channel.permissions_for(bot_member) if bot_member else None
            if perms and not perms.send_messages:
                await interaction.followup.send("❌ I don't have permission to send messages in that channel.", ephemeral=True)
                return

            await set_guild_bot_update_channel(interaction.guild.id, channel.id)
            await interaction.followup.send(f"✅ Bot updates will be sent to {channel.mention}", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send("❌ Failed to set bot updates channel.", ephemeral=True)
            raise e

    # ============================================================================
    # DEPRECATED COMMANDS - USE /server-config INSTEAD
    # These commands have been consolidated into the unified /server-config interface
    # Located in: cogs/server_management/server_config.py
    # Kept here commented for reference only
    # ============================================================================
    
    # @changelog_only()
    # @app_commands.default_permissions(manage_guild=True)
    # @app_commands.command(name="show_bot_updates_channel", description="⚠️ DEPRECATED - Use /server-config instead")
    # async def show_bot_updates_channel(self, interaction: discord.Interaction):
    #     """DEPRECATED: Show the currently configured bot updates channel. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can view bot updates channels and all server settings there.",
    #         ephemeral=True
    #     )
    
    # @changelog_only()
    # @app_commands.default_permissions(manage_guild=True)
    # @app_commands.command(name="remove_bot_updates_channel", description="⚠️ DEPRECATED - Use /server-config instead")
    # async def remove_bot_updates_channel(self, interaction: discord.Interaction):
    #     """DEPRECATED: Remove the bot updates channel configuration. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can manage bot updates channels and all server settings there.",
    #         ephemeral=True
    #     )
    
    # ============================================================================
    # END DEPRECATED COMMANDS
    # ============================================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(Changelog(bot))
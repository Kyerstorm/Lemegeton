import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Optional
from datetime import datetime
from database import is_user_bot_moderator, execute_db_operation, init_say_command_logs_table
from cogs_test.general_commands.dashboard import command_meta

logger = logging.getLogger("say")

class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Say cog initialized")

    async def cog_load(self):
        """Initialize database when cog loads."""
        await init_say_command_logs_table()
        logger.info("Say cog loaded successfully")

    async def log_say_command(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int,
        message_content: str,
        is_embed: bool = False,
        reply_to_message_id: Optional[int] = None
    ):
        """Log /say command usage to database for moderation accountability"""
        try:
            await execute_db_operation(
                "log say command",
                """INSERT INTO say_command_logs
                   (user_id, guild_id, channel_id, message_content, is_embed, reply_to_message_id, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, guild_id, channel_id, message_content, 1 if is_embed else 0, reply_to_message_id, datetime.utcnow().isoformat())
            )
            logger.info(f"Logged /say command from user {user_id} in guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to log /say command: {e}", exc_info=True)

    @app_commands.command(
        name="say",
        description="Make the bot say something (Moderators only). Supports markdown, embeds, and channel targeting."
    )
    @command_meta(section="Utilities", name="Say")
    @app_commands.describe(
        message="What the bot should say",
        channel="Channel to send message in (optional, defaults to current channel)",
        embed="Send as an embed (optional, default: False)",
        reply_to="Message ID to reply to (optional)"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: Optional[discord.TextChannel] = None,
        embed: bool = False,
        reply_to: Optional[str] = None
    ):
        try:
            # ✅ Check for built-in moderation perms
            has_mod_perms = (
                interaction.user.guild_permissions.manage_messages
                or interaction.user.guild_permissions.kick_members
                or interaction.user.guild_permissions.ban_members
                or interaction.user.guild_permissions.manage_guild
            )

            # ✅ Check custom database-based moderator system
            is_bot_mod = await is_user_bot_moderator(interaction.user)

            # 🚫 If user isn't a mod or bot mod, deny access
            if not (has_mod_perms or is_bot_mod):
                await interaction.response.send_message(
                    "❌ You need moderator permissions to use this command.",
                    ephemeral=True
                )
                return

        except Exception as e:
            logger.error(f"Error checking permissions: {e}", exc_info=True)
            # If check fails (e.g. database error), also deny access
            await interaction.response.send_message(
                "❌ You can't use this command.",
                ephemeral=True
            )
            return

        # Determine target channel
        target_channel = channel if channel else interaction.channel

        # Verify bot has permissions in target channel
        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {target_channel.mention}!",
                ephemeral=True
            )
            return

        # Handle reply_to parameter
        reply_to_message = None
        reply_to_message_id = None
        if reply_to:
            try:
                reply_to_message_id = int(reply_to)
                reply_to_message = await target_channel.fetch_message(reply_to_message_id)
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Invalid message ID: `{reply_to}`\nMessage IDs must be numbers.",
                    ephemeral=True
                )
                return
            except discord.NotFound:
                await interaction.response.send_message(
                    f"❌ Could not find message with ID `{reply_to}` in {target_channel.mention}!",
                    ephemeral=True
                )
                return
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"❌ I don't have permission to read message history in {target_channel.mention}!",
                    ephemeral=True
                )
                return
            except Exception as e:
                logger.error(f"Error fetching message {reply_to}: {e}", exc_info=True)
                await interaction.response.send_message(
                    f"❌ An error occurred while fetching the message to reply to.",
                    ephemeral=True
                )
                return

        # 🗣️ Defer response and send the message
        await interaction.response.defer(ephemeral=True)

        try:
            if embed:
                # Send as embed
                embed_obj = discord.Embed(
                    description=message,
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                embed_obj.set_footer(
                    text=f"Sent by {interaction.user.display_name}",
                    icon_url=interaction.user.display_avatar.url
                )

                sent_message = await target_channel.send(
                    embed=embed_obj,
                    reference=reply_to_message if reply_to_message else None
                )
            else:
                # Send as plain text
                sent_message = await target_channel.send(
                    message,
                    reference=reply_to_message if reply_to_message else None
                )

            # Log the command usage
            await self.log_say_command(
                user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=target_channel.id,
                message_content=message,
                is_embed=embed,
                reply_to_message_id=reply_to_message_id
            )

            # ✅ Send confirmation
            confirmation_text = f"✅ Message sent in {target_channel.mention}!"
            if embed:
                confirmation_text += " (as embed)"
            if reply_to_message:
                confirmation_text += f" (reply to message {reply_to})"

            confirmation = await interaction.followup.send(confirmation_text, ephemeral=True)

            # Auto-delete confirmation after 3 seconds
            await asyncio.sleep(3)
            try:
                await confirmation.delete()
            except discord.NotFound:
                pass  # If already deleted or ephemeral, just ignore

        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to send messages in {target_channel.mention}!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while sending the message.",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Say(bot))
    logger.info("Say cog successfully loaded")

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from database import is_user_bot_moderator

class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="say",
        description="Say what you want the bot to say (Moderators only). Supports markdown, mentions, etc."
    )
    @app_commands.describe(message="Say what you want the bot to say.")
    async def say(self, interaction: discord.Interaction, message: str):
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

            # 🚫 If user isn’t a mod or bot mod, deny access
            if not (has_mod_perms or is_bot_mod):
                await interaction.response.send_message(
                    "❌ You can’t use this command.",
                    ephemeral=True
                )
                return

        except Exception:
            # If check fails (e.g. database error), also deny access
            await interaction.response.send_message(
                "❌ You can’t use this command.",
                ephemeral=True
            )
            return

        # 🗣️ Send the message publicly
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(message)

        # ✅ Send confirmation and auto-delete after 3 seconds
        confirmation = await interaction.followup.send("✅ Sent your message!", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await confirmation.delete()
        except discord.NotFound:
            pass  # If already deleted or ephemeral, just ignore

async def setup(bot):
    await bot.add_cog(Say(bot))

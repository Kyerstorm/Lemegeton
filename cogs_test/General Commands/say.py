import discord
from discord import app_commands
from discord.ext import commands

class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="say",
        description="Say what you want the bot to say. Supports markdown, mentions, etc."
    )
    @app_commands.describe(message="Say what you want the bot to say.")
    async def say(self, interaction: discord.Interaction, message: str):
        # Defer to avoid timeout if deleting later (optional)
        await interaction.response.defer(ephemeral=True)

        # Send the message to the same channel
        await interaction.channel.send(message)

        # Optionally confirm to the user (only they see this)
        await interaction.followup.send("✅ Sent your message!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Say(bot))


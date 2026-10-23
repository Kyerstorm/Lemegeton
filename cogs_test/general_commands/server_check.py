"""Read-only diagnostics for the invoking Discord server and channel."""
from __future__ import annotations
import logging
import discord
from discord import app_commands
from discord.ext import commands
from database import execute_db_operation, get_guild_bot_update_channel
from cogs_test.general_commands.dashboard import command_meta

logger = logging.getLogger(__name__)

def collect_checks(guild: discord.Guild, channel: discord.abc.GuildChannel, bot_member: discord.Member | None) -> list[tuple[str, str, str]]:
    """Return (status, check, actionable detail) for verifiable current-context checks."""
    checks: list[tuple[str, str, str]] = []
    if bot_member is None:
        return [("Needs attention", "Bot membership", "The bot member object is unavailable. Recheck that the bot is still in this server.")]
    perms = channel.permissions_for(bot_member)
    for permission, label, fix in (
        ("view_channel", "View this channel", "Grant the bot View Channel in this channel or its category."),
        ("send_messages", "Send messages", "Grant the bot Send Messages in this channel."),
        ("embed_links", "Embed links", "Grant the bot Embed Links so rich command responses can render."),
    ):
        okay = bool(getattr(perms, permission, False))
        checks.append(("Healthy" if okay else "Needs attention", label, "Permission is available." if okay else fix))
    return checks

def diagnostic_embed(guild: discord.Guild, channel: discord.abc.GuildChannel, bot_member: discord.Member | None) -> discord.Embed:
    checks = collect_checks(guild, channel, bot_member)
    healthy = sum(status == "Healthy" for status, _, _ in checks)
    attention = sum(status == "Needs attention" for status, _, _ in checks)
    embed = discord.Embed(
        title=f"Server Check · {guild.name}",
        description=f"Read-only diagnostics for {getattr(channel, 'mention', channel.name)}.\n**Healthy:** {healthy} · **Needs attention:** {attention}",
        color=discord.Color.green() if attention == 0 else discord.Color.orange(),
    )
    for status, name, details in checks:
        symbol = "✅" if status == "Healthy" else "⚠️" if status == "Needs attention" else "ℹ️"
        embed.add_field(name=f"{symbol} {name} · {status}", value=details[:1024], inline=False)
    embed.set_footer(text="Only the current guild and invocation channel were inspected. No configuration was changed.")
    return embed

async def add_configured_channel_checks(embed: discord.Embed, guild: discord.Guild) -> None:
    """Diagnose the two channel settings exposed by the existing Server Config UI."""
    configurations = []
    try:
        update_channel_id = await get_guild_bot_update_channel(guild.id)
        configurations.append(("Bot updates channel", update_channel_id))
    except Exception:
        logger.warning("Could not read bot-updates configuration for guild %s", guild.id, exc_info=True)
        configurations.append(("Bot updates channel", "unavailable"))

    try:
        row = await execute_db_operation(
            "diagnose invite tracking channel",
            "SELECT announcement_channel_id FROM invite_tracker_settings WHERE guild_id = ?",
            (guild.id,),
            fetch_type="one",
        )
        configurations.append(("Invite tracking channel", row[0] if row else None))
    except Exception:
        logger.warning("Could not read invite channel configuration for guild %s", guild.id, exc_info=True)
        configurations.append(("Invite tracking channel", "unavailable"))

    bot_member = guild.me
    for label, channel_id in configurations:
        if channel_id == "unavailable":
            status, detail = "Unable to verify", "The existing configuration record could not be read. Check database health and retry."
        elif channel_id is None:
            status, detail = "Healthy", "Not configured; this optional notification feature is currently disabled."
        else:
            channel = guild.get_channel_or_thread(int(channel_id))
            if channel is None or getattr(getattr(channel, "guild", None), "id", None) != guild.id:
                status, detail = "Needs attention", f"The configured channel ID {channel_id} cannot be resolved in this guild. Re-select a valid channel in /server-config."
            elif bot_member is None:
                status, detail = "Unable to verify", "The bot member is not available in the guild cache."
            elif not channel.permissions_for(bot_member).send_messages:
                status, detail = "Needs attention", f"The bot cannot send messages in {channel.mention}. Grant Send Messages or choose another channel in /server-config."
            else:
                status, detail = "Healthy", f"{channel.mention} exists in this server and the bot can send messages there."
        icon = "✅" if status == "Healthy" else "⚠️" if status == "Needs attention" else "ℹ️"
        embed.add_field(name=f"{icon} {label} · {status}", value=detail[:1024], inline=False)

    healthy = sum("· Healthy" in field.name for field in embed.fields)
    attention = sum("· Needs attention" in field.name for field in embed.fields)
    unable = sum("· Unable to verify" in field.name for field in embed.fields)
    embed.description = (
        f"Read-only diagnostics for this guild and its configured notification channels.\\n"
        f"**Healthy:** {healthy} · **Needs attention:** {attention} · **Unable to verify:** {unable}"
    )


def diagnostic_text(embed: discord.Embed) -> str:
    """Plain-text fallback so the report still works when Embed Links is missing."""
    parts = [embed.title or "Server Check", embed.description or ""]
    for field in embed.fields:
        parts.append(f"{field.name}\\n{field.value}")
    parts.append(embed.footer.text if embed.footer else "")
    return "\\n\\n".join(part for part in parts if part)[:1900]


class ServerCheckView(discord.ui.View):
    def __init__(self, guild_id: int, channel_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.channel_id = channel_id

    @discord.ui.button(label="Refresh diagnostics", style=discord.ButtonStyle.secondary, custom_id="server-check:refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild_id != self.guild_id or interaction.channel_id != self.channel_id:
            await interaction.response.send_message("This diagnostic panel belongs to another server or channel.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission is required to refresh diagnostics.", ephemeral=True)
            return
        await interaction.response.defer()
        channel = interaction.guild.get_channel_or_thread(self.channel_id) if interaction.guild else None
        if not interaction.guild or channel is None:
            await interaction.edit_original_response(content="The original channel is no longer available.", embed=None, view=None)
            return
        embed = diagnostic_embed(interaction.guild, channel, interaction.guild.me)
        await add_configured_channel_checks(embed, interaction.guild)
        if interaction.guild.me and not channel.permissions_for(interaction.guild.me).embed_links:
            await interaction.edit_original_response(content=diagnostic_text(embed), embed=None, view=self)
        else:
            await interaction.edit_original_response(content=None, embed=embed, view=self)

class ServerCheck(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="server-check", description="Run read-only configuration and permission diagnostics for this server")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @command_meta(section="Server Management", name="Server Check")
    async def server_check(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission is required for diagnostics.", ephemeral=True)
            return
        channel = interaction.channel
        if channel is None or not hasattr(channel, "permissions_for"):
            await interaction.response.send_message("The current channel's permissions cannot be inspected.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = diagnostic_embed(interaction.guild, channel, interaction.guild.me)
        await add_configured_channel_checks(embed, interaction.guild)
        if interaction.guild.me and not channel.permissions_for(interaction.guild.me).embed_links:
            await interaction.edit_original_response(content=diagnostic_text(embed), view=ServerCheckView(interaction.guild.id, channel.id))
        else:
            await interaction.edit_original_response(content=None, embed=embed, view=ServerCheckView(interaction.guild.id, channel.id))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerCheck(bot))

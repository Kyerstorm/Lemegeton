"""Lunar Roles: custom booster roles (commands). Logic lives in helpers/lunar_roles."""
import discord
from discord import app_commands
from discord.ext import commands

from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_info_embed, build_success_embed
from helpers.lunar_roles import ADMIN_GROUP, ROLE_LIMIT
from helpers.lunar_roles import service, storage

logger = service.logger


def _yes_no(value: bool) -> str:
    return "✅ Yes" if value else "❌ No"


class LunarRoles(commands.Cog):
    """Custom booster roles: one personal role per booster."""

    admin = app_commands.Group(
        name=ADMIN_GROUP,
        description="Set up Lunar Roles (custom booster roles)",
        guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            updated = await service.hydrate_migrated_roles(self.bot)
            if updated:
                logger.info("Hydrated %s migrated booster role record(s)", updated)
        except Exception:
            logger.exception("Hydrating migrated booster roles failed")

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error("Lunar command %s failed", getattr(interaction.command, "qualified_name", "?"),
                     exc_info=error)
        embed = build_error_embed("Something went wrong", "That didn't work. Please try again in a moment.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============================================================================
    # ADMIN COMMANDS
    # ============================================================================

    @admin.command(name="settings", description="Show Lunar Roles settings and server feature status")
    @command_meta(section="Customization", name="Lunar Admin Settings")
    async def admin_settings(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        settings = await storage.get_guild_settings(guild.id)
        features = service.feature_status(guild)
        counts = await storage.count_roles_by_status(guild.id)
        problems = service.setup_problems(guild, settings)

        def role_text(role_id):
            role = guild.get_role(role_id) if role_id else None
            return role.mention if role else ("*deleted role*" if role_id else "Not set")

        def channel_text(channel_id, empty):
            channel = guild.get_channel(channel_id) if channel_id else None
            return channel.mention if channel else ("*deleted channel*" if channel_id else empty)

        allowed = [guild.get_role(r) for r in settings.allowed_role_ids]
        allowed_text = ", ".join(r.mention for r in allowed if r) or "None"

        embed = build_info_embed("Lunar Roles Settings", f"Settings for **{guild.name}**")
        embed.add_field(name="Status", value="🟢 On" if settings.enabled else "🔴 Off", inline=True)
        embed.add_field(name="Anchor role", value=role_text(settings.anchor_role_id), inline=True)
        embed.add_field(name="Cooldown", value=f"{settings.cooldown_seconds}s" if settings.cooldown_seconds else "Off", inline=True)
        embed.add_field(name="Command channel", value=channel_text(settings.command_channel_id, "Anywhere"), inline=True)
        embed.add_field(name="Log channel", value=channel_text(settings.log_channel_id, "Not set"), inline=True)
        embed.add_field(name="Blocked words", value=str(len(settings.blocked_words)), inline=True)
        embed.add_field(name="Extra allowed roles", value=allowed_text, inline=False)
        embed.add_field(
            name="Server features",
            value=(
                f"Gradient / holographic: {_yes_no(features.gradient)}\n"
                f"Role icons: {_yes_no(features.icons)}\n"
                f"Roles: {features.role_count} / {ROLE_LIMIT}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Custom roles",
            value=(
                f"Active: {counts[storage.STATUS_ACTIVE]}\n"
                f"Saved: {counts[storage.STATUS_SAVED]}\n"
                f"Missing: {counts[storage.STATUS_MISSING]}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Problems",
            value="\n".join(f"• {p}" for p in problems) if problems else "None",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="anchor", description="Place new custom roles directly below this role")
    @command_meta(section="Customization", name="Lunar Admin Anchor")
    @app_commands.describe(role="Custom roles are created directly below this role (must be below the bot's top role)")
    async def admin_anchor(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_anchor(interaction.guild, role)
        if result.ok:
            embed = build_success_embed("Anchor Set", result.message)
            if not result.data.enabled:
                embed.add_field(name="Next step", value=f"Run `/{ADMIN_GROUP} enable` to turn Lunar Roles on.", inline=False)
        else:
            embed = build_error_embed("Can't Use That Role", result.message)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="enable", description="Turn Lunar Roles on for this server")
    @command_meta(section="Customization", name="Lunar Admin Enable")
    async def admin_enable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_enabled(interaction.guild, True)
        if result.ok:
            embed = build_success_embed("Lunar Roles Enabled", result.message)
            problems = service.setup_problems(interaction.guild, result.data)
            if problems:
                embed.add_field(name="Heads up", value="\n".join(f"• {p}" for p in problems), inline=False)
        else:
            embed = build_error_embed("Can't Enable Yet", result.message)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="disable", description="Turn Lunar Roles off for this server")
    @command_meta(section="Customization", name="Lunar Admin Disable")
    async def admin_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_enabled(interaction.guild, False)
        embed = build_success_embed("Lunar Roles Disabled", result.message + " Existing roles are kept.")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LunarRoles(bot))
    logger.info("LunarRoles cog loaded")

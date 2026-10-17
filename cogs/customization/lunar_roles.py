"""Lunar Roles: custom booster roles (commands). Logic lives in helpers/lunar_roles."""
import discord
from discord import app_commands
from discord.ext import commands

from typing import Optional

from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_info_embed, build_success_embed
from helpers.lunar_roles import ADMIN_GROUP, COMMAND_GROUP, ROLE_LIMIT
from helpers.lunar_roles import service, storage, validation

logger = service.logger

MODE_LABELS = {
    service.MODE_SOLID: "Solid",
    service.MODE_GRADIENT: "Gradient",
    service.MODE_HOLOGRAPHIC: "Holographic",
}


def _yes_no(value: bool) -> str:
    return "✅ Yes" if value else "❌ No"


async def _reply(interaction: discord.Interaction, result: service.Result, success_title: str, error_title: str):
    if result.ok:
        embed = build_success_embed(success_title, result.message)
    else:
        embed = build_error_embed(error_title, result.message)
    if result.notes:
        embed.add_field(name="⚠️ Heads up", value="\n\n".join(result.notes)[:1024], inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


class LunarRoles(commands.Cog):
    """Custom booster roles: one personal role per booster."""

    lunar = app_commands.Group(
        name=COMMAND_GROUP,
        description="Your custom booster role",
        guild_only=True,
    )
    color = app_commands.Group(name="color", description="Color your role", parent=lunar)

    admin = app_commands.Group(
        name=ADMIN_GROUP,
        description="Set up Lunar Roles (custom booster roles)",
        guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )
    allow_role = app_commands.Group(
        name="allow-role", description="Roles allowed to use Lunar Roles besides boosters", parent=admin
    )
    blocked_words = app_commands.Group(
        name="blocked-words", description="Words that can't be used in custom role names", parent=admin
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        try:
            await service.handle_role_deleted(role)
        except Exception:
            logger.exception("Handling deleted role %s in guild %s failed", role.id, role.guild.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if service.is_moderation_role(role):
            await self._sweep(role.guild, f"new moderation role {role.name!r}")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if not service.is_moderation_role(after):
            return
        if not service.is_moderation_role(before) or before.name != after.name:
            await self._sweep(after.guild, f"moderation role {after.name!r} changed")

    async def _sweep(self, guild: discord.Guild, why: str) -> service.SweepResult:
        try:
            return await service.enforce_name_rules(guild, why)
        except Exception:
            logger.exception("Name rules sweep failed in guild %s (%s)", guild.id, why)
            return service.SweepResult()

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            updated = await service.hydrate_migrated_roles(self.bot)
            if updated:
                logger.info("Hydrated %s migrated booster role record(s)", updated)
        except Exception:
            logger.exception("Hydrating migrated booster roles failed")
        try:
            guild_ids = await storage.list_guilds_with_active_roles()
        except Exception:
            logger.exception("Couldn't list guilds for the startup name check")
            return
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild is not None:
                result = await self._sweep(guild, "startup check")
                if result.renamed or result.failed:
                    logger.info("Startup name check in guild %s: %s renamed, %s failed",
                                guild_id, len(result.renamed), len(result.failed))

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        logger.error("Lunar command %s failed", getattr(interaction.command, "qualified_name", "?"),
                     exc_info=error)
        embed = build_error_embed("Something went wrong", "That didn't work. Please try again in a moment.")
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============================================================================
    # USER COMMANDS
    # ============================================================================

    @lunar.command(name="role", description="Create your custom role")
    @command_meta(section="Customization", name="Lunar Role")
    @app_commands.describe(name="Name for your role")
    async def lunar_role(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        result = await service.create_role(interaction.user, name)
        await _reply(interaction, result, "Role Ready", "Couldn't Create Your Role")

    @lunar.command(name="name", description="Rename your custom role")
    @command_meta(section="Customization", name="Lunar Name")
    @app_commands.describe(new_name="New name for your role")
    async def lunar_name(self, interaction: discord.Interaction, new_name: app_commands.Range[str, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        result = await service.rename(interaction.user, new_name)
        await _reply(interaction, result, "Role Renamed", "Couldn't Rename Your Role")

    @color.command(name="set", description="Set your role color by hex")
    @command_meta(section="Customization", name="Lunar Color Set")
    @app_commands.describe(
        color="Hex color, e.g. #FF66AA",
        secondary_color="Second hex color to make a gradient (optional)",
    )
    async def lunar_color_set(self, interaction: discord.Interaction, color: str, secondary_color: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        primary = validation.parse_hex(color)
        secondary = validation.parse_hex(secondary_color) if secondary_color else None
        if primary is None or (secondary_color and secondary is None):
            bad = color if primary is None else secondary_color
            embed = build_error_embed(
                "Invalid Color", f"{validation.code(bad)} isn't a hex color. Try `#FF66AA`, `FF66AA` or `#F6A`."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        mode = service.MODE_GRADIENT if secondary is not None else service.MODE_SOLID
        result = await service.set_colors(interaction.user, mode, primary, secondary)
        await _reply(interaction, result, "Color Updated", "Couldn't Change Your Color")

    @color.command(name="holographic", description="Give your role Discord's holographic style")
    @command_meta(section="Customization", name="Lunar Color Holographic")
    async def lunar_color_holographic(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_colors(interaction.user, service.MODE_HOLOGRAPHIC)
        await _reply(interaction, result, "Color Updated", "Couldn't Change Your Color")

    @lunar.command(name="assign", description="Put your custom role back on")
    @command_meta(section="Customization", name="Lunar Assign")
    async def lunar_assign(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.assign(interaction.user)
        await _reply(interaction, result, "Role On", "Couldn't Assign Your Role")

    @lunar.command(name="unassign", description="Take your custom role off (you keep it)")
    @command_meta(section="Customization", name="Lunar Unassign")
    async def lunar_unassign(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.unassign(interaction.user)
        await _reply(interaction, result, "Role Off", "Couldn't Remove Your Role")

    @lunar.command(name="info", description="Show a custom role's name, colors and icon")
    @command_meta(section="Customization", name="Lunar Info")
    @app_commands.describe(user="Whose role to show (default: yours)")
    async def lunar_info(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer(ephemeral=True)
        target = user or interaction.user
        result = await service.get_info(interaction.user, target)
        if not result.ok:
            await interaction.followup.send(embed=build_error_embed("No Role", result.message), ephemeral=True)
            return
        record, role = result.data
        mode = record.color_mode
        if mode == service.MODE_HOLOGRAPHIC:
            colors = "Discord holographic preset"
        elif mode == service.MODE_GRADIENT:
            colors = f"`{validation.format_hex(record.primary_color)}` → `{validation.format_hex(record.secondary_color)}`"
        else:
            colors = f"`{validation.format_hex(record.primary_color)}`" if record.primary_color else "Default"
        status = {
            storage.STATUS_ACTIVE: "Active",
            storage.STATUS_SAVED: "Saved (not boosting)",
            storage.STATUS_MISSING: "Missing (recreated on next change)",
        }.get(record.status, record.status)

        embed = build_info_embed(f"{target.display_name}'s Lunar Role", role.mention if role else f"**{record.name or 'Unnamed'}**")
        if record.primary_color:
            embed.colour = discord.Colour(record.primary_color)
        embed.add_field(name="Name", value=discord.utils.escape_markdown(record.name or "Unnamed"), inline=True)
        embed.add_field(name="Style", value=MODE_LABELS.get(mode, mode), inline=True)
        embed.add_field(name="Colors", value=colors, inline=True)
        has_icon = bool(role and role.display_icon) or bool(record.icon_png)
        embed.add_field(name="Icon", value="Yes" if has_icon else "None", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        if record.created_at:
            embed.add_field(name="Created", value=record.created_at.strftime("%d %b %Y"), inline=True)
        if role and isinstance(role.display_icon, discord.Asset):
            embed.set_thumbnail(url=role.display_icon.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

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
        anchor_text = role_text(settings.anchor_role_id)
        if settings.anchor_role_id:
            anchor_text = f"Directly {settings.anchor_place} {anchor_text}"
        embed.add_field(name="Anchor role", value=anchor_text, inline=True)
        embed.add_field(name="Cooldown", value=f"{settings.cooldown_seconds}s" if settings.cooldown_seconds else "Off", inline=True)
        embed.add_field(name="Command channel", value=channel_text(settings.command_channel_id, "Anywhere"), inline=True)
        embed.add_field(name="Log channel", value=channel_text(settings.log_channel_id, "Not set"), inline=True)
        embed.add_field(
            name="Blocked words",
            value=f"Built-in: {len(service.active_protected_words(settings))} on\nCustom: {len(settings.blocked_words)}",
            inline=True,
        )
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
        breaking = await service.names_breaking_rules(guild)
        embed.add_field(
            name="Names breaking the rules",
            value=(
                str(len(breaking)) if not breaking
                else f"⚠️ {len(breaking)}: "
                     + ", ".join(f"<@{record.user_id}>" for record, _, _ in breaking[:10])
                     + ". These are renamed automatically; if this stays above 0, check I have Manage Roles "
                       "and my role is above theirs."
            ),
            inline=False,
        )
        hiding = service.colored_roles_above_custom(guild, settings, await storage.list_active_role_ids(guild.id))
        if hiding:
            shown = ", ".join(r.mention for r in hiding[:10]) + (f" and {len(hiding) - 10} more" if len(hiding) > 10 else "")
            embed.add_field(
                name="⚠️ Colors may be hidden",
                value=(
                    f"{shown} {'has' if len(hiding) == 1 else 'have'} a color and sit{'s' if len(hiding) == 1 else ''} "
                    "above the custom roles, so members with "
                    f"{'it' if len(hiding) == 1 else 'them'} won't see their custom color. "
                    f"Use `/{ADMIN_GROUP} anchor place:above` on a higher role, or remove those roles' colors."
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="anchor", description="Choose where new custom roles are placed")
    @command_meta(section="Customization", name="Lunar Admin Anchor")
    @app_commands.describe(
        role="Custom roles are placed next to this role (must be below the bot's top role)",
        place="Directly below (default) or directly above the anchor",
    )
    @app_commands.choices(place=[
        app_commands.Choice(name="below", value=service.PLACE_BELOW),
        app_commands.Choice(name="above", value=service.PLACE_ABOVE),
    ])
    async def admin_anchor(
        self, interaction: discord.Interaction, role: discord.Role, place: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_anchor(interaction.guild, role, place.value if place else service.PLACE_BELOW)
        if result.ok:
            embed = build_success_embed("Anchor Set", result.message)
            if not result.data.enabled:
                embed.add_field(name="Next step", value=f"Run `/{ADMIN_GROUP} enable` to turn Lunar Roles on.", inline=False)
            embed.add_field(name="Note", value="Existing custom roles aren't moved; only new ones are placed by the anchor.", inline=False)
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

    @allow_role.command(name="add", description="Let members with this role use Lunar Roles (besides boosters)")
    @command_meta(section="Customization", name="Lunar Admin Allow Role Add")
    @app_commands.describe(role="Members with this role can use Lunar Roles")
    async def admin_allow_role_add(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        result = await service.add_allowed_role(interaction.guild, role)
        await _reply(interaction, result, "Role Allowed", "Couldn't Add That Role")

    @allow_role.command(name="remove", description="Stop a role from granting Lunar Roles access")
    @command_meta(section="Customization", name="Lunar Admin Allow Role Remove")
    @app_commands.describe(role="Role to remove from the allowed list")
    async def admin_allow_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        result = await service.remove_allowed_role(interaction.guild, role)
        await _reply(interaction, result, "Role Removed", "Couldn't Remove That Role")

    @allow_role.command(name="list", description="Show roles allowed to use Lunar Roles besides boosters")
    @command_meta(section="Customization", name="Lunar Admin Allow Role List")
    async def admin_allow_role_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        roles = await service.list_allowed_roles(interaction.guild)
        body = "\n".join(f"• {r.mention}" for r in roles) if roles else "None - only server boosters can use Lunar Roles."
        await interaction.followup.send(embed=build_info_embed("Allowed Roles", body), ephemeral=True)

    @blocked_words.command(name="add", description="Block a word in role names (or turn a built-in word back on)")
    @command_meta(section="Customization", name="Lunar Admin Blocked Words Add")
    @app_commands.describe(word="Word or phrase to block")
    async def admin_blocked_add(self, interaction: discord.Interaction, word: app_commands.Range[str, 1, 50]):
        await interaction.response.defer(ephemeral=True)
        result = await service.add_blocked_word(interaction.guild, word)
        if not result.ok:
            await _reply(interaction, result, "Word Blocked", "Couldn't Block That Word")
            return
        sweep = await self._sweep(interaction.guild, "word blocked")
        embed = build_success_embed("Word Blocked", result.message)

        def lines(items, fmt):
            shown = [fmt(*item) for item in items[:15]]
            if len(items) > 15:
                shown.append(f"…and {len(items) - 15} more")
            return "\n".join(shown)[:1024]

        if sweep.renamed:
            embed.add_field(
                name=f"Renamed ({len(sweep.renamed)})",
                value=lines(sweep.renamed, lambda uid, old, new: f"<@{uid}>: {validation.code(old)} → {validation.code(new)}"),
                inline=False,
            )
        else:
            embed.add_field(name="Renamed", value="No existing role names used it.", inline=False)
        if sweep.failed:
            embed.add_field(
                name=f"Couldn't rename ({len(sweep.failed)})",
                value=lines(sweep.failed, lambda uid, name, why: f"<@{uid}>: {validation.code(name)} - {why}"),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @blocked_words.command(name="remove", description="Unblock a word (built-in words can be switched off)")
    @command_meta(section="Customization", name="Lunar Admin Blocked Words Remove")
    @app_commands.describe(word="Word or phrase to unblock")
    async def admin_blocked_remove(self, interaction: discord.Interaction, word: app_commands.Range[str, 1, 50]):
        await interaction.response.defer(ephemeral=True)
        result = await service.remove_blocked_word(interaction.guild, word)
        await _reply(interaction, result, "Word Unblocked", "Couldn't Unblock That Word")

    @blocked_words.command(name="list", description="Show blocked and protected words for role names")
    @command_meta(section="Customization", name="Lunar Admin Blocked Words List")
    async def admin_blocked_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await storage.get_guild_settings(interaction.guild.id)

        def words(items):
            text = ", ".join(validation.code(w) for w in items)
            return text[:1000] + "…" if len(text) > 1000 else (text or "None")

        embed = build_info_embed(
            "Blocked Words",
            "Names are also refused if they copy an existing role's name or include the name of a role "
            "with moderation permissions.",
        )
        embed.add_field(
            name="Built-in (whole words, leetspeak and separators ignored)",
            value=words(service.active_protected_words(settings)),
            inline=False,
        )
        if settings.removed_default_words:
            embed.add_field(name="Built-in, switched off", value=words(settings.removed_default_words), inline=False)
        embed.add_field(name="Custom (blocked anywhere in the name)", value=words(settings.blocked_words), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LunarRoles(bot))
    logger.info("LunarRoles cog loaded")

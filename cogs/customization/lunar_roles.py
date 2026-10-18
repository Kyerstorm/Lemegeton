"""Lunar Roles: custom booster roles (commands). Logic lives in helpers/lunar_roles."""
import asyncio
import hashlib
import io
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from cogs_test.general_commands.dashboard import command_meta
from helpers.color_palette import PALETTE
from helpers.embed_helper import build_error_embed, build_info_embed, build_success_embed, build_warning_embed
from helpers.lunar_roles import ADMIN_GROUP, COMMAND_GROUP, ROLE_LIMIT
from helpers.lunar_roles import images, service, storage, tokens, validation

logger = service.logger  # file log (logs/lunar_roles.log)
console_logger = logging.getLogger("lunar_roles_console")  # propagates to the bot's console output

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


def _embed(title: str, text: str, colour: discord.Colour) -> discord.Embed:
    return discord.Embed(title=title, description=text[:4000], colour=colour)


class PendingButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"lunar:pending:(?P<id>[0-9]+):(?P<action>confirm|cancel)",
):
    """Confirm/Cancel for a saved pending removal. Persistent: works after restarts."""

    def __init__(self, pending_id: int, action: str):
        confirm = action == "confirm"
        super().__init__(discord.ui.Button(
            label="Confirm removal" if confirm else "Cancel (keep roles)",
            style=discord.ButtonStyle.danger if confirm else discord.ButtonStyle.secondary,
            custom_id=f"lunar:pending:{pending_id}:{action}",
        ))
        self.pending_id = pending_id
        self.action = action

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["id"]), match["action"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        if interaction.guild is None or perms is None or not perms.manage_roles:
            await interaction.response.send_message("Only members with **Manage Roles** can do this.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if self.action == "cancel":
            await interaction.response.edit_message(embed=_embed("Cancelling…", "One moment.", PALETTE.NEUTRAL), view=None)
            result = await service.cancel_pending(guild, self.pending_id, interaction.user)
            title = "Removal Cancelled" if result.ok else "Nothing To Do"
            await interaction.edit_original_response(embed=_embed(title, result.message, PALETTE.NEUTRAL), view=None)
            return

        await interaction.response.edit_message(embed=_embed("Removing…", "Starting.", PALETTE.WARNING), view=None)

        async def progress(done: int, total: int, report: service.ArchiveReport):
            await interaction.edit_original_response(
                embed=_embed("Removing…", f"{done}/{total} processed. {report.summary()}", PALETTE.WARNING)
            )

        result = await service.confirm_pending(guild, self.pending_id, interaction.user, progress=progress)
        if not result.ok:
            await interaction.edit_original_response(embed=_embed("Nothing To Do", result.message, PALETTE.NEUTRAL))
            return
        await interaction.edit_original_response(embed=_report_embed("Removal Confirmed", result.data))


def _pending_view(pending_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(PendingButton(pending_id, "confirm"))
    view.add_item(PendingButton(pending_id, "cancel"))
    return view


def _report_embed(title: str, report: service.ArchiveReport, intro: str = "") -> discord.Embed:
    lines = [intro] if intro else []
    lines.append(report.summary())
    if report.archived:
        lines.append("**Removed:** " + ", ".join(f"<@{uid}>" for uid, _ in report.archived[:30]))
    if report.skipped:
        lines.append("**Skipped:** " + ", ".join(f"<@{uid}> ({why})" for uid, why in report.skipped[:15]))
    if report.failed:
        lines.append("**Failed:** " + ", ".join(f"<@{uid}> ({why})" for uid, why in report.failed[:15]))
    colour = PALETTE.WARNING if report.failed else PALETTE.SUCCESS
    return _embed(title, "\n".join(lines), colour)


class ConfirmView(discord.ui.View):
    """60-second Confirm/Cancel for an admin command; only the admin who ran it can press."""

    def __init__(self, invoker_id: int, on_confirm, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.on_confirm = on_confirm
        self.message: Optional[discord.WebhookMessage] = None
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("Only the admin who ran the command can answer this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finished = True
        self.stop()
        await interaction.response.edit_message(embed=_embed("Working…", "Starting.", PALETTE.WARNING), view=None)
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finished = True
        self.stop()
        await interaction.response.edit_message(embed=_embed("Cancelled", "Nothing was changed.", PALETTE.NEUTRAL), view=None)

    async def on_timeout(self):
        if self.finished or self.message is None:
            return
        try:
            await self.message.edit(embed=_embed("Timed Out", "No answer within 60 seconds, so nothing was changed.", PALETTE.NEUTRAL), view=None)
        except discord.HTTPException:
            pass


PALETTE_TIMEOUT = 300  # seconds the palette menus stay usable
CLEAR_SECONDARY = "clear"


class PaletteView(discord.ui.View):
    """Two select menus from /lunar palette. Only the member who ran it can use them."""

    def __init__(self, owner: discord.Member, colors: list, gradient_ok: bool):
        super().__init__(timeout=PALETTE_TIMEOUT)
        self.owner_id = owner.id
        self.colors = colors
        self.primary: Optional[int] = None
        self.secondary: Optional[int] = None
        self.message: Optional[discord.WebhookMessage] = None
        self.last_result: Optional[service.Result] = None
        self.cooldown_passed = False  # only the first successful pick in this menu checks the cooldown

        self.primary_select = discord.ui.Select(
            placeholder="Primary color",
            options=[discord.SelectOption(label=f"#{c:06X}", value=f"{c:06X}") for c in colors[:25]],
        )
        self.primary_select.callback = self._on_primary
        self.add_item(self.primary_select)

        secondary_options = [discord.SelectOption(label="Clear secondary", value=CLEAR_SECONDARY,
                                                  description="Back to a solid color")]
        secondary_options += [discord.SelectOption(label=f"#{c:06X}", value=f"{c:06X}") for c in colors[:24]]
        self.secondary_select = discord.ui.Select(
            placeholder="Secondary color — makes a gradient" if gradient_ok
            else "Gradients need 3 server boosts (Enhanced Role Styles)",
            options=secondary_options,
            disabled=not gradient_ok,
        )
        self.secondary_select.callback = self._on_secondary
        self.add_item(self.secondary_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                f"This palette belongs to someone else. Run `/{COMMAND_GROUP} palette` to get your own.", ephemeral=True
            )
            return False
        return True

    async def _on_primary(self, interaction: discord.Interaction):
        self.primary = int(self.primary_select.values[0], 16)
        await self._apply(interaction)

    async def _on_secondary(self, interaction: discord.Interaction):
        value = self.secondary_select.values[0]
        self.secondary = None if value == CLEAR_SECONDARY else int(value, 16)
        await self._apply(interaction)

    async def _apply(self, interaction: discord.Interaction):
        await interaction.response.defer()
        member = interaction.user
        primary = self.primary
        if primary is None:  # secondary picked first: build on the role's current colour
            record = await storage.get_custom_role(member.guild.id, member.id)
            primary = record.primary_color if record and record.color_mode != service.MODE_HOLOGRAPHIC else None
        if primary is None:
            self.last_result = service.Result(False, "Pick a **primary** color first.")
        elif self.secondary is not None:
            self.last_result = await service.set_colors(member, service.MODE_GRADIENT, primary, self.secondary,
                                                        check_cooldown=not self.cooldown_passed)
        else:
            self.last_result = await service.set_colors(member, service.MODE_SOLID, primary,
                                                        check_cooldown=not self.cooldown_passed)
        if self.last_result.ok:
            self.cooldown_passed = True
        self._show_selection()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    def _show_selection(self):
        """Keep the picked colours shown in the menus (Discord resets them to the placeholder otherwise)."""
        primary = f"{self.primary:06X}" if self.primary is not None else None
        secondary = f"{self.secondary:06X}" if self.secondary is not None else None
        for option in self.primary_select.options:
            option.default = option.value == primary
        for option in self.secondary_select.options:
            option.default = option.value == secondary

    def build_embed(self, expired: bool = False) -> discord.Embed:
        lines = [
            "Pick a **primary** color for a solid color. Add a **secondary** color to make a gradient.",
            "",
            f"**Primary:** {validation.code(validation.format_hex(self.primary)) if self.primary is not None else 'not picked'}",
            f"**Secondary:** {validation.code(validation.format_hex(self.secondary)) if self.secondary is not None else 'none'}",
        ]
        if expired:
            lines += ["", f"⏱️ This palette expired. Run `/{COMMAND_GROUP} palette` again."]
        colour = PALETTE.PRIMARY
        if self.last_result is not None:
            lines += ["", ("✅ " if self.last_result.ok else "❌ ") + self.last_result.message]
            if self.last_result.ok and self.primary is not None:
                colour = discord.Colour(self.primary)
        embed = discord.Embed(title="Colors from your avatar", description="\n".join(lines), colour=colour)
        embed.set_image(url="attachment://palette.png")
        if self.last_result is not None and self.last_result.notes:
            embed.add_field(name="⚠️ Heads up", value="\n\n".join(self.last_result.notes)[:1024], inline=False)
        embed.set_footer(text=f"Only you can use these menus. They expire after {PALETTE_TIMEOUT // 60} minutes.")
        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=self.build_embed(expired=True), view=self)
            except discord.HTTPException:
                pass


LIST_PAGE_SIZE = 10
LIST_TIMEOUT = 300  # seconds the list buttons stay usable

STATUS_LABELS = {
    storage.STATUS_ACTIVE: "Active",
    storage.STATUS_SAVED: "Saved",
    storage.STATUS_MISSING: "Missing",
}


def _list_line(entry: service.ListEntry) -> str:
    record = entry.record
    if entry.role is not None:
        role_text = entry.role.mention
    else:
        role_text = f"**{discord.utils.escape_markdown(record.name or 'Unnamed')}**"
    line = f"<@{record.user_id}> · {role_text} · {STATUS_LABELS.get(record.status, record.status)}"
    if entry.pending:
        line += " · ⏳ waiting for removal approval"
    if entry.snoozed:
        line += " · 💤 kept (asked again later)"
    return line


class ListView(discord.ui.View):
    """Previous/Next pages for /lunar-admin list. Only the admin who ran it can use them."""

    def __init__(self, invoker_id: int, entries: list, title: str):
        super().__init__(timeout=LIST_TIMEOUT)
        self.invoker_id = invoker_id
        self.entries = entries
        self.title = title
        self.page = 0
        self.pages = max(1, -(-len(entries) // LIST_PAGE_SIZE))
        self.message: Optional[discord.WebhookMessage] = None
        self._update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                f"Run `/{ADMIN_GROUP} list` to get your own list.", ephemeral=True
            )
            return False
        return True

    def _update_buttons(self):
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.pages - 1

    def build_embed(self, expired: bool = False) -> discord.Embed:
        start = self.page * LIST_PAGE_SIZE
        shown = self.entries[start:start + LIST_PAGE_SIZE]
        body = "\n".join(_list_line(e) for e in shown) if shown else "No custom roles here yet."
        if expired:
            body += f"\n\n⏱️ These buttons expired. Run `/{ADMIN_GROUP} list` again."
        embed = build_info_embed(self.title, body)
        embed.set_footer(text=f"Page {self.page + 1} of {self.pages} · {len(self.entries)} role(s)")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(embed=self.build_embed(expired=True), view=self)
            except discord.HTTPException:
                pass


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
        self._first_reconcile = True
        self._debug_warned = False

    async def cog_load(self):
        self.bot.add_dynamic_items(PendingButton)
        service.pending_view_factory = _pending_view
        self._warn_debug_switch_console()
        # Hot reload (cog watcher) after the bot is ready: on_ready won't fire again.
        if self.bot.user is not None and self.bot.is_ready() and not self.reconcile_loop.is_running():
            self.reconcile_loop.start()

    async def cog_unload(self):
        self.reconcile_loop.cancel()
        self.bot.remove_dynamic_items(PendingButton)
        service.pending_view_factory = None

    # (setting name, is it set, is it active, what it does, log-channel text)
    @staticmethod
    def _debug_switches():
        return (
            ("LUNAR_DEBUG_FAIL_MEMBER_FETCH", config.LUNAR_DEBUG_FAIL_MEMBER_FETCH, service.debug_fetch_fail_active(),
             "Reconcile will NOT remove any custom roles while this is set.",
             "the regular check won't remove any custom roles"),
            ("LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS", config.LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS,
             service.debug_preview_enhanced_active(),
             "The color picker shows Gradient/Holographic even without Enhanced Role Styles (3 server boosts; saving is still refused).",
             "the color picker unlocks Gradient and Holographic for previewing (saving them is still refused)"),
            ("LUNAR_DEBUG_PREVIEW_ROLE_ICONS", config.LUNAR_DEBUG_PREVIEW_ROLE_ICONS,
             service.debug_preview_icons_active(),
             "The color picker's Role Icon tab works without Role Icons (setting an icon is still refused).",
             "the color picker unlocks the Role Icon tab for testing (setting an icon is still refused)"),
        )

    @classmethod
    def _warn_debug_switch_console(cls):
        for name, is_set, active, effect, _ in cls._debug_switches():
            if not is_set:
                continue
            if active:
                for line in (
                    "!" * 72,
                    f"!!! {name} IS ON - TEST SWITCH",
                    f"!!! {effect}",
                    "!!! Remove it from .env outside testing.",
                    "!" * 72,
                ):
                    console_logger.warning(line)
                    logger.warning(line)
            else:
                console_logger.warning("%s is set but ignored (ENVIRONMENT isn't development).", name)

    async def _warn_debug_switch_channels(self):
        if self._debug_warned:
            return
        active = [(name, text) for name, _, on, _, text in self._debug_switches() if on]
        if not active:
            return
        self._debug_warned = True
        for guild in self.bot.guilds:
            for name, text in active:
                await service.log_event(
                    guild, f"🚧 **Test switch on:** `{name}` is set, so {text}. Remove it from `.env` outside testing.",
                    "error",
                )

    # ============================================================================
    # LIFECYCLE EVENTS
    # ============================================================================

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or (before.premium_since == after.premium_since and before.roles == after.roles):
            return
        try:
            await self._handle_member_change(before, after)
        except Exception:
            logger.exception("Handling member update for %s in guild %s failed", after.id, after.guild.id)

    async def _handle_member_change(self, before: discord.Member, after: discord.Member):
        guild = after.guild
        settings = await storage.get_guild_settings(guild.id)
        was = service.is_eligible(before, settings)
        now = service.is_eligible(after, settings)
        boost_started = before.premium_since is None and after.premium_since is not None

        if was and not now:
            stopped_boosting = before.premium_since is not None and after.premium_since is None
            record = await storage.get_custom_role(guild.id, after.id)
            if record and record.status != storage.STATUS_SAVED:
                service.queue_archive(guild, after.id, "stopped boosting" if stopped_boosting else "lost their allowed role")
            return

        if now and not was:
            service.unqueue_archive(guild.id, after.id)
            if (await service.restore(after, settings)).ok:
                return  # restore sends the "welcome back" DM
            ready = service.ensure_ready(guild, settings).ok
            if boost_started:
                await self._send_boost_welcome(after, ready)
            elif ready and await storage.get_custom_role(guild.id, after.id) is None:
                await self._send_access_dm(after)
            return

        if boost_started:  # already allowed through a role; still thank them for boosting
            await self._send_boost_welcome(after, service.ensure_ready(guild, settings).ok)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return
        try:
            record = await storage.get_custom_role(member.guild.id, member.id)
            if record and record.status != storage.STATUS_SAVED:
                service.queue_archive(member.guild, member.id, "left the server")
        except Exception:
            logger.exception("Handling member leave for %s in guild %s failed", member.id, member.guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        try:
            await service.restore(member)
        except Exception:
            logger.exception("Handling member join for %s in guild %s failed", member.id, member.guild.id)

    async def _send_boost_welcome(self, member: discord.Member, ready: bool):
        embed = discord.Embed(
            title="🎉 Welcome, Server Booster!",
            description=f"Thank you for boosting **{member.guild.name}**!",
            color=PALETTE.WARNING,
        )
        if ready:
            embed.add_field(
                name="🎨 Your own custom role",
                value=f"Use `/{COMMAND_GROUP} role <name>` to create it, then `/{COMMAND_GROUP} color set` to color it!\n\n"
                      f"**Example:** `/{COMMAND_GROUP} role name:My Cool Role`",
                inline=False,
            )
            embed.add_field(
                name="💡 Tips",
                value="• You get **one** custom role per server\n"
                      f"• Rename or recolor it anytime with `/{COMMAND_GROUP} name` and `/{COMMAND_GROUP} color set`\n"
                      "• If you stop boosting, your role is saved and comes back when you boost again",
                inline=False,
            )
        embed.set_footer(text=f"Thank you for supporting {member.guild.name}!")
        await self._dm(member, embed)

    async def _send_access_dm(self, member: discord.Member):
        embed = discord.Embed(
            title="🎨 You can make a custom role",
            description=f"You now have access to custom roles in **{member.guild.name}**.\n"
                        f"Use `/{COMMAND_GROUP} role <name>` to create yours, then `/{COMMAND_GROUP} color set` to color it.",
            color=PALETTE.PRIMARY,
        )
        await self._dm(member, embed)

    @staticmethod
    async def _dm(member: discord.Member, embed: discord.Embed):
        try:
            await member.send(embed=embed)
            logger.info("Sent Lunar DM to %s in guild %s", member.id, member.guild.id)
        except discord.HTTPException:
            logger.info("Couldn't DM %s (DMs closed)", member.id)

    # ============================================================================
    # RECONCILE (startup + every LUNAR_RECONCILE_MINUTES)
    # ============================================================================

    @tasks.loop(minutes=config.LUNAR_RECONCILE_MINUTES)
    async def reconcile_loop(self):
        why = "startup check" if self._first_reconcile else "regular check"
        self._first_reconcile = False
        try:
            guild_ids = await storage.list_guilds_with_records()
        except Exception:
            logger.exception("Couldn't list guilds for the Lunar reconcile")
            return
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logger.warning("Reconcile skipped guild %s: not available to the bot", guild_id)
                continue
            try:
                await service.reconcile_guild(guild)
            except Exception:
                logger.exception("Reconcile failed in guild %s", guild_id)
            await self._sweep(guild, why)
        logger.info("Reconcile (%s) finished for %s guild(s); next in %s min",
                    why, len(guild_ids), config.LUNAR_RECONCILE_MINUTES)

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
        await self._warn_debug_switch_channels()
        # First run happens immediately (startup reconcile + name check), then every N minutes.
        if not self.reconcile_loop.is_running():
            self.reconcile_loop.start()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Every /lunar command (not /lunar-admin) only works in the command channel, if one is set."""
        command = interaction.command
        root = getattr(command, "root_parent", None) if command else None
        if root is None or root.name != COMMAND_GROUP or interaction.guild is None:
            return True
        settings = await storage.get_guild_settings(interaction.guild.id)
        problem = service.command_channel_problem(interaction.channel, settings)
        if problem is None:
            return True
        await interaction.response.send_message(embed=build_error_embed("Wrong Channel", problem), ephemeral=True)
        return False

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure) and interaction.response.is_done():
            return  # interaction_check already told them where to go
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

    @color.command(name="set", description="Set your role color by hex. Try /lunar color-picker to pick it visually.")
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
        if record.icon_emoji or (role and isinstance(role.display_icon, str)):
            icon_text = record.icon_emoji or role.display_icon
        elif record.icon_png or (role and role.display_icon):
            icon_text = "Image"
        else:
            icon_text = "None"
        embed.add_field(name="Icon", value=icon_text, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        if record.created_at:
            embed.add_field(name="Created", value=record.created_at.strftime("%d %b %Y"), inline=True)
        if role and isinstance(role.display_icon, discord.Asset):
            embed.set_thumbnail(url=role.display_icon.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @lunar.command(name="palette", description="Pick your role color from the colors in your avatar")
    @command_meta(section="Customization", name="Lunar Palette")
    async def lunar_palette(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        error = await service.precheck(member)
        if error:
            await interaction.followup.send(embed=build_error_embed("Can't Show Your Palette", error.message), ephemeral=True)
            return
        result = await service.get_palette(member)
        if not result.ok:
            await interaction.followup.send(embed=build_error_embed("Can't Show Your Palette", result.message), ephemeral=True)
            return
        colors = result.data
        swatches = await asyncio.to_thread(images.render_swatches, colors)
        view = PaletteView(member, colors, gradient_ok=service.feature_status(member.guild).gradient)
        view.message = await interaction.followup.send(
            embed=view.build_embed(), file=discord.File(io.BytesIO(swatches), filename="palette.png"),
            view=view, ephemeral=True, wait=True,
        )

    @lunar.command(name="icon", description="Set your role icon from an image or an emoji (empty = remove it)")
    @command_meta(section="Customization", name="Lunar Icon")
    @app_commands.describe(
        image=f"PNG or JPEG, up to {images.format_size(images.source_max_bytes())}. The center square is used.",
        emoji="A standard emoji like 🌙 (pick it from the emoji picker)",
    )
    async def lunar_icon(self, interaction: discord.Interaction,
                         image: Optional[discord.Attachment] = None, emoji: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if image is not None and emoji:
            await interaction.followup.send(
                embed=build_error_embed("Pick One", "Send either an image **or** an emoji, not both."), ephemeral=True
            )
            return
        if image is None and not emoji:
            result = await service.remove_icon(member)
            await _reply(interaction, result, "Icon Removed", "Couldn't Remove Your Icon")
            return
        if image is not None:
            error = await service.precheck(member)
            if error:
                await interaction.followup.send(embed=build_error_embed("Couldn't Set Your Icon", error.message), ephemeral=True)
                return
            logger.info(
                "Icon upload from %s: filename=%r content_type=%r size=%s %sx%s flags=%s url=%s",
                member.id, image.filename, image.content_type, image.size, image.width, image.height,
                image.flags.value, image.url.split("?")[0],
            )
            try:
                images.check_declared_size(image.size)  # before downloading anything
                images.check_attachment_metadata(image.content_type, image.flags.animated)
                data = await image.read(use_cached=False)  # the original file, not the media proxy
            except images.ImageError as exc:
                await interaction.followup.send(embed=build_error_embed("Couldn't Set Your Icon", exc.message), ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(
                    embed=build_error_embed("Couldn't Set Your Icon", "I couldn't download that image. Please try again."),
                    ephemeral=True,
                )
                return
            logger.info("Icon upload from %s: downloaded %s bytes, first bytes %s, sha256 %s",
                        member.id, len(data), data[:16].hex(" "), hashlib.sha256(data).hexdigest()[:16])
            if len(data) != image.size:
                logger.warning("Icon upload from %s: downloaded %s bytes but Discord reported %s - the file was changed",
                               member.id, len(data), image.size)
            result = await service.set_icon(member, image=data)
            if result.ok:
                result.message += f" Tip: crop it precisely with `/{COMMAND_GROUP} color-picker`."
        else:
            result = await service.set_icon(member, emoji=emoji)
        await _reply(interaction, result, "Icon Set", "Couldn't Set Your Icon")

    @lunar.command(name="color-picker", description="Get a private link to a web page for styling your role")
    @command_meta(section="Customization", name="Lunar Color Picker")
    async def lunar_color_picker(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        guild = member.guild
        error = await service.precheck(member)
        if error:
            await interaction.followup.send(embed=build_error_embed("Can't Open The Picker", error.message), ephemeral=True)
            return
        problem = service.picker_link_problem()
        if problem is None and not getattr(self.bot, "lunar_picker_ready", False):
            problem = "the web server isn't running (check the bot log for why it didn't start)"
        if problem:
            logger.warning("Color picker link refused in guild %s: %s", guild.id, problem)
            await service.log_event(guild, f"I couldn't give {member.mention} a color picker link: {problem}.", "error")
            await interaction.followup.send(
                embed=build_error_embed("Can't Open The Picker", service.PICKER_UNAVAILABLE_MESSAGE), ephemeral=True
            )
            return

        token, link = tokens.create(guild.id, member.id)
        url = service.picker_url(token)
        latest = int(link.max_expires_at)
        embed = build_info_embed(
            "Your Color Picker",
            f"This private link stays open while you use it. It closes after "
            f"**{service.format_duration(int(link.idle_ttl))}** without use, and at <t:{latest}:t> "
            f"(<t:{latest}:R>) at the latest.\n\n"
            f"Running `/{COMMAND_GROUP} color-picker` again gives you a new link and stops this one. "
            "**Don't share it:** anyone with it can change your role until it closes.",
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Open color picker", style=discord.ButtonStyle.link, url=url))
        try:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException:
            # Discord can refuse link buttons for some addresses (like localhost); show the link as text.
            logger.info("Discord refused the picker link button in guild %s; sending the link as text", guild.id)
            embed.add_field(name="Open this link in your browser", value=url, inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("Color picker link created for %s in guild %s", member.id, guild.id)

    @lunar.command(name="position", description="Move your role directly above or below another member's Lunar role")
    @command_meta(section="Customization", name="Lunar Position")
    @app_commands.describe(
        direction="Put your role directly above or below that role",
        role="Another member's Lunar role",
    )
    @app_commands.choices(direction=[
        app_commands.Choice(name="above", value=service.PLACE_ABOVE),
        app_commands.Choice(name="below", value=service.PLACE_BELOW),
    ])
    async def lunar_position(self, interaction: discord.Interaction, direction: app_commands.Choice[str], role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        result = await service.move(interaction.user, role, direction.value)
        await _reply(interaction, result, "Role Moved", "Couldn't Move Your Role")

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
        embed.add_field(name="Cooldown", value=service.format_duration(settings.cooldown_seconds) if settings.cooldown_seconds else "Off", inline=True)
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
                f"Gradient / holographic (3 boosts): {_yes_no(features.gradient)}\n"
                f"Role icons (Boost Level 2): {_yes_no(features.icons)}\n"
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
        pending = await storage.get_open_pending(guild.id)
        if pending is not None:
            embed.add_field(
                name="⚠️ Removal waiting for approval",
                value=f"{len(pending.user_ids)} custom role(s) ({pending.reason}). "
                      f"Use `/{ADMIN_GROUP} pending` to confirm or cancel.",
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
            restored = await service.restore_saved(interaction.guild)
            if restored:
                embed.add_field(name="Restored", value=f"{restored} saved role(s) for members who qualify again.", inline=False)
        else:
            embed = build_error_embed("Can't Enable Yet", result.message)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="disable", description="Turn Lunar Roles off for this server")
    @command_meta(section="Customization", name="Lunar Admin Disable")
    async def admin_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_enabled(interaction.guild, False)
        embed = build_success_embed(
            "Lunar Roles Disabled",
            result.message + " Existing roles are kept. Members who stop qualifying still lose their role; "
                             "saved roles come back once you enable it again.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @admin.command(name="log-channel", description="Where Lunar Roles posts events and errors (empty = off)")
    @command_meta(section="Customization", name="Lunar Admin Log Channel")
    @app_commands.describe(channel="Channel for Lunar Roles logs; leave empty to turn logging off")
    async def admin_log_channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if channel is None:
            await storage.update_guild_settings(guild.id, log_channel_id=None)
            await interaction.followup.send(embed=build_success_embed("Logging Off", "Lunar Roles won't post logs anymore."), ephemeral=True)
            return
        perms = channel.permissions_for(guild.me)
        missing = [name for name, ok in (("View Channel", perms.view_channel), ("Send Messages", perms.send_messages),
                                         ("Embed Links", perms.embed_links)) if not ok]
        if missing:
            await interaction.followup.send(
                embed=build_error_embed("Can't Post There", f"I need {', '.join(f'**{m}**' for m in missing)} in {channel.mention}."),
                ephemeral=True,
            )
            return
        settings = await storage.update_guild_settings(guild.id, log_channel_id=channel.id)
        await service.log_event(guild, f"Lunar Roles will post events here (set by {interaction.user.mention}).", "success", settings)
        await interaction.followup.send(embed=build_success_embed("Log Channel Set", f"Logging to {channel.mention}."), ephemeral=True)

    @admin.command(name="channel", description="Only allow /lunar commands in one channel (empty = anywhere)")
    @command_meta(section="Customization", name="Lunar Admin Channel")
    @app_commands.describe(channel="Channel for /lunar commands (its threads work too); leave empty to allow anywhere")
    async def admin_channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_command_channel(interaction.guild, channel)
        await _reply(interaction, result, "Command Channel Set" if channel else "Command Channel Cleared", "Couldn't Set The Channel")

    @admin.command(name="cooldown", description="How long members wait between role changes (0 = off)")
    @command_meta(section="Customization", name="Lunar Admin Cooldown")
    @app_commands.describe(seconds="Seconds between changes, 0 to 86400 (0 turns it off)")
    async def admin_cooldown(self, interaction: discord.Interaction,
                             seconds: app_commands.Range[int, 0, service.MAX_COOLDOWN_SECONDS]):
        await interaction.response.defer(ephemeral=True)
        result = await service.set_cooldown(interaction.guild, seconds)
        await _reply(interaction, result, "Cooldown Set", "Couldn't Set The Cooldown")

    @admin.command(name="list", description="List every custom role: owner, role and status")
    @command_meta(section="Customization", name="Lunar Admin List")
    @app_commands.describe(status="Only show roles with this status (default: all)")
    @app_commands.choices(status=[
        app_commands.Choice(name="active", value=storage.STATUS_ACTIVE),
        app_commands.Choice(name="saved", value=storage.STATUS_SAVED),
        app_commands.Choice(name="missing", value=storage.STATUS_MISSING),
    ])
    async def admin_list(self, interaction: discord.Interaction, status: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer(ephemeral=True)
        entries = await service.list_entries(interaction.guild, status.value if status else None)
        title = f"Lunar Roles · {status.name}" if status else "Lunar Roles"
        view = ListView(interaction.user.id, entries, title)
        if view.pages == 1:
            await interaction.followup.send(embed=view.build_embed(), ephemeral=True)
            return
        view.message = await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True, wait=True)

    @admin.command(name="remove", description="Delete a member's custom role and its saved settings (moderation)")
    @command_meta(section="Customization", name="Lunar Admin Remove")
    @app_commands.describe(
        user="Whose custom role to delete (works for members who left, too)",
        reason="Optional. If given, the member gets a DM with this reason; if not, they aren't told",
    )
    async def admin_remove(self, interaction: discord.Interaction, user: discord.User,
                           reason: Optional[app_commands.Range[str, 1, 300]] = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        record = await storage.get_custom_role(guild.id, user.id)
        if record is None:
            await interaction.followup.send(embed=build_error_embed("No Role", f"{user.mention} doesn't have a Lunar role."), ephemeral=True)
            return
        role = guild.get_role(record.role_id) if record.role_id else None
        shown = role.mention if role else validation.code(record.name or "unnamed")
        told = f"They'll get a DM with the reason:\n> {reason}" if reason else "No reason given, so they won't be told."

        async def on_confirm(button_interaction: discord.Interaction):
            result = await service.admin_remove(guild, user, interaction.user, reason)
            embed = (build_success_embed("Role Removed", result.message) if result.ok
                     else build_error_embed("Couldn't Remove That Role", result.message))
            await button_interaction.edit_original_response(embed=embed)

        view = ConfirmView(interaction.user.id, on_confirm)
        view.message = await interaction.followup.send(
            embed=build_warning_embed(
                "Confirm Removal",
                f"Delete {user.mention}'s custom role {shown} ({STATUS_LABELS.get(record.status, record.status).lower()})? "
                "Its saved settings are deleted too, so this role won't come back if they qualify again "
                f"(they could still make a new one).\n\n{told}\n\n"
                "This prompt expires in 60 seconds.",
            ),
            view=view, ephemeral=True, wait=True,
        )

    @admin.command(name="pending", description="See and confirm or cancel a removal waiting for approval")
    @command_meta(section="Customization", name="Lunar Admin Pending")
    async def admin_pending(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pending = await storage.get_open_pending(interaction.guild.id)
        if pending is None:
            await interaction.followup.send(embed=build_info_embed("Nothing Pending", "No removals are waiting for approval."), ephemeral=True)
            return
        text = service.pending_text(pending, service.mass_archive_threshold())
        await interaction.followup.send(
            embed=_embed("Removal Waiting For Approval", text, PALETTE.WARNING), view=_pending_view(pending.id), ephemeral=True
        )

    @allow_role.command(name="add", description="Let members with this role use Lunar Roles (besides boosters)")
    @command_meta(section="Customization", name="Lunar Admin Allow Role Add")
    @app_commands.describe(role="Members with this role can use Lunar Roles")
    async def admin_allow_role_add(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        result = await service.add_allowed_role(interaction.guild, role)
        if result.ok:
            restored = await service.restore_saved(interaction.guild)
            if restored:
                result.message += f"\n\nRestored {restored} saved role(s) for members who qualify again."
        await _reply(interaction, result, "Role Allowed", "Couldn't Add That Role")

    @allow_role.command(name="remove", description="Stop a role from granting Lunar Roles access")
    @command_meta(section="Customization", name="Lunar Admin Allow Role Remove")
    @app_commands.describe(role="Role to remove from the allowed list")
    async def admin_allow_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        settings = await storage.get_guild_settings(guild.id)
        if role.id not in settings.allowed_role_ids:
            await _reply(interaction, await service.remove_allowed_role(guild, role), "Role Removed", "Couldn't Remove That Role")
            return
        affected = await service.preview_allowed_role_removal(guild, role)
        threshold = service.mass_archive_threshold()
        if len(affected) <= threshold:
            await self._remove_allowed_role(interaction, role, affected, from_button=False)
            return

        async def on_confirm(button_interaction: discord.Interaction):
            await self._remove_allowed_role(button_interaction, role, affected, from_button=True)

        view = ConfirmView(interaction.user.id, on_confirm)
        view.message = await interaction.followup.send(
            embed=build_warning_embed(
                "Confirm Mass Removal",
                f"Removing {role.mention} from the allowed list will remove **{len(affected)} custom role(s)** "
                f"(more than the safety limit of {threshold}). Their settings are saved, so the roles come back "
                "if they qualify again.\n\nThis prompt expires in 60 seconds.",
            ),
            view=view, ephemeral=True, wait=True,
        )

    async def _remove_allowed_role(self, interaction: discord.Interaction, role: discord.Role,
                                   affected: list, from_button: bool):
        guild = interaction.guild
        result = await service.remove_allowed_role(guild, role)
        if not result.ok:
            embed = build_error_embed("Couldn't Remove That Role", result.message)
            if from_button:
                await interaction.edit_original_response(embed=embed)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
            return

        async def progress(done: int, total: int, report: service.ArchiveReport):
            if from_button:
                await interaction.edit_original_response(
                    embed=_embed("Removing…", f"{done}/{total} processed. {report.summary()}", PALETTE.WARNING)
                )

        report = await service.process_archives(
            guild, {u: f"allowed role {role.name!r} removed" for u in affected},
            progress=progress, log_title=f"Allowed role {role.name} removed by {interaction.user}",
        )
        embed = _report_embed("Role Removed", report, intro=result.message) if affected else build_success_embed("Role Removed", result.message)
        if from_button:
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

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

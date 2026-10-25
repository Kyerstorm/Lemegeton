"""Custom Roles: custom booster roles (the /custom-role and /custom-role-admin panels). Logic lives in helpers/custom_roles."""
import asyncio
import hashlib
import io
import logging
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from cogs_test.general_commands.dashboard import command_meta
from helpers.color_palette import PALETTE
from helpers.embed_helper import build_error_embed, build_info_embed, build_success_embed, build_warning_embed
from helpers.command_error_handler import FEEDBACK_ERROR_GUIDANCE
from helpers.custom_roles import ADMIN_GROUP, COMMAND_GROUP, ROLE_LIMIT
from helpers.custom_roles import images, service, storage, tokens, validation

logger = service.logger  # file log (logs/custom_roles.log)
console_logger = logging.getLogger("custom_roles_console")  # propagates to the bot's console output
console_logger.setLevel(logging.INFO)  # refusals and slow-database notes reach the console too

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


def log_panel_error(what: str, interaction: discord.Interaction, error: BaseException) -> None:
    """A panel failure: to the console (what Railway's log view shows) and to logs/custom_roles.log."""
    guild_id = getattr(interaction, "guild_id", None) or getattr(getattr(interaction, "guild", None), "id", None)
    user_id = getattr(getattr(interaction, "user", None), "id", None)
    for log in (logger, console_logger):
        log.error("Custom Roles %s failed in guild %s for user %s: %r", what, guild_id, user_id, error,
                  exc_info=(type(error), error, error.__traceback__))


def log_panel_note(level: int, message: str, *args) -> None:
    """Something an admin should be able to see on Railway (a refusal, a slow database): console and file."""
    for log in (logger, console_logger):
        log.log(level, "Custom Roles: " + message, *args)


async def _send_error(interaction: discord.Interaction):
    embed = build_error_embed("Something went wrong", FEEDBACK_ERROR_GUIDANCE)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.HTTPException as exc:  # the interaction may have expired too; the error is logged anyway
        log_panel_note(logging.WARNING, "couldn't tell user %s about an error: %r",
                       getattr(interaction.user, "id", None), exc)


class LoggedView(discord.ui.View):
    """A View whose errors are logged (console and file) and answered, instead of only discord.py's log line."""

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        log_panel_error(f"{type(self).__name__} {getattr(item, 'label', None) or type(item).__name__!r}",
                        interaction, error)
        await _send_error(interaction)


def _progress_updater(interaction: discord.Interaction, title: str) -> service.ProgressCallback:
    """Shows "done/total" on the interaction's message. Never raises: the message may be gone
    or the interaction token expired (15 min), and that must not stop the removal."""
    async def progress(done: int, total: int, report: service.ArchiveReport):
        try:
            await interaction.edit_original_response(
                embed=_embed(title, f"{done}/{total} processed. {report.summary()}", PALETTE.WARNING)
            )
        except discord.HTTPException as exc:
            logger.warning("Couldn't show progress %s/%s in guild %s: %s", done, total, interaction.guild_id, exc)
    return progress


class PendingButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"custom-role:pending:(?P<id>[0-9]+):(?P<action>confirm|cancel)",
):
    """Confirm/Cancel for a saved pending removal. Persistent: works after restarts."""

    def __init__(self, pending_id: int, action: str):
        confirm = action == "confirm"
        super().__init__(discord.ui.Button(
            label="Confirm removal" if confirm else "Cancel (keep roles)",
            style=discord.ButtonStyle.danger if confirm else discord.ButtonStyle.secondary,
            custom_id=f"custom-role:pending:{pending_id}:{action}",
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
        try:
            await self._run(interaction)
        except Exception as exc:
            log_panel_error(f"pending removal {self.action}", interaction, exc)
            await _send_error(interaction)

    async def _run(self, interaction: discord.Interaction):
        guild = interaction.guild
        if self.action == "cancel":
            await interaction.response.edit_message(embed=_embed("Cancelling…", "One moment.", PALETTE.NEUTRAL), view=None)
            result = await service.cancel_pending(guild, self.pending_id, interaction.user)
            title = "Removal Cancelled" if result.ok else "Nothing To Do"
            await interaction.edit_original_response(embed=_embed(title, result.message, PALETTE.NEUTRAL), view=None)
            return

        await interaction.response.edit_message(embed=_embed("Removing…", "Starting.", PALETTE.WARNING), view=None)

        progress = _progress_updater(interaction, "Removing…")
        result = await service.confirm_pending(guild, self.pending_id, interaction.user, progress=progress)
        if not result.ok:
            await interaction.edit_original_response(embed=_embed("Nothing To Do", result.message, PALETTE.NEUTRAL))
            return
        await interaction.edit_original_response(embed=_report_embed("Removal Confirmed", result.data))


def _pending_view(pending_id: int) -> discord.ui.View:
    view = LoggedView(timeout=None)
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


class ConfirmView(LoggedView):
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


LEGACY_TIMEOUT = 120  # seconds the import-legacy preview buttons stay usable


class LegacyImportView(LoggedView):
    """Buttons under the Import old roles preview; only the admin who opened it can press."""

    def __init__(self, invoker_id: int, plan: service.LegacyPlan, on_choice):
        super().__init__(timeout=LEGACY_TIMEOUT)
        self.invoker_id = invoker_id
        self.on_choice = on_choice  # async (interaction, archive_others: bool)
        self.message: Optional[discord.WebhookMessage] = None
        self.finished = False
        taking, others = len(plan.take_over), len(plan.not_qualifying)
        if taking:
            self._add(f"Take over {taking}", discord.ButtonStyle.success, archive=False)
        if others:
            label = f"Take over {taking} and archive {others}" if taking else f"Archive {others}"
            self._add(label, discord.ButtonStyle.danger, archive=True)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self._cancel
        self.add_item(cancel)

    def _add(self, label: str, style: discord.ButtonStyle, archive: bool):
        button = discord.ui.Button(label=label, style=style)

        async def callback(interaction: discord.Interaction):
            self.finished = True
            self.stop()
            await interaction.response.edit_message(embed=_embed("Working…", "Starting.", PALETTE.WARNING), view=None)
            await self.on_choice(interaction, archive)

        button.callback = callback
        self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("Only the admin who ran the command can answer this.", ephemeral=True)
            return False
        return True

    async def _cancel(self, interaction: discord.Interaction):
        self.finished = True
        self.stop()
        await interaction.response.edit_message(embed=_embed("Cancelled", "Nothing was changed.", PALETTE.NEUTRAL), view=None)

    async def on_timeout(self):
        if self.finished or self.message is None:
            return
        try:
            await self.message.edit(embed=_embed("Timed Out", f"No answer within {LEGACY_TIMEOUT // 60} minutes, "
                                                              "so nothing was changed.", PALETTE.NEUTRAL), view=None)
        except discord.HTTPException:
            pass


def _legacy_lines(entries, line, limit: int = 15) -> str:
    lines = [line(e) for e in entries[:limit]]
    if len(entries) > limit:
        lines.append(f"…and {len(entries) - limit} more")
    return "\n".join(lines)


def legacy_preview_text(plan: service.LegacyPlan) -> str:
    """The import-legacy preview: what will be taken over, who doesn't qualify, what's skipped."""
    old = f"`{service.LEGACY_COMMAND}`"
    parts = [f"Found **{plan.total}** old {old} role(s) in this server."]
    if plan.take_over:
        parts.append(
            f"**Will be taken over ({len(plan.take_over)})**: they become these members' custom roles. "
            "Name, color and position stay the same, and no new roles are made.\n"
            + _legacy_lines(plan.take_over, lambda e: f"<@{e.user_id}> → {e.role.mention}")
        )
    if plan.not_qualifying:
        parts.append(
            f"**Members who don't qualify ({len(plan.not_qualifying)})**: their roles stay untouched unless you "
            "pick **archive**. Archiving deletes the role from Discord and saves its settings, so it comes back "
            "if they qualify again.\n"
            + _legacy_lines(plan.not_qualifying, lambda e: f"<@{e.user_id}> → {e.role.mention} ({e.reason})")
        )
    if plan.skipped:
        parts.append(
            f"**Skipped ({len(plan.skipped)})**: left exactly as they are.\n"
            + _legacy_lines(plan.skipped, lambda e: f"<@{e.user_id}>: {e.reason}")
        )
    if not plan.take_over and not plan.not_qualifying:
        parts.append("Nothing to import.")
    else:
        parts.append(f"Nothing is deleted from the old {old} records. "
                     f"These buttons expire in {LEGACY_TIMEOUT // 60} minutes.")
    text = "\n\n".join(parts)
    return text if len(text) <= 4000 else text[:3990] + "\n…"


PREVIEW_TIMEOUT = 300  # seconds the Apply/Cancel buttons under a color preview stay usable
PREVIEW_FILE = "color-preview.png"


def preview_colors(mode: str, primary: Optional[int], secondary: Optional[int]) -> list:
    """The colors Discord blends on a name for this style."""
    if mode == service.MODE_HOLOGRAPHIC:
        return list(service.HOLOGRAPHIC_COLORS)
    if mode == service.MODE_GRADIENT:
        return [primary, secondary]
    return [primary]


def color_preview_embed(mode: str, colors: list) -> discord.Embed:
    shown = ("Discord's holographic preset" if mode == service.MODE_HOLOGRAPHIC
             else " → ".join(f"`{validation.format_hex(c)}`" for c in colors))
    embed = build_info_embed(
        "Color Preview",
        f"**{MODE_LABELS.get(mode, mode)}:** {shown}\n\n"
        "This is how your name will look. Nothing has changed yet: press **Apply** to use it.",
    )
    embed.colour = discord.Colour(colors[0])
    embed.set_image(url=f"attachment://{PREVIEW_FILE}")
    hard = [theme for theme, background in (("dark", images.DARK_THEME), ("light", images.LIGHT_THEME))
            if min(images.contrast_ratio(c, background) for c in colors) < images.LOW_CONTRAST]
    if hard:
        embed.add_field(name="⚠️ Heads up", inline=False,
                        value=f"This may be hard to read on Discord's {' and '.join(hard)} theme.")
    return embed


class ColorPreviewView(LoggedView):
    """Apply/Cancel under a color preview from the panel's Color form. Only the member who filled it in can press."""

    def __init__(self, owner_id: int, mode: str, primary: Optional[int], secondary: Optional[int], on_done):
        super().__init__(timeout=PREVIEW_TIMEOUT)
        self.owner_id = owner_id
        self.mode, self.primary, self.secondary = mode, primary, secondary
        self.on_done = on_done  # async (Result): shows the outcome on the panel too
        self.message: Optional[discord.WebhookMessage] = None
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                f"This preview belongs to someone else. Run `/{COMMAND_GROUP}` and press **Color** to get your own.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.success)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finished = True
        self.stop()
        await interaction.response.defer()
        result = await service.set_colors(interaction.user, self.mode, self.primary, self.secondary)
        embed = (build_success_embed("Color Applied", result.message) if result.ok
                 else build_error_embed("Couldn't Change The Color", result.message))
        await interaction.edit_original_response(embed=embed, view=None, attachments=[])
        await self.on_done(result)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finished = True
        self.stop()
        await interaction.response.edit_message(embed=_embed("Cancelled", "Nothing was changed.", PALETTE.NEUTRAL),
                                                view=None, attachments=[])

    async def on_timeout(self):
        if self.finished or self.message is None:
            return
        try:
            await self.message.edit(embed=_embed("Preview Expired", "Nothing was changed. Press **Color** on the panel "
                                                 "to try again.", PALETTE.NEUTRAL), view=None, attachments=[])
        except discord.HTTPException:
            pass


PALETTE_TIMEOUT = 300  # seconds the palette menus stay usable
CLEAR_SECONDARY = "clear"


class PaletteView(LoggedView):
    """Two select menus from the panel's Palette button. Only the member who ran it can use them."""

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
                f"This palette belongs to someone else. Run `/{COMMAND_GROUP}` and press **Palette** to get your own.", ephemeral=True
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
            lines += ["", f"⏱️ This palette expired. Press **Palette** in `/{COMMAND_GROUP}` again."]
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
LIST_ALL = "all"

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


class ListView(LoggedView):
    """Previous/Next pages (and a status filter) for the admin panel's Members button. Only that admin can use them."""

    def __init__(self, invoker_id: int, entries: list, title: str, guild: Optional[discord.Guild] = None):
        super().__init__(timeout=LIST_TIMEOUT)
        self.invoker_id = invoker_id
        self.entries = entries
        self.title = title
        self.base_title = title
        self.guild = guild
        self.page = 0
        self.pages = max(1, -(-len(entries) // LIST_PAGE_SIZE))
        self.message: Optional[discord.WebhookMessage] = None
        if guild is not None:  # filter by status (fetches the list again)
            self.status_select = discord.ui.Select(placeholder="Show: all", row=1, options=[
                discord.SelectOption(label="All", value=LIST_ALL, default=True),
                *(discord.SelectOption(label=label, value=status) for status, label in STATUS_LABELS.items()),
            ])
            self.status_select.callback = self._on_status
            self.add_item(self.status_select)
        self._update_buttons()

    async def _on_status(self, interaction: discord.Interaction):
        value = self.status_select.values[0]
        status = None if value == LIST_ALL else value
        self.entries = await service.list_entries(self.guild, status)
        self.title = f"{self.base_title} · {STATUS_LABELS[status].lower()}" if status else self.base_title
        self.page = 0
        self.pages = max(1, -(-len(self.entries) // LIST_PAGE_SIZE))
        for option in self.status_select.options:
            option.default = option.value == value
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                f"Press **Members** in `/{ADMIN_GROUP}` to get your own list.", ephemeral=True
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
            body += f"\n\n⏱️ These buttons expired. Press **Members** in `/{ADMIN_GROUP}` again."
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


# ============================================================================
# PANELS: /custom-role (members) and /custom-role-admin (admins)
# ============================================================================

PANEL_TTL = 15 * 60  # seconds; Discord's interaction limit, so a panel stops working after this
PANEL_MEMBER = "me"
PANEL_ADMIN = "admin"
MEMBER_TITLE = "Your Custom Role"
ADMIN_TITLE = "Custom Roles Settings"
COLOR_FORM_TIP = "To pick a color by eye, press **Color picker** on the panel."
ICON_FORM_TIP = "To crop an image precisely, press **Color picker** on the panel."
HEX_HELP = "Try `#FF66AA`, `FF66AA` or `#F6A`."
FORM_READ_TIMEOUT = 2.0  # seconds for the database read before a form opens; Discord gives up after 3
SLOW_DB_MESSAGE = "The database is slow right now, so I couldn't open that. Please try again in a moment."
SETUP_MARKS = {service.SETUP_DONE: "✅", service.SETUP_TODO: "❌", service.SETUP_OPTIONAL: "➖"}
BLOCKED_WORD_MAX = 50


def panel_expired_text(panel: str) -> str:
    return f"This panel expired, run `/{COMMAND_GROUP if panel == PANEL_MEMBER else ADMIN_GROUP}` again."


def _expiry_line(opened_at: int) -> str:
    return f"⏱️ This panel expires <t:{opened_at + PANEL_TTL}:R>."


async def _send(interaction: discord.Interaction, embed: discord.Embed, view: Optional[discord.ui.View] = None):
    if view is None:
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


def _with_result(embed: discord.Embed, result: Optional[service.Result]) -> discord.Embed:
    """Show the outcome of the last change at the top of a panel."""
    if result is None:
        return embed
    line = ("✅ " if result.ok else "❌ ") + result.message
    embed.description = f"{line}\n\n{embed.description or ''}"[:4000]
    if result.notes:
        embed.add_field(name="⚠️ Heads up", value="\n\n".join(result.notes)[:1024], inline=False)
    return embed


class SlowDatabase(Exception):
    """The read before a form timed out; the member was already told to try again."""


async def read_before_reply(interaction: discord.Interaction, read, what: str):
    """Run a database read that has to finish before the first reply (a form, or the channel check).

    Discord gives up on an interaction after 3 seconds, so a slow database gets "Try again" instead
    of "This interaction failed". Raises SlowDatabase after replying.
    """
    try:
        return await asyncio.wait_for(read, FORM_READ_TIMEOUT)
    except asyncio.TimeoutError:
        log_panel_note(logging.WARNING, "database too slow (over %ss) before %s in guild %s for user %s",
                       FORM_READ_TIMEOUT, what, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=build_error_embed("Try Again", SLOW_DB_MESSAGE), ephemeral=True)
        raise SlowDatabase(what) from None


async def send_refusal(interaction: discord.Interaction, title: str, result: Optional[service.Result]) -> None:
    """A short ❌ reply under the admin panel when an action was refused, so it can't be missed.
    The panel shows the same line at the top."""
    if result is None or result.ok:
        return
    log_panel_note(logging.INFO, "admin %s in guild %s: %s refused: %s",
                   interaction.user.id, interaction.guild_id, title, result.message.replace("\n", " "))
    try:
        await interaction.followup.send(embed=build_error_embed(title, result.message[:4000]), ephemeral=True)
    except discord.HTTPException as exc:
        log_panel_note(logging.WARNING, "couldn't send the refusal reply to %s: %r", interaction.user.id, exc)


def setup_checklist_text(guild: discord.Guild, settings: storage.GuildSettings) -> str:
    return "\n".join(f"{SETUP_MARKS[status]} {text}" for status, text in service.setup_checklist(guild, settings))


def _combined(lines: list, empty: str = "Nothing changed.") -> service.Result:
    """One Result for a form that made several changes: lines are (ok, message)."""
    if not lines:
        return service.Result(True, empty)
    if len(lines) == 1:
        return service.Result(*lines[0])
    return service.Result(all(ok for ok, _ in lines), "\n".join(f"• {text}" for _, text in lines))


class PanelButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"custom-role:panel:(?P<panel>me|admin):(?P<action>[a-z-]+):(?P<owner>[0-9]+):(?P<at>[0-9]+)",
):
    """A button on a /custom-role or /custom-role-admin panel.

    Persistent (like PendingButton), so a press after the panel expired, or after a restart, still gets an
    answer instead of Discord's "This interaction failed".
    """

    def __init__(self, panel: str, action: str, owner_id: int, opened_at: int, label: str = "…",
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary, row: Optional[int] = None):
        super().__init__(discord.ui.Button(
            label=label, style=style, row=row,
            custom_id=f"custom-role:panel:{panel}:{action}:{owner_id}:{opened_at}",
        ))
        self.panel = panel
        self.action = action
        self.owner_id = owner_id
        self.opened_at = opened_at

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(match["panel"], match["action"], int(match["owner"]), int(match["at"]), label=item.label or "…")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            return await self._check(interaction)
        except Exception as exc:
            log_panel_error(f"panel button {self.panel}/{self.action} check", interaction, exc)
            await _send_error(interaction)
            return False

    async def _check(self, interaction: discord.Interaction) -> bool:
        if time.time() > self.opened_at + PANEL_TTL:
            await interaction.response.edit_message(
                embed=_embed("Panel Expired", panel_expired_text(self.panel), PALETTE.NEUTRAL), view=None
            )
            return False
        command = COMMAND_GROUP if self.panel == PANEL_MEMBER else ADMIN_GROUP
        if interaction.guild is None or interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                f"This panel belongs to someone else. Run `/{command}` to get your own.", ephemeral=True
            )
            return False
        perms = getattr(interaction.user, "guild_permissions", None)
        if self.panel == PANEL_ADMIN and (perms is None or not perms.manage_roles):
            await interaction.response.send_message("Only members with **Manage Roles** can do this.", ephemeral=True)
            return False
        return True

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("CustomRoles")
        if cog is None:
            await interaction.response.send_message("Custom Roles isn't running right now. Try again in a minute.",
                                                    ephemeral=True)
            return
        try:
            await cog.panel_action(interaction, self)
        except SlowDatabase:
            pass  # already answered with "Try again" and logged
        except Exception as exc:
            log_panel_error(f"panel button {self.panel}/{self.action}", interaction, exc)
            await _send_error(interaction)


def _panel_view(panel: str, owner_id: int, opened_at: int, buttons: list) -> discord.ui.View:
    """buttons: (action, label, style, row)."""
    view = LoggedView(timeout=PANEL_TTL)
    for action, label, style, row in buttons:
        view.add_item(PanelButton(panel, action, owner_id, opened_at, label=label, style=style, row=row))
    return view


class PanelModal(discord.ui.Modal):
    """A form opened from a panel button; `handler(interaction, modal)` does the work."""

    def __init__(self, title: str, handler):
        super().__init__(title=title, timeout=PANEL_TTL)
        self.handler = handler

    def field(self, text: str, component, description: Optional[str] = None):
        self.add_item(discord.ui.Label(text=text, component=component, description=description))
        return component

    async def on_submit(self, interaction: discord.Interaction):
        await self.handler(interaction, self)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item=None):
        log_panel_error(f"panel form {self.title!r}", interaction, error)
        await _send_error(interaction)


def role_embed(title: str, record: storage.CustomRole, role: Optional[discord.Role], description: str) -> discord.Embed:
    """A custom role's name, style, colors, icon and status."""
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

    embed = build_info_embed(title, description)
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
    return embed


def _role_shown(record: storage.CustomRole, role: Optional[discord.Role]) -> str:
    return role.mention if role else f"**{discord.utils.escape_markdown(record.name or 'Unnamed')}**"


async def member_panel(member: discord.Member, opened_at: int, result: Optional[service.Result] = None):
    """The /custom-role panel: (embed, view or None)."""
    error = await service.precheck(member, need_role=False)
    if error is not None:
        embed = build_error_embed(MEMBER_TITLE, error.message)
        if result is not None and result.message != error.message:
            _with_result(embed, result)
        return embed, None
    style = discord.ButtonStyle
    info = await service.get_info(member, member)
    if not info.ok:
        embed = build_info_embed(
            MEMBER_TITLE,
            "You don't have a custom role yet. Press **Create role** to make one; you can color it and add "
            f"an icon right after.\n{_expiry_line(opened_at)}",
        )
        view = _panel_view(PANEL_MEMBER, member.id, opened_at, [
            ("create", "Create role", style.success, 0),
            ("lookup", "Look up a member", style.secondary, 0),
        ])
        return _with_result(embed, result), view
    record, role = info.data
    embed = role_embed(MEMBER_TITLE, record, role,
                       f"{_role_shown(record, role)}\n\nChange it with the buttons below.\n{_expiry_line(opened_at)}")
    wearing = role is not None and role in member.roles
    view = _panel_view(PANEL_MEMBER, member.id, opened_at, [
        ("rename", "Rename", style.primary, 0),
        ("color", "Color", style.primary, 0),
        ("icon", "Icon", style.primary, 0),
        ("palette", "Palette", style.secondary, 0),
        ("unwear", "Take off", style.secondary, 1) if wearing else ("wear", "Put on", style.success, 1),
        ("move", "Move", style.secondary, 1),
        *([("picker", "Color picker", style.secondary, 1)] if config.CUSTOM_ROLES_PICKER_ENABLED else []),
        ("lookup", "Look up a member", style.secondary, 1),
    ])
    return _with_result(embed, result), view


def parse_color_form(style: Optional[str], primary_text: str, secondary_text: str = "") -> service.Result:
    """Read the Color form without changing anything: data = (mode, primary, secondary).
    style None = solid; solid ignores the second color; holographic needs none."""
    style = style or service.MODE_SOLID
    if style == service.MODE_HOLOGRAPHIC:
        return service.Result(True, "", (service.MODE_HOLOGRAPHIC, None, None))
    primary_text, secondary_text = (primary_text or "").strip(), (secondary_text or "").strip()
    if not primary_text:
        return service.Result(False, f"Type a color. {HEX_HELP}")
    gradient = style == service.MODE_GRADIENT
    if gradient and not secondary_text:
        return service.Result(False, "A gradient needs a second color too.")
    primary = validation.parse_hex(primary_text)
    secondary = validation.parse_hex(secondary_text) if gradient else None
    bad = primary_text if primary is None else (secondary_text if gradient and secondary is None else None)
    if bad is not None:
        return service.Result(False, f"{validation.code(bad)} isn't a hex color. {HEX_HELP}")
    return service.Result(True, "", (style, primary, secondary))


async def apply_color_form(member: discord.Member, style: Optional[str], primary_text: str,
                           secondary_text: str = "") -> service.Result:
    """The Color form applied straight away (the panel previews it first, see ColorPreviewView)."""
    parsed = parse_color_form(style, primary_text, secondary_text)
    if not parsed.ok:
        return parsed
    return await service.set_colors(member, *parsed.data)


async def icon_from_attachment(member: discord.Member, image: discord.Attachment) -> service.Result:
    """Set the role icon from an uploaded image, checking what Discord tells us before downloading it."""
    error = await service.precheck(member)
    if error:
        return error
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
        return service.Result(False, exc.message)
    except discord.HTTPException:
        return service.Result(False, "I couldn't download that image. Please try again.")
    logger.info("Icon upload from %s: downloaded %s bytes, first bytes %s, sha256 %s",
                member.id, len(data), data[:16].hex(" "), hashlib.sha256(data).hexdigest()[:16])
    if len(data) != image.size:
        logger.warning("Icon upload from %s: downloaded %s bytes but Discord reported %s - the file was changed",
                       member.id, len(data), image.size)
    result = await service.set_icon(member, image=data)
    if result.ok and config.CUSTOM_ROLES_PICKER_ENABLED:
        result.message += " Tip: crop it precisely with **Color picker**."
    return result


async def apply_icon_form(member: discord.Member, uploads: list, emoji: str, remove: bool) -> service.Result:
    """The Icon form: exactly one of an uploaded image, an emoji, or "Remove my icon"."""
    emoji = (emoji or "").strip()
    chosen = sum(bool(x) for x in (uploads, emoji, remove))
    if chosen == 0:
        return service.Result(False, "Upload an image, type an emoji, or tick **Remove my icon**.")
    if chosen > 1:
        return service.Result(False, "Pick one: an image, an emoji, **or** Remove my icon.")
    if remove:
        return await service.remove_icon(member)
    if emoji:
        return await service.set_icon(member, emoji=emoji)
    return await icon_from_attachment(member, uploads[0])


async def settings_embed(guild: discord.Guild, settings: Optional[storage.GuildSettings] = None) -> discord.Embed:
    """Everything /custom-role-admin shows: settings, server features, counts and problems."""
    settings = settings or await storage.get_guild_settings(guild.id)
    features = service.feature_status(guild)
    counts = await storage.count_roles_by_status(guild.id)
    problems = service.setup_problems(guild, settings)
    not_imported = (await service.plan_legacy_import(guild, settings)).not_imported
    if not_imported:
        problems.append(f"Old /nitro-role-set roles not imported yet: {not_imported}. Press **Import old roles**.")

    def role_text(role_id):
        role = guild.get_role(role_id) if role_id else None
        return role.mention if role else ("*deleted role*" if role_id else "Not set")

    def channel_text(channel_id, empty):
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel.mention if channel else ("*deleted channel*" if channel_id else empty)

    allowed = [guild.get_role(r) for r in settings.allowed_role_ids]
    allowed_text = ", ".join(r.mention for r in allowed if r) or "None"

    embed = build_info_embed(ADMIN_TITLE, f"Settings for **{guild.name}**")
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
    embed.add_field(name="Extra allowed roles", value=allowed_text[:1024], inline=False)
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
        value="\n".join(f"• {p}" for p in problems)[:1024] if problems else "None",
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
                  "Press **Pending removal** to confirm or cancel.",
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
                "Press **Anchor** and choose **Directly above it** on a higher role, or remove those roles' colors."
            ),
            inline=False,
        )
    return embed


async def admin_panel(guild: discord.Guild, admin_id: int, opened_at: int, result: Optional[service.Result] = None):
    """The /custom-role-admin panel: (embed, view)."""
    settings = await storage.get_guild_settings(guild.id)
    pending = await storage.get_open_pending(guild.id)
    embed = await settings_embed(guild, settings)
    embed.description = f"Settings for **{guild.name}**. Change them with the buttons below.\n{_expiry_line(opened_at)}"
    if not settings.enabled:  # first field, so it's the first thing an admin sees
        embed.insert_field_at(0, name="🛠️ Setup checklist (Custom Roles is off)",
                              value=setup_checklist_text(guild, settings)[:1024], inline=False)
    style = discord.ButtonStyle
    view = _panel_view(PANEL_ADMIN, admin_id, opened_at, [
        ("disable", "Turn off", style.secondary, 0) if settings.enabled else ("enable", "Turn on", style.success, 0),
        ("anchor", "Anchor", style.primary, 0),
        ("log", "Log channel", style.primary, 0),
        ("channel", "Command channel", style.primary, 0),
        ("cooldown", "Cooldown", style.primary, 0),
        ("allowed", "Allowed roles", style.primary, 1),
        ("words", "Blocked words", style.primary, 1),
        ("members", "Members", style.secondary, 1),
        ("remove", "Remove a member", style.danger, 1),
        ("pending", f"Pending removal ({len(pending.user_ids)})" if pending else "Pending removal",
         style.danger if pending else style.secondary, 1),
        ("import", "Import old roles", style.secondary, 2),
        ("refresh", "Refresh", style.secondary, 2),
    ])
    return _with_result(embed, result), view


async def apply_log_channel(guild: discord.Guild, admin: discord.abc.User, channel) -> service.Result:
    """The Log channel form: a text channel, or None to turn logging off."""
    if channel is None:
        await storage.update_guild_settings(guild.id, log_channel_id=None)
        return service.Result(True, "Logging is off: Custom Roles won't post logs anymore.")
    perms = channel.permissions_for(guild.me)
    missing = [name for name, ok in (("View Channel", perms.view_channel), ("Send Messages", perms.send_messages),
                                     ("Embed Links", perms.embed_links)) if not ok]
    if missing:
        return service.Result(False, f"I need {', '.join(f'**{m}**' for m in missing)} in {channel.mention}.")
    settings = await storage.update_guild_settings(guild.id, log_channel_id=channel.id)
    await service.log_event(guild, f"Custom Roles will post events here (set by {admin.mention}).", "success", settings)
    return service.Result(True, f"Logging to {channel.mention}.")


async def apply_cooldown_form(guild: discord.Guild, text: str) -> service.Result:
    text = (text or "").strip()
    if not text.isdigit() or int(text) > service.MAX_COOLDOWN_SECONDS:
        return service.Result(False, f"Type a whole number of seconds from 0 to {service.MAX_COOLDOWN_SECONDS} "
                                     "(0 turns the cooldown off).")
    return await service.set_cooldown(guild, int(text))


def _form_words(text: str) -> list:
    """One word or phrase per line (commas work too), without repeats."""
    words = []
    for part in (text or "").replace(",", "\n").splitlines():
        word = part.strip()
        if word and word.lower() not in (w.lower() for w in words):
            words.append(word)
    return words


def blocked_words_text(settings: storage.GuildSettings) -> str:
    """The current lists, shown at the top of the Blocked words form."""
    def words(items):
        text = ", ".join(validation.code(w) for w in items)
        return text[:1000] + "…" if len(text) > 1000 else (text or "None")

    lines = [
        f"**Built-in** (whole words, leetspeak ignored): {words(service.active_protected_words(settings))}",
        f"**Yours** (blocked anywhere in a name): {words(settings.blocked_words)}",
    ]
    if settings.removed_default_words:
        lines.insert(1, f"**Built-in, switched off:** {words(settings.removed_default_words)}")
    lines.append("Names copying another role, or a moderation role's name, are always refused.")
    return "\n".join(lines)


async def apply_blocked_words_form(guild: discord.Guild, block_text: str, unblock_text: str, sweep) -> service.Result:
    """The Blocked words form. `sweep(guild, why)` renames existing names that now break the rules."""
    to_block, to_unblock = _form_words(block_text), _form_words(unblock_text)
    if not to_block and not to_unblock:
        return service.Result(False, "Type at least one word to block or unblock.")
    lines = []
    blocked_any = False
    for word in to_block:
        if len(word) > BLOCKED_WORD_MAX:
            lines.append((False, f"{validation.code(word[:BLOCKED_WORD_MAX])}… is too long "
                                 f"({BLOCKED_WORD_MAX} characters at most)."))
            continue
        result = await service.add_blocked_word(guild, word)
        lines.append((result.ok, result.message))
        blocked_any = blocked_any or result.ok
    for word in to_unblock:
        result = await service.remove_blocked_word(guild, word)
        lines.append((result.ok, result.message))
    if blocked_any:
        swept = await sweep(guild, "word blocked")
        if swept.renamed:
            shown = ", ".join(f"<@{uid}>: {validation.code(old)} → {validation.code(new)}"
                              for uid, old, new in swept.renamed[:10])
            more = f" and {len(swept.renamed) - 10} more" if len(swept.renamed) > 10 else ""
            lines.append((True, f"Renamed {len(swept.renamed)} existing role(s): {shown}{more}"))
        else:
            lines.append((True, "No existing role names used it."))
        if swept.failed:
            shown = ", ".join(f"<@{uid}> ({why})" for uid, _, why in swept.failed[:10])
            lines.append((False, f"Couldn't rename {len(swept.failed)}: {shown}"))
    return _combined(lines)


class CustomRoles(commands.Cog):
    """Custom booster roles: one personal role per booster."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._first_reconcile = True
        self._debug_warned = False

    async def cog_load(self):
        self.bot.add_dynamic_items(PendingButton, PanelButton)
        service.pending_view_factory = _pending_view
        self._warn_debug_switch_console()
        # Hot reload (cog watcher) after the bot is ready: on_ready won't fire again.
        if self.bot.user is not None and self.bot.is_ready() and not self.reconcile_loop.is_running():
            self.reconcile_loop.start()

    async def cog_unload(self):
        self.reconcile_loop.cancel()
        self.bot.remove_dynamic_items(PendingButton, PanelButton)
        service.pending_view_factory = None

    # (setting name, is it set, is it active, what it does, log-channel text)
    @staticmethod
    def _debug_switches():
        return (
            ("CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH", config.CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH, service.debug_fetch_fail_active(),
             "Reconcile will NOT remove any custom roles while this is set.",
             "the regular check won't remove any custom roles"),
            ("CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS", config.CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS,
             service.debug_preview_enhanced_active(),
             "The color picker shows Gradient/Holographic even without Enhanced Role Styles (3 server boosts; saving is still refused).",
             "the color picker unlocks Gradient and Holographic for previewing (saving them is still refused)"),
            ("CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS", config.CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS,
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
                value=f"Run `/{COMMAND_GROUP}` in the server and press **Create role**. The same panel colors it, "
                      "adds an icon and more.",
                inline=False,
            )
            embed.add_field(
                name="💡 Tips",
                value="• You get **one** custom role per server\n"
                      f"• Change it anytime with `/{COMMAND_GROUP}`\n"
                      "• If you stop boosting, your role is saved and comes back when you boost again",
                inline=False,
            )
        embed.set_footer(text=f"Thank you for supporting {member.guild.name}!")
        await self._dm(member, embed)

    async def _send_access_dm(self, member: discord.Member):
        embed = discord.Embed(
            title="🎨 You can make a custom role",
            description=f"You now have access to custom roles in **{member.guild.name}**.\n"
                        f"Run `/{COMMAND_GROUP}` there and press **Create role** to make yours.",
            color=PALETTE.PRIMARY,
        )
        await self._dm(member, embed)

    @staticmethod
    async def _dm(member: discord.Member, embed: discord.Embed):
        try:
            await member.send(embed=embed)
            logger.info("Sent Custom Role DM to %s in guild %s", member.id, member.guild.id)
        except discord.HTTPException:
            logger.info("Couldn't DM %s (DMs closed)", member.id)

    # ============================================================================
    # RECONCILE (startup + every CUSTOM_ROLES_RECONCILE_MINUTES)
    # ============================================================================

    @tasks.loop(minutes=config.CUSTOM_ROLES_RECONCILE_MINUTES)
    async def reconcile_loop(self):
        why = "startup check" if self._first_reconcile else "regular check"
        self._first_reconcile = False
        try:
            guild_ids = await storage.list_guilds_with_records()
        except Exception:
            logger.exception("Couldn't list guilds for the custom roles reconcile")
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
                    why, len(guild_ids), config.CUSTOM_ROLES_RECONCILE_MINUTES)

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
        """/custom-role (not /custom-role-admin) only works in the command channel, if one is set."""
        command = interaction.command
        root = (getattr(command, "root_parent", None) or command) if command else None
        if root is None or root.name != COMMAND_GROUP or interaction.guild is None:
            return True
        try:
            settings = await read_before_reply(interaction, storage.get_guild_settings(interaction.guild.id),
                                               f"/{COMMAND_GROUP}")
        except SlowDatabase:
            return False  # already answered; cog_app_command_error ignores the CheckFailure
        problem = service.command_channel_problem(interaction.channel, settings)
        if problem is None:
            return True
        await interaction.response.send_message(embed=build_error_embed("Wrong Channel", problem), ephemeral=True)
        return False

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure) and interaction.response.is_done():
            return  # interaction_check already told them where to go
        log_panel_error(f"command /{getattr(interaction.command, 'qualified_name', '?')}", interaction,
                        getattr(error, "original", error))
        await _send_error(interaction)

    # ============================================================================
    # COMMANDS: one panel each
    # ============================================================================

    @app_commands.command(name=COMMAND_GROUP, description="Your custom booster role: create it, style it, wear it")
    @app_commands.guild_only()
    @command_meta(section="Customization", name="Custom Role")
    async def custom_role_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed, view = await member_panel(interaction.user, int(time.time()))
        await _send(interaction, embed, view)

    @app_commands.command(name=ADMIN_GROUP, description="Set up Custom Roles: anchor, channels, allowed roles and more")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @command_meta(section="Customization", name="Custom Role Admin")
    async def custom_role_admin_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed, view = await admin_panel(interaction.guild, interaction.user.id, int(time.time()))
        await _send(interaction, embed, view)

    async def panel_action(self, interaction: discord.Interaction, button: PanelButton):
        """A panel button was pressed (PanelButton already checked expiry and who pressed it)."""
        handlers = {
            PANEL_MEMBER: {
                "create": self._member_create, "rename": self._member_rename, "color": self._member_color,
                "icon": self._member_icon, "palette": self._member_palette, "wear": self._member_wear,
                "unwear": self._member_wear, "move": self._member_move, "picker": self._member_picker,
                "lookup": self._member_lookup,
            },
            PANEL_ADMIN: {
                "enable": self._admin_toggle, "disable": self._admin_toggle, "anchor": self._admin_anchor,
                "log": self._admin_log, "channel": self._admin_channel, "cooldown": self._admin_cooldown,
                "allowed": self._admin_allowed, "words": self._admin_words, "members": self._admin_members,
                "remove": self._admin_remove, "pending": self._admin_pending, "import": self._admin_import,
                "refresh": self._admin_refresh,
            },
        }[button.panel]
        handler = handlers.get(button.action)
        if handler is None:  # a button from an older version of the panel
            await interaction.response.edit_message(
                embed=_embed("Panel Expired", panel_expired_text(button.panel), PALETTE.NEUTRAL), view=None
            )
            return
        await handler(interaction, button)

    async def _refresh_member(self, interaction: discord.Interaction, opened_at: int,
                              result: Optional[service.Result] = None):
        embed, view = await member_panel(interaction.user, opened_at, result)
        await interaction.edit_original_response(embed=embed, view=view)

    async def _refresh_admin(self, interaction: discord.Interaction, opened_at: int,
                             result: Optional[service.Result] = None):
        embed, view = await admin_panel(interaction.guild, interaction.user.id, opened_at, result)
        await interaction.edit_original_response(embed=embed, view=view)

    def _member_form(self, title: str, opened_at: int, work) -> PanelModal:
        """A form whose `work(member, modal) -> Result` changes the role, then the panel shows the outcome."""
        async def handler(interaction: discord.Interaction, modal: PanelModal):
            await interaction.response.defer()
            result = await work(interaction.user, modal)
            await self._refresh_member(interaction, opened_at, result)
        return PanelModal(title, handler)

    def _admin_form(self, title: str, opened_at: int, work, refused: str = "Not Saved") -> PanelModal:
        """A form whose `work(interaction, modal) -> Result` changes a setting, then the panel shows it.
        A refusal also gets its own ❌ reply titled `refused`."""
        async def handler(interaction: discord.Interaction, modal: PanelModal):
            await interaction.response.defer()
            result = await work(interaction, modal)
            await self._refresh_admin(interaction, opened_at, result)
            await send_refusal(interaction, refused, result)
        return PanelModal(title, handler)

    # ---------------------------------------------------------------- member panel buttons

    async def _member_create(self, interaction: discord.Interaction, button: PanelButton):
        modal = self._member_form("Create your role", button.opened_at,
                                  lambda member, form: service.create_role(member, form.name.value))
        modal.name = modal.field("Role name", discord.ui.TextInput(max_length=100, placeholder="My Cool Role"))
        await interaction.response.send_modal(modal)

    async def _member_rename(self, interaction: discord.Interaction, button: PanelButton):
        record = await read_before_reply(
            interaction, storage.get_custom_role(interaction.guild.id, interaction.user.id), "the Rename form")
        modal = self._member_form("Rename your role", button.opened_at,
                                  lambda member, form: service.rename(member, form.name.value))
        modal.name = modal.field("New name", discord.ui.TextInput(
            max_length=100, default=(record.name if record else None) or None))
        await interaction.response.send_modal(modal)

    async def _member_color(self, interaction: discord.Interaction, button: PanelButton):
        member = interaction.user
        record = await read_before_reply(interaction, storage.get_custom_role(member.guild.id, member.id),
                                         "the Color form")
        mode = record.color_mode if record else service.MODE_SOLID
        enhanced = service.feature_status(member.guild).gradient
        primary = (validation.format_hex(record.primary_color)
                   if record and record.primary_color and mode != service.MODE_HOLOGRAPHIC else None)
        secondary = (validation.format_hex(record.secondary_color)
                     if record and record.secondary_color and mode == service.MODE_GRADIENT else None)

        async def handler(submit: discord.Interaction, form: PanelModal):
            await submit.response.defer()
            problem = parse_color_form(form.style.value if form.style else None, form.primary.value,
                                       form.secondary.value if form.secondary else "")
            if problem.ok:
                problem = await self._send_color_preview(submit, button.opened_at, *problem.data)
            if problem is not None:  # shown on the panel, like the other forms
                await self._refresh_member(submit, button.opened_at, problem)

        modal = PanelModal("Color your role", handler)
        modal.style = modal.secondary = None
        if enhanced:
            modal.style = modal.field("Style", discord.ui.RadioGroup(options=[
                discord.RadioGroupOption(label="Solid", value=service.MODE_SOLID, description="One color",
                                         default=mode == service.MODE_SOLID),
                discord.RadioGroupOption(label="Gradient", value=service.MODE_GRADIENT,
                                         description="Fades from the first color to the second",
                                         default=mode == service.MODE_GRADIENT),
                discord.RadioGroupOption(label="Holographic", value=service.MODE_HOLOGRAPHIC,
                                         description="Discord's holographic preset (colors below are ignored)",
                                         default=mode == service.MODE_HOLOGRAPHIC),
            ]))
        modal.primary = modal.field(
            "Primary color (hex)" if enhanced else "Color (hex)",
            discord.ui.TextInput(required=not enhanced, max_length=10, placeholder="#FF66AA", default=primary),
            description="Like #FF66AA, FF66AA or #F6A",
        )
        if enhanced:
            modal.secondary = modal.field(
                "Second color (hex)",
                discord.ui.TextInput(required=False, max_length=10, placeholder="#60A5FA", default=secondary),
                description="Only used when the style is Gradient",
            )
            if config.CUSTOM_ROLES_PICKER_ENABLED:
                modal.add_item(discord.ui.TextDisplay(COLOR_FORM_TIP))
        else:
            tip = f"\n\n{COLOR_FORM_TIP}" if config.CUSTOM_ROLES_PICKER_ENABLED else ""
            modal.add_item(discord.ui.TextDisplay(f"{service.NO_GRADIENT_MESSAGE}{tip}"))
        await interaction.response.send_modal(modal)

    async def _send_color_preview(self, submit: discord.Interaction, opened_at: int, mode: str,
                                  primary: Optional[int], secondary: Optional[int]) -> Optional[service.Result]:
        """Show the picked color on Discord's dark and light themes with Apply/Cancel. Nothing changes
        until Apply. Returns a Result for the panel if it can't be previewed, else None."""
        member = submit.user
        error = await service.precheck(member)
        if error:
            return error
        if mode != service.MODE_SOLID and not service.feature_status(member.guild).gradient:
            return service.Result(False, service.NO_GRADIENT_MESSAGE)
        colors = preview_colors(mode, primary, secondary)
        png = await asyncio.to_thread(images.render_color_preview, member.display_name, colors)

        async def on_done(result: service.Result):
            try:
                await self._refresh_member(submit, opened_at, result)
            except discord.HTTPException:
                pass  # the panel was dismissed or its token ran out; the preview already shows the outcome

        view = ColorPreviewView(member.id, mode, primary, secondary, on_done)
        view.message = await submit.followup.send(
            embed=color_preview_embed(mode, colors), file=discord.File(io.BytesIO(png), filename=PREVIEW_FILE),
            view=view, ephemeral=True, wait=True,
        )
        return None

    async def _member_icon(self, interaction: discord.Interaction, button: PanelButton):
        async def work(member, form):
            return await apply_icon_form(member, form.image.values, form.emoji.value, form.remove.value)

        modal = self._member_form("Role icon", button.opened_at, work)
        modal.image = modal.field(
            "Upload an image", discord.ui.FileUpload(required=False, max_values=1),
            description=f"PNG or JPEG, up to {images.format_size(images.source_max_bytes())}. The center square is used.",
        )
        modal.emoji = modal.field("Or one emoji", discord.ui.TextInput(required=False, max_length=32, placeholder="🎨"),
                                  description="A standard emoji from the emoji picker")
        modal.remove = modal.field("Remove my icon", discord.ui.Checkbox(),
                                   description="Tick this to take your current icon off")
        if config.CUSTOM_ROLES_PICKER_ENABLED:
            modal.add_item(discord.ui.TextDisplay(ICON_FORM_TIP))
        await interaction.response.send_modal(modal)

    async def _member_palette(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user
        error = await service.precheck(member)
        result = error or await service.get_palette(member)
        if not result.ok:
            await _send(interaction, build_error_embed("Can't Show Your Palette", result.message))
            return
        colors = result.data
        swatches = await asyncio.to_thread(images.render_swatches, colors)
        view = PaletteView(member, colors, gradient_ok=service.feature_status(member.guild).gradient)
        view.message = await interaction.followup.send(
            embed=view.build_embed(), file=discord.File(io.BytesIO(swatches), filename="palette.png"),
            view=view, ephemeral=True, wait=True,
        )

    async def _member_wear(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer()
        if button.action == "wear":
            result = await service.assign(interaction.user)
        else:
            result = await service.unassign(interaction.user)
        await self._refresh_member(interaction, button.opened_at, result)

    async def _member_move(self, interaction: discord.Interaction, button: PanelButton):
        async def work(member, form):
            if not form.role.values:
                return service.Result(False, "Pick another member's custom role.")
            return await service.move(member, form.role.values[0], form.place.value or service.PLACE_ABOVE)

        modal = self._member_form("Move your role", button.opened_at, work)
        modal.role = modal.field("Next to whose role?", discord.ui.RoleSelect(required=True,
                                 placeholder="Another member's custom role"))
        modal.place = modal.field("Put mine", discord.ui.RadioGroup(options=[
            discord.RadioGroupOption(label="Directly above it", value=service.PLACE_ABOVE, default=True),
            discord.RadioGroupOption(label="Directly below it", value=service.PLACE_BELOW),
        ]))
        await interaction.response.send_modal(modal)

    async def _member_picker(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._send_picker_link(interaction)

    async def _send_picker_link(self, interaction: discord.Interaction):
        member = interaction.user
        guild = member.guild
        error = await service.precheck(member)
        if error:
            await _send(interaction, build_error_embed("Can't Open The Picker", error.message))
            return
        problem = service.picker_link_problem()
        if problem is None and not getattr(self.bot, "custom_role_picker_ready", False):
            problem = "the web server isn't running (check the bot log for why it didn't start)"
        if problem:
            logger.warning("Color picker link refused in guild %s: %s", guild.id, problem)
            await service.log_event(guild, f"I couldn't give {member.mention} a color picker link: {problem}.", "error")
            await _send(interaction, build_error_embed("Can't Open The Picker", service.PICKER_UNAVAILABLE_MESSAGE))
            return

        token, link = tokens.create(guild.id, member.id)
        url = service.picker_url(token)
        latest = int(link.max_expires_at)
        embed = build_info_embed(
            "Your Color Picker",
            f"This private link stays open while you use it. It closes after "
            f"**{service.format_duration(int(link.idle_ttl))}** without use, and at <t:{latest}:t> "
            f"(<t:{latest}:R>) at the latest.\n\n"
            "Pressing **Color picker** again gives you a new link and stops this one. "
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

    async def _member_lookup(self, interaction: discord.Interaction, button: PanelButton):
        async def handler(submit: discord.Interaction, form: PanelModal):
            await submit.response.defer(ephemeral=True, thinking=True)
            target = form.user.values[0] if form.user.values else None
            if target is None or getattr(target, "guild", None) is None:
                await _send(submit, build_error_embed("No Role", "That member isn't in this server."))
                return
            result = await service.get_info(submit.user, target)
            if not result.ok:
                await _send(submit, build_error_embed("No Role", result.message))
                return
            record, role = result.data
            await _send(submit, role_embed(f"{target.display_name}'s Custom Role", record, role,
                                           _role_shown(record, role)))

        modal = PanelModal("Look up a member's role", handler)
        modal.user = modal.field("Member", discord.ui.UserSelect(required=True, placeholder="Whose role to show"))
        await interaction.response.send_modal(modal)

    # ---------------------------------------------------------------- admin panel buttons

    async def _admin_toggle(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer()
        guild = interaction.guild
        enable = button.action == "enable"
        result = await service.set_enabled(guild, enable)
        if result.ok and enable:
            restored = await service.restore_saved(guild)
            if restored:
                result.message += f" Restored {restored} saved role(s) for members who qualify again."
        elif result.ok:
            result.message += " Existing roles are kept, and nothing is removed automatically while it's off."
        await self._refresh_admin(interaction, button.opened_at, result)
        await send_refusal(interaction, "Can't Turn It On Yet" if enable else "Can't Turn It Off", result)

    async def _admin_anchor(self, interaction: discord.Interaction, button: PanelButton):
        guild = interaction.guild
        settings = await read_before_reply(interaction, storage.get_guild_settings(guild.id), "the Anchor form")
        current = guild.get_role(settings.anchor_role_id) if settings.anchor_role_id else None
        place = settings.anchor_place if settings.anchor_role_id else service.PLACE_BELOW

        async def work(submit, form):
            if not form.role.values:
                return service.Result(False, "Pick an anchor role.")
            result = await service.set_anchor(guild, form.role.values[0], form.place.value or service.PLACE_BELOW)
            if result.ok:
                result.message += " Existing custom roles aren't moved; only new ones are placed by the anchor."
                if not result.data.enabled:
                    result.message += " Next: press **Turn on**."
            return result

        modal = self._admin_form("Anchor role", button.opened_at, work, refused="Anchor Not Set")
        modal.role = modal.field("Anchor role", discord.ui.RoleSelect(
            required=True, default_values=[discord.Object(current.id, type=discord.Role)] if current else []),
            description="New custom roles go next to it. It must be below my highest role.")
        modal.place = modal.field("Place new roles", discord.ui.RadioGroup(options=[
            discord.RadioGroupOption(label="Directly above it", value=service.PLACE_ABOVE,
                                     description="Recommended: put the anchor just below the colored roles",
                                     default=place == service.PLACE_ABOVE),
            discord.RadioGroupOption(label="Directly below it", value=service.PLACE_BELOW,
                                     default=place == service.PLACE_BELOW),
        ]))
        await interaction.response.send_modal(modal)

    def _channel_form(self, guild: discord.Guild, title: str, label: str, description: str, opened_at: int,
                      current_id, work):
        """A form with one optional text channel select; `work(submit, channel or None)`."""
        async def form_work(submit, form):
            picked = form.channel.values
            channel = submit.guild.get_channel(picked[0].id) if picked else None
            return await work(submit, channel)

        current = guild.get_channel(current_id) if current_id else None
        modal = self._admin_form(title, opened_at, form_work)
        modal.channel = modal.field(label, discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text], required=False, min_values=0, max_values=1,
            default_values=[discord.Object(current.id, type=discord.TextChannel)] if current else []),
            description=description)
        return modal

    async def _admin_log(self, interaction: discord.Interaction, button: PanelButton):
        settings = await read_before_reply(interaction, storage.get_guild_settings(interaction.guild.id),
                                           "the Log channel form")
        modal = self._channel_form(
            interaction.guild, "Log channel", "Log channel", "Where Custom Roles posts events and errors. Leave it empty to turn logging off.",
            button.opened_at, settings.log_channel_id,
            lambda submit, channel: apply_log_channel(submit.guild, submit.user, channel),
        )
        await interaction.response.send_modal(modal)

    async def _admin_channel(self, interaction: discord.Interaction, button: PanelButton):
        settings = await read_before_reply(interaction, storage.get_guild_settings(interaction.guild.id),
                                           "the Command channel form")
        modal = self._channel_form(
            interaction.guild, "Command channel", "Command channel",
            f"/{COMMAND_GROUP} only works there (and in its threads). Leave it empty to allow any channel.",
            button.opened_at, settings.command_channel_id,
            lambda submit, channel: service.set_command_channel(submit.guild, channel),
        )
        await interaction.response.send_modal(modal)

    async def _admin_cooldown(self, interaction: discord.Interaction, button: PanelButton):
        settings = await read_before_reply(interaction, storage.get_guild_settings(interaction.guild.id),
                                           "the Cooldown form")
        modal = self._admin_form("Cooldown", button.opened_at,
                                 lambda submit, form: apply_cooldown_form(submit.guild, form.seconds.value))
        modal.seconds = modal.field("Seconds between changes", discord.ui.TextInput(
            max_length=5, default=str(settings.cooldown_seconds)),
            description=f"0 to {service.MAX_COOLDOWN_SECONDS} (a day). 0 turns it off. "
                        "Covers renames, colors, icons and moves.")
        await interaction.response.send_modal(modal)

    async def _admin_allowed(self, interaction: discord.Interaction, button: PanelButton):
        guild = interaction.guild
        settings = await read_before_reply(interaction, storage.get_guild_settings(guild.id), "the Allowed roles form")
        current = [r for r in (guild.get_role(rid) for rid in settings.allowed_role_ids) if r]
        modal = self._admin_form("Allowed roles", button.opened_at, self._apply_allowed_roles)
        modal.roles = modal.field("Roles that can use Custom Roles", discord.ui.RoleSelect(
            required=False, min_values=0, max_values=25,
            default_values=[discord.Object(r.id, type=discord.Role) for r in current[:25]]),
            description="Besides boosters. Leave it empty for boosters only.")
        await interaction.response.send_modal(modal)

    async def _apply_allowed_roles(self, interaction: discord.Interaction, form: PanelModal) -> service.Result:
        guild = interaction.guild
        settings = await storage.get_guild_settings(guild.id)
        chosen = {role.id for role in form.roles.values}
        adds = [r for r in (guild.get_role(rid) for rid in chosen if rid not in settings.allowed_role_ids) if r]
        removes = [r for r in (guild.get_role(rid) for rid in settings.allowed_role_ids if rid not in chosen) if r]
        lines = []
        for role in adds:
            result = await service.add_allowed_role(guild, role)
            lines.append((result.ok, result.message))
        if any(ok for ok, _ in lines):
            restored = await service.restore_saved(guild)
            if restored:
                lines.append((True, f"Restored {restored} saved role(s) for members who qualify again."))
        if removes:
            affected = await service.preview_allowed_role_removal(guild, removes)
            threshold = service.mass_archive_threshold()
            if len(affected) > threshold:
                await self._confirm_allowed_removal(interaction, removes, affected, threshold)
                lines.append((True, f"Taking {', '.join(r.mention for r in removes)} off the list would remove "
                                    f"**{len(affected)} custom role(s)**, so it waits for you to confirm below."))
            else:
                lines += await self._remove_allowed_roles(guild, interaction.user, removes, affected)
        return _combined(lines)

    async def _remove_allowed_roles(self, guild: discord.Guild, admin: discord.abc.User, roles: list,
                                    affected: list, progress=None) -> list:
        """Take roles off the allowed list, then archive members who no longer qualify. Returns (ok, text) lines."""
        lines = []
        removed = []
        for role in roles:
            result = await service.remove_allowed_role(guild, role)
            lines.append((result.ok, result.message))
            if result.ok:
                removed.append(role)
        if removed and affected:
            names = ", ".join(repr(r.name) for r in removed)
            why = f"allowed role {names} removed" if len(removed) == 1 else f"allowed roles {names} removed"
            report = await service.process_archives(
                guild, {u: why for u in affected}, progress=progress,
                log_title=f"Allowed role {', '.join(r.name for r in removed)} removed by {admin}",
            )
            lines.append((not report.failed, f"Members who no longer qualify: {report.summary()}"))
        return lines

    async def _confirm_allowed_removal(self, interaction: discord.Interaction, roles: list, affected: list,
                                       threshold: int):
        guild, admin = interaction.guild, interaction.user

        async def on_confirm(button_interaction: discord.Interaction):
            progress = _progress_updater(button_interaction, "Removing…")
            result = _combined(await self._remove_allowed_roles(guild, admin, roles, affected, progress))
            await button_interaction.edit_original_response(embed=_embed(
                "Allowed Roles Updated", result.message, PALETTE.SUCCESS if result.ok else PALETTE.WARNING))

        view = ConfirmView(admin.id, on_confirm)
        view.message = await interaction.followup.send(
            embed=build_warning_embed(
                "Confirm Mass Removal",
                f"Taking {', '.join(r.mention for r in roles)} off the allowed list will remove "
                f"**{len(affected)} custom role(s)** (more than the safety limit of {threshold}). Their settings "
                "are saved, so the roles come back if they qualify again.\n\nThis prompt expires in 60 seconds.",
            ),
            view=view, ephemeral=True, wait=True,
        )

    async def _admin_words(self, interaction: discord.Interaction, button: PanelButton):
        settings = await read_before_reply(interaction, storage.get_guild_settings(interaction.guild.id),
                                           "the Blocked words form")
        modal = self._admin_form(
            "Blocked words", button.opened_at,
            lambda submit, form: apply_blocked_words_form(submit.guild, form.block.value, form.unblock.value,
                                                          self._sweep),
        )
        modal.add_item(discord.ui.TextDisplay(blocked_words_text(settings)[:4000]))
        modal.block = modal.field("Block", discord.ui.TextInput(
            style=discord.TextStyle.paragraph, required=False, max_length=1000, placeholder="One word or phrase per line"),
            description="Built-in words you switched off can be turned back on here")
        modal.unblock = modal.field("Unblock", discord.ui.TextInput(
            style=discord.TextStyle.paragraph, required=False, max_length=1000, placeholder="One word or phrase per line"),
            description="Built-in words can be switched off here")
        await interaction.response.send_modal(modal)

    async def _admin_members(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer(ephemeral=True, thinking=True)
        entries = await service.list_entries(interaction.guild)
        view = ListView(interaction.user.id, entries, "Custom Roles", guild=interaction.guild)
        view.message = await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True, wait=True)

    async def _admin_remove(self, interaction: discord.Interaction, button: PanelButton):
        async def handler(submit: discord.Interaction, form: PanelModal):
            await submit.response.defer(ephemeral=True, thinking=True)
            user, problem = await self._remove_target(submit, form.user.values, form.user_id.value)
            if problem:
                await _send(submit, build_error_embed("Who?", problem))
                return
            await self._send_remove_confirm(submit, user, form.reason.value.strip() or None)

        modal = PanelModal("Remove a member's custom role", handler)
        modal.user = modal.field("Member", discord.ui.UserSelect(required=False, min_values=0, max_values=1))
        modal.user_id = modal.field("Or their user ID", discord.ui.TextInput(
            required=False, max_length=20, placeholder="123456789012345678"),
            description="For someone who left the server")
        modal.reason = modal.field("Reason (optional)", discord.ui.TextInput(
            style=discord.TextStyle.paragraph, required=False, max_length=300),
            description="If given, they get a DM with it. If not, they aren't told.")
        await interaction.response.send_modal(modal)

    @staticmethod
    async def _remove_target(interaction: discord.Interaction, picked: list, id_text: str):
        """(user, None) or (None, why) from the Remove form's member select or typed ID."""
        id_text = (id_text or "").strip()
        if picked and id_text:
            return None, "Pick a member **or** type an ID, not both."
        if picked:
            return picked[0], None
        if not id_text:
            return None, "Pick a member, or type the user ID of someone who left."
        if not id_text.isdigit():
            return None, f"{validation.code(id_text)} isn't a user ID (it's a long number)."
        member = interaction.guild.get_member(int(id_text))
        if member is not None:
            return member, None
        try:
            return await interaction.client.fetch_user(int(id_text)), None
        except discord.NotFound:
            return None, "No Discord user has that ID."
        except discord.HTTPException:
            return None, "I couldn't look that user up. Please try again."

    async def _send_remove_confirm(self, interaction: discord.Interaction, user: discord.abc.User,
                                   reason: Optional[str]):
        guild = interaction.guild
        record = await storage.get_custom_role(guild.id, user.id)
        if record is None:
            await _send(interaction, build_error_embed("No Role", f"{user.mention} doesn't have a custom role."))
            return
        role = guild.get_role(record.role_id) if record.role_id else None
        shown = role.mention if role else validation.code(record.name or "unnamed")
        told = f"They'll get a DM with the reason:\n> {reason}" if reason else "No reason given, so they won't be told."
        admin = interaction.user

        async def on_confirm(button_interaction: discord.Interaction):
            result = await service.admin_remove(guild, user, admin, reason)
            embed = (build_success_embed("Role Removed", result.message) if result.ok
                     else build_error_embed("Couldn't Remove That Role", result.message))
            await button_interaction.edit_original_response(embed=embed)

        view = ConfirmView(admin.id, on_confirm)
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

    async def _admin_pending(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer(ephemeral=True, thinking=True)
        pending = await storage.get_open_pending(interaction.guild.id)
        if pending is None:
            await _send(interaction, build_info_embed("Nothing Pending", "No removals are waiting for approval."))
            return
        text = service.pending_text(pending, service.mass_archive_threshold())
        await _send(interaction, _embed("Removal Waiting For Approval", text, PALETTE.WARNING), _pending_view(pending.id))

    async def _admin_import(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._send_import_preview(interaction)

    async def _send_import_preview(self, interaction: discord.Interaction):
        guild = interaction.guild
        problem = await service.member_data_problem(guild) or service.archive_blocker(guild)
        if problem:
            await _send(interaction, build_error_embed(
                "Can't Import Right Now",
                f"I can't check who qualifies right now ({problem}), so I won't import anything. Try again in a minute.",
            ))
            return
        plan = await service.plan_legacy_import(guild)
        text = legacy_preview_text(plan)
        if not plan.take_over and not plan.not_qualifying:
            await _send(interaction, build_info_embed("Import Old Booster Roles", text))
            return
        take_over_ids = {e.user_id for e in plan.take_over}
        archive_ids = {e.user_id for e in plan.not_qualifying}
        admin = interaction.user

        async def on_choice(button_interaction: discord.Interaction, archive_others: bool):
            progress = _progress_updater(button_interaction, "Archiving…")
            report = await service.import_legacy(
                guild, admin, take_over_ids, archive_ids if archive_others else set(), progress=progress
            )
            lines = [f"Took over **{len(report.taken_over)}** old role(s) as custom roles (name, color and position kept)."]
            if report.archive is not None:
                lines.append(f"Archived old roles of members who don't qualify: {report.archive.summary()}")
            elif archive_ids:
                lines.append(f"Left the {len(archive_ids)} old role(s) of members who don't qualify untouched.")
            if report.skipped:
                lines.append("**Skipped:** " + ", ".join(f"<@{uid}> ({why})" for uid, why in report.skipped[:15]))
            failed = report.archive is not None and report.archive.failed
            embed = _embed("Import Finished", "\n".join(lines), PALETTE.WARNING if failed else PALETTE.SUCCESS)
            await button_interaction.edit_original_response(embed=embed)

        view = LegacyImportView(admin.id, plan, on_choice)
        view.message = await interaction.followup.send(
            embed=build_warning_embed("Import Old Booster Roles", text), view=view, ephemeral=True, wait=True,
        )

    async def _admin_refresh(self, interaction: discord.Interaction, button: PanelButton):
        await interaction.response.defer()
        await self._refresh_admin(interaction, button.opened_at)

async def setup(bot: commands.Bot):
    await bot.add_cog(CustomRoles(bot))
    logger.info("CustomRoles cog loaded")

"""Offline checks for setup in a new server: the admin panel's checklist, Turn on's checks, ❌ replies
for refused admin actions, the timeout on the read before a form opens, and panel errors in the logs."""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

from types import SimpleNamespace as NS  # noqa: E402

import discord  # noqa: E402

from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 12
assert GID in _safety.TEST_GUILD_IDS

results = []


def check(label, cond, detail=None):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + ("" if cond or detail is None else f"  [{detail}]"))


class Response:
    def __init__(self):
        self.modals, self.sent, self.edits, self.deferred, self.done = [], [], [], [], False

    async def send_modal(self, modal):
        self.modals.append(modal)
        self.done = True

    async def send_message(self, content=None, **kw):
        self.sent.append(content if content is not None else kw.get("embed"))
        self.done = True

    async def edit_message(self, **kw):
        self.edits.append(kw)
        self.done = True

    async def defer(self, **kw):
        self.deferred.append(kw)
        self.done = True

    def is_done(self):
        return self.done


class Followup:
    def __init__(self):
        self.sent = []

    async def send(self, embed=None, view=None, ephemeral=None, wait=False, file=None):
        self.sent.append(NS(embed=embed, view=view, ephemeral=ephemeral))
        return NS(edit=None)


class Inter:
    def __init__(self, user, cog):
        self.user, self.guild, self.guild_id = user, user.guild, user.guild.id
        self.client = NS(get_cog=lambda name: cog if name == "CustomRoles" else None)
        self.response, self.followup, self.edited = Response(), Followup(), []
        self.command = None

    async def edit_original_response(self, **kw):
        self.edited.append(kw)


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def find(self, text):
        return [r for r in self.records if text in r.getMessage()]


async def main():
    import database as db
    from cogs.customization import custom_roles as cog_mod
    from cogs.customization.custom_roles import PANEL_ADMIN, PANEL_MEMBER
    from helpers.custom_roles import COMMAND_GROUP, service, storage

    q = db.execute_db_operation
    await db.init_custom_roles_tables()

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals",
                      "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))

    async def new_guild():
        """A server the bot just joined: nothing set up."""
        await reset()
        g = FakeGuild(GID)
        g.channel.permissions_for = lambda me: discord.Permissions(view_channel=True, send_messages=True,
                                                                   embed_links=True)
        admin = FakeMember(g, name="admin")
        admin.guild_permissions = discord.Permissions(manage_roles=True)
        return g, admin

    cog = cog_mod.CustomRoles(NS(custom_role_picker_ready=False))
    now = int(time.time())

    def button(view, action):
        return next(item for item in view.children if item.action == action)

    async def press(view, action, user):
        inter = Inter(user, cog)
        item = button(view, action)
        if await item.interaction_check(inter):
            await item.callback(inter)
        return inter

    async def submit(modal, user):
        inter = Inter(user, cog)
        await modal.on_submit(inter)
        return inter

    def checklist(embed):
        first = embed.fields[0] if embed.fields else None
        return first.value if first and "Setup checklist" in first.name else None

    # ================================================================== setup checklist on the admin panel
    g, admin = await new_guild()
    embed, view = await cog_mod.admin_panel(g, admin.id, now)
    steps = checklist(embed)
    check("off: the checklist is the first field", steps is not None, [f.name for f in embed.fields][:2])
    lines = (steps or "").splitlines()
    check("fresh server: Manage Roles ✅, Anchor ❌, role order ❌ (anchor first), log ➖, Turn on ❌",
          len(lines) == 5 and lines[0].startswith("✅") and "Manage Roles" in lines[0]
          and lines[1].startswith("❌") and "**Anchor**" in lines[1]
          and lines[2].startswith("❌") and "set the anchor first" in lines[2]
          and lines[3].startswith("➖") and "Log channel" in lines[3]
          and lines[4].startswith("❌") and "Then press **Turn on**" in lines[4], lines)

    g.me.guild_permissions = discord.Permissions.none()
    steps = checklist((await cog_mod.admin_panel(g, admin.id, now))[0])
    check("no Manage Roles: first step ❌ says where to give it",
          steps.splitlines()[0].startswith("❌") and "Server Settings → Roles" in steps.splitlines()[0], steps)
    g.me.guild_permissions = discord.Permissions(manage_roles=True)

    high = g.add_role("Above The Bot", g.bot_role.position + 1)
    await storage.update_guild_settings(GID, anchor_role_id=high.id)
    steps = checklist((await cog_mod.admin_panel(g, admin.id, now))[0])
    check("anchor above my role: ❌ says to move my role above the anchor",
          steps.splitlines()[2].startswith("❌") and "Move my role" in steps.splitlines()[2]
          and high.mention in steps.splitlines()[2], steps)

    await storage.update_guild_settings(GID, anchor_role_id=g.anchor.id, log_channel_id=g.channel.id)
    steps = checklist((await cog_mod.admin_panel(g, admin.id, now))[0]).splitlines()
    check("ready: first four ✅ and 'Press **Turn on**.'",
          all(line.startswith("✅") for line in steps[:4]) and steps[4] == "❌ Press **Turn on**.", steps)

    await storage.update_guild_settings(GID, enabled=True)
    embed, _ = await cog_mod.admin_panel(g, admin.id, now)
    check("on: no checklist", checklist(embed) is None)

    # ================================================================== Turn on: checks and ❌ replies
    g, admin = await new_guild()
    embed, view = await cog_mod.admin_panel(g, admin.id, now)

    inter = await press(view, "enable", admin)
    reply = inter.followup.sent[-1].embed if inter.followup.sent else None
    check("Turn on, no anchor: a separate ❌ reply saying to set an Anchor",
          reply is not None and reply.title == "❌ Can't Turn It On Yet" and "Set an Anchor first" in reply.description
          and inter.followup.sent[-1].ephemeral, reply.description if reply else None)
    check("  ...and the panel line too", inter.edited[-1]["embed"].description.startswith("❌ Set an Anchor first"))
    check("  ...still off", not (await storage.get_guild_settings(GID)).enabled)

    await storage.update_guild_settings(GID, anchor_role_id=g.anchor.id)
    g.me.guild_permissions = discord.Permissions.none()
    inter = await press(view, "enable", admin)
    reply = inter.followup.sent[-1].embed if inter.followup.sent else None
    check("Turn on without Manage Roles: refused, reply says to give my role Manage Roles",
          reply is not None and "Manage Roles" in reply.description and "Server Settings → Roles" in reply.description
          and not (await storage.get_guild_settings(GID)).enabled, reply.description if reply else None)
    g.me.guild_permissions = discord.Permissions(manage_roles=True)

    g.bot_role.position, g.anchor.position = 1, 2  # my role below the anchor
    inter = await press(view, "enable", admin)
    reply = inter.followup.sent[-1].embed if inter.followup.sent else None
    check("Turn on with my role below the anchor: refused, reply says to move my role above it",
          reply is not None and "Move my role above" in reply.description
          and not (await storage.get_guild_settings(GID)).enabled, reply.description if reply else None)
    g.bot_role.position, g.anchor.position = 2, 1

    inter = await press(view, "enable", admin)
    check("Turn on when ready: on, no ❌ reply", (await storage.get_guild_settings(GID)).enabled
          and not inter.followup.sent and inter.edited[-1]["embed"].description.startswith("✅"))
    _, view = await cog_mod.admin_panel(g, admin.id, now)
    inter = await press(view, "disable", admin)
    check("Turn off: no ❌ reply", not inter.followup.sent and not (await storage.get_guild_settings(GID)).enabled)

    # ================================================================== other admin refusals get a reply too
    _, view = await cog_mod.admin_panel(g, admin.id, now)
    modal = (await press(view, "anchor", admin)).response.modals[-1]
    high = g.add_role("Too High", g.bot_role.position + 1)
    modal.role._values, modal.place._value = [high], "above"
    inter = await submit(modal, admin)
    reply = inter.followup.sent[-1].embed if inter.followup.sent else None
    check("Anchor above my role: ❌ 'Anchor Not Set' reply saying to move my role or pick a lower one",
          reply is not None and reply.title == "❌ Anchor Not Set" and "Move my role above" in reply.description
          and (await storage.get_guild_settings(GID)).anchor_role_id == g.anchor.id,
          reply.description if reply else None)
    modal.role._values = [g.anchor]
    inter = await submit(modal, admin)
    check("Anchor accepted: no ❌ reply", not inter.followup.sent)

    modal = (await press(view, "cooldown", admin)).response.modals[-1]
    modal.seconds._value = "soon"
    inter = await submit(modal, admin)
    check("Cooldown refused: ❌ 'Not Saved' reply with the rule",
          inter.followup.sent and inter.followup.sent[-1].embed.title == "❌ Not Saved"
          and "86400" in inter.followup.sent[-1].embed.description)
    modal.seconds._value = "0"
    check("Cooldown accepted: no reply", not (await submit(modal, admin)).followup.sent)

    # ================================================================== slow database before a form
    cog_mod.FORM_READ_TIMEOUT = 0.05
    file_log, console_log = Capture(), Capture()
    cog_mod.logger.addHandler(file_log)
    cog_mod.console_logger.addHandler(console_log)
    real_settings, real_record = storage.get_guild_settings, storage.get_custom_role

    async def slow(*args, **kw):
        await asyncio.sleep(1)

    storage.get_guild_settings = slow
    try:
        inter = await press(view, "anchor", admin)
        check("slow database: no form, a 'Try Again' reply instead of 'This interaction failed'",
              not inter.response.modals and inter.response.sent
              and inter.response.sent[-1].title == "❌ Try Again"
              and "try again" in inter.response.sent[-1].description.lower())
        check("  ...logged to the console and the file",
              console_log.find("database too slow") and file_log.find("database too slow"))
        check("  ...not reported as an error", not console_log.find("failed in guild"))
        for action in ("log", "channel", "cooldown", "allowed", "words"):
            inter = await press(view, action, admin)
            if inter.response.modals or not inter.response.sent:
                check(f"slow database: {action} form refused too", False)
                break
        else:
            check("slow database: every admin form waits at most the timeout", True)
        inter = Inter(admin, cog)
        inter.command = NS(name=COMMAND_GROUP, root_parent=None)
        inter.channel = g.channel
        check("slow database in the /custom-role channel check: 'Try Again', command stopped",
              not await cog.interaction_check(inter) and inter.response.sent[-1].title == "❌ Try Again")
    finally:
        storage.get_guild_settings = real_settings

    member = FakeMember(g, booster=True, name="member")
    await service.set_enabled(g, True)
    await service.create_role(member, "Slow Test")
    _, mview = await cog_mod.member_panel(member, now)
    storage.get_custom_role = slow
    try:
        inter = await press(mview, "rename", member)
        check("slow database: Rename form says Try Again", not inter.response.modals and inter.response.sent)
        inter = await press(mview, "color", member)
        check("slow database: Color form says Try Again", not inter.response.modals and inter.response.sent)
    finally:
        storage.get_custom_role = real_record
    inter = await press(mview, "rename", member)
    check("normal speed: the form opens", inter.response.modals)
    cog_mod.FORM_READ_TIMEOUT = 2.0

    # ================================================================== panel errors reach the console
    console_log.records.clear()
    file_log.records.clear()

    async def broken(interaction, button):
        raise RuntimeError("boom in refresh")

    cog._admin_refresh = broken
    inter = await press(view, "refresh", admin)
    errors = console_log.find("panel button admin/refresh")
    check("a failing button: error with traceback on the console and in the file",
          errors and errors[0].levelno == logging.ERROR and errors[0].exc_info
          and "boom in refresh" in errors[0].getMessage() and file_log.find("panel button admin/refresh"))
    check("  ...says which server and member", str(GID) in errors[0].getMessage() and str(admin.id) in errors[0].getMessage()
          if errors else False)
    check("  ...and the member gets 'Something went wrong'",
          inter.response.sent and "Something went wrong" in inter.response.sent[-1].title)
    del cog._admin_refresh

    modal = cog_mod.PanelModal("Test form", None)
    inter = Inter(admin, cog)
    await modal.on_error(inter, ValueError("bad form"))
    check("a failing form: logged to the console", console_log.find("panel form 'Test form'"))

    confirm = cog_mod.ConfirmView(admin.id, None)
    inter = Inter(admin, cog)
    await confirm.on_error(inter, KeyError("x"), confirm.confirm)
    check("a failing Confirm button (any panel view): logged to the console and answered",
          console_log.find("ConfirmView 'Confirm'") and inter.response.sent)
    check("panel views log their errors", all(issubclass(cls, cog_mod.LoggedView) for cls in (
        cog_mod.ConfirmView, cog_mod.LegacyImportView, cog_mod.ColorPreviewView, cog_mod.PaletteView, cog_mod.ListView)))
    check("the panel's own view logs too",
          isinstance(cog_mod._panel_view(PANEL_MEMBER, 1, now, []), cog_mod.LoggedView)
          and isinstance(cog_mod._pending_view(1), cog_mod.LoggedView))

    pending_button = cog_mod.PendingButton(424242, "cancel")
    inter = Inter(admin, cog)

    async def explode(*a, **kw):
        raise RuntimeError("pending boom")

    real_cancel = service.cancel_pending
    service.cancel_pending = explode
    try:
        await pending_button.callback(inter)
    finally:
        service.cancel_pending = real_cancel
    check("a failing pending-removal button: logged to the console", console_log.find("pending removal cancel"))

    expired = cog_mod._panel_view(PANEL_ADMIN, admin.id, now - cog_mod.PANEL_TTL - 5,
                                  [("refresh", "Refresh", discord.ButtonStyle.secondary, 0)])
    inter = await press(expired, "refresh", admin)
    check("expired panels still answer (unchanged)", "expired" in inter.response.edits[-1]["embed"].description)

    cog_mod.logger.removeHandler(file_log)
    cog_mod.console_logger.removeHandler(console_log)
    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

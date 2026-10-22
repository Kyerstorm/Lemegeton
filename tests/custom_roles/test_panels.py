"""Offline checks for the /custom-role and /custom-role-admin panels: buttons, forms, expiry and Discord's limits."""
import asyncio
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

from types import SimpleNamespace as NS  # noqa: E402

import discord  # noqa: E402
from PIL import Image  # noqa: E402

from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 11
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
        self.sent.append(NS(embed=embed, view=view, ephemeral=ephemeral, file=file))
        return NS(edit=self._edit)

    async def _edit(self, **kw):
        pass


class Inter:
    """One button press or form submit."""

    def __init__(self, user, cog, fetch_user=None):
        self.user, self.guild = user, user.guild
        self.client = NS(get_cog=lambda name: cog if name == "CustomRoles" else None, fetch_user=fetch_user)
        self.response, self.followup, self.edited = Response(), Followup(), []

    async def edit_original_response(self, **kw):
        self.edited.append(kw)


class FakeFlags:
    def __init__(self, animated=False):
        self.animated, self.value = animated, 0


class FakeAttachment:
    def __init__(self, data, filename="icon.png", content_type="image/png"):
        self.data, self.filename, self.content_type = data, filename, content_type
        self.size, self.width, self.height = len(data), 64, 64
        self.flags = FakeFlags()
        self.url = f"https://cdn.discordapp.com/attachments/1/2/{filename}"

    async def read(self, *, use_cached=False):
        return self.data


def labels(view):
    return {item.action: item.item.label for item in view.children}


def button(view, action):
    return next(item for item in view.children if item.action == action)


def limits_problem(modal):
    """Why Discord would refuse this form, or None."""
    if len(modal.children) > 5:
        return f"{len(modal.children)} items"
    if len(modal.title) > 45:
        return f"title {modal.title!r} too long"
    for item in modal.children:
        if isinstance(item, discord.ui.Label):
            if len(item.text) > 45:
                return f"label {item.text!r} too long"
            if item.description and len(item.description) > 100:
                return f"description {item.description!r} too long"
            if isinstance(item.component, discord.ui.RadioGroup) and not 2 <= len(item.component.options) <= 10:
                return "radio group needs 2-10 options"
        elif not isinstance(item, discord.ui.TextDisplay):
            return f"{type(item).__name__} must be inside a Label"
    modal.to_components()  # serialises like discord.py does before sending
    return None


async def main():
    import config
    import database as db
    from cogs.customization import custom_roles as cog_mod
    from cogs.customization.custom_roles import PANEL_ADMIN, PANEL_MEMBER, PANEL_TTL, PanelButton
    from helpers.custom_roles import ADMIN_GROUP, COMMAND_GROUP, FEATURE_GRADIENT, service, storage

    q = db.execute_db_operation
    await db.init_custom_roles_tables()
    service.ARCHIVE_BATCH_PAUSE = 0
    service.pending_view_factory = lambda pid: f"VIEW-{pid}"

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals",
                      "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        service._skip_warned.clear()
        service._recent_archives.clear()

    async def new_guild(features=(), ready=True):
        await reset()
        g = FakeGuild(GID, features)
        if ready:
            await service.set_anchor(g, g.anchor)
            await service.set_enabled(g, True)
            await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
        return g

    async def record(member):
        return await storage.get_custom_role(GID, member.id)

    cog = cog_mod.CustomRoles(NS(custom_role_picker_ready=False))

    async def press(view, action, user, **kw):
        """Press a panel button; returns the interaction."""
        inter = Inter(user, cog, **kw)
        item = button(view, action)
        if await item.interaction_check(inter):
            await item.callback(inter)
        return inter

    async def submit(modal, user, **kw):
        inter = Inter(user, cog, **kw)
        await modal.on_submit(inter)
        return inter

    def panel_after(inter):
        """The panel as a form submit or button left it: (embed, view)."""
        last = inter.edited[-1]
        return last["embed"], last["view"]

    # ================================================================== the two commands
    commands_ = {c.name: c for c in cog_mod.CustomRoles.__cog_app_commands__}
    check("exactly two commands: /custom-role and /custom-role-admin",
          sorted(commands_) == sorted([COMMAND_GROUP, ADMIN_GROUP]), sorted(commands_))
    check("both are plain commands (no subcommands)",
          all(isinstance(c, discord.app_commands.Command) for c in commands_.values()))
    check("both are server-only", all(c.guild_only for c in commands_.values()))
    admin_cmd = commands_[ADMIN_GROUP]
    check("/custom-role-admin needs Manage Roles by default",
          admin_cmd.default_permissions is not None and admin_cmd.default_permissions.manage_roles)
    check("/custom-role is open to everyone", commands_[COMMAND_GROUP].default_permissions is None)
    check("dashboard metadata kept", getattr(commands_[COMMAND_GROUP].callback, "__dashboard_name__", "") == "Custom Role"
          and getattr(admin_cmd.callback, "__dashboard_name__", "") == "Custom Role Admin")

    # ================================================================== member panel: not set up / no role
    g = await new_guild(ready=False)
    m = FakeMember(g, booster=True, name="booster")
    now = int(time.time())
    embed, view = await cog_mod.member_panel(m, now)
    check("not set up: explains, no buttons", view is None and "isn't set up" in embed.description, embed.description)

    g = await new_guild()
    m = FakeMember(g, booster=True, name="booster")
    outsider = FakeMember(g, name="outsider")
    embed, view = await cog_mod.member_panel(outsider, now)
    check("not eligible: explains, no buttons", view is None and embed.description, embed.description)

    embed, view = await cog_mod.member_panel(m, now)
    check("no role yet: Create role and Look up buttons",
          labels(view) == {"create": "Create role", "lookup": "Look up a member"}, labels(view))
    check("panel says when it expires", f"<t:{now + PANEL_TTL}:R>" in embed.description, embed.description)
    custom_id = button(view, "create").item.custom_id
    check("button custom_id carries panel, action, owner and open time",
          custom_id == f"custom-role:panel:me:create:{m.id}:{now}" and len(custom_id) <= 100, custom_id)
    match = PanelButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    rebuilt = await PanelButton.from_custom_id(None, NS(label="Create role"), match)
    check("persistent: rebuilt from its custom_id after a restart",
          (rebuilt.panel, rebuilt.action, rebuilt.owner_id, rebuilt.opened_at) == (PANEL_MEMBER, "create", m.id, now))

    # ================================================================== expiry and who can press
    old_view = cog_mod._panel_view(PANEL_MEMBER, m.id, now - PANEL_TTL - 1, [("rename", "Rename", discord.ButtonStyle.primary, 0)])
    inter = await press(old_view, "rename", m)
    edit = inter.response.edits[-1] if inter.response.edits else {}
    check("expired panel: the press answers 'This panel expired, run /custom-role again'",
          edit.get("embed") is not None and edit["embed"].description == "This panel expired, run `/custom-role` again."
          and edit.get("view") is None and not inter.response.modals, edit)
    old_admin = cog_mod._panel_view(PANEL_ADMIN, m.id, now - PANEL_TTL - 1, [("refresh", "Refresh", discord.ButtonStyle.secondary, 0)])
    inter = await press(old_admin, "refresh", m)
    check("expired admin panel names /custom-role-admin",
          inter.response.edits[-1]["embed"].description == "This panel expired, run `/custom-role-admin` again.")
    fresh = cog_mod._panel_view(PANEL_MEMBER, m.id, now - PANEL_TTL + 30, [("rename", "Rename", discord.ButtonStyle.primary, 0)])
    check("not expired 30 s before the limit", await button(fresh, "rename").interaction_check(Inter(m, cog)))
    inter = Inter(outsider, cog)
    check("someone else's panel: refused with a reply",
          not await button(view, "create").interaction_check(inter) and "someone else" in inter.response.sent[-1])
    no_perms = FakeMember(g, name="no perms")
    no_perms.guild_permissions = discord.Permissions.none()
    admin_view = cog_mod._panel_view(PANEL_ADMIN, no_perms.id, now, [("refresh", "Refresh", discord.ButtonStyle.secondary, 0)])
    inter = Inter(no_perms, cog)
    check("admin panel: needs Manage Roles at press time",
          not await button(admin_view, "refresh").interaction_check(inter) and "Manage Roles" in inter.response.sent[-1])
    unknown = cog_mod._panel_view(PANEL_MEMBER, m.id, now, [("frobnicate", "?", discord.ButtonStyle.secondary, 0)])
    inter = await press(unknown, "frobnicate", m)
    check("unknown (older) button: treated as expired", "expired" in inter.response.edits[-1]["embed"].description)
    inter = Inter(m, None)
    await button(view, "create").callback(inter)
    check("cog not loaded: friendly reply", "isn't running" in inter.response.sent[-1])

    # ================================================================== Create role
    inter = await press(view, "create", m)
    modal = inter.response.modals[-1]
    check("Create role opens a form within Discord's limits", limits_problem(modal) is None, limits_problem(modal))
    modal.name._value = "Panel Role"
    inter = await submit(modal, m)
    embed, view = panel_after(inter)
    check("form submit updates the panel in place (deferred update)", inter.response.deferred == [{}])
    check("created: ✅ result on top and the full button set",
          embed.description.startswith("✅ Created **Panel Role**") and set(labels(view)) ==
          {"rename", "color", "icon", "palette", "unwear", "move", "picker", "lookup"}, (embed.description, labels(view)))
    check("created message points at the Color button", "**Color**" in embed.description, embed.description)
    check("wearing it: shows Take off", labels(view)["unwear"] == "Take off")
    check("panel shows the role's fields", [f.name for f in embed.fields][:5] == ["Name", "Style", "Colors", "Icon", "Status"])
    check("the new panel keeps the original open time (fixed 15 minutes)",
          button(view, "rename").opened_at == now)

    # ================================================================== Rename
    inter = await press(view, "rename", m)
    modal = inter.response.modals[-1]
    check("Rename form prefilled with the current name", modal.name.default == "Panel Role" and limits_problem(modal) is None)
    modal.name._value = "Renamed In Panel"
    embed, view = panel_after(await submit(modal, m))
    check("renamed", embed.description.startswith("✅") and (await record(m)).name == "Renamed In Panel", embed.description)
    modal.name._value = "Moderator"
    embed, view = panel_after(await submit(modal, m))
    check("refused name: ❌ on the panel, name unchanged",
          embed.description.startswith("❌") and (await record(m)).name == "Renamed In Panel", embed.description)

    # ================================================================== Color (no Enhanced Role Styles)
    inter = await press(view, "color", m)
    modal = inter.response.modals[-1]
    kinds = [type(i.component).__name__ if isinstance(i, discord.ui.Label) else type(i).__name__ for i in modal.children]
    check("Color form without 3 boosts: one hex field and the reason, no style choice",
          kinds == ["TextInput", "TextDisplay"] and modal.style is None and limits_problem(modal) is None, kinds)
    check("  ...says gradients need 3 boosts and points at the picker",
          "3 server boosts" in modal.children[1].content and "Color picker" in modal.children[1].content)
    check("  ...the hex field is required", modal.primary.required)
    modal.primary._value = "#A78BFA"
    embed, view = panel_after(await submit(modal, m))
    check("solid color set", embed.description.startswith("✅") and (await record(m)).primary_color == 0xA78BFA, embed.description)
    modal.primary._value = "purple"
    embed, view = panel_after(await submit(modal, m))
    check("bad hex: ❌ with examples", embed.description.startswith("❌") and "isn't a hex color" in embed.description
          and "#FF66AA" in embed.description, embed.description)
    inter = await press(view, "color", m)
    check("Color form prefilled with the current color", inter.response.modals[-1].primary.default == "#A78BFA")
    r = await cog_mod.apply_color_form(m, service.MODE_GRADIENT, "#FF0000", "#0000FF")
    check("gradient without the perk: refused with the 3-boost message", not r.ok and "3 server boosts" in r.message, r.message)

    # ================================================================== Icon
    inter = await press(view, "icon", m)
    modal = inter.response.modals[-1]
    kinds = [type(i.component).__name__ if isinstance(i, discord.ui.Label) else type(i).__name__ for i in modal.children]
    check("Icon form: file upload, emoji, remove checkbox, tip",
          kinds == ["FileUpload", "TextInput", "Checkbox", "TextDisplay"] and limits_problem(modal) is None, kinds)
    check("  ...one optional file", modal.image.max_values == 1 and not modal.image.required)
    check("  ...says the size limit", "8 MB" in modal.children[0].description, modal.children[0].description)
    r = await cog_mod.apply_icon_form(m, [], "", False)
    check("nothing chosen: says what to do", not r.ok and "Upload an image" in r.message)
    r = await cog_mod.apply_icon_form(m, [], "🎨", True)
    check("two chosen: pick one", not r.ok and "Pick one" in r.message)
    png = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 100, 50)).save(png, format="PNG")
    modal.image._values, modal.emoji._value, modal.remove._value = [FakeAttachment(png.getvalue())], "", False
    embed, view = panel_after(await submit(modal, m))
    check("uploaded image is checked, then the Boost Level 2 refusal",
          embed.description.startswith("❌") and "Your image is fine" in embed.description, embed.description)
    modal.image._values, modal.emoji._value = [], "🎨"
    embed, view = panel_after(await submit(modal, m))
    check("emoji goes through the same path", embed.description.startswith("❌") and "Boost Level 2" in embed.description,
          embed.description)
    modal.emoji._value, modal.remove._value = "", True
    embed, view = panel_after(await submit(modal, m))
    check("Remove my icon: handled (nothing to remove here)", embed.description.startswith(("✅", "❌")), embed.description)

    # ================================================================== Take off / Put on
    embed, view = panel_after(await press(view, "unwear", m))
    role = g.get_role((await record(m)).role_id)
    check("Take off: role removed, button becomes Put on",
          role not in m.roles and labels(view).get("wear") == "Put on" and embed.description.startswith("✅"))
    check("  ...message points at Put on", "**Put on**" in embed.description, embed.description)
    embed, view = panel_after(await press(view, "wear", m))
    check("Put on: role back, button becomes Take off", role in m.roles and labels(view).get("unwear") == "Take off")

    # ================================================================== Move / Look up / Color picker
    inter = await press(view, "move", m)
    modal = inter.response.modals[-1]
    check("Move form: role select and above/below", limits_problem(modal) is None
          and [o.value for o in modal.place.options] == ["above", "below"])
    modal.role._values, modal.place._value = [g.anchor], "below"
    embed, view = panel_after(await submit(modal, m))
    check("Move next to a role that isn't a custom role: ❌", embed.description.startswith("❌"), embed.description)
    modal.role._values = []
    embed, view = panel_after(await submit(modal, m))
    check("Move with nothing picked: ❌", embed.description.startswith("❌"), embed.description)

    inter = await press(view, "lookup", m)
    modal = inter.response.modals[-1]
    check("Look up form within limits", limits_problem(modal) is None)
    modal.user._values = [outsider]
    inter = await submit(modal, m)
    check("look up someone without a role: says so (new message, not the panel)",
          "doesn't have a custom role" in inter.followup.sent[-1].embed.description and not inter.edited
          and inter.response.deferred == [{"ephemeral": True, "thinking": True}])
    other = FakeMember(g, booster=True, name="other")
    await service.create_role(other, "Other Role")
    modal.user._values = [other]
    inter = await submit(modal, m)
    shown = inter.followup.sent[-1].embed
    check("look up someone with a role: their role card", shown.title.endswith("other's Custom Role")
          and any(f.name == "Name" and f.value == "Other Role" for f in shown.fields), shown.title)

    inter = await press(view, "picker", m)
    check("Color picker with the web server off: friendly error",
          "isn't available" in inter.followup.sent[-1].embed.description)
    check("  ...which mentions the panel, not old commands", "`/custom-role` panel" in inter.followup.sent[-1].embed.description)

    # ================================================================== Color (3 boosts)
    g2 = await new_guild(features=[FEATURE_GRADIENT])
    b = FakeMember(g2, booster=True, name="gradient fan")
    await service.create_role(b, "Fade")
    _, bview = await cog_mod.member_panel(b, now)
    inter = await press(bview, "color", b)
    modal = inter.response.modals[-1]
    kinds = [type(i.component).__name__ if isinstance(i, discord.ui.Label) else type(i).__name__ for i in modal.children]
    check("Color form with 3 boosts: style radio, two hex fields, tip",
          kinds == ["RadioGroup", "TextInput", "TextInput", "TextDisplay"] and limits_problem(modal) is None, kinds)
    check("  ...style options and current style picked",
          [o.value for o in modal.style.options] == ["solid", "gradient", "holographic"]
          and [o.default for o in modal.style.options] == [True, False, False])
    check("  ...hex fields optional (holographic needs none)", not modal.primary.required and not modal.secondary.required)
    modal.style._value, modal.primary._value, modal.secondary._value = "gradient", "#FF0000", ""
    embed, _ = panel_after(await submit(modal, b))
    check("gradient without a second color: ❌", embed.description.startswith("❌") and "second color" in embed.description,
          embed.description)
    modal.secondary._value = "#0000FF"
    embed, bview = panel_after(await submit(modal, b))
    rec = await record(b)
    check("gradient set", embed.description.startswith("✅") and rec.color_mode == "gradient"
          and (rec.primary_color, rec.secondary_color) == (0xFF0000, 0x0000FF), embed.description)
    inter = await press(bview, "color", b)
    again = inter.response.modals[-1]
    check("form reopens with gradient picked and both colors filled",
          [o.default for o in again.style.options] == [False, True, False]
          and (again.primary.default, again.secondary.default) == ("#FF0000", "#0000FF"))
    again.style._value, again.primary._value, again.secondary._value = "solid", "#00FF00", "#0000FF"
    await submit(again, b)
    rec = await record(b)
    check("solid ignores a leftover second color", rec.color_mode == "solid" and rec.primary_color == 0x00FF00
          and not rec.secondary_color, (rec.color_mode, rec.secondary_color))
    again.style._value, again.primary._value, again.secondary._value = "holographic", "", ""
    await submit(again, b)
    check("holographic needs no colors", (await record(b)).color_mode == "holographic")
    inter = await press(bview, "color", b)
    check("after holographic the hex fields start empty",
          (inter.response.modals[-1].primary.default, inter.response.modals[-1].secondary.default) == (None, None))

    # ================================================================== admin panel
    g = await new_guild(ready=False)
    admin = FakeMember(g, name="admin")
    admin.guild_permissions = discord.Permissions(manage_roles=True)
    g.channel.permissions_for = lambda me: discord.Permissions(view_channel=True, send_messages=True, embed_links=True)
    embed, view = await cog_mod.admin_panel(g, admin.id, now)
    check("admin panel: settings plus every button", set(labels(view)) == {
        "enable", "anchor", "log", "channel", "cooldown", "allowed", "words", "members", "remove", "pending",
        "import", "refresh"}, labels(view))
    check("  ...off: Turn on", labels(view)["enable"] == "Turn on" and embed.title.endswith("Custom Roles Settings"))
    check("  ...problems point at the Anchor button", "**Anchor**" in next(f.value for f in embed.fields if f.name == "Problems"))
    check("  ...expiry shown", f"<t:{now + PANEL_TTL}:R>" in embed.description)
    rows = {}
    for item in view.children:
        rows.setdefault(item.item.row, []).append(item)
    check("  ...at most 5 buttons per row", all(len(r) <= 5 for r in rows.values()), {k: len(v) for k, v in rows.items()})

    embed, view = panel_after(await press(view, "enable", admin))
    check("Turn on before an anchor: ❌ pointing at Anchor", embed.description.startswith("❌") and "**Anchor**" in embed.description,
          embed.description)

    inter = await press(view, "anchor", admin)
    modal = inter.response.modals[-1]
    check("Anchor form within limits, below by default", limits_problem(modal) is None
          and [o.default for o in modal.place.options] == [False, True])
    modal.role._values, modal.place._value = [g.anchor], "above"
    embed, view = panel_after(await submit(modal, admin))
    s = await storage.get_guild_settings(GID)
    check("anchor set (above), next step is Turn on", embed.description.startswith("✅") and "Turn on" in embed.description
          and s.anchor_role_id == g.anchor.id and s.anchor_place == "above", embed.description)
    inter = await press(view, "anchor", admin)
    check("Anchor form reopens with the current anchor and place",
          [v.id for v in inter.response.modals[-1].role.default_values] == [g.anchor.id]
          and [o.default for o in inter.response.modals[-1].place.options] == [True, False])

    embed, view = panel_after(await press(view, "enable", admin))
    check("Turn on: on, button becomes Turn off", embed.description.startswith("✅") and labels(view).get("disable") == "Turn off"
          and (await storage.get_guild_settings(GID)).enabled)
    embed, view = panel_after(await press(view, "disable", admin))
    check("Turn off: says nothing is removed automatically while off",
          "nothing is removed automatically" in embed.description and labels(view).get("enable") == "Turn on", embed.description)
    embed, view = panel_after(await press(view, "enable", admin))

    inter = await press(view, "cooldown", admin)
    modal = inter.response.modals[-1]
    check("Cooldown form prefilled", modal.seconds.default == "0" and limits_problem(modal) is None)
    modal.seconds._value = "abc"
    embed, view = panel_after(await submit(modal, admin))
    check("cooldown: not a number refused", embed.description.startswith("❌") and "86400" in embed.description)
    modal.seconds._value = "300"
    embed, view = panel_after(await submit(modal, admin))
    check("cooldown 300 saved", embed.description.startswith("✅") and (await storage.get_guild_settings(GID)).cooldown_seconds == 300)
    await service.set_cooldown(g, 0)

    inter = await press(view, "log", admin)
    modal = inter.response.modals[-1]
    check("Log channel form: optional text-channel select", limits_problem(modal) is None and not modal.channel.required
          and modal.channel.channel_types == [discord.ChannelType.text])
    modal.channel._values = [NS(id=g.channel.id)]
    embed, view = panel_after(await submit(modal, admin))
    check("log channel set (the select's channel is looked up in the server)",
          embed.description.startswith("✅") and (await storage.get_guild_settings(GID)).log_channel_id == g.channel.id
          and "set by" in g.channel.texts()[-1], embed.description)
    inter = await press(view, "log", admin)
    check("Log channel form prefilled", [c.id for c in inter.response.modals[-1].channel.default_values] == [g.channel.id])
    blind = NS(id=1, mention="<#1>", permissions_for=lambda me: discord.Permissions(view_channel=True))
    r = await cog_mod.apply_log_channel(g, admin, blind)
    check("log channel without send/embed: refused, names both", not r.ok and "Send Messages" in r.message and "Embed Links" in r.message)
    r = await cog_mod.apply_log_channel(g, admin, None)
    check("empty = logging off", r.ok and (await storage.get_guild_settings(GID)).log_channel_id is None)
    await storage.update_guild_settings(GID, log_channel_id=g.channel.id)

    inter = await press(view, "channel", admin)
    modal = inter.response.modals[-1]
    modal.channel._values = [NS(id=g.channel.id)]
    embed, view = panel_after(await submit(modal, admin))
    check("command channel set", (await storage.get_guild_settings(GID)).command_channel_id == g.channel.id
          and "/custom-role` now only works" in embed.description, embed.description)
    modal.channel._values = []
    embed, view = panel_after(await submit(modal, admin))
    check("command channel cleared", (await storage.get_guild_settings(GID)).command_channel_id is None
          and "any channel" in embed.description, embed.description)

    # ---------------------------------------------------------------- allowed roles
    vip, artist = g.add_role("VIP", 1), g.add_role("Artist", 1)
    inter = await press(view, "allowed", admin)
    modal = inter.response.modals[-1]
    check("Allowed roles form: up to 25 roles, may be empty", limits_problem(modal) is None
          and modal.roles.max_values == 25 and modal.roles.min_values == 0 and not modal.roles.required)
    modal.roles._values = [vip, artist]
    embed, view = panel_after(await submit(modal, admin))
    s = await storage.get_guild_settings(GID)
    check("two roles allowed at once", sorted(s.allowed_role_ids) == sorted([vip.id, artist.id]) and embed.description.startswith("✅"),
          embed.description)
    holders = [FakeMember(g, roles=[vip, artist], name=f"both{i}") for i in range(2)]
    vip_only = FakeMember(g, roles=[vip], name="vip only")
    for h in (*holders, vip_only):
        await service.create_role(h, f"Role {h.name}")
    check("preview with several roles counts members holding both",
          sorted(await service.preview_allowed_role_removal(g, [vip, artist])) == sorted(h.id for h in (*holders, vip_only))
          and await service.preview_allowed_role_removal(g, artist) == [])
    inter = await press(view, "allowed", admin)
    check("Allowed roles form prefilled", sorted(r.id for r in inter.response.modals[-1].roles.default_values)
          == sorted([vip.id, artist.id]))

    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 2
    modal = inter.response.modals[-1]
    modal.roles._values = []
    inter = await submit(modal, admin)
    embed, view = panel_after(inter)
    confirm = inter.followup.sent[-1] if inter.followup.sent else None
    check("removing both over the safety limit: waits for Confirm, nothing removed yet",
          confirm is not None and isinstance(confirm.view, cog_mod.ConfirmView) and "3 custom role(s)" in confirm.embed.description
          and sorted((await storage.get_guild_settings(GID)).allowed_role_ids) == sorted([vip.id, artist.id])
          and all([(await record(h)).status == "active" for h in holders]), embed.description)
    check("  ...the panel says it's waiting", "confirm below" in embed.description, embed.description)
    press_confirm = Inter(admin, cog)
    await confirm.view.confirm.callback(press_confirm)
    s = await storage.get_guild_settings(GID)
    check("Confirm: both roles off the list, the 3 roles archived",
          s.allowed_role_ids == [] and all([(await record(h)).status == "saved" for h in (*holders, vip_only)])
          and "Removed 3" in press_confirm.edited[-1]["embed"].description, press_confirm.edited[-1]["embed"].description)
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10

    modal.roles._values = [vip]
    embed, view = panel_after(await submit(modal, admin))
    check("adding a role back restores members who qualify again",
          "Restored" in embed.description and (await record(vip_only)).status == "active", embed.description)
    modal.roles._values = []
    embed, view = panel_after(await submit(modal, admin))
    check("removing under the limit: done right away and reported", (await record(vip_only)).status == "saved"
          and "Removed" in embed.description, embed.description)
    embed, view = panel_after(await submit(modal, admin))
    check("no change: says so", "Nothing changed" in embed.description, embed.description)

    # ---------------------------------------------------------------- blocked words
    rude = FakeMember(g, booster=True, name="rude")
    await service.create_role(rude, "Zorp Squad")
    inter = await press(view, "words", admin)
    modal = inter.response.modals[-1]
    check("Blocked words form: current lists, Block and Unblock", limits_problem(modal) is None
          and isinstance(modal.children[0], discord.ui.TextDisplay) and "Built-in" in modal.children[0].content)
    modal.block._value, modal.unblock._value = "zorp\nZORP\n" + "x" * 51, "mod"
    embed, view = panel_after(await submit(modal, admin))
    s = await storage.get_guild_settings(GID)
    check("block a word (repeats ignored), refuse a too-long one, switch a built-in off",
          "zorp" in s.blocked_words and "mod" in s.removed_default_words and embed.description.startswith("❌")
          and "too long" in embed.description, embed.description)
    check("  ...existing names using it are renamed and listed",
          (await record(rude)).name == "rude's role" and "Renamed 1" in embed.description, embed.description)
    modal.block._value, modal.unblock._value = "", ""
    embed, view = panel_after(await submit(modal, admin))
    check("empty Blocked words form: ❌ says what to type", embed.description.startswith("❌"), embed.description)
    modal.block._value, modal.unblock._value = "mod", "zorp"
    embed, view = panel_after(await submit(modal, admin))
    s = await storage.get_guild_settings(GID)
    check("turn the built-in back on and unblock the custom word",
          embed.description.startswith("✅") and "zorp" not in s.blocked_words and "mod" not in s.removed_default_words,
          embed.description)
    check("Blocked words text lists switched-off built-ins only when there are some",
          "switched off" not in cog_mod.blocked_words_text(s))

    # ---------------------------------------------------------------- members, remove, pending, import, refresh
    inter = await press(view, "members", admin)
    lst = inter.followup.sent[-1].view
    check("Members: list with a status filter", isinstance(lst, cog_mod.ListView) and lst.status_select is not None)
    lst.status_select._values = ["saved"]
    filt = Inter(admin, cog)
    await lst._on_status(filt)
    shown = filt.response.edits[-1]["embed"]
    check("filter: saved only", "· saved" in shown.title and all("Saved" in line for line in shown.description.splitlines()),
          shown.description)

    async def no_user(uid):
        raise discord.NotFound(NS(status=404, reason="x"), "Unknown User")

    target = Inter(admin, cog, fetch_user=no_user)
    check("remove: member and ID both given", (await cog._remove_target(target, [rude], "123"))[1] is not None)
    check("remove: neither given", "Pick a member" in (await cog._remove_target(target, [], " "))[1])
    check("remove: not a number", "isn't a user ID" in (await cog._remove_target(target, [], "abc"))[1])
    check("remove: unknown ID", (await cog._remove_target(target, [], "42"))[1] == "No Discord user has that ID.")
    check("remove: ID of a member here", (await cog._remove_target(target, [], str(rude.id)))[0] is rude)
    inter = await press(view, "remove", admin, fetch_user=no_user)
    modal = inter.response.modals[-1]
    check("Remove form within limits", limits_problem(modal) is None)
    modal.user._values, modal.user_id._value, modal.reason._value = [rude], "", "Rude name"
    inter = await submit(modal, admin, fetch_user=no_user)
    confirm = inter.followup.sent[-1]
    check("Remove: asks to confirm first, with the reason", isinstance(confirm.view, cog_mod.ConfirmView)
          and "Rude name" in confirm.embed.description and await record(rude) is not None)
    press_confirm = Inter(admin, cog)
    await confirm.view.confirm.callback(press_confirm)
    check("Remove confirmed: gone, DM sent", await record(rude) is None and rude.dms and "Rude name" in rude.dms[-1])

    inter = await press(view, "pending", admin)
    check("Pending removal with nothing pending", inter.followup.sent[-1].embed.title.endswith("Nothing Pending"))
    inter = await press(view, "import", admin)
    check("Import old roles with none: nothing to import", "Nothing to import" in inter.followup.sent[-1].embed.description)
    embed, view = panel_after(await press(view, "refresh", admin))
    check("Refresh: panel rebuilt without a result line", not embed.description.startswith(("✅", "❌")))

    # ================================================================== every form fits Discord's limits
    g = await new_guild(features=[FEATURE_GRADIENT])
    m = FakeMember(g, booster=True, name="limits")
    m.guild_permissions = discord.Permissions(manage_roles=True)
    await service.create_role(m, "Limits")
    _, mview = await cog_mod.member_panel(m, now)
    _, aview = await cog_mod.admin_panel(g, m.id, now)
    forms = []
    for view, actions in ((mview, ("rename", "color", "icon", "move", "lookup")),
                          (aview, ("anchor", "log", "channel", "cooldown", "allowed", "words", "remove"))):
        for action in actions:
            inter = await press(view, action, m)
            forms.append((action, limits_problem(inter.response.modals[-1]) if inter.response.modals else "no form"))
    check("every form: at most 5 items, labels and titles short enough, serialisable",
          all(problem is None for _, problem in forms), [f for f in forms if f[1]])

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

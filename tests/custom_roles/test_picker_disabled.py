"""Offline checks for CUSTOM_ROLES_PICKER_ENABLED=false: no Color picker button, no picker tips, no web server."""
import asyncio
import io
import os
import sys
import time

# Must be set before config is imported (it reads the switch once).
os.environ["CUSTOM_ROLES_PICKER_ENABLED"] = "false"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

from types import SimpleNamespace as NS  # noqa: E402

import discord  # noqa: E402
from PIL import Image  # noqa: E402

from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 10
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

    def __init__(self, user, cog):
        self.user, self.guild = user, user.guild
        self.client = NS(get_cog=lambda name: cog if name == "CustomRoles" else None, fetch_user=None)
        self.response, self.followup, self.edited = Response(), Followup(), []

    async def edit_original_response(self, **kw):
        self.edited.append(kw)


class FakeFlags:
    def __init__(self):
        self.animated, self.value = False, 0


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


def form_texts(modal):
    return [item.content for item in modal.children if isinstance(item, discord.ui.TextDisplay)]


def mentions_picker(texts):
    return any("Color picker" in text for text in texts)


async def main():
    import config
    import database as db
    from cogs.customization import custom_roles as cog_mod
    from cogs.customization.custom_roles import PANEL_MEMBER
    from helpers.custom_roles import FEATURE_GRADIENT, FEATURE_ICONS, service, storage
    from web.dashboard import DashboardWebServer

    check("switch read as off", config.CUSTOM_ROLES_PICKER_ENABLED is False, config.CUSTOM_ROLES_PICKER_ENABLED)

    q = db.execute_db_operation
    await db.init_custom_roles_tables()
    for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals",
                  "custom_role_archive_snoozes"):
        await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))

    g = FakeGuild(GID, (FEATURE_GRADIENT, FEATURE_ICONS))
    await service.set_anchor(g, g.anchor)
    await service.set_enabled(g, True)
    await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
    m = FakeMember(g, booster=True, name="booster")
    cog = cog_mod.CustomRoles(NS(custom_role_picker_ready=False))
    now = int(time.time())

    async def press(view, action, user):
        inter = Inter(user, cog)
        item = button(view, action)
        if await item.interaction_check(inter):
            await item.callback(inter)
        return inter

    # ================================================================== panel buttons
    _, view = await cog_mod.member_panel(m, now)
    inter = await press(view, "create", m)
    modal = inter.response.modals[-1]
    modal.name._value = "Picker Off Role"
    await modal.on_submit(Inter(m, cog))
    _, view = await cog_mod.member_panel(m, now)
    check("full panel: every button except Color picker",
          set(labels(view)) == {"rename", "color", "icon", "palette", "unwear", "move", "lookup"}, labels(view))

    # ================================================================== form tips
    color_modal = (await press(view, "color", m)).response.modals[-1]
    check("Color form: no Color picker tip", not mentions_picker(form_texts(color_modal)), form_texts(color_modal))
    plain = FakeGuild(GID, ())
    plain_member = FakeMember(plain, booster=True, name="no enhanced styles")
    plain_view = cog_mod._panel_view(PANEL_MEMBER, plain_member.id, now,
                                     [("color", "Color", discord.ButtonStyle.primary, 0)])
    plain_modal = (await press(plain_view, "color", plain_member)).response.modals[-1]
    texts = form_texts(plain_modal)
    check("Color form without Enhanced Role Styles: explains that, no picker tip",
          any(service.NO_GRADIENT_MESSAGE in text for text in texts) and not mentions_picker(texts), texts)
    icon_modal = (await press(view, "icon", m)).response.modals[-1]
    check("Icon form: no Color picker tip", not mentions_picker(form_texts(icon_modal)), form_texts(icon_modal))

    # ================================================================== icon upload message
    png = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 100, 50)).save(png, format="PNG")
    result = await cog_mod.apply_icon_form(m, [FakeAttachment(png.getvalue())], "", False)
    check("icon upload works and its message has no picker tip",
          result.ok and "Color picker" not in result.message, (result.ok, result.message))

    # ================================================================== a panel opened before the switch
    stale = cog_mod._panel_view(PANEL_MEMBER, m.id, now, [("picker", "Color picker", discord.ButtonStyle.secondary, 1)])
    inter = await press(stale, "picker", m)
    sent = [s.embed for s in inter.followup.sent if s.embed is not None]
    check("old Color picker button: polite refusal, no link",
          len(sent) == 1 and sent[0].title.endswith("Can't Open The Picker")
          and all(s.view is None for s in inter.followup.sent), [(e.title, e.description) for e in sent])
    check("service explains why", "turned off" in (service.picker_link_problem() or ""), service.picker_link_problem())

    # ================================================================== web server
    bot = NS()
    server = DashboardWebServer(bot)
    if server.configured:
        check("web server: dashboard is configured here, so this check doesn't apply", True)
    else:
        await server.start()
        check("web server: not started (no dashboard, picker off)",
              server.runner is None and not getattr(bot, "custom_role_picker_ready", False))

    await q("c", "DELETE FROM custom_role_records WHERE guild_id = ?", (GID,))
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

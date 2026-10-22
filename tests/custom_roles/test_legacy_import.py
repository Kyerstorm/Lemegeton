"""Offline checks for old /nitro-role-set roles: /custom-role-admin import-legacy, self-adoption, and no
automatic archiving while Custom Roles is off."""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from fakes import FakeGuild, FakeMember  # noqa: E402

GID = 10
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


class Followup:
    def __init__(self):
        self.sent = []

    async def send(self, embed=None, view=None, ephemeral=None, wait=False):
        self.sent.append((embed, view))
        return SimpleNamespace(edit=self._edit)

    async def _edit(self, **kw):
        self.sent.append((kw.get("embed"), kw.get("view")))


class Response:
    def __init__(self):
        self.edits = []

    async def defer(self, **kw):
        pass

    async def edit_message(self, **kw):
        self.edits.append(kw)

    async def send_message(self, *args, **kw):
        self.edits.append(kw)


async def main():
    import database as db
    from helpers.custom_roles import service, storage

    q = db.execute_db_operation
    await db.init_booster_roles_table()
    await db.init_custom_roles_tables()
    service.ARCHIVE_BATCH_PAUSE = 0
    service.pending_view_factory = lambda pid: f"VIEW-{pid}"

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals", "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        await q("c", "DELETE FROM booster_roles WHERE guild_id = ?", (GID,))
        service._skip_warned.clear()
        service._recent_archives.clear()

    async def new_guild(enabled=True):
        await reset()
        g = FakeGuild(GID)
        await service.set_anchor(g, g.anchor, service.PLACE_ABOVE)
        await service.set_enabled(g, enabled)
        await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
        return g

    async def old_role(member_id, role_id):
        await db.set_booster_role(member_id, GID, role_id)

    async def legacy_count():
        return (await q("c", "SELECT COUNT(*) FROM booster_roles WHERE guild_id = ?", (GID,), fetch_type="one"))[0]

    async def record(uid):
        return await storage.get_custom_role(GID, uid)

    def below_bot(g, name, colour=0):
        return g.add_role(name, g.bot_role.position, colour)  # lands just below the bot's role

    # ================================================================== no automatic import
    g = await new_guild()
    m = FakeMember(g, booster=True, name="early")
    r = below_bot(g, "Early Old Role")
    await old_role(m.id, r.id)
    await db.init_custom_roles_tables()  # startup: the table setup used to copy booster_roles here
    check("startup no longer copies old roles into Custom Roles", await record(m.id) is None)

    # ================================================================== the preview (plan)
    g = await new_guild()
    allowed = below_bot(g, "Allowed")
    await service.add_allowed_role(g, allowed)
    a = FakeMember(g, booster=True, name="a")
    a_role = below_bot(g, "A's Old Role", 0xAA00FF)
    a_role.secondary_colour = discord.Colour(0x00FFAA)
    h = FakeMember(g, roles=[allowed], name="h")
    h_role = below_bot(g, "H's Old Role", 0x123456)
    b = FakeMember(g, booster=True, name="b")  # their old role was deleted
    c = FakeMember(g, name="c")  # in the server, doesn't qualify
    c_role = below_bot(g, "C's Old Role", 0x444444)
    d_id = 999001  # left the server
    d_role = below_bot(g, "D's Old Role")
    e = FakeMember(g, booster=True, name="e")
    e_role = g.add_role("E's Old Role", g.bot_role.position + 1)  # above the bot's role
    f = FakeMember(g, booster=True, name="f")
    f_old = below_bot(g, "F's Old Role")
    gm = FakeMember(g, booster=True, name="gm")
    gm_role = below_bot(g, "Mod-ish Old Role")
    gm_role.permissions = discord.Permissions(kick_members=True)
    for uid, rid in ((a.id, a_role.id), (h.id, h_role.id), (b.id, 123456789), (c.id, c_role.id), (d_id, d_role.id),
                     (e.id, e_role.id), (f.id, f_old.id), (gm.id, gm_role.id)):
        await old_role(uid, rid)
    f_new = await service.create_role(f, "F New")
    check("setup: f's old role is adopted instead of a second role", f_new.ok and (await record(f.id)).role_id == f_old.id,
          f_new.message)
    # a member who already had both roles before this change: point f's custom role record at a separate role
    f_custom = below_bot(g, "F's Custom Role")
    await storage.update_custom_role(GID, f.id, role_id=f_custom.id, name=f_custom.name)

    plan = await service.plan_legacy_import(g)
    take = {e_.user_id for e_ in plan.take_over}
    others = {e_.user_id: e_.reason for e_ in plan.not_qualifying}
    skipped = {e_.user_id: e_.reason for e_ in plan.skipped}
    check("preview: total counts every old role", plan.total == 8, plan.total)
    check("preview: qualifying members with a live old role are taken over (booster and allowed role)", take == {a.id, h.id}, take)
    check("preview: members who don't qualify are listed separately, with why",
          others == {c.id: service.LEGACY_NOT_QUALIFYING, d_id: service.LEGACY_LEFT}, others)
    check("preview: deleted old role skipped", skipped.get(b.id) == service.LEGACY_ROLE_GONE, skipped)
    check("preview: role above the bot skipped", "highest role" in skipped.get(e.id, ""), skipped)
    check("preview: role with moderation permissions skipped", "moderation" in skipped.get(gm.id, ""), skipped)
    check("preview: member who already has a separate live custom role skipped",
          skipped.get(f.id) == service.LEGACY_HAS_CUSTOM_ROLE, skipped)
    check("not imported yet = old roles that still exist and aren't custom roles", plan.not_imported == 7, plan.not_imported)

    from cogs.customization.custom_roles import LegacyImportView, CustomRoles, legacy_preview_text, settings_embed
    text = legacy_preview_text(plan)
    check("preview text: all three parts, counts and the no-new-roles promise",
          "Found **8**" in text and "Will be taken over (2)" in text and "Members who don't qualify (2)" in text
          and "Skipped (4)" in text and "no new roles are made" in text and "stay untouched unless" in text, text)
    view = LegacyImportView(1, plan, None)
    labels = [child.label for child in view.children]
    check("preview buttons: take over / take over and archive / cancel",
          labels == ["Take over 2", "Take over 2 and archive 2", "Cancel"], labels)

    # ================================================================== nothing automatic touches old roles
    roles_before = {r.id for r in g.roles}
    positions_before = {r.id: r.position for r in g.roles}
    await service.reconcile_guild(g)
    check("regular check (enabled) never touches old roles that aren't imported",
          not g.deleted and {r.id for r in g.roles} == roles_before and await record(a.id) is None)

    # ================================================================== import: take over only
    inter_admin = SimpleNamespace(id=4242, mention="<@4242>")
    report = await service.import_legacy(g, inter_admin, {a.id, h.id}, set())
    ra, rh = await record(a.id), await record(h.id)
    check("import: takes over the old roles (record points at the same role)",
          ra.role_id == a_role.id and rh.role_id == h_role.id and ra.status == rh.status == "active")
    check("import: keeps name and colors (gradient read from the role)",
          ra.name == "A's Old Role" and ra.color_mode == "gradient" and ra.primary_color == 0xAA00FF
          and ra.secondary_color == 0x00FFAA and rh.color_mode == "solid" and rh.primary_color == 0x123456, ra)
    check("import: no role created, deleted, renamed or moved",
          {r.id for r in g.roles} == roles_before and not g.deleted and a_role.name == "A's Old Role"
          and {r.id: r.position for r in g.roles} == positions_before)
    check("import: members who don't qualify left untouched without the archive choice",
          await record(c.id) is None and await record(d_id) is None and g.get_role(c_role.id) and g.get_role(d_role.id))
    check("import: the old table is never changed", await legacy_count() == 8)
    check("import: report and log channel", {u for u, _ in report.taken_over} == {a.id, h.id}
          and "imported old" in g.channel.texts()[-1], g.channel.texts()[-1:])
    check("import: not a 'change' for the cooldown", ra.last_changed_at is None)

    plan = await service.plan_legacy_import(g)
    check("running the preview again: taken-over roles show as already imported",
          {e_.user_id for e_ in plan.skipped if e_.reason == service.LEGACY_ALREADY_IMPORTED} == {a.id, h.id}
          and not plan.take_over and plan.not_imported == 5, plan.not_imported)

    # ================================================================== import: archive the ones who don't qualify
    report = await service.import_legacy(g, inter_admin, set(), {c.id, d_id})
    rc, rd = await record(c.id), await record(d_id)
    check("archive part: roles of members who don't qualify archived (deleted, settings saved)",
          rc.status == rd.status == "saved" and c_role.id in g.deleted and d_role.id in g.deleted
          and rc.name == "C's Old Role" and rc.primary_color == 0x444444, (rc, g.deleted))
    check("archive part: only the confirmed ones", set(g.deleted) == {c_role.id, d_role.id}, g.deleted)
    check("archive part: old table still unchanged", await legacy_count() == 8)
    check("archive part: report", report.archive is not None and len(report.archive.archived) == 2)

    # stale preview: a member who qualifies by the time the admin confirms isn't archived
    g = await new_guild()
    late = FakeMember(g, name="late")
    late_role = below_bot(g, "Late Old Role")
    await old_role(late.id, late_role.id)
    plan = await service.plan_legacy_import(g)
    late.premium_since = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    report = await service.import_legacy(g, inter_admin, set(), {e_.user_id for e_ in plan.not_qualifying})
    check("confirm after the member started boosting: nothing archived", not g.deleted and await record(late.id) is None)

    # ================================================================== settings: Problems line
    g = await new_guild()
    p = FakeMember(g, booster=True, name="p")
    p_role = below_bot(g, "P's Old Role")
    await old_role(p.id, p_role.id)
    cog = CustomRoles.__new__(CustomRoles)
    i = SimpleNamespace(guild=g, user=SimpleNamespace(id=4242), response=Response(), followup=Followup())
    embed = await settings_embed(g)
    problems = next((fl.value for fl in embed.fields if fl.name == "Problems"), "")
    check("settings: 'Old /nitro-role-set roles not imported yet: 1' under Problems",
          "Old /nitro-role-set roles not imported yet: 1" in problems and "Import old roles" in problems, problems)

    # ================================================================== Import old roles (preview, then a button)
    i = SimpleNamespace(guild=g, user=SimpleNamespace(id=4242, mention="<@4242>"), response=Response(), followup=Followup())
    await cog._send_import_preview(i)
    embed, view = i.followup.sent[-1]
    check("command: preview first, nothing changed yet", "Will be taken over (1)" in embed.description
          and view is not None and await record(p.id) is None, embed.description)
    stranger = SimpleNamespace(user=SimpleNamespace(id=1), response=Response())
    check("command: only the admin who ran it can press", not await view.interaction_check(stranger))
    edits = []
    press = SimpleNamespace(user=SimpleNamespace(id=4242), response=Response(),
                            edit_original_response=lambda **kw: _record_edit(edits, kw))
    await view.children[0].callback(press)
    check("command: 'Take over 1' imports and reports", (await record(p.id)).role_id == p_role.id
          and "Took over **1**" in edits[-1]["embed"].description, edits[-1]["embed"].description if edits else None)
    problems = next((fl.value for fl in (await settings_embed(g)).fields if fl.name == "Problems"), "")
    check("settings: the line disappears once imported", "not imported yet" not in problems, problems)

    g.chunked, g.chunk_behaviour = False, "fail"
    i = SimpleNamespace(guild=g, user=SimpleNamespace(id=4242), response=Response(), followup=Followup())
    await cog._send_import_preview(i)
    check("command: refuses when the member list can't be loaded", "can't check who qualifies" in i.followup.sent[-1][0].description
          and i.followup.sent[-1][1] is None)

    # ================================================================== self-adoption: never stack
    g = await new_guild()
    x = FakeMember(g, booster=True, name="x")
    x_role = below_bot(g, "X Old")
    await old_role(x.id, x_role.id)
    count = len(g.roles)
    r = await service.create_role(x, "Brand New")
    rx = await record(x.id)
    check("/custom-role role with an old role: takes it over instead of creating a second",
          r.ok and "already had a booster role" in r.message and rx.role_id == x_role.id and len(g.roles) == count
          and x_role.name == "X Old", r.message)
    r = await service.create_role(x, "Again")
    check("/custom-role role again: 'already exists', still one role", not r.ok and "already exists" in r.message and len(g.roles) == count)
    check("self-adoption logged", "took over their old" in g.channel.texts()[-1])

    y = FakeMember(g, booster=True, name="y")
    y_role = below_bot(g, "Y Old")
    await old_role(y.id, y_role.id)
    count = len(g.roles)
    r = await service.rename(y, "Y Renamed")
    check("another /custom-role command (rename) adopts first, then renames the same role",
          r.ok and (await record(y.id)).role_id == y_role.id and y_role.name == "Y Renamed" and len(g.roles) == count, r.message)

    z = FakeMember(g, booster=True, name="z")
    z_role = below_bot(g, "Z Old")
    await old_role(z.id, z_role.id)
    check("the color picker's check (precheck) adopts too", await service.precheck(z) is None
          and (await record(z.id)).role_id == z_role.id)

    w = FakeMember(g, booster=True, name="w")
    w_role = g.add_role("W Old", g.bot_role.position + 1)
    await old_role(w.id, w_role.id)
    count = len(g.roles)
    r = await service.create_role(w, "W New")
    check("old role I can't take over: refused, no second role", not r.ok and "won't make you a second one" in r.message
          and len(g.roles) == count and await record(w.id) is None, r.message)

    v = FakeMember(g, booster=True, name="v")
    await old_role(v.id, 987654321)  # deleted long ago
    r = await service.create_role(v, "V New")
    check("old role already deleted: a new custom role is made as usual", r.ok and (await record(v.id)).name == "V New", r.message)

    u = FakeMember(g, booster=True, name="u")
    await service.create_role(u, "U Custom")
    rec = await record(u.id)
    g.roles.remove(g.get_role(rec.role_id))
    await storage.update_custom_role(GID, u.id, status="saved", role_id=None)
    u_role = below_bot(g, "U Old")
    await old_role(u.id, u_role.id)
    count = len(g.roles)
    r = await service.create_role(u, "U Again")
    check("saved custom role record + live old role: the old role is taken over, not a restore next to it",
          r.ok and (await record(u.id)).role_id == u_role.id and (await record(u.id)).status == "active"
          and len(g.roles) == count, r.message)

    n = FakeMember(g, name="n")  # doesn't qualify
    n_role = below_bot(g, "N Old")
    await old_role(n.id, n_role.id)
    check("member who doesn't qualify: normal refusal, old role not touched",
          not (await service.create_role(n, "N")).ok and await record(n.id) is None and g.get_role(n_role.id))

    # ================================================================== nothing archived automatically while off
    g = await new_guild(enabled=False)
    gone = FakeMember(g, booster=True, name="gone")
    await storage.update_guild_settings(GID, enabled=True)
    await service.create_role(gone, "Gone Role")
    await storage.update_guild_settings(GID, enabled=False)
    gone.premium_since = None  # stopped boosting while Custom Roles is off
    await service.reconcile_guild(g)
    check("regular check while off: nothing archived or deleted", not g.deleted and (await record(gone.id)).status == "active")
    out = await service.archive_automatically(g, {gone.id: "stopped boosting"}, "test")
    check("member events while off: nothing archived", out is None and not g.deleted)
    await storage.update_guild_settings(GID, enabled=True)
    await service.reconcile_guild(g)
    check("once enabled, the regular check archives as usual", (await record(gone.id)).status == "saved" and g.deleted)

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


async def _record_edit(store, kw):
    store.append(kw)


asyncio.run(main())

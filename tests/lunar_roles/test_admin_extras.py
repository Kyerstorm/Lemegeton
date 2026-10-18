"""Offline Milestone 5 checks: command channel, cooldown, position, restore spot, admin list and remove."""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from fakes import FakeGuild, FakeMember, forbidden  # noqa: E402

GID = 6
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


class RecordingGuild(FakeGuild):
    """Records which roles each edit_role_positions call touched."""

    def __init__(self, gid, features=()):
        super().__init__(gid, features)
        self.position_calls = []

    async def edit_role_positions(self, positions, reason=None):
        self.position_calls.append({r.id: p for r, p in positions.items()})
        await super().edit_role_positions(positions, reason)


def order(guild):
    """Role names bottom to top (without @everyone)."""
    return [r.name for r in sorted((r for r in guild.roles if not r.is_default()), key=lambda r: (r.position, r.id))]


class Response:
    def __init__(self):
        self.sent, self.edits, self.done = [], [], False

    async def send_message(self, *args, **kw):
        self.sent.append(kw)
        self.done = True

    async def defer(self, **kw):
        self.done = True

    async def edit_message(self, **kw):
        self.edits.append(kw)
        self.done = True

    def is_done(self):
        return self.done


async def main():
    import database as db
    from helpers.lunar_roles import ADMIN_GROUP, COMMAND_GROUP, service, storage

    q = db.execute_db_operation
    await db.init_lunar_roles_tables()
    service.ARCHIVE_BATCH_PAUSE = 0
    service.pending_view_factory = lambda pid: f"VIEW-{pid}"

    async def reset():
        for table in ("lunar_custom_roles", "lunar_guild_settings", "lunar_pending_removals", "lunar_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        service._skip_warned.clear()
        service._recent_archives.clear()

    async def new_guild(features=()):
        await reset()
        g = RecordingGuild(GID, features)
        await service.set_anchor(g, g.anchor)
        await service.set_enabled(g, True)
        await storage.update_guild_settings(GID, log_channel_id=g.channel.id)
        return g

    async def record(member):
        return await storage.get_custom_role(GID, member.id)

    async def age_change(member, seconds):
        await q("c", "UPDATE lunar_custom_roles SET last_changed_at = CURRENT_TIMESTAMP - make_interval(secs => ?) "
                     "WHERE guild_id = ? AND user_id = ?", (seconds, GID, member.id))

    # ------------------------------------------------------------------ helpers
    check("format_duration", [service.format_duration(s) for s in (0, 45, 90, 3600, 86400, 3725)]
          == ["0s", "45s", "1m 30s", "1h", "1d", "1h 2m 5s"])
    g = await new_guild()
    check("cooldown 86401 refused", not (await service.set_cooldown(g, 86401)).ok)
    check("cooldown -1 refused", not (await service.set_cooldown(g, -1)).ok)
    r = await service.set_cooldown(g, 120)
    check("cooldown 120 saved", r.ok and (await storage.get_guild_settings(GID)).cooldown_seconds == 120 and "2m" in r.message, r.message)
    r = await service.set_cooldown(g, 0)
    check("cooldown 0 = off", r.ok and "off" in r.message and (await storage.get_guild_settings(GID)).cooldown_seconds == 0)

    # ------------------------------------------------------------------ command channel
    g = await new_guild()
    allowed = SimpleNamespace(id=9101, guild=g, mention="<#9101>", parent_id=None)
    other = SimpleNamespace(id=9102, guild=g, mention="<#9102>", parent_id=None)
    thread = SimpleNamespace(id=9103, guild=g, mention="<#9103>", parent_id=9101)
    other_thread = SimpleNamespace(id=9104, guild=g, mention="<#9104>", parent_id=9102)
    g.get_channel = lambda cid: {9101: allowed, 9102: other, g.channel.id: g.channel}.get(cid)
    settings = await storage.get_guild_settings(GID)
    check("no command channel: anywhere", service.command_channel_problem(other, settings) is None)
    r = await service.set_command_channel(g, allowed)
    settings = r.data
    check("set command channel", r.ok and settings.command_channel_id == 9101)
    check("allowed in the channel", service.command_channel_problem(allowed, settings) is None)
    check("allowed in its threads", service.command_channel_problem(thread, settings) is None)
    msg = service.command_channel_problem(other, settings)
    check("refused elsewhere, names the channel", msg is not None and "<#9101>" in msg, msg)
    check("refused in other channels' threads", service.command_channel_problem(other_thread, settings) is not None)
    g.get_channel = lambda cid: {9102: other, g.channel.id: g.channel}.get(cid)  # channel deleted
    check("deleted command channel lifts the restriction", service.command_channel_problem(other, settings) is None)
    g.get_channel = lambda cid: {9101: allowed, 9102: other, g.channel.id: g.channel}.get(cid)

    from cogs.customization.lunar_roles import LunarRoles, ListView, PaletteView
    cog = LunarRoles.__new__(LunarRoles)

    def interaction(group, channel, user=None):
        root = SimpleNamespace(name=group)
        return SimpleNamespace(command=SimpleNamespace(root_parent=root), guild=g, channel=channel,
                               response=Response(), user=user)

    i = interaction(COMMAND_GROUP, other)
    ok = await cog.interaction_check(i)
    check("cog check blocks /lunar in the wrong channel with a reply",
          not ok and i.response.sent and i.response.sent[0]["ephemeral"] and "<#9101>" in i.response.sent[0]["embed"].description)
    i = interaction(COMMAND_GROUP, thread)
    check("cog check allows /lunar in a thread of the channel", await cog.interaction_check(i) and not i.response.sent)
    i = interaction(ADMIN_GROUP, other)
    check("cog check never blocks /lunar-admin", await cog.interaction_check(i) and not i.response.sent)
    r = await service.set_command_channel(g, None)
    check("clearing the command channel", r.ok and r.data.command_channel_id is None)
    i = interaction(COMMAND_GROUP, other)
    check("cleared: /lunar works anywhere", await cog.interaction_check(i))

    # ------------------------------------------------------------------ cooldown
    g = await new_guild(features=["ROLE_ICONS"])
    await service.set_cooldown(g, 60)
    m = FakeMember(g, booster=True, name="cool")
    r = await service.create_role(m, "Cool Role")
    check("create works with cooldown on", r.ok, r.message)
    check("creating doesn't start the cooldown", await storage.seconds_since_change(GID, m.id) is None)
    r = await service.rename(m, "Cooler Role")
    check("first change right after create allowed", r.ok, r.message)
    since = await storage.seconds_since_change(GID, m.id)
    check("change stamps last_changed_at (DB clock)", since is not None and 0 <= since < 5, since)
    for label, call in (
        ("rename", lambda: service.rename(m, "Coolest")),
        ("color set", lambda: service.set_colors(m, "solid", 0x112233)),
        ("icon emoji", lambda: service.set_icon(m, emoji="🌙")),
    ):
        r = await call()
        check(f"{label} blocked during cooldown with a countdown", not r.ok and "<t:" in r.message and ":R>" in r.message, r.message)
    check("blocked change didn't touch the role", g.get_role((await record(m)).role_id).name == "Cooler Role")
    r = await service.set_colors(m, "solid", 0x112233, check_cooldown=False)
    check("check_cooldown=False (later palette pick) goes through", r.ok, r.message)
    await age_change(m, 61)
    r = await service.set_icon(m, emoji="🌙")
    check("allowed again after the cooldown", r.ok, r.message)
    r = await service.remove_icon(m)
    check("remove icon blocked during cooldown", not r.ok and "<t:" in r.message, r.message)
    await age_change(m, 61)
    check("remove icon allowed after it", (await service.remove_icon(m)).ok)
    await age_change(m, 61)
    r = await service.rename(m, "Admin")
    check("failed (filtered) change after cooldown doesn't stamp", not r.ok and (await storage.seconds_since_change(GID, m.id)) > 60)
    r = await service.assign(m)
    check("assign/unassign aren't blocked by cooldown",
          (await service.unassign(m)).ok and (await service.assign(m)).ok)
    await service.set_cooldown(g, 0)
    check("cooldown 0: back-to-back changes fine",
          (await service.rename(m, "One")).ok and (await service.rename(m, "Two")).ok)

    # restore doesn't count as a change
    await service.set_cooldown(g, 60)
    await q("c", "UPDATE lunar_custom_roles SET last_changed_at = NULL WHERE guild_id = ? AND user_id = ?", (GID, m.id))
    m.premium_since = None
    await service.archive(g, m.id, "test")
    m.premium_since = discord.utils.utcnow()
    r = await service.restore(m, dm=False)
    check("restore works", r.ok, r.message)
    check("restore doesn't start the cooldown", await storage.seconds_since_change(GID, m.id) is None)
    check("change right after restore allowed", (await service.rename(m, "Back Again")).ok)

    # palette: only the first successful pick in a menu checks the cooldown
    await age_change(m, 61)

    class Inter:
        def __init__(self, user):
            self.user, self.response = user, Response()

        async def edit_original_response(self, **kw):
            pass

    view = PaletteView(m, [0xFF0000, 0x00FF00, 0x0000FF], gradient_ok=False)
    view.primary_select._values = ["FF0000"]
    await view._on_primary(Inter(m))
    first = view.last_result
    view.primary_select._values = ["00FF00"]
    await view._on_primary(Inter(m))
    check("palette: first pick checks cooldown and passes", first.ok, first.message)
    check("palette: second pick in the same menu isn't blocked", view.last_result.ok, view.last_result.message)
    view2 = PaletteView(m, [0xFF0000, 0x00FF00], gradient_ok=False)
    view2.primary_select._values = ["FF0000"]
    await view2._on_primary(Inter(m))
    check("palette: a new menu checks the cooldown again", not view2.last_result.ok and "<t:" in view2.last_result.message,
          view2.last_result.message)
    await service.set_cooldown(g, 0)

    # ------------------------------------------------------------------ position
    g = await new_guild()
    a, b, c = (FakeMember(g, booster=True, name=n) for n in ("amy", "ben", "cat"))
    for who, name in ((a, "A"), (b, "B"), (c, "C")):
        await service.create_role(who, name)
    check("setup order A < B < C < anchor", order(g) == ["A", "B", "C", "Anchor", "Lunar Test"], order(g))
    ra, rb, rc = [g.get_role((await record(x)).role_id) for x in (a, b, c)]

    g.position_calls.clear()
    r = await service.move(a, rc, "above")
    check("move A above C (up)", r.ok and order(g) == ["B", "C", "A", "Anchor", "Lunar Test"], (r.message, order(g)))
    check("only the span moved", all(rid in {ra.id, rb.id, rc.id} for call in g.position_calls for rid in call), g.position_calls)
    check("move stamps the cooldown clock", await storage.seconds_since_change(GID, a.id) is not None)
    r = await service.move(a, rb, "below")
    check("move A below B (down)", r.ok and order(g) == ["A", "B", "C", "Anchor", "Lunar Test"], (r.message, order(g)))
    positions = [x.position for x in g.roles if not x.is_default()]
    check("no two roles share a position after moving down", len(positions) == len(set(positions)), positions)
    g.position_calls.clear()
    r = await service.move(a, rb, "below")
    check("already there: no Discord call", r.ok and not g.position_calls, g.position_calls)
    check("move logged with both role names as text",
          any("moved" in t and "(`A`)" in t and "(`B`)" in t for t in g.channel.texts()))

    r = await service.move(a, ra, "above")
    check("refuses own role", not r.ok and "own role" in r.message, r.message)
    r = await service.move(a, g.anchor, "above")
    check("refuses a non-custom role", not r.ok and "isn't a Lunar role" in r.message, r.message)
    r = await service.move(a, rb, "sideways")
    check("refuses a bad direction", not r.ok)
    c.premium_since = None
    await service.archive(g, c.id, "test")
    r = await service.move(a, rc, "above")
    check("refuses a saved (deleted) custom role", not r.ok and "isn't a Lunar role" in r.message, r.message)
    c.premium_since = discord.utils.utcnow()
    outsider = FakeMember(g, name="outsider")
    r = await service.move(outsider, rb, "above")
    check("non-booster refused", not r.ok and "boost" in r.message.lower(), r.message)
    nobody = FakeMember(g, booster=True, name="norole")
    r = await service.move(nobody, rb, "above")
    check("no role yet refused", not r.ok and "/lunar role" in r.message, r.message)
    await service.set_cooldown(g, 60)
    r = await service.move(a, rb, "above")
    check("move blocked during cooldown", not r.ok and "<t:" in r.message, r.message)
    await service.set_cooldown(g, 0)

    # moves with gaps in Discord's position numbers never touch roles outside the span
    g2 = RecordingGuild(GID)
    high = g2.add_role("High", 3)  # above the bot
    x1, x2, x3 = (g2.add_role(n, 1) for n in ("X1", "X2", "X3"))
    for role, pos in ((x1, 1), (x2, 3), (x3, 5), (g2.anchor, 7), (g2.bot_role, 9), (high, 10)):
        role.position = pos
    after = await service._place_next_to(g2, x1, x3.id, "above", "test")
    check("gaps: X1 moved above X3", order(g2)[:3] == ["X2", "X3", "X1"], order(g2))
    touched = set(g2.position_calls[-1])
    check("gaps: bot role and roles above it untouched", touched <= {x1.id, x2.id, x3.id} and high.position == 10
          and g2.bot_role.position == 9, g2.position_calls)
    check("gaps: span reuses its own numbers", sorted(after[i] for i in (x1.id, x2.id, x3.id)) == [1, 3, 5], after)

    # ------------------------------------------------------------------ restore goes back near its old spot
    g = await new_guild()
    a, b, c = (FakeMember(g, booster=True, name=n) for n in ("amy", "ben", "cat"))
    for who, name in ((a, "A"), (b, "B"), (c, "C")):
        await service.create_role(who, name)
    b.premium_since = None
    await service.archive(g, b.id, "test")
    check("archive saved a position hint", (await record(b)).position_hint is not None)
    b.premium_since = discord.utils.utcnow()
    await service.restore(b, dm=False)
    check("middle role restored between A and C", order(g)[:3] == ["A", "B", "C"], order(g))
    c.premium_since = None
    await service.archive(g, c.id, "test")
    c.premium_since = discord.utils.utcnow()
    await service.restore(c, dm=False)
    check("top role restored on top", order(g)[:3] == ["A", "B", "C"], order(g))
    a.premium_since = None
    await service.archive(g, a.id, "test")
    a.premium_since = discord.utils.utcnow()
    r = await service.create_role(a, "A")  # /lunar role with saved settings also uses the hint
    check("bottom role restored at the bottom (via /lunar role)", r.ok and order(g)[:3] == ["A", "B", "C"], order(g))
    await service.move(c, (g.get_role((await record(a)).role_id)), "below")  # C now at the bottom
    check("setup: C moved to the bottom", order(g)[:3] == ["C", "A", "B"], order(g))
    c.premium_since = None
    await service.archive(g, c.id, "test")
    c.premium_since = discord.utils.utcnow()
    await service.restore(c, dm=False)
    check("moved role comes back where it was moved to", order(g)[:3] == ["C", "A", "B"], order(g))

    g = await new_guild()
    solo = FakeMember(g, booster=True, name="solo")
    await service.create_role(solo, "Solo")
    solo.premium_since = None
    await service.archive(g, solo.id, "test")
    solo.premium_since = discord.utils.utcnow()
    await service.restore(solo, dm=False)
    check("no other custom roles: anchor decides", order(g) == ["Solo", "Anchor", "Lunar Test"], order(g))

    # ------------------------------------------------------------------ /lunar-admin list
    g = await new_guild()
    admin = FakeMember(g, name="admin")
    members = [FakeMember(g, booster=True, name=f"m{n:02d}") for n in range(23)]
    for n, who in enumerate(members):
        await service.create_role(who, f"Role {n:02d}")
    for who in members[:5]:
        who.premium_since = None
        await service.archive(g, who.id, "test")
    gone = g.get_role((await record(members[5])).role_id)
    gone.guild.roles.remove(gone)
    await service.get_info(members[5], members[5])  # notices it's gone -> missing
    pending = await storage.create_pending(GID, [members[6].id], "test")
    await storage.snooze_users(GID, [members[7].id])

    entries = await service.list_entries(g)
    statuses = [e.record.status for e in entries]
    check("list has everyone", len(entries) == 23)
    check("list order: active, then missing, then saved",
          statuses == ["active"] * 17 + ["missing"] + ["saved"] * 5, statuses)
    active_positions = [e.role.position for e in entries if e.record.status == "active"]
    check("active sorted highest role first", active_positions == sorted(active_positions, reverse=True))
    check("pending and snoozed flagged",
          next(e for e in entries if e.record.user_id == members[6].id).pending
          and next(e for e in entries if e.record.user_id == members[7].id).snoozed)
    check("filter: saved only", [e.record.status for e in await service.list_entries(g, "saved")] == ["saved"] * 5)

    view = ListView(admin.id, entries, "Lunar Roles")
    check("23 entries -> 3 pages, Previous disabled", view.pages == 3 and view.previous.disabled and not view.next.disabled)
    embed = view.build_embed()
    check("page 1 shows 10 lines and a footer", embed.description.count("\n") == 9 and "Page 1 of 3" in embed.footer.text)
    i = SimpleNamespace(user=admin, response=Response())
    await view.next.callback(i)
    await view.next.callback(i)
    check("Next to the last page disables Next", view.page == 2 and view.next.disabled and not view.previous.disabled)
    last = i.response.edits[-1]["embed"]
    check("last page shows the remaining 3", last.description.count("\n") == 2 and "Page 3 of 3" in last.footer.text)
    check("saved rows show their saved name", "**Role 04**" in last.description, last.description)
    page_texts = []
    v = ListView(admin.id, entries, "x")
    for p in range(v.pages):
        v.page = p
        page_texts.append(v.build_embed().description)
    everything = "\n".join(page_texts)
    check("⏳ and 💤 marks appear", "⏳" in everything and "💤" in everything)
    check("missing row shows as Missing", "Missing" in everything)
    stranger = SimpleNamespace(id=1, user=SimpleNamespace(id=999), response=Response())
    check("only the invoker can page", not await view.interaction_check(stranger) and stranger.response.sent)
    check("empty list", "No custom roles" in ListView(admin.id, [], "x").build_embed().description
          and ListView(admin.id, [], "x").pages == 1)
    await storage.resolve_pending(pending.id, storage.PENDING_CANCELLED, None)

    # ------------------------------------------------------------------ /lunar-admin remove
    g = await new_guild()
    admin = FakeMember(g, name="admin")
    quiet = FakeMember(g, booster=True, name="quiet")
    await service.create_role(quiet, "Quiet")
    quiet_role = g.get_role((await record(quiet)).role_id)
    r = await service.admin_remove(g, quiet, admin)
    check("remove without reason", r.ok and "weren't told" in r.message, r.message)
    check("Discord role deleted", quiet_role.id in g.deleted)
    check("record deleted (nothing kept)", await record(quiet) is None)
    check("no DM without a reason", quiet.dms == [])
    check("remove logged", any("removed" in t and "Quiet" in t for t in g.channel.texts()))

    loud = FakeMember(g, booster=True, name="loud")
    await service.create_role(loud, "Loud")
    r = await service.admin_remove(g, loud, admin, "Rude name")
    check("remove with reason DMs the member", r.ok and loud.dms and "Rude name" in loud.dms[0] and "Loud" in loud.dms[0], loud.dms)
    check("reason in the log", any("Rude name" in t for t in g.channel.texts()))

    closed = FakeMember(g, booster=True, name="closed")
    await service.create_role(closed, "Closed")

    async def no_dm(content=None, embed=None):
        raise forbidden()
    closed.send = no_dm
    r = await service.admin_remove(g, closed, admin, "Spam")
    check("DMs closed: still removed, says it couldn't DM", r.ok and r.data[1] is False and "couldn't DM" in r.message, r.message)

    saved = FakeMember(g, booster=True, name="saved")
    await service.create_role(saved, "Saved One")
    saved.premium_since = None
    await service.archive(g, saved.id, "test")
    saved.leave()
    r = await service.admin_remove(g, saved, admin)
    check("removes a saved record of someone who left", r.ok and await record(saved) is None, r.message)
    r = await service.admin_remove(g, saved, admin)
    check("nothing to remove", not r.ok and "doesn't have" in r.message)

    high = FakeMember(g, booster=True, name="high")
    await service.create_role(high, "High")
    high_role = g.get_role((await record(high)).role_id)
    high_role.position = g.bot_role.position + 1
    r = await service.admin_remove(g, high, admin, "x")
    check("role above the bot: refused, record kept, no DM", not r.ok and await record(high) is not None and not high.dms, r.message)
    high_role.position = 1
    high_role.fail_delete = True
    r = await service.admin_remove(g, high, admin)
    check("Discord refuses delete: record kept", not r.ok and await record(high) is not None, r.message)
    high_role.fail_delete = False

    # pending removals and snoozes
    p1, p2 = (FakeMember(g, booster=True, name=n) for n in ("p1", "p2"))
    for who in (p1, p2):
        await service.create_role(who, f"Pend {who.name}")
    pend = await service._open_or_extend_pending(g, [p1.id, p2.id], "test reason")
    await storage.snooze_users(GID, [p1.id])
    edits_before = len(g.channel.edits)
    service.queue_archive(g, p1.id, "test")
    r = await service.admin_remove(g, p1, admin)
    after = await storage.get_pending(pend.id)
    check("remove takes the member out of the open pending removal", r.ok and after.user_ids == [p2.id] and after.status == "pending",
          after)
    check("pending alert updated", len(g.channel.edits) > edits_before)
    check("snooze cleared", p1.id not in await storage.snoozed_user_ids(GID) | await storage.expired_snooze_user_ids(GID))
    check("queued event dropped", p1.id not in service._event_queue.get(GID, {}))
    r = await service.admin_remove(g, p2, admin)
    after = await storage.get_pending(pend.id)
    check("removing the last one closes the pending removal", r.ok and after.status == storage.PENDING_WITHDRAWN, after)
    check("closed alert loses its buttons", g.channel.edits[-1][1].get("view") is None)
    check("no open pending left", await storage.get_open_pending(GID) is None)
    service._event_queue.pop(GID, None)

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

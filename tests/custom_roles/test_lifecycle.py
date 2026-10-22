"""Offline Milestone 3 checks: lifecycle, mass-removal guard, pending, snooze, data safety."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord  # noqa: E402
from fakes import FakeGuild, FakeMember, forbidden  # noqa: E402

GID = 4
assert GID in _safety.TEST_GUILD_IDS
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


async def main():
    import config
    import database as db
    from helpers.custom_roles import service, storage

    q = db.execute_db_operation
    await db.init_custom_roles_tables()

    service.ARCHIVE_BATCH_PAUSE = 0
    service.EVENT_BATCH_SECONDS = 0.05
    service.MEMBER_FETCH_TIMEOUT = 0.2
    service.pending_view_factory = lambda pid: f"VIEW-{pid}"
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10

    async def reset():
        for table in ("custom_role_records", "custom_role_guild_settings", "custom_role_pending_removals", "custom_role_archive_snoozes"):
            await q("c", f"DELETE FROM {table} WHERE guild_id = ?", (GID,))
        service._skip_warned.clear()
        service._recent_archives.clear()

    async def setup(guild):
        await service.set_anchor(guild, guild.anchor)
        await service.set_enabled(guild, True)
        await storage.update_guild_settings(GID, log_channel_id=guild.channel.id)

    async def record(member):
        return await storage.get_custom_role(GID, member.id)

    async def settle():
        await asyncio.sleep(service.EVENT_BATCH_SECONDS + 0.2)

    # ------------------------------------------------------------------ archive / restore
    await reset()
    g = FakeGuild(GID)
    await setup(g)
    vip = g.add_role("Member", 1)
    await service.add_allowed_role(g, vip)
    m = FakeMember(g, roles=[vip], name="hammad")
    vip.members.append(m)
    r = await service.create_role(m, "Moon Child")
    await service.set_colors(m, "solid", 0xFF66AA)
    role = r.data
    check("eligible through allowed role", service.is_eligible(m, await storage.get_guild_settings(GID)))

    r = await service.archive(g, m.id, "test")
    check("archive refused while still eligible", not r.ok and r.message == service.SKIP_STILL_QUALIFIES)

    m.roles.remove(vip)
    r = await service.archive(g, m.id, "lost their allowed role")
    rec = await record(m)
    check("archive deletes the role", r.ok and role.id in g.deleted and g.get_role(role.id) is None, r.message)
    check("archive saves settings", rec.status == "saved" and rec.role_id is None and rec.name == "Moon Child"
          and rec.primary_color == 0xFF66AA and rec.position_hint is not None, rec)
    check("archive sends no DM", m.dms == [])

    m.roles.append(vip)
    r = await service.restore(m)
    rec = await record(m)
    new_role = g.get_role(rec.role_id)
    check("restore recreates same name + color", r.ok and new_role.name == "Moon Child" and new_role.colour.value == 0xFF66AA)
    check("restore assigns the role", new_role in m.roles)
    check("restore DM text", m.dms == ["Welcome back — your role **Moon Child** is back in **Test Server**."], m.dms)
    check("restore logged to channel", any("Restored" in t for t in g.channel.texts()))

    # delete failure keeps the record active
    m.roles.remove(vip)
    new_role.fail_delete = True
    r = await service.archive(g, m.id, "test")
    check("failed delete keeps record active", not r.ok and (await record(m)).status == "active", r.message)
    new_role.fail_delete = False

    # archive works while disabled; restore waits for enable
    await service.set_enabled(g, False)
    r = await service.archive(g, m.id, "test")
    check("archive works while disabled", r.ok and (await record(m)).status == "saved")
    m.roles.append(vip)
    r = await service.restore(m)
    check("restore refused while disabled", not r.ok and (await record(m)).status == "saved")
    await service.set_enabled(g, True)
    n = await service.restore_saved(g)
    check("restore_saved after enable restores", n == 1 and (await record(m)).status == "active")

    # ------------------------------------------------------------------ events: leave, batching
    leaver = FakeMember(g, booster=True, name="leaver")
    await service.create_role(leaver, "Bye Role")
    leaver.leave()
    service.queue_archive(g, leaver.id, "left the server")
    check("queued removal not instant", (await record(leaver)).status == "active")
    await settle()
    check("member leave archives after batch window", (await record(leaver)).status == "saved")

    # ------------------------------------------------------------------ guard: burst -> pending
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 2
    burst = [FakeMember(g, booster=True, name=f"b{i}") for i in range(3)]
    for b in burst:
        await service.create_role(b, f"Star {b.name}")
    sent_before = len(g.channel.sent)
    for b in burst:
        b.premium_since = None
        service.queue_archive(g, b.id, "stopped boosting")
    await settle()
    pending = await storage.get_open_pending(GID)
    check("burst over threshold -> pending, nothing deleted",
          pending is not None and sorted(pending.user_ids) == sorted(b.id for b in burst)
          and all([g.get_role((await record(b)).role_id) for b in burst]))
    alert = [msg for msg in g.channel.sent[sent_before:] if msg.kwargs.get("view") == f"VIEW-{pending.id}"]
    check("alert with buttons posted to log channel", len(alert) == 1 and "3 custom role(s)" in alert[0].kwargs["embed"].description)
    check("alert message id saved", (await storage.get_pending(pending.id)).log_message_id == alert[0].id)

    r = await service.archive(g, burst[0].id, "other path")
    check("pending members not archived by other paths", not r.ok and r.message == service.SKIP_PENDING)
    rep = await service.process_archives(g, {burst[1].id: "x"})
    check("process_archives skips pending members", rep.skipped and not rep.archived)

    # another burst merges, no second alert
    extra = FakeMember(g, booster=True, name="late")
    await service.create_role(extra, "Late Star")
    extra.premium_since = None
    extra2 = FakeMember(g, booster=True, name="late2")
    await service.create_role(extra2, "Late Star2")
    extra2.premium_since = None
    sends = len(g.channel.sent)
    await service.archive_automatically(g, {extra.id: "x", extra2.id: "y", burst[0].id: "z"}, "second burst")
    pending2 = await storage.get_open_pending(GID)
    check("second burst merges into same pending", pending2.id == pending.id and len(pending2.user_ids) == 5)
    check("merge edits alert instead of posting again", len(g.channel.sent) == sends and g.channel.edits)

    # does not expire on its own: still open later
    check("pending doesn't expire on its own", (await storage.get_open_pending(GID)) is not None)

    # ------------------------------------------------------------------ cancel -> snooze
    admin = FakeMember(g, name="admin")
    r = await service.cancel_pending(g, pending.id, admin)
    check("cancel ok", r.ok and await storage.get_open_pending(GID) is None)
    check("cancel kept roles", all([g.get_role((await record(b)).role_id) for b in burst]))
    snoozed = await storage.snoozed_user_ids(GID)
    check("cancel snoozes all 5 for 24h", len(snoozed) == 5)
    r = await service.cancel_pending(g, pending.id, admin)
    check("second click says already handled", not r.ok and "already" in r.message)

    await service.reconcile_guild(g)
    check("reconcile during snooze: no new prompt", await storage.get_open_pending(GID) is None)
    check("reconcile during snooze: roles kept", all([g.get_role((await record(b)).role_id) for b in burst]))

    # snooze expires -> asked once more, even below threshold
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10
    await q("c", "UPDATE custom_role_archive_snoozes SET until = CURRENT_TIMESTAMP - make_interval(hours => 1) WHERE guild_id = ?", (GID,))
    await service.reconcile_guild(g)
    pending3 = await storage.get_open_pending(GID)
    check("after 24h: asked once more (not removed silently)", pending3 is not None and len(pending3.user_ids) == 5
          and all([g.get_role((await record(b)).role_id) for b in burst]), pending3)
    check("expired snoozes cleared once re-asked", not await storage.expired_snooze_user_ids(GID))
    await service.reconcile_guild(g)
    check("next reconcile doesn't re-prompt", (await storage.get_open_pending(GID)).id == pending3.id)

    # ------------------------------------------------------------------ confirm -> gradual
    service.ARCHIVE_BATCH_SIZE = 2
    burst[2].premium_since = burst[0].premium_since or __import__("datetime").datetime.now()  # requalified meanwhile
    calls = []

    async def progress(done, total, report):
        calls.append((done, total))

    r = await service.confirm_pending(g, pending3.id, admin, progress=progress)
    report = r.data
    check("confirm processes in batches", calls == [(2, 5), (4, 5), (5, 5)], calls)
    check("confirm archives 4, skips the one who qualifies again",
          len(report.archived) == 4 and [u for u, _ in report.skipped] == [burst[2].id], report)
    check("confirm edits the alert", any("Confirmed by" in kw["embed"].description for _, kw in g.channel.edits))
    r = await service.confirm_pending(g, pending3.id, admin)
    check("confirm twice -> already handled", not r.ok)
    service.ARCHIVE_BATCH_SIZE = 5

    # ------------------------------------------------------------------ slow strip (many small batches)
    await reset()
    g = FakeGuild(GID)
    await setup(g)
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 3
    slow = [FakeMember(g, booster=True, name=f"s{i}") for i in range(5)]
    for x in slow:
        await service.create_role(x, f"Slow {x.name}")
        x.premium_since = None
    for x in slow[:3]:  # three separate batches of one, within the window
        await service.archive_automatically(g, {x.id: "stopped boosting"}, "stopped boosting")
    check("slow strip: first 3 (= limit) archived one by one",
          [(await record(x)).status for x in slow[:3]] == ["saved"] * 3)
    await service.archive_automatically(g, {slow[3].id: "stopped boosting"}, "stopped boosting")
    p = await storage.get_open_pending(GID)
    check("slow strip: 4th within 10 minutes is held for approval", p and p.user_ids == [slow[3].id]
          and (await record(slow[3])).status == "active")
    await service.archive_automatically(g, {slow[4].id: "stopped boosting"}, "stopped boosting")
    p = await storage.get_open_pending(GID)
    check("slow strip: later ones join the open pending", p and sorted(p.user_ids) == sorted([slow[3].id, slow[4].id]))
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10

    # ------------------------------------------------------------------ data safety
    await reset()
    g = FakeGuild(GID)
    await setup(g)
    a = FakeMember(g, booster=True, name="alice")
    await service.create_role(a, "Alice Role")
    a.premium_since = None  # changed while the bot was "offline"

    g.chunked, g.chunk_behaviour = False, "fail"
    await service.reconcile_guild(g)
    check("chunk failure: nothing archived", (await record(a)).status == "active")
    warn_count = sum("Skipped removing" in t for t in g.channel.texts())
    check("chunk failure: warned in log channel", warn_count == 1)
    await service.reconcile_guild(g)
    check("same problem not re-posted every run", sum("Skipped removing" in t for t in g.channel.texts()) == 1)

    g.chunk_behaviour = "hang"
    await service.reconcile_guild(g)
    check("chunk timeout: nothing archived", (await record(a)).status == "active")

    g.chunked, g.chunk_behaviour = True, None
    g.unavailable = True
    await service.reconcile_guild(g)
    check("guild unavailable: nothing archived", (await record(a)).status == "active")
    g.unavailable = False

    g.me.guild_permissions = discord.Permissions.none()
    await service.reconcile_guild(g)
    check("missing Manage Roles: nothing archived", (await record(a)).status == "active")
    check("missing Manage Roles: warning names it", any("Manage Roles" in t for t in g.channel.texts()))
    g.me.guild_permissions = discord.Permissions(manage_roles=True)

    config.CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH = True
    os.environ["ENVIRONMENT"] = "development"
    check("debug switch active in development", service.debug_fetch_fail_active())
    await service.reconcile_guild(g)
    check("debug switch: nothing archived", (await record(a)).status == "active")
    os.environ["ENVIRONMENT"] = "production"
    check("debug switch ignored in production", not service.debug_fetch_fail_active())
    os.environ["ENVIRONMENT"] = "development"
    config.CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH = False

    await service.reconcile_guild(g)
    check("good data next run: archived", (await record(a)).status == "saved")

    # roles deleted while offline -> missing
    b = FakeMember(g, booster=True, name="bob")
    await service.create_role(b, "Bob Role")
    g.roles.remove(g.get_role((await record(b)).role_id))
    await service.reconcile_guild(g)
    check("reconcile marks deleted roles missing", (await record(b)).status == "missing")

    # boosted while offline -> restored
    a.premium_since = b.premium_since
    await service.reconcile_guild(g)
    check("reconcile restores saved roles of qualifying members", (await record(a)).status == "active"
          and a.dms[-1].startswith("Welcome back"))

    # ------------------------------------------------------------------ allowed role deleted / preview
    await reset()
    g = FakeGuild(GID)
    await setup(g)
    member_role = g.add_role("Member", 1)
    other_allowed = g.add_role("Artist", 1)
    await service.add_allowed_role(g, member_role)
    await service.add_allowed_role(g, other_allowed)
    plain = [FakeMember(g, roles=[member_role], name=f"p{i}") for i in range(3)]
    booster = FakeMember(g, booster=True, roles=[member_role], name="boo")
    both = FakeMember(g, roles=[member_role, other_allowed], name="both")
    for x in (*plain, booster, both):
        await service.create_role(x, f"Role {x.name}")
    affected = await service.preview_allowed_role_removal(g, member_role)
    check("preview counts exactly (not boosters / other allowed role)", sorted(affected) == sorted(p.id for p in plain), affected)

    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 2
    g.roles.remove(member_role)
    for x in (*plain, booster, both):
        if member_role in x.roles:
            x.roles.remove(member_role)
    await service.handle_role_deleted(member_role)
    s = await storage.get_guild_settings(GID)
    pending = await storage.get_open_pending(GID)
    check("deleted allowed role pruned from settings", member_role.id not in s.allowed_role_ids)
    check("deleted allowed role over threshold -> pending", pending and sorted(pending.user_ids) == sorted(p.id for p in plain))
    check("nobody archived yet", all([(await record(p)).status == "active" for p in plain]))
    check("booster and other-allowed kept", (await record(booster)).status == "active" and (await record(both)).status == "active")
    await service.cancel_pending(g, pending.id, FakeMember(g, name="adm"))

    # under threshold: archived directly
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10
    await q("c", "DELETE FROM custom_role_archive_snoozes WHERE guild_id = ?", (GID,))
    g.roles.remove(other_allowed)
    both.roles.remove(other_allowed)
    await service.handle_role_deleted(other_allowed)
    check("deleted allowed role under threshold -> archived now", (await record(both)).status == "saved")

    # ------------------------------------------------------------------ cog: transitions, DMs, admin flow
    from cogs.customization import custom_roles as cog_mod
    cog = cog_mod.CustomRoles(type("Bot", (), {"guilds": [g]})())
    await reset()
    g = FakeGuild(GID)
    await setup(g)
    allowed = g.add_role("Member", 1)
    await service.add_allowed_role(g, allowed)
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10

    newb = FakeMember(g, name="newbooster")
    before = newb.snapshot()
    newb.premium_since = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await cog._handle_member_change(before, newb)
    check("boost start without saved role -> welcome DM",
          len(newb.dms) == 1 and newb.dms[0].title == "🎉 Welcome, Server Booster!"
          and any("/custom-role" in f.value and "Create role" in f.value for f in newb.dms[0].fields))

    await service.create_role(newb, "Fresh")
    before = newb.snapshot()
    newb.premium_since = None
    await cog._handle_member_change(before, newb)
    await settle()
    check("boost stop -> archived via queue", (await record(newb)).status == "saved")

    before = newb.snapshot()
    newb.premium_since = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await cog._handle_member_change(before, newb)
    check("boost again with saved role -> restore + welcome-back DM only",
          (await record(newb)).status == "active" and newb.dms[-1].startswith("Welcome back"))

    gainer = FakeMember(g, name="gainer")
    before = gainer.snapshot()
    gainer.roles.append(allowed)
    await cog._handle_member_change(before, gainer)
    check("gaining allowed role -> short access DM", gainer.dms and gainer.dms[0].title == "🎨 You can make a custom role")

    await storage.update_guild_settings(GID, enabled=False)
    other = FakeMember(g, name="notready")
    before = other.snapshot()
    other.premium_since = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await cog._handle_member_change(before, other)
    check("boost while not set up -> thank-you without custom role fields", other.dms and not other.dms[0].fields)
    await storage.update_guild_settings(GID, enabled=True)

    # interactive allow-role remove under threshold (direct)
    holders = [FakeMember(g, roles=[allowed], name=f"h{i}") for i in range(2)]
    for h in holders:
        await service.create_role(h, f"Holder {h.name}")
    affected = await service.preview_allowed_role_removal(g, allowed)
    lines = await cog._remove_allowed_roles(g, admin, [allowed], affected)
    text = " ".join(line for _, line in lines)
    check("allowed role removed (<= threshold) archives and reports",
          all([(await record(h)).status == "saved" for h in holders]) and "Removed 2" in text, text)

    # ------------------------------------------------------------------ post-merge fixes
    async def until(cond, timeout=3.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while not await cond() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)

    async def saved(member):
        return (await record(member)).status == "saved"

    async def flush_done():
        task = service._event_tasks.get(GID)
        return task is None or task.done()

    def not_found():
        return discord.NotFound(type("R", (), {"status": 404, "reason": "x"})(), "Unknown Message")

    await reset()
    g = FakeGuild(GID)
    await setup(g)
    admin = FakeMember(g, name="admin2")
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 10

    # fix 1: a removal queued while a flush is running is still handled
    a, b = FakeMember(g, booster=True, name="flushA"), FakeMember(g, booster=True, name="flushB")
    for x in (a, b):
        await service.create_role(x, f"Flush {x.name}")
        x.premium_since = None
    real_auto = service.archive_automatically
    started = asyncio.Event()

    async def slow_auto(guild, reasons, why):
        started.set()
        await asyncio.sleep(0.3)
        return await real_auto(guild, reasons, why)

    service.archive_automatically = slow_auto
    try:
        service.queue_archive(g, a.id, "stopped boosting")
        await asyncio.wait_for(started.wait(), 2)
        service.queue_archive(g, b.id, "stopped boosting")  # arrives mid-flush
        await until(lambda: saved(b))
        await until(flush_done)
    finally:
        service.archive_automatically = real_auto
    check("fix 1: member queued mid-flush is archived with no further event", await saved(a) and await saved(b))
    check("fix 1: the flush task ends once the queue is empty", await flush_done())

    # fix 3: a member who qualifies again while archive() waits for the lock keeps the role
    c = FakeMember(g, booster=True, name="reboost")
    await service.create_role(c, "Comeback")
    since, c.premium_since = c.premium_since, None
    lock = service.user_lock(GID, c.id)
    await lock.acquire()
    task = asyncio.create_task(service.archive(g, c.id, "stopped boosting"))
    for _ in range(200):  # until archive() passed its early check and waits for the lock
        if lock._waiters:
            break
        await asyncio.sleep(0.01)
    c.premium_since = since  # boosts again meanwhile
    lock.release()
    r = await task
    rec = await record(c)
    check("fix 3: re-checked inside the lock -> role kept",
          not r.ok and r.message == service.SKIP_STILL_QUALIFIES and rec.status == "active"
          and g.get_role(rec.role_id) is not None, (r, rec))

    # fix 2: a progress update that fails doesn't stop a confirmed removal
    config.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD = 1
    service.ARCHIVE_BATCH_SIZE = 2
    many = [FakeMember(g, booster=True, name=f"p{i}") for i in range(5)]
    for x in many:
        await service.create_role(x, f"Prog {x.name}")
        x.premium_since = None
    await service.archive_automatically(g, {x.id: "stopped boosting" for x in many}, "test burst")
    pend = await storage.get_open_pending(GID)
    calls = []

    async def bad_progress(done, total, report):
        calls.append(done)
        if len(calls) == 2:
            raise not_found()  # the alert was deleted mid-run

    r = await service.confirm_pending(g, pend.id, admin, progress=bad_progress)
    check("fix 2: progress raising mid-run still processes every member",
          r.ok and len(r.data.archived) == 5 and calls == [2, 4, 5], (r, calls))
    check("fix 2: every member's role was removed", all([await saved(x) for x in many]))
    check("fix 2: summary still logged", any("Pending removal confirmed" in t for t in g.channel.texts()))
    service.ARCHIVE_BATCH_SIZE = 5

    from cogs.customization.custom_roles import _progress_updater

    class GoneInteraction:
        guild_id = GID

        async def edit_original_response(self, **kw):
            raise not_found()

    try:
        await _progress_updater(GoneInteraction(), "Removing…")(1, 2, service.ArchiveReport())
        swallowed = True
    except discord.HTTPException:
        swallowed = False
    check("fix 2: the cog's progress updater never raises HTTPException", swallowed)

    await reset()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

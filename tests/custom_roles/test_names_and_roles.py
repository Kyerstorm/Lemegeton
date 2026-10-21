"""Offline Milestone 2 checks: validation + service layer against the real DB, fake Discord."""
import asyncio
import datetime
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

import discord

GID = 3
assert GID in _safety.TEST_GUILD_IDS
_ids = itertools.count(5000)
results = []


def check(label, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label + (f"  [{extra}]" if extra and not cond else ""))


class FakeRole:
    def __init__(self, guild, name, position, default=False, managed=False):
        self.guild, self.id, self.name, self.position = guild, next(_ids), name, position
        self._default = default
        self.colour = discord.Colour(0)
        self.secondary_colour = None
        self.tertiary_colour = None
        self.display_icon = None
        self.permissions = discord.Permissions.none()
        self.mention = f"<@&{self.id}>"
        self.members = []

    def is_bot_managed(self):
        return False

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= other.position

    async def edit(self, **kw):
        self.guild.calls.append(("edit", self.id, kw))
        if "name" in kw:
            self.name = kw["name"]
        _apply_colours(self, kw)


def _apply_colours(role, kw):
    if "colour" in kw:
        role.colour = kw["colour"]
    for key in ("secondary", "tertiary"):
        if f"{key}_colour" in kw:
            # mimic discord.py: `x_colour or x_color`
            value = kw.get(f"{key}_colour") or kw.get(f"{key}_color")
            setattr(role, f"{key}_colour", value)


class FakeGuild:
    def __init__(self, features=()):
        self.id = GID
        self.features = list(features)
        self.calls = []
        self.everyone = FakeRole(self, "@everyone", 0, default=True)
        self.admin = FakeRole(self, "Admin", 1)
        self.anchor = FakeRole(self, "Boosters Anchor", 2)
        self.bot_role = FakeRole(self, "Test Bot", 3)
        self.bot_role.permissions = discord.Permissions(manage_roles=True)
        self.roles = [self.everyone, self.admin, self.anchor, self.bot_role]
        self.me = type("Me", (), {})()
        self.me.top_role = self.bot_role
        self.me.guild_permissions = discord.Permissions(manage_roles=True)

    def get_member(self, uid):
        return next((m for m in getattr(self, "members", []) if m.id == uid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    async def create_role(self, **kw):
        self.calls.append(("create", kw))
        for r in self.roles:
            if not r.is_default():
                r.position += 1
        role = FakeRole(self, kw["name"], 1)
        _apply_colours(role, kw)
        self.roles.append(role)
        return role

    async def fetch_roles(self):
        return list(self.roles)

    async def edit_role_positions(self, positions, reason=None):
        self.calls.append(("positions", {r.id: p for r, p in positions.items()}))
        for r, p in positions.items():
            r.position = p

    def delete(self, role):
        self.roles.remove(role)

    def add_role(self, name, position, colour=0, perms=None):
        for r in self.roles:
            if not r.is_default() and r.position >= position:
                r.position += 1
        role = FakeRole(self, name, position)
        role.colour = discord.Colour(colour)
        if perms:
            role.permissions = perms
        self.roles.append(role)
        return role


class FakeMember:
    def __init__(self, guild, booster=True, roles=()):
        self.id, self.guild = next(_ids), guild
        self.premium_since = datetime.datetime.now(datetime.timezone.utc) if booster else None
        self.roles = [guild.everyone, *roles]
        for r in roles:
            r.members.append(self)
        guild.members = [*getattr(guild, "members", []), self]
        self.display_name = self.mention = self.name = f"member{self.id}"
        self.dms = []
        self.dms_closed = False

    async def send(self, text):
        if self.dms_closed:
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "Cannot send messages to this user")
        self.dms.append(text)

    async def add_roles(self, *roles, reason=None):
        self.roles.extend(r for r in roles if r not in self.roles)

    async def remove_roles(self, *roles, reason=None):
        self.roles = [r for r in self.roles if r not in roles]

    def __str__(self):
        return self.display_name


def sorted_names(guild):
    return [r.name for r in sorted(guild.roles, key=lambda r: r.position, reverse=True)]


async def main():
    import database as db
    from helpers.custom_roles import service, storage, validation as v

    q = db.execute_db_operation
    await db.init_custom_roles_tables()

    async def cleanup():
        await q("c", "DELETE FROM custom_role_records WHERE guild_id = ?", (GID,))
        await q("c", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))

    await cleanup()

    # ---------------- validation ----------------
    check("hex #FF66AA", v.parse_hex("#FF66AA") == 0xFF66AA)
    check("hex ff66aa", v.parse_hex("ff66aa") == 0xFF66AA)
    check("hex #F6A expands", v.parse_hex("#F6A") == 0xFF66AA)
    check("hex black -> 010101", v.parse_hex("#000000") == 0x010101)
    check("hex junk rejected", v.parse_hex("#GG0000") is None and v.parse_hex("#12345") is None and v.parse_hex("") is None)
    check("name trimmed/collapsed", v.check_role_name("  Moon   Child ")[0] == "Moon Child")
    check("name empty rejected", v.check_role_name("   ")[0] is None)
    check("name invisible-only rejected", v.check_role_name("​ㅤ⠀")[0] is None)
    check("name >100 rejected", v.check_role_name("x" * 101)[0] is None)
    check("name @everyone rejected", v.check_role_name("hi @EVERYONE")[0] is None)
    check("name @here hidden zwsp rejected", v.check_role_name("@​here")[0] is None)
    check("name matches existing role rejected", v.check_role_name("admin", ["Admin"])[0] is None)
    check("name zwsp-disguised existing role rejected", v.check_role_name("Ad​min", ["Admin"])[0] is None)
    check("blocked word rejected", v.check_role_name("so BadWord", blocked_words=["badword"])[0] is None)
    check("blocked word spaced/punct rejected", v.check_role_name("b.a d-w o r d", blocked_words=["badword"])[0] is None)
    check("normal name allowed", v.check_role_name("Mogged", ["Admin"], ["badword"]) == ("Mogged", None))

    # ---------------- gate ----------------
    guild = FakeGuild()
    booster = FakeMember(guild)
    r = await service.create_role(booster, "Mogged")
    check("not set up -> refused", not r.ok and "isn't set up" in r.message)

    await service.set_anchor(guild, guild.anchor)
    await service.set_enabled(guild, True)

    plain = FakeMember(guild, booster=False)
    for name, coro in [
        ("role", service.create_role(plain, "x")), ("name", service.rename(plain, "x")),
        ("color", service.set_colors(plain, "solid", 1)), ("holo", service.set_colors(plain, "holographic")),
        ("assign", service.assign(plain)), ("unassign", service.unassign(plain)), ("info", service.get_info(plain, plain)),
    ]:
        r = await coro
        check(f"non-booster refused: {name}", not r.ok and "boosters" in r.message)

    r = await service.rename(booster, "x")
    check("no role yet -> told to run /custom-role role", not r.ok and "/custom-role role" in r.message)

    # ---------------- create ----------------
    r = await service.create_role(booster, "Mogged")
    role = r.data
    check("create ok", r.ok, r.message)
    check("role assigned", role in booster.roles)
    check("created with no permissions", guild.calls[0][1]["permissions"] == discord.Permissions.none())
    order = sorted_names(guild)
    check("placed directly below anchor", order.index("Mogged") == order.index("Boosters Anchor") + 1, order)
    check("below bot top role", role.position < guild.bot_role.position)
    first_id = role.id

    r = await service.create_role(booster, "Again")
    check("second /custom-role role says already exists", not r.ok and "already exists by the name `Mogged`" in r.message)
    check("still exactly one custom role", sum(1 for x in guild.roles if x.name in ("Mogged", "Again")) == 1)

    r = await service.create_role(FakeMember(guild), "admin")
    check("name of existing server role refused", not r.ok and "Admin" in r.message)

    # second booster: new role also directly below anchor
    b2 = FakeMember(guild)
    r2 = await service.create_role(b2, "Second")
    order = sorted_names(guild)
    check("second role directly below anchor", order.index("Second") == order.index("Boosters Anchor") + 1, order)
    r = await service.create_role(FakeMember(guild), "mogged")
    check("custom role names are not reserved (allowed)", r.ok, r.message)

    # ---------------- rename / color ----------------
    creates_before = sum(1 for c in guild.calls if c[0] == "create")
    r = await service.rename(booster, "  Moon   Child ")
    check("rename ok + same role id", r.ok and r.data.id == first_id and r.data.name == "Moon Child", r.message)
    r = await service.set_colors(booster, "solid", 0xFF66AA)
    check("solid color ok + same role", r.ok and role.colour.value == 0xFF66AA and r.data.id == first_id, r.message)
    r = await service.set_colors(booster, "gradient", 1, 2)
    check("gradient refused without perk (says 3 server boosts)", not r.ok and "3 server boosts" in r.message
          and "Enhanced Role Styles" in r.message, r.message)
    r = await service.set_colors(booster, "holographic")
    check("holographic refused without perk", not r.ok and "3 server boosts" in r.message, r.message)
    check("no new roles created by edits", sum(1 for c in guild.calls if c[0] == "create") == creates_before)

    guild.features.append("ENHANCED_ROLE_COLORS")
    r = await service.set_colors(booster, "gradient", 0x111111, 0x222222)
    check("gradient ok with perk", r.ok and role.secondary_colour.value == 0x222222, r.message)
    r = await service.set_colors(booster, "solid", 0x333333)
    check("solid after gradient clears secondary", r.ok and role.secondary_colour is None, role.secondary_colour)
    r = await service.set_colors(booster, "holographic")
    check("holographic ok", r.ok and (role.colour.value, role.secondary_colour.value, role.tertiary_colour.value) == (11127295, 16759788, 16761760))
    rec = await storage.get_custom_role(GID, booster.id)
    check("record stores holographic", rec.color_mode == "holographic" and rec.name == "Moon Child")

    # ---------------- assign / unassign ----------------
    r = await service.assign(booster)
    check("assign when wearing -> already", not r.ok and "already wearing" in r.message)
    r = await service.unassign(booster)
    check("unassign ok, role kept", r.ok and role not in booster.roles and guild.get_role(role.id) is not None)
    r = await service.unassign(booster)
    check("unassign twice -> not wearing", not r.ok)
    r = await service.assign(booster)
    check("assign puts it back", r.ok and role in booster.roles)

    # ---------------- admin deletes the role ----------------
    guild.delete(role)
    booster.roles.remove(role)
    r = await service.rename(booster, "Phoenix")
    new_role = r.data
    check("rename after manual delete recreates", r.ok and new_role.id != first_id and new_role.name == "Phoenix", r.message)
    check("recreated role keeps saved style", new_role.tertiary_colour is not None and new_role.tertiary_colour.value == 16761760)
    check("recreated role assigned", new_role in booster.roles)
    order = sorted_names(guild)
    check("recreated directly below anchor", order.index("Phoenix") == order.index("Boosters Anchor") + 1, order)
    check("only one custom role for this member", sum(1 for x in guild.roles if x.name in ("Moon Child", "Phoenix")) == 1)
    rec = await storage.get_custom_role(GID, booster.id)
    check("record points at new role", rec.role_id == new_role.id and rec.status == "active")

    # perk lost -> recreate falls back to solid with a notice
    guild.features.remove("ENHANCED_ROLE_COLORS")
    guild.delete(new_role)
    r = await service.assign(booster)
    check("assign after delete recreates (solid fallback notice)", r.ok and any("solid color" in n for n in r.notes), r.notes)

    # ---------------- info ----------------
    r = await service.get_info(booster, booster)
    check("info self", r.ok and r.data[0].name == "Phoenix")
    r = await service.get_info(booster, plain)
    check("info other without role", not r.ok and "doesn't have" in r.message)

    # ---------------- allowed roles ----------------
    vip = FakeRole(guild, "VIP", 1)
    guild.roles.append(vip)
    member_vip = FakeMember(guild, booster=False, roles=[vip])
    r = await service.create_role(member_vip, "Vip Role")
    check("non-booster before allow-role refused", not r.ok)
    r = await service.add_allowed_role(guild, vip)
    check("allow-role add", r.ok)
    r = await service.add_allowed_role(guild, vip)
    check("allow-role add twice refused", not r.ok)
    r = await service.add_allowed_role(guild, guild.everyone)
    check("allow-role @everyone refused", not r.ok)
    r = await service.create_role(member_vip, "Vip Role")
    check("allowed-role member can create", r.ok, r.message)
    check("allow-role list", [x.id for x in await service.list_allowed_roles(guild)] == [vip.id])
    r = await service.remove_allowed_role(guild, vip)
    check("allow-role remove", r.ok and not (await storage.get_guild_settings(GID)).allowed_role_ids)
    r = await service.rename(member_vip, "Nope")
    check("eligibility re-checked after removal", not r.ok and "boosters" in r.message)

    # ---------------- failures ----------------
    guild.me.guild_permissions = discord.Permissions.none()
    r = await service.create_role(FakeMember(guild), "NoPerms")
    check("missing Manage Roles -> clear message", not r.ok and "Manage Roles" in r.message)
    guild.me.guild_permissions = discord.Permissions(manage_roles=True)

    async def forbidden(**kw):
        raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "Missing Permissions")
    current = guild.get_role((await storage.get_custom_role(GID, b2.id)).role_id)
    current.edit = forbidden
    r = await service.rename(b2, "Blocked")
    check("Discord 403 -> friendly message", not r.ok and "Manage Roles" in r.message)

    current.position = guild.bot_role.position + 1
    r = await service.set_colors(b2, "solid", 5)
    check("role above bot -> clear message", not r.ok and "above my highest role" in r.message)

    filler = [FakeRole(guild, f"f{i}", 1) for i in range(250 - len(guild.roles))]
    guild.roles.extend(filler)
    r = await service.create_role(FakeMember(guild), "Full")
    check("250-role limit refused", not r.ok and "250" in r.message)
    for f in filler:
        guild.roles.remove(f)

    await service.set_enabled(guild, False)
    r = await service.assign(booster)
    check("disabled -> not set up message", not r.ok and "isn't set up" in r.message)

    await fixes_round(service, storage, v, q)
    await round_a_b(service, storage, v, q)

    await cleanup()
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


async def fixes_round(service, storage, v, q):
    print("\n--- review fixes ---")
    await q("c", "DELETE FROM custom_role_records WHERE guild_id = ?", (GID,))
    await q("c", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))
    P = v.DEFAULT_PROTECTED_WORDS

    # 2. protected words
    for bad in ["Dev", "Mod", "Server Booster", "m0d", "a.d.m.i.n", "a d m i n", "Mods", "Moon-Dev",
                "Th3 Admins", "ServerBooster", "Nitro Gang", "Discord Official", "Moon_Staff", "b0t", "Team Rocket"]:
        check(f"protected refused: {bad!r}", v.check_role_name(bad, protected_words=P)[0] is None)
    for ok in ["Modern Art", "Botanist", "Teamwork", "Developing Moon", "Moonchild", "Admiral"]:
        check(f"protected allows: {ok!r}", v.check_role_name(ok, protected_words=P)[0] == ok)
    check("custom blocked word anywhere", v.check_role_name("xxbadwordxx", blocked_words=["badword"])[0] is None)
    check("custom blocked word leet", v.check_role_name("b4dw0rd", blocked_words=["badword"])[0] is None)
    check("mod role name refused as word", v.check_role_name("Night Guardians", protected_role_names=["Guardians"])[0] is None)
    check("mod role name leet refused", v.check_role_name("Guard1ans", protected_role_names=["Guardians"])[0] is None)
    check("non-mod role substring ok", v.check_role_name("Guardianship", protected_role_names=["Guardians"])[0] == "Guardianship")
    check("reserved leet exact refused", v.check_role_name("M0derat0r", reserved_names=["Moderator"])[0] is None)

    # 5. inline code
    check("code() keeps backslashes, swaps backticks", v.code("#12345") == "`#12345`" and "`" not in v.code("a`b")[1:-1])

    guild = FakeGuild()
    await service.set_anchor(guild, guild.anchor)
    await service.set_enabled(guild, True)
    settings = await storage.get_guild_settings(GID)
    check("anchor place defaults to below", settings.anchor_place == "below")
    check("built-in words on by default", service.active_protected_words(settings) == list(P))

    guild.add_role("Guardians", 3, perms=discord.Permissions(kick_members=True))
    guild.add_role("Artists", 3)
    m = FakeMember(guild)
    r = await service.create_role(m, "Guardians Club")
    check("service: mod role name refused", not r.ok and "Guardians" in r.message, r.message)
    r = await service.create_role(m, "Artists Club")
    check("service: non-mod role name inside is fine", r.ok, r.message)
    r = await service.rename(m, "Dev")
    check("service: 'Dev' refused by default", not r.ok and "dev" in r.message)

    r = await service.remove_blocked_word(guild, "dev")
    check("blocked-words remove built-in", r.ok and "dev" in (await storage.get_guild_settings(GID)).removed_default_words)
    r = await service.rename(m, "Dev")
    check("'Dev' allowed after switching off", r.ok, r.message)
    r = await service.add_blocked_word(guild, "DEV")
    check("blocked-words add turns built-in back on", r.ok and not (await storage.get_guild_settings(GID)).removed_default_words)
    r = await service.add_blocked_word(guild, "dev")
    check("adding an active built-in says already", not r.ok)
    r = await service.add_blocked_word(guild, "  Moon  Pie ")
    check("blocked-words add custom (normalized)", r.ok and (await storage.get_guild_settings(GID)).blocked_words == ["moon pie"])
    r = await service.rename(m, "MoonPie Fan")
    check("custom phrase blocked even without space", not r.ok)
    r = await service.remove_blocked_word(guild, "moon pie")
    check("blocked-words remove custom", r.ok and not (await storage.get_guild_settings(GID)).blocked_words)
    r = await service.remove_blocked_word(guild, "nothere")
    check("remove unknown word refused", not r.ok)
    r = await service.add_blocked_word(guild, "...")
    check("add unusable word refused", not r.ok)

    # 1. placement above + hidden colors
    mod = guild.add_role("Moderator", guild.anchor.position + 1, colour=0x00FF00)
    m2 = FakeMember(guild, roles=[mod])
    hidden = service.colored_roles_above_custom(guild, await storage.get_guild_settings(GID), await storage.list_active_role_ids(GID))
    check("settings warns about colored Moderator above custom roles", mod in hidden, [x.name for x in hidden])
    await service.create_role(m2, "Starlight")
    r = await service.set_colors(m2, "solid", 0xFF0000)
    check("color change warns when Moderator hides it (in notes)",
          r.ok and any("**Moderator** role is higher" in n for n in r.notes) and "Moderator" not in r.message, (r.message, r.notes))

    r = await service.set_anchor(guild, mod, "above")
    check("anchor place:above saved", r.ok and (await storage.get_guild_settings(GID)).anchor_place == "above", r.message)
    m3 = FakeMember(guild, roles=[mod])
    r = await service.create_role(m3, "Aurora")
    order = sorted_names(guild)
    check("place above: directly above anchor", order.index("Aurora") == order.index("Moderator") - 1, order)
    check("place above: still below bot top", r.data.position < guild.bot_role.position)
    r = await service.set_colors(m3, "solid", 0x0000FF)
    check("no hidden warning when custom role is above", r.ok and not r.notes, r.notes)
    r = await service.set_anchor(guild, guild.bot_role, "above")
    check("anchor = bot top role refused", not r.ok)
    r = await service.set_anchor(guild, guild.anchor, "sideways")
    check("bad place refused", not r.ok)

    # 3. info + role delete listener
    role = guild.get_role((await storage.get_custom_role(GID, m3.id)).role_id)
    guild.delete(role)
    r = await service.get_info(m3, m3)
    check("info shows missing after manual delete", r.ok and r.data[0].status == "missing" and r.data[1] is None)
    check("info persisted missing", (await storage.get_custom_role(GID, m3.id)).status == "missing")

    role2 = guild.get_role((await storage.get_custom_role(GID, m2.id)).role_id)
    guild.delete(role2)
    await service.handle_role_deleted(role2)
    rec = await storage.get_custom_role(GID, m2.id)
    check("on_guild_role_delete marks missing", rec.status == "missing" and rec.role_id is None)
    await service.handle_role_deleted(guild.admin)  # untracked role: no-op
    check("untracked role delete is a no-op", (await storage.get_custom_role(GID, m.id)).status == "active")


async def round_a_b(service, storage, v, q):
    print("\n--- A: hidden-color notice / B: name sweep ---")
    await q("c", "DELETE FROM custom_role_records WHERE guild_id = ?", (GID,))
    await q("c", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))
    EXPECTED = ("Your **Moderator** role is higher and has its own color, so Discord shows that color "
                "instead of yours. Ask an admin if they can move custom roles higher.")

    # ---- A ----
    guild = FakeGuild()
    await service.set_anchor(guild, guild.anchor)  # below
    await service.set_enabled(guild, True)
    mod = guild.add_role("Moderator", guild.anchor.position + 1, colour=0xFFFF00)  # yellow, above anchor
    plain_mod = guild.add_role("Helpers Corner", guild.anchor.position + 1)       # no color: never hides
    m = FakeMember(guild, roles=[mod, plain_mod])

    r = await service.create_role(m, "Starlight")
    check("A create (no color yet): no note", r.ok and not r.notes, r.notes)
    r = await service.set_colors(m, "solid", 0xFF66AA)
    check("A color set: exact note", r.ok and r.notes == [EXPECTED], r.notes)
    check("A color set: main message unchanged", r.message == "Your role color is now `#FF66AA`.", r.message)

    # recreate path: delete role, then rename -> recreated with saved color
    role = r.data
    guild.delete(role)
    m.roles.remove(role)
    r = await service.rename(m, "Nova")
    check("A recreate (rename after delete): note present", r.ok and EXPECTED in r.notes, r.notes)

    # restore path via /custom-role role after the role is gone (saved color restored)
    role = r.data
    guild.delete(role)
    m.roles.remove(role)
    r = await service.create_role(m, "Comet")
    check("A create restoring saved color: note present", r.ok and EXPECTED in r.notes, r.notes)

    # assign path that recreates
    role = r.data
    guild.delete(role)
    m.roles.remove(role)
    r = await service.assign(m)
    check("A assign that recreates: note present", r.ok and EXPECTED in r.notes, r.notes)

    # member without the higher colored role: no note
    other = FakeMember(guild)
    await service.create_role(other, "Quiet")
    r = await service.set_colors(other, "solid", 0x123456)
    check("A no higher colored role: no note", r.ok and not r.notes, r.notes)

    # cog shows notes in a separate field
    from cogs.customization import custom_roles as cog_mod
    sent = {}

    class FakeFollowup:
        async def send(self, embed=None, ephemeral=None):
            sent["embed"] = embed
    interaction = type("I", (), {"followup": FakeFollowup()})()
    await cog_mod._reply(interaction, service.Result(True, "Your role color is now `#FF66AA`.", None, [EXPECTED]), "Color Updated", "x")
    fields = {f.name: f.value for f in sent["embed"].fields}
    check("A reply embed has '⚠️ Heads up' field with the note", fields.get("⚠️ Heads up") == EXPECTED, fields)

    # ---- B ----
    await q("c", "DELETE FROM custom_role_records WHERE guild_id = ?", (GID,))
    await q("c", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))
    guild = FakeGuild()
    await service.set_anchor(guild, guild.anchor)
    await service.set_enabled(guild, True)
    await service.remove_blocked_word(guild, "dev")

    a = FakeMember(guild); a.name = "hammad"
    b = FakeMember(guild); b.name = "dev_guy"         # "dev_guy's role" contains the word dev -> "Custom Role"
    c = FakeMember(guild); c.name = "closeddms"; c.dms_closed = True
    d = FakeMember(guild); d.name = "fine"
    e = FakeMember(guild); e.name = "toohigh"
    for member, name in ((a, "Dev"), (b, "Dev Squad"), (c, "Dev Moon"), (d, "Moonlight"), (e, "Dev High")):
        r = await service.create_role(member, name)
        check(f"B setup: {name!r} created while 'dev' is off", r.ok, r.message)
    e_role = guild.get_role((await storage.get_custom_role(GID, e.id)).role_id)
    e_role.position = guild.bot_role.position + 1  # admin moved it above the bot
    check("B count before block = 0", len(await service.names_breaking_rules(guild)) == 0)

    r = await service.add_blocked_word(guild, "dev")
    check("B re-enable built-in 'dev'", r.ok)
    check("B count after block (before sweep) = 4", len(await service.names_breaking_rules(guild)) == 4)
    sweep = await service.enforce_name_rules(guild, "word blocked")
    renamed = {uid: (old, new) for uid, old, new in sweep.renamed}
    check("B 'Dev' -> \"hammad's role\"", renamed.get(a.id) == ("Dev", "hammad's role"), renamed)
    check("B username with blocked word -> 'Custom Role'", renamed.get(b.id) == ("Dev Squad", "Custom Role"), renamed)
    check("B closed DMs still renamed", renamed.get(c.id, (None, None))[1] == "closeddms's role", renamed)
    check("B untouched name kept", d.id not in renamed and guild.get_role((await storage.get_custom_role(GID, d.id)).role_id).name == "Moonlight")
    check("B role above bot reported as failed", [(u, n) for u, n, _ in sweep.failed] == [(e.id, "Dev High")], sweep.failed)
    check("B new name saved in DB", (await storage.get_custom_role(GID, a.id)).name == "hammad's role")
    check("B same role edited (no new role)", guild.get_role((await storage.get_custom_role(GID, a.id)).role_id).name == "hammad's role")
    check("B DM text exact", a.dms == ["Your role name was reset because it contains a blocked word. Use /custom-role name to choose a new one."], a.dms)
    check("B unaffected member got no DM", d.dms == [])
    check("B count after sweep = 1 (the one above the bot)", len(await service.names_breaking_rules(guild)) == 1)

    # Forbidden while editing -> failed, not crash
    e_role.position = 1
    async def forbidden(**kw):
        raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "Missing Permissions")
    e_role.edit = forbidden
    sweep = await service.enforce_name_rules(guild, "retry")
    check("B Forbidden reported as failed", sweep.failed and "permission" in sweep.failed[0][2], sweep.failed)

    # moderation role events (cog listeners)
    del e_role.edit
    cog = cog_mod.CustomRoles(type("Bot", (), {})())
    keeper = FakeMember(guild); keeper.name = "keeper"
    await service.create_role(keeper, "Night Watch")
    watch = guild.add_role("Watch", 2)  # no perms yet
    before = type("Before", (), {"name": "Watch", "permissions": discord.Permissions.none()})()
    await cog.on_guild_role_update(before, watch)  # still no perms: nothing
    check("B role update without mod perms: name kept",
          guild.get_role((await storage.get_custom_role(GID, keeper.id)).role_id).name == "Night Watch")
    watch.permissions = discord.Permissions(manage_messages=True)
    await cog.on_guild_role_update(before, watch)
    check("B role gains mod perms -> sweep renames 'Night Watch'",
          guild.get_role((await storage.get_custom_role(GID, keeper.id)).role_id).name == "keeper's role")

    starry = FakeMember(guild); starry.name = "starry"
    await service.create_role(starry, "Star Guard")
    guard = guild.add_role("Guard", 2, perms=discord.Permissions(kick_members=True))
    await cog.on_guild_role_create(guard)
    check("B new mod role created -> sweep renames 'Star Guard'",
          guild.get_role((await storage.get_custom_role(GID, starry.id)).role_id).name == "starry's role")

    luna = FakeMember(guild); luna.name = "luna"
    await service.create_role(luna, "Sky Wardens")
    old = type("Before", (), {"name": "Guard", "permissions": guard.permissions})()
    guard.name = "Wardens"
    await cog.on_guild_role_update(old, guard)
    check("B mod role renamed -> sweep renames 'Sky Wardens'",
          guild.get_role((await storage.get_custom_role(GID, luna.id)).role_id).name == "luna's role")


asyncio.run(main())

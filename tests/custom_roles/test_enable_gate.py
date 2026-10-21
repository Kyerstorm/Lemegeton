"""Offline check: /custom-role-admin enable refuses until a valid anchor is set."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (must come before any project import)

from types import SimpleNamespace as NS


class FakeRole:
    def __init__(self, id, position, default=False):
        self.id, self.position, self._default = id, position, default
        self.mention = f"<@&{id}>"

    def is_default(self):
        return self._default

    def __ge__(self, other):
        return self.position >= other.position


GID = 2  # throwaway guild id
assert GID in _safety.TEST_GUILD_IDS


async def main():
    import database as db
    from helpers.custom_roles import service, storage

    await db.execute_db_operation("cleanup", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))

    bot_top = FakeRole(900, 10)
    anchor_ok = FakeRole(901, 5)
    anchor_high = FakeRole(902, 12)
    roles = {r.id: r for r in (bot_top, anchor_ok, anchor_high)}
    guild = NS(id=GID, me=NS(top_role=bot_top), get_role=lambda rid: roles.get(rid))

    results = []

    def check(label, cond):
        results.append(cond)
        print(("PASS " if cond else "FAIL ") + label)

    r = await service.set_enabled(guild, True)
    check("enable with no anchor is refused", not r.ok and "anchor" in r.message.lower())
    check("  ...and feature stays off", (await storage.get_guild_settings(GID)).enabled is False)
    check("  ...user gate says not set up", not service.ensure_ready(guild, await storage.get_guild_settings(GID)).ok)

    await storage.update_guild_settings(GID, anchor_role_id=999)  # role that doesn't exist
    r = await service.set_enabled(guild, True)
    check("enable with a deleted anchor is refused", not r.ok)

    await storage.update_guild_settings(GID, anchor_role_id=anchor_high.id)  # stored directly, bypassing /anchor
    r = await service.set_enabled(guild, True)
    check("enable with anchor above the bot is refused", not r.ok)

    r = await service.set_anchor(guild, anchor_high)
    check("/anchor refuses a role above the bot", not r.ok)
    r = await service.set_anchor(guild, FakeRole(0, 0, default=True))
    check("/anchor refuses @everyone", not r.ok)

    r = await service.set_anchor(guild, anchor_ok)
    check("/anchor accepts a role below the bot", r.ok)
    r = await service.set_enabled(guild, True)
    check("enable after a valid anchor works", r.ok and r.data.enabled is True)
    check("  ...user gate now passes", service.ensure_ready(guild, r.data).ok)

    roles.pop(anchor_ok.id)  # admin deletes the anchor later
    check("deleted anchor closes the user gate again",
          not service.ensure_ready(guild, await storage.get_guild_settings(GID)).ok)

    r = await service.set_enabled(guild, False)
    check("disable works", r.ok and r.data.enabled is False)

    await db.execute_db_operation("cleanup", "DELETE FROM custom_role_guild_settings WHERE guild_id = ?", (GID,))
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


asyncio.run(main())

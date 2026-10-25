"""Regression tests for dashboard-managed application-command execution policy."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from cogs_test.general_commands.dashboard import COMMAND_REGISTRY, DashboardCog, _is_enabled


class FakeConfigDB:
    def __init__(self, config=None, error=None):
        self.config = config or {"sections": {}, "commands": {}}
        self.error = error

    async def get_guild_config(self, guild_id):
        if self.error:
            raise self.error
        return self.config


class DashboardCommandPolicyTests(unittest.TestCase):
    def test_protected_commands_stay_enabled_even_with_false_overrides(self):
        command = SimpleNamespace(name="help")
        meta = {"command": command, "section": "General"}
        config = {"sections": {"General": False}, "commands": {"help": False}}
        self.assertTrue(_is_enabled("help", meta, config))

    def test_explicit_command_override_wins_over_section_state(self):
        command = SimpleNamespace(name="browse")
        meta = {"command": command, "section": "Media"}
        self.assertTrue(_is_enabled("browse", meta, {"sections": {"Media": False}, "commands": {"browse": True}}))
        self.assertFalse(_is_enabled("browse", meta, {"sections": {"Media": True}, "commands": {"browse": False}}))

    def test_section_default_is_used_when_command_has_no_override(self):
        command = SimpleNamespace(name="browse")
        meta = {"command": command, "section": "Media"}
        self.assertTrue(_is_enabled("browse", meta, {"sections": {"Media": True}, "commands": {}}))
        self.assertFalse(_is_enabled("browse", meta, {"sections": {"Media": False}, "commands": {}}))
        self.assertFalse(_is_enabled("browse", meta, {"sections": {}, "commands": {}}))


class DashboardCommandExecutionGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original = COMMAND_REGISTRY._commands.copy()
        COMMAND_REGISTRY._commands.clear()
        self.command = SimpleNamespace(name="browse", qualified_name="browse", checks=[])
        COMMAND_REGISTRY.register("browse", self.command, "Media")
        self.cog = DashboardCog.__new__(DashboardCog)
        self.cog.db = FakeConfigDB({"sections": {}, "commands": {"browse": False}})
        self.interaction = SimpleNamespace(guild=SimpleNamespace(id=42), command=self.command)

    async def asyncTearDown(self):
        COMMAND_REGISTRY._commands.clear()
        COMMAND_REGISTRY._commands.update(self.original)

    async def test_disabled_command_is_blocked_by_execution_check(self):
        self.assertFalse(await self.cog._dashboard_execution_guard(self.interaction))

    async def test_enabled_command_passes_execution_check(self):
        self.cog.db.config["commands"]["browse"] = True
        self.assertTrue(await self.cog._dashboard_execution_guard(self.interaction))

    async def test_database_failure_fails_closed(self):
        self.cog.db.error = RuntimeError("database unavailable")
        self.assertFalse(await self.cog._dashboard_execution_guard(self.interaction))

    async def test_direct_messages_do_not_inherit_a_guild_override(self):
        self.interaction.guild = None
        self.assertTrue(await self.cog._dashboard_execution_guard(self.interaction))


if __name__ == "__main__":
    unittest.main()

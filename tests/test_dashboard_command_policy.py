"""Regression tests for dashboard-managed application-command execution policy."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs_test.general_commands.dashboard import (
    COMMAND_REGISTRY,
    DashboardCog,
    _is_enabled,
    _restore_dashboard_config,
)


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
        self.assertTrue(_is_enabled("browse", meta, {"sections": {}, "commands": {}}))


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


class DashboardRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_rollback_persists_snapshot_and_attempts_resynchronization(self):
        class FakeRestoreDB:
            def __init__(self):
                self.saved = None

            async def _set_guild_config(self, guild_id, config):
                self.saved = (guild_id, dict(config))

        db = FakeRestoreDB()
        bot = SimpleNamespace()
        guild = SimpleNamespace(id=42)
        snapshot = {"sections": {"Media": False}, "commands": {"browse": True}}

        with patch(
            "cogs_test.general_commands.dashboard.attempt_sync_for_guild",
            new_callable=AsyncMock,
            return_value=True,
        ) as sync:
            await _restore_dashboard_config(db, bot, guild, snapshot, "test operation")

        self.assertEqual(db.saved, (42, snapshot))
        sync.assert_awaited_once_with(bot, guild)

    async def test_rollback_keeps_saved_snapshot_when_resync_is_unavailable(self):
        class FakeRestoreDB:
            def __init__(self):
                self.saved = None

            async def _set_guild_config(self, guild_id, config):
                self.saved = (guild_id, dict(config))

        db = FakeRestoreDB()
        bot = SimpleNamespace()
        guild = SimpleNamespace(id=73)
        snapshot = {"sections": {}, "commands": {"example": False}}

        with patch(
            "cogs_test.general_commands.dashboard.attempt_sync_for_guild",
            new_callable=AsyncMock,
            return_value=False,
        ):
            await _restore_dashboard_config(db, bot, guild, snapshot, "sync unavailable")

        self.assertEqual(db.saved, (73, snapshot))


if __name__ == "__main__":
    unittest.main()

"""Source-level regression checks for private runtime adapters embedded in bot.py."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
BOT_TREE = ast.parse(BOT_SOURCE)
PICKER_SERVER_SOURCE = (ROOT / "web" / "custom_role_picker_server.py").read_text(encoding="utf-8")


class DashboardRuntimeSourceTests(unittest.TestCase):
    def test_runtime_adapters_live_in_the_existing_bot_entrypoint(self):
        classes = {node.name for node in BOT_TREE.body if isinstance(node, ast.ClassDef)}
        functions = {node.name for node in BOT_TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertIn("DashboardBotBridge", classes)
        self.assertNotIn("CustomRolePickerServer", classes)
        self.assertIn("from web.custom_role_picker_server import CustomRolePickerServer", BOT_SOURCE)
        self.assertIn("class CustomRolePickerServer:", PICKER_SERVER_SOURCE)
        self.assertIn("_connection_status", functions)
        self.assertIn("_valid_identifier", functions)

    def test_private_listeners_use_authentication_and_loopback_defaults(self):
        self.assertIn('"127.0.0.1"', BOT_SOURCE)
        self.assertIn("DASHBOARD_BRIDGE_SECRET", BOT_SOURCE)
        self.assertIn("hmac.compare_digest", BOT_SOURCE)
        self.assertIn("ipaddress.ip_address(candidate)", PICKER_SERVER_SOURCE)
        self.assertIn("non-loopback host", PICKER_SERVER_SOURCE)
        self.assertIn("at least 32 UTF-8 bytes", BOT_SOURCE)
        self.assertIn("async with self._guild_lock(guild.id)", BOT_SOURCE)

    def test_removed_adapter_modules_are_not_referenced_or_present(self):
        self.assertNotIn("utils.dashboard_bridge", BOT_SOURCE)
        self.assertNotIn("utils.dashboard_picker_server", BOT_SOURCE)
        self.assertNotIn("utils.dashboard_picker_server", (ROOT / "tests" / "custom_roles" / "test_picker_web.py").read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "utils" / "dashboard_bridge.py").exists())
        self.assertFalse((ROOT / "utils" / "dashboard_picker_server.py").exists())

    def test_command_updates_keep_sync_and_rollback_paths(self):
        self.assertIn("attempt_sync_for_guild", BOT_SOURCE)
        self.assertIn("The previous configuration was restored", BOT_SOURCE)
        self.assertIn("async with self._guild_lock(guild.id)", BOT_SOURCE)


if __name__ == "__main__":
    unittest.main()

"""Focused tests for the private custom-role picker listener."""
import unittest
from types import SimpleNamespace

import config
from web.custom_role_picker_server import CustomRolePickerServer, loopback_bind_host


class LoopbackBindHostTests(unittest.TestCase):
    def test_only_literal_loopback_addresses_are_accepted(self):
        for value in ("127.0.0.1", "127.0.0.2", "::1", "localhost"):
            with self.subTest(value=value):
                self.assertIsNotNone(loopback_bind_host(value))
        for value in ("0.0.0.0", "::", "192.0.2.10", "localhost.evil.example", "127.0.0.1.evil.example", ""):
            with self.subTest(value=value):
                self.assertIsNone(loopback_bind_host(value))


class PickerServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_listener_is_refused_before_app_creation(self):
        old_enabled = config.CUSTOM_ROLES_PICKER_ENABLED
        old_host = config.DASHBOARD_PICKER_HOST
        bot = SimpleNamespace(custom_role_picker_ready=False)
        try:
            config.CUSTOM_ROLES_PICKER_ENABLED = True
            config.DASHBOARD_PICKER_HOST = "0.0.0.0"
            server = CustomRolePickerServer(bot)
            await server.start()
            self.assertIsNone(server.runner)
            self.assertIsNone(server.site)
            self.assertFalse(bot.custom_role_picker_ready)
        finally:
            config.CUSTOM_ROLES_PICKER_ENABLED = old_enabled
            config.DASHBOARD_PICKER_HOST = old_host


if __name__ == "__main__":
    unittest.main()

"""Focused unit tests for the loopback-only bot management bridge."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from utils.dashboard_bridge import DashboardBotBridge, _connection_status, _effective_enabled, _iso, _valid_identifier


class DashboardBridgeHelperTests(unittest.TestCase):
    def test_actor_identifiers_must_be_positive_numeric_ids(self):
        self.assertTrue(_valid_identifier("123456789"))
        self.assertTrue(_valid_identifier(123456789))
        for value in ("", "0", "-1", "1.2", "abc", None, True, "1/../../etc"):
            self.assertFalse(_valid_identifier(value))

    def test_explicit_command_override_takes_precedence_over_section_default(self):
        meta = {"command": SimpleNamespace(name="browse"), "section": "Media"}
        self.assertTrue(_effective_enabled("browse", meta, {"sections": {"Media": False}, "commands": {"browse": True}}))
        self.assertFalse(_effective_enabled("browse", meta, {"sections": {"Media": True}, "commands": {"browse": False}}))

    def test_section_state_is_used_only_without_an_explicit_override(self):
        meta = {"command": SimpleNamespace(name="browse"), "section": "Media"}
        self.assertTrue(_effective_enabled("browse", meta, {"sections": {"Media": True}, "commands": {}}))
        self.assertFalse(_effective_enabled("browse", meta, {"sections": {}, "commands": {}}))

    def test_protected_command_remains_enabled(self):
        meta = {"command": SimpleNamespace(name="help"), "section": "General"}
        self.assertTrue(_effective_enabled("help", meta, {"sections": {"General": False}, "commands": {"help": False}}))

    def test_gateway_status_distinguishes_connecting_offline_degraded_and_online(self):
        self.assertEqual(_connection_status(False, False, None), "connecting")
        self.assertEqual(_connection_status(False, True, None), "offline")
        self.assertEqual(_connection_status(True, False, 120.0), "online")
        self.assertEqual(_connection_status(True, True, 650.0), "degraded")

    def test_timestamp_serialization_is_safe(self):
        now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
        self.assertEqual(_iso(now), "2026-01-02T03:04:00+00:00")
        self.assertIsNone(_iso(None))


class DashboardBridgeAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_invalid_bearer_secret_is_rejected(self):
        bridge = DashboardBotBridge(SimpleNamespace())
        bridge.secret = "test-bridge-secret"
        request = make_mocked_request("GET", "/health", headers={"Authorization": "Bearer wrong"})

        async def handler(_request):
            return web.Response(text="should not execute")

        response = await bridge._authenticate(request, handler)
        self.assertEqual(response.status, 401)
        self.assertEqual(json.loads(response.text)["error"], "Unauthorized internal dashboard request.")

    async def test_matching_bearer_secret_allows_request(self):
        bridge = DashboardBotBridge(SimpleNamespace())
        bridge.secret = "test-bridge-secret"
        request = make_mocked_request("GET", "/health", headers={"Authorization": "Bearer test-bridge-secret"})

        async def handler(_request):
            return web.json_response({"ok": True})

        response = await bridge._authenticate(request, handler)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text), {"ok": True})


if __name__ == "__main__":
    unittest.main()

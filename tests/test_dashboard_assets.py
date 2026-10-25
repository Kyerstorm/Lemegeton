"""Regression checks for Rust-owned dashboard markup, styling, and browser behavior."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "dashboard-rs" / "src" / "ui.rs").read_text(encoding="utf-8")
AUTH_SOURCE = (ROOT / "dashboard-rs" / "src" / "auth.rs").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "dashboard-rs" / "src" / "main.rs").read_text(encoding="utf-8")


class DashboardAssetTests(unittest.TestCase):
    def test_markup_and_styles_are_embedded_in_rust(self):
        for marker in ("data-view=", "overview", "commands", "extensions", "audit",
                       "diagnostics", "logs", "integrations", "database", "Dashboard navigation",
                       "confirmDialog", "guildPicker", "@media(max-width:760px)",
                       "@media(max-width:420px)", "prefers-reduced-motion:reduce", ":focus-visible"):
            with self.subTest(marker=marker):
                self.assertIn(marker, UI_SOURCE)

    def test_no_standalone_frontend_assets_remain(self):
        for path in ("web/static/dashboard.html", "web/static/login.html",
                     "web/static/dashboard.css", "web/static/dashboard.js"):
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())
        self.assertIn("ui::dashboard_html()", AUTH_SOURCE)
        self.assertIn("ui::login_html()", AUTH_SOURCE)
        self.assertIn("ui::static_asset", MAIN_SOURCE)

    def test_security_and_reduced_motion_remain_present(self):
        self.assertIn("X-CSRF-Token", UI_SOURCE)
        self.assertIn("state.refreshing=false", UI_SOURCE)
        self.assertIn("frame-ancestors 'none'", MAIN_SOURCE)


if __name__ == "__main__":
    unittest.main()

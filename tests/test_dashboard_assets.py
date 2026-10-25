"""Structural regression checks for the replacement dashboard accessibility and security."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web" / "static"


class DashboardAssetTests(unittest.TestCase):
    def test_dashboard_contains_real_management_views(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        for marker in ('data-view="overview"', 'data-view="commands"', 'data-view="extensions"',
                       'data-view="audit"', 'data-view="diagnostics"', 'data-view="logs"',
                       'data-view="integrations"', 'data-view="database"', 'aria-label="Dashboard navigation"',
                       'id="confirmDialog"', 'id="guildPicker"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_dashboard_does_not_embed_inline_javascript_or_secrets(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>", html.lower())
        for forbidden in ("DASHBOARD_CLIENT_SECRET", "DISCORD_TOKEN", "DASHBOARD_BRIDGE_SECRET"):
            self.assertNotIn(forbidden, html)

    def test_styles_include_mobile_breakpoints_and_reduced_motion(self):
        css = (STATIC / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:760px)", css)
        self.assertIn("@media(max-width:420px)", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn(":focus-visible", css)

    def test_frontend_sends_csrf_on_mutations_and_prevents_overlapping_refreshes(self):
        js = (STATIC / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('headers["X-CSRF-Token"] = state.csrf', js)
        self.assertIn('method:"PUT"', js)
        self.assertIn("state.refreshing=false", js)
        self.assertIn("if(!state.guild||state.refreshing)return;", js)

    def test_dashboard_references_only_current_static_assets(self):
        html = (STATIC / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn('/static/dashboard.css', html)
        self.assertIn('/static/dashboard.js', html)
        self.assertNotIn("theme.css", html)


if __name__ == "__main__":
    unittest.main()

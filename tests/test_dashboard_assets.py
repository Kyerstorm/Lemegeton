"""Source and routing regression checks for the TypeScript dashboard frontend."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "dashboard-rs" / "src" / "ui.rs").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "dashboard-rs" / "src" / "main.rs").read_text(encoding="utf-8")
AUTH_SOURCE = (ROOT / "dashboard-rs" / "src" / "auth.rs").read_text(encoding="utf-8")
FRONTEND_APP = (ROOT / "dashboard-frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
FRONTEND_STYLES = (ROOT / "dashboard-frontend" / "src" / "styles.ts").read_text(encoding="utf-8")
FRONTEND_ENTRY = (ROOT / "dashboard-frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
FRONTEND_CONFIG = (ROOT / "dashboard-frontend" / "vite.config.ts").read_text(encoding="utf-8")
FRONTEND_PACKAGE = (ROOT / "dashboard-frontend" / "package.json").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "dashboard.yml").read_text(encoding="utf-8")
START_SCRIPT = (ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")


class DashboardAssetTests(unittest.TestCase):
    def test_frontend_is_authored_in_typescript_and_tsx(self):
        self.assertIn("createRoot", FRONTEND_ENTRY)
        self.assertIn("function LoginPage()", FRONTEND_APP)
        for page in ("overview", "commands", "extensions", "audit", "diagnostics",
                     "logs", "integrations", "database"):
            with self.subTest(page=page):
                self.assertIn('id: "' + page + '"', FRONTEND_APP)
        self.assertIn("src/styles.ts", FRONTEND_CONFIG)
        self.assertIn('fileName: () => "app.js"', FRONTEND_CONFIG)

    def test_frontend_keeps_live_controls_and_api_contracts(self):
        for marker in ("/api/bootstrap", "/api/system", "/api/integrations",
                       "/api/logs?file=", "/api/logout", "/commands/",
                       "/sync", "/reset", "X-CSRF-Token", 'credentials: "same-origin"',
                       "toggleCommand", "Publish slash commands", "Reset server overrides"):
            with self.subTest(marker=marker):
                self.assertIn(marker, FRONTEND_APP)
        self.assertIn("prefers-reduced-motion:reduce", FRONTEND_STYLES)

    def test_frontend_uses_built_assets_without_standalone_source_files(self):
        self.assertIn('href="/static/app.css"', UI_SOURCE)
        self.assertIn('src="/static/app.js"', UI_SOURCE)
        self.assertIn('"app.js"', UI_SOURCE)
        self.assertIn('"app.css"', UI_SOURCE)
        for path in (
            "dashboard-frontend/index.html",
            "dashboard-frontend/src/index.html",
            "dashboard-frontend/src/styles.css",
            "dashboard-frontend/src/app.css",
            "web/static/dashboard.html",
            "web/static/login.html",
            "web/static/dashboard.css",
            "web/static/dashboard.js",
        ):
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())
        self.assertIn("ui::dashboard_html()", AUTH_SOURCE)
        self.assertIn("ui::login_html()", AUTH_SOURCE)
        self.assertIn("ui::static_asset", MAIN_SOURCE)

    def test_production_build_and_deployment_configs_include_the_frontend(self):
        import json
        import tomllib

        railpack = json.loads((ROOT / "railpack.json").read_text(encoding="utf-8"))
        self.assertEqual(railpack["packages"]["node"], "22")
        package = json.loads(FRONTEND_PACKAGE)
        self.assertGreaterEqual(int(package["engines"]["node"].lstrip(">=")), 22)

        railway_json = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        nested_railway = json.loads((ROOT / "config" / "railway.json").read_text(encoding="utf-8"))
        railway_toml = tomllib.loads((ROOT / "railway.toml").read_text(encoding="utf-8"))
        commands = (
            railway_json["build"]["buildCommand"],
            nested_railway["build"]["buildCommand"],
            railway_toml["build"]["buildCommand"],
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("npm run typecheck --prefix dashboard-frontend", command)
                self.assertIn("npm run build --prefix dashboard-frontend", command)
                self.assertIn("cargo build --manifest-path dashboard-rs/Cargo.toml --release", command)
        self.assertIn("dashboard-frontend/dist/app.js", START_SCRIPT)
        self.assertIn("dashboard-frontend/dist/app.css", START_SCRIPT)
        self.assertIn("test -s dashboard-frontend/dist/app.js", WORKFLOW)
        self.assertIn("test -s dashboard-frontend/dist/app.css", WORKFLOW)
        self.assertIn('      - "railpack.json"', WORKFLOW)
        self.assertIn('      - "config/railway.json"', WORKFLOW)
        self.assertIn('      - "scripts/start.sh"', WORKFLOW)


    def test_accessibility_and_security_headers_remain(self):
        for marker in ("@media(max-width:760px)", "@media(max-width:480px)",
                       "prefers-reduced-motion:reduce", ":focus-visible"):
            with self.subTest(marker=marker):
                self.assertIn(marker, FRONTEND_STYLES)
        self.assertNotIn("dangerouslySetInnerHTML", FRONTEND_APP)
        self.assertIn("script-src 'self'", MAIN_SOURCE)
        self.assertIn("style-src 'self'", MAIN_SOURCE)
        self.assertIn("frame-ancestors 'none'", MAIN_SOURCE)


if __name__ == "__main__":
    unittest.main()

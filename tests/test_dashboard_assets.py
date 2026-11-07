"""Regression checks for the current Next.js + Rust dashboard deployment."""

from pathlib import Path
import json
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class DashboardAssetTests(unittest.TestCase):
    def test_frontend_uses_next_app_router_and_static_export(self):
        package = json.loads(source("web/frontend/package.json"))
        config = source("web/frontend/next.config.ts")
        layout = source("web/frontend/app/layout.tsx")
        page = source("web/frontend/app/page.tsx")
        login = source("web/frontend/app/login/page.tsx")
        app = source("web/frontend/src/App.tsx")

        self.assertIn("next", package["dependencies"])
        self.assertIn("build", package["scripts"])
        self.assertIn("typecheck", package["scripts"])
        self.assertIn('output: "export"', config)
        self.assertIn("metadata", layout)
        self.assertIn('robots: { index: false, follow: false }', layout)
        self.assertIn("App", page)
        self.assertIn("App", login)
        self.assertIn('"use client"', app)
        self.assertIn("/api/bootstrap", app)
        self.assertIn("X-CSRF-Token", app)
        self.assertIn("credentials: \"same-origin\"", app)
        self.assertIn("atlas", app)

    def test_rust_serves_the_exported_pages_and_safe_next_assets(self):
        ui = source("web/backend/src/ui.rs")
        main = source("web/backend/src/main.rs")

        self.assertIn('web/frontend/out/index.html', ui)
        self.assertIn('web/frontend/out/login/index.html', ui)
        self.assertIn('web/frontend/out/_next', ui)
        self.assertIn('part == ".."', ui)
        self.assertIn('"/_next/{*path}"', main)
        self.assertIn("ui::dashboard_html()", source("web/backend/src/auth.rs"))
        self.assertIn("ui::login_html()", source("web/backend/src/auth.rs"))

    def test_guild_scoped_api_keeps_authorization_and_atlas_bridge(self):
        api = source("web/backend/src/api.rs")
        main = source("web/backend/src/main.rs")
        state = source("web/backend/src/state.rs")
        auth = source("web/backend/src/auth.rs")

        atlas_start = api.index("pub async fn atlas")
        atlas_handler = api[atlas_start:atlas_start + 1600]
        self.assertIn("authorized_guild", atlas_handler)
        self.assertIn("atlas_bridge_json", atlas_handler)
        self.assertIn('"/api/guilds/{guild_id}/atlas"', main)
        self.assertIn("pub async fn manageable_guilds", state)
        self.assertIn("can_manage_guild", state)
        self.assertIn("session_from_headers", auth)
        self.assertIn("allow_oauth_start", auth)

    def test_dashboard_security_headers_and_oauth_validation_remain(self):
        main = source("web/backend/src/main.rs")
        state = source("web/backend/src/state.rs")
        auth = source("web/backend/src/auth.rs")
        cargo = source("web/backend/Cargo.toml")

        for header in ("x-content-type-options", "x-frame-options",
                       "referrer-policy", "permissions-policy",
                       "cross-origin-opener-policy", "cross-origin-resource-policy"):
            with self.subTest(header=header):
                self.assertIn(header, main)
        self.assertIn("validate_public_configuration", state)
        self.assertIn("allow_oauth_start", state)
        self.assertIn("Too many sign-in attempts", auth)
        self.assertIn("oauth_ready", auth)
        self.assertIn('version = "1.54.1"', cargo)

    def test_railway_and_docker_use_current_paths_and_build_every_runtime(self):
        root_railway = json.loads(source("railway.json"))
        nested_railway = json.loads(source("config/railway.json"))
        railway_toml = tomllib.loads(source("railway.toml"))
        docker = source("Dockerfile")
        start = source("scripts/start.sh")
        compose = source("docker-compose.yml")
        workflow = source(".github/workflows/dashboard.yml")
        package = json.loads(source("package.json"))

        self.assertIn("web/frontend", root_railway["build"]["buildCommand"])
        self.assertIn("web/backend/Cargo.toml", root_railway["build"]["buildCommand"])
        for command in (nested_railway["build"]["buildCommand"], railway_toml["build"]["buildCommand"]):
            with self.subTest(command=command):
                self.assertIn("web/frontend", command)
                self.assertIn("web/backend/Cargo.toml", command)
                self.assertIn("npm test", command)
                self.assertNotIn("dashboard-frontend", command)
                self.assertNotIn("dashboard-rs", command)

        self.assertEqual(package["scripts"]["test"],
                         "npm run build && node --test dist/tests/*.test.js")
        for marker in ("npm run typecheck", "npm audit", "npm run build",
                       "npm test", "cargo build --manifest-path web/backend/Cargo.toml --release",
                       "python:3.13-slim-bookworm AS runtime", "USER 10001:10001",
                       "HEALTHCHECK", "COPY --from=frontend", "COPY --from=rust-builder"):
            with self.subTest(marker=marker):
                self.assertIn(marker, docker)
        self.assertIn('"$DASHBOARD_BIN" &', start)
        self.assertIn("python bot.py &", start)
        self.assertNotIn("node --env-file-if-exists=.env dist/bot.js &", start)
        self.assertIn("127.0.0.1:8080:8080", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertIn("docker build --pull", workflow)
        self.assertIn("docker compose config --quiet", workflow)

    def test_deployment_refuses_to_start_without_built_dashboard_assets(self):
        start = source("scripts/start.sh")
        ui = source("web/backend/src/ui.rs")

        self.assertIn("web/frontend/out/index.html", start)
        self.assertIn("web/frontend/out/login/index.html", start)
        self.assertIn("target/release/lemegeton-dashboard", start)
        self.assertIn("SERVICE_UNAVAILABLE", ui)
        self.assertFalse((ROOT / "dashboard-frontend").exists())
        self.assertFalse((ROOT / "dashboard-rs").exists())


if __name__ == "__main__":
    unittest.main()

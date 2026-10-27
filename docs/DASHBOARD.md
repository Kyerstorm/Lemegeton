# Lemegeton web dashboard

The public control plane is a Rust/Axum service with a React + TypeScript frontend in `dashboard-frontend/src/`. Screen components live in `.tsx` and styling is authored in `styles.ts`; Vite builds those sources into `dashboard-frontend/dist/app.js` and `app.css`, which Rust serves from the same origin. The root `railpack.json` explicitly supplies Node 22 for this nested package, so a Python/Rust deployment does not rely on language auto-detection to provide Node. The Rust service binds to loopback by default and refuses non-loopback binding unless `DASHBOARD_ALLOW_PUBLIC_BIND=true`; Railway/container configuration explicitly opts into the platform ingress interface. No handwritten dashboard HTML or standalone CSS/JavaScript source files are used. The Discord bot remains the existing Python/discord.py application. A narrow runtime adapter stays consolidated in `bot.py` because only the live bot process owns its command tree and gateway connection.

## Capabilities and boundaries

- Discord OAuth2 login uses the `identify` and `guilds` scopes. A browser session is random, HttpOnly, SameSite=Lax, expires, and is invalidated on logout. Write requests require an origin match and a CSRF token.
- Every guild API operation refreshes the OAuth token when necessary and re-fetches the caller's current guild permissions. Access is restricted to guilds where the bot is a member and the caller has Manage Server or Administrator permission. IDs supplied by the browser are never sufficient authorization.
- The command directory is rebuilt from the live Discord command tree after extension loading and hot-reloads. Every slash-command leaf is indexed; explicit command metadata wins, with cog/module-based categories used for the rest. Nested command groups stay grouped during synchronization rather than being flattened into invalid top-level entries.
- A runtime application-command check validates persisted guild settings before execution, even if Discord still displays a global command. The web bridge and in-Discord dashboard share the same registry and per-guild PostgreSQL settings. Unmanaged prefix commands are not claimed to be configurable; protected system commands cannot be toggled.
- Command changes are written through the bot's existing PostgreSQL configuration layer and are synchronized to Discord before the API confirms success. If synchronization fails, the bridge restores the previous configuration and attempts to restore the prior command set.
- Extension inventory, runtime status, persisted configuration, audit history, and selected logs reflect the running bot. Runtime load/unload/reload controls are deliberately omitted because the current architecture does not provide a safety contract for unloading arbitrary cogs.
- Logs and bot-wide integration configuration are owner-only. Only booleans and provider labels are returned for integrations; secrets are never sent to the browser.
- The existing custom-role picker remains in Python on a second loopback port and is reverse-proxied through Rust so existing picker tokens and role-validation rules remain in effect.

The service does not expose arbitrary code execution, shell commands, raw SQL, or unrestricted extension operations.

## Environment

Configure the following in the service environment (see `.env.example` for the full template):

| Variable | Purpose |
| --- | --- |
| `DASHBOARD_CLIENT_ID` | Discord application/client ID |
| `DASHBOARD_CLIENT_SECRET` | OAuth2 client secret; server-side only |
| `DASHBOARD_REDIRECT_URI` | Exact registered callback, ending in `/oauth/callback` |
| `DASHBOARD_PUBLIC_URL` | Exact public origin used by the browser, with no trailing slash |
| `DASHBOARD_COOKIE_SECURE` | Set `true` when served over HTTPS |
| `DASHBOARD_OWNER_IDS` | Optional comma-separated Discord IDs with bot-wide log/integration access |
| `ADMIN_DISCORD_ID` | Existing configured bot administrator; also receives dashboard-owner access |
| `DASHBOARD_BRIDGE_SECRET` | Long random shared secret, read by Rust and the embedded bot runtime |
| `DASHBOARD_BRIDGE_URL` | Internal bridge URL; default `http://127.0.0.1:8091` |
| `DASHBOARD_PICKER_URL` | Private picker URL; default `http://127.0.0.1:8092` |
| `DASHBOARD_PORT` | Public Rust service port; default `8080` |
| `DASHBOARD_ALLOW_PUBLIC_BIND` | Explicit opt-in to a non-loopback bind; only enable behind platform ingress or a protected reverse proxy |
| `CUSTOM_ROLES_PUBLIC_URL` | Exact browser-visible origin for picker mutation Origin checks; match `DASHBOARD_PUBLIC_URL` |
| `CUSTOM_ROLES_TRUST_PROXY` | Enable only when the trusted ingress appends the real client IP as the rightmost `X-Forwarded-For` entry |

Use a random `DASHBOARD_BRIDGE_SECRET` of at least 32 UTF-8 bytes (for example, `openssl rand -hex 32`). Do not commit it. Rust refuses to call the bot bridge with a shorter value; the Python bridge and picker refuse non-loopback listeners. The Rust web service binds to `127.0.0.1` by default. On production HTTPS, set `DASHBOARD_PUBLIC_URL` and `CUSTOM_ROLES_PUBLIC_URL` to the same browser-visible origin and `DASHBOARD_COOKIE_SECURE=true`; startup fails closed if a non-local HTTP origin or mismatched OAuth callback is configured. The configured OAuth callback must exactly match the Discord Developer Portal entry.

The bot still requires its existing Discord token and PostgreSQL configuration. The dashboard does not create a second Discord client or a second command registry.

## Local development

1. Install Python dependencies with `python -m pip install -r requirements.txt`.
2. Install Node.js 22 or newer and a current stable Rust toolchain.
3. Configure the environment values above and the existing bot/database values.
4. Build the frontend: `npm install --prefix dashboard-frontend && npm run build --prefix dashboard-frontend`.
5. Build the public service: `cargo build --manifest-path dashboard-rs/Cargo.toml`.
6. Start the dashboard backend with `cargo run --manifest-path dashboard-rs/Cargo.toml` from the repository root in one terminal.
7. Start the existing bot with `python bot.py` in another terminal. The bot starts its private runtime adapter and custom-role picker automatically.
8. Open the public dashboard address. For local development, register `http://localhost:8080/oauth/callback` and use `DASHBOARD_PUBLIC_URL=http://localhost:8080`.

For the combined deployment entry point, build the frontend assets and release binary first, then use `./scripts/start.sh`. The Railway build command installs Node dependencies, generates the frontend assets, compiles the Rust service, and starts both services through this script. `dashboard-frontend/dist/` is generated output and is not a frontend source directory.

## Testing and checks

- Rust unit tests: `cargo test --manifest-path dashboard-rs/Cargo.toml`
- Rust formatting: `cargo fmt --manifest-path dashboard-rs/Cargo.toml -- --check`
- Python syntax: `python -m compileall -q bot.py web/custom_role_picker.py`
- Bridge unit tests: `python -m unittest discover -s tests -p "test_dashboard_bridge.py"`
- Existing custom-role web regression suite: run the project's documented `tests/custom_roles/run_all.py` entry point in a configured test environment.

CI runs the Rust tests, Python syntax compilation, and focused bridge tests. The complete Discord/database-backed bot test suite still needs the repository's normal test fixture and PostgreSQL setup.

## Operational notes

- Rust sessions and OAuth state are held in process memory. Restarting the service invalidates dashboard sessions; this deployment mode expects one Rust dashboard instance. Use a shared session store before scaling horizontally.
- Gateway status is reported as online, degraded (ready but at least 500 ms latency), offline (a previously ready connection is no longer ready), or connecting (ready has not yet been observed). If the bot bridge is down, status is unknown with the last in-memory observation where available. Command mutations fail instead of returning optimistic success.
- Application command visibility in Discord is distinct from command execution. Only commands in the existing dashboard registry are changed and synchronized; unrelated guild commands are preserved by the bot synchronizer.
- Database and audit writes reuse the existing configuration tables in PostgreSQL. No competing dashboard database is introduced.
- If the dashboard sign-in button fails, verify the application ID, client secret, exact callback URL, public origin, and secure-cookie setting. If login works but command data is unavailable, verify the bridge secret matches and that the bot's DashboardCog has initialized its database pool.

## Production deployment: VPS, systemd, and Nginx

For a VPS, use the separate systemd services and Nginx reverse proxy in `deploy/vps/`. The bot and public Rust service run as different unprivileged users; only the bot user can write bot data and logs. Rust binds to loopback, the bot bridge and custom-role picker stay on loopback, and Nginx terminates TLS and limits public request rates.

Read [the VPS deployment guide](../deploy/vps/README.md) before opening firewall ports. Expose only SSH and HTTPS (HTTP may be open for the redirect/ACME flow); do not expose ports 8080, 8091, or 8092 publicly. Keep OAuth client secrets and the bridge secret in root-owned service environment files, not in Git. Set the public origin and OAuth callback to the same HTTPS host, set `DASHBOARD_COOKIE_SECURE=true`, and use a unique 32-byte-or-longer bridge secret in both service environments.

The example is designed for a single VPS instance. Sessions and OAuth states are held in Rust process memory, so restarts invalidate browser sessions and multi-instance scaling requires a shared session store plus coordinated rate limits. Nginx TLS, firewall rules, OS updates, service credentials, and backups remain part of the operator's security boundary.

## Docker Compose deployment

A minimal Docker deployment is provided by `Dockerfile`, `.dockerignore`, and `docker-compose.yml`. It builds the TypeScript bundle and Rust release binary in separate build stages, runs as a non-root user, drops Linux capabilities, applies `no-new-privileges`, and publishes port 8080 only on the host loopback interface for a host-level reverse proxy. Create the bind-mounted `data`, `logs`, and `runtime-home` directories and set their ownership to UID/GID `10001` before starting it. Keep `.env` out of the image and readable only by the Docker operator.

The combined container preserves the existing private local bridge. For stronger process isolation on a VPS, prefer the separate systemd services rather than exposing either private Python listener.

## Security and dependency checks

The dashboard workflow runs the TypeScript type-check, `npm audit`, production asset checks, Rust tests, and `cargo audit` against the dependency resolution for that run. Tokio's minimum version is pinned above the October 2026 race-condition advisory's affected release; the advisory documents `1.54.1` as patched: [RUSTSEC-2026-0384](https://rustsec.org/advisories/RUSTSEC-2026-0384.html). The frontend toolchain is audited as well; see [the Vite security advisory list](https://github.com/vitejs/vite/security/advisories).

See [the security review and residual risks](SECURITY_AUDIT.md). Automated tests are not a substitute for rotating previously exposed credentials, a real TLS/OAuth deployment smoke test, OS updates, or a production penetration test.

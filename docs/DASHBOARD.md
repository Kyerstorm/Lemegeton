# Lemegeton web dashboard

The public control plane is a Rust/Axum service with a React + TypeScript frontend in `dashboard-frontend/src/`. Screen components live in `.tsx` and styling is authored in `styles.ts`; Vite builds those sources into `dashboard-frontend/dist/app.js` and `app.css`, which Rust serves from the same origin. The root `railpack.json` explicitly supplies Node 22 for this nested package, so a Python/Rust deployment does not rely on language auto-detection to provide Node. No handwritten dashboard HTML or standalone CSS/JavaScript source files are used. The Discord bot remains the existing Python/discord.py application. A narrow runtime adapter stays consolidated in `bot.py` because only the live bot process owns its command tree and gateway connection.

## Capabilities and boundaries

- Discord OAuth2 login uses the `identify` and `guilds` scopes. A browser session is random, HttpOnly, SameSite=Lax, expires, and is invalidated on logout. Write requests require an origin match and a CSRF token.
- Every guild API operation refreshes the OAuth token when necessary and re-fetches the caller's current guild permissions. Access is restricted to guilds where the bot is a member and the caller has Manage Server or Administrator permission. IDs supplied by the browser are never sufficient authorization.
- The command directory is built from the actual dashboard-managed application-command registry. A runtime application-command check validates persisted guild settings before execution, even if Discord still displays a global command. Unmanaged prefix commands are not claimed to be configurable; protected system commands cannot be toggled.
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

Use a strong unique value for `DASHBOARD_BRIDGE_SECRET`. Do not commit it. The bot runtime adapter and custom-role picker listeners must remain bound to loopback; the public dashboard is served by Rust. On production HTTPS, set `DASHBOARD_PUBLIC_URL` to the browser-visible origin and `DASHBOARD_COOKIE_SECURE=true`. The configured OAuth callback must exactly match the Discord Developer Portal entry.

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

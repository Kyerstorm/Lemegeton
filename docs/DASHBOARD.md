# Lemegeton web dashboard

The public control plane is a Rust/Axum service with a Next.js App Router frontend in `web/frontend/app/`. Interactive screens and authored styling are React + TypeScript components in `web/frontend/src/`; global dashboard styles are defined in `web/frontend/src/Components/DesignSystem/GlobalStyles.tsx`, and the Custom Roles picker theme is defined in `web/frontend/src/Components/Features/CustomRoles/PickerStyles.tsx`. The public `/status/` route is a separate, unauthenticated status surface; it reads only the safe aggregate projection from `GET /api/status` and does not expose dashboard sessions, guild data, bridge credentials, or internal diagnostics. Next.js builds a static export in `web/frontend/out/`; Rust serves the exported page routes, hashed `_next/static` chunks, allowlisted `/brand/*` and `/fonts/*` files, `/icon.svg`, and `/apple-touch-icon.png` from the same origin. The root `railpack.json` supplies Node 22 for this nested package. The Rust service binds to loopback by default and refuses non-loopback binding unless `DASHBOARD_ALLOW_PUBLIC_BIND=true`; Railway/container configuration explicitly opts into the platform ingress interface. The combined Docker and Railway entry point runs the compiled TypeScript bot and Rust dashboard together through `scripts/start.sh`. No Python runtime is part of the v3 launch or build path.

## Capabilities and boundaries

- First-party policy pages are served at `/terms-of-service/`, `/privacy-policy/`, `/community-guidelines/`, and `/copyright-complaints/`, and `/dmca/`. The pages render the Markdown files in `docs/legal/` (including `DMCA.md`) at build time, keeping one source of truth for the dashboard and repository.
- The cookie preference banner is shown when a browser has no current choice. Accept all, Reject optional, and Configure are available before any optional browser storage is accessed. Essential session/OAuth/consent cookies remain active; the only optional preference currently implemented is remembering the last selected Discord server in local storage. It is disabled by default, is only read/written after opt-in, and is removed when disabled. There are no analytics or advertising trackers in the current dashboard. A persistent Cookie settings control lets visitors change or withdraw their choice.
- Cookie decisions use an opaque HttpOnly, SameSite=Lax cookie and a server-side libSQL row containing the functional preference, consent version, decision time, and expiry. Decisions expire after 180 days. HTTPS deployments use host-only `__Host-` session, OAuth-state, and preference cookies with `Secure`, `HttpOnly`, and `Path=/`; local HTTP development uses the compatible non-prefixed names. Cookie preference writes require the exact public Origin and are covered by the API/write rate limits.

- Discord OAuth2 login uses the `identify` and `guilds` scopes. The login button submits a same-origin POST to `/oauth/start`; the notice directly below it links to the current Terms of Service, Privacy Policy, and Community Guidelines and states that continuing accepts them. After Discord verifies the account and dashboard access, the OAuth callback records the current policy versions and acceptance time before issuing the browser session. Existing sessions without current consent remain behind the legacy consent fallback. Sessions are random, HttpOnly, SameSite=Lax, expire, and are invalidated on logout. Write requests require an origin match and a CSRF token.
- Every guild API operation refreshes the OAuth token when necessary and re-fetches the caller's current guild permissions. Access is restricted to guilds where the bot is a member and the caller has Manage Server or Administrator permission. Registered bot moderators and configured dashboard owners may also sign in for bot-wide tools without a manageable guild; bot moderators are resolved through the existing `isBotModerator` helper (`ADMIN_DISCORD_ID` or `bot_moderators`). IDs supplied by the browser are never sufficient authorization.
- The TypeScript bridge reads only commands explicitly registered in the TypeScript command registry. Seven feature commands are configurable per guild: `/discover`, `/archive`, `/community`, `/play`, `/profile`, `/custom-role`, and `/music`. Their settings are stored in the shared libSQL database. `/settings` and `/language` remain protected setup commands; the standalone help, privacy, feedback, and restricted operations commands are not feature toggles.
- A runtime application-command check validates persisted guild settings before execution, even if Discord still displays a global command. The web bridge and in-Discord dashboard share the same registry and per-guild libSQL settings. Unmanaged prefix commands are not claimed to be configurable; protected system commands cannot be toggled.
- The common bot interaction gate checks the same persisted feature setting for slash commands, autocomplete, existing buttons/selects, and modal submissions. Disabling a feature therefore blocks its old interactive controls as well as new command invocations. Protected setup and standalone commands remain outside this feature-toggle registry.
- The same guild feature settings are enforced at message and worker boundaries: Archive upload intake checks `/archive`; AniList user links check `/profile` while AniList media/entity/review/activity and Steam store previews check `/discover`; Music polling and every Discover alert/follow worker re-check `/music` or `/discover`; Daily Drop, Reading Club reminders, release digests, Media Automation and Media Night results check `/community`. Outbox claim queries omit disabled guilds; if a feature is switched off after a job is claimed, the worker releases the claim without increasing retry attempts. Re-enabling resumes pending work. Privacy cleanup, retention enforcement and private asset cleanup intentionally continue while a feature is disabled.
- Command changes are written to the selected guild's libSQL feature settings. The bridge publishes the v3 global slash-command registry on an explicit sync; per-guild feature guards remain the source of truth for whether a command action may run. If a write or Discord synchronization fails, the bridge attempts to restore the previous guild setting and reports failure.
- Registered command inventory, runtime status, persisted configuration, audit history, and recent structured logs reflect the TypeScript bridge process. The current log endpoint returns a bounded in-memory recent-log buffer; it is not a durable log-file reader. Runtime load/unload/reload controls are omitted because the v3 registry is static.
- The public status page polls `GET /api/status` every 30 seconds. The Rust endpoint checks its shared data store and privately queries the bot health bridge, then returns only component names, coarse health states, safe latency values and an observation timestamp. Bot guild counts, command inventories, runtime versions, bridge secrets, and raw diagnostics are excluded. Incident history and uptime percentages remain unavailable until durable incident recording and historical sampling are implemented.
- The Commands page uses shared form controls and a reusable Save Changes bar. Guild feature settings and each command's role/channel access policy have separate drafts, save state, reset behavior, and revision checks. A failed save keeps that section's draft in the browser; the server remains authoritative and revalidates the caller, guild, command, roles, channels, and expected revision.
- Runtime logs and bot-wide integration status are bot-moderator-only. The sidebar hides both sections from other accounts, and the Rust API independently rechecks `isBotModerator` on every request; the bootstrap flag is presentation-only and cannot grant access. Only bounded recent log events and integration labels/configuration booleans are returned. Credential values and tokens are never sent to the browser.
- The Custom Roles picker rate-limits failed tokens and image-link fetches with bounded per-identity maps (10,000 keys each). When a map is full, expired entries are swept on a bounded interval and new identities are rejected until capacity is available. This limiter is local to the single bot/picker process; additional picker replicas require a coordinated shared limiter before deployment.
- The `/discover` Knowledge Atlas view includes an authenticated dashboard link carrying the selected title, category, provider identity/URL and invoking guild. Rust re-checks the signed-in member's Manage Server or Administrator access, then the TypeScript bridge checks bot membership and guild setup before querying a bounded graph. The Atlas supports up to three hops/40 nodes, provider and community links, source-kind/category/relationship/provider/provider-ID/evidence filters, deterministic category clusters, shortest paths and bounded JSON/SVG/PNG exports. Each hop re-applies guild/global visibility; images are fetched only from approved HTTPS provider hosts with redirects disabled and timeouts. The browser never receives the bot bridge secret. The custom-role browser picker is served by the TypeScript bot on a private loopback port and reverse-proxied through Rust. Its bearer token is issued in the URL fragment, stored only as a SHA-256 hash in process memory, sent only in the Authorization header, and revoked on replacement, expiry or bot restart. Writes require the configured browser Origin and every request re-checks the current guild member, eligibility, role record and role hierarchy. External icon image links are HTTPS-only, resolved to public addresses and fetched with the resolved IP pinned to the TLS request; redirects are refused.

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
| `DASHBOARD_OWNER_IDS` | Optional comma-separated Discord IDs allowed to sign in without Manage Server access; does not grant bot-moderator-only tools |
| `ADMIN_DISCORD_ID` | Existing configured bot administrator; also receives dashboard-owner access |
| `DASHBOARD_BRIDGE_SECRET` | Long random shared secret, read by Rust and the embedded bot runtime |
| `DASHBOARD_BRIDGE_URL` | Internal bot-management bridge URL; default `http://127.0.0.1:8091` |
| `DASHBOARD_ATLAS_BRIDGE_URL` | Private Knowledge Atlas bridge URL; default `http://127.0.0.1:8093` |
| `DASHBOARD_BRIDGE_HOST` | TypeScript bridge bind host; loopback only, default `127.0.0.1` |
| `DASHBOARD_BRIDGE_PORT` | TypeScript bridge port; default `8091` |
| `DASHBOARD_PICKER_URL` | Private picker URL; default `http://127.0.0.1:8092` |
| `DASHBOARD_PORT` | Public Rust service port; default `8080` |
| `LIBSQL_PATH` | Shared local libSQL file for bot data, dashboard sessions, OAuth states, rate limits, refresh leases and cookie consent; default `./data/bot/lemegeton.db` |
| `DASHBOARD_SESSION_DB_PATH` | Optional legacy SQLite dashboard file imported at startup; leave unset on new installations |
| `DASHBOARD_ALLOW_PUBLIC_BIND` | Explicit opt-in to a non-loopback bind; only enable behind platform ingress or a protected reverse proxy |
| `CUSTOM_ROLES_PUBLIC_URL` | Exact browser-visible origin for picker mutation Origin checks; match `DASHBOARD_PUBLIC_URL` |
| `CUSTOM_ROLES_TRUST_PROXY` | Enable only when the trusted ingress appends the real client IP as the rightmost `X-Forwarded-For` entry |

Use a random `DASHBOARD_BRIDGE_SECRET` of at least 32 UTF-8 bytes (for example, `openssl rand -hex 32`). Do not commit it. Rust refuses to call the bot bridge with a shorter value; the TypeScript bridge and picker refuse non-loopback listeners. The Rust web service binds to `127.0.0.1` by default. On production HTTPS, set `DASHBOARD_PUBLIC_URL` and `CUSTOM_ROLES_PUBLIC_URL` to the same browser-visible origin and `DASHBOARD_COOKIE_SECURE=true`; startup fails closed if a non-local HTTP origin or mismatched OAuth callback is configured. The configured OAuth callback must exactly match the Discord Developer Portal entry.

The bot requires its Discord token and the shared `LIBSQL_PATH`, `ROCKSDB_PATH` and `BACKUP_DIRECTORY` paths. The dashboard does not create a second Discord client or a second command registry. In Discord, **/settings** is the command-control entry point; guild feature toggles and relevant setup controls live in its private panel. The old `/dashboard` command surface is not part of the v3 registry.

## Local development

1. Install dependencies with `npm install` and `npm install --prefix web/frontend`.
2. Install Node.js 22 or newer and a current stable Rust toolchain.
3. Configure the environment values above and the existing bot/database values.
4. Build the frontend: `npm install --prefix web/frontend && npm run typecheck --prefix web/frontend && npm run build --prefix web/frontend`.
5. Build the public service: `cargo build --manifest-path web/backend/Cargo.toml`.
6. Start the dashboard backend with `cargo run --manifest-path web/backend/Cargo.toml` from the repository root in one terminal.
7. Build the bot with `npm run build` and start it with `npm start`. It starts the private Custom Roles picker listener automatically when enabled.
8. Open the public dashboard address. For local development, register `http://localhost:8080/oauth/callback` and use `DASHBOARD_PUBLIC_URL=http://localhost:8080`.

For the combined deployment entry point, build the frontend assets and release binary first, then use `./scripts/start.sh`. The Railway build command installs Node dependencies, generates the frontend assets, compiles the Rust service, and starts both services through this script. `web/frontend/out/` is generated static-export output and is not a frontend source directory.

## Testing and checks

- Rust unit tests: `cargo test --manifest-path web/backend/Cargo.toml`
- Rust formatting: `cargo fmt --manifest-path web/backend/Cargo.toml -- --check`
- TypeScript bot: `npm run typecheck && npm test`
- TypeScript bot: `npm run typecheck && npm test` (the test command builds the bot before running the Node test suite).
- Next.js frontend: `npm run typecheck --prefix web/frontend && npm run test:unit --prefix web/frontend && npm run build --prefix web/frontend && npm run test:e2e --prefix web/frontend`.
- Rust dashboard: `cargo test --manifest-path web/backend/Cargo.toml` and `cargo fmt --manifest-path web/backend/Cargo.toml -- --check`.
- Docker contract: `bash -n scripts/start.sh`, `docker compose config --quiet`, and `docker build --tag lemegeton:local .`.

The TypeScript workflow builds the libSQL and RocksDB native addons and runs the bot tests against isolated local files. The Rust workflow checks the complete workspace; frontend, dependency, container and repository-security checks run separately. Live Discord permissions and external provider credentials still require owner-controlled acceptance.

## Operational notes

- Rust dashboard sessions, single-use OAuth state, write/OAuth rate events, Discord refresh-token leases and anonymous cookie preference records share the same libSQL database as the bot. Cookie choices are retained for 180 days. Keep the database on persistent local storage accessible to both processes, with directory permissions restricted to the service account.
- Gateway status from the TypeScript bridge is reported as online, degraded (ready but at least 500 ms latency), offline (a previously ready connection is no longer ready), or connecting (ready has not yet been observed). If the bot bridge is down, status is unknown with the last in-memory observation where available. Command mutations fail instead of returning optimistic success.
- Application command visibility in Discord is distinct from command execution. The v3 bridge publishes the consolidated global command registry; it is not a per-guild command registrar and does not promise to retain unrelated legacy application commands outside that registry.
- libSQL is the single authoritative store for bot, guild configuration, archive, community, media and dashboard state. RocksDB stores private media objects; it does not contain guild configuration or authorization records.
- If the dashboard sign-in button fails, verify the application ID, client secret, exact callback URL, public origin, and secure-cookie setting. If login works but command data is unavailable, verify the bridge secret matches, the TypeScript bridge is listening on loopback port 8091, and both processes can open the configured `LIBSQL_PATH`.

## Production deployment: VPS, systemd, and Nginx

For a VPS, use the separate systemd services and Nginx reverse proxy in `deploy/vps/`. The bot and public Rust service run as different unprivileged users; only the bot user can write bot data and logs. Rust binds to loopback, the bot bridge and TypeScript custom-role picker stay on loopback, and Nginx terminates TLS and limits public request rates.

Read [the VPS deployment guide](../deploy/vps/README.md) before opening firewall ports. Expose only SSH and HTTPS (HTTP may be open for the redirect/ACME flow); do not expose ports 8080, 8091, or 8092 publicly. Keep OAuth client secrets and the bridge secret in root-owned service environment files, not in Git. Set the public origin and OAuth callback to the same HTTPS host, set `DASHBOARD_COOKIE_SECURE=true`, and use a unique 32-byte-or-longer bridge secret in both service environments.

The default VPS example runs one Rust dashboard instance. For local load balancing, install `lemegeton-dashboard@.service`, disable the single-instance unit, and start `@8080`, `@8081` and `@8082`. Nginx uses `least_conn` across those loopback workers. Each instance shares the same `LIBSQL_PATH` file for bot and dashboard state. Keep that database on local same-host persistent storage rather than NFS or cross-host filesystems. The Discord bot/gateway stays a single service. `/health/ready` checks the shared libSQL store; open-source Nginx uses passive failure handling, so monitor readiness externally.

## Docker Compose deployment

A minimal Docker deployment is provided by `Dockerfile`, `.dockerignore`, and `docker-compose.yml`. It builds the TypeScript bundle and Rust release binary in separate build stages, runs as a non-root user, drops Linux capabilities, applies `no-new-privileges`, and publishes port 8080 only on the host loopback interface for a host-level reverse proxy. Create the bind-mounted `data`, `logs`, and `runtime-home` directories and set their ownership to UID/GID `10001` before starting it. Keep `.env` out of the image and readable only by the Docker operator.

The combined container uses `scripts/start.sh` to supervise the compiled TypeScript bot and Rust dashboard. Bot and dashboard state are persisted together at `/app/data/bot/lemegeton.db`, with RocksDB objects at `/app/data/objects` and backup bundles at `/app/data/backups`; the startup script applies a restrictive umask. The TypeScript bot serves the private Custom Roles picker assets and bridge; the Rust service reverse-proxies the picker. For stronger process isolation on a VPS, use the separate systemd services and keep both private listeners on loopback.

## Security and dependency checks

The dashboard workflow runs the TypeScript type-check, `npm audit`, production asset checks, Rust tests, and `cargo audit` against the dependency resolution for that run. Tokio's minimum version is pinned above the October 2026 race-condition advisory's affected release; the advisory documents `1.54.1` as patched: [RUSTSEC-2026-0384](https://rustsec.org/advisories/RUSTSEC-2026-0384.html). The Next.js frontend toolchain is audited in the dashboard workflow as well.

See [the security review and residual risks](SECURITY_AUDIT.md). Automated tests are not a substitute for rotating previously exposed credentials, a real TLS/OAuth deployment smoke test, OS updates, or a production penetration test.

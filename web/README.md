# Lemegeton Web Dashboard

The dashboard is Lemegeton's optional web control plane. It lets authorized Discord server managers configure the bot without creating a second bot runtime or moving application logic out of the existing TypeScript bot.

**Frontend:** Next.js, React, TypeScript and CSS  
**Dashboard service:** Rust, Axum and Tokio  
**Bot data:** PostgreSQL, through the existing TypeScript bot and its private bridge  
**Dashboard coordination:** SQLite in WAL mode for sessions, OAuth state, rate-limit events and refresh leases

This document is the web project's file map and implementation guide. It distinguishes files that exist today from the fuller dashboard structure planned for the revamp.

- [Repository README](../README.md)
- [Dashboard behavior and deployment guide](../docs/DASHBOARD.md)
- [System architecture](../docs/ARCHITECTURE.md)
- [Environment template](../.env.example)
- [VPS deployment guide](../deploy/vps/README.md)

---

## 1. Responsibility boundaries

The dashboard is a control plane, not another bot.

| Part | Owns |
|:--|:--|
| Next.js frontend | Pages, layout, interactive controls, client-side validation and presentation |
| Rust/Axum service | Discord OAuth2, browser sessions, CSRF checks, authorization, dashboard API, rate limiting, static asset serving and the private bot bridge |
| TypeScript bot | Discord gateway, command registry, command execution, guild feature settings and application services |
| PostgreSQL | Authoritative bot, guild, member, archive and media data |
| SQLite | Small dashboard-only session and coordination records; it does not replace PostgreSQL |

The browser never receives the Discord bot token, dashboard bridge secret, OAuth client secret, database credentials or provider secrets. There is no Next.js API server or separate Node backend in this design. OAuth callback handling and protected writes stay in Rust.

The current frontend is configured as a static export. Rust serves the exported pages and assets from the same origin. Any implementation of the requested **/userId/guildId/** dashboard paths must preserve that deployment model or explicitly change it as a separate architecture decision; do not accidentally introduce a Node server to make dynamic routes work.

## 2. Current tracked structure

This is the actual **web/** tree on **lemegeton-v3** before the planned revamp files are added.

```text
web/
├── backend/
│   ├── Cargo.toml
│   └── src/
│       ├── api.rs
│       ├── auth.rs
│       ├── main.rs
│       ├── state.rs
│       ├── store.rs
│       └── ui.rs
├── favicon.svg
├── frontend/
│   ├── app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── page.tsx
│   ├── next-env.d.ts
│   ├── next.config.ts
│   ├── package.json
│   ├── src/
│   │   └── App.tsx
│   └── tsconfig.json
├── picker.css
├── picker.html
├── picker.js
└── theme.css
```

### Existing file responsibilities

| File | Current responsibility |
|:--|:--|
| backend/src/main.rs | Rust service entry point and startup |
| backend/src/api.rs | Dashboard HTTP routes and API handling |
| backend/src/auth.rs | Discord OAuth and session authentication |
| backend/src/state.rs | Shared application state |
| backend/src/store.rs | SQLite-backed dashboard persistence and coordination |
| backend/src/ui.rs | Static frontend and UI response handling |
| backend/Cargo.toml | Rust dependencies and package configuration |
| frontend/app/ | Next.js App Router pages, layout and global CSS |
| frontend/src/App.tsx | Existing React dashboard interface |
| frontend/package.json | Frontend scripts and dependencies |
| picker.html, picker.js, picker.css | Existing Custom Roles picker interface |
| theme.css | Existing picker theme stylesheet |
| favicon.svg | Web service icon |

The picker is an existing separate interface. It is not the dashboard's main component system and should not be used as a reason to duplicate the dashboard's forms, icon registry or layout.

---

## 3. Complete planned dashboard structure

The following tree is the intended organization for the dashboard revamp. **Except for the files listed in section 2, these are planned paths, not files that currently exist.** Add them as implementation lands; do not create empty placeholders or claim the features are operational beforehand.

```text
web/
├── README.md
├── favicon.svg
├── theme.css
├── picker.html
├── picker.js
├── picker.css
│
├── frontend/
│   ├── app/
│   │   ├── (dashboard)/
│   │   │   └── [userId]/
│   │   │       └── [guildId]/
│   │   │           ├── layout.tsx
│   │   │           ├── page.tsx
│   │   │           ├── commands/
│   │   │           │   └── page.tsx
│   │   │           ├── roles/
│   │   │           │   └── page.tsx
│   │   │           ├── channels/
│   │   │           │   └── page.tsx
│   │   │           └── settings/
│   │   │               └── page.tsx
│   │   ├── login/
│   │   │   └── page.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   │
│   ├── src/
│   │   ├── App.tsx
│   │   │
│   │   ├── Components/
│   │   │   ├── Icons/
│   │   │   │   ├── Actions/
│   │   │   │   │   ├── SaveIcon.tsx
│   │   │   │   │   ├── ResetIcon.tsx
│   │   │   │   │   ├── CloseIcon.tsx
│   │   │   │   │   └── RefreshIcon.tsx
│   │   │   │   ├── Navigation/
│   │   │   │   │   ├── ChevronIcon.tsx
│   │   │   │   │   ├── MenuIcon.tsx
│   │   │   │   │   └── ExternalLinkIcon.tsx
│   │   │   │   ├── Status/
│   │   │   │   │   ├── CheckIcon.tsx
│   │   │   │   │   ├── AlertIcon.tsx
│   │   │   │   │   ├── LoaderIcon.tsx
│   │   │   │   │   └── ShieldIcon.tsx
│   │   │   │   ├── Discord/
│   │   │   │   │   ├── DiscordIcon.tsx
│   │   │   │   │   ├── ServerIcon.tsx
│   │   │   │   │   └── RoleIcon.tsx
│   │   │   │   ├── Icon.tsx
│   │   │   │   ├── IconButton.tsx
│   │   │   │   ├── IconRegistry.ts
│   │   │   │   └── index.ts
│   │   │
│   │   │   ├── Layout/
│   │   │   │   ├── DashboardShell.tsx
│   │   │   │   ├── DashboardSidebar.tsx
│   │   │   │   ├── DashboardHeader.tsx
│   │   │   │   └── GuildSwitcher.tsx
│   │   │   ├── Feedback/
│   │   │   │   ├── LoadingState.tsx
│   │   │   │   ├── ErrorState.tsx
│   │   │   │   ├── EmptyState.tsx
│   │   │   │   └── ToastProvider.tsx
│   │   │   ├── Forms/
│   │   │   │   ├── FormField.tsx
│   │   │   │   ├── Toggle.tsx
│   │   │   │   └── Select.tsx
│   │   │   ├── Dialogs/
│   │   │   │   ├── ConfirmActionDialog.tsx
│   │   │   │   └── UnsavedChangesDialog.tsx
│   │   │   └── SaveChangesBar.tsx
│   │   │
│   │   ├── Features/
│   │   │   ├── Auth/
│   │   │   │   ├── AuthGuard.tsx
│   │   │   │   └── useSession.ts
│   │   │   ├── Consent/
│   │   │   │   ├── ConsentGate.tsx
│   │   │   │   └── useConsent.ts
│   │   │   ├── Guilds/
│   │   │   │   ├── GuildGrid.tsx
│   │   │   │   ├── GuildCard.tsx
│   │   │   │   └── useGuildAccess.ts
│   │   │   ├── Commands/
│   │   │   │   ├── CommandList.tsx
│   │   │   │   ├── CommandRuleEditor.tsx
│   │   │   │   └── useCommandRules.ts
│   │   │   ├── Roles/
│   │   │   │   ├── RolePermissionEditor.tsx
│   │   │   │   └── useRolePermissions.ts
│   │   │   └── Channels/
│   │   │       ├── ChannelRuleEditor.tsx
│   │   │       └── useChannelRules.ts
│   │   │
│   │   ├── Hooks/
│   │   │   ├── useDirtyState.ts
│   │   │   ├── useUnsavedChanges.ts
│   │   │   └── useReducedMotion.ts
│   │   ├── Lib/
│   │   │   ├── api.ts
│   │   │   ├── auth.ts
│   │   │   ├── routes.ts
│   │   │   └── validation.ts
│   │   ├── Types/
│   │   │   ├── auth.ts
│   │   │   ├── guild.ts
│   │   │   ├── command.ts
│   │   │   └── settings.ts
│   │   └── three/
│   │       ├── DashboardScene.tsx
│   │       └── SceneFallback.tsx
│   │
│   └── tests/
│       ├── auth-guard.test.tsx
│       ├── guild-access.test.tsx
│       ├── consent-flow.test.tsx
│       ├── save-changes-bar.test.tsx
│       ├── unsaved-changes.test.tsx
│       ├── command-rules.test.tsx
│       └── rate-limit-ui.test.tsx
│
└── backend/
    └── src/
        ├── rate_limit.rs
        └── rate_limit_tests.rs
```

### Frontend folder map

| Folder | Purpose |
|:--|:--|
| app/ | Route entry points and shared page shell |
| Components/Icons/ | One central animated SVG icon system, grouped by action, navigation, status and Discord usage |
| Components/Layout/ | Dashboard shell, navigation, header and guild switching |
| Components/Feedback/ | Loading, error, empty and toast states |
| Components/Forms/ | Reusable, accessible form controls |
| Components/Dialogs/ | Explicit confirmations and unsaved-change handling |
| Components/SaveChangesBar.tsx | Shared Discord-style Reset / Save Changes surface |
| Features/Auth/ | Browser session state and route protection presentation |
| Features/Consent/ | Terms and privacy acceptance presentation |
| Features/Guilds/ | Guild picker, membership state and access presentation |
| Features/Commands/ | Command list and command rule editing |
| Features/Roles/ | Role include/exclude rule editing |
| Features/Channels/ | Channel include/exclude rule editing |
| Hooks/ | Dirty-state, navigation protection and reduced-motion hooks |
| Lib/ | Typed Rust API client, route helpers and client validation |
| Types/ | Shared frontend response and configuration types |
| three/ | Optional WebGL scene and non-WebGL fallback |
| tests/ | Focused UI, authorization-state and failure-path tests |

The existing app/page.tsx, app/login/page.tsx, app/layout.tsx, app/globals.css and src/App.tsx should be extended or migrated deliberately. Do not create parallel versions of the same page or leave two competing dashboard shells.

The OAuth callback remains a Rust endpoint (currently documented as **/oauth/callback**). Do not add a Next.js route handler for OAuth or dashboard writes: that would create a second backend surface and split security responsibilities.

### Backend folder map

| File | Responsibility |
|:--|:--|
| main.rs | Rust service entry point and startup |
| api.rs | Public dashboard routes, OAuth callback and API handlers |
| auth.rs | Discord OAuth, session validation, CSRF and authorization checks |
| state.rs | Shared service state and dependencies |
| store.rs | SQLite session, OAuth-state, rate-event and refresh-lease persistence |
| ui.rs | Static-export asset serving and UI fallback behavior |
| rate_limit.rs | Planned Axum rate-limit middleware and request policy |
| rate_limit_tests.rs | Planned focused tests for limits, concurrency and retry responses |

Keep the backend small and module responsibilities clear. Add another Rust module only when the code has a real independent responsibility.

---

## 4. Dashboard behavior

### Sign-in and guild selection

1. A user signs in through Discord OAuth2 using the configured **identify** and **guilds** scopes.
2. Rust creates and validates the browser session. The session cookie is HttpOnly, SameSite=Lax and expires; write requests also require origin validation and a CSRF token.
3. The guild picker displays servers the user can manage.
4. A guild where the bot is already installed is shown as available.
5. A guild where the user can invite the bot but it is not installed is shown as disabled/greyed, with an Invite action rather than editable settings.
6. Selecting an installed guild opens the intended **/userId/guildId/** area and its settings sections.

The URL's user and guild IDs are routing values only. Every protected Rust request must independently verify the signed-in Discord identity, current guild membership and current Manage Server or Administrator permission. It must also verify that the bot is still a member of the selected guild. Never authorize from a URL, cached browser object or stale permission claim.

Unauthenticated requests should go through Discord sign-in and return to the original safe destination after the callback. Validate return paths to prevent open redirects.

### Command, role and channel rules

- Command settings are scoped to one guild.
- Role and channel selectors must use current Discord guild data.
- Include and exclude rules must be explicit and have deterministic precedence.
- A command outside its allowed channel rules must be hidden/disabled in the dashboard and rejected by the bot-side runtime check.
- A selected role or channel that is deleted or no longer available must be reported as stale; do not silently broaden access.
- Discord-native application command permissions and bot-side checks are separate enforcement layers. Do not claim that Discord natively enforces every custom channel rule if the platform API does not support that exact rule.

The TypeScript bot remains the source of truth for the command registry and runtime feature guard. Rust authorizes dashboard access and forwards approved changes through the private bridge.

### Save Changes and Reset

Every settings section tracks its own last server-confirmed snapshot and its local draft.

| State | Required behavior |
|:--|:--|
| Clean | No action bar; no unnecessary save request |
| Dirty | Show the action bar |
| Saving | Disable duplicate submission and show progress |
| Saved | Confirm success and update the saved snapshot |
| Failed | Keep the user's edits and show a recoverable error |
| Conflict | Do not overwrite a newer server revision; ask the UI to reload or reconcile |

The action bar follows the requested Discord pattern:

- **Reset** is neutral grey and restores the last server-confirmed values for that section.
- **Save Changes** is green and saves only that section's validated changes.
- Both controls have clear disabled, focus, hover, pressed and pending states.
- Double-clicking Save must not create duplicate writes.
- Navigation with unsaved edits must warn before discarding them.
- A failed save must never clear the local draft.
- A stale revision must be rejected rather than silently overwriting newer settings.

### Consent and privacy

The dashboard must present the repository's existing Terms of Service and Privacy Policy and record the required acceptance through the authenticated service. Explain what data is used, why it is needed, and how to withdraw or request applicable privacy actions. Do not create a second policy that contradicts the canonical documents.

---

## 5. Design and interaction rules

The visual direction is premium monochrome / Nothing OS-inspired: strong hierarchy, restrained surfaces, precise spacing, clear state changes and minimal unnecessary copy. Avoid a generic admin template.

- Use local/system font stacks. Do not load Google Fonts or other remote font files.
- Use the shared Components/Icons registry for dashboard iconography rather than embedding unrelated icon implementations in each screen.
- Icons may animate on hover, press, loading and state transitions. Respect prefers-reduced-motion; animation must not carry meaning by itself.
- Use WebGL/Three.js only for decorative atmosphere and transitions. Navigation, forms, settings and status feedback must remain usable if WebGL fails, is blocked or is disabled.
- Keep controls keyboard accessible, labelled and readable at increased zoom.
- Every form needs empty, loading, invalid, disabled, success and error behavior where applicable.
- Do not use motion to hide loading delays or mask a failed operation.

### What-if interaction checklist

| What if… | Required result |
|:--|:--|
| Save is clicked twice quickly | One logical write; button enters pending state |
| Reset is clicked after editing | Restore only that section's last saved snapshot |
| A save request fails | Keep the draft and allow retry |
| The browser submits an outdated revision | Reject conflict; do not overwrite newer data |
| The user's Discord permission is removed | The next protected request is denied |
| The bot is removed from the guild | Disable configuration and explain why |
| A role or channel no longer exists | Mark the rule stale; do not widen access |
| A user changes URL IDs | Rust re-checks identity, guild membership and permissions |
| A session expires during editing | Re-authenticate safely; do not claim unsaved work was saved |
| A request is spammed | Return 429 with a useful Retry-After value |
| An input contains HTML or script-like text | Validate as data and render as text; never evaluate it |
| An oversized or malformed request arrives | Reject it before expensive processing |
| WebGL or an animated icon fails | Keep the functional CSS/HTML fallback |
| Reduced motion is enabled | Preserve state feedback without motion |
| SQLite is locked or unavailable | Fail safely; do not bypass rate limits or authorization |

---

## 6. Rate limiting and load balancing

Rate limiting must be enforced by the Rust service, not only by disabled frontend buttons.

### Planned enforcement layers

1. **Ingress proxy:** Apply coarse IP-level limits and connection protections before traffic reaches Axum.
2. **Axum middleware:** Apply endpoint-specific limits and identify the authenticated account and guild where available.
3. **Shared dashboard store:** Use atomic SQLite transactions for rate events and limit decisions so multiple Rust workers on the same host observe the same counters.
4. **Response contract:** Return HTTP 429 and a meaningful Retry-After value when a limit is reached.

Limit keys should distinguish the relevant dimensions: client IP, signed-in account, guild and route/action. Include burst and sustained limits, request-body and upload-size limits, and concurrency protection for expensive operations. Configure trusted proxy handling explicitly; do not trust arbitrary X-Forwarded-For values from the public internet.

### SQLite and worker model

SQLite is the dashboard's secondary coordination store, not another PostgreSQL database and not the bot's primary data store. For the documented same-host Nginx setup, multiple Rust workers can share the same local persistent SQLite WAL file for sessions, OAuth state, rate events and refresh leases. Use transactional updates and handle lock contention deliberately.

This design is for workers on the same host and local filesystem. Do not put the WAL database on NFS or treat it as a cross-host distributed database. Multi-host horizontal scaling would require a separate shared-storage decision; do not silently add Redis or a second PostgreSQL service.

The bot gateway remains a single bot process. Load balancing applies to the Rust dashboard service, not to multiple competing Discord gateway clients.

---

## 7. Build, run and verify

Run commands from the repository root unless the command explicitly changes directory.

### Frontend

```bash
npm install --prefix web/frontend
npm run typecheck --prefix web/frontend
npm run build --prefix web/frontend
```

The production frontend is statically exported and served by Rust. Build output is generated; do not commit node_modules/, .next/ or exported output unless the repository's deployment workflow explicitly requires it.

### Rust dashboard

```bash
cargo fmt --manifest-path web/backend/Cargo.toml -- --check
cargo test --manifest-path web/backend/Cargo.toml
cargo build --manifest-path web/backend/Cargo.toml --release
```

### Relevant integration checks

- Verify OAuth callback URL, session cookie attributes, CSRF and logout invalidation.
- Test direct requests to another user's or another guild's URL.
- Revoke a user's Discord permission and verify the next request is rejected.
- Remove the bot from a guild and verify its dashboard becomes unavailable.
- Test the bridge while the bot is offline and while PostgreSQL is unavailable.
- Test rate-limit behavior through every load-balanced Rust worker.
- Confirm that all workers share the same local SQLite state and that lock errors fail safely.
- Test the frontend with WebGL unavailable and reduced motion enabled.

Live Discord OAuth, bot permissions, provider credentials and production ingress still require environment-specific acceptance. A successful local build does not prove those external integrations are configured correctly.

## 8. Configuration and operational references

The full environment template is in [the repository .env.example](../.env.example). The dashboard-specific variables include:

- Discord OAuth client ID, secret, public URL and exact redirect URI.
- Secure cookie configuration.
- Dashboard bridge secret and private bridge addresses.
- Rust service port and bind policy.
- SQLite session database path.
- Optional owner IDs and trusted-proxy configuration for the Custom Roles picker.

Keep secrets server-side and out of Git. Production must use HTTPS, secure cookies, a registered exact OAuth callback and a strong private bridge secret.

See [the dashboard implementation and operations guide](../docs/DASHBOARD.md) for the implemented OAuth, authorization, API, storage, local-development and deployment details. See [the VPS deployment guide](../deploy/vps/README.md) before exposing the service through a public reverse proxy.

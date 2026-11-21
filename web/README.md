# Lemegeton Web

<p align="center">
  <img src="frontend/public/brand/lemegeton.svg" alt="Lemegeton" width="88" />
</p>

<p align="center">
  <strong>LEMEGETON / CONTROL PLANE</strong><br />
  A private, multi-guild control centre for the Lemegeton Discord bot.
</p>

<p align="center">
  <strong>Next.js · React · TypeScript · Three.js · Rust · Axum</strong>
</p>

The web application is an optional dashboard for Discord server managers. It provides a secure interface for inspecting a server's bot status and configuring supported features without creating a second Discord gateway client or moving bot execution into the website.

This README is the source of truth for the web project's current files, target file structure, frontend/backend boundaries, migration rules, security model, design system and verification requirements.

- [Main repository README](../README.md)
- [Dashboard behavior and deployment](../docs/DASHBOARD.md)
- [System architecture](../docs/ARCHITECTURE.md)
- [Environment template](../.env.example)
- [VPS deployment guide](../deploy/vps/README.md)

---

## 1. Product boundaries

The dashboard is a control plane, not another bot and not a second application backend.

| Layer | Responsibility |
|:--|:--|
| Next.js App Router | Static page entry points and application shell |
| React + TypeScript | Dashboard interactions, components, state and client-side routing |
| Styled Components | Authored styling in TSX; no standalone CSS source files in the target |
| Three.js | Optional browser-side 3D/WebGL visuals |
| Rust + Axum | OAuth, sessions, authorization, API routes, rate limiting, asset serving and bot bridge |
| Existing TypeScript bot | Discord gateway, command registry, command execution and guild feature logic |
| PostgreSQL | Authoritative bot, guild, member, archive and media data |
| SQLite | Dashboard sessions and same-host coordination state |

The browser must never receive the Discord bot token, OAuth client secret, database credentials, private bridge secret, provider credentials or privileged refresh tokens.

There is no Next.js API server. OAuth callbacks, protected configuration writes, permission checks and rate limiting remain in Rust. The existing TypeScript bot remains responsible for executing Discord commands.

## 2. Current tracked web structure

This is the actual **web/** tree after the first dashboard foundation changes on `lemegeton-v3`.

~~~text
web/
├── README.md
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
│   │   ├── error.tsx
│   │   ├── global-error.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── loading.tsx
│   │   ├── login/
│   │   │   └── page.tsx
│   │   ├── not-found.tsx
│   │   └── page.tsx
│   ├── next-env.d.ts
│   ├── next.config.ts
│   ├── package.json
│   ├── public/
│   │   └── brand/
│   │       └── lemegeton.svg
│   ├── src/
│   │   ├── App.tsx
│   │   └── Components/
│   │       ├── Brand/
│   │       │   └── BrandMark.tsx
│   │       ├── Icons/
│   │       │   ├── Icon.tsx
│   │       │   ├── IconRegistry.ts
│   │       │   └── index.ts
│   │       └── Feedback/
│   │           ├── ErrorState.tsx
│   │           └── NotFoundState.tsx
│   └── tsconfig.json
├── picker.css
├── picker.html
├── picker.js
└── theme.css
~~~

### Existing file responsibilities

| Path | Responsibility / status |
|:--|:--|
| backend/src/main.rs | Axum startup; browser fallback serves the exported custom 404 and API fallback returns JSON 404 |
| backend/src/ui.rs | Static export and asset serving, including the generated 404 document |
| backend/src/api.rs | Dashboard API handlers and private Custom Roles service proxy |
| backend/src/auth.rs | Discord OAuth start/callback, session creation, bootstrap and logout |
| backend/src/state.rs | Shared configuration, sessions, guild authorization and bridge helpers |
| backend/src/store.rs | SQLite WAL session and coordination persistence |
| frontend/src/App.tsx | Existing dashboard; navigation now uses shared animated SVG icons and the Lemegeton brand mark |
| frontend/src/Components/Brand/BrandMark.tsx | Shared web-owned Lemegeton logo component |
| frontend/src/Components/Icons/Icon.tsx | Animated SVG renderer with reduced-motion handling |
| frontend/src/Components/Icons/IconRegistry.ts | Typed icon-name registry |
| frontend/src/Components/Icons/index.ts | Shared icon exports |
| frontend/src/Components/Feedback/NotFoundState.tsx | Branded 404 presentation |
| frontend/src/Components/Feedback/ErrorState.tsx | Recoverable dashboard failure presentation |
| frontend/app/not-found.tsx | Next.js custom not-found entry |
| frontend/app/error.tsx | Next.js route error boundary |
| frontend/app/global-error.tsx | Root-level Next.js error boundary |
| frontend/app/loading.tsx | Next.js route loading state |
| frontend/public/brand/lemegeton.svg | Web-owned copy of the existing Lemegeton logo |
| picker.html, picker.js, picker.css, theme.css | Still-tracked migration inputs; port behavior to TSX/TypeScript before deleting |

The custom 404 is generated by Next.js as build output and served by Rust with HTTP 404. No authored HTML page was added. The existing global and picker CSS files remain migration work; this first implementation does not claim the CSS-to-TSX migration is complete.

---

## 3. Complete target project structure

The tree below is the complete planned web structure. It includes current files that will be retained, files that will be reorganized, and new files required for the dashboard revamp.

**Legend**

- **Existing** — already tracked in the current web directory.
- **Extend** — keep the file and add the required behavior.
- **Migrate** — move behavior out of a legacy file into the new TypeScript/TSX implementation, then remove the old file after parity checks.
- **Planned** — new source file to add when its feature is implemented.

~~~text
web/
├── README.md
│
├── backend/
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs                         # Existing: Axum startup and route registration
│       ├── api.rs                          # Existing: API handlers and bot bridge proxy
│       ├── auth.rs                         # Existing: Discord OAuth and sessions
│       ├── state.rs                        # Existing: app state and authorization helpers
│       ├── store.rs                        # Existing: SQLite persistence and coordination
│       ├── ui.rs                           # Existing: static assets and UI route responses
│       └── rate_limit.rs                   # Planned: shared endpoint policies and middleware
│
└── frontend/
    ├── app/
    │   ├── layout.tsx                      # Extend: metadata, providers and root shell
    │   ├── page.tsx                        # Extend: entry point rendered by Rust-served shell
    │   ├── login/
    │   │   └── page.tsx                    # Extend: Discord login screen
    │   ├── custom-roles/
    │   │   └── page.tsx                    # Planned: React/TSX replacement for the legacy picker
    │   ├── terms/
    │   │   └── page.tsx                    # Planned: existing Terms document viewer
    │   ├── privacy/
    │   │   └── page.tsx                    # Planned: existing Privacy document viewer
    │   ├── guidelines/
    │   │   └── page.tsx                    # Planned: existing Community Guidelines viewer
    │   ├── loading.tsx                     # Planned: route loading state
    │   ├── not-found.tsx                   # Planned: custom 404 route
    │   ├── error.tsx                       # Planned: route-level failure boundary
    │   └── global-error.tsx                # Planned: root-level failure boundary
    │
    ├── src/
    │   ├── App.tsx                         # Existing: progressively split into feature views
    │   │
    │   ├── Components/
    │   │   ├── Icons/
    │   │   │   ├── index.ts
    │   │   │   ├── Icon.tsx
    │   │   │   ├── IconButton.tsx
    │   │   │   ├── IconRegistry.ts
    │   │   │   ├── Actions/
    │   │   │   │   ├── SaveIcon.tsx
    │   │   │   │   ├── ResetIcon.tsx
    │   │   │   │   ├── EditIcon.tsx
    │   │   │   │   ├── DeleteIcon.tsx
    │   │   │   │   ├── CopyIcon.tsx
    │   │   │   │   └── RefreshIcon.tsx
    │   │   │   ├── Navigation/
    │   │   │   │   ├── OverviewIcon.tsx
    │   │   │   │   ├── CommandsIcon.tsx
    │   │   │   │   ├── ArchiveIcon.tsx
    │   │   │   │   ├── MenuIcon.tsx
    │   │   │   │   └── ChevronIcon.tsx
    │   │   │   ├── Status/
    │   │   │   │   ├── SuccessIcon.tsx
    │   │   │   │   ├── ErrorIcon.tsx
    │   │   │   │   ├── WarningIcon.tsx
    │   │   │   │   ├── LoadingIcon.tsx
    │   │   │   │   └── ShieldIcon.tsx
    │   │   │   └── Discord/
    │   │   │       ├── DiscordIcon.tsx
    │   │   │       ├── GuildIcon.tsx
    │   │   │       ├── RoleIcon.tsx
    │   │   │       └── ChannelIcon.tsx
    │   │   │
    │   │   ├── Layout/
    │   │   │   ├── DashboardShell.tsx
    │   │   │   ├── Sidebar.tsx
    │   │   │   ├── Topbar.tsx
    │   │   │   ├── GuildSwitcher.tsx
    │   │   │   └── MobileNavigation.tsx
    │   │   │
    │   │   ├── UI/
    │   │   │   ├── Button.tsx
    │   │   │   ├── IconButton.tsx
    │   │   │   ├── Input.tsx
    │   │   │   ├── Select.tsx
    │   │   │   ├── Switch.tsx
    │   │   │   ├── Badge.tsx
    │   │   │   ├── Card.tsx
    │   │   │   ├── Tabs.tsx
    │   │   │   ├── Tooltip.tsx
    │   │   │   └── DataTable.tsx
    │   │   │
    │   │   ├── Forms/
    │   │   │   ├── FormField.tsx
    │   │   │   ├── FormSection.tsx
    │   │   │   ├── SaveChangesBar.tsx
    │   │   │   └── UnsavedChangesDialog.tsx
    │   │   │
    │   │   ├── Dialogs/
    │   │   │   ├── ConfirmDialog.tsx
    │   │   │   └── DestructiveActionDialog.tsx
    │   │   │
    │   │   └── Feedback/
    │   │       ├── LoadingState.tsx
    │   │       ├── EmptyState.tsx
    │   │       ├── ErrorState.tsx
    │   │       ├── NotFoundState.tsx
    │   │       ├── ForbiddenState.tsx
    │   │       ├── OfflineState.tsx
    │   │       ├── RateLimitState.tsx
    │   │       └── ServiceUnavailableState.tsx
    │   │
    │   ├── Features/
    │   │   ├── Authentication/
    │   │   │   ├── LoginScreen.tsx
    │   │   │   ├── SessionGuard.tsx
    │   │   │   └── useSession.ts
    │   │   │
    │   │   ├── Consent/
    │   │   │   ├── ConsentGate.tsx
    │   │   │   ├── PolicyViewer.tsx
    │   │   │   └── useConsent.ts
    │   │   │
    │   │   ├── Guilds/
    │   │   │   ├── GuildOverview.tsx
    │   │   │   ├── GuildGrid.tsx
    │   │   │   ├── GuildCard.tsx
    │   │   │   ├── GuildSearch.tsx
    │   │   │   └── InviteBotAction.tsx
    │   │   │
    │   │   ├── Overview/
    │   │   │   ├── OverviewPage.tsx
    │   │   │   ├── BotStatusCard.tsx
    │   │   │   ├── CommandSummary.tsx
    │   │   │   ├── ActivitySummary.tsx
    │   │   │   └── ServerSummary.tsx
    │   │   │
    │   │   ├── Commands/
    │   │   │   ├── CommandsPage.tsx
    │   │   │   ├── CommandList.tsx
    │   │   │   ├── CommandDetails.tsx
    │   │   │   ├── CommandSettings.tsx
    │   │   │   ├── CommandAccessEditor.tsx
    │   │   │   ├── RoleAccessRules.tsx
    │   │   │   ├── ChannelAccessRules.tsx
    │   │   │   ├── AccessPreview.tsx
    │   │   │   └── useCommandSettings.ts
    │   │   │
    │   │   ├── CustomRoles/
    │   │   │   ├── RoleStudio.tsx
    │   │   │   ├── RolePreview.tsx
    │   │   │   ├── RoleNameEditor.tsx
    │   │   │   ├── ColorPicker.tsx
    │   │   │   ├── GradientEditor.tsx
    │   │   │   ├── RoleIconEditor.tsx
    │   │   │   ├── ImageUploader.tsx
    │   │   │   ├── ImageCropper.tsx
    │   │   │   ├── UploadValidation.ts
    │   │   │   └── useRoleStudio.ts
    │   │   │
    │   │   ├── Archive/
    │   │   │   ├── ArchiveSettings.tsx
    │   │   │   └── useArchiveSettings.ts
    │   │   │
    │   │   ├── KnowledgeAtlas/
    │   │   │   ├── KnowledgeAtlasPage.tsx
    │   │   │   ├── AtlasGraph.tsx
    │   │   │   ├── AtlasFilters.tsx
    │   │   │   └── AtlasDetailPanel.tsx
    │   │   │
    │   │   ├── Extensions/
    │   │   │   └── ExtensionsPage.tsx
    │   │   ├── Activity/
    │   │   │   └── AuditHistory.tsx
    │   │   ├── Diagnostics/
    │   │   │   ├── DiagnosticsPage.tsx
    │   │   │   └── HealthSummary.tsx
    │   │   ├── Logs/
    │   │   │   └── RuntimeLogs.tsx
    │   │   ├── Integrations/
    │   │   │   └── IntegrationsPage.tsx
    │   │   ├── Persistence/
    │   │   │   └── DatabaseStatus.tsx
    │   │   └── Settings/
    │   │       └── SettingsPage.tsx
    │   │
    │   ├── Three/
    │   │   ├── SceneLoader.tsx
    │   │   ├── SceneCanvas.tsx
    │   │   ├── MonochromeScene.tsx
    │   │   ├── OrbitalGeometry.tsx
    │   │   ├── ShaderMaterials.ts
    │   │   ├── SceneConfig.ts
    │   │   ├── DisposeScene.ts
    │   │   └── WebGLFallback.tsx
    │   │
    │   ├── DesignSystem/
    │   │   ├── ThemeProvider.tsx
    │   │   ├── GlobalStyles.tsx
    │   │   ├── Tokens.ts
    │   │   ├── Typography.ts
    │   │   ├── Motion.ts
    │   │   └── styled.d.ts
    │   │
    │   ├── Providers/
    │   │   ├── StyledComponentsRegistry.tsx
    │   │   └── AppProviders.tsx
    │   │
    │   ├── Hooks/
    │   │   ├── useDirtyState.ts
    │   │   ├── useSaveChanges.ts
    │   │   ├── useUnsavedChanges.ts
    │   │   └── useReducedMotion.ts
    │   │
    │   ├── Lib/
    │   │   ├── api.ts
    │   │   ├── routes.ts
    │   │   ├── validation.ts
    │   │   ├── svgValidation.ts
    │   │   ├── safeReturnPath.ts
    │   │   ├── errors.ts
    │   │   └── formatters.ts
    │   │
    │   ├── Config/
    │   │   ├── navigation.ts
    │   │   └── icons.ts
    │   │
    │   └── Types/
    │       ├── auth.ts
    │       ├── guild.ts
    │       ├── command.ts
    │       ├── permissions.ts
    │       ├── customRole.ts
    │       └── api.ts
    │
    ├── public/
    │   ├── brand/
    │   │   ├── lemegeton.svg
    │   │   ├── lemegeton-mark.svg
    │   │   ├── wordmark-light.svg
    │   │   ├── wordmark-dark.svg
    │   │   └── favicon.svg
    │   ├── icons/
    │   │   └── static/
    │   ├── textures/
    │   └── models/
    │
    ├── tests/
    │   ├── unit/
    │   │   ├── route-parser.test.ts
    │   │   ├── validation.test.ts
    │   │   └── permission-preview.test.ts
    │   ├── components/
    │   │   ├── save-changes-bar.test.tsx
    │   │   ├── custom-role-picker.test.tsx
    │   │   └── error-states.test.tsx
    │   └── e2e/
    │       ├── login-flow.spec.ts
    │       ├── guild-access.spec.ts
    │       ├── command-settings.spec.ts
    │       └── custom-roles.spec.ts
    │
    ├── package.json
    ├── next.config.ts
    ├── next-env.d.ts
    └── tsconfig.json
~~~

Only add a file when its responsibility is needed. This tree is the intended full organization, not an instruction to create empty placeholders for every planned path.

---

## 4. Legacy picker and theme migration

The existing standalone picker must become a normal part of the Next.js/React interface.

| Current file | Target | Final action |
|:--|:--|:--|
| web/picker.html | frontend/app/custom-roles/page.tsx | Remove old HTML after route parity |
| web/picker.js | frontend/src/Features/CustomRoles/*.tsx and *.ts | Move behavior into typed React components and TypeScript utilities, then remove |
| web/picker.css | Styled Components inside the picker components | Move visual rules to TSX, then remove |
| web/theme.css | frontend/src/DesignSystem/Tokens.ts and ThemeProvider.tsx | Move tokens to TypeScript, then remove |
| frontend/app/globals.css | frontend/src/DesignSystem/GlobalStyles.tsx | Migrate global styling, then remove the CSS file |
| web/favicon.svg | frontend/public/brand/favicon.svg | Move and update references |
| assets/icons/lemegeton.svg | frontend/public/brand/lemegeton.svg | Move or copy after checking every existing consumer |

### Custom Roles parity requirements

The TSX implementation must preserve the existing picker behavior before the old files are deleted:

- Color entry, normalization, preview and validation.
- Dark and light Discord message previews.
- Role name editing.
- Gradient and enhanced-style capability checks.
- Role icon emoji and image selection.
- Image upload, crop and size validation.
- Existing access/error banners and loading states.
- Private picker-token handling.

The current picker receives its short-lived token after the URL fragment. The migration must preserve the important security properties: consume the fragment, remove it from the visible address, keep the token tab-local, send it only in the Authorization header, never put it in a query string, and never forward the dashboard session cookie to the picker service.

The current Rust proxy owns the /custom-roles path. During migration, the browser page will own /custom-roles/ and the Rust proxy will move to an API-only namespace such as /api/custom-roles/. Keep the picker service private until its functionality has been migrated and verified. Do not expose its internal port publicly.

### SVG and pasted input safety

SVG is an accepted asset format, but an SVG upload is still untrusted input. Do not inject pasted markup into the DOM or render arbitrary SVG strings directly. Validate the file type and size, reject scripts, event attributes, foreignObject and external references, and use a trusted sanitizing/rasterization path before preview or storage. Server-side checks remain authoritative.

---

## 5. Styling: TSX only

The final authored frontend source should contain:

- TypeScript: .ts
- React components: .tsx
- Static vector assets: .svg
- Configuration and metadata: .json, .toml and other required non-HTML source formats

Do not add authored .html, .css or .js files.

Use Styled Components for component styles and global styles. Global tokens belong in Tokens.ts; the shared theme belongs in ThemeProvider.tsx; GlobalStyles.tsx defines the reset, base typography, focus behavior, scrollbars and global layout. StyledComponentsRegistry.tsx integrates style collection with the Next.js App Router.

The current globals.css, picker.css and theme.css are migration inputs only. They are not part of the target tree.

### Generated output is different from authored source

Next.js static export necessarily emits HTML documents and browser assets into its build output directory. Those are generated build artifacts, not manually authored project files. Do not commit generated out/, .next/ or node_modules/ directories unless a deployment process explicitly requires them.

---

## 6. Where Three.js lives

Three.js is a JavaScript library, but it is fully usable from TypeScript and TSX. The project does not need a standalone .js file.

The dashboard uses React Three Fiber as the React renderer for Three.js:

| Technology | Use |
|:--|:--|
| three | Core Three.js scene, geometry, materials and renderer |
| @types/three | TypeScript declarations for Three.js |
| @react-three/fiber | React renderer and lifecycle integration |
| Custom ShaderMaterial | Small, authored shader effects for the monochrome visual identity |

The current frontend uses React 19, so the planned renderer is React Three Fiber v9, which is the stable major compatible with React 19. Do not adopt the v10 alpha as the default.

### File ownership

| File | Responsibility |
|:--|:--|
| Three/SceneLoader.tsx | Client-only loading boundary; keep WebGL out of server rendering |
| Three/SceneCanvas.tsx | Canvas creation, renderer configuration and resize lifecycle |
| Three/MonochromeScene.tsx | Scene composition |
| Three/OrbitalGeometry.tsx | Reusable meshes and geometry |
| Three/ShaderMaterials.ts | Typed ShaderMaterial definitions and shader source strings |
| Three/SceneConfig.ts | Scene constants and bounded quality settings |
| Three/DisposeScene.ts | Resource cleanup for geometries, materials, textures and renderers |
| Three/WebGLFallback.tsx | Static SVG/React fallback if WebGL is unavailable |

Load the scene only on the client. Keep it decorative: no navigation, settings or important information may depend on WebGL. Respect reduced-motion preferences, support low-power devices and dispose of GPU resources when the component unmounts.

Do not add ShaderGradient as a dependency automatically. Use its repository as a shader-design reference first; add the package only if a specific effect cannot be implemented cleanly with the existing Three.js layer.

---

## 7. Routing and static export

The existing frontend uses Next.js static export:

- output: export
- trailingSlash: true
- Rust serves the exported files from the same origin.

The required server dashboard URL is:

~~~text
/{discordUserId}/{guildId}/
~~~

The selected view can be represented by a safe internal path:

~~~text
/{discordUserId}/{guildId}/
/{discordUserId}/{guildId}/commands
/{discordUserId}/{guildId}/roles
/{discordUserId}/{guildId}/channels
/{discordUserId}/{guildId}/settings
~~~

Do not create Next.js dynamic route folders such as app/[userId]/[guildId]/ while output: export remains enabled. Unknown user and guild IDs are only known at request time; static export cannot produce one Next page for every possible pair.

Instead:

1. Rust recognizes the dashboard URL shape and validates the identifiers.
2. Rust checks the session and serves the static dashboard shell.
3. The TypeScript route resolver parses the browser pathname after hydration.
4. The frontend requests the selected guild data from Rust.
5. Every protected API request independently checks session identity, guild access, permissions and bot presence.

The pathname is not an authorization token. Changing either ID must never grant access.

### Rust UI routing

The Rust UI layer should distinguish:
- / and /login — known static pages.
- /custom-roles/ — the new TSX picker page.
- /{userId}/{guildId}/... — a validated dashboard-shell path.
- /_next/... and public assets — static build assets.
- /api/... — JSON/API routes only.
- unknown UI paths — the custom 404 response.
- unknown API paths — structured JSON 404 responses.

The OAuth callback remains /oauth/callback in Rust. Do not create a Next.js OAuth route handler or a second API backend.

### .nojekyll

A .nojekyll marker is not required for this deployment. The frontend is exported and served by the Rust service, not published as a standalone GitHub Pages site. Add frontend/public/.nojekyll only if a future deployment explicitly uses GitHub Pages for the static files; it does not replace the Rust API or OAuth service.

---

## 8. Authentication, consent and guild access

### Discord sign-in

The current login flow is handled by Rust:
- GET /oauth/start
- GET /oauth/callback
- GET /api/bootstrap
- POST /api/logout

The normal login uses only the required Discord scopes. Request command-permission authorization separately when a server manager opens the command access editor and needs native command permission synchronization.

### Required policy acceptance

After login, the user must complete the required acceptance flow for the current versions of:
- Terms of Service
- Privacy Policy
- Community Guidelines

Use the existing policy documents and versioned consent storage. Do not create a second consent system or treat privacy-policy acknowledgement as the legal basis for every form of personal-data processing.

### Guild picker

Show every guild returned by Discord where the authenticated user has Manage Server or Administrator permission:
- Bot present: show a green status mark and allow the dashboard to open.
- Bot absent: show a muted/disabled card with an invitation action.
- Permission removed: deny access on the next protected request.
- Bot removed: disable the guild configuration and explain the reason.

The bot must be checked against current guild membership; do not trust an old browser response.

---

## 9. Command configuration and access policies

Each configurable command needs two independent policy editors.

### Who can use the command?

- Everyone
- Only selected roles
- Everyone except selected roles

### Where can it run?

- All channels
- Only selected channels
- All channels except selected channels

The preview must show the effective rule in plain language. An allow-list denies unlisted subjects; an exclusion list allows unlisted subjects; explicit deny takes precedence. Empty allow-lists must never accidentally mean everyone.

The dashboard should synchronize Discord-native application-command visibility where the API supports the configured rule. The bot must also evaluate its own authoritative policy at runtime. UI hiding alone is not security enforcement.

Before a policy is saved:
1. Confirm the actor still manages the guild.
2. Validate each role and channel belongs to that guild.
3. Validate the command is configurable and not protected.
4. Validate Discord permission limits.
5. Persist the desired policy with a revision.
6. Synchronize native Discord command permissions where supported.
7. Record success or failure; never show a successful state when synchronization failed.

---

## 10. Save Changes and Reset

Every editable section keeps a server-confirmed snapshot and a local draft.

| State | Interface behavior |
|:--|:--|
| Clean | No action bar; buttons disabled or hidden |
| Dirty | Show the action bar |
| Saving | Green Save Changes button enters loading state; duplicate submission prevented |
| Saved | Show confirmation and update the confirmed snapshot |
| Failed | Keep the draft and show a retryable error |
| Conflict | Keep the draft and explain that a newer revision exists |

The Discord-inspired action bar uses:
- **Reset:** grey secondary action. Restore only the current section's last server-confirmed snapshot.
- **Save Changes:** green primary action. Validate and persist only the current section.
- Keyboard focus, hover, pressed, disabled and loading states.
- An unsaved-changes warning before navigation.
- Idempotency or revision checks to prevent duplicate and stale writes.

Reset must never silently write to the server. A failed save must never discard the draft.

---

## 11. Design system and animated icons

The visual language combines a disciplined monochrome editorial grid with restrained WebGL geometry:
- Near-black and graphite surfaces.
- Off-white text and subdued metadata.
- Fine borders and consistent spacing.
- Strong typography and minimal decoration.
- A single geometric visual focal point rather than gradients everywhere.
- Responsive layout, keyboard access and reduced-motion behavior.

### Animated icons

All interface icons must use the shared Components/Icons registry. Do not scatter one-off icon SVGs throughout feature components.

Use locally implemented SVG/React icon components inspired by the interaction patterns in pqoqubbw/icons. Animations should represent real UI states: hover, pressed, expanded, loading, success or error. Keep them brief, consistent and optional under reduced motion. The icon must remain clear when animation is disabled.

### Save bar states

The Reset control stays grey. Save Changes stays green. Color must be accompanied by accessible labels and state text; color alone cannot communicate success, failure or disabled state.

---

## 12. Error, loading and not-found states

The dashboard needs both Next.js route-level states and reusable feature-level states.

| File | Purpose |
|:--|:--|
| app/loading.tsx | Root route loading state |
| app/not-found.tsx | Custom static 404 page |
| app/error.tsx | Recoverable route error boundary |
| app/global-error.tsx | Root-level fallback if the app shell fails |
| Components/Feedback/NotFoundState.tsx | Unknown page, guild or resource state |
| Components/Feedback/ForbiddenState.tsx | Signed-in user lacks the required guild permission |
| Components/Feedback/ErrorState.tsx | Recoverable operation or rendering failure |
| Components/Feedback/OfflineState.tsx | Rust API or network unavailable |
| Components/Feedback/RateLimitState.tsx | HTTP 429 with retry timing |
| Components/Feedback/ServiceUnavailableState.tsx | Bot bridge or storage unavailable |

The Rust service must return the correct status code. For browser routes it should serve the generated 404 document where appropriate; for APIs it should return a consistent JSON error shape. Never turn an authorization failure into a successful empty response.

The user-facing state should explain what happened, offer a safe next action, and avoid leaking tokens, SQL, stack traces or private server data.

---

## 13. Rate limiting and load balancing

Rate limiting is enforced by Rust, not only by frontend button disabling.

### Required dimensions

- Client IP, using forwarded headers only from explicitly trusted proxies.
- Authenticated Discord account.
- Guild ID for guild-scoped mutations.
- Endpoint and operation type.
- Burst and sustained request rates.
- Request size, upload size and expensive-operation concurrency.

Return HTTP 429 with a meaningful Retry-After value. Do not ban accounts merely because they hit a temporary threshold. Keep separate policies for OAuth, reads, writes, search, uploads and resource-intensive operations.

### Storage and deployment boundary

The current dashboard store uses SQLite WAL for session, OAuth-state and coordination data. Same-host Rust workers can coordinate through the same local database file and atomic transactions.

Do not place a SQLite WAL database on NFS or treat it as a multi-host distributed database. Multi-host scaling needs an explicit shared atomic rate-limit store decision. Do not silently introduce Redis or another PostgreSQL service.

The Discord gateway remains a single bot runtime. Load balancing applies to the Rust dashboard service; it does not mean running multiple competing gateway clients with the same bot token.

### Existing and planned implementation

OAuth-start throttling already exists in the Rust authentication/state path. The planned rate_limit.rs module will centralize endpoint-specific policies and reusable middleware without duplicating existing checks. Keep SQLite transaction handling and busy-timeout behavior consistent with store.rs.

---

## 14. Security and What-if review

Use the question **“What if the user does something unexpected?”** for every interactive feature.

| What if… | Required behavior |
|:--|:--|
| User changes the user ID or guild ID in the URL | Rust checks the session and current guild permission; deny unauthorized access |
| A user clicks Save twice | One logical update; no duplicate mutation |
| Reset is clicked after editing | Restore only the last confirmed local snapshot |
| Discord permission disappears during editing | Reject the next protected write |
| A role or channel was deleted | Mark the rule invalid; never broaden access |
| The bot leaves a guild | Disable its configuration surface |
| Session expires while editing | Re-authenticate and retain recoverable local draft where safe |
| OAuth callback is replayed | Reject consumed/expired state |
| A user pastes markup or SVG | Treat input as data; validate and sanitize; never execute it |
| A file is oversized or malformed | Reject before expensive decoding |
| Requests are repeated rapidly | Rate limit at the Rust boundary |
| Backend storage is unavailable | Fail closed for protected writes |
| Discord permission sync fails | Show sync failure; do not claim the policy is applied |
| WebGL is unavailable | Render the static fallback |
| An animated icon fails | Render a normal static icon |
| Reduced motion is enabled | Disable nonessential motion |
| Unknown route is opened | Show the custom not-found state |
| API route is unknown | Return structured JSON 404 |

The final implementation should include tests for the important cases above. Frontend validation improves usability but never replaces Rust authorization, bot-side command checks or server-side file validation.

---

## 15. Asset rules

All dashboard-owned assets belong under frontend/public:
- Lemegeton logo and wordmarks.
- Favicon.
- Static SVG assets.
- Locally hosted textures or models, only when used.

Do not load Google Fonts, remote icon libraries, external CSS, analytics pixels or unnecessary CDN assets. Prefer the system font stack. If a locally bundled font is genuinely needed, verify its licence and place it under frontend/public/fonts.

The animated icon library is authored as TSX components; the public icons directory is for static SVG assets only.

Before moving the current root assets/icons/lemegeton.svg, search all bot, docs and build references. Update all consumers before deleting or relocating the original file. Do not leave two competing logo copies.

---

## 16. Dependencies and source formats

### Current frontend dependencies

The existing frontend package currently contains Next.js, React, React DOM and TypeScript. The Three.js and CSS-in-JS dependencies below are planned additions, not installed dependencies.

### Planned additions

| Package | Why |
|:--|:--|
| styled-components | Component and global styling authored in TSX |
| three | Three.js core |
| @types/three | Three.js type definitions |
| @react-three/fiber v9 | React renderer for Three.js, paired with React 19 |

Add a test library only when the focused component tests are introduced. Avoid installing a large UI kit, multiple animation libraries or state libraries for features that can be handled with the existing React stack.

### Authored source format policy

| Format | Allowed use |
|:--|:--|
| .tsx | React pages, visual components, styled components and icon components |
| .ts | API clients, types, validation, scene utilities, shader definitions and configuration |
| .svg | Static brand, icon and fallback vector assets |
| .json | Package, TypeScript and tool configuration |
| .rs | Rust backend source |
| .toml | Rust package configuration |
| .html | No authored source files |
| .css | No authored source files in the final target |
| .js / .mjs | No manually authored frontend source files in the final target |

Next.js still generates browser HTML, JavaScript bundles and style output during its build. These generated files live in the build directory and are not manually authored source files.

---

## 17. Build, run and verification

Run commands from the repository root.

### Frontend

~~~bash
npm install --prefix web/frontend
npm run typecheck --prefix web/frontend
npm run build --prefix web/frontend
~~~

The frontend uses Next.js static export. Build output is generated under the frontend output directory and served by Rust. Do not rely on next start as a second production web server.

### Rust backend

~~~bash
cargo fmt --manifest-path web/backend/Cargo.toml -- --check
cargo test --manifest-path web/backend/Cargo.toml
cargo build --manifest-path web/backend/Cargo.toml --release
~~~

Run the Rust dashboard service with the repository's configured environment. Keep it bound to loopback behind the configured reverse proxy unless an explicit public-bind configuration is intentionally enabled.

### Verification checklist

- TypeScript typecheck and production static export.
- Rust formatting, unit tests and release build.
- OAuth state validation, callback replay rejection, session expiry and logout.
- Legal-version acceptance and re-acceptance after policy updates.
- Direct user/guild URL navigation and refresh through Rust routing.
- Cross-account and cross-guild access denial.
- Guild permission loss and bot removal.
- Command role/channel include and exclude rules.
- Discord-native command permission synchronization and failure recovery.
- Save, reset, double-submit and stale-revision conflicts.
- Custom Roles picker parity, token-fragment handling, upload validation and crop behavior.
- 404, forbidden, offline, rate-limit and service-unavailable states.
- WebGL unavailable, context loss and reduced-motion behavior.
- Rate limits across every same-host Rust worker.
- CSP, same-origin asset loading and absence of remote font requests.
- Mobile layouts, keyboard navigation and focus visibility.

A successful local build does not prove live Discord OAuth, provider credentials, bridge connectivity, PostgreSQL availability or production proxy configuration. Verify those against the actual deployment environment before release.

---

## 18. Design and implementation references

These references inform file organization and interaction design. They are references, not dependencies to copy wholesale.

| Source | What Lemegeton adopts |
|:--|:--|
| [shadcn/ui](https://github.com/shadcn-ui/ui) | Clear App Router, component and hook boundaries; reusable source components |
| [Next.js dashboard starter](https://github.com/Kiranism/next-shadcn-dashboard-starter) | Feature-oriented screens, route loading/error states, hooks and shared UI organization |
| [Next.js CSS-in-JS guide](https://nextjs.org/docs/app/guides/css-in-js) | Styled Components registry and server style collection for the App Router |
| [React Three Fiber](https://github.com/pmndrs/react-three-fiber) | Declarative Three.js scenes integrated with React |
| [ReactVibe](https://reactvibe.com) | Interaction and transition inspiration |
| [Bencho](https://bencho.dev) | Tactile, directly manipulable component patterns |
| [pqoqubbw/icons](https://github.com/pqoqubbw/icons) | Animated SVG icon inspiration |
| [Dqnamo Kitchen](https://www.dqnamo.com/kitchen) | Physical-feeling controls and feedback states |
| [ShaderGradient](https://github.com/ruucm/shadergradient) | Shader and WebGL visual inspiration |

The implementation should adopt the useful patterns while preserving Lemegeton's existing architecture. Do not import unrelated systems, frameworks or dependencies merely because a reference project uses them.

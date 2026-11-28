# Web performance and route checklist

Scope: **Lemegeton v3**, `web/`, branch `lemegeton-v3`.

Statuses are based on inspected source, not assumptions:

- **FINISHED** — verified in the current implementation or completed by this change.
- **INCOMPLETE** — part of the mechanism exists, but coverage or verification is missing.
- **NOT FINISHED** — implementation was not found or requires additional architecture/infrastructure.

## Performance checklist

| Requirement | Status | Evidence and remaining work |
|---|---|---|
| Prevent duplicate API requests | **FINISHED** | `web/frontend/src/Lib/api.ts` coalesces identical in-flight GETs by path, CSRF token and request headers. Mutations are never coalesced. The public status endpoint also has a 10-second single-flight cache. |
| Debounce search and autocomplete inputs, if needed | **FINISHED** | Command search filters the already-loaded list locally. Atlas search submits explicitly from a form; it does not call the API for each keystroke. A debounce timer is not needed for those flows. |
| Paginate API results | **FINISHED** | Persisted guild audit history uses ID-based keyset pagination end-to-end: the bot bridge returns a cursor and enforces a 1–100 limit; the Rust API validates it after guild authorization; the frontend appends 25-record pages and rejects stale guild/request responses. A `(guild_id, id DESC)` index supports the query. Rust tests and the audit-pagination Playwright E2E test passed in CI. Other list endpoints are already bounded or fixed-size. |
| Move slow tasks to a background job queue | **INCOMPLETE** | The bot already has a persistent media-asset cleanup retry queue. There is no general dashboard/background-job contract for longer-running work; identify and measure those tasks before extending it. |
| Fix N+1 queries | **INCOMPLETE** | Rust dashboard handlers generally authorize and forward one operation to the private bot bridge. A full query/caller audit and production query profiling across bot services is still required before claiming N+1 issues are resolved. |
| Enable Brotli or Gzip compression | **FINISHED** | The supported VPS Nginx reverse-proxy configuration enables Gzip for HTML, CSS, JavaScript, JSON, XML and SVG responses. Deployments that bypass this Nginx configuration must enable equivalent compression at their ingress or CDN. |
| Cache frequently accessed data, including bot data | **INCOMPLETE** | This change adds a 10-second in-process cache/single-flight for the public aggregate status response. The authenticated system endpoint also keeps its last known health value. There is no comprehensive bot/provider cache policy or shared cross-instance cache; Redis is not currently part of this architecture. |
| Remove unused dependencies | **INCOMPLETE** | Root and frontend dependencies install successfully in CI, and the dashboard type-check, tests and production export pass. A full import-to-manifest usage graph audit has not been run, so no dependency was removed speculatively. |
| Set timeouts for external API calls | **FINISHED** | The shared Rust Reqwest client has a 12-second total timeout and 4-second connect timeout. Browser dashboard API calls and public status fetches now abort after 15 seconds, including response-body parsing. |
| Update the UI before the server responds | **INCOMPLETE** | Form drafts and command configuration state update locally before Save. Not every server mutation has a tested optimistic update plus rollback path; audit each action separately. |
| Lazy-load images below the viewport | **FINISHED** | The frontend image audit found no content images below the initial viewport: the Overview wordmark and status/login brand marks are first-view assets; custom-role crop/preview images are populated only after user interaction. Those first-view assets remain eager rather than being delayed. |
| Run independent requests in parallel | **FINISHED** | Dashboard overview refresh uses `Promise.allSettled` for Overview, Commands, System and Audit. Public status now runs the independent dashboard-store and bot-bridge health checks concurrently with `tokio::join!`. |
| Add database indexes for common queries, including the bot | **INCOMPLETE** | The shared schema already indexes issue history, Steam lookups, media cleanup/assets, archive lookups and dashboard session/OAuth/rate-event/consent queries. This change adds `(guild_id, id DESC)` for audit cursor pages. The complete bot query workload still needs query-plan and production-metric validation. |
| Trace slow backend requests with OpenTelemetry | **NOT FINISHED** | Structured tracing/logging exists, but no OpenTelemetry SDK/exporter or request-level trace pipeline is configured. |
| Render pages on the server or at build time | **FINISHED** | Every page shell is generated at build time by Next.js static export. Rust authenticates dashboard requests before serving the static shell; user/guild data hydrates through authenticated APIs and is not embedded in the shared export. |
| Load third-party scripts after the page | **FINISHED** | The dashboard layout does not load third-party JavaScript. The former standalone Garden page, which referenced remote Google Fonts, has been removed; its CSP exception has also been removed. |
| Virtualize long lists | **NOT FINISHED** | No list virtualization is configured. Measure Atlas, activity, command and log views, then virtualize only the lists whose rendered row counts justify it. |
| Select only the columns needed | **INCOMPLETE** | Dashboard storage reads use explicit column lists for legacy migration and the health query selects a single value. A complete audit of bot-side SQL, including wildcard projections, remains outstanding. |
| Use database connection pooling | **FINISHED** | The shared libSQL storage adapter uses a bounded per-process pool of eight connections. Queries and batches reuse leases; transactions hold their connection until commit or rollback. Both targeted storage tests (pool reuse and transaction persistence), Clippy and the optimized backend build passed in CI. The broader dashboard Rust test binary still has two separate session-cookie fixture failures; pool size has not been load-tuned. |
| Prevent unnecessary rerenders | **INCOMPLETE** | The dashboard memoizes some derived command/Atlas state, but the large App component still owns many state values and rerenders its subtree. A React Profiler pass is required before adding more memoization or splitting state. |
| Enable browser caching for static files | **FINISHED** | Hashed Next assets are served with `public, max-age=31536000, immutable`; public brand/font assets receive a one-hour cache policy. |
| Load-balance traffic across multiple app instances | **INCOMPLETE** | The VPS Nginx example already defines three Rust dashboard upstreams, and a systemd template starts instances on ports 8080–8082. Production deployment, passive-failure behavior and load testing against the shared local libSQL store remain unverified. The Discord bot stays a single process. |
| Self-host fonts and limit font weights | **INCOMPLETE** | Dashboard fonts are self-hosted under `frontend/public/fonts`. Geist/Geist Mono variable font files expose weight ranges; further subsetting/weight reduction needs bundle and typography review. |
| Track real-user speed with performance monitoring | **NOT FINISHED** | No real-user monitoring collector or Web Vitals reporting endpoint is configured. Add only after defining consent, retention, privacy disclosure and a first-party collection boundary. |
| Test on slow phones and networks | **INCOMPLETE** | Status E2E covers a held API response, first-check recovery, stale-snapshot behavior, and landscape overflow/compact spacing. A 390×844 Chromium run also applies 4× CPU throttling and a simulated 3G profile (450 ms latency, 400 kbps down / 100 kbps up) while asserting the loading skeleton; all 21 browser E2E tests passed in CI. Physical-device, real-network and battery/memory-profile testing remain outstanding. |
| Add landscape responsiveness | **INCOMPLETE** | Existing width-based responsive rules remain in place, and the public status page now compacts header, hero, component and footer spacing at landscape heights up to 520px. Playwright checks for horizontal overflow and compact spacing at 844×390 both passed in CI. The same short-height landscape audit has not yet been applied across every authenticated dashboard view or verified on physical phones/tablets. |

## URL and dashboard behavior

| Requirement | Status | Verified behavior |
|---|---|---|
| All static pages use clean extensionless public URLs | **FINISHED** | Next exports non-root page artifacts as `route.html`; Rust serves those pages at `/login`, `/custom-roles`, `/how-it-works`, `/status` and the legal routes. Trailing-slash and legacy `.html`/`index.html` paths redirect to canonical URLs. The authenticated `/user-id/guild-id/` route remains unchanged. |
| Public status URL is `/status`, not `/status/index.html` | **FINISHED** | The public route is exactly `/status`; `/status/`, `/status.html` and `/status/index.html` redirect to it. The internal static artifact is `web/frontend/out/status.html`, not the public URL. The page declares `/status` canonical. |
| Type Garden is part of Lemegeton's Overview, not a separate page | **FINISHED** | The local Lemegeton typed botanical wordmark animation remains in Overview. The separate Type Garden link/page and remote-font page asset are removed; legacy `/garden` links redirect to the dashboard. |
| Thank-you is a popup with Continue, not a standalone page | **FINISHED** | `/thank-you` redirects to the dashboard with a `#thank-you` fragment. The existing receipt design opens as an accessible dialog, and Continue dismisses it without a separate thank-you page. |
| Dashboard page swaps keep the same user/guild URL | **FINISHED** | The `navigate` handler changes React page state only. The path remains `/user-id/guild-id/` while switching dashboard sections; selecting another guild changes only the guild segment. |

## PDF-source checklist and project mapping

The supplied PDFs were rendered and visually inspected. Each is a two-page browser capture of the BreakingBreach guide viewer, not a full copy of the advertised guide. The visible viewer page counts and cover details below are source facts; missing checklist entries are not inferred.

### Checklist mapped to the visible source material

| Visible guide material | Project check | Status | Evidence / limitation |
|---|---|---|---|
| App-Performance Toolkit: a clipped preview shows **Skeleton Screens** as a checklist item. | Keep useful loading skeletons for data views. | **FINISHED** | Overview has loading skeleton cards and public status has skeleton rows while its first check is pending. The delayed-response status E2E test passed in CI. |
| Build Apps That Don’t Break: the intro names concurrent requests, slow providers, edited URL numbers and release failures as examples, and advertises 12 reliability/security topics. | Coalesce duplicate GETs; time-bound provider requests; validate user/guild identifiers and authorize every guild request; verify release changes. | **INCOMPLETE** | GET coalescing, timeouts and backend ID/permission checks exist. Dashboard type-check, unit/component tests, static build, browser E2E, targeted storage tests, Clippy and the optimized backend build passed in CI. The broader dashboard Rust test suite reports two session-cookie fixture failures, and the 12 full topic pages were not supplied. |
| GitHub Actions Credential Theft: the cover depicts a workflow change reaching a build runner with access to secrets, tokens and a cloud role. | Limit PR workflow permissions; do not expose live secrets to untrusted PR code; pin actions; disable persisted checkout credentials. | **FINISHED** | All 17 current workflow files were inspected: no `pull_request_target` or `workflow_run` trigger was found; PR-triggered workflows use read-only repository permissions; third-party actions are pinned to full commit SHAs; checkout uses `persist-credentials: false`; live-secret acceptance workflows are manually dispatched. This covers only the risk pattern visible on page 1, not the missing incident-response pages. |
| Pre-launch AI Security Checklist: its cover says it contains practical checks for AI features, but no control is visible. | Extract and apply AI-specific security controls. | **INCOMPLETE** | The attachment contains only the cover/preview. No AI-specific controls can be attributed to this source without its remaining pages. |
| App Launch Checklist: viewer shows **Page 1 of 112**, but its content area is blank. | Extract and apply the launch checklist. | **INCOMPLETE** | No checklist item is legible in the supplied capture. The 112-page source is required. |

### Uploaded guide inventory

| Uploaded file | Viewer title and advertised length | What the actual capture exposes | Source checklist status |
|---|---|---|---|
| `BreakingBreach · Guides(3).pdf` | **App-Performance Toolkit** — Page 1 of 41; cover advertises **31 fixes** and **31 copy-paste prompts**. | Cover plus clipped checklist preview containing **Skeleton Screens**. The remaining fixes/prompts are absent. | **INCOMPLETE** — full 41-page guide needed. |
| `BreakingBreach · Guides(4).pdf` | **App Launch Checklist** — Page 1 of 112. | Title and page indicator only; captured content area is blank. | **INCOMPLETE** — full 112-page guide needed. |
| `BreakingBreach · Guides.pdf` | **Build Apps That Don’t Break** — Page 1 of 34; cover advertises **12 topics**. | Introductory reliability/security framing and examples, but not the 12 topic write-ups. | **INCOMPLETE** — full 34-page guide needed. |
| `BreakingBreach · Guides(1).pdf` | **Pre-launch AI Security Checklist** — Page 1 of 19. | Cover says “Practical checks for AI features in your app”; individual controls are not visible. | **INCOMPLETE** — full 19-page guide needed. |
| `BreakingBreach · Guides(2).pdf` | **GitHub Actions Credential Theft** — Page 1 of 4. | High-level workflow/credential exposure diagram and short incident summary; full response steps are absent. | **INCOMPLETE** — full 4-page guide needed. |

The five captures contain **10 physical PDF pages**, while their five named guides advertise **210 pages** in total. The guide-library page visible in the captures lists **six guides / 234 pages**, including an additional **Protect Your App from Data Loss** guide of 24 pages that was not uploaded.

- [x] Open and render all five uploaded PDFs.
- [x] Record visible guide titles, viewer page counts and legible cover/intro details.
- [x] Map visible actionable themes to repository checks.
- [ ] Extract the remaining App-Performance Toolkit fixes and prompts.
- [ ] Extract the 112 App Launch checklist items.
- [ ] Extract the 12 Build Apps reliability/security topics.
- [ ] Extract the Pre-launch AI Security controls.
- [ ] Extract the remaining GitHub Actions incident-response guidance.
- [ ] Obtain the missing 24-page Protect Your App from Data Loss guide if the full library is in scope.

The PDF-source checklist cannot honestly be marked complete from these captures. The full guide PDFs are required to complete the source-specific rows; no missing items have been invented.

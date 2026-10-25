# Dashboard security review

**Scope:** Rust/Axum public control plane, React/TypeScript dashboard, Discord OAuth/session handling, per-guild authorization, the Rust-to-Python bridge, custom-role picker, its image-fetch pipeline, and deployment packaging.

**Status:** This is a source-level hardening pass with focused regression tests. It is not a guarantee of invulnerability or a substitute for a production penetration test. External OAuth, real HTTPS termination, VPS firewall state, live Discord permissions, and host-level compromise are not verifiable from repository source alone.

## Findings fixed

| Severity | Finding | Mitigation |
| --- | --- | --- |
| High | Dashboard owner IDs could bypass per-guild Manage Server/Admin permission checks. | Per-guild authorization now always requires current Discord Manage Server or Administrator permission plus bot membership. Owner IDs remain for bot-wide owner-only views. |
| High | The Rust service defaulted to binding all interfaces, potentially exposing its plaintext listener. | Rust defaults to loopback and refuses public binding without `DASHBOARD_ALLOW_PUBLIC_BIND=true`. Railway/container configuration explicitly opts into ingress; VPS deployment uses Nginx/TLS in front of loopback. |
| High | Public URL, OAuth callback, and secure-cookie settings were not validated together. | Startup fails closed for non-HTTPS public origins outside localhost, callback-origin/path mismatch, or HTTPS without secure cookies. |
| Medium | Repeated OAuth starts could fill the in-memory pending state map. | Global OAuth-start rate limit, bounded state table, and Nginx per-client rate limits. |
| Medium | Concurrent requests could race a rotating Discord OAuth refresh token. | Refresh calls are serialized, the session is re-read under the lock, and fresh tokens are reused by concurrent requests. |
| Medium | Logout invalidated only the local session. | Local session removal happens first; a bounded Discord token-revocation attempt follows. Local logout works if Discord is temporarily unreachable. |
| Medium | The bot bridge accepted short secrets and internal listeners relied only on configuration. | Shared bridge secret must be at least 32 UTF-8 bytes; Python bridge/picker refuse non-loopback bind addresses; Rust refuses a weak bridge secret. |
| Medium | The Rust-to-picker proxy forwarded almost all caller-supplied request headers. | A tight allow-list passes only the bearer token, content negotiation, origin, and expected proxy client-address headers. Cookie, host, hop-by-hop, and forwarded-host values are dropped. |
| Medium | Guild command synchronization could overlap a toggle or reset. | `/sync` takes the same per-guild lock used by toggles/resets. |
| Medium | Dependency trees were not automatically audited. | CI adds `npm audit` and `cargo audit`, plus type checking, asset build checks, and regression tests. The workflow can be dispatched manually and runs weekly. |
| Medium | Picker mutation routes accepted a missing `Origin` and request `Host` as fallback trusted origin. | Actual mutation routes require a present, exact match to the configured public origin. Unsupported method/path pairs preserve normal 404/405 responses. |
| Medium | Picker's global body limit was below allowed icon-image uploads. | The limit is derived from configured source-image size plus multipart overhead; the upload handler retains its own byte cap. |
| Low | Internal URL parsing accepted invalid digit strings as ports. | Loopback service ports must parse as a nonzero `u16`. |
| Low | Several defense-in-depth headers were missing. | Added COOP/CORP, `X-Permitted-Cross-Domain-Policies`, `object-src 'none'`, and conditional HSTS when secure cookies are enabled. |

## Attack-surface checks

- **Authorization bypass:** per-guild access intersects the authenticated user's current Discord guilds, live Manage Server/Admin permissions, and guilds where the bot is present. Owner-only features do not grant blanket guild access.
- **CSRF/session abuse:** cookies are HttpOnly/SameSite=Lax; OAuth state is single-use and browser-cookie-bound; writes require matching Origin and constant-time CSRF comparison; the custom-role picker uses a short-lived bearer link rather than an ambient cookie.
- **Header/host confusion:** proxy headers are filtered before internal forwarding; bridge/picker bind hosts are validated as literal loopback addresses; public origin and OAuth callback are validated.
- **SSRF:** the existing image fetcher permits HTTPS/port 443 only, rejects private/non-global DNS answers, pins checked addresses to prevent DNS rebinding, disables redirects and environment proxies, and limits streamed responses. Image decoding separately checks format, pixel dimensions, and animation.
- **Resource exhaustion:** OAuth state has a cap and rate limit; picker per-address/member rate-limit maps are hard-bounded under rotating-key floods; API writes and picker tokens are rate-limited; image transfers are concurrency-limited and byte-limited; uploads use an explicit allow-listed route set.
- **XSS and browser policy:** self-only script/style CSP, `textContent`-based error messages, no `dangerouslySetInnerHTML`, and picker assets served from an explicit allow-list without using request path components as filesystem paths.
- **Deployment escape:** Docker runs as a non-root UID, drops Linux capabilities, uses a read-only root filesystem, and publishes the public web listener only on host loopback. VPS examples isolate bot and dashboard service users and put Nginx TLS in front of Rust.

## Dependency verification

Tokio's minimum version is pinned to `1.54.1`, the patched release for [RUSTSEC-2026-0384](https://rustsec.org/advisories/RUSTSEC-2026-0384.html), reported in October 2026. The affected bug is a race in `tokio::time::Interval` on v1.54.0; the advisory identifies `1.54.1` as patched. [Source: RustSec](https://rustsec.org/advisories/RUSTSEC-2026-0384.html). CI runs `cargo audit` and `npm audit` against the dependency resolution for that build.

## Residual risks and required operational checks

1. Rust sessions and OAuth state are in process memory. Restarting Rust invalidates active sessions. Multiple replicas need shared sessions and distributed rate limits.
2. Python remains responsible for the live discord.py gateway and command tree. The public dashboard API and authorization boundary remain Rust; the Python bridge stays narrow and private.
3. CI cannot verify a deployed TLS proxy, host firewall, real OAuth registration, provider uptime, secrets access control, or the live Discord permission matrix.
4. The bot process can perform actions allowed to its Discord token. Keep the token private, use minimum Discord permissions, rotate exposed credentials, and restrict writes to source and environment files.
5. Builds without committed lockfiles are not fully reproducible. Review dependency lockfile policy for release deployment.
6. After deploying, test an authorized and unauthorized guild, OAuth cancellation/expiry, logout/revocation failure, rejected bridge auth, command-sync rollback, and an image upload at the configured size boundary.

**Security goal:** reduce reachable interfaces, fail closed on malformed deployment/auth configuration, keep identity and per-guild permission checks server-side, and exercise regressions in CI. No source tree can honestly promise that attackers have no possible path; deployment and credential risks still matter.

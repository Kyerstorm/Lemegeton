# Dashboard security review

**Scope:** Rust/Axum public control plane, React/TypeScript dashboard, Discord OAuth/session handling, per-guild authorization, the Rust-to-TypeScript bridge, custom-role picker, its image-fetch pipeline, and deployment packaging.

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
| Medium | The bot bridge accepted short secrets and internal listeners relied only on configuration. | Shared bridge secret must be at least 32 UTF-8 bytes; TypeScript bridge/picker refuse non-loopback bind addresses; Rust refuses a weak bridge secret. |
| Medium | The Rust-to-picker proxy forwarded almost all caller-supplied request headers. | A tight allow-list passes only the bearer token, content negotiation, origin, and expected proxy client-address headers. Cookie, host, hop-by-hop, and forwarded-host values are dropped. |
| Medium | Guild command synchronization could overlap a toggle or reset. | `/sync` takes the same per-guild lock used by toggles/resets. |

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

## Additional findings from PR #17 source review (2026-11-19)

**Review boundary:** this was a source-level review of the lemegeton-v3 branch, including the scraper, current callers, tests, dashboard authorization path, workflows and dependency manifests. No request was sent to a live target. No deployed website hostname or staging environment was supplied, so live configuration, TLS termination, firewall rules, OAuth registration and production behavior remain unverified.

The review used [ARTEX](https://github.com/BaaRai/ARTEX) as a defensive methodology reference: enforce an explicit scope at the execution boundary, re-check allow-listed targets instead of trusting upstream scope claims, require human approval for consequential automated actions, cap execution budgets and preserve evidence for each finding. ARTEX was not run against Lemegeton or any live host.

### MEDIUM — Scraper URL validation (remediated in source)

**Status:** Remediated on lemegeton-v3 (2026-11-19); focused scraper compilation and regression tests passed. Remote reachability was not established and no live target was tested.

**Affected code:** helpers/integration/web-scraper.ts, especially isPrivateIp(), validatePublicHttpUrl(), fetchResource() and the Playwright request route.

The IPv6 branch of isPrivateIp() rejects selected loopback, unique-local, link-local and multicast prefixes, but does not normalize IPv4-mapped IPv6 addresses before classification. The WHATWG URL parser canonicalizes these forms into compressed IPv6 notation; the current prefix checks then fail to recognize mapped loopback, private or link-local IPv4 destinations. I verified this behavior with Node's URL and net.isIP parsers locally; no connection was attempted.

The same validator checks the URL hostname but does not resolve and validate all A/AAAA records or pin the actual connection to an approved address. This leaves a DNS-rebinding gap if an attacker-controlled hostname can reach the generic fetch helpers. The HTTP transports, manual redirects and Playwright route checks all rely on the same hostname-level policy.

The existing webnovel discovery callers mostly use fixed provider endpoints and restrict parsed provider links to expected hosts. I did not establish an unauthenticated route that lets a user supply an arbitrary URL, so this is not reported as a proven remotely exploitable SSRF. It is a concrete validation defect in a reusable server-side request boundary and should be fixed before that boundary is used with broader or user-controlled inputs.

**Remediation applied:**
- Normalize IPv4-mapped IPv6 addresses to their IPv4 destination before applying the address policy; use a maintained IP parser/classifier that distinguishes globally routable addresses from private, loopback, link-local, shared, documentation and other special-use ranges.
- Resolve both A and AAAA records and reject a hostname if any candidate is outside the permitted public address policy.
- Pin the HTTP connection to the validated address while retaining the original hostname for Host, TLS SNI and certificate verification. Do not perform a second unchecked DNS lookup between validation and connection.
- Re-apply the same policy to redirects, retries, fallback transports and browser navigation/resource requests. Add network-level egress restrictions for Playwright.
- Add regression tests for IPv4-mapped IPv6, mixed public/private DNS answers, DNS changes between validation and connection, redirect chains and each supported transport.

The source now classifies IPv4-mapped IPv6 addresses and a conservative set of non-public/special-use IPv4 and IPv6 ranges, resolves both address families, fails closed if any DNS answer is non-public, and pins Node fetch/Undici and Axios connections to the validated answer set. Axios environment proxies are disabled for this path. Playwright is restricted to local Chromium with a pinned IPv4 resolver rule; cross-host requests and WebSockets are blocked, while remote browser endpoints and Firefox/WebKit are rejected because their DNS path cannot be pinned by this implementation. The injectable fetchImpl remains a test-only transport and must be left unset in production.

The focused tests/web-scraper.test.ts compile-and-run step passed on PR head 035c52f55fe520ad681434dfe7733b97d1499f2b, including the mapped-address, special-use IPv4/IPv6, mixed-DNS-answer and redirect regression cases. The full TypeScript project check remains blocked by pre-existing provider-union errors in src/commands/discover.ts; the same errors were present on the branch head before this security patch. The full bot test/build and Docker production-image steps therefore did not complete on this head.

This follows the defensive guidance in the [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html), which explicitly warns that domain allow-listing alone does not prevent DNS rebinding and recommends connecting only to validated addresses.

### MEDIUM — Bot runtime dependency audit coverage (resolved)

**Status:** Resolved in CI on lemegeton-v3 (2026-11-19). The TypeScript bot workflow now runs npm audit --audit-level=high against the root bot dependency tree after install; the latest run reported zero vulnerabilities.

The root bot dependency tree is now covered by the TypeScript bot workflow's high-severity npm audit gate. The first verified run on 2026-11-19 returned zero vulnerabilities; this is a point-in-time audit result, not a guarantee that future dependency releases will remain vulnerability-free.

**Required remediation:** add a root-package npm audit step with an agreed severity threshold, keep the frontend and Rust audits, and make the checks run on the lemegeton-v3 pull-request head. Review any reported advisory against actual usage and upgrade compatibility before changing dependencies.

### LOW — Dependency resolution is not pinned in the repository

**Status:** Open; reproducibility and supply-chain review gap.

The inspected lemegeton-v3 tree contains no root package-lock.json, web/frontend/package-lock.json or Cargo.lock. The npm manifests use semver ranges, and the workflows use npm install. Builds and advisory results can therefore resolve to different transitive versions over time, and a reviewed dependency graph cannot be reproduced exactly from the commit alone.

This issue remains open. The CI audit generates a temporary npm lockfile during the job but does not commit it, and no generated npm/Cargo lockfile has been added to the branch.

**Required remediation:** commit the npm lockfiles for the root bot and frontend plus the workspace Cargo.lock; use npm ci for the matching npm projects and locked Cargo commands in CI/release builds. Run [OSV-Scanner](https://google.github.io/osv-scanner/) against those lockfiles and retain the existing npm audit and cargo audit checks. OSV-Scanner's own documentation recommends resolved lockfiles for the exact dependency versions selected by an environment.

### Additional hardening coverage

The v3 CI now includes a CodeQL source-analysis workflow for TypeScript, Rust and GitHub Actions using security-extended and security-and-quality query suites. Add targeted custom Semgrep rules in a later pass for high-risk local patterns such as unscoped guild database operations, privileged Discord component handlers without action-time authorization, and unvalidated URL-fetch sinks; Semgrep is not yet configured in this repository. [CodeQL's supported-language documentation](https://docs.github.com/en/enterprise-cloud@latest/code-security/concepts/code-scanning/codeql/codeql-code-scanning) includes TypeScript, Rust and GitHub Actions; [Semgrep](https://github.com/semgrep/semgrep) supports custom static-analysis rules.

Use [Trivy filesystem scanning](https://trivy.dev/docs/latest/target/filesystem/) for repository/container vulnerability, secret and misconfiguration checks. Use [OWASP ZAP Baseline](https://www.zaproxy.org/docs/docker/baseline-scan/) as a passive check against an owner-controlled staging deployment; it does not perform active attacks and does not replace authorization tests. Do not run active security tests against a live system without explicit ownership and authorization.

The in-memory Rust dashboard sessions and OAuth state described in Residual risks remain an operational limitation: process restarts invalidate sessions, and multiple replicas require shared session storage and distributed rate limiting. This was already documented and is not a newly discovered source flaw in this review.

## Dependency verification

Tokio's minimum version is pinned to `1.54.1`, the patched release for [RUSTSEC-2026-0384](https://rustsec.org/advisories/RUSTSEC-2026-0384.html), reported in October 2026. The affected bug is a race in `tokio::time::Interval` on v1.54.0; the advisory identifies `1.54.1` as patched. [Source: RustSec](https://rustsec.org/advisories/RUSTSEC-2026-0384.html). CI now audits the root bot dependency tree, the dashboard frontend and the Rust backend. The committed lockfile gap remains open: the `lemegeton-v3` tree still has no root or frontend `package-lock.json` and no `Cargo.lock`.

## Verification snapshot (2026-11-19)

- Root bot dependency audit: passed; npm audit --audit-level=high reported zero vulnerabilities.
- Focused scraper compile and regression suite: passed on PR head 035c52f55fe520ad681434dfe7733b97d1499f2b.
- Dashboard frontend: type-check, production build and frontend npm audit passed in the same workflow.
- Rust backend: cargo test and cargo audit passed in the latest dashboard workflow.
- The previous bot type-check and Docker image blocker in src/commands/discover.ts was addressed by normalizing provider search results to SearchRecord[] before aggregation. The latest pipeline run will verify the correction.

## Residual risks and required operational checks

1. Rust sessions and OAuth state are in process memory. Restarting Rust invalidates active sessions. Multiple replicas need shared sessions and distributed rate limits.
2. The TypeScript Node.js process owns the live Discord.js gateway, command registry, private bridge, and Custom Role picker. Rust remains the public dashboard API and authorization boundary.
3. CI cannot verify a deployed TLS proxy, host firewall, real OAuth registration, provider uptime, secrets access control, or the live Discord permission matrix.
4. The bot process can perform actions allowed to its Discord token. Keep the token private, use minimum Discord permissions, rotate exposed credentials, and restrict writes to source and environment files.
5. Builds without committed lockfiles are not fully reproducible. Review dependency lockfile policy for release deployment.
6. After deploying, test an authorized and unauthorized guild, OAuth cancellation/expiry, logout/revocation failure, rejected bridge auth, command-sync rollback, and an image upload at the configured size boundary.

**Security goal:** reduce reachable interfaces, fail closed on malformed deployment/auth configuration, keep identity and per-guild permission checks server-side, and exercise regressions in CI. No source tree can honestly promise that attackers have no possible path; deployment and credential risks still matter.

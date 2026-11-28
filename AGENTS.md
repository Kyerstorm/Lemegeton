# AGENTS.md — Lemegeton Engineering Guide

This file describes the current v3 repository architecture and the engineering rules for changes. Verify the checked-out branch and actual callers before relying on any path or feature claim.

## 1. Project Context and Branch Discipline

Lemegeton is a multi-guild Discord bot for media discovery, information, recommendations, archives, and community features. The v3 implementation uses Node.js 22.9+, TypeScript, discord.js, one shared local libSQL database, and a private RocksDB object store. The optional dashboard uses a Next.js frontend and a Rust/Axum backend.

The `multi_guild` branch is the earlier Python implementation and is a source-reference branch when performing the v3 migration audit. Do not treat its Python files or docs as the current v3 runtime. The `lemegeton-v3` branch is the head of Draft PR #17. When working on that PR, make changes only on `lemegeton-v3`; do not modify or synchronize `multi_guild` unless the user explicitly requests it.

Respect the branch and PR explicitly selected by the user. Do not create another branch or PR as a routine step. Keep commits focused; when a task changes multiple independent files and the repository workflow expects commits, use one coherent commit per file rather than repeatedly committing the same file.

## 2. Current Architectural Landmarks

Confirm each path and its contents before editing; the architecture may evolve.

- `bot.ts`: Discord.js client setup, runtime lifecycle, event routing, background workers, and shutdown.
- `src/utility/database/libsql/`: shared libSQL schema, queries, SQL translation and Rust storage binding. `src/utility/database/rocksdb/` contains the private RocksDB wrapper and C++ addon; the root `database.ts` compatibility file is removed.
- `helpers/runtime/`: typed configuration, Discord runtime helpers, logging, diagnostics, issue references and retention policy.
- `helpers/dashboard/`: private dashboard bridge, guild permissions and dashboard configuration services.
- `helpers/integration/`: provider clients and provider-specific request/response handling (AniList, Steam, IGDB, Google Books, TMDB, Atlas, the web scraper, and the Botasaurus worker bridge).
- `workers/`: the isolated optional Botasaurus Python browser worker, its configuration/dependencies, and dedicated container image.
- `helpers/`: shared domain services, security, embeds, archive/community/custom-role/media helpers.
- `src/commands/`: the seven dashboard-configurable feature commands (`discover`, `archive`, `community`, `play`, `profile`, `custom-role`, and `music`) plus the protected server-setup command `settings`.
- `src/standalone/`: standalone top-level commands such as `help`, `privacy`, `feedback`, and restricted operations commands. Do not fold the documented standalone exceptions into feature commands.
- `src/utility/`: utility command handlers.
- `src/integrations/`: non-command runtime integrations such as message-based embeds; these are not slash-command modules.
- `src/registry.ts` and `src/deploy-commands.ts`: command inventory and registration.
- `tests/`: TypeScript/Node tests, including isolated local libSQL and RocksDB integration tests.
- `web/frontend/`: Next.js App Router frontend and React/TypeScript UI.
- `web/backend/`: Rust/Axum dashboard service and authorization boundary.
- `web/picker.html`, `web/picker.js`, `web/picker.css`, `web/theme.css`: browser assets served by the TypeScript Custom Roles picker. The JavaScript file is a browser asset, not a Python/runtime entry point.
- `.env.example`, `package.json`, `tsconfig.json`, `Cargo.toml`, `Dockerfile`, `docker-compose.yml`, `railway.toml`, and `scripts/start.sh`: configuration, builds, and deployment.
- `docs/`: current specifications, operation, security, and migration documentation.

The primary v3 bot runtime remains Node.js/TypeScript. One isolated optional Python worker is permitted under `workers/`: `botasaurus.py`, `config.py`, `requirements.txt`, and its dedicated Dockerfile. This worker is an external browser service, not a second Discord bot runtime. Do not reintroduce `bot.py`, unrelated Python modules, Python virtual-environment launchers, or old Python-only maintenance scripts. Preserve the `web/picker.js` browser asset unless its TypeScript server integration is deliberately replaced.

## 3. Required Engineering Workflow

For every meaningful task:

1. **Understand:** inspect the relevant modules, callers, schemas, config, tests, docs, and git diff before editing.
2. **Scope:** identify the smallest change that satisfies the request. State material assumptions and trade-offs; ask only when ambiguity prevents a reliable implementation.
3. **Plan:** identify the intended files and observable success criteria.
4. **Implement:** make surgical changes. Every changed line must directly support the task.
5. **Verify:** run the narrowest relevant checks, then broader checks where feasible; inspect the final diff.
6. **Report:** name changed files, actual verification results, and remaining limitations.

Do not claim that tests, deployment, live Discord checks, provider calls, or production database operations succeeded unless they were actually executed and the result was observed.

## 4. Scope Control and Repository Hygiene

- Prefer existing helpers, providers, schema patterns, and command implementations over duplicate code.
- Do not add unrequested features, speculative abstractions, dependencies, placeholders, or unrelated refactors.
- Preserve public command names/options, response behavior, configuration compatibility, and stored data unless explicitly asked to change them.
- Remove imports and variables made unused by your own edits; leave unrelated dead code alone.
- Do not commit generated output, local databases, logs, caches, credentials, IDE state, or temporary inspection scripts.
- Keep user-facing text and documentation concise. Do not describe planned functionality as operational.
- Inspect the final diff and ensure only requested files changed.

## 5. Multi-Guild Isolation — Critical

A cross-guild data leak is a serious regression. Every command, database operation, cache, event handler, scheduled worker, and dashboard action must preserve the intended scope.

- Obtain guild context from the Discord interaction or event and validate it before guild-specific work.
- Carry `guild_id` through the full call chain: command/component → service/helper → database operation.
- Scope guild-owned reads, writes, deletes, uniqueness constraints, counts, and scheduled work by guild. Parameterize SQL values.
- Distinguish guild-owned settings/history from deliberately global records and linked external identities. Do not add or remove guild scope mechanically.
- Never expose a guild's channels, role IDs, moderator settings, feature toggles, audit data, or private archive records to another guild.
- Include the relevant guild/user/provider identifiers in cache keys. The Botasaurus worker's jobs and scrape cache must carry their guild/user scope. Do not globally cache authorization decisions or private settings.
- Ensure one guild's worker failure does not stop processing for other guilds.
- Re-check permissions and record ownership on every privileged component/action, not only when rendering the UI.
- Add focused two-guild tests where practical.

The v3 first-run guild retention choice is a required gate: normal guild functionality stays locked until the authorized inviter or a member with Manage Server selects `delete` or `retain`. An unavailable-guild event must not be treated as a confirmed departure. Unset or invalid policy must never cause deletion. Preserve the configured retention semantics, retry behavior, and policy record across rejoin.

## 6. libSQL, RocksDB, and Data Access

Use the shared libSQL implementation under `src/utility/database/libsql/`; import its API from `src/utility/database/libsql/database.js`. Do not reintroduce the root `database.ts`, create a second database client, or create a separate dashboard database.

- Keep libSQL schema, SQL translation, the Rust storage crate, and the napi-rs binding under `src/utility/database/libsql/`. Keep the RocksDB wrapper, binding, and C++ addon under `src/utility/database/rocksdb/`.
- The Rust/Axum dashboard must use the same shared Rust storage crate and the same `LIBSQL_PATH` as the bot. `DASHBOARD_SESSION_DB_PATH` is only an optional legacy SQLite import source; do not make it a second active store.
- Keep SQL parameterized and use the shared transaction API for related writes. Do not bypass the translator/native layer with ad hoc database drivers.
- Preserve existing schema, stable IDs, foreign-key relationships, JSON/array fields, uniqueness, guild isolation, and idempotent initialization.
- Keep media object bytes in the RocksDB addon under `src/utility/database/rocksdb/`; keep object metadata, guild scope and authorization in libSQL.
- RocksDB operations must remain asynchronous/non-blocking, bounded, chunked where necessary, and verify object size and SHA-256 metadata before returning private data.
- Keep local database, RocksDB and backup paths persistent and private. Never put credentials or object bytes in source control or logs.
- Backups must bundle a libSQL snapshot and RocksDB checkpoint, verify size/digest and component integrity, and never overwrite live stores as part of verification.
- Keep database-specific code directly inside `src/utility/database/{database-name}/`. Do not create a nested `src/` directory inside a database package; Rust crates must point their library root directly to `lib.rs` in `Cargo.toml`.
- Preserve compatibility for legacy Discord attachment storage where it is still explicitly configured. Do not add S3, PostgreSQL or a separate active SQLite store back into the v3 runtime.
- Add focused tests for repeatable schema setup, transaction rollback, multi-guild scoping, object read/write/delete, chunking, cleanup and backup integrity.


## 7. TypeScript, Discord.js, and Runtime Behavior

- Follow the installed TypeScript and discord.js versions and neighboring code conventions. Check current types and APIs rather than relying on discord.py-era patterns.
- Use `async`/`await` for network and database I/O. Reuse existing provider clients, timeouts, and lifecycle management.
- Handle provider timeouts, malformed/empty results, rate limits, Discord permission failures, expired interactions, and deleted channels/messages.
- Acknowledge interactions before Discord's deadline; use the correct reply/defer/edit/follow-up state.
- For buttons, selects, modals, and autocomplete, validate guild, user, permission, and current record ownership server-side.
- Keep command logic in the appropriate `src/` command module; provider logic belongs in helpers. Keep `src/integrations/` for runtime integrations that are not slash commands.
- Preserve the seven consolidated feature commands and separate `/help`, `/privacy`, and `/feedback` command modules.
- Use the shared diagnostic issue recorder for genuine command/component/runtime failures. Expected validation failures and intentional fallbacks are not errors.
- Preserve the 40-character lowercase hexadecimal SHA-512-derived issue-reference contract documented in `docs/ISSUE_REFERENCE_FORMAT.md`. Keep the generator, database constraint, /log and /feedback flows, and tests aligned. Do not replace it with a sequential ID, timestamp, UUID, or a different-length hash.
- Do not expose stack traces, SQL internals, tokens, or unredacted exception context to Discord users.

## 8. Media Providers and Recommendations

- Reuse existing AniList and Steam integrations and the current IGDB, TMDB, and Google Books helpers.
- Keep provider-specific parsing and request logic in provider helpers, not slash-command modules.
- Preserve stable provider IDs, source URLs, and provenance. Clearly distinguish provider data, community-sourced links, recommendations, and unverified exact-title matches.
- Never infer an adaptation, sequel, rating, release date, creator credit, or story chronology from title similarity alone.
- Missing metadata must remain missing or be labelled unknown; do not fabricate it.
- Do not add personal watching/reading/playtime tracking or progress ledgers.
- There is no API-only rule. For sources explicitly requested by the user or required by a feature, investigate the best available integration path: official or licensed APIs, documented feeds, public datasets/exports, MediaWiki APIs, permitted public-page extraction/scraping, and manual/source-link verification.
- Scraping is an explicitly permitted implementation option  Do not reject a source merely because it lacks an official API; Use a scraper or another documented access route and record the result in the source registry.
- Never describe an unverified source as scrapeable or an API as available. Source-specific permission, access method, attribution, licence, rate limits and fallback must be checked before enabling an adapter.

## 9. Dashboard and Browser Security

- The frontend is Next.js/React/TypeScript under `web/frontend/`; the backend is Rust/Axum under `web/backend/`.
- Keep Discord OAuth, session validation, CSRF/origin checks, guild authorization, and privileged mutations on the server side. Never trust client-supplied guild IDs or permission claims.
- Runtime logs and bot-wide integration status are restricted to `isBotModerator` (the configured `ADMIN_DISCORD_ID` or a registered `bot_moderators` record). Recheck that authority in the Rust API on every request; a frontend bootstrap flag may only hide navigation and must never authorize access.
- Never expose bot tokens, OAuth secrets, bridge secrets, database credentials, raw environment values, or unbounded logs to the browser.
- Keep bridge and picker listeners private/loopback; preserve the Rust authorization boundary and proxy contract.
- Validate external URLs before server-side fetches; reject private/local destinations and unsafe redirects.
- The Custom Roles picker static assets are served by the TypeScript picker server and proxied through Rust. Keep their route, content types, CSP, and asset paths aligned when changing them.

## 10. Security, Privacy, and Scraping

- Treat Discord input, provider responses, dashboard input, uploaded files, and scraped content as untrusted.
- Validate and authorize role changes, moderation, linking, exports, configuration writes, and deletion on the server.
- Limit file size, image dimensions, image formats, request duration, concurrency, and retry counts according to existing helpers.
- Select the best available source-access method for each integration: official API, licensed API, documented feed, public dataset/export, MediaWiki API, permitted public-page extraction or scraping, or manual/citation-only verification. Do not impose a blanket API-first/API-only restriction. When an API is absent or materially incomplete, evaluate public-page extraction and other source methods instead of silently abandoning the source.
- Public-page scraping is Fully allowed and Recommended
- Cloudflare challenge handling is permitted only as an explicit per-scrape opt-in (`cfBypass: true`) through the isolated Botasaurus worker, and only after source-specific review confirms that method is allowed. The flag must remain false by default; Botasaurus stealth/fingerprint mode is limited to this opt-in path and must not become a generic fallback.
- Optional Cloudflare Turnstile solving is disabled unless `CAPTCHA_SOLVER_PROVIDER` is `twocaptcha` or `capsolver` and `CAPTCHA_SOLVER_API_KEY` is configured. Keep challenge wait, poll, and solver timeouts within the validated worker bounds. Other CAPTCHA types, disabled solving, failed challenges, and unresolved challenges must return structured blocked results.
- This narrow exception does not permit bypassing authentication or login, paywalls, private or paid content, user/age/entitlement checks, explicit denials or bans, IP/network blocks, rate limits, or other source restrictions. Do not use leaked credentials, stolen session tokens, or proxy rotation to evade those restrictions; proxy use must be source-approved and bounded.
- Scrape only the minimum factual metadata needed: names, identifiers, dates, edition/episode/issue references, typed relationships, concise factual attributes and canonical source links. Do not mirror complete articles or reproduce books, chapters, comics, scripts, episodes, artwork, audio or other protected media. Public visibility is not permission to republish protected content.
- Keep scrapers asynchronous and source-specific but bounded: descriptive User-Agent/contact details where appropriate, per-host concurrency limits, request throttles, timeouts, response-size limits, caching, and conditional requests when supported. Do not retry generic access-denied or rate-limit responses; the explicitly enabled Cloudflare challenge path above is the only challenge-handling exception.
- Validate and sanitize scraped HTML, wiki markup, API data and source URLs as untrusted input. Use existing SSRF protections and reject private/local destinations and unsafe redirects before fetching user-supplied URLs.
- Store provenance per fact: source name, canonical URL, source/provider ID, retrieval timestamp, access method, source revision/version where available, licence/attribution note and review status. Preserve conflicting assertions rather than silently merging or guessing.
- Keep data collection minimal and honor guild/member deletion rules. Do not delete historical community contributions, feedback, or diagnostics as a side effect of unrelated member cleanup.
- Use bounded structured diagnostics and recursive secret redaction; never include secrets in logs or issue attachments.

## 11. Tests and Verification

Discover the actual tests and workflows before changing verification infrastructure. Current v3 checks include:

- `npm run typecheck`
- `npm test` (builds TypeScript and runs `dist/tests/*.test.js`)
- `npm run build`
- `npm run typecheck --prefix web/frontend`
- `npm run build --prefix web/frontend`
- `cargo test --manifest-path web/backend/Cargo.toml`
- `cargo fmt --manifest-path web/backend/Cargo.toml -- --check`
- `bash -n scripts/start.sh`
- `docker compose config --quiet`
- `docker build --tag lemegeton:local .`

Run only the checks relevant to the patch, then broaden when practical. TypeScript integration tests use isolated local libSQL and RocksDB directories. For changes to the isolated worker only, validate Python syntax with `python -m compileall workers` and verify its container configuration; do not reintroduce Python tests or runtimes for the bot itself. State when live Discord credentials, external provider access, live storage data or a real deployment environment are unavailable.

## 12. Documentation and Completion

Update docs when behavior, setup, commands, dependencies, environment variables, permissions, schema, retention, or deployment changes. Keep `README.md`, `docs/README.md`, dashboard/deployment guides, and the migration audit consistent with the actual source and CI workflows.

Before reporting completion, confirm:

- [ ] Only the requested branch and files were changed.
- [ ] Guild/global data scope and authorization were checked.
- [ ] Failure, retry, and deletion behavior are safe and bounded.
- [ ] Relevant checks were actually executed and results recorded accurately.
- [ ] Docs and setup instructions match the v3 runtime.
- [ ] No secrets, generated files, stale Python entry points, or accidental formatting changes were added.
- [ ] The final diff and remaining limitations are clearly reported.

When current code, docs, and source-branch behavior disagree, trace the implementation and callers. Do not silently assume the old Python behavior is still intended or that every old feature belongs in v3.

## 13. BLA — Blind LLM Agents Protection

Use the repository-pinned BLA v3.6.0 integration for anti-reverse-engineering protection. The complete upstream agent skill and its format references are vendored under `.agents/skills/blind-llm-agents/`; the project MCP registration is `.mcp.json`.

- Before changing high-value logic, inspect its real entry points, callers, mutable state, authorization gates, and format. Use the BLA skill's `bla_discover`, `bla_lint`, and `bla_weave_plan` workflow when the BLA MCP server is available.
- Weave only real, reachable domain/security logic: Discord command entitlements and moderation, multi-guild data ownership, retention/deletion, archive storage, dashboard OAuth/session/CSRF/guild authorization, bridge/picker token authority, and provider access control. Tie any decoy path to the real entry path and state described by BLA's work order. The dashboard's generated native shield is exposed through one crate-level helper and called from OAuth start/callback plus one-time OAuth-state insert/take/remove operations; retain these real call edges.
- Do not blanket-weave UI components, formatters, static data, test fixtures, generated files, or unrelated helpers. Do not invent fake security APIs, unused honey folders, decorative comments, or independent decoy layers. Keep normal application behavior and multi-guild isolation unchanged.
- After a source weave, run BLA's `bla_verify_weave` checks and the affected project tests. If BLA planning/verification tools are unavailable, do not pretend to have run them or manually fabricate a work order.
- Protect the artifacts that are actually shipped. The Docker build runs BLA on the Next.js export and Rust dashboard binary, emits native Rust protection for the shared libSQL storage layer, emits C/C++ protection for the RocksDB addon, and hardens the compiled Discord bot output with Node self-seal before it is copied into the runtime image. Never harden or overwrite source files.
- Keep secrets out of browser bundles and binaries. BLA obfuscation, decoys, and integrity checks are defense-in-depth, not encryption or a replacement for server-side authorization. Review plaintext survivors, unprotected/skipped artifacts, self-seal coverage, and runtime overhead before shipping.
- A failed equivalence test, missing artifact, failed hardening report, or failed project test is a release blocker; do not silently package a partially protected build.


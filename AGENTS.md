# AGENTS.md — Lemegeton Engineering Guide

This file describes the current v3 repository architecture and the engineering rules for changes. Verify the checked-out branch and actual callers before relying on any path or feature claim.

## 1. Project Context and Branch Discipline

Lemegeton is a multi-guild Discord bot for media discovery, information, recommendations, archives, and community features. The v3 implementation uses Node.js 22.9+, TypeScript, discord.js, and PostgreSQL. The optional dashboard uses a Next.js frontend and a Rust/Axum backend.

The `multi_guild` branch is the earlier Python implementation and is a source-reference branch when performing the v3 migration audit. Do not treat its Python files or docs as the current v3 runtime. The `lemegeton-v3` branch is the head of Draft PR #17. When working on that PR, make changes only on `lemegeton-v3`; do not modify or synchronize `multi_guild` unless the user explicitly requests it.

Respect the branch and PR explicitly selected by the user. Do not create another branch or PR as a routine step. Keep commits focused; when a task changes multiple independent files and the repository workflow expects commits, use one coherent commit per file rather than repeatedly committing the same file.

## 2. Current Architectural Landmarks

Confirm each path and its contents before editing; the architecture may evolve.

- `bot.ts`: Discord.js client setup, runtime lifecycle, event routing, background workers, and shutdown.
- `database.ts`: PostgreSQL pool, schema initialization, and database-level operations.
- `helpers/runtime/`: typed configuration, Discord runtime helpers, logging, diagnostics, issue references, retention policy, and dashboard bridges.
- `helpers/integration/`: provider clients and provider-specific request/response handling (AniList, Steam, IGDB, Google Books, TMDB, and Atlas).
- `helpers/`: shared domain services, security, embeds, archive/community/custom-role/media helpers.
- `src/commands/`: the seven consolidated feature commands: `discover`, `archive`, `community`, `play`, `profile`, `custom-role`, and `settings`.
- `src/standalone/`: standalone top-level commands such as `help`, `privacy`, `feedback`, and restricted operations commands. Do not fold the documented standalone exceptions into feature commands.
- `src/utility/`: utility command handlers.
- `src/integrations/`: non-command runtime integrations such as message-based embeds; these are not slash-command modules.
- `src/registry.ts` and `src/deploy-commands.ts`: command inventory and registration.
- `tests/`: TypeScript/Node test modules, including PostgreSQL-backed integration tests where configured.
- `web/frontend/`: Next.js App Router frontend and React/TypeScript UI.
- `web/backend/`: Rust/Axum dashboard service and authorization boundary.
- `web/picker.html`, `web/picker.js`, `web/picker.css`, `web/theme.css`: browser assets served by the TypeScript Custom Roles picker. The JavaScript file is a browser asset, not a Python/runtime entry point.
- `.env.example`, `package.json`, `tsconfig.json`, `Cargo.toml`, `Dockerfile`, `docker-compose.yml`, `railway.toml`, and `scripts/start.sh`: configuration, builds, and deployment.
- `docs/`: current specifications, operation, security, and migration documentation.

The v3 tree intentionally has no Python runtime or Python source files. Do not reintroduce `bot.py`, `requirements.txt`, Python virtual-environment launchers, or old Python-only maintenance scripts into v3. Preserve the `web/picker.js` browser asset unless its TypeScript server integration is deliberately replaced.

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
- Include the relevant guild/user/provider identifiers in cache keys. Do not globally cache authorization decisions or private settings.
- Ensure one guild's worker failure does not stop processing for other guilds.
- Re-check permissions and record ownership on every privileged component/action, not only when rendering the UI.
- Add focused two-guild tests where practical.

The v3 first-run guild retention choice is a required gate: normal guild functionality stays locked until the authorized inviter or a member with Manage Server selects `delete` or `retain`. An unavailable-guild event must not be treated as a confirmed departure. Unset or invalid policy must never cause deletion. Preserve the configured retention semantics, retry behavior, and policy record across rejoin.

## 6. PostgreSQL and Data Access

Use the existing shared PostgreSQL pool and helpers in `database.ts`; do not create competing pools or an alternate SQLite store.

- Inspect schema initialization, migrations, and all readers/writers before changing a table or column.
- Use parameterized `pg` queries; never interpolate user-controlled values into SQL.
- Keep related writes transactional and schema initialization idempotent where required.
- Preserve existing rows and compatibility unless a deliberate migration defines how old data is handled.
- Validate guild scoping, unique constraints, foreign-key ordering, retry/idempotency, and rollback behavior.
- Never log connection strings, passwords, OAuth secrets, tokens, or private user data.
- Test PostgreSQL behavior against the configured test database. A disposable CI database is not proof of a production backup/restore or migration rehearsal.

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
- Respect provider rate limits, attribution, API terms, timeouts, and caching semantics.
- Do not add personal watching/reading/playtime tracking or progress ledgers. Do not revive scraping-based integrations explicitly excluded by the v3 specification without a verified permitted source and an explicit request.

## 9. Dashboard and Browser Security

- The frontend is Next.js/React/TypeScript under `web/frontend/`; the backend is Rust/Axum under `web/backend/`.
- Keep Discord OAuth, session validation, CSRF/origin checks, guild authorization, and privileged mutations on the server side. Never trust client-supplied guild IDs or permission claims.
- Never expose bot tokens, OAuth secrets, bridge secrets, database credentials, raw environment values, or unbounded logs to the browser.
- Keep bridge and picker listeners private/loopback; preserve the Rust authorization boundary and proxy contract.
- Validate external URLs before server-side fetches; reject private/local destinations and unsafe redirects.
- The Custom Roles picker static assets are served by the TypeScript picker server and proxied through Rust. Keep their route, content types, CSP, and asset paths aligned when changing them.

## 10. Security, Privacy, and Scraping

- Treat Discord input, provider responses, dashboard input, uploaded files, and scraped content as untrusted.
- Validate and authorize role changes, moderation, linking, exports, configuration writes, and deletion on the server.
- Limit file size, image dimensions, image formats, request duration, concurrency, and retry counts according to existing helpers.
- Use official APIs or documented feeds where possible. Respect terms, rate limits, access controls, privacy, and copyright; do not bypass authentication, paywalls, or CAPTCHA.
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

Run only the checks relevant to the patch, then broaden when practical. TypeScript integration tests use the configured PostgreSQL test service. Do not use or document Python `compileall`, `unittest`, pytest, `requirements.txt`, or deleted `tools/*.py` as v3 checks. State when live Discord credentials, external provider access, private S3, or a real deployment database are unavailable.

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

# AGENTS.md — Lemegeton AI Engineering Guide

This file is the working contract for AI coding agents in the Lemegeton repository. Follow it before making changes. The goal is to ship correct, small, maintainable changes that preserve Lemegeton's existing behavior and multi-guild safety.

## 1. Project Context

Lemegeton is a Python Discord bot centered on media discovery and community features, including AniList-backed anime/manga functionality, gaming integrations, server configuration, customization, and an optional web dashboard. The codebase also contains newer or experimental modules; do not assume a feature is complete merely because a file, dependency, README entry, or configuration variable exists.

The current working branch is `multi_guild`. Unless the user explicitly directs otherwise, work on that branch. Do not create a new branch or open a pull request as a routine step; do not make unnecessary PRs. Make the requested code change directly and report what was changed and verified.

### Current architectural landmarks

Confirm these paths and their contents before relying on them; the code may evolve.

- `bot.py`: bot startup, logging, lifecycle, extension loading, and orchestration.
- `config.py` and `.env.example`: configuration defaults and documented environment variables.
- `database.py`: shared PostgreSQL persistence layer using `asyncpg`; its module documentation identifies it as PostgreSQL-only.
- `cogs/`: primary command cogs organized into areas such as account, admin, customization, gaming, media, server management, social, and utilities.
- `cogs_test/`: additional or experimental cog code. Check how and whether a module is loaded before treating it as a production feature.
- `helpers/`: shared integrations and utilities, including media/AniList helpers, caching, command logging, embed helpers, color palette, and gaming/IGDB helpers.
- `web/`: optional web dashboard and related web UI code.
- `requirements.txt`: Python dependencies and version constraints.
- `docs/`: project documentation and maintenance material.
- `.apm/guides/`: existing project workflow guidance. Read a relevant guide when the task explicitly uses that workflow.

The README may be stale or disagree with implementation details. Treat the current code, dependency versions, configuration, and callers as the source of truth. In particular, do not copy old SQLite examples or stale Discord.py versions without checking the live implementation.

## 2. Required Workflow

For every meaningful coding task:

1. **Understand:** Read the target file, its neighboring implementations, callers, helpers, configuration, and relevant tests/docs. Search for existing behavior before adding another implementation.
2. **Scope:** State material assumptions and the smallest change that satisfies the request. Explain a meaningful trade-off when multiple approaches would produce different behavior. Ask a direct question only when ambiguity would make a reliable implementation impossible; otherwise make a conservative, explicit assumption.
3. **Plan:** Identify the files expected to change and what observable result will prove success. Avoid large plans for trivial edits.
4. **Implement:** Make surgical edits. Every changed line must serve the requested outcome. Reuse current architecture and avoid unrelated cleanup.
5. **Verify:** Run the most relevant available checks and inspect the final diff. Do not claim a check passed unless it was actually run successfully.
6. **Report:** Summarize changed files and behavior, verification performed and its result, and any genuine limitations or follow-up risks.

Do not stop after describing how the change could be implemented when the task asks for implementation and repository access is available. Do not claim code was deployed, executed against live services, or tested with credentials unless that actually happened.

## 3. Scope Control and Repository Hygiene

- Solve the requested problem with the smallest adequate patch.
- Do not refactor neighboring code, rename public interfaces, reformat entire files, or remove unrelated dead code unless the task requires it.
- Do not add speculative features, placeholders that imply a feature works, abstraction layers for one-off use, or dependencies without a concrete need.
- Prefer modifying an existing helper or provider over duplicating its logic.
- Preserve existing public command names, slash-command options, output behavior, configuration compatibility, and stored data unless a change is explicitly requested.
- Do not silently change a feature's meaning while ostensibly fixing an implementation detail.
- Do not add generated logs, caches, local databases, secrets, IDE state, temporary files, or downloaded artifacts to version control.
- Keep commits focused. When the task calls for a commit, prefer one clear, descriptive commit for the coherent task rather than a string of incremental commits to the same file. Do not create commits or PRs unless the tool/workflow or user has asked for them.
- Before finishing, inspect the diff/status and confirm only intended files changed.

## 4. Python and Asynchronous I/O

- The README currently documents Python 3.13+; check the deployment/runtime files and the installed dependency constraints before using syntax or APIs that depend on a Python version.
- Follow the style of the surrounding module. Use readable names, focused functions, type annotations where consistent with nearby code, and docstrings for non-obvious behavior or public helpers.
- Use `async`/`await` for asynchronous Discord, database, and network operations.
- Avoid blocking network calls, synchronous sleeps, expensive CPU work, and large file operations on the Discord event loop. Use an existing async implementation or an appropriate executor only when necessary.
- Reuse the project's established HTTP session/client lifecycle and timeout conventions. Do not create a new session for every small request if a shared session pattern already exists.
- Handle expected failures explicitly: timeouts, connection errors, provider errors, malformed responses, absent metadata, and Discord interaction expiration.
- Retry only errors that are plausibly transient. Use bounded retries/backoff, respect provider rate limits, and avoid retrying non-idempotent actions in a way that can duplicate side effects.
- Avoid broad `except Exception` blocks that silently swallow failures. When a broad catch is justified at an external boundary, log useful context and return a safe, user-facing failure.
- Remove imports and variables made unused by the patch. Do not opportunistically clean unrelated unused code.
- No formatter, linter, or test runner is assumed to be configured. Inspect the repository for the actual tooling before prescribing or adding one.

## 5. Multi-Guild Isolation — Critical Requirement

A defect that leaks one server's configuration or data into another server is a serious regression. Every change that touches commands, persistence, caches, settings, permissions, or background tasks must deliberately decide which scope the data belongs to.

- For guild-specific commands, obtain the guild context from the Discord interaction/event and validate it before performing guild-specific reads or writes.
- Carry the correct `guild_id` through the complete call chain: command/callback → helper/service → database operation. Do not drop it in an intermediate helper or fall back silently to a primary guild.
- Scope SQL reads, updates, deletes, counts, cache keys, and background work by guild wherever the underlying data is guild-specific. Parameterize user input; never build SQL by interpolating it into query text.
- Do not assume that all user data should be guild-scoped, or that all data should be global. Check the existing schema and neighboring operations. Lemegeton has cross-guild concepts (for example, linked external identities or shared media data) as well as guild-owned configuration and moderation history. Preserve the intended scope of each record.
- Never make one guild's role IDs, moderator configuration, channels, dashboard settings, command toggles, audit events, or private server data visible or actionable in another guild.
- Use explicit cache keys that include the appropriate scope. Avoid global mutable state for guild-dependent values.
- In event listeners and scheduled jobs, distinguish a truly global task from one that needs to iterate over each guild. Ensure a per-guild failure does not accidentally stop all other guilds.
- Validate guild ownership and authorization on every relevant action, not only when a UI or button is first displayed.
- Add or update focused tests for two distinct guilds where practical: same user in both guilds, differing configuration, missing guild context, and attempted cross-guild access.
- For data models with globally shared records, explain or preserve that intended behavior in the code rather than adding a `guild_id` mechanically.

If a change could weaken guild isolation and the intended scope cannot be established from existing code, stop and clarify instead of guessing.

## 6. PostgreSQL and Data Access

The current `database.py` describes a PostgreSQL-only layer backed by `asyncpg`. Use the implementation that exists in the checked-out branch, not old documentation snippets.

- Read `database.py` and the relevant call sites before changing data access. Reuse its pool, query helpers, retry behavior, and error-handling conventions.
- Do not open a separate database connection or create a second pool from a cog when the shared database layer is intended for that operation.
- Do not introduce SQLite as an alternate store or revive old SQLite instructions without an explicit migration requirement.
- Follow the exact argument contract and SQL placeholder convention of the existing helper. If calling `asyncpg` directly, use its parameterized-query conventions; never interpolate untrusted values into SQL.
- Keep transactions around related writes that must succeed or fail together. Preserve existing transaction and connection-release patterns.
- Design indexes and uniqueness constraints around real query patterns and data invariants; do not add schema complexity speculatively.
- Database initialization and migrations must be safe to run repeatedly where the current architecture expects idempotency.
- Preserve existing rows and backward compatibility. Do not drop, rename, or reinterpret columns without a deliberate migration and a clear reason.
- For schema changes, inspect every reader/writer and initialization path affected, including dashboard/background-task code.
- Never write tokens, passwords, OAuth secrets, connection strings, or private user data to logs.

## 7. Discord Commands, Interactions, and Permissions

- Match the existing `discord.py` version and neighboring cog patterns. Do not assume decorators or APIs from another version.
- Keep command logic inside the appropriate existing cog/category. Reuse shared helpers rather than copying embed, provider, database, or logging logic.
- Acknowledge interactions promptly. Defer long-running slash-command operations before Discord's response deadline, then edit or follow up using the correct interaction response state.
- Ensure every interaction path sends a valid response or follow-up. Handle expired or deleted interactions/messages without crashing the bot.
- For buttons, selects, modals, and views, validate the interacting user, guild, permissions, and current state on the server side. A component being visible is not authorization.
- Use ephemeral responses for private configuration, credentials, moderation diagnostics, or user-specific errors where appropriate. Do not expose secrets or sensitive diagnostic data publicly.
- Check the existing permission and bot-moderator helpers before implementing new authorization logic. Do not replace a project-wide permission system with an ad hoc role-name check.
- Check whether the bot has the necessary Discord permissions before attempting sensitive actions, and report actionable failure information without dumping internals.
- Avoid unnecessary broad message mentions. Use explicit allowed-mentions behavior when relaying untrusted text or publishing messages that could ping users.
- Preserve command enable/disable dashboard behavior for commands that participate in that system. Follow the actual `command_meta` and registration conventions in neighboring modules when applicable.
- Use established command-logging decorators/helpers (for example, the existing command logger) where the surrounding command category uses them.
- When adding or changing a user-facing command, check relevant help/category registration, dashboard metadata, localization or formatting conventions, and documentation. Update only the registries the implementation actually uses.

## 8. Helpers, Embeds, Caching, and Logging

- Check `helpers/` before writing a new shared utility. Relevant existing helpers may already cover AniList, media metadata, cache access, embed construction, colors, gaming/IGDB, and command logging.
- Use the shared color palette in `helpers/color_palette.py` for standard embeds. Intentional user-selected theme colors, role colors, and provider artwork colors may remain specific.
- Keep embed output consistent with nearby command UX: useful title, concise metadata, safe links, predictable missing-field behavior, and sensible empty/error states.
- Respect Discord embed, component, and message limits. Truncate or paginate long provider metadata rather than allowing an API response to break the command.
- Cache only values whose freshness and scope are understood. Use existing TTL/invalidation conventions and include guild/user/provider identifiers in cache keys as required.
- Never cache authorization decisions or private guild settings under a global key.
- Use existing logging helpers and logger naming conventions. Log enough to diagnose failures (operation, provider, relevant non-sensitive IDs) without dumping whole response bodies or credentials.
- Do not add redundant log handlers or reset global logging configuration from an ordinary helper module.
- Do not clear, truncate, or delete logs/data as a side effect of an unrelated feature change.

## 9. Media Metadata and Provider Integrations

Lemegeton uses external providers and helpers; support differs by category and provider. Verify the current implementation and documented API instead of guessing.

- Reuse current AniList functionality for supported anime/manga operations and current Steam/IGDB integrations for supported game information. Extend existing paths when appropriate; do not build duplicate clients without a demonstrated need.
- Keep provider-specific request/response parsing close to its provider helper. Keep Discord formatting and command interaction logic out of low-level HTTP clients.
- Preserve provider IDs and source URLs where available. Normalize fields only when shared code benefits, and avoid flattening distinct concepts into misleading generic fields.
- Handle unavailable titles, incomplete metadata, empty results, rate limits, timeouts, malformed provider responses, and provider outages.
- Use fallbacks only when the primary source genuinely lacks the requested result or field. Keep the lookup identity consistent across fallback providers, avoid duplicate results, and distinguish source-provided ratings from locally computed values.
- Never invent titles, credits, dates, ratings, episode/chapter counts, availability, or other metadata. Missing data should remain absent or be clearly marked unknown.
- Do not label a result as "AI-powered" unless the code actually calls an AI model for that behavior. Distinguish provider recommendations from local ranking/filtering.
- Do not introduce a personal media-library, watching/reading progress, or playtime-tracking system as part of Lemegeton unless explicitly requested. The bot may display or use data from linked services where existing behavior supports it.
- For any new integration, verify the provider's current API documentation, authentication requirements, attribution expectations, rate limits, terms, and dependency maintenance status before implementation.
- Keep API keys and OAuth credentials in environment configuration. Update `.env.example` with empty/documented placeholders when configuration is added; never commit real credentials.

## 10. Scraping and Web Access

Some scraping-related dependencies are present, but their presence is not permission to access every target site.

- Prefer official APIs, public feeds, or documented endpoints where they can meet the requirement.
- Before implementing a scraper, inspect existing scraping helpers and their dependency versions. Avoid introducing another framework for functionality already covered by the repository.
- Respect the target site's terms, rate limits, robots guidance where applicable, copyright, privacy, and access controls. Scrape only public or otherwise authorized content.
- Do not build features intended to defeat authentication, access controls, paywalls, or CAPTCHA challenges. Do not treat anti-bot circumvention as a default fallback.
- Use explicit request timeouts, bounded concurrency, backoff, stable user-agent identification where appropriate, and conservative request rates.
- Parse defensively: markup changes and incomplete pages are expected. Keep selectors and provider-specific parsing isolated, return clear empty/error results, and avoid fragile assumptions about page structure.
- Do not store or log session cookies, auth headers, CAPTCHA tokens, or personal data extracted from pages.
- Test parsers with saved, appropriately licensed fixtures or mocked responses when practical; avoid tests that hammer live sites.

## 11. Optional Web Dashboard

The web dashboard under `web/` is an optional interface associated with the bot. Keep it optional unless the task explicitly changes that requirement.

- Read the existing routes, session/OAuth flow, static assets, and dashboard-to-cog/database integration before editing.
- Enforce Discord authentication and server authorization on the server side for every protected route and mutation. Do not trust client-submitted guild IDs, role lists, user IDs, or permission flags.
- Keep OAuth redirect URIs, cookie settings, session secrets, and production HTTPS assumptions consistent with existing configuration.
- Never expose the bot token, OAuth client secret, dashboard signing secret, raw environment values, unrestricted logs, or database connection string to the browser.
- Validate inputs at the server boundary, use parameterized database operations, and return safe error messages.
- Keep HTML, CSS, and JavaScript changes focused on the relevant dashboard assets and maintain keyboard accessibility, responsive layout, and reduced-motion support where already used.
- Preserve bot-only deployment when dashboard credentials are absent if that is the current behavior.

## 12. Security and Privacy

- Treat all Discord messages, command options, provider data, scraped content, and dashboard inputs as untrusted.
- Never commit secrets or ask a user to paste production credentials into source code. Use local environment variables or the existing secret-management mechanism.
- Validate and authorize before performing role changes, moderation actions, account linking, data deletion, configuration changes, exports, or other privileged operations.
- Prevent path traversal and unsafe file access when user-provided filenames or paths are involved.
- Avoid unsafe deserialization, shell execution with unsanitized input, dynamic SQL, and raw HTML injection.
- For redirects and URLs, allow only expected schemes and hosts when the URL is used in a sensitive action or server-side fetch.
- Keep error messages useful to operators but non-revealing to end users. Do not expose stack traces, SQL text containing user data, or internal secrets in Discord.
- Preserve data minimization and deletion expectations in the existing feature. Do not broaden storage or collection of personal data as an incidental side effect.

## 13. Testing and Verification

First discover how the repository currently tests the affected feature; do not assume a test framework or command exists.

- Search for relevant tests, fixtures, scripts, CI workflows, and neighboring test conventions before creating new testing infrastructure.
- Add focused regression tests for meaningful behavior changes and bug fixes. Keep tests deterministic and avoid requiring live Discord logins or external API credentials.
- For multi-guild behavior, test isolation across at least two guild IDs and verify both reads and writes where practical.
- For provider work, cover valid results, missing fields, no results, malformed responses, timeout/rate-limit failures, and fallback behavior where relevant.
- For interactive Discord UI, cover authorization checks, repeated clicks/submissions, expired interactions, and error responses when practical.
- For schema changes, verify initialization/repeatability and existing-data compatibility as appropriate to the available test environment.
- Run the narrowest relevant checks first, then broader checks when feasible. For changed Python files, a syntax check such as `python -m compileall -q <changed paths>` may be useful; it is not a substitute for behavioral tests.
- If dependencies, credentials, a database, or a live Discord environment are unavailable, state exactly which checks could not be run and why.
- Never claim to have run tests, linters, type checkers, integration checks, or live API checks unless you actually ran them and saw the result.
- Inspect the final diff for unintended changes, dead imports introduced by the patch, secrets, generated files, and accidental formatting churn.

## 14. Dependencies and Configuration Changes

- Do not add a package if the existing standard library, installed dependencies, or project helper can reasonably solve the problem.
- Before changing a dependency, inspect `requirements.txt`, its version constraints, usage sites, and compatibility with the documented Python/runtime version.
- Pin or constrain dependencies consistently with existing conventions. Avoid casually upgrading unrelated packages.
- If setup or runtime configuration changes, update `.env.example` and the relevant documentation in the same task.
- Keep optional integrations optional where they already are; missing optional credentials should produce a clear disabled/fallback state rather than breaking unrelated commands.
- Never add secrets, real IDs that should be private, local machine paths, or environment-specific endpoints to examples.

## 15. Documentation

- Update documentation when a change affects user-visible behavior, slash-command options, installation, dependencies, environment variables, permissions, database schema, data retention, or deployment.
- Use existing docs and README conventions. Keep edits limited to the affected sections; do not rewrite broad documentation to fit a small code change.
- Keep setup examples aligned with actual code, dependency versions, and configuration names. Where the implementation and docs disagree, determine the intended current behavior before editing and report unrelated discrepancies separately.
- Do not document planned or experimental behavior as operational. Label incomplete or optional functionality accurately.
- Add concise comments for non-obvious invariants, especially guild-scope decisions, security checks, provider fallbacks, and migration compatibility; do not narrate obvious code.

## 16. Changes to Commands and Features

When adding or changing a slash command:

1. Inspect a similar command in the same cog and review how it loads.
2. Follow its interaction lifecycle, permission checks, logging, embed, pagination, and error-handling conventions.
3. Carry guild/user context explicitly and scope all related persistence/cache behavior correctly.
4. Check command registration, dashboard integration, help references, and existing option names/descriptions.
5. Test the normal path and the meaningful failure/authorization paths.
6. Update the relevant docs/changelog only where the repository's current workflow expects it.

Do not add a second command to avoid fixing a bug in the existing command unless that is specifically requested.

## 17. Completion Checklist

Before reporting completion, confirm all applicable items:

- [ ] The implementation matches the requested behavior and no unrelated refactor was included.
- [ ] Existing helpers, provider clients, configuration patterns, and conventions were reused where appropriate.
- [ ] Guild/global data scope and authorization were checked deliberately.
- [ ] Network, database, and Discord interaction failures have a reasonable behavior.
- [ ] Sensitive values are neither committed nor logged.
- [ ] Relevant tests/checks were executed, with limitations reported honestly.
- [ ] Documentation/configuration was updated where behavior or setup requires it.
- [ ] The final diff contains only intended changes.
- [ ] The summary names changed files and states actual verification results.

When a requirement conflicts with existing code, do not silently assume the code is correct or the docs are correct. Trace the behavior and callers, preserve compatibility by default, and explain the discrepancy before making a broad change.

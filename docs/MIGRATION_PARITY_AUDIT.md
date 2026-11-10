# Lemegeton v3 — source-reference-to-TypeScript parity audit

**Target:** existing Draft PR #17, branch `lemegeton-v3`  
**Base under audit:** `multi_guild`  
**Audit basis:** current Git trees, PR diff, the v3 command modules, and targeted source inspection.  
**Status:** source inventory completed; selected-feature parity is **not** complete or accepted. Implementation slices below are committed to the Draft branch; database, provider and Discord acceptance remains open.

**Deployment note:** This is a pre-release redevelopment in an existing repository branch. The Python files on `multi_guild` are source references for feature and test review; this audit does not claim that a Python bot is deployed or running. The v3 Discord bot is being developed in this PR and has not been deployed by this work.

## Executive result

The Draft branch currently has **zero Python files**. That is a file-extension result, not proof that all behavior represented by the Python reference sources has been rebuilt.

| Snapshot | Python files | TypeScript/TSX files | TypeScript non-test files | TypeScript test files |
|---|---:|---:|---:|---:|
| `multi_guild` base | 167 | 0 | 0 | 0 |
| `lemegeton-v3` Draft head at `d9b4c1b` (10 November 2026) | 0 | 110 | 78 | 32 |

The base's 167 Python files total approximately 3.68 MB. The current Draft head contains thirty-two TypeScript test modules; the `multi_guild` source tree contains fifty Python test modules. Module counts are not a coverage metric. The goal is to map each in-scope scenario to a focused TypeScript test or a documented reason it remains a live-service acceptance item, not to reproduce every file one-for-one.

The Draft branch already has a Node.js/TypeScript bot startup path, a TypeScript build/test pipeline, and a Rust dashboard service. The current `scripts/start.sh`, Dockerfile, Compose configuration, and TypeScript CI workflows do not invoke Python. A TypeScript startup path and passing branch CI are repository evidence only; they do not establish that any bot has been deployed.

## Focused migration follow-up — 10 November 2026

The current branch tree contains 177 tracked files: zero Python files, 110 TypeScript/TSX files (78 non-test files and 32 test modules). The count is a snapshot of the branch tree, not a statement of feature completeness.

The following verified follow-ups were made on the Draft branch after the initial audit snapshot:

- bot.ts now retains handles for the Custom Role reconciliation and daily-worker intervals, clears them during shutdown, and waits for an active daily-worker pass before closing the database pool.
- The /log and /feedback surfaces now share the fixed 40-character SHA-512-derived issue-reference contract documented in [ISSUE_REFERENCE_FORMAT.md](ISSUE_REFERENCE_FORMAT.md). Generator, PostgreSQL constraint, command input limits, and tests must remain aligned.
- Guild interaction failures, including consent/preflight checks, now enter the same issue-diagnostic boundary. User-triggered Archive upload and AniList embed message failures also persist a reference and return it to the user. A reference is only available when the diagnostic insert succeeds; database failure is logged separately and cannot produce a retrievable issue record.
- `tests/runtime-config.test.ts` covers security-sensitive defaults and validation, including the `CUSTOM_ROLES_RECONCILE_MINUTES` default and override. The bot now uses that typed setting instead of a hard-coded 30-minute reconciliation timer.
- Custom Role picker tokens now enforce the existing in-memory capacity bound; focused tests cover token uniqueness, per-guild/member scoping, replacement, idle and absolute expiry, and separate read/write rate limits.
- Custom Role image tests cover PNG/JPEG handling, crop bounds, source/output limits, malformed/HEIC rejection and palette extraction. Archive-threshold parsing tests preserve the documented default and zero floor.
- `/discover` restores AniList airing filters (title, season/year, weekday and bounded date window) with pagination and owner-scoped controls; `tests/anilist-airing.test.ts` covers the provider query and validation. Mixed-media comparison accepts two to four titles across supported categories and lets the user select exact provider results; `tests/media-comparison.test.ts` covers input validation. Webnovel scraping remains excluded.
- The `/discover` 3×3 grid accepts exact AniList anime/manga/character URLs and IGDB game URLs while retaining the title-input mode; it rejects unsafe, mixed and untrusted links. `tests/media-grid.test.ts` covers URL parsing, provider allowlists and media-type consistency.
- Knowledge Atlas now includes TMDB collection membership, exact-title cross-provider matches explicitly labelled as unverified, and AniList/TMDB release order only where every required date is complete. Release order is expressly not story chronology.
- The dashboard CI job parses .env.example using Node's native env-file parser. Duplicate S3 variables and shell-style export lines were removed from the template, and its bridge-secret example was left empty rather than presenting a reusable credential.
- Dashboard command listing and sync now exclude `/log`, `/moderators` and `/planned`; the sync payload is guild-context-only, and a test asserts the operator-command exclusion while keeping `/help`, `/privacy` and `/feedback` present.

## CI verification — 10 November 2026

Latest CI snapshot: branch head `d9b4c1b6a5458ed22242129c469d059a570bc023`.

- [TypeScript bot checks](https://github.com/Kyerstorm/Lemegeton/actions/runs/42803020600) — **passed** (type-check and test job).
- [Dashboard security and backend checks](https://github.com/Kyerstorm/Lemegeton/actions/runs/42803020782) — running when this audit snapshot was written; do not treat it as passed until GitHub reports success.

Even when both workflows pass, CI does not prove live Discord permissions, third-party credentials, S3 deletion recovery or target-PostgreSQL migration/restore.

The audit distinguishes source inventory from selected-feature parity. The previous Twitch/trending status rotator, generic webhook monitoring and stale-user cleanup are not implemented. The bot currently retains guild data on `GuildDelete`; whether to delete it requires an explicit data-retention decision. No destructive cleanup is added without that decision.
## What source-to-TypeScript migration completion means

1. Every in-scope feature behavior selected from the Python source tree is implemented in the v3 TypeScript runtime or its retained Rust/dashboard boundary.
2. The behavior is mapped to the approved compact command surface; the previous command count is not copied one-for-one.
3. Guild scoping, permissions, provider attribution, storage semantics, and privacy are preserved.
4. Every meaningful source test scenario for an in-scope feature is ported or superseded by a focused TypeScript test. Test harnesses, fixtures, and maintenance scripts receive a deliberate disposition.
5. Backup, experimental, broken, unsupported, and out-of-scope code is recorded as excluded rather than silently called “migrated.”
6. PostgreSQL schema compatibility, any explicitly required data import, scheduled work, startup/shutdown, and recovery have implementation and test evidence.
7. Source parity does not itself authorize deployment. First deployment and rollback remain a separate, owner-approved release activity.

## Command and runtime parity register

| Python reference source | v3 destination | Current evidence | Remaining parity work |
|---|---|---|---|
| `bot.py` | `bot.ts`, `helpers/runtime/config.ts`, logger, security and service helpers | TypeScript gateway runtime, guild-only interaction routing, command dispatch, issue diagnostics, Atlas bridge, Daily Drop and Reading Club delivery, Media Night result delivery, retryable release-digest scheduling and tracked shutdown for Custom Role reconciliation/daily-worker timers exist. Shutdown clears timers, waits for an active daily-worker pass, stops listeners/schedulers and closes PostgreSQL. | Python cog hot-reload, stale-user cleanup, the previous Twitch/trending status rotator and generic webhook monitors are not ported. Guild data is retained on `GuildDelete` pending an explicit retention decision. Verify gateway intents, channel permissions and scheduled-worker recovery with live Discord/PostgreSQL acceptance. |
| `config.py` | `helpers/runtime/config.ts` and service-specific environment readers | Typed environment parsing and Node-native `.env.example` parsing in CI exist. Tests cover required credentials, safe defaults, moderator guild ID, paired IGDB credentials, HTTPS-only URLs, loopback-only listeners and `CUSTOM_ROLES_RECONCILE_MINUTES`. The runtime now honors the configured Custom Role reconciliation interval. | The previous environment surface is intentionally not one-for-one. HLTB, cog watch, Twitch status, generic AI, unused webhook and old cleanup settings need consumer-by-consumer disposition. Do not reintroduce unused settings; verify actual Node/Rust deployment consumers before editing `.env.example`. |
| `database.py` | `database.ts` plus domain-specific helpers | The existing multi_guild source database layer is PostgreSQL, not SQLite. The v3 schema creates its feature tables transactionally and retains users, steam_users, bot_moderators and Custom Role tables. Startup widens existing booster_roles snowflakes to BIGINT and backfills missing steam_users.guild_id to the configured/default guild before enforcing a (discord_id, guild_id) primary key. The initializer does not drop tables that are outside the current v3 feature scope. | The table-name comparison found 38 source table definitions and 49 v3 definitions, with only eight identically named tables. Tables used only by news/free-game/challenge/progress/invite/analytics features have not been imported; several are intentionally out of scope, and the initializer leaves source-only tables untouched. Verify table/column/index compatibility against the repository schema and the intended deployment schema, with data counts and backup/restore checks if an import is required. No live target database was available for this audit. |
| Media browse/recommend/random/trending | `/discover`, AniList/Steam/IGDB/Books/TMDB helpers | Category search, filters, trending, random, recommendation buttons and supported provider views exist. Exact-title cross-provider Atlas matches are separately labelled as unverified rather than confirmed adaptations. | Complete provider-fixture coverage for all categories, filters, pagination and failure behavior; verify third-party responses against live services. |
| `cogs/media/airing.py`, `trailer.py`, `tv_guide.py` | `/discover` and `/community` | AniList airing supports title, season/year, UTC weekday and a validated 1–14 day window; results are future-only, sorted and paginated in an owner-scoped `/discover` session. Discord renders local time with explicit UTC context. The TMDB TV Guide resolves exact series, exposes season metadata and paginates spoiler-marked episode details. | Verify AniList filters and release times against live responses, including date boundaries and provider outages. Trailer/provider fixture coverage exists; live-service acceptance remains open. |
| `cogs/media/compare.py` | `/discover` comparison | The compare flow accepts two to four entries across anime, manga, light novels, books, movies, TV and games. It lets the user select each exact provider result and keeps source/provider attribution; missing data is not inferred. | Validate provider failures and compare-field quality against live provider fixtures. Webnovel is excluded because the source implementation relies on unverified scraping. |
| `cogs/media/connected_media.py` | `/discover`, Knowledge Atlas, Archive and Community links | Creator exploration and Atlas relationships exist. TMDB regional watch-provider lookup and supported YouTube/Vimeo video listing are integrated into `/discover`, with exact-title selection. The server's default media region now persists through `/settings`; `/discover` accepts a per-request region override. | Guild-scoped relationship suggestion/review is now integrated into `/discover`; submissions require distinct titles, supported categories, HTTPS links and evidence, and moderators with Manage Server or Manage Messages can list, inspect, approve or reject them. Approval adds a guild-only community-sourced Atlas edge. `/community` already creates spoiler-aware threads, saves the thread ID, and closes/archives threads with creator-or-manager authorization. Creator search routes to TMDB person credits for films/TV and Google Books `inauthor:` results for books; AniList creator search remains for anime/manga/light novels. Collection guides use exact TMDB movie selection and date-ordered collection membership. The TV Guide now resolves exact series, displays show status, creators, networks, season/episode counts and runtimes, lets users select seasons, and paginates spoiler-marked episode summaries. Reading-order parity still needs a provider-backed sequencing rule; webnovel live updates remain excluded because the previous Python implementation is a scraper rather than a verified official API. |
| `cogs/media/cross_media_recommendations.py` | `/discover` | AniList recommendations, IGDB similar games and the existing cross-media candidate ranking helpers have dedicated tests for normalization, explanations and provider-failure isolation. Exact-title cross-provider Atlas entries are visibly marked unverified. | Complete end-to-end provider acceptance for books/TMDB/game candidates, ranking quality and source metadata. Do not label title matches as verified adaptations. |
| `cogs/media/franchise.py` | `/discover` and Knowledge Atlas | Atlas stores typed provider, recommendation and guild-scoped community edges. AniList relation details retain status and full start dates; TMDB collection membership is indexed. Exact-title cross-provider matches are explicitly unverified. AniList/TMDB release order appears only when every required date is complete and is labelled “not story chronology.” Tests cover ordering and relation metadata. | The view is a bounded direct-relationship snapshot, not an inferred transitive franchise tree. Validate live provider joins and duplicate behavior; no sequel/adaptation is inferred from title similarity alone. |
| `cogs/media/three_by_three.py` | `helpers/media/media-grid.ts`, `/discover`, tests | `/discover` grid keeps the nine-title flow and also accepts exactly nine same-type provider URLs: AniList anime/manga/character IDs or IGDB game slugs. Unsafe, mixed and untrusted URLs are rejected; exact IDs are resolved rather than substituting fuzzy search results. Image downloads remain bounded and missing covers use placeholders. | Verify layout and provider cover behavior with live source data. The previous persistent cover cache was not reproduced; current code does not claim cached results. |
| `cogs/media/community_archives.py`, `panel.py` | `/archive` | Unified Archive categories, server/global scope, uploads, collections, collaborators and Archive Trails exist. Pending-entry lookup defaults to the current server only; global lookup is explicit and global deletion requires a configured global moderator. Approved-entry removal through reports now supports the approved state; status changes and moderation-log inserts run in one PostgreSQL transaction, and report actioning follows successful removal. Focused tests cover lookup scopes and moderation-state eligibility. | The private S3 lifecycle now queues asset cleanup in the same PostgreSQL transaction as entry deletion, attempts deletion immediately, and retries failures from the existing worker with capped exponential backoff; queued assets are checked for remaining Archive references before object removal. Remaining acceptance: inject S3 failures and verify retry/recovery, and test full panel CRUD, pagination, attachments, categories, moderator review and cross-guild isolation against PostgreSQL. Preserve Panels as an Archive category, not a separate command. |
| `cogs/media/reading_club.py` | `/community` plus `helpers/community/community-reading.ts` | Guild-scoped nominations for manga/manhwa/manhua/webtoon/light novels/webnovels/books; one active vote per member with vote changes; manager selection by vote count (earliest nomination breaks ties) or explicit nomination; selected-read thread scheduling with future timezone-aware timestamps; persistent due-time notices with a five-minute retry window. No individual reading progress is stored. | Verify PostgreSQL migration/recovery and live Discord thread permissions. Previous reading-order exploration is intentionally not guessed; connect it to verified provider relationship edges only when sequence semantics are explicit. |
| `cogs/media/media_night.py` | `/community` Media Night | AniList candidates are provider-backed and adult-flagged entries are excluded; mood matching uses provider genres/tags; unbiased random sampling selects distinct entries; session and candidate rows persist in PostgreSQL; public buttons use database candidate IDs; one vote per member is locked; expired sessions close and final results are published through a retryable worker. | Run end-to-end Discord/PostgreSQL acceptance, verify candidate-tag behavior against live AniList responses, and keep the UI explicit that tag filtering is not an age rating. No adult-content recommendations or gambling are ported. |
| `cogs/media/release_calendar.py` | `/community` release calendar and guild digest worker | On-demand previews combine AniList airings, region-aware TMDB movie dates and TMDB next-episode dates with season/episode metadata. PostgreSQL stores per-guild channel, timezone, daily/weekly cadence, weekday, categories, region and next run; managers can preview, configure and disable; the bot queues due deliveries and retries failures. | Run end-to-end Discord/PostgreSQL acceptance, verify the TMDB `/tv/on_the_air` detail coverage and selected region behavior, and exercise schedule recovery after downtime. Release dates remain provider-sourced rather than inferred. |
| `cogs/gaming/game.py`, Steam modules | `/discover`, `/profile`, `/play` | Steam and IGDB helpers, game discovery, similar games, linked Steam profile and quiz sessions exist. | Verify all supported Steam profile/store fields, game recommendation behavior, pagination and safe provider failure. |
| `cogs/gaming/free_games_checker.py` | No current v3 destination | Explicitly excluded in the v3 specification because the previous implementation relies on storefront parsing/undocumented interfaces. | Do not port the scraper. Reconsider only if a stable, permitted promotions API is verified. |
| Custom-role cogs and helpers | `/custom-role`, `helpers/custom-roles/*` | TypeScript lifecycle, validation, image/picker and storage helpers exist. Picker-link capacity, token scope, replacement, idle/absolute expiry, read/write throttling, PNG/JPEG/crop safety, palette extraction, mass-archive threshold parsing and configured reconciliation interval now have focused tests. | Complete Discord/PostgreSQL lifecycle acceptance for role ownership, guild boundaries, cooldowns, role hierarchy, rollback and image persistence. Live picker proxy/permissions remain unverified. |
| `cogs/admin/dashboard.py`, dashboard frontend | `/settings`, Next.js frontend, Rust/Axum backend | A TS bot bridge and authenticated Atlas dashboard path exist. | Verify all in-scope guild configuration, channel selectors, feature visibility, authorization and audit behavior. Dashboard sync now filters `/log`, `/moderators` and `/planned` out of global command publication and keeps every published feature command restricted to guild context. `/help`, `/privacy` and `/feedback` remain separate standalone commands. Preserve the Rust trust boundary. |
| `cogs/server_management/server_check.py`, selected `server_config.py` behavior | `/settings` diagnostics | Some setting and channel controls exist. | Port only diagnostics/configuration needed by approved v3 features; prove channel permission checks and server isolation. General server administration is not an automatic migration target. |
| `cogs/admin/bot_moderators.py`, `utils/bot_monitoring.py`, `utils/monitoring_system.py` | Standalone `/log`, `/moderators`, `/planned`, runtime health and authorized diagnostics | The three bot-moderator commands remain independent, are omitted from global registration, register only to `BOT_MODERATOR_GUILD_ID`, and check both guild and moderator authorization on command/component interactions. `/log` uses the globally unique issue hash from that operations server so moderators can inspect errors raised in other guilds; `/feedback` still verifies a submitted issue hash against the originating guild. `/moderators` is the public command name. | Verify access controls and diagnostic redaction with live Discord permissions; structured health metrics and operational alerting still require parity acceptance. Never expose operator data to ordinary guild members. |
| Social/profile cogs | `/profile`, `helpers/runtime/profile.ts` | AniList/Steam linking, per-guild visibility preferences, opt-in affinity, minimum-three-member aggregate taste and leaderboard controls exist. Linking preserves existing display preferences; unlinking clears the provider identifier from the guild-scoped record. Neither integration stores member OAuth tokens. | Add PostgreSQL-backed tests for link/unlink and consent changes; confirm export/deletion policy and validate provider freshness. Individual anime/manga progress, milestones and completion tracking remain out of scope. |
| Utilities: help/privacy/feedback | Separate `/help`, `/privacy`, `/feedback` modules | All three remain independent command modules. `/log` and `/feedback` use the documented 40-character lowercase hexadecimal SHA-512-derived issue reference; the generator, database constraint, input validation and tests preserve the same contract. Guild-only interaction policy and consent handling have focused coverage. | Validate first-run consent, issue lookup/redaction and feedback delivery against a configured PostgreSQL database and live Discord permissions. Keep these commands separate. |
| Other utility commands | Existing TS modules include invite, link conversion and timestamp | Implementations exist in the Draft branch. | Reconcile them against the approved public surface and existing user decisions; do not expand into an unrelated utility collection. |
| Bot-moderator operations | `/log`, `/moderators`, and `/planned` remain independent standalone command modules | Diagnostic lookup, bot moderator management, and planned-feature management modules exist. | Keep all three commands separate, bot-moderator-only, and guild-registered exclusively to the one `BOT_MODERATOR_GUILD_ID`. Guard every command and component interaction at runtime. The deployed command name in this branch is `/moderators`; do not reintroduce `/adminmoderators` or register operator commands globally. |

## Python reference files outside the selected v3 scope

The base source tree also contains backup, under-maintenance, test, and helper files. They are reviewed for useful behavior, but their presence alone does not make them part of the v3 product scope.

- `backup/bot.py`, `backup/hltb.py`, `backup/metacritic.py`: backup artifacts, not selected v3 features.
- `under_maintenance/challenges/challenge_progress.py`: personal AniList manga progress behavior conflicts with the explicit no-personal-progress rule.
- `under_maintenance/reminders.py`: general reminders conflict with the media-only automation scope.
- `under_maintenance/challenges/challenge_manage.py` and `challenge_leaderboard.py`: inspect whether any community-only challenge behavior is still wanted; do not reintroduce personal progress tracking.
- Theme/decor files: a general theme system or marketplace is explicitly outside the current approved scope. Custom Roles remain in scope.
- Free-game/news/web-scraping code: only reconsider when an official, stable, terms-compliant provider source is established.
- Invite tracking, generic server analytics, generic admin cleanup and broad moderation backups are not automatically in the selected v3 scope.
- Temporary scripts and migration helpers are kept only when they still serve a necessary development, release, or data-migration task; otherwise document why they are not part of v3.
- Tests and fixtures are not runtime features. Port the assertions that protect selected v3 behavior into TypeScript tests; document excluded scenarios without requiring a matching number of test files.

## Integration and environment-dependent acceptance

- GitHub's branch comparison reports `lemegeton-v3` as diverged from `multi_guild`: **501 commits ahead, 86 commits behind**, merge base `e7c7c99728fc71c30a9bff65d5eed194ae8ffaf1`. PR #17 currently reports `mergeable=false` / `mergeable_state=dirty`. No synchronization or conflict resolution was attempted in this audit; resolve deliberately on the PR branch only, preserving the base branch and all work from both sides.
- No live Discord test server/application credentials were available for gateway-intent, channel-permission, component-authorization, command-registration, thread and scheduled-delivery acceptance.
- No target PostgreSQL instance or sanitized target schema/data snapshot was available. CI verifies Rust/TypeScript builds and tests, not real source-to-target data import, restore, or rollback.
- Guild departure currently retains guild-owned records. Whether a future guild removal should retain or purge those records is an owner/privacy decision; no destructive cleanup is inferred.
- Interactive release-calendar previews use independent provider requests and retain successful provider results when another selected provider fails; `/community` names unavailable providers and makes clear that the remaining results are partial. Tests cover one-provider failure and the all-selected-providers-unavailable case. Scheduled release digests deliberately use stricter delivery semantics: if any selected provider is unavailable, the digest is not sent or marked complete and the delivery remains queued for retry. Verify this retry behavior against PostgreSQL and a live Discord test channel.

## Required TypeScript coverage

The source tree has fifty Python test modules under `tests/`; the current Draft snapshot has thirty-two TypeScript test modules. The target is not fifty matching files. The target is focused coverage for every selected v3 behavior, especially:

- AniList/Steam/IGDB/TMDB/Google Books normalization, empty responses, timeouts, rate limits, and malformed payloads.
- Media search/filter/random/recommendation/compare/trailer/airing/creator/franchise flows.
- Archive submission, permissions, S3 assets, global/server visibility, collections, trails, moderation, edit/delete and attachment cleanup.
- Guild isolation for settings, activities, rankings, sessions, notifications and graph data.
- Custom-role lifecycle, picker, image fetching, permissions, role hierarchy, cooldown and existing data import.
- Dashboard OAuth, Rust bridge authentication, guild authorization and channel permissions.
- Terms/privacy, issue hash creation, feedback/log authorization, diagnostic redaction and interaction error handling.
- Database transaction behavior, migration compatibility, backup/restore and shutdown/job recovery.
- Docker startup, process supervision, health checks, signals and restart behavior.

## Exact source inventory (167 files on `multi_guild`)

### Runtime, configuration, database and provider code

```text
bot.py
config.py
database.py
verify_pg.py
helpers/__init__.py
helpers/anilist_helper.py
helpers/cache_helper.py
helpers/challenge_helper.py
helpers/color_palette.py
helpers/command_error_handler.py
helpers/command_logger.py
helpers/crypto_random.py
helpers/custom_roles/__init__.py
helpers/custom_roles/images.py
helpers/custom_roles/safe_fetch.py
helpers/custom_roles/service.py
helpers/custom_roles/storage.py
helpers/custom_roles/tokens.py
helpers/custom_roles/validation.py
helpers/embed_helper.py
helpers/gaming_utils.py
helpers/igdb_helper.py
helpers/logging_helper.py
helpers/media_graph.py
helpers/media_helper.py
helpers/media_storage.py
helpers/profile_helper.py
helpers/repo_stats.py
helpers/steam_helper.py
helpers/terms_consent.py
helpers/text_helper.py
helpers/theme_helper.py
helpers/tmdb_discovery.py
helpers/utility_helper.py
helpers/web_scraper.py
utils/bot_monitoring.py
utils/monitoring_system.py
```

### Previous cogs (63 files)

```text
cogs/account/__init__.py
cogs/account/admin_login.py
cogs/admin/__init__.py
cogs/admin/bot_moderators.py
cogs/admin/dashboard.py
cogs/admin/github_tracker.py
cogs/admin/user_cleanup.py
cogs/customization/__init__.py
cogs/customization/custom_roles.py
cogs/customization/decor.py
cogs/customization/theme_integration.py
cogs/customization/theme_showcase.py
cogs/customization/themes.py
cogs/gaming/__init__.py
cogs/gaming/free_games_checker.py
cogs/gaming/game.py
cogs/gaming/steam_game.py
cogs/gaming/steam_profile.py
cogs/gaming/steam_recommendation.py
cogs/media/__init__.py
cogs/media/airing.py
cogs/media/animanga_completion_checker.py
cogs/media/browse.py
cogs/media/community_archives.py
cogs/media/compare.py
cogs/media/connected_media.py
cogs/media/cross_media_recommendations.py
cogs/media/discovery_hub.py
cogs/media/franchise.py
cogs/media/library_backup.py
cogs/media/media_night.py
cogs/media/news.py
cogs/media/panel.py
cogs/media/random.py
cogs/media/reading_club.py
cogs/media/recommendations.py
cogs/media/release_calendar.py
cogs/media/three_by_three.py
cogs/media/trailer.py
cogs/media/trending.py
cogs/media/tv_guide.py
cogs/server_management/__init__.py
cogs/server_management/invite_tracker.py
cogs/server_management/server_check.py
cogs/server_management/server_config.py
cogs/server_management/welcome_dm.py
cogs/server_management/welcome_message.py
cogs/social/__init__.py
cogs/social/affinity.py
cogs/social/anilist_leaderboard.py
cogs/social/anilist_site_embed.py
cogs/social/feedback.py
cogs/social/lolilist.py
cogs/social/social_embed.py
cogs/utilities/__init__.py
cogs/utilities/convertlinks.py
cogs/utilities/help.py
cogs/utilities/invite.py
cogs/utilities/notifications.py
cogs/utilities/planned_features.py
cogs/utilities/privacy.py
cogs/utilities/say.py
cogs/utilities/timestamp.py
```

### Backups and maintenance-only modules (7 files)

```text
backup/bot.py
backup/hltb.py
backup/metacritic.py
under_maintenance/challenges/challenge_leaderboard.py
under_maintenance/challenges/challenge_manage.py
under_maintenance/challenges/challenge_progress.py
under_maintenance/reminders.py
```

### Automation and scripts (10 files: one repository workflow helper plus nine scripts)

```text
.github/scripts/repository_health.py
scripts/.tmp_inspect_helpers.py
scripts/.tmp_invite_leave_test.py
scripts/.tmp_invite_smoke_test.py
scripts/.tmp_profile_view_test.py
scripts/.tmp_smoke_tests.py
scripts/convert_to_async.py
scripts/migrate_news_data.py
scripts/migrate_news_db.py
scripts/test_import_cogs.py
```

### Tests and fixtures (50 files)

```text
tests/custom_roles/_safety.py
tests/custom_roles/fakes.py
tests/custom_roles/make_test_images.py
tests/custom_roles/run_all.py
tests/custom_roles/seed_test_server.py
tests/custom_roles/test_admin_extras.py
tests/custom_roles/test_enable_gate.py
tests/custom_roles/test_previous_import.py
tests/custom_roles/test_lifecycle.py
tests/custom_roles/test_names_and_roles.py
tests/custom_roles/test_palette_and_icons.py
tests/custom_roles/test_panels.py
tests/custom_roles/test_picker_disabled.py
tests/custom_roles/test_picker_edit.py
tests/custom_roles/test_picker_icon.py
tests/custom_roles/test_picker_web.py
tests/custom_roles/test_setup_fixes.py
tests/test_anilist_site_embed.py
tests/test_browse_filters.py
tests/test_browse_provider_search.py
tests/test_command_error_handler.py
tests/test_command_error_handler_coverage.py
tests/test_community_archives.py
tests/test_compare_helpers.py
tests/test_connected_media.py
tests/test_cross_media_recommendations.py
tests/test_custom_role_picker_server.py
tests/test_dashboard_assets.py
tests/test_dashboard_bridge.py
tests/test_dashboard_command_policy.py
tests/test_franchise_helpers.py
tests/test_github_tracker.py
tests/test_media_discovery_helpers.py
tests/test_media_graph.py
tests/test_media_night_filters.py
tests/test_media_storage.py
tests/test_new_media_commands.py
tests/test_novelupdates_scraper.py
tests/test_panel_command.py
tests/test_privacy_command.py
tests/test_privacy_hardening.py
tests/test_rate_limit_memory.py
tests/test_reading_club.py
tests/test_release_calendar.py
tests/test_repo_stats.py
tests/test_repository_integrity.py
tests/test_screen_discovery.py
tests/test_terms_consent.py
tests/test_tv_guide.py
tests/test_web_scraper.py
```

> Count note: the file inventory above is grouped by purpose. Package marker files, scripts, tests, backups and under-maintenance modules are counted in the total; the count is from the base Git tree, not a guessed count from the PR diff display.

## Exit gate

Do not mark source migration complete until each in-scope row above has implementation/test evidence, the Python reference test scenarios relevant to selected v3 features have explicit dispositions, CI passes on the current Draft head, multi-guild isolation and schema compatibility are proven, and startup/shutdown/recovery are covered. This audit does not assert that a previous bot was deployed and does not authorize a production release. The PR remains Draft until the repository owner explicitly says otherwise.

# Lemegeton v3 — Python-to-TypeScript parity audit

**Target:** existing Draft PR #17, branch `lemegeton-v3`  
**Base under audit:** `multi_guild`  
**Audit basis:** current Git trees, PR diff, the v3 command modules, and targeted source inspection.  
**Status:** inventory completed; behavior parity is **not** complete or accepted.

## Executive result

The Draft branch currently has **zero Python files**. That is a file-extension result, not proof that the removed Python behavior has all been rebuilt.

| Snapshot | Python files | TypeScript/TSX files | TypeScript non-test files | TypeScript test files |
|---|---:|---:|---:|---:|
| `multi_guild` base | 167 | 0 | 0 | 0 |
| `lemegeton-v3` Draft head after connected-media parity work | 0 | 84 | 70 | 14 |

The base's 167 Python files total approximately 3.68 MB. The Draft head has twelve TypeScript test files, compared with fifty Python files under the base's `tests/` directory. This is a substantial regression-coverage gap until each relevant legacy test has either been ported, replaced by equivalent coverage, or explicitly retired with a reason.

The Draft branch already has a Node.js/TypeScript bot startup path, a TypeScript build/test pipeline, and a Rust dashboard service. The current `scripts/start.sh`, Dockerfile, Compose configuration, and TypeScript CI workflows do not invoke Python. Do not describe the production bot as cut over merely because this branch's startup path is TypeScript.

## What “all Python files migrated” means

1. Every in-scope, production behavior from the base is implemented in the v3 TypeScript runtime or its retained Rust/dashboard boundary.
2. The behavior is mapped to the approved compact command surface; legacy command count is not copied one-for-one.
3. Guild scoping, permissions, provider attribution, storage semantics, and privacy are preserved.
4. Every meaningful legacy test is ported or superseded by a focused TypeScript test. Test harnesses, fixtures, and maintenance scripts receive a deliberate disposition.
5. Backup, experimental, broken, unsupported, and out-of-scope code is recorded as excluded rather than silently called “migrated.”
6. PostgreSQL compatibility, existing data, scheduled work, deployment, rollback, and cutover have explicit evidence.
7. Only after those checks pass can the old Python runtime be considered retired.

## Command and runtime parity register

| Legacy source | v3 destination | Current evidence | Remaining parity work |
|---|---|---|---|
| `bot.py` | `bot.ts`, `helpers/config.ts`, logger, security and service helpers | TypeScript gateway runtime, guild-only interaction routing, command dispatch, issue diagnostics, Atlas bridge, and daily delivery loop exist. | Complete lifecycle parity for cog loading equivalents, stale-user/left-guild cleanup, status updates, monitoring hooks, bridge endpoints, graceful shutdown and every scheduled job. Verify intents and permission behavior against production. |
| `config.py` | `helpers/config.ts` | Typed environment parsing exists. | Compare every active legacy setting, default, validation rule and deployment consumer; remove obsolete values only after confirming no caller needs them. |
| `database.py` | `database.ts` plus domain-specific helpers | PostgreSQL pool/query/transaction foundation and multiple v3 data services exist. | Audit all legacy tables, indexes, constraints, ID-width assumptions, JSON columns, data ownership, import paths and rollback. Prove existing data survives deployment. |
| Media browse/recommend/random/trending | `/discover`, AniList/Steam/IGDB/Books/TMDB helpers | Category search, filters, trending, random, recommendation buttons and supported provider views exist. | Test all supported categories and legacy filter behavior; restore only stable provider-backed fields and ensure recommendations are labelled by provenance. |
| `cogs/media/airing.py`, `trailer.py`, `tv_guide.py` | `/discover` and `/community` | AniList airing/trailer fields and TMDB film/TV search exist. | Full season/episode detail, pagination, time-zone display, fallback behavior and provider response edge cases are not yet evidenced as parity-complete. |
| `cogs/media/compare.py` | `/discover` comparison | A second-title comparison option exists. | Verify parity for supported media types, missing fields, IGDB/Steam comparison, normalization and provenance. |
| `cogs/media/connected_media.py` | `/discover`, Knowledge Atlas, Archive and Community links | Creator exploration and Atlas relationships exist. TMDB regional watch-provider lookup and supported YouTube/Vimeo video listing are integrated into `/discover`, with exact-title selection. The server's default media region now persists through `/settings`; `/discover` accepts a per-request region override. | Guild-scoped relationship suggestion/review is now integrated into `/discover`; submissions require distinct titles, supported categories, HTTPS links and evidence, and moderators with Manage Server or Manage Messages can list, inspect, approve or reject them. Approval adds a guild-only community-sourced Atlas edge. `/community` already creates spoiler-aware threads, saves the thread ID, and closes/archives threads with creator-or-manager authorization. Creator search routes to TMDB person credits for films/TV and Google Books `inauthor:` results for books; AniList creator search remains for anime/manga/light novels. Collection guides use exact TMDB movie selection and date-ordered collection membership. Reading-order parity still needs a provider-backed sequencing rule; webnovel live updates remain excluded because the legacy source is a scraper rather than a verified official API. |
| `cogs/media/cross_media_recommendations.py` | `/discover` | AniList recommendations and IGDB similar games exist. | Verify cross-category candidate pools, local-match explanations, books/TMDB support and provider failure isolation. |
| `cogs/media/franchise.py` | `/discover` and Knowledge Atlas | Atlas supports typed, sourced relationships and bounded graph views. | Verify franchise traversal, sequencing, relationship labels, cross-provider joins, duplicate handling and community links. |
| `cogs/media/three_by_three.py` | `helpers/media-grid.ts`, `/discover`, tests | Nine-title parsing, safe image-host allowlist, bounded image downloads, placeholder covers and PNG generation exist. | Compare input flow, title resolution, IGDB cover lookup, cache semantics, failure messages and image layout. The helper is a port candidate, not proof of full UX parity. |
| `cogs/media/community_archives.py`, `panel.py` | `/archive` | Unified Archive categories, server/global scope, uploads, collections, collaborators and Archive Trails exist. | Confirm legacy panel CRUD, pagination, attachment lifecycle, all categories, moderator review, cleanup and S3 privacy; preserve Panels as an Archive category, not a separate command. |
| `cogs/media/media_night.py`, `reading_club.py` | `/community` | Daily activities, sessions, RSVP/waitlist and spoiler-aware discussions exist. | Port only community event behavior: nominations, candidate selection, schedules, voting, session state and expiry. Do not add member reading progress or personal media tracking. |
| `cogs/media/release_calendar.py` | `/community`, media notification services, `/settings` | Basic provider-dated anime/manga notification scanning, film/TV metadata and a community calendar foundation exist. | Per-title subscriptions, richer release kinds, guild digests, timezone scheduling, delivery retry/idempotency and complete legacy calendar filters remain outstanding. |
| `cogs/gaming/game.py`, Steam modules | `/discover`, `/profile`, `/play` | Steam and IGDB helpers, game discovery, similar games, linked Steam profile and quiz sessions exist. | Verify all supported Steam profile/store fields, game recommendation behavior, pagination and safe provider failure. |
| `cogs/gaming/free_games_checker.py` | No current v3 destination | Explicitly excluded in the v3 specification because the legacy implementation relies on storefront parsing/undocumented interfaces. | Do not port the scraper. Reconsider only if a stable, permitted promotions API is verified. |
| Custom-role cogs and helpers | `/custom-role`, `helpers/custom-role-*` | TypeScript lifecycle, validation, image/picker and storage helpers exist. | Port and run the complete lifecycle/picker/admin regression suite; verify ownership, guild boundaries, cooldowns, role hierarchy, asset validation and rollback. |
| `cogs/admin/dashboard.py`, dashboard frontend | `/settings`, Next.js frontend, Rust/Axum backend | A TS bot bridge and authenticated Atlas dashboard path exist. | Verify all in-scope guild configuration, channel selectors, feature visibility, authorization and audit behavior. Preserve the Rust trust boundary. |
| `cogs/server_management/server_check.py`, selected `server_config.py` behavior | `/settings` diagnostics | Some setting and channel controls exist. | Port only diagnostics/configuration needed by approved v3 features; prove channel permission checks and server isolation. General server administration is not an automatic migration target. |
| `cogs/admin/bot_moderators.py`, `utils/bot_monitoring.py`, `utils/monitoring_system.py` | `/moderators`, `/log`, runtime health and authorized diagnostics | Moderator and issue-hash flows exist. | Verify access checks, structured health metrics, operational alerting and sensitive diagnostic redaction; do not expose operator data to ordinary guild members. |
| Social/profile cogs | `/profile`, `helpers/profile.ts` | AniList/Steam linking, visibility controls, affinity, aggregate taste and leaderboard paths exist. | Verify unlink/consent revocation, token lifecycle, privacy defaults, aggregate minimum thresholds and source freshness. |
| Utilities: help/privacy/feedback | Separate `/help`, `/privacy`, `/feedback` modules | All three have independent command modules and are in the registry separately. | Keep them as standalone commands; test first-run consent, privacy accuracy, feedback issue-hash validation and guild-only policy. Never merge these into a metropolis command. |
| Other utility commands | Existing TS modules include invite, link conversion and timestamp | Implementations exist in the Draft branch. | Reconcile them against the approved public surface and existing user decisions; do not expand into an unrelated utility collection. |
| Generic planned-feature voting | `src/planned.ts` currently exists | Code is present in the Draft head. | This conflicts with the v3 spec's exclusion of a generic voting backlog. Record this discrepancy for a deliberate product decision; do not silently claim it is an approved core feature. |

## Legacy files that are not automatic production migrations

The base tree contains backup, under-maintenance, test, and helper files. They must be audited, but a Python file does not become an approved runtime feature just because it existed.

- `backup/bot.py`, `backup/hltb.py`, `backup/metacritic.py`: historical backup scripts, not production bot cogs.
- `under_maintenance/challenges/challenge_progress.py`: personal AniList manga progress behavior conflicts with the explicit no-personal-progress rule.
- `under_maintenance/reminders.py`: general reminders conflict with the media-only automation scope.
- `under_maintenance/challenges/challenge_manage.py` and `challenge_leaderboard.py`: inspect whether any community-only challenge behavior is still wanted; do not reintroduce personal progress tracking.
- Theme/decor files: a general theme system or marketplace is explicitly outside the current approved scope. Custom Roles remain in scope.
- Free-game/news/web-scraping code: only reconsider when an official, stable, terms-compliant provider source is established.
- Invite tracking, generic server analytics, generic admin cleanup and broad moderation backups are not automatically in the selected v3 scope.
- Temporary scripts and migration helpers must be converted only when they still serve a necessary release/data migration task; otherwise document retirement.
- Tests and test fixtures are not runtime features. Their useful assertions and scenarios must be ported into TypeScript tests or explicitly retired with a reason.

## Required TypeScript test parity

The base has fifty Python test files under `tests/`; the Draft has twelve TypeScript test files. The target is not necessarily fifty files with identical names. The target is equivalent coverage for all retained behavior, especially:

- AniList/Steam/IGDB/TMDB/Google Books normalization, empty responses, timeouts, rate limits, and malformed payloads.
- Media search/filter/random/recommendation/compare/trailer/airing/creator/franchise flows.
- Archive submission, permissions, S3 assets, global/server visibility, collections, trails, moderation, edit/delete and attachment cleanup.
- Guild isolation for settings, activities, rankings, sessions, notifications and graph data.
- Custom-role lifecycle, picker, image fetching, permissions, role hierarchy, cooldown and legacy data import.
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

### Legacy cogs (63 files)

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
tests/custom_roles/test_legacy_import.py
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

Do not mark migration complete until the relevant rows above have implementation/test evidence, the 50 legacy Python test scenarios have explicit dispositions, CI passes on the current Draft head, multi-guild isolation and data compatibility are proven, and deployment/cutover is reversible. The PR remains Draft until the repository owner explicitly says otherwise.

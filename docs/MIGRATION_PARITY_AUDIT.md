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
| `lemegeton-v3` Draft head at `cdcfa08` (10 November 2026) | 0 | 111 | 78 | 33 |

The base's 167 Python files total approximately 3.68 MB. The current Draft head contains thirty-four TypeScript test modules; the `multi_guild` source tree contains fifty Python test modules. Module counts are not a coverage metric. The goal is to map each in-scope scenario to a focused TypeScript test or a documented reason it remains a live-service acceptance item, not to reproduce every file one-for-one.

The Draft branch already has a Node.js/TypeScript bot startup path, a TypeScript build/test pipeline, and a Rust dashboard service. The current `scripts/start.sh`, Dockerfile, Compose configuration, and TypeScript CI workflows do not invoke Python. A TypeScript startup path and passing branch CI are repository evidence only; they do not establish that any bot has been deployed.

## Focused migration follow-up — 10 November 2026

The current branch tree contains 178 tracked files: zero Python files, 111 TypeScript/TSX files (78 non-test files and 33 test modules). The count is a snapshot of the branch tree, not a statement of feature completeness.

The following verified follow-ups were made on the Draft branch after the initial audit snapshot:

- bot.ts now retains handles for the Custom Role reconciliation and daily-worker intervals, clears them during shutdown, and waits for an active daily-worker pass before closing the database pool.
- The /log and /feedback surfaces now share the fixed 40-character SHA-512-derived issue-reference contract documented in [ISSUE_REFERENCE_FORMAT.md](ISSUE_REFERENCE_FORMAT.md). Generator, PostgreSQL constraint, command input limits, and tests must remain aligned.
- Guild interaction failures, including consent/preflight checks, now enter the same issue-diagnostic boundary. User-triggered Archive upload and AniList embed message failures also persist a reference and return it to the user. A reference is only available when the diagnostic insert succeeds; database failure is logged separately and cannot produce a retrievable issue record.
- `tests/runtime-config.test.ts` covers security-sensitive defaults and validation, including the `CUSTOM_ROLES_RECONCILE_MINUTES` default and override. The bot now uses that typed setting instead of a hard-coded 30-minute reconciliation timer.
- Custom Role picker tokens now enforce the existing in-memory capacity bound; focused tests cover token uniqueness, per-guild/member scoping, replacement, idle and absolute expiry, and separate read/write rate limits.
- Custom Role image tests cover PNG/JPEG handling, crop bounds, source/output limits, malformed/HEIC rejection and palette extraction. Archive-threshold parsing tests preserve the documented default and zero floor.
- `/discover` restores AniList airing filters (title, season/year, weekday and bounded date window) with pagination and owner-scoped controls; `tests/anilist-airing.test.ts` covers the provider query and validation. Mixed-media comparison accepts two to four titles across supported categories and lets the user select exact provider results; `tests/media-comparison.test.ts` covers input validation. Webnovel scraping remains excluded.
- Google Books now has dedicated tests for query parameters, whitespace/subject validation, metadata normalization, ISBN extraction, HTTPS image URLs, malformed entries and provider failures; the subject sanitizer was corrected to collapse actual whitespace.
- The `/discover` 3×3 grid accepts exact AniList anime/manga/character URLs and IGDB game URLs while retaining the title-input mode; it rejects unsafe, mixed and untrusted links. `tests/media-grid.test.ts` covers URL parsing, provider allowlists and media-type consistency.
- Knowledge Atlas now includes TMDB collection membership, exact-title cross-provider matches explicitly labelled as unverified, and AniList/TMDB release order only where every required date is complete. Release order is expressly not story chronology.
- The dashboard CI job parses .env.example using Node's native env-file parser. Duplicate S3 variables and shell-style export lines were removed from the template, and its bridge-secret example was left empty rather than presenting a reusable credential.
- Dashboard command listing and sync now exclude `/log`, `/moderators` and `/planned`; the sync payload is guild-context-only, and a test asserts the operator-command exclusion while keeping `/help`, `/privacy` and `/feedback` present.

## CI verification — 10 November 2026

Latest CI snapshot: code-bearing branch head `cdcfa08b998654bb19da211975f712697ef69ec6`.

- [TypeScript bot checks](https://github.com/Kyerstorm/Lemegeton/actions/runs/42803939032) — **passed** (type-check and all 146 tests).
- [Dashboard security and backend checks](https://github.com/Kyerstorm/Lemegeton/actions/runs/42803938648) — running when this audit snapshot was written; do not treat it as passed until GitHub reports success.

Even when both workflows pass, CI does not prove live Discord permissions, third-party credentials, S3 deletion recovery or target-PostgreSQL migration/restore.

The audit distinguishes source inventory from selected-feature parity. The previous Twitch/trending status rotator, generic webhook monitoring and stale-user cleanup are not implemented. Guild departure now follows the per-server `delete` or `retain` choice in `guild_retention_settings`; normal functionality remains locked until the original inviter or a Manage Server member chooses.
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
| `bot.py` | `bot.ts`, `helpers/runtime/config.ts`, logger, security and service helpers | TypeScript gateway runtime, guild-only routing, interaction/message diagnostics, Atlas bridge, Daily Drop, Reading Club, Media Night, retryable release digest and media-notification scheduler are implemented. Custom Role and daily-worker timers are tracked and stopped at shutdown. Member departures immediately remove only that member’s guild-scoped AniList/Steam links and profile preferences; startup reconciliation repeats this only after Discord returns a complete member list. | Python cog hot-reload, Twitch/trending status rotation and generic webhook monitors are intentionally retired. **Guild-wide `GuildDelete` retention is now configurable per guild**: the original bot inviter or a member with Manage Server selects delete or retain before runtime functionality is enabled. When delete is chosen, guild-scoped database rows are removed transactionally and private objects use the existing retryable S3 cleanup queue. The retention choice survives departure. A transient unavailable-guild event does not trigger deletion. Live intents, channel permissions and scheduled-delivery recovery still require a real Discord/PostgreSQL acceptance run. |
| `config.py` | `helpers/runtime/config.ts` plus Rust dashboard configuration | Typed v3 settings cover Discord credentials/application ID (including legacy `CLIENT_ID` alias), feedback channel, Archive global moderators, admin/operator guild, PostgreSQL connection/TLS/pool, AniList, Steam, IGDB, Google Books, TMDB, private S3 storage, dashboard bridge/picker and Custom Roles. `CUSTOM_ROLES_RECONCILE_MINUTES`, mass-archive threshold, image limit and safe debug preview switches are consumed. `.env.example` now contains only v3 bot/Rust settings and its native env-file validation runs in dashboard CI. | Legacy MOD_ROLE_ID/guild_mod_roles, BOT_UPDATE_ROLE_ID/GitHub tracker, generic webhooks, Twitch/status/cog-watch settings, LLM credentials, generic API retry knobs, old cleanup intervals, challenge-role settings and MDBList are not consumed by the v3 runtime and are not silently reintroduced. Member cleanup is now event-driven plus guarded startup reconciliation. `CLIENT_ID` remains a tested compatibility alias; `DB_PATH`/`DATABASE_PATH` SQLite settings are retired because both source and v3 use PostgreSQL. |
| `database.py` | `database.ts` plus domain-specific helpers | Both source and v3 are PostgreSQL. The current source has 38 unique table definitions and v3 has 52; seven table names are shared (`users`, `steam_users`, `bot_moderators`, and four Custom Roles tables). Existing `users` rows are backfilled into guild scope while AniList fields are preserved; Steam guild IDs and composite keys are normalized; existing Custom Role/booster Discord snowflakes are widened to BIGINT. `media_assets` has a compatible field layout in both implementations. Idempotent imports now cover legacy Panels, their moderation-log channel/role, media brackets, adaptation polls, source-backed Media Quiz questions and per-guild AniManga completion channels. | The remaining 31 source-only tables are either explicitly retired feature data (progress/challenges, invite tracking, news/free-game scraping, `/say` logs, GitHub tracker) or unused legacy tables (`guild_mod_roles`, `custom_role_meta`). `booster_roles` remains a source for the existing Custom Role takeover/import flow and is not bulk-copied. Old per-user `user_stats`/`achievements` are not imported because v3 fetches current AniList data and derives non-persistent milestones; personal progress is out of scope. Tests run against PostgreSQL service containers and cover the described imports/repeatability, but no user-supplied target database or production snapshot has been tested. |
| Media browse/recommend/random/trending | `/discover`, AniList/Steam/IGDB/Books/TMDB helpers | Category search, filters, trending, random, recommendation buttons and supported provider views exist. AniList, IGDB, Steam and TMDB have focused provider tests; Google Books now has query, metadata, ISBN, URL, malformed-response and HTTP-failure fixtures. Exact-title cross-provider Atlas matches are separately labelled as unverified rather than confirmed adaptations. | Complete provider-fixture coverage for all categories, filters, pagination and failure behavior; verify third-party responses against live services. |
| `cogs/media/airing.py`, `trailer.py`, `tv_guide.py` | `/discover` and `/community` | AniList airing supports title, season/year, UTC weekday and a validated 1–14 day window; results are future-only, sorted and paginated in an owner-scoped `/discover` session. Discord renders local time with explicit UTC context. The TMDB TV Guide resolves exact series, exposes season metadata and paginates spoiler-marked episode details. | Verify AniList filters and release times against live responses, including date boundaries and provider outages. Trailer/provider fixture coverage exists; live-service acceptance remains open. |
| `cogs/media/compare.py` | `/discover` comparison | The compare flow accepts two to four entries across anime, manga, light novels, books, movies, TV and games. It lets the user select each exact provider result and keeps source/provider attribution; missing data is not inferred. | Validate provider failures and compare-field quality against live provider fixtures. Webnovel is excluded because the source implementation relies on unverified scraping. |
| `cogs/media/connected_media.py` | `/discover`, Knowledge Atlas, Archive and Community links | Creator exploration and Atlas relationships exist. TMDB regional watch-provider lookup and supported YouTube/Vimeo video listing are integrated into `/discover`, with exact-title selection. The server's default media region now persists through `/settings`; `/discover` accepts a per-request region override. | Guild-scoped relationship suggestion/review is now integrated into `/discover`; submissions require distinct titles, supported categories, HTTPS links and evidence, and moderators with Manage Server or Manage Messages can list, inspect, approve or reject them. Approval adds a guild-only community-sourced Atlas edge. `/community` already creates spoiler-aware threads, saves the thread ID, and closes/archives threads with creator-or-manager authorization. Creator search routes to TMDB person credits for films/TV and Google Books `inauthor:` results for books; AniList creator search remains for anime/manga/light novels. Collection guides use exact TMDB movie selection and date-ordered collection membership. The TV Guide now resolves exact series, displays show status, creators, networks, season/episode counts and runtimes, lets users select seasons, and paginates spoiler-marked episode summaries. The inspected source contains an internal `reading_order` helper but no registered public reading-order command or sequencing algorithm; v3 does not invent one. Webnovel live updates remain excluded because the previous Python implementation is a scraper rather than a verified official API. |
| `cogs/media/cross_media_recommendations.py` | `/discover` | AniList recommendations, IGDB similar games and the existing cross-media candidate ranking helpers have dedicated tests for normalization, explanations and provider-failure isolation. Exact-title cross-provider Atlas entries are visibly marked unverified. | Complete end-to-end provider acceptance for books/TMDB/game candidates, ranking quality and source metadata. Do not label title matches as verified adaptations. |
| `cogs/media/franchise.py` | `/discover` and Knowledge Atlas | Atlas stores typed provider, recommendation and guild-scoped community edges. AniList relation details retain status and full start dates; TMDB collection membership is indexed. Exact-title cross-provider matches are explicitly unverified. AniList/TMDB release order appears only when every required date is complete and is labelled “not story chronology.” Tests cover ordering and relation metadata. | The view is a bounded direct-relationship snapshot, not an inferred transitive franchise tree. Validate live provider joins and duplicate behavior; no sequel/adaptation is inferred from title similarity alone. |
| `cogs/media/three_by_three.py` | `helpers/media/media-grid.ts`, `/discover`, tests | `/discover` grid keeps the nine-title flow and also accepts exactly nine same-type provider URLs: AniList anime/manga/character IDs or IGDB game slugs. Unsafe, mixed and untrusted URLs are rejected; exact IDs are resolved rather than substituting fuzzy search results. Image downloads remain bounded and missing covers use placeholders. | Verify layout and provider cover behavior with live source data. The previous persistent cover cache was not reproduced; current code does not claim cached results. |
| `cogs/media/community_archives.py`, `panel.py` | `/archive` | Unified Archive categories, server/global visibility, uploads, collections, collaborators, Trails and moderation exist. Existing `panels` rows and tags import idempotently into the Panels category; safe entries retain source/media/attachment metadata, NSFW rows remain in the source table, and old rows are never deleted. Panel moderation-log channel and role migrate into Archive settings and are used by review authorization. Panel of the Day selects one approved, non-spoiler, image-backed entry per guild/day while respecting server/global visibility. | Private S3 cleanup is queued transactionally and retried with capped backoff. **Legacy `panel_storage_channel_id` is not mapped to `upload_channel_id`**: the former was private bot-managed object storage; the latter is member-facing intake. Deployments relying on the Discord storage-channel fallback still need configured private S3 or an explicitly approved storage replacement. Inject S3 failures and verify recovery; live Discord channel permissions and cross-guild isolation also remain acceptance items. Panels stay an Archive category, not a separate command. |
| `cogs/media/reading_club.py` | `/community` plus `helpers/community/community-reading.ts` | Guild-scoped nominations for manga/manhwa/manhua/webtoon/light novels/webnovels/books; one active vote per member with vote changes; manager selection by vote count (earliest nomination breaks ties) or explicit nomination; selected-read thread scheduling with future timezone-aware timestamps; persistent due-time notices with a five-minute retry window. No individual reading progress is stored. | Verify PostgreSQL migration/recovery and live Discord thread permissions. Previous reading-order exploration is intentionally not guessed; connect it to verified provider relationship edges only when sequence semantics are explicit. |
| `cogs/media/media_night.py` | `/community` Media Night | AniList candidates are provider-backed and adult-flagged entries are excluded; mood matching uses provider genres/tags; unbiased random sampling selects distinct entries; session and candidate rows persist in PostgreSQL; public buttons use database candidate IDs; one vote per member is locked; expired sessions close and final results are published through a retryable worker. | Run end-to-end Discord/PostgreSQL acceptance, verify candidate-tag behavior against live AniList responses, and keep the UI explicit that tag filtering is not an age rating. No adult-content recommendations or gambling are ported. |
| `cogs/media/release_calendar.py` | `/community` release calendar and guild digest worker | On-demand previews combine AniList airings, region-aware TMDB movie dates and TMDB next-episode dates with season/episode metadata. PostgreSQL stores per-guild channel, timezone, daily/weekly cadence, weekday, categories, region and next run; managers can preview, configure and disable; the bot queues due deliveries and retries failures. | Run end-to-end Discord/PostgreSQL acceptance, verify the TMDB `/tv/on_the_air` detail coverage and selected region behavior, and exercise schedule recovery after downtime. Release dates remain provider-sourced rather than inferred. |
| `cogs/gaming/game.py`, Steam modules | `/discover`, `/profile`, `/play` | Steam and IGDB helpers, game discovery, similar games, linked Steam profile and quiz sessions exist. | Verify all supported Steam profile/store fields, game recommendation behavior, pagination and safe provider failure. |
| `cogs/gaming/free_games_checker.py` | No current v3 destination | Explicitly excluded in the v3 specification because the previous implementation relies on storefront parsing/undocumented interfaces. | Do not port the scraper. Reconsider only if a stable, permitted promotions API is verified. |
| Custom-role cogs and helpers | `/custom-role`, `helpers/custom-roles/*` | TypeScript lifecycle, validation, image/picker and storage helpers exist. Picker-link capacity, token scope, replacement, idle/absolute expiry, read/write throttling, PNG/JPEG/crop safety, palette extraction, mass-archive threshold parsing and configured reconciliation interval now have focused tests. | Complete Discord/PostgreSQL lifecycle acceptance for role ownership, guild boundaries, cooldowns, role hierarchy, rollback and image persistence. Live picker proxy/permissions remain unverified. |
| `cogs/admin/dashboard.py`, dashboard frontend | `/settings`, Next.js frontend, Rust/Axum backend | A TS bot bridge and authenticated Atlas dashboard path exist. | Verify all in-scope guild configuration, channel selectors, feature visibility, authorization and audit behavior. Dashboard sync now filters `/log`, `/moderators` and `/planned` out of global command publication and keeps every published feature command restricted to guild context. `/help`, `/privacy` and `/feedback` remain separate standalone commands. Preserve the Rust trust boundary. |
| `cogs/server_management/server_check.py`, selected `server_config.py` behavior | `/settings` diagnostics | Read-only `diagnostics` action checks the current channel plus configured media-notification, Archive, Custom Roles and scheduled-delivery channels for View Channel, Send Messages and Embed Links. It is ephemeral, Manage Server-only and changes no settings. | Live Discord channel permissions and missing/deleted channel behavior still need acceptance. Bot-update and invite-tracking configuration remain retired with their old features. |
| `cogs/admin/bot_moderators.py`, `utils/bot_monitoring.py`, `utils/monitoring_system.py` | Standalone `/log`, `/moderators`, `/planned`, runtime health and authorized diagnostics | The three bot-moderator commands remain independent, are omitted from global registration, register only to `BOT_MODERATOR_GUILD_ID`, and check both guild and moderator authorization on command/component interactions. `/log` uses the globally unique issue hash from that operations server so moderators can inspect errors raised in other guilds; `/feedback` still verifies a submitted issue hash against the originating guild. `/moderators` is the public command name. | Verify access controls and diagnostic redaction with live Discord permissions; structured health metrics and operational alerting still require parity acceptance. Never expose operator data to ordinary guild members. |
| Social/profile cogs | `/profile`, `helpers/runtime/profile.ts` | AniList/Steam linking, per-guild visibility, opt-in affinity, minimum-three-member aggregate taste and privacy-gated anime/manga leaderboards exist. On member departure, AniList/Steam links plus profile and Archive browsing preferences are removed only for that guild; startup reconciliation performs the same cleanup only after a complete Discord member list is confirmed. | Link/unlink and opt-out behavior has source-level implementation but still needs live provider/Discord acceptance. The old leaderboard exposed additional chapter/episode/completed/combined metrics; v3 intentionally exposes anime/manga entry-count leaderboards only, with at least three opted-in current members and mean score as tie-breaker. No personal progress is stored. |
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

- GitHub's branch comparison reports `lemegeton-v3` as diverged from `multi_guild`: **630 commits ahead, 86 commits behind**, merge base `e7c7c99728fc71c30a9bff65d5eed194ae8ffaf1` (checked 11 November 2026). PR #17 reports `mergeable=false` / `mergeable_state=dirty`. No synchronization or conflict resolution was attempted; do not merge or resolve conflicts automatically. The PR branch and base each contain independent history.
- No live Discord test server/application credentials were available for gateway-intent, channel-permission, component-authorization, command-registration, thread and scheduled-delivery acceptance.
- No target PostgreSQL instance or sanitized data snapshot was available, so this audit cannot verify schema application or recovery against the intended database. The Python files on `multi_guild` are source-reference code, not an assumed running or deployed service; no import from a Python runtime is presumed necessary. If there is pre-existing database data that must be retained, confirm that requirement and test its migration/restore separately.
- Guild departure now follows the required per-guild retention choice documented above; an unset choice retains data rather than deleting it.
- Interactive release-calendar previews use independent provider requests and retain successful provider results when another selected provider fails; `/community` names unavailable providers and makes clear that the remaining results are partial. Tests cover one-provider failure and the all-selected-providers-unavailable case. Scheduled release digests deliberately use stricter delivery semantics: if any selected provider is unavailable, the digest is not sent or marked complete and the delivery remains queued for retry. Verify this retry behavior against PostgreSQL and a live Discord test channel.

## Required TypeScript coverage

The source tree has fifty Python test modules under `tests/`; the current Draft snapshot has thirty-four TypeScript test modules. The target is not fifty matching files. The target is focused coverage for every selected v3 behavior, especially:

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


## Integration and runtime boundary correction — 10 November 2026

Verified on Draft head `7198ac4` and the preceding structural commits:

- `src/integrations/` contains only message-driven integration modules: `anilist-embed.ts` and `social-embed.ts`. These are not slash commands.
- Provider clients and shared integration logic live under `helpers/integration/`: AniList, Atlas, Google Books, IGDB, Steam and TMDB.
- The old `helpers/providers/` directory is removed. Imports in bot, commands, community helpers, profile helpers and provider tests now target `helpers/integration/`.
- `/adminlogin` is back under `src/standalone/admin-login.ts`; `/convertlinks` is back under `src/utility/convertlinks.ts`. Both are registered only in `BOT_MODERATOR_GUILD_ID`, excluded from global deployment and dashboard command synchronization. `/adminlogin` additionally requires bot-moderator authorization.
- The redundant `helpers/embeds/anilist.ts` and `helpers/embeds/social.ts` wildcard re-export shims were removed. Embed builders remain in `helpers/embeds/core.ts`; message handlers live in `src/integrations/`.
- `bot.ts` now starts the social/Steam link integration, uses typed configuration for the Atlas bridge secret and port, and passes `config.database` to PostgreSQL initialization.
- `database.ts` keeps the documented 40-character lowercase hexadecimal issue-reference constraint. No sequential or alternate reference format was introduced. The redundant second unique index on `users(discord_id, guild_id)` was removed because the table's unique constraint already supplies that index.
- The TypeScript test suite was updated for the new import boundaries and asserts that `adminlogin` and `convertlinks` are excluded from dashboard/global command synchronization.

The current tree snapshot at this audit update contains 219 tracked paths, 112 TypeScript/TSX files (33 test modules), and zero Python files. These counts are inventory only.

The TypeScript bot workflow passed on head `7198ac4` (type-check and test job). Dashboard/container checks were still running at the time of this update. Live Discord authorization, a target PostgreSQL migration/restore, and full source-feature parity remain separate acceptance gates; this structural correction does not close the overall migration exit gate.

## Migration continuation — 11 November 2026

**Code snapshot audited:** `009eced06b8638cde995e206b48eef0a578d2f1f`  
**PR:** #17 remains open and Draft, base `multi_guild`.  
**Tree:** 222 tracked paths, zero Python files, 115 TypeScript/TSX files, 34 TypeScript test modules.

### Verified migration slices completed

- **Legacy user identity:** a pre-guild `users` table receives `guild_id`; existing rows are backfilled to the configured primary guild only when that setting is supplied. Discord IDs are widened to BIGINT, AniList fields are retained, and the old single-guild uniqueness key is replaced by the guild-composite key. The integration test exercises PostgreSQL schema conversion and repeat initialization.
- **Legacy Panels:** safe, non-NSFW `panels` rows and `panel_tags` import idempotently into the unified Archive. Source rows remain untouched. Old `panel_mod_role_id` and `panel_log_channel_id` migrate to the new Archive moderator role and moderation-notification channel.
- **Panel of the Day:** `/archive` selects a stable daily panel for each server. The selector restricts entries to approved, non-spoiler, image-backed items that are global or belong to the requesting guild. A database lock and per-guild/day key prevent duplicate selection.
- **Community polls:** old media brackets and adaptation polls migrate into `community_rankings`, candidates and votes. Poll identity keys make imports idempotent; guild ownership, options and existing votes are retained.
- **Community quiz pool:** old media-quiz rows with a valid HTTPS source and fields within current limits migrate into a pending-review quiz pack. Invalid or unsupported source rows remain in their original table; imported questions are not automatically approved.
- **Animanga completion destination:** legacy `guild_manga_channels` records migrate to `media_notification_settings` as enabled anime+manga notifications. Existing v3 settings win on conflict.
- **Member departure privacy:** a member leaving a guild removes only their guild-scoped AniList/Steam links, profile preferences and Archive browsing preference. Startup reconciliation checks the complete Guild Members list and skips destructive action if Discord returns incomplete data. It does not delete historical Archive/community contributions, feedback or issue records.

### Schema disposition

The latest source/schema comparison found **38** distinct table definitions in `multi_guild` and **52** in v3, with seven identically named tables. Table names are not a coverage score: numerous legacy tables represent replaced v3 data models.

- `media_assets` is schema-compatible between the previous PostgreSQL helper and v3; no table rewrite is needed for those existing object records.
- `booster_roles` is widened to BIGINT when present and retained for the Custom Role takeover/import path. It is not blindly copied into `custom_role_records`.
- `guild_mod_roles` has no active command/cog callers in the inspected source tree; the old table/helper is not the new Archive moderator-role feature. The Archive-specific panel role is migrated separately.
- `custom_role_meta` has no runtime consumer in the inspected old source; v3 does not recreate it.
- `user_stats` and `achievements` are not imported: v3 obtains current AniList statistics on demand and derives milestone displays without retaining a personal progress ledger.
- Personal manga/watch/play progress and challenge tables, invite/recruitment tracking, news scraping, free-game scraping, generic `/say` logs and the GitHub commit tracker are outside the approved v3 scope. Their legacy rows are not recreated or consumed by v3.
- The old per-server AniManga channel table is now imported rather than classified as retired.

### Configuration disposition

The typed v3 config retains the settings consumed by the TypeScript bot and Rust dashboard: Discord credentials/application ID (with `CLIENT_ID` as a compatibility alias), feedback channel, Archive global moderators, operator/admin guild, PostgreSQL and TLS, AniList/Steam/IGDB/TMDB/Google Books credentials, S3, dashboard bridge/picker and Custom Roles. The removed Python-only settings are not reintroduced: old server mod-role and bot-update roles, GitHub tracking, Twitch/status rotation, cog hot-reload, webhook monitors, generic LLM/retry settings, old cleanup polling intervals, challenge-role settings and MDBList. SQLite `DB_PATH`/`DATABASE_PATH` settings are retired because the source database and v3 database are PostgreSQL.

The `.env.example` was cleaned in this migration pass: removed old generic-role/update roles, webhooks, status/cog watcher, cleanup polling, Twitch, GitHub tracker, generic LLM/retry keys, legacy Google Cloud/EZ keys, SQLite-era `DISCORD_GUILD_ID`/`CHANNEL_ID`, public S3 settings with no v3 consumer, MDBList, and the obsolete Python-only member-fetch debug switch. The retained sample entries match the typed bot settings and Rust dashboard deployment contract; CI validates the file using Node's native env-file parser.

### Latest CI evidence and remaining acceptance

- TypeScript bot workflow on code head `009eced`: **passed**, type-check, build and all 164 tests passed: [run 42904087018](https://github.com/Kyerstorm/Lemegeton/actions/runs/42904087018).
- Dashboard/security/backend workflow on code head `009eced`: frontend type-check, high-severity npm audit, production build/static-asset checks and Rust tests **passed**. Docker image build/runtime contract and `cargo audit` were still running at the last check: [run 42904087415](https://github.com/Kyerstorm/Lemegeton/actions/runs/42904087415). Do not treat the whole workflow as green until its final conclusion is success.
- No live production PostgreSQL target, sanitized production backup, Discord application credentials or test guild were available. CI database fixtures prove the migration SQL against the test schema, not a production data restore.
- **Guild departure retention:** implemented as a required per-server choice (`delete` or `retain`). `GuildCreate`/startup attempts to record the original inviter from the Bot Add audit-log entry; the inviter or any Manage Server member can choose. Until configured, slash commands, components, message-driven embeds/uploads, scheduled deliveries, the Atlas bridge, Dashboard guild routes, and the Custom Roles picker are blocked. `GuildDelete` only purges on an available-guild leave event when `delete` was selected; database deletion is transactional, S3 object deletion uses the retry queue, and the policy row is preserved across a rejoin. A `deleted_at` marker makes successful cleanup idempotent; startup and periodic scans retry unfinished delete actions only for guilds no longer in the bot cache, while active guilds are excluded. PostgreSQL integration and authorization unit tests cover the behavior. Live Discord audit-log permissions and S3 deletion recovery still require acceptance.
- **Legacy Panel storage fallback is unresolved:** the old private `panel_storage_channel_id` was a bot-managed storage destination, while v3 `upload_channel_id` is a member intake channel. They are not interchangeable. If an existing deployment depends on private Discord-channel storage, configure private S3 or approve a distinct replacement before claiming that path is migrated.
- AniList leaderboard parity is intentionally narrower: v3 shows privacy-opted-in anime/manga entry-count rankings only, not the old chapters/episodes/completed/combined metrics. Restoring those metrics without the old per-title progress storage would need a separate product decision.
- PR #17 remains Draft. This audit work does not merge, synchronize or alter `multi_guild`.

### Guild departure policy and first-run gate — 11 November 2026

- Added `guild_retention_settings` with the original inviter, the required `delete`/`retain` choice, and the actor who last changed it.
- On join and startup, the bot attempts to resolve the Bot Add audit-log entry. The recorded inviter may choose the policy; a member with Manage Server can always choose or change it if audit-log access is unavailable or the inviter is no longer available.
- Until the choice is stored, the bot blocks normal slash commands and components, guild message integrations, per-guild scheduled work, Atlas lookups, Dashboard guild actions, and Custom Roles picker access. `/settings` with no action opens the retention choice; other settings stay locked.
- `deleteGuildData` discovers guild-scoped columns in the current PostgreSQL schema, removes rows transactionally while respecting foreign-key ordering, then attempts private S3 asset cleanup through the existing retry queue. The policy row is deliberately retained so a re-invited bot continues to honor the saved decision. `deleted_at` records successful database cleanup; failed event-time deletion is retried at startup and on the existing reconciliation interval, only when the guild is absent from the bot's cache. Failed retries do not block processing of other departed guilds.
- The old `/server-check` behavior is folded into `/settings action:diagnostics` rather than adding another top-level command. It checks the current channel and configured v3 delivery channels for View Channel, Send Messages and Embed Links; the report is read-only and ephemeral.
- Reading Club reminder and Media Night result workers now filter unconfigured guilds inside their PostgreSQL claim queries, so locked guilds are not marked attempted or closed before selection.
- A transient unavailable-guild event is ignored; only an available guild departure applies the selected action. An unset or invalid action falls back to retention, never deletion.
- Authorization tests cover the inviter and Manage Server paths. Permission-summary tests cover diagnostics output. PostgreSQL integration tests cover target-guild cleanup, preservation of another guild's data, retention-policy persistence, retry recovery, active-guild exclusion, and the fact that locked guilds are not claimed by scheduled workers.
- Live audit-log permissions, a real guild kick/rejoin test, production PostgreSQL restore, and S3 failure/retry recovery remain acceptance tasks.

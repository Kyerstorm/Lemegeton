# Design: Lemegeton V2 Phase 2 — Account Section Refactor

## Status
Investigated 2026-09-19. Ready for implementation.

## Context
Fourth section of Lemegeton V2's Phase 2 (Gaming, Media, Social already complete — see
`.claude/PRPs/reports/lemegeton-v2-{gaming,media,social}-refactor-report.md` and the archived specs in
`.claude/PRPs/plans/completed/`). Applies the same 7-category checklist to the 3 files in
`cogs/account/`: `login.py` (1017 lines), `profile.py` (1500 lines), `admin_login.py` (223 lines).

## Decisions Made (do not re-litigate during implementation)
| Decision | Answer |
|---|---|
| Ground rules | Same as Gaming/Media/Social: full 7-category checklist, reliability/error-handling weighted highest, internals free to change, command/listener behavior and output unchanged |
| Database scope | Same as prior passes: no schema changes. One exception explicitly scoped in Task 7 below (new guild-aware helper *functions* in `database.py`, not new tables/columns — `steam_users` table already exists) |
| `admin_login.py`'s `admin_login_prefix` (`@commands.command`, prefix-only) | **Do not wire `account_error_handler` onto it** — same decision Social made for `lolilist.py`'s legacy prefix commands (different decorator contract, out of scope) |
| `@log_command` decorator (from `helpers/command_logger.py`) | **Out of scope, observation only.** `admin_login.py` already uses it (pre-existing, unrelated to the removed dashboard `command_meta` system); `login.py`/`profile.py` don't. This decorator was never part of the Gaming/Media/Social passes' established scope — not adding it here either, to keep scope consistent across the series. Flagged as a possible future consistency item, not built now |
| `embed_helper.py`'s existing `build_user_profile_embed()` / `build_favorites_embed()` | **Not relevant to this pass.** These are pre-existing, currently-unused module-level functions with the same names as things `profile.py` needs — investigation confirmed `profile.py` has its own *local* dead `build_favorites_embed()` (see Category 7) that is unrelated to and doesn't call the `embed_helper` one. Do not assume they're wired up; verify independently during implementation before reusing either |

## Investigation Findings (7-category checklist, evidence gathered before design)

### 1. Import boilerplate
- `login.py:159-166` — a function-local `import sys` + `sys.path.insert(0, str(repo_root))` hack inside `LoginView.status_button`, done solely to import `helpers.steam_helper.get_library_stats` (the module already imports `resolve_vanity_url`/`get_player_summaries` from the same module at top-level — only this one function was added later without updating the top-level import). Same class of fix as Media's `recommendations.py` cleanup.
- `login.py` also has **4 redundant `import aiosqlite` statements** inside functions (lines 661, 761, 797, 975) despite `aiosqlite` already being imported at module level (line 8). Pure dead-weight imports, not fallback boilerplate — different sub-issue than the `sys.path` hack, same category.
- `profile.py` and `admin_login.py` use flat imports throughout — no boilerplate to remove.

### 2. Direct API calls duplicating helpers
- `login.py:_resolve_steam_vanity()` opens **two separate `aiohttp.ClientSession()` blocks** back-to-back (lines 596 and 608) — one to resolve the vanity URL, one to fetch the player summary — when both `resolve_vanity_url()` and `get_player_summaries()` accept an existing session and could share one. Unlike Social's AniList-session duplication (flagged as a *future*, cross-cutting candidate because it touched Media too), this is contained to a single function in a single file — safe to fix directly in this pass.
- `profile.py`'s `fetch_user_stats()` and `fetch_social_stats()` each open their own `aiohttp.ClientSession()` — same category as Social's AniList finding. **Out of scope** here too, for the same reason (would need a cross-cutting session shared with Media/Social/Gaming to do properly — not building it mid-Account-pass).
- No hand-rolled GraphQL bypassing `post_graphql()` — `admin_login.py` and `login.py` route through `fetch_anilist_user_basic()`; `profile.py` routes through `post_graphql()` directly with its own queries (`USER_STATS_QUERY`, `SOCIAL_STATS_QUERY`) — that's the intended use of the helper, not a violation.

### 3. Inline embeds vs embed_helper
Inline `discord.Embed()` counts: `profile.py` ~15 (main profile embed + achievements/favorites/gallery per-page embeds), `login.py` ~5 (status embed, login command's 2 state embeds, LoginView usages), `admin_login.py` 2 (one via `build_success_embed`/`build_error_embed` already, one raw). `login.py`'s `handle_register()`/`handle_steam_register()` already use `build_success_embed()` — good. Candidates for the "1-2 main result embeds only" light touch (same discipline as Media/Social):
- `profile.py`'s main `profile_embed` (the command's primary output) — large and bespoke, may not fit an existing/new builder cleanly without behavior drift; judge during implementation (see Task 10).
- `login.py`'s `login()` command's two state embeds (connected vs. not-connected) — good candidate, both are the command's *only* embed output.
- `admin_login.py`'s final "AniList Login Successful" embed (line 195) is still raw `discord.Embed()` despite the file already importing `build_success_embed` for its other two embeds — an easy, low-risk win.
Do NOT touch `profile.py`'s per-page embeds in `AchievementsView`/`FavoritesView`/`GalleryView`/`UnifiedProfileView`/`ProfilePager` (10+ small embeds) — same "main embeds only" scope Media/Social applied to their multi-page views.

### 4. Error handling (biggest structural gap, same as prior passes — but smaller here)
No section-wide decorator exists. Only **1 bare `except:`** in this section (`profile.py:579`, inside the `defer()` failure-recovery block — catches a failed attempt to notify the user that defer itself failed; same "best-effort cleanup" pattern already accepted elsewhere in this codebase). Much smaller bare-except count than Gaming/Media/Social (7 each) — this section already has unusually careful manual error handling (see `profile.py`'s multi-layered defer/send/fallback-embed logic). Build `account_error_handler` in a new `helpers/account_utils.py` anyway, for the same reasons as the prior three passes: consistency, and a safety net for *uncaught* exceptions the extensive manual handling doesn't already catch. Same adapted pattern as `media_utils.py`/`social_utils.py` (typed exceptions as an unreachable opt-in escape hatch — `anilist_helper.py`/`steam_helper.py` don't raise them here either).

### 5. Function length
- `profile.py`'s `profile()` command handler — **~310 lines** (566-876). By far the largest single function found in this Phase 2 series to date (larger than Social's `affinity.py` handler at 277 lines). Clearly a fetch+compute+build+send tangle: guild check → DB lookup with cross-guild fallback → cache check → AniList fetch → achievement computation → bio image extraction → social stats fetch → stat persistence → embed build → view construction → send-with-fallback. Strong candidate for splitting into named steps.
- `login.py`'s `login()` command handler — **~97 lines** (828-925). Fetch user data → build embed(s) → build view → send. Candidate for splitting, smaller than the Gaming/Media/Social precedent threshold but still a fetch+build+send tangle.
- `login.py`'s `handle_steam_register()` — **~110 lines** (629-738). Validation → vanity resolution → 4 separate hand-rolled DB CRUD blocks → embed build. Splitting this is entangled with Task 7's DB-helper extraction — extracting the DB CRUD into named helper functions will naturally shrink this function without a separate manual split.
- `profile.py`'s `build_achievements()` — **~170 lines** (233-401). Judgment call per the established convention: this already delegates chunks to `check_milestone_achievements()`/`check_score_achievements()` (imported helpers), making it more "one cohesive achievement-scoring pass over several categories" than a fetch+format+send tangle — default to leaving it as one function per the Gaming (`_generate_recommendations`) and Social (`calculate_affinity`) precedent, but read in full before deciding, same discipline as those passes.
- Other functions not deep-read at design time — apply the same judgment call live during implementation.

### 6. Duplicated DB lookups
Hand-rolled `anilist_username` tuple indexing (`row[4]`) appears at 4 live sites across this section:
`login.py:755` (`get_user_data`), `login.py:960` (`check_connection_health`), `profile.py:616` (`profile()`),
`admin_login.py:117` (`_get_existing_user`, which also reads `row[5]` for `anilist_id` — no equivalent
centralized helper exists for that index; leave that half of the tuple as direct indexing, consistent with
the Social pass only ever consolidating the `anilist_username` half). Route all 4 `[4]`-index reads through
`database.get_anilist_username_from_row()` (added during the Media pass, already used by Media/Social) — a
DRY consolidation, not a bug fix; all 4 sites already read the correct index.

**Separately, a real duplication specific to this section**: `login.py` hand-rolls raw `aiosqlite.connect(DB_PATH)` + SQL against the `steam_users` table at **4 separate call sites** within the same file (`handle_steam_register` — check/update/insert; `get_user_data` — select; `unregister_user` — delete; `check_connection_health` — select). No guild-aware helper functions exist for `steam_users` in `database.py` (unlike the `users` table, which already has `get_user_guild_aware`/`register_user_guild_aware`/etc.). This is the section's largest category-2/6-style finding — see Task 7.

### 7. Dead code
- `profile.py`'s `Pager` class (1434-1453) and `ProfilePager` class (918-953) — confirmed **zero references anywhere** in the codebase (grepped both `cogs/` and `helpers/`) beyond their own definitions. The live paginated-view pattern is `UnifiedProfileView` + `AchievementsView`/`FavoritesView`/`GalleryView`, which don't use either class.
- `profile.py`'s module-level `build_favorites_embed()` function (404-482) — confirmed **zero callers** within `profile.py` itself (the live favorites display goes through `FavoritesView.build_anime_favorites()` etc., a different, newer per-page-type implementation). Not to be confused with `embed_helper.py`'s own `build_favorites_embed()`, a different, also-currently-unused function this pass does not touch (out of scope per Decisions Made).
- `login.py`'s two "Deprecated method removed - use X instead" comments (lines 558, 570) are stale leftover comments, not dead code — clean up as part of Task 4's tidying since they're immediately adjacent to the import/boilerplate cleanup pass, not a separate task.

## Mandatory Reading
| Priority | File | Why |
|---|---|---|
| P0 | `.claude/PRPs/reports/lemegeton-v2-social-refactor-report.md` (and gaming/media reports) | The checklist, gotchas, and adapted-decorator precedent this pass follows |
| P0 | `Lemegeton_v2/helpers/social_utils.py` | Most recent, most relevant pattern to mirror for `account_error_handler` |
| P0 | `Lemegeton_v2/database.py` (`get_anilist_username_from_row`, `get_user_guild_aware`, `register_user_guild_aware`, `init_steam_users_table`) | Existing helper Category 6 routes calls through, plus the naming/shape convention new `steam_users` guild-aware helpers (Task 7) must match |
| P1 | `Lemegeton_v2/cogs/account/profile.py` | Largest file, most findings (categories 3, 5, 6, 7) — read `profile()` (566-876) and `build_achievements()` (233-401) in full before touching either |
| P1 | `Lemegeton_v2/cogs/account/login.py` | Second-largest file, most structural findings (categories 1, 2, 5, 6 — the `steam_users` CRUD duplication lives entirely here) |
| P2 | `Lemegeton_v2/cogs/account/admin_login.py` | Smallest file, lightest touch — decorator + one embed + one DB-lookup consolidation |
| P2 | `Lemegeton_v2/helpers/gaming_utils.py` (`ConnectionPool`, lines ~96-138) | Reference only, for context on how session-sharing is solved elsewhere — Task 8's Steam session fix is local/contained and does NOT need to adopt this pattern, just merge two sessions into one within `_resolve_steam_vanity` |

## NOT Building
- No cross-cutting aiohttp connection pool for AniList calls in `profile.py` (flagged in category 2 as a future candidate, consistent with Social's identical decision).
- No `@log_command` wiring onto `login.py`/`profile.py` — out of this series' established scope (see Decisions Made).
- No restructuring of `profile.py`'s `AchievementsView`/`FavoritesView`/`GalleryView`/`UnifiedProfileView` per-page embeds — main embeds only.
- No database schema changes (Task 7 adds functions to `database.py`, not tables/columns — `steam_users` table already exists as of `init_steam_users_table()`).
- No changes to any other section (Admin, Server Management, Utilities remain untouched).

## Step-by-Step Tasks

### Task 1: Build account_error_handler
- **ACTION**: Create `Lemegeton_v2/helpers/account_utils.py` mirroring `social_utils.py`'s structure (rename Social→Account throughout: `AccountError`, `AccountAPIError`, `AccountNotFoundError`, etc.; log file `logs/account.log`, logger name "Account").
- **MIRROR**: `helpers/social_utils.py`.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/helpers/account_utils.py`.

### Task 2: Wire account_error_handler onto Account app commands
- **ACTION**: Add the decorator to `login.py`'s `login` command and `profile.py`'s `profile` command (both `@app_commands.command`). Do not add it to `admin_login.py`'s `admin_login_prefix` (`@commands.command`, prefix-only — different decorator contract, out of scope per Decisions Made).
- **GOTCHA**: `profile.py`'s `profile()` handler already has careful manual `discord.NotFound`/`Exception` handling around its `defer()` call at the very top. The decorator is a supplementary safety net for anything *not* already caught further down the function — don't remove or duplicate the existing defer-specific handling, just wrap the whole function.
- **VALIDATE**: grep confirms decorator present on exactly these 2 commands, absent from the prefix command.

### Task 3: Fix the bare except (category 4)
- **ACTION**: Replace `profile.py:579`'s bare `except:` with typed/logged handling (it currently silently swallows a failure to send an error message after `defer()` itself already failed) — log at `warning`, keep the swallow-and-continue behavior since there's genuinely nothing further to do at that point.

### Task 4: Import boilerplate cleanup (category 1)
- **ACTION**: In `login.py`: (a) remove the function-local `import sys` + `sys.path.insert` block in `status_button` (lines 159-166), add `get_library_stats` to the existing top-level `from helpers.steam_helper import resolve_vanity_url, get_player_summaries` line instead; (b) remove all 4 redundant function-local `import aiosqlite` statements (lines 661, 761, 797, 975) — already imported at module level; (c) remove the 2 stale "Deprecated method removed" comments (lines 558, 570).
- **VALIDATE**: `grep -n "sys.path.insert\|^\s*import aiosqlite" Lemegeton_v2/cogs/account/login.py` returns zero matches outside the top-level import block.

### Task 5: Consolidate anilist_username DB lookup (category 6)
- **ACTION**: Route `login.py:755`, `login.py:960`, `profile.py:616`, and `admin_login.py:117` (username half only — leave the `anilist_id` index untouched) through `database.get_anilist_username_from_row()`.
- **VALIDATE**: All 4 sites produce identical values before/after — confirm no behavior change, same as Social's Task 5.

### Task 6: Remove dead code (category 7)
- **ACTION**: Delete `profile.py`'s `Pager` class, `ProfilePager` class, and module-level `build_favorites_embed()` function, after confirming zero references (including non-call references) across the whole `Lemegeton_v2/` tree, not just `cogs/account/`.
- **VALIDATE**: `grep -rn "ProfilePager\|class Pager\b" Lemegeton_v2/` returns zero matches; `grep -rn "build_favorites_embed" Lemegeton_v2/cogs/account/profile.py` returns zero matches.

### Task 7: Consolidate steam_users DB access (category 2 + 6, section-specific)
- **ACTION**: Add guild-aware helper functions to `database.py` for the `steam_users` table (naming to match the existing `users`-table convention, e.g. `get_steam_user_guild_aware`, `upsert_steam_user_guild_aware`, `delete_steam_user_guild_aware`), then route `login.py`'s 4 raw-SQL call sites (`handle_steam_register`, `get_user_data`, `unregister_user`, `check_connection_health`) through them.
- **GOTCHA**: The 4 call sites do NOT all have identical lookup semantics today — `handle_steam_register`'s existing-user check does guild-scoped lookup first, then falls back to a global (no-guild) lookup; `get_user_data`/`check_connection_health` query by `discord_id` only (no guild filter at all); `unregister_user` branches on whether `guild_id` is `None`. Preserve each site's exact existing behavior — this is a call-site consolidation (shared DB-access code), not a semantics unification. If a single helper can't honestly serve a call site's existing behavior, add a second helper rather than force a behavior change.
- **VALIDATE**: Each of the 4 call sites produces identical results before/after for the same inputs; `python -m py_compile Lemegeton_v2/database.py Lemegeton_v2/cogs/account/login.py`.

### Task 8: Merge duplicate Steam aiohttp sessions (category 2, section-specific, small)
- **ACTION**: In `login.py:_resolve_steam_vanity()`, merge the two sequential `async with aiohttp.ClientSession(...)` blocks (vanity resolution + player summary fetch) into one shared session context.
- **VALIDATE**: Behavior unchanged — both API calls still happen in the same order with the same error handling.

### Task 9: Function length — judgment-call pass (category 5)
- **ACTION**: Read `profile.py`'s `profile()` command handler (~310 lines) in full and split the fetch+compute+build+send tangle into named steps (e.g. resolve-registration-with-fallback, fetch-or-cache AniList data, compute achievements, build main embed, build views, send-with-fallback) — this is the largest function this series has touched, apply extra care. Read `login.py`'s `login()` handler (~97 lines) and `handle_steam_register()` (post-Task-7, likely already shrunk) and split if still a clear fetch+build+send tangle. Read `build_achievements()` (~170 lines) and apply the default-to-leave-as-one-cohesive-function judgment call per precedent, unless reading reveals an obvious clean seam. Record reasoning for each in the implementation report.

### Task 10: Light embed_helper touch-up (category 3)
- **ACTION**: Route `admin_login.py`'s final raw "AniList Login Successful" embed through `build_success_embed()` (already imported in that file, trivial win). Route `login.py`'s `login()` command's 2 state embeds through a new or existing `embed_helper.py` builder. For `profile.py`'s main `profile_embed`: attempt to extract a builder if the shape reasonably allows it without changing rendered output (bio-image/banner precedence, achievement summary field, footer text); if it's too bespoke to safely extract without behavior drift (same risk Social hit with `anilist_site_embed.py`'s two main embeds), leave it inline and document why in the report rather than forcing it.

## Testing Strategy
No automated test suite exists. Validation: `python -m py_compile` on every touched file; a real
`importlib.import_module()` test inside a running `asyncio` event loop; reference-cleanup greps for
removed patterns; manual smoke test flagged as a required follow-up (no bot token available to the
implementer) — this section is especially worth a careful manual pass given Task 7 touches account
registration/deregistration, the highest-consequence flows in the whole bot.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Task 7's `steam_users` consolidation subtly changes one call site's guild-scoping behavior (e.g. accidentally adding a guild filter to a site that currently checks globally, or vice versa) | Medium | High (users could appear registered/unregistered incorrectly, or Steam data could leak/miss across guilds) | Task 7's GOTCHA explicitly catalogs each site's current behavior before touching any of them; prefer 2 narrow helpers over 1 that papers over a real difference |
| `profile.py`'s 310-line `profile()` handler turns out to be more tangled than a clean fetch/build/send split allows (e.g. shared local variables threaded through many steps) | Medium | Medium (could introduce subtle bugs with no test suite to catch them) | Task 9's explicit "read in full before deciding" gate, same discipline as Social's `affinity.py` handling |
| `account_error_handler`'s typed exceptions are unreachable, same as Media/Social | High (same root cause: `anilist_helper.py`/`steam_helper.py` don't raise them at this layer) | Low (defense-in-depth, documented as such) | Task 1 explicitly mirrors the already-adapted `social_utils.py`, not Gaming's original |

## Next Step
Implement directly (established pattern for this Phase 2 series) — write the implementation report to
`.claude/PRPs/reports/lemegeton-v2-account-refactor-report.md` and archive this spec to
`.claude/PRPs/plans/completed/` when done, mirroring Gaming, Media, and Social's closeout.

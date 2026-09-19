# Design: Lemegeton V2 Phase 2 — Social Section Refactor

## Status
Approved by user 2026-09-19. Ready for implementation.

## Context
Third section of Lemegeton V2's Phase 2 (see `Lemegeton_v2/docs/cog-refactor-convention.md`* for the
7-category checklist and gotchas established during the Gaming and Media passes). Applies the same
checklist to the 7 files in `cogs/social/`.

*Note: `Lemegeton_v2/docs/cog-refactor-convention.md` and `Lemegeton_v2/CLAUDE.md` were deleted per
explicit user request in the commit that closed out the Media pass. The convention (7-category
checklist, judgment-call gotchas) still applies as established precedent from the Gaming/Media reports
in `.claude/PRPs/reports/`; this spec restates the checklist inline since the doc no longer exists.

## Decisions Made (do not re-litigate during implementation)
| Decision | Answer |
|---|---|
| Ground rules | Same as Gaming/Media: full 7-category checklist, reliability/error-handling weighted highest, internals free to change, command/listener behavior and output unchanged |
| Database scope | Same as Gaming/Media: no schema changes, only consolidate duplicated query logic |
| Scope: listener-only cogs | **Include both** `anilist_site_embed.py` (2154 lines, AniList link auto-embed via `on_message`) and `social_embed.py` (167 lines, social/Steam link rewriting via `on_message`) — despite having zero slash commands, they're live features in `cogs/social/` and in-scope for this pass |
| `anilist_leaderboard.py:891-905`'s `_fetch_user_data()` mis-indexing | **Not a live bug** — confirmed dead code. `fetch_and_cache_stats()` (which calls it) has zero callers; the live path is `fetch_and_cache_stats_guild_aware()` (correctly indexed at line 1414). Reclassified from a "fix immediately" correctness issue to a normal Category 7 dead-code finding |

## Investigation Findings (7-category checklist, evidence gathered before design)

### 1. Import boilerplate
One file has the Gaming-style `try/except ModuleNotFoundError` + `sys.path.insert` fallback:
`social_embed.py:9-16`. The other 6 files use flat imports already.

### 2. Direct API calls duplicating helpers
- `affinity.py`, `anilist_leaderboard.py`, `anilist_site_embed.py`, `lolilist.py` each create their own
  `aiohttp.ClientSession()` rather than sharing a connection-pooled session — same pattern Gaming's
  `connection_pool` (in `gaming_utils.py`) solved for Steam calls. No equivalent exists for AniList calls
  in Media or here; out of scope to build one now (would be a cross-cutting change touching Media too —
  flag as a future candidate, don't build it mid-Social-pass).
- `anilist_site_embed.py` calls `post_graphql` directly at 6 sites — already routed through the shared
  helper, no duplication to fix there.
- No evidence of hand-rolled GraphQL queries bypassing `post_graphql` in this section (unlike Media's
  `browse.py`/`random.py` finding) — `affinity.py` and `anilist_leaderboard.py` use `fetch_user_stats()`
  from `anilist_helper.py` already.

### 3. Inline embeds vs embed_helper
Inline `discord.Embed()` counts: `lolilist.py` 35(!), `anilist_site_embed.py` 13, `anilist_leaderboard.py`
5, `affinity.py` 4, `feedback.py` 1, `server_boost.py` 1. `lolilist.py`'s count is high but this file was
explicitly kept "as-is" (undocumented feature, Phase 1 decision) — light touch only, same treatment
Media gave `trailer.py`/`trending.py`. `anilist_site_embed.py`'s `build_tags_embed()` (396 lines) is
already its own dedicated builder method, just very large — a Category 5 finding, not a Category 3 one.

### 4. Error handling (biggest structural gap, same as Gaming/Media)
No section-wide decorator exists. Per the same pattern as Gaming (`gaming_error_handler`) and Media
(`media_error_handler`), build a `social_error_handler` in a new `helpers/social_utils.py`. **7 bare
`except:`**: `anilist_site_embed.py` ×6, `social_embed.py` ×1 (in `SimpleView.on_timeout`, same
"ignore failed edit-on-timeout" pattern already fixed elsewhere in this codebase's Gaming pass).

Given the Media pass's finding that `anilist_helper.py` never raises typed exceptions (it returns
`None`/sentinels on failure), `social_error_handler` will follow the same adapted pattern documented in
`media_utils.py`: real value comes from the `discord.NotFound` + generic-`Exception` safety net; typed
exception branches are included for future opt-in use, not because anything currently raises them.

### 5. Function length
- `affinity.py:calculate_affinity()` — **461 lines**. Single scoring algorithm (compatibility breakdown
  across many weighted factors) — apply the convention's judgment call: likely a cohesive algorithm, not
  a fetch+format+send tangle. Read in full during implementation before deciding whether any natural
  sub-steps exist worth extracting, but default to leaving it as one function per the Gaming pass's
  precedent with `_generate_recommendations()`.
- `affinity.py`'s `affinity` command handler — **277 lines**. Likely a fetch+build+send tangle (command
  handlers usually are) — candidate for splitting.
- `anilist_site_embed.py:build_tags_embed()` — **396 lines**. Embed-construction function; check during
  implementation whether it's naturally many independent field-building steps (splittable) or one
  intertwined pass over the data (not).
- `server_boost.py:booster_role_set()` — **157 lines**. Command handler, candidate for splitting.
- Other functions not deep-read at design time — apply the same judgment call live during implementation.

### 6. Duplicated DB lookups
Two live sites already correctly index anilist_username at position 4:
`anilist_site_embed.py:120-121` and `anilist_leaderboard.py:1414`. Neither is broken, but both hand-roll
the same tuple access `database.py`'s `get_anilist_username_from_row()` (added during the Media pass)
already centralizes. Route both through it for consistency — this is a DRY consolidation, not a bug fix.

### 7. Dead code
- `anilist_leaderboard.py`'s `fetch_and_cache_stats()` (~30 lines) and `_fetch_user_data()` (~66 lines) —
  confirmed zero callers of `fetch_and_cache_stats()` anywhere in the file; the live path uses
  `fetch_and_cache_stats_guild_aware()` instead. Delete both (see Decisions Made above for why this was
  reclassified from a correctness fix to a dead-code deletion).
- No other dead code identified yet — apply the convention doc's "verify zero occurrences including
  decorator args" discipline to anything else flagged during implementation before deleting it.

## Mandatory Reading
| Priority | File | Why |
|---|---|---|
| P0 | `.claude/PRPs/reports/lemegeton-v2-gaming-refactor-report.md` and `lemegeton-v2-media-refactor-report.md` | The checklist, gotchas, and adapted-decorator precedent this pass follows (convention doc itself was deleted) |
| P0 | `Lemegeton_v2/helpers/media_utils.py` | Pattern to mirror for the new `social_error_handler` — including the "typed exceptions may be unreachable" adaptation |
| P0 | `Lemegeton_v2/database.py` (`get_anilist_username_from_row`) | Existing helper category 6 routes calls through |
| P1 | `Lemegeton_v2/cogs/social/anilist_site_embed.py` | Largest file, most findings (categories 1, 2, 4, 5, 6 all present) |
| P1 | `Lemegeton_v2/cogs/social/affinity.py` | Two very large functions (461 + 277 lines) needing the judgment-call read |
| P2 | `Lemegeton_v2/cogs/social/anilist_leaderboard.py` (lines 891-1068, 1393-1440) | Dead-code deletion target + the live guild-aware replacement to confirm nothing else references the dead path |
| P2 | `Lemegeton_v2/cogs/social/lolilist.py` | Kept "as-is" per Phase 1 — light touch only (error handling + decorator uniformity, not embed/function restructuring) |

## NOT Building
- No cross-cutting shared `aiohttp` connection pool for AniList calls (flagged in category 2 as a future
  candidate, not built now — would touch Media too, out of this section's scope).
- No restructuring of `lolilist.py`'s 35 inline embeds or its two legacy `@commands.command` prefix
  commands (`!loliadd`/`!lolidelete`) — Phase 1 already decided to keep this file as-is; this pass only
  adds the error-handler decorator and fixes reliability gaps, consistent with how Media treated
  `trailer.py`/`trending.py`.
- No database schema changes.
- No changes to any other section (Account, Admin, Server Management, Utilities remain untouched).

## Step-by-Step Tasks

### Task 1: Build social_error_handler
- **ACTION**: Create `Lemegeton_v2/helpers/social_utils.py` mirroring `media_utils.py`'s adapted
  structure (typed exceptions as an opt-in escape hatch, real value from `discord.NotFound` +
  generic-`Exception` handling, since `anilist_helper.py` doesn't raise typed exceptions here either).
- **MIRROR**: `helpers/media_utils.py`.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/helpers/social_utils.py`.

### Task 2: Wire social_error_handler onto all Social commands
- **ACTION**: Add the decorator to all 5 `@app_commands.command`-decorated commands (`affinity`,
  `anilist_leaderboard`, `feedback`, `lolilist`, `nitro-role-set`). Do not add it to `lolilist.py`'s two
  legacy `@commands.command` prefix commands (`!loliadd`/`!lolidelete`) — different decorator contract,
  out of scope per "NOT Building."
- **VALIDATE**: grep confirms decorator present on every `@app_commands.command` in `cogs/social/`.

### Task 3: Fix bare excepts (category 4)
- **ACTION**: Replace the 7 bare `except:` (`anilist_site_embed.py` ×6, `social_embed.py` ×1) with typed
  handling distinguishing network/API failures from parse/logic failures, logged at `warning` where
  currently silent.

### Task 4: Import boilerplate cleanup (category 1)
- **ACTION**: Remove `social_embed.py`'s `try/except ModuleNotFoundError` + `sys.path.insert` fallback,
  replace with a flat import, matching the other 6 files' convention.

### Task 5: Consolidate anilist_username DB lookup (category 6)
- **ACTION**: Route `anilist_site_embed.py:120-121` and `anilist_leaderboard.py:1414` through
  `database.get_anilist_username_from_row()` instead of hand-rolled tuple indexing.
- **VALIDATE**: Both sites produce identical values before/after (they're already correct — this is a
  consolidation, not a fix; confirm no behavior change).

### Task 6: Remove dead code (category 7)
- **ACTION**: Delete `anilist_leaderboard.py`'s `fetch_and_cache_stats()` and `_fetch_user_data()` after
  confirming zero references (including non-call references).

### Task 7: Function length — judgment-call pass (category 5)
- **ACTION**: Read `affinity.py:calculate_affinity()` (461 lines), `affinity.py`'s `affinity` command
  handler (277 lines), `anilist_site_embed.py:build_tags_embed()` (396 lines), and
  `server_boost.py:booster_role_set()` (157 lines) in full. Apply the convention's judgment call: split
  fetch+format+send tangles into named steps; leave single cohesive algorithms alone. Record the
  reasoning for each in the implementation report, same discipline as Gaming's
  `_generate_recommendations()` decision.

### Task 8: Light embed_helper touch-up (category 3)
- **ACTION**: During Task 7's read-through, identify each file's 1-2 *main* result embeds (not
  transient/loading ones) and route them through `embed_helper.py` builders, adding new builder
  functions if none fit — same "light touch, main embeds only" scope Media applied. Do not attempt
  `lolilist.py`'s 35 embeds (kept as-is per Phase 1).

## Testing Strategy
No automated test suite exists. Validation: `python -m py_compile` on every touched file; a real
`importlib.import_module()` test inside a running `asyncio` event loop; reference-cleanup greps for
removed patterns; manual smoke test flagged as a required follow-up (no bot token available to the
implementer).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `social_error_handler`'s typed exceptions are unreachable, same as Media's | High (same root cause: `anilist_helper.py` doesn't raise them) | Low (defense-in-depth layer, documented as such from the start) | Task 1 explicitly mirrors the already-adapted `media_utils.py`, not Gaming's original |
| `affinity.py`'s two large functions turn out to be more tangled than they look, making extraction risky | Medium | Medium (could introduce subtle scoring bugs with no test suite to catch them) | Task 7's explicit "read in full before deciding" gate, same discipline as Gaming's `_generate_recommendations()` call |
| `anilist_site_embed.py`'s paginator-state persistence (`get_all_paginator_states`/`set_paginator_state`) has subtle cross-restart behavior that's easy to break while touching nearby code | Medium | Medium (View state wouldn't restore correctly after a bot restart) | Treat this subsystem as higher-risk; avoid touching its persistence logic unless a specific finding requires it |

## Next Step
Implement directly (established pattern for this Phase 2 series) — write the implementation report to
`.claude/PRPs/reports/lemegeton-v2-social-refactor-report.md` and archive this spec to
`.claude/PRPs/plans/completed/` when done, mirroring Gaming and Media's closeout.

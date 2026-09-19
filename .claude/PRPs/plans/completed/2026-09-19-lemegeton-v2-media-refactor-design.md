# Design: Lemegeton V2 Phase 2 — Media Section Removal + Refactor

## Status
Approved by user 2026-09-19. Ready for implementation.

## Context

Second section of Lemegeton V2's Phase 2 (see `Lemegeton_v2/docs/cog-refactor-convention.md` for the
7-category checklist and gotchas established during the first pass on Gaming). This section combines
two workstreams: (1) removing the `news.py` cog entirely per explicit user decision, and (2) applying
the same refactor checklist to the remaining 7 Media files.

## Decisions Made (do not re-litigate during implementation)

| Decision | Answer |
|---|---|
| Ground rules | Same as Gaming: full 7-category checklist, reliability/error-handling weighted highest, internals free to change, command behavior/output unchanged |
| Database scope | Same as Gaming: no schema changes, only consolidate duplicated query logic |
| Error handler | Build a new `media_error_handler` (mirrors `gaming_utils.py`'s `@gaming_error_handler` pattern) in a new `helpers/media_utils.py`, wired onto all remaining Media commands |
| news.py | **Remove entirely** — cog file, both commands (`admin-news-manage`, `test-twitter-scrape`), background scraping task, and its View/Modal classes. Confirmed isolated: only `database.py` (own table defs, left untouched) and a `requirements.txt` comment reference it; zero `bot.py` coupling (auto-discovery same as Gaming/Phase 1) |
| news database tables | `news_accounts`, `news_filters`, `news_metadata` become orphaned but are **not** dropped (no schema changes this pass) |
| `snscrape` dependency | Remove from `requirements.txt` along with its explanatory comment — it was `news.py`-only |

## Investigation Findings (7-category checklist, evidence gathered before design)

`helpers/media_helper.py` exists and is populated (798 lines, 8 async functions) — not empty like
Phase 1's `theme_helper.py`. Do not assume it needs deletion.

### 1. Import boilerplate
Clean — none of the 8 files have Gaming's `try/except ModuleNotFoundError` + `sys.path.insert` pattern.
All use flat imports already. **No action needed for this category.**

### 2. Direct API calls duplicating helpers (highest-value category)
- `browse.py:35-68` `fetch_media()` — near-duplicate of `anilist_helper.py:233` `fetch_media_by_search()`
  (same field set, missing `exclude_novels` filtering, creates its own throwaway session per call).
- `browse.py:76-137` `fetch_user_anilist_progress()` and `random.py:138` (same name/signature) —
  both reimplement the MediaList progress query that `media_helper.py:49` `fetch_user_progress()`
  already does, **except the helper version has TTL caching and typed exception handling that neither
  cog-local copy has.** Single highest-value fix in this section.
- `three_by_three.py:548-605` `fetch_media_by_id()` — **NOT a true duplicate** despite sharing a name
  with `anilist_helper.py:185`'s `fetch_media_by_id()`. Deliberately narrower (cached, cover-image-only,
  supports `media_type == "character"` which the shared helper doesn't). Naming collision only — rename
  one for clarity, do not merge.
- `anilist_helper.py:354` and `media_helper.py:421` both define `fetch_user_stats()` with different
  signatures — verify which cogs in this section actually call which before touching either.

### 3. Inline embeds vs embed_helper
Already mostly consistent (e.g. `animanga_completion_checker.py`: 11 builder calls vs 1 inline).
Inline `discord.Embed()` counts: `browse.py` 5 (lines 284, 350, 528, 576, 632 — several are transient
loading/progress messages, low value to extract), `recommendations.py` 3 (309, 772, 788), `random.py` 2
(217, 295), others 1 each. Low priority relative to categories 2/4 — touch only the main result embeds
(`browse.py:284/350`, `random.py:217`, `recommendations.py:309`).

### 4. Error handling (biggest structural gap vs. Gaming)
No section-wide decorator exists at all (Gaming had `@gaming_error_handler`, just underused — Media has
nothing). Per user decision, build one. Additionally: **10 bare `except:`** (no exception type — worse
than Gaming's bare `except Exception:` since it also catches `SystemExit`/`KeyboardInterrupt`):
`recommendations.py:406,437,468,499,531` (5 in one file), `three_by_three.py:886,905`. (`news.py`'s
3 bare excepts at 889/1237/1263 are moot — that file is being deleted.)

### 5. Function length
- `browse.py:253` `search()` — **416 lines**, largest in the section. Contains an entire nested View
  class (`__init__` at line 391 through `on_timeout` at line 664, ~277 lines) defined *inside* the
  command function. **Unlike Gaming's closures, this nested class takes its dependencies as explicit
  constructor parameters** (`embed1, media_data, real_type_val, guild_id, bot`), not captured
  outer-scope variables — a **safe** extraction to a module-level class. Different risk profile than
  Gaming; do the extraction.
- `browse.py:546` `rebuild_buttons()` (116 lines) — part of the same nested class, moves with it.
- `three_by_three.py:784` `generate_3x3()` (161 lines), `recommendations.py:729` `recommendations()`
  (135 lines), `animanga_completion_checker.py:460` `post_updates()` (112 lines), `three_by_three.py:548`
  `fetch_media_by_id()` (106 lines) — not inspected in depth yet. Apply the convention doc's judgment
  call during implementation (don't split single cohesive algorithms; do split fetch+format+send
  tangles) rather than committing to a specific split here.

### 6. Duplicated DB lookups
`browse.py` and `random.py` both hand-parse a raw DB tuple (`user[4]` for `anilist_username`, comment:
"Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)") instead
of named access. `recommendations.py:744-747` does the same via a local (function-scoped, not
module-level) `from database import get_user_guild_aware` import, then the same `user_data[4]` pattern.
Three files, three copies, fragile magic-number indexing. Consolidate into one named-access helper.

### 7. Dead code
`browse.py:179` `build_sorted_user_progress_list()` — confirmed zero call sites anywhere in the file.
Delete. **Caution**: a broad heuristic scan also flagged ~20 other functions as "unreferenced" — these
are false positives, invoked via discord.py decorator/framework hooks (`@tasks.loop`'s `before_loop`/
`error`, `on_timeout` overrides, `autocomplete=` parameters). Verify zero occurrences of the name
*anywhere including decorator arguments* before flagging anything else as dead, same discipline as
confirming `_create_recommendation_embed` was dead in the Gaming pass.

## Mandatory Reading

| Priority | File | Why |
|---|---|---|
| P0 | `Lemegeton_v2/docs/cog-refactor-convention.md` | The checklist and gotchas this pass follows |
| P0 | `Lemegeton_v2/helpers/gaming_utils.py` (lines 141-247) | Pattern to mirror for the new `media_error_handler` |
| P0 | `Lemegeton_v2/helpers/media_helper.py` | Existing `fetch_user_progress()` (line 49) that categories 2/6 consolidate into |
| P1 | `Lemegeton_v2/cogs/media/browse.py` | Largest file, most findings (categories 2, 5, 6, 7 all present) |
| P1 | `Lemegeton_v2/helpers/anilist_helper.py` (lines 185, 233, 354) | `fetch_media_by_id()`/`fetch_media_by_search()`/`fetch_user_stats()` — the helpers category 2 routes calls through |
| P2 | `Lemegeton_v2/cogs/media/news.py` | To be deleted — confirm scope before deleting (2 commands, background task, View/Modal classes) |
| P2 | `Lemegeton_v2/requirements.txt` (lines 10-11) | `snscrape` dependency + comment to remove |

## NOT Building
- No `database.py` schema changes — `news_accounts`/`news_filters`/`news_metadata` tables become
  orphaned but stay in place.
- No merging of the two different `fetch_media_by_id()` functions (rename for clarity only).
- No deep restructuring of `trailer.py`/`trending.py`/`animanga_completion_checker.py` beyond what
  categories 2-7 concretely surface during implementation reading — not deep-read at design time.
- No changes to any other Media section beyond these 7 files (Account, Admin, Server Management,
  Social, Utilities remain untouched, as before).

## Step-by-Step Tasks

### Task 1: Delete news.py and its dependency
- **ACTION**: Delete `Lemegeton_v2/cogs/media/news.py`. Remove the `snscrape==0.7.0.20230622` line and
  its preceding comment from `Lemegeton_v2/requirements.txt`.
- **VALIDATE**: `grep -rn "news" Lemegeton_v2/bot.py Lemegeton_v2/cogs/` (excluding the deleted file)
  returns no cog-loading or cross-reference matches.

### Task 2: Build media_error_handler
- **ACTION**: Create `Lemegeton_v2/helpers/media_utils.py` mirroring `gaming_utils.py`'s structure:
  typed exceptions for AniList/media failures (e.g. `MediaAPIError`, `MediaNotFoundError`,
  `RateLimitError` — name per what `anilist_helper.py` actually raises/returns, verify during
  implementation rather than assuming Gaming's exact exception set applies) and a
  `media_error_handler` decorator following the same interaction-extraction + typed-except pattern.
- **MIRROR**: `helpers/gaming_utils.py:141-247`.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/helpers/media_utils.py`.

### Task 3: Wire media_error_handler onto all Media commands
- **ACTION**: Add the decorator to all 10 remaining commands across the 7 files.
- **VALIDATE**: grep confirms decorator present on every `@app_commands.command` in `cogs/media/`.

### Task 4: Consolidate duplicate AniList progress fetch (category 2)
- **ACTION**: Replace `browse.py`'s and `random.py`'s inline MediaList progress queries with calls to
  `media_helper.fetch_user_progress()`.
- **GOTCHA**: Confirm the helper's caching/return shape matches what both call sites currently expect
  before swapping — don't assume identical signatures without checking.

### Task 5: Consolidate anilist_username DB lookup (category 6)
- **ACTION**: Add a named-access helper (in `media_helper.py` or `database.py`, per what fits existing
  conventions) replacing the `user[4]`/`user_data[4]` raw-tuple indexing in `browse.py`, `random.py`,
  `recommendations.py`.
- **VALIDATE**: grep for `[4]` indexing on user tuples in the 3 files returns zero matches after the
  change.

### Task 6: Fix bare excepts (category 4)
- **ACTION**: Replace the 7 remaining bare `except:` (`recommendations.py` ×5, `three_by_three.py` ×2)
  with typed handling distinguishing network/API failures from parse/logic failures, logged at
  `warning` where currently silent.

### Task 7: Extract browse.py's nested View class (category 5)
- **ACTION**: Move the View class currently nested inside `search()` (lines ~391-664) to module level
  as a named top-level class, since it already takes dependencies as explicit constructor parameters.
- **GOTCHA**: Verify no remaining closure-captured variable was missed before finalizing — re-read the
  class after extraction to confirm every reference is either a constructor param or an import.

### Task 8: Remove dead code (category 7)
- **ACTION**: Delete `browse.py`'s `build_sorted_user_progress_list()` after confirming zero references
  (including non-call references like decorator args).

### Task 9: Rename the colliding fetch_media_by_id (category 2/7 overlap)
- **ACTION**: Rename `three_by_three.py`'s `fetch_media_by_id()` to something reflecting its narrower
  contract (e.g. `fetch_media_cover_cached()` or similar — exact name is an implementation-time call,
  just avoid the collision with `anilist_helper.py`'s function of the same name).

### Task 10: Light embed_helper touch-up (category 3)
- **ACTION**: Route `browse.py:284/350`, `random.py:217`, `recommendations.py:309`'s main result embeds
  through `embed_helper.py` builders (new builder functions if none fit). Leave transient
  loading/progress embeds inline.

## Testing Strategy
No automated test suite exists. Validation: `python -m py_compile` on every touched file; a real
`importlib.import_module()` test inside a running `asyncio` event loop (per the convention doc —
`gaming_utils.py`-style modules schedule background tasks at import time); reference-cleanup greps for
removed patterns; manual smoke test flagged as a required follow-up (no bot token available to the
implementer).

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `media_error_handler`'s exception set doesn't match what `anilist_helper.py` actually raises, making the decorator a no-op | Medium | Low (defense-in-depth layer, not the only error handling) | Task 2 explicitly calls for verifying against real code rather than copying Gaming's exception names blindly |
| `browse.py`'s nested View class extraction misses a captured variable | Low-Medium | Medium (broken carousel navigation) | Task 7's explicit re-read-after-extraction gate |
| Deleting `news.py` breaks something not caught by the isolation check | Low | Low-Medium | Pre-design grep confirmed only `database.py` (own tables, untouched) and a requirements.txt comment reference it |

## Next Step
Implement directly (user has established the pattern of approving in-chat and implementing without a
separate `/prp-implement` invocation for this Phase 2 series) — or run `/prp-implement` against this
file if the user prefers that explicit step.

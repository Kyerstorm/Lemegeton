# Design: Lemegeton V2 Phase 2 — Gaming Section Refactor (Template Pass)

## Status
Approved by user 2026-09-19. Ready for implementation planning via `writing-plans`.

## Context

This is Phase 2 of the Lemegeton V2 effort. Phase 1 (see `.claude/PRPs/plans/completed/lemegeton-v2.plan.md` and `.claude/PRPs/reports/lemegeton-v2-report.md`) created `Lemegeton_v2/` as a copy-then-trim of the original bot, removing the dashboard command-management system and the cosmetic theme system, and resolving three undocumented-command decisions (kept `lolilist.py`, kept `convertlinks.py`, cut `library_backup.py`). That left `Lemegeton_v2/` with 40 commands across 7 sections and an accurate `CLAUDE.md`.

Phase 2's stated goal is "architecture simplification, performance/reliability, and code quality" — a goal broad enough to span the entire remaining codebase. Rather than attempt a whole-bot pass in one design, the user chose to scope Phase 2 as a series of section-by-section refactors, starting with one section as a **template**: establish the pattern once, thoroughly, then repeat it for the remaining 6 sections in later phases.

## Decisions Made (via clarifying questions, do not re-litigate during implementation)

| Decision | Answer |
|---|---|
| Scope shape | One section first, as a template for later phases (not a whole-bot pass, not a single cross-cutting concern) |
| First section | Gaming (`cogs/gaming/`: `steam_profile.py`, `steam_recommendation.py`, `steam_game.py`, `free_games_checker.py` — 4 files, 6 commands, ~3486 lines) |
| Motivation | Maintainability ("hard to maintain/extend") + general cleanliness — no single named bug driving this |
| Interface freedom | Internals (helper signatures, file structure) are fair game to change; user-visible command behavior/output must not change |
| Database scope | Off-limits for this pass — no `database.py` schema changes. (The two ad-hoc `*_backup` tables flagged in Phase 1 are a separate, still-unaddressed item, not part of this design.) |
| Definition of done | CLAUDE.md's "Command Review Guidelines" checklist, weighted toward reliability/error-handling over the other categories |
| Convention doc | Yes — this pass produces a short "how we refactor a cog section" doc for reuse in later phases |
| Known failure modes | None specifically reported by the user — treat Steam API reliability generally (timeouts, rate limits, malformed responses all equally worth handling) |
| Review checkpoint | None mid-pass — implement, write the convention doc, and report everything together |
| Chosen approach | **Approach B: full Command Review Guidelines pass** across all 7 checklist categories (see Approaches Considered below) |

## Investigation Findings (evidence gathered before design, cite these during implementation)

A read-only analysis of the 4 Gaming cog files plus `helpers/steam_helper.py`, `helpers/gaming_utils.py`, `helpers/embed_helper.py`, `helpers/command_logger.py` found:

### 1. Duplicate import-fallback boilerplate
- `steam_profile.py:13-65` (53 lines) — triple-nested try/except re-importing the same 4 modules 3 times with `sys.path` manipulation
- `steam_recommendation.py:11-48` (38 lines) — identical pattern
- `steam_game.py:16-21` — simpler variant: unconditional `sys.path.insert` + single flat import block
- `free_games_checker.py` — **no path hack at all**, flat top-level imports — proves the hack is unnecessary (`bot.py`'s cog loader already ensures `repo_root` is resolvable at import time)

### 2. Direct API calls bypassing existing helpers (highest-value finding)
`helpers/steam_helper.py` already defines clean, error-handled wrapper functions duplicated inline by the cogs:
- `resolve_vanity_url()` (steam_helper.py:126-139) vs. `steam_profile.py:102-111`, the wishlist block (`:1132-1145`), and `steam_recommendation.py` — all re-implement vanity resolution via direct `safe_json()` calls
- `get_player_summaries()` (steam_helper.py:142-155) vs. `steam_profile.py:113-116`, `:1150-1157`
- `get_owned_games()` (steam_helper.py:174-191) vs. `steam_profile.py:144-148`, `steam_recommendation.py:123-125`
- ~15-20 duplicated call sites total

### 3. Inline embed creation bypassing embed_helper
- `steam_profile.py` — 14 raw `discord.Embed(...)` constructions (e.g. lines 209, 463, 472, 534, 599, 678, 732) with hardcoded colors; only error paths use `build_error_embed`/`build_warning_embed`
- `steam_recommendation.py:433-438` — main recommendation embed built inline with manual color logic (lines 417-431)
- `steam_game.py:118` (`create_carousel_embed`, 130 lines) — same pattern

### 4. Error handling / reliability gaps (top priority)
- `@gaming_error_handler` (typed exceptions `SteamAPIError`/`ProfilePrivateError`/`ProfileNotFoundError`/`RateLimitError`, `helpers/gaming_utils.py:143-168`) exists but is applied to only 3 of 6 commands: present on `steam-profile` (`steam_profile.py:76`) and `steam-wishlist` (`:1096`); **missing** from `steam-recommendation` (`steam_recommendation.py:57`), `steam-game` (`steam_game.py:368` — doesn't even import it), and both free-games commands (`free_games_checker.py:936`, `:1017`)
- `steam_profile.py:280-289` — bio scrape: bare `except Exception: logger.debug(..., exc_info=True)`, silently swallows all failures
- `steam_profile.py:168-186` — badge count scrape: same bare-except pattern
- `steam_recommendation.py:178-383` (`_generate_recommendations`, 206 lines) — ~15-65 sequential `safe_json` calls with zero retry/backoff; a flaky response mid-loop silently `continue`s with no user-visible indication
- `steam_recommendation.py:392-401` — embed builder logs the error but still builds a degraded embed instead of surfacing a clean failure
- `steam_profile.py:280-346` (`toggle_cb`) — nested try/except that can silently no-op (lines 338-346: catches a resend failure, tries a warning embed, and `pass`es with no log at all if that also fails)
- `free_games_checker.py` — **already the quality bar**: proper try/except + status-code checks + explicit timeouts throughout (`fetch_epic_free_games` lines 34-145, `fetch_steam_free_games` lines 219-515)

### 5. Function length / complexity
- `steam_profile.py:78` `steam_profile()` — 231 lines
- `steam_recommendation.py:178` `_generate_recommendations()` — 206 lines
- `steam_recommendation.py:76` `steam_recommendation()` — 101 lines
- `steam_game.py:118` `create_carousel_embed()` — 130 lines
- `steam_game.py:374` `steam_game()` — 115 lines
- `free_games_checker.py:219` `fetch_steam_free_games()` — 297 lines (largest in the section — left alone per scope, see Approach notes)
- `free_games_checker.py:1150` `check_free_games()` — 153 lines
- `free_games_checker.py:1019`, `:524` — 130 and 111 lines

### 6. Database access patterns (no schema changes — logic consolidation only)
- `steam_profile.py:86`, `:1112` — inline `aiosqlite.connect(DB_PATH)` + raw SQL for "get my linked Steam account," duplicated verbatim
- `steam_recommendation.py:97` — same inline connect, plus an extra guild-scoped-then-global fallback (lines 101-112) not present in the other two — same intent, three different implementations
- `free_games_checker.py` — already uses `database.execute_db_operation()` per CLAUDE.md convention — the target pattern

### 7. Duplicate validation/parsing logic
- Vanity-URL-vs-SteamID64 detection (`if user and not user.isdigit()`) reimplemented independently in `steam_profile.py:102` and the wishlist block (`:1132`/`:1146`); `steam_recommendation.py` doesn't support vanity URLs at all (steamid-only, inconsistent with the other two)

## Approaches Considered

**Approach A — Reliability + duplication only** (categories 2/4/6/7, skip 3/5): smaller diff, faster, lower risk, but partial template — later sections would need a second pass for structural/cosmetic categories.

**Approach B — Full Command Review Guidelines pass** (all 7 categories): larger diff and review burden, but since this file is explicitly the template for 6 more sections, doing it shallowly here pushes the same rework onto every future phase. **Chosen.**

**Approach C — Error handling only**: lowest risk, fastest, but leaves the largest actual finding (helper-call duplication, category 2) untouched and barely functions as a template beyond one narrow dimension.

## Design

### Architecture
No new files, no new subsystems. The fix is **consolidation into existing infrastructure** — `steam_helper.py` and `gaming_utils.py` already contain the right abstractions (API wrappers, typed exceptions, an error-handling decorator); the cog files simply don't consistently use them. `free_games_checker.py` stays effectively untouched — it is already the reference implementation for this section. One new helper function is added to `steam_helper.py` to eliminate triplicated DB-lookup logic; everything else is cogs calling helpers that already exist.

### Components — per-file changes

**`steam_profile.py`** (1201 lines):
- Remove the 53-line import-fallback block → flat imports (mirror `free_games_checker.py`'s style)
- Replace inline `safe_json()` Steam API calls with `resolve_vanity_url()` / `get_player_summaries()` / `get_owned_games()`
- `@gaming_error_handler` already present on both commands in this file — verify, no change needed
- Replace the two bare-except scrape blocks (bio scrape, badge count scrape) with handling that distinguishes expected vs. unexpected failures and logs at the appropriate level instead of silently swallowing
- Split the 231-line `steam_profile()` handler into fetch / build-embed / build-views stages
- Route the 14 inline `discord.Embed()` calls through new `embed_helper.py` builder(s) shaped for this cog's embeds
- Replace the 2 duplicated DB lookups with the new `get_linked_steamid()` helper
- Fix `toggle_cb`'s silent double-failure `pass` (lines 338-346) to log at minimum

**`steam_recommendation.py`** (463 lines):
- Remove the 38-line import-fallback block
- Add `@gaming_error_handler` (currently missing)
- Replace inline API calls with the `steam_helper.py` wrappers
- Split `_generate_recommendations()` (206 lines) into preference-analysis / candidate-search / scoring stages
- Fix the swallow-then-degrade pattern at the embed-builder step (~line 392) to raise/surface a clear error instead of building a degraded embed silently
- Replace its DB lookup with `get_linked_steamid(discord_id, guild_id)` — the existing guild-then-global fallback behavior is preserved as a parameter on the shared helper, not dropped
- Add vanity-URL support via `resolve_vanity_url()` to match the other two entry points (currently steamid-only)

**`steam_game.py`** (501 lines):
- Add the missing `gaming_utils` import + `@gaming_error_handler` decorator on `steam-game`
- Split `create_carousel_embed()` (130 lines) and the 115-line command handler into smaller pieces

**`free_games_checker.py`** (1321 lines):
- Add `@gaming_error_handler` to its 2 commands for uniformity with the rest of the section (it already has solid manual error handling — this is a consistency change, not a gap fix)
- Otherwise left alone — it is the quality bar the other 3 files are being brought up to, not a file needing the same treatment. Do not restructure its already-correct `fetch_steam_free_games()`/`fetch_epic_free_games()` functions beyond the decorator addition, even though `fetch_steam_free_games()` (297 lines) is technically the longest function in the section — splitting a function that already works correctly and isn't part of the identified problem is out of scope for this pass.

**`helpers/steam_helper.py`**:
- Add `get_linked_steamid(discord_id: int, guild_id: Optional[int] = None) -> Optional[tuple]` — consolidates the 3 duplicated DB lookups, preserving `steam_recommendation.py`'s guild-then-global fallback as the general behavior when `guild_id` is provided

**`helpers/embed_helper.py`**:
- Add builder function(s) for the Gaming section's embed shapes (profile embed, recommendation embed, carousel embed) — exact function signatures are an implementation-planning detail, not fixed here

### Data Flow
Unchanged from the user's perspective — same command produces the same Discord response. Internally: command handler → resolve identity (`get_linked_steamid()` or `resolve_vanity_url()`) → fetch data (`steam_helper.py` wrappers, each handling its own retries/timeouts) → build embed (`embed_helper.py` builders) → send. `@gaming_error_handler` becomes the single place catching `SteamAPIError`/`ProfilePrivateError`/`ProfileNotFoundError`/`RateLimitError` and converting them to consistent user-facing messages, replacing each command's ad hoc handling.

### Error Handling (central focus of this pass)
- All 6 Gaming commands get `@gaming_error_handler`
- Both bare `except Exception: logger.debug(..., exc_info=True)` silent-swallow spots get replaced with handling that distinguishes expected failures (private profile, not found) from unexpected ones (network/parse errors) and logs at the correct level
- The recommendation embed builder stops silently degrading on malformed data; it raises so the decorator produces a proper user-facing error instead

### Testing
No automated test suite exists in this codebase (confirmed in Phase 1 — no `tests/` dir, no pytest config). Validation for this pass:
- `python -m py_compile` on every touched file
- A reference-cleanup grep confirming no orphaned imports from the removed try/except fallback blocks
- **Manual smoke test strongly advisable but not performed by the implementer without a live Discord bot token**: exercise all 6 Gaming commands against a real guild before considering this pass fully verified. This is flagged explicitly rather than silently skipped, since this pass touches actual runtime logic (not just decorator stripping, unlike Phase 1).

## NOT Building (explicit out-of-scope for this pass)
- No changes to `database.py` schema, `steam_users` table structure, or any other table
- No restructuring of `free_games_checker.py`'s already-correct fetch functions beyond adding the error-handler decorator
- No changes to the other 6 sections (Account, Admin, Media, Server Management, Social, Utilities) — this is a template pass for Gaming only
- No new automated test suite (out of scope for this pass; the absence is noted, not fixed here)
- No change to user-visible command behavior, output formatting, or embed *content* (only embed *construction method* changes — from inline to helper-based)

## Deliverable: Convention Doc
As part of implementing this design, produce a short "how we refactor a cog section" document capturing: the 7-category checklist as applied here, the specific before/after patterns (import style, API-call-via-helper, error-handler wiring, DB-lookup consolidation, embed-builder routing, function-splitting threshold), and pointers to this Gaming refactor as the worked example. Location and exact format are an implementation-planning detail — likely `Lemegeton_v2/docs/cog-refactor-convention.md` or similar, to be determined during planning.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Behavior drift while consolidating 3 duplicated implementations into 1 (e.g. `get_linked_steamid()` losing `steam_recommendation.py`'s guild-then-global fallback nuance) | Medium | Medium (wrong Steam account resolved in some edge case) | Design explicitly calls out preserving the fallback as a parameter; implementation should test both call patterns (with and without guild fallback) |
| No automated tests and no bot token available to the implementer means regressions in complex flows (e.g. the 206-line recommendation scoring logic) could go undetected until a human tests it | Medium | Medium | Explicit manual-smoke-test flag in Testing section; recommend the user test before merging |
| Splitting long functions introduces subtle bugs if state/closures aren't threaded through correctly | Low-Medium | Medium | Compile-check catches syntax issues; careful review of each split function's inputs/outputs during implementation |

## Next Step
Invoke `writing-plans` to turn this design into a step-by-step implementation plan.

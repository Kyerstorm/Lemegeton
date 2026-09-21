# Design: Lemegeton V2 Phase 2 — Utilities Section Refactor

## Status
Investigated 2026-09-21. Ready for implementation.

## Context
Sixth and final section of Lemegeton V2's Phase 2 (Gaming, Media, Social, Account, Server Management
already complete — see `.claude/PRPs/reports/lemegeton-v2-{gaming,media,social,account,server-management}-refactor-report.md`
and their design docs in `.claude/PRPs/plans/completed/`). Applies the same 7-category checklist to the 8
files in `cogs/utilities/` (3,444 lines total): `convertlinks.py` (244), `help.py` (817), `invite.py` (172),
`notifications.py` (451), `planned_features.py` (975), `say.py` (202), `timestamp.py` (255), `userinfo.py` (324).

## Decisions Made (do not re-litigate during implementation)
| Decision | Answer |
|---|---|
| Ground rules | Same as prior five passes: full 7-category checklist, reliability/error-handling weighted highest, internals free to change, command/listener behavior and output unchanged |
| `reminders.py` gap | Confirmed **absent** from `Lemegeton_v2/cogs/utilities/` — only referenced in `database.py`'s table-init list, `README.md`, and `start.bat`. CLAUDE.md's original section listing still names it. This was never ported into V2's `cogs/utilities/` at all (predates this Phase 2 series — no evidence it was cut deliberately in Phase 1 either). **Do not build it.** Flag as an open gap for the user in the report, same as the `convertlinks.py` question below — not this pass's job to invent a reminders feature |
| `convertlinks.py`'s unresolved Phase 1 status | The original Phase 1 plan (`lemegeton-v2.plan.md`, "Open Question for User") flagged `convertlinks.py` as undocumented and never got an explicit keep/cut answer. **Do not unilaterally delete or restructure its functionality** — treat it like any other file for the 7-category cleanup (code quality only), and re-flag the keep/cut decision in this report's Next Steps, exactly as the original plan required |
| `planned_features.py`'s `!planned` prefix command | `@commands.command`, not `@app_commands.command` — no `utilities_error_handler` wiring (same "prefix commands don't get the decorator" rule Account applied to `admin_login_prefix`). This file has **zero** app commands, so it gets zero decorator wiring |
| `help.py`'s and `planned_features.py`'s main content embeds | Bespoke, large, data-driven (command reference text / feature listings) — same "too bespoke to safely extract without behavior drift" judgment call Account made for `profile.py`'s main embed and Server Management made for `serverinfo.py`'s pages. **Leave inline** |
| `userinfo.py`'s `create_darlux_embed` Dark Luxury system | Same precedent as `serverinfo.py` (Server Management pass) — a self-contained, differently-themed builder, not an `embed_helper.py` violation. **Do not touch** |

## Investigation Findings (7-category checklist, evidence gathered before design)

### 1. Import boilerplate
- `timestamp.py:16-20` — a function-local... actually **module-level** `import sys` + `sys.path.insert(0, str(repo_root))` hack, done solely to import `helpers.command_logger.log_command`. Identical pattern to Account's `login.py` fix (Phase 2, Account pass, Task 4): every other cog in this codebase imports `helpers.*` directly with no sys.path hack (repo root is already on `sys.path` via `bot.py`). Dead weight — replace with a direct `from helpers.command_logger import log_command`.
- No other file in this section has import boilerplate to remove.

### 2. Direct API calls duplicating helpers
Not applicable — `convertlinks.py`'s `fetch_anilist_user_id()` calls already go through `helpers/anilist_helper.py` correctly; no other file makes AniList/Steam API calls at all.

### 3. Inline embeds vs embed_helper
- `invite.py` — **zero `embed_helper` import**, 2 raw `discord.Embed()` calls (the main invite embed, and its exception-path error embed). Clear, low-risk candidate: route the error embed through `build_error_embed()`. The main embed is the command's sole bespoke output (not a status/success template) — leave it inline, same as every prior pass's "main content embed" allowance, but note the file could adopt `build_error_embed` for its one error path trivially.
- `notifications.py` — **zero `embed_helper` import**, ~10 raw `discord.Embed()` sites across the top-level `/notifications` command (2: success-path overview + exception-path error) and `NotificationTypeView`/`NotificationTypeSelect`'s button/select callbacks (~8, each a small state-change result). Per established precedent (Server Management's `InviteThemeView`, Account's per-page views): touch only the **top-level command's own 2 embeds** (its normal display + its exception handler), leave the view/select callback embeds inline — same "main output only" scoping every prior pass used for multi-state interactive views.
- `timestamp.py` — 1 raw `discord.Embed()`, the command's sole output. Low-risk, single call site — route through a light embed_helper touch, OR leave as the command's bespoke main-content embed (judged during implementation same as `invite.py`'s main embed; default to leaving it since it's the *only* output and has no error-path/status-path duplication to unify).
- `say.py` — 1 raw `discord.Embed()`, but it wraps **user-authored message content** the moderator is asking the bot to say — this is not bot status/UI, it's the payload. **Do not route through embed_helper** (would be a category error, same as leaving Media/Social's user-content embeds alone).
- `help.py` — already imports and uses `build_error_embed`/`build_warning_embed` for its 2 error/permission paths. Its 2 main content embeds (overview, category) are bespoke reference documents — leave inline (see Decisions Made).
- `planned_features.py` — many raw `discord.Embed()` calls, all bespoke feature-listing/confirmation content tied tightly to this file's own status/category badge system (`STATUS_CONFIG`/`CATEGORY_CONFIG` color mapping) — leave inline (see Decisions Made).
- `userinfo.py` — bespoke Dark Luxury system, out of scope (see Decisions Made).

### 4. Error handling
No section-wide decorator exists. **6 live bare `except:`** found — the richest count since Gaming/Media/Social's original 7-each (larger than Account's 1 and Server Management's 0):
- `convertlinks.py:91, 104, 149, 156, 213` — all in `AddMoreView.done()`'s DM-sending/progress-update flow (notify-user-of-dedup, initial DM, progress-bar edit, final-results DM ×2). Each is a genuine "best-effort, DM might be closed/blocked" pattern — same class as Account's `profile.py:579` bare except. Type and log each (`except Exception`, `logger.debug`/`warning`), preserving the exact same swallow-and-continue (or swallow-and-fallback-message) behavior at each site.
- `timestamp.py:56` — inside `validate_time_format()`'s `int()` parsing (catches malformed hour/minute strings). Type as `except ValueError`.

App commands eligible for `utilities_error_handler` (7 total, across 6 files):
- `convertlinks.py`: `convertlinks`
- `say.py`: `say`
- `timestamp.py`: `timestamp`
- `invite.py`: `invite`
- `userinfo.py`: `user`
- `notifications.py`: `notifications`
- `help.py`: `help`
- `planned_features.py`: **none** (prefix-only, see Decisions Made)

New file `helpers/utilities_utils.py`, mirroring `social_utils.py`/`account_utils.py`/`server_management_utils.py` (rename to `Utilities`-flavored names, log file `logs/utilities.log`, logger name "Utilities").

### 5. Function length
- `convertlinks.py`'s `AddMoreView.done()` — ~85 lines (76-160): dedup links → DM initial progress message → loop-convert-with-progress-bar-updates → DM final summary → confirm. A clear fetch+process+send tangle, same shape as prior passes' splits. Candidate to split into named steps (`_deduplicate_links`, `_send_initial_progress`, `_convert_all_links`, `_send_results`), judged during implementation for exact seams (progress-message object is threaded through the loop, needs care).
- No other function in this section exceeds ~80 lines; `help.py`'s methods are already well-decomposed; `planned_features.py`'s modal/view methods are each single-purpose and reasonably sized despite the file's overall length (975 lines is many *small* classes, not one large function).

### 6. Duplicated logic (CLAUDE.md's Review Checklist category 1/6 combined — no DB-lookup duplication found here, but two real code-duplication findings)
- `planned_features.py`'s `AddFeatureModal.on_submit()` and `EditFeatureModal.on_submit()` both hand-roll an **identical category-normalization dict** (`category_map = {...}`, 8 entries) and identical status-normalization logic (~15 lines duplicated verbatim in each). Extract to a shared cog method (e.g. `_normalize_category(raw: str) -> str`, `_normalize_status(raw: str) -> str`).
- `planned_features.py`'s `EditFeatureView.create_and_add_select_menu()` and `RemoveFeatureView.create_and_add_select_menu()` duplicate ~30 lines of identical option-building/truncation logic (label/description truncation to Discord's 100-char limits, "no features available" fallback option). Extract to a shared helper (e.g. a module-level `_build_feature_select_options(features: list) -> list[discord.SelectOption]` function, since both classes need it and neither owns the other).
- No `anilist_username`/other cross-file shared-field duplication found in this section (different domain).

### 7. Dead code
**None found.** No commented-out blocks, no unused classes/functions confirmed via grep across all 8 files (unlike Server Management's ~50-line deprecated block). This category is a no-op for this pass.

## Mandatory Reading
| Priority | File | Why |
|---|---|---|
| P0 | `.claude/PRPs/reports/lemegeton-v2-{account,server-management}-refactor-report.md` | The checklist, gotchas, and adapted-decorator precedent this pass follows |
| P0 | `Lemegeton_v2/helpers/social_utils.py` or `server_management_utils.py` | Pattern to mirror for `utilities_error_handler` |
| P1 | `Lemegeton_v2/cogs/utilities/convertlinks.py` | Richest findings — categories 4 (5 bare excepts), 5 (function split) |
| P1 | `Lemegeton_v2/cogs/utilities/planned_features.py` | Largest file, category 6's two duplication findings |
| P2 | `Lemegeton_v2/cogs/utilities/notifications.py`, `invite.py`, `timestamp.py` | Category 3 candidates (light embed_helper touch-ups) |
| P2 | `Lemegeton_v2/cogs/utilities/say.py`, `help.py`, `userinfo.py` | Lightest touch — decorator only (say, help) or decorator + judgment calls already resolved (userinfo, help) |

## NOT Building
- No `reminders.py` cog (flagged gap, not this pass's job — see Decisions Made).
- No unilateral keep/cut decision on `convertlinks.py`'s existence (flagged, not decided — see Decisions Made).
- No embed_helper migration for `say.py`'s user-authored-content embed, `help.py`'s/`planned_features.py`'s bespoke content embeds, or `userinfo.py`'s Dark Luxury system.
- No database schema changes; no new `database.py` helpers needed (no DB-lookup duplication found in this section, unlike Server Management's Task 6).
- No changes to any other section — this closes out Phase 2 entirely (no sections remain after Utilities).

## Step-by-Step Tasks

### Task 1: Build utilities_error_handler
- **ACTION**: Create `Lemegeton_v2/helpers/utilities_utils.py` mirroring `social_utils.py`/`server_management_utils.py`.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/helpers/utilities_utils.py`.

### Task 2: Wire decorator onto the 7 app commands
- **ACTION**: Add to `convertlinks`, `say`, `timestamp`, `invite`, `user` (userinfo.py), `notifications`, `help`. Do not add to `planned_features.py`'s `!planned`.
- **VALIDATE**: grep confirms decorator present on exactly these 7 commands.

### Task 3: Fix the 6 bare excepts (category 4)
- **ACTION**: Type and log `convertlinks.py:91,104,149,156,213` and `timestamp.py:56` per the Investigation Findings — preserve each site's exact swallow/fallback behavior.
- **VALIDATE**: `grep -rn "except:\s*$" Lemegeton_v2/cogs/utilities/` returns zero matches.

### Task 4: Import boilerplate cleanup (category 1)
- **ACTION**: Replace `timestamp.py`'s `sys.path.insert` block with a direct `from helpers.command_logger import log_command`.
- **VALIDATE**: `grep -n "sys.path.insert" Lemegeton_v2/cogs/utilities/timestamp.py` returns zero matches; `python -m py_compile Lemegeton_v2/cogs/utilities/timestamp.py`.

### Task 5: Light embed_helper touch-up (category 3)
- **ACTION**: Route `invite.py`'s exception-path error embed through `build_error_embed()`. Route `notifications.py`'s top-level `/notifications` command's 2 embeds (normal display + exception handler) through `embed_helper.py` builders (new or existing) — leave its view/select callback embeds untouched. Judge `timestamp.py`'s single embed live; leave inline unless a trivial win presents itself without behavior drift.
- **VALIDATE**: `python -m py_compile` on all 3 touched files; embed content/fields unchanged.

### Task 6: Extract duplicated logic in planned_features.py (category 6)
- **ACTION**: Add `_normalize_category()`/`_normalize_status()` cog methods, route both modals' `on_submit()` through them. Add a shared `_build_feature_select_options()` helper, route both `EditFeatureView`/`RemoveFeatureView` through it.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/cogs/utilities/planned_features.py`; both modals/views produce identical results before/after for the same inputs.

### Task 7: Dead code removal (category 7)
- **ACTION**: N/A — investigation found none in this section.

### Task 8: Function length — judgment-call pass (category 5)
- **ACTION**: Read `convertlinks.py`'s `AddMoreView.done()` in full and split into named steps if the read confirms clean seams (expected, per investigation). Record reasoning in the report.

## Testing Strategy
No automated test suite exists. Validation: `python -m py_compile` on every touched file; a real
`importlib.import_module()` test inside a running `asyncio` event loop; reference-cleanup greps for
removed patterns (`sys.path.insert`, bare `except:`); manual smoke test flagged as a required follow-up
(no bot token available) — `/convertlinks`'s DM-based batch flow and `/say`'s moderator-permission gate
are worth prioritizing given they're the highest-consequence flows in this section.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `convertlinks.py`'s `done()` split accidentally changes the progress-message object's lifecycle (it's edited repeatedly across the loop) | Medium | Medium (progress bar could stop updating or duplicate messages could appear) | Task 8 requires a full re-read before splitting; keep the progress-message object passed explicitly between extracted steps rather than relying on implicit closure state |
| `notifications.py`'s embed_helper migration accidentally pulls a view/select-callback embed into scope instead of just the 2 top-level command embeds | Low | Low (cosmetic only, no functional break) | Task 5 explicitly scopes to "top-level command's own 2 embeds" only |
| `utilities_error_handler`'s typed exceptions are unreachable, same as every prior pass | High (no API-error-raising helpers used in this section either) | Low (defense-in-depth, documented as such) | Task 1 explicitly mirrors the already-adapted pattern |

## Next Step
Implement directly (established pattern for this Phase 2 series) — write the implementation report to
`.claude/PRPs/reports/lemegeton-v2-utilities-refactor-report.md` and note in its Next Steps that this
closes out the entire 6-section Phase 2 series (Gaming, Media, Social, Account, Server Management,
Utilities) — a final cross-section wrap-up summary may be worth offering to the user at that point.

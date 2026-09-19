# Plan: Lemegeton V2 — Trimmed, Simplified Discord Bot

## Summary
Lemegeton V2 is a copy-then-trim rewrite of the existing multi-guild Discord bot, seeded at `Lemegeton_v2/` on the `lemegeton-v2` branch. V2 removes two self-contained subsystems (the dashboard command-management system and the cosmetic theme system), reconciles stale documentation with actual code, and then focuses on architecture simplification, reliability, and code-quality improvements across what remains — without changing the bot's core multi-guild data model.

## User Story
As a server admin running Lemegeton, I want a bot with fewer moving parts and less unused/dead code, so that it's easier to maintain, less likely to break in confusing ways, and just as reliable for the features people actually use.

## Problem → Solution
**Current state**: 43 commands across 33 cog files, a per-guild dashboard enable/disable UI that has no actual runtime enforcement (cosmetic only), a 1,578-line theme system with no cross-cog dependents, several undocumented/orphan commands not mentioned in CLAUDE.md, and documentation (CLAUDE.md) that describes helper functions and enforcement logic that don't exist in the code.
**Desired state**: A leaner bot with the dashboard and theme subsystems fully removed (not just disabled), no dead imports/decorators left behind, accurate documentation, and the remaining ~38 commands/32 files reviewed for simplification opportunities (duplicate logic, oversized functions, inconsistent error handling) per the existing "Command Review Guidelines" in CLAUDE.md.

## Metadata
- **Complexity**: XL (cross-cutting removal across 30+ files, plus an open-ended follow-on simplification pass)
- **Source PRD**: N/A — scoped via direct user clarification (see Decisions below)
- **PRD Phase**: N/A
- **Estimated Files**: ~35 touched in Phase 1 (removal), remainder TBD in Phase 2 (simplification, scoped per-cog later)

---

## Decisions Already Made (do not re-litigate during implementation)

| Decision | Answer |
|---|---|
| How is V2 created? | Copy-then-trim, same repo. `Lemegeton_v2/` already created (branch `lemegeton-v2`, copied from `multi_guild` @ commit `c4b75d7`) as a byte-for-byte copy of `bot.py`, `config.py`, `database.py`, `cogs/`, `cogs_test/`, `helpers/`, `requirements.txt`, `Procfile`, `runtime.txt`, `railway.json`, `railway.toml`, `start.bat`, `README.md`. `data/`, `logs/`, `backup/`, `scripts/`, `under_maintenance/`, `utils/`, `tools/`, `docs/` were **not** copied (dead/auxiliary per `.gitignore` and repo inspection) — pull individual files back in later only if a kept feature turns out to need them. |
| What gets cut? | (1) Dashboard command-management system, (2) Customization/theme system. Confirmed explicitly by user. |
| What's the improvement focus for what remains? | Simplify architecture, improve performance/reliability, improve code quality/maintainability — general direction, not yet scoped to specific cogs. |
| Existing `v2` / `Version-2-Test-Build` branches | Explicitly ignored per user instruction — new branch `lemegeton-v2` used instead; do not touch or reference those branches. |

## Open Question for User (surface before/during implementation, do not silently decide)
The command inventory below turned up **3 commands not mentioned anywhere in CLAUDE.md's documented structure**: `social/lolilist.py` (`lolilist`), `utilities/convertlinks.py`, and `media/library_backup.py`. These may be legitimate undocumented features or abandoned experiments. Flag to the user before Phase 2 simplification: keep, cut, or investigate each.

---

## UX Design
N/A — this is an internal architecture/maintenance change. No new user-facing commands are added; two admin-facing surfaces disappear (`/dashboard`, `/theme` + `/admin-guild-theme`).

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `/dashboard` command | Admins can view/toggle command enable-state per guild via UI | Command removed entirely | No functional loss: investigation confirmed toggles were never enforced at runtime (no `app_command_enabled_check()` exists in the codebase despite CLAUDE.md documenting one) |
| `/theme`, `/admin-guild-theme` | Users/admins pick from 30+ cosmetic embed themes | Commands removed entirely | Embeds fall back to whatever default color scheme cogs use directly (verify no cog broke by assuming a theme was applied — investigation found none do) |
| All other 41 commands | Decorated with `@command_meta(section=..., name=...)` for dashboard discovery | Decorator and its import removed | Metadata tagging only (`setattr`, no wrapping) — command behavior is unaffected |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `bot.py` | 1050-1150 | Cog auto-discovery/loading loop — `cog_dirs = ['cogs', 'cogs_test']` at line 1054 is the single point controlling whether the dashboard cog loads |
| P0 | `cogs_test/general_commands/dashboard.py` | 1-100 | `command_meta` decorator implementation (pure `setattr`, no wrapping — confirms safe removal), `CommandRegistry`, `ConfigDB` (own SQLite file, not `database.py`) |
| P0 | `cogs/account/profile.py` | 19, 567 | Canonical example of the `command_meta` import + decorator pattern repeated in 30 files — use as the template for every strip |
| P1 | `helpers/theme_helper.py` | all (0 lines) | Confirmed empty — CLAUDE.md's documented theme helper API (`apply_theme()`, `get_user_theme()`, etc.) does not exist in code. Delete the file; do not try to "migrate" nonexistent functions. |
| P1 | `cogs/customization/` | all (`themes.py` 1133 lines, `theme_integration.py` 126 lines, `theme_showcase.py` 319 lines) | Self-contained theme system, zero external cog dependents confirmed by grep |
| P1 | `cogs/customization/server_boost.py` | all (256 lines) | **NOT part of the theme cut** — nitro booster role-color command is unrelated to cosmetic embed themes. Keep this file; move it out of `cogs/customization/` before deleting that directory (e.g. to `cogs/social/` or a new `cogs/community/`) so it isn't accidentally deleted with the rest. |
| P2 | `database.py` | ~4351-4352, ~4410-4411 | Stale `dashboard_guild_configs`/`dashboard_audit_log` entries in a guild-data-cleanup utility's table list — these tables are never created here (dashboard uses its own DB file); remove the dead entries while touching this file |
| P2 | `database.py` | ~2081-2087 | Ad-hoc `global_challenges_backup`/`challenge_manga_backup` tables created outside the `init_*_table()` pattern — flag for the Phase 2 simplification pass, not part of dashboard/theme removal |
| P2 | `CLAUDE.md` | Dashboard System, Helper Functions sections | Source of the stale documentation (documents an enforcement mechanism and theme helper API that don't exist) — must be rewritten for V2, not copied as-is |

## External Documentation
No external research needed — this is an internal removal/simplification task using only established patterns already in the codebase (discord.py cog loading, aiosqlite, existing decorator conventions).

---

## Patterns to Remove (mirror this exact shape at each of the 30 call sites)

### DASHBOARD_IMPORT_AND_DECORATOR
```python
// SOURCE: cogs/account/profile.py:19, 567
from cogs_test.general_commands.dashboard import command_meta
...
    @command_meta(section="Account", name="Profile")
    @app_commands.command(name="profile", description="...")
```
Remove the import line and the `@command_meta(...)` line only. Leave `@app_commands.command(...)` and everything else untouched.

### DASHBOARD_COG_LOADING
```python
// SOURCE: bot.py:1053-1054
# Check both cogs and cogs_test directories
cog_dirs = ['cogs', 'cogs_test']
```
Change to `cog_dirs = ['cogs']` and remove the now-inaccurate comment.

### STALE_DASHBOARD_DB_CLEANUP_ENTRIES
```python
// SOURCE: database.py ~4351-4352, ~4410-4411
("dashboard_guild_configs", "guild_id"),
("dashboard_audit_log", "guild_id"),
```
Delete these tuple entries from whatever list they're part of (confirm surrounding context when editing — these are inside a guild-data-cleanup helper's table registry).

---

## Files to Change (Phase 1 — Removal)

| File (all under `Lemegeton_v2/`) | Action | Justification |
|---|---|---|
| `cogs_test/` (entire directory) | DELETE | Dashboard system — cosmetic-only, zero runtime enforcement found |
| `cogs/customization/themes.py`, `theme_integration.py`, `theme_showcase.py` | DELETE | Theme system — zero cross-cog dependents |
| `helpers/theme_helper.py` | DELETE | Already empty; CLAUDE.md's documented API for it doesn't exist |
| `cogs/customization/server_boost.py` | MOVE | Not part of the theme cut — relocate before deleting the rest of `cogs/customization/`, then delete the now-empty directory |
| `bot.py` | UPDATE (line ~1054) | Drop `cogs_test` from `cog_dirs` |
| 30 cog files across `cogs/account/`, `cogs/admin/`, `cogs/gaming/`, `cogs/media/`, `cogs/server_management/`, `cogs/social/`, `cogs/utilities/` (full list: run `grep -rl "command_meta" cogs/` on the V2 copy to enumerate exactly, since this plan's inventory was taken from the pre-copy source) | UPDATE | Strip `command_meta` import + decorator per the pattern above |
| `database.py` | UPDATE (~4351-4352, ~4410-4411) | Remove stale `dashboard_guild_configs`/`dashboard_audit_log` cleanup entries |
| `CLAUDE.md` (new one for `Lemegeton_v2/`, not yet created) | CREATE | Rewrite for V2: remove Dashboard System section, remove/correct theme_helper.py API docs, correct command/table counts using the verified inventory below instead of the stale numbers |

## NOT Building (Phase 1 scope)
- No changes to the multi-guild data model, `(discord_id, guild_id)` composite key pattern, or any of the 34 core tables in `database.py`.
- No decisions yet on `lolilist`, `convertlinks`, or `library_backup` — flagged as an open question above, not auto-cut.
- No Phase 2 (architecture/performance/code-quality) work is scoped by this plan — that requires a follow-up plan once Phase 1 lands and the "reduce commands" scope is clarified further with the user.
- Not touching `server_boost.py`'s functionality, only its file location.

---

## Step-by-Step Tasks

### Task 1: Enumerate exact dashboard call sites in the V2 copy
- **ACTION**: Run `grep -rln "command_meta" Lemegeton_v2/cogs/` to get the authoritative file list (the 30-file count above was taken from the pre-copy source and must be re-verified against the actual `Lemegeton_v2/` tree before editing).
- **VALIDATE**: Count matches expectation (~30 files, 39 decorator occurrences — some files have 2+ commands).

### Task 2: Strip dashboard decorators and imports
- **ACTION**: For each file from Task 1, remove the `from cogs_test.general_commands.dashboard import command_meta` import line and every `@command_meta(...)` line.
- **MIRROR**: DASHBOARD_IMPORT_AND_DECORATOR pattern above.
- **GOTCHA**: Some files may have the import combined with other imports on adjacent lines — remove only the `command_meta` line, not neighboring imports. Some cogs (e.g. `steam_profile.py`, `invite_tracker.py`) have multiple `@app_commands.command` in one file — make sure every decorated command in the file is caught, not just the first.
- **VALIDATE**: `grep -rn "command_meta" Lemegeton_v2/` returns zero matches anywhere (including `bot.py` and `database.py`).

### Task 3: Delete the dashboard cog directory
- **ACTION**: `rm -rf Lemegeton_v2/cogs_test/`
- **GOTCHA**: Confirm Task 2 is fully complete first — deleting this before stripping imports elsewhere will break every cog's import at load time.
- **VALIDATE**: Directory no longer exists; `python -m py_compile Lemegeton_v2/bot.py` still succeeds.

### Task 4: Update bot.py cog loading
- **ACTION**: Change `cog_dirs = ['cogs', 'cogs_test']` to `cog_dirs = ['cogs']` at the line identified in Mandatory Reading. Update the preceding comment.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/bot.py`

### Task 5: Relocate server_boost.py, then remove the theme system
- **ACTION**: Move `Lemegeton_v2/cogs/customization/server_boost.py` to `Lemegeton_v2/cogs/social/server_boost.py` (or another logical home — confirm with user if unsure). Update any relative imports inside it if they assumed the old package path. Then delete `Lemegeton_v2/cogs/customization/themes.py`, `theme_integration.py`, `theme_showcase.py`, and the now-empty `cogs/customization/` directory. Delete `Lemegeton_v2/helpers/theme_helper.py`.
- **GOTCHA**: Check `bot.py`'s cog-discovery loop — it likely auto-discovers by walking `cogs/`, so moving `server_boost.py` to another subpackage should just work without a bot.py change, but confirm by re-reading the loading loop (Mandatory Reading P0) rather than assuming.
- **VALIDATE**: `grep -rn "theme_helper\|cogs.customization.themes\|cogs.customization.theme_integration\|cogs.customization.theme_showcase" Lemegeton_v2/` returns zero matches.

### Task 6: Clean up stale database.py cleanup entries
- **ACTION**: Remove the `dashboard_guild_configs`/`dashboard_audit_log` tuple entries per the STALE_DASHBOARD_DB_CLEANUP_ENTRIES pattern.
- **GOTCHA**: Read enough surrounding context to confirm you're editing the guild-data-cleanup table registry and not accidentally deleting an unrelated entry near it.
- **VALIDATE**: `python -m py_compile Lemegeton_v2/database.py`; `grep -n "dashboard_guild_configs\|dashboard_audit_log" Lemegeton_v2/database.py` returns zero matches.

### Task 7: Full syntax + import validation pass
- **ACTION**: `python -m py_compile` every `.py` file under `Lemegeton_v2/` (loop with `find`/`Get-ChildItem`).
- **VALIDATE**: Zero compile errors across the tree.

### Task 8: Write Lemegeton_v2/CLAUDE.md
- **ACTION**: Copy the root `CLAUDE.md` into `Lemegeton_v2/CLAUDE.md` and edit it: delete the entire "Dashboard System" section, delete/correct the `theme_helper.py` API documentation in "Helper Functions", correct the "Total Commands" and section counts using the verified Task 1 grep results (not the original's stale "43 commands / 8 sections" claim), remove `@command_meta` from the "Cog Structure Pattern" and "Critical Conventions" example code.
- **GOTCHA**: Don't just delete sections — CLAUDE.md's project structure diagram, database table list, and "Common Pitfalls" numbering will need renumbering/adjustment after removing the dashboard-integration pitfall entry.
- **VALIDATE**: Manual read-through; no remaining references to dashboard, `command_meta`, or the nonexistent theme_helper API.

### Task 9: Flag the three undocumented commands to the user
- **ACTION**: Before considering Phase 1 complete, surface `lolilist`, `convertlinks`, and `library_backup` to the user (per the Open Question above) and get an explicit keep/cut/investigate decision for each. Do not decide unilaterally.
- **VALIDATE**: User has responded; decision recorded in this plan or a follow-up note.

---

## Testing Strategy

No automated test suite exists in this codebase (no `tests/` directory or pytest config found). Validation is compile-check + manual smoke test.

### Edge Cases Checklist
- [ ] A cog file with 2+ `@command_meta`-decorated commands (e.g. `steam_profile.py`, `invite_tracker.py`, `welcome_dm.py`, `news.py`, `animanga_completion_checker.py`) has every occurrence stripped, not just the first.
- [ ] `server_boost.py`'s move doesn't break its own internal imports (check for `from . import` or `from cogs.customization import` style relative references).
- [ ] `bot.py`'s cog auto-discovery still finds every remaining cog after `cogs_test` is dropped and `customization/` is deleted.
- [ ] No other file outside the 30 identified in Task 1 has a stray `command_meta` or `theme_helper` reference the grep-based inventory missed (re-run the grep after each deletion, not just before).

---

## Validation Commands

### Static Analysis
```bash
find Lemegeton_v2 -name "*.py" -exec python -m py_compile {} \;
```
EXPECT: Zero compile errors

### Reference Cleanup Verification
```bash
grep -rn "command_meta\|cogs_test\|theme_helper" Lemegeton_v2/ --include="*.py"
```
EXPECT: No matches

### Manual Validation
- [ ] Bot starts locally against a test guild (`python Lemegeton_v2/bot.py` with a `.env` pointed at a throwaway bot token) and syncs commands without errors.
- [ ] `/profile`, `/help`, and one command from each remaining section execute successfully.
- [ ] Confirm `/dashboard`, `/theme`, `/admin-guild-theme` no longer appear in Discord's command list after a sync.

---

## Acceptance Criteria
- [ ] All 9 tasks completed
- [ ] Zero `command_meta`/`cogs_test`/`theme_helper` references remain in `Lemegeton_v2/`
- [ ] `Lemegeton_v2/CLAUDE.md` accurately describes the trimmed codebase (no stale dashboard/theme docs)
- [ ] Bot boots and syncs commands successfully in a local test run
- [ ] User has made an explicit decision on `lolilist`/`convertlinks`/`library_backup`

## Completion Checklist
- [ ] Code follows discovered patterns (decorator strip only, no incidental refactoring mixed in)
- [ ] No unnecessary scope additions — Phase 2 (architecture/performance/quality work) is explicitly deferred to a follow-up plan
- [ ] Self-contained — no questions needed during Phase 1 implementation beyond the one flagged open question (Task 9)

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A cog has multiple decorated commands and one gets missed during the strip, leaving a dangling import error | Medium | High (bot fails to boot) | Task 7's full compile pass across every file catches this before runtime |
| `server_boost.py` has an import that assumed its old package location | Low | Medium (one cog fails to load, rest of bot fine since cogs load independently) | Explicit GOTCHA in Task 5; re-check import lines after the move |
| CLAUDE.md rewrite (Task 8) drifts further from reality if not cross-checked against the actual post-trim command/table counts | Medium | Low (docs-only, doesn't affect runtime) | Task 8 explicitly requires using Task 1's verified grep output, not the original doc's numbers |
| "Reduce commands" scope is still open beyond dashboard/theme — Phase 2 work could be started prematurely without user sign-off | Medium | Medium (wasted work if user's actual command-cut list differs) | This plan explicitly scopes only Phase 1 (dashboard+theme removal); Phase 2 requires a follow-up plan |

## Notes
- Investigation (background agent, see conversation) found CLAUDE.md documents functionality that doesn't exist in code: an `app_command_enabled_check()` runtime enforcement function for the dashboard (not found anywhere), and a `theme_helper.py` API (file is empty, 0 lines). This means the "dashboard toggles" were purely cosmetic in the original bot — disabling a command via `/dashboard` never actually prevented it from running. This is worth knowing context for why removal is low-risk, and worth calling out to the user as a discovered fact, not just an implementation detail.
- Full command inventory (43 commands, 33 files) and full 34-table database schema were captured during investigation and are preserved in the conversation history — re-derive from `Lemegeton_v2/` directly with `grep -rn "app_commands.command" cogs/` and `grep -n "^async def init_.*_table" database.py` if this plan file is consulted in isolation later, since file:line numbers will drift as Phase 1 edits land.

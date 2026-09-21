# Design: Lemegeton V2 Phase 2 — Server Management Section Refactor

## Status
Investigated 2026-09-21. Ready for implementation.

## Context
Fifth section of Lemegeton V2's Phase 2 (Gaming, Media, Social, Account already complete — see
`.claude/PRPs/reports/lemegeton-v2-{gaming,media,social,account}-refactor-report.md` and the archived
specs in `.claude/PRPs/plans/completed/`). Applies the same 7-category checklist to the 5 files in
`cogs/server_management/`: `invite_tracker.py` (1272 lines), `server_config.py` (608 lines),
`serverinfo.py` (375 lines), `welcome_dm.py` (290 lines), `welcome_message.py` (155 lines).

## Decisions Made (do not re-litigate during implementation)
| Decision | Answer |
|---|---|
| Ground rules | Same as prior four passes: full 7-category checklist, reliability/error-handling weighted highest, internals free to change, command/listener behavior and output unchanged |
| Database scope | No schema changes. New guild-aware helper *functions* in `database.py` only (table `invite_tracker_settings` already exists) |
| `welcome_message.py`'s `on_guild_join` listener | Not an app command — no error-handler decorator applies (same "listeners don't get the decorator" rule prior passes used for non-command entry points). Still eligible for Category 5 (function length) and Category 3 (embed) review |
| A real cross-cog staleness gap found during investigation | **Do not fix.** `server_config.py`'s `SetInviteChannelModal` writes a new invite-tracking channel to the DB but `InviteTracker`'s in-memory `announcement_channels` dict is only loaded once in `cog_load()` — a channel changed via `/server-config` has no live effect until bot restart (the modal's own code comment admits this: "the invite tracker cog will pick it up on next check", but no such recheck exists). This is a genuine behavior gap, not a code-quality nit — fixing it would change runtime behavior, which is out of scope for a "output unchanged" refactor pass. Flag to the user in the report; consolidate the *duplicated SQL* around it (Task 6) without touching the staleness itself |

## Investigation Findings (7-category checklist, evidence gathered before design)

### 1. Import boilerplate
- `server_config.py:15` imports `is_user_moderator` from `database` — confirmed **zero uses** anywhere in the file (grepped). Dead import.
- `invite_tracker.py:13` imports `DB_PATH` from `database` — confirmed **zero uses** anywhere in the file (all DB access already goes through `execute_db_operation`). Dead import.
- `serverinfo.py` maintains its own separate SQLite file (`data/bot_meta.db`) with raw `aiosqlite.connect()` calls in `init_db()`/`log_serverinfo()`, bypassing `database.py`/`execute_db_operation()` entirely — inconsistent with the rest of the codebase's `execute_db_operation()` convention (CLAUDE.md's `userinfo_usage` table shows the intended pattern: usage-logging tables live in the main DB). Isolated to 2 small functions, best-effort/already-swallowed exceptions. Candidate for Task 4 — see NOT Building if it turns out too risky to migrate blind (no guild isolation currently, would need a guild_id column added, which crosses into schema-change territory the series avoids — judge live).
- `welcome_dm.py`, `welcome_message.py`: flat imports, no boilerplate.

### 2. Direct API calls duplicating helpers
Not applicable to this section — no AniList/Steam API calls anywhere in `server_management/` (confirmed by grep for `aiohttp`, `anilist_helper`, `steam_helper`; `welcome_dm.py`'s one `aiohttp.ClientSession()` use is a one-off Discord-attachment download, not a duplicated-helper case).

### 3. Inline embeds vs embed_helper
- `invite_tracker.py`, `server_config.py`, `welcome_dm.py`, `welcome_message.py` already route every embed through `build_error_embed`/`build_success_embed`/`build_info_embed`/`build_warning_embed` — no raw `discord.Embed()` construction found in any of these 4 files. Nothing to do here.
- `serverinfo.py` uses its own bespoke `create_darlux_embed()` helper (deep-black/royal-gold "Dark Luxury" palette) for all 6 paginated embed pages — a self-contained, differently-themed builder, not a violation of the "use embed_helper" convention (embed_helper.py's builders don't offer this palette/pagination shape). Same precedent as Gaming/Media leaving bespoke multi-page views alone — **do not touch**.

### 4. Error handling
No section-wide decorator exists. Only **1 `except:`** found in the whole section, and it's inside a fully commented-out dead code block (`invite_tracker.py:611`, part of the deprecated command removed from Category 7) — so effectively **zero live bare excepts**, the smallest count in this series yet (smaller than Account's 1). Build `server_management_error_handler` anyway, for the same consistency reason Account gave when its own bare-except count was unusually low: a safety net for uncaught exceptions, matching the pattern established across Gaming/Media/Social/Account. New file `helpers/server_management_utils.py`, mirroring `social_utils.py`/`account_utils.py` (rename to `ServerManagement`-flavored names, log file `logs/server_management.log`).

App commands eligible for the decorator (7 total, across 4 files):
- `invite_tracker.py`: `invite_stats`, `invite_leaderboard`, `invite_theme`
- `server_config.py`: `server_config`
- `serverinfo.py`: `server`
- `welcome_dm.py`: `set_welcome_dm`, `welcome_dm_status`
- `welcome_message.py`: none (listener-only, no app command — see Decisions Made)

### 5. Function length
- `serverinfo.py`'s `build_guild_pages()` — ~100 lines (247-346), builds 6 distinct embed pages (hero/presence/emoji/roles/moderation/summary) in one function. Closer to the "cohesive single pass over categories" precedent (like Gaming's `_generate_recommendations`) than a fetch+compute+build+send tangle — no I/O, no branching complexity, just sequential embed construction. Judgment call: **candidate to split into 6 named `_build_*_page()` helpers** for readability (each page is already a clean, independent unit — lower risk than prior passes' splits since there's no shared mutable state to thread through carefully, only `guild`/`members`/`requester`). Read in full again before deciding, same discipline as before.
- `welcome_message.py`'s `on_guild_join()` — ~90 lines (50-142): channel-resolution (3-tier fallback) → embed construction (3 fields) → send. A clean 2-3 step split (`_find_welcome_channel()`, `_build_welcome_embed()`) similar in shape to prior passes' fetch+build+send splits.
- No other function in this section exceeds ~80 lines.

### 6. Duplicated DB lookups
The `invite_tracker_settings` table (`guild_id`, `announcement_channel_id`) is accessed via **5 separate hand-rolled raw-SQL call sites across 2 files**:
- `invite_tracker.py:159` (`_load_channel_settings`) — `SELECT guild_id, announcement_channel_id FROM invite_tracker_settings` (all guilds, no filter — used once at cog_load)
- `server_config.py:127` (`manage_invite_channel` button) — `SELECT announcement_channel_id ... WHERE guild_id = ?`
- `server_config.py:215` (`view_all_settings` button) — same SELECT, duplicated verbatim
- `server_config.py:318` (`remove_channel` button) — `DELETE FROM invite_tracker_settings WHERE guild_id = ?`
- `server_config.py:486` (`SetInviteChannelModal.on_submit`) — `INSERT OR REPLACE INTO invite_tracker_settings (guild_id, announcement_channel_id, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)`

Add guild-aware helpers to `database.py` (naming to match the `users`-table convention, e.g. `get_invite_channel_guild_aware`, `set_invite_channel_guild_aware`, `delete_invite_channel_guild_aware`, `get_all_invite_channel_settings`) and route all 5 sites through them — pure call-site consolidation, identical query semantics preserved at each site (see Decisions Made — do NOT also fix the cross-cog cache-staleness gap this consolidation surfaces).

No other duplicated-lookup pattern found in this section (no `anilist_username`-style shared field here).

### 7. Dead code
- `invite_tracker.py:563-613` — a fully commented-out deprecated `set_invite_channel` app command plus orphaned trailing code fragments (leftover embed-building lines with no enclosing function), explicitly labeled "DEPRECATED COMMAND... Kept here commented for reference only" and "Leftover code from deprecated command above". Confirmed superseded by `server_config.py`'s unified `/server-config` interface (same functionality, already live). ~50 lines, safe to delete entirely.
- `server_config.py:15`'s unused `is_user_moderator` import (Category 1, cross-referenced here).
- `invite_tracker.py:13`'s unused `DB_PATH` import (Category 1, cross-referenced here).

## Mandatory Reading
| Priority | File | Why |
|---|---|---|
| P0 | `.claude/PRPs/reports/lemegeton-v2-account-refactor-report.md` (and gaming/media/social reports) | The checklist, gotchas, and adapted-decorator precedent this pass follows |
| P0 | `Lemegeton_v2/helpers/social_utils.py` or `account_utils.py` | Pattern to mirror for `server_management_error_handler` |
| P0 | `Lemegeton_v2/database.py` (`init_invite_tracker_settings` table def ~1432, `get_guild_bot_update_channel`/`remove_guild_bot_update_channel` for naming convention) | Existing helper shape new `invite_tracker_settings` guild-aware helpers (Task 6) must match |
| P1 | `Lemegeton_v2/cogs/server_management/invite_tracker.py` | Largest file, most findings (categories 1, 4/7 dead code, 6) |
| P1 | `Lemegeton_v2/cogs/server_management/server_config.py` | Second-largest, most call sites for Task 6's consolidation |
| P2 | `Lemegeton_v2/cogs/server_management/serverinfo.py` | Category 5 candidate (`build_guild_pages` split), Category 1 judgment call (`bot_meta.db`) |
| P2 | `Lemegeton_v2/cogs/server_management/welcome_dm.py`, `welcome_message.py` | Lightest touch — decorator + one function split (`welcome_message.py`) |

## NOT Building
- No fix for the `/server-config` → `InviteTracker` cache-staleness gap (flagged, not fixed — see Decisions Made).
- No migration of `serverinfo.py`'s `bot_meta.db` usage-logging to the main DB unless investigation during implementation shows it's safe without a schema change (judge live; default to leaving it if a guild_id column would be needed).
- No restructuring of `serverinfo.py`'s `create_darlux_embed` palette system or its 6 paginated embed pages' content — only the function *shape* (Task 8's optional split), not the visual output.
- No database schema changes (Task 6 adds functions to `database.py`, not tables/columns).
- No changes to any other section (Utilities remains untouched).

## Step-by-Step Tasks

### Task 1: Build server_management_error_handler
- **ACTION**: Create `Lemegeton_v2/helpers/server_management_utils.py` mirroring `social_utils.py`/`account_utils.py` (rename appropriately; log file `logs/server_management.log`, logger name "ServerManagement").
- **VALIDATE**: `python -m py_compile Lemegeton_v2/helpers/server_management_utils.py`.

### Task 2: Wire decorator onto the 7 app commands
- **ACTION**: Add the decorator to `invite_stats`, `invite_leaderboard`, `invite_theme` (`invite_tracker.py`), `server_config` (`server_config.py`), `server` (`serverinfo.py`), `set_welcome_dm`, `welcome_dm_status` (`welcome_dm.py`). Do not add it to `welcome_message.py`'s `on_guild_join` listener.
- **VALIDATE**: grep confirms decorator present on exactly these 7 commands.

### Task 3: Remove dead code (category 7)
- **ACTION**: Delete `invite_tracker.py:563-613`'s commented-out deprecated command block and its orphaned trailing fragments, after confirming (grep) the live `/server-config` path fully supersedes it. Remove `server_config.py:15`'s unused `is_user_moderator` import and `invite_tracker.py:13`'s unused `DB_PATH` import.
- **VALIDATE**: `grep -n "set_invite_channel\|is_user_moderator\|DB_PATH" Lemegeton_v2/cogs/server_management/*.py` returns no matches outside legitimate remaining uses (there should be none for these three).

### Task 4: Import boilerplate judgment call (category 1)
- **ACTION**: Assess `serverinfo.py`'s `bot_meta.db` usage-logging in full during implementation. If it can be routed through `execute_db_operation()` against a `serverinfo_usage` table in the main DB without adding a schema column (i.e., without a guild_id-scoping change), migrate it. If not, leave as-is and document why in the report (same "leave inline and document why" allowance prior passes used).

### Task 5: Fix bare except (category 4)
- **ACTION**: N/A as a standalone task — the only bare `except:` found was inside the dead code Task 3 deletes. Confirm zero live bare excepts remain after Task 3 (`grep -rn "except:\s*$" Lemegeton_v2/cogs/server_management/`).

### Task 6: Consolidate invite_tracker_settings DB access (category 6)
- **ACTION**: Add guild-aware helper functions to `database.py` for `invite_tracker_settings` (`get_invite_channel_guild_aware`, `set_invite_channel_guild_aware`, `delete_invite_channel_guild_aware`, `get_all_invite_channel_settings`), then route the 5 call sites (`invite_tracker.py`'s `_load_channel_settings`; `server_config.py`'s `manage_invite_channel`, `view_all_settings`, `remove_channel`, `SetInviteChannelModal.on_submit`) through them.
- **GOTCHA**: Preserve each site's exact query semantics — `_load_channel_settings` is the only all-guilds (no `WHERE`) read; the rest are single-guild reads/writes. Do not silently fix the cache-staleness gap this consolidation makes visible (see Decisions Made).
- **VALIDATE**: `python -m py_compile Lemegeton_v2/database.py Lemegeton_v2/cogs/server_management/invite_tracker.py Lemegeton_v2/cogs/server_management/server_config.py`; each call site produces identical results before/after for the same inputs.

### Task 7: Light embed_helper touch-up (category 3)
- **ACTION**: N/A — investigation found no raw `discord.Embed()` usage outside `serverinfo.py`'s intentionally bespoke `create_darlux_embed()` system, which is out of scope (see NOT Building). No changes needed.

### Task 8: Function length — judgment-call pass (category 5)
- **ACTION**: Read `serverinfo.py`'s `build_guild_pages()` in full and split into 6 named `_build_*_page()` methods if the read confirms each page is a clean, independent unit (expected, per investigation). Read `welcome_message.py`'s `on_guild_join()` in full and split into `_find_welcome_channel()` + `_build_welcome_embed()` + the existing send call. Record reasoning for each in the implementation report.

## Testing Strategy
No automated test suite exists. Validation: `python -m py_compile` on every touched file; a real
`importlib.import_module()` test inside a running `asyncio` event loop; reference-cleanup greps for
removed patterns (`set_invite_channel`, `is_user_moderator`, unused `DB_PATH`); manual smoke test flagged
as a required follow-up (no bot token available to the implementer) — this section's `/server-config`
channel-setting flows and the `on_member_join`/`on_member_remove` listeners are worth prioritizing given
Task 6 touches shared settings storage.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Task 6's consolidation accidentally changes `_load_channel_settings`'s all-guilds query into a single-guild one, or vice versa for the single-guild sites | Medium | High (invite tracking silently breaks for some/all guilds) | Task 6's GOTCHA explicitly catalogs the all-guilds vs. single-guild split; add 2 distinct helpers rather than force one shape |
| `serverinfo.py`'s `bot_meta.db` migration (Task 4) turns out to need a schema change to preserve behavior | Low | Low (judgment call explicitly allows leaving it as-is) | Task 4's "if not, leave as-is and document why" escape hatch |
| `server_management_error_handler`'s typed exceptions are unreachable, same as Media/Social/Account | High (no API-error-raising helpers in this domain-free section either) | Low (defense-in-depth, documented as such) | Task 1 explicitly mirrors the already-adapted `social_utils.py`/`account_utils.py` |

## Next Step
Implement directly (established pattern for this Phase 2 series) — write the implementation report to
`.claude/PRPs/reports/lemegeton-v2-server-management-refactor-report.md` and archive this spec to
`.claude/PRPs/plans/completed/` when done, mirroring Gaming, Media, Social, and Account's closeout.

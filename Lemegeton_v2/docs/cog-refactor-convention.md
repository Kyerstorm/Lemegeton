# Cog Section Refactor Convention

Derived from the Gaming section refactor (Phase 2 of Lemegeton V2 — see
`docs/superpowers/specs/2026-09-19-lemegeton-v2-gaming-refactor-design.md` at the repo root and
`.claude/PRPs/reports/` for the full design and implementation record). This is the template to
follow when refactoring the remaining sections (Account, Admin, Media, Server Management, Social,
Utilities).

## The 7-category checklist

Work through each category per cog file, in this order — later categories often reveal more
instances of earlier ones:

1. **Import boilerplate.** Look for defensive `try/except ImportError` + `sys.path.insert()` blocks
   at the top of cog files. If even one file in the section imports cleanly with flat
   `from helpers.x import y` statements, the fallback logic elsewhere is dead complexity — `bot.py`'s
   cog auto-loader already guarantees the repo root is resolvable. Standardize on flat imports.
2. **Direct API/DB calls that duplicate an existing helper.** Grep the section's helper file
   (`helpers/<section>_helper.py`) for wrapper functions, then grep the cog files for the same
   endpoint URL or query called inline instead of through the wrapper. This is usually the
   highest-value fix — it's not just style, it means bug fixes to the wrapper (retries, error
   handling) silently don't apply to the inline copies.
3. **Inline embed construction.** `discord.Embed(...)` built directly in a cog with hardcoded colors,
   versus a `build_*_embed()` call to `embed_helper.py`. Extract shared embed shapes into
   `embed_helper.py` functions that take already-fetched data as plain arguments — keep them pure
   (no I/O, no `self`), so a View class's method can become a thin wrapper that calls the helper.
4. **Error handling gaps.** If the section has (or should have) a typed-exception decorator (like
   Gaming's `@gaming_error_handler` in `helpers/gaming_utils.py`), check it's applied to *every*
   command, not just the ones written after it existed. Bare `except Exception: logger.debug(...)`
   blocks that swallow everything identically are a red flag — split network failures
   (`aiohttp.ClientError`, `asyncio.TimeoutError`) from parse failures, and log at `warning` not
   `debug` for anything the user might want explained. A `pass` with genuinely no logging on a
   double-failure path (try A, except try B, except pass) is worth a minimum one log line even if
   you don't change the control flow.
5. **Oversized functions.** Command handlers or embed builders over ~150 lines usually mean fetch,
   business logic, and presentation are tangled together. **Only split what the design actually
   scopes** — don't split a large function just because it's large if it's a single cohesive
   algorithm (see Gotcha below); prefer extracting embed construction (a clean boundary) over
   splitting deeply-nested UI callback closures (a risky one).
6. **Duplicated DB lookups.** The same "look up this user's linked account" query copy-pasted across
   multiple commands, sometimes with subtly different fallback behavior (e.g. one file adds a
   guild-scoped-then-global fallback the others lack). Consolidate into one helper function in
   `helpers/<section>_helper.py`, and preserve the most permissive existing behavior (the fallback)
   as the shared default — don't silently drop it to match the simpler call sites.
7. **Dead code.** While reading for the above, watch for methods/functions that look like they should
   be called but aren't — e.g. a cog defines its own `_build_x_embed()` that duplicates a View
   class's method of the same name, but only the View's method is ever actually invoked. Grep for
   every call site before assuming a function is live. Delete confirmed-dead code rather than fixing
   bugs in it.

## Gotchas learned from the Gaming pass

- **A design's line-number findings can point at dead code.** The Gaming design's investigation
  flagged a "swallow-then-degrade" embed-builder bug at a specific line range — but that code turned
  out to be an unused duplicate (category 7) of the actual live method elsewhere. Before implementing
  a fix, confirm the flagged code path is actually reachable; if it isn't, deleting it may already
  resolve the finding.
- **Don't split algorithmically cohesive functions just to hit a line-count target.** A single
  function implementing one algorithm (e.g. "analyze library → search candidates → score them") with
  several accumulator variables threaded through sequential steps is often *more* readable as one
  function than as three functions passing 5+ parameters between them. Reserve splitting for
  functions that are long because they mix unrelated concerns (fetch + format + send), not because
  they're long by nature of the algorithm.
- **Closures are a stop sign, not a green light.** Discord UI callbacks (button/select callbacks
  defined as nested `async def` closures capturing outer-scope variables like `embed` or `view`) are
  high-risk to mechanically split or extract — a closure that reassigns an outer-scope variable
  (e.g. `embed = build_warning_embed(...)` inside an except block, clobbering the `embed` the *next*
  button press would reference) can hide a real bug. Fixing the reassignment (rename the inner
  variable) is safe and worthwhile; restructuring the closure nesting itself usually isn't worth the
  risk without test coverage.
- **A design's "add decorator everywhere" instruction can be redundant in specific files without
  being wrong.** `free_games_checker.py` already had thorough manual error handling; adding
  `@gaming_error_handler` there doesn't fix a gap, it just makes the section's decorator usage
  uniform so a future reader doesn't have to wonder why one file is missing it. That's still worth
  doing — uniformity has its own value — just don't expect it to change behavior in files that were
  already solid.
- **Verify a design's assumption against the actual function signature before implementing it.** The
  Gaming design assumed one command was missing vanity-URL support alongside its steamid-only path;
  in the actual code, that command takes no user-identifying parameter at all (it's always
  self-lookup), so the finding didn't apply. Check the real signature before writing the fix.

## Validation sequence (no test suite exists in this codebase)

1. `python -m py_compile` every touched file.
2. Grep for the boilerplate/pattern you removed (`command_meta`, `sys.path.insert`, the specific dead
   function name, etc.) across the whole `Lemegeton_v2/` tree — not just the files you think you
   touched — to catch anything missed.
3. Attempt a real `importlib.import_module()` of every touched module **inside a running asyncio
   event loop** (`asyncio.run(main())`), not a bare script — several helper modules schedule
   background tasks at import time (`asyncio.create_task(...)`) and will raise
   `RuntimeError: no running event loop` outside one. This catches `NameError`s and missing-import
   bugs that `py_compile` (parse-only) cannot.
4. Clean up any `data/`, `logs/`, or `__pycache__/` artifacts the import test creates — they're
   runtime side effects, not source changes.
5. Flag manual smoke testing against a live Discord bot token as a required follow-up if you don't
   have one available — don't claim full verification without it.

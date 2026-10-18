# Lunar Roles offline tests

These tests check the Lunar Roles service layer, name filter, lifecycle, mass-removal guard,
palette and icon code without Discord. They use fake Discord objects (`fakes.py`) and a
**local PostgreSQL** (the same one the bot uses in development).

## Run them

From the repo root, with the bot's virtual environment:

```bash
.venv/Scripts/python.exe tests/lunar_roles/run_all.py
```

On Linux/macOS use `.venv/bin/python`. Add `-v` to see every check. To run one file:
`.venv/Scripts/python.exe tests/lunar_roles/test_lifecycle.py`.

**You need:**
- `.env` pointing at a local PostgreSQL: `POSTGRES_HOST=localhost` or `127.0.0.1`.
- `ENVIRONMENT=development`, or `ENVIRONMENT` unset.

The bot doesn't need to be running. Each file prints `PASS`/`FAIL` lines and an `N/N passed`
summary.

## Safety (`_safety.py`, imported first by every test)

- **Local development database only.** The tests refuse to start if `DATABASE_URL`,
  `POSTGRES_DSN` or `POSTGRES_URL` is set, if `POSTGRES_HOST` isn't localhost, or if
  `ENVIRONMENT` isn't development.
- **No Discord.** The bot token is never loaded, and any Discord API call raises an error.
  Everything Discord-side is faked.
- **Fake servers only.** Tests only create and delete rows for the guild IDs 2–5. Real Discord
  server IDs are 17–20 digit numbers, so real data can't be touched.
- **Separate logs.** Logs go to a temporary folder, not the bot's `logs/`.

## Files

| File | Covers |
|---|---|
| `test_enable_gate.py` | `/lunar-admin enable` refuses until a valid anchor is set; the "isn't set up yet" gate |
| `test_names_and_roles.py` | Hex parsing, the name filter (protected words, leetspeak, moderation-role names, blocked words), create/rename/color/assign/unassign/info, anchor placement, hidden-color notes, the name sweep |
| `test_lifecycle.py` | Archive/restore, events, reconcile, mass-removal guard, pending removals and snoozes, skipping on incomplete data, the debug switch |
| `test_palette_and_icons.py` | Icon preparation (crop, EXIF, decompression bombs, file types), emoji check, avatar palette, palette menus, icon set/remove/restore, the `/lunar icon` upload path |
| `fakes.py` | Fake guilds, roles, members and channels |
| `make_test_images.py` | Not a test. Generates `test_images/` for testing `/lunar icon` by hand in Discord |

## Test images for Discord

```bash
.venv/Scripts/python.exe -I tests/lunar_roles/make_test_images.py test_images
```

This writes eleven files into `test_images/`, which is gitignored.
**`11_BOMB_decompression_DO_NOT_OPEN.png.bin` is a decompression bomb: a 48 KB file that decodes
to 400 million pixels.** Don't open it in an image viewer. It ends in `.bin` so Discord's upload
dialog doesn't try to preview it; the bot still detects it as a PNG.

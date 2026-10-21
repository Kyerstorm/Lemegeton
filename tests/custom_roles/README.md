# Custom Roles offline tests

These tests check the Custom Roles service layer, name filter, lifecycle, mass-removal guard,
palette and icon code without Discord. They use fake Discord objects (`fakes.py`) and a
**local PostgreSQL** (the same one the bot uses in development).

## Run them

From the repo root, with the bot's virtual environment:

```bash
.venv/Scripts/python.exe tests/custom_roles/run_all.py
```

On Linux/macOS use `.venv/bin/python`. Add `-v` to see every check. To run one file:
`.venv/Scripts/python.exe tests/custom_roles/test_lifecycle.py`.

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
- **Fake servers only.** Tests only create and delete rows for the guild IDs 2–10. Real Discord
  server IDs are 17–20 digit numbers, so real data can't be touched. (`seed_test_server.py` isn't
  a test and has its own limits; see below.)
- **Separate logs.** Logs go to a temporary folder, not the bot's `logs/`.

## Files

| File | Covers |
|---|---|
| `test_enable_gate.py` | `/custom-role-admin enable` refuses until a valid anchor is set; the "isn't set up yet" gate |
| `test_names_and_roles.py` | Hex parsing, the name filter (protected words, leetspeak, moderation-role names, blocked words), create/rename/color/assign/unassign/info, anchor placement, hidden-color notes, the name sweep |
| `test_lifecycle.py` | Archive/restore, events, reconcile, mass-removal guard, pending removals and snoozes, skipping on incomplete data, the debug switch |
| `test_palette_and_icons.py` | Icon preparation (crop, EXIF, decompression bombs, file types), emoji check, avatar palette, palette menus, icon set/remove/restore, the `/custom-role icon` upload path |
| `test_admin_extras.py` | Command channel, cooldown, `/custom-role position` (including gaps in Discord's position numbers), restoring near the old spot, `/custom-role-admin list` and `remove` |
| `test_picker_web.py` | Web server refactor (picker without the dashboard), picker link tokens, security headers, token-in-URL refusal, eligibility re-checks, rate limits, spoofed `X-Forwarded-For`, `/custom-role color-picker` |
| `test_picker_edit.py` | Picker write APIs (color, name), palette, cooldown on the web, the preview test switch, XSS safety (hostile names come back as plain data; `picker.js` never inserts HTML), theme rules (`picker.css` has no colors or lengths; every theme value has a comment) |
| `test_picker_icon.py` | Role icon originals (up to 8 MB, stored byte for byte) and crops, the 256/128/64 output, the SSRF-safe link fetcher (URL rules, a 29-address allow-list, mixed DNS answers, pinning, redirects, size and time limits against a local test site), the icon APIs (upload, link, emoji, Edit current crop, remove), rate and concurrency limits, the test switch, the image CSP, the pixel limits (8192 px a side, 16 MP) with messages naming the limit hit, HEIC detection, and the page's checks matching the server's word for word (run through node when it's installed) |
| `test_legacy_import.py` | Old `/nitro-role-set` roles: no automatic copy at startup, the `/custom-role-admin import-legacy` preview (take over / don't qualify / skipped with reasons) and buttons, take-over keeping name, colors and position without creating or deleting roles, the archive option, the settings Problems line, self-adoption by any `/custom-role` command (never a second role), and no automatic archiving while Custom Roles is off |
| `fakes.py` | Fake guilds, roles, members and channels |
| `make_test_images.py` | Not a test. Generates `test_images/` for testing `/custom-role icon` by hand in Discord |
| `seed_test_server.py` | Not a test. Adds or removes fake saved records in the test server, for testing `/custom-role-admin list` pages |

## Fake records for `/custom-role-admin list`

```bash
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py add 15
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py status
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py remove
```

This is the one script that writes to a real server's rows, so it has its own limits:
- It only uses the server in `.env`'s `GUILD_ID`, and only if Custom Roles has settings there.
- It refuses to run when `ENVIRONMENT=production`, and `_safety.py` still applies (local
  development database, no token, no Discord calls).
- It only creates `saved` records with the fake user IDs 1000001–1000060, which can't be real
  Discord users. `remove` deletes every record in that range, which is exactly what `add` made.

For `/custom-role-admin import-legacy`, it can also add old `/nitro-role-set` rows:

```bash
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-add ROLE_ID [USER_ID]
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-status
.venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-remove
```

Without `USER_ID`, a fake member who "left the server" (1000901 and up) is used. It never
overwrites an existing row, and `legacy-remove` deletes only the rows `legacy-add` made (plus any
custom role records an import made for its fake members).

## Test images for Discord

```bash
.venv/Scripts/python.exe -I tests/custom_roles/make_test_images.py test_images
```

This writes seventeen files into `test_images/`, which is gitignored. It also deletes files from
older milestones whose result has changed. Files `01`–`03`, `12`, `13` and `17` are valid; the
rest are refused, each with its own message.
- `04_too_big_over_8mb.png` (~8.5 MB) is over the size limit; `12_ok_big_photo.jpg` (~4 MB) is a
  valid large original.
- Pixel limits: `10_too_wide_9000px.png`, `15_too_tall_9000px_rotated.jpg` (stored wide, shown
  tall by its EXIF rotation) and `14_too_many_pixels_48mp.jpg` (8064×6048) are refused;
  `13_ok_long_8000px.png` and `17_ok_12mp_phone_photo.jpg` (4032×3024) fit.
- `16_iphone_photo.heic` only has a HEIC header, which is all the bot checks.
**`11_BOMB_decompression_DO_NOT_OPEN.png.bin` is a decompression bomb: a 48 KB file that decodes
to 400 million pixels.** Don't open it in an image viewer. It ends in `.bin` so Discord's upload
dialog doesn't try to preview it; the bot still detects it as a PNG.

# Custom Roles — Build Spec

Custom booster roles for any server, built into the **Lemegeton** bot (`multi_guild` branch).
Every server booster gets **one** personal role they can name, color (solid, gradient, holographic) and give an icon,
from slash commands **or** from a private web page (the "color picker").

Read this whole file before writing code. Follow the build order in §11 and stop after each milestone so the
human can test it in Discord.

---

## 1. Ground rules

- **Work inside the existing Lemegeton codebase.** Do not touch unrelated cogs. Match the existing style
  (cogs + `helpers/`, `build_*_embed` helpers, `command_meta`, per-file loggers).
- **Never use or ask for the production bot token.** Development runs on a separate *test bot* in a private test server.
- **discord.py stays at 2.6.0** (pinned in `requirements.txt`). It already supports everything needed:
  `Role.edit()` / `Guild.create_role()` accept `secondary_colour`, `tertiary_colour` and `display_icon`.
- **One source of truth for role logic.** Slash commands, the website API and the automatic events all call the
  same service functions (§7). No duplicated Discord-editing logic.
- The command group name is a **single constant** (`COMMAND_GROUP = "custom-role"`) so it can be renamed in one place.
- Show your plan for each milestone before writing it, and keep commits small and descriptive.

## 2. Facts about the existing code (verified)

| Area | Fact | Consequence |
|---|---|---|
| Current feature | `cogs/customization/server_boost.py` has `/nitro-role-set role_name hex_color` (solid only) and an `on_member_update` boost-welcome DM. | **Replace** this cog's command with the `/custom-role` group. Keep (and update) the welcome DM. |
| Database | **PostgreSQL only** (`database.py`, asyncpg). Queries go through `execute_db_operation(name, sql, params, fetch_type=...)` using `?` placeholders; the layer converts `INTEGER` → `BIGINT` and `?` → `$n`. | Use `execute_db_operation`. Register new table init functions in `init_db()`'s `table_init_functions` list. |
| Existing table | `booster_roles(discord_id, guild_id, role_id, created_at, updated_at)`, PK `(discord_id, guild_id)`. | Import its rows with `/custom-role-admin import-legacy` (§8; originally "on first init"), then stop using the old helpers. |
| Cog loader | `bot.py` loads **every `.py` file** under `cogs/` and `cogs_test/` as an extension. | Put non-cog code (service, image utils) in `helpers/`, **not** under `cogs/`. |
| Intents | `members` and `message_content` intents are enabled. | Boost start/stop is detectable via `on_member_update` (`premium_since`). |
| Command sync | Commands are synced globally (`bot.tree.sync()`). | Nothing extra needed. |
| Web server | `web/dashboard.py` (`DashboardWebServer`, aiohttp) serves the admin dashboard. **`start()` returns early unless `DASHBOARD_CLIENT_ID`, `DASHBOARD_CLIENT_SECRET` and `DASHBOARD_SECRET_KEY` are all set.** | Refactor so the HTTP server starts if **either** the dashboard is configured **or** the color picker is enabled; only register dashboard/OAuth routes when the dashboard is configured. The picker must work with no OAuth configured. |
| Security middleware | Rejects cross-origin POST/PUT/PATCH/DELETE; CSP is `script-src 'self'`, `img-src 'self' https://cdn.discordapp.com data:`, `connect-src 'self'`. | Picker JS must be **external files** (no inline `<script>`). Use **`data:` URLs** for image previews (not `blob:`), or explicitly add `blob:` to `img-src`. |
| Theme | `web/static/theme.css` holds the dashboard's design tokens as CSS variables. | Picker styling must also be token-driven (§6.6). |
| Utilities | `helpers/color_palette.py`, `helpers/embed_helper.py` exist; Pillow 11 is installed. | Reuse them. |

## 3. Core behaviour rules

1. **One role per booster per server.** Every change (name, color, icon) **edits that role in place**.
   Never create a second role for the same user. Never leave old roles behind.
2. **Who can use it:** members with `premium_since` set (boosters), plus any members holding an admin-configured
   "extra allowed" role (empty by default). Re-check eligibility on **every** action (command, web call), not just at link creation.
3. **Stop boosting** (or lose eligibility, or leave the server): delete the role from Discord, and keep the
   settings in the database with status `saved` (name, colors, icon bytes, position hint).
4. **Boost again:** if saved settings exist, recreate the role from them, assign it, and DM the user that it is back.
   If not, send the normal welcome DM.
5. **Reconcile on startup and every 30 minutes** to catch events missed while the bot was offline:
   active records whose member left / is no longer eligible → treat as stop-boosting;
   active records whose Discord role was deleted by an admin → mark `missing` (next user action recreates it from saved settings).
6. **Placement:** new custom roles are created **directly below an admin-chosen anchor role** (§5). If no anchor
   is set, directly below the bot's highest role. Never place a custom role above the bot's top role.
7. **Assign / unassign** only toggles whether the member wears their role; the role itself stays.
8. **Cooldown** between changes is an admin setting, **0 (off) by default**. discord.py already handles Discord rate limits.
9. **Feature checks before applying:**
   - Gradient/holographic requires guild feature `ENHANCED_ROLE_COLORS` (Discord's "Enhanced Role Styles": **3 server boosts**, no Boost Level needed). Without it, reject with a clear message (don't silently fall back).
   - Role icons require guild feature `ROLE_ICONS` (Boost Level 2).
   - Source for both: [Discord's article](https://support.discord.com/hc/en-us/articles/31444213087255). The bot checks the feature flags, not the boost count.
   - Holographic is a fixed Discord preset: primary `11127295`, secondary `16759788`, tertiary `16761760`. Users cannot pick holographic colors.
10. **Role limit:** Discord allows at most **250 roles per server**. Before creating a role, check `len(guild.roles)`;
    if at the limit, refuse with a friendly message and log it to the log channel.

## 4. User commands (`/custom-role ...`)

All replies are **ephemeral** and use the existing embed helpers. If an admin restricted commands to a channel,
reply with where to use them instead.

| Command | Options | Behaviour |
|---|---|---|
| `/custom-role role` | `name` (required) | Create your role with this name and assign it. If you already have one: reply *"Your role already exists by the name `X`"* + hint to `/custom-role assign` and `/custom-role name`. If you have `saved`/`missing` settings, recreate from them, using the new name. |
| `/custom-role name` | `new_name` (required) | Rename your role (name filter §4.1). |
| `/custom-role color set` | `color` (hex, required), `secondary_color` (hex, optional) | Solid if only `color`; gradient if both. Accept `#RRGGBB`, `RRGGBB`, `#RGB`. Description: *"Set your role color by hex. Try /custom-role color-picker to pick it visually."* |
| `/custom-role color holographic` | — | Apply Discord's holographic preset. |
| `/custom-role color-picker` | — | Reply with a private link (button) to the web picker (§6). Link expires (default 15 min); generating a new one invalidates the old one. |
| `/custom-role palette` | — | Extract colors from the user's avatar (§6.4) and reply with **two select menus** ("Primary color", "Secondary color — makes a gradient", max 25 options each, label = hex, emoji-free). Picking primary sets a solid color; picking a secondary as well makes a gradient. Include a "Clear secondary" option. |
| `/custom-role icon` | `image` (attachment, optional) | With an image: validate, center-crop to square, resize to 64×64 PNG ≤ 256 KB, apply. **Without an image: remove the icon.** Tip in reply: use the color picker to crop precisely. |
| `/custom-role assign` | — | Put your role back on yourself. |
| `/custom-role unassign` | — | Take your role off (role is kept). |
| `/custom-role position` | `direction` (above/below), `role` (another member's custom role) | Move your role directly above/below another **custom** role. Refuse if the target isn't a tracked custom role or the move would leave the custom-role block. |
| `/custom-role info` | `user` (optional) | Show a role's name, colors (as hex + mode), icon, and created date. |

Commands that change something require the user to have a role (except `/custom-role role`); otherwise tell them to run `/custom-role role <name>` first.

### 4.1 Role name filter
- Length 1–100, trimmed, collapse whitespace.
- Reject names matching (case-insensitive) any **existing non-custom role** in the server (prevents impersonating "Admin", "Moderator", etc.).
- Reject names containing admin-configured blocked words (case-insensitive, also after removing spaces/punctuation).
- Reject `@everyone` / `@here` and names that are only invisible characters.

## 5. Admin commands (`/custom-role-admin ...`)

Default member permission: **Manage Roles**. Settings are stored per guild (§8).

| Command | Behaviour |
|---|---|
| `/custom-role-admin settings` | Show all current settings and feature status (gradient available? icons available? role count / 250). |
| `/custom-role-admin anchor role:` | Custom roles are placed directly below this role. Must be below the bot's top role. |
| `/custom-role-admin channel [channel]` | Restrict user commands to one channel; no argument = anywhere. (Admins can also use Discord's Server Settings → Integrations.) |
| `/custom-role-admin log-channel [channel]` | Where to log create/rename/color/icon/delete/restore events and errors. |
| `/custom-role-admin blocked-words add/remove/list` | Manage blocked words for role names. |
| `/custom-role-admin cooldown seconds:` | 0 = off (default). |
| `/custom-role-admin allow-role add/remove/list` | Extra roles allowed to use the feature besides boosters (none by default). |
| `/custom-role-admin list` | Paginated list of all custom roles: owner, role, status (active/saved/missing). |
| `/custom-role-admin remove user:` | Delete a user's custom role (moderation). Keeps nothing; logs it. |
| `/custom-role-admin enable` / `disable` | Turn the whole feature on/off for the server. |

## 6. Web color picker

Same look and flow as the reference screenshots (dark page, centered column ~600px wide).

### 6.1 Flow
1. `/custom-role color-picker` → service creates a token: `secrets.token_urlsafe(32)`, bound to `(user_id, guild_id)`,
   expiry `CUSTOM_ROLES_PICKER_TTL` (default 900 s), stored in memory (one active token per user per guild).
2. Bot replies ephemerally with a link button to `{CUSTOM_ROLES_PUBLIC_URL}/custom-roles/{token}`.
3. The page reads the token from the URL path and calls the API with header `Authorization: Bearer <token>`
   (the token is never sent in API URLs). Pages set `Referrer-Policy: no-referrer` and `Cache-Control: no-store`.
4. Expired/invalid token → friendly "This link expired — run `/custom-role color-picker` again" page.

### 6.2 Page layout
- **Live preview, top:** two fake Discord messages, **dark theme** and **light theme** cards. Each shows the user's
  avatar, display name rendered in the selected style (solid color, CSS gradient text via `background-clip: text`,
  or an animated holographic approximation), the role icon next to the name, a timestamp, and a sample message.
  The preview updates instantly as the user changes anything, **before** they press Set.
- **Tabs:** `Color` | `Role Icon` | `Name`.
- **Color tab:**
  - Mode switch: `Solid` | `Gradient` | `Holographic` (Gradient/Holographic disabled with a tooltip if the server lacks `ENHANCED_ROLE_COLORS`, i.e. has fewer than 3 boosts).
  - Solid: swatch + hex input + color picker popover (saturation/hue area + vertical slider) + `Set color`.
  - Gradient: gradient bar preview, Primary and Secondary (swatch + hex + picker popover each) + `Set gradient`.
  - Holographic: preview + `Set holographic`.
  - Card **"Colors extracted from your profile picture"**: swatch grid. In Solid mode one grid; in Gradient mode two grids (Primary / Secondary). Clicking a swatch fills that color.
- **Role Icon tab:**
  - Source switch `Upload` | `Link`.
  - Upload: drop zone "Drop an image here, or click to browse — PNG or JPEG · up to 256 KB".
  - Link: URL input + help text "A direct link to a PNG or JPEG, up to 256 KB. Links that redirect won't work, so paste the image's own address."
  - Preview box showing the chosen image, and it also appears on the message preview above.
  - Square **crop editor** (drag + zoom) before applying. Buttons: `Set icon`, `Edit current crop` (loads the current icon into the crop editor), `Remove current icon`.
  - Disabled with an explanation if the server lacks `ROLE_ICONS`.
- **Name tab:** text input with the same filter as §4.1 (validated server-side; show the error inline) + `Set name`.
- Toast/inline status after each action (success or the exact error). Buttons show a loading state and can't be double-submitted.
- Works on mobile widths (no horizontal scroll) and is keyboard accessible.

### 6.3 API (all under `/custom-roles/api/`, all require the bearer token)
| Method & path | Purpose |
|---|---|
| `GET state` | Display name, avatar URL, current role (name, mode, colors, icon as data URL or null), guild features (gradient/icons allowed), whether the user is still eligible. |
| `GET palette` | Colors extracted from the avatar (§6.4). |
| `POST color` | `{mode: "solid"|"gradient"|"holographic", primary, secondary}` |
| `POST name` | `{name}` |
| `POST icon` | Multipart upload of the **already-cropped** PNG from the browser. Server re-validates and re-encodes it with Pillow. |
| `POST icon/fetch` | `{url}` → server fetches the image safely (§6.5) and returns it as a data URL for the crop editor. **Does not apply it.** |
| `DELETE icon` | Remove icon. |

Every write goes through the service layer (§7), re-checks eligibility, feature support, cooldown and the name filter,
and returns `{ok, message, state}`. Rate-limit writes per token (e.g. 20/minute).

### 6.4 Avatar palette (shared by `/custom-role palette` and the web)
Download the member's avatar from the Discord CDN (static PNG, size 128), quantize with Pillow to ~16–20 distinct colors,
drop near-duplicates, sort by prominence, return hex strings. Cache per avatar hash.

### 6.5 Icon handling and link-fetch safety
- Accept PNG/JPEG only (check magic bytes, not just the extension); max 256 KB input; decode with Pillow; reject animated images;
  re-encode as a 64×64 PNG (Discord's documented role-icon size; max 256 KB).
- Link fetching (SSRF-safe): `https` only; resolve DNS and **reject private, loopback, link-local, multicast and reserved IPs**
  (check every resolved address, and connect to the checked IP); **no redirects**; 5 s timeout; stream and abort past 256 KB;
  require an image content type.

### 6.6 Theming (so the server dev can match a server's own theme easily)
- Files: `web/static/custom_roles/picker.html`, `picker.css`, `picker.js`, `theme.css`.
- **All** colors, radii, fonts and spacing used by the picker are CSS variables defined in **`theme.css`** only
  (e.g. `--lp-bg`, `--lp-card`, `--lp-text`, `--lp-muted`, `--lp-accent` (default Discord blurple `#5865F2`), `--lp-radius`).
  `picker.css` must not contain hard-coded colors. Changing the theme = editing that one file.
- Add a short comment block at the top of `theme.css` explaining each variable.

## 7. Service layer — `helpers/custom_roles/`

Put shared logic here (a package with no `setup()`; it lives outside `cogs/`):

- `service.py` — `ensure_eligible`, `create_role`, `rename`, `set_colors`, `set_icon`, `remove_icon`, `assign`,
  `unassign`, `move`, `archive` (stop-boosting), `restore` (re-boost), `reconcile_guild`. Each returns a result object
  with a user-facing message; raises nothing to the caller for expected failures.
- `validation.py` — hex parsing, name filter (§4.1).
- `images.py` — palette extraction, icon validation/crop/re-encode, safe URL fetch.
- `tokens.py` — picker token create/lookup/expire.
- `storage.py` — DB access (§8).

Handle these everywhere with clear messages: bot missing **Manage Roles**; target role above the bot; role was deleted
manually; 250-role limit; missing guild feature; user no longer eligible; Discord API errors (log full trace, show a short message).
Use a per-user `asyncio.Lock` so two simultaneous changes for the same user can't race.

## 8. Data model (PostgreSQL via `execute_db_operation`)

`custom_role_records`
| column | type | notes |
|---|---|---|
| guild_id, user_id | BIGINT | PK (guild_id, user_id) |
| role_id | BIGINT NULL | null when saved/missing |
| status | TEXT | `active` / `saved` / `missing` |
| name | TEXT | |
| color_mode | TEXT | `solid` / `gradient` / `holographic` |
| primary_color, secondary_color | INTEGER NULL | |
| icon_png | BYTEA NULL | ≤ 256 KB, kept so restore can re-apply it |
| last_changed_at, created_at, updated_at | TIMESTAMP | |

`custom_role_guild_settings` — guild_id PK, enabled, anchor_role_id, command_channel_id, log_channel_id, cooldown_seconds,
allowed_role_ids (TEXT/JSON), blocked_words (TEXT/JSON), updated_at.

**Migration (changed in Milestone 9):** rows are **not** copied automatically on init any more, because the startup
check then archived old roles of members who no longer qualified, on every server, before an admin had decided anything.
Instead `/custom-role-admin import-legacy` shows a preview (taken over / members who don't qualify / skipped, with reasons)
and, on confirm, takes the existing roles over as they are (name, color, position read from Discord; nothing recreated).
Members who don't qualify are archived only if the admin picks that option. A member who uses `/custom-role` before the import
takes over their own old role. Nothing is ever archived automatically while Custom Roles is off. The old table is left
in place and only read.

## 9. Configuration (`config.py` + `.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `CUSTOM_ROLES_PICKER_ENABLED` | `true` | Start the web server for the picker even if the dashboard isn't configured. |
| `CUSTOM_ROLES_PUBLIC_URL` | `http://localhost:8080` | Base URL used in picker links (production: the bot's public HTTPS URL). |
| `CUSTOM_ROLES_PICKER_TTL` | `900` | Link lifetime in seconds. |

Reuse `DASHBOARD_HOST` / `DASHBOARD_PORT` for the listening address.

## 10. Messages
- Welcome DM on boost: thank them, point to `/custom-role role <name>` and `/custom-role color-picker`.
- Restore DM on re-boost: "Welcome back — your role **X** is back."
- Stop-boost: no DM needed; log it.
- Keep user-facing text short, friendly, and free of stack traces.

## 11. Build order (stop after each milestone for testing)

1. **Foundation:** tables + migration, settings, service layer skeleton, `/custom-role-admin settings|anchor|enable|disable`.
2. **Core role commands:** `role`, `name`, `color set`, `color holographic`, `assign`, `unassign`, `info`.
3. **Lifecycle:** boost welcome, stop-boost archive, re-boost restore, member-leave, startup + 30-min reconcile, log channel.
4. **Palette + icon commands:** `palette`, `icon`.
5. **Admin extras:** `channel`, `blocked-words`, `cooldown`, `allow-role`, `list`, `remove`, `position`.
6. **Web server refactor** (§2 "Web server") + token flow + `/custom-role color-picker`.
7. **Picker page:** preview, color tab, palette grid, name tab.
8. **Icon tab:** upload, link fetch, crop editor, remove.
9. **Polish + docs:** README section "Custom Roles", `.env.example` entries, admin setup notes, final test pass (§12).

## 12. Test checklist (human runs these in the test server)
- [ ] Non-booster gets a clear "boosters only" message for every user command.
- [ ] `/custom-role role Mogged` creates exactly one role below the anchor and assigns it; running it again says it already exists.
- [ ] Renaming, recoloring and icon changes edit the **same** role ID (no new roles appear in Server Settings → Roles).
- [ ] Solid, gradient and holographic all apply; gradient is refused with a clear message in a server without the perk.
- [ ] Names like "Admin" (an existing role), blocked words, `@everyone`, empty/invisible names are refused.
- [ ] `/custom-role palette` shows avatar colors; choosing primary + secondary produces a gradient.
- [ ] `/custom-role icon` with a big/odd-shaped image gets cropped to a square 64×64; without an image removes the icon.
- [ ] Remove boost (or simulate: temporarily drop eligibility via allow-role) → role deleted, settings saved; boost again → same name/colors/icon restored + DM.
- [ ] Stop the bot, change eligibility, start the bot → reconcile fixes it.
- [ ] Picker link opens, preview updates live in both themes, every Set button works and matches Discord.
- [ ] Expired link and a second newer link (old one invalid) both behave correctly.
- [ ] Icon link: private IPs (`https://127.0.0.1/...`, `https://192.168.x.x/...`), redirects, >256 KB and non-images are all refused.
- [ ] Editing only `theme.css` re-themes the whole page.
- [ ] Bot without Manage Roles / anchor above the bot → clear admin-facing error, nothing crashes.

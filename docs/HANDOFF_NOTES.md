# Lunar Roles — Setup and Handoff Guide

Everything needed to run Lunar Roles (custom booster roles) on the real server: deploying on
Railway, first-time setup in Discord, theming the color picker, and the checks that could only be
done on a boosted server.

- What Lunar Roles does and every command: the [Lunar Roles section of the README](../README.md#-lunar-roles)
- All settings with their defaults: the `LUNAR ROLES` block at the end of [`.env.example`](../.env.example)
- The original design spec: [LUNAR_ROLES_SPEC.md](LUNAR_ROLES_SPEC.md)

**Contents**
1. [Before you start](#1-before-you-start)
2. [Railway setup](#2-railway-setup)
3. [First-time setup in the server](#3-first-time-setup-in-the-server)
4. [Theming the color picker](#4-theming-the-color-picker)
5. [Boosted server final check](#5-boosted-server-final-check)
6. [Behaviour worth knowing](#6-behaviour-worth-knowing)
7. [Still unverified, and known issues](#7-still-unverified-and-known-issues)

---

## 1. Before you start

- **Privileged intents:** in the Discord Developer Portal (your application → Bot), turn on
  **Server Members** and **Message Content**. Without them the bot can't connect.
- **Bot permissions:** the bot needs **Manage Roles** in the server.
- **One copy only:** run a single copy of the bot. Color picker links live in memory, so a second
  copy wouldn't know about them, and every restart ends the open links (members just run
  `/lunar color-picker` again).
- **Database:** Lunar Roles uses the bot's normal PostgreSQL database (`DATABASE_URL`). Its tables
  are created automatically at startup.
  - **Icon storage:** each member's original icon image is kept exactly as uploaded (up to 8 MB),
    so it can be re-cropped later without losing quality. The icon sent to Discord is a separate
    small PNG (at most 256 KB).
  - Worst case is about 8 MB per member with an image icon. A typical phone photo is 2–5 MB, and
    most uploads are far smaller.
  - Originals are kept for saved roles too, so they come back on restore. They're deleted when the
    icon is removed or replaced by an emoji, and by `/lunar-admin remove`.
  - Lower `LUNAR_ICON_SOURCE_MAX_BYTES` to cap this.

## 2. Railway setup

### Variables

Set these on the bot's Railway service, alongside the bot's usual ones (`DISCORD_TOKEN`,
`DATABASE_URL`, …):

| Variable | Value | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | **Required.** When unset, the bot treats itself as development: the test switches would work and `http://` picker links would be handed out. |
| `LUNAR_PUBLIC_URL` | `https://<your domain>` | The picker's address, with no trailing slash. In production the bot only hands out `https://` links; with `http://` it refuses and posts the reason in the Lunar log channel. |
| `DASHBOARD_HOST` | `0.0.0.0` | Listen on all addresses, so Railway can reach the page. |
| `DASHBOARD_PORT` | `8080` | Must match the domain's target port (below). |
| `LUNAR_PICKER_ENABLED` | `true` | The default; set it to `false` to turn the picker off. |
| `LUNAR_TRUST_PROXY` | `true` | Use the visitor's address from Railway's proxy for the bad-link limit (see the caveat below). |

**Never set these in production:** `LUNAR_DEBUG_FAIL_MEMBER_FETCH`,
`LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS`, `LUNAR_DEBUG_PREVIEW_ROLE_ICONS`, or
`LUNAR_MASS_ARCHIVE_THRESHOLD=0`.
- The three `LUNAR_DEBUG_*` switches are for testing only. They only take effect when
  `ENVIRONMENT=development`, and while one is on the bot prints a loud `!!!` warning at startup
  and posts 🚧 in every Lunar log channel. If you ever see that warning on Railway, remove the
  variable.
  - `LUNAR_DEBUG_FAIL_MEMBER_FETCH`: checks remove no roles.
  - `LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS`: unlocks the Gradient/Holographic preview without the
    server perk.
  - `LUNAR_DEBUG_PREVIEW_ROLE_ICONS`: unlocks the Role Icon tab without the perk.
- `LUNAR_MASS_ARCHIVE_THRESHOLD=0` makes every single removal wait for an admin to confirm.

The other settings (check interval, mass-removal threshold, icon size, link lifetimes) have
sensible defaults; see `.env.example`.

### Public address for the color picker

(Checked against Railway's docs on 2026-10-18.)

1. In the bot's service: **Settings → Networking → Public Networking → Generate Domain**. You get
   a `*.up.railway.app` address. If the service has a TCP Proxy, the button is hidden until the
   proxy is removed.
2. **Target port:** Railway detects the port when the app listens on only one, and you can change
   it with the edit icon next to the domain. It must be the same as `DASHBOARD_PORT` (8080).
3. Set `LUNAR_PUBLIC_URL=https://<that domain>` and redeploy.
4. Open `https://<the domain>/lunar`. You should see the picker page saying no link was found.
   Then run `/lunar color-picker` in Discord and open the link.

**Custom domain (optional):** add it in the same Networking section. Railway shows a `CNAME` and a
`TXT` record, and **both** are needed: without the TXT record the domain returns 404 even once
the CNAME works. HTTPS certificates are automatic for both kinds of domain. Change
`LUNAR_PUBLIC_URL` to the custom domain afterwards.

**Things Railway's docs didn't confirm:**
- **`PORT`:** the docs don't say whether Railway sets a `PORT` variable. The bot ignores `PORT` and
  listens on `DASHBOARD_PORT`, so just make sure the domain's target port matches it.
- **`0.0.0.0` vs `::`:** if the domain says the application failed to respond, check the port
  first, then try `DASHBOARD_HOST=::`.
- **`X-Forwarded-For`:** Railway documents `X-Real-IP` and `X-Forwarded-Proto: https`, but doesn't
  mention `X-Forwarded-For`.
  - With `LUNAR_TRUST_PROXY=true`, the bot uses the **rightmost** `X-Forwarded-For` entry (the one
    a proxy appends). The leftmost entries are ignored because visitors can make them up.
  - If Railway doesn't append to it, the bot falls back to the proxy's own address, so all
    visitors share one limit for *bad* links. That's safe: valid links are never blocked by it.
  - Worth checking which headers arrive after the first deploy.

**Dashboard caveat (not Lunar Roles):** behind Railway's HTTPS proxy, the separate web dashboard
will probably refuse its own changes with "Cross-origin requests are not allowed." See
[section 7](#7-still-unverified-and-known-issues). The color picker isn't affected.

## 3. First-time setup in the server

Lunar Roles is **off by default**. Until an admin finishes these steps, `/lunar` commands reply
that it isn't set up yet. `/lunar-admin` commands need **Manage Roles**, so other members don't
see them.

1. **Place the bot's role.** In Server Settings → Roles, drag the bot's own role **above** the
   spot where custom roles should go. Discord only lets the bot manage roles below its own.
2. **Choose the anchor role.** Custom roles are created next to it.
   - Run `/lunar-admin anchor role:<role> place:above`.
   - `above` is recommended: custom roles then sit above the server's other colored roles. A
     member's name color comes from their highest colored role, so a custom role below another
     colored role won't show.
   - The anchor must be below the bot's role. Existing roles aren't moved.
3. **Set the log channel.** Run `/lunar-admin log-channel channel:#lunar-logs` (a staff-only
   channel).
   - It keeps a history of every change, plus warnings and the mass-removal alerts with their
     Confirm/Cancel buttons.
   - The file log (`logs/lunar_roles.log`) is wiped on every restart, so this channel is the
     real history.
4. **Set the booster channel (optional).** Run `/lunar-admin channel channel:#booster-lounge` to
   allow `/lunar` commands only in that channel and its threads. Leave it out (or run it empty) to
   allow them anywhere. `/lunar-admin` commands always work everywhere.
5. **Optional extras:**
   - `/lunar-admin allow-role add role:<role>`: members with this role qualify too, without
     boosting.
   - `/lunar-admin cooldown seconds:<n>`: a wait between changes (0 = off, the default).
   - `/lunar-admin blocked-words add word:<word>`: more words to keep out of role names. Built-in
     protected words (admin, mod, staff, nitro, …) are already on.
6. **Turn it on.** Run `/lunar-admin enable`. Boosters who already have saved roles get them back
   straight away.
7. **Check.** Run `/lunar-admin settings`.
   - **Server features** should show whether the server has gradient/holographic styles (they
     need 3 server boosts) and role icons (they need Boost Level 2).
   - **Problems** should be empty.
   - If there's a "Colors may be hidden" warning, some colored roles sit above the custom roles.
     Move the anchor up, or move those roles down.
8. **Try it.** As a booster, run `/lunar role name:Test`, then `/lunar color-picker`.

**Moving from `/nitro-role-set`:** the old booster role command is gone. Existing roles from it
were copied once into Lunar Roles. They're picked up when the bot starts, and their names are read
from Discord. The old `booster_roles` table is left in place.

## 4. Theming the color picker

To restyle the page, edit **only** `web/static/lunar/lunar-theme.css`.

- Every color, radius, font, spacing and size the page uses is a `--lp-*` variable in that file,
  grouped by area (page, controls, messages, preview cards, icon crop, shape, type, spacing,
  sizes), and each has a comment saying what it changes.
- `picker.css` only refers to these variables. Don't put colors, sizes or fonts in it; an offline
  test fails if you do.
- **Not covered by the theme (on purpose):**
  - The preview cards copy Discord's own dark and light themes, so members see roughly what
    Discord shows. Change those variables only if Discord changes its colors.
  - The holographic colors are Discord's fixed preset.
  - The color square's overlays and the hue rainbow are drawn by `picker.js`, because they show
    the colors being picked.
  - `favicon.svg` has its own two colors, because a favicon can't read CSS variables.
- The page is dark (`color-scheme: dark`). For a light page, change `color-scheme` and the page
  and control colors together.
- **Trying changes:** the bot reads the files on every request, so locally a browser refresh
  shows the change. On Railway, push and redeploy.
- **Accessibility:** keep text readable (about 4.5:1 contrast against its background), and keep
  the focus ring (`--lp-focus`) clearly visible.

## 5. Boosted server final check

Lunar Lab, the test server, had no boosts. So gradients, holographic and role icons were only
tested live as the "not available here" refusals; their success paths have offline tests only.

The two perks have different requirements in Discord
([Discord's article](https://support.discord.com/hc/en-us/articles/31444213087255)):
- **Gradient and holographic** ("Enhanced Role Styles") need **3 server boosts**, and no Boost
  Level.
- **Role icons** need **Boost Level 2**.

So a server with 3 boosts can already do part 5a; part 5b waits for Boost Level 2. Do each part
once on the real server, as a booster, with Lunar Roles set up (section 3). Anything that fails:
check the Lunar log channel and `logs/lunar_roles.log` for the reason.

### 5a. 3-boost check: gradients and holographic

First, `/lunar-admin settings` → **Server features** should show ✅ for
**Gradient / holographic (3 boosts)**.

**Colors**
- [ ] `/lunar color set color:#A78BFA secondary_color:#60A5FA`: the name shows a gradient in the
      member list and in chat.
- [ ] `/lunar color holographic`: the holographic style shows.
- [ ] `/lunar color set color:#A78BFA`: back to solid; the gradient is gone.
- [ ] In the color picker, the Gradient and Holographic designs aren't locked. Setting each one
      changes the role in Discord, and the preview roughly matches.
- [ ] `/lunar palette`: picking a secondary color makes a gradient.
- [ ] A member stops boosting (or loses the allowed role) and qualifies again: the gradient comes
      back with the role.

### 5b. Boost Level 2 check: role icons

First, `/lunar-admin settings` → **Server features** should show ✅ for
**Role icons (Boost Level 2)**.

**Role icons: set**
- [ ] `/lunar icon image:<a PNG or JPEG photo>`: the icon shows next to the name in chat.
- [ ] `/lunar icon emoji:🌙`: the emoji becomes the icon.
- [ ] Color picker → Role Icon → **Upload**: pick a photo, drag and zoom the crop, then **Set
      icon**. The icon in Discord shows the part you cropped.
- [ ] Role Icon → **Link**: paste a direct image link (for example a Wikimedia "Original file"
      link). It loads into the crop editor and can be set.
- [ ] Role Icon → **Emoji**: one emoji can be set.

**Role icons: edit crop**
- [ ] After setting an image icon, reload the picker and click **Edit current crop**. The original
      opens at the saved crop. Change it and **Set icon**; Discord shows the new crop.
- [ ] An icon set with `/lunar icon` can also be re-cropped this way (it starts centred).

**Role icons: remove**
- [ ] **Remove current icon** in the picker: the icon disappears in Discord.
- [ ] `/lunar icon` with no options also removes it.

**Role icons: quality**
- [ ] Discord shows the icon sharp at **256 px**. Open the role in Server Settings → Roles, or
      open the icon image in a browser: it should be 256×256 for a crop of at least 256 px.
      Smaller crops give 128 or 64 px icons, and very detailed images can drop to 128 px to stay
      under Discord's 256 KB limit.
- [ ] The icon looks right in both Discord's dark and light themes.
- [ ] A member stops boosting (or loses the allowed role) and qualifies again: the icon comes back
      with the role.

## 6. Behaviour worth knowing

- **Who qualifies:** server boosters, plus members holding an allowed role
  (`/lunar-admin allow-role`).
  - Losing eligibility or leaving deletes the custom role but saves its settings. Qualifying
    again restores it near its old spot.
  - Losing the allowed role, the role being taken off the list, or the role being deleted all
    count as no longer qualifying.
- **Blocked words:**
  - Custom blocked words match anywhere in a name, so a short word like "ass" also blocks "Class".
  - Built-in words (admin, mod, dev, staff, …) match whole words only, ignoring case, leetspeak
    (`m0d`) and separators (`a.d.m.i.n`).
  - Names that copy a role with moderation permissions are refused too.
  - Blocking a word renames existing roles that break the rule and DMs their owners.
- **Mass-removal guard:**
  - An admin action that would remove more than the threshold (`LUNAR_MASS_ARCHIVE_THRESHOLD`,
    10) asks for a 60-second confirmation.
  - Automatic mass removals (an allowed role deleted, another bot stripping a role, a big check)
    are held until an admin confirms, in the log channel or with `/lunar-admin pending`. Held
    removals never expire.
  - Cancel keeps the roles and asks again after 24 hours.
- **Untrusted data:** if the member list can't be fully loaded, the bot lacks Manage Roles, or the
  server is unavailable, the check removes nothing that run and tries again next time.
- **Command channel:** `/lunar-admin channel` limits `/lunar` commands to one channel and its
  threads. If that channel is deleted, the limit lapses.
- **Cooldown:** renames, colors, icons and `/lunar position` moves count as changes. Creating or
  restoring a role doesn't, and admins aren't exempt. In one `/lunar palette` menu only the first
  pick is checked.
- **Moving roles:** members can put their role directly above or below another member's custom
  role with `/lunar position`.
- **`/lunar-admin remove`** deletes a member's custom role and its saved settings, so it won't
  come back. With a `reason` the member gets a DM with it; without one they aren't told.
  - There's no way to block someone from making a new role. Mods use Discord's own tools
    (timeouts, kicks, bans, removing the allowed role) for repeat offenders.
- **Log entries** show a role's name next to its mention, because Discord shows a deleted role's
  mention as "@unknown-role".
- **Color picker links:**
  - Each link is private, and a new one replaces the old.
  - **How long a link lasts:** it closes after 1 hour without use (`LUNAR_PICKER_IDLE_TTL`), and
    after 3 hours at the latest (`LUNAR_PICKER_MAX_TTL`). Every successful page request (loading,
    saving) restarts the 1-hour clock; trying colors without saving doesn't.
  - The token sits after `#` in the link, so it's never sent to a server in an address or logged.
    The page sends it only in an `Authorization` header and refuses it in a URL.
  - Every request checks again that the member is in the server, still qualifies and has a role.
    Losing the role, an admin `remove` or disabling Lunar Roles ends access at once.
  - Limits: 60 reads and 20 changes a minute per link, and 30 bad links per address per
    10 minutes.
- **Color picker page:**
  - It has a live preview of Discord's dark and light themes, plus Color, Role Icon and Name tabs.
  - Changes made on the page follow the same rules as the commands (name filter, cooldown, server
    perks) and are logged the same way.
  - **Images on the page** only ever come from the bot itself (`data:`/`blob:` URLs, enforced by
    the page's CSP). Avatars and Discord-hosted icons are downloaded by the bot and passed on.
- **Role icon images** (the same rules for `/lunar icon`, uploads and links):
  - **Accepted:** PNG or JPEG, checked by the file's content (not its name). Up to 8 MB
    (`LUNAR_ICON_SOURCE_MAX_BYTES`), **8192 px a side** and **16 million pixels** in total.
    Animated images are refused.
  - **Phone photos:** a normal 12 MP photo (4032×3024) fits. A full 48 MP photo (8064×6048) is
    refused with "Try a 12 MP photo or a screenshot." Most phones save 12 MP unless a 48 MP mode
    is on.
  - **Refusal messages name the limit hit**, for example "This image is 9000 px tall; the limit is
    8192 px per side." Sizes are as the photo is shown (with the camera's rotation applied).
  - **HEIC/HEIF (iPhone photos)** aren't supported. They're recognised by their content and get
    "iPhone HEIC photos aren't supported. Save it as JPEG or PNG (or take a screenshot) and try
    again." When choosing a photo in Safari on an iPhone, the upload box asks for PNG/JPEG, so
    iOS usually converts the photo to JPEG by itself.
  - **The final icon:** the largest of 256, 128 or 64 px (never larger than the crop) that fits
    under 256 KB, resized with LANCZOS and saved as PNG.
  - **Memory:** a 16-megapixel image takes about 64 MB while it's processed, server-side and in
    the member's browser. The page reads an image's size from its header before the browser
    decodes it, so a decompression bomb is refused without freezing the browser. The page only
    draws onto a small 128 px preview canvas, far below iPhone Safari's canvas limit.
- **Image links (Role Icon tab):** the bot downloads them itself, with these rules:
  - **Allowed links:** `https://` on port 443 only, with no username or password in the link.
  - **Public addresses only:** every address the name resolves to must be public (an
    allow-list). Private, local, cloud-metadata and IPv6-wrapped private addresses (6to4, NAT64,
    Teredo, IPv4-mapped) are refused.
  - **Pinned connection:** the bot connects only to the addresses it checked.
  - **Download limits:** no redirects, 10 seconds, 8 MB, PNG/JPEG only, checked again by content.
  - **Rate limits:** 6 links a minute per member, and at most 3 fetches at once for the whole bot.
  - **Logging:** only the domain and the outcome go to `logs/lunar_roles.log`, never the full link.
  - **User-Agent:** `LemegetonLunarRoles/1.0 (+<LUNAR_PUBLIC_URL>/lunar; role icon fetch)`. Some
    sites (Wikimedia) refuse requests without a contact address like this.
  - The bot only fetches links on servers that have Role Icons.
- **Migration:** existing `booster_roles` rows were copied once into `lunar_custom_roles` (a marker
  row in `lunar_meta` stops it re-running).
- `/nitro-role-set` and `cogs/customization/server_boost.py` are gone. The boost welcome DM now
  lives in `cogs/customization/lunar_roles.py`.
- **Offline tests:** `tests/lunar_roles/` (see its README). They run against a local development
  PostgreSQL only and never use the real bot token.

## 7. Still unverified, and known issues

**Couldn't be tested in Lunar Lab**
- Gradients, holographic (3 boosts) and role icons (Boost Level 2) succeeding: see the
  [boosted server final check](#5-boosted-server-final-check).
- `/lunar position` moving a role next to another member's role: Lunar Lab had only one member, so
  only the refusals were tested live.
- Slash commands inside threads: they don't show up in threads in Lunar Lab, so "threads of the
  command channel are allowed" is tested offline only.
- On Railway: which forwarded headers arrive (see "Things Railway's docs didn't confirm").
- The picker on phones wasn't tested live.

**Issues outside Lunar Roles (not fixed)**
- `cogs_test.panel` fails to load ("context menus cannot be defined inside a class").
- The news and free-games tasks fail at startup with "Client has not been properly initialised"
  (they wait for "ready" before the bot has logged in).
- Some other cogs query tables or columns that don't exist in PostgreSQL (`paginator_state`,
  `guild_config`, …), which logs errors at startup.
- **Dashboard writes behind Railway's proxy:** the dashboard's same-origin check builds the
  expected address from the request's own scheme (`request.scheme`). Behind Railway's HTTPS proxy
  that scheme is `http`, while the browser's `Origin` is `https://…`. So dashboard POST/PUT
  requests (sync, reset, toggling commands) will probably be refused with "Cross-origin requests
  are not allowed." The color picker doesn't have this problem: it checks against
  `LUNAR_PUBLIC_URL`.

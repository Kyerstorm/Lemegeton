# Lunar Roles — Handoff Notes

Running notes for whoever deploys or maintains Lunar Roles (custom booster roles).
The full build spec is in [LUNAR_ROLES_SPEC.md](LUNAR_ROLES_SPEC.md).

## Deployment (Railway)

- Set `ENVIRONMENT=production` on Railway. When it's unset, the bot treats itself as development.
- Never set `LUNAR_DEBUG_FAIL_MEMBER_FETCH`, `LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS`,
  `LUNAR_DEBUG_PREVIEW_ROLE_ICONS` or `LUNAR_MASS_ARCHIVE_THRESHOLD=0` in production.
  - `LUNAR_DEBUG_FAIL_MEMBER_FETCH` is a test switch that stops reconcile from removing any roles.
    It only takes effect when `ENVIRONMENT=development`, and it logs a loud warning at startup and
    in every log channel while it's on.
  - `LUNAR_DEBUG_PREVIEW_ENHANCED_COLORS` is a test switch that unlocks Gradient and Holographic
    in the color picker page on a server without Enhanced Role Colors, so their design can be
    checked. Saving them is still refused. It only takes effect when `ENVIRONMENT=development`, and
    it logs the same loud warning at startup and in every log channel.
  - `LUNAR_DEBUG_PREVIEW_ROLE_ICONS` is the same kind of test switch for the picker's Role Icon
    tab on a server without Role Icons (Boost Level 2): upload, link and crop work, but setting
    the icon is refused.
  - `LUNAR_MASS_ARCHIVE_THRESHOLD=0` makes every single removal wait for an admin to confirm.
- Lunar Roles settings and their defaults (see `.env.example`):
  - `LUNAR_RECONCILE_MINUTES=30`: minutes between automatic checks; one also runs at startup.
  - `LUNAR_MASS_ARCHIVE_THRESHOLD=10`: removing more than this many custom roles at once needs an
    admin to confirm.
  - `LUNAR_ICON_SOURCE_MAX_BYTES=8388608` (8 MB): the largest original image for a role icon,
    by upload, link or `/lunar icon`.
- **Database storage for icons:** each member's original icon image is kept exactly as uploaded
  (up to 8 MB), so it can be re-cropped later without losing quality.
  - The final icon sent to Discord is a separate small PNG (at most 256 KB).
  - Worst case is about 8 MB per member with an image icon. A typical phone photo is 2–5 MB, and
    most uploads are far smaller.
  - Originals are kept for saved (archived) roles too, so they come back on restore.
  - They're deleted when the icon is removed or replaced by an emoji, and by `/lunar-admin remove`.
  - Lower `LUNAR_ICON_SOURCE_MAX_BYTES` to cap this.
- The bot needs the **Server Members** and **Message Content** privileged intents enabled in the
  Discord Developer Portal, or it can't connect.

## Color picker web page (public address)

The picker (`/lunar color-picker`) is a small web page served by the bot itself, on
`DASHBOARD_HOST:DASHBOARD_PORT`. It doesn't need the dashboard's OAuth settings.

**Railway steps** (checked against Railway's docs on 2026-10-18; links below):
1. In the bot's service: **Settings → Networking → Public Networking → Generate Domain**.
   You get a `*.up.railway.app` address. If the service has a TCP Proxy, the button is hidden
   until the proxy is removed.
2. **Target port:** Railway detects the port when the app listens on only one, and you can change
   it later with the edit icon next to the domain. Make sure it's the same as `DASHBOARD_PORT`
   (8080 by default).
3. Set these variables on the service:
   - `LUNAR_PUBLIC_URL=https://<the domain>` (no trailing slash)
   - `DASHBOARD_HOST=0.0.0.0`
   - `DASHBOARD_PORT=8080`
   - `LUNAR_PICKER_ENABLED=true`
   - `LUNAR_TRUST_PROXY=true` (see the caveat below)
   - `ENVIRONMENT=production`
4. Redeploy, then open `https://<the domain>/lunar`. You should see the picker page saying no
   link was found. Then run `/lunar color-picker` in Discord and open the link.

**Custom domain (optional):** add it in the same Networking section. Railway shows a `CNAME`
and a `TXT` record, and **both** are needed: without the TXT record the domain returns 404 even
once the CNAME works. HTTPS certificates are automatic for both kinds of domain.

**Things Railway's docs didn't confirm:**
- **`PORT`:** the pages read don't say whether Railway sets a `PORT` variable or what happens if
  you set one. The bot ignores `PORT` and listens on `DASHBOARD_PORT`, so just make sure the
  domain's target port matches it.
- **`0.0.0.0` vs `::`:** the docs don't say which address public networking needs. `0.0.0.0` is
  the usual choice. If the domain says the application failed to respond, check the port first,
  then try `DASHBOARD_HOST=::`.
- **`X-Forwarded-For`:** Railway documents `X-Real-IP` as the header with the visitor's address
  and `X-Forwarded-Proto: https`, but doesn't mention `X-Forwarded-For`.
  - With `LUNAR_TRUST_PROXY=true`, the bot uses the **rightmost** `X-Forwarded-For` entry, the one
    a proxy appends. The leftmost entries are ignored because visitors can make them up.
  - If Railway doesn't append to `X-Forwarded-For`, the bot falls back to the proxy's own address,
    so all visitors share one limit for *bad* links. That's safe: valid links are never blocked
    by it, so the worst case is a weaker limit on link guessing.
  - Check after the first deploy which headers actually arrive.

**How links behave:**
- Links are kept in memory, so run **one copy** of the bot only. Every restart or redeploy ends
  all open links, and members just run `/lunar color-picker` again.
- In production the bot only hands out `https://` links. With an `http://` `LUNAR_PUBLIC_URL` it
  refuses and posts the reason in the Lunar log channel.

## Server setup (per server)

- The feature is **off by default**. An admin runs `/lunar-admin anchor` and then
  `/lunar-admin enable`; until then, user commands say Lunar Roles isn't set up.
- Pick the anchor with `place:above`, so custom roles sit above any other colored roles.
  The highest colored role a member has decides their name color.
- The bot needs **Manage Roles**, and its own role must be above the anchor.
- `/lunar-admin` commands need Manage Roles, so members without it won't see them.
- Set a log channel with `/lunar-admin log-channel` to keep a history. `logs/lunar_roles.log`
  is wiped on every restart.
- Log entries show a role's name next to its mention, because Discord shows a deleted role's
  mention as "@unknown-role".

## Behaviour worth knowing

- **Blocked words:**
  - Custom blocked words match anywhere in a name, so a short word like "ass" also blocks "Class".
  - Built-in words (admin, mod, dev, staff, …) match whole words only, ignoring case,
    leetspeak (`m0d`) and separators (`a.d.m.i.n`).
  - Names that copy a role with moderation permissions are refused too.
  - Blocking a word renames existing roles that break the rule and DMs their owners.
- **Who qualifies:** server boosters, plus members holding an "allowed role"
  (`/lunar-admin allow-role`). Losing eligibility or leaving deletes the custom role but saves its
  settings, and qualifying again restores it.
- **Mass-removal guard:**
  - An admin action that would remove more than the threshold asks for a 60-second confirmation.
  - Automatic mass removals (an allowed role deleted, another bot stripping a role, a big
    reconcile) are held until an admin confirms. See `/lunar-admin pending` or the log channel.
    Held removals never expire.
  - Cancel keeps the roles and asks again after 24 hours.
- **Untrusted data:** if the member list can't be fully loaded, the bot lacks Manage Roles, or the
  server is unavailable, reconcile removes nothing that run and tries again next time.
- **Command channel:** `/lunar-admin channel` limits `/lunar` commands to one channel and its
  threads (no channel = anywhere). `/lunar-admin` commands work everywhere. If that channel is
  deleted, the limit lapses.
- **Cooldown:** `/lunar-admin cooldown` (0 = off, the default; at most 1 day). Renames, colors,
  icons and `/lunar position` moves count as changes. Creating or restoring a role doesn't, and
  admins aren't exempt. In one `/lunar palette` menu only the first pick is checked.
- **Moving roles:** members can put their role directly above or below another member's custom
  role with `/lunar position`. A role that comes back after a member qualifies again returns near
  its old spot among the custom roles; with no other custom roles it goes by the anchor.
- **`/lunar-admin list`** shows every custom role (owner, role, status), 10 per page.
- **`/lunar-admin remove`** deletes a member's custom role and its saved settings, so it won't
  come back. With a `reason` the member gets a DM with it; without one they aren't told.
  - It also takes them out of a pending removal.
  - There's no way to block someone from making a new role. Mods use Discord's own tools
    (timeouts, kicks, bans, removing the allowed role) for repeat offenders.
- **Color picker links:**
  - Each link is private, and a new one replaces the old.
  - **How long a link lasts:** it closes after 1 hour without use (`LUNAR_PICKER_IDLE_TTL`,
    seconds), and after 3 hours at the latest (`LUNAR_PICKER_MAX_TTL`). Every successful page
    request (loading, saving) restarts the 1-hour clock. Fiddling with colors without saving
    doesn't count as use.
  - The token sits after `#` in the link, so it's never sent to a server in an address or logged.
  - The page sends it only in an `Authorization` header and refuses it in a URL.
  - Every request re-checks that the member is in the server, still qualifies and has a role.
    Losing the role, an admin `remove` or disabling Lunar Roles ends access at once.
  - Limits: 60 reads and 20 changes a minute per link, and 30 bad links per address per
    10 minutes.
- **Image links (Role Icon tab):** the bot downloads them itself, with these rules:
  - **Allowed links:** `https://` on port 443 only, with no username or password in the link.
  - **Public addresses only:** every address the name resolves to must be public (an
    allow-list). Private, local, cloud-metadata and IPv6-wrapped private addresses
    (6to4, NAT64, Teredo, IPv4-mapped) are refused.
  - **Pinned connection:** the bot connects only to the addresses it checked.
  - **Download limits:** no redirects, 10 seconds, 8 MB, PNG/JPEG only, checked again by content.
  - **Rate limits:** 6 links a minute per member, and at most 3 fetches at once for the whole bot.
  - **Logging:** only the domain and the outcome go to `logs/lunar_roles.log`, never the full link.
  - **User-Agent:** `LemegetonLunarRoles/1.0 (+<LUNAR_PUBLIC_URL>/lunar; role icon fetch)`.
    Some sites (Wikimedia) refuse requests without a contact address like this.
  - The bot only fetches links on servers that have Role Icons (or with the test switch on).
- **Color picker page:**
  - It has a live preview of Discord's dark and light themes, plus Color, Role Icon and Name tabs.
  - **Role Icon tab:**
    - **Sources:** upload a PNG/JPEG, load one from a link, or type one emoji.
    - **Cropping:** images are cropped in the page (drag, zoom, keyboard), and the server cuts the
      square from the original.
    - **The icon sent to Discord:** the largest of 256, 128 or 64 px that fits under 256 KB
      (LANCZOS, PNG). `/lunar icon` uses the same rule, and its icons can be re-cropped from the
      picker.
    - "Edit current crop" reopens the stored original at the saved crop.
  - **Image size check:** the page reads an image's width and height from its header before the
    browser decodes it, so a decompression bomb is refused without freezing the member's browser.
  - **Images on the page** only ever come from the bot itself (`data:`/`blob:` URLs, enforced by
    the page's CSP). Avatars and Discord-hosted icons are downloaded by the bot and passed on.
  - Changes made on the page follow the same rules as the commands (name filter, cooldown,
    feature checks) and are logged the same way.
  - **Restyling:** edit only `web/static/lunar/lunar-theme.css`. Every color, radius, font,
    spacing and size is there, each with a comment.
    - `picker.css` must not contain any (a test checks).
    - The favicon (`favicon.svg`) has its own two colors.
- **Migration:** existing `booster_roles` rows were copied once into `lunar_custom_roles` (a marker
  row in `lunar_meta` stops it re-running). The old table is left in place.
- `/nitro-role-set` and `cogs/customization/server_boost.py` are gone. The boost welcome DM now
  lives in `cogs/customization/lunar_roles.py`.

## Still to verify

- Final icon and gradient check needs a boosted server. The test server (Lunar Lab) has neither
  `ENHANCED_ROLE_COLORS` (gradient/holographic) nor `ROLE_ICONS` (Boost Level 2), so only the
  "not available here" refusals were tested live; the success paths have offline tests only.
- `/lunar position` moving a role next to another member's role: Lunar Lab has only one member,
  so only the refusals were tested live.
- Slash commands inside threads: they don't show up in threads in Lunar Lab, so "threads of the
  command channel are allowed" is tested offline only.
- On Railway: which forwarded headers arrive (see "Things Railway's docs didn't confirm").

## Pre-existing issues outside Lunar Roles (not fixed)

- `cogs_test.panel` fails to load ("context menus cannot be defined inside a class").
- The news and free-games tasks fail at startup with "Client has not been properly initialised"
  (they wait for "ready" before the bot has logged in).
- **Dashboard writes behind Railway's proxy:** the dashboard's same-origin check builds the
  expected address from the request's own scheme (`request.scheme`). Behind Railway's HTTPS proxy
  that scheme is `http`, while the browser's `Origin` is `https://…`. So dashboard POST/PUT
  requests (sync, reset, toggling commands) will probably be refused with "Cross-origin requests
  are not allowed." The color picker doesn't have this problem: it checks against
  `LUNAR_PUBLIC_URL`.

# Custom Roles — Setup and Handoff Guide

Everything needed to run Custom Roles (custom booster roles) on the real server: deploying on
Railway, first-time setup in Discord, theming the color picker, and the checks that could only be
done on a boosted server.

- What Custom Roles does and every command: the [Custom Roles section of the README](../README.md#-custom-roles)
- All settings with their defaults: the `CUSTOM ROLES` block at the end of [`.env.example`](../.env.example)
- The original design spec: [CUSTOM_ROLES_SPEC.md](CUSTOM_ROLES_SPEC.md)

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
  `/custom-role color-picker` again).
- **Database:** Custom Roles uses the bot's normal PostgreSQL database (`DATABASE_URL`). Its tables
  are created automatically at startup.
  - **Icon storage:** each member's original icon image is kept exactly as uploaded (up to 8 MB),
    so it can be re-cropped later without losing quality. The icon sent to Discord is a separate
    small PNG (at most 256 KB).
  - Worst case is about 8 MB per member with an image icon. A typical phone photo is 2–5 MB, and
    most uploads are far smaller.
  - Originals are kept for saved roles too, so they come back on restore. They're deleted when the
    icon is removed or replaced by an emoji, and by `/custom-role-admin remove`.
  - Lower `CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES` to cap this.

## 2. Railway setup

### Variables

Set these on the bot's Railway service, alongside the bot's usual ones (`DISCORD_TOKEN`,
`DATABASE_URL`, …):

| Variable | Value | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | **Required.** When unset, the bot treats itself as development: the test switches would work and `http://` picker links would be handed out. |
| `CUSTOM_ROLES_PUBLIC_URL` | `https://<your domain>` | The picker's address, with no trailing slash. In production the bot only hands out `https://` links; with `http://` it refuses and posts the reason in the custom roles log channel. |
| `DASHBOARD_HOST` | `0.0.0.0` | Listen on all addresses, so Railway can reach the page. |
| `DASHBOARD_PORT` | `8080` | Must match the domain's target port (below). |
| `CUSTOM_ROLES_PICKER_ENABLED` | `true` | The default; set it to `false` to turn the picker off. |
| `CUSTOM_ROLES_TRUST_PROXY` | `true` | Use the visitor's address from Railway's proxy for the bad-link limit (see the caveat below). |

**Never set these in production:** `CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH`,
`CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS`, `CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS`, or
`CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD=0`.
- The three `CUSTOM_ROLES_DEBUG_*` switches are for testing only. They only take effect when
  `ENVIRONMENT=development`, and while one is on the bot prints a loud `!!!` warning at startup
  and posts 🚧 in every custom roles log channel. If you ever see that warning on Railway, remove the
  variable.
  - `CUSTOM_ROLES_DEBUG_FAIL_MEMBER_FETCH`: checks remove no roles.
  - `CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS`: unlocks the Gradient/Holographic preview without the
    server perk.
  - `CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS`: unlocks the Role Icon tab without the perk.
- `CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD=0` makes every single removal wait for an admin to confirm.

The other settings (check interval, mass-removal threshold, icon size, link lifetimes) have
sensible defaults; see `.env.example`.

### Public address for the color picker

(Checked against Railway's docs on 2026-10-18.)

1. In the bot's service: **Settings → Networking → Public Networking → Generate Domain**. You get
   a `*.up.railway.app` address. If the service has a TCP Proxy, the button is hidden until the
   proxy is removed.
2. **Target port:** Railway detects the port when the app listens on only one, and you can change
   it with the edit icon next to the domain. It must be the same as `DASHBOARD_PORT` (8080).
3. Set `CUSTOM_ROLES_PUBLIC_URL=https://<that domain>` and redeploy.
4. Open `https://<the domain>/custom-roles`. You should see the picker page saying no link was found.
   Then run `/custom-role color-picker` in Discord and open the link.

**Custom domain (optional):** add it in the same Networking section. Railway shows a `CNAME` and a
`TXT` record, and **both** are needed: without the TXT record the domain returns 404 even once
the CNAME works. HTTPS certificates are automatic for both kinds of domain. Change
`CUSTOM_ROLES_PUBLIC_URL` to the custom domain afterwards.

**Things Railway's docs didn't confirm:**
- **`PORT`:** the docs don't say whether Railway sets a `PORT` variable. The bot ignores `PORT` and
  listens on `DASHBOARD_PORT`, so just make sure the domain's target port matches it.
- **`0.0.0.0` vs `::`:** if the domain says the application failed to respond, check the port
  first, then try `DASHBOARD_HOST=::`.
- **`X-Forwarded-For`:** Railway documents `X-Real-IP` and `X-Forwarded-Proto: https`, but doesn't
  mention `X-Forwarded-For`.
  - With `CUSTOM_ROLES_TRUST_PROXY=true`, the bot uses the **rightmost** `X-Forwarded-For` entry (the one
    a proxy appends). The leftmost entries are ignored because visitors can make them up.
  - If Railway doesn't append to it, the bot falls back to the proxy's own address, so all
    visitors share one limit for *bad* links. That's safe: valid links are never blocked by it.
  - Worth checking which headers arrive after the first deploy.

**Dashboard caveat (not Custom Roles):** behind Railway's HTTPS proxy, the separate web dashboard
will probably refuse its own changes with "Cross-origin requests are not allowed." See
[section 7](#7-still-unverified-and-known-issues). The color picker isn't affected.

## 3. First-time setup in the server

Custom Roles is **off by default**. Until an admin finishes these steps, `/custom-role` commands reply
that it isn't set up yet. `/custom-role-admin` commands need **Manage Roles**, so other members don't
see them.

1. **Place the bot's role.** In Server Settings → Roles, drag the bot's own role **above** the
   spot where custom roles should go. Discord only lets the bot manage roles below its own.
2. **Choose the anchor role.** Custom roles are created next to it.
   - Run `/custom-role-admin anchor role:<role> place:above`.
   - `above` is recommended: custom roles then sit above the server's other colored roles. A
     member's name color comes from their highest colored role, so a custom role below another
     colored role won't show.
   - The anchor must be below the bot's role. Existing roles aren't moved.
3. **Import the old `/nitro-role-set` roles** (do this right after the anchor). Run
   `/custom-role-admin import-legacy`. It only shows a preview at first:
   - **Will be taken over:** members who qualify and still have their old role. It becomes their
     custom role exactly as it is (name, color, position); no new role is made.
   - **Members who don't qualify** (stopped boosting, or left the server): listed separately.
     Their old roles stay untouched unless you press **Take over … and archive …**. Archiving
     deletes the role from Discord and saves its settings, so it comes back if they qualify
     again.
   - **Skipped:** the role no longer exists, or the bot can't safely take it over (it's above the
     bot's role, or has moderation permissions). Also members who already have a different custom
     role; those have two roles, so remove one by hand.
   - Then press **Take over N** (or **Take over N and archive M**), or **Cancel**. The buttons last
     2 minutes, and only you can press them.
   - **Nothing is deleted** from the old `booster_roles` table, and you can run the command again
     any time; already imported roles are skipped.
   - If some members qualify through an allowed role instead of boosting, add it first
     (`/custom-role-admin allow-role add`), or they'll show up as not qualifying.
   - If a member uses any `/custom-role` command (once Custom Roles is on) before you've imported, they
     take over their own old role automatically, so roles never stack. `/custom-role-admin settings` lists "Old /nitro-role-set roles
     not imported yet: N" under **Problems** while there are any.
4. **Set the log channel.** Run `/custom-role-admin log-channel channel:#role-logs` (a staff-only
   channel).
   - It keeps a history of every change, plus warnings and the mass-removal alerts with their
     Confirm/Cancel buttons.
   - The file log (`logs/custom_roles.log`) is wiped on every restart, so this channel is the
     real history.
5. **Set the booster channel (optional).** Run `/custom-role-admin channel channel:#booster-lounge` to
   allow `/custom-role` commands only in that channel and its threads. Leave it out (or run it empty) to
   allow them anywhere. `/custom-role-admin` commands always work everywhere.
6. **Optional extras:**
   - `/custom-role-admin allow-role add role:<role>`: members with this role qualify too, without
     boosting.
   - `/custom-role-admin cooldown seconds:<n>`: a wait between changes (0 = off, the default).
   - `/custom-role-admin blocked-words add word:<word>`: more words to keep out of role names. Built-in
     protected words (admin, mod, staff, nitro, …) are already on.
7. **Turn it on.** Run `/custom-role-admin enable`. Boosters who already have saved roles get them back
   straight away. **While Custom Roles is off, nothing is removed automatically**; once it's on,
   the regular check (every 30 minutes) removes roles of members who no longer qualify.
8. **Check.** Run `/custom-role-admin settings`.
   - **Server features** should show whether the server has gradient/holographic styles (they
     need 3 server boosts) and role icons (they need Boost Level 2).
   - **Problems** should be empty.
   - If there's a "Colors may be hidden" warning, some colored roles sit above the custom roles.
     Move the anchor up, or move those roles down.
9. **Try it.** As a booster, run `/custom-role role name:Test`, then `/custom-role color-picker`.

**Moving from `/nitro-role-set`:** the old booster role command is gone. Its roles are never
copied automatically; they come over through step 3 (or when their member first uses `/custom-role`).
The old `booster_roles` table is left in place and never changed.

## 4. Theming the color picker

To restyle the page, edit **only** `web/static/custom_roles/theme.css`.

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
once on the real server, as a booster, with Custom Roles set up (section 3). Anything that fails:
check the custom roles log channel and `logs/custom_roles.log` for the reason.

### 5a. 3-boost check: gradients and holographic

First, `/custom-role-admin settings` → **Server features** should show ✅ for
**Gradient / holographic (3 boosts)**.

**Colors**
- [ ] `/custom-role color set color:#A78BFA secondary_color:#60A5FA`: the name shows a gradient in the
      member list and in chat.
- [ ] `/custom-role color holographic`: the holographic style shows.
- [ ] `/custom-role color set color:#A78BFA`: back to solid; the gradient is gone.
- [ ] In the color picker, the Gradient and Holographic designs aren't locked. Setting each one
      changes the role in Discord, and the preview roughly matches.
- [ ] `/custom-role palette`: picking a secondary color makes a gradient.
- [ ] A member stops boosting (or loses the allowed role) and qualifies again: the gradient comes
      back with the role.

### 5b. Boost Level 2 check: role icons

First, `/custom-role-admin settings` → **Server features** should show ✅ for
**Role icons (Boost Level 2)**.

**Role icons: set**
- [ ] `/custom-role icon image:<a PNG or JPEG photo>`: the icon shows next to the name in chat.
- [ ] `/custom-role icon emoji:🌙`: the emoji becomes the icon.
- [ ] Color picker → Role Icon → **Upload**: pick a photo, drag and zoom the crop, then **Set
      icon**. The icon in Discord shows the part you cropped.
- [ ] Role Icon → **Link**: paste a direct image link (for example a Wikimedia "Original file"
      link). It loads into the crop editor and can be set.
- [ ] Role Icon → **Emoji**: one emoji can be set.

**Role icons: edit crop**
- [ ] After setting an image icon, reload the picker and click **Edit current crop**. The original
      opens at the saved crop. Change it and **Set icon**; Discord shows the new crop.
- [ ] An icon set with `/custom-role icon` can also be re-cropped this way (it starts centred).

**Role icons: remove**
- [ ] **Remove current icon** in the picker: the icon disappears in Discord.
- [ ] `/custom-role icon` with no options also removes it.

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
  (`/custom-role-admin allow-role`).
  - Losing eligibility or leaving deletes the custom role but saves its settings. Qualifying
    again restores it near its old spot.
  - Only while Custom Roles is **on**: when it's off, no role is archived automatically (neither by
    the regular check nor by member events). An admin can still confirm removals by hand.
  - Losing the allowed role, the role being taken off the list, or the role being deleted all
    count as no longer qualifying.
- **Blocked words:**
  - Custom blocked words match anywhere in a name, so a short word like "ass" also blocks "Class".
  - Built-in words (admin, mod, dev, staff, …) match whole words only, ignoring case, leetspeak
    (`m0d`) and separators (`a.d.m.i.n`).
  - Names that copy a role with moderation permissions are refused too.
  - Blocking a word renames existing roles that break the rule and DMs their owners.
- **Mass-removal guard:**
  - An admin action that would remove more than the threshold (`CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD`,
    10) asks for a 60-second confirmation.
  - Automatic mass removals (an allowed role deleted, another bot stripping a role, a big check)
    are held until an admin confirms, in the log channel or with `/custom-role-admin pending`. Held
    removals never expire.
  - Cancel keeps the roles and asks again after 24 hours.
- **Untrusted data:** if the member list can't be fully loaded, the bot lacks Manage Roles, or the
  server is unavailable, the check removes nothing that run and tries again next time.
- **Command channel:** `/custom-role-admin channel` limits `/custom-role` commands to one channel and its
  threads. If that channel is deleted, the limit lapses.
- **Cooldown:** renames, colors, icons and `/custom-role position` moves count as changes. Creating or
  restoring a role doesn't, and admins aren't exempt. In one `/custom-role palette` menu only the first
  pick is checked.
- **Moving roles:** members can put their role directly above or below another member's custom
  role with `/custom-role position`.
- **`/custom-role-admin remove`** deletes a member's custom role and its saved settings, so it won't
  come back. With a `reason` the member gets a DM with it; without one they aren't told.
  - There's no way to block someone from making a new role. Mods use Discord's own tools
    (timeouts, kicks, bans, removing the allowed role) for repeat offenders.
- **Log entries** show a role's name next to its mention, because Discord shows a deleted role's
  mention as "@unknown-role".
- **Color picker links:**
  - Each link is private, and a new one replaces the old.
  - **How long a link lasts:** it closes after 1 hour without use (`CUSTOM_ROLES_PICKER_IDLE_TTL`), and
    after 3 hours at the latest (`CUSTOM_ROLES_PICKER_MAX_TTL`). Every successful page request (loading,
    saving) restarts the 1-hour clock; trying colors without saving doesn't.
  - The token sits after `#` in the link, so it's never sent to a server in an address or logged.
    The page sends it only in an `Authorization` header and refuses it in a URL.
  - Every request checks again that the member is in the server, still qualifies and has a role.
    Losing the role, an admin `remove` or disabling Custom Roles ends access at once.
  - Limits: 60 reads and 20 changes a minute per link, and 30 bad links per address per
    10 minutes.
- **Color picker page:**
  - It has a live preview of Discord's dark and light themes, plus Color, Role Icon and Name tabs.
  - Changes made on the page follow the same rules as the commands (name filter, cooldown, server
    perks) and are logged the same way.
  - **Images on the page** only ever come from the bot itself (`data:`/`blob:` URLs, enforced by
    the page's CSP). Avatars and Discord-hosted icons are downloaded by the bot and passed on.
- **Role icon images** (the same rules for `/custom-role icon`, uploads and links):
  - **Accepted:** PNG or JPEG, checked by the file's content (not its name). Up to 8 MB
    (`CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES`), **8192 px a side** and **16 million pixels** in total.
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
  - **Logging:** only the domain and the outcome go to `logs/custom_roles.log`, never the full link.
  - **User-Agent:** `LemegetonCustomRoles/1.0 (+<CUSTOM_ROLES_PUBLIC_URL>/custom-roles; role icon fetch)`. Some
    sites (Wikimedia) refuse requests without a contact address like this.
  - The bot only fetches links on servers that have Role Icons.
- **Old `/nitro-role-set` roles:** `/custom-role-admin import-legacy` (section 3, step 3) or self-adoption
  when the member first uses `/custom-role`. Taking over only creates the custom role record for the existing
  role, so nothing changes in Discord. `booster_roles` is only read, never changed.
- `/nitro-role-set` and `cogs/customization/server_boost.py` are gone. The boost welcome DM now
  lives in `cogs/customization/custom_roles.py`.
- **Offline tests:** `tests/custom_roles/` (see its README). They run against a local development
  PostgreSQL only and never use the real bot token.

## 7. Still unverified, and known issues

**Couldn't be tested in Lunar Lab**
- Gradients, holographic (3 boosts) and role icons (Boost Level 2) succeeding: see the
  [boosted server final check](#5-boosted-server-final-check).
- `/custom-role position` moving a role next to another member's role: Lunar Lab had only one member, so
  only the refusals were tested live.
- Slash commands inside threads: they don't show up in threads in Lunar Lab, so "threads of the
  command channel are allowed" is tested offline only.
- On Railway: which forwarded headers arrive (see "Things Railway's docs didn't confirm").
- The picker on phones wasn't tested live.

**Issues outside Custom Roles (not fixed)**
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
  `CUSTOM_ROLES_PUBLIC_URL`.

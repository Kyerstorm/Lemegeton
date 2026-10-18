# Lunar Roles — Handoff Notes

Running notes for whoever deploys or maintains Lunar Roles (custom booster roles).
The full build spec is in [LUNAR_ROLES_SPEC.md](LUNAR_ROLES_SPEC.md).

## Deployment (Railway)

- Set `ENVIRONMENT=production` on Railway. When it's unset, the bot treats itself as development.
- Never set `LUNAR_DEBUG_FAIL_MEMBER_FETCH` or `LUNAR_MASS_ARCHIVE_THRESHOLD=0` in production.
  - `LUNAR_DEBUG_FAIL_MEMBER_FETCH` is a test switch that stops reconcile from removing any roles.
    It only takes effect when `ENVIRONMENT=development`, and it logs a loud warning at startup and
    in every log channel while it's on.
  - `LUNAR_MASS_ARCHIVE_THRESHOLD=0` makes every single removal wait for an admin to confirm.
- Lunar Roles settings and their defaults (see `.env.example`):
  - `LUNAR_RECONCILE_MINUTES=30`: minutes between automatic checks; one also runs at startup.
  - `LUNAR_MASS_ARCHIVE_THRESHOLD=10`: removing more than this many custom roles at once needs an
    admin to confirm.
- The bot needs the **Server Members** and **Message Content** privileged intents enabled in the
  Discord Developer Portal, or it can't connect.

## Server setup (per server)

- The feature is **off by default**. An admin runs `/lunar-admin anchor` and then
  `/lunar-admin enable`; until then, user commands say Lunar Roles isn't set up.
- Pick the anchor with `place:above`, so custom roles sit above any other colored roles.
  The highest colored role a member has decides their name color.
- The bot needs **Manage Roles**, and its own role must be above the anchor.
- `/lunar-admin` commands need Manage Roles, so members without it won't see them.
- Set a log channel with `/lunar-admin log-channel` to keep a history. `logs/lunar_roles.log`
  is wiped on every restart.

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
- **Migration:** existing `booster_roles` rows were copied once into `lunar_custom_roles` (a marker
  row in `lunar_meta` stops it re-running). The old table is left in place.
- `/nitro-role-set` and `cogs/customization/server_boost.py` are gone. The boost welcome DM now
  lives in `cogs/customization/lunar_roles.py`.

## Still to verify

- Final icon and gradient check needs a boosted server. The test server (Lunar Lab) has neither
  `ENHANCED_ROLE_COLORS` (gradient/holographic) nor `ROLE_ICONS` (Boost Level 2), so only the
  "not available here" refusals were tested live; the success paths have offline tests only.

## Pre-existing issues outside Lunar Roles (not fixed)

- `cogs_test.panel` fails to load ("context menus cannot be defined inside a class").
- The news and free-games tasks fail at startup with "Client has not been properly initialised"
  (they wait for "ready" before the bot has logged in).

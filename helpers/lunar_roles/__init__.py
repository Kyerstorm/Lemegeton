"""Lunar Roles: one custom role per server booster.

Shared logic for the slash commands, the web picker and the automatic events.
This package has no setup() and lives outside cogs/ so the cog loader skips it.

Modules:
    storage  - PostgreSQL access (tables are created in database.init_lunar_roles_tables)
    service  - eligibility, setup checks and every change to a member's role
"""

# Rename the slash command groups here (and only here).
COMMAND_GROUP = "lunar"
ADMIN_GROUP = f"{COMMAND_GROUP}-admin"

# Discord's hard limit on roles per server.
ROLE_LIMIT = 250

# Guild features required for some styles.
FEATURE_GRADIENT = "ENHANCED_ROLE_COLORS"  # "Enhanced Role Styles": 3 server boosts, no Boost Level needed
FEATURE_ICONS = "ROLE_ICONS"               # Role Icons: Boost Level 2

# Discord's fixed holographic preset (primary, secondary, tertiary).
HOLOGRAPHIC_COLORS = (11127295, 16759788, 16761760)

# CLAUDE.md (Lemegeton V2)

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is Lemegeton V2** — a trimmed copy of the original Lemegeton bot. V2 removed the dashboard
> command-management system and the cosmetic theme system (see "What Changed from V1" below). This
> document describes the codebase **as it exists in V2**, not the original — command counts, table
> lists, and feature descriptions below were re-verified against the actual code on 2026-09-19, not
> copied from the original's (partially stale) documentation.

## Project Overview

Lemegeton is a production-ready multi-guild Discord bot for anime/manga tracking with AniList integration, AI-powered recommendations, Steam gaming integration, and comprehensive community features. Built async-first with discord.py 2.6.0 and Python 3.13+.

**Current Version:** V2 — Multi-Guild, no dashboard, no theme system

### Key Features

**🎯 Account & Profile System**
- AniList account linking with OAuth
- Rich profile displays with 12-hour caching
- User statistics and achievements
- Admin login management for troubleshooting

**📊 Media Tracking**
- Browse anime/manga with advanced filtering
- AI-powered recommendations based on user preferences
- Trending anime/manga displays
- Random anime/manga discovery
- Trailer viewing with AniList integration
- 3x3 favorite grids generation
- News monitoring from Twitter/X accounts
- Anime/manga completion channel notifications

**🎮 Gaming Integration**
- Steam profile displays with library stats
- Game recommendations based on Steam library
- Free games notifications (Epic, Steam, GOG, etc.)
- Steam game search and information

**👥 Social Features**
- AniList affinity calculator (compatibility with friends)
- Server-wide AniList leaderboards
- Feedback system for bug reports and suggestions
- Invite tracking with recruitment statistics
- Nitro booster custom role colors (moved here from the removed customization/ package)

**🏰 Server Management**
- Server configuration interface
- Invite analytics and leaderboards
- Welcome DM system
- Moderator role management

**🔧 Utilities**
- Comprehensive help system
- Reminder system with natural language parsing
- Multi-type notification subscriptions
- Timestamp generator
- User information displays
- Say command for moderators

**👑 Admin Features**
- Bot moderator system (global permissions)
- Changelog publishing system
- Bot updates channel configuration
- Audit logging with git-style history (invite/challenge subsystems only — see below)

---

## What Changed from V1

V2 is a copy-then-trim of the original codebase. Two subsystems were removed entirely because they
were either dead weight or cosmetic-only:

1. **Dashboard command-management system** (`cogs_test/`) — an interactive `/dashboard` UI that let
   admins toggle commands on/off per guild. Investigation before removal found **no runtime enforcement
   code anywhere** (`app_command_enabled_check()`, referenced in the original's docs, does not exist in
   the actual source) — the toggles never actually prevented a command from running. Every cog's
   `@command_meta(...)` decorator (a no-op metadata tag, confirmed via `setattr` with no wrapping) and
   its import were stripped; `bot.py`'s cog loader no longer scans `cogs_test/`.
2. **Customization/theme system** (`cogs/customization/themes.py`, `theme_integration.py`,
   `theme_showcase.py`, `helpers/theme_helper.py`) — a 30+ theme cosmetic embed-styling system with zero
   cross-cog dependents (confirmed by grep before deletion). `helpers/theme_helper.py` was already an
   empty file in the original — the API the original CLAUDE.md documented for it never existed.
   `cogs/customization/server_boost.py` (nitro booster role colors) was **not** part of this cut — it
   was unrelated functionality that happened to live in the same directory, and was relocated to
   `cogs/social/server_boost.py` before the rest of the directory was deleted.

**Net effect**: 40 commands across 7 sections (down from the original's ~43 across 8 — exact original
counts were themselves inconsistent with the actual code; see the per-section table below, which is
freshly verified against this repository). This includes the `library_backup.py` removal below.

No changes were made to the multi-guild data model or any of the 34 core tables inherited from V1.
Two stale table-name entries (`dashboard_guild_configs`, `dashboard_audit_log`) were removed from
`database.py`'s guild-data-cleanup registry — those tables were never actually created there (the
dashboard used its own separate SQLite file), so this was dead-entry cleanup, not a schema change.

**Resolved**: three commands existed with no mention in either version of CLAUDE.md's documented
structure and no `@command_meta` in the original (added without dashboard integration). User decision:
`cogs/social/lolilist.py` — **kept** (real feature, just undocumented). `cogs/utilities/convertlinks.py`
— **kept** (same reason). `cogs/media/library_backup.py` — **cut** (removed entirely; had zero other
files referencing it, so deletion was self-contained).

**Not yet scoped**: broader "reduce commands" and architecture/performance/code-quality simplification
work beyond the two subsystem removals above. That requires a follow-up plan once command-level cut
decisions are made explicitly (see `.claude/PRPs/plans/lemegeton-v2.plan.md` at the repo root for the
plan that produced this V2 baseline, and its "NOT Building" section for exact scope boundaries).

---

## Core Architecture

### Multi-Guild Pattern (Critical)

**Every database operation MUST be guild-aware.** Tables use `(discord_id, guild_id)` composite keys for data isolation across multiple Discord servers.

```python
# ✅ CORRECT - Always pass guild_id
user = await database.get_user_guild_aware(discord_id, interaction.guild_id)

# ❌ WRONG - Never use legacy global functions
user = await database.get_user(discord_id)  # No guild isolation!
```

All cog commands must pass `interaction.guild_id` to database functions for proper multi-server support.

### Project Structure

```
Lemegeton_v2/
├── bot.py                          # Main entry point
├── config.py                       # Environment configuration
├── database.py                     # Database wrapper with execute_db_operation()
├── cogs/                           # Command modules (40 commands)
│   ├── account/                    # Login, profile, admin login
│   ├── admin/                      # Bot moderators, changelog
│   ├── gaming/                     # Steam integration, free games
│   ├── media/                      # Browse, trending, recommendations
│   ├── server_management/          # Server info, config, invites
│   ├── social/                     # Feedback, affinity, leaderboards, server boost (nitro roles)
│   └── utilities/                  # Help, reminders, notifications
├── helpers/                        # Shared utility functions
│   ├── anilist_helper.py           # AniList API integration
│   ├── cache_helper.py             # Profile caching
│   ├── command_logger.py           # Command execution logging
│   ├── embed_helper.py             # Embed formatting
│   ├── profile_helper.py           # Profile rendering
│   └── steam_helper.py             # Steam API integration
├── data/                           # SQLite databases (not copied into V2 — recreated at runtime)
└── logs/                           # Log files (auto-rotate at 50MB, not copied into V2)
```

Note: `cogs_test/` (dashboard), `cogs/customization/` (themes), and `helpers/theme_helper.py` do not
exist in V2 — see "What Changed from V1" above. `backup/`, `scripts/`, `under_maintenance/`, `utils/`,
`tools/`, and `docs/` from the original repo were not carried into V2 at all (dead/auxiliary content);
pull individual files back in only if a kept feature turns out to depend on them.

### Technology Stack

- **Python 3.13+** with async/await
- **discord.py 2.6.0** - Discord API wrapper
- **aiosqlite** - Async SQLite operations (never use blocking `sqlite3`)
- **aiohttp** - Async HTTP requests (never use `requests`)
- **BeautifulSoup4** - HTML parsing
- **Pillow** - Image generation

---

## Command Inventory (verified against this codebase)

| Section | Commands | File count |
|---|---|---|
| Account | 2 | 2 |
| Admin | 2 | 1 |
| Gaming | 6 | 4 |
| Media | 10 | 8 |
| Server Management | 8 | 4 |
| Social | 5 | 5 (incl. `server_boost.py`) |
| Utilities | 7 | 7 |
| **Total** | **40** | **31** |

Re-derive with `grep -rc "@app_commands.command" cogs/<section>/ --include="*.py"` if this table goes
stale after further edits — do not trust a stale count the way the original CLAUDE.md's "43 commands"
figure turned out to be approximate.

---

## Logging System

### Overview

Lemegeton uses a comprehensive file-based logging system with module-specific loggers. All logs are stored in `logs/` directory and auto-rotate at 50MB.

### Logging Architecture

**Global Database Logger:**
```python
# In database.py
logger = logging.getLogger("Database")
logger.setLevel(logging.DEBUG)

# File handler with rotation
file_handler = logging.FileHandler("logs/database.log", encoding='utf-8')
formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

**Per-Module Loggers:**
```python
# In each cog file
from pathlib import Path
import logging

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "module_name.log"

logger = logging.getLogger("module_name")
logger.setLevel(logging.INFO)

# Only add handler if not already present
if not logger.handlers:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # Fallback to console if file logging fails
        stream_handler = logging.StreamHandler()
        logger.addHandler(stream_handler)
```

### Logging Levels

**DEBUG** - Detailed diagnostic information
**INFO** - General informational messages
**WARNING** - Warning messages for recoverable issues
**ERROR** - Error messages with stack traces (use `exc_info=True`)

### Log File Management

**Auto-Rotation:**
```python
LOG_MAX_SIZE = 50 * 1024 * 1024  # 50MB max log file size

if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > LOG_MAX_SIZE:
    open(log_file_path, 'w').close()
```

### Command Execution Logging

**@log_command Decorator:**
```python
from helpers.command_logger import log_command

@app_commands.command(name="mycommand", description="...")
@log_command  # Automatically logs execution time and user
async def mycommand(self, interaction: discord.Interaction):
    # Implementation
```

### Best Practices

1. Always use module-specific loggers (`logging.getLogger("module_name")`)
2. Log important state changes (`logger.info(f"User {user_id} linked AniList account: {username}")`)
3. Include stack traces for errors (`logger.error(f"Error: {e}", exc_info=True)`)
4. Use appropriate log levels (DEBUG for diagnostics, INFO for normal ops, WARNING for recoverable issues, ERROR for failures)
5. Never log sensitive data (tokens, credentials) — log identifiers only

---

## Helper Functions

### Overview

The `helpers/` directory contains shared utility functions used across multiple cogs. All helpers are async-first and follow consistent patterns.

### anilist_helper.py

**Purpose:** AniList GraphQL API integration with rate limiting (90 requests/minute)

```python
async def post_graphql(session, query, variables=None)
async def fetch_user_stats(session, username)
async def fetch_user_list(session, username, list_type="MANGA", status="CURRENT")
async def search_media(session, query, media_type="MANGA")
async def get_media_details(session, media_id)
```

### cache_helper.py

**Purpose:** File-based caching for profile data (12-hour TTL)

```python
async def get_cached_profile(user_id: int) -> Optional[dict]
async def set_cached_profile(user_id: int, data: dict)
async def clear_cache(user_id: int = None)
def is_cache_valid(timestamp: str, ttl_hours: int = 12) -> bool
```

Storage: `data/profile_cache.json`

### command_logger.py

**Purpose:** Automatic command execution logging with timing via the `@log_command` decorator.

### embed_helper.py

**Purpose:** Consistent embed formatting across the bot

```python
def create_error_embed(title: str, description: str) -> discord.Embed
def create_success_embed(title: str, description: str) -> discord.Embed
def create_info_embed(title: str, description: str) -> discord.Embed
def create_warning_embed(title: str, description: str) -> discord.Embed
def truncate_field(text: str, max_length: int = 1024) -> str
```

**Discord Embed Limits:** Title 256 chars, Description 4096 chars, Field Name 256 chars, Field Value 1024 chars, Footer 2048 chars, Total 6000 chars.

### profile_helper.py

**Purpose:** Profile rendering with bio cleanup and formatting

```python
async def render_profile(user_data: dict, theme: dict) -> discord.Embed
def clean_bio(bio: str) -> str
def format_stats(stats: dict) -> str
def calculate_achievements(stats: dict) -> List[str]
```

Note: `render_profile`'s `theme` parameter is a holdover from before the theme system removal — verify
at implementation time whether it still does anything meaningful or should be simplified away as part
of Phase 2 cleanup.

### steam_helper.py

**Purpose:** Steam API integration for gaming features

```python
async def get_steam_profile(steam_id: str) -> dict
async def get_owned_games(steam_id: str) -> List[dict]
async def search_steam_game(query: str) -> List[dict]
async def get_game_details(app_id: int) -> dict
def calculate_library_stats(games: List[dict]) -> dict
```

**API Keys:** Uses `STEAM_API_KEY` from `.env`

---

## Database Guide

### Database Architecture

**Main Database:** `data/database.db` (SQLite with aiosqlite)

**Key Principles:**
1. All operations use `execute_db_operation()` for consistency
2. Multi-guild isolation with composite keys
3. Async-first with connection pooling
4. Retry logic (3 attempts, 1s delay)
5. Comprehensive logging

### execute_db_operation() Convention

```python
async def execute_db_operation(
    operation_name: str,
    query: str,
    params: tuple = (),
    fetch_type: Optional[str] = None
) -> Any
```

**Fetch Types:** `'one'` (single row or None), `'all'` (list of rows), `'lastrowid'` (last inserted row ID), `None` (no return — INSERT/UPDATE/DELETE).

```python
# Fetch single user
user = await execute_db_operation(
    "get user",
    "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?",
    (discord_id, guild_id),
    fetch_type='one'
)
```

### Connection Management

```python
CONNECTION_RETRIES = 3
RETRY_DELAY = 1.0  # seconds
DB_TIMEOUT = 30.0  # seconds
```

### Core Tables (inherited unchanged from V1)

34 tables via `init_*_table()` functions in `database.py`, including: `users`, `user_stats`,
`achievements`, `reminders`, `guild_challenges`, `guild_challenge_roles`, `guild_challenge_manga`,
`guild_manga_channels`, `guild_bot_update_channels`, `guild_mod_roles`, `bot_moderators`,
`userinfo_usage`, `booster_roles`, `say_command_logs`, `invites`, `invite_uses`, `recruitment_stats`,
`user_leaves`, `invite_tracker_settings`, `invite_theme_settings` (join/leave message theming for the
invite tracker — unrelated to the removed cosmetic embed theme system, kept), `steam_users`,
`news_accounts`, `news_filters`, `news_metadata`, `account_whitelist`, `free_games_channels`,
`free_games_metadata`, `free_games_posted`, and others. Re-derive the exact list with
`grep -n "^async def init_.*_table" database.py` — do not trust a hardcoded list here as the source of
truth once the schema changes further.

Two ad-hoc tables (`global_challenges_backup`, `challenge_manga_backup`) are created outside the normal
`init_*_table()` pattern (~line 2081 in the original) — flagged for a future Phase 2 cleanup pass, not
addressed in V2's initial trim.

### Guild-Aware Functions

```python
# ✅ CORRECT
user = await database.get_user_guild_aware(discord_id, guild_id)

# ❌ WRONG
user = await database.get_user(discord_id)  # No guild isolation!
```

---

## Development Commands

### Running the Bot Locally

**Windows:**
```powershell
.venv\Scripts\Activate.ps1
python bot.py
```

**Linux/Mac:**
```bash
source venv/bin/activate
python bot.py
```

### Environment Variables

Required in `.env` file:
- `DISCORD_TOKEN` - Bot token from Discord Developer Portal (required)
- `PRIMARY_GUILD_ID` - Default guild for legacy data migration (required)
- `BOT_ID` - Bot user ID (optional)
- `DATABASE_PATH` - Path to SQLite database (default: `data/database.db`)
- `ENVIRONMENT` - `production` or `development` (affects cog watch interval)
- `STEAM_API_KEY` - Steam API key for gaming features (optional)

---

## Cog Development

### Cog Structure Pattern

```python
from discord.ext import commands
from discord import app_commands
import discord
import logging
from pathlib import Path
from database import execute_db_operation
from helpers.command_logger import log_command

# Logging Setup
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "mycog.log"

logger = logging.getLogger("MyCog")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

class MyCog(commands.Cog):
    """Cog description for documentation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("MyCog initialized")

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("MyCog loaded successfully")

    @app_commands.command(name="mycommand", description="Command description")
    @app_commands.describe(param1="Description of parameter 1")
    @log_command  # Auto-log command execution with timing
    async def mycommand(self, interaction: discord.Interaction, param1: str):
        guild_id = interaction.guild_id

        await interaction.response.defer(ephemeral=True)

        try:
            user = await execute_db_operation(
                "get user",
                "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?",
                (interaction.user.id, guild_id),
                fetch_type='one'
            )

            if not user:
                await interaction.followup.send(
                    "❌ You need to use `/login` first!",
                    ephemeral=True
                )
                return

            result = await process_command(user, param1)

            embed = discord.Embed(
                title="Success",
                description=f"Processed: {result}",
                color=discord.Color.green()
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.NotFound:
            logger.error("Interaction expired before completion")
        except Exception as e:
            logger.error(f"Error in mycommand: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred. Please try again.",
                    ephemeral=True
                )
            except:
                pass  # Interaction might be expired

async def setup(bot: commands.Bot):
    """Setup function required for cog loading."""
    await bot.add_cog(MyCog(bot))
    logger.info("MyCog setup complete")
```

Note: no `@command_meta` decorator — V2 has no dashboard to register with.

### Cog Organization

- **`cogs/account/`** - login.py, profile.py
- **`cogs/admin/`** - bot_moderators.py, changelog.py
- **`cogs/gaming/`** - steam_profile.py, steam_recommendation.py, steam_game.py, free_games_checker.py
- **`cogs/media/`** - browse.py, trending.py, recommendations.py, three_by_three.py, trailer.py, random.py, news.py, animanga_completion_checker.py
- **`cogs/server_management/`** - serverinfo.py, server_config.py, invite_tracker.py, welcome_dm.py
- **`cogs/social/`** - affinity.py, anilist_leaderboard.py, feedback.py, lolilist.py (undocumented — see above), server_boost.py (moved from the removed customization/ package)
- **`cogs/utilities/`** - help.py, notifications.py, timestamp.py, say.py, userinfo.py, invite.py, convertlinks.py (undocumented — see above)

---

## Command Review Guidelines

When asked to review a command file, systematically analyze and improve the code following these guidelines. This is the primary tool for V2's Phase 2 simplification work once it's scoped.

### Review Checklist

**1. Remove Redundant Code**
- Duplicate logic, constants, validation, API calls, embed creation, database patterns

**2. Extract Helper Functions**
- Place in the appropriate helper file (`text_helper.py`, `embed_helper.py`, `anilist_helper.py`, `steam_helper.py`, `utility_helper.py`, `profile_helper.py`)
- Clear naming following existing patterns; docstrings with Args/Returns

**3. Improve Code Quality**
- Function length <100 lines, reduced nesting, single responsibility, proper error handling, type hints, correct logging levels

**4. Improve Clarity**
- Descriptive variable names, comments only for non-obvious logic, dead code removal, consistent formatting

**5. Standardize Implementation**
- Always use helper functions for API calls, embed creation, and database operations — never inline

**6. Performance & Best Practices**
- Async-only I/O, deferred interactions for >3s operations, guild awareness, API rate limiting, caching where appropriate

### Review Process

1. Read the entire command file, identify issues, search for existing helpers
2. Document findings with line numbers and priority (high/medium/low)
3. Extract helpers, refactor, remove redundancy, improve clarity
4. Validate: `python -m py_compile path/to/file.py`, check imports, update findings doc

### Common Issues to Look For

**High Priority:** Hardcoded API endpoints, direct GraphQL queries instead of `post_graphql()`, inline embed creation with hardcoded colors, duplicate ID parsing, missing guild-aware operations, sync libraries (`requests`, `sqlite3`)

**Medium Priority:** Duplicate user fetching, complex inline timestamp parsing, inline error messages, functions >150 lines, excessive `logger.info()` that should be `logger.debug()`

**Low Priority:** Style inconsistencies, missing type hints, unused imports

---

## Common Patterns

### Async HTTP Requests

```python
import aiohttp

async with aiohttp.ClientSession() as session:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
        if response.status == 200:
            data = await response.json()
        else:
            logger.error(f"HTTP {response.status}: {url}")
```

### AniList API Integration

```python
from helpers.anilist_helper import fetch_user_stats
import aiohttp

async with aiohttp.ClientSession() as session:
    stats = await fetch_user_stats(session, username)
```

### Profile Caching (12-Hour TTL)

```python
from helpers.cache_helper import get_cached_profile, set_cached_profile

cached = await get_cached_profile(user_id)
if cached:
    return cached

data = await fetch_from_api(user_id)
await set_cached_profile(user_id, data)
```

### Interactive UI Components

```python
class MyView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)  # 2-minute timeout
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="Action", style=discord.ButtonStyle.primary)
    async def action_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        await interaction.response.defer()
        result = await process_action(self.guild_id, interaction.user.id)
        await interaction.followup.send(f"✅ {result}", ephemeral=True)
```

### Background Tasks

```python
from discord.ext import tasks

@tasks.loop(minutes=15)
async def my_task(self):
    try:
        result = await perform_operation()

        # Save timestamp at END (not start) for accurate status displays
        await execute_db_operation(
            "update last check",
            "UPDATE bot_meta SET last_check = ? WHERE key = 'my_task'",
            (datetime.utcnow().isoformat(),)
        )

    except Exception as e:
        logger.error(f"Task error: {e}", exc_info=True)
        # Task continues despite errors

@my_task.before_loop
async def before_my_task(self):
    await self.bot.wait_until_ready()
    logger.info("Background task starting")
```

---

## Critical Conventions

1. **Guild-Aware Functions**: Always pass `interaction.guild_id` to database functions
2. **Async-First**: Use `aiohttp`, `aiosqlite` - never blocking libraries like `requests` or `sqlite3`
3. **Database Operations**: Always use `execute_db_operation()`, never raw connections
4. **Defer Interactions**: Always `await interaction.response.defer()` for operations >3 seconds
5. **Error Handling**: Wrap responses in try/except for `discord.NotFound` (expired interactions)
6. **Command Logging**: Use `@log_command` decorator from `helpers.command_logger`
7. **Timestamps**: Save check timestamps at task END for accurate "last check" displays
8. **Embed Limits**: Discord limits - title: 256 chars, description: 4096 chars, fields: 25 max
9. **View Timeouts**: Set appropriate timeout values (default 120s for user menus)
10. **Button Ownership**: Check `interaction.user.id` in button callbacks
11. **File Logging**: Create module-specific loggers with file handlers in `logs/`

---

## Common Pitfalls to Avoid

1. Forgetting `guild_id` in database operations
2. Using sync libraries (requests, sqlite3) instead of async (aiohttp, aiosqlite)
3. Not deferring long-running interactions
4. Missing error handling for expired interactions
5. Direct DB connections instead of `execute_db_operation()`
6. Not validating user input in modals
7. Missing rate limiting for external APIs
8. Hardcoding guild IDs instead of using config
9. Not cleaning up Views/Modals with proper timeout handling
10. Not checking button/select ownership in interactive views
11. Missing file handler fallback in logging setup
12. Not handling cache expiration in profile displays
13. Forgetting to log important state changes

---

## Testing Checklist

Before committing changes:

- [ ] Run syntax check: `python -m py_compile path/to/file.py`
- [ ] Test command locally with `/command`
- [ ] Check logs for errors in `logs/`
- [ ] Check for hardcoded guild IDs
- [ ] Verify async patterns (no blocking calls)
- [ ] Test error handling with invalid inputs
- [ ] Confirm logging output in appropriate log file

No automated test suite exists yet in this codebase (no `tests/` directory or pytest config) —
consider adding one as part of Phase 2 code-quality work.

---

**Last Updated:** 2026-09-19 (V2 baseline — dashboard and theme systems removed)
**Bot Version:** V2 — Multi-Guild, no dashboard, no theme system
**Total Commands:** 40 across 7 sections (freshly verified; see Command Inventory above)
**Database Tables:** 34 tables with guild isolation, inherited unchanged from V1

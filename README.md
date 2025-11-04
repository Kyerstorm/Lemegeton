# 🎌 Lemegeton - Multi-Guild Discord Anime & Gaming Bot

A production-ready Discord bot that combines anime/manga tracking with AI-powered recommendations, Steam gaming integration, and comprehensive community features. Built with **full multi-guild support** and an **interactive dashboard management system** for server administrators.

![Python](https://img.shields.io/badge/python-3.13+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.6.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-production--ready-success.svg)
![Multi-Guild](https://img.shields.io/badge/multi--guild-ready-brightgreen.svg)
![Railway](https://img.shields.io/badge/railway-deployable-purple.svg)
![Commands](https://img.shields.io/badge/commands-43-brightgreen.svg)

---

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Commands](#-commands)
- [Dashboard System](#-dashboard-system)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [Deployment](#-deployment)
- [Development](#-development)
- [Database](#-database)
- [Contributing](#-contributing)
- [Support](#-support)

---

## ✨ Features

### 🎯 Account & Profile System

- **AniList OAuth Integration** - Secure account linking with OAuth flow
- **Rich Profile Displays** - Comprehensive profiles with 12-hour caching for performance
  - 🖼️ **Bio Gallery** - Browse all bio images in a paginated gallery view
  - 🏅 **Achievements** - View unlocked achievements and progress tracking
  - ⭐ **Favorites** - Browse favorite anime, manga, characters, and studios
  - 📝 **Auto-Cleaned Bio** - Automatic markdown and HTML cleanup for readability
  - 👥 **Social Stats** - Followers and following counts
  - 📅 **Account Age** - See how long users have been on AniList
  - ⚡ **12-Hour Cache** - Faster loading with intelligent caching system
- **Admin Login Management** - Troubleshooting tools for bot moderators
- **User Statistics** - Comprehensive tracking of anime/manga consumption

### 📊 Media Tracking & Discovery

- **Interactive Browsing** - Advanced filtering and sorting for:
  - Anime
  - Manga
  - Light Novels
  - General Novels
- **AI-Powered Recommendations** - Personalized suggestions based on highly-rated titles (8.0+)
  - Analyzes user preferences
  - Cross-media recommendations
  - Similar title discovery
- **Trending Lists** - Stay updated with currently popular series
- **Random Discovery** - Get random anime/manga suggestions
- **Trailer Viewing** - Watch trailers directly through AniList integration
- **3x3 Favorite Grids** - Generate beautiful 3x3 grids of favorite media
- **Twitter/X News Monitoring** - Track anime/manga news from Twitter accounts
- **AniList Site Embeds** - Direct links and embeds to AniList pages
- **Library Backup** - Export and backup your AniList library
- **Completion Tracking** - Automatic notifications for completed anime/manga

### 🎮 Gaming Integration

- **Steam Profile Display** - View Steam profiles with library statistics
- **Steam Game Recommendations** - Personalized game suggestions based on your Steam library
- **Steam Game Search** - Search and view detailed information about Steam games
- **Free Games Tracker** - Automatic notifications for free games from:
  - Epic Games Store
  - Steam
  - GOG
  - Other platforms
- **Cross-Platform Discovery** - Connect your anime/manga and gaming interests

### 👥 Social Features

- **AniList Affinity Calculator** - Calculate compatibility with friends based on preferences
- **Server-Wide Leaderboards** - Compete with other users across various metrics:
  - Anime count
  - Manga count
  - Mean score
  - Episodes watched
  - Chapters read
- **Feedback System** - Report bugs and suggest improvements
- **Invite Tracking** - Recruitment statistics and leaderboards
- **Social Embeds** - Rich social interaction displays

### 🎨 Customization

- **Theme System** - 30+ beautiful themes including:
  - Dark Luxury (default)
  - Cyberpunk
  - Sunset
  - Ocean
  - Forest
  - Midnight
  - Royal
  - And 23+ more!
- **Guild-Wide Themes** - Server moderators can set server-wide default themes
- **User-Specific Themes** - Individual preferences override guild settings
- **Theme Preview** - Preview themes before applying
- **Nitro Booster Custom Roles** - Automatic role color customization for Nitro boosters

### 🏰 Server Management

- **Interactive Dashboard** - Command management system (`/dashboard`)
  - Per-command enable/disable
  - Section-based organization
  - Git-style audit logging
  - Real-time status indicators
- **Server Configuration** - Centralized server settings (`/server-config`)
- **Invite Analytics** - Track invite usage and recruitment statistics
- **Welcome DM System** - Automated welcome messages for new members
- **Moderator Role Management** - Configure moderator roles per server
- **Bot Updates Channel** - Configure channels for bot update notifications
- **Completion Channels** - Set channels for anime/manga completion notifications

### 🔧 Utilities

- **Comprehensive Help System** - Interactive help with category browsing
- **Reminder System** - Natural language parsing for reminders (under maintenance)
- **Multi-Type Notifications** - Subscribe to various update types
- **Planned Features** - View upcoming features and vote on priorities
- **Timestamp Generator** - Create Discord timestamps
- **User Information Display** - View detailed Discord user information
- **Say Command** - Moderators can make the bot send messages
- **Invite Link** - Share the bot with other servers
- **Server Info** - Display comprehensive server information

### 👑 Admin Features

- **Bot Moderator System** - Global permissions management
- **Changelog Publishing** - Create and publish changelogs
- **Command Enable/Disable** - Per-server command management via dashboard
- **Audit Logging** - Git-style history of all configuration changes
- **User Cleanup** - Maintenance tools for inactive users

### 🌐 Multi-Guild Support

- **Full Multi-Server Deployment** - Deploy across unlimited Discord servers
- **Guild-Aware Data Isolation** - All database operations scoped to guild context
- **Per-Guild Configuration** - Independent settings for each server
- **Cross-Guild User Profiles** - Users maintain a single profile across all servers
- **Guild-Specific Challenges** - Independent challenge systems per server
- **Flexible Role Management** - Configure different roles for each server

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.13+** (required)
- **Discord Bot Token** (from [Discord Developer Portal](https://discord.com/developers/applications))
- **AniList Account** (optional, but recommended for full functionality)
- **Steam API Key** (optional, for gaming features)

### Installation

**Windows:**
```powershell
# Clone the repository
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton

# Create virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create .env file
copy .env.example .env
# Edit .env with your configuration (see Configuration section)

# Run the bot
python bot.py
```

**Linux/Mac:**
```bash
# Clone the repository
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your configuration (see Configuration section)

# Run the bot
python bot.py
```

---

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# Required
DISCORD_TOKEN=your_discord_bot_token_here
PRIMARY_GUILD_ID=123456789012345678

# Optional
BOT_ID=your_bot_user_id
DATABASE_PATH=data/database.db
ENVIRONMENT=development
STEAM_API_KEY=your_steam_api_key_here
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token from the Developer Portal |
| `PRIMARY_GUILD_ID` | ✅ Yes | Primary guild ID for backward compatibility |
| `BOT_ID` | ❌ No | Your bot's user ID (auto-detected if not set) |
| `DATABASE_PATH` | ❌ No | Path to SQLite database (default: `data/database.db`) |
| `ENVIRONMENT` | ❌ No | `development` or `production` (affects cog watch interval) |
| `STEAM_API_KEY` | ❌ No | Steam API key for gaming features (get from [Steam Web API](https://steamcommunity.com/dev/apikey)) |

---

## 🎯 Commands

> All commands are slash commands. Type `/` in Discord to see available commands.

### Total: **43 Commands** across **8 Sections**

### 🔐 Account Management (3 commands)

- `/login` - Register or update your AniList account connection
- `/profile [user]` - View comprehensive AniList profile with gallery, achievements, and favorites
- `/admin-login` - Admin login management for troubleshooting (Bot Moderator only)

### 📺 Media (11 commands)

- `/browse` - Interactive browsing with advanced filtering and sorting
- `/recommendations [member]` - AI-powered personalized recommendations
- `/trending` - View currently trending anime and manga
- `/random` - Get random anime/manga suggestions
- `/trailer <media>` - Watch trailers for anime/manga
- `/three-by-three [user]` - Generate 3x3 favorite grids
- `/news` - Manage Twitter/X news monitoring (Bot Moderator)
- `/test-twitter-scrape` - Test Twitter scraping functionality (Bot Moderator)
- `/set-manga-completion-channel` - Configure completion notifications (Admin)
- `/show-manga-completion-channel` - View configured completion channel (Admin)
- `/library-backup` - Export and backup your AniList library

### 🎮 Gaming (5 commands)

- `/steam-profile <username>` - Show Steam profile and library stats
- `/steam-recommendation <username>` - Get personalized game recommendations
- `/steam-game <query>` - Search and view Steam game information
- `/free-games` - Check free games and manage notifications
- `/check-free-games` - Manually trigger free games check (Bot Moderator)

### 🎨 Customization (3 commands)

- `/theme` - Browse, preview, and apply custom themes
- `/admin-guild-theme` - Manage server-wide theme settings (Bot Moderator)
- `/nitrorole-set` - Configure Nitro booster custom role colors (Admin)

### 🏰 Server Management (8 commands)

- `/serverinfo` - Display comprehensive server information
- `/server-config` - Centralized server configuration interface
- `/invite-stats` - View invite usage statistics
- `/invite-leaderboard` - View recruitment leaderboard
- `/invite-theme` - Customize invite embed theme
- `/set-welcome-dm` - Configure welcome DM messages (Admin)
- `/welcome-dm-status` - View welcome DM configuration (Admin)
- `/dashboard` - Interactive command management dashboard (Admin)

### 👥 Social (3 commands)

- `/anilist-leaderboard` - View server-wide AniList leaderboards
- `/affinity [member]` - Calculate AniList compatibility with friends
- `/feedback` - Submit ideas or report bugs

### 🛠️ Utilities (7 commands)

- `/help [category]` - Interactive help system with category browsing
- `/notifications` - Manage your notification preferences
- `/say <message>` - Make the bot send a message (Moderator)
- `/userinfo [user]` - View detailed Discord user information
- `/timestamp` - Generate Discord timestamps
- `/invite` - Get bot invite link
- `/planned-features` - View planned bot features and vote

### 👑 Admin (3 commands)

- `/bot-moderators` - Manage bot moderators (Bot Moderator)
- `/changelog` - Create and publish changelogs (Bot Moderator)
- `/set-bot-updates-channel` - Configure bot update notifications (Admin)

---

## 🎛️ Dashboard System

The **Interactive Dashboard** (`/dashboard`) is a powerful command management system that allows server administrators to control which bot commands are enabled or disabled on a per-server basis.

### Features

- **Section-Based Organization** - Commands organized into 8 logical sections
- **Per-Command Toggle** - Enable/disable individual commands
- **Real-Time Status** - Visual indicators (✅ enabled / ❌ disabled)
- **Git-Style Audit Log** - Complete history of all configuration changes
- **Batch Operations** - "Subscribe to All" / "Unsubscribe from All" buttons
- **Reset Functionality** - Restore default configuration
- **Dark Aesthetic UI** - GitHub-inspired interface

### Using the Dashboard

1. Type `/dashboard` in your Discord server
2. Use the dropdown or navigation buttons (◀️ ▶️) to browse sections
3. Click command buttons to toggle them on/off
4. View real-time status indicators
5. Use "Reset Config" to restore defaults
6. Use "View Audit" to see change history

### Dashboard Sections

- **Account** (3 commands)
- **Admin** (3 commands)
- **Customization** (3 commands)
- **Gaming** (5 commands)
- **Media** (11 commands)
- **Server Management** (8 commands)
- **Social** (3 commands)
- **Utilities** (7 commands)

**Total: 43 commands** managed through the dashboard

### For Developers

Commands are automatically registered with the dashboard using the `@command_meta` decorator:

```python
from cogs_test.general_commands.dashboard import command_meta

@app_commands.command(name="mycommand", description="...")
@command_meta(section="Utilities", name="My Command")
async def mycommand(self, interaction: discord.Interaction):
    # Command implementation
```

The dashboard automatically discovers decorated commands at bot startup.

---

## 🏗️ Project Structure

```
Lemegeton/
├── bot.py                          # Main bot entry point
├── config.py                       # Environment configuration
├── database.py                     # Database wrapper with execute_db_operation()
├── requirements.txt                # Python dependencies
├── runtime.txt                     # Python version for Railway
├── Procfile                        # Railway deployment configuration
├── .env.example                    # Environment template
│
├── cogs/                           # Command modules (43+ commands)
│   ├── account/                    # Login, profile, admin login
│   ├── admin/                      # Bot moderators, changelog, user cleanup
│   ├── customization/              # Themes, server boost, nitro roles
│   ├── gaming/                     # Steam integration, free games
│   ├── media/                      # Browse, recommendations, trending, news
│   ├── server_management/          # Server info, config, invites, welcome DMs
│   ├── social/                     # Leaderboards, affinity, feedback
│   └── utilities/                  # Help, notifications, say, userinfo, etc.
│
├── cogs_test/                      # Test cogs (dashboard system)
│   └── general_commands/
│       ├── dashboard.py            # Command management dashboard
│       ├── alfiles.py              # AniList file operations
│       ├── birthday.py             # Birthday tracking
│       ├── hltb.py                 # HowLongToBeat integration
│       └── metacritic.py           # Metacritic integration
│
├── helpers/                        # Shared utility functions
│   ├── anilist_helper.py           # AniList API integration (90 req/min rate limit)
│   ├── cache_helper.py             # Profile caching (12-hour TTL)
│   ├── command_logger.py           # Command execution logging
│   ├── embed_helper.py             # Discord embed formatting
│   ├── profile_helper.py           # Profile rendering with bio cleanup
│   ├── steam_helper.py             # Steam API integration
│   ├── theme_helper.py             # Theme application
│   └── ...                         # Additional helpers
│
├── data/                           # Data storage
│   ├── database.db                 # Main SQLite database
│   ├── dashboard_guilds.db         # Dashboard configurations
│   ├── profile_cache.json          # Profile cache (12-hour TTL)
│   └── ...                         # Additional data files
│
├── logs/                           # Log files (auto-rotate at 50MB)
│   ├── bot.log                     # Main bot log
│   ├── database.log                # Database operations
│   └── {module}.log                # Module-specific logs
│
├── tools/                          # Database maintenance scripts
│   ├── analyze_db.py               # Database structure analysis
│   ├── verify_guild_isolation.py   # Multi-guild verification
│   ├── test_multi_guild.py         # Multi-guild testing
│   └── ...                         # Additional maintenance tools
│
└── docs/                           # Documentation
    ├── README.md                   # Extended documentation
    ├── LICENSE                     # License file
    └── bugs.md                     # Known issues tracker
```

---

## 🚂 Railway Deployment

Deploy to Railway for 24/7 hosting:

### Step 1: Prepare Your Repository

1. Fork this repository
2. Ensure all files are committed

### Step 2: Create Railway Project

1. Create a [Railway](https://railway.app) account
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your forked repository

### Step 3: Configure Environment Variables

In the Railway dashboard, add these environment variables:

```
DISCORD_TOKEN=your_discord_bot_token
PRIMARY_GUILD_ID=123456789012345678
BOT_ID=your_bot_user_id
DATABASE_PATH=/data/database.db
ENVIRONMENT=production
STEAM_API_KEY=your_steam_api_key (optional)
```

### Step 4: Configure Persistent Storage

1. Go to your service settings
2. Add a volume mount at `/data` for database persistence
3. Railway will automatically create the volume

### Step 5: Deploy

Railway automatically:
- ✅ Installs dependencies from `requirements.txt`
- ✅ Uses `Procfile` to start the bot
- ✅ Creates persistent volume for database
- ✅ Provides 24/7 uptime
- ✅ Auto-restarts on crashes

### Monitoring

Check your Railway dashboard for:
- Logs and error messages
- Resource usage (CPU, memory)
- Deployment status

---

## 🔧 Development

### Running Locally

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

### Development Tools

Run all tools from project root for correct `DATABASE_PATH` resolution:

```bash
# Database analysis
python tools/analyze_db.py

# Multi-guild testing
python tools/test_multi_guild.py

# Verify guild isolation
python tools/verify_guild_isolation.py

# Database usage statistics
python tools/analyze_db_usage.py

# Database integrity check
python tools/check_db.py
```

### Adding New Commands

1. Create a new file in the appropriate `cogs/` subdirectory
2. Use `@app_commands.command()` decorator for slash commands
3. Add `@command_meta(section="SectionName", name="Display Name")` for dashboard integration
4. Always pass `interaction.guild_id` to database functions
5. Add command to `help.py` command categories
6. Update `README.md` and changelog

### Code Structure

```python
from discord.ext import commands
from discord import app_commands
import discord
from database import execute_db_operation
from helpers.command_logger import log_command
from cogs_test.general_commands.dashboard import command_meta

class MyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mycommand", description="...")
    @command_meta(section="Utilities", name="My Command")
    @log_command
    async def mycommand(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id  # Always get guild context first
        
        await interaction.response.defer(ephemeral=True)
        
        # Use guild-aware database functions
        user = await execute_db_operation(
            "get user",
            "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?",
            (interaction.user.id, guild_id),
            fetch_type='one'
        )
        
        # Command logic...

async def setup(bot: commands.Bot):
    await bot.add_cog(MyCog(bot))
```

### Critical Conventions

1. ✅ **Always use guild-aware database functions** - Pass `interaction.guild_id`
2. ✅ **Async-first** - Use `aiohttp`, `aiosqlite` (never `requests`, `sqlite3`)
3. ✅ **Defer long operations** - Always `await interaction.response.defer()` for operations >3 seconds
4. ✅ **Error handling** - Wrap responses in try/except for `discord.NotFound`
5. ✅ **Command logging** - Use `@log_command` decorator
6. ✅ **Dashboard integration** - Add `@command_meta` to all commands
7. ✅ **File logging** - Create module-specific loggers in `logs/`

---

## 💾 Database

### Architecture

- **Main Database:** `data/database.db` (SQLite with aiosqlite)
- **Dashboard Database:** `data/dashboard_guilds.db` (guild configurations)
- **Connection Pooling:** Automatic retry logic (3 attempts, 1s delay)
- **Multi-Guild Isolation:** All tables use `(discord_id, guild_id)` composite keys

### Key Tables

| Table | Purpose |
|-------|---------|
| `users` | User profiles with AniList usernames |
| `user_stats` | User statistics per guild |
| `guild_challenges` | Challenge configurations per guild |
| `guild_mod_roles` | Moderator roles per guild |
| `reminders` | User reminders with recurrence support |
| `planned_features` | Feature planning and voting |
| `themes` | Theme customization data |
| `recruitment_stats` | Invite tracking statistics |
| `invite_events` | Invite event history |
| `say_command_logs` | Moderation command logs |

### Database Operations

Always use `execute_db_operation()` wrapper:

```python
# Fetch single row
user = await execute_db_operation(
    "get user",
    "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?",
    (discord_id, guild_id),
    fetch_type='one'
)

# Fetch multiple rows
users = await execute_db_operation(
    "get all users",
    "SELECT * FROM users WHERE guild_id = ?",
    (guild_id,),
    fetch_type='all'
)

# Insert with last row ID
row_id = await execute_db_operation(
    "insert reminder",
    "INSERT INTO reminders (user_id, message, remind_at) VALUES (?, ?, ?)",
    (user_id, message, remind_at),
    fetch_type='lastrowid'
)

# Update (no return)
await execute_db_operation(
    "update user",
    "UPDATE users SET anilist_username = ? WHERE discord_id = ? AND guild_id = ?",
    (username, discord_id, guild_id)
)
```

### Database Maintenance

```bash
# Backup database
python tools/backup_database.py

# Analyze structure
python tools/analyze_db.py

# Verify integrity
python tools/check_db.py

# Cleanup old data
python tools/cleanup_database.py --reminders --days 30
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

### Development Workflow

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/AmazingFeature`)
3. **Make your changes** following the code conventions
4. **Test thoroughly** with multiple guilds
5. **Commit your changes** (`git commit -m 'Add some AmazingFeature'`)
6. **Push to the branch** (`git push origin feature/AmazingFeature`)
7. **Open a Pull Request**

### Development Guidelines

- ✅ Follow existing code structure and patterns
- ✅ Use async/await for all I/O operations
- ✅ Always use guild-aware database functions
- ✅ Add `@command_meta` decorator for dashboard integration
- ✅ Update `help.py` and `README.md` for new commands
- ✅ Add entries to `docs/structured_changelog.txt`
- ✅ Test with multiple guilds before submitting
- ✅ Use `@log_command` decorator for command logging
- ✅ Create module-specific loggers in `logs/`

### Code Style

- **Async-first** - Never use blocking libraries
- **Guild-aware** - Always pass `guild_id` to database functions
- **Error handling** - Wrap interactions in try/except
- **Logging** - Log important state changes
- **Documentation** - Add docstrings for new functions

---

## 🐛 Troubleshooting

### Bot not responding to commands

- ✅ Check Discord bot token is correct
- ✅ Verify bot has necessary permissions in Discord server
- ✅ Wait up to 1 hour for slash commands to sync on new guilds
- ✅ Check logs in `logs/bot.log`
- ✅ Verify bot is online in Discord

### Database errors

- ✅ Ensure `data/` directory exists and is writable
- ✅ Check `DATABASE_PATH` environment variable
- ✅ Run tools from project root
- ✅ Verify database file permissions
- ✅ Check `logs/database.log` for detailed errors

### AniList API errors

- ✅ AniList has rate limits (90 requests/minute) - wait and retry
- ✅ Check internet connectivity
- ✅ Verify AniList username exists (use "Check AniList" button in `/login`)
- ✅ Check `logs/anilist_helper.log` for API errors

### Multi-Guild configuration issues

- ✅ Use `/server-config` in each server to configure server-specific settings
- ✅ Use `/dashboard` to manage commands per server
- ✅ Ensure users have appropriate permissions (Admin/Moderator)
- ✅ User data is shared across guilds, but guild configurations are independent
- ✅ Run `python tools/verify_guild_isolation.py` to verify isolation

### Dashboard not working

- ✅ Ensure you have Administrator permissions
- ✅ Check `logs/dashboard.log` for errors
- ✅ Verify `data/dashboard_guilds.db` exists and is writable
- ✅ Try resetting configuration via "Reset Config" button

---

## 📊 Statistics

- **Commands**: 43 slash commands
- **Cogs**: 40+ command modules
- **Database Tables**: 20+ tables with multi-guild support
- **Themes**: 30+ customizable themes
- **Sections**: 8 dashboard sections
- **Active Development**: Regular updates and bug fixes
- **Multi-Guild**: Fully tested across multiple Discord servers
- **Rate Limits**: AniList (90 req/min), Discord API (automatic handling)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](docs/LICENSE) file for details.

---

## 🆘 Support

- **Discord Server**: [Join our Support Server](https://discord.gg/xUGD7krzws)
- **Documentation**: See `docs/README.md` for extended documentation
- **Issues**: [GitHub Issues](https://github.com/Kyerstorm/Lemegeton/issues)
- **Feature Requests**: Use the `/feedback` command in Discord
- **Bug Reports**: Use `/feedback` or create a GitHub issue

---

## 🙏 Acknowledgments

- **AniList API** - Comprehensive anime/manga data
- **Discord.py** - Excellent Discord bot framework
- **Railway** - Reliable hosting platform
- **Community** - Thank you to all contributors and users!

---

## 🎯 Roadmap

- [ ] Reminder system enhancements
- [ ] Additional gaming platform integrations
- [ ] Advanced analytics dashboard
- [ ] Mobile app integration
- [ ] Community events system
- [ ] More customization options

---

Made with ❤️ for the anime community by [Kyerstorm](https://github.com/Kyerstorm) & [Vireon](https://github.com/VireonNoctis)

**Deploy once, use everywhere!** 🚀

---

**Last Updated**: 2025-11-02  
**Bot Version**: Multi-Guild with Dashboard System  
**Python Version**: 3.13+  
**Discord.py Version**: 2.6.0

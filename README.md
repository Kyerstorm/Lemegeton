# 🎌 Lemegeton - Multi-Guild Discord Anime & Gaming Bot

A comprehensive Discord bot that combines anime/manga tracking with AI-powered recommendations, featuring interactive UIs, personalized suggestions, community challenges, and **full multi-guild deployment support**.

![Python](https://img.shields.io/badge/python-3.13+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.6.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-production--ready-success.svg)
![Multi-Guild](https://img.shields.io/badge/multi--guild-ready-brightgreen.svg)
![Railway](https://img.shields.io/badge/railway-deployable-purple.svg)

## ✨ Key Features

### 📚 Anime & Manga Tracking
- **AniList Integration** - Connect your AniList profile for seamless tracking
- **Enhanced Profile Viewing** - Comprehensive profiles with:
  - 🖼️ **Bio Gallery** - Browse all bio images in a paginated gallery
  - 🏅 **Achievements** - View unlocked achievements and progress
  - ⭐ **Favorites** - Browse favorite anime, manga, characters, and studios
  - 📝 **Auto-Cleaned Bio** - Markdown formatting cleaned for readability
  - 👥 **Social Stats** - Followers and following counts
  - 📅 **Account Age** - See how long you've been on AniList
  - ⚡ **12-Hour Cache** - Faster loading with smart caching system
- **AI-Powered Recommendations** - Get personalized suggestions based on your highly-rated titles (8.0+)
- **Interactive Browsing** - Browse anime, manga, light novels, and general novels with advanced filtering
- **Trending Lists** - Stay updated with the latest popular series
- **Twitter/X News Monitoring** - Track anime/manga news from Twitter accounts

### 🎨 Customization & Themes
- **Theme System** - Browse and apply custom themes to personalize your bot experience
- **Guild Themes** - Server moderators can set server-wide default themes
- **Theme Preview** - Preview themes before applying them
- **Individual Preferences** - User themes override guild settings

### 🏆 Community Features
- **Reading Challenges** - Participate in community-wide anime/manga challenges
- **Leaderboards** - Compete with other users across various metrics
- **Achievement System** - Unlock achievements for various milestones
- **Challenge Role Management** - Automatic role assignment based on challenge progress

### 🎮 Gaming Integration
- **Steam Profile Viewing** - Display Steam profiles and stats
- **Steam Recommendations** - Get personalized game recommendations based on your library
- **Free Games Tracker** - Automatic notifications for free games from Epic, GOG, and Steam (checks every 6 hours)
- **Cross-Platform Discovery** - Connect your anime/manga and gaming interests

### 🌐 Multi-Guild Support & Configuration
- **Multi-Server Ready** - Deploy across multiple Discord servers with per-guild configuration
- **Guild-Specific Settings** - Each server maintains independent challenge roles and configurations
- **Flexible Role Management** - Configure different challenge roles for each server
- **Cross-Guild User Profiles** - Users keep a single profile shared across guilds
- **Guild-Aware Data Isolation** - Most database operations are scoped to the guild where they were triggered

### ⚙️ Server Management
- **Centralized Configuration** - `/server-config` command for unified server management
- **Bot Moderators** - Manage users with bot-wide elevated permissions
- **Channel Configuration** - Set channels for bot updates and anime/manga completion notifications
- **Role Management** - Configure challenge roles and moderator roles per server
- **Notification System** - Users can manage their update notification preferences

### 🛠️ Utility Commands
- **Planned Features** - View upcoming bot features and updates
- **Feedback System** - Report issues and suggest improvements
- **Interactive Help** - Comprehensive help system with category browsing
- **Invite Link** - Share the bot with other servers

## 🚀 Quick Start

### Prerequisites
- Python 3.13+
- Discord Bot Token (from [Discord Developer Portal](https://discord.com/developers/applications))
- AniList Account (optional, but recommended)

### Installation

**Windows:**
```powershell
# Clone the repository
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton

# Create virtual environment
python -m venv venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create .env file with your configuration
copy .env.example .env
# Edit .env with your Discord token and other settings

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

# Create .env file with your configuration
cp .env.example .env
# Edit .env with your Discord token and other settings

# Run the bot
python bot.py
```

### Configuration

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token_here
PRIMARY_GUILD_ID=123456789012345678
BOT_ID=your_bot_user_id
DATABASE_PATH=data/database.db
ENVIRONMENT=development
```

**Environment Variables:**
- `DISCORD_TOKEN` (required) - Your Discord bot token
- `PRIMARY_GUILD_ID` (required) - Primary guild ID for backward compatibility
- `BOT_ID` (optional) - Your bot's user ID
- `DATABASE_PATH` (optional) - Path to SQLite database (default: `data/database.db`)
- `ENVIRONMENT` (optional) - `development` or `production`

## 🎯 Commands

> All commands are slash commands. Type `/` in Discord to see available commands.

### 🔐 Account Management
- `/login` - Register or update your AniList account connection

### 📊 Profile & Stats
- `/profile [user]` - View comprehensive AniList profile with:
  - Interactive buttons: 🖼️ Gallery, 🏅 Achievements, ⭐ Favorites
  - Bio with automatic formatting cleanup and image extraction
  - Social stats (followers/following) and account age
  - Unified anime/manga statistics comparison
  - 12-hour cache for improved performance

### 📺 Anime & Manga
- `/browse` - Interactive browsing with filtering and sorting
- `/trending` - View currently trending anime and manga
- `/recommendations [member]` - AI-powered personalized recommendations
- `/random` - Get random anime/manga suggestions
- `/admin-news-manage` - Manage Twitter/X news monitoring (Bot Moderator)

### 🏆 Challenges & Competition
- `/challenge_progress` - View your reading challenge progress
- `/challenge_update` - Manually update challenge progress
- `/challenge_manage` - Create and manage challenges (Moderator)
- `/challenge_leaderboard` - View challenge rankings
- `/leaderboard` - Server leaderboards for various metrics

### 🎮 Gaming
- `/steam-profile <username>` - Show Steam profile and stats
- `/steam-recommendation <username>` - Get game recommendations
- `/free-games` - Check free games and manage automatic notifications (checks every 6 hours)

### 🎨 Customization
- `/theme` - Browse, preview, and apply custom themes
- `/admin-guild-theme` - Manage server-wide theme settings (Bot Moderator)

### ⚙️ Server Management (Admin/Moderator Only)
- `/server-config` - Centralized server configuration
- `/moderators` - Manage bot moderators
- `/set_bot_updates_channel` - Configure bot update notifications
- `/set_animanga_completion_channel` - Configure completion notifications

### 🛠️ Utilities
- `/notifications` - Manage your notification preferences
- `/planned` - View planned bot features
- `/feedback` - Submit ideas or report bugs
- `/invite` - Get bot invite link
- `/help [category]` - Interactive help system

### 👑 Admin Commands (Bot Moderators Only)
- `/changelog` - Create and publish changelogs
- `/show_manga_channel` - View configured manga channel

## 🏗️ Project Structure

```
Lemegeton/
├── bot.py                          # Main bot entry point
├── config.py                       # Configuration management
├── database.py                     # Database operations (SQLite)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment template
├── cogs/                          # Command modules
│   ├── account/                   # Account management (login, profile)
│   ├── admin/                     # Admin commands (changelog, guild config)
│   ├── bot_management/            # Bot moderators
│   ├── challenges/                # Reading challenges
│   ├── customization/             # Themes
│   ├── gaming/                    # Steam integration
│   ├── media/                     # Anime/manga (browse, recommendations, news)
│   ├── server_management/         # Server configuration
│   ├── social/                    # Social features (leaderboards, affinity)
│   └── utilities/                 # Utility commands (help, feedback, planned)
├── helpers/                       # Shared utility functions
│   ├── anilist_helper.py         # AniList API integration
│   ├── cache_helper.py           # Caching system
│   ├── embed_helper.py           # Discord embed formatting
│   └── ...
├── data/                          # Data storage
│   └── database.db               # SQLite database
├── logs/                          # Log files
└── docs/                          # Documentation
    ├── DEPLOYMENT_CHECKLIST.md
    ├── RAILWAY_DEPLOYMENT.md
    └── structured_changelog.txt
```

## 🚂 Railway Deployment

Deploy to Railway for 24/7 hosting:

1. Fork this repository
2. Create a [Railway](https://railway.app) account
3. Create a new project from your forked repo
4. Set environment variables in Railway dashboard:
   - `DISCORD_TOKEN`
   - `PRIMARY_GUILD_ID`
   - `BOT_ID`
5. Deploy!

**Railway automatically:**
- Installs dependencies from `requirements.txt`
- Uses `Procfile` to start the bot
- Creates persistent volume for database
- Provides 24/7 uptime

For detailed instructions, see [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md)

## 🔧 Development

### Running Tests
```bash
# Run database analysis
python tools/analyze_db.py

# Run multi-guild tests
python tools/test_multi_guild.py
```

### Database Management
The bot uses SQLite with `aiosqlite` for async operations. All database functions are in `database.py` and use the `execute_db_operation()` wrapper for consistent logging and error handling.

**Key principles:**
- Always use guild-aware functions (`*_guild_aware()` variants)
- Never use blocking `sqlite3` - always use `aiosqlite`
- Run tools from project root for correct `DATABASE_PATH` resolution

### Adding New Commands
1. Create a new file in the appropriate `cogs/` subdirectory
2. Use `@app_commands.command()` decorator for slash commands
3. Always pass `interaction.guild_id` to database functions
4. Add command to `help.py` command categories
5. Update `README.md` and changelog

## 🐛 Troubleshooting

### Bot not responding to commands
- Check Discord bot token is correct
- Verify bot has necessary permissions in Discord server
- Wait up to 1 hour for slash commands to sync on new guilds
- Check logs in `logs/bot.log`

### Database errors
- Ensure `data/` directory exists and is writable
- Check `DATABASE_PATH` environment variable
- Run tools from project root

### AniList API errors
- AniList has rate limits - wait and retry
- Check internet connectivity
- Verify AniList username exists (use "Check AniList" button in `/login`)

### Multi-Guild configuration issues
- Use `/server-config` in each server to configure server-specific settings
- Ensure users have appropriate permissions (Admin/Moderator)
- User data is shared across guilds, but guild configurations are independent

## 📊 Database Schema

The bot uses a comprehensive SQLite database with the following key tables:
- `users` - User profiles with `(discord_id, guild_id)` composite key
- `user_stats` - User statistics per guild
- `guild_challenges` - Challenge configurations per guild
- `guild_challenge_roles` - Role assignments per guild
- `guild_mod_roles` - Moderator roles per guild
- `paginator_state` - UI state persistence
- `planned_features` - Feature planning system
- `themes` - Theme customization data

All tables follow guild-aware design patterns for multi-server isolation.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

**Development guidelines:**
- Follow existing code structure and patterns
- Use async/await for all I/O operations
- Always use guild-aware database functions
- Update help.py and README.md for new commands
- Add entries to `docs/structured_changelog.txt`
- Test with multiple guilds before submitting

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](docs/LICENSE) file for details.

## 🆘 Support

- **Discord Server**: [Join our Support Server](https://discord.gg/xUGD7krzws)
- **Documentation**: [docs/README.md](docs/README.md)
- **Issues**: [GitHub Issues](https://github.com/Kyerstorm/Lemegeton/issues)
- **Feature Requests**: Use the `/feedback` command in Discord

## 🙏 Acknowledgments

- **AniList API** - Comprehensive anime/manga data
- **Discord.py** - Excellent Discord bot framework
- **Railway** - Reliable hosting platform
- **Community** - Thank you to all contributors and users!

## 📈 Statistics

- **Commands**: 30+ slash commands
- **Cogs**: 40+ command modules
- **Database Tables**: 15+ tables with multi-guild support
- **Active Development**: Regular updates and bug fixes
- **Multi-Guild**: Fully tested across multiple Discord servers

---

Made with ❤️ for the anime community by [Kyerstorm](https://github.com/Kyerstorm)

**Deploy once, use everywhere!** 🚀

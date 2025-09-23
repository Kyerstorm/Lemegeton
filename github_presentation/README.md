# 🎌 Lemegeton - Discord Anime & Gaming Bot

A comprehensive Discord bot that combines anime/manga tracking with AI-powered recommendations, featuring interactive UIs, personalized suggestions, and community challenges.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

## ⚠️ Important Notice

**This is a presentation/demo version of the bot.** Before deploying:

1. **Replace placeholder values** in `config.py` with your actual Discord server role IDs
2. **Update the admin user ID** in `bot.py` (search for `123456789012345678`)
3. **Configure your environment variables** properly using the `.env.example` template
4. **Test thoroughly** in a development environment first

**Security reminders:**
- Never commit your `.env` file or database files
- Keep your Discord bot token secure
- Regularly update dependenciesegeton - Discord Anime & Gaming Bot

A comprehensive Discord bot that combines anime/manga tracking with AI-powered recommendations, featuring interactive UIs, personalized suggestions, and community challenges.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

## ✨ Key Features

### 📚 Anime & Manga Tracking
- **AniList Integration** - Connect your AniList profile for seamless tracking
- **AI-Powered Recommendations** - Get personalized suggestions based on your highly-rated titles (8.0+)
- **Interactive Browsing** - Browse anime, manga, light novels, and general novels with advanced filtering
- **Profile Viewing** - Comprehensive user statistics and favorite series
- **Watchlist Management** - Track your current and planned anime/manga
- **Trending Lists** - Stay updated with the latest popular series

### 🏆 Community Features
- **Global Challenges** - Participate in community-wide anime/manga challenges
- **Leaderboards** - Compete with other users across various metrics
- **User Comparison** - Compare profiles and statistics with friends
- **Achievement System** - Unlock achievements for various milestones
- **Multi-Guild Support** - Works across unlimited Discord servers with complete data isolation

### 🤖 Utility Commands
- **Timestamp Converter** - Convert timestamps between formats
- **Random Recommendations** - Get surprise anime/manga suggestions
- **Statistics Tracking** - Detailed user engagement analytics
- **AniList Username Verification** - Check username validity before registration
- **Feedback System** - Report issues and suggest improvements

## 🚀 Quick Start (Railway - Recommended)

The easiest way to deploy Lemegeton is using Railway's free hosting:

1. **Fork this repository** to your GitHub account
2. **Create a Railway account** at [railway.app](https://railway.app)
3. **Deploy from GitHub** - Select your forked repository
4. **Set environment variables** (see [Railway Deployment Guide](docs/RAILWAY_DEPLOYMENT.md))
5. **Deploy!** Your bot will be online 24/7

📖 **Full Railway Guide**: [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md)

## 🛠️ Manual Installation

### Prerequisites
- **Python 3.8+** - [Download Python](https://python.org/downloads/)
- **Discord Bot Token** - [Discord Developer Portal](https://discord.com/developers/applications)
- **Git** - [Download Git](https://git-scm.com/downloads)

### Step 1: Clone Repository

```bash
git clone https://github.com/Kyerstorm/lemegeton-test.git
cd lemegeton-test
```

### Step 2: Install Dependencies

#### Option A: Quick Setup (Windows)
```cmd
# Run the automated setup script
setup_user.bat
```

#### Option B: Manual Setup
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token_here
GUILD_ID=your_discord_server_id
BOT_ID=your_bot_user_id
CHANNEL_ID=your_main_channel_id
DATABASE_PATH=data/database.db
ENVIRONMENT=development
```

### Step 4: Run the Bot

#### Local Development
1. Run `start.bat` to start the bot with monitoring
2. Visit `http://localhost:5000` for monitoring dashboard
3. Bot supports unlimited Discord servers simultaneously

#### Production Deployment
1. See `docs/RAILWAY_DEPLOYMENT.md` for web-based deployment
2. See `docs/RAILWAY_CLI_DEPLOYMENT.md` for CLI deployment
3. All configuration files are in the `config/` folder

## 🎯 Commands

### Account Management
- `/login` - Register your AniList username
- `/check_anilist` - Verify if an AniList username exists
- `/profile` - View your AniList profile and statistics

### Recommendations & Discovery
- `/recommendations` - Get AI-powered recommendations based on your 8.0+ rated titles
- `/trending` - View current trending anime and manga
- `/random` - Get random anime/manga suggestions
- `/search_similar` - Find anime similar to a specific title

### Interactive Features
- `/browse` - Interactive category browsing (Anime/Manga/Light Novels/Novels)
- `/compare` - Compare your profile with another user
- `/watchlist` - Manage your anime/manga watchlist

### Challenges & Competition
- `/challenge_progress` - View your current challenge progress
- `/challenge_leaderboard` - See challenge rankings
- `/leaderboard` - View various community leaderboards

### Utilities
- `/timestamp` - Convert and format timestamps
- `/stats` - View bot usage statistics
- `/feedback` - Send feedback to the developers
- `/help` - Interactive help system with command categories

## 📁 Project Structure

```
lemegeton-test/
├── 📂 bot.py                 # Main bot entry point
├── 📂 config.py              # Configuration management
├── 📂 database.py            # Database operations
├── 📂 requirements.txt       # Python dependencies
├── 📂 start.bat              # Windows startup script
├── 📂 cogs/                  # Bot command modules
│   ├── anilist.py           # AniList integration
│   ├── recommendations.py   # AI recommendation system
│   ├── browse.py            # Interactive browsing
│   ├── challenge_*.py       # Challenge system
│   ├── help.py              # Interactive help system
│   └── ...                  # Other command modules
├── 📂 helpers/               # Utility functions
│   ├── media_helper.py      # AniList API helpers
│   └── challenge_helper.py  # Challenge management
├── 📂 data/                  # Database and cache files
├── 📂 docs/                  # Documentation
├── 📂 logs/                  # Application logs
└── 📂 scripts/               # Maintenance scripts
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `DISCORD_TOKEN` | Discord bot token | ✅ | `MTk4NjIyNDgzNDcxOTI1MjQ4...` |
| `GUILD_ID` | Discord server ID | ✅ | `123456789012345678` |
| `BOT_ID` | Discord bot user ID | ✅ | `987654321098765432` |
| `CHANNEL_ID` | Main channel ID | ✅ | `555666777888999000` |
| `DATABASE_PATH` | Database file path | ❌ | `/app/database.db` |
| `ENVIRONMENT` | Runtime environment | ❌ | `production` |

### Bot Configuration (`config.py`)

```python
# Discord settings
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Database
DB_PATH = os.getenv("DATABASE_PATH", "database.db")
```

## 🐛 Troubleshooting

### Common Issues

#### "Command failed with exit code 1"
- **Check Python version**: Ensure Python 3.8+
- **Dependencies**: Run `pip install -r requirements.txt`
- **Permissions**: Ensure proper file permissions

#### "Bot not responding to commands"
- **Permissions**: Check bot has necessary permissions in Discord
- **Token**: Verify Discord bot token is correct
- **Guild ID**: Ensure GUILD_ID matches your Discord server

#### "Database errors"
- **File permissions**: Ensure bot can write to database directory
- **Path**: Check DATABASE_PATH is correct
- **SQLite**: Ensure SQLite3 is available

#### "AniList API errors"
- **Rate limits**: AniList API has rate limits
- **Network issues**: Check internet connectivity
- **Invalid usernames**: Ensure usernames exist on AniList

### Debug Mode

Enable detailed logging by modifying `config.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Files

The bot creates detailed logs in the `logs/` directory:
- `bot.log` - Main bot operations
- `database.log` - Database operations
- `media_helper.log` - AniList API calls
- Command-specific logs for debugging

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YourUsername/lemegeton-test.git
cd lemegeton-test

# Create development environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run in development mode
python bot.py
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](docs/LICENSE) file for details.

## 🆘 Support

- **Discord Server**: [https://discord.gg/xUGD7krzws](https://discord.gg/xUGD7krzws)
- **Documentation**: [docs/README.md](docs/README.md)
- **Issues**: [GitHub Issues](https://github.com/Kyerstorm/lemegeton-test/issues)
- **Feature Requests**: Use the `/feedback` command in Discord

## 🙏 Acknowledgments

- **AniList API** - For providing comprehensive anime/manga data
- **Discord.py** - Excellent Discord bot framework
- **Railway** - Reliable hosting platform
- **Contributors** - Thank you to all who have contributed to this project

---

**Made with ❤️ for the anime community**
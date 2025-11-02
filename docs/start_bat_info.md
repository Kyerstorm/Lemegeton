# Start.bat Interactive Manager Guide

This guide explains how to use the new interactive `start.bat` script for managing your Lemegeton Discord bot.

## Quick Start

Simply double-click `start.bat` or run it from the command line:
```bash
start.bat
```

You'll see an interactive menu with numbered options.

## Multi-Window Workflow

**NEW:** When you start or restart the bot, the script automatically opens a **new menu window**!

### How It Works:

1. **Start Bot (Option 1 or 2)**
   - Original window: Bot runs here (you can see all output)
   - NEW window: Menu opens automatically for you to use other options

2. **Restart Bot (Option 3 from new window)**
   - Current menu window: Bot starts here and takes over
   - NEW window: Menu opens again for further commands
   - Old bot window: Automatically closes when Python process is killed

3. **Continuous Cycle**
   - You always have one bot window (running) and one menu window (for commands)
   - Can restart, check logs, or manage database without stopping the bot
   - Just use option [3] from the menu window whenever you need to restart

### Example Workflow:
```
Window 1: Open start.bat → Choose [1] Start Bot
         ↓
Window 1: Bot running (shows logs)
Window 2: Menu opens automatically → Choose [4] View Live Logs or [3] Restart

If you chose [3] Restart:
Window 2: Becomes new bot window (old Window 1 closes)
Window 3: Menu opens automatically for next command
```

This means you can easily restart the bot or check logs without closing and reopening start.bat manually!

### Visual Diagram:
```
┌─────────────────────────────────────────────────────────┐
│ Step 1: Start Bot                                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Window 1: Menu]                                        │
│  Choose option [1] Start Bot                            │
│        │                                                 │
│        ├──> [Window 1: Bot Running]                     │
│        │    (Shows bot logs)                            │
│        │                                                 │
│        └──> [Window 2: Menu Opens]                      │
│             (Ready for commands)                        │
│                                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Step 2: Restart Bot                                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Window 2: Menu]                                        │
│  Choose option [3] Restart Bot                          │
│        │                                                 │
│        ├──> Kills Window 1 (Old Bot)                    │
│        │                                                 │
│        ├──> [Window 2: Bot Running]                     │
│        │    (Becomes new bot window)                    │
│        │                                                 │
│        └──> [Window 3: Menu Opens]                      │
│             (Ready for next command)                    │
│                                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Result: Continuous Cycle                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Always have:                                            │
│  • ONE window with bot running                          │
│  • ONE window with menu for commands                    │
│  • Can restart/check logs anytime                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Main Menu Options

### Bot Management

**[1] Start Bot (Normal Mode)**
- Starts the bot with standard logging
- Activates virtual environment automatically
- Checks for `.env` file before starting
- **Automatically opens a NEW menu window** so you can manage the bot while it runs
- Bot continues running in the original window
- Press Ctrl+C to stop the bot
- Returns to menu when stopped

**[2] Start Bot (Debug Mode)**
- Starts bot with unbuffered Python output (`-u` flag)
- Shows all logs immediately in console
- **Automatically opens a NEW menu window** for bot management
- Bot continues running in the original window with debug output
- Great for debugging issues in real-time
- Recommended for development and testing

**[3] Restart Bot**
- Finds and kills any running Python processes automatically
- **Does NOT ask for confirmation** - immediately terminates Python processes
- Starts the bot in the current window
- **Opens a NEW menu window** for further management
- Old bot window is closed, new bot window takes its place
- Useful for quick restarts during development

---

### Log Management

**[4] View Live Logs**
- Monitor log files in real-time (like `tail -f` on Linux)
- Choose from:
  - Main Bot Log - Overall bot activity
  - Database Log - Database operations
  - News Log - Twitter/X monitoring
  - Reminders Log - Reminder system activity
  - Invite Log - Bot invite events
- Press Ctrl+C to stop monitoring
- Updates automatically as new entries are written

**[5] View Recent Logs**
- View last 50 lines of any log file
- Quick way to check recent activity
- Option 5 shows summary of all log files (size, last modified)

**[6] Clear All Logs**
- Deletes all `.log` files in the `logs/` folder
- Asks for confirmation before deleting
- Useful for starting fresh or when logs get too large
- **Warning:** This action cannot be undone!

---

### System Monitoring

**[7] Check Bot Status**
- Shows if bot is currently running
- Lists running Python processes
- Checks for:
  - `.env` file
  - Virtual environment
  - Database file (with size)
- Shows last log entry from bot.log
- Great for quick health check

---

### Database Tools

**[8] Database Tools**

Opens a submenu with database management options:

1. **Check Database Integrity** - Runs `tools\check_db.py`
   - Verifies database is not corrupted
   - Checks for structural issues

2. **Analyze Database Structure** - Runs `tools\analyze_db.py`
   - Shows all tables and their schemas
   - Displays indexes and relationships

3. **View Database Stats** - Runs `tools\analyze_db_usage.py`
   - Shows row counts per table
   - Displays database usage statistics

4. **Run Database Cleanup** - Runs `tools\cleanup_database.py`
   - Removes orphaned records
   - Optimizes database size

5. **Verify Guild Isolation** - Runs `tools\verify_guild_isolation.py`
   - Ensures multi-guild data separation
   - Checks for data leaks between guilds

---

### Development Tools

**[9] Git Status**
- Shows current git branch
- Displays uncommitted changes
- Shows last 5 commits
- Requires Git to be installed

**[A] Run Tests**

Opens a submenu with test options:

1. **Test Multi-Guild Features** - Runs `tools\test_multi_guild.py`
2. **Test Steam API** - Runs `tools\test_steam_api.py`
3. **Test Free Games** - Runs `tools\test_free_games.py`

Great for verifying features work before deploying.

**[B] Update Dependencies**
- Updates pip to latest version
- Installs/updates all packages from `requirements.txt`
- Runs with `--upgrade` flag
- Useful after pulling updates from git

**[C] Environment Info**
- Shows Python version
- Shows pip version
- Lists all installed packages
- Shows discord.py version specifically
- Displays system information
- Shows current working directory

**[D] Backup Database**
- Creates timestamped backup in `backups/` folder
- Format: `database_backup_YYYYMMDD_HHMMSS.db`
- Shows backup size
- Lists all existing backups
- Recommended before major updates or migrations

---

## Usage Tips

### For Daily Development

1. Use option **[2] Start Bot (Debug Mode)** to see logs immediately
2. Use option **[4] View Live Logs** in a separate terminal to monitor specific log files
3. Use option **[3] Restart Bot** for quick restarts after code changes

### For Testing New Features

1. Use option **[D] Backup Database** before testing
2. Use option **[7] Check Bot Status** to verify environment
3. Use option **[A] Run Tests** to test specific features
4. Use option **[4] View Live Logs** to monitor activity

### For Production

1. Use option **[1] Start Bot (Normal Mode)** for stable operation
2. Use option **[5] View Recent Logs** to check activity periodically
3. Use option **[D] Backup Database** regularly
4. Use option **[8] Database Tools → [1]** to check integrity weekly

### For Troubleshooting

1. Use option **[7] Check Bot Status** to verify environment setup
2. Use option **[5] View Recent Logs** to see what happened
3. Use option **[8] Database Tools → [1]** to check for corruption
4. Use option **[C] Environment Info** to verify dependencies

---

## Keyboard Shortcuts in Menu

- Type the number or letter and press Enter
- Type `0` to exit at any time
- Press Ctrl+C during bot operation to stop the bot
- Press Ctrl+C during log viewing to return to menu

---

## Common Workflows

### Starting Bot for First Time
```
1. Run start.bat
2. Choose [7] Check Bot Status - verify environment
3. Choose [1] Start Bot (Normal Mode)
```

### Making Code Changes
```
1. Make your changes in your editor
2. Go to the menu window (already open after starting bot)
3. Choose [3] Restart Bot - old bot window closes, new one starts
4. In the NEW menu window, choose [4] View Live Logs if needed
5. Repeat as needed - menu window always reopens automatically
```

### Before Deploying Updates
```
1. Choose [D] Backup Database
2. Choose [B] Update Dependencies
3. Choose [A] Run Tests
4. Choose [1] Start Bot (Normal Mode)
5. Choose [7] Check Bot Status - verify running
```

### Weekly Maintenance
```
1. Choose [D] Backup Database
2. Choose [8] Database Tools → [1] Check Integrity
3. Choose [8] Database Tools → [3] View Stats
4. Choose [6] Clear All Logs (if too large)
```

---

## Troubleshooting the Script

**"Virtual environment not found"**
- Make sure `.venv` folder exists in the bot directory
- Run: `python -m venv .venv` to create it
- Install dependencies: `.venv\Scripts\pip install -r requirements.txt`

**"Git is not installed or not in PATH"**
- Git option [9] requires Git to be installed
- Download from: https://git-scm.com/download/win
- Or skip this option if you don't use Git

**Log files not found**
- Log files are created when the bot runs
- Start the bot first, then view logs

**Database tools fail**
- Make sure the tool scripts exist in `tools/` folder
- Verify virtual environment is activated
- Check that the database exists at `data/database.db`

---

## Technical Details

### Virtual Environment
The script automatically activates `.venv\Scripts\activate.bat` before running Python commands.

### Log Monitoring
Uses PowerShell's `Get-Content -Wait -Tail` for real-time log monitoring (similar to `tail -f` on Linux).

### Process Management
Uses `tasklist` and `taskkill` to find and stop Python processes. Be careful with option [3] if you have other Python scripts running.

### Backup Naming
Backups use `wmic os get localdatetime` for timestamp to ensure consistent sorting and unique names.

---

## File Locations

- **Logs**: `logs/*.log`
- **Database**: `data/database.db`
- **Backups**: `backups/database_backup_*.db`
- **Tools**: `tools/*.py`
- **Config**: `.env`
- **Virtual Environment**: `.venv/`

---

## Security Notes

- The script does NOT display your `.env` file contents
- Backups are stored locally in the `backups/` folder
- Log files may contain sensitive information (tokens, IDs)
- Do not share log files or backups publicly

---

## Need Help?

If you encounter issues:
1. Check option **[7] Check Bot Status** for environment problems
2. Check option **[5] View Recent Logs** for error messages
3. Check option **[C] Environment Info** for dependency issues
4. Review the error message shown in the console

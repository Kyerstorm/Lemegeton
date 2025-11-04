@echo off
setlocal EnableDelayedExpansion
title Lemegeton Discord Bot Manager

:MENU
cls
echo ============================================================
echo           LEMEGETON DISCORD BOT MANAGER
echo ============================================================
echo.
echo [1] Start Bot (Normal Mode)
echo [2] Start Bot (Debug Mode)
echo [3] Restart Bot
echo [4] View Live Logs
echo [5] View Recent Logs
echo [6] Clear All Logs
echo [7] Check Bot Status
echo [8] Database Tools
echo [9] Git Status
echo [A] Run Tests
echo [B] Update Dependencies
echo [C] Environment Info
echo [D] Backup Database
echo [0] Exit
echo.
echo ============================================================
set /p choice="Enter your choice: "

if "%choice%"=="1" goto START_NORMAL
if "%choice%"=="2" goto START_DEBUG
if "%choice%"=="3" goto RESTART_BOT
if "%choice%"=="4" goto VIEW_LIVE_LOGS
if "%choice%"=="5" goto VIEW_RECENT_LOGS
if "%choice%"=="6" goto CLEAR_LOGS
if "%choice%"=="7" goto CHECK_STATUS
if "%choice%"=="8" goto DATABASE_TOOLS
if "%choice%"=="9" goto GIT_STATUS
if /i "%choice%"=="A" goto RUN_TESTS
if /i "%choice%"=="B" goto UPDATE_DEPS
if /i "%choice%"=="C" goto ENV_INFO
if /i "%choice%"=="D" goto BACKUP_DB
if "%choice%"=="0" goto EXIT

echo Invalid choice. Please try again.
timeout /t 2 >nul
goto MENU

:START_NORMAL
cls
echo ============================================================
echo                   STARTING BOT (NORMAL)
echo ============================================================
echo.
echo [*] Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [+] Virtual environment activated
) else (
    echo [!] Virtual environment not found at .venv\Scripts\
    echo [!] Please ensure the virtual environment exists
    pause
    goto MENU
)

echo.
echo [*] Checking for .env file...
if not exist ".env" (
    echo [!] WARNING: .env file not found!
    echo [!] Please create a .env file with your configuration
    pause
    goto MENU
)
echo [+] .env file found

echo.
echo [*] Starting bot...
echo [*] Press Ctrl+C to stop the bot
echo [*] Opening new menu window for bot management...
echo.
echo ============================================================
echo.

:: Open a new start.bat window for menu access
start "Lemegeton Bot Manager" "%~f0"

:: Run bot in current window
python bot.py

echo.
echo.
echo [*] Bot stopped.
echo.
pause
goto MENU

:START_DEBUG
cls
echo ============================================================
echo                   STARTING BOT (DEBUG)
echo ============================================================
echo.
echo [*] Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [+] Virtual environment activated
) else (
    echo [!] Virtual environment not found
    pause
    goto MENU
)

echo.
echo [*] Starting bot with detailed logging...
echo [*] Press Ctrl+C to stop the bot
echo [*] Opening new menu window for bot management...
echo.
echo ============================================================
echo.

:: Open a new start.bat window for menu access
start "Lemegeton Bot Manager" "%~f0"

:: Set Python to unbuffered mode for immediate log output
set PYTHONUNBUFFERED=1
python -u bot.py

echo.
echo.
echo [*] Bot stopped.
echo.
pause
goto MENU

:RESTART_BOT
cls
echo ============================================================
echo                    RESTARTING BOT
echo ============================================================
echo.
echo [*] Looking for running bot process...

:: Kill any running Python processes that might be the bot
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [*] Found running Python process(es)
    echo [*] Terminating Python processes...
    taskkill /F /IM python.exe >nul 2>&1
    echo [+] Python processes terminated
    timeout /t 2 >nul
) else (
    echo [*] No running Python processes found
)

echo.
echo [*] Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [+] Virtual environment activated
) else (
    echo [!] Virtual environment not found at .venv\Scripts\
    echo [!] Please ensure the virtual environment exists
    pause
    goto MENU
)

echo.
echo [*] Restarting bot...
echo [*] Press Ctrl+C to stop the bot
echo.
echo ============================================================
echo.

:: Run bot in current window
python bot.py

echo.
echo.
echo [*] Bot stopped after restart.
echo.
pause
goto MENU

:VIEW_LIVE_LOGS
cls
echo ============================================================
echo                    LIVE LOG VIEWER
echo ============================================================
echo.
echo Select log file to monitor:
echo.
echo [1] Main Bot Log
echo [2] Database Log
echo [3] News Log
echo [4] Reminders Log
echo [5] Invite Log
echo [0] Back to Menu
echo.
set /p logchoice="Enter your choice: "

if "%logchoice%"=="1" set LOGFILE=logs\bot.log
if "%logchoice%"=="2" set LOGFILE=logs\database.log
if "%logchoice%"=="3" set LOGFILE=logs\news.log
if "%logchoice%"=="4" set LOGFILE=logs\reminders.log
if "%logchoice%"=="5" set LOGFILE=logs\invite.log
if "%logchoice%"=="0" goto MENU

if not defined LOGFILE (
    echo Invalid choice.
    timeout /t 2 >nul
    goto VIEW_LIVE_LOGS
)

if not exist "%LOGFILE%" (
    echo [!] Log file not found: %LOGFILE%
    echo [!] The log will be created when the bot runs
    pause
    goto MENU
)

echo.
echo [*] Monitoring: %LOGFILE%
echo [*] Press Ctrl+C to stop monitoring
echo.
echo ============================================================
echo.

:: Use PowerShell to tail the file (similar to tail -f on Linux)
powershell -Command "Get-Content '%LOGFILE%' -Wait -Tail 50"

goto MENU

:VIEW_RECENT_LOGS
cls
echo ============================================================
echo                  RECENT LOGS VIEWER
echo ============================================================
echo.
echo Select log file to view:
echo.
echo [1] Main Bot Log (last 50 lines)
echo [2] Database Log (last 50 lines)
echo [3] News Log (last 50 lines)
echo [4] Reminders Log (last 50 lines)
echo [5] All Logs Summary
echo [0] Back to Menu
echo.
set /p logchoice="Enter your choice: "

if "%logchoice%"=="1" set LOGFILE=logs\bot.log
if "%logchoice%"=="2" set LOGFILE=logs\database.log
if "%logchoice%"=="3" set LOGFILE=logs\news.log
if "%logchoice%"=="4" set LOGFILE=logs\reminders.log
if "%logchoice%"=="5" goto SHOW_ALL_LOGS
if "%logchoice%"=="0" goto MENU

if not defined LOGFILE (
    echo Invalid choice.
    timeout /t 2 >nul
    goto VIEW_RECENT_LOGS
)

if not exist "%LOGFILE%" (
    echo [!] Log file not found: %LOGFILE%
    pause
    goto MENU
)

cls
echo ============================================================
echo Last 50 lines of: %LOGFILE%
echo ============================================================
echo.
powershell -Command "Get-Content '%LOGFILE%' -Tail 50"
echo.
echo ============================================================
pause
goto MENU

:SHOW_ALL_LOGS
cls
echo ============================================================
echo                   ALL LOGS SUMMARY
echo ============================================================
echo.

for %%F in (logs\*.log) do (
    echo ----------------------------------------
    echo File: %%F
    echo Last modified:
    forfiles /P logs /M %%~nxF /C "cmd /c echo @fdate @ftime" 2>nul
    echo Size:
    for %%A in ("%%F") do echo %%~zA bytes
    echo ----------------------------------------
    echo.
)

pause
goto MENU

:CLEAR_LOGS
cls
echo ============================================================
echo                    CLEAR LOGS
echo ============================================================
echo.
echo [!] WARNING: This will delete all log files!
echo [!] This action cannot be undone.
echo.
echo Are you sure you want to continue? (Y/N)
set /p confirm="> "

if /i not "%confirm%"=="Y" (
    echo [*] Operation cancelled.
    timeout /t 2 >nul
    goto MENU
)

echo.
echo [*] Clearing logs...

if exist "logs\*.log" (
    del /Q logs\*.log 2>nul
    echo [+] All log files deleted
) else (
    echo [*] No log files found
)

echo.
pause
goto MENU

:CHECK_STATUS
cls
echo ============================================================
echo                    BOT STATUS CHECK
echo ============================================================
echo.

echo [*] Checking for running Python processes...
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [+] Python process is running
    echo.
    echo Details:
    tasklist /FI "IMAGENAME eq python.exe" /FO TABLE
) else (
    echo [-] No Python process found - Bot is likely not running
)

echo.
echo ============================================================
echo.
echo [*] Checking environment...
echo.

if exist ".env" (
    echo [+] .env file: Found
) else (
    echo [!] .env file: NOT FOUND
)

if exist ".venv\Scripts\python.exe" (
    echo [+] Virtual environment: Found
) else (
    echo [!] Virtual environment: NOT FOUND
)

if exist "data\database.db" (
    echo [+] Database: Found
    for %%A in ("data\database.db") do echo     Size: %%~zA bytes
) else (
    echo [!] Database: NOT FOUND
)

echo.
echo [*] Recent bot activity (last log entry):
if exist "logs\bot.log" (
    powershell -Command "Get-Content 'logs\bot.log' -Tail 1"
) else (
    echo     No log file found
)

echo.
echo ============================================================
pause
goto MENU

:DATABASE_TOOLS
cls
echo ============================================================
echo                   DATABASE TOOLS
echo ============================================================
echo.
echo [1] Check Database Integrity
echo [2] Analyze Database Structure
echo [3] View Database Stats
echo [4] Run Database Cleanup
echo [5] Verify Guild Isolation
echo [0] Back to Menu
echo.
set /p dbchoice="Enter your choice: "

if "%dbchoice%"=="1" goto DB_CHECK
if "%dbchoice%"=="2" goto DB_ANALYZE
if "%dbchoice%"=="3" goto DB_STATS
if "%dbchoice%"=="4" goto DB_CLEANUP
if "%dbchoice%"=="5" goto DB_VERIFY
if "%dbchoice%"=="0" goto MENU

echo Invalid choice.
timeout /t 2 >nul
goto DATABASE_TOOLS

:DB_CHECK
cls
echo ============================================================
echo              DATABASE INTEGRITY CHECK
echo ============================================================
echo.
call .venv\Scripts\activate.bat
python tools\check_db.py
echo.
pause
goto DATABASE_TOOLS

:DB_ANALYZE
cls
echo ============================================================
echo              DATABASE STRUCTURE ANALYSIS
echo ============================================================
echo.
call .venv\Scripts\activate.bat
python tools\analyze_db.py
echo.
pause
goto DATABASE_TOOLS

:DB_STATS
cls
echo ============================================================
echo                  DATABASE STATISTICS
echo ============================================================
echo.
call .venv\Scripts\activate.bat
python tools\analyze_db_usage.py
echo.
pause
goto DATABASE_TOOLS

:DB_CLEANUP
cls
echo ============================================================
echo                  DATABASE CLEANUP
echo ============================================================
echo.
call .venv\Scripts\activate.bat
python tools\cleanup_database.py
echo.
pause
goto DATABASE_TOOLS

:DB_VERIFY
cls
echo ============================================================
echo              VERIFY GUILD ISOLATION
echo ============================================================
echo.
call .venv\Scripts\activate.bat
python tools\verify_guild_isolation.py
echo.
pause
goto DATABASE_TOOLS

:GIT_STATUS
cls
echo ============================================================
echo                     GIT STATUS
echo ============================================================
echo.

where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Git is not installed or not in PATH
    pause
    goto MENU
)

echo [*] Current branch and status:
echo.
git status

echo.
echo ============================================================
echo.
echo [*] Recent commits:
echo.
git log --oneline -5

echo.
echo ============================================================
pause
goto MENU

:RUN_TESTS
cls
echo ============================================================
echo                     RUN TESTS
echo ============================================================
echo.
echo [1] Test Multi-Guild Features
echo [2] Test Steam API
echo [3] Test Free Games
echo [4] Test Twitter Scraping
echo [0] Back to Menu
echo.
set /p testchoice="Enter your choice: "

call .venv\Scripts\activate.bat

if "%testchoice%"=="1" (
    python tools\test_multi_guild.py
)
if "%testchoice%"=="2" (
    python tools\test_steam_api.py
)
if "%testchoice%"=="3" (
    python tools\test_free_games.py
)
if "%testchoice%"=="0" goto MENU

echo.
pause
goto RUN_TESTS

:UPDATE_DEPS
cls
echo ============================================================
echo                UPDATE DEPENDENCIES
echo ============================================================
echo.
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo [*] Updating pip...
python -m pip install --upgrade pip

echo.
echo [*] Installing/updating requirements...
pip install -r requirements.txt --upgrade

echo.
echo [+] Dependencies updated!
echo.
pause
goto MENU

:ENV_INFO
cls
echo ============================================================
echo               ENVIRONMENT INFORMATION
echo ============================================================
echo.

call .venv\Scripts\activate.bat

echo [*] Python Version:
python --version

echo.
echo [*] Pip Version:
pip --version

echo.
echo [*] Installed Packages:
pip list

echo.
echo [*] Discord.py Version:
python -c "import discord; print(f'discord.py {discord.__version__}')" 2>nul || echo Not installed

echo.
echo [*] System Information:
systeminfo | findstr /B /C:"OS Name" /C:"OS Version" /C:"System Type"

echo.
echo [*] Working Directory:
cd

echo.
echo ============================================================
pause
goto MENU

:BACKUP_DB
cls
echo ============================================================
echo                   BACKUP DATABASE
echo ============================================================
echo.

if not exist "data\database.db" (
    echo [!] Database not found at data\database.db
    pause
    goto MENU
)

:: Create backups directory if it doesn't exist
if not exist "backups" mkdir backups

:: Generate timestamp for backup filename
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set timestamp=%datetime:~0,8%_%datetime:~8,6%

set BACKUP_FILE=backups\database_backup_%timestamp%.db

echo [*] Creating backup...
copy "data\database.db" "%BACKUP_FILE%" >nul

if %ERRORLEVEL% EQU 0 (
    echo [+] Backup created successfully!
    echo [+] Location: %BACKUP_FILE%

    for %%A in ("%BACKUP_FILE%") do (
        echo [*] Size: %%~zA bytes
    )
) else (
    echo [!] Backup failed!
)

echo.
echo [*] Existing backups:
dir /B backups\database_backup_*.db 2>nul || echo     No backups found

echo.
pause
goto MENU

:EXIT
cls
echo ============================================================
echo             Thanks for using Lemegeton Bot!
echo ============================================================
echo.
echo Goodbye!
timeout /t 2 >nul
exit /b 0

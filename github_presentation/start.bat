@echo off

REM ==========================================
REM   Enhanced Discord Bot Startup Script
REM   Lemegeton Public Bot with Monitoring
REM ==========================================

echo ========================================
echo   Starting Lemegeton Public Bot
echo   with Monitoring Dashboard
echo ========================================
echo.

REM Enable error checking and debugging
set DEBUG_MODE=1

REM Change directory to the bot's folder
echo Changing to bot directory...
cd /d "%~dp0"
echo Current directory: %CD%
echo.

REM Check if virtual environment exists
echo Checking for virtual environment...
if not exist ".venv\" (
    echo WARNING: Virtual environment not found at .venv\
    echo Consider running setup.bat first for optimal setup
    echo.
) else (
    echo ✅ Virtual environment found at .venv\
)

REM Check if Python is available (prefer venv, fallback to system)
echo Checking Python installation...
if exist ".venv\Scripts\python.exe" (
    echo Using virtual environment Python...
    set PYTHON_CMD=.venv\Scripts\python.exe
    .venv\Scripts\python.exe --version
    if %errorlevel% neq 0 (
        echo ERROR: Virtual environment Python failed
        echo Falling back to system Python...
        goto :check_system_python
    )
) else (
    :check_system_python
    echo Using system Python...
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: Python is not installed or not in PATH
        echo Please install Python and add it to your system PATH
        echo.
        echo Press any key to exit...
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
)

echo Python command set to: %PYTHON_CMD%
echo.

REM Check for required files
echo Checking bot files...
echo Looking for bot.py...
if not exist "bot.py" (
    echo ERROR: bot.py not found in current directory
    echo Current directory: %CD%
    dir bot.* /b
    echo.
    echo Press any key to exit...
    pause
    exit /b 1
) else (
    echo ✅ bot.py found
)

echo Looking for config.py...
if not exist "config.py" (
    echo ERROR: config.py not found - Please configure your bot first
    echo Current directory: %CD%
    dir config.* /b
    echo.
    echo Press any key to exit...
    pause
    exit /b 1
) else (
    echo ✅ config.py found
)

REM Check if monitoring system is available
echo Checking monitoring system...
if exist "utils\monitoring_dashboard.py" (
    if exist "utils\monitoring_system.py" (
        echo ✅ Monitoring system detected
        set MONITORING_AVAILABLE=1
    ) else (
        echo ⚠️ utils\monitoring_system.py not found
        set MONITORING_AVAILABLE=0
    )
) else (
    echo ⚠️ utils\monitoring_dashboard.py not found
    set MONITORING_AVAILABLE=0
)

echo Monitoring available: %MONITORING_AVAILABLE%
echo.

REM Start monitoring dashboard in background if available
if %MONITORING_AVAILABLE%==1 (
    echo.
    echo Starting monitoring dashboard...
    echo Command: start "Monitoring Dashboard" /min %PYTHON_CMD% utils\monitoring_dashboard.py
    start "Monitoring Dashboard" /min %PYTHON_CMD% utils\monitoring_dashboard.py
    if %errorlevel% neq 0 (
        echo WARNING: Failed to start monitoring dashboard (error %errorlevel%)
    ) else (
        echo Monitoring dashboard started at http://localhost:5000
    )
    echo Waiting 3 seconds for startup...
    timeout /t 3 /nobreak >nul
) else (
    echo Skipping monitoring dashboard (not available)
)

REM Start the main bot
echo.
echo Starting Lemegeton Bot (Public Mode)...
echo ========================================
echo Command: %PYTHON_CMD% bot.py
echo.

REM Run the bot and capture exit code
%PYTHON_CMD% bot.py
set BOT_EXIT_CODE=%errorlevel%

REM Bot stopped - show status
echo.
echo ========================================
echo   Bot has stopped (Exit Code: %BOT_EXIT_CODE%)
echo ========================================

if %BOT_EXIT_CODE% neq 0 (
    echo ❌ Bot exited with error code: %BOT_EXIT_CODE%
    echo This may indicate an error occurred.
    echo Check the logs in the logs/ folder for details.
) else (
    echo ✅ Bot exited normally
)

if %MONITORING_AVAILABLE%==1 (
    echo.
    echo Note: Monitoring dashboard may still be running
    echo Visit http://localhost:5000 to check status
)

echo.
echo Press any key to exit...
pause >nul
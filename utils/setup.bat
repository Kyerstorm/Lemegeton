@echo off
setlocal

cd /d "%~dp0\.."

echo Lemegeton TypeScript setup
echo.

where node >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js 22 or newer is required.
  exit /b 1
)
node --version
where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm is required.
  exit /b 1
)
where cargo >nul 2>&1
if errorlevel 1 (
  echo ERROR: Rust and Cargo are required to build the dashboard backend.
  exit /b 1
)

echo.
echo Installing bot dependencies...
call npm install --no-audit --no-fund
if errorlevel 1 exit /b 1

echo.
echo Building and testing TypeScript bot...
call npm test
if errorlevel 1 exit /b 1

echo.
echo Installing dashboard dependencies...
call npm install --prefix web\frontend --no-audit --no-fund
if errorlevel 1 exit /b 1

echo.
echo Checking and building dashboard...
call npm run typecheck --prefix web\frontend
if errorlevel 1 exit /b 1
call npm run build --prefix web\frontend
if errorlevel 1 exit /b 1

echo.
echo Building Rust dashboard...
call cargo build --manifest-path web\backend\Cargo.toml --release
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Configure .env, then deploy with the supported host or Docker.
endlocal

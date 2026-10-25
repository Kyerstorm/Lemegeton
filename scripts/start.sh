#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -s "$ROOT/dashboard-frontend/dist/app.js" || ! -s "$ROOT/dashboard-frontend/dist/app.css" ]]; then
  echo "Dashboard frontend assets are missing. Build them with: npm install --prefix dashboard-frontend && npm run build --prefix dashboard-frontend" >&2
  exit 1
fi

DASHBOARD_BIN="$ROOT/dashboard-rs/target/release/lemegeton-dashboard"
if [[ ! -x "$DASHBOARD_BIN" ]]; then
  echo "Rust dashboard binary is missing. Build it with: cargo build --manifest-path dashboard-rs/Cargo.toml --release" >&2
  exit 1
fi

"$DASHBOARD_BIN" &
dashboard_pid=$!
python bot.py &
bot_pid=$!

cleanup() {
  kill -TERM "$dashboard_pid" "$bot_pid" 2>/dev/null || true
  wait "$dashboard_pid" 2>/dev/null || true
  wait "$bot_pid" 2>/dev/null || true
}
trap cleanup TERM INT EXIT

wait -n "$dashboard_pid" "$bot_pid"
status=$?
cleanup
trap - TERM INT EXIT
exit "$status"

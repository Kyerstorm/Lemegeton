#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "Lemegeton startup error: $*" >&2
  exit 1
}

command -v node >/dev/null 2>&1 || fail "Node.js 22 or newer is required."
node --version | grep -Eq '^v(22|2[3-9]|[3-9][0-9])\.' || fail "Node.js 22 or newer is required."

if [[ ! -s "$ROOT/dist/bot.js" ]]; then
  [[ -x "$ROOT/node_modules/.bin/tsc" ]] || fail "TypeScript output is missing and dependencies are not installed. Run npm install first."
  echo "TypeScript build output is missing; compiling the bot."
  npm run build --prefix "$ROOT"
fi

[[ -s "$ROOT/web/frontend/out/index.html" ]] || fail "The Next.js dashboard export is missing. Build it with: npm install --prefix web/frontend && npm run typecheck --prefix web/frontend && npm run build --prefix web/frontend"
[[ -s "$ROOT/web/frontend/out/login/index.html" ]] || fail "The dashboard login export is missing."
DASHBOARD_BIN="$ROOT/target/release/lemegeton-dashboard"
[[ -x "$DASHBOARD_BIN" ]] || fail "The Rust dashboard binary is missing. Build it with: cargo build --manifest-path web/backend/Cargo.toml --release"

"$DASHBOARD_BIN" &
dashboard_pid=$!
node --env-file-if-exists="$ROOT/.env" "$ROOT/dist/bot.js" &
bot_pid=$!

cleanup() {
  local pid
  for pid in "$dashboard_pid" "$bot_pid"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  for pid in "$dashboard_pid" "$bot_pid"; do
    wait "$pid" 2>/dev/null || true
  done
}

on_signal() {
  local status="$1"
  cleanup
  exit "$status"
}

trap 'on_signal 130' INT
trap 'on_signal 143' TERM

set +e
wait -n "$dashboard_pid" "$bot_pid"
status=$?
set -e

cleanup
trap - INT TERM
exit "$status"

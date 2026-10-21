"""Import this FIRST in every Custom Roles test. It makes the tests safe to run.

- Refuses to run unless the database is a local PostgreSQL in development
  (no DATABASE_URL-style connection strings, POSTGRES_HOST must be localhost).
- Never loads the bot token, and makes any Discord API call fail loudly.
  Tests only use fake Discord objects (fakes.py).
- Moves logging into a temporary folder so test runs don't mix into the
  running bot's logs/.
- Tests only create and delete rows for tiny fake guild IDs (TEST_GUILD_IDS),
  which can never match a real Discord server ID.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEST_GUILD_IDS = (2, 3, 4, 5, 6, 7, 8, 9, 10)  # real Discord IDs are 17-20 digit snowflakes
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _refuse(reason: str) -> None:
    sys.exit(f"REFUSING TO RUN CUSTOM ROLES TESTS: {reason}")


# Test labels contain emoji; Windows consoles default to cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# 1) Never load the bot token. load_dotenv doesn't override variables that are already set.
os.environ["DISCORD_TOKEN"] = ""
from dotenv import dotenv_values, load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")
settings = {**dotenv_values(REPO / ".env"), **os.environ}

# 2) Only a local development database.
for key in ("DATABASE_URL", "POSTGRES_DSN", "POSTGRES_URL"):
    if settings.get(key):
        _refuse(f"{key} is set. These tests only run against a local PostgreSQL (POSTGRES_HOST=localhost).")
host = (settings.get("POSTGRES_HOST") or "127.0.0.1").strip().lower()
if host not in LOCAL_HOSTS:
    _refuse(f"POSTGRES_HOST is {host!r}, not a local database.")
if (settings.get("ENVIRONMENT") or "development").strip().lower() != "development":
    _refuse("ENVIRONMENT isn't development.")

# 3) Project imports, with logs written to a throwaway folder.
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
os.chdir(tempfile.mkdtemp(prefix="custom_roles_tests_"))

# 4) Any real Discord API call is a bug in a test.
import discord.http  # noqa: E402


async def _no_discord(*args, **kwargs):
    raise RuntimeError("Custom Roles tests must never call the Discord API (use fakes.py).")


discord.http.HTTPClient.request = _no_discord

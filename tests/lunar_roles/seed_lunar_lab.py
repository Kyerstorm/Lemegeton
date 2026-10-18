"""Not a test. Adds fake "saved" Lunar records to the test server so /lunar-admin list has pages.

    .venv/Scripts/python.exe tests/lunar_roles/seed_lunar_lab.py add [count]   # default 15, max 60
    .venv/Scripts/python.exe tests/lunar_roles/seed_lunar_lab.py status
    .venv/Scripts/python.exe tests/lunar_roles/seed_lunar_lab.py remove        # deletes everything it added

Safety:
- Only touches the server in .env's GUILD_ID (the Lunar Lab test server), and only if Lunar
  Roles has settings there.
- Refuses to run when ENVIRONMENT=production. _safety.py then also requires a local
  development database, never loads the bot token and blocks Discord API calls.
- Only creates records with status "saved" and the fake user IDs 1000001-1000060. Those can't
  be real Discord users (real IDs are 17-20 digits), so "remove" deletes exactly what "add" made.
- Saved records of members who aren't in the server are left alone by the bot: reconcile
  doesn't archive them and nothing restores them.
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[2]
_env = dotenv_values(REPO / ".env")
for _source in (_env.get("ENVIRONMENT"), os.environ.get("ENVIRONMENT")):
    if (_source or "").strip().lower() == "production":
        sys.exit("REFUSING TO SEED: ENVIRONMENT is production.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _safety  # noqa: E402,F401  (local dev database only, no token, no Discord calls)

SEED_FIRST_ID = 1_000_001
SEED_MAX = 60
SEED_IDS = range(SEED_FIRST_ID, SEED_FIRST_ID + SEED_MAX)
SEED_COLORS = (0xFF66AA, 0x66CCFF, 0xFFD166, 0x06D6A0, 0x9B5DE5, 0xF15BB5)
USAGE = "Usage: seed_lunar_lab.py add [count] | status | remove"


def _guild_id() -> int:
    raw = (_env.get("GUILD_ID") or "").strip()
    if not raw.isdigit() or not 17 <= len(raw) <= 20:
        sys.exit("REFUSING TO SEED: GUILD_ID in .env is missing or isn't a Discord server ID.")
    return int(raw)


async def _count(q, guild_id: int) -> int:
    row = await q(
        "count lunar seed records",
        "SELECT COUNT(*) FROM lunar_custom_roles WHERE guild_id = ? AND user_id BETWEEN ? AND ?",
        (guild_id, SEED_IDS[0], SEED_IDS[-1]),
        fetch_type="one",
    )
    return int(row[0])


async def main(args) -> int:
    import database as db

    if not args or args[0] not in {"add", "status", "remove"}:
        print(USAGE)
        return 2
    command = args[0]
    q = db.execute_db_operation
    await db.init_lunar_roles_tables()
    guild_id = _guild_id()
    settings = await q(
        "check lunar settings for seed guild",
        "SELECT 1 FROM lunar_guild_settings WHERE guild_id = ?",
        (guild_id,),
        fetch_type="one",
    )
    if not settings:
        print("REFUSING TO SEED: Lunar Roles has no settings for the GUILD_ID server in .env. "
              "Run /lunar-admin anchor there first.")
        return 1

    if command == "status":
        print(f"{await _count(q, guild_id)} seed record(s) in the GUILD_ID server.")
        return 0

    if command == "remove":
        before = await _count(q, guild_id)
        for table in ("lunar_custom_roles", "lunar_archive_snoozes"):
            await q(
                "remove lunar seed records",
                f"DELETE FROM {table} WHERE guild_id = ? AND user_id BETWEEN ? AND ?",
                (guild_id, SEED_IDS[0], SEED_IDS[-1]),
            )
        print(f"Removed {before} seed record(s). {await _count(q, guild_id)} left.")
        return 0

    try:
        count = int(args[1]) if len(args) > 1 else 15
    except ValueError:
        print(USAGE)
        return 2
    if not 1 <= count <= SEED_MAX:
        print(f"Count must be 1-{SEED_MAX}.")
        return 2
    for n, user_id in enumerate(SEED_IDS[:count], start=1):
        await q(
            "add lunar seed record",
            """
            INSERT INTO lunar_custom_roles (guild_id, user_id, role_id, status, name, color_mode, primary_color,
                                            created_at, updated_at)
            VALUES (?, ?, NULL, 'saved', ?, 'solid', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            (guild_id, user_id, f"Seed Role {n:02d}", SEED_COLORS[n % len(SEED_COLORS)]),
        )
    print(f"{await _count(q, guild_id)} seed record(s) in the GUILD_ID server (all 'saved'). "
          "Remove them with: seed_lunar_lab.py remove")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

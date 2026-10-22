"""Not a test. Adds fake "saved" custom role records to the test server so /custom-role-admin list has pages,
and fake old /nitro-role-set rows (booster_roles) for testing /custom-role-admin import-legacy.

    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py add [count]   # default 15, max 60
    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py status
    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py remove        # deletes everything it added

    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-add ROLE_ID [USER_ID]
    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-status
    .venv/Scripts/python.exe tests/custom_roles/seed_test_server.py legacy-remove  # only the rows legacy-add made

legacy-add records ROLE_ID as USER_ID's old /nitro-role-set role. Without USER_ID it uses the next
fake ID from 1000901 (someone who "left the server"). It never overwrites an existing row, and
legacy-remove deletes only the rows it added (remembered in custom_role_meta), plus custom role records of its
fake members. custom role records of real members are left alone; remove those with /custom-role-admin remove.

Safety:
- Only touches the server in .env's GUILD_ID (the test server), and only if Custom
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
USAGE = ("Usage: seed_test_server.py add [count] | status | remove | "
         "legacy-add ROLE_ID [USER_ID] | legacy-status | legacy-remove")
LEGACY_FAKE_FIRST_ID = 1_000_901
LEGACY_META_KEY = "seed_legacy_rows"


def _guild_id() -> int:
    raw = (_env.get("GUILD_ID") or "").strip()
    if not raw.isdigit() or not 17 <= len(raw) <= 20:
        sys.exit("REFUSING TO SEED: GUILD_ID in .env is missing or isn't a Discord server ID.")
    return int(raw)


async def _count(q, guild_id: int) -> int:
    row = await q(
        "count custom role seed records",
        "SELECT COUNT(*) FROM custom_role_records WHERE guild_id = ? AND user_id BETWEEN ? AND ?",
        (guild_id, SEED_IDS[0], SEED_IDS[-1]),
        fetch_type="one",
    )
    return int(row[0])


async def main(args) -> int:
    import database as db

    if not args or args[0] not in {"add", "status", "remove", "legacy-add", "legacy-status", "legacy-remove"}:
        print(USAGE)
        return 2
    command = args[0]
    q = db.execute_db_operation
    await db.init_custom_roles_tables()
    guild_id = _guild_id()
    settings = await q(
        "check custom role settings for seed guild",
        "SELECT 1 FROM custom_role_guild_settings WHERE guild_id = ?",
        (guild_id,),
        fetch_type="one",
    )
    if not settings:
        print("REFUSING TO SEED: Custom Roles has no settings for the GUILD_ID server in .env. "
              "Run /custom-role-admin anchor there first.")
        return 1

    if command.startswith("legacy-"):
        return await _legacy(q, guild_id, command, args[1:])

    if command == "status":
        print(f"{await _count(q, guild_id)} seed record(s) in the GUILD_ID server.")
        return 0

    if command == "remove":
        before = await _count(q, guild_id)
        for table in ("custom_role_records", "custom_role_archive_snoozes"):
            await q(
                "remove custom role seed records",
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
            "add custom role seed record",
            """
            INSERT INTO custom_role_records (guild_id, user_id, role_id, status, name, color_mode, primary_color,
                                            created_at, updated_at)
            VALUES (?, ?, NULL, 'saved', ?, 'solid', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            (guild_id, user_id, f"Seed Role {n:02d}", SEED_COLORS[n % len(SEED_COLORS)]),
        )
    print(f"{await _count(q, guild_id)} seed record(s) in the GUILD_ID server (all 'saved'). "
          "Remove them with: seed_test_server.py remove")
    return 0


async def _legacy(q, guild_id: int, command: str, args) -> int:
    import json

    row = await q("read legacy seed list", "SELECT value FROM custom_role_meta WHERE key = ?", (LEGACY_META_KEY,), fetch_type="one")
    seeded = [tuple(pair) for pair in json.loads(row[0])] if row and row[0] else []

    async def save():
        await q("save legacy seed list",
                "INSERT INTO custom_role_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (LEGACY_META_KEY, json.dumps(seeded)))

    if command == "legacy-status":
        total = (await q("count legacy rows", "SELECT COUNT(*) FROM booster_roles WHERE guild_id = ?", (guild_id,),
                         fetch_type="one"))[0]
        print(f"{total} old /nitro-role-set row(s) in the GUILD_ID server, {len(seeded)} of them added by this script:")
        for user_id, role_id in seeded:
            print(f"  user {user_id} -> role {role_id}")
        return 0

    if command == "legacy-remove":
        for user_id, role_id in seeded:
            await q("remove legacy seed row", "DELETE FROM booster_roles WHERE guild_id = ? AND discord_id = ? AND role_id = ?",
                    (guild_id, user_id, role_id))
        fake = [u for u, _ in seeded if LEGACY_FAKE_FIRST_ID <= u < LEGACY_FAKE_FIRST_ID + 100]
        for user_id in fake:  # custom role records an import made for the fake "left the server" members
            for table in ("custom_role_records", "custom_role_archive_snoozes"):
                await q("remove legacy seed record", f"DELETE FROM {table} WHERE guild_id = ? AND user_id = ?",
                        (guild_id, user_id))
        print(f"Removed {len(seeded)} old-role row(s) this script added, and any custom role records of its "
              f"{len(fake)} fake member(s).")
        seeded.clear()
        await save()
        return 0

    try:
        role_id = int(args[0])
        user_id = int(args[1]) if len(args) > 1 else None
    except (IndexError, ValueError):
        print(USAGE)
        return 2
    if user_id is None:
        used = {u for u, _ in seeded}
        user_id = next(i for i in range(LEGACY_FAKE_FIRST_ID, LEGACY_FAKE_FIRST_ID + 100) if i not in used)
    added = await q(
        "add legacy seed row",
        "INSERT INTO booster_roles (discord_id, guild_id, role_id) VALUES (?, ?, ?) "
        "ON CONFLICT (discord_id, guild_id) DO NOTHING RETURNING discord_id",
        (user_id, guild_id, role_id), fetch_type="one",
    )
    if not added:
        print(f"User {user_id} already has an old-role row; nothing changed.")
        return 1
    seeded.append((user_id, role_id))
    await save()
    print(f"Added: user {user_id} -> role {role_id} as an old /nitro-role-set role. Undo with: seed_test_server.py legacy-remove")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))

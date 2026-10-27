import asyncio, asyncpg
from dotenv import dotenv_values

async def main():
    c = await asyncpg.connect(dotenv_values(".env")["DATABASE_URL"])
    for t in ("planned_features", "feature_status_history", "alfiles", "files"):
        r = await c.fetchrow(
            "select column_name, is_identity, column_default from information_schema.columns "
            "where table_schema='public' and table_name=$1 and ordinal_position=1", t)
        print(f"  {t:24} first col={r['column_name']!r:6} identity={r['is_identity']} default={r['column_default']}")
    cols = await c.fetch(
        "select column_name, is_nullable, column_default from information_schema.columns "
        "where table_schema='public' and table_name='feature_status_history' order by ordinal_position")
    print("  feature_status_history:", [(r[0], r[1], r[2]) for r in cols])
    fks = await c.fetch(
        "select conname, pg_get_constraintdef(oid) d from pg_constraint "
        "where conrelid='feature_status_history'::regclass and contype='f'")
    print("  its FKs:", [f["d"] for f in fks])
    # write test: insert like the cog does (no id), then roll back
    tr = c.transaction(); await tr.start()
    try:
        required = [r[0] for r in cols if r[1] == "NO" and r[2] is None and r[0] != "id"]
        fid = await c.fetchval("select id from planned_features order by id limit 1")
        vals = {"feature_id": fid}
        for col in required:
            vals.setdefault(col, "test" if "status" in col else 1)
        names = list(vals)
        new_id = await c.fetchval(
            f"insert into feature_status_history ({', '.join(names)}) values "
            f"({', '.join('$'+str(i+1) for i in range(len(names)))}) returning id", *vals.values())
        print(f"  write test: inserted without id -> got id {new_id} (rolled back)")
    except Exception as e:
        print("  write test FAILED:", type(e).__name__, e)
    finally:
        await tr.rollback()
    # sequences past existing ids everywhere?
    bad = []
    for r in await c.fetch(
        "select table_name, column_name from information_schema.columns "
        "where table_schema='public' and is_identity='YES'"):
        mx = await c.fetchval(f'select max("{r[1]}") from "{r[0]}"')
        seq = await c.fetchval("select pg_get_serial_sequence($1, $2)", f'"{r[0]}"', r[1])
        last = await c.fetchval(f"select last_value from {seq}") if seq else None
        if mx is not None and (last is None or last < mx):
            bad.append((r[0], mx, last))
    print("  identity sequences behind their max id:", bad or "none")
    await c.close()

asyncio.run(main())

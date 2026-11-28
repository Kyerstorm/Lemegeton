import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase, query, queryOne } from "../src/utility/database/libsql/database.js";

test("libSQL schema initialization is repeatable and preserves guild-scoped rows", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-schema-repeat-"));
  const config = { path: join(directory, "bot.db"), primaryGuildId: "111111111111111111" };
  try {
    await initDatabase(config);
    await query(
      "INSERT INTO users (discord_id, guild_id, username) VALUES ($1,$2,$3),($1,$4,$3)",
      ["123456789012345678", "111111111111111111", "member", "222222222222222222"],
    );
    await query(
      "INSERT INTO guild_retention_settings (guild_id, invited_by) VALUES ($1,$2)",
      ["111111111111111111", "123456789012345678"],
    );

    await initDatabase(config);

    const firstGuild = await queryOne<{ discord_id: string; guild_id: string }>(
      "SELECT discord_id, guild_id FROM users WHERE guild_id = $1",
      ["111111111111111111"],
    );
    const secondGuild = await queryOne<{ discord_id: string; guild_id: string }>(
      "SELECT discord_id, guild_id FROM users WHERE guild_id = $1",
      ["222222222222222222"],
    );
    assert.equal(firstGuild?.discord_id, "123456789012345678");
    assert.equal(firstGuild?.guild_id, "111111111111111111");
    assert.equal(secondGuild?.guild_id, "222222222222222222");
    assert.equal(await queryOne("SELECT guild_id FROM guild_retention_settings WHERE guild_id = $1", ["222222222222222222"]), null);
    const tables = await query<{ name: string }>(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('users','guild_retention_settings','media_assets','bot_database_backups') ORDER BY name",
    );
    assert.deepEqual(tables.map(row => row.name), [
      "bot_database_backups", "guild_retention_settings", "media_assets", "users",
    ]);
  } finally {
    await closeDatabase().catch(() => undefined);
    await rm(directory, { recursive: true, force: true });
  }
});

import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  deleteArchiveAsset,
  deleteCustomRoleIconSource,
  readArchiveAsset,
  readCustomRoleIconSource,
  storeArchiveUpload,
  storeCustomRoleIconSource,
  configureMediaStorage,
} from "../helpers/media/media-storage.js";
import { closeRocksDb } from "../src/utility/database/rocksdb/rocksdb.js";

test("private RocksDB media round-trips chunked Archive uploads and guild-scoped role icons", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-rocks-media-"));
  const guildId = "987654321098765432";
  const otherGuildId = "987654321098765433";
  const userId = "123456789012345678";
  const objectBytes = Buffer.alloc(1024 * 1024 + 37, 0x5a);
  const iconBytes = Buffer.from("private-role-icon-image");
  try {
    await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: guildId });
    configureMediaStorage({
      archiveUploadMaxBytes: 20 * 1024 * 1024,
      rocksDbPath: join(directory, "objects"),
    });

    const assetId = await storeArchiveUpload(
      guildId,
      userId,
      "panels",
      { name: "panel.png", contentType: "image/png", bytes: objectBytes },
      ["image"],
    );
    assert.deepEqual(await readArchiveAsset(assetId, guildId), objectBytes);
    assert.equal(await readArchiveAsset(assetId, otherGuildId), null);
    assert.equal(await deleteArchiveAsset(assetId), true);
    assert.equal(await readArchiveAsset(assetId, guildId), null);

    const iconId = await storeCustomRoleIconSource(guildId, userId, iconBytes, "image/png");
    assert.deepEqual(await readCustomRoleIconSource(iconId, guildId), iconBytes);
    assert.equal(await readCustomRoleIconSource(iconId, otherGuildId), null);
    assert.equal(await deleteCustomRoleIconSource(iconId, otherGuildId), false);
    assert.equal(await deleteCustomRoleIconSource(iconId, guildId), true);
    assert.equal(await readCustomRoleIconSource(iconId, guildId), null);
  } finally {
    closeRocksDb();
    await closeDatabase().catch(() => undefined);
    await rm(directory, { recursive: true, force: true });
  }
});

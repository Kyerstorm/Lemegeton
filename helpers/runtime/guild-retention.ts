import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { deleteArchiveAsset } from "../media/media-storage.js";
import { getSupportedLanguage, isGuildLanguageConfigured } from "./languages.js";

export type GuildLeaveAction = "delete" | "retain";

export interface GuildRetentionSettings {
  invited_by: string | null;
  leave_action: GuildLeaveAction | null;
}

export function isGuildLeaveAction(value: unknown): value is GuildLeaveAction {
  return value === "delete" || value === "retain";
}

export function canConfigureGuildLeaveAction(
  invitedBy: string | null,
  actorId: string,
  canManageServer: boolean,
): boolean {
  return canManageServer || invitedBy === actorId;
}

export async function ensureGuildRetentionSettings(guildId: string): Promise<void> {
  await query(
    "INSERT INTO guild_retention_settings (guild_id) VALUES ($1) ON CONFLICT (guild_id) DO NOTHING",
    [guildId],
  );
}

export async function recordGuildInviter(guildId: string, invitedBy: string): Promise<void> {
  await query(
    `INSERT INTO guild_retention_settings (guild_id, invited_by)
     VALUES ($1,$2)
     ON CONFLICT (guild_id) DO UPDATE
       SET invited_by = COALESCE(guild_retention_settings.invited_by, EXCLUDED.invited_by),
           updated_at = CASE
             WHEN guild_retention_settings.invited_by IS NULL THEN NOW()
             ELSE guild_retention_settings.updated_at
           END`,
    [guildId, invitedBy],
  );
}

export async function getGuildRetentionSettings(guildId: string): Promise<GuildRetentionSettings> {
  const row = await queryOne<{ invited_by: string | null; leave_action: string | null }>(
    "SELECT invited_by::text, leave_action FROM guild_retention_settings WHERE guild_id = $1",
    [guildId],
  );
  return {
    invited_by: row?.invited_by ?? null,
    leave_action: isGuildLeaveAction(row?.leave_action) ? row.leave_action : null,
  };
}

export async function isGuildRetentionConfigured(guildId: string): Promise<boolean> {
  const row = await queryOne<{ leave_action: string | null }>(
    "SELECT leave_action FROM guild_retention_settings WHERE guild_id = $1",
    [guildId],
  );
  return isGuildLeaveAction(row?.leave_action);
}

export function isGuildSetupCompleteState(retentionConfigured: boolean, languageConfigured: boolean): boolean {
  return retentionConfigured && languageConfigured;
}

export async function isGuildSetupComplete(guildId: string): Promise<boolean> {
  const [retentionConfigured, languageConfigured] = await Promise.all([
    isGuildRetentionConfigured(guildId),
    isGuildLanguageConfigured(guildId),
  ]);
  return isGuildSetupCompleteState(retentionConfigured, languageConfigured);
}

export async function saveGuildSetupSettings(
  guildId: string,
  actorId: string,
  action: GuildLeaveAction,
  languageCode: string,
): Promise<void> {
  if (!isGuildLeaveAction(action)) throw new Error("Choose whether to delete or retain this server's data.");
  const language = getSupportedLanguage(languageCode);
  if (!language) throw new Error("Choose a language from the supported language list.");

  await transaction(async client => {
    await client.query(
      `INSERT INTO guild_retention_settings (guild_id, leave_action, updated_by)
       VALUES ($1,$2,$3)
       ON CONFLICT (guild_id) DO UPDATE
         SET leave_action = EXCLUDED.leave_action,
             updated_by = EXCLUDED.updated_by,
             deleted_at = NULL,
             updated_at = NOW()`,
      [guildId, action, actorId],
    );
    await client.query(
      `INSERT INTO guild_language_settings (guild_id, language_code, updated_by)
       VALUES ($1,$2,$3)
       ON CONFLICT (guild_id) DO UPDATE
         SET language_code = EXCLUDED.language_code,
             updated_by = EXCLUDED.updated_by,
             updated_at = NOW()`,
      [guildId, language.code, actorId],
    );
  });
}

export async function setGuildLeaveAction(
  guildId: string,
  action: GuildLeaveAction,
  actorId: string,
): Promise<void> {
  await query(
    `INSERT INTO guild_retention_settings (guild_id, leave_action, updated_by)
     VALUES ($1,$2,$3)
     ON CONFLICT (guild_id) DO UPDATE
       SET leave_action = EXCLUDED.leave_action,
           updated_by = EXCLUDED.updated_by,
           deleted_at = NULL,
           updated_at = NOW()`,
    [guildId, action, actorId],
  );
}

function quoteIdentifier(identifier: string): string {
  return '"' + identifier.replaceAll('"', '""') + '"';
}

/**
 * Removes guild-owned database records transactionally, then deletes private
 * object storage assets. Failed deletions remain in the existing retry queue.
 * The retention decision itself is deliberately preserved across departures.
 */
export async function deleteGuildData(guildId: string): Promise<{
  deletedRows: number;
  assetsAttempted: number;
  assetsPending: number;
}> {
  const assets = await query<{ id: string }>(
    "SELECT id::text FROM media_assets WHERE guild_id = $1 ORDER BY id",
    [guildId],
  );

  const deletedRows = await transaction(async client => {
    const tables = await client.query<{ table_name: string }>(
      "SELECT name AS table_name FROM sqlite_master " +
      "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' " +
      "AND name NOT IN ('guild_retention_settings', 'media_assets') ORDER BY name",
    );
    const scopedTables: Array<{ table_name: string; column_name: string }> = [];
    const guildColumns = new Set(["guild_id", "created_guild_id", "uploader_guild_id"]);
    for (const table of tables.rows) {
      const columns = await client.query<{ name: string }>(
        "PRAGMA table_info(" + quoteIdentifier(table.table_name) + ")",
      );
      for (const column of columns.rows) {
        if (guildColumns.has(column.name)) {
          scopedTables.push({ table_name: table.table_name, column_name: column.name });
        }
      }
    }

    let totalDeleted = 0;
    for (let pass = 0; pass <= scopedTables.length; pass += 1) {
      let deletedThisPass = 0;
      let blocked = false;
      for (const table of scopedTables) {
        const target = `"main".${quoteIdentifier(table.table_name)}`;
        const column = quoteIdentifier(table.column_name);
        await client.query("SAVEPOINT guild_purge_item");
        try {
          const result = await client.query(
            `DELETE FROM ${target} WHERE ${column} = $1`,
            [guildId],
          );
          const count = result.rowCount ?? 0;
          deletedThisPass += count;
          totalDeleted += count;
          await client.query("RELEASE SAVEPOINT guild_purge_item");
        } catch (error) {
          await client.query("ROLLBACK TO SAVEPOINT guild_purge_item");
          await client.query("RELEASE SAVEPOINT guild_purge_item");
          if ((error as { code?: string }).code !== "23503") throw error;
          blocked = true;
        }
      }
      if (!blocked) break;
      if (deletedThisPass === 0) {
        throw new Error("Guild data deletion is blocked by a foreign-key reference outside the guild-scoped tables.");
      }
      if (pass === scopedTables.length) {
        throw new Error("Guild data deletion did not reach a consistent empty state.");
      }
    }
    return totalDeleted;
  });

  let assetsPending = 0;
  for (const asset of assets) {
    try {
      await deleteArchiveAsset(Number(asset.id));
      const queued = await queryOne<{ exists: boolean }>(
        "SELECT EXISTS (SELECT 1 FROM media_asset_cleanup_queue WHERE asset_id = $1) AS exists",
        [asset.id],
      );
      if (queued?.exists) assetsPending += 1;
    } catch {
      assetsPending += 1;
    }
  }
  await query(
    "UPDATE guild_retention_settings SET deleted_at = NOW(), updated_at = NOW() WHERE guild_id = $1 AND leave_action = 'delete'",
    [guildId],
  );
  return { deletedRows, assetsAttempted: assets.length, assetsPending };
}

export async function retryDepartedGuildDeletions(activeGuildIds: Iterable<string>): Promise<{
  checked: number;
  deleted: number;
  failed: number;
}> {
  const active = [...activeGuildIds];
  const pending = await query<{ guild_id: string }>(
    `SELECT guild_id::text
       FROM guild_retention_settings
      WHERE leave_action = 'delete' AND deleted_at IS NULL
        AND NOT (guild_id = ANY($1::bigint[]))
      ORDER BY created_at ASC LIMIT 25`,
    [active],
  );

  let deleted = 0;
  let failed = 0;
  for (const row of pending) {
    try {
      await deleteGuildData(row.guild_id);
      deleted += 1;
    } catch {
      failed += 1;
    }
  }
  return { checked: pending.length, deleted, failed };
}

import { query, queryOne } from "../../database.js";

const DEFAULT_MEDIA_REGION = "IE";

export function normalizeMediaRegion(value: string): string | null {
  const region = value.trim().toUpperCase();
  return /^[A-Z]{2}$/.test(region) ? region : null;
}

export async function getGuildMediaRegion(guildId: string | null): Promise<string> {
  if (!guildId) return DEFAULT_MEDIA_REGION;
  const row = await queryOne<{ release_region: string }>(
    "SELECT release_region FROM connected_media_guild_settings WHERE guild_id = $1",
    [guildId],
  );
  return normalizeMediaRegion(row?.release_region ?? "") ?? DEFAULT_MEDIA_REGION;
}

export async function setGuildMediaRegion(guildId: string, value: string, updatedBy: string): Promise<string> {
  const region = normalizeMediaRegion(value);
  if (!region) throw new Error("Media region must be a two-letter country code, such as IE or US.");
  await query(
    `INSERT INTO connected_media_guild_settings (guild_id, release_region, updated_by)
     VALUES ($1, $2, $3)
     ON CONFLICT (guild_id) DO UPDATE
       SET release_region = EXCLUDED.release_region,
           updated_by = EXCLUDED.updated_by,
           updated_at = NOW()`,
    [guildId, region, updatedBy],
  );
  return region;
}

import { query, queryOne } from "../database.js";

export const FEATURE_NAMES = ["discover","archive","community","play","profile","custom-role"] as const;
export type FeatureName = typeof FEATURE_NAMES[number];
export type FeatureSettings = Record<FeatureName, boolean>;

export function isFeatureName(value: string): value is FeatureName {
  return (FEATURE_NAMES as readonly string[]).includes(value);
}

export async function getFeatureSettings(guildId: string): Promise<FeatureSettings> {
  const states: FeatureSettings = {discover:true,archive:true,community:true,play:true,profile:true};
  const rows = await query<{feature_name:string;enabled:boolean}>(
    "SELECT feature_name,enabled FROM guild_feature_settings WHERE guild_id = $1", [guildId],
  );
  for (const row of rows) if (isFeatureName(row.feature_name)) states[row.feature_name] = row.enabled;
  return states;
}

export async function isFeatureEnabled(guildId: string, feature: string): Promise<boolean> {
  if (!isFeatureName(feature)) return true;
  const row = await queryOne<{enabled:boolean}>(
    "SELECT enabled FROM guild_feature_settings WHERE guild_id = $1 AND feature_name = $2", [guildId,feature],
  );
  return row?.enabled ?? true;
}

export async function setFeatureEnabled(guildId: string, feature: FeatureName, enabled: boolean, actorId: string): Promise<void> {
  await query(
    `INSERT INTO guild_feature_settings (guild_id,feature_name,enabled,updated_by)
     VALUES ($1,$2,$3,$4)
     ON CONFLICT (guild_id,feature_name)
     DO UPDATE SET enabled=EXCLUDED.enabled,updated_by=EXCLUDED.updated_by,updated_at=NOW()`,
    [guildId,feature,enabled,actorId],
  );
}

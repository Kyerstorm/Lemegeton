import { query, queryOne } from "../../database.js";

export type RoleAccessMode = "everyone" | "include" | "exclude";
export type ChannelAccessMode = "all" | "include" | "exclude";
export type CommandAccessPolicy = {
  role_mode: RoleAccessMode;
  role_ids: string[];
  channel_mode: ChannelAccessMode;
  channel_ids: string[];
  revision: number;
};
type StoredPolicy = Omit<CommandAccessPolicy, "revision"> & { revision: string | number };
const DEFAULT_POLICY: CommandAccessPolicy = {
  role_mode: "everyone", role_ids: [], channel_mode: "all", channel_ids: [], revision: 0,
};

export async function initCommandAccessSchema(): Promise<void> {
  await query(`
    CREATE TABLE IF NOT EXISTS guild_command_access (
      guild_id TEXT NOT NULL,
      command_name VARCHAR(100) NOT NULL,
      role_mode VARCHAR(12) NOT NULL DEFAULT 'everyone'
        CHECK (role_mode IN ('everyone','include','exclude')),
      role_ids JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(role_ids) = 'array'),
      channel_mode VARCHAR(12) NOT NULL DEFAULT 'all'
        CHECK (channel_mode IN ('all','include','exclude')),
      channel_ids JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(channel_ids) = 'array'),
      revision BIGINT NOT NULL DEFAULT 1,
      updated_by TEXT NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (guild_id, command_name)
    )
  `);
}

function storedPolicy(row?: StoredPolicy | null): CommandAccessPolicy {
  if (!row) return { ...DEFAULT_POLICY };
  return {
    role_mode: row.role_mode,
    role_ids: Array.isArray(row.role_ids) ? row.role_ids.map(String) : [],
    channel_mode: row.channel_mode,
    channel_ids: Array.isArray(row.channel_ids) ? row.channel_ids.map(String) : [],
    revision: Number(row.revision) || 0,
  };
}

export async function getCommandAccessPolicy(guildId: string, commandName: string): Promise<CommandAccessPolicy> {
  const row = await queryOne<StoredPolicy>(
    `SELECT role_mode,role_ids,channel_mode,channel_ids,revision::text
       FROM guild_command_access WHERE guild_id=$1 AND command_name=$2`,
    [guildId, commandName],
  );
  return storedPolicy(row);
}

export async function getCommandAccessPolicies(guildId: string): Promise<Record<string, CommandAccessPolicy>> {
  const rows = await query<(StoredPolicy & { command_name: string })>(
    `SELECT command_name,role_mode,role_ids,channel_mode,channel_ids,revision::text
       FROM guild_command_access WHERE guild_id=$1`,
    [guildId],
  );
  return Object.fromEntries(rows.map(row => {
    const { command_name: commandName, ...policy } = row;
    return [commandName, storedPolicy(policy)];
  }));
}

export async function saveCommandAccessPolicy(
  guildId: string,
  commandName: string,
  actorId: string,
  expectedRevision: number,
  policy: Omit<CommandAccessPolicy, "revision">,
): Promise<CommandAccessPolicy | null> {
  const row = await queryOne<{ revision: string }>(
    `INSERT INTO guild_command_access
       (guild_id,command_name,role_mode,role_ids,channel_mode,channel_ids,updated_by,revision)
     SELECT $1,$2,$3,$4::jsonb,$5,$6::jsonb,$7,1
     WHERE $8=0 OR EXISTS (
       SELECT 1 FROM guild_command_access
        WHERE guild_id=$1 AND command_name=$2
     )
     ON CONFLICT (guild_id,command_name) DO UPDATE SET
       role_mode=EXCLUDED.role_mode, role_ids=EXCLUDED.role_ids,
       channel_mode=EXCLUDED.channel_mode, channel_ids=EXCLUDED.channel_ids,
       updated_by=EXCLUDED.updated_by, updated_at=NOW(),
       revision=guild_command_access.revision+1
     WHERE guild_command_access.revision=$8 AND $8>0
     RETURNING revision::text`,
    [guildId, commandName, policy.role_mode, JSON.stringify(policy.role_ids),
      policy.channel_mode, JSON.stringify(policy.channel_ids), actorId, expectedRevision],
  );
  return row ? { ...policy, revision: Number(row.revision) || 0 } : null;
}

export function commandAccessMatches(
  policy: Omit<CommandAccessPolicy, "revision">,
  channelId: string | null,
  memberRoleIds: readonly string[],
): boolean {
  const roleMatch = policy.role_ids.some(id => memberRoleIds.includes(id));
  const channelMatch = Boolean(channelId && policy.channel_ids.includes(channelId));
  const roleAllowed = policy.role_mode === "everyone"
    || (policy.role_mode === "include" ? policy.role_ids.length > 0 && roleMatch : !roleMatch);
  const channelAllowed = policy.channel_mode === "all"
    || (policy.channel_mode === "include" ? policy.channel_ids.length > 0 && channelMatch : !channelMatch);
  return roleAllowed && channelAllowed;
}

function interactionRoleIds(member: unknown): string[] {
  if (!member || typeof member !== "object") return [];
  const roles = (member as { roles?: unknown }).roles;
  if (Array.isArray(roles)) return roles.map(String);
  if (roles && typeof roles === "object" && "cache" in roles) {
    const cache = (roles as { cache?: { keys?: () => IterableIterator<string> } }).cache;
    return cache?.keys ? Array.from(cache.keys(), String) : [];
  }
  return [];
}

export async function isCommandAccessAllowed(
  guildId: string,
  commandName: string,
  channelId: string | null,
  member: unknown,
): Promise<boolean> {
  const policy = await getCommandAccessPolicy(guildId, commandName);
  return commandAccessMatches(policy, channelId, interactionRoleIds(member));
}

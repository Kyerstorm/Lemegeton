import { PermissionsBitField, type GuildMember } from "discord.js";
import { query, queryOne, transaction } from "../../database.js";
import { cleanText } from "../security/security.js";
import { GLOBAL_MODERATOR_IDS } from "./archive-access.js";
export { isGlobalArchiveModerator } from "./archive-access.js";
import { getArchiveEntry, parseTags, type ArchiveCategory, type ArchiveEntry, type ArchiveVisibility } from "./archive.js";

export async function addArchiveReport(
  guildId: string,
  reporterId: string,
  entryId: string,
  reason: string,
): Promise<void> {
  const entry = await getArchiveEntry(guildId, entryId);
  if (!entry) throw new Error("That approved entry is not visible in this server.");
  await query(
    `INSERT INTO community_archive_reports (archive_type, entry_id, guild_id, reporter_id, reason)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (guild_id, entry_id, reporter_id) DO UPDATE SET
       reason = EXCLUDED.reason, status = 'pending', reviewed_by = NULL, review_reason = NULL,
       created_at = NOW(), reviewed_at = NULL`,
    [entry.archive_type, entryId, guildId, reporterId, cleanText(reason, 500)],
  );
}

export async function canModerateArchive(member: GuildMember, guildId: string, visibility: ArchiveVisibility): Promise<boolean> {
  const canManage = member.permissions.has(PermissionsBitField.Flags.Administrator)
    || member.permissions.has(PermissionsBitField.Flags.ManageGuild)
    || member.permissions.has(PermissionsBitField.Flags.ManageMessages);
  if (visibility === "global") return GLOBAL_MODERATOR_IDS.has(member.id);
  if (canManage) return true;
  const row = await queryOne<{ moderator_role_id: string | null }>(
    "SELECT moderator_role_id FROM guild_archive_settings WHERE guild_id = $1",
    [guildId],
  ).catch(() => null);
  return Boolean(row?.moderator_role_id && member.roles.cache.has(row.moderator_role_id));
}

export async function listPendingEntries(guildId: string, visibility: ArchiveVisibility): Promise<ArchiveEntry[]> {
  const rows = visibility === "global"
    ? await query<ArchiveEntry>(
        "SELECT * FROM community_archive_entries WHERE visibility = 'global' AND status IN ('pending','pending_upload') ORDER BY created_at ASC LIMIT 20",
      )
    : await query<ArchiveEntry>(
        "SELECT * FROM community_archive_entries WHERE visibility = 'server' AND created_guild_id = $1 AND status IN ('pending','pending_upload') ORDER BY created_at ASC LIMIT 20",
        [guildId],
      );
  return rows.map((entry) => ({ ...entry, tags: parseTags(String((entry as unknown as { tags: string }).tags ?? "[]")) }));
}

export function canModerateArchiveStatus(status: string, action: "approve" | "reject" | "remove"): boolean {
  if (status === "pending" || status === "pending_upload") return true;
  return status === "approved" && action === "remove";
}

export async function moderateArchiveEntry(
  guildId: string,
  moderatorId: string,
  entryId: string,
  action: "approve" | "reject" | "remove",
  reason: string,
  global = false,
): Promise<void> {
  if (global && !GLOBAL_MODERATOR_IDS.has(moderatorId)) {
    throw new Error("Only configured global Archive moderators can review global entries.");
  }
  const cleanReason = cleanText(reason, 500);
  await transaction(async (client) => {
    const scope = global
      ? "id = $1 AND visibility = 'global'"
      : "id = $1 AND visibility = 'server' AND created_guild_id = $2";
    const selected = await client.query<{
      id: string;
      created_guild_id: string;
      visibility: ArchiveVisibility;
      status: string;
      archive_type: ArchiveCategory;
      source_url: string | null;
    }>(
      "SELECT id, created_guild_id, visibility, status, archive_type, source_url FROM community_archive_entries WHERE " + scope + " FOR UPDATE",
      global ? [entryId] : [entryId, guildId],
    );
    const row = selected.rows[0];
    if (!row) throw new Error("That entry was not found in this moderation scope.");
    if (!canModerateArchiveStatus(row.status, action)) {
      throw new Error("That contribution has already been reviewed.");
    }
    if (row.status === "pending_upload" && action === "approve") {
      const count = await client.query<{ count: string }>(
        "SELECT COUNT(*) AS count FROM community_archive_entry_assets WHERE entry_id = $1",
        [entryId],
      );
      const hasAsset = Number(count.rows[0]?.count ?? 0) > 0;
      const hasSource = row.archive_type === "soundtracks" && Boolean(row.source_url);
      if (!hasAsset && !hasSource) {
        throw new Error("This soundtrack submission still needs an accepted private upload or HTTPS music source before approval.");
      }
    }
    const newStatus = action === "approve" ? "approved" : action === "reject" ? "rejected" : "removed";
    const updateScope = global
      ? "id = $3 AND visibility = 'global' AND status = $4"
      : "id = $3 AND visibility = 'server' AND created_guild_id = $4 AND status = $5";
    const updated = await client.query(
      "UPDATE community_archive_entries SET status = $1, moderation_reason = $2, updated_at = NOW() WHERE " + updateScope,
      global
        ? [newStatus, cleanReason, entryId, row.status]
        : [newStatus, cleanReason, entryId, guildId, row.status],
    );
    if (updated.rowCount !== 1) throw new Error("That contribution changed before moderation could be saved. Refresh the queue and try again.");
    await client.query(
      "INSERT INTO community_archive_moderation_log (entry_id, guild_id, moderator_id, action, reason, is_global) VALUES ($1, $2, $3, $4, $5, $6)",
      [entryId, row.created_guild_id, moderatorId, action, cleanReason, global],
    );
  });
}

export interface ArchiveReport {
  id: string;
  entry_id: string;
  title: string;
  archive_type: ArchiveCategory;
  reporter_id: string;
  reason: string;
  created_at: Date;
  visibility: ArchiveVisibility;
}

export async function listArchiveReports(guildId: string, global = false): Promise<ArchiveReport[]> {
  return global
    ? query<ArchiveReport>(
        `SELECT r.id, r.entry_id, e.title, r.archive_type, r.reporter_id, r.reason, r.created_at, e.visibility
         FROM community_archive_reports r
         JOIN community_archive_entries e ON e.id = r.entry_id
         WHERE e.visibility = 'global' AND r.status = 'pending'
         ORDER BY r.created_at ASC LIMIT 20`,
      )
    : query<ArchiveReport>(
        `SELECT r.id, r.entry_id, e.title, r.archive_type, r.reporter_id, r.reason, r.created_at, e.visibility
         FROM community_archive_reports r
         JOIN community_archive_entries e ON e.id = r.entry_id
         WHERE r.guild_id = $1 AND e.visibility = 'server' AND e.created_guild_id = $1 AND r.status = 'pending'
         ORDER BY r.created_at ASC LIMIT 20`,
        [guildId],
      );
}

export async function reviewArchiveReport(
  guildId: string,
  reportId: string,
  moderatorId: string,
  decision: "dismiss" | "remove",
  reason: string,
  global = false,
): Promise<void> {
  if (global && !GLOBAL_MODERATOR_IDS.has(moderatorId)) {
    throw new Error("Only configured global Archive moderators can review global reports.");
  }
  const scope = global
    ? "e.visibility = 'global'"
    : "r.guild_id = $2 AND e.visibility = 'server' AND e.created_guild_id = $2";
  const report = await queryOne<{
    entry_id: string;
    visibility: ArchiveVisibility;
    created_guild_id: string;
    entry_status: string;
  }>(
    "SELECT r.entry_id, e.visibility, e.created_guild_id, e.status AS entry_status " +
    "FROM community_archive_reports r JOIN community_archive_entries e ON e.id = r.entry_id " +
    "WHERE r.id = $1 AND " + scope + " AND r.status = 'pending'",
    global ? [reportId] : [reportId, guildId],
  );
  if (!report) throw new Error("That pending Archive report was not found in this moderation scope.");
  if (decision === "remove" && report.entry_status !== "removed") {
    await moderateArchiveEntry(guildId, moderatorId, report.entry_id, "remove", reason, global);
  }
  await query(
    "UPDATE community_archive_reports SET status = $1, reviewed_by = $2, review_reason = $3, reviewed_at = NOW() WHERE id = $4 AND status = 'pending'",
    [decision === "dismiss" ? "dismissed" : "actioned", moderatorId, cleanText(reason, 500), reportId],
  );
}

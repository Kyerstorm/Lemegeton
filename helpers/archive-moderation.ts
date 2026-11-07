import { PermissionsBitField, type GuildMember } from "discord.js";
import { query, queryOne } from "../database.js";
import { cleanText } from "./security.js";
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
  const row = await queryOne<{ panel_mod_role_id: string | null }>(
    "SELECT panel_mod_role_id FROM guild_settings WHERE guild_id = $1",
    [guildId],
  ).catch(() => null);
  return Boolean(row?.panel_mod_role_id && member.roles.cache.has(row.panel_mod_role_id));
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

export async function moderateArchiveEntry(
  guildId: string,
  moderatorId: string,
  entryId: string,
  action: "approve" | "reject" | "remove",
  reason: string,
  global = false,
): Promise<void> {
  const row = await queryOne<{
    id: string;
    created_guild_id: string;
    visibility: ArchiveVisibility;
    status: string;
    archive_type: ArchiveCategory;
    source_url: string | null;
  }>(
    `SELECT id, created_guild_id, visibility, status, archive_type, source_url FROM community_archive_entries
     WHERE id = $1 AND ${global ? "visibility = 'global'" : "visibility = 'server' AND created_guild_id = $2"}`,
    global ? [entryId] : [entryId, guildId],
  );
  if (!row) throw new Error("That pending entry was not found in this moderation scope.");
  if (row.status !== "pending" && row.status !== "pending_upload") {
    throw new Error("That contribution has already been reviewed.");
  }
  if (row.status === "pending_upload" && action === "approve") {
    const count = await queryOne<{ count: string }>(
      "SELECT COUNT(*) AS count FROM community_archive_entry_assets WHERE entry_id = $1",
      [entryId],
    );
    const hasAsset = Number(count?.count ?? 0) > 0;
    const hasSource = row.archive_type === "soundtracks" && Boolean(row.source_url);
    if (!hasAsset && !hasSource) {
      throw new Error("This soundtrack submission still needs an accepted private upload or HTTPS music source before approval.");
    }
  }
  const newStatus = action === "approve" ? "approved" : action === "reject" ? "rejected" : "removed";
  await query(
    `UPDATE community_archive_entries SET status = $1, moderation_reason = $2, updated_at = NOW()
     WHERE id = $3 AND ${global ? "visibility = 'global'" : "visibility = 'server' AND created_guild_id = $4"}`,
    global ? [newStatus, cleanText(reason, 500), entryId] : [newStatus, cleanText(reason, 500), entryId, guildId],
  );
  await query(
    `INSERT INTO community_archive_moderation_log
     (entry_id, guild_id, moderator_id, action, reason, is_global)
     VALUES ($1, $2, $3, $4, $5, $6)`,
    [entryId, row.created_guild_id, moderatorId, action, cleanText(reason, 500), global],
  );
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
  const report = await queryOne<{ entry_id: string; visibility: ArchiveVisibility; created_guild_id: string }>(
    `SELECT r.entry_id, e.visibility, e.created_guild_id
     FROM community_archive_reports r
     JOIN community_archive_entries e ON e.id = r.entry_id
     WHERE r.id = $1 AND ${global ? "e.visibility = 'global'" : "r.guild_id = $2 AND e.visibility = 'server' AND e.created_guild_id = $2"}
       AND r.status = 'pending'`,
    global ? [reportId] : [reportId, guildId],
  );
  if (!report) throw new Error("That pending Archive report was not found in this moderation scope.");
  await query(
    `UPDATE community_archive_reports
     SET status = $1, reviewed_by = $2, review_reason = $3, reviewed_at = NOW()
     WHERE id = $4 AND status = 'pending'`,
    [decision === "dismiss" ? "dismissed" : "actioned", moderatorId, cleanText(reason, 500), reportId],
  );
  if (decision === "remove") {
    await moderateArchiveEntry(
      guildId,
      moderatorId,
      report.entry_id,
      "remove",
      reason,
      global,
    );
  }
}

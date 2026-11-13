import { query, queryOne } from "../../database.js";
import { cleanText } from "../security/security.js";
import { getArchiveEntry, type ArchiveCategory, type ArchiveVisibility } from "./archive.js";

export interface ArchiveSpotlight {
  id: string;
  visibility: ArchiveVisibility;
  entry_id: string;
  curator_id: string;
  note: string;
  starts_at: Date;
  ends_at: Date;
  title: string;
  archive_type: ArchiveCategory;
  media_type: string;
  source_url: string | null;
  created_by: string;
}

export function validateSpotlightWindow(startsAt: Date, endsAt: Date, now = new Date()): void {
  if (!Number.isFinite(startsAt.getTime()) || !Number.isFinite(endsAt.getTime())) {
    throw new Error("Spotlight start and end must be valid dates.");
  }
  if (startsAt.getTime() < now.getTime() - 60_000) {
    throw new Error("A spotlight cannot start in the past.");
  }
  const duration = endsAt.getTime() - startsAt.getTime();
  if (duration <= 0 || duration > 30 * 24 * 60 * 60 * 1000) {
    throw new Error("A spotlight must last between one minute and 30 days.");
  }
}

export async function createArchiveSpotlight(input: {
  guildId: string;
  curatorId: string;
  entryId: string;
  visibility: ArchiveVisibility;
  note?: string;
  startsAt: Date;
  endsAt: Date;
}): Promise<string> {
  validateSpotlightWindow(input.startsAt, input.endsAt);
  const global = input.visibility === "global";
  const entry = await getArchiveEntry(input.guildId, input.entryId, false, global);
  if (!entry || entry.status !== "approved") {
    throw new Error("Only an approved Archive entry in the selected visibility scope can be featured.");
  }
  if (global && entry.visibility !== "global") {
    throw new Error("A global spotlight can only feature a global Archive entry.");
  }
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_archive_spotlights
       (guild_id, visibility, entry_id, curator_id, note, starts_at, ends_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7)
     RETURNING id::text AS id`,
    [global ? null : input.guildId, input.visibility, input.entryId, input.curatorId,
      cleanText(input.note ?? "", 500), input.startsAt, input.endsAt],
  );
  if (!row) throw new Error("The Archive spotlight could not be created.");
  return row.id;
}

export async function listArchiveSpotlights(guildId: string, now = new Date(), limit = 10): Promise<ArchiveSpotlight[]> {
  return query<ArchiveSpotlight>(
    `SELECT s.id::text, s.visibility, s.entry_id::text, s.curator_id::text, s.note,
            s.starts_at, s.ends_at, e.title, e.archive_type, e.media_type,
            e.source_url, e.created_by::text
       FROM community_archive_spotlights s
       JOIN community_archive_entries e ON e.id = s.entry_id
      WHERE s.status = 'published'
        AND s.starts_at <= $2 AND s.ends_at > $2
        AND (s.visibility = 'global' OR (s.visibility = 'server' AND s.guild_id = $1))
        AND e.status = 'approved'
        AND ((s.visibility = 'global' AND e.visibility = 'global')
          OR (s.visibility = 'server' AND (
            e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)
          )))
      ORDER BY s.starts_at DESC, s.created_at DESC
      LIMIT $3`,
    [guildId, now, Math.max(1, Math.min(20, Math.floor(limit)))],
  );
}

export async function cancelArchiveSpotlight(
  guildId: string,
  spotlightId: string,
  actorId: string,
  canModerateServer: boolean,
  isGlobalModerator: boolean,
): Promise<void> {
  const changed = await queryOne<{ id: string }>(
    `UPDATE community_archive_spotlights
        SET status = 'cancelled'
      WHERE id = $1 AND status = 'published'
        AND ((visibility = 'server' AND guild_id = $2 AND (curator_id = $3 OR $4 = TRUE))
          OR (visibility = 'global' AND $5 = TRUE))
      RETURNING id::text AS id`,
    [spotlightId, guildId, actorId, canModerateServer, isGlobalModerator],
  );
  if (!changed) throw new Error("That spotlight was not found in your moderation scope or is already cancelled.");
}

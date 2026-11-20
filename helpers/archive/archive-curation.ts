import { query, queryOne } from "../../database.js";
import { cleanText } from "../security/security.js";
import { isGlobalArchiveModerator } from "./archive-access.js";
import { ARCHIVE_CATEGORIES, getArchiveEntry, type ArchiveCategory, type ArchiveVisibility } from "./archive.js";

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


export interface ArchiveCategoryIndexItem {
  category: ArchiveCategory;
  entry_count: number;
}

export interface ArchiveCollectionSpotlight {
  id: string;
  collection_id: string;
  visibility: ArchiveVisibility;
  curator_id: string;
  note: string;
  starts_at: Date;
  ends_at: Date;
  title: string;
  description: string;
  owner_id: string;
  entry_count: number;
}

export function completeArchiveCategoryIndex(
  rows: readonly { archive_type: string; entry_count: number }[],
): ArchiveCategoryIndexItem[] {
  const counts = new Map(rows.map((row) => [row.archive_type, Math.max(0, Math.trunc(row.entry_count))]));
  return ARCHIVE_CATEGORIES.map((category) => ({
    category: category.value,
    entry_count: counts.get(category.value) ?? 0,
  }));
}

export async function listArchiveCategoryIndex(guildId: string): Promise<ArchiveCategoryIndexItem[]> {
  const rows = await query<{ archive_type: string; entry_count: number }>(
    "SELECT archive_type, COUNT(*)::INT AS entry_count FROM community_archive_entries " +
    "WHERE status = 'approved' AND (visibility = 'global' OR (visibility = 'server' AND created_guild_id = $1)) " +
    "GROUP BY archive_type",
    [guildId],
  );
  return completeArchiveCategoryIndex(rows);
}

export function canFeatureArchiveCollection(
  collectionVisibility: ArchiveVisibility,
  ownerId: string,
  curatorId: string,
  visibility: ArchiveVisibility,
  canModerateServer: boolean,
  isGlobalModerator: boolean,
): boolean {
  if (visibility === "global") return isGlobalModerator && collectionVisibility === "global";
  return ownerId === curatorId || canModerateServer;
}

export async function createArchiveCollectionSpotlight(input: {
  guildId: string;
  curatorId: string;
  collectionId: string;
  visibility: ArchiveVisibility;
  startsAt: Date;
  endsAt: Date;
  note?: string;
  canModerateServer: boolean;
}): Promise<string> {
  validateSpotlightWindow(input.startsAt, input.endsAt);
  const globalModerator = isGlobalArchiveModerator(input.curatorId);
  if (input.visibility === "global" && !globalModerator) {
    throw new Error("Only configured global Archive moderators can feature a collection globally.");
  }
  const collection = await queryOne<{ guild_id: string; owner_id: string; visibility: ArchiveVisibility }>(
    "SELECT guild_id::text, owner_id::text, visibility FROM archive_collections " +
    "WHERE id = $1 AND status = 'active' AND (visibility = 'global' OR guild_id = $2)",
    [input.collectionId, input.guildId],
  );
  if (!collection) throw new Error("That active collection is not visible in this server.");
  if (!canFeatureArchiveCollection(
    collection.visibility,
    collection.owner_id,
    input.curatorId,
    input.visibility,
    input.canModerateServer,
    globalModerator,
  )) {
    throw new Error(input.visibility === "global"
      ? "Only configured global Archive moderators can feature a global collection."
      : "Only the collection owner or an Archive moderator can feature this collection.");
  }
  const row = await queryOne<{ id: string }>(
    "INSERT INTO community_archive_collection_spotlights " +
    "(guild_id, visibility, collection_id, curator_id, note, starts_at, ends_at) " +
    "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id",
    [input.visibility === "global" ? null : input.guildId, input.visibility, input.collectionId,
      input.curatorId, cleanText(input.note ?? "", 500), input.startsAt, input.endsAt],
  );
  if (!row) throw new Error("The collection feature could not be scheduled.");
  return row.id;
}

export async function listArchiveCollectionSpotlights(
  guildId: string,
  now = new Date(),
  limit = 10,
): Promise<ArchiveCollectionSpotlight[]> {
  return query<ArchiveCollectionSpotlight>(
    "SELECT s.id::text, s.collection_id::text, s.visibility, s.curator_id::text, s.note, " +
    "s.starts_at, s.ends_at, c.title, c.description, c.owner_id::text, COUNT(DISTINCT e.id)::INT AS entry_count " +
    "FROM community_archive_collection_spotlights s " +
    "JOIN archive_collections c ON c.id = s.collection_id " +
    "LEFT JOIN archive_collection_items ci ON ci.collection_id = c.id " +
    "LEFT JOIN community_archive_entries e ON e.id = ci.entry_id AND e.status = 'approved' " +
    "AND ((c.visibility = 'global' AND e.visibility = 'global') OR " +
    "(c.visibility = 'server' AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)))) " +
    "WHERE s.status = 'published' AND s.starts_at <= $2 AND s.ends_at > $2 " +
    "AND (s.visibility = 'global' OR (s.visibility = 'server' AND s.guild_id = $1)) " +
    "AND ((s.visibility = 'global' AND c.visibility = 'global') OR " +
    "(s.visibility = 'server' AND (c.visibility = 'global' OR (c.visibility = 'server' AND c.guild_id = $1)))) " +
    "GROUP BY s.id, c.id HAVING COUNT(DISTINCT e.id) > 0 ORDER BY s.starts_at DESC, s.created_at DESC LIMIT $3",
    [guildId, now, Math.max(1, Math.min(20, Math.floor(limit)))],
  );
}

export async function cancelArchiveCollectionSpotlight(
  guildId: string,
  spotlightId: string,
  actorId: string,
  canModerateServer: boolean,
): Promise<void> {
  const globalModerator = isGlobalArchiveModerator(actorId);
  const changed = await queryOne<{ id: string }>(
    "UPDATE community_archive_collection_spotlights SET status = 'cancelled' " +
    "WHERE id = $1 AND status = 'published' " +
    "AND ((visibility = 'server' AND guild_id = $2 AND (curator_id = $3 OR $4 = TRUE)) " +
    "OR (visibility = 'global' AND $5 = TRUE)) RETURNING id::text AS id",
    [spotlightId, guildId, actorId, canModerateServer, globalModerator],
  );
  if (!changed) throw new Error("That featured collection was not found in your moderation scope or is already cancelled.");
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
  if (global && !isGlobalArchiveModerator(input.curatorId)) {
    throw new Error("Only configured global Archive moderators can feature a global Archive entry.");
  }
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
): Promise<void> {
  const globalModerator = isGlobalArchiveModerator(actorId);
  const changed = await queryOne<{ id: string }>(
    `UPDATE community_archive_spotlights
        SET status = 'cancelled'
      WHERE id = $1 AND status = 'published'
        AND ((visibility = 'server' AND guild_id = $2 AND (curator_id = $3 OR $4 = TRUE))
          OR (visibility = 'global' AND $5 = TRUE))
      RETURNING id::text AS id`,
    [spotlightId, guildId, actorId, canModerateServer, globalModerator],
  );
  if (!changed) throw new Error("That spotlight was not found in your moderation scope or is already cancelled.");
}

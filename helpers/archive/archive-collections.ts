import { query, queryOne } from "../../database.js";
import { cleanText } from "../security/security.js";
import { getArchiveEntry, parseTags, type ArchiveEntry, type ArchiveVisibility } from "./archive.js";

export async function saveArchiveCollection(
  guildId: string,
  ownerId: string,
  title: string,
  description: string,
  visibility: ArchiveVisibility,
): Promise<string> {
  const cleanTitle = cleanText(title, 160);
  if (!cleanTitle) throw new Error("A collection title is required.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO archive_collections (guild_id, owner_id, title, description, visibility)
     VALUES ($1, $2, $3, $4, $5) RETURNING id`,
    [guildId, ownerId, cleanTitle, cleanText(description, 1_000), visibility],
  );
  if (!row) throw new Error("The collection could not be created.");
  return row.id;
}

export async function addEntryToCollection(
  guildId: string,
  userId: string,
  collectionId: string,
  entryId: string,
  note: string,
): Promise<void> {
  const collection = await queryOne<{ owner_id: string; visibility: ArchiveVisibility }>(
    "SELECT owner_id, visibility FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active'",
    [collectionId, guildId],
  );
  if (!collection) throw new Error("That collection was not found in this server.");
  const permitted = collection.owner_id === userId || await queryOne(
    "SELECT 1 FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2 AND role IN ('editor','contributor')",
    [collectionId, userId],
  );
  if (!permitted) throw new Error("You do not have permission to edit this collection.");
  const entry = await getArchiveEntry(guildId, entryId);
  if (!entry) throw new Error("That entry is not visible in this server.");
  if (collection.visibility === "global" && entry.visibility !== "global") {
    throw new Error("A global collection cannot include a server-only entry.");
  }
  await query(
    `INSERT INTO archive_collection_items (collection_id, entry_id, added_by, note, position)
     VALUES ($1, $2, $3, $4, (SELECT COALESCE(MAX(position), 0) + 1 FROM archive_collection_items WHERE collection_id = $1))
     ON CONFLICT (collection_id, entry_id) DO UPDATE SET note = EXCLUDED.note`,
    [collectionId, entryId, userId, cleanText(note, 500)],
  );
}

export async function listArchiveCollections(guildId: string, ownerId?: string): Promise<Array<{ id: string; title: string; description: string; visibility: ArchiveVisibility; owner_id: string; entry_count: number }>> {
  const rows = await query<{
    id: string; title: string; description: string; visibility: ArchiveVisibility; owner_id: string; entry_count: number;
  }>(
    `SELECT c.id, c.title, c.description, c.visibility, c.owner_id,
       COUNT(e.id)::INT AS entry_count
     FROM archive_collections c
     LEFT JOIN archive_collection_items ci ON ci.collection_id = c.id
     LEFT JOIN community_archive_entries e ON e.id = ci.entry_id
       AND e.status = 'approved'
       AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1))
     WHERE c.status = 'active'
       AND (c.visibility = 'global' OR c.guild_id = $1)
       AND ($2::BIGINT IS NULL OR c.owner_id = $2)
     GROUP BY c.id
     ORDER BY c.updated_at DESC LIMIT 15`,
    [guildId, ownerId ?? null],
  );
  return rows;
}

export async function getCollectionItems(guildId: string, collectionId: string): Promise<ArchiveEntry[]> {
  const rows = await query<ArchiveEntry>(
    `SELECT e.* FROM archive_collection_items ci
     JOIN archive_collections c ON c.id = ci.collection_id
     JOIN community_archive_entries e ON e.id = ci.entry_id
     WHERE ci.collection_id = $1 AND c.status = 'active'
       AND (c.visibility = 'global' OR c.guild_id = $2)
       AND e.status = 'approved'
       AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $2))
     ORDER BY ci.position ASC LIMIT 25`,
    [collectionId, guildId],
  );
  return rows.map((entry) => ({ ...entry, tags: parseTags(String((entry as unknown as { tags: string }).tags ?? "[]")) }));
}

export async function saveArchiveTrail(
  guildId: string,
  ownerId: string,
  title: string,
  introduction: string,
  visibility: ArchiveVisibility,
): Promise<string> {
  const row = await queryOne<{ id: string }>(
    `INSERT INTO archive_trails (guild_id, owner_id, title, introduction, visibility)
     VALUES ($1, $2, $3, $4, $5) RETURNING id`,
    [guildId, ownerId, cleanText(title, 160), cleanText(introduction, 1_000), visibility],
  );
  if (!row) throw new Error("The Archive Trail could not be created.");
  return row.id;
}

export async function addEntryToTrail(
  guildId: string,
  userId: string,
  trailId: string,
  entryId: string,
  explanation: string,
): Promise<void> {
  const trail = await queryOne<{ owner_id: string; visibility: ArchiveVisibility }>(
    "SELECT owner_id, visibility FROM archive_trails WHERE id = $1 AND guild_id = $2 AND status = 'active'",
    [trailId, guildId],
  );
  if (!trail || trail.owner_id !== userId) throw new Error("Only the Archive Trail owner can add or reorder steps.");
  const entry = await getArchiveEntry(guildId, entryId);
  if (!entry) throw new Error("That entry is not visible in this server.");
  if (trail.visibility === "global" && entry.visibility !== "global") {
    throw new Error("A global trail cannot include a server-only entry.");
  }
  const position = await queryOne<{ next: number }>(
    "SELECT COALESCE(MAX(step_number), 0) + 1 AS next FROM archive_trail_steps WHERE trail_id = $1",
    [trailId],
  );
  await query(
    `INSERT INTO archive_trail_steps (trail_id, step_number, entry_id, explanation, added_by)
     VALUES ($1, $2, $3, $4, $5)
     ON CONFLICT (trail_id, entry_id) DO NOTHING`,
    [trailId, position?.next ?? 1, entryId, cleanText(explanation, 500), userId],
  );
}

export async function listArchiveTrails(guildId: string): Promise<Array<{ id: string; title: string; introduction: string; owner_id: string; step_count: number }>> {
  return query(
    `SELECT t.id, t.title, t.introduction, t.owner_id, COUNT(e.id)::INT AS step_count
     FROM archive_trails t
     LEFT JOIN archive_trail_steps s ON s.trail_id = t.id
     LEFT JOIN community_archive_entries e ON e.id = s.entry_id
       AND e.status = 'approved'
       AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1))
     WHERE t.status = 'active' AND (t.visibility = 'global' OR t.guild_id = $1)
     GROUP BY t.id ORDER BY t.updated_at DESC LIMIT 15`,
    [guildId],
  );
}

export async function addCollectionCollaborator(
  guildId: string,
  ownerId: string,
  collectionId: string,
  userId: string,
  role: "editor" | "contributor",
): Promise<void> {
  const collection = await queryOne<{ owner_id: string }>(
    "SELECT owner_id FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active' AND visibility = 'server'",
    [collectionId, guildId],
  );
  if (!collection || collection.owner_id !== ownerId) throw new Error("Only the owner of a server collection can invite collaborators.");
  await query(
    `INSERT INTO archive_collection_collaborators (collection_id, user_id, role, invited_by)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (collection_id, user_id) DO UPDATE SET role = EXCLUDED.role, invited_by = EXCLUDED.invited_by`,
    [collectionId, userId, role, ownerId],
  );
}

export async function removeCollectionCollaborator(
  guildId: string,
  ownerId: string,
  collectionId: string,
  userId: string,
): Promise<void> {
  const collection = await queryOne<{ owner_id: string }>(
    "SELECT owner_id FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active'",
    [collectionId, guildId],
  );
  if (!collection || collection.owner_id !== ownerId) throw new Error("Only the collection owner can remove collaborators.");
  await query(
    "DELETE FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2",
    [collectionId, userId],
  );
}

export async function removeEntryFromCollection(
  guildId: string,
  userId: string,
  collectionId: string,
  entryId: string,
): Promise<void> {
  const collection = await queryOne<{ owner_id: string }>(
    "SELECT owner_id FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active'",
    [collectionId, guildId],
  );
  if (!collection) throw new Error("That collection was not found in this server.");
  const permitted = collection.owner_id === userId || await queryOne(
    "SELECT 1 FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2 AND role = 'editor'",
    [collectionId, userId],
  );
  if (!permitted) throw new Error("Only the collection owner or an editor can remove items.");
  await query(
    "DELETE FROM archive_collection_items WHERE collection_id = $1 AND entry_id = $2",
    [collectionId, entryId],
  );
}

export async function getArchiveTrailSteps(guildId: string, trailId: string): Promise<Array<{
  step_number: number;
  explanation: string;
  entry: ArchiveEntry;
}>> {
  const rows = await query<ArchiveEntry & { step_number: number; explanation: string }>(
    `SELECT e.*, s.step_number, s.explanation
     FROM archive_trails t
     JOIN archive_trail_steps s ON s.trail_id = t.id
     JOIN community_archive_entries e ON e.id = s.entry_id
     WHERE t.id = $1 AND t.status = 'active'
       AND (t.visibility = 'global' OR t.guild_id = $2)
       AND e.status = 'approved'
       AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $2))
     ORDER BY s.step_number ASC LIMIT 25`,
    [trailId, guildId],
  );
  return rows.map((row) => ({
    step_number: row.step_number,
    explanation: row.explanation,
    entry: { ...row, tags: parseTags(String((row as unknown as { tags: string }).tags ?? "[]")) },
  }));
}

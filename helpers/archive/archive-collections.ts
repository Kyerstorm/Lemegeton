import { query, queryOne, transaction } from "../../database.js";
import { cleanText } from "../security/security.js";
import { getArchiveEntry, parseTags, type ArchiveEntry, type ArchiveVisibility } from "./archive.js";

export function moveArchiveItem(items: readonly string[], entryId: string, position: number): string[] {
  if (!Number.isInteger(position) || position < 1) throw new Error("Choose a one-based position of at least 1.");
  const currentIndex = items.indexOf(entryId);
  if (currentIndex < 0) throw new Error("That entry is not part of this collection or Trail.");
  const next = [...items];
  const [entry] = next.splice(currentIndex, 1);
  next.splice(Math.min(position - 1, next.length), 0, entry!);
  return next;
}

export function reorderVisibleArchiveItems(
  items: readonly { entry_id: string; visible: boolean }[],
  entryId: string,
  position: number,
): string[] {
  const visible = items.filter((item) => item.visible).map((item) => item.entry_id);
  const hidden = items.filter((item) => !item.visible).map((item) => item.entry_id);
  return [...moveArchiveItem(visible, entryId, position), ...hidden];
}

export async function reorderCollectionEntry(
  guildId: string,
  userId: string,
  collectionId: string,
  entryId: string,
  position: number,
): Promise<void> {
  await transaction(async (client) => {
    const selected = await client.query<{ owner_id: string; visibility: ArchiveVisibility }>(
      "SELECT owner_id::text, visibility FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active' FOR UPDATE",
      [collectionId, guildId],
    );
    const collection = selected.rows[0];
    if (!collection) throw new Error("That collection was not found in this server.");
    if (collection.owner_id !== userId) {
      const editor = await client.query(
        "SELECT 1 FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2 AND role = 'editor'",
        [collectionId, userId],
      );
      if (!editor.rowCount) throw new Error("Only the collection owner or an editor can reorder entries.");
    }
    const rows = await client.query<{ entry_id: string; visible: boolean }>(
      "SELECT ci.entry_id::text AS entry_id, " +
      "(e.status = 'approved' AND (e.visibility = 'global' OR " +
      "(e.visibility = 'server' AND e.created_guild_id = $2)) AND " +
      "($3 <> 'global' OR e.visibility = 'global')) AS visible " +
      "FROM archive_collection_items ci JOIN community_archive_entries e ON e.id = ci.entry_id " +
      "WHERE ci.collection_id = $1 ORDER BY ci.position ASC, ci.created_at ASC FOR UPDATE OF ci",
      [collectionId, guildId, collection.visibility],
    );
    const ordered = reorderVisibleArchiveItems(rows.rows, entryId, position);
    for (const [index, orderedId] of ordered.entries()) {
      await client.query(
        "UPDATE archive_collection_items SET position = $1 WHERE collection_id = $2 AND entry_id = $3",
        [index + 1, collectionId, orderedId],
      );
    }
    await client.query("UPDATE archive_collections SET updated_at = NOW() WHERE id = $1 AND guild_id = $2", [collectionId, guildId]);
  });
}

export async function reorderArchiveTrailStep(
  guildId: string,
  userId: string,
  trailId: string,
  entryId: string,
  position: number,
): Promise<void> {
  await transaction(async (client) => {
    const selected = await client.query<{ owner_id: string; visibility: ArchiveVisibility }>(
      "SELECT owner_id::text, visibility FROM archive_trails WHERE id = $1 AND guild_id = $2 AND status = 'active' FOR UPDATE",
      [trailId, guildId],
    );
    const trail = selected.rows[0];
    if (!trail || trail.owner_id !== userId) throw new Error("Only the Archive Trail owner can reorder its steps.");
    const rows = await client.query<{ entry_id: string; visible: boolean }>(
      "SELECT s.entry_id::text AS entry_id, " +
      "(e.status = 'approved' AND (e.visibility = 'global' OR " +
      "(e.visibility = 'server' AND e.created_guild_id = $2)) AND " +
      "($3 <> 'global' OR e.visibility = 'global')) AS visible " +
      "FROM archive_trail_steps s JOIN community_archive_entries e ON e.id = s.entry_id " +
      "WHERE s.trail_id = $1 ORDER BY s.step_number ASC FOR UPDATE OF s",
      [trailId, guildId, trail.visibility],
    );
    const ordered = reorderVisibleArchiveItems(rows.rows, entryId, position);
    await client.query("UPDATE archive_trail_steps SET step_number = -step_number - 1000000 WHERE trail_id = $1", [trailId]);
    for (const [index, orderedId] of ordered.entries()) {
      await client.query(
        "UPDATE archive_trail_steps SET step_number = $1 WHERE trail_id = $2 AND entry_id = $3",
        [index + 1, trailId, orderedId],
      );
    }
    await client.query("UPDATE archive_trails SET updated_at = NOW() WHERE id = $1 AND guild_id = $2", [trailId, guildId]);
  });
}

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
  await transaction(async (client) => {
    const selected = await client.query<{ owner_id: string; visibility: ArchiveVisibility }>(
      "SELECT owner_id::text, visibility FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active' FOR UPDATE",
      [collectionId, guildId],
    );
    const collection = selected.rows[0];
    if (!collection) throw new Error("That collection was not found in this server.");
    if (collection.owner_id !== userId) {
      const collaborator = await client.query(
        "SELECT 1 FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2 AND role IN ('editor','contributor')",
        [collectionId, userId],
      );
      if (!collaborator.rowCount) throw new Error("You do not have permission to edit this collection.");
    }
    const selectedEntry = await client.query<{ status: string; visibility: ArchiveVisibility; created_guild_id: string }>(
      "SELECT status, visibility, created_guild_id::text FROM community_archive_entries WHERE id = $1 FOR SHARE",
      [entryId],
    );
    const entry = selectedEntry.rows[0];
    if (!entry || entry.status !== "approved"
      || !(entry.visibility === "global" || (entry.visibility === "server" && entry.created_guild_id === guildId))) {
      throw new Error("That entry is not visible in this server.");
    }
    if (collection.visibility === "global" && entry.visibility !== "global") {
      throw new Error("A global collection cannot include a server-only entry.");
    }
    await client.query(
      `INSERT INTO archive_collection_items (collection_id, entry_id, added_by, note, position)
       VALUES ($1, $2, $3, $4, (SELECT COALESCE(MAX(position), 0) + 1 FROM archive_collection_items WHERE collection_id = $1))
       ON CONFLICT (collection_id, entry_id) DO UPDATE SET note = EXCLUDED.note`,
      [collectionId, entryId, userId, cleanText(note, 500)],
    );
    await client.query("UPDATE archive_collections SET updated_at = NOW() WHERE id = $1", [collectionId]);
  });
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
  await transaction(async (client) => {
    const selected = await client.query<{ owner_id: string; visibility: ArchiveVisibility }>(
      "SELECT owner_id::text, visibility FROM archive_trails WHERE id = $1 AND guild_id = $2 AND status = 'active' FOR UPDATE",
      [trailId, guildId],
    );
    const trail = selected.rows[0];
    if (!trail || trail.owner_id !== userId) throw new Error("Only the Archive Trail owner can add or reorder steps.");
    const selectedEntry = await client.query<{ status: string; visibility: ArchiveVisibility; created_guild_id: string }>(
      "SELECT status, visibility, created_guild_id::text FROM community_archive_entries WHERE id = $1 FOR SHARE",
      [entryId],
    );
    const entry = selectedEntry.rows[0];
    if (!entry || entry.status !== "approved"
      || !(entry.visibility === "global" || (entry.visibility === "server" && entry.created_guild_id === guildId))) {
      throw new Error("That entry is not visible in this server.");
    }
    if (trail.visibility === "global" && entry.visibility !== "global") {
      throw new Error("A global trail cannot include a server-only entry.");
    }
    const position = await client.query<{ next: number }>(
      "SELECT COALESCE(MAX(step_number), 0) + 1 AS next FROM archive_trail_steps WHERE trail_id = $1",
      [trailId],
    );
    await client.query(
      `INSERT INTO archive_trail_steps (trail_id, step_number, entry_id, explanation, added_by)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (trail_id, entry_id) DO NOTHING`,
      [trailId, position.rows[0]?.next ?? 1, entryId, cleanText(explanation, 500), userId],
    );
    await client.query("UPDATE archive_trails SET updated_at = NOW() WHERE id = $1", [trailId]);
  });
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
  await transaction(async (client) => {
    const selected = await client.query<{ owner_id: string }>(
      "SELECT owner_id::text FROM archive_collections WHERE id = $1 AND guild_id = $2 AND status = 'active' FOR UPDATE",
      [collectionId, guildId],
    );
    const collection = selected.rows[0];
    if (!collection) throw new Error("That collection was not found in this server.");
    if (collection.owner_id !== userId) {
      const editor = await client.query(
        "SELECT 1 FROM archive_collection_collaborators WHERE collection_id = $1 AND user_id = $2 AND role = 'editor'",
        [collectionId, userId],
      );
      if (!editor.rowCount) throw new Error("Only the collection owner or an editor can remove items.");
    }
    await client.query(
      "DELETE FROM archive_collection_items WHERE collection_id = $1 AND entry_id = $2",
      [collectionId, entryId],
    );
    await client.query("UPDATE archive_collections SET updated_at = NOW() WHERE id = $1", [collectionId]);
  });
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

import {
  MessageFlags,
  PermissionsBitField,
  type Client,
  type GuildMember,
  type Message,
} from "discord.js";
import { query, queryOne } from "../database.js";
import { deleteArchiveAsset } from "./media-storage.js";
import { archiveUploadAllowed, storeArchiveUpload } from "./media-storage.js";
import { cleanText, isValidHttpsUrl, normalizeTags } from "./security.js";

export const ARCHIVE_CATEGORIES = [
  { label: "Manga Panels", value: "panels", emoji: "📚" },
  { label: "Quotes", value: "quotes", emoji: "💬" },
  { label: "Fanworks", value: "fanworks", emoji: "🎨" },
  { label: "Moodboards", value: "moodboards", emoji: "🖼️" },
  { label: "Soundtracks", value: "soundtracks", emoji: "🎵" },
  { label: "Scenes", value: "scenes", emoji: "🎬" },
  { label: "Recommendations", value: "recommendation-board", emoji: "⭐" },
  { label: "Theories", value: "theories", emoji: "💡" },
] as const;

export type ArchiveCategory = typeof ARCHIVE_CATEGORIES[number]["value"];
export type ArchiveVisibility = "server" | "global";

const DEFAULT_CATEGORIES = ARCHIVE_CATEGORIES.map((category) => category.value);
const UPLOAD_KINDS = new Set(["image", "audio", "video"]);
const GLOBAL_MODERATOR_IDS = new Set(
  (process.env.ARCHIVE_GLOBAL_MODERATOR_IDS ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter((id) => /^\d{17,20}$/.test(id)),
);

export interface ArchiveSettings {
  enabledCategories: ArchiveCategory[];
  uploadTypes: string[];
}

export interface ArchiveSubmission {
  guildId: string;
  userId: string;
  category: ArchiveCategory;
  title: string;
  content: string;
  sourceTitle?: string;
  creator?: string;
  mediaType: string;
  sourceUrl?: string;
  tags: string[];
  spoiler: boolean;
  visibility: ArchiveVisibility;
  needsUpload: boolean;
}

export interface ArchiveEntry {
  id: string;
  archive_type: ArchiveCategory;
  title: string;
  content: string;
  source_title: string | null;
  creator: string | null;
  media_type: string;
  source_url: string | null;
  tags: string[];
  spoiler: boolean;
  status: string;
  created_by: string;
  created_guild_id: string;
  visibility: ArchiveVisibility;
  media_asset_id: string | null;
  attachment_count?: number;
  created_at: Date;
}

export function isArchiveCategory(value: string): value is ArchiveCategory {
  return ARCHIVE_CATEGORIES.some((category) => category.value === value);
}

export async function getArchiveSettings(guildId: string): Promise<ArchiveSettings> {
  const row = await queryOne<{ enabled_categories: string; upload_types: string }>(
    "SELECT enabled_categories, upload_types FROM guild_archive_settings WHERE guild_id = $1",
    [guildId],
  );
  if (!row) return { enabledCategories: DEFAULT_CATEGORIES, uploadTypes: ["image"] };
  try {
    const categories = JSON.parse(row.enabled_categories) as unknown;
    const uploads = JSON.parse(row.upload_types) as unknown;
    if (!Array.isArray(categories) || !categories.every((item) => isArchiveCategory(String(item)))) {
      throw new Error("Invalid archive categories.");
    }
    if (!Array.isArray(uploads) || !uploads.every((item) => typeof item === "string" && UPLOAD_KINDS.has(item))) {
      throw new Error("Invalid archive upload settings.");
    }
    return {
      enabledCategories: [...new Set(categories as ArchiveCategory[])],
      uploadTypes: [...new Set(uploads as string[])],
    };
  } catch {
    // Invalid settings fail closed instead of enabling categories/uploads by accident.
    return { enabledCategories: [], uploadTypes: [] };
  }
}

export async function saveArchiveSettings(
  guildId: string,
  actorId: string,
  categories: ArchiveCategory[],
  uploadTypes: string[],
): Promise<void> {
  const normalizedCategories = [...new Set(categories)];
  const normalizedUploads = [...new Set(uploadTypes)];
  if (!normalizedCategories.length) throw new Error("Keep at least one archive category enabled.");
  if (!normalizedCategories.every(isArchiveCategory)) throw new Error("One or more categories are invalid.");
  if (!normalizedUploads.every((item) => UPLOAD_KINDS.has(item))) throw new Error("One or more upload types are invalid.");
  await query(
    `INSERT INTO guild_archive_settings (guild_id, enabled_categories, upload_types, updated_by, updated_at)
     VALUES ($1, $2, $3, $4, NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       enabled_categories = EXCLUDED.enabled_categories,
       upload_types = EXCLUDED.upload_types,
       updated_by = EXCLUDED.updated_by,
       updated_at = NOW()`,
    [guildId, JSON.stringify(normalizedCategories), JSON.stringify(normalizedUploads), actorId],
  );
}

export async function submitArchiveEntry(input: ArchiveSubmission): Promise<string> {
  const settings = await getArchiveSettings(input.guildId);
  if (!settings.enabledCategories.includes(input.category)) {
    throw new Error("That archive category is disabled in this server.");
  }
  const title = cleanText(input.title, 200);
  const body = input.content.trim();
  const sourceTitle = input.sourceTitle ? cleanText(input.sourceTitle, 200) : null;
  const creator = input.creator ? cleanText(input.creator, 200) : null;
  if (!title || !body) throw new Error("A title and description/content are both required.");
  if (body.length > 3_000) throw new Error("Archive descriptions are limited to 3,000 characters.");
  if (input.category === "quotes") {
    if (body.length > 280) throw new Error("Quotes are limited to 280 characters. Do not submit lyrics, chapters or long copyrighted passages.");
    if (!sourceTitle) throw new Error("Quotes need the source work's title for attribution.");
  }
  if (input.category === "fanworks" && !creator) {
    throw new Error("Fanworks need the original creator's name or handle.");
  }
  const sourceUrl = isValidHttpsUrl(input.sourceUrl, input.category === "fanworks");
  const tags = normalizeTags(input.tags.join(","));
  const allowedUploads = new Set(settings.uploadTypes);
  const needsUpload = input.needsUpload;
  if (needsUpload && input.category === "soundtracks" && !allowedUploads.has("audio") && !allowedUploads.has("video")) {
    throw new Error("This server has not enabled audio or video uploads. Supply an HTTPS music/video source link instead.");
  }
  if (input.visibility === "global" && !GLOBAL_MODERATOR_IDS.size) {
    throw new Error("Global Archive publishing is not enabled yet. This server can still publish server-only entries.");
  }
  const result = await queryOne<{ id: string }>(
    `INSERT INTO community_archive_entries
     (archive_type, title, content, source_title, creator, media_type, source_url,
      tags, spoiler, status, created_by, created_guild_id, visibility)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
     RETURNING id`,
    [
      input.category,
      title,
      body,
      sourceTitle,
      creator,
      cleanText(input.mediaType, 32) || "Other",
      sourceUrl,
      JSON.stringify(tags),
      input.spoiler,
      needsUpload ? "pending_upload" : "pending",
      input.userId,
      input.guildId,
      input.visibility,
    ],
  );
  if (!result) throw new Error("The Archive could not save this submission.");
  return result.id;
}

function parseTags(value: string): string[] {
  try {
    const parsed = JSON.parse(value) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string").slice(0, 10) : [];
  } catch {
    return [];
  }
}

export async function listArchiveEntries(
  guildId: string,
  category?: ArchiveCategory,
  keyword?: string,
  offset = 0,
  limit = 5,
): Promise<ArchiveEntry[]> {
  const conditions = [
    "status = 'approved'",
    "(visibility = 'global' OR (visibility = 'server' AND created_guild_id = $1))",
  ];
  const values: unknown[] = [guildId];
  if (category) {
    values.push(category);
    conditions.push(`archive_type = $${values.length}`);
  }
  if (keyword?.trim()) {
    values.push(`%${keyword.trim().slice(0, 100)}%`);
    conditions.push(`(title ILIKE $${values.length} OR content ILIKE $${values.length} OR COALESCE(source_title, '') ILIKE $${values.length} OR COALESCE(creator, '') ILIKE $${values.length})`);
  }
  values.push(Math.max(0, offset), Math.min(10, Math.max(1, limit)));
  const rows = await query<ArchiveEntry>(
    `SELECT e.*,
       (SELECT COUNT(*) FROM community_archive_entry_assets a WHERE a.entry_id = e.id) AS attachment_count
     FROM community_archive_entries e
     WHERE ${conditions.join(" AND ")}
     ORDER BY e.created_at DESC
     OFFSET $${values.length - 1} LIMIT $${values.length}`,
    values,
  );
  return rows.map((entry) => ({
    ...entry,
    tags: parseTags(String((entry as unknown as { tags: string }).tags ?? "[]")),
  }));
}

export async function getArchiveEntry(guildId: string, entryId: string, includePending = false): Promise<ArchiveEntry | null> {
  const conditions = includePending
    ? "(visibility = 'global' OR created_guild_id = $1)"
    : "(visibility = 'global' OR (visibility = 'server' AND created_guild_id = $1)) AND status = 'approved'";
  const row = await queryOne<ArchiveEntry>(
    `SELECT e.*,
       (SELECT COUNT(*) FROM community_archive_entry_assets a WHERE a.entry_id = e.id) AS attachment_count
     FROM community_archive_entries e
     WHERE id = $2 AND ${conditions}`,
    [guildId, entryId],
  );
  return row ? { ...row, tags: parseTags(String((row as unknown as { tags: string }).tags ?? "[]")) } : null;
}

export async function getOwnSubmissions(guildId: string, userId: string): Promise<ArchiveEntry[]> {
  const rows = await query<ArchiveEntry>(
    `SELECT * FROM community_archive_entries
     WHERE created_guild_id = $1 AND created_by = $2
     ORDER BY created_at DESC LIMIT 10`,
    [guildId, userId],
  );
  return rows.map((entry) => ({ ...entry, tags: parseTags(String((entry as unknown as { tags: string }).tags ?? "[]")) }));
}

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

export function isGlobalArchiveModerator(userId: string): boolean {
  return GLOBAL_MODERATOR_IDS.has(userId);
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

export async function handleArchiveUploadMessage(message: Message, _client: Client): Promise<boolean> {
  if (!message.guildId || message.author.bot || !message.attachments.size) return false;
  const settingsRow = await queryOne<{ panel_storage_channel_id: string | null }>(
    "SELECT panel_storage_channel_id FROM guild_settings WHERE guild_id = $1",
    [message.guildId],
  ).catch(() => null);
  if (!settingsRow?.panel_storage_channel_id || settingsRow.panel_storage_channel_id !== message.channelId) return false;
  const pending = await queryOne<{ id: string; archive_type: ArchiveCategory }>(
    `SELECT id, archive_type FROM community_archive_entries
     WHERE created_guild_id = $1 AND created_by = $2 AND status = 'pending_upload'
     ORDER BY created_at DESC LIMIT 1`,
    [message.guildId, message.author.id],
  );
  if (!pending) {
    await message.reply("There is no pending Archive submission waiting for an upload from you.");
    return true;
  }
  const settings = await getArchiveSettings(message.guildId);
  let stored = 0;
  for (const attachment of [...message.attachments.values()].slice(0, 5)) {
    const upload = {
      name: attachment.name,
      contentType: attachment.contentType ?? "application/octet-stream",
      bytes: Buffer.alloc(0),
    };
    if (!archiveUploadAllowed(pending.archive_type, settings.uploadTypes, upload)) continue;
    if (attachment.size > MAX_UPLOAD_BYTES) continue;
    const response = await fetch(attachment.url, { signal: AbortSignal.timeout(15_000) });
    if (!response.ok) continue;
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!archiveUploadAllowed(pending.archive_type, settings.uploadTypes, { ...upload, bytes })) continue;
    const assetId = await storeArchiveUpload(message.guildId, message.author.id, pending.archive_type, { ...upload, bytes }, settings.uploadTypes);
    const position = stored + 1;
    await query(
      `INSERT INTO community_archive_entry_assets (entry_id, asset_id, position, uploaded_by)
       VALUES ($1, $2, $3, $4)`,
      [pending.id, assetId, position, message.author.id],
    );
    if (position === 1) {
      await query(
        "UPDATE community_archive_entries SET media_asset_id = $1, attachment_filename = $2, attachment_content_type = $3 WHERE id = $4",
        [assetId, attachment.name, upload.contentType, pending.id],
      );
    }
    stored += 1;
  }
  await message.reply(stored
    ? `Saved ${stored} private upload(s) for Archive submission #${pending.id}. Return to the private submission response and press **Finish upload** when you're done.`
    : "No attachments were accepted. Check this category's enabled media types, file extension, MIME type and 20 MB size limit.");
  return true;
}

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export async function finishArchiveUpload(guildId: string, userId: string, entryId: string): Promise<void> {
  const pending = await queryOne<{ id: string; archive_type: ArchiveCategory; source_url: string | null }>(
    "SELECT id, archive_type, source_url FROM community_archive_entries WHERE id = $1 AND created_guild_id = $2 AND created_by = $3 AND status = 'pending_upload'",
    [entryId, guildId, userId],
  );
  if (!pending) throw new Error("That pending upload does not belong to you in this server.");
  const assets = await queryOne<{ count: string }>(
    "SELECT COUNT(*) AS count FROM community_archive_entry_assets WHERE entry_id = $1",
    [entryId],
  );
  if (!Number(assets?.count ?? 0) && !(pending.archive_type === "soundtracks" && pending.source_url)) {
    throw new Error("Add at least one accepted upload before finishing this submission.");
  }
  await query("UPDATE community_archive_entries SET status = 'pending', updated_at = NOW() WHERE id = $1 AND created_guild_id = $2 AND created_by = $3", [entryId, guildId, userId]);
}


export async function updateArchiveEntry(
  guildId: string,
  userId: string,
  entryId: string,
  changes: {
    title?: string;
    content?: string;
    sourceTitle?: string;
    creator?: string;
    sourceUrl?: string;
    tags?: string[];
    spoiler?: boolean;
  },
): Promise<void> {
  const entry = await queryOne<{ created_by: string; created_guild_id: string; visibility: ArchiveVisibility; status: string; archive_type: ArchiveCategory }>(
    "SELECT created_by, created_guild_id, visibility, status, archive_type FROM community_archive_entries WHERE id = $1 AND created_guild_id = $2",
    [entryId, guildId],
  );
  if (!entry || entry.visibility !== "server") throw new Error("That server-only contribution was not found.");
  if (entry.created_by !== userId) throw new Error("Only the original contributor can edit this entry.");
  if (!["pending","approved"].includes(entry.status)) throw new Error("This submission cannot be edited in its current moderation state.");
  const title = changes.title === undefined ? undefined : cleanText(changes.title, 200);
  const content = changes.content === undefined ? undefined : changes.content.trim();
  if (title !== undefined && !title) throw new Error("An entry title cannot be empty.");
  if (content !== undefined && !content) throw new Error("An entry description cannot be empty.");
  if (content !== undefined && content.length > 3_000) throw new Error("Archive descriptions are limited to 3,000 characters.");
  if (entry.archive_type === "quotes" && content !== undefined && content.length > 280) {
    throw new Error("Quotes are limited to 280 characters. Do not submit lyrics or long copyrighted passages.");
  }
  const sourceUrl = changes.sourceUrl === undefined ? undefined : isValidHttpsUrl(changes.sourceUrl);
  const tags = changes.tags === undefined ? undefined : normalizeTags(changes.tags.join(","));
  await query(
    `UPDATE community_archive_entries SET
       title = COALESCE($1, title),
       content = COALESCE($2, content),
       source_title = COALESCE($3, source_title),
       creator = COALESCE($4, creator),
       source_url = COALESCE($5, source_url),
       tags = COALESCE($6, tags),
       spoiler = COALESCE($7, spoiler),
       status = CASE WHEN status = 'approved' THEN 'pending' ELSE status END,
       moderation_reason = NULL,
       updated_at = NOW()
     WHERE id = $8 AND created_guild_id = $9 AND created_by = $10 AND visibility = 'server'`,
    [
      title ?? null,
      content ?? null,
      changes.sourceTitle === undefined ? null : cleanText(changes.sourceTitle, 200),
      changes.creator === undefined ? null : cleanText(changes.creator, 200),
      sourceUrl ?? null,
      tags === undefined ? null : JSON.stringify(tags),
      changes.spoiler ?? null,
      entryId,
      guildId,
      userId,
    ],
  );
}

export async function deleteArchiveEntry(
  guildId: string,
  actorId: string,
  entryId: string,
  canModerate: boolean,
  global = false,
): Promise<void> {
  const entry = await queryOne<{
    id: string;
    created_by: string;
    created_guild_id: string;
    visibility: ArchiveVisibility;
  }>(
    `SELECT id, created_by, created_guild_id, visibility
     FROM community_archive_entries
     WHERE id = $1 AND ${global ? "visibility = 'global'" : "visibility = 'server' AND created_guild_id = $2"}`,
    global ? [entryId] : [entryId, guildId],
  );
  if (!entry) throw new Error("That Archive entry was not found in this visibility scope.");
  if (entry.created_by !== actorId && !canModerate) throw new Error("Only the original contributor or an Archive moderator can delete this entry.");
  if (entry.visibility === "global" && !isGlobalArchiveModerator(actorId)) {
    throw new Error("Global Archive entries can only be deleted by a configured global moderator.");
  }
  const assets = await query<{ asset_id: string }>(
    "SELECT asset_id FROM community_archive_entry_assets WHERE entry_id = $1 ORDER BY position ASC",
    [entryId],
  );
  await query("DELETE FROM community_archive_entries WHERE id = $1", [entryId]);
  for (const asset of assets) {
    try {
      await deleteArchiveAsset(Number(asset.asset_id));
    } catch {
      // The entry is already removed; a failed S3 deletion is an orphan for operator cleanup.
    }
  }
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

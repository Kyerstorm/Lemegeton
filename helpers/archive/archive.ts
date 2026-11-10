import {
  MessageFlags,
  type Client,
  type Message,
} from "discord.js";
import { query, queryOne, transaction } from "../../database.js";
import { deleteArchiveAsset } from "../media/media-storage.js";
import { archiveUploadAllowed, getArchiveUploadMaxBytes, storeArchiveUpload } from "../media/media-storage.js";
import { cleanText, isValidHttpsUrl, normalizeTags } from "../security/security.js";
import { GLOBAL_MODERATOR_IDS, isGlobalArchiveModerator } from "./archive-access.js";
export { isGlobalArchiveModerator } from "./archive-access.js";

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

export const ARCHIVE_TAG_CATALOG = [
  "action","adventure","comedy","drama","fantasy","horror","mystery","psychological",
  "romance","sci-fi","slice of life","supernatural","thriller","tragedy","isekai",
  "martial arts","school life","historical","shounen","shoujo","seinen","josei",
  "manhwa","manhua","double spread","splash page","panel sequence","iconic moment",
  "character close-up","fight scene","comedy panel","emotional scene","flashback",
  "worldbuilding","monster / creature","weapons","magic","cyberpunk","post-apocalyptic",
  "folklore","mythology","politics","survival","revenge","cultivation","time travel",
  "reincarnation","sports","mecha","music","friendship","found family","coming of age",
  "school","historical fantasy","urban fantasy","mystery investigation","time loop",
  "reconstruction","dystopia","science fiction","travel","workplace","royalty",
] as const;

export function searchArchiveTags(query: string, selected: string[] = []): string[] {
  const term = query.trim().toLocaleLowerCase("en-US");
  const excluded = new Set(selected.map((tag) => tag.trim().toLocaleLowerCase("en-US")));
  return ARCHIVE_TAG_CATALOG.filter((tag) => {
    const normalized = tag.toLocaleLowerCase("en-US");
    return !excluded.has(normalized) && (!term || normalized.includes(term));
  }).sort((left, right) => {
    const leftStarts = left.toLocaleLowerCase("en-US").startsWith(term);
    const rightStarts = right.toLocaleLowerCase("en-US").startsWith(term);
    return Number(rightStarts) - Number(leftStarts) || left.localeCompare(right);
  }).slice(0, 25);
}

export type ArchiveCategory = typeof ARCHIVE_CATEGORIES[number]["value"];
export type ArchiveVisibility = "server" | "global";

const DEFAULT_CATEGORIES = ARCHIVE_CATEGORIES.map((category) => category.value);
const UPLOAD_KINDS = new Set(["image", "audio", "video"]);
export interface ArchiveSettings {
  enabledCategories: ArchiveCategory[];
  uploadTypes: string[];
  uploadChannelId: string | null;
  moderationChannelId: string | null;
  moderatorRoleId: string | null;
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
  chapterNumber?:string;
  linkedMediaProvider?:string;
  linkedMediaId?:string;
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
  chapter_number:string|null;
  linked_media_provider:string|null;
  linked_media_id:string|null;
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

export function parsePanelChapterCaption(value:string):{chapterNumber:string;caption:string}{
 const match=/^\s*(?:(?:chapter|ch\.?)\s*)?#?(\d+(?:\.\d+)?|N\/A)(?:\s*(?:[-–—:|]\s*|\s+)(.*?))?\s*$/i.exec(value.trim());
 if(!match||/[–—:|\-]$/.test(value.trim()))throw new Error("Enter a chapter number or N/A. An optional caption can follow, e.g. Chapter 12 — Final battle.");
 const chapterNumber=match[1]?.toUpperCase()==="N/A"?"N/A":match[1]!;
 return{chapterNumber,caption:(match[2]??"").trim()};
}

export function parseAniListMangaReference(value:string):{id:string|null;url:string|null}{
 const raw=value.trim();
 if(!raw)return{id:null,url:null};
 if(/^\d+$/.test(raw)){
  const id=BigInt(raw);
  if(id<=0n||id>BigInt(Number.MAX_SAFE_INTEGER))throw new Error("AniList manga IDs must be positive safe integers.");
  const normalized=id.toString();
  return{id:normalized,url:`https://anilist.co/manga/${normalized}`};
 }
 let url:URL;
 try{url=new URL(raw);}catch{throw new Error("Use a numeric AniList manga ID or an HTTPS AniList manga URL.");}
 const match=/^\/manga\/(\d+)(?:\/|$)/i.exec(url.pathname);
 if(url.protocol!=="https:"||!["anilist.co","www.anilist.co"].includes(url.hostname.toLowerCase())||!match){
  throw new Error("Use a numeric AniList manga ID or an HTTPS AniList manga URL.");
 }
 const id=BigInt(match[1]!);
 if(id<=0n||id>BigInt(Number.MAX_SAFE_INTEGER))throw new Error("AniList manga IDs must be positive safe integers.");
 const normalized=id.toString();
 return{id:normalized,url:`https://anilist.co/manga/${normalized}`};
}

export function isArchiveCategory(value: string): value is ArchiveCategory {
  return ARCHIVE_CATEGORIES.some((category) => category.value === value);
}

export async function getArchiveSettings(guildId: string): Promise<ArchiveSettings> {
  const row = await queryOne<{
    enabled_categories: string;
    upload_types: string;
    upload_channel_id: string | null;
    moderation_channel_id: string | null;
    moderator_role_id: string | null;
  }>(
    "SELECT enabled_categories, upload_types, upload_channel_id::text, moderation_channel_id::text, moderator_role_id::text FROM guild_archive_settings WHERE guild_id = $1",
    [guildId],
  );
  if (!row) return { enabledCategories: DEFAULT_CATEGORIES, uploadTypes: ["image"], uploadChannelId: null, moderationChannelId: null, moderatorRoleId: null };
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
      uploadChannelId: row.upload_channel_id,
      moderationChannelId: row.moderation_channel_id,
      moderatorRoleId: row.moderator_role_id,
    };
  } catch {
    // Invalid settings fail closed instead of enabling categories/uploads by accident.
    return { enabledCategories: [], uploadTypes: [], uploadChannelId: row.upload_channel_id, moderationChannelId: row.moderation_channel_id, moderatorRoleId: row.moderator_role_id };
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

export function isValidArchiveChannelId(channelId:string|null):boolean {
  return channelId===null || /^\d{17,20}$/.test(channelId);
}

export async function saveArchiveChannelSetting(
  guildId: string,
  actorId: string,
  kind: "upload" | "moderation",
  channelId: string | null,
): Promise<void> {
  if (!isValidArchiveChannelId(channelId)) {
    throw new Error("Choose a normal text or announcement channel from this server.");
  }
  const column = kind === "upload" ? "upload_channel_id" : "moderation_channel_id";
  await query(
    `INSERT INTO guild_archive_settings (guild_id, ${column}, updated_by, updated_at)
     VALUES ($1, $2, $3, NOW())
     ON CONFLICT (guild_id) DO UPDATE
       SET ${column} = EXCLUDED.${column}, updated_by = EXCLUDED.updated_by, updated_at = NOW()`,
    [guildId, channelId, actorId],
  );
}

export function isValidArchiveModeratorRoleId(roleId: string | null): boolean {
  return roleId === null || /^\\d{17,20}$/.test(roleId);
}

export async function saveArchiveModeratorRole(
  guildId: string,
  actorId: string,
  roleId: string | null,
): Promise<void> {
  if (!isValidArchiveModeratorRoleId(roleId) || roleId === guildId) {
    throw new Error("Choose a valid server role. @everyone cannot be an Archive moderator role.");
  }
  await query(
    `INSERT INTO guild_archive_settings (guild_id, moderator_role_id, updated_by, updated_at)
     VALUES ($1, $2, $3, NOW())
     ON CONFLICT (guild_id) DO UPDATE
       SET moderator_role_id = EXCLUDED.moderator_role_id, updated_by = EXCLUDED.updated_by, updated_at = NOW()`,
    [guildId, roleId, actorId],
  );
}

export async function getLastArchiveCategory(guildId: string, userId: string): Promise<ArchiveCategory | null> {
  const row = await queryOne<{ last_category: string }>(
    "SELECT last_category FROM archive_user_preferences WHERE guild_id = $1 AND user_id = $2",
    [guildId, userId],
  );
  return row && isArchiveCategory(row.last_category) ? row.last_category : null;
}

export async function rememberArchiveCategory(guildId: string, userId: string, category: ArchiveCategory): Promise<void> {
  await query(
    `INSERT INTO archive_user_preferences (guild_id,user_id,last_category,updated_at)
     VALUES ($1,$2,$3,NOW())
     ON CONFLICT (guild_id,user_id)
     DO UPDATE SET last_category = EXCLUDED.last_category, updated_at = NOW()`,
    [guildId,userId,category],
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
  if (!title || (!body && input.category!=="panels")) throw new Error("A title and description/content are both required.");
  const chapterNumber=input.category==="panels"?input.chapterNumber?.trim():undefined;
  if(input.category==="panels"&&(!chapterNumber||!(/^(?:\d+(?:\.\d+)?|N\/A)$/i.test(chapterNumber))))throw new Error("Manga panel entries need a chapter number or N/A.");
  const linkedMediaId=input.category==="panels"&&input.linkedMediaProvider==="AniList"&&input.linkedMediaId&&/^\d+$/.test(input.linkedMediaId)?input.linkedMediaId:null;
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
  if(input.category==="panels"&&tags.some(tag=>["nsfw","mature","adult"].includes(tag.toLowerCase())))throw new Error("Age-restricted tags are not accepted in the Community Archive.");
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
      tags, spoiler, status, created_by, created_guild_id, visibility, chapter_number, linked_media_provider, linked_media_id)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
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
      chapterNumber??null,
      linkedMediaId?"AniList":null,
      linkedMediaId,
    ],
  );
  if (!result) throw new Error("The Archive could not save this submission.");
  return result.id;
}

export function parseTags(value: string): string[] {
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

export function archiveEntryLookupScope(includePending: boolean, globalOnly: boolean): string {
  if (globalOnly) return includePending ? "visibility = 'global'" : "visibility = 'global' AND status = 'approved'";
  if (includePending) return "visibility = 'server' AND created_guild_id = $2";
  return "(visibility = 'global' OR (visibility = 'server' AND created_guild_id = $2)) AND status = 'approved'";
}

export async function getArchiveEntry(
  guildId: string,
  entryId: string,
  includePending = false,
  globalOnly = false,
): Promise<ArchiveEntry | null> {
  const row = await queryOne<ArchiveEntry>(
    `SELECT e.*,
       (SELECT COUNT(*) FROM community_archive_entry_assets a WHERE a.entry_id = e.id) AS attachment_count
     FROM community_archive_entries e
     WHERE id = $1 AND ${archiveEntryLookupScope(includePending, globalOnly)}`,
    globalOnly ? [entryId] : [entryId, guildId],
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

export async function handleArchiveUploadMessage(message: Message, _client: Client): Promise<boolean> {
  if (!message.guildId || message.author.bot || !message.attachments.size) return false;
  const settings = await getArchiveSettings(message.guildId);
  if (!settings.uploadChannelId || settings.uploadChannelId !== message.channelId) return false;
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
  let stored = 0;
  for (const attachment of [...message.attachments.values()].slice(0, 5)) {
    const upload = {
      name: attachment.name,
      contentType: attachment.contentType ?? "application/octet-stream",
      bytes: Buffer.alloc(0),
    };
    if (!archiveUploadAllowed(pending.archive_type, settings.uploadTypes, upload)) continue;
    if (attachment.size > getArchiveUploadMaxBytes()) continue;
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
    chapterNumber?: string;
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
  if (content !== undefined && !content && entry.archive_type !== "panels") throw new Error("An entry description cannot be empty.");
  if (content !== undefined && content.length > 3_000) throw new Error("Archive descriptions are limited to 3,000 characters.");
  if (entry.archive_type === "quotes" && content !== undefined && content.length > 280) {
    throw new Error("Quotes are limited to 280 characters. Do not submit lyrics or long copyrighted passages.");
  }
  const panelReference = entry.archive_type === "panels" && changes.sourceUrl !== undefined
    ? parseAniListMangaReference(changes.sourceUrl)
    : null;
  const sourceUrl = changes.sourceUrl === undefined ? undefined
    : entry.archive_type === "panels" ? panelReference?.url ?? null
    : isValidHttpsUrl(changes.sourceUrl);
  const chapterNumber = changes.chapterNumber === undefined ? undefined : changes.chapterNumber.trim();
  if(entry.archive_type==="panels"&&chapterNumber!==undefined&&!/^(?:\d+(?:\.\d+)?|N\/A)$/i.test(chapterNumber))throw new Error("Manga panel entries need a chapter number or N/A.");
  const tags = changes.tags === undefined ? undefined : normalizeTags(changes.tags.join(","));
  if(entry.archive_type==="panels"&&tags?.some(tag=>["nsfw","mature","adult"].includes(tag.toLowerCase())))throw new Error("Age-restricted tags are not accepted in the Community Archive.");
  await query(
    `UPDATE community_archive_entries SET
       title = COALESCE($1, title),
       content = COALESCE($2, content),
       source_title = COALESCE($3, source_title),
       creator = COALESCE($4, creator),
       source_url = COALESCE($5, source_url),
       tags = COALESCE($6, tags),
       spoiler = COALESCE($7, spoiler),
       chapter_number = COALESCE($8, chapter_number),
       linked_media_provider = COALESCE($9, linked_media_provider),
       linked_media_id = COALESCE($10, linked_media_id),
       status = CASE WHEN status = 'approved' THEN 'pending' ELSE status END,
       moderation_reason = NULL,
       updated_at = NOW()
     WHERE id = $11 AND created_guild_id = $12 AND created_by = $13 AND visibility = 'server'`,
    [
      title ?? null,
      content ?? null,
      changes.sourceTitle === undefined ? null : cleanText(changes.sourceTitle, 200),
      changes.creator === undefined ? null : cleanText(changes.creator, 200),
      sourceUrl ?? null,
      tags === undefined ? null : JSON.stringify(tags),
      changes.spoiler ?? null,
      chapterNumber ?? null,
      panelReference?.id ? "AniList" : null,
      panelReference?.id ?? null,
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
  const assets = await transaction(async (client) => {
    const scope = global
      ? "id = $1 AND visibility = 'global'"
      : "id = $1 AND visibility = 'server' AND created_guild_id = $2";
    const selected = await client.query<{
      id: string;
      created_by: string;
      created_guild_id: string;
      visibility: ArchiveVisibility;
    }>(
      "SELECT id, created_by, created_guild_id, visibility FROM community_archive_entries WHERE " + scope + " FOR UPDATE",
      global ? [entryId] : [entryId, guildId],
    );
    const entry = selected.rows[0];
    if (!entry) throw new Error("That Archive entry was not found in this visibility scope.");
    if (entry.created_by !== actorId && !canModerate) throw new Error("Only the original contributor or an Archive moderator can delete this entry.");
    if (entry.visibility === "global" && !isGlobalArchiveModerator(actorId)) {
      throw new Error("Global Archive entries can only be deleted by a configured global moderator.");
    }
    await client.query(
      "INSERT INTO media_asset_cleanup_queue (asset_id) SELECT asset_id FROM community_archive_entry_assets WHERE entry_id = $1 ON CONFLICT (asset_id) DO NOTHING",
      [entryId],
    );
    const linkedAssets = await client.query<{ asset_id: string }>(
      "SELECT asset_id::text FROM community_archive_entry_assets WHERE entry_id = $1 ORDER BY position ASC",
      [entryId],
    );
    await client.query("DELETE FROM community_archive_entries WHERE id = $1", [entryId]);
    return linkedAssets.rows;
  });
  for (const asset of assets) {
    try {
      await deleteArchiveAsset(Number(asset.asset_id));
    } catch {
      // The durable cleanup queue retries failed private-object deletions.
    }
  }
}

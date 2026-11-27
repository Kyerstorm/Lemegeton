import { createHash, randomUUID } from "node:crypto";
import sharp from "sharp";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { AttachmentBuilder, ChannelType, PermissionFlagsBits, type Client, type TextChannel } from "discord.js";
import type { BotConfig } from "../runtime/config.js";
import { logger } from "../runtime/logger.js";
import {
  deleteRocksObject,
  getRocksObject,
  openRocksDb,
  putRocksObject,
} from "../../src/utility/database/rocksdb/rocksdb.js";

type MediaStorageConfig = Pick<BotConfig, "archiveUploadMaxBytes" | "rocksDbPath">;
let runtimeConfig: MediaStorageConfig = {
  archiveUploadMaxBytes: 20 * 1024 * 1024,
  rocksDbPath: "./data/objects",
};
let rocksReady: Promise<void> | undefined;

async function ensureRocksDb(): Promise<void> {
  if (!rocksReady) {
    rocksReady = openRocksDb(runtimeConfig.rocksDbPath).catch(error => {
      rocksReady = undefined;
      throw error;
    });
  }
  await rocksReady;
}

export function configureMediaStorage(config: MediaStorageConfig): void {
  if (runtimeConfig.rocksDbPath !== config.rocksDbPath) rocksReady = undefined;
  runtimeConfig = config;
}

export function getArchiveUploadMaxBytes(): number {
  return runtimeConfig.archiveUploadMaxBytes;
}
export function archiveUploadChannelIsPrivate(
  everyoneCanView: boolean,
  botCanView: boolean,
  botCanSendMessages: boolean,
  botCanManageMessages: boolean,
): boolean {
  return !everyoneCanView && botCanView && botCanSendMessages && botCanManageMessages;
}

export function archiveStorageChannelIsPrivate(
  everyoneCanView: boolean,
  botCanView: boolean,
  botCanSendMessages: boolean,
  botCanAttachFiles: boolean,
): boolean {
  return !everyoneCanView && botCanView && botCanSendMessages && botCanAttachFiles;
}

export async function downloadArchiveUpload(
  value: string,
  fetcher: typeof fetch = globalThis.fetch,
): Promise<Buffer> {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("The Discord attachment URL is invalid.");
  }
  if (url.protocol !== "https:" || url.hostname !== "cdn.discordapp.com"
    || url.username || url.password) {
    throw new Error("Archive uploads must come directly from Discord's attachment CDN.");
  }

  const response = await fetcher(url, {
    signal: AbortSignal.timeout(15_000),
    redirect: "error",
  });
  if (!response.ok) throw new Error("Discord could not provide the attachment bytes.");
  if (response.url) {
    const finalUrl = new URL(response.url);
    if (finalUrl.protocol !== "https:" || finalUrl.hostname !== "cdn.discordapp.com") {
      throw new Error("The Discord attachment redirected outside its trusted CDN.");
    }
  }

  const maximum = getArchiveUploadMaxBytes();
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximum) {
    throw new Error("Archive uploads are limited to " + maximum + " bytes.");
  }
  if (!response.body) {
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!bytes.length || bytes.byteLength > maximum) {
      throw new Error("Archive uploads must be between 1 byte and " + maximum + " bytes.");
    }
    return bytes;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      total += next.value.byteLength;
      if (total > maximum) {
        await reader.cancel();
        throw new Error("Archive uploads are limited to " + maximum + " bytes.");
      }
      chunks.push(next.value);
    }
  } finally {
    reader.releaseLock();
  }
  if (!total) throw new Error("The Discord attachment was empty.");
  return Buffer.concat(chunks.map(chunk => Buffer.from(chunk)), total);
}

const MIME_BY_EXTENSION: Record<string, string> = {
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
  ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
  ".opus": "audio/ogg", ".wav": "audio/wav", ".flac": "audio/flac", ".aac": "audio/aac",
  ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/x-m4v",
};
const ALLOWED_BY_CATEGORY: Record<string, ReadonlySet<string>> = {
  panels: new Set(["image"]),
  quotes: new Set(["image"]),
  fanworks: new Set(["image", "audio", "video"]),
  moodboards: new Set(["image"]),
  soundtracks: new Set(["audio", "video"]),
  scenes: new Set(["image", "video"]),
  "recommendation-board": new Set(),
  theories: new Set(["image", "video"]),
};

export interface ArchiveUpload {
  name: string;
  contentType: string;
  bytes: Buffer;
}

export function classifyArchiveUpload(category: string, upload: ArchiveUpload): { kind: string; contentType: string; extension: string } {
  const extension = upload.name.toLowerCase().match(/\.[a-z0-9]{1,8}$/)?.[0] ?? "";
  const expected = MIME_BY_EXTENSION[extension];
  if (!expected) throw new Error("That file extension is not supported by the Archive.");
  const supplied = upload.contentType.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if (supplied && supplied !== "application/octet-stream" && supplied !== expected) {
    throw new Error("The file type does not match its filename.");
  }
  if (upload.bytes.byteLength < 1 || upload.bytes.byteLength > getArchiveUploadMaxBytes()) {
    throw new Error("Archive uploads must be between 1 byte and 20 MB.");
  }
  const kind = expected.startsWith("image/") ? "image" : expected.startsWith("audio/") ? "audio" : "video";
  if (!ALLOWED_BY_CATEGORY[category]?.has(kind)) {
    throw new Error(`${kind} uploads are not supported for the ${category} category.`);
  }
  return { kind, contentType: expected, extension };
}

export function archiveUploadAllowed(category: string, enabled: string[], upload: ArchiveUpload): boolean {
  try {
    // The caller checks the real attachment size before downloading/storing bytes.
    const kind = classifyArchiveUpload(category, { ...upload, bytes: Buffer.from([0]) }).kind;
    return enabled.includes(kind);
  } catch {
    return false;
  }
}

export function archiveStorageProvider(legacyStorageChannelId: string | null): "discord" | "rocksdb" {
  return legacyStorageChannelId ? "discord" : "rocksdb";
}

async function legacyStorageChannel(client: Client, guildId: string, channelId: string): Promise<TextChannel> {
  if (!/^\d{17,20}$/.test(channelId)) throw new Error("The configured legacy storage channel ID is invalid.");
  const channel = await client.channels.fetch(channelId).catch(() => null);
  if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
    throw new Error("The configured legacy Archive storage channel is unavailable. Ask a server manager to repair it; storage will not switch automatically.");
  }
  const textChannel = channel as TextChannel;
  if (textChannel.guildId !== guildId) {
    throw new Error("The configured legacy Archive storage channel belongs to a different server.");
  }
  const member = await textChannel.guild.members.fetchMe();
  const botPermissions = textChannel.permissionsFor(member);
  const publicPermissions = textChannel.permissionsFor(textChannel.guild.roles.everyone);
  if (!archiveStorageChannelIsPrivate(
    publicPermissions.has(PermissionFlagsBits.ViewChannel),
    botPermissions.has(PermissionFlagsBits.ViewChannel),
    botPermissions.has(PermissionFlagsBits.SendMessages),
    botPermissions.has(PermissionFlagsBits.AttachFiles),
  )) {
    throw new Error("The configured legacy Archive storage channel must remain private and grant the bot View Channel, Send Messages and Attach Files.");
  }
  return textChannel;
}

const ARCHIVE_IMAGE_FORMATS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpeg",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/avif": "heif",
};

export async function stripArchiveImageMetadata(input: Buffer, contentType: string): Promise<Buffer> {
  const expectedFormat = ARCHIVE_IMAGE_FORMATS[contentType];
  if (!expectedFormat) throw new Error("That Archive image format cannot be sanitized.");

  const options = { animated: true, limitInputPixels: 16_000_000 };
  let metadata;
  try {
    metadata = await sharp(input, options).metadata();
  } catch {
    throw new Error("The Archive image could not be decoded safely.");
  }
  if (metadata.format !== expectedFormat) {
    throw new Error("The image contents do not match their declared image type.");
  }

  // Re-encode every accepted image so EXIF/GPS, IPTC, XMP and unrecognized
  // ancillary metadata cannot survive in a stored Archive attachment.
  try {
    const image = sharp(input, options).rotate();
    let sanitized: Buffer;
    switch (contentType) {
      case "image/jpeg":
        sanitized = await image.jpeg({ quality: 100, chromaSubsampling: "4:4:4" }).toBuffer();
        break;
      case "image/png":
        sanitized = await image.png({ compressionLevel: 9 }).toBuffer();
        break;
      case "image/gif":
        sanitized = await image.gif().toBuffer();
        break;
      case "image/webp":
        sanitized = await image.webp({ lossless: true }).toBuffer();
        break;
      case "image/avif":
        sanitized = await image.avif({ lossless: true }).toBuffer();
        break;
      default:
        throw new Error("unsupported_image_format");
    }

    if (!sanitized.length || sanitized.byteLength > getArchiveUploadMaxBytes()) {
      throw new Error("sanitized_image_exceeds_upload_limit");
    }
    const verified = await sharp(sanitized, options).metadata();
    if (verified.exif || verified.iptc || verified.xmp) {
      throw new Error("image_metadata_remains");
    }
    return sanitized;
  } catch {
    throw new Error("The Archive image could not be sanitized safely. Try exporting it as a new PNG or JPEG.");
  }
}

export async function storeArchiveUpload(
  guildId: string,
  userId: string,
  category: string,
  upload: ArchiveUpload,
  configuredUploadTypes: string[],
  options: { client?: Client; legacyStorageChannelId?: string | null } = {},
): Promise<number> {
  const { kind, contentType, extension } = classifyArchiveUpload(category, upload);
  if (!configuredUploadTypes.includes(kind)) {
    throw new Error(`This server has not enabled ${kind} uploads for the Archive.`);
  }
  const storedUpload = kind === "image"
    ? { ...upload, bytes: await stripArchiveImageMetadata(upload.bytes, contentType) }
    : upload;

  if (archiveStorageProvider(options.legacyStorageChannelId ?? null) === "discord") {
    if (!options.client || !options.legacyStorageChannelId) {
      throw new Error("The legacy Archive storage channel could not be resolved.");
    }
    const channel = await legacyStorageChannel(options.client, guildId, options.legacyStorageChannelId);
    const message = await channel.send({
      files: [new AttachmentBuilder(storedUpload.bytes, { name: storedUpload.name })],
      allowedMentions: { parse: [] },
    });
    const attachment = message.attachments.first();
    if (!attachment) {
      await message.delete().catch(() => undefined);
      throw new Error("Discord did not return the stored Archive attachment.");
    }
    const digest = createHash("sha256").update(storedUpload.bytes).digest("hex");
    try {
      return await transaction(async database => {
        const inserted = await database.query<{ id: string }>(
          `INSERT INTO media_assets
           (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
           VALUES ('discord', $1, $2, $3, $4, $5, $6, TRUE, $7, $8) RETURNING id`,
          [`archive/${guildId}`, channel.id, `${message.id}/${attachment.id}`, contentType,
            storedUpload.bytes.byteLength, digest, userId, guildId],
        );
        const id = inserted.rows[0]?.id;
        if (!id) throw new Error("Legacy Archive asset registry insert returned no ID.");
        await database.query(
          "INSERT INTO media_asset_cleanup_queue (asset_id, next_attempt_at) VALUES ($1, NOW() + INTERVAL '1 hour')",
          [id],
        );
        return Number(id);
      });
    } catch (error) {
      await message.delete().catch(() => undefined);
      throw error;
    }
  }

  await ensureRocksDb();
  const key = `archive/${guildId}/${randomUUID()}${extension}`;
  const digest = createHash("sha256").update(storedUpload.bytes).digest("hex");
  await putRocksObject(key, storedUpload.bytes, {
    contentType,
    sha256: digest,
    guildId,
    namespace: `archive/${guildId}`,
  });
  try {
    return await transaction(async database => {
      const inserted = await database.query<{ id: string }>(
        `INSERT INTO media_assets
         (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
         VALUES ('rocksdb', $1, 'local', $2, $3, $4, $5, TRUE, $6, $7) RETURNING id`,
        [`archive/${guildId}`, key, contentType, storedUpload.bytes.byteLength, digest, userId, guildId],
      );
      const id = inserted.rows[0]?.id;
      if (!id) throw new Error("RocksDB media asset registry insert returned no ID.");
      await database.query(
        "INSERT INTO media_asset_cleanup_queue (asset_id, next_attempt_at) VALUES ($1, NOW() + INTERVAL '1 hour')",
        [id],
      );
      return Number(id);
    });
  } catch (error) {
    await deleteRocksObject(key).catch(() => undefined);
    throw error;
  }
}

export async function resolveLegacyArchiveAttachmentUrl(
  client: Client,
  guildId: string,
  channelId: string,
  messageId: string,
  filename?: string | null,
): Promise<string | null> {
  try {
    const channel = await client.channels.fetch(channelId);
    if (!channel || channel.type !== ChannelType.GuildText) return null;
    const textChannel = channel as TextChannel;
    if (textChannel.guildId !== guildId) return null;
    const message = await textChannel.messages.fetch(messageId);
    const attachment = (filename ? message.attachments.find(item => item.name === filename) : null)
      ?? message.attachments.first();
    return attachment?.url ?? null;
  } catch {
    return null;
  }
}

export async function signedArchiveAssetUrl(
  assetId: number,
  client: Client | undefined,
  expectedGuildId: string,
): Promise<string | null> {
  const asset = await queryOne<{
    provider: string;
    bucket_name: string;
    object_key: string;
    is_private: boolean;
    guild_id: string | null;
    namespace: string;
  }>(
    "SELECT provider, bucket_name, object_key, is_private, guild_id, namespace FROM media_assets WHERE id = $1",
    [assetId],
  );
  if (!asset || !asset.is_private || asset.guild_id !== expectedGuildId
    || asset.namespace !== `archive/${expectedGuildId}`) return null;
  if (asset.provider !== "discord" || !client) return null;

  const [messageId, attachmentId] = asset.object_key.split("/", 2);
  if (typeof messageId !== "string" || typeof attachmentId !== "string"
    || !/^\\d{17,20}$/.test(messageId) || !/^\\d{17,20}$/.test(attachmentId)) return null;
  const channel = await legacyStorageChannel(client, asset.guild_id, asset.bucket_name).catch(() => null);
  if (!channel) return null;
  const message = await channel.messages.fetch(messageId).catch(() => null);
  if (!message || message.guildId !== asset.guild_id || message.channelId !== asset.bucket_name) return null;
  return message.attachments.get(attachmentId)?.url ?? null;
}

export async function readArchiveAsset(assetId: number, expectedGuildId: string): Promise<Buffer | null> {
  const asset = await queryOne<{
    provider: string;
    object_key: string;
    content_type: string;
    is_private: boolean;
    guild_id: string | null;
    namespace: string;
    sha256: string;
    size_bytes: string | number;
  }>(
    "SELECT provider, object_key, content_type, is_private, guild_id, namespace, sha256, size_bytes " +
    "FROM media_assets WHERE id = $1",
    [assetId],
  );
  if (!asset || !asset.is_private || asset.provider !== "rocksdb"
    || asset.guild_id !== expectedGuildId || asset.namespace !== `archive/${expectedGuildId}`) return null;

  await ensureRocksDb();
  const bytes = await getRocksObject(asset.object_key);
  if (!bytes || bytes.byteLength !== Number(asset.size_bytes)) return null;
  if (createHash("sha256").update(bytes).digest("hex") !== asset.sha256) {
    throw new Error("The stored Archive asset failed its SHA-256 integrity check.");
  }
  return bytes;
}

export function archiveAssetCleanupBackoffSeconds(attempt: number): number {
  const retry = Number.isFinite(attempt) ? Math.max(1, Math.floor(attempt)) : 1;
  return Math.min(86_400, 60 * 2 ** Math.min(retry - 1, 11));
}

export async function queueArchiveAssetCleanup(assetId: number): Promise<boolean> {
  const asset = await queryOne<{ id: string }>("SELECT id FROM media_assets WHERE id = $1", [assetId]);
  if (!asset) return false;
  await query(
    "INSERT INTO media_asset_cleanup_queue (asset_id) VALUES ($1) ON CONFLICT (asset_id) DO NOTHING",
    [assetId],
  );
  return true;
}

export async function deleteArchiveAsset(assetId: number, client?: Client): Promise<boolean> {
  let deletionError: unknown;
  const deleted = await transaction(async database => {
    // Linkers share-lock this row. Holding its update lock through remote deletion
    // prevents an attachment from being linked after the reference check.
    const selected = await database.query<{
      provider: string; bucket_name: string; object_key: string; guild_id: string | null; namespace: string;
    }>(
      "SELECT provider, bucket_name, object_key, guild_id::text, namespace FROM media_assets WHERE id = $1 FOR UPDATE",
      [assetId],
    );
    const asset = selected.rows[0];
    if (!asset) return false;

    await database.query(
      "INSERT INTO media_asset_cleanup_queue (asset_id) VALUES ($1) ON CONFLICT (asset_id) DO NOTHING",
      [assetId],
    );
    const references = await database.query<{ referenced: boolean }>(
      "SELECT (EXISTS (SELECT 1 FROM community_archive_entry_assets WHERE asset_id = $1) OR EXISTS (SELECT 1 FROM community_archive_entries WHERE media_asset_id = $1)) AS referenced",
      [assetId],
    );
    if (references.rows[0]?.referenced) {
      await database.query("DELETE FROM media_asset_cleanup_queue WHERE asset_id = $1", [assetId]);
      return false;
    }

    try {
      if (asset.provider === "discord") {
        if (!client || !asset.guild_id || asset.namespace !== `archive/${asset.guild_id}`) {
          throw new Error("The Discord client is unavailable for legacy Archive cleanup.");
        }
        const [messageId, attachmentId] = asset.object_key.split("/", 2);
        if (typeof messageId !== "string" || typeof attachmentId !== "string"
          || !/^\d{17,20}$/.test(messageId) || !/^\d{17,20}$/.test(attachmentId)) {
          throw new Error("Legacy Archive asset metadata is invalid.");
        }
        const channel = await client.channels.fetch(asset.bucket_name).catch(error => {
          const code = Number((error as { code?: unknown })?.code);
          const status = Number((error as { status?: unknown })?.status);
          if (code === 10003 || status === 404) return null;
          throw error;
        });
        if (channel) {
          if ((channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)
            || (channel as TextChannel).guildId !== asset.guild_id) {
            throw new Error("Legacy Archive asset channel no longer matches its source server.");
          }
          const message = await (channel as TextChannel).messages.fetch(messageId).catch(error => {
            const code = Number((error as { code?: unknown })?.code);
            const status = Number((error as { status?: unknown })?.status);
            if (code === 10008 || status === 404) return null;
            throw error;
          });
          if (message && (message.guildId !== asset.guild_id || message.channelId !== asset.bucket_name)) {
            throw new Error("Legacy Archive asset message ownership could not be verified.");
          }
          await message?.delete();
        }
      } else if (asset.provider === "rocksdb") {
        await ensureRocksDb();
        await deleteRocksObject(asset.object_key);
      } else {
        throw new Error("Unsupported Archive storage provider.");
      }
    } catch (error) {
      const queued = await database.query<{ attempts: number }>(
        "SELECT attempts FROM media_asset_cleanup_queue WHERE asset_id = $1 FOR UPDATE",
        [assetId],
      );
      const attempts = Number(queued.rows[0]?.attempts ?? 0) + 1;
      const reason = error instanceof Error ? error.message.slice(0, 300) : "Unknown storage error";
      await database.query(
        "UPDATE media_asset_cleanup_queue SET attempts = $2, next_attempt_at = NOW() + ($3 * INTERVAL '1 second'), last_error = $4 WHERE asset_id = $1",
        [assetId, attempts, archiveAssetCleanupBackoffSeconds(attempts), reason],
      );
      logger.warn("Private Archive asset deletion failed; retry remains queued", {
        assetId,
        provider: asset.provider,
        reason,
      });
      deletionError = error;
      return false;
    }

    await database.query("DELETE FROM media_assets WHERE id = $1", [assetId]);
    return true;
  });

  if (deletionError) throw deletionError;
  return deleted;
}

export async function processArchiveAssetCleanup(limit = 10, client?: Client): Promise<{ attempted: number; failed: number }> {
  const boundedLimit = Math.min(50, Math.max(1, Math.floor(limit)));
  const due = await transaction(async database => {
    // Claim due rows atomically. A five-minute lease lets another worker recover
    // the row if this process exits before the object deletion is attempted.
    const claimed = await database.query<{ asset_id: string }>(
      `WITH due AS (
         SELECT asset_id
         FROM media_asset_cleanup_queue
         WHERE next_attempt_at <= NOW()
         ORDER BY next_attempt_at ASC
         LIMIT $1
         FOR UPDATE SKIP LOCKED
       )
       UPDATE media_asset_cleanup_queue q
       SET next_attempt_at = NOW() + INTERVAL '5 minutes'
       FROM due
       WHERE q.asset_id = due.asset_id
       RETURNING q.asset_id::text`,
      [boundedLimit],
    );
    return claimed.rows;
  });

  let attempted = 0;
  let failed = 0;
  for (const item of due) {
    attempted += 1;
    try {
      await deleteArchiveAsset(Number(item.asset_id), client);
    } catch {
      failed += 1;
    }
  }
  return { attempted, failed };
}


export async function storeCustomRoleIconSource(
  guildId: string,
  userId: string,
  bytes: Buffer,
  contentType: "image/png" | "image/jpeg",
): Promise<number> {
  if (bytes.byteLength < 1) throw new Error("The role icon image is empty.");
  if (bytes.byteLength > 8 * 1024 * 1024) throw new Error("The role icon image exceeds the 8 MB storage limit.");
  await ensureRocksDb();
  const extension = contentType === "image/png" ? ".png" : ".jpg";
  const key = `custom-roles/${guildId}/${randomUUID()}${extension}`;
  const digest = createHash("sha256").update(bytes).digest("hex");
  await putRocksObject(key, bytes, {
    contentType,
    sha256: digest,
    guildId,
    namespace: `custom-roles/${guildId}`,
  });
  try {
    const inserted = await queryOne<{ id: string }>(
      `INSERT INTO media_assets
       (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
       VALUES ('rocksdb', $1, 'local', $2, $3, $4, $5, TRUE, $6, $7) RETURNING id`,
      [`custom-roles/${guildId}`, key, contentType, bytes.byteLength, digest, userId, guildId],
    );
    if (!inserted) throw new Error("Custom role icon asset registry insert returned no ID.");
    return Number(inserted.id);
  } catch (error) {
    await deleteRocksObject(key).catch(() => undefined);
    throw error;
  }
}

export async function readCustomRoleIconSource(assetId: number, guildId: string): Promise<Buffer | null> {
  const asset = await queryOne<{
    object_key: string;
    is_private: boolean;
    namespace: string;
    sha256: string;
    size_bytes: string | number;
  }>(
    "SELECT object_key, is_private, namespace, sha256, size_bytes " +
    "FROM media_assets WHERE id = $1 AND guild_id = $2",
    [assetId, guildId],
  );
  if (!asset || !asset.is_private || asset.namespace !== `custom-roles/${guildId}`) return null;
  await ensureRocksDb();
  const bytes = await getRocksObject(asset.object_key);
  if (!bytes || bytes.byteLength !== Number(asset.size_bytes)) return null;
  if (createHash("sha256").update(bytes).digest("hex") !== asset.sha256) {
    throw new Error("The custom role icon failed its SHA-256 integrity check.");
  }
  return bytes;
}

export async function deleteCustomRoleIconSource(assetId: number, guildId: string): Promise<boolean> {
  const asset = await queryOne<{ object_key: string }>(
    "SELECT object_key FROM media_assets " +
    "WHERE id = $1 AND guild_id = $2 AND namespace = $3 AND is_private = TRUE AND provider = 'rocksdb'",
    [assetId, guildId, `custom-roles/${guildId}`],
  );
  if (!asset) return false;
  await ensureRocksDb();
  await deleteRocksObject(asset.object_key);
  await query("DELETE FROM media_assets WHERE id = $1 AND guild_id = $2", [assetId, guildId]);
  return true;
}

import { createHash, randomUUID } from "node:crypto";
import {
  DeleteObjectCommand,
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { query, queryOne } from "../../database.js";
import { AttachmentBuilder, ChannelType, PermissionFlagsBits, type Client, type TextChannel } from "discord.js";
import type { BotConfig } from "../runtime/config.js";

type MediaStorageConfig = Pick<BotConfig,
  "archiveUploadMaxBytes" | "s3EndpointUrl" | "s3Region" | "s3AccessKeyId" |
  "s3SecretAccessKey" | "s3Bucket" | "s3SignedUrlTtlSeconds"
>;
let runtimeConfig: MediaStorageConfig = {
  archiveUploadMaxBytes: 20 * 1024 * 1024,
  s3Region: "us-east-1",
  s3Bucket: null,
  s3SignedUrlTtlSeconds: 900,
};

export function configureMediaStorage(config: MediaStorageConfig): void {
  runtimeConfig = config;
  client?.destroy();
  client = undefined;
  signature = "";
}

export function getArchiveUploadMaxBytes(): number {
  return runtimeConfig.archiveUploadMaxBytes;
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

let client: S3Client | undefined;
let signature = "";

function s3Client(): S3Client {
  const endpoint = runtimeConfig.s3EndpointUrl;
  const region = runtimeConfig.s3Region;
  const accessKeyId = runtimeConfig.s3AccessKeyId;
  const secretAccessKey = runtimeConfig.s3SecretAccessKey;
  if (Boolean(accessKeyId) !== Boolean(secretAccessKey)) {
    throw new Error("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be configured together.");
  }
  const nextSignature = [endpoint, region, accessKeyId, secretAccessKey].join("|");
  if (!client || signature !== nextSignature) {
    client?.destroy();
    client = new S3Client({
      region,
      ...(endpoint ? { endpoint, forcePathStyle: true } : {}),
      ...(accessKeyId && secretAccessKey ? { credentials: { accessKeyId, secretAccessKey } } : {}),
    });
    signature = nextSignature;
  }
  return client;
}

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

export function archiveStorageProvider(legacyStorageChannelId: string | null): "discord" | "s3" {
  return legacyStorageChannelId ? "discord" : "s3";
}

async function legacyStorageChannel(client: Client, guildId: string, channelId: string): Promise<TextChannel> {
  if (!/^\\d{17,20}$/.test(channelId)) throw new Error("The configured legacy storage channel ID is invalid.");
  const channel = await client.channels.fetch(channelId).catch(() => null);
  if (!channel || channel.type !== ChannelType.GuildText) {
    throw new Error("The configured legacy Archive storage channel is unavailable. Ask a server manager to repair it; storage will not switch automatically.");
  }
  const textChannel = channel as TextChannel;
  if (textChannel.guildId !== guildId) {
    throw new Error("The configured legacy Archive storage channel belongs to a different server.");
  }
  const member = await textChannel.guild.members.fetchMe();
  const botPermissions = textChannel.permissionsFor(member);
  const publicPermissions = textChannel.permissionsFor(textChannel.guild.roles.everyone);
  if (!botPermissions.has([PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.AttachFiles])
    || publicPermissions.has(PermissionFlagsBits.ViewChannel)) {
    throw new Error("The configured legacy Archive storage channel must remain private and grant the bot View Channel, Send Messages and Attach Files.");
  }
  return textChannel;
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
  if (archiveStorageProvider(options.legacyStorageChannelId ?? null) === "discord") {
    if (!options.client || !options.legacyStorageChannelId) {
      throw new Error("The legacy Archive storage channel could not be resolved.");
    }
    const channel = await legacyStorageChannel(options.client, guildId, options.legacyStorageChannelId);
    const message = await channel.send({
      files: [new AttachmentBuilder(upload.bytes, { name: upload.name })],
      allowedMentions: { parse: [] },
    });
    const attachment = message.attachments.first();
    if (!attachment) {
      await message.delete().catch(() => undefined);
      throw new Error("Discord did not return the stored Archive attachment.");
    }
    const digest = createHash("sha256").update(upload.bytes).digest("hex");
    try {
      const inserted = await queryOne<{ id: string }>(
        `INSERT INTO media_assets
         (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
         VALUES ('discord', $1, $2, $3, $4, $5, $6, TRUE, $7, $8) RETURNING id`,
        [`archive/${guildId}`, channel.id, `${message.id}/${attachment.id}`, contentType, upload.bytes.byteLength, digest, userId, guildId],
      );
      if (!inserted) throw new Error("Legacy Archive asset registry insert returned no ID.");
      return Number(inserted.id);
    } catch (error) {
      await message.delete().catch(() => undefined);
      throw error;
    }
  }

  const bucket = runtimeConfig.s3Bucket ?? undefined;
  if (!bucket) {
    throw new Error("Private S3 storage is not configured. Ask an administrator to configure private S3 storage before accepting new Archive uploads.");
  }
  const storage = s3Client();
  const key = `archive/${guildId}/${randomUUID()}${extension}`;
  const digest = createHash("sha256").update(upload.bytes).digest("hex");
  try {
    await storage.send(new PutObjectCommand({
      Bucket: bucket,
      Key: key,
      Body: upload.bytes,
      ContentType: contentType,
      CacheControl: "private, no-store",
      Metadata: { sha256: digest },
    }));
  } catch {
    throw new Error("The private media upload failed. The archive entry was not saved.");
  }

  try {
    const inserted = await queryOne<{ id: string }>(
      `INSERT INTO media_assets
       (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
       VALUES ('s3', $1, $2, $3, $4, $5, $6, TRUE, $7, $8) RETURNING id`,
      [`archive/${guildId}`, bucket, key, contentType, upload.bytes.byteLength, digest, userId, guildId],
    );
    if (!inserted) throw new Error("Media asset registry insert returned no ID.");
    return Number(inserted.id);
  } catch (error) {
    try { await storage.send(new DeleteObjectCommand({ Bucket: bucket, Key: key })); } catch { /* preserve the database error */ }
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
  client?: Client,
  expectedGuildId?: string,
): Promise<string | null> {
  const asset = await queryOne<{ provider: string; bucket_name: string; object_key: string; is_private: boolean; guild_id: string | null; namespace: string }>(
    "SELECT provider, bucket_name, object_key, is_private, guild_id::text, namespace FROM media_assets WHERE id = $1",
    [assetId],
  );
  if (!asset || !asset.is_private) return null;
  if (expectedGuildId && asset.guild_id !== expectedGuildId) return null;
  if (asset.provider === "discord") {
    if (!client || !asset.guild_id || asset.namespace !== `archive/${asset.guild_id}`) return null;
    const [messageId, attachmentId] = asset.object_key.split("/", 2);
    if (typeof messageId !== "string" || typeof attachmentId !== "string" || !/^\d{17,20}$/.test(messageId) || !/^\d{17,20}$/.test(attachmentId)) return null;
    const channel = await client.channels.fetch(asset.bucket_name).catch(() => null);
    if (!channel || channel.type !== ChannelType.GuildText || (channel as TextChannel).guildId !== asset.guild_id) return null;
    const message = await (channel as TextChannel).messages.fetch(messageId).catch(() => null);
    if (!message || message.guildId !== asset.guild_id || message.channelId !== asset.bucket_name) return null;
    return message.attachments.get(attachmentId)?.url ?? null;
  }
  if (asset.provider !== "s3") return null;
  return getSignedUrl(s3Client(), new GetObjectCommand({
    Bucket: asset.bucket_name,
    Key: asset.object_key,
  }), { expiresIn: runtimeConfig.s3SignedUrlTtlSeconds });
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
  const asset = await queryOne<{
    provider: string; bucket_name: string; object_key: string; guild_id: string | null; namespace: string;
  }>(
    "SELECT provider, bucket_name, object_key, guild_id::text, namespace FROM media_assets WHERE id = $1",
    [assetId],
  );
  if (!asset) return false;
  await queueArchiveAssetCleanup(assetId);
  const references = await queryOne<{ referenced: boolean }>(
    "SELECT (EXISTS (SELECT 1 FROM community_archive_entry_assets WHERE asset_id = $1) OR EXISTS (SELECT 1 FROM community_archive_entries WHERE media_asset_id = $1)) AS referenced",
    [assetId],
  );
  if (references?.referenced) {
    await query("DELETE FROM media_asset_cleanup_queue WHERE asset_id = $1", [assetId]);
    return false;
  }
  try {
    if (asset.provider === "discord") {
      if (!client || !asset.guild_id || asset.namespace !== `archive/${asset.guild_id}`) {
        throw new Error("The Discord client is unavailable for legacy Archive cleanup.");
      }
      const [messageId, attachmentId] = asset.object_key.split("/", 2);
      if (typeof messageId !== "string" || typeof attachmentId !== "string" || !/^\d{17,20}$/.test(messageId) || !/^\d{17,20}$/.test(attachmentId)) {
        throw new Error("Legacy Archive asset metadata is invalid.");
      }
      const channel = await client.channels.fetch(asset.bucket_name).catch(error => {
        const code = Number((error as { code?: unknown })?.code);
        const status = Number((error as { status?: unknown })?.status);
        if (code === 10003 || status === 404) return null;
        throw error;
      });
      if (channel) {
        if (channel.type !== ChannelType.GuildText || (channel as TextChannel).guildId !== asset.guild_id) {
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
    } else if (asset.provider === "s3") {
      await s3Client().send(new DeleteObjectCommand({ Bucket: asset.bucket_name, Key: asset.object_key }));
    } else {
      throw new Error("Unsupported Archive storage provider.");
    }
    await query("DELETE FROM media_assets WHERE id = $1", [assetId]);
    return true;
  } catch (error) {
    const queued = await queryOne<{ attempts: number }>(
      "SELECT attempts FROM media_asset_cleanup_queue WHERE asset_id = $1",
      [assetId],
    ).catch(() => null);
    const attempts = Number(queued?.attempts ?? 0) + 1;
    await query(
      "UPDATE media_asset_cleanup_queue SET attempts = $2, next_attempt_at = NOW() + ($3 * INTERVAL '1 second'), last_error = 'Private asset deletion failed' WHERE asset_id = $1",
      [assetId, attempts, archiveAssetCleanupBackoffSeconds(attempts)],
    ).catch(() => undefined);
    throw error;
  }
}

export async function processArchiveAssetCleanup(limit = 10, client?: Client): Promise<{ attempted: number; failed: number }> {
  const boundedLimit = Math.min(50, Math.max(1, Math.floor(limit)));
  const due = await query<{ asset_id: string }>(
    "SELECT asset_id::text FROM media_asset_cleanup_queue WHERE next_attempt_at <= NOW() ORDER BY next_attempt_at ASC LIMIT $1",
    [boundedLimit],
  );
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
  const bucket = runtimeConfig.s3Bucket ?? undefined;
  if (!bucket) throw new Error("Private S3 storage is not configured. Image role icons cannot be saved safely.");
  const extension = contentType === "image/png" ? ".png" : ".jpg";
  const key = `custom-roles/${guildId}/${randomUUID()}${extension}`;
  const digest = createHash("sha256").update(bytes).digest("hex");
  const storage = s3Client();
  await storage.send(new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: bytes,
    ContentType: contentType,
    CacheControl: "private, no-store",
    Metadata: { sha256: digest },
  }));
  try {
    const inserted = await queryOne<{ id: string }>(
      `INSERT INTO media_assets
       (provider, namespace, bucket_name, object_key, content_type, size_bytes, sha256, is_private, uploaded_by, guild_id)
       VALUES ('s3', $1, $2, $3, $4, $5, $6, TRUE, $7, $8) RETURNING id`,
      [`custom-roles/${guildId}`, bucket, key, contentType, bytes.byteLength, digest, userId, guildId],
    );
    if (!inserted) throw new Error("Custom role icon asset registry insert returned no ID.");
    return Number(inserted.id);
  } catch (error) {
    await storage.send(new DeleteObjectCommand({ Bucket: bucket, Key: key })).catch(() => undefined);
    throw error;
  }
}

export async function readCustomRoleIconSource(assetId: number, guildId: string): Promise<Buffer | null> {
  const asset = await queryOne<{ bucket_name: string; object_key: string; is_private: boolean; namespace: string }>(
    "SELECT bucket_name, object_key, is_private, namespace FROM media_assets WHERE id = $1 AND guild_id = $2",
    [assetId, guildId],
  );
  if (!asset || !asset.is_private || asset.namespace !== `custom-roles/${guildId}`) return null;
  const response = await s3Client().send(new GetObjectCommand({
    Bucket: asset.bucket_name,
    Key: asset.object_key,
  }));
  if (!response.Body) return null;
  return Buffer.from(await response.Body.transformToByteArray());
}

export async function deleteCustomRoleIconSource(assetId: number, guildId: string): Promise<boolean> {
  const asset = await queryOne<{ bucket_name: string; object_key: string }>(
    "SELECT bucket_name, object_key FROM media_assets WHERE id = $1 AND guild_id = $2 AND namespace = $3 AND is_private = TRUE",
    [assetId, guildId, `custom-roles/${guildId}`],
  );
  if (!asset) return false;
  await s3Client().send(new DeleteObjectCommand({ Bucket: asset.bucket_name, Key: asset.object_key }));
  await query("DELETE FROM media_assets WHERE id = $1 AND guild_id = $2", [assetId, guildId]);
  return true;
}

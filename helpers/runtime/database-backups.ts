import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { GetObjectCommand, HeadObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import type { BotConfig } from "./config.js";
import { query, queryOne } from "../../database.js";

export interface DatabaseBackupRecord {
  id: string;
  object_key: string;
  sha256: string;
  size_bytes: string;
  status: "creating" | "verified" | "failed";
  verification_error: string | null;
  created_at: Date;
  verified_at: Date | null;
}

export function databaseBackupObjectKey(id: string, createdAt: Date): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error("A valid backup UUID is required.");
  }
  if (!Number.isFinite(createdAt.getTime())) throw new Error("The backup date is invalid.");
  const monthKey = createdAt.toISOString().slice(0, 7);
  const year = monthKey.slice(0, 4);
  const month = monthKey.slice(5, 7);
  return "database-backups/" + year + "/" + month + "/" + id + ".dump";
}

export async function listDatabaseBackups(limit = 5): Promise<DatabaseBackupRecord[]> {
  const boundedLimit = Math.max(1, Math.min(20, Math.floor(limit) || 5));
  return query<DatabaseBackupRecord>(
    "SELECT id::text, object_key, sha256, size_bytes::text, status, verification_error, created_at, verified_at " +
    "FROM bot_database_backups ORDER BY created_at DESC LIMIT $1",
    [boundedLimit],
  );
}

function storageClient(config: BotConfig): S3Client {
  if (!config.s3Bucket) throw new Error("Configure a private S3-compatible bucket before creating backups.");
  if (Boolean(config.s3AccessKeyId) !== Boolean(config.s3SecretAccessKey)) {
    throw new Error("Both S3 access-key fields must be configured together.");
  }
  return new S3Client({
    region: config.s3Region,
    ...(config.s3EndpointUrl ? { endpoint: config.s3EndpointUrl, forcePathStyle: true } : {}),
    ...(config.s3AccessKeyId && config.s3SecretAccessKey
      ? { credentials: { accessKeyId: config.s3AccessKeyId, secretAccessKey: config.s3SecretAccessKey } }
      : {}),
  });
}

function postgresProcessConfig(config: BotConfig): { args: string[]; env: NodeJS.ProcessEnv } {
  const database = config.database;
  let username = database.user;
  let password = database.password;
  let databaseName = database.database;
  if (database.connectionString) {
    const dsn = new URL(database.connectionString);
    username = decodeURIComponent(dsn.username || username);
    password = decodeURIComponent(dsn.password || password);
    databaseName = decodeURIComponent(dsn.pathname.replace(/^\/+/, "")) || databaseName;
  }
  return {
    args: [
      "--format=custom", "--no-owner", "--no-privileges",
      "--host", database.host, "--port", String(database.port),
      "--username", username, "--dbname", databaseName,
    ],
    env: {
      ...process.env,
      PGPASSWORD: password,
      PGSSLMODE: database.ssl ? "require" : "disable",
      ...(database.sslCaFile ? { PGSSLROOTCERT: database.sslCaFile } : {}),
    },
  };
}

function runProcess(binary: string, args: string[], env: NodeJS.ProcessEnv): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { env, stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(binary + " exceeded the 10-minute execution limit."));
    }, 10 * 60 * 1000);
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", chunk => { stderr = (stderr + String(chunk)).slice(-4_000); });
    child.once("error", error => { clearTimeout(timeout); reject(new Error(binary + " could not start: " + error.message)); });
    child.once("close", code => {
      clearTimeout(timeout);
      if (code === 0) resolve();
      else reject(new Error(binary + " exited with code " + String(code) + (stderr ? ": " + stderr.trim() : ".")));
    });
  });
}

async function hashFile(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk as Buffer);
  return digest.digest("hex");
}

async function downloadObject(client: S3Client, config: BotConfig, objectKey: string, targetPath: string): Promise<void> {
  const response = await client.send(new GetObjectCommand({ Bucket: config.s3Bucket!, Key: objectKey }));
  if (!response.Body) throw new Error("The backup object returned an empty body.");
  await pipeline(Readable.from(response.Body as AsyncIterable<Uint8Array>), createWriteStream(targetPath, { flags: "wx", mode: 0o600 }));
}

async function verifyArchive(path: string, expectedDigest: string, expectedSize: number): Promise<void> {
  const file = await stat(path);
  if (!file.size || file.size !== expectedSize) throw new Error("The backup file size does not match its stored metadata.");
  if (await hashFile(path) !== expectedDigest) throw new Error("The backup SHA-256 digest does not match its stored metadata.");
  await runProcess("pg_restore", ["--list", path], process.env);
}

async function updateBackupStatus(
  id: string, status: "verified" | "failed", digest?: string, size?: number, error?: string,
): Promise<void> {
  await query(
    "UPDATE bot_database_backups SET status = $2, sha256 = COALESCE($3, sha256), " +
    "size_bytes = COALESCE($4, size_bytes), verification_error = $5, " +
    "verified_at = CASE WHEN $2 = 'verified' THEN NOW() ELSE NULL END WHERE id = $1",
    [id, status, digest ?? null, size ?? null, error?.slice(0, 2_000) ?? null],
  );
}

async function getBackup(id: string): Promise<DatabaseBackupRecord> {
  const row = await queryOne<DatabaseBackupRecord>(
    "SELECT id::text, object_key, sha256, size_bytes::text, status, verification_error, created_at, verified_at " +
    "FROM bot_database_backups WHERE id = $1",
    [id],
  );
  if (!row) throw new Error("That database backup was not found.");
  return row;
}

export async function createDatabaseBackup(config: BotConfig, createdBy: string): Promise<DatabaseBackupRecord> {
  if (!config.s3Bucket) throw new Error("Configure a private S3-compatible bucket before creating backups.");
  const id = randomUUID();
  const objectKey = databaseBackupObjectKey(id, new Date());
  await query(
    "INSERT INTO bot_database_backups (id, object_key, sha256, size_bytes, created_by, status) VALUES ($1,$2,$3,0,$4,'creating')",
    [id, objectKey, "0".repeat(64), createdBy],
  );
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-db-backup-"));
  const dumpPath = join(directory, id + ".dump");
  const verifyPath = join(directory, id + ".verify.dump");
  let client: S3Client | undefined;
  try {
    client = storageClient(config);
    const processConfig = postgresProcessConfig(config);
    await runProcess("pg_dump", [...processConfig.args, "--file", dumpPath], processConfig.env);
    const file = await stat(dumpPath);
    if (!file.size) throw new Error("pg_dump returned an empty archive.");
    const digest = await hashFile(dumpPath);
    await client.send(new PutObjectCommand({
      Bucket: config.s3Bucket, Key: objectKey, Body: createReadStream(dumpPath),
      ContentLength: file.size, ContentType: "application/octet-stream",
      ServerSideEncryption: "AES256", Metadata: { "backup-id": id, sha256: digest },
    }));
    const head = await client.send(new HeadObjectCommand({ Bucket: config.s3Bucket, Key: objectKey }));
    if (head.ContentLength !== file.size) throw new Error("The uploaded S3 object size does not match the local archive.");
    await downloadObject(client, config, objectKey, verifyPath);
    await verifyArchive(verifyPath, digest, file.size);
    await updateBackupStatus(id, "verified", digest, file.size);
    return await getBackup(id);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backup failure.";
    await updateBackupStatus(id, "failed", undefined, undefined, message).catch(() => undefined);
    throw error;
  } finally {
    client?.destroy();
    await rm(directory, { recursive: true, force: true });
  }
}

export async function verifyDatabaseBackup(id: string, config: BotConfig): Promise<DatabaseBackupRecord> {
  const backup = await getBackup(id);
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-db-verify-"));
  const verifyPath = join(directory, backup.id + ".dump");
  let client: S3Client | undefined;
  try {
    client = storageClient(config);
    const head = await client.send(new HeadObjectCommand({ Bucket: config.s3Bucket!, Key: backup.object_key }));
    const size = Number(backup.size_bytes);
    if (!Number.isSafeInteger(size) || size < 1 || head.ContentLength !== size) {
      throw new Error("The stored S3 object size does not match backup metadata.");
    }
    await downloadObject(client, config, backup.object_key, verifyPath);
    await verifyArchive(verifyPath, backup.sha256, size);
    await updateBackupStatus(backup.id, "verified", backup.sha256, size);
    return await getBackup(backup.id);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backup verification failure.";
    await updateBackupStatus(backup.id, "failed", undefined, undefined, message).catch(() => undefined);
    throw error;
  } finally {
    client?.destroy();
    await rm(directory, { recursive: true, force: true });
  }
}

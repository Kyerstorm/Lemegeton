import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createReadStream, createWriteStream, readFileSync } from "node:fs";
import { Client } from "pg";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { GetObjectCommand, HeadObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";
import type { BotConfig, DatabaseConfig } from "./config.js";
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
  rehearsal_status: "not_run" | "passed" | "failed";
  rehearsal_error: string | null;
  rehearsal_at: Date | null;
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

export function databaseRehearsalName(id: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error("A valid backup UUID is required for a restore rehearsal.");
  }
  return "lemegeton_rehearsal_" + randomUUID().replace(/-/g, "");
}

export async function listDatabaseBackups(limit = 5): Promise<DatabaseBackupRecord[]> {
  const boundedLimit = Math.max(1, Math.min(20, Math.floor(limit) || 5));
  return query<DatabaseBackupRecord>(
    "SELECT id::text, object_key, sha256, size_bytes::text, status, verification_error, created_at, verified_at, " +
    "rehearsal_status, rehearsal_error, rehearsal_at " +
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
    "SELECT id::text, object_key, sha256, size_bytes::text, status, verification_error, created_at, verified_at, " +
    "rehearsal_status, rehearsal_error, rehearsal_at FROM bot_database_backups WHERE id = $1",
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


function pgClient(config: DatabaseConfig, databaseName?: string): Client {
  let connectionString = config.connectionString;
  if (connectionString && databaseName) {
    const parsed = new URL(connectionString);
    parsed.pathname = "/" + encodeURIComponent(databaseName);
    connectionString = parsed.toString();
  }
  return new Client({
    ...(connectionString
      ? { connectionString }
      : { host: config.host, port: config.port, database: databaseName ?? config.database, user: config.user, password: config.password }),
    ssl: config.ssl
      ? { rejectUnauthorized: true, ...(config.sslCaFile ? { ca: readFileSync(config.sslCaFile, "utf8") } : {}) }
      : false,
    connectionTimeoutMillis: 10_000,
    query_timeout: 30_000,
    application_name: "lemegeton-backup-rehearsal",
  });
}

function restoreProcessConfig(database: DatabaseConfig, databaseName: string): { args: string[]; env: NodeJS.ProcessEnv } {
  let username = database.user;
  let password = database.password;
  if (database.connectionString) {
    const dsn = new URL(database.connectionString);
    username = decodeURIComponent(dsn.username || username);
    password = decodeURIComponent(dsn.password || password);
  }
  return {
    args: [
      "--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges",
      "--host", database.host, "--port", String(database.port),
      "--username", username, "--dbname", databaseName,
    ],
    env: {
      ...process.env, PGPASSWORD: password,
      PGSSLMODE: database.ssl ? "require" : "disable",
      ...(database.sslCaFile ? { PGSSLROOTCERT: database.sslCaFile } : {}),
    },
  };
}

async function updateRehearsalStatus(id: string, status: "passed" | "failed", error?: string): Promise<void> {
  await query(
    "UPDATE bot_database_backups SET rehearsal_status = $2, rehearsal_error = $3, rehearsal_at = NOW() WHERE id = $1",
    [id, status, error?.slice(0, 2_000) ?? null],
  );
}

/** Restores only to a uniquely named temporary database on the separately configured rehearsal cluster. */
export async function rehearseDatabaseBackup(
  id: string,
  config: BotConfig,
): Promise<{ backupId: string; databaseName: string; tableCount: number }> {
  const target = config.backupRehearsalDatabase;
  if (!target) throw new Error("Set BACKUP_REHEARSAL_DATABASE_URL to a separate PostgreSQL host or port before running a restore rehearsal.");
  const backup = await getBackup(id);
  if (backup.status !== "verified") throw new Error("Only a verified backup can be used for a restore rehearsal.");
  const temporaryDatabase = databaseRehearsalName(backup.id);
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-restore-rehearsal-"));
  const archivePath = join(directory, backup.id + ".dump");
  const size = Number(backup.size_bytes);
  let storage: S3Client | undefined;
  let admin: Client | undefined;
  let restored: Client | undefined;
  let failure: string | undefined;
  let tableCount = 0;

  try {
    if (!Number.isSafeInteger(size) || size < 1) throw new Error("Backup size metadata is invalid.");
    storage = storageClient(config);
    const head = await storage.send(new HeadObjectCommand({ Bucket: config.s3Bucket!, Key: backup.object_key }));
    if (head.ContentLength !== size) throw new Error("The stored S3 object size does not match backup metadata.");
    await downloadObject(storage, config, backup.object_key, archivePath);
    await verifyArchive(archivePath, backup.sha256, size);

    admin = pgClient(target);
    await admin.connect();
    await admin.query("CREATE DATABASE \"" + temporaryDatabase + "\"");

    const restore = restoreProcessConfig(target, temporaryDatabase);
    await runProcess("pg_restore", [...restore.args, archivePath], restore.env);

    restored = pgClient(target, temporaryDatabase);
    await restored.connect();
    const validation = await restored.query<{ table_count: number; core_table: string | null }>(
      "SELECT COUNT(*)::INT AS table_count, " +
      "(SELECT to_regclass('public.guild_retention_settings')::text) AS core_table " +
      "FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
    );
    tableCount = validation.rows[0]?.table_count ?? 0;
    if (tableCount < 1 || !validation.rows[0]?.core_table) {
      throw new Error("The restored archive is missing the expected Lemegeton core schema.");
    }
  } catch (error) {
    failure = error instanceof Error ? error.message : "Unknown restore rehearsal failure.";
  } finally {
    if (restored) await restored.end().catch(error => {
      failure = [failure, "Could not close the temporary restore connection: " + (error instanceof Error ? error.message : "unknown error")].filter(Boolean).join(" ");
    });
    if (admin) {
      await admin.query("DROP DATABASE IF EXISTS \"" + temporaryDatabase + "\"").catch(error => {
        failure = [failure, "Temporary rehearsal database cleanup failed: " + (error instanceof Error ? error.message : "unknown error")].filter(Boolean).join(" ");
      });
    }
    if (admin) await admin.end().catch(error => {
      failure = [failure, "Could not close the rehearsal admin connection: " + (error instanceof Error ? error.message : "unknown error")].filter(Boolean).join(" ");
    });
    storage?.destroy();
    await rm(directory, { recursive: true, force: true }).catch(error => {
      failure = [failure, "Temporary restore files could not be removed: " + (error instanceof Error ? error.message : "unknown error")].filter(Boolean).join(" ");
    });
  }

  if (failure) {
    await updateRehearsalStatus(backup.id, "failed", failure).catch(() => undefined);
    throw new Error(failure);
  }
  await updateRehearsalStatus(backup.id, "passed");
  return { backupId: backup.id, databaseName: temporaryDatabase, tableCount };
}

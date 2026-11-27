import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, lstat, mkdir, mkdtemp, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { query, queryOne, backupDatabase, inspectDatabase } from "../../src/utility/database/libsql/database.js";
import { createRocksCheckpoint, openRocksDb } from "../../src/utility/database/rocksdb/rocksdb.js";
import type { BotConfig } from "./config.js";

export interface DatabaseBackupRecord {
  id: string;
  object_key: string;
  sha256: string;
  size_bytes: string | number;
  status: "creating" | "verified" | "failed";
  verification_error: string | null;
  created_by: string;
  created_at: Date;
  verified_at: Date | null;
  rehearsal_status: "not_run" | "passed" | "failed";
  rehearsal_error: string | null;
  rehearsal_at: Date | null;
}

const MAX_BACKUP_BYTES = 8 * 1024 * 1024 * 1024;
const BACKUP_PROCESS_TIMEOUT_MS = 10 * 60 * 1000;

export function databaseBackupObjectKey(id: string, createdAt: Date): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error("A valid backup UUID is required.");
  }
  if (!Number.isFinite(createdAt.getTime())) throw new Error("The backup date is invalid.");
  const month = createdAt.toISOString().slice(0, 7);
  return `database-backups/${month.slice(0, 4)}/${month.slice(5, 7)}/${id}.tar.gz`;
}

export function databaseRehearsalName(id: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error("A valid backup UUID is required for a restore rehearsal.");
  }
  return "lemegeton_rehearsal_" + randomUUID().replace(/-/g, "");
}

function backupFilePath(config: BotConfig, key: string): string {
  if (!/^database-backups\/\d{4}\/\d{2}\/[0-9a-f-]{36}\.tar\.gz$/i.test(key)) {
    throw new Error("The stored backup path is invalid.");
  }
  const root = resolve(config.backupDirectory);
  const file = resolve(root, key);
  const relativePath = relative(root, file);
  if (!relativePath || relativePath === ".." || relativePath.startsWith(".." + sep) || isAbsolute(relativePath)) {
    throw new Error("The stored backup path escapes the configured backup directory.");
  }
  return file;
}

async function ensureBackupDirectory(config: BotConfig): Promise<void> {
  const root = resolve(config.backupDirectory);
  await mkdir(root, { recursive: true, mode: 0o700 });
  const details = await lstat(root);
  if (details.isSymbolicLink() || !details.isDirectory()) {
    throw new Error("BACKUP_DIRECTORY must be a real directory, not a symlink or file.");
  }
  await chmod(root, 0o700);
}

function runProcess(binary: string, args: string[], timeoutMs = BACKUP_PROCESS_TIMEOUT_MS): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(binary, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (error) reject(error);
      else resolvePromise(stdout);
    };
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new Error(binary + " exceeded the backup process time limit."));
    }, timeoutMs);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", chunk => {
      stdout += String(chunk);
      if (stdout.length > 2 * 1024 * 1024) {
        child.kill("SIGKILL");
        finish(new Error(binary + " returned more output than expected."));
      }
    });
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", chunk => { stderr = (stderr + String(chunk)).slice(-4_000); });
    child.once("error", error => finish(new Error(binary + " could not start: " + error.message)));
    child.once("close", code => {
      if (code === 0) finish();
      else finish(new Error(binary + " exited with code " + String(code) + (stderr ? ": " + stderr.trim() : ".")));
    });
  });
}

async function hashFile(path: string): Promise<string> {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk as Buffer);
  return digest.digest("hex");
}

async function extractVerifiedArchive(archivePath: string, directory: string): Promise<void> {
  const listing = await runProcess("tar", ["-tzf", archivePath]);
  const entries = listing.split("\n").map(path => path.trim()).filter(Boolean);
  if (!entries.length || entries.length > 1_000_000) {
    throw new Error("The database backup archive has an invalid file listing.");
  }
  for (const entry of entries) {
    const normalized = entry.replace(/\/$/, "");
    if (normalized.startsWith("/") || normalized.split("/").some(part => part === "..")) {
      throw new Error("The database backup archive contains an unsafe file path.");
    }
    if (normalized !== "bot.db" && normalized !== "objects" && !normalized.startsWith("objects/")) {
      throw new Error("The database backup archive contains an unexpected file.");
    }
  }
  if (!entries.includes("bot.db") || !entries.includes("objects/")) {
    throw new Error("The backup must contain the libSQL database and RocksDB checkpoint.");
  }
  await runProcess("tar", ["-xzf", archivePath, "--no-same-owner", "--no-same-permissions", "-C", directory]);
}

async function verifyArchive(archivePath: string, expectedDigest: string, expectedSize: number): Promise<number> {
  const file = await stat(archivePath);
  if (!file.isFile() || file.size < 1 || file.size !== expectedSize || file.size > MAX_BACKUP_BYTES) {
    throw new Error("The backup file size does not match its stored metadata or exceeds the archive limit.");
  }
  if (await hashFile(archivePath) !== expectedDigest) {
    throw new Error("The backup SHA-256 digest does not match its stored metadata.");
  }

  const directory = await mkdtemp(join(tmpdir(), "lemegeton-backup-verify-"));
  try {
    await extractVerifiedArchive(archivePath, directory);
    const databasePath = join(directory, "bot.db");
    const objectsPath = join(directory, "objects");
    const inspection = await inspectDatabase(databasePath);
    if (inspection.integrity !== "ok" || inspection.tableCount < 1) {
      throw new Error("The bundled libSQL database failed its integrity check.");
    }
    const objects = await readdir(objectsPath);
    if (!objects.includes("CURRENT") || !objects.some(name => name.startsWith("MANIFEST-"))) {
      throw new Error("The bundled RocksDB checkpoint is incomplete.");
    }
    return inspection.tableCount;
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

export async function listDatabaseBackups(limit = 5): Promise<DatabaseBackupRecord[]> {
  const boundedLimit = Math.max(1, Math.min(20, Math.floor(limit) || 5));
  return query<DatabaseBackupRecord>(
    "SELECT id, object_key, sha256, size_bytes, status, verification_error, created_by, created_at, verified_at, " +
    "rehearsal_status, rehearsal_error, rehearsal_at " +
    "FROM bot_database_backups ORDER BY created_at DESC LIMIT $1",
    [boundedLimit],
  );
}

async function getBackup(id: string): Promise<DatabaseBackupRecord> {
  const row = await queryOne<DatabaseBackupRecord>(
    "SELECT id, object_key, sha256, size_bytes, status, verification_error, created_by, created_at, verified_at, " +
    "rehearsal_status, rehearsal_error, rehearsal_at FROM bot_database_backups WHERE id = $1",
    [id],
  );
  if (!row) throw new Error("That database backup was not found.");
  return row;
}

async function updateBackupStatus(
  id: string,
  status: "verified" | "failed",
  digest?: string,
  size?: number,
  error?: string,
): Promise<void> {
  await query(
    "UPDATE bot_database_backups SET status = $2, sha256 = COALESCE($3, sha256), " +
    "size_bytes = COALESCE($4, size_bytes), verification_error = $5, " +
    "verified_at = CASE WHEN $2 = 'verified' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id = $1",
    [id, status, digest ?? null, size ?? null, error?.slice(0, 2_000) ?? null],
  );
}

export async function createDatabaseBackup(config: BotConfig, createdBy: string): Promise<DatabaseBackupRecord> {
  await ensureBackupDirectory(config);
  const id = randomUUID();
  const objectKey = databaseBackupObjectKey(id, new Date());
  const archivePath = backupFilePath(config, objectKey);
  await mkdir(dirname(archivePath), { recursive: true, mode: 0o700 });
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-storage-backup-"));
  const databasePath = join(directory, "bot.db");
  const objectsPath = join(directory, "objects");

  await query(
    "INSERT INTO bot_database_backups (id, object_key, sha256, size_bytes, created_by, status) " +
    "VALUES ($1,$2,$3,0,$4,'creating')",
    [id, objectKey, "0".repeat(64), createdBy],
  );

  try {
    await backupDatabase(databasePath);
    await openRocksDb(config.rocksDbPath);
    await createRocksCheckpoint(objectsPath);
    await runProcess("tar", ["-czf", archivePath, "-C", directory, "bot.db", "objects"]);
    await chmod(archivePath, 0o600);
    const file = await stat(archivePath);
    const digest = await hashFile(archivePath);
    await verifyArchive(archivePath, digest, file.size);
    await updateBackupStatus(id, "verified", digest, file.size);
    return await getBackup(id);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backup failure.";
    await rm(archivePath, { force: true }).catch(() => undefined);
    await updateBackupStatus(id, "failed", undefined, undefined, message).catch(() => undefined);
    throw error;
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

export async function verifyDatabaseBackup(id: string, config: BotConfig): Promise<DatabaseBackupRecord> {
  const backup = await getBackup(id);
  const archivePath = backupFilePath(config, backup.object_key);
  try {
    const size = Number(backup.size_bytes);
    if (!Number.isSafeInteger(size) || size < 1 || size > MAX_BACKUP_BYTES) {
      throw new Error("Backup size metadata is invalid.");
    }
    await verifyArchive(archivePath, backup.sha256, size);
    await updateBackupStatus(backup.id, "verified", backup.sha256, size);
    return await getBackup(id);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backup verification failure.";
    await updateBackupStatus(backup.id, "failed", undefined, undefined, message).catch(() => undefined);
    throw error;
  }
}

/** Extracts the snapshot to a disposable location and validates both native stores without touching the live paths. */
export async function rehearseDatabaseBackup(
  id: string,
  config: BotConfig,
): Promise<{ backupId: string; databaseName: string; tableCount: number }> {
  const backup = await getBackup(id);
  if (backup.status !== "verified") {
    throw new Error("Only a verified backup can be used for a restore rehearsal.");
  }
  const archivePath = backupFilePath(config, backup.object_key);
  try {
    const size = Number(backup.size_bytes);
    if (!Number.isSafeInteger(size) || size < 1 || size > MAX_BACKUP_BYTES) {
      throw new Error("Backup size metadata is invalid.");
    }
    const tableCount = await verifyArchive(archivePath, backup.sha256, size);
    await query(
      "UPDATE bot_database_backups SET rehearsal_status = 'passed', rehearsal_error = NULL, rehearsal_at = CURRENT_TIMESTAMP WHERE id = $1",
      [id],
    );
    return { backupId: id, databaseName: databaseRehearsalName(id), tableCount };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown restore rehearsal failure.";
    await query(
      "UPDATE bot_database_backups SET rehearsal_status = 'failed', rehearsal_error = $2, rehearsal_at = CURRENT_TIMESTAMP WHERE id = $1",
      [id, message.slice(0, 2_000)],
    ).catch(() => undefined);
    throw error;
  }
}

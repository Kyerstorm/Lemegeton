import { createRequire } from "node:module";
import { chmod, mkdir, lstat } from "node:fs/promises";
import { dirname, resolve } from "node:path";

interface RocksNativeStore {
  putObject(key: string, bytes: Buffer, metadata: string): Promise<void>;
  putChunk(key: string, index: number, bytes: Buffer): Promise<void>;
  finishObject(key: string, sizeBytes: number, chunkCount: number, metadata: string): Promise<void>;
  getObject(key: string): Promise<Buffer | null>;
  getObjectInfo(key: string): Promise<string | null>;
  readChunk(key: string, index: number): Promise<Buffer | null>;
  deleteObject(key: string): Promise<void>;
  createCheckpoint(path: string): Promise<void>;
  close(): void;
}

interface RocksNativeModule {
  RocksStore: new (path: string) => RocksNativeStore;
}

export interface RocksObjectInfo {
  sizeBytes: number;
  chunkCount: number;
  metadata: Record<string, unknown>;
}

const require = createRequire(resolve(process.cwd(), "package.json"));
const native = require(resolve(process.cwd(), "build/Release/lemegeton_rocksdb.node")) as RocksNativeModule;
const chunkSize = 1024 * 1024;
let instance: RocksNativeStore | undefined;
let activePath = "";

function safeKey(key: string): string {
  if (!key || key.length > 512 || key.startsWith("/") || key.split("/").some(part => !part || part === "." || part === "..")) {
    throw new Error("The RocksDB object key is invalid.");
  }
  return key;
}

export async function openRocksDb(path: string): Promise<void> {
  const target = resolve(path);
  if (instance && activePath === target) return;
  if (instance) {
    instance.close();
    instance = undefined;
  }
  await mkdir(dirname(target), { recursive: true, mode: 0o700 });
  await mkdir(target, { recursive: true, mode: 0o700 });
  const details = await lstat(target);
  if (details.isSymbolicLink() || !details.isDirectory()) {
    throw new Error("ROCKSDB_PATH must be a real directory.");
  }
  await chmod(target, 0o700);
  instance = new native.RocksStore(target);
  activePath = target;
}

function store(): RocksNativeStore {
  if (!instance) throw new Error("RocksDB has not been opened. Configure media storage before accessing objects.");
  return instance;
}

export async function putRocksObject(
  key: string,
  bytes: Buffer,
  metadata: Record<string, unknown>,
): Promise<void> {
  const target = safeKey(key);
  if (!Buffer.isBuffer(bytes) || bytes.length < 1 || bytes.length > 256 * 1024 * 1024) {
    throw new Error("RocksDB objects must contain between 1 byte and 256 MB.");
  }
  const chunks = Math.ceil(bytes.length / chunkSize);
  const encoded = JSON.stringify(metadata);
  try {
    for (let index = 0; index < chunks; index += 1) {
      await store().putChunk(target, index, bytes.subarray(index * chunkSize, Math.min(bytes.length, (index + 1) * chunkSize)));
    }
    await store().finishObject(target, bytes.length, chunks, encoded);
  } catch (error) {
    await store().deleteObject(target).catch(() => undefined);
    throw error;
  }
}

export async function putRocksObjectStream(
  key: string,
  source: AsyncIterable<Uint8Array>,
  metadata: Record<string, unknown>,
  maximumBytes = 256 * 1024 * 1024,
): Promise<{ sizeBytes: number; sha256: string }> {
  const target = safeKey(key);
  const { createHash } = await import("node:crypto");
  const digest = createHash("sha256");
  let pending = Buffer.alloc(0);
  let size = 0;
  let index = 0;
  const writeChunk = async (chunk: Buffer) => {
    await store().putChunk(target, index, chunk);
    index += 1;
  };

  try {
    for await (const piece of source) {
      const bytes = Buffer.from(piece);
      size += bytes.length;
      if (size > maximumBytes) throw new Error("The streamed RocksDB object exceeds its configured size limit.");
      digest.update(bytes);
      pending = pending.length ? Buffer.concat([pending, bytes]) : bytes;
      while (pending.length >= chunkSize) {
        await writeChunk(pending.subarray(0, chunkSize));
        pending = pending.subarray(chunkSize);
      }
    }
    if (!size) throw new Error("The streamed RocksDB object is empty.");
    if (pending.length) await writeChunk(pending);
    await store().finishObject(target, size, index, JSON.stringify(metadata));
    return { sizeBytes: size, sha256: digest.digest("hex") };
  } catch (error) {
    await store().deleteObject(target).catch(() => undefined);
    throw error;
  }
}

export async function getRocksObjectInfo(key: string): Promise<RocksObjectInfo | null> {
  const raw = await store().getObjectInfo(safeKey(key));
  if (raw === null) return null;
  let parsed: { sizeBytes?: unknown; chunkCount?: unknown; metadata?: unknown };
  try {
    parsed = JSON.parse(raw) as typeof parsed;
  } catch {
    throw new Error("RocksDB object metadata is corrupt.");
  }
  if (!Number.isSafeInteger(parsed.sizeBytes) || Number(parsed.sizeBytes) < 1
    || !Number.isInteger(parsed.chunkCount) || Number(parsed.chunkCount) < 1
    || Number(parsed.chunkCount) > 256
    || parsed.metadata === null || typeof parsed.metadata !== "object" || Array.isArray(parsed.metadata)) {
    throw new Error("RocksDB object metadata is incomplete.");
  }
  return {
    sizeBytes: Number(parsed.sizeBytes),
    chunkCount: Number(parsed.chunkCount),
    metadata: parsed.metadata as Record<string, unknown>,
  };
}

export async function* readRocksObjectStream(key: string): AsyncGenerator<Buffer> {
  const target = safeKey(key);
  const info = await getRocksObjectInfo(target);
  if (!info) return;
  let total = 0;
  for (let index = 0; index < info.chunkCount; index += 1) {
    const chunk = await store().readChunk(target, index);
    if (!chunk || chunk.length < 1 || chunk.length > chunkSize) {
      throw new Error("A RocksDB object chunk is missing or invalid.");
    }
    total += chunk.length;
    yield chunk;
  }
  if (total !== info.sizeBytes) throw new Error("RocksDB object size does not match its metadata.");
}

export async function getRocksObject(key: string): Promise<Buffer | null> {
  const parts: Buffer[] = [];
  for await (const chunk of readRocksObjectStream(key)) parts.push(chunk);
  return parts.length ? Buffer.concat(parts) : null;
}

export async function createRocksCheckpoint(path: string): Promise<void> {
  const target = resolve(path);
  await mkdir(dirname(target), { recursive: true, mode: 0o700 });
  const details = await lstat(target).catch(error => {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  });
  if (details) throw new Error("The RocksDB checkpoint destination already exists.");
  await store().createCheckpoint(target);
}

export async function deleteRocksObject(key: string): Promise<void> {
  await store().deleteObject(safeKey(key));
}

export function closeRocksDb(): void {
  instance?.close();
  instance = undefined;
  activePath = "";
}

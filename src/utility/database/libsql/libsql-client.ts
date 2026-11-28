import { createRequire } from "node:module";
import { resolve } from "node:path";
import { toLibSqlSql } from "./sql.js";

interface NativeResult {
  rows: Record<string, unknown>[];
  rowCount: number;
  lastInsertRowid: string;
}

interface NativeStorage {
  openDatabase(path: string): Promise<void>;
  integrityCheck(): Promise<string>;
  backupDatabase(path: string): Promise<void>;
  inspectDatabase(path: string): Promise<string>;
  executeBatch(sql: string): Promise<void>;
  queryDatabase(sql: string, params: string): Promise<string>;
  beginTransaction(): Promise<string>;
  queryTransaction(id: string, sql: string, params: string): Promise<string>;
  commitTransaction(id: string): Promise<void>;
  rollbackTransaction(id: string): Promise<void>;
}

const require = createRequire(resolve(process.cwd(), "package.json"));
const native = require(resolve(process.cwd(), "build/Release/lemegeton_storage.node")) as NativeStorage;

export interface DatabaseQueryResult<T> {
  rows: T[];
  rowCount: number;
  lastInsertRowid: string;
}

export interface DatabaseConnection {
  query<T = Record<string, unknown>>(sql: string, values?: readonly unknown[]): Promise<DatabaseQueryResult<T>>;
  release(): void;
}

function encodeParams(values: readonly unknown[]): string {
  return JSON.stringify(values.map(value => {
    if (value instanceof Date) return value.toISOString().replace("T", " ").replace("Z", "");
    if (Buffer.isBuffer(value)) return { $blob: [...value] };
    if (typeof value === "bigint") return value.toString();
    return value;
  }));
}

function decodeValue(value: unknown, column: string): unknown {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const tagged = value as { $blob?: unknown };
    if (Array.isArray(tagged.$blob)) return Buffer.from(tagged.$blob as number[]);
  }
  if (typeof value === "string" && (column.endsWith("_at") || column.endsWith("_date") || column === "until" || column === "next_airing_at")) {
    const normalized = value.includes("T") ? value : value.replace(" ", "T") + "Z";
    const date = new Date(normalized);
    if (Number.isFinite(date.getTime())) return date;
  }
  return value;
}

function decodeResult<T>(raw: string): DatabaseQueryResult<T> {
  const result = JSON.parse(raw) as NativeResult;
  const rows = result.rows.map(row => Object.fromEntries(
    Object.entries(row).map(([key, value]) => [key, decodeValue(value, key)]),
  )) as T[];
  return { rows, rowCount: result.rowCount, lastInsertRowid: result.lastInsertRowid };
}

export async function openLibSql(path: string): Promise<void> {
  await native.openDatabase(path);
}

export interface LibSqlInspection {
  integrity: string;
  tableCount: number;
}

export async function backupLibSqlDatabase(path: string): Promise<void> {
  await native.backupDatabase(path);
}

export async function inspectLibSqlDatabase(path: string): Promise<LibSqlInspection> {
  return JSON.parse(await native.inspectDatabase(path)) as LibSqlInspection;
}

export async function libSqlIntegrityCheck(): Promise<string> {
  return native.integrityCheck();
}

export async function libSqlExecuteBatch(sql: string): Promise<void> {
  await native.executeBatch(sql);
}

async function queryNative<T>(
  sql: string,
  values: readonly unknown[],
  transactionId?: string,
): Promise<DatabaseQueryResult<T>> {
  const translated = toLibSqlSql(sql);
  const params = encodeParams(values);
  const raw = transactionId
    ? await native.queryTransaction(transactionId, translated, params)
    : await native.queryDatabase(translated, params);
  return decodeResult<T>(raw);
}

export async function libSqlQuery<T = Record<string, unknown>>(
  sql: string,
  values: readonly unknown[] = [],
): Promise<DatabaseQueryResult<T>> {
  return queryNative<T>(sql, values);
}

export async function libSqlTransaction<T>(
  operation: (client: DatabaseConnection) => Promise<T>,
): Promise<T> {
  const id = await native.beginTransaction();
  const client: DatabaseConnection = {
    query: <Row = Record<string, unknown>>(sql: string, values: readonly unknown[] = []) =>
      queryNative<Row>(sql, values, id),
    release: () => undefined,
  };

  try {
    const value = await operation(client);
    await native.commitTransaction(id);
    return value;
  } catch (error) {
    await native.rollbackTransaction(id).catch(() => undefined);
    throw error;
  }
}

export async function applyLibSqlSchemaStatement(
  source: string,
  database?: DatabaseConnection,
): Promise<void> {
  // The legacy schema list also contains PostgreSQL-only DO blocks for conditional constraints.
  // libSQL cannot execute PL/pgSQL; equivalent constraints belong in the CREATE TABLE definitions.
  if (/^\s*DO\s+\$[A-Za-z_][A-Za-z0-9_]*\$/i.test(source)) return;

  const sql = toLibSqlSql(source, true).replace(/;$/, "");
  if (!sql || /^ALTER TABLE .* (?:DROP CONSTRAINT|ADD CONSTRAINT|ALTER COLUMN)\b/i.test(sql)) return;

  const execute = async <T = Record<string, unknown>>(statement: string) =>
    database ? database.query<T>(statement) : libSqlQuery<T>(statement);

  const addColumn = sql.match(/^ALTER TABLE ([A-Za-z_][A-Za-z0-9_]*) ADD COLUMN ([A-Za-z_][A-Za-z0-9_]*)\b/i);
  if (addColumn) {
    const [, table, column] = addColumn;
    const info = await execute<{ name: string }>("PRAGMA table_info(" + JSON.stringify(table) + ")");
    if (info.rows.some(row => row.name === column)) return;
  }

  await execute(sql);
}

export const libSqlNative = native;

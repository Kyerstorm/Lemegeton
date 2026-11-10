import { createHash, randomBytes, randomUUID } from "node:crypto";
import type { QueryResultRow } from "pg";
import { queryOne } from "../../database.js";

export const ISSUE_REFERENCE_LENGTH = 40;
const ISSUE_HASH_PATTERN = /^[a-f0-9]{40}$/i;
const REDACTED = "[REDACTED]";
const MAX_DEPTH = 8;
const MAX_NODES = 1_200;
const MAX_STRING_LENGTH = 12_000;
const MAX_TOTAL_CHARACTERS = 48_000;
const MAX_ITEMS = 100;

export interface IssueLogInput {
  guildId: string; userId: string; username: string; interactionId: string;
  channelId: string | null; command: string; details: Record<string, unknown>; error: unknown;
}
export interface IssueLogRecord extends QueryResultRow {
  issue_hash: string; guild_id: string; user_id: string; username: string;
  interaction_id: string; channel_id: string | null; command_name: string;
  details: Record<string, unknown>; created_at: Date | string;
}
export interface IssueInteractionContext {
  id: string; guildId: string | null;
  user: { id: string; username: string; globalName?: string | null };
  channelId: string | null;
}
interface Budget { nodes: number; characters: number }

function safeString(value: unknown): string {
  try { return String(value); } catch { return "[Unserializable value]"; }
}
function redactString(value: string): string {
  return value
    .replace(/(Bot\s+)[A-Za-z0-9._-]{20,}/gi, "$1" + REDACTED)
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/-]{12,}/gi, "$1" + REDACTED)
    .replace(/(\b(?:token|password|secret|api[_-]?key|authorization|cookie|client[_-]?secret)\b\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, "$1" + REDACTED)
    .replace(/([?&](?:access_token|refresh_token|token|api_key|key|password|secret)=)[^&#\s]*/gi, "$1" + REDACTED)
    .replace(/\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{16})\b/g, REDACTED);
}
function isSensitiveKey(key: string): boolean {
  return /(?:token|password|secret|api[_-]?key|authorization|cookie)/i.test(key);
}
function bounded(value: string, budget: Budget): string {
  const remaining = MAX_TOTAL_CHARACTERS - budget.characters;
  if (remaining <= 0) return "[Diagnostic text limit reached]";
  const text = value.slice(0, Math.min(MAX_STRING_LENGTH, remaining));
  budget.characters += text.length;
  return text.length < value.length ? text + "… [truncated]" : text;
}
function sanitize(
  value: unknown, key: string, depth: number, seen: WeakSet<object>, budget: Budget,
): unknown {
  if (isSensitiveKey(key)) return REDACTED;
  budget.nodes += 1;
  if (budget.nodes > MAX_NODES) return "[Diagnostic item limit reached]";
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") return bounded(redactString(value), budget);
  if (typeof value === "number") return Number.isFinite(value) ? value : safeString(value);
  if (typeof value === "bigint" || typeof value === "symbol") return bounded(safeString(value), budget);
  if (typeof value === "undefined") return "[undefined]";
  if (typeof value === "function") return "[Function]";
  if (depth >= MAX_DEPTH) return "[Maximum diagnostic depth reached]";
  if (typeof value !== "object") return bounded(safeString(value), budget);
  if (seen.has(value)) return "[Circular reference]";
  seen.add(value);
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? "Invalid Date" : value.toISOString();
  if (ArrayBuffer.isView(value)) return "[Binary data omitted]";
  if (Array.isArray(value)) return value.slice(0, MAX_ITEMS).map(item => sanitize(item, "", depth + 1, seen, budget));
  let entries: Array<[string, unknown]>;
  try { entries = Object.entries(value as Record<string, unknown>).slice(0, MAX_ITEMS); }
  catch { return "[Unserializable object]"; }
  let namedField = "";
  try {
    const record = value as Record<string, unknown>;
    namedField = String(record.name ?? record.key ?? "");
  } catch { /* Ignore inaccessible metadata fields. */ }
  return Object.fromEntries(entries.map(([childKey, childValue]) => [
    bounded(childKey, budget),
    childKey === "value" && isSensitiveKey(namedField) ? REDACTED
      : sanitize(childValue, childKey, depth + 1, seen, budget),
  ]));
}
export function sanitizeIssueDetails(details: Record<string, unknown>): Record<string, unknown> {
  return sanitize(details, "", 0, new WeakSet<object>(), { nodes: 0, characters: 0 }) as Record<string, unknown>;
}
export function isIssueHash(value: string): boolean {
  return typeof value === "string" && ISSUE_HASH_PATTERN.test(value.trim());
}

/** Generate a fixed 160-bit public reference using a domain-separated SHA-512 digest. */
export function createIssueHash(interactionId: string, userId = "", guildId = ""): string {
  const digest = createHash("sha512");
  digest.update("lemegeton:diagnostic-reference:v1\0");
  digest.update("entropy\0").update(randomBytes(64));
  const frame = (label: string, value: string): void => {
    const bytes = Buffer.from(value, "utf8");
    digest.update(label).update("\0").update(String(bytes.length)).update("\0").update(bytes).update("\0");
  };
  frame("uuid", randomUUID());
  frame("interaction", interactionId);
  frame("user", userId);
  frame("guild", guildId);
  return digest.digest("hex").slice(0, ISSUE_REFERENCE_LENGTH);
}
export function serializeIssueError(error: unknown, seen = new WeakSet<object>(), depth = 0): Record<string, unknown> {
  if (depth >= 6) return { name: "Error", message: "[Maximum error cause depth reached]", stack: null };
  if (error === null || (typeof error !== "object" && typeof error !== "function")) {
    return { name: "UnknownError", message: safeString(error), stack: null };
  }
  if (seen.has(error as object)) return { name: "Error", message: "[Circular error cause]", stack: null };
  seen.add(error as object);
  const value = error as Error & { code?: unknown; status?: unknown; cause?: unknown; errors?: unknown };
  const result: Record<string, unknown> = {
    name: typeof value.name === "string" ? value.name : "UnknownError",
    message: typeof value.message === "string" ? value.message : safeString(error),
    stack: typeof value.stack === "string" ? value.stack : null,
  };
  if (typeof value.code === "string" || typeof value.code === "number") result.code = value.code;
  if (typeof value.status === "string" || typeof value.status === "number") result.status = value.status;
  if (value.cause !== undefined) result.cause = serializeIssueError(value.cause, seen, depth + 1);
  if (Array.isArray(value.errors)) result.errors = value.errors.slice(0, 10).map(item => serializeIssueError(item, seen, depth + 1));
  return result;
}
export function issueHashNotice(hash: string): string {
  return "Issue reference: " + String.fromCharCode(96) + hash + String.fromCharCode(96) +
    ". Include this reference in /feedback so a moderator can inspect the diagnostic record with /log.";
}
export async function createIssueLog(input: IssueLogInput): Promise<string> {
  const details = sanitizeIssueDetails({ ...input.details, error: serializeIssueError(input.error) });
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const issueHash = createIssueHash(input.interactionId, input.userId, input.guildId);
    const inserted = await queryOne<{ issue_hash: string }>(
      "INSERT INTO issue_logs\n" +
      " (issue_hash, guild_id, user_id, username, interaction_id, channel_id, command_name, details)\n" +
      " VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)\n" +
      " ON CONFLICT (issue_hash) DO NOTHING\n" +
      " RETURNING issue_hash",
      [issueHash, input.guildId, input.userId, input.username.slice(0, 120),
        input.interactionId, input.channelId, input.command.slice(0, 100), JSON.stringify(details)],
    );
    if (inserted) return inserted.issue_hash;
  }
  throw new Error("A unique issue reference could not be allocated after repeated collision retries.");
}
export async function createInteractionIssueLog(
  interaction: IssueInteractionContext, command: string, error: unknown, details: Record<string, unknown> = {},
): Promise<string | null> {
  if (!interaction.guildId) return null;
  const message = (interaction as IssueInteractionContext & { message?: { id?: string } | null }).message;
  const messageId = typeof message?.id === "string" ? message.id : null;
  try {
    return await createIssueLog({
      guildId: interaction.guildId, userId: interaction.user.id,
      username: interaction.user.globalName ?? interaction.user.username,
      interactionId: interaction.id, channelId: interaction.channelId, command,
      details: { ...details, ...(messageId ? { messageId } : {}), interactionId: interaction.id, guildId: interaction.guildId, channelId: interaction.channelId },
      error,
    });
  } catch { return null; }
}
export async function findIssueLog(issueHash: string, guildId?: string): Promise<IssueLogRecord | null> {
  if (!isIssueHash(issueHash)) return null;
  const normalizedHash = issueHash.trim().toLowerCase();
  return queryOne<IssueLogRecord>(
    "SELECT issue_hash, guild_id, user_id, username, interaction_id, channel_id, command_name, details, created_at " +
    "FROM issue_logs WHERE issue_hash = $1" + (guildId ? " AND guild_id = $2" : ""),
    guildId ? [normalizedHash, guildId] : [normalizedHash],
  );
}
export function serializeIssueLogRecord(record: IssueLogRecord): string {
  return JSON.stringify({
    issueReference: record.issue_hash,
    occurredAt: record.created_at instanceof Date ? record.created_at.toISOString() : record.created_at,
    command: record.command_name, guildId: record.guild_id,
    user: { id: record.user_id, username: record.username },
    channelId: record.channel_id, interactionId: record.interaction_id,
    details: sanitizeIssueDetails(record.details ?? {}),
  }, null, 2);
}

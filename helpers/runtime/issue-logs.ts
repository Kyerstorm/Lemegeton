import { createHash, randomBytes, randomUUID } from "node:crypto";
import type { QueryResultRow } from "pg";
import { query, queryOne } from "../../database.js";

const ISSUE_HASH_PATTERN = /^(?:[a-f0-9]{40}|[a-f0-9]{128})$/i;
const REDACTED = "[REDACTED]";

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
  id: string;
  guildId: string | null;
  user: { id: string; username: string; globalName?: string | null };
  channelId: string | null;
}
function redactString(value: string): string {
  return value
    .replace(/(Bot\s+)[A-Za-z0-9._-]{20,}/gi, `$1${REDACTED}`)
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi, `$1${REDACTED}`)
    .replace(/((?:token|password|secret|api[_-]?key|authorization)\s*[:=]\s*)[^\s,;]+/gi, `$1${REDACTED}`);
}
function isSensitiveKey(key: string): boolean {
  return /(?:token|password|secret|api[_-]?key|authorization|cookie)/i.test(key);
}
function redactValue(value: unknown, key = ""): unknown {
  if (isSensitiveKey(key)) return REDACTED;
  if (typeof value === "string") return redactString(value).slice(0, 12_000);
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => redactValue(item));
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const namedField = String(record.name ?? record.key ?? "");
    return Object.fromEntries(Object.entries(record).slice(0, 100).map(([childKey, childValue]) => [
      childKey, childKey === "value" && isSensitiveKey(namedField) ? REDACTED : redactValue(childValue, childKey),
    ]));
  }
  if (typeof value === "bigint") return value.toString();
  return value;
}
export function sanitizeIssueDetails(details: Record<string, unknown>): Record<string, unknown> {
  return redactValue(details) as Record<string, unknown>;
}
export function isIssueHash(value: string): boolean { return ISSUE_HASH_PATTERN.test(value.trim()); }

/** A 40-character reference seeded with 256 bits of cryptographic randomness. */
export function createIssueHash(interactionId: string, userId = ""): string {
  return createHash("sha1")
    .update(randomBytes(32))
    .update(randomUUID())
    .update(interactionId)
    .update(userId)
    .digest("hex");
}
export function issueHashNotice(hash: string): string {
  return `Issue reference: \`${hash}\`. Include this reference in /feedback so a moderator can inspect the diagnostic record with /log.`;
}
export async function createIssueLog(input: IssueLogInput): Promise<string> {
  const error = input.error instanceof Error
    ? { name: input.error.name, message: input.error.message, stack: input.error.stack ?? null }
    : { name: "UnknownError", message: String(input.error), stack: null };
  const details = sanitizeIssueDetails({ ...input.details, error });
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const issueHash = createIssueHash(input.interactionId, input.userId);
    const inserted = await queryOne<{ issue_hash: string }>(
      `INSERT INTO issue_logs
        (issue_hash, guild_id, user_id, username, interaction_id, channel_id, command_name, details)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
       ON CONFLICT (issue_hash) DO NOTHING
       RETURNING issue_hash`,
      [issueHash, input.guildId, input.userId, input.username.slice(0, 120),
        input.interactionId, input.channelId, input.command.slice(0, 100), JSON.stringify(details)],
    );
    if (inserted) return inserted.issue_hash;
  }
  throw new Error("A unique issue reference could not be allocated after repeated collision retries.");
}
export async function createInteractionIssueLog(
  interaction: IssueInteractionContext,
  command: string,
  error: unknown,
  details: Record<string, unknown> = {},
): Promise<string | null> {
  if (!interaction.guildId) return null;
  try {
    return await createIssueLog({
      guildId: interaction.guildId,
      userId: interaction.user.id,
      username: interaction.user.globalName ?? interaction.user.username,
      interactionId: interaction.id,
      channelId: interaction.channelId,
      command,
      details: { ...details, interactionId: interaction.id, guildId: interaction.guildId, channelId: interaction.channelId },
      error,
    });
  } catch {
    return null;
  }
}
export async function findIssueLog(issueHash: string, guildId: string): Promise<IssueLogRecord | null> {
  if (!isIssueHash(issueHash)) return null;
  return queryOne<IssueLogRecord>(
    `SELECT issue_hash, guild_id, user_id, username, interaction_id, channel_id,
            command_name, details, created_at
       FROM issue_logs WHERE issue_hash = $1 AND guild_id = $2`,
    [issueHash.trim().toLowerCase(), guildId],
  );
}

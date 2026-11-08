import { createHash, randomBytes, randomUUID } from "node:crypto";
import type { Interaction } from "discord.js";
import { query, queryOne } from "../database.js";
import { logger } from "./logger.js";

export interface CreatedIssue {
  hash: string;
  persisted: boolean;
}

export interface IssueLogRow {
  [column: string]: unknown;
  issue_hash: string;
  uuid_hash: string;
  guild_id: string | null;
  user_id: string;
  created_at: Date | string;
  details: Record<string, unknown>;
}

let schemaPromise: Promise<void> | undefined;

function ensureIssueLogSchema(): Promise<void> {
  schemaPromise ??= query(
    `CREATE TABLE IF NOT EXISTS issue_logs (
      issue_hash CHAR(128) PRIMARY KEY,
      uuid_hash CHAR(128) NOT NULL,
      guild_id BIGINT,
      user_id BIGINT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      details JSONB NOT NULL
    )`,
  ).then(async () => {
    await query("CREATE INDEX IF NOT EXISTS issue_logs_guild_created_idx ON issue_logs (guild_id, created_at DESC)");
  }).catch((error: unknown) => {
    schemaPromise = undefined;
    throw error;
  });
  return schemaPromise;
}

export async function initializeIssueLogs(): Promise<void> {
  await ensureIssueLogSchema();
}

function redact(value: unknown, key = ""): unknown {
  if (/token|password|secret|authorization|api[_-]?key/i.test(key)) return "[REDACTED]";
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => redact(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .slice(0, 100)
        .map(([childKey, childValue]) => [childKey, redact(childValue, childKey)]),
    );
  }
  if (typeof value === "string") {
    return value
      .replace(/(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, "$1=[REDACTED]")
      .slice(0, 12_000);
  }
  return value;
}

function interactionContext(interaction: Interaction): Record<string, unknown> {
  const commandName = interaction.isChatInputCommand() || interaction.isAutocomplete()
    ? interaction.commandName
    : undefined;
  const options = interaction.isChatInputCommand() || interaction.isAutocomplete()
    ? redact(interaction.options.data)
    : undefined;
  const customId = "customId" in interaction ? interaction.customId : undefined;

  return {
    interactionId: interaction.id,
    interactionType: interaction.type,
    commandName,
    customId,
    guildId: interaction.guildId,
    channelId: interaction.channelId,
    userId: interaction.user.id,
    username: interaction.user.username,
    options,
  };
}

/**
 * Store one independently searchable issue record for an interaction failure.
 * The public identifier is a random SHA-512 digest; the UUID is separately
 * hashed and retained for internal correlation without exposing the UUID.
 */
export async function createIssueLog(
  interaction: Interaction,
  error: unknown,
  event = "interaction",
): Promise<CreatedIssue> {
  const uuid = randomUUID();
  const uuidHash = createHash("sha512").update(uuid).digest("hex");
  const hash = createHash("sha512")
    .update(randomBytes(64))
    .update(uuidHash)
    .update(interaction.id)
    .digest("hex");
  const thrown = error instanceof Error
    ? { name: error.name, message: error.message, stack: error.stack }
    : { name: "UnknownError", message: String(error), stack: undefined };
  const details = redact({
    event,
    occurredAt: new Date().toISOString(),
    interaction: interactionContext(interaction),
    error: thrown,
  }) as Record<string, unknown>;

  try {
    await ensureIssueLogSchema();
    await query(
      `INSERT INTO issue_logs (issue_hash, uuid_hash, guild_id, user_id, details)
       VALUES ($1, $2, $3, $4, $5::jsonb)`,
      [hash, uuidHash, interaction.guildId, interaction.user.id, JSON.stringify(details)],
    );
    return { hash, persisted: true };
  } catch (persistError) {
    logger.error("Could not persist interaction issue log", {
      interactionId: interaction.id,
      reason: persistError instanceof Error ? persistError.message : "Unknown database error",
    });
    return { hash, persisted: false };
  }
}

export async function findIssueLog(hash: string, guildId: string): Promise<IssueLogRow | null> {
  await ensureIssueLogSchema();
  return queryOne<IssueLogRow>(
    `SELECT issue_hash, uuid_hash, guild_id::text, user_id::text, created_at, details
     FROM issue_logs
     WHERE issue_hash = $1 AND guild_id = $2`,
    [hash.toLowerCase(), guildId],
  );
}

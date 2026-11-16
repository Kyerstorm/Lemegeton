import { createHash } from "node:crypto";
import { query, queryOne, transaction } from "../../database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export type MediaAutomationCategory = "anime" | "tv" | "movies";
export type MediaAutomationAction = "announce" | "discussion";

const CATEGORIES = new Set<MediaAutomationCategory>(["anime", "tv", "movies"]);

export function normalizeMediaAutomationCategories(value: string | readonly string[]): MediaAutomationCategory[] {
  const rawValues = typeof value === "string" ? value.split(",") : [...value];
  const values = rawValues.map(item => item.trim().toLowerCase())
    .filter(Boolean);
  const categories = [...new Set(values)];
  if (!categories.length || categories.some(item => !CATEGORIES.has(item as MediaAutomationCategory))) {
    throw new Error("Choose one or more supported categories: anime, tv or movies.");
  }
  return categories as MediaAutomationCategory[];
}

export function mediaAutomationEventKey(release: { title: string; provider: string; url: string; when: Date }): string {
  if (!Number.isFinite(release.when.getTime())) throw new Error("The release date is invalid.");
  return createHash("sha256")
    .update(JSON.stringify([release.provider, release.url, release.title, release.when.toISOString()]))
    .digest("hex");
}

export interface MediaAutomationRule {
  id: string;
  guild_id: string;
  name: string;
  channel_id: string;
  categories: MediaAutomationCategory[];
  region: string;
  action: MediaAutomationAction;
  enabled: boolean;
  claim_token: string;
}

export interface MediaAutomationDelivery {
  id: string;
  guild_id: string;
  channel_id: string;
  rule_name: string;
  action: MediaAutomationAction;
  event_key: string;
  title: string;
  provider: string;
  source_url: string;
  release_at: Date;
  discussion_id: string | null;
  claim_token: string;
}

export async function listMediaAutomationRules(guildId: string): Promise<Array<{
  id: string; name: string; channel_id: string; categories: MediaAutomationCategory[];
  region: string; action: MediaAutomationAction; enabled: boolean; next_check_at: Date;
}>> {
  return query(
    "SELECT id::text, name, channel_id::text, categories, region, action, enabled, next_check_at " +
    "FROM community_media_automation_rules WHERE guild_id = $1 ORDER BY created_at DESC LIMIT 20",
    [guildId],
  );
}

export async function saveMediaAutomationRule(input: {
  guildId: string;
  actorId: string;
  name: string;
  channelId: string;
  categories: string | readonly string[];
  region: string;
  action: string;
}): Promise<void> {
  const name = cleanText(input.name, 100);
  const categories = normalizeMediaAutomationCategories(input.categories);
  const region = input.region.trim().toUpperCase();
  const action = input.action.trim().toLowerCase();
  if (!name) throw new Error("An automation rule name is required.");
  if (!/^\d{17,20}$/.test(input.guildId) || !/^\d{17,20}$/.test(input.channelId)) {
    throw new Error("Choose a valid server and destination channel.");
  }
  if (!/^[A-Z]{2}$/.test(region)) throw new Error("Use a two-letter country code such as IE or US.");
  if (action !== "announce" && action !== "discussion") throw new Error("Choose announce or discussion.");
  await query(
    "INSERT INTO community_media_automation_rules (guild_id, name, channel_id, categories, region, action, created_by) " +
    "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (guild_id, name) DO UPDATE SET " +
    "channel_id = EXCLUDED.channel_id, categories = EXCLUDED.categories, region = EXCLUDED.region, " +
    "action = EXCLUDED.action, enabled = TRUE, next_check_at = NOW(), claim_until = NULL, claim_token = NULL, updated_at = NOW()",
    [input.guildId, name, input.channelId, categories, region, action, input.actorId],
  );
}

export async function toggleMediaAutomationRule(guildId: string, ruleId: string): Promise<boolean> {
  const row = await queryOne<{ enabled: boolean }>(
    "UPDATE community_media_automation_rules SET enabled = NOT enabled, next_check_at = NOW(), " +
    "claim_until = NULL, claim_token = NULL, updated_at = NOW() WHERE id = $1 AND guild_id = $2 RETURNING enabled",
    [ruleId, guildId],
  );
  if (!row) throw new Error("That automation rule was not found in this server.");
  return row.enabled;
}

export async function claimDueMediaAutomationRules(): Promise<MediaAutomationRule[]> {
  return query<MediaAutomationRule>(
    "WITH due AS (SELECT id FROM community_media_automation_rules " +
    "WHERE enabled = TRUE AND next_check_at <= NOW() AND (claim_until IS NULL OR claim_until <= NOW()) " +
    "ORDER BY next_check_at, id LIMIT 20 FOR UPDATE SKIP LOCKED) " +
    "UPDATE community_media_automation_rules r SET claim_until = NOW() + INTERVAL '10 minutes', " +
    "claim_token = gen_random_uuid()::text, next_check_at = NOW() " +
    "FROM due WHERE r.id = due.id " +
    "RETURNING r.id::text, r.guild_id::text, r.name, r.channel_id::text, r.categories, r.region, r.action, r.enabled, r.claim_token",
    [],
  );
}

export async function releaseMediaAutomationRuleClaim(rule: MediaAutomationRule, retrySoon = false): Promise<void> {
  await query(
    "UPDATE community_media_automation_rules SET claim_until = NULL, claim_token = NULL, " +
    "next_check_at = NOW() + CASE WHEN $4 THEN INTERVAL '15 minutes' ELSE INTERVAL '1 hour' END, updated_at = NOW() " +
    "WHERE id = $1 AND guild_id = $2 AND claim_token = $3",
    [rule.id, rule.guild_id, rule.claim_token, retrySoon],
  );
}

export async function queueMediaAutomationRelease(
  rule: MediaAutomationRule,
  release: { title: string; when: Date; provider: string; url: string },
): Promise<boolean> {
  const title = cleanText(release.title, 240);
  const url = isValidHttpsUrl(release.url);
  if (!title || !url || !Number.isFinite(release.when.getTime())) return false;
  const eventKey = mediaAutomationEventKey({ ...release, url });
  const row = await queryOne<{ id: string }>(
    "INSERT INTO community_media_automation_deliveries " +
    "(rule_id, guild_id, event_key, title, provider, source_url, release_at) " +
    "SELECT id, guild_id, $3, $4, $5, $6, $7 FROM community_media_automation_rules " +
    "WHERE id = $1 AND guild_id = $2 AND claim_token = $8 AND enabled = TRUE " +
    "ON CONFLICT (rule_id, event_key) DO NOTHING RETURNING id::text",
    [rule.id, rule.guild_id, eventKey, title, cleanText(release.provider, 64), url, release.when, rule.claim_token],
  );
  return row !== null;
}

export async function claimDueMediaAutomationDeliveries(): Promise<MediaAutomationDelivery[]> {
  return query<MediaAutomationDelivery>(
    "WITH due AS (SELECT d.id FROM community_media_automation_deliveries d " +
    "JOIN community_media_automation_rules r ON r.id = d.rule_id AND r.enabled = TRUE " +
    "WHERE d.status IN ('pending','processing') AND d.next_attempt_at <= NOW() " +
    "AND (d.claim_until IS NULL OR d.claim_until <= NOW()) " +
    "ORDER BY d.next_attempt_at, d.id LIMIT 30 FOR UPDATE OF d SKIP LOCKED), " +
    "claimed AS (UPDATE community_media_automation_deliveries d SET status = 'processing', " +
    "claim_until = NOW() + INTERVAL '10 minutes', claim_token = gen_random_uuid()::text " +
    "FROM due WHERE d.id = due.id RETURNING d.*) " +
    "SELECT d.id::text, d.guild_id::text, r.channel_id::text, r.name AS rule_name, r.action, " +
    "d.event_key, d.title, d.provider, d.source_url, d.release_at, d.discussion_id::text, d.claim_token " +
    "FROM claimed d JOIN community_media_automation_rules r ON r.id = d.rule_id",
    [],
  );
}

export async function createMediaAutomationDiscussion(input: {
  delivery: MediaAutomationDelivery;
  creatorId: string;
}): Promise<string> {
  return transaction(async client => {
    const locked = await client.query<{ discussion_id: string | null }>(
      "SELECT discussion_id::text FROM community_media_automation_deliveries " +
      "WHERE id = $1 AND guild_id = $2 AND claim_token = $3 AND status = 'processing' FOR UPDATE",
      [input.delivery.id, input.delivery.guild_id, input.delivery.claim_token],
    );
    const existing = locked.rows[0]?.discussion_id;
    if (existing) return existing;
    if (!locked.rows[0]) throw new Error("The automation delivery claim expired.");
    const title = cleanText("Release discussion · " + input.delivery.title, 180);
    const prompt = cleanText(
      "This discussion was opened by the server's Media Automation Studio for a provider-dated release. " +
      "Share reactions and theories, and use Discord spoiler tags for details beyond the release boundary.",
      1_500,
    );
    const inserted = await client.query<{ id: string }>(
      "INSERT INTO community_discussions " +
      "(guild_id, channel_id, creator_id, title, prompt, media_title, media_url, spoiler_boundary, spoiler_warning) " +
      "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id::text AS id",
      [input.delivery.guild_id, input.delivery.channel_id, input.creatorId, title, prompt,
        cleanText(input.delivery.title, 200), isValidHttpsUrl(input.delivery.source_url),
        "Provider-dated release", "Mark later plot details with Discord spoiler tags."],
    );
    const discussionId = inserted.rows[0]?.id;
    if (!discussionId) throw new Error("The release discussion could not be created.");
    await client.query(
      "UPDATE community_media_automation_deliveries SET discussion_id = $1 " +
      "WHERE id = $2 AND guild_id = $3 AND claim_token = $4",
      [discussionId, input.delivery.id, input.delivery.guild_id, input.delivery.claim_token],
    );
    return discussionId;
  });
}

export async function markMediaAutomationDelivery(
  delivery: MediaAutomationDelivery,
  status: "sent" | "pending",
  messageId?: string,
  error?: string,
): Promise<void> {
  const current = await queryOne<{ attempts: number }>(
    "SELECT attempts FROM community_media_automation_deliveries " +
    "WHERE id = $1 AND guild_id = $2 AND claim_token = $3 AND status = 'processing'",
    [delivery.id, delivery.guild_id, delivery.claim_token],
  );
  if (!current) return;
  const attempts = current.attempts + (status === "pending" ? 1 : 0);
  const nextStatus = status === "pending" && attempts >= 6 ? "failed" : status;
  const retryMinutes = Math.min(60, Math.max(2, 2 ** attempts));
  await query(
    "UPDATE community_media_automation_deliveries SET status = $4, attempts = $5, " +
    "next_attempt_at = CASE WHEN $4 = 'pending' THEN NOW() + ($6 * INTERVAL '1 minute') ELSE next_attempt_at END, " +
    "message_id = COALESCE($7, message_id), last_error = $8, claim_until = NULL, claim_token = NULL " +
    "WHERE id = $1 AND guild_id = $2 AND claim_token = $3",
    [delivery.id, delivery.guild_id, delivery.claim_token, nextStatus, attempts, retryMinutes,
      messageId ?? null, error?.slice(0, 1_000) ?? null],
  );
}

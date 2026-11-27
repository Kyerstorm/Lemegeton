import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { randomUUID } from "node:crypto";
import { logger } from "../runtime/logger.js";
import { cleanText } from "../security/security.js";
import type { Client } from "discord.js";
import { EmbedBuilder as DiscordEmbedBuilder } from "discord.js";

export type CapsuleAudience = "owner" | "contributors" | "guild";
export type CapsuleStatus = "collecting" | "sealed" | "revealing" | "revealed" | "cancelled" | "failed";

export interface TimeCapsule {
  id: string;
  guild_id: string;
  owner_id: string;
  channel_id: string;
  title: string;
  description: string;
  release_at: string;
  audience: CapsuleAudience;
  status: CapsuleStatus;
  delivery_error: string | null;
  created_at: string;
  contribution_count: number;
}

export interface TimeCapsuleContribution {
  id: string;
  contributor_id: string;
  content: string;
  created_at: string;
}

interface DueCapsule {
  id: string;
  guild_id: string;
  owner_id: string;
  channel_id: string;
  title: string;
  description: string;
  audience: CapsuleAudience;
  claim_token: string;
}

const USER_ID_PATTERN = /^\d{17,20}$/;
let workerTimer: NodeJS.Timeout | undefined;
let workerPromise: Promise<void> | undefined;
let workerRunning = false;

function requiredText(value: string, maximum: number, label: string): string {
  const clean = cleanText(value, maximum);
  if (!clean) throw new Error(label + " is required.");
  return clean;
}

function parseFutureDate(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime()) || date.getTime() < Date.now() + 60_000) {
    throw new Error("Choose a valid release time at least one minute in the future.");
  }
  return date.toISOString();
}

export async function createTimeCapsule(input: {
  guildId: string;
  ownerId: string;
  channelId: string;
  title: string;
  description?: string;
  releaseAt: string;
  audience?: CapsuleAudience;
}): Promise<string> {
  if (!USER_ID_PATTERN.test(input.guildId) || !USER_ID_PATTERN.test(input.ownerId) || !USER_ID_PATTERN.test(input.channelId)) {
    throw new Error("A valid server, owner and destination channel are required.");
  }
  const title = requiredText(input.title, 180, "Capsule title");
  const description = cleanText(input.description, 800);
  const releaseAt = parseFutureDate(input.releaseAt);
  const audience = input.audience ?? "guild";
  if (!["owner", "contributors", "guild"].includes(audience)) throw new Error("Choose a valid capsule audience.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO time_capsules (guild_id,owner_id,channel_id,title,description,release_at,audience)
     VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id`,
    [input.guildId,input.ownerId,input.channelId,title,description,releaseAt,audience],
  );
  if (!row) throw new Error("The time capsule could not be created.");
  return row.id;
}

export async function listTimeCapsules(guildId: string, limit = 15, viewerId?: string): Promise<Array<{
  id: string; owner_id: string; title: string; release_at: string; audience: CapsuleAudience; status: CapsuleStatus; contribution_count: number;
}>> {
  return query(
    `SELECT c.id::text,c.owner_id::text,c.title,c.release_at,c.audience,c.status,
      (SELECT COUNT(*) FROM time_capsule_contributions x WHERE x.capsule_id=c.id AND x.guild_id=c.guild_id)::INT AS contribution_count
     FROM time_capsules c WHERE c.guild_id=$1 AND c.status IN ('collecting','sealed')
       AND (c.audience<>'owner' OR c.owner_id=$3)
     ORDER BY c.release_at ASC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit))),viewerId??""],
  );
}

export async function getTimeCapsule(guildId: string, capsuleId: string, viewerId?: string): Promise<{
  capsule: TimeCapsule;
  contributions: TimeCapsuleContribution[];
} | null> {
  const viewer = viewerId ?? "";
  const capsule = await queryOne<TimeCapsule>(
    `SELECT c.id::text,c.guild_id::text,c.owner_id::text,c.channel_id::text,c.title,
      CASE
        WHEN c.status='collecting' AND c.owner_id=$3 THEN c.description
        WHEN c.status='revealed' AND (c.audience='guild' OR c.owner_id=$3 OR
          (c.audience='contributors' AND EXISTS (SELECT 1 FROM time_capsule_contributions v WHERE v.capsule_id=c.id AND v.guild_id=c.guild_id AND v.contributor_id=$3))) THEN c.description
        ELSE ''
      END AS description,
      c.release_at,c.audience,c.status,
      CASE WHEN c.owner_id=$3 THEN c.delivery_error ELSE NULL END AS delivery_error,
      c.created_at,
      (SELECT COUNT(*) FROM time_capsule_contributions x WHERE x.capsule_id=c.id AND x.guild_id=c.guild_id)::INT AS contribution_count
     FROM time_capsules c WHERE c.id=$1 AND c.guild_id=$2 AND (c.audience<>'owner' OR c.owner_id=$3)`,
    [capsuleId,guildId,viewer],
  );
  if (!capsule) return null;
  const contributions = await query<TimeCapsuleContribution>(
    `SELECT x.id::text,x.contributor_id::text,
      CASE
        WHEN c.status='collecting' AND c.owner_id=$3 THEN x.content
        WHEN c.status='revealed' AND (c.audience='guild' OR c.owner_id=$3 OR
          (c.audience='contributors' AND EXISTS (SELECT 1 FROM time_capsule_contributions v WHERE v.capsule_id=c.id AND v.guild_id=c.guild_id AND v.contributor_id=$3))) THEN x.content
        ELSE ''
      END AS content,x.created_at
     FROM time_capsule_contributions x JOIN time_capsules c ON c.id=x.capsule_id AND c.guild_id=x.guild_id
     WHERE x.capsule_id=$1 AND x.guild_id=$2 ORDER BY x.created_at ASC LIMIT 100`,
    [capsuleId,guildId,viewer],
  );
  return { capsule, contributions };
}

export async function contributeToTimeCapsule(input: {
  guildId: string; capsuleId: string; contributorId: string; content: string;
}): Promise<boolean> {
  if (!USER_ID_PATTERN.test(input.contributorId)) throw new Error("A valid Discord contributor ID is required.");
  const content = requiredText(input.content, 2_500, "Contribution");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO time_capsule_contributions (capsule_id,guild_id,contributor_id,content)
     SELECT c.id,c.guild_id,$3,$4 FROM time_capsules c
     WHERE c.id=$1 AND c.guild_id=$2 AND c.status='collecting'
       AND (c.audience<>'owner' OR c.owner_id=$3)
       AND ((SELECT COUNT(*) FROM time_capsule_contributions x WHERE x.capsule_id=c.id)<50
         OR EXISTS (SELECT 1 FROM time_capsule_contributions x WHERE x.capsule_id=c.id AND x.contributor_id=$3))
     ON CONFLICT (capsule_id,contributor_id) DO UPDATE SET content=excluded.content,created_at=CURRENT_TIMESTAMP
     RETURNING id::text AS id`,
    [input.capsuleId,input.guildId,input.contributorId,content],
  );
  if (!row) throw new Error("That capsule is not accepting contributions.");
  return true;
}

export async function sealTimeCapsule(input: {
  guildId: string; capsuleId: string; ownerId: string;
}): Promise<void> {
  await transaction(async client => {
    const result = await client.query(
      "SELECT owner_id::text,status,release_at FROM time_capsules WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.capsuleId,input.guildId],
    );
    const capsule = result.rows[0] as { owner_id: string; status: string; release_at: string } | undefined;
    if (!capsule || capsule.owner_id !== input.ownerId) throw new Error("Only the capsule owner can seal it.");
    if (capsule.status !== "collecting") throw new Error("This capsule is no longer collecting contributions.");
    if (new Date(capsule.release_at).getTime() <= Date.now()) throw new Error("The scheduled release time has passed.");
    const contributions = await client.query(
      "SELECT id FROM time_capsule_contributions WHERE capsule_id=$1 AND guild_id=$2 LIMIT 1",
      [input.capsuleId,input.guildId],
    );
    if (!contributions.rowCount) throw new Error("Add at least one contribution before sealing the capsule.");
    await client.query(
      "UPDATE time_capsules SET status='sealed',sealed_at=CURRENT_TIMESTAMP WHERE id=$1 AND guild_id=$2 AND status='collecting'",
      [input.capsuleId,input.guildId],
    );
  });
}

export async function cancelTimeCapsule(input: {
  guildId: string; capsuleId: string; ownerId: string;
}): Promise<void> {
  const row = await queryOne<{ owner_id: string; status: string }>(
    "SELECT owner_id::text,status FROM time_capsules WHERE id=$1 AND guild_id=$2",
    [input.capsuleId,input.guildId],
  );
  if (!row || row.owner_id !== input.ownerId) throw new Error("Only the capsule owner can cancel it.");
  if (!["collecting","sealed"].includes(row.status)) throw new Error("This capsule can no longer be cancelled.");
  await query(
    "UPDATE time_capsules SET status='cancelled' WHERE id=$1 AND guild_id=$2 AND status IN ('collecting','sealed')",
    [input.capsuleId,input.guildId],
  );
}

export async function claimDueTimeCapsules(limit = 10): Promise<DueCapsule[]> {
  const safeLimit = Math.max(1,Math.min(25,Math.floor(limit)));
  const claimToken = randomUUID();
  return transaction(async client => {
    await client.query(
      `UPDATE time_capsules
       SET status='failed',delivery_error='Delivery status unknown after the worker claim expired. Check the destination before retrying.',
         claim_token=NULL,claimed_at=NULL
       WHERE status='revealing' AND claimed_at<=datetime('now','-5 minutes')`,
      [],
    );
    const result = await client.query(
      `UPDATE time_capsules SET status='revealing',claim_token=$1,claimed_at=CURRENT_TIMESTAMP
       WHERE id IN (
         SELECT id FROM time_capsules WHERE status='sealed' AND datetime(release_at)<=datetime('now')
         ORDER BY release_at ASC LIMIT $2
       ) AND status='sealed'
       RETURNING id::text,guild_id::text,owner_id::text,channel_id::text,title,description,audience,claim_token`,
      [claimToken,safeLimit],
    );
    return result.rows as DueCapsule[];
  });
}

async function getTimeCapsuleContributions(guildId: string, capsuleId: string, claimToken: string): Promise<TimeCapsuleContribution[]> {
  return query<TimeCapsuleContribution>(
    `SELECT x.id::text,x.contributor_id::text,x.content,x.created_at
     FROM time_capsule_contributions x JOIN time_capsules c ON c.id=x.capsule_id AND c.guild_id=x.guild_id
     WHERE x.guild_id=$1 AND x.capsule_id=$2 AND c.status='revealing' AND c.claim_token=$3
     ORDER BY x.created_at ASC LIMIT 50`,
    [guildId,capsuleId,claimToken],
  );
}

export async function finishTimeCapsuleReveal(input: {
  guildId: string; capsuleId: string; claimToken: string; messageId?: string;
  failedReason?: string;
}): Promise<boolean> {
  const nextStatus = input.failedReason ? "failed" : "revealed";
  const result = await query(
    `UPDATE time_capsules SET status=$1,revealed_message_id=$2,delivery_error=$3,revealed_at=CASE WHEN $1='revealed' THEN CURRENT_TIMESTAMP ELSE NULL END,
      claim_token=NULL,claimed_at=NULL
     WHERE id=$4 AND guild_id=$5 AND status='revealing' AND claim_token=$6 RETURNING id`,
    [nextStatus,input.messageId??null,input.failedReason?.slice(0,500)??null,input.capsuleId,input.guildId,input.claimToken],
  );
  return result.length > 0;
}

function revealEmbeds(capsule: DueCapsule, contributions: TimeCapsuleContribution[]): EmbedBuilder[] {
  const embeds: EmbedBuilder[] = [];
  let embed = new DiscordEmbedBuilder().setTitle("Time capsule · " + capsule.title.slice(0,200))
    .setDescription(capsule.description.slice(0,1_000) || "A sealed collection has reached its release date.");
  for (const contribution of contributions) {
    const value = contribution.content.slice(0,850) || "No text contribution.";
    if (embed.data.fields && embed.data.fields.length >= 5) {
      embeds.push(embed);
      embed = new DiscordEmbedBuilder().setTitle("Time capsule · continued");
    }
    embed.addFields({ name: "From <@" + contribution.contributor_id + ">", value, inline: false });
  }
  embeds.push(embed);
  return embeds.slice(0,10);
}

async function deliverCapsule(client: Client, capsule: DueCapsule): Promise<string | undefined> {
  const contributions = await getTimeCapsuleContributions(capsule.guild_id,capsule.id,capsule.claim_token);
  if (!contributions.length) throw new Error("The sealed capsule has no stored contributions.");
  const embeds = revealEmbeds(capsule,contributions);
  if (capsule.audience === "guild") {
    const channel = await client.channels.fetch(capsule.channel_id);
    if (!channel || !channel.isTextBased() || !("send" in channel) || !("guildId" in channel) || channel.guildId !== capsule.guild_id) {
      throw new Error("The configured capsule channel is unavailable in its server.");
    }
    const message = await channel.send({ embeds, allowedMentions: { parse: [] } });
    return message.id;
  }
  const recipientIds = capsule.audience === "owner"
    ? [capsule.owner_id]
    : [...new Set([capsule.owner_id,...contributions.map(item => item.contributor_id)])];
  for (const userId of recipientIds) {
    const user = await client.users.fetch(userId);
    await user.send({ embeds, allowedMentions: { parse: [] } });
  }
  return undefined;
}

async function runCapsuleWorker(client: Client): Promise<void> {
  if (workerRunning) return;
  workerRunning = true;
  try {
    const due = await claimDueTimeCapsules();
    for (const capsule of due) {
      try {
        const messageId = await deliverCapsule(client,capsule);
        await finishTimeCapsuleReveal({
          guildId:capsule.guild_id,capsuleId:capsule.id,claimToken:capsule.claim_token,messageId,
        });
      } catch (error) {
        const reason = error instanceof Error ? error.message : "Unknown capsule delivery error";
        await finishTimeCapsuleReveal({
          guildId:capsule.guild_id,capsuleId:capsule.id,claimToken:capsule.claim_token,failedReason:reason,
        }).catch(() => false);
        logger.warn("Time capsule reveal failed and was marked for moderator review",{
          guildId:capsule.guild_id,capsuleId:capsule.id,reason,
        });
      }
    }
  } catch (error) {
    logger.error("Time capsule worker failed",{
      reason:error instanceof Error?error.message:"Unknown error",
    });
  } finally {
    workerRunning = false;
  }
}

export function startTimeCapsuleWorker(client: Client): void {
  if (workerTimer) return;
  workerPromise = runCapsuleWorker(client);
  workerTimer = setInterval(() => {
    workerPromise = runCapsuleWorker(client);
    void workerPromise;
  },60_000);
  workerTimer.unref();
}

export async function stopTimeCapsuleWorker(): Promise<void> {
  if (workerTimer) clearInterval(workerTimer);
  workerTimer = undefined;
  await workerPromise?.catch(() => undefined);
}

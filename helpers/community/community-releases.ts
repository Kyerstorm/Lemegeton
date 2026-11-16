import { query, queryOne, transaction } from "../../database.js";
import { cleanText } from "../security/security.js";
import { resolveDeliveryRetry } from "./delivery-retries.js";

export type ReleaseCategory = "anime" | "tv" | "movies" | "games";
export type ReleaseCadence = "daily" | "weekly";
export type ReleaseEntityType = "title" | "creator" | "franchise" | "category" | "episodes";

export interface ReleaseSchedule {
  guild_id: string;
  channel_id: string;
  time_zone: string;
  local_time: string;
  cadence: ReleaseCadence;
  weekday: number;
  categories: ReleaseCategory[];
  entity_types: ReleaseEntityType[];
  entity_ids: string[];
  region: string;
  enabled: boolean;
  next_run_at: Date;
}

export interface ReleaseDelivery {
  id: string;
  guild_id: string;
  channel_id: string;
  window_start: Date;
  window_end: Date;
  categories: ReleaseCategory[];
  entity_types: ReleaseEntityType[];
  entity_ids: string[];
  region: string;
  time_zone: string;
  claim_token: string;
}

const CATEGORY_SET = new Set<ReleaseCategory>(["anime", "tv", "movies", "games"]);
const ENTITY_TYPE_SET = new Set<ReleaseEntityType>(["title", "creator", "franchise", "category", "episodes"]);
const DEFAULT_ENTITY_TYPES: ReleaseEntityType[] = ["title", "creator", "franchise", "category", "episodes"];
const DEFAULT_ENTITY_IDS = ["all"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function zonedParts(date: Date, timeZone: string): { time: string; weekday: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const weekday = WEEKDAYS.indexOf(values.weekday ?? "");
  if (weekday < 0) throw new Error("The configured timezone did not return a valid weekday.");
  return { time: `${values.hour}:${values.minute}`, weekday };
}

export function nextReleaseOccurrence(
  timeZone: string,
  localTime: string,
  cadence: ReleaseCadence,
  weekday: number,
  after = new Date(),
): Date {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone }).format(after);
  } catch {
    throw new Error("Enter a valid IANA timezone such as Europe/Dublin or America/New_York.");
  }
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(localTime)) {
    throw new Error("Enter the digest time as HH:MM in 24-hour format.");
  }
  if (!["daily", "weekly"].includes(cadence)) throw new Error("Choose a daily or weekly release digest.");
  if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) throw new Error("Choose a weekday between Sunday and Saturday.");
  const start = Math.floor(after.getTime() / 60_000) * 60_000 + 60_000;
  const limit = (cadence === "daily" ? 48 : 8 * 24) * 60;
  for (let minute = 0; minute < limit; minute += 1) {
    const candidate = new Date(start + minute * 60_000);
    const local = zonedParts(candidate, timeZone);
    if (local.time === localTime && (cadence === "daily" || local.weekday === weekday)) return candidate;
  }
  throw new Error("Could not find the next release digest time in the configured timezone.");
}

export function normalizeReleaseCategories(values: readonly string[]): ReleaseCategory[] {
  const categories = [...new Set(values.map((value) => value.trim().toLowerCase()).filter(Boolean))];
  if (!categories.length || categories.some((value) => !CATEGORY_SET.has(value as ReleaseCategory))) {
    throw new Error("Choose one or more supported categories: anime, tv, movies or games.");
  }
  return categories as ReleaseCategory[];
}

export function normalizeReleaseEntityTypes(values: readonly string[]): ReleaseEntityType[] {
  const entities = [...new Set(values.map(value => value.trim().toLowerCase()).filter(Boolean))];
  if (entities.some(value => !ENTITY_TYPE_SET.has(value as ReleaseEntityType))) {
    throw new Error("Choose supported followed-entity types: title, creator, franchise, category or episodes.");
  }
  return entities as ReleaseEntityType[];
}

export function normalizeReleaseEntityIds(values: readonly string[]): string[] {
  const ids = [...new Set(values.map(value => value.trim()).filter(Boolean))];
  if (ids.includes("all")) return ["all"];
  if (ids.includes("none")) return ["none"];
  if (!ids.every(value => /^(subscription:\d{1,20}|anime:\d{1,12})$/.test(value))) {
    throw new Error("Choose all followed entities, no followed entities, or a valid server follow.");
  }
  return ids;
}

export function parseReleaseCadenceInput(
  value: string,
  fallbackWeekday = 1,
): { cadence: ReleaseCadence; weekday: number } {
  if (!Number.isInteger(fallbackWeekday) || fallbackWeekday < 0 || fallbackWeekday > 6) {
    throw new Error("Choose a weekday between Sunday and Saturday.");
  }
  const normalized = value.trim().toLowerCase();
  if (normalized === "daily") return { cadence: "daily", weekday: fallbackWeekday };
  const match = /^weekly(?::(sun|mon|tue|wed|thu|fri|sat))?$/.exec(normalized);
  if (!match) throw new Error("Cadence must be daily or weekly:mon (using a three-letter weekday).");
  const weekday = match[1] ? WEEKDAYS.findIndex(day => day.toLowerCase() === match[1]) : fallbackWeekday;
  if (weekday < 0) throw new Error("Choose a weekday between Sunday and Saturday.");
  return { cadence: "weekly", weekday };
}

export async function saveReleaseSchedule(input: {
  guildId: string;
  channelId: string;
  actorId: string;
  timeZone: string;
  localTime: string;
  cadence: ReleaseCadence;
  weekday: number;
  categories: readonly string[];
  entityTypes?: readonly string[];
  entityIds?: readonly string[];
  region: string;
  enabled?: boolean;
}): Promise<Date> {
  const region = input.region.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(region)) throw new Error("Release region must be a two-letter country code.");
  const categories = normalizeReleaseCategories(input.categories);
  const entityTypes = normalizeReleaseEntityTypes(input.entityTypes ?? DEFAULT_ENTITY_TYPES);
  const entityIds = normalizeReleaseEntityIds(input.entityIds ?? DEFAULT_ENTITY_IDS);
  const nextRunAt = nextReleaseOccurrence(input.timeZone, input.localTime, input.cadence, input.weekday);
  await query(
    `INSERT INTO community_release_schedules
     (guild_id, channel_id, time_zone, local_time, cadence, weekday, categories, entity_types, entity_ids, region, enabled, next_run_at, created_by, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       channel_id=EXCLUDED.channel_id,
       time_zone=EXCLUDED.time_zone,
       local_time=EXCLUDED.local_time,
       cadence=EXCLUDED.cadence,
       weekday=EXCLUDED.weekday,
       categories=EXCLUDED.categories,
       entity_types=EXCLUDED.entity_types,
       entity_ids=EXCLUDED.entity_ids,
       region=EXCLUDED.region,
       enabled=EXCLUDED.enabled,
       next_run_at=EXCLUDED.next_run_at,
       created_by=EXCLUDED.created_by,
       updated_at=NOW()`,
    [input.guildId,input.channelId,input.timeZone,input.localTime,input.cadence,input.weekday,categories,entityTypes,entityIds,region,input.enabled ?? true,nextRunAt,input.actorId],
  );
  return nextRunAt;
}

export async function disableReleaseSchedule(guildId: string): Promise<void> {
  await query("UPDATE community_release_schedules SET enabled=FALSE, updated_at=NOW() WHERE guild_id=$1", [guildId]);
}

export async function resumeReleaseSchedule(guildId: string): Promise<Date | null> {
  const schedule = await getReleaseSchedule(guildId);
  if (!schedule) return null;
  const nextRunAt = nextReleaseOccurrence(
    schedule.time_zone, schedule.local_time, schedule.cadence, schedule.weekday,
  );
  await query(
    "UPDATE community_release_schedules SET enabled=TRUE,next_run_at=$2,updated_at=NOW() WHERE guild_id=$1",
    [guildId,nextRunAt],
  );
  return nextRunAt;
}

export async function getReleaseSchedule(guildId: string): Promise<ReleaseSchedule | null> {
  return queryOne<ReleaseSchedule>(
    `SELECT guild_id::text, channel_id::text, time_zone, local_time, cadence, weekday,
            categories, entity_types, entity_ids, region, enabled, next_run_at
       FROM community_release_schedules WHERE guild_id=$1`,
    [guildId],
  );
}

export async function dueReleaseSchedules(): Promise<ReleaseSchedule[]> {
  return query<ReleaseSchedule>(
    `SELECT guild_id::text, channel_id::text, time_zone, local_time, cadence, weekday,
            categories, entity_types, entity_ids, region, enabled, next_run_at
       FROM community_release_schedules
      WHERE enabled=TRUE AND next_run_at <= NOW()
      ORDER BY next_run_at ASC LIMIT 50`,
  );
}

export async function prepareReleaseDelivery(schedule: ReleaseSchedule): Promise<void> {
  await transaction(async (client) => {
    const locked = await client.query(
      `SELECT * FROM community_release_schedules
        WHERE guild_id=$1 AND enabled=TRUE AND next_run_at <= NOW()
        FOR UPDATE SKIP LOCKED`,
      [schedule.guild_id],
    );
    const current = locked.rows[0] as ReleaseSchedule | undefined;
    if (!current) return;
    const scheduledFor = new Date(current.next_run_at);
    const nextRunAt = nextReleaseOccurrence(
      current.time_zone, current.local_time, current.cadence, Number(current.weekday), scheduledFor,
    );
    const windowEnd = nextRunAt;
    await client.query(
      "UPDATE community_release_schedules SET next_run_at=$1, updated_at=NOW() WHERE guild_id=$2",
      [nextRunAt, current.guild_id],
    );
    await client.query(
      `INSERT INTO community_release_deliveries
       (guild_id,scheduled_for,channel_id,window_start,window_end,categories,entity_types,entity_ids,region,time_zone,status,attempts,next_attempt_at)
       VALUES ($1,$2,$3,$2,$4,$5,$6,$7,$8,$9,'pending',0,NOW())
       ON CONFLICT (guild_id,scheduled_for) DO NOTHING`,
      [current.guild_id,scheduledFor,current.channel_id,windowEnd,current.categories,current.entity_types,current.entity_ids,current.region,current.time_zone],
    );
  });
}

export async function dueReleaseDeliveries(): Promise<ReleaseDelivery[]> {
  return query<ReleaseDelivery>(
    `WITH due AS (
       SELECT id FROM community_release_deliveries
       WHERE (status = 'pending' AND next_attempt_at <= NOW())
          OR (status = 'processing' AND claim_until <= NOW())
       ORDER BY created_at ASC LIMIT 20 FOR UPDATE SKIP LOCKED
     ),
     claimed AS (
       UPDATE community_release_deliveries d
       SET status = 'processing', claim_until = NOW() + INTERVAL '15 minutes',
           claim_token = md5(random()::text || clock_timestamp()::text || d.id::text)
       FROM due WHERE d.id = due.id
       RETURNING d.id, d.guild_id, d.channel_id, d.window_start, d.window_end, d.categories, d.entity_types, d.entity_ids, d.region, d.time_zone, d.claim_token
     )
     SELECT id::text, guild_id::text, channel_id::text, window_start, window_end, categories, entity_types, entity_ids, region, time_zone, claim_token
     FROM claimed ORDER BY id ASC`,
  );
}

export async function markReleaseDelivery(
  deliveryId: string, claimToken: string, status: "sent" | "pending", messageId?: string, error?: string,
): Promise<"sent" | "pending" | "failed" | null> {
  return transaction(async client => {
    const current = await client.query<{ attempts: number }>(
      "SELECT attempts FROM community_release_deliveries WHERE id = $1 AND status = 'processing' AND claim_token = $2 FOR UPDATE",
      [deliveryId, claimToken],
    );
    const row = current.rows[0];
    if (!row) return null;
    const retry = status === "sent" ? null : resolveDeliveryRetry(Number(row.attempts), 5);
    const nextStatus = status === "sent" ? "sent" : retry!.status;
    await client.query(
      `UPDATE community_release_deliveries
       SET status = $1, message_id = COALESCE($2, message_id), attempts = attempts + 1,
           last_error = $3, claim_until = NULL, claim_token = NULL,
           next_attempt_at = CASE WHEN $1 = 'pending' THEN NOW() + $4 * INTERVAL '1 minute' ELSE next_attempt_at END
       WHERE id = $5 AND status = 'processing' AND claim_token = $6`,
      [nextStatus, messageId ?? null, error ? cleanText(error, 500) : null, retry?.delayMinutes ?? 0, deliveryId, claimToken],
    );
    return nextStatus;
  });
}


export interface ReleaseDigestEntityEvent {
  entity_type: ReleaseEntityType;
  title: string;
  description: string;
  source_url: string;
  provider: string;
  event_at: Date | string;
}

export async function getReleaseDigestEntityEvents(input: {
  guildId: string;
  windowStart: Date;
  windowEnd: Date;
  entityTypes: readonly string[];
  entityIds: readonly string[];
}): Promise<ReleaseDigestEntityEvent[]> {
  const entityTypes = normalizeReleaseEntityTypes(input.entityTypes);
  const entityIds = normalizeReleaseEntityIds(input.entityIds);
  if (entityIds.includes("none") || !entityTypes.length) return [];
  const allEntities = entityIds.includes("all");
  const subscriptionIds = entityIds
    .filter(value => value.startsWith("subscription:"))
    .map(value => value.slice("subscription:".length));
  const animeIds = entityIds
    .filter(value => value.startsWith("anime:"))
    .map(value => value.slice("anime:".length));
  const events: ReleaseDigestEntityEvent[] = [];
  const subscriptionTypes = entityTypes.filter(type => type !== "episodes");
  if (subscriptionTypes.length && (allEntities || subscriptionIds.length)) {
    events.push(...await query<ReleaseDigestEntityEvent>(
      `SELECT f.follow_type AS entity_type, d.title, d.description,
              f.site_url AS source_url, 'AniList'::text AS provider, d.created_at AS event_at
         FROM media_follow_deliveries d
         JOIN media_follow_subscriptions f ON f.id=d.subscription_id AND f.guild_id=d.guild_id
        WHERE d.guild_id=$1 AND d.created_at >= $2 AND d.created_at < $3
          AND f.follow_type = ANY($4::text[])
          AND ($5::boolean OR f.id = ANY($6::bigint[]))
          AND d.status <> 'failed'
        ORDER BY d.created_at ASC,d.id ASC LIMIT 40`,
      [input.guildId,input.windowStart,input.windowEnd,subscriptionTypes,allEntities,subscriptionIds],
    ));
  }
  if (entityTypes.includes("episodes") && (allEntities || animeIds.length)) {
    events.push(...await query<ReleaseDigestEntityEvent>(
      `SELECT 'episodes'::text AS entity_type,
              d.title || ' · Episode ' || d.episode_number::text AS title,
              'Provider-scheduled anime episode'::text AS description,
              d.site_url AS source_url, 'AniList'::text AS provider,
              d.scheduled_for AS event_at
         FROM guild_media_follow_deliveries d
        WHERE d.guild_id=$1 AND d.scheduled_for >= $2 AND d.scheduled_for < $3
          AND ($4::boolean OR d.anilist_id::text = ANY($5::text[]))
          AND d.status <> 'failed'
        ORDER BY d.scheduled_for ASC,d.id ASC LIMIT 40`,
      [input.guildId,input.windowStart,input.windowEnd,allEntities,animeIds],
    ));
  }
  return events.sort((left,right) =>
    new Date(left.event_at).getTime() - new Date(right.event_at).getTime(),
  ).slice(0,40);
}

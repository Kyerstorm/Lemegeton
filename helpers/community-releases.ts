import { query, queryOne, transaction } from "../database.js";
import { cleanText } from "./security.js";

export type ReleaseCategory = "anime" | "tv" | "movies";
export type ReleaseCadence = "daily" | "weekly";

export interface ReleaseSchedule {
  guild_id: string;
  channel_id: string;
  time_zone: string;
  local_time: string;
  cadence: ReleaseCadence;
  weekday: number;
  categories: ReleaseCategory[];
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
  region: string;
}

const CATEGORY_SET = new Set<ReleaseCategory>(["anime", "tv", "movies"]);
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
  if (!/^([01]\\d|2[0-3]):[0-5]\\d$/.test(localTime)) {
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
    throw new Error("Choose one or more supported categories: anime, tv, movies.");
  }
  return categories as ReleaseCategory[];
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
  region: string;
}): Promise<Date> {
  const region = input.region.trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(region)) throw new Error("Release region must be a two-letter country code.");
  const categories = normalizeReleaseCategories(input.categories);
  const nextRunAt = nextReleaseOccurrence(input.timeZone, input.localTime, input.cadence, input.weekday);
  await query(
    `INSERT INTO community_release_schedules
     (guild_id, channel_id, time_zone, local_time, cadence, weekday, categories, region, enabled, next_run_at, created_by, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,TRUE,$9,$10,NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       channel_id=EXCLUDED.channel_id,
       time_zone=EXCLUDED.time_zone,
       local_time=EXCLUDED.local_time,
       cadence=EXCLUDED.cadence,
       weekday=EXCLUDED.weekday,
       categories=EXCLUDED.categories,
       region=EXCLUDED.region,
       enabled=TRUE,
       next_run_at=EXCLUDED.next_run_at,
       created_by=EXCLUDED.created_by,
       updated_at=NOW()`,
    [input.guildId,input.channelId,input.timeZone,input.localTime,input.cadence,input.weekday,categories,region,nextRunAt,input.actorId],
  );
  return nextRunAt;
}

export async function disableReleaseSchedule(guildId: string): Promise<void> {
  await query("UPDATE community_release_schedules SET enabled=FALSE, updated_at=NOW() WHERE guild_id=$1", [guildId]);
}

export async function getReleaseSchedule(guildId: string): Promise<ReleaseSchedule | null> {
  return queryOne<ReleaseSchedule>(
    `SELECT guild_id::text, channel_id::text, time_zone, local_time, cadence, weekday,
            categories, region, enabled, next_run_at
       FROM community_release_schedules WHERE guild_id=$1`,
    [guildId],
  );
}

export async function dueReleaseSchedules(): Promise<ReleaseSchedule[]> {
  return query<ReleaseSchedule>(
    `SELECT guild_id::text, channel_id::text, time_zone, local_time, cadence, weekday,
            categories, region, enabled, next_run_at
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
    const intervalDays = current.cadence === "weekly" ? 7 : 1;
    const windowEnd = new Date(scheduledFor.getTime() + intervalDays * 24 * 60 * 60 * 1000);
    const nextRunAt = nextReleaseOccurrence(
      current.time_zone, current.local_time, current.cadence, Number(current.weekday), scheduledFor,
    );
    await client.query(
      "UPDATE community_release_schedules SET next_run_at=$1, updated_at=NOW() WHERE guild_id=$2",
      [nextRunAt, current.guild_id],
    );
    await client.query(
      `INSERT INTO community_release_deliveries
       (guild_id,scheduled_for,channel_id,window_start,window_end,categories,region,status,attempts,next_attempt_at)
       VALUES ($1,$2,$3,$2,$4,$5,$6,'pending',0,NOW())
       ON CONFLICT (guild_id,scheduled_for) DO NOTHING`,
      [current.guild_id,scheduledFor,current.channel_id,windowEnd,current.categories,current.region],
    );
  });
}

export async function dueReleaseDeliveries(): Promise<ReleaseDelivery[]> {
  return query<ReleaseDelivery>(
    `SELECT id::text, guild_id::text, channel_id::text, window_start, window_end, categories, region
       FROM community_release_deliveries
      WHERE status='pending' AND next_attempt_at <= NOW()
      ORDER BY created_at ASC LIMIT 20`,
  );
}

export async function markReleaseDelivery(
  deliveryId: string,
  status: "sent" | "pending",
  messageId?: string,
  error?: string,
): Promise<void> {
  await query(
    `UPDATE community_release_deliveries
        SET status=$1,
            message_id=COALESCE($2,message_id),
            attempts=attempts+1,
            last_error=$3,
            next_attempt_at=CASE WHEN $1='pending'
              THEN NOW() + LEAST(attempts+1,10) * INTERVAL '5 minutes'
              ELSE next_attempt_at END
      WHERE id=$4 AND status='pending'`,
    [status,messageId ?? null,error ? cleanText(error,500) : null,deliveryId],
  );
}

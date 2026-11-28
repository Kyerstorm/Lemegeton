import { query, queryOne } from "../../src/utility/database/libsql/database.js";
import type { TimelineEvent } from "./timeline-events.js";

export type TimelineSequenceType = "in-universe" | "publication" | "release" | "adaptation" | "continuity";

export interface StoredTimelineEvent extends TimelineEvent {
  sequenceType: TimelineSequenceType;
  region?: string | null;
  platform?: string | null;
  continuity?: string | null;
}

function safeIdentity(value: string, label: string): string {
  const clean = value.trim().slice(0, 160);
  if (!clean) throw new TypeError(label + " is required.");
  return clean;
}

function safeSourceUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || !url.hostname) throw new TypeError("Timeline source URLs must use HTTPS.");
  return url.toString();
}

function safeDate(value: string | null): string | null {
  if (value === null) return null;
  if (!/^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(value)) throw new TypeError("Timeline dates must retain year, month or day precision.");
  return value;
}

export async function saveTimelineEvents(input: {
  provider: string;
  providerId: string;
  sequenceType: TimelineSequenceType;
  events: readonly StoredTimelineEvent[];
}): Promise<number> {
  const provider = safeIdentity(input.provider, "Provider");
  const providerId = safeIdentity(input.providerId, "Provider ID");
  let saved = 0;
  for (const event of input.events.slice(0, 100)) {
    const eventKey = safeIdentity(event.id, "Timeline event key").slice(0, 400);
    const title = safeIdentity(event.title, "Timeline event title").slice(0, 500);
    const eventType = safeIdentity(event.eventType, "Timeline event type").slice(0, 100);
    const sourceName = safeIdentity(event.sourceName, "Timeline source name").slice(0, 120);
    const sourceUrl = safeSourceUrl(event.sourceUrl);
    await query(
      `INSERT INTO media_timeline_provider_events
        (provider,provider_id,sequence_type,event_key,title,event_type,date_value,date_precision,source_name,source_url,region,platform,continuity)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       ON CONFLICT (provider,provider_id,sequence_type,event_key) DO UPDATE SET
         title=excluded.title,event_type=excluded.event_type,date_value=excluded.date_value,
         date_precision=excluded.date_precision,source_name=excluded.source_name,source_url=excluded.source_url,
         region=excluded.region,platform=excluded.platform,continuity=excluded.continuity,observed_at=CURRENT_TIMESTAMP`,
      [
        provider,providerId,input.sequenceType,eventKey,title,eventType,safeDate(event.date.value),
        event.date.precision,sourceName,sourceUrl,event.region ?? null,event.platform ?? null,event.continuity ?? null,
      ],
    );
    saved += 1;
  }
  return saved;
}

export async function listTimelineEvents(provider: string, providerId: string, sequenceType: TimelineSequenceType): Promise<StoredTimelineEvent[]> {
  const rows = await query<{
    event_key: string; title: string; event_type: string; date_value: string | null; date_precision: StoredTimelineEvent["date"]["precision"];
    source_name: string; source_url: string; region: string | null; platform: string | null; continuity: string | null;
  }>(
    `SELECT event_key,title,event_type,date_value,date_precision,source_name,source_url,region,platform,continuity
       FROM media_timeline_provider_events WHERE provider=$1 AND provider_id=$2 AND sequence_type=$3
       ORDER BY CASE WHEN date_value IS NULL THEN 1 ELSE 0 END,date_value,event_key LIMIT 100`,
    [safeIdentity(provider, "Provider"),safeIdentity(providerId, "Provider ID"),sequenceType],
  );
  return rows.map(row => ({
    id: row.event_key,
    title: row.title,
    description: null,
    date: {
      value: row.date_value,
      precision: row.date_precision,
      label: row.date_value ?? "Date not supplied",
    },
    eventType: row.event_type,
    sequenceType,
    sourceName: row.source_name,
    sourceUrl: row.source_url,
    region: row.region,
    platform: row.platform,
    continuity: row.continuity,
  }));
}

export interface TimelineCorrectionRequest {
  id: string;
  provider: string;
  provider_id: string;
  entity_title: string;
  sequence_type: TimelineSequenceType;
  event_key: string;
  proposed_value: string;
  evidence_url: string;
  created_by: string;
  status: "pending" | "approved" | "rejected";
  review_note: string | null;
  created_at: string;
}

export async function listTimelineCorrectionRequests(
  guildId: string,
  status: TimelineCorrectionRequest["status"] = "pending",
  limit = 20,
): Promise<TimelineCorrectionRequest[]> {
  return query<TimelineCorrectionRequest>(
    `SELECT id::text,provider,provider_id,entity_title,sequence_type,event_key,proposed_value,evidence_url,
       created_by::text,status,review_note,created_at
     FROM timeline_correction_requests
     WHERE guild_id=$1 AND status=$2
     ORDER BY created_at ASC,id ASC LIMIT $3`,
    [guildId,status,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getTimelineCorrectionRequest(
  guildId: string,
  requestId: string,
): Promise<TimelineCorrectionRequest | null> {
  return queryOne<TimelineCorrectionRequest>(
    `SELECT id::text,provider,provider_id,entity_title,sequence_type,event_key,proposed_value,evidence_url,
       created_by::text,status,review_note,created_at
     FROM timeline_correction_requests WHERE id=$1 AND guild_id=$2`,
    [requestId,guildId],
  );
}

export async function reviewTimelineCorrectionRequest(input: {
  guildId: string;
  requestId: string;
  reviewerId: string;
  decision: "approved" | "rejected";
  note?: string;
}): Promise<boolean> {
  const request = await queryOne<{ created_by: string; status: string }>(
    "SELECT created_by::text,status FROM timeline_correction_requests WHERE id=$1 AND guild_id=$2",
    [input.requestId,input.guildId],
  );
  if (!request || request.status !== "pending") return false;
  if (request.created_by === input.reviewerId) throw new Error("The requester cannot review their own chronology correction.");
  const note = (input.note ?? "").trim().slice(0,500) || null;
  const updated = await queryOne<{ id: string }>(
    `UPDATE timeline_correction_requests
       SET status=$1,reviewed_by=$2,review_note=$3,reviewed_at=CURRENT_TIMESTAMP
     WHERE id=$4 AND guild_id=$5 AND status='pending' AND created_by<>$2
     RETURNING id::text AS id`,
    [input.decision,input.reviewerId,note,input.requestId,input.guildId],
  );
  return Boolean(updated);
}

export async function listApprovedTimelineCorrections(input: {
  guildId: string;
  provider: string;
  providerId: string;
  sequenceType: TimelineSequenceType;
  eventKey: string;
}): Promise<Array<{ proposed_value: string; evidence_url: string; reviewed_by: string; reviewed_at: string }>> {
  return query(
    `SELECT proposed_value,evidence_url,reviewed_by::text,reviewed_at
     FROM timeline_correction_requests
     WHERE guild_id=$1 AND provider=$2 AND provider_id=$3 AND sequence_type=$4
       AND event_key=$5 AND field_name='date' AND status='approved'
     ORDER BY reviewed_at DESC,id DESC LIMIT 3`,
    [input.guildId,input.provider,input.providerId,input.sequenceType,input.eventKey],
  );
}

export async function createTimelineCorrectionRequest(input: {
  guildId: string;
  provider: string;
  providerId: string;
  entityTitle: string;
  sequenceType: TimelineSequenceType;
  eventKey: string;
  proposedDate: string;
  evidenceUrl: string;
  createdBy: string;
}): Promise<string | null> {
  const date = safeDate(input.proposedDate);
  if (!date) throw new TypeError("Enter a year, year-month or full date.");
  const source = safeSourceUrl(input.evidenceUrl);
  const created = await queryOne<{ id: string | number }>(
    `INSERT INTO timeline_correction_requests
      (guild_id,provider,provider_id,entity_title,sequence_type,event_key,field_name,proposed_value,evidence_url,created_by)
     VALUES ($1,$2,$3,$4,$5,$6,'date',$7,$8,$9) RETURNING id`,
    [
      input.guildId,safeIdentity(input.provider,"Provider"),safeIdentity(input.providerId,"Provider ID"),
      safeIdentity(input.entityTitle,"Entity title"),input.sequenceType,safeIdentity(input.eventKey,"Event key"),
      date,source,input.createdBy,
    ],
  );
  return created ? String(created.id) : null;
}

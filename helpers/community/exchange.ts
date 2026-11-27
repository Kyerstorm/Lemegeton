import { query, queryOne } from "../../src/utility/database/libsql/database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export interface ExchangeRequest {
  id: string;
  guild_id: string;
  owner_id: string;
  title: string;
  description: string;
  media_category: string | null;
  preferences: string | null;
  exclusions: string | null;
  visibility: "guild" | "restricted";
  status: "open" | "solved" | "closed";
  created_at: string;
}

export interface ExchangeCandidate {
  id: string;
  title: string;
  source_url: string | null;
  provider: string | null;
  provider_id: string | null;
  explanation: string;
  caveat: string | null;
  submitted_by: string;
  is_shortlisted: number;
  owner_feedback: "good_match" | "not_match" | null;
}

export async function createExchangeRequest(input: {
  guildId: string; ownerId: string; title: string; description: string;
  mediaCategory?: string; preferences?: string; exclusions?: string; visibility?: "guild" | "restricted";
}): Promise<string> {
  const title = cleanText(input.title, 180);
  const description = cleanText(input.description, 1_000);
  if (!title || !description) throw new Error("Provide a short title and describe the kind of media you are looking for.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO exchange_requests (guild_id,owner_id,title,description,media_category,preferences,exclusions,visibility)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id::text AS id`,
    [
      input.guildId,input.ownerId,title,description,
      cleanText(input.mediaCategory,60)||null,cleanText(input.preferences,500)||null,cleanText(input.exclusions,500)||null,
      input.visibility ?? "guild",
    ],
  );
  if (!row) throw new Error("The recommendation request could not be created.");
  return row.id;
}

export async function listExchangeRequests(
  guildId: string,
  limit = 15,
  viewerId?: string,
): Promise<Array<{
  id: string; title: string; media_category: string | null; owner_id: string; candidate_count: number; visibility: "guild" | "restricted";
}>> {
  return query(
    `SELECT r.id::text AS id,r.title,r.media_category,r.owner_id::text AS owner_id,r.visibility,
      (SELECT COUNT(*) FROM exchange_candidates c WHERE c.request_id=r.id AND c.guild_id=r.guild_id AND c.status='active')::INT AS candidate_count
     FROM exchange_requests r
     WHERE r.guild_id=$1 AND r.status='open' AND (r.visibility='guild' OR r.owner_id=$3)
     ORDER BY r.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit))),viewerId ?? null],
  );
}

export interface ExchangeClarification {
  id: string;
  candidate_id: string | null;
  author_id: string;
  message: string;
  created_at: string;
}

export async function getExchangeRequest(guildId: string, requestId: string, viewerId?: string): Promise<{
  request: ExchangeRequest; candidates: ExchangeCandidate[]; clarifications: ExchangeClarification[];
} | null> {
  const request = await queryOne<ExchangeRequest>(
    `SELECT id::text,guild_id::text,owner_id::text,title,description,media_category,preferences,exclusions,visibility,status,created_at
     FROM exchange_requests WHERE id=$1 AND guild_id=$2 AND (visibility='guild' OR owner_id=$3)`,
    [requestId,guildId,viewerId ?? null],
  );
  if (!request) return null;
  const [candidates,clarifications] = await Promise.all([
    query<ExchangeCandidate>(
      `SELECT c.id::text,c.title,c.source_url,c.provider,c.provider_id,c.explanation,c.caveat,c.submitted_by::text,c.is_shortlisted,
        (SELECT f.feedback FROM exchange_candidate_feedback f
         WHERE f.guild_id=c.guild_id AND f.request_id=c.request_id AND f.candidate_id=c.id AND f.owner_id=$3 LIMIT 1) AS owner_feedback
       FROM exchange_candidates c WHERE c.request_id=$1 AND c.guild_id=$2 AND c.status='active'
       ORDER BY c.is_shortlisted DESC,c.created_at ASC LIMIT 25`,
      [requestId,guildId,request.owner_id],
    ),
    query<ExchangeClarification>(
      `SELECT id::text,candidate_id::text,author_id::text,message,created_at
       FROM exchange_clarifications WHERE request_id=$1 AND guild_id=$2
       ORDER BY created_at ASC,id ASC LIMIT 25`,
      [requestId,guildId],
    ),
  ]);
  return { request, candidates, clarifications };
}

export async function addExchangeCandidate(input: {
  guildId: string; requestId: string; submittedBy: string; title: string;
  sourceUrl?: string; provider?: string; providerId?: string; explanation: string; caveat?: string;
}): Promise<string> {
  const title = cleanText(input.title,200);
  const explanation = cleanText(input.explanation,500);
  if (!title || !explanation) throw new Error("A recommendation needs a title and an explanation.");
  const url = isValidHttpsUrl(input.sourceUrl);
  const provider = cleanText(input.provider,80)||null;
  const providerId = cleanText(input.providerId,160)||null;
  if (!url && !(provider && providerId)) throw new Error("Add an HTTPS source link, or provide both a provider and provider ID.");
  if (Boolean(provider)!==Boolean(providerId)) throw new Error("Provider and provider ID must be supplied together.");
  const request = await queryOne<{ id: string }>(
    `SELECT id::text AS id FROM exchange_requests
     WHERE id=$1 AND guild_id=$2 AND status='open' AND (visibility='guild' OR owner_id=$3)
       AND (SELECT COUNT(*) FROM exchange_candidates c WHERE c.request_id=exchange_requests.id AND c.guild_id=exchange_requests.guild_id AND c.status='active')<50`,
    [input.requestId,input.guildId,input.submittedBy],
  );
  if (!request) throw new Error("That open request is not available or has reached its recommendation limit.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO exchange_candidates
      (request_id,guild_id,title,source_url,provider,provider_id,explanation,caveat,submitted_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id::text AS id`,
    [input.requestId,input.guildId,title,url,provider,providerId,explanation,cleanText(input.caveat,300)||null,input.submittedBy],
  );
  if (!row) throw new Error("The recommendation could not be saved.");
  return row.id;
}

export async function setExchangeCandidateShortlist(input: {
  guildId: string; requestId: string; candidateId: string; ownerId: string; shortlisted: boolean;
}): Promise<void> {
  const owner = await queryOne<{ owner_id: string }>(
    "SELECT owner_id::text FROM exchange_requests WHERE id=$1 AND guild_id=$2 AND status='open'",
    [input.requestId,input.guildId],
  );
  if (!owner || owner.owner_id!==input.ownerId) throw new Error("Only the request owner can manage its shortlist.");
  const result = await queryOne<{ id: string }>(
    `UPDATE exchange_candidates SET is_shortlisted=$1
     WHERE id=$2 AND request_id=$3 AND guild_id=$4 AND status='active' RETURNING id::text AS id`,
    [input.shortlisted?1:0,input.candidateId,input.requestId,input.guildId],
  );
  if (!result) throw new Error("That recommendation does not belong to this request.");
}

export async function findSimilarExchangeRequests(input: {
  guildId: string; title: string; viewerId: string; excludeRequestId?: string; limit?: number;
}): Promise<Array<{ id: string; title: string; description: string; candidate_count: number }>> {
  const title = cleanText(input.title,180);
  if (!title || title.length < 3) return [];
  const pattern = "%" + title.toLocaleLowerCase("en-US").replace(/[%_]/g,"") + "%";
  return query(
    `SELECT r.id::text,r.title,r.description,
       (SELECT COUNT(*) FROM exchange_candidates c WHERE c.request_id=r.id AND c.guild_id=r.guild_id AND c.status='active')::INT AS candidate_count
     FROM exchange_requests r
     WHERE r.guild_id=$1 AND r.status='open' AND (r.visibility='guild' OR r.owner_id=$2)
       AND ($4 IS NULL OR r.id<>$4) AND lower(r.title) LIKE $3
     ORDER BY r.created_at DESC LIMIT $5`,
    [input.guildId,input.viewerId,pattern,input.excludeRequestId ?? null,Math.max(1,Math.min(5,Math.floor(input.limit ?? 3)))],
  );
}

export async function setExchangeRequestVisibility(input: {
  guildId: string; requestId: string; ownerId: string; visibility: "guild" | "restricted";
}): Promise<void> {
  const updated = await queryOne<{ id: string }>(
    `UPDATE exchange_requests SET visibility=$1,updated_at=CURRENT_TIMESTAMP
     WHERE id=$2 AND guild_id=$3 AND owner_id=$4 AND status='open' RETURNING id::text AS id`,
    [input.visibility,input.requestId,input.guildId,input.ownerId],
  );
  if (!updated) throw new Error("Only the owner can change visibility on an open request.");
}

export async function rateExchangeCandidate(input: {
  guildId: string; requestId: string; candidateId: string; ownerId: string;
  feedback: "good_match" | "not_match";
}): Promise<void> {
  const owner = await queryOne<{ id: string }>(
    "SELECT id::text FROM exchange_requests WHERE id=$1 AND guild_id=$2 AND owner_id=$3 AND status='open'",
    [input.requestId,input.guildId,input.ownerId],
  );
  if (!owner) throw new Error("Only the request owner can rate recommendations.");
  const updated = await queryOne<{ id: string }>(
    `INSERT INTO exchange_candidate_feedback (guild_id,request_id,candidate_id,owner_id,feedback)
     SELECT c.guild_id,c.request_id,c.id,$4,$5 FROM exchange_candidates c
     WHERE c.id=$1 AND c.request_id=$2 AND c.guild_id=$3 AND c.status='active'
     ON CONFLICT (guild_id,request_id,candidate_id,owner_id)
     DO UPDATE SET feedback=excluded.feedback,updated_at=CURRENT_TIMESTAMP
     RETURNING candidate_id::text AS id`,
    [input.candidateId,input.requestId,input.guildId,input.ownerId,input.feedback],
  );
  if (!updated) throw new Error("That recommendation does not belong to this request.");
}

export async function addExchangeClarification(input: {
  guildId: string; requestId: string; authorId: string; message: string; candidateId?: string;
}): Promise<string> {
  const message = cleanText(input.message,800);
  if (!message) throw new Error("Write a clarification message.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO exchange_clarifications (guild_id,request_id,candidate_id,author_id,message)
     SELECT r.guild_id,r.id,c.id,$4,$5
     FROM exchange_requests r
     LEFT JOIN exchange_candidates c ON c.id=$3 AND c.request_id=r.id AND c.guild_id=r.guild_id AND c.status='active'
     WHERE r.id=$1 AND r.guild_id=$2 AND (r.visibility='guild' OR r.owner_id=$4)
       AND r.status='open' AND ($3 IS NULL OR c.id IS NOT NULL)
       AND (SELECT COUNT(*) FROM exchange_clarifications x
            WHERE x.request_id=r.id AND x.guild_id=r.guild_id AND x.author_id=$4)<10
     RETURNING id::text AS id`,
    [input.requestId,input.guildId,input.candidateId ?? null,input.authorId,message],
  );
  if (!row) throw new Error("That request or recommendation is no longer available.");
  return row.id;
}

export interface ExchangeCandidateReport {
  id: string; candidate_id: string; request_id: string; title: string;
  reported_by: string; reason: string; status: "pending" | "reviewed" | "dismissed";
}

export async function reportExchangeCandidate(input: {
  guildId: string; requestId: string; candidateId: string; reportedBy: string; reason: string;
}): Promise<string> {
  const reason = cleanText(input.reason,500);
  if (!reason) throw new Error("Provide a reason for the report.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO exchange_candidate_reports (guild_id,request_id,candidate_id,reported_by,reason)
     SELECT c.guild_id,c.request_id,c.id,$4,$5
     FROM exchange_candidates c JOIN exchange_requests r ON r.id=c.request_id AND r.guild_id=c.guild_id
     WHERE c.id=$1 AND c.request_id=$2 AND c.guild_id=$3 AND c.status='active'
       AND r.status='open' AND (r.visibility='guild' OR r.owner_id=$4)
     ON CONFLICT (guild_id,request_id,candidate_id,reported_by) DO NOTHING
     RETURNING id::text AS id`,
    [input.candidateId,input.requestId,input.guildId,input.reportedBy,reason],
  );
  if (!row) throw new Error("That recommendation is not available or has already been reported.");
  return row.id;
}

export async function listExchangeCandidateReports(guildId: string, limit=20): Promise<ExchangeCandidateReport[]> {
  return query(
    `SELECT r.id::text,c.id::text AS candidate_id,r.request_id::text,c.title,r.reported_by::text,r.reason,r.status
     FROM exchange_candidate_reports r JOIN exchange_candidates c
       ON c.id=r.candidate_id AND c.request_id=r.request_id AND c.guild_id=r.guild_id
     WHERE r.guild_id=$1 AND r.status='pending'
     ORDER BY r.created_at ASC,r.id ASC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getExchangeCandidateReport(guildId: string, reportId: string): Promise<ExchangeCandidateReport | null> {
  return queryOne(
    `SELECT r.id::text,c.id::text AS candidate_id,r.request_id::text,c.title,r.reported_by::text,r.reason,r.status
     FROM exchange_candidate_reports r JOIN exchange_candidates c
       ON c.id=r.candidate_id AND c.request_id=r.request_id AND c.guild_id=r.guild_id
     WHERE r.guild_id=$1 AND r.id=$2`,
    [guildId,reportId],
  );
}

export async function reviewExchangeCandidateReport(input: {
  guildId: string; reportId: string; reviewerId: string; decision: "reviewed" | "dismissed";
}): Promise<boolean> {
  const report = await queryOne<{ reported_by: string; status: string }>(
    "SELECT reported_by::text,status FROM exchange_candidate_reports WHERE id=$1 AND guild_id=$2",
    [input.reportId,input.guildId],
  );
  if (!report || report.status!=="pending") return false;
  if (report.reported_by===input.reviewerId) throw new Error("The reporter cannot review their own recommendation report.");
  const updated = await queryOne<{ id:string }>(
    `UPDATE exchange_candidate_reports SET status=$1,reviewed_by=$2,reviewed_at=CURRENT_TIMESTAMP
     WHERE id=$3 AND guild_id=$4 AND status='pending' AND reported_by<>$2
     RETURNING id::text AS id`,
    [input.decision,input.reviewerId,input.reportId,input.guildId],
  );
  return Boolean(updated);
}

export async function removeExchangeCandidate(input: {
  guildId: string; requestId: string; candidateId: string; actorId: string; canModerate: boolean;
}): Promise<void> {
  if (!input.canModerate) throw new Error("A moderator permission is required to remove a recommendation.");
  const updated = await queryOne<{ id: string }>(
    `UPDATE exchange_candidates SET status='removed'
     WHERE id=$1 AND request_id=$2 AND guild_id=$3 AND status='active'
     RETURNING id::text AS id`,
    [input.candidateId,input.requestId,input.guildId],
  );
  if (!updated) throw new Error("That recommendation is already removed or belongs to another request.");
}

export async function closeExchangeRequest(input: {
  guildId: string; requestId: string; actorId: string; canModerate?: boolean; solved?: boolean;
}): Promise<void> {
  const row = await queryOne<{ owner_id: string }>(
    "SELECT owner_id::text FROM exchange_requests WHERE id=$1 AND guild_id=$2 AND status='open'",
    [input.requestId,input.guildId],
  );
  if (!row) throw new Error("That open request was not found.");
  if (row.owner_id!==input.actorId && !input.canModerate) throw new Error("Only the request owner or a moderator can close it.");
  await query(
    "UPDATE exchange_requests SET status=$1,updated_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3 AND status='open'",
    [input.solved?"solved":"closed",input.requestId,input.guildId],
  );
}

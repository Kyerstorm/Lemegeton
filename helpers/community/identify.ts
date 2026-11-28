import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export interface IdentifyCase {
  id: string;
  guild_id: string;
  owner_id: string;
  title: string;
  description: string;
  media_category: string | null;
  year_hint: string | null;
  language: string | null;
  region: string | null;
  platform: string | null;
  visibility: "guild" | "restricted";
  status: "open" | "solved" | "unresolved" | "closed";
  solved_candidate_id: string | null;
  created_at: string;
}

export interface IdentifyCandidate {
  id: string;
  title: string;
  source_url: string | null;
  provider: string | null;
  provider_id: string | null;
  explanation: string;
  submitted_by: string;
  status: "active" | "accepted" | "rejected";
  support_count: number;
  challenge_count: number;
}

export interface IdentifyEvidence {
  id: string;
  candidate_id: string | null;
  description: string;
  source_url: string | null;
  submitted_by: string;
  created_at: string;
}

export async function createIdentifyCase(input: {
  guildId: string; ownerId: string; title: string; description: string;
  mediaCategory?: string; yearHint?: string; language?: string; region?: string; platform?: string;
  channelId?: string | null; visibility?: "guild" | "restricted";
}): Promise<string> {
  const title = cleanText(input.title, 180);
  const description = cleanText(input.description, 1_000);
  if (!title || !description) throw new Error("Provide a short title and description of what you remember.");
  const visibility = input.visibility ?? "guild";
  const channelId = input.channelId ?? null;
  if (visibility === "restricted" && !channelId) throw new Error("A restricted case must be tied to its creating channel.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO identify_cases
      (guild_id,owner_id,channel_id,title,description,media_category,year_hint,language,region,platform,visibility)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id::text AS id`,
    [
      input.guildId,input.ownerId,channelId,title,description,
      cleanText(input.mediaCategory, 50) || null,cleanText(input.yearHint, 40) || null,
      cleanText(input.language, 60) || null,cleanText(input.region, 60) || null,cleanText(input.platform, 80) || null,
      visibility,
    ],
  );
  if (!row) throw new Error("The identification case could not be created.");
  return row.id;
}

export async function listIdentifyCases(
  guildId: string,
  limit = 15,
  viewerId?: string,
  channelId?: string | null,
  canModerate = false,
): Promise<Array<{
  id: string; title: string; media_category: string | null; owner_id: string; candidate_count: number; created_at: string;
}>> {
  return query(
    `SELECT c.id::text AS id,c.title,c.media_category,c.owner_id::text AS owner_id,
      (SELECT COUNT(*) FROM identify_candidates x WHERE x.case_id=c.id AND x.status='active')::INT AS candidate_count,
      c.created_at
     FROM identify_cases c WHERE c.guild_id=$1 AND c.status='open'
       AND (c.visibility='guild' OR c.owner_id=$3 OR c.channel_id=$4 OR $5=1)
     ORDER BY c.created_at DESC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit))),viewerId ?? null,channelId ?? null,canModerate ? 1 : 0],
  );
}

export async function getIdentifyCase(
  guildId: string,
  caseId: string,
  viewerId?: string,
  channelId?: string | null,
  canModerate = false,
): Promise<{
  case: IdentifyCase;
  candidates: IdentifyCandidate[];
  evidence: IdentifyEvidence[];
} | null> {
  const item = await queryOne<IdentifyCase>(
    `SELECT id::text,guild_id::text,owner_id::text,title,description,media_category,year_hint,language,region,platform,
      visibility,status,solved_candidate_id::text,created_at
     FROM identify_cases WHERE id=$1 AND guild_id=$2
       AND (visibility='guild' OR owner_id=$3 OR channel_id=$4 OR $5=1)`,
    [caseId,guildId,viewerId ?? null,channelId ?? null,canModerate ? 1 : 0],
  );
  if (!item) return null;
  const [candidates,evidence] = await Promise.all([
    query<IdentifyCandidate>(
      `SELECT c.id::text,c.title,c.source_url,c.provider,c.provider_id,c.explanation,c.submitted_by::text,c.status,
        (SELECT COUNT(*) FROM identify_candidate_votes v WHERE v.candidate_id=c.id AND v.stance='support')::INT AS support_count,
        (SELECT COUNT(*) FROM identify_candidate_votes v WHERE v.candidate_id=c.id AND v.stance='challenge')::INT AS challenge_count
       FROM identify_candidates c WHERE c.case_id=$1 AND c.guild_id=$2
       ORDER BY CASE c.status WHEN 'accepted' THEN 0 WHEN 'active' THEN 1 ELSE 2 END,c.created_at ASC LIMIT 25`,
      [caseId,guildId],
    ),
    query<IdentifyEvidence>(
      `SELECT id::text,candidate_id::text,description,source_url,submitted_by::text,created_at
       FROM identify_evidence WHERE case_id=$1 AND guild_id=$2 ORDER BY created_at ASC LIMIT 20`,
      [caseId,guildId],
    ),
  ]);
  return { case: item, candidates, evidence };
}

export async function addIdentifyCandidate(input: {
  guildId: string; caseId: string; submittedBy: string; title: string;
  sourceUrl?: string; provider?: string; providerId?: string; explanation: string;
}): Promise<string> {
  const title = cleanText(input.title, 200);
  const explanation = cleanText(input.explanation, 500);
  if (!title || !explanation) throw new Error("A candidate needs a title and an explanation.");
  const url = isValidHttpsUrl(input.sourceUrl);
  const caseItem = await queryOne<{ id: string }>(
    "SELECT id::text AS id FROM identify_cases WHERE id=$1 AND guild_id=$2 AND status='open'",
    [input.caseId,input.guildId],
  );
  if (!caseItem) throw new Error("That open case was not found in this server.");
  const provider = cleanText(input.provider, 80) || null;
  const providerId = cleanText(input.providerId, 160) || null;
  if (Boolean(provider) !== Boolean(providerId)) throw new Error("Provider and provider ID must be supplied together.");
  const result = await queryOne<{ id: string }>(
    `INSERT INTO identify_candidates (case_id,guild_id,title,source_url,provider,provider_id,explanation,submitted_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id::text AS id`,
    [input.caseId,input.guildId,title,url,provider,providerId,explanation,input.submittedBy],
  );
  if (!result) throw new Error("The candidate could not be saved.");
  return result.id;
}

export async function addIdentifyEvidence(input: {
  guildId: string; caseId: string; candidateId?: string; submittedBy: string;
  description: string; sourceUrl?: string;
}): Promise<string> {
  const description = cleanText(input.description, 500);
  if (!description) throw new Error("Evidence needs a short description.");
  const url = isValidHttpsUrl(input.sourceUrl);
  const caseItem = await queryOne<{ id: string }>(
    "SELECT id::text AS id FROM identify_cases WHERE id=$1 AND guild_id=$2 AND status='open'",
    [input.caseId,input.guildId],
  );
  if (!caseItem) throw new Error("That open case was not found in this server.");
  if (input.candidateId) {
    const candidate = await queryOne<{ id: string }>(
      "SELECT id::text AS id FROM identify_candidates WHERE id=$1 AND case_id=$2 AND guild_id=$3",
      [input.candidateId,input.caseId,input.guildId],
    );
    if (!candidate) throw new Error("That candidate does not belong to this case.");
  }
  const row = await queryOne<{ id: string }>(
    `INSERT INTO identify_evidence (case_id,guild_id,candidate_id,description,source_url,submitted_by)
     VALUES ($1,$2,$3,$4,$5,$6) RETURNING id::text AS id`,
    [input.caseId,input.guildId,input.candidateId ?? null,description,url,input.submittedBy],
  );
  if (!row) throw new Error("The evidence could not be saved.");
  return row.id;
}

export async function voteIdentifyCandidate(input: {
  guildId: string; caseId: string; candidateId: string; userId: string; stance: "support" | "challenge";
}): Promise<void> {
  const saved = await queryOne<{ id: string }>(
    `INSERT INTO identify_candidate_votes (guild_id,case_id,candidate_id,user_id,stance)
     SELECT $1,$2,$3,$4,$5
     WHERE EXISTS (SELECT 1 FROM identify_cases WHERE id=$2 AND guild_id=$1 AND status='open')
       AND EXISTS (SELECT 1 FROM identify_candidates WHERE id=$3 AND case_id=$2 AND guild_id=$1 AND status='active')
     ON CONFLICT (guild_id,candidate_id,user_id) DO UPDATE SET stance=excluded.stance,created_at=CURRENT_TIMESTAMP
     RETURNING candidate_id::text AS id`,
    [input.guildId,input.caseId,input.candidateId,input.userId,input.stance],
  );
  if (!saved) throw new Error("That candidate is no longer available for feedback.");
}

export async function solveIdentifyCase(input: {
  guildId: string; caseId: string; candidateId: string; actorId: string; canModerate?: boolean;
}): Promise<void> {
  await transaction(async client => {
    const caseResult = await client.query(
      "SELECT owner_id::text,status FROM identify_cases WHERE id=$1 AND guild_id=$2 FOR UPDATE",
      [input.caseId,input.guildId],
    );
    const item = caseResult.rows[0] as { owner_id: string; status: string } | undefined;
    if (!item || item.status !== "open") throw new Error("That identification case is not open.");
    if (item.owner_id !== input.actorId && !input.canModerate) throw new Error("Only the case owner or a moderator can mark the case solved.");
    const candidate = await client.query(
      "SELECT id FROM identify_candidates WHERE id=$1 AND case_id=$2 AND guild_id=$3 AND status='active'",
      [input.candidateId,input.caseId,input.guildId],
    );
    if (!candidate.rowCount) throw new Error("Choose an active candidate from this case.");
    await client.query(
      "UPDATE identify_candidates SET status=CASE WHEN id=$1 THEN 'accepted' ELSE 'rejected' END WHERE case_id=$2 AND guild_id=$3",
      [input.candidateId,input.caseId,input.guildId],
    );
    await client.query(
      "UPDATE identify_cases SET status='solved',solved_candidate_id=$1,updated_at=CURRENT_TIMESTAMP,closed_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3",
      [input.candidateId,input.caseId,input.guildId],
    );
  });
}

export async function closeIdentifyCase(input: {
  guildId: string; caseId: string; actorId: string; canModerate?: boolean; unresolved?: boolean;
}): Promise<void> {
  const row = await queryOne<{ owner_id: string; status: string }>(
    "SELECT owner_id::text,status FROM identify_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if (!row || row.status !== "open") throw new Error("That case is not open.");
  if (row.owner_id !== input.actorId && !input.canModerate) throw new Error("Only the case owner or a moderator can close this case.");
  await query(
    "UPDATE identify_cases SET status=$1,updated_at=CURRENT_TIMESTAMP,closed_at=CURRENT_TIMESTAMP WHERE id=$2 AND guild_id=$3 AND status='open'",
    [input.unresolved ? "unresolved" : "closed",input.caseId,input.guildId],
  );
}

export async function reopenIdentifyCase(input: {
  guildId: string; caseId: string; actorId: string; canModerate?: boolean;
}): Promise<void> {
  const row = await queryOne<{ owner_id: string; status: string }>(
    "SELECT owner_id::text,status FROM identify_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if (!row || !["solved","unresolved","closed"].includes(row.status)) throw new Error("That case cannot be reopened.");
  if (row.owner_id !== input.actorId && !input.canModerate) throw new Error("Only the case owner or a moderator can reopen this case.");
  await query(
    "UPDATE identify_cases SET status='open',solved_candidate_id=NULL,updated_at=CURRENT_TIMESTAMP,closed_at=NULL WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  await query("UPDATE identify_candidates SET status='active' WHERE case_id=$1 AND guild_id=$2", [input.caseId,input.guildId]);
}

export interface IdentifyCaseReport {
  id: string;
  case_id: string;
  case_title: string;
  reported_by: string;
  reason: string;
  status: "pending" | "reviewed" | "dismissed";
  created_at: string;
}

export async function listIdentifyCaseReports(guildId: string, limit = 20): Promise<IdentifyCaseReport[]> {
  return query<IdentifyCaseReport>(
    `SELECT r.id::text,r.case_id::text,c.title AS case_title,r.reported_by::text,r.reason,r.status,r.created_at
     FROM identify_case_reports r JOIN identify_cases c ON c.id=r.case_id AND c.guild_id=r.guild_id
     WHERE r.guild_id=$1 AND r.status='pending'
     ORDER BY r.created_at ASC,r.id ASC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getIdentifyCaseReport(guildId: string, reportId: string): Promise<IdentifyCaseReport | null> {
  return queryOne<IdentifyCaseReport>(
    `SELECT r.id::text,r.case_id::text,c.title AS case_title,r.reported_by::text,r.reason,r.status,r.created_at
     FROM identify_case_reports r JOIN identify_cases c ON c.id=r.case_id AND c.guild_id=r.guild_id
     WHERE r.guild_id=$1 AND r.id=$2`,
    [guildId,reportId],
  );
}

export async function reviewIdentifyCaseReport(input: {
  guildId: string; reportId: string; reviewerId: string; decision: "reviewed" | "dismissed";
}): Promise<boolean> {
  const request = await queryOne<{ reported_by: string; status: string }>(
    "SELECT reported_by::text,status FROM identify_case_reports WHERE id=$1 AND guild_id=$2",
    [input.reportId,input.guildId],
  );
  if (!request || request.status !== "pending") return false;
  if (request.reported_by === input.reviewerId) throw new Error("The reporter cannot review their own case report.");
  const updated = await queryOne<{ id: string }>(
    `UPDATE identify_case_reports SET status=$1
     WHERE id=$2 AND guild_id=$3 AND status='pending' AND reported_by<>$4
     RETURNING id::text AS id`,
    [input.decision,input.reportId,input.guildId,input.reviewerId],
  );
  return Boolean(updated);
}

export async function findSimilarIdentifyCases(input: {
  guildId: string; title: string; viewerId: string; channelId?: string | null;
  canModerate?: boolean; excludeCaseId?: string; limit?: number;
}): Promise<Array<{ id: string; title: string; description: string; media_category: string | null }>> {
  const title = cleanText(input.title,180);
  if (!title || title.length < 3) return [];
  const pattern = "%" + title.toLocaleLowerCase("en-US").replace(/[%_]/g,"") + "%";
  return query(
    `SELECT id::text,title,description,media_category
     FROM identify_cases
     WHERE guild_id=$1 AND status IN ('open','solved') AND ($6 IS NULL OR id<>$6)
       AND (visibility='guild' OR owner_id=$2 OR channel_id=$3 OR $4=1)
       AND lower(title) LIKE $5
     ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,created_at DESC LIMIT $7`,
    [input.guildId,input.viewerId,input.channelId ?? null,input.canModerate ? 1 : 0,pattern,
      input.excludeCaseId ?? null,Math.max(1,Math.min(5,Math.floor(input.limit ?? 3)))],
  );
}

export async function searchSolvedIdentifyCases(input: {
  guildId: string; queryText: string; viewerId: string; channelId?: string | null;
  canModerate?: boolean; limit?: number;
}): Promise<Array<{ id: string; title: string; description: string; media_category: string | null }>> {
  const term = cleanText(input.queryText,100);
  if (!term || term.length < 2) throw new Error("Search requires at least two characters.");
  const pattern = "%" + term.toLocaleLowerCase("en-US").replace(/[%_]/g,"") + "%";
  return query(
    `SELECT id::text,title,description,media_category
     FROM identify_cases
     WHERE guild_id=$1 AND status='solved'
       AND (visibility='guild' OR owner_id=$2 OR channel_id=$3 OR $4=1)
       AND (lower(title) LIKE $5 OR lower(description) LIKE $5)
     ORDER BY closed_at DESC,created_at DESC LIMIT $6`,
    [input.guildId,input.viewerId,input.channelId ?? null,input.canModerate ? 1 : 0,pattern,
      Math.max(1,Math.min(15,Math.floor(input.limit ?? 10)))],
  );
}
export async function reportIdentifyCase(input: { guildId: string; caseId: string; reportedBy: string; reason: string }): Promise<void> {
  const reason = cleanText(input.reason,500);
  if (!reason) throw new Error("Provide a reason for the report.");
  const exists = await queryOne<{ id: string }>(
    "SELECT id::text AS id FROM identify_cases WHERE id=$1 AND guild_id=$2",
    [input.caseId,input.guildId],
  );
  if (!exists) throw new Error("That case was not found in this server.");
  await query(
    "INSERT INTO identify_case_reports (guild_id,case_id,reported_by,reason) VALUES ($1,$2,$3,$4)",
    [input.guildId,input.caseId,input.reportedBy,reason],
  );
}

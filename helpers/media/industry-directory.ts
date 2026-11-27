import { query, queryOne } from "../../src/utility/database/libsql/database.js";

export interface IndustryPinInput {
  guildId: string;
  provider: string;
  providerId: string;
  displayName: string;
  category: string;
  sourceUrl: string;
  pinnedBy: string;
}

export interface IndustryPin extends IndustryPinInput {
  id: string;
  createdAt: string;
}

function required(value: string, label: string, maxLength: number): string {
  const clean = value.trim();
  if (!clean || clean.length > maxLength) throw new TypeError(label + " is required and must be at most " + maxLength + " characters.");
  return clean;
}

function sourceUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || !url.hostname) throw new TypeError("Industry source URLs must use HTTPS.");
  return url.toString();
}

export async function pinIndustryOrganization(input: IndustryPinInput): Promise<boolean> {
  const inserted = await queryOne<{ id: string | number }>(
    `INSERT INTO industry_directory_pins
      (guild_id,provider,provider_id,display_name,category,source_url,pinned_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7)
     ON CONFLICT (guild_id,provider,provider_id) DO NOTHING
     RETURNING id`,
    [
      input.guildId,
      required(input.provider, "Provider", 80),
      required(input.providerId, "Provider ID", 160),
      required(input.displayName, "Organization name", 200),
      required(input.category, "Organization category", 80),
      sourceUrl(input.sourceUrl),
      input.pinnedBy,
    ],
  );
  return inserted !== null;
}

export async function listIndustryPins(guildId: string, limit = 25): Promise<IndustryPin[]> {
  const rows = await query<{
    id: string | number; guild_id: string; provider: string; provider_id: string;
    display_name: string; category: string; source_url: string; pinned_by: string; created_at: string;
  }>(
    `SELECT id,guild_id,provider,provider_id,display_name,category,source_url,pinned_by,created_at
       FROM industry_directory_pins WHERE guild_id=$1
      ORDER BY display_name COLLATE NOCASE LIMIT $2`,
    [guildId, Math.max(1, Math.min(100, Math.floor(limit)))],
  );
  return rows.map(row => ({
    id: String(row.id),
    guildId: row.guild_id,
    provider: row.provider,
    providerId: row.provider_id,
    displayName: row.display_name,
    category: row.category,
    sourceUrl: row.source_url,
    pinnedBy: row.pinned_by,
    createdAt: row.created_at,
  }));
}

export async function removeIndustryPin(guildId: string, pinId: string): Promise<boolean> {
  const result = await query(
    "DELETE FROM industry_directory_pins WHERE guild_id=$1 AND id=$2 RETURNING id",
    [guildId, pinId],
  );
  return result.length > 0;
}

export interface IndustryCorrectionRequest {
  id: string;
  provider: string;
  provider_id: string;
  organization_name: string;
  field_name: string;
  proposed_value: string;
  evidence_url: string;
  created_by: string;
  status: "pending" | "approved" | "rejected";
}

export interface IndustryIdentityLinkRequest {
  id: string;
  source_provider: string;
  source_provider_id: string;
  source_name: string;
  target_provider: string;
  target_provider_id: string;
  target_name: string;
  target_url: string;
  evidence_url: string;
  created_by: string;
  status: "pending" | "approved" | "rejected";
}

export async function createIndustryIdentityLinkRequest(input: {
  guildId: string;
  sourceProvider: string;
  sourceProviderId: string;
  sourceName: string;
  sourceUrl: string;
  targetProvider: string;
  targetProviderId: string;
  targetName: string;
  targetUrl: string;
  evidenceUrl: string;
  createdBy: string;
}): Promise<string | null> {
  const sourceProvider = required(input.sourceProvider,"Source provider",80);
  const sourceProviderId = required(input.sourceProviderId,"Source provider ID",160);
  const targetProvider = required(input.targetProvider,"Target provider",80);
  const targetProviderId = required(input.targetProviderId,"Target provider ID",160);
  if (sourceProvider === targetProvider && sourceProviderId === targetProviderId) {
    throw new TypeError("Choose a different provider identity.");
  }
  const created = await queryOne<{ id: string | number }>(
    `INSERT INTO industry_identity_links
      (guild_id,source_provider,source_provider_id,source_name,source_url,target_provider,target_provider_id,target_name,target_url,evidence_url,created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
     ON CONFLICT (guild_id,source_provider,source_provider_id,target_provider,target_provider_id) DO NOTHING
     RETURNING id`,
    [
      input.guildId,sourceProvider,sourceProviderId,required(input.sourceName,"Source name",200),sourceUrl(input.sourceUrl),
      targetProvider,targetProviderId,required(input.targetName,"Target name",200),sourceUrl(input.targetUrl),
      sourceUrl(input.evidenceUrl),input.createdBy,
    ],
  );
  return created ? String(created.id) : null;
}

export async function listPendingIndustryCorrections(guildId: string, limit = 15): Promise<IndustryCorrectionRequest[]> {
  return query(
    `SELECT id::text,provider,provider_id,organization_name,field_name,proposed_value,evidence_url,
       created_by::text,status
     FROM industry_correction_requests WHERE guild_id=$1 AND status='pending'
     ORDER BY created_at ASC,id ASC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getIndustryCorrectionRequest(guildId: string, requestId: string): Promise<IndustryCorrectionRequest | null> {
  return queryOne(
    `SELECT id::text,provider,provider_id,organization_name,field_name,proposed_value,evidence_url,
       created_by::text,status
     FROM industry_correction_requests WHERE id=$1 AND guild_id=$2`,
    [requestId,guildId],
  );
}

export async function reviewIndustryCorrectionRequest(input: {
  guildId: string; requestId: string; reviewerId: string; decision: "approved" | "rejected"; note?: string;
}): Promise<boolean> {
  const request = await queryOne<{ created_by: string; status: string }>(
    "SELECT created_by::text,status FROM industry_correction_requests WHERE id=$1 AND guild_id=$2",
    [input.requestId,input.guildId],
  );
  if (!request || request.status !== "pending") return false;
  if (request.created_by === input.reviewerId) throw new Error("The requester cannot review their own Industry correction.");
  const updated = await queryOne<{ id: string }>(
    `UPDATE industry_correction_requests SET status=$1,reviewed_by=$2,review_note=$3,reviewed_at=CURRENT_TIMESTAMP
     WHERE id=$4 AND guild_id=$5 AND status='pending' AND created_by<>$2 RETURNING id::text AS id`,
    [input.decision,input.reviewerId,(input.note ?? "").trim().slice(0,500) || null,input.requestId,input.guildId],
  );
  return Boolean(updated);
}

export async function listPendingIndustryIdentityLinks(guildId: string, limit = 15): Promise<IndustryIdentityLinkRequest[]> {
  return query(
    `SELECT id::text,source_provider,source_provider_id,source_name,target_provider,target_provider_id,target_name,
       target_url,evidence_url,created_by::text,status
     FROM industry_identity_links WHERE guild_id=$1 AND status='pending'
     ORDER BY created_at ASC,id ASC LIMIT $2`,
    [guildId,Math.max(1,Math.min(25,Math.floor(limit)))],
  );
}

export async function getIndustryIdentityLinkRequest(guildId: string, requestId: string): Promise<IndustryIdentityLinkRequest | null> {
  return queryOne(
    `SELECT id::text,source_provider,source_provider_id,source_name,target_provider,target_provider_id,target_name,
       target_url,evidence_url,created_by::text,status
     FROM industry_identity_links WHERE id=$1 AND guild_id=$2`,
    [requestId,guildId],
  );
}

export async function reviewIndustryIdentityLinkRequest(input: {
  guildId: string; requestId: string; reviewerId: string; decision: "approved" | "rejected"; note?: string;
}): Promise<boolean> {
  const request = await queryOne<{ created_by: string; status: string }>(
    "SELECT created_by::text,status FROM industry_identity_links WHERE id=$1 AND guild_id=$2",
    [input.requestId,input.guildId],
  );
  if (!request || request.status !== "pending") return false;
  if (request.created_by === input.reviewerId) throw new Error("The requester cannot review their own provider identity link.");
  const updated = await queryOne<{ id: string }>(
    `UPDATE industry_identity_links SET status=$1,reviewed_by=$2,review_note=$3,reviewed_at=CURRENT_TIMESTAMP
     WHERE id=$4 AND guild_id=$5 AND status='pending' AND created_by<>$2 RETURNING id::text AS id`,
    [input.decision,input.reviewerId,(input.note ?? "").trim().slice(0,500) || null,input.requestId,input.guildId],
  );
  return Boolean(updated);
}

export async function listApprovedIndustryCorrections(input: {
  guildId: string; provider: string; providerId: string;
}): Promise<Array<{ field_name: string; proposed_value: string; evidence_url: string }>> {
  return query(
    `SELECT field_name,proposed_value,evidence_url FROM industry_correction_requests
     WHERE guild_id=$1 AND provider=$2 AND provider_id=$3 AND status='approved'
     ORDER BY reviewed_at DESC,id DESC LIMIT 10`,
    [input.guildId,input.provider,input.providerId],
  );
}

export async function listApprovedIndustryIdentityLinks(input: {
  guildId: string; provider: string; providerId: string;
}): Promise<Array<{ provider: string; provider_id: string; name: string; url: string; evidence_url: string }>> {
  return query(
    `SELECT
       CASE WHEN source_provider=$2 AND source_provider_id=$3 THEN target_provider ELSE source_provider END AS provider,
       CASE WHEN source_provider=$2 AND source_provider_id=$3 THEN target_provider_id ELSE source_provider_id END AS provider_id,
       CASE WHEN source_provider=$2 AND source_provider_id=$3 THEN target_name ELSE source_name END AS name,
       CASE WHEN source_provider=$2 AND source_provider_id=$3 THEN target_url ELSE source_url END AS url,
       evidence_url
     FROM industry_identity_links
     WHERE guild_id=$1 AND status='approved'
       AND ((source_provider=$2 AND source_provider_id=$3) OR (target_provider=$2 AND target_provider_id=$3))
     ORDER BY reviewed_at DESC,id DESC LIMIT 10`,
    [input.guildId,input.provider,input.providerId],
  );
}

export async function createIndustryCorrectionRequest(input: {
  guildId: string;
  provider: string;
  providerId: string;
  organizationName: string;
  fieldName: string;
  proposedValue: string;
  evidenceUrl: string;
  createdBy: string;
}): Promise<string | null> {
  const created = await queryOne<{ id: string | number }>(
    `INSERT INTO industry_correction_requests
      (guild_id,provider,provider_id,organization_name,field_name,proposed_value,evidence_url,created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id`,
    [
      input.guildId,
      required(input.provider, "Provider", 80),
      required(input.providerId, "Provider ID", 160),
      required(input.organizationName, "Organization name", 200),
      required(input.fieldName, "Field name", 80),
      required(input.proposedValue, "Proposed value", 1_000),
      sourceUrl(input.evidenceUrl),
      input.createdBy,
    ],
  );
  return created ? String(created.id) : null;
}

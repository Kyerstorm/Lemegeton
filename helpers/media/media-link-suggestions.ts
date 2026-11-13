import { query, queryOne } from "../../database.js";
import { normalizeAtlasCategory, recordAtlasRelationship, safeAtlasUrl, type MediaCategory } from "../integration/atlas.js";

export const MEDIA_LINK_RELATIONSHIPS = [
  "adaptation",
  "source material",
  "sequel",
  "prequel",
  "spin-off",
  "side story",
  "other",
] as const;

export type MediaLinkRelationship = typeof MEDIA_LINK_RELATIONSHIPS[number];
export type MediaLinkDecision = "approved" | "rejected";

export interface MediaLinkSuggestionInput {
  sourceTitle: string;
  sourceCategory: string;
  sourceUrl: string;
  relationship: string;
  targetTitle: string;
  targetCategory: string;
  targetUrl: string;
  evidence: string;
}

export interface MediaLinkSuggestion {
  id: string;
  source_title: string;
  source_category: string;
  source_url: string;
  relationship_type: string;
  target_title: string;
  target_category: string;
  target_url: string;
  evidence: string;
  submitter_id: string;
  created_at: Date;
}

export interface MediaLinkReviewResult {
  suggestion: MediaLinkSuggestion;
  indexed: boolean;
}

function cleanTitle(value: string): string {
  return value.replace(/\s+/g, " ").trim().slice(0, 200);
}

export function normalizeMediaLinkSuggestion(input: MediaLinkSuggestionInput): MediaLinkSuggestionInput | null {
  const sourceTitle = cleanTitle(input.sourceTitle);
  const targetTitle = cleanTitle(input.targetTitle);
  const sourceCategory = normalizeAtlasCategory(input.sourceCategory);
  const targetCategory = normalizeAtlasCategory(input.targetCategory);
  const sourceUrl = safeAtlasUrl(input.sourceUrl);
  const targetUrl = safeAtlasUrl(input.targetUrl);
  const relationship = input.relationship.trim().toLocaleLowerCase("en-US");
  const evidence = input.evidence.replace(/\s+/g, " ").trim().slice(0, 1_500);
  const titleKey = (value: string) => value.normalize("NFKC").toLocaleLowerCase("en-US").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

  if (!sourceTitle || !targetTitle || titleKey(sourceTitle) === titleKey(targetTitle)) return null;
  if (!sourceCategory || !targetCategory || !sourceUrl || !targetUrl) return null;
  if (!(MEDIA_LINK_RELATIONSHIPS as readonly string[]).includes(relationship)) return null;
  if (evidence.length < 15) return null;

  return {
    sourceTitle,
    sourceCategory,
    sourceUrl,
    relationship,
    targetTitle,
    targetCategory,
    targetUrl,
    evidence,
  };
}

export async function createMediaLinkSuggestion(
  guildId: string,
  submitterId: string,
  input: MediaLinkSuggestionInput,
): Promise<string> {
  const normalized = normalizeMediaLinkSuggestion(input);
  if (!normalized) {
    throw new Error("Provide distinct titles, supported categories, complete HTTPS source links, a valid relationship and at least 15 characters of evidence.");
  }
  const row = await queryOne<{ id: string }>(
    `INSERT INTO media_link_suggestions
      (guild_id,submitter_id,source_title,source_category,source_url,relationship_type,
       target_title,target_category,target_url,evidence)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
     RETURNING id`,
    [guildId,submitterId,normalized.sourceTitle,normalized.sourceCategory,normalized.sourceUrl,
      normalized.relationship,normalized.targetTitle,normalized.targetCategory,normalized.targetUrl,normalized.evidence],
  );
  if (!row) throw new Error("The media relationship suggestion could not be saved.");
  return row.id;
}

export async function listPendingMediaLinkSuggestions(guildId: string): Promise<MediaLinkSuggestion[]> {
  return query<MediaLinkSuggestion>(
    `SELECT id,source_title,source_category,source_url,relationship_type,target_title,target_category,
            target_url,evidence,submitter_id,created_at
       FROM media_link_suggestions
      WHERE guild_id = $1 AND status = 'pending'
      ORDER BY created_at ASC LIMIT 20`,
    [guildId],
  );
}

export async function getPendingMediaLinkSuggestion(
  guildId: string,
  suggestionId: string,
): Promise<MediaLinkSuggestion | null> {
  return queryOne<MediaLinkSuggestion>(
    `SELECT id,source_title,source_category,source_url,relationship_type,target_title,target_category,
            target_url,evidence,submitter_id,created_at
       FROM media_link_suggestions
      WHERE id = $1 AND guild_id = $2 AND status = 'pending'`,
    [suggestionId,guildId],
  );
}

export async function reviewMediaLinkSuggestion(input: {
  guildId: string;
  suggestionId: string;
  reviewerId: string;
  decision: MediaLinkDecision;
  reason?: string;
}): Promise<MediaLinkReviewResult | null> {
  const suggestion = await queryOne<MediaLinkSuggestion>(
    `UPDATE media_link_suggestions
        SET status = $1, reviewer_id = $2, review_reason = $3, reviewed_at = NOW()
      WHERE id = $4 AND guild_id = $5 AND status = 'pending'
      RETURNING id,source_title,source_category,source_url,relationship_type,target_title,target_category,
                target_url,evidence,submitter_id,created_at`,
    [input.decision,input.reviewerId,(input.reason ?? "").trim().slice(0,1_000),input.suggestionId,input.guildId],
  );
  if (!suggestion) return null;
  let indexed = false;
  if (input.decision === "approved") {
    indexed = await recordAtlasRelationship({
      sourceTitle:suggestion.source_title,
      sourceCategory:suggestion.source_category,
      sourceUrl:suggestion.source_url,
      targetTitle:suggestion.target_title,
      targetCategory:suggestion.target_category,
      targetUrl:suggestion.target_url,
      relationshipType:suggestion.relationship_type,
      sourceKind:"community",
      sourceLabel:"Moderator-approved suggestion in this server",
      guildId:input.guildId,
      evidence:suggestion.evidence,
      createdBy:input.reviewerId,
    });
  }
  return { suggestion, indexed };
}

import { query, queryOne } from "../../database.js";

export type MediaCategory = "ANIME" | "MANGA" | "LIGHT_NOVEL" | "WEBNOVEL" | "BOOK" | "MOVIE" | "TV" | "GAME";
export type RelationshipSource = "provider" | "recommendation" | "community";
export interface AtlasRelationInput {
  title: string;
  category: MediaCategory | string;
  url?: string | null;
  relationshipType: string;
}
export interface AtlasRelation {
  title: string;
  category: MediaCategory;
  url: string | null;
  relationType: string;
  source: string;
  sourceKind: RelationshipSource;
}
interface AtlasRow {
  source_title: string; source_title_key: string; source_category: string; source_url: string | null;
  target_title: string; target_title_key: string; target_category: string; target_url: string | null;
  relationship_type: string; source_kind: RelationshipSource; source_label: string;
}
const CATEGORIES = new Set<MediaCategory>(["ANIME","MANGA","LIGHT_NOVEL","WEBNOVEL","BOOK","MOVIE","TV","GAME"]);
const SOURCES = new Set<RelationshipSource>(["provider","recommendation","community"]);

export function normalizeAtlasTitle(value: string): string {
  return String(value ?? "").normalize("NFKC").toLocaleLowerCase("en-US")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim().slice(0, 256);
}

export function normalizeAtlasCategory(value: string): MediaCategory | null {
  const normalized = String(value ?? "").trim().replace(/[\s-]+/g, "_").toUpperCase();
  const aliases: Record<string, MediaCategory> = {
    NOVEL:"LIGHT_NOVEL", LIGHTNOVEL:"LIGHT_NOVEL", LIGHT_NOVELS:"LIGHT_NOVEL",
    BOOKS:"BOOK", GENERAL_NOVEL:"BOOK", MOVIES:"MOVIE", TV_SERIES:"TV",
    TELEVISION:"TV", WEBNOVELS:"WEBNOVEL",
  };
  const category = aliases[normalized] ?? normalized;
  return CATEGORIES.has(category as MediaCategory) ? category as MediaCategory : null;
}

export function safeAtlasUrl(value: string | null | undefined): string | null {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "https:" || !url.hostname || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export async function recordAtlasRelationship(input: {
  sourceTitle: string; sourceCategory: string; sourceUrl?: string | null;
  targetTitle: string; targetCategory: string; targetUrl?: string | null;
  relationshipType: string; sourceKind: RelationshipSource; sourceLabel: string;
  guildId?: string | null; evidence?: string | null; createdBy?: string | null;
}): Promise<boolean> {
  const sourceTitle = input.sourceTitle.replace(/\s+/g, " ").trim().slice(0, 256);
  const targetTitle = input.targetTitle.replace(/\s+/g, " ").trim().slice(0, 256);
  const sourceKey = normalizeAtlasTitle(sourceTitle);
  const targetKey = normalizeAtlasTitle(targetTitle);
  const sourceCategory = normalizeAtlasCategory(input.sourceCategory);
  const targetCategory = normalizeAtlasCategory(input.targetCategory);
  const relationshipType = input.relationshipType.replace(/_/g, " ").replace(/\s+/g, " ").trim().toLocaleLowerCase("en-US").slice(0, 64) || "related";
  if (!sourceTitle || !targetTitle || !sourceKey || !targetKey || !sourceCategory || !targetCategory
    || (sourceKey === targetKey && sourceCategory === targetCategory) || !SOURCES.has(input.sourceKind)) return false;
  const guildId = input.sourceKind === "community" ? input.guildId?.trim() : null;
  if (input.sourceKind === "community" && !guildId) return false;

  const inserted = await queryOne<{ id: string }>(
    `INSERT INTO media_relationship_graph
      (source_title, source_title_key, source_category, source_url, target_title, target_title_key,
       target_category, target_url, relationship_type, source_kind, source_label, guild_id, evidence, created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
     ON CONFLICT DO NOTHING RETURNING id`,
    [sourceTitle,sourceKey,sourceCategory,safeAtlasUrl(input.sourceUrl),targetTitle,targetKey,targetCategory,
      safeAtlasUrl(input.targetUrl),relationshipType,input.sourceKind,input.sourceLabel.trim().slice(0,100) || input.sourceKind,
      guildId,input.evidence?.trim().slice(0,1500) || null,input.createdBy ?? null],
  );
  return inserted !== null;
}

export async function recordProviderRelationships(input: {
  sourceTitle: string; sourceCategory: string; sourceUrl?: string | null;
  relations: AtlasRelationInput[]; sourceLabel: string;
}): Promise<number> {
  const saved = await Promise.all(input.relations.slice(0, 20).map((relation) => recordAtlasRelationship({
    sourceTitle: input.sourceTitle, sourceCategory: input.sourceCategory, sourceUrl: input.sourceUrl,
    targetTitle: relation.title, targetCategory: relation.category, targetUrl: relation.url,
    relationshipType: relation.relationshipType, sourceKind: "provider", sourceLabel: input.sourceLabel,
  })));
  return saved.filter(Boolean).length;
}

export async function findAtlasRelationships(
  guildId: string | null, title: string, category: string, url?: string | null, limit = 20,
): Promise<AtlasRelation[]> {
  const titleKey = normalizeAtlasTitle(title);
  const normalizedCategory = normalizeAtlasCategory(category);
  if (!titleKey || !normalizedCategory) return [];
  const safeUrl = safeAtlasUrl(url) ?? "";
  const visibility = guildId ? "(guild_id IS NULL OR guild_id = $1)" : "guild_id IS NULL";
  const offset = guildId ? 1 : 0;
  const rows = await query<AtlasRow>(
    `SELECT source_title,source_title_key,source_category,source_url,target_title,target_title_key,
            target_category,target_url,relationship_type,source_kind,source_label
       FROM media_relationship_graph
      WHERE ${visibility}
        AND ((source_title_key = $${offset+1} AND source_category = $${offset+2} AND ($${offset+3} = '' OR source_url = $${offset+3}))
          OR (target_title_key = $${offset+1} AND target_category = $${offset+2} AND ($${offset+3} = '' OR target_url = $${offset+3})))
      ORDER BY CASE source_kind WHEN 'provider' THEN 0 WHEN 'recommendation' THEN 1 ELSE 2 END,
               created_at DESC
      LIMIT $${offset+4}`,
    guildId ? [guildId,titleKey,normalizedCategory,safeUrl,Math.max(1,Math.min(limit,30))]
      : [titleKey,normalizedCategory,safeUrl,Math.max(1,Math.min(limit,30))],
  );
  const seen = new Set<string>();
  const result: AtlasRelation[] = [];
  for (const row of rows) {
    const outgoing = row.source_title_key === titleKey && row.source_category === normalizedCategory
      && (!safeUrl || row.source_url === safeUrl);
    const relatedTitle = outgoing ? row.target_title : row.source_title;
    const relatedCategory = normalizeAtlasCategory(outgoing ? row.target_category : row.source_category);
    if (!relatedTitle || !relatedCategory) continue;
    let relationType = row.relationship_type.replace(/_/g, " ").replace(/\b\w/g, (v) => v.toUpperCase());
    if (!outgoing) relationType = `Incoming: ${relationType}`;
    if (row.source_kind === "community") relationType = `Community-verified: ${relationType}`;
    if (row.source_kind === "recommendation") relationType = `Recommendation: ${relationType}`;
    const relation: AtlasRelation = {
      title: relatedTitle, category: relatedCategory, url: safeAtlasUrl(outgoing ? row.target_url : row.source_url),
      relationType, source: row.source_label, sourceKind: row.source_kind,
    };
    const key = [normalizeAtlasTitle(relation.title),relation.category,relation.url ?? "",relation.relationType].join("|");
    if (!seen.has(key)) { seen.add(key); result.push(relation); }
  }
  return result;
}

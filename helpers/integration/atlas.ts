import { query, queryOne } from "../../database.js";

export type MediaCategory = "ANIME" | "MANGA" | "LIGHT_NOVEL" | "WEBNOVEL" | "BOOK" | "MOVIE" | "TV" | "GAME" | "CREATOR" | "FRANCHISE" | "ARCHIVE_ENTRY" | "ARCHIVE_COLLECTION" | "DISCUSSION" | "ACTIVITY";
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
export interface AtlasGraphNode {
  id: string;
  title: string;
  category: MediaCategory;
  url: string | null;
  depth: number;
  sourceKind?: RelationshipSource;
  sourceLabel?: string;
  relationType?: string;
}
export interface AtlasGraphEdge {
  from: string;
  to: string;
  relationType: string;
  sourceLabel: string;
  sourceKind: RelationshipSource;
}
export interface AtlasGraphResult {
  rootId: string;
  nodes: AtlasGraphNode[];
  edges: AtlasGraphEdge[];
  directRelationships: AtlasRelation[];
  truncated: boolean;
}
export interface AtlasGraphOptions {
  maxDepth?: number;
  maxNodes?: number;
  perNodeLimit?: number;
}

const CATEGORIES = new Set<MediaCategory>(["ANIME","MANGA","LIGHT_NOVEL","WEBNOVEL","BOOK","MOVIE","TV","GAME","CREATOR","FRANCHISE","ARCHIVE_ENTRY","ARCHIVE_COLLECTION","DISCUSSION","ACTIVITY"]);
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
    if (row.source_kind === "community") relationType = `Community-sourced: ${relationType}`;
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


/** Stable identity for one category-aware work/edition node in a bounded graph. */
export function atlasNodeIdentity(title: string, category: string, url?: string | null): string {
  return JSON.stringify([normalizeAtlasCategory(category), normalizeAtlasTitle(title), safeAtlasUrl(url)]);
}

/**
 * Expand an Atlas neighborhood using a caller-supplied, visibility-aware edge loader.
 * Breadth-first ordering keeps results deterministic and prevents deeper nodes from
 * displacing the root's direct connections.
 */
export async function buildAtlasGraph(
  root: { title: string; category: string; url?: string | null },
  loadRelationships: (node: AtlasGraphNode, limit: number) => Promise<AtlasRelation[]>,
  options: AtlasGraphOptions = {},
): Promise<AtlasGraphResult> {
  const category = normalizeAtlasCategory(root.category);
  const title = root.title.replace(/\s+/g, " ").trim().slice(0, 256);
  const rootId = atlasNodeIdentity(title, root.category, root.url);
  if (!category || !normalizeAtlasTitle(title) || rootId.startsWith("[null")) {
    return { rootId: "", nodes: [], edges: [], directRelationships: [], truncated: false };
  }

  const maxDepth = Math.max(1, Math.min(3, Math.floor(options.maxDepth ?? 2)));
  const maxNodes = Math.max(2, Math.min(40, Math.floor(options.maxNodes ?? 24)));
  const perNodeLimit = Math.max(1, Math.min(16, Math.floor(options.perNodeLimit ?? 8)));
  const rootNode: AtlasGraphNode = {
    id: rootId, title, category, url: safeAtlasUrl(root.url), depth: 0,
  };
  const nodes = new Map<string, AtlasGraphNode>([[rootId, rootNode]]);
  const parentByNode = new Map<string, string | null>([[rootId, null]]);
  const edges: AtlasGraphEdge[] = [];
  const edgeKeys = new Set<string>();
  const directRelationships: AtlasRelation[] = [];
  let frontier = [rootNode];
  let truncated = false;
  const isAncestor = (candidate: string, nodeId: string): boolean => {
    let parent = parentByNode.get(nodeId) ?? null;
    while (parent) {
      if (parent === candidate) return true;
      parent = parentByNode.get(parent) ?? null;
    }
    return false;
  };

  for (let depth = 0; depth < maxDepth && frontier.length; depth += 1) {
    const batches = await Promise.all(frontier.map(async node => ({
      node,
      relationships: await loadRelationships(node, perNodeLimit + 1),
    })));
    const next: AtlasGraphNode[] = [];

    for (const batch of batches) {
      if (batch.relationships.length > perNodeLimit) truncated = true;
      for (const relation of batch.relationships.slice(0, perNodeLimit)) {
        const targetCategory = normalizeAtlasCategory(relation.category);
        const targetTitle = relation.title.replace(/\s+/g, " ").trim().slice(0, 256);
        if (!targetCategory || !normalizeAtlasTitle(targetTitle)) continue;
        const targetId = atlasNodeIdentity(targetTitle, targetCategory, relation.url);
        if (!targetId || targetId === batch.node.id) continue;

        let target = nodes.get(targetId);
        if (target && target.depth < batch.node.depth && isAncestor(targetId, batch.node.id)) continue;
        if (!target) {
          if (nodes.size >= maxNodes) {
            truncated = true;
            continue;
          }
          target = {
            id: targetId,
            title: targetTitle,
            category: targetCategory,
            url: safeAtlasUrl(relation.url),
            depth: batch.node.depth + 1,
            sourceKind: relation.sourceKind,
            sourceLabel: relation.source,
            relationType: relation.relationType,
          };
          nodes.set(targetId, target);
          parentByNode.set(targetId, batch.node.id);
          next.push(target);
        }

        const edgeKey = JSON.stringify([batch.node.id, targetId, relation.relationType, relation.sourceKind, relation.source]);
        if (edgeKeys.has(edgeKey)) continue;
        edgeKeys.add(edgeKey);
        edges.push({
          from: batch.node.id,
          to: targetId,
          relationType: relation.relationType,
          sourceLabel: relation.source,
          sourceKind: relation.sourceKind,
        });
        if (batch.node.depth === 0) directRelationships.push(relation);
      }
    }

    frontier = next;
  }

  return { rootId, nodes: [...nodes.values()], edges, directRelationships, truncated };
}

/** Multi-hop expansion always reuses the guild-scoped relationship query at every hop. */
export function findAtlasGraph(
  guildId: string | null,
  root: { title: string; category: string; url?: string | null },
  options: AtlasGraphOptions = {},
): Promise<AtlasGraphResult> {
  return buildAtlasGraph(
    root,
    (node, limit) => findAtlasRelationships(guildId, node.title, node.category, node.url, limit),
    options,
  );
}

export function createAtlasDiscordUrl(guildId: string, channelId: string | null): string | null {
  if (!/^\d{17,20}$/.test(guildId) || !channelId || !/^\d{17,20}$/.test(channelId)) return null;
  return "https://discord.com/channels/" + guildId + "/" + channelId;
}

export function archiveMediaTypesForCategory(category: string): string[] {
  switch (normalizeAtlasCategory(category)) {
    case "ANIME": return ["anime"];
    case "MANGA": return ["manga", "manhwa", "manhua", "webtoon"];
    case "LIGHT_NOVEL": return ["light novel", "light_novel"];
    case "WEBNOVEL": return ["webnovel", "web novel"];
    case "BOOK": return ["book"];
    case "MOVIE": return ["movie", "film"];
    case "TV": return ["tv", "television", "series"];
    case "GAME": return ["game", "video game"];
    default: return [];
  }
}

interface AtlasCommunityRow {
  id: string;
  title: string;
  channel_id?: string | null;
  thread_id?: string | null;
  activity_type?: string | null;
}

function communityRelation(
  row: AtlasCommunityRow, category: MediaCategory, relationType: string,
  source: string, guildId: string, channelId?: string | null,
): AtlasRelation {
  return {
    title: row.title, category,
    url: createAtlasDiscordUrl(guildId, row.thread_id ?? channelId ?? null),
    relationType, source, sourceKind: "community",
  };
}

/**
 * Read community entities associated with a selected media identity.
 * Every query is scoped to the invoking guild; archive entries must be approved
 * and visible, and discussions/sessions must still be active before appearing.
 */
export async function findAtlasCommunityLinks(
  guildId: string | null, title: string, category: string,
  url?: string | null, providerId?: string | null, limit = 20,
): Promise<AtlasRelation[]> {
  const titleKey = normalizeAtlasTitle(title);
  const mediaCategory = normalizeAtlasCategory(category);
  if (!guildId || !/^\d{17,20}$/.test(guildId) || !titleKey || !mediaCategory) return [];

  const safeUrl = safeAtlasUrl(url) ?? "";
  const aniListId = providerId && /^\d{1,12}$/.test(providerId)
    && (mediaCategory === "MANGA" || mediaCategory === "LIGHT_NOVEL") ? providerId : "";
  const archiveTypes = archiveMediaTypesForCategory(mediaCategory);
  const maximum = Math.max(1, Math.min(limit, 20));
  const matchArchive =
    "e.status = 'approved' " +
    "AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)) " +
    "AND lower(btrim(e.media_type)) = ANY($4::text[]) " +
    "AND ((lower(btrim(COALESCE(e.source_title, ''))) = lower(btrim($2)) " +
    "AND (e.source_url IS NULL OR $3 = '' OR e.source_url = $3)) " +
    "OR ($5 <> '' AND e.linked_media_provider = 'AniList' AND e.linked_media_id = $5))";

  const [archives, collections, discussions, sessions, reading, rankings] = await Promise.all([
    archiveTypes.length ? query<AtlasCommunityRow>(
      "SELECT e.id::text AS id, e.title FROM community_archive_entries e WHERE " + matchArchive +
      " ORDER BY e.created_at DESC LIMIT $6",
      [guildId,title,safeUrl,archiveTypes,aniListId,maximum],
    ) : Promise.resolve([] as AtlasCommunityRow[]),
    archiveTypes.length ? query<AtlasCommunityRow>(
      "SELECT DISTINCT c.id::text AS id, c.title FROM archive_collections c " +
      "WHERE c.guild_id = $1 AND c.status = 'active' AND EXISTS (" +
      " SELECT 1 FROM archive_collection_items ci " +
      " JOIN community_archive_entries e ON e.id = ci.entry_id " +
      " WHERE ci.collection_id = c.id AND " + matchArchive +
      ") ORDER BY c.title LIMIT $6",
      [guildId,title,safeUrl,archiveTypes,aniListId,maximum],
    ) : Promise.resolve([] as AtlasCommunityRow[]),
    query<AtlasCommunityRow>(
      "SELECT d.id::text AS id, d.title, d.channel_id::text AS channel_id, d.thread_id::text AS thread_id " +
      "FROM community_discussions d WHERE d.guild_id = $1 AND d.status = 'open' " +
      "AND (d.closes_at IS NULL OR d.closes_at > NOW()) " +
      "AND (lower(btrim(COALESCE(d.media_title, ''))) = lower(btrim($2)) OR ($3 <> '' AND d.media_url = $3)) " +
      "ORDER BY d.created_at DESC LIMIT $4",
      [guildId,title,safeUrl,maximum],
    ),
    query<AtlasCommunityRow>(
      "SELECT s.id::text AS id, s.title, s.channel_id::text AS channel_id, s.thread_id::text AS thread_id, s.activity_type " +
      "FROM community_sessions s WHERE s.guild_id = $1 AND s.status IN ('scheduled','open') " +
      "AND s.scheduled_at >= NOW() " +
      "AND (lower(btrim(COALESCE(s.media_title, ''))) = lower(btrim($2)) OR ($3 <> '' AND s.media_url = $3)) " +
      "ORDER BY s.scheduled_at ASC LIMIT $4",
      [guildId,title,safeUrl,maximum],
    ),
    query<AtlasCommunityRow>(
      "SELECT n.id::text AS id, n.title, n.channel_id::text AS channel_id, n.thread_id::text AS thread_id " +
      "FROM community_reading_nominations n WHERE n.guild_id = $1 AND n.status IN ('open','selected') " +
      "AND (lower(btrim(n.title)) = lower(btrim($2)) OR ($3 <> '' AND n.source_url = $3)) " +
      "ORDER BY n.created_at DESC LIMIT $4",
      [guildId,title,safeUrl,maximum],
    ),
    query<AtlasCommunityRow>(
      "SELECT r.id::text AS id, r.title, r.channel_id::text AS channel_id FROM community_rankings r " +
      "JOIN community_ranking_candidates c ON c.ranking_id = r.id " +
      "WHERE r.guild_id = $1 AND r.status IN ('open','closed') AND c.status = 'approved' " +
      "AND (lower(btrim(c.title)) = lower(btrim($2)) OR ($3 <> '' AND c.source_url = $3)) " +
      "ORDER BY r.created_at DESC LIMIT $4",
      [guildId,title,safeUrl,maximum],
    ),
  ]);

  const relations: AtlasRelation[] = [
    ...archives.map(row => communityRelation(row,"ARCHIVE_ENTRY","Contributed to","Community Archive",guildId)),
    ...collections.map(row => communityRelation(row,"ARCHIVE_COLLECTION","Included in","Archive collection",guildId)),
    ...discussions.map(row => communityRelation(row,"DISCUSSION","Discussed in","Spoiler-aware discussion",guildId,row.channel_id)),
    ...sessions.map(row => communityRelation(row,"ACTIVITY","Scheduled community session",
      "Community session · " + (row.activity_type ?? "activity"),guildId,row.channel_id)),
    ...reading.map(row => communityRelation(row,"ACTIVITY","Nominated for","Community reading club",guildId,row.channel_id)),
    ...rankings.map(row => communityRelation(row,"ACTIVITY","Included in","Community ranking",guildId,row.channel_id)),
  ];
  const seen = new Set<string>();
  return relations.filter(relation => {
    const key = [relation.category,normalizeAtlasTitle(relation.title),relation.url ?? "",relation.source].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0,maximum);
}

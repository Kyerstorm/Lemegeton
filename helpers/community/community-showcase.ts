import { query } from "../../database.js";

export type CommunityShowcaseKind = "collection" | "trail" | "ranking" | "tournament" | "creation" | "session" | "discussion";

export interface CommunityShowcaseEntry {
  id: string;
  kind: CommunityShowcaseKind;
  title: string;
  description: string;
  creator_id: string;
  created_at: Date;
  item_count: number;
  result_title: string | null;
  detail_label: string | null;
  source_url: string | null;
}

export function orderCommunityShowcaseEntries(
  entries: readonly CommunityShowcaseEntry[],
  limit = 15,
): CommunityShowcaseEntry[] {
  const boundedLimit = Math.max(1, Math.min(25, Math.floor(limit) || 15));
  return [...entries]
    .sort((left, right) => right.created_at.getTime() - left.created_at.getTime())
    .slice(0, boundedLimit);
}

export async function listCommunityShowcase(guildId: string, limit = 15): Promise<CommunityShowcaseEntry[]> {
  const boundedLimit = Math.max(1, Math.min(25, Math.floor(limit) || 15));
  const [collections, trails, rankings, tournaments, creations, sessions, discussions] = await Promise.all([
    query<CommunityShowcaseEntry>(
      "SELECT c.id::text, 'collection'::text AS kind, c.title, c.description, " +
      "c.owner_id::text AS creator_id, c.updated_at AS created_at, COUNT(DISTINCT e.id)::INT AS item_count, " +
      "NULL::text AS result_title, NULL::text AS detail_label, NULL::text AS source_url FROM archive_collections c " +
      "JOIN archive_collection_items ci ON ci.collection_id = c.id " +
      "JOIN community_archive_entries e ON e.id = ci.entry_id AND e.status = 'approved' " +
      "AND ((c.visibility = 'global' AND e.visibility = 'global') OR " +
      "(c.visibility = 'server' AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)))) " +
      "WHERE c.status = 'active' AND (c.visibility = 'global' OR c.guild_id = $1) " +
      "GROUP BY c.id HAVING COUNT(DISTINCT e.id) > 0 ORDER BY c.updated_at DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT t.id::text, 'trail'::text AS kind, t.title, t.introduction AS description, " +
      "t.owner_id::text AS creator_id, t.updated_at AS created_at, COUNT(DISTINCT e.id)::INT AS item_count, " +
      "NULL::text AS result_title, NULL::text AS detail_label, NULL::text AS source_url FROM archive_trails t " +
      "JOIN archive_trail_steps s ON s.trail_id = t.id " +
      "JOIN community_archive_entries e ON e.id = s.entry_id AND e.status = 'approved' " +
      "AND ((t.visibility = 'global' AND e.visibility = 'global') OR " +
      "(t.visibility = 'server' AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)))) " +
      "WHERE t.status = 'active' AND (t.visibility = 'global' OR t.guild_id = $1) " +
      "GROUP BY t.id HAVING COUNT(DISTINCT e.id) > 0 ORDER BY t.updated_at DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT r.id::text, 'ranking'::text AS kind, r.title, r.description, " +
      "r.creator_id::text AS creator_id, COALESCE(r.closed_at, r.created_at) AS created_at, " +
      "COUNT(DISTINCT c.id)::INT AS item_count, NULL::text AS result_title, " +
      "NULL::text AS detail_label, NULL::text AS source_url " +
      "FROM community_rankings r JOIN community_ranking_candidates c " +
      "ON c.ranking_id = r.id AND c.status = 'approved' " +
      "WHERE r.guild_id = $1 AND r.status = 'closed' AND r.kind = 'ranking' " +
      "GROUP BY r.id HAVING COUNT(DISTINCT c.id) > 0 " +
      "ORDER BY COALESCE(r.closed_at, r.created_at) DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT t.id::text, 'tournament'::text AS kind, t.title, t.description, " +
      "t.creator_id::text AS creator_id, COALESCE(t.closed_at, t.created_at) AS created_at, " +
      "1::INT AS item_count, champion.title AS result_title, NULL::text AS detail_label, " +
      "NULL::text AS source_url FROM community_tournaments t " +
      "JOIN community_tournament_candidates champion " +
      "ON champion.id = t.winner_candidate_id AND champion.status = 'champion' " +
      "WHERE t.guild_id = $1 AND t.status = 'completed' " +
      "ORDER BY COALESCE(t.closed_at, t.created_at) DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT e.id::text, 'creation'::text AS kind, e.title, ''::text AS description, " +
      "e.created_by::text AS creator_id, e.created_at, 1::INT AS item_count, " +
      "e.archive_type AS result_title, e.media_type AS detail_label, e.source_url " +
      "FROM community_archive_entries e WHERE e.status = 'approved' " +
      "AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $1)) " +
      "ORDER BY e.created_at DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT s.id::text, 'session'::text AS kind, s.title, ''::text AS description, " +
      "s.host_id::text AS creator_id, s.scheduled_at AS created_at, 1::INT AS item_count, " +
      "s.activity_type AS result_title, NULL::text AS detail_label, s.media_url AS source_url " +
      "FROM community_sessions s WHERE s.guild_id = $1 AND s.status IN ('scheduled','open') AND s.scheduled_at < NOW() " +
      "ORDER BY s.scheduled_at DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
    query<CommunityShowcaseEntry>(
      "SELECT d.id::text, 'discussion'::text AS kind, d.title, ''::text AS description, " +
      "d.creator_id::text AS creator_id, d.created_at, 1::INT AS item_count, " +
      "'Media discussion'::text AS result_title, " +
      "CASE WHEN d.spoiler_boundary IS NULL THEN 'Discussion' ELSE 'Spoiler-aware discussion' END::text AS detail_label, " +
      "d.media_url AS source_url FROM community_discussions d " +
      "WHERE d.guild_id = $1 AND d.status = 'closed' " +
      "ORDER BY d.created_at DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
  ]);
  return orderCommunityShowcaseEntries(
    [...collections, ...trails, ...rankings, ...tournaments, ...creations, ...sessions, ...discussions],
    boundedLimit,
  );
}

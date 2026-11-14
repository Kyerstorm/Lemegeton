import { query } from "../../database.js";

export type CommunityShowcaseKind = "collection" | "trail" | "ranking" | "tournament";

export interface CommunityShowcaseEntry {
  id: string;
  kind: CommunityShowcaseKind;
  title: string;
  description: string;
  creator_id: string;
  created_at: Date;
  item_count: number;
  result_title: string | null;
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
  const [collections, trails, rankings, tournaments] = await Promise.all([
    query<CommunityShowcaseEntry>(
      "SELECT c.id::text, 'collection'::text AS kind, c.title, c.description, " +
      "c.owner_id::text AS creator_id, c.updated_at AS created_at, COUNT(DISTINCT e.id)::INT AS item_count, " +
      "NULL::text AS result_title FROM archive_collections c " +
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
      "NULL::text AS result_title FROM archive_trails t " +
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
      "COUNT(DISTINCT c.id)::INT AS item_count, NULL::text AS result_title " +
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
      "1::INT AS item_count, champion.title AS result_title " +
      "FROM community_tournaments t JOIN community_tournament_candidates champion " +
      "ON champion.id = t.winner_candidate_id AND champion.status = 'champion' " +
      "WHERE t.guild_id = $1 AND t.status = 'completed' " +
      "ORDER BY COALESCE(t.closed_at, t.created_at) DESC LIMIT $2",
      [guildId, boundedLimit],
    ),
  ]);
  return orderCommunityShowcaseEntries([...collections, ...trails, ...rankings, ...tournaments], boundedLimit);
}

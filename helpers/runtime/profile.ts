import { query, queryOne } from "../../database.js";
import type { AniListUserInterests, AniListUserProfile } from "../providers/anilist.js";
import { AniListClient } from "../providers/anilist.js";
import type { SteamProfile } from "../providers/steam.js";
import { SteamClient } from "../providers/steam.js";
import { cleanText } from "../security/security.js";

export interface ProfilePreferences {
  guild_id: string;
  user_id: string;
  public_profile: boolean;
  show_anilist: boolean;
  show_steam: boolean;
  allow_affinity: boolean;
  server_taste_opt_in: boolean;
  share_leaderboard: boolean;
}

export interface LinkedProfile {
  discordId: string;
  anilistUsername: string | null;
  steamId: string | null;
  steamVanityName: string | null;
  preferences: ProfilePreferences;
  anilist: AniListUserProfile | null;
  steam: SteamProfile | null;
  contributions: number;
}

function defaultPreferences(guildId: string, userId: string): ProfilePreferences {
  return {
    guild_id: guildId,
    user_id: userId,
    public_profile: false,
    show_anilist: true,
    show_steam: true,
    allow_affinity: false,
    server_taste_opt_in: false,
    share_leaderboard: false,
  };
}

export async function getProfilePreferences(guildId: string, userId: string): Promise<ProfilePreferences> {
  const row = await queryOne<ProfilePreferences>(
    "SELECT guild_id, user_id, public_profile, show_anilist, show_steam, allow_affinity, server_taste_opt_in, share_leaderboard FROM profile_preferences WHERE guild_id = $1 AND user_id = $2",
    [guildId, userId],
  );
  return row ?? defaultPreferences(guildId, userId);
}

export async function updateProfilePreferences(
  guildId: string,
  userId: string,
  changes: Partial<Omit<ProfilePreferences, "guild_id" | "user_id">>,
): Promise<ProfilePreferences> {
  const current = await getProfilePreferences(guildId, userId);
  const next = { ...current, ...changes };
  await query(
    `INSERT INTO profile_preferences
     (guild_id, user_id, public_profile, show_anilist, show_steam, allow_affinity, server_taste_opt_in, share_leaderboard, updated_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
     ON CONFLICT (guild_id, user_id) DO UPDATE SET
       public_profile = EXCLUDED.public_profile,
       show_anilist = EXCLUDED.show_anilist,
       show_steam = EXCLUDED.show_steam,
       allow_affinity = EXCLUDED.allow_affinity,
       server_taste_opt_in = EXCLUDED.server_taste_opt_in,
       share_leaderboard = EXCLUDED.share_leaderboard,
       updated_at = NOW()`,
    [
      guildId, userId, next.public_profile, next.show_anilist, next.show_steam,
      next.allow_affinity, next.server_taste_opt_in, next.share_leaderboard,
    ],
  );
  return next;
}

export async function linkAniListAccount(
  guildId: string,
  userId: string,
  discordUsername: string,
  aniList: AniListClient,
  username: string,
): Promise<AniListUserProfile> {
  const profile = await aniList.getUser(username);
  if (!profile) throw new Error("AniList could not verify that username. Check its spelling and try again.");
  await query(
    `INSERT INTO users (discord_id, guild_id, username, anilist_username, anilist_id, updated_at)
     VALUES ($1, $2, $3, $4, $5, NOW())
     ON CONFLICT (discord_id, guild_id) DO UPDATE SET
       username = EXCLUDED.username,
       anilist_username = EXCLUDED.anilist_username,
       anilist_id = EXCLUDED.anilist_id,
       updated_at = NOW()`,
    [userId, guildId, cleanText(discordUsername, 100), profile.name, profile.id],
  );
  // Provider linking never overrides the member's existing display/privacy consent.
  return profile;
}

export async function unlinkAniListAccount(guildId: string, userId: string): Promise<boolean> {
  const result = await queryOne<{ discord_id: string }>(
    "UPDATE users SET anilist_username = NULL, anilist_id = NULL, updated_at = NOW() WHERE discord_id = $1 AND guild_id = $2 AND anilist_username IS NOT NULL RETURNING discord_id",
    [userId, guildId],
  );
  return Boolean(result);
}

export async function linkSteamAccount(
  guildId: string,
  userId: string,
  vanityInput: string,
  steam: SteamClient,
): Promise<SteamProfile> {
  const steamId = await steam.resolveSteamId(vanityInput);
  const profile = await steam.getProfile(steamId);
  await query(
    `INSERT INTO steam_users (discord_id, guild_id, steam_id, vanity_name, updated_at)
     VALUES ($1, $2, $3, $4, NOW())
     ON CONFLICT (discord_id, guild_id) DO UPDATE SET
       steam_id = EXCLUDED.steam_id,
       vanity_name = EXCLUDED.vanity_name,
       updated_at = NOW()`,
    [userId, guildId, steamId, profile.personaName],
  );
  // Provider linking never overrides the member's existing display/privacy consent.
  return profile;
}

export async function unlinkSteamAccount(guildId: string, userId: string): Promise<boolean> {
  const result = await queryOne<{ discord_id: string }>("DELETE FROM steam_users WHERE discord_id = $1 AND guild_id = $2 RETURNING discord_id", [userId, guildId]);
  return Boolean(result);
}

export async function getLinkedProfile(
  guildId: string,
  userId: string,
  discordUsername: string,
  aniList: AniListClient,
  steam: SteamClient,
  allowPrivate = false,
): Promise<LinkedProfile | null> {
  const preferences = await getProfilePreferences(guildId, userId);
  if (!allowPrivate && !preferences.public_profile) return null;
  const [user, steamLink] = await Promise.all([
    queryOne<{ anilist_username: string | null }>(
      "SELECT anilist_username FROM users WHERE discord_id = $1 AND guild_id = $2",
      [userId, guildId],
    ),
    queryOne<{ steam_id: string; vanity_name: string }>(
      "SELECT steam_id, vanity_name FROM steam_users WHERE discord_id = $1 AND guild_id = $2",
      [userId, guildId],
    ),
  ]);
  const [anilist, steamProfile, contribution] = await Promise.all([
    user?.anilist_username && preferences.show_anilist
      ? aniList.getUser(user.anilist_username).catch(() => null)
      : Promise.resolve(null),
    steamLink && preferences.show_steam
      ? steam.getProfile(steamLink.steam_id).catch(() => null)
      : Promise.resolve(null),
    queryOne<{ count: string }>(
      `SELECT COUNT(*) AS count FROM community_archive_entries
       WHERE created_guild_id = $1 AND created_by = $2
         AND status = 'approved' AND visibility = 'server'`,
      [guildId, userId],
    ).catch(() => null),
  ]);
  return {
    discordId: userId,
    anilistUsername: user?.anilist_username ?? null,
    steamId: steamLink?.steam_id ?? null,
    steamVanityName: steamLink?.vanity_name ?? null,
    preferences,
    anilist,
    steam: steamProfile,
    contributions: Number(contribution?.count ?? 0),
  };
}

function weightedGenreOverlap(
  first: Array<{ genre: string; count: number }>,
  second: Array<{ genre: string; count: number }>,
): { percent: number; shared: Array<{ genre: string; first: number; second: number }> } {
  const left = new Map(first.map((item) => [item.genre, Math.max(0, item.count)]));
  const right = new Map(second.map((item) => [item.genre, Math.max(0, item.count)]));
  const names = new Set([...left.keys(), ...right.keys()]);
  if (!names.size) return { percent: 0, shared: [] };
  let minimum = 0;
  let maximum = 0;
  for (const name of names) {
    const a = left.get(name) ?? 0;
    const b = right.get(name) ?? 0;
    minimum += Math.min(a, b);
    maximum += Math.max(a, b);
  }
  const shared = [...names]
    .filter((name) => left.has(name) && right.has(name))
    .map((genre) => ({ genre, first: left.get(genre) ?? 0, second: right.get(genre) ?? 0 }))
    .sort((a, b) => Math.min(b.first, b.second) - Math.min(a.first, a.second))
    .slice(0, 8);
  return { percent: maximum ? Math.round((minimum / maximum) * 100) : 0, shared };
}

export function getAniListProfileAchievements(profile: AniListUserProfile): Array<{ title: string; detail: string }> {
  const achievements: Array<{ title: string; detail: string }> = [];
  if (profile.anime.count >= 100) achievements.push({ title: "Anime shelf", detail: "100+ entries on the linked AniList profile" });
  if (profile.anime.count >= 500) achievements.push({ title: "Anime archive", detail: "500+ entries on the linked AniList profile" });
  if (profile.manga.count >= 50) achievements.push({ title: "Manga shelf", detail: "50+ entries on the linked AniList profile" });
  if (profile.manga.count >= 200) achievements.push({ title: "Manga archive", detail: "200+ entries on the linked AniList profile" });
  if (profile.anime.count >= 10 && profile.anime.meanScore >= 80) {
    achievements.push({ title: "High anime average", detail: "AniList-reported mean score of 80 or higher across 10+ entries" });
  }
  return achievements;
}

export async function getAniListAffinity(
  guildId: string,
  firstUserId: string,
  secondUserId: string,
  aniList: AniListClient,
): Promise<{ first: string; second: string; percent: number; sharedAnime: string[]; sharedManga: string[] }> {
  if (firstUserId === secondUserId) throw new Error("Choose another member to compare interests.");
  const [firstPrefs, secondPrefs] = await Promise.all([
    getProfilePreferences(guildId, firstUserId),
    getProfilePreferences(guildId, secondUserId),
  ]);
  if (!firstPrefs.allow_affinity || !secondPrefs.allow_affinity) {
    throw new Error("Both members must opt in to AniList affinity sharing.");
  }
  const [firstLink, secondLink] = await Promise.all([
    queryOne<{ anilist_username: string | null }>("SELECT anilist_username FROM users WHERE guild_id = $1 AND discord_id = $2", [guildId, firstUserId]),
    queryOne<{ anilist_username: string | null }>("SELECT anilist_username FROM users WHERE guild_id = $1 AND discord_id = $2", [guildId, secondUserId]),
  ]);
  if (!firstLink?.anilist_username || !secondLink?.anilist_username) throw new Error("Both members need linked AniList accounts.");
  const [first, second] = await Promise.all([
    aniList.getUser(firstLink.anilist_username),
    aniList.getUser(secondLink.anilist_username),
  ]);
  if (!first || !second) throw new Error("AniList could not retrieve both shared profiles.");
  const anime = weightedGenreOverlap(first.anime.genres, second.anime.genres);
  const manga = weightedGenreOverlap(first.manga.genres, second.manga.genres);
  const score = Math.round(anime.percent * 0.6 + manga.percent * 0.4);
  return {
    first: first.name,
    second: second.name,
    percent: score,
    sharedAnime: anime.shared.map((item) => item.genre),
    sharedManga: manga.shared.map((item) => item.genre),
  };
}

export type AniListLeaderboardMedium = "anime" | "manga";
export interface AniListLeaderboardEntry {
  userId: string;
  aniListName: string;
  aniListUrl: string;
  entries: number;
  meanScore: number;
}

export async function getAniListLeaderboard(
  guildId: string,
  memberIds: ReadonlySet<string>,
  medium: AniListLeaderboardMedium,
  aniList: AniListClient,
): Promise<{ entries: AniListLeaderboardEntry[]; optedIn: number; checked: number }> {
  const rows = await query<{ user_id: string; anilist_username: string }>(
    `SELECT u.discord_id AS user_id, u.anilist_username
       FROM users u
       JOIN profile_preferences p ON p.guild_id = u.guild_id AND p.user_id = u.discord_id
      WHERE u.guild_id = $1 AND p.share_leaderboard = TRUE
        AND u.anilist_username IS NOT NULL
      ORDER BY u.discord_id`,
    [guildId],
  );
  const candidates = rows.filter(row => memberIds.has(row.user_id));
  if (candidates.length < 3) throw new Error("The AniList leaderboard is hidden until at least three current server members opt in.");

  const selected = candidates.slice(0, 100);
  const entries: AniListLeaderboardEntry[] = [];
  for (let index = 0; index < selected.length; index += 4) {
    const batch = await Promise.all(selected.slice(index, index + 4).map(async row => {
      try {
        const profile = await aniList.getUser(row.anilist_username);
        if (!profile) return null;
        const stats = profile[medium];
        return {
          userId: row.user_id,
          aniListName: profile.name,
          aniListUrl: profile.url,
          entries: stats.count,
          meanScore: stats.meanScore,
        } satisfies AniListLeaderboardEntry;
      } catch {
        return null;
      }
    }));
    entries.push(...batch.filter((entry): entry is AniListLeaderboardEntry => entry !== null));
  }
  if (entries.length < 3) throw new Error("The AniList leaderboard is hidden until at least three opted-in profiles can be retrieved.");
  entries.sort((left, right) => right.entries - left.entries || right.meanScore - left.meanScore || left.aniListName.localeCompare(right.aniListName));
  return { entries: entries.slice(0, 10), optedIn: candidates.length, checked: selected.length };
}

export async function getServerTaste(
  guildId: string,
  aniList: AniListClient,
): Promise<{
  participants: number;
  anime: Array<{genre:string;count:number}>;
  manga: Array<{genre:string;count:number}>;
  animeTags: Array<{tag:string;count:number}>;
  mangaTags: Array<{tag:string;count:number}>;
}> {
  const participants = await query<{ anilist_username: string }>(
    `SELECT u.anilist_username
     FROM users u
     JOIN profile_preferences p ON p.guild_id = u.guild_id AND p.user_id = u.discord_id
     WHERE u.guild_id = $1 AND p.server_taste_opt_in = TRUE
       AND p.show_anilist = TRUE AND u.anilist_username IS NOT NULL`,
    [guildId],
  );
  if (participants.length < 3) throw new Error("Server Taste is hidden until at least three members opt in.");

  const profiles: AniListUserInterests[] = [];
  for (let index = 0; index < participants.length; index += 4) {
    const batch = await Promise.all(participants.slice(index,index+4).map((row) =>
      aniList.getUserInterests(row.anilist_username).catch(() => null),
    ));
    profiles.push(...batch.filter((item): item is AniListUserInterests => item !== null));
  }
  if (profiles.length < 3) {
    throw new Error("Server Taste is hidden until at least three opted-in AniList lists are publicly accessible.");
  }

  const countUnique = (select: (profile:AniListUserInterests)=>string[]) => {
    const counts = new Map<string,number>();
    for (const profile of profiles) for (const item of new Set(select(profile))) {
      counts.set(item,(counts.get(item)??0)+1);
    }
    return [...counts].map(([name,count])=>({name,count})).sort((a,b)=>b.count-a.count).slice(0,8);
  };
  return {
    participants: profiles.length,
    anime: countUnique((profile)=>profile.anime.genres).map(({name, count})=>({genre:name,count})),
    manga: countUnique((profile)=>profile.manga.genres).map(({name, count})=>({genre:name,count})),
    animeTags: countUnique((profile)=>profile.anime.tags).map(({name, count})=>({tag:name,count})),
    mangaTags: countUnique((profile)=>profile.manga.tags).map(({name, count})=>({tag:name,count})),
  };
}

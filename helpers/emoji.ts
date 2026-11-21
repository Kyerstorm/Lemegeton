/**
 * Text-only compatibility exports for existing bot response builders.
 *
 * Interface names remain stable while all decorative emoji output is disabled.
 * Dashboard iconography is provided by the animated SVG component library.
 */
const EMOJI_NAMES = [
  "loading",
  "working",
  "success",
  "approve",
  "reject",
  "warning",
  "error",
  "info",
  "question",
  "close",
  "closed",
  "completedClose",
  "back",
  "next",
  "previous",
  "refresh",
  "swap",
  "search",
  "filter",
  "sort",
  "expand",
  "collapse",
  "link",
  "externalLink",
  "copy",
  "upload",
  "download",
  "lock",
  "unlock",
  "settings",
  "anime",
  "manga",
  "lightNovel",
  "book",
  "webNovel",
  "movie",
  "television",
  "game",
  "soundtrack",
  "creator",
  "studio",
  "music",
  "language",
  "customRole",
  "random",
  "trending",
  "popular",
  "recommendation",
  "idea",
  "calendar",
  "clock",
  "bookmark",
  "archive",
  "collection",
  "community",
  "vote",
  "discussion",
  "event",
  "profile",
  "leaderboard",
  "gift",
  "hourglass",
  "check",
  "cross",
  "heart",
  "target",
  "stats",
  "popularity",
  "recommended",
  "panels",
  "quote",
  "fanworks",
  "moodboard",
  "scenes",
  "theory",
  "globe",
  "mangaDiscovery",
  "lightNovelDiscovery",
  "film",
  "theatre",
  "microphone",
  "building",
  "rankingAnime",
  "rankingManga",
  "rankingCombined",
  "rankingChapters",
  "rankingEpisodes",
  "finish",
  "goldMedal",
  "silverMedal",
  "bronzeMedal",
  "chevronLeft",
  "chevronRight",
  "bell",
  "activityBubble",
  "crown",
  "testing",
  "pause",
  "tools",
  "performance",
  "bug",
  "rocket",
  "chevronLeftPlain",
  "chevronRightPlain",
  "anilist",
  "steam",
  "epicGames",
  "gog",
  "login",
  "shoppingCart",
  "IGDB",
  "Novelfire",
  "openlibrary",
  "Letterboxd",
  "TMDB",
  "RoyalRoad",
  "MangaDex",
  "GoogleBooks",
  "crossref",
  "Spotify",
  "Soundcloud",
  "Youtube",
  "kitsu",
  "Novelupdates",
  "wuxiaclick",
  "scribblehub",
  "NovelArchive",
  "NoveliTo",
] as const;

export type EmojiName = (typeof EMOJI_NAMES)[number];

export const emoji = Object.fromEntries(
  EMOJI_NAMES.map((name) => [name, ""]),
) as Record<EmojiName, string>;

export function customEmoji(
  _name: string,
  _id: string,
  _animated = false,
): string {
  return "";
}

export function withEmoji(_name: EmojiName, text: string): string {
  return text;
}

export function loadingMessage(activity: string): string {
  return activity;
}

export function providerEmoji(_provider: string): string {
  return "";
}

export function providerFooter(
  provider: string,
  detail = "Source metadata",
): string {
  const label = provider.trim().slice(0, 80) || "Metadata provider";
  const suffix = detail.trim();
  return (suffix ? `${label} · ${suffix}` : label).slice(0, 2_048);
}

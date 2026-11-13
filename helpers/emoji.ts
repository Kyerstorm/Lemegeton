/**
 * Central Unicode emoji palette for bot responses.
 *
 * Keep every current emoji value here so future animated/custom replacements only
 * require changes to this file. Do not embed custom Discord emoji IDs in the palette.
 */
export const emoji = {
  // Interaction states
  loading: "⏳",
  working: "🔄",
  success: "✅",
  approve: "✅",
  reject: "❌",
  warning: "⚠️",
  error: "❌",
  info: "ℹ️",
  question: "❓",
  close: "✖️",
  closed: "🔒",
  completedClose: "✅",

  // Navigation and controls
  back: "◀️",
  next: "▶️",
  previous: "⬅️",
  refresh: "🔄",
  swap: "🔀",
  search: "🔎",
  filter: "🎚️",
  sort: "↕️",
  expand: "⤢",
  collapse: "↙️",
  link: "🔗",
  externalLink: "↗️",
  copy: "📋",
  upload: "📤",
  download: "📥",
  lock: "🔒",
  unlock: "🔓",
  settings: "⚙️",

  // Media categories
  anime: "📺",
  manga: "📖",
  lightNovel: "📚",
  book: "📕",
  webNovel: "📝",
  movie: "🎬",
  television: "📡",
  game: "🎮",
  soundtrack: "🎵",
  creator: "✍️",
  studio: "🎨",

  // Discovery and community
  random: "🎲",
  trending: "📈",
  popular: "🔥",
  recommendation: "💡",
  calendar: "🗓️",
  clock: "🕒",
  bookmark: "🔖",
  archive: "🗃️",
  collection: "🗂️",
  community: "👥",
  vote: "🗳️",
  discussion: "💬",
  event: "📅",
  profile: "👤",
  leaderboard: "🏆",
  gift: "🎁",

  // Additional interface symbols kept as Unicode for future replacement.
  hourglass: "⌛", warningUnicode: "⚠️", warningPlain: "⚠",
  check: "✅", cross: "❌", heart: "❤️", target: "🎯", stats: "📊", popularity: "🔥",
  recommended: "⭐", panels: "📚", quote: "💬", fanworks: "🎨", moodboard: "🖼️",
  scenes: "🎬", theory: "💡", globe: "🌐", mangaDiscovery: "📚", lightNovelDiscovery: "📖",
  film: "🎞️", theatre: "🎭", microphone: "🎙️", building: "🏢",
  rankingAnime: "🎬", rankingManga: "📖", rankingCombined: "🌟",
  rankingChapters: "📚", rankingEpisodes: "📺", finish: "🏁",
  goldMedal: "🥇", silverMedal: "🥈", bronzeMedal: "🥉",
  refreshUnicode: "🔄", chevronLeft: "◀️", chevronRight: "▶️",
  bell: "🔔", activityBubble: "🗨️", crown: "👑",
  testing: "🧪", pause: "⏸️", tools: "🔧", performance: "⚡", bug: "🐛", rocket: "🚀",
  chevronLeftPlain: "◀", chevronRightPlain: "▶",

  // Provider and account markers
  anilist: "📚",
  steam: "🎮",
  epicGames: "🎮",
  gog: "🎮",
  login: "🔑",
  shoppingCart: "🛒",
} as const;

export type EmojiName = keyof typeof emoji;

export function customEmoji(name: string, id: string, animated = false): string {
  return `<${animated ? "a" : ""}:${name}:${id}>`;
}

export function withEmoji(name: EmojiName, text: string): string {
  return `${emoji[name]} ${text}`;
}

export function loadingMessage(activity: string): string {
  return `${emoji.loading} ${activity}`;
}

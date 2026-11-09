/**
 * Central emoji palette for bot responses.
 *
 * Unicode symbols are intentional fallbacks. Only use custom Discord emoji markup
 * when the emoji ID has been verified in the bot's server.
 */
export const emoji = {
  // Interaction states
  loading: "⏳",
  working: "<a:refresh:1557773578655629424>",
  success: "<a:approved:1559632013034659871>",
  approved: "<a:approved:1559632013034659871>",
  reject: "<a:reject:1559632010572734596>",
  warning: "<:error:1557775268146323467>",
  error: "<:error:1557775268146323467>",
  info: "ℹ️",
  question: "<:question:1557775415148290048>",
  close: "<:close:1557778028686213210>",
  closed: "<:closed:1559632007523475536>",
  completedClose: "<:completedclose:1557778427237503087>",

  // Navigation and controls
  back: "◀️",
  next: "▶️",
  previous: "⬅️",
  refresh: "<a:refresh:1557773578655629424>",
  swap: "<:swap:1557778022701076581>",
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
  gift: "<:gift:1557773581994303589>",

  // Provider and account markers
  anilist: "<:anilist:1557779525763338330>",
  steam: "<a:steam:1557099612135886949>",
  epicGames: "<:epicgames:1557099608532983950>",
  gog: "<:GOG:1433757557628866640>",
  login: "<:login:1557774167267475516>",
  shoppingCart: "<a:shoppingcart:1557772890382798878>",
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

export const emoji = {
  loading: "<a:loading:000000000000000000>",

  approved: "<a:approved:1559632013034659871>",
  reject: "<a:reject:1559632010572734596>",
  closed: "<:closed:1559632007523475536>",
  close: "<:close:1557778028686213210>",
  completedclose: "<:completedclose:1557778427237503087>",
  error: "<:error:1557775268146323467>",
  question: "<:question:1557775415148290048>",
  swap: "<:swap:1557778022701076581>",
  refresh: "<a:refresh:1557773578655629424>",
  login: "<:login:1557774167267475516>",
  gift: "<:gift:1557773581994303589>",
  shoppingcart: "<a:shoppingcart:1557772890382798878>",
  anilist: "<:anilist:1557779525763338330>",
  steam: "<a:steam:1557099612135886949>",
  epicgames: "<:epicgames:1557099608532983950>",
  gog: "<:GOG:1433757557628866640>",
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

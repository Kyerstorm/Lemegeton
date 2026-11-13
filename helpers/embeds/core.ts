import { EmbedBuilder } from "discord.js";
import { emoji } from "../emoji.js";

export const EMBED_COLOURS = {
  primary: 0x7c5cff,
  secondary: 0x48567d,
  success: 0x2ecc71,
  warning: 0xf1c40f,
  danger: 0xe74c3c,
  info: 0x3498db,
  neutral: 0x8291aa,
  panel: 0x1f273a,
} as const;

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as RecordValue
    : {};
}
function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value.trim() || fallback : fallback;
}
function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function safeUrl(value: unknown): string | null {
  const raw = text(value);
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}
function plainText(value: unknown, max = 1_000): string {
  return text(value)
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}
function mediaTitle(value: unknown): string {
  const title = record(value);
  return text(title.romaji) || text(title.english) || text(title.native) || "Unknown title";
}
function mediaUrl(value: unknown): string | null {
  return safeUrl(record(value).siteUrl);
}
function dateValue(value: unknown): string | null {
  const date = record(value);
  const parts = [date.year, date.month, date.day];
  if (parts.some(part => typeof part !== "number" || !Number.isInteger(part))) return null;
  return parts.map((part, index) => String(part).padStart(index === 0 ? 4 : 2, "0")).join("-");
}
function statsLine(label: string, value: unknown): string | null {
  const count = number(value);
  return count === null ? null : `**${label}:** ${Math.round(count).toLocaleString("en-US")}`;
}

/** Ports the shared activity embed builder, with bounded text and HTTPS-only media links. */
export function buildActivityEmbed(
  activity: unknown,
  activityType: string,
  user: unknown,
  body: string,
  mediaLinks: string[] = [],
  likes = 0,
  comments = 0,
): EmbedBuilder {
  const author = record(user);
  const avatar = safeUrl(record(author.avatar).large);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary);
  const authorUrl = safeUrl(author.siteUrl);
  if (authorUrl) embed.setURL(authorUrl);
  embed.setAuthor({
    name: (activityType === "Reply" ? emoji.discussion + " " : "") + text(author.name, "Unknown"),
    ...(authorUrl ? { url: authorUrl } : {}),
    ...(avatar ? { iconURL: avatar } : {}),
  });
  const cleanBody = plainText(body, 3_500);
  if (activityType === "MessageActivity") {
    embed.setDescription(`To **${plainText(text(record(record(activity).recipient).name, "Unknown"))}**\n\n${cleanBody || "*No message text*"}`);
  } else if (activityType === "ListActivity") {
    const item = record(record(activity).media);
    const title = mediaTitle(item.title);
    const progress = text(record(activity).progress) || text(record(activity).status);
    embed.setTitle(progress ? `Read Chapter ${progress} of ${title}` : title);
    const url = mediaUrl(item);
    if (url) embed.setURL(url);
    embed.setDescription(cleanBody || title);
    const cover = safeUrl(record(item.coverImage).large);
    if (cover) embed.setThumbnail(cover);
  } else {
    embed.setDescription(cleanBody || (activityType === "Reply" ? "*No reply text*" : "*No content*"));
  }
  const statParts = [`${emoji.heart} ${Math.max(0, Math.floor(likes))}`];
  if (comments > 0) statParts.push(`${emoji.discussion} ${Math.floor(comments)}`);
  embed.addFields({ name: "Stats", value: statParts.join(" · "), inline: true });
  for (const [index, link] of mediaLinks.slice(0, 5).entries()) {
    const url = safeUrl(link);
    if (!url) continue;
    if (index === 0 && /\.(?:png|jpe?g|gif|webp)(?:[?#].*)?$/i.test(url)) embed.setImage(url);
    else embed.addFields({ name: emoji.link + " Media", value: `[Open attachment](${url})`, inline: false });
  }
  return embed.setFooter({ text: "Powered by AniList" });
}

/** Summary embed used by the original AniList and shared media embed builders. */
export function buildMediaEmbed(mediaValue: unknown): EmbedBuilder {
  const media = record(mediaValue);
  const title = record(media.title);
  const romaji = text(title.romaji);
  const english = text(title.english);
  const native = text(title.native);
  let titleLine = romaji || english || native || "Unknown title";
  if (english && english !== romaji) titleLine += ` (${english})`;
  if (native && native !== romaji && native !== english) titleLine += ` | ${native}`;
  const description = plainText(media.description, 800);
  const embed = new EmbedBuilder()
    .setColor(EMBED_COLOURS.primary)
    .setTitle(titleLine.slice(0, 256))
    .setDescription(description || "*No synopsis available*");
  const url = safeUrl(media.siteUrl);
  if (url) embed.setURL(url);
  const cover = safeUrl(record(media.coverImage).large);
  const banner = safeUrl(media.bannerImage);
  if (cover) embed.setThumbnail(cover);
  if (banner) embed.setImage(banner);
  const meta: string[] = [];
  if (text(media.type)) meta.push(`**Type:** ${text(media.type)}`);
  if (text(media.status)) meta.push(`**Status:** ${text(media.status).replaceAll("_", " ")}`);
  if (number(media.episodes) !== null) meta.push(`${emoji.movie} Episodes: ${media.episodes}`);
  if (number(media.chapters) !== null) meta.push(`${emoji.manga} Chapters: ${media.chapters}`);
  if (number(media.volumes) !== null) meta.push(`${emoji.lightNovel} Volumes: ${media.volumes}`);
  const start = dateValue(media.startDate);
  const end = dateValue(media.endDate);
  if (start) meta.push(`**Start:** ${start}`);
  if (end) meta.push(`**End:** ${end}`);
  if (meta.length) embed.addFields({ name: "Info", value: meta.join("\n").slice(0, 1_000), inline: false });
  const studioValues=Array.isArray(media.studios)?media.studios:list(record(media.studios).nodes);
  const studios = studioValues
    .map(item => typeof item==="string"?item:text(record(item).name))
    .filter(Boolean)
    .slice(0, 8);
  if (studios.length) embed.addFields({ name: "Studio", value: studios.join(", ").slice(0, 900), inline: true });
  const stats = [
    number(media.popularity) !== null ? `${emoji.popularity} Popularity: ${media.popularity}` : null,
    number(media.favourites) !== null ? `${emoji.heart} Favourites: ${media.favourites}` : null,
    text(media.source) ? `${emoji.link} Source: ${text(media.source)}` : null,
  ].filter((item): item is string => Boolean(item));
  if (stats.length) embed.addFields({ name: "Stats", value: stats.join("\n").slice(0, 900), inline: true });
  const characterValue=media.characters;
  const characters=Array.isArray(characterValue)
    ? characterValue.map(item=>({role:record(item).role,node:{id:record(item).id,name:{full:record(item).name}}}))
    : list(record(characterValue).edges);
  const main = characters.filter(item => text(record(item).role).toUpperCase() === "MAIN");
  const preview = (main.length ? main : characters).slice(0, 6).flatMap(item => {
    const node = record(record(item).node);
    const id = number(node.id);
    const name = text(record(node.name).full);
    return id && name ? [`[${name.slice(0, 100)}](https://anilist.co/character/${id})`] : [];
  });
  if (preview.length) embed.addFields({ name: "Main Characters", value: preview.join(" • ").slice(0, 1_000), inline: false });
  return embed.setFooter({ text: "AniList Media" });
}

export function buildRelationsEmbeds(mediaValue: unknown): EmbedBuilder[] {
  const relationsValue=record(mediaValue).relations;
  const edges = Array.isArray(relationsValue)
    ? relationsValue.map(item=>({relationType:record(item).relation,node:{id:record(item).id,title:{romaji:record(item).title},siteUrl:record(item).url,category:record(item).category}}))
    : list(record(relationsValue).edges);
  if (!edges.length) return [new EmbedBuilder().setColor(EMBED_COLOURS.neutral).setDescription("No relations found.")];
  const embeds: EmbedBuilder[] = [];
  for (let index = 0; index < edges.length; index += 6) {
    const chunk = edges.slice(index, index + 6);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Relations");
    for (const edgeValue of chunk) {
      const edge = record(edgeValue);
      const node = record(edge.node);
      const url = mediaUrl(node);
      embed.addFields({
        name: text(edge.relationType, text(node.type, "Related")).slice(0, 256),
        value: (url ? `[${mediaTitle(node.title)}](${url})` : mediaTitle(node.title)).slice(0, 1_000),
        inline: false,
      });
    }
    const first = record(record(chunk[0]).node);
    const image = safeUrl(record(first.coverImage).large);
    if (image) embed.setThumbnail(image);
    embeds.push(embed);
  }
  return embeds;
}

export function buildCharactersEmbeds(mediaValue: unknown, support = false): EmbedBuilder[] {
  const media=record(mediaValue);
  const normalized=Array.isArray(media.characters)?media.characters:null;
  const edges = normalized
    ? normalized.map(item=>({role:record(item).role,node:{id:record(item).id,name:{full:record(item).name},image:{large:record(item).image}}}))
    : list(record(media.characters).edges);
  const selected = edges.filter(edge => (text(record(edge).role).toUpperCase() === "MAIN") !== support);
  const items = (selected.length ? selected : edges).slice(0, 48);
  if (!items.length) return [new EmbedBuilder().setColor(EMBED_COLOURS.neutral).setDescription("No characters found.")];
  const embeds: EmbedBuilder[] = [];
  for (let index = 0; index < items.length; index += 6) {
    const chunk = items.slice(index, index + 6);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle(support ? "Support Cast" : "Main Characters");
    for (const item of chunk) {
      const node = record(record(item).node);
      const id = number(node.id);
      const name = text(record(node.name).full, "Unknown");
      embed.addFields({ name: name.slice(0, 256), value: id ? `[AniList](https://anilist.co/character/${id})` : "—", inline: false });
    }
    const image = safeUrl(record(record(record(chunk[0]).node).image).large);
    if (image) embed.setThumbnail(image);
    embeds.push(embed);
  }
  return embeds;
}

export function buildStaffEmbeds(mediaValue: unknown): EmbedBuilder[] {
  const media=record(mediaValue);
  const edges = Array.isArray(media.staffCredits)
    ? media.staffCredits.map(item=>({role:record(item).role,node:{id:record(item).id,name:{full:record(item).name},siteUrl:record(item).url,image:{large:record(item).image}}}))
    : list(record(media.staff).edges);
  if (!edges.length) return [new EmbedBuilder().setColor(EMBED_COLOURS.neutral).setDescription("No staff information found.")];
  const embeds: EmbedBuilder[] = [];
  for (let index = 0; index < edges.length; index += 8) {
    const chunk = edges.slice(index, index + 8);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.secondary).setTitle("Staff");
    for (const item of chunk) {
      const node = record(record(item).node);
      const id = number(node.id);
      const name = text(record(node.name).full, "Unknown");
      const role = text(record(item).role, "Staff");
      embed.addFields({ name: name.slice(0, 256), value: `${role.slice(0, 120)}${id ? `\n[AniList](https://anilist.co/staff/${id})` : ""}`.slice(0, 1_000), inline: false });
    }
    const image = safeUrl(record(record(record(chunk[0]).node).image).large);
    if (image) embed.setThumbnail(image);
    embeds.push(embed);
  }
  return embeds;
}

export function buildStatsEmbed(mediaValue: unknown): EmbedBuilder {
  const stats = record(record(mediaValue).stats);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.success).setTitle("Stats Distribution");
  const status = list(stats.statusDistribution).flatMap(item => {
    const row = record(item);
    return text(row.status) ? [`**${text(row.status).replaceAll("_", " ").toLowerCase()}** — ${number(row.amount) ?? 0} users`] : [];
  });
  if (status.length) embed.addFields({ name: "Status Distribution", value: status.join("\n").slice(0, 1_000), inline: false });
  const scores = list(stats.scoreDistribution).map(record).sort((a,b) => (number(a.score) ?? 0) - (number(b.score) ?? 0));
  if (scores.length) embed.addFields({ name: "Score Distribution", value: scores.map(row => `${number(row.score) ?? "—"}: ${number(row.amount) ?? 0}`).join(" | ").slice(0, 1_000), inline: false });
  if (!embed.data.fields?.length) embed.setDescription("No statistical distribution data available.");
  return embed;
}

export function buildRecommendationsEmbed(mediaValue: unknown, maxItems = 5): EmbedBuilder {
  const media=record(mediaValue);
  const edges = Array.isArray(media.recommendations)
    ? media.recommendations.map(item=>({node:{mediaRecommendation:{id:record(item).id,title:{romaji:record(item).title},siteUrl:record(item).url,coverImage:{large:record(item).image}}}}))
    : list(record(media.recommendations).edges);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.warning).setTitle(emoji.target + " Recommendations")
    .setDescription("Top recommendations from AniList");
  let count = 0;
  for (const edgeValue of edges) {
    const rec = record(record(record(edgeValue).node).mediaRecommendation);
    if (!Object.keys(rec).length) continue;
    const url = mediaUrl(rec);
    embed.addFields({ name: mediaTitle(rec.title).slice(0, 256), value: url ? `[AniList](${url})` : "—", inline: false });
    const cover = safeUrl(record(rec.coverImage).large);
    if (cover) embed.setThumbnail(cover);
    count += 1;
    if (count >= Math.max(1, Math.min(maxItems, 10))) break;
  }
  if (!count) embed.setDescription("No recommendations found.");
  return embed.setFooter({ text: "AniList Recommendations" });
}

export function buildTagsEmbed(mediaValue: unknown): EmbedBuilder {
  const tags = list(record(mediaValue).tags);
  if (!tags.length) return new EmbedBuilder().setColor(EMBED_COLOURS.neutral).setDescription("No tags found.");
  const lines = tags.slice(0, 50).map(item => {
    const row = record(item);
    const name = text(row.name, "Unknown");
    const rank = number(row.rank);
    return `||${name.slice(0, 100)}||${rank === null ? "" : ` — #${rank}`}`;
  });
  return new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Tags").setDescription(lines.join("  \n").slice(0, 4_000));
}

function safeScore(value: unknown): string {
  const score = number(value);
  return score === null || score === 0 ? "—" : `${score.toFixed(1)}/100`;
}
function userUrl(user: RecordValue): string | null {
  return safeUrl(user.url ?? user.siteUrl);
}
function userStats(value: unknown, type: "anime" | "manga"): string {
  const row = record(value);
  const lines = [
    statsLine("Entries", row.count),
    `**Mean score:** ${safeScore(row.meanScore)}`,
    statsLine(type === "anime" ? "Episodes" : "Chapters", type === "anime" ? row.episodesWatched : row.chaptersRead),
    ...(type === "anime" ? [statsLine("Minutes", row.minutesWatched)] : [statsLine("Volumes", row.volumesRead)]),
  ].filter((item): item is string => Boolean(item));
  return lines.join("\n").slice(0, 1_000) || "No statistics supplied.";
}

export function buildUserProfileEmbed(userValue: unknown): EmbedBuilder {
  const user = record(userValue);
  const name = text(user.name, "Unknown User");
  const url = userUrl(user);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle(`${emoji.profile} ${name} • AniList Profile`.slice(0,256))
    .setDescription(plainText(user.about, 900) || "*No profile description provided.*");
  if (url) embed.setURL(url);
  const avatar = safeUrl(user.avatar);
  const banner = safeUrl(user.banner);
  if (avatar) embed.setThumbnail(avatar);
  if (banner) embed.setImage(banner);
  embed.addFields(
    { name: emoji.movie + " Anime Snapshot", value: userStats(user.anime, "anime"), inline: true },
    { name: emoji.lightNovel + " Manga Snapshot", value: userStats(user.manga, "manga"), inline: true },
  );
  return embed.setFooter({ text: `AniList • User ID ${number(user.id) ?? "—"}` });
}

export function buildUserStatsEmbed(userValue: unknown): EmbedBuilder {
  const user = record(userValue);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.success)
    .setTitle(`${emoji.stats} ${text(user.name, "AniList User")} • Statistics`.slice(0,256));
  const url = userUrl(user);
  if (url) embed.setURL(url);
  embed.addFields(
    { name: emoji.movie + " Anime", value: userStats(user.anime, "anime"), inline: true },
    { name: emoji.lightNovel + " Manga", value: userStats(user.manga, "manga"), inline: true },
  );
  return embed.setFooter({ text: `AniList • User ID ${number(user.id) ?? "—"}` });
}

export function buildUserFavoritesEmbed(userValue: unknown): EmbedBuilder {
  const user = record(userValue);
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.danger)
    .setTitle(`${emoji.heart} ${text(user.name, "AniList User")} • Favorites`.slice(0,256))
    .setDescription("The first five favourites from each category, as available through AniList.");
  const url = userUrl(user);
  if (url) embed.setURL(url);
  const avatar = safeUrl(user.avatar);
  if (avatar) embed.setThumbnail(avatar);
  const favorites = record(user.favorites ?? user.favourites);
  for (const [key,label,kind] of [
    ["anime",emoji.film+" Anime","media"],["manga",emoji.manga+" Manga","media"],["characters",emoji.theatre+" Characters","character"],
    ["staff",emoji.microphone+" Staff","staff"],["studios",emoji.building+" Studios","studio"],
  ] as const) {
    const rawSection=favorites[key];
    const section=record(rawSection);
    const nodes=Array.isArray(rawSection)?rawSection:list(section.nodes);
    const links = nodes.slice(0,5).flatMap(item => {
      const row = record(item);
      const title = kind === "media" ? mediaTitle(row.title)
        : kind === "studio" ? text(row.name, "Unknown")
        : text(record(row.name).full, "Unknown");
      const itemUrl = safeUrl(row.url ?? row.siteUrl);
      return [itemUrl ? `[${title.slice(0,90)}](${itemUrl})` : title.slice(0,90)];
    });
    embed.addFields({ name: label, value: links.join(", ") || "*None listed*", inline: false });
  }
  return embed.setFooter({ text: `AniList • User ID ${number(user.id) ?? "—"}` });
}

function statusEmbed(title: string, description: string, color: number, prefix: string): EmbedBuilder {
  return new EmbedBuilder().setColor(color).setTitle((prefix + " " + title).slice(0,256)).setDescription(description.slice(0,4_000));
}
export function buildErrorEmbed(title: string, description: string): EmbedBuilder {
  return statusEmbed(title, description, EMBED_COLOURS.danger, emoji.cross);
}
export function buildSuccessEmbed(title: string, description: string): EmbedBuilder {
  return statusEmbed(title, description, EMBED_COLOURS.success, emoji.check);
}
export function buildWarningEmbed(title: string, description: string): EmbedBuilder {
  return statusEmbed(title, description, EMBED_COLOURS.warning, emoji.error);
}
export function buildInfoEmbed(title: string, description: string): EmbedBuilder {
  return statusEmbed(title, description, EMBED_COLOURS.primary, emoji.info);
}
export function buildTrendingEmbed(mediaList: unknown[], title: string, description: string): EmbedBuilder {
  const embed = new EmbedBuilder().setColor(EMBED_COLOURS.warning).setTitle(title.slice(0,256)).setDescription(description.slice(0,4_000));
  for (const [index,item] of mediaList.slice(0,10).entries()) {
    const row = record(item);
    const score = number(row.averageScore);
    const url = mediaUrl(row);
    const value = score === null ? "Score unavailable" : `Score: ${score}%`;
    embed.addFields({ name: `${index+1}. ${mediaTitle(row.title)}`.slice(0,256), value: url ? `[${value}](${url})` : value, inline: false });
  }
  return embed.setFooter({ text: "Fetched from AniList" });
}

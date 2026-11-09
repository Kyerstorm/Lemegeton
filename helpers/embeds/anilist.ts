import { EmbedBuilder, type Message } from "discord.js";
import {
  AniListClient,
  type AniListMedia,
  type AniListPublicActivity,
  type AniListUserProfile,
} from "../anilist.js";
import {
  buildCharactersEmbeds,
  buildMediaEmbed,
  buildRecommendationsEmbed,
  buildRelationsEmbeds,
  buildStaffEmbeds,
  buildStatsEmbed,
  buildTagsEmbed,
  buildUserFavoritesEmbed,
  buildUserProfileEmbed,
  buildUserStatsEmbed,
  EMBED_COLOURS,
} from "./core.js";

export type AniListProfileSection = "overview" | "stats" | "favorites" | "activity";
export type AniListLinkTarget =
  | { kind: "media"; id: number; type: "ANIME" | "MANGA" }
  | { kind: "user"; username: string; section: AniListProfileSection };

const IGNORED_USER_ROUTES = new Set([
  "animelist", "anime", "anime-list", "mangalist", "manga", "manga-list",
]);

/** Recognizes only documented public media/profile URLs; personal list routes are excluded. */
export function parseAniListUrl(value: string | URL): AniListLinkTarget | null {
  let url: URL;
  try {
    url = value instanceof URL ? value : new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || !["anilist.co", "www.anilist.co"].includes(url.hostname.toLowerCase())) return null;
  const segments = url.pathname.split("/").filter(Boolean);
  const route = (segments[0] ?? "").toLowerCase();

  if (route === "anime" || route === "manga") {
    const id = Number(segments[1]);
    if (!/^\d+$/.test(segments[1] ?? "") || !Number.isSafeInteger(id) || id < 1) return null;
    return { kind: "media", id, type: route === "anime" ? "ANIME" : "MANGA" };
  }

  if (route !== "user" || !segments[1]) return null;
  const username = decodeUserSegment(segments[1]);
  if (!username || username.length > 64 || /[/?#]/.test(username)) return null;
  const subroute = (segments[2] ?? "").toLowerCase();
  if (IGNORED_USER_ROUTES.has(subroute)) return null;
  const section: AniListProfileSection =
    subroute === "stats" || subroute === "statistics" ? "stats"
      : subroute === "favorites" ? "favorites"
      : subroute === "activity" ? "activity"
      : subroute === "" ? "overview"
      : "overview";
  return { kind: "user", username, section };
}

function decodeUserSegment(value: string): string | null {
  try {
    return decodeURIComponent(value).trim();
  } catch {
    return null;
  }
}

function firstAniListUrl(content: string): URL | null {
  const matches = content.match(/https?:\/\/[^\s<>]+/gi) ?? [];
  for (const raw of matches) {
    const candidate = raw.replace(/[),.!?\]}]+$/g, "");
    try {
      const url = new URL(candidate);
      if (url.hostname.toLowerCase() === "anilist.co" || url.hostname.toLowerCase() === "www.anilist.co") return url;
    } catch {
      // Continue to the next URL in the message.
    }
  }
  return null;
}

function buildActivitySection(user: AniListUserProfile, activities: AniListPublicActivity[]): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(EMBED_COLOURS.info)
    .setTitle("🗨️ " + user.name + " · Public Activity")
    .setURL(user.url)
    .setDescription("Recent public text and message activity returned by AniList. Personal list/progress activities are not displayed.")
    .setFooter({ text: "AniList · Public profile activity" });
  if (user.avatar) embed.setThumbnail(user.avatar);
  for (const activity of activities.slice(0, 8)) {
    const body = activity.text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 750);
    const heading = activity.kind === "MESSAGE" && activity.recipientName
      ? "To " + activity.recipientName
      : activity.kind === "MESSAGE" ? "Message" : "Post";
    embed.addFields({
      name: heading + " · " + new Date(activity.createdAt * 1000).toLocaleDateString("en-GB"),
      value: (body || "*No text*") + "\n[Open on AniList](" + activity.url + ")",
      inline: false,
    });
  }
  if (!activities.length) embed.setDescription("No recent public text or message activity was returned by AniList.");
  return embed;
}

function detailEmbeds(media: AniListMedia): EmbedBuilder[] {
  const result: EmbedBuilder[] = [buildMediaEmbed(media)];
  if (media.relations.length) result.push(...buildRelationsEmbeds(media).slice(0, 2));
  if (media.characters.length) result.push(...buildCharactersEmbeds(media).slice(0, 1));
  if (media.staffCredits.length) result.push(...buildStaffEmbeds(media).slice(0, 1));
  if (media.stats.statusDistribution.length || media.stats.scoreDistribution.length) result.push(buildStatsEmbed(media));
  if (media.tags.length) result.push(buildTagsEmbed(media));
  if (media.recommendations.length) result.push(buildRecommendationsEmbed(media));
  return result.slice(0, 10);
}

function profileEmbed(user: AniListUserProfile, section: AniListProfileSection): EmbedBuilder {
  switch (section) {
    case "stats": return buildUserStatsEmbed(user);
    case "favorites": return buildUserFavoritesEmbed(user);
    default: return buildUserProfileEmbed(user);
  }
}

/** Adds provider-backed AniList embeds without scraping pages or deleting the user's message. */
export async function handleAniListLinkMessage(message: Message, client: AniListClient): Promise<boolean> {
  if (!message.guildId || message.author.bot) return false;
  const url = firstAniListUrl(message.content);
  if (!url) return false;
  const target = parseAniListUrl(url);
  if (!target) return false;

  if (target.kind === "media") {
    const media = await client.getMediaById(target.id, target.type);
    if (!media) {
      await message.reply({
        content: "AniList did not return a public, supported media record for that link.",
        allowedMentions: { parse: [] },
      });
      return true;
    }
    await message.reply({ embeds: detailEmbeds(media), allowedMentions: { parse: [] } });
    return true;
  }

  const user = await client.getUser(target.username);
  if (!user) {
    await message.reply({
      content: "AniList did not return a public profile for that username.",
      allowedMentions: { parse: [] },
    });
    return true;
  }
  const embed = target.section === "activity"
    ? buildActivitySection(user, await client.getRecentActivities(target.username))
    : profileEmbed(user, target.section);
  await message.reply({ embeds: [embed], allowedMentions: { parse: [] } });
  return true;
}

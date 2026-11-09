import { EmbedBuilder, type Message } from "discord.js";
import {
  AniListClient,
  type AniListEntityKind,
  type AniListMedia,
  type AniListPublicActivity,
  type AniListPublicEntity,
  type AniListReviewRecord,
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
  | { kind: "entity"; id: number; entityKind: AniListEntityKind }
  | { kind: "review"; id: number }
  | { kind: "activity"; id: number }
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

  if (["character","staff","studio","review","activity"].includes(route)) {
    const id = Number(segments[1]);
    if (!/^\d+$/.test(segments[1] ?? "") || !Number.isSafeInteger(id) || id < 1) return null;
    if (route === "character" || route === "staff" || route === "studio") {
      return { kind:"entity", id, entityKind:route.toUpperCase() as AniListEntityKind };
    }
    return { kind:route,id } as AniListLinkTarget;
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

function entityEmbed(entity:AniListPublicEntity):EmbedBuilder {
  const embed=new EmbedBuilder()
    .setColor(entity.kind==="CHARACTER"?EMBED_COLOURS.primary:entity.kind==="STAFF"?EMBED_COLOURS.secondary:EMBED_COLOURS.info)
    .setTitle(entity.name.slice(0,256))
    .setURL(entity.url)
    .setDescription((entity.description?.replace(/<[^>]*>/g," ").replace(/\s+/g," ").trim().slice(0,1_000))||"No description supplied by AniList.")
    .setFooter({text:"AniList · "+entity.kind.toLowerCase()+" metadata"});
  if(entity.image)embed.setThumbnail(entity.image);
  if(entity.roles.length)embed.addFields({name:entity.kind==="STAFF"?"Occupations":"Details",value:entity.roles.join(", ").slice(0,900),inline:true});
  if(entity.yearsActive.length)embed.addFields({name:"Years active",value:entity.yearsActive.join(", "),inline:true});
  if(entity.works.length)embed.addFields({
    name:"Known works",
    value:entity.works.slice(0,10).map(work=>{
      const label=work.title.slice(0,120);
      return "["+label+"]("+work.url+") · "+work.type+(work.role?" · "+work.role:"");
    }).join("\n").slice(0,1_000),
    inline:false,
  });
  return embed;
}

function reviewEmbed(review:AniListReviewRecord):EmbedBuilder {
  const body=(review.body??review.summary??"No review text was supplied by AniList.")
    .replace(/<br\s*\/?\s*>/gi,"\n")
    .replace(/<[^>]*>/g," ")
    .replace(/\s+/g," ")
    .trim()
    .slice(0,3_000);
  const embed=new EmbedBuilder()
    .setColor(EMBED_COLOURS.warning)
    .setTitle("AniList Review · "+review.mediaTitle.slice(0,190))
    .setURL(review.url)
    .setDescription(body||"No review text was supplied by AniList.")
    .addFields(
      {name:"Media",value:"["+review.mediaTitle.slice(0,150)+"]("+review.mediaUrl+")",inline:true},
      {name:"Reviewer",value:"["+review.userName.slice(0,100)+"]("+review.userUrl+")",inline:true},
      {name:"Score",value:review.score===null?"Not scored":String(review.score),inline:true},
      {name:"Rating",value:review.rating===null?"Unavailable":String(review.rating),inline:true},
      {name:"Rating count",value:review.ratingAmount===null?"Unavailable":String(review.ratingAmount),inline:true},
    )
    .setFooter({text:"AniList · Review metadata"});
  if(review.createdAt>0)embed.setTimestamp(new Date(review.createdAt*1000));
  return embed;
}

function linkedActivityEmbed(activity:AniListPublicActivity):EmbedBuilder {
  const body=activity.text.replace(/<br\s*\/?\s*>/gi,"\n").replace(/<[^>]*>/g," ").replace(/\s+/g," ").trim().slice(0,2_500);
  const title=activity.kind==="MESSAGE"&&activity.recipientName
    ?"Message to "+activity.recipientName
    :activity.kind==="MESSAGE"?"AniList Message":"AniList Activity";
  const embed=new EmbedBuilder()
    .setColor(EMBED_COLOURS.info)
    .setTitle(title.slice(0,256))
    .setURL(activity.url)
    .setDescription(body||"No public text was supplied by AniList.")
    .addFields({name:"Author",value:activity.userName.slice(0,150),inline:true})
    .setFooter({text:"AniList · Public activity"});
  embed.setTimestamp(new Date(activity.createdAt*1000));
  return embed;
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

  if (target.kind === "entity") {
    const entity=await client.getPublicEntity(target.id,target.entityKind);
    if(!entity){
      await message.reply({content:"AniList did not return a public record for that "+target.entityKind.toLowerCase()+".",allowedMentions:{parse:[]}});
      return true;
    }
    await message.reply({embeds:[entityEmbed(entity)],allowedMentions:{parse:[]}});
    return true;
  }

  if (target.kind === "review") {
    const review=await client.getReviewById(target.id);
    if(!review){
      await message.reply({content:"AniList did not return a public review for that link.",allowedMentions:{parse:[]}});
      return true;
    }
    await message.reply({embeds:[reviewEmbed(review)],allowedMentions:{parse:[]}});
    return true;
  }

  if (target.kind === "activity") {
    const activity=await client.getActivityById(target.id);
    if(!activity){
      await message.reply({content:"AniList did not return a public text or message activity for that link.",allowedMentions:{parse:[]}});
      return true;
    }
    await message.reply({embeds:[linkedActivityEmbed(activity)],allowedMentions:{parse:[]}});
    return true;
  }

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

import { createHash } from "node:crypto";
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
  type Client,
  type Guild,
  type NewsChannel,
  type TextChannel,
} from "discord.js";
import { emoji } from "../emoji.js";
import { logger } from "../runtime/logger.js";
import { AniListClient, type AniListEntityKind, type AniListMedia, type AniListMediaType, type AniListPublicEntity, type AniListRecentlyFinishedMedia } from "../integration/anilist.js";
import { TmdbClient } from "../integration/tmdb.js";
import { IgdbClient } from "../integration/igdb.js";
import { upcomingProviderReleases } from "../community/community-sessions.js";
import { getGuildMediaRegion } from "./media-region.js";
import type { BotConfig } from "../runtime/config.js";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { isGuildSetupComplete } from "../runtime/guild-retention.js";
import { isFeatureEnabled } from "../runtime/settings.js";
import { resolveDeliveryRetry } from "../community/delivery-retries.js";

export type MediaNotificationKind = "ANIME" | "MANGA";
export interface MediaNotificationSettings {
  guild_id: string;
  channel_id: string | null;
  enabled: boolean;
  include_anime: boolean;
  include_manga: boolean;
  include_movies: boolean;
  include_tv: boolean;
  include_games: boolean;
  last_run_at: Date | string | null;
}
type NotificationChannel = TextChannel | NewsChannel;

function withDefaults(row: MediaNotificationSettings | null, guildId: string): MediaNotificationSettings {
  return row ?? { guild_id: guildId, channel_id: null, enabled: false, include_anime: true, include_manga: true, include_movies: false, include_tv: false, include_games: false, last_run_at: null };
}

export async function getMediaNotificationSettings(guildId: string): Promise<MediaNotificationSettings> {
  const row = await queryOne<MediaNotificationSettings>(
    "SELECT guild_id::text, channel_id::text, enabled, include_anime, include_manga, include_movies, include_tv, include_games, last_run_at FROM media_notification_settings WHERE guild_id = $1",
    [guildId],
  );
  return withDefaults(row, guildId);
}

export async function setMediaNotificationSettings(
  guildId: string,
  patch: Partial<Pick<MediaNotificationSettings, "channel_id" | "enabled" | "include_anime" | "include_manga" | "include_movies" | "include_tv" | "include_games">>,
  actorId: string,
): Promise<MediaNotificationSettings> {
  const current = await getMediaNotificationSettings(guildId);
  const next = { ...current, ...patch };
  if (next.enabled && !next.channel_id) throw new Error("Choose a notification channel before enabling media notifications.");
  if (next.enabled && !next.include_anime && !next.include_manga && !next.include_movies && !next.include_tv && !next.include_games) {
    throw new Error("Enable at least one media category before turning on notifications.");
  }
  await query(
    `INSERT INTO media_notification_settings
       (guild_id, channel_id, enabled, include_anime, include_manga, include_movies, include_tv, include_games, updated_by, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       channel_id=EXCLUDED.channel_id, enabled=EXCLUDED.enabled,
       include_anime=EXCLUDED.include_anime, include_manga=EXCLUDED.include_manga,
       include_movies=EXCLUDED.include_movies, include_tv=EXCLUDED.include_tv, include_games=EXCLUDED.include_games,
       updated_by=EXCLUDED.updated_by, updated_at=NOW(), last_run_at=NULL`,
    [guildId, next.channel_id, next.enabled, next.include_anime, next.include_manga, next.include_movies, next.include_tv, next.include_games, actorId],
  );
  return { ...next, guild_id: guildId };
}

export function filterMediaNotificationCandidates(
  items: AniListRecentlyFinishedMedia[],
  kind: MediaNotificationKind,
): AniListRecentlyFinishedMedia[] {
  return items.filter(item => kind === "ANIME"
    ? item.type === "ANIME" && item.format !== "OVA" && item.episodes !== null && item.episodes >= 8
    : item.type === "MANGA" && item.format !== "ONE_SHOT" && item.chapters !== null && item.chapters >= 40);
}

function buildEmbed(item: AniListRecentlyFinishedMedia): EmbedBuilder {
  const embed = new EmbedBuilder()
    .setColor(item.status === "FINISHED" ? 0x57f287 : 0xed4245)
    .setTitle((item.status === "FINISHED" ? emoji.check + " " : emoji.error + " ") + item.title.slice(0, 250))
    .setURL(item.url)
    .setDescription((item.description ?? "No description supplied by AniList.")
      .replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 900))
    .addFields(
      { name: "Status", value: item.status === "FINISHED" ? "Finished" : "Cancelled", inline: true },
      { name: item.type === "ANIME" ? "Episodes" : "Chapters", value: String(item.episodes ?? item.chapters ?? "Unavailable"), inline: true },
      { name: "Format", value: item.format?.replaceAll("_", " ") ?? "Unavailable", inline: true },
      { name: "Average score", value: item.averageScore === null ? "Not rated" : item.averageScore + "/100", inline: true },
      { name: "End date", value: item.endDate ? [item.endDate.day, item.endDate.month, item.endDate.year].join("/") : "Unavailable", inline: true },
      { name: "Genres", value: item.genres.slice(0, 6).join(", ") || "Unavailable", inline: false },
    )
    .setFooter({ text: "AniList · Recently finished media" });
  if (item.cover) embed.setThumbnail(item.cover);
  return embed;
}

async function getNotificationChannel(guild: Guild, channelId: string): Promise<NotificationChannel | null> {
  const channel = await guild.channels.fetch(channelId).catch(() => null);
  if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) return null;
  const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
  if (!botMember) return null;
  const permissions = channel.permissionsFor(botMember);
  if (!permissions?.has(PermissionFlagsBits.ViewChannel)
    || !permissions.has(PermissionFlagsBits.SendMessages)
    || !permissions.has(PermissionFlagsBits.EmbedLinks)) return null;
  return channel as NotificationChannel;
}

function previousUtcDay(now: Date): { after: Date; before: Date } {
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const after = new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000);
  return { after, before: today };
}

function ranWithinDay(lastRun: Date | string | null, now: number): boolean {
  if (!lastRun) return false;
  const value = lastRun instanceof Date ? lastRun.getTime() : new Date(lastRun).getTime();
  return Number.isFinite(value) && now - value < 24 * 60 * 60 * 1000;
}

async function wasDelivered(guildId: string, kind: MediaNotificationKind, mediaId: number): Promise<boolean> {
  return Boolean(await queryOne<{ media_id: string }>(
    "SELECT media_id::text FROM media_notification_deliveries WHERE guild_id=$1 AND media_type=$2 AND media_id=$3",
    [guildId, kind, mediaId],
  ));
}

async function markDelivered(guildId: string, kind: MediaNotificationKind, mediaId: number): Promise<void> {
  await query(
    "INSERT INTO media_notification_deliveries (guild_id,media_type,media_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
    [guildId, kind, mediaId],
  );
}

async function deliverGuild(
  guild: Guild,
  settings: MediaNotificationSettings,
  anime: AniListRecentlyFinishedMedia[],
  manga: AniListRecentlyFinishedMedia[],
): Promise<void> {
  if (!settings.enabled || !settings.channel_id || !await isFeatureEnabled(guild.id, "discover")) return;
  const channel = await getNotificationChannel(guild, settings.channel_id);
  if (!channel) {
    logger.warn("Media notifications paused because the configured channel is unavailable or missing permissions", {
      guildId: guild.id, channelId: settings.channel_id,
    });
    return;
  }
  const items = [
    ...(settings.include_anime ? anime.map(item => ({ kind: "ANIME" as const, item })) : []),
    ...(settings.include_manga ? manga.map(item => ({ kind: "MANGA" as const, item })) : []),
  ];
  let failed = false;
  for (const { kind, item } of items) {
    if (await wasDelivered(guild.id, kind, item.id)) continue;
    try {
      await channel.send({
        embeds: [buildEmbed(item)],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("View on AniList").setStyle(ButtonStyle.Link).setURL(item.url),
        )],
        allowedMentions: { parse: [] },
      });
      await markDelivered(guild.id, kind, item.id);
    } catch (error) {
      failed = true;
      logger.warn("Could not deliver a recent media completion notification", {
        guildId: guild.id, mediaId: item.id, kind,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 1200));
  }
  if (!failed) await query("UPDATE media_notification_settings SET last_run_at=NOW() WHERE guild_id=$1", [guild.id]);
}

export interface GuildMediaFollow {
  guild_id: string;
  anilist_id: number;
  title: string;
  site_url: string;
  cover_image: string | null;
  next_episode: number | null;
  next_airing_at: Date | string | null;
  last_notified_episode: number;
  followed_by: string;
}

function aniListMediaTitle(media: Awaited<ReturnType<AniListClient["getMediaById"]>>): string {
  return media?.title.english ?? media?.title.romaji ?? media?.title.native ?? "Untitled anime";
}

export async function getGuildMediaFollows(guildId: string): Promise<GuildMediaFollow[]> {
  return query<GuildMediaFollow>(
    "SELECT guild_id::text, anilist_id, title, site_url, cover_image, next_episode, next_airing_at, " +
    "last_notified_episode, followed_by::text FROM guild_media_follows " +
    "WHERE guild_id = $1 ORDER BY title ASC LIMIT 25",
    [guildId],
  );
}

export async function followAniListAnime(
  guildId: string,
  userId: string,
  mediaId: number,
  aniList: AniListClient,
  now = new Date(),
): Promise<GuildMediaFollow> {
  if (!Number.isSafeInteger(mediaId) || mediaId < 1) throw new Error("Provide a valid positive AniList anime ID.");
  const media = await aniList.getMediaById(mediaId, "ANIME");
  if (!media || media.type !== "ANIME") throw new Error("AniList did not return a supported anime for that ID.");
  if (!media.siteUrl.startsWith("https://anilist.co/anime/")) throw new Error("The AniList anime URL was not valid.");
  const next = media.nextAiringEpisode ?? null;
  const lastNotified = next
    ? next.airingAt * 1000 <= now.getTime() ? next.episode : Math.max(0, next.episode - 1)
    : 0;
  return transaction(async (client) => {
    await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [guildId]);
    const follows = await client.query<{ count: string }>(
      "SELECT COUNT(*)::text AS count FROM guild_media_follows WHERE guild_id = $1",
      [guildId],
    );
    if (Number(follows.rows[0]?.count ?? 0) >= 25) {
      throw new Error("This server has reached the 25-title follow limit.");
    }
    const row = await client.query<GuildMediaFollow>(
      "INSERT INTO guild_media_follows " +
      "(guild_id, anilist_id, title, site_url, cover_image, next_episode, next_airing_at, last_notified_episode, followed_by) " +
      "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) " +
      "ON CONFLICT (guild_id, anilist_id) DO NOTHING " +
      "RETURNING guild_id::text, anilist_id, title, site_url, cover_image, next_episode, next_airing_at, last_notified_episode, followed_by::text",
      [guildId, media.id, aniListMediaTitle(media), media.siteUrl, media.coverImage,
        next?.episode ?? null, next ? new Date(next.airingAt * 1000) : null, lastNotified, userId],
    );
    if (!row.rows[0]) throw new Error("This anime is already followed by this server.");
    return row.rows[0];
  });
}

export async function unfollowAniListAnime(guildId: string, mediaId: number): Promise<boolean> {
  const row = await queryOne<{ anilist_id: number }>(
    "DELETE FROM guild_media_follows WHERE guild_id = $1 AND anilist_id = $2 RETURNING anilist_id",
    [guildId, mediaId],
  );
  return Boolean(row);
}

export function resolveDueFollowEpisode(
  follow: Pick<GuildMediaFollow, "next_episode" | "next_airing_at" | "last_notified_episode">,
  latest: { episode: number; airingAt: number } | null,
  now = new Date(),
): number | null {
  const lastNotified = Number(follow.last_notified_episode);
  const storedEpisode = follow.next_episode === null ? null : Number(follow.next_episode);
  const storedAt = follow.next_airing_at
    ? new Date(follow.next_airing_at).getTime()
    : null;
  if (storedEpisode !== null && storedEpisode > lastNotified
    && storedAt !== null && Number.isFinite(storedAt) && storedAt <= now.getTime() + 60_000) {
    return storedEpisode;
  }
  if (latest && latest.episode > lastNotified && latest.airingAt * 1000 <= now.getTime() + 60_000) {
    return latest.episode;
  }
  return null;
}

async function deliverDueAnimeFollows(client: Client, aniList: AniListClient, now: Date): Promise<void> {
  const follows = await query<GuildMediaFollow>(
    "SELECT f.guild_id::text, f.anilist_id, f.title, f.site_url, f.cover_image, " +
    "f.next_episode, f.next_airing_at, f.last_notified_episode, f.followed_by::text " +
    "FROM guild_media_follows f JOIN media_notification_settings s ON s.guild_id = f.guild_id " +
    "WHERE s.enabled = TRUE AND s.include_anime = TRUE AND s.channel_id IS NOT NULL " +
    "ORDER BY f.updated_at ASC, f.guild_id, f.anilist_id LIMIT 100",
  );
  for (const follow of follows) {
    if (!await isGuildSetupComplete(follow.guild_id) || !await isFeatureEnabled(follow.guild_id, "discover")) continue;
    if (!client.guilds.cache.has(follow.guild_id)) continue;
    try {
      const media = await aniList.getMediaById(Number(follow.anilist_id), "ANIME");
      if (!media || media.type !== "ANIME" || !media.siteUrl.startsWith("https://anilist.co/anime/")) continue;
      const latest = media.nextAiringEpisode ?? null;
      const dueEpisode = resolveDueFollowEpisode(follow, latest, now);
      let nextEpisode = latest?.episode ?? follow.next_episode;
      let nextAiringAt = latest ? new Date(latest.airingAt * 1000) : follow.next_airing_at;
      if (media.status === "FINISHED" || media.status === "CANCELLED") {
        nextEpisode = null;
        nextAiringAt = null;
      }
      await transaction(async transactionClient => {
        if (dueEpisode !== null) {
          const scheduledFor = follow.next_airing_at
            ? new Date(follow.next_airing_at)
            : latest ? new Date(latest.airingAt * 1000) : now;
          await transactionClient.query(
            `INSERT INTO guild_media_follow_deliveries
             (guild_id, anilist_id, episode_number, scheduled_for, title, site_url, cover_image)
             VALUES ($1,$2,$3,$4,$5,$6,$7)
             ON CONFLICT (guild_id, anilist_id, episode_number) DO NOTHING`,
            [follow.guild_id, follow.anilist_id, dueEpisode, scheduledFor, aniListMediaTitle(media), media.siteUrl, media.coverImage],
          );
        }
        await transactionClient.query(
          "UPDATE guild_media_follows SET title = $1, site_url = $2, cover_image = $3, " +
          "next_episode = $4, next_airing_at = $5, updated_at = NOW() " +
          "WHERE guild_id = $6 AND anilist_id = $7",
          [aniListMediaTitle(media), media.siteUrl, media.coverImage, nextEpisode, nextAiringAt, follow.guild_id, follow.anilist_id],
        );
      });
    } catch (error) {
      logger.warn("AniList title follow could not be checked or queued", {
        guildId: follow.guild_id, mediaId: follow.anilist_id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      await query("UPDATE guild_media_follows SET updated_at = NOW() WHERE guild_id = $1 AND anilist_id = $2",
        [follow.guild_id, follow.anilist_id]).catch(() => undefined);
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 300));
  }
}

interface DueAnimeFollowDelivery {
  id: string;
  guild_id: string;
  anilist_id: number;
  episode_number: number;
  title: string;
  site_url: string;
  cover_image: string | null;
  channel_id: string;
  claim_token: string;
}

async function dueAnimeFollowDeliveries(): Promise<DueAnimeFollowDelivery[]> {
  return query<DueAnimeFollowDelivery>(
    `WITH due AS (
       SELECT d.id FROM guild_media_follow_deliveries d
       WHERE ((d.status = 'pending' AND d.next_attempt_at <= NOW())
          OR (d.status = 'processing' AND d.claim_until <= NOW()))
         AND NOT EXISTS (SELECT 1 FROM guild_feature_settings feature
           WHERE feature.guild_id = d.guild_id AND feature.feature_name = 'discover' AND feature.enabled = FALSE)
         AND EXISTS (
           SELECT 1 FROM guild_media_follows f
           JOIN media_notification_settings s ON s.guild_id = f.guild_id
           WHERE f.guild_id = d.guild_id AND f.anilist_id = d.anilist_id
             AND s.enabled = TRUE AND s.include_anime = TRUE AND s.channel_id IS NOT NULL
         )
       ORDER BY d.created_at ASC LIMIT 100 FOR UPDATE SKIP LOCKED
     ),
     claimed AS (
       UPDATE guild_media_follow_deliveries d
       SET status = 'processing', claim_until = NOW() + INTERVAL '15 minutes',
           claim_token = md5(random()::text || clock_timestamp()::text || d.id::text)
       FROM due WHERE d.id = due.id
       RETURNING d.id, d.guild_id, d.anilist_id, d.episode_number, d.title, d.site_url, d.cover_image, d.claim_token
     )
     SELECT c.id::text, c.guild_id::text, c.anilist_id, c.episode_number, c.title, c.site_url, c.cover_image,
            s.channel_id::text, c.claim_token
     FROM claimed c
     JOIN media_notification_settings s ON s.guild_id = c.guild_id AND s.enabled = TRUE AND s.include_anime = TRUE
     JOIN guild_media_follows f ON f.guild_id = c.guild_id AND f.anilist_id = c.anilist_id
     ORDER BY c.id ASC`,
  );
}

async function releaseAnimeFollowDeliveryClaim(deliveryId: string, claimToken: string): Promise<void> {
  await query(
    "UPDATE guild_media_follow_deliveries SET status = 'pending', claim_until = NULL, claim_token = NULL " +
    "WHERE id = $1 AND status = 'processing' AND claim_token = $2",
    [deliveryId, claimToken],
  );
}

async function markAnimeFollowDelivery(
  deliveryId: string, claimToken: string, status: "sent" | "pending", messageId?: string, error?: string,
): Promise<"sent" | "pending" | "failed" | null> {
  return transaction(async client => {
    const current = await client.query<{ guild_id: string; anilist_id: number; episode_number: number; attempts: number }>(
      "SELECT guild_id::text, anilist_id, episode_number, attempts FROM guild_media_follow_deliveries " +
      "WHERE id = $1 AND status = 'processing' AND claim_token = $2 FOR UPDATE",
      [deliveryId, claimToken],
    );
    const row = current.rows[0];
    if (!row) return null;
    const retry = status === "sent" ? null : resolveDeliveryRetry(Number(row.attempts), 1);
    const nextStatus = status === "sent" ? "sent" : retry!.status;
    await client.query(
      `UPDATE guild_media_follow_deliveries
       SET status = $1, message_id = COALESCE($2, message_id), attempts = attempts + 1,
           last_error = $3, claim_until = NULL, claim_token = NULL,
           next_attempt_at = CASE WHEN $1 = 'pending' THEN NOW() + $4 * INTERVAL '1 minute' ELSE next_attempt_at END
       WHERE id = $5 AND status = 'processing' AND claim_token = $6`,
      [nextStatus, messageId ?? null, error ? error.slice(0, 500) : null, retry?.delayMinutes ?? 0, deliveryId, claimToken],
    );
    if (nextStatus === "sent") {
      await client.query(
        "UPDATE guild_media_follows SET last_notified_episode = GREATEST(last_notified_episode, $1), updated_at = NOW() " +
        "WHERE guild_id = $2 AND anilist_id = $3",
        [row.episode_number, row.guild_id, row.anilist_id],
      );
    }
    return nextStatus;
  });
}

async function deliverQueuedAnimeFollowAlerts(client: Client, now: Date): Promise<void> {
  const deliveries = await dueAnimeFollowDeliveries();
  for (const delivery of deliveries) {
    if (!await isGuildSetupComplete(delivery.guild_id)) continue;
    if (!await isFeatureEnabled(delivery.guild_id, "discover")) {
      await releaseAnimeFollowDeliveryClaim(delivery.id, delivery.claim_token);
      continue;
    }
    const guild = client.guilds.cache.get(delivery.guild_id);
    const channel = guild ? await getNotificationChannel(guild, delivery.channel_id) : null;
    if (!channel) {
      await markAnimeFollowDelivery(delivery.id, delivery.claim_token, "pending", undefined, "Configured media notification channel is unavailable.").catch(() => undefined);
      continue;
    }
    try {
      const embed = new EmbedBuilder()
        .setColor(0x5865f2)
        .setTitle(delivery.title.slice(0, 240))
        .setURL(delivery.site_url)
        .setDescription("Episode " + delivery.episode_number + " has reached its AniList scheduled airing time.")
        .addFields(
          { name: "Episode", value: String(delivery.episode_number), inline: true },
          { name: "Schedule", value: "Provider-dated airing", inline: true },
        )
        .setFooter({ text: "AniList · Server title follow" })
        .setTimestamp(now);
      if (delivery.cover_image) embed.setThumbnail(delivery.cover_image);
      const message = await channel.send({
        embeds: [embed],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("View on AniList").setStyle(ButtonStyle.Link).setURL(delivery.site_url),
        )],
        allowedMentions: { parse: [] },
      });
      await markAnimeFollowDelivery(delivery.id, delivery.claim_token, "sent", message.id);
    } catch (error) {
      await markAnimeFollowDelivery(delivery.id, delivery.claim_token, "pending", undefined, error instanceof Error ? error.message : "Unknown delivery error").catch(() => undefined);
      logger.warn("AniList episode alert delivery failed", {
        guildId: delivery.guild_id, mediaId: delivery.anilist_id, episode: delivery.episode_number,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 300));
  }
}


export type MediaFollowType = "title" | "creator" | "franchise" | "category";
export type AniListFollowTargetKind = "ANIME" | "MANGA" | "STAFF" | "STUDIO";

export interface MediaFollowSubscription {
  id: string;
  guild_id: string;
  follow_type: MediaFollowType;
  target_kind: AniListFollowTargetKind;
  target_id: string;
  media_type: AniListMediaType | null;
  title: string;
  site_url: string;
  cover_image: string | null;
  snapshot: unknown;
  followed_by: string;
  last_checked_at: Date | string | null;
}

const FOLLOW_GENRES = [
  "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror",
  "Mystery", "Psychological", "Romance", "Sci-Fi", "Thriller",
];

function entityTitle(media: AniListMedia): string {
  return media.title.english ?? media.title.romaji ?? media.title.native ?? "Untitled media";
}

export function buildMediaFollowSnapshot(
  followType: MediaFollowType,
  data: AniListMedia | AniListPublicEntity | AniListMedia[],
): unknown {
  if (followType === "creator") {
    const entity = data as AniListPublicEntity;
    return {
      name: entity.name,
      roles: [...entity.roles].sort(),
      yearsActive: [...entity.yearsActive].sort((a, b) => a - b),
      works: entity.works.map(work => ({ id: work.id, type: work.type, role: work.role })).sort((a, b) => a.id - b.id),
    };
  }
  if (followType === "category") {
    return (data as AniListMedia[]).map(media => ({
      id: media.id, type: media.type, title: entityTitle(media),
      status: media.status, format: media.format, startDate: media.startDate,
    })).sort((a, b) => a.id - b.id);
  }
  const media = data as AniListMedia;
  if (followType === "franchise") {
    return {
      title: entityTitle(media),
      relations: media.relations.map(relation => ({
        id: relation.id, category: relation.category, relation: relation.relation,
        title: relation.title, url: relation.url,
      })).sort((a, b) => a.id - b.id),
    };
  }
  return {
    title: entityTitle(media), status: media.status, format: media.format,
    episodes: media.episodes, chapters: media.chapters, volumes: media.volumes,
    startDate: media.startDate,
    genres: [...media.genres].sort(), nextAiringEpisode: media.nextAiringEpisode ?? null,
  };
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return "{" + Object.keys(object).sort().map(key => JSON.stringify(key) + ":" + canonicalJson(object[key])).join(",") + "}";
  }
  return JSON.stringify(value) ?? "null";
}

export function mediaFollowSnapshotKey(snapshot: unknown): string {
  return createHash("sha256").update(canonicalJson(snapshot)).digest("hex");
}

export async function getGuildMediaFollowSubscriptions(guildId: string): Promise<MediaFollowSubscription[]> {
  return query<MediaFollowSubscription>(
    "SELECT id::text, guild_id::text, follow_type, target_kind, target_id, media_type, title, site_url, " +
    "cover_image, snapshot, followed_by::text, last_checked_at FROM media_follow_subscriptions " +
    "WHERE guild_id = $1 ORDER BY title ASC LIMIT 25",
    [guildId],
  );
}

export async function followAniListSubscription(
  guildId: string, userId: string, rawFollowType: string, rawTargetKind: string,
  rawTarget: string, aniList: AniListClient,
): Promise<MediaFollowSubscription> {
  const followType = rawFollowType.trim().toLowerCase() as MediaFollowType;
  const targetKind = rawTargetKind.trim().toUpperCase() as AniListFollowTargetKind;
  const target = rawTarget.trim();
  if (!/^\d{17,20}$/.test(guildId) || !/^\d{17,20}$/.test(userId)) {
    throw new Error("A valid Discord server and user are required.");
  }
  if (!["title", "creator", "franchise", "category"].includes(followType)) {
    throw new Error("Choose title, creator, franchise or category as the follow type.");
  }
  if (!["ANIME", "MANGA", "STAFF", "STUDIO"].includes(targetKind)) {
    throw new Error("Choose ANIME, MANGA, STAFF or STUDIO as the AniList target type.");
  }

  let mediaType: AniListMediaType | null = null;
  let targetId: string;
  let title: string;
  let siteUrl: string;
  let coverImage: string | null;
  let source: AniListMedia | AniListPublicEntity | AniListMedia[];

  if (followType === "creator") {
    if (targetKind !== "STAFF" && targetKind !== "STUDIO") throw new Error("Creator follows require a STAFF or STUDIO AniList ID.");
    if (!/^\d{1,12}$/.test(target) || Number(target) < 1 || !Number.isSafeInteger(Number(target))) {
      throw new Error("Enter a valid positive AniList creator ID.");
    }
    const entity = await aniList.getPublicEntity(Number(target), targetKind as AniListEntityKind);
    if (!entity || entity.kind !== targetKind) throw new Error("AniList did not return that creator or studio.");
    source = entity;
    targetId = String(entity.id);
    title = entity.name;
    siteUrl = entity.url;
    coverImage = entity.image;
  } else if (followType === "category") {
    if (targetKind !== "ANIME" && targetKind !== "MANGA") throw new Error("Category follows require ANIME or MANGA.");
    const genre = FOLLOW_GENRES.find(value => value.toLowerCase() === target.toLowerCase());
    if (!genre) throw new Error("Choose a supported AniList genre, such as Action, Fantasy, Mystery or Romance.");
    mediaType = targetKind;
    const matches = await aniList.searchByGenres(targetKind, [genre]);
    source = matches;
    targetId = genre;
    title = genre + " · " + targetKind.toLowerCase() + " category";
    siteUrl = "https://anilist.co/search/" + targetKind.toLowerCase();
    coverImage = matches[0]?.coverImage ?? null;
  } else {
    if (targetKind !== "ANIME" && targetKind !== "MANGA") throw new Error("Title and franchise follows require ANIME or MANGA.");
    if (!/^\d{1,12}$/.test(target) || Number(target) < 1 || !Number.isSafeInteger(Number(target))) {
      throw new Error("Enter a valid positive AniList media ID.");
    }
    const media = await aniList.getMediaById(Number(target), targetKind);
    if (!media || media.type !== targetKind || !media.siteUrl.startsWith("https://anilist.co/")) {
      throw new Error("AniList did not return a supported title for that ID.");
    }
    source = media;
    mediaType = targetKind;
    targetId = String(media.id);
    title = entityTitle(media) + (followType === "franchise" ? " · franchise" : "");
    siteUrl = media.siteUrl;
    coverImage = media.coverImage;
  }

  const snapshot = buildMediaFollowSnapshot(followType, source);
  return transaction(async client => {
    await client.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", [guildId]);
    const count = await client.query<{ count: string }>(
      "SELECT COUNT(*)::text AS count FROM media_follow_subscriptions WHERE guild_id = $1", [guildId],
    );
    if (Number(count.rows[0]?.count ?? 0) >= 25) throw new Error("This server has reached the 25-subscription follow limit.");
    const inserted = await client.query<MediaFollowSubscription>(
      "INSERT INTO media_follow_subscriptions " +
      "(guild_id,follow_type,target_kind,target_id,media_type,title,site_url,cover_image,snapshot,followed_by) " +
      "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT (guild_id,follow_type,target_kind,target_id) DO NOTHING " +
      "RETURNING id::text,guild_id::text,follow_type,target_kind,target_id,media_type,title,site_url,cover_image,snapshot,followed_by::text,last_checked_at",
      [guildId, followType, targetKind, targetId, mediaType, title, siteUrl, coverImage, snapshot, userId],
    );
    if (!inserted.rows[0]) throw new Error("That target is already followed by this server.");
    return inserted.rows[0];
  });
}

export async function removeMediaFollowSubscription(guildId: string, subscriptionId: string): Promise<boolean> {
  if (!/^\d+$/.test(subscriptionId)) return false;
  return Boolean(await queryOne<{ id: string }>(
    "DELETE FROM media_follow_subscriptions WHERE guild_id=$1 AND id=$2 RETURNING id::text",
    [guildId, subscriptionId],
  ));
}

async function latestSubscriptionSnapshot(
  follow: MediaFollowSubscription, aniList: AniListClient,
): Promise<{ snapshot: unknown; title: string; siteUrl: string; coverImage: string | null } | null> {
  if (follow.follow_type === "creator") {
    const entity = await aniList.getPublicEntity(Number(follow.target_id), follow.target_kind as AniListEntityKind);
    if (!entity) return null;
    return { snapshot: buildMediaFollowSnapshot("creator", entity), title: entity.name, siteUrl: entity.url, coverImage: entity.image };
  }
  if (follow.follow_type === "category") {
    if (!follow.media_type) return null;
    const matches = await aniList.searchByGenres(follow.media_type, [follow.target_id]);
    return {
      snapshot: buildMediaFollowSnapshot("category", matches), title: follow.title,
      siteUrl: follow.site_url, coverImage: matches[0]?.coverImage ?? follow.cover_image,
    };
  }
  if (!follow.media_type) return null;
  const media = await aniList.getMediaById(Number(follow.target_id), follow.media_type);
  if (!media || media.type !== follow.media_type || !media.siteUrl.startsWith("https://anilist.co/")) return null;
  return {
    snapshot: buildMediaFollowSnapshot(follow.follow_type, media),
    title: entityTitle(media) + (follow.follow_type === "franchise" ? " · franchise" : ""),
    siteUrl: media.siteUrl, coverImage: media.coverImage,
  };
}

async function refreshMediaFollowSubscriptions(aniList: AniListClient): Promise<void> {
  const subscriptions = await query<MediaFollowSubscription>(
    `SELECT f.id::text,f.guild_id::text,f.follow_type,f.target_kind,f.target_id,f.media_type,
            f.title,f.site_url,f.cover_image,f.snapshot,f.followed_by::text,f.last_checked_at
       FROM media_follow_subscriptions f JOIN media_notification_settings s ON s.guild_id=f.guild_id
      WHERE s.enabled=TRUE AND s.channel_id IS NOT NULL
        AND (f.media_type IS NULL OR (f.media_type='ANIME' AND s.include_anime=TRUE)
          OR (f.media_type='MANGA' AND s.include_manga=TRUE))
      ORDER BY f.last_checked_at ASC NULLS FIRST,f.id ASC LIMIT 100`,
  );
  for (const follow of subscriptions) {
    if (!await isGuildSetupComplete(follow.guild_id) || !await isFeatureEnabled(follow.guild_id, "discover")) continue;
    try {
      const latest = await latestSubscriptionSnapshot(follow, aniList);
      if (latest) {
        const eventKey = mediaFollowSnapshotKey(latest.snapshot);
        if (eventKey !== mediaFollowSnapshotKey(follow.snapshot)) {
          await query(
            `INSERT INTO media_follow_deliveries
               (guild_id,subscription_id,event_key,title,site_url,cover_image,description)
             VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (subscription_id,event_key) DO NOTHING`,
            [follow.guild_id, follow.id, eventKey, latest.title, latest.siteUrl, latest.coverImage,
              "AniList reports a verified metadata change for this followed target."],
          );
          await query(
            "UPDATE media_follow_subscriptions SET title=$1,site_url=$2,cover_image=$3,snapshot=$4,last_checked_at=NOW(),updated_at=NOW() WHERE id=$5 AND guild_id=$6",
            [latest.title, latest.siteUrl, latest.coverImage, latest.snapshot, follow.id, follow.guild_id],
          );
        } else {
          await query("UPDATE media_follow_subscriptions SET last_checked_at=NOW() WHERE id=$1 AND guild_id=$2", [follow.id, follow.guild_id]);
        }
      } else {
        await query("UPDATE media_follow_subscriptions SET last_checked_at=NOW() WHERE id=$1 AND guild_id=$2", [follow.id, follow.guild_id]);
      }
    } catch (error) {
      logger.warn("AniList follow subscription could not be refreshed", {
        guildId: follow.guild_id, subscriptionId: follow.id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      await query("UPDATE media_follow_subscriptions SET last_checked_at=NOW() WHERE id=$1 AND guild_id=$2",
        [follow.id, follow.guild_id]).catch(() => undefined);
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 300));
  }
}

interface DueMediaFollowDelivery {
  id: string; guild_id: string; subscription_id: string; title: string;
  site_url: string; cover_image: string | null; description: string;
  channel_id: string; claim_token: string;
}

async function dueMediaFollowDeliveries(): Promise<DueMediaFollowDelivery[]> {
  return query<DueMediaFollowDelivery>(
    `WITH due AS (
       SELECT d.id FROM media_follow_deliveries d
       WHERE ((d.status='pending' AND d.next_attempt_at<=NOW()) OR (d.status='processing' AND d.claim_until<=NOW()))
         AND NOT EXISTS (SELECT 1 FROM guild_feature_settings feature
           WHERE feature.guild_id = d.guild_id AND feature.feature_name = 'discover' AND feature.enabled = FALSE)
         AND EXISTS (
           SELECT 1 FROM media_follow_subscriptions f JOIN media_notification_settings s ON s.guild_id=f.guild_id
            WHERE f.id=d.subscription_id AND f.guild_id=d.guild_id AND s.enabled=TRUE AND s.channel_id IS NOT NULL
              AND (f.media_type IS NULL OR (f.media_type='ANIME' AND s.include_anime=TRUE)
                OR (f.media_type='MANGA' AND s.include_manga=TRUE))
         )
       ORDER BY d.created_at ASC LIMIT 100 FOR UPDATE SKIP LOCKED
     ), claimed AS (
       UPDATE media_follow_deliveries d SET status='processing',claim_until=NOW()+INTERVAL '10 minutes',
         claim_token=md5(random()::text || clock_timestamp()::text || d.id::text)
       FROM due WHERE d.id=due.id
       RETURNING d.id,d.guild_id,d.subscription_id,d.title,d.site_url,d.cover_image,d.description,d.claim_token
     )
     SELECT c.id::text,c.guild_id::text,c.subscription_id::text,c.title,c.site_url,c.cover_image,c.description,
       s.channel_id::text,c.claim_token FROM claimed c
       JOIN media_notification_settings s ON s.guild_id=c.guild_id AND s.enabled=TRUE AND s.channel_id IS NOT NULL
       JOIN media_follow_subscriptions f ON f.id=c.subscription_id AND f.guild_id=c.guild_id
      ORDER BY c.id ASC`,
  );
}

async function releaseMediaFollowDeliveryClaim(deliveryId: string, claimToken: string): Promise<void> {
  await query(
    "UPDATE media_follow_deliveries SET status = 'pending', claim_until = NULL, claim_token = NULL " +
    "WHERE id = $1 AND status = 'processing' AND claim_token = $2",
    [deliveryId, claimToken],
  );
}

async function markMediaFollowDelivery(
  deliveryId: string, claimToken: string, status: "sent" | "pending", messageId?: string, error?: string,
): Promise<void> {
  await transaction(async client => {
    const current = await client.query<{ attempts: number }>(
      "SELECT attempts FROM media_follow_deliveries WHERE id=$1 AND status='processing' AND claim_token=$2 FOR UPDATE",
      [deliveryId, claimToken],
    );
    const row = current.rows[0];
    if (!row) return;
    const retry = status === "sent" ? null : resolveDeliveryRetry(Number(row.attempts), 1);
    const nextStatus = status === "sent" ? "sent" : retry!.status;
    await client.query(
      `UPDATE media_follow_deliveries SET status=$1,message_id=COALESCE($2,message_id),attempts=attempts+1,
         last_error=$3,claim_until=NULL,claim_token=NULL,
         next_attempt_at=CASE WHEN $1='pending' THEN NOW()+$4*INTERVAL '1 minute' ELSE next_attempt_at END
       WHERE id=$5 AND status='processing' AND claim_token=$6`,
      [nextStatus, messageId ?? null, error?.slice(0, 500) ?? null, retry?.delayMinutes ?? 0, deliveryId, claimToken],
    );
  });
}

async function deliverQueuedMediaFollowAlerts(client: Client, now: Date): Promise<void> {
  for (const delivery of await dueMediaFollowDeliveries()) {
    if (!await isGuildSetupComplete(delivery.guild_id)) continue;
    if (!await isFeatureEnabled(delivery.guild_id, "discover")) {
      await releaseMediaFollowDeliveryClaim(delivery.id, delivery.claim_token);
      continue;
    }
    const guild = client.guilds.cache.get(delivery.guild_id);
    const channel = guild ? await getNotificationChannel(guild, delivery.channel_id) : null;
    if (!channel) {
      await markMediaFollowDelivery(delivery.id, delivery.claim_token, "pending", undefined, "Configured media notification channel is unavailable.").catch(() => undefined);
      continue;
    }
    try {
      const embed = new EmbedBuilder().setColor(0x5865f2).setTitle(delivery.title.slice(0, 240))
        .setURL(delivery.site_url).setDescription(delivery.description)
        .setFooter({ text: "AniList · Media Follow Centre" }).setTimestamp(now);
      if (delivery.cover_image) embed.setThumbnail(delivery.cover_image);
      const message = await channel.send({
        embeds: [embed],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("View on AniList").setStyle(ButtonStyle.Link).setURL(delivery.site_url),
        )],
        allowedMentions: { parse: [] },
      });
      await markMediaFollowDelivery(delivery.id, delivery.claim_token, "sent", message.id);
    } catch (error) {
      await markMediaFollowDelivery(delivery.id, delivery.claim_token, "pending", undefined, error instanceof Error ? error.message : "Unknown delivery error").catch(() => undefined);
      logger.warn("Media follow metadata alert delivery failed", {
        guildId: delivery.guild_id, subscriptionId: delivery.subscription_id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 300));
  }
}

export function mediaReleaseEventKey(release: { title: string; provider: string; url: string; when: Date }): string {
  if (!Number.isFinite(release.when.getTime())) throw new Error("The provider release date is invalid.");
  return createHash("sha256")
    .update(JSON.stringify([release.provider, release.url, release.title, release.when.toISOString()]))
    .digest("hex");
}

interface DueMediaReleaseDelivery {
  id: string; guild_id: string; category: "anime" | "movies" | "tv" | "games";
  title: string; provider: string; source_url: string; release_at: Date | string;
  channel_id: string; claim_token: string;
}

async function queueProviderReleaseAlerts(client: Client, aniList: AniListClient, config: BotConfig, now: Date): Promise<void> {
  const settings = await query<MediaNotificationSettings>(
    "SELECT guild_id::text,channel_id::text,enabled,include_anime,include_manga,include_movies,include_tv,include_games,last_run_at " +
    "FROM media_notification_settings WHERE enabled=TRUE AND channel_id IS NOT NULL " +
    "AND (include_anime=TRUE OR include_movies=TRUE OR include_tv=TRUE OR include_games=TRUE)",
  );
  const from = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const to = new Date(now.getTime() + 15 * 60 * 1000);
  const tmdb = new TmdbClient(config.tmdbBearerToken);
  const igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
  const scans = new Map<string, ReturnType<typeof upcomingProviderReleases>>();
  for (const row of settings) {
    try {
      if (!await isGuildSetupComplete(row.guild_id) || !await isFeatureEnabled(row.guild_id, "discover") || !client.guilds.cache.has(row.guild_id)) continue;
    const categories: Array<"anime" | "tv" | "movies" | "games"> = [];
    if (row.include_anime) categories.push("anime");
    if (row.include_tv) categories.push("tv");
    if (row.include_movies) categories.push("movies");
    if (row.include_games) categories.push("games");
    if (!categories.length) continue;
    const region = await getGuildMediaRegion(row.guild_id);
    const key = region + ":" + categories.slice().sort().join(",");
    let scan = scans.get(key);
    if (!scan) {
      scan = upcomingProviderReleases(aniList, tmdb, from, to, region, categories, igdb);
      scans.set(key, scan);
    }
    const result = await scan;
    if (result.unavailableProviders.length) logger.warn("Some provider release alerts were unavailable", {
      guildId: row.guild_id, providers: result.unavailableProviders,
    });
    for (const release of result.results) {
      if (release.when < from || release.when > to) continue;
      let source: URL;
      try {
        source = new URL(release.url);
        if (source.protocol !== "https:" || source.username || source.password) continue;
      } catch { continue; }
      const eventKey = mediaReleaseEventKey(release);
      await query(
        "INSERT INTO media_release_notification_deliveries (guild_id,event_key,category,title,provider,source_url,release_at) " +
        "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (guild_id,event_key) DO NOTHING",
        [row.guild_id, eventKey, release.category, release.title.slice(0, 240),
          release.provider.slice(0, 80), source.toString(), release.when],
      );
    }
    } catch (error) {
      logger.warn("Provider release scan failed for one guild", {
        guildId: row.guild_id, reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
  }
}

async function dueMediaReleaseDeliveries(): Promise<DueMediaReleaseDelivery[]> {
  return query<DueMediaReleaseDelivery>(
    `WITH due AS (
       SELECT d.id FROM media_release_notification_deliveries d
       JOIN media_notification_settings s ON s.guild_id=d.guild_id
       WHERE ((d.status='pending' AND d.next_attempt_at<=NOW()) OR (d.status='processing' AND d.claim_until<=NOW()))
         AND d.release_at<=NOW()+INTERVAL '15 minutes' AND s.enabled=TRUE AND s.channel_id IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM guild_feature_settings feature
           WHERE feature.guild_id = d.guild_id AND feature.feature_name = 'discover' AND feature.enabled = FALSE)
         AND ((d.category='anime' AND s.include_anime=TRUE) OR (d.category='movies' AND s.include_movies=TRUE)
           OR (d.category='tv' AND s.include_tv=TRUE) OR (d.category='games' AND s.include_games=TRUE))
       ORDER BY d.release_at ASC,d.id ASC LIMIT 100 FOR UPDATE OF d SKIP LOCKED
     ), claimed AS (
       UPDATE media_release_notification_deliveries d SET status='processing',claim_until=NOW()+INTERVAL '10 minutes',
         claim_token=md5(random()::text || clock_timestamp()::text || d.id::text)
       FROM due WHERE d.id=due.id
       RETURNING d.id,d.guild_id,d.category,d.title,d.provider,d.source_url,d.release_at,d.claim_token
     )
     SELECT c.id::text,c.guild_id::text,c.category,c.title,c.provider,c.source_url,c.release_at,
       s.channel_id::text,c.claim_token FROM claimed c
       JOIN media_notification_settings s ON s.guild_id=c.guild_id AND s.enabled=TRUE AND s.channel_id IS NOT NULL
      ORDER BY c.release_at ASC,c.id ASC`,
  );
}

async function releaseMediaReleaseDeliveryClaim(deliveryId: string, claimToken: string): Promise<void> {
  await query(
    "UPDATE media_release_notification_deliveries SET status = 'pending', claim_until = NULL, claim_token = NULL " +
    "WHERE id = $1 AND status = 'processing' AND claim_token = $2",
    [deliveryId, claimToken],
  );
}

async function markMediaReleaseDelivery(
  deliveryId: string, claimToken: string, status: "sent" | "pending", messageId?: string, error?: string,
): Promise<void> {
  await transaction(async client => {
    const current = await client.query<{ attempts: number }>(
      "SELECT attempts FROM media_release_notification_deliveries WHERE id=$1 AND status='processing' AND claim_token=$2 FOR UPDATE",
      [deliveryId, claimToken],
    );
    const row = current.rows[0];
    if (!row) return;
    const retry = status === "sent" ? null : resolveDeliveryRetry(Number(row.attempts), 1);
    const nextStatus = status === "sent" ? "sent" : retry!.status;
    await client.query(
      `UPDATE media_release_notification_deliveries SET status=$1,message_id=COALESCE($2,message_id),attempts=attempts+1,
         last_error=$3,claim_until=NULL,claim_token=NULL,
         next_attempt_at=CASE WHEN $1='pending' THEN NOW()+$4*INTERVAL '1 minute' ELSE next_attempt_at END
       WHERE id=$5 AND status='processing' AND claim_token=$6`,
      [nextStatus, messageId ?? null, error?.slice(0, 500) ?? null, retry?.delayMinutes ?? 0, deliveryId, claimToken],
    );
  });
}

async function deliverQueuedMediaReleaseAlerts(client: Client, now: Date): Promise<void> {
  for (const delivery of await dueMediaReleaseDeliveries()) {
    if (!await isGuildSetupComplete(delivery.guild_id)) continue;
    if (!await isFeatureEnabled(delivery.guild_id, "discover")) {
      await releaseMediaReleaseDeliveryClaim(delivery.id, delivery.claim_token);
      continue;
    }
    const guild = client.guilds.cache.get(delivery.guild_id);
    const channel = guild ? await getNotificationChannel(guild, delivery.channel_id) : null;
    if (!channel) {
      await markMediaReleaseDelivery(delivery.id, delivery.claim_token, "pending", undefined, "Configured media notification channel is unavailable.").catch(() => undefined);
      continue;
    }
    try {
      const category = delivery.category === "movies" ? "Film" : delivery.category === "tv" ? "TV episode" :
        delivery.category === "games" ? "Game release" : "Anime episode";
      const releaseAt = new Date(delivery.release_at);
      const releaseTimestamp = Number.isFinite(releaseAt.getTime()) ? Math.floor(releaseAt.getTime() / 1000) : 0;
      const embed = new EmbedBuilder().setColor(0x5865f2).setTitle(delivery.title.slice(0, 240))
        .setURL(delivery.source_url)
        .setDescription(category + " · Provider-reported release time: <t:" + releaseTimestamp + ":F> (<t:" + releaseTimestamp + ":R>)")
        .addFields({ name: "Source", value: delivery.provider, inline: true })
        .setFooter({ text: "Media Alert Centre · Verified provider schedule" }).setTimestamp(now);
      const message = await channel.send({
        embeds: [embed],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setLabel("Open source").setStyle(ButtonStyle.Link).setURL(delivery.source_url),
        )],
        allowedMentions: { parse: [] },
      });
      await markMediaReleaseDelivery(delivery.id, delivery.claim_token, "sent", message.id);
    } catch (error) {
      await markMediaReleaseDelivery(delivery.id, delivery.claim_token, "pending", undefined, error instanceof Error ? error.message : "Unknown delivery error").catch(() => undefined);
      logger.warn("Provider media release alert delivery failed", {
        guildId: delivery.guild_id, category: delivery.category,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    await new Promise(resolveDelay => setTimeout(resolveDelay, 300));
  }
}

let timer: ReturnType<typeof setInterval> | null = null;
let running = false;
let stopping = false;
let cycleFinished: Promise<void> | null = null;
let finishCycle: (() => void) | null = null;

export async function runMediaNotificationCycle(client: Client, aniList: AniListClient, now = new Date(), config?: BotConfig): Promise<void> {
  if (running || stopping) return;
  running = true;
  cycleFinished = new Promise<void>(resolve => { finishCycle = resolve; });
  try {
    try {
      const rows = await query<MediaNotificationSettings>(
        "SELECT guild_id::text, channel_id::text, enabled, include_anime, include_manga, include_movies, include_tv, include_games, last_run_at " +
        "FROM media_notification_settings WHERE enabled=TRUE AND channel_id IS NOT NULL",
      );
      const active: MediaNotificationSettings[] = [];
      for (const row of rows) {
        if (!ranWithinDay(row.last_run_at, now.getTime()) && await isGuildSetupComplete(row.guild_id)
          && await isFeatureEnabled(row.guild_id, "discover")) active.push(row);
      }
      if (active.length) {
        const { after, before } = previousUtcDay(now);
        const fetchAnime = active.some(row => row.include_anime);
        const fetchManga = active.some(row => row.include_manga);
        const anime = fetchAnime
          ? filterMediaNotificationCandidates(await aniList.recentlyFinished("ANIME", after, before), "ANIME") : [];
        const manga = fetchManga
          ? filterMediaNotificationCandidates(await aniList.recentlyFinished("MANGA", after, before), "MANGA") : [];
        for (const settings of active) {
          const guild = client.guilds.cache.get(settings.guild_id);
          if (!guild) continue;
          await deliverGuild(guild, settings, anime, manga).catch(error => logger.error("Media notification guild scan failed", {
            guildId: guild.id, reason: error instanceof Error ? error.message : "Unknown error",
          }));
        }
      }
    } catch (error) {
      logger.error("Media completion notification scan failed", { reason: error instanceof Error ? error.message : "Unknown error" });
    }
    await deliverDueAnimeFollows(client, aniList, now).catch(error => logger.error("AniList title follow scan failed", {
      reason: error instanceof Error ? error.message : "Unknown error",
    }));
    await deliverQueuedAnimeFollowAlerts(client, now).catch(error => logger.error("AniList episode alert outbox failed", {
      reason: error instanceof Error ? error.message : "Unknown error",
    }));
    await refreshMediaFollowSubscriptions(aniList).catch(error => logger.error("Media Follow Centre scan failed", {
      reason: error instanceof Error ? error.message : "Unknown error",
    }));
    await deliverQueuedMediaFollowAlerts(client, now).catch(error => logger.error("Media follow metadata outbox failed", {
      reason: error instanceof Error ? error.message : "Unknown error",
    }));
    if (config) {
      await queueProviderReleaseAlerts(client, aniList, config, now).catch(error => logger.error("Provider media release scan failed", {
        reason: error instanceof Error ? error.message : "Unknown error",
      }));
      await deliverQueuedMediaReleaseAlerts(client, now).catch(error => logger.error("Provider media release alert outbox failed", {
        reason: error instanceof Error ? error.message : "Unknown error",
      }));
    }
  } finally {
    running = false;
    finishCycle?.();
    finishCycle = null;
    cycleFinished = null;
  }
}

export function startMediaNotificationScheduler(client: Client, config: BotConfig): void {
  if (timer) return;
  stopping = false;
  const aniList = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
  void runMediaNotificationCycle(client, aniList, new Date(), config);
  timer = setInterval(() => void runMediaNotificationCycle(client, aniList, new Date(), config), 15 * 60 * 1000);
  timer.unref();
  logger.info("Daily media completion notification scanner started", { intervalMinutes: 15 });
}

export async function stopMediaNotificationScheduler(): Promise<void> {
  stopping = true;
  if (timer) clearInterval(timer);
  timer = null;
  const activeCycle = cycleFinished;
  if (activeCycle) await activeCycle;
}

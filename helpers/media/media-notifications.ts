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
import { AniListClient, type AniListRecentlyFinishedMedia } from "../integration/anilist.js";
import type { BotConfig } from "../runtime/config.js";
import { query, queryOne, transaction } from "../../database.js";
import { isGuildSetupComplete } from "../runtime/guild-retention.js";

export type MediaNotificationKind = "ANIME" | "MANGA";
export interface MediaNotificationSettings {
  guild_id: string;
  channel_id: string | null;
  enabled: boolean;
  include_anime: boolean;
  include_manga: boolean;
  last_run_at: Date | string | null;
}
type NotificationChannel = TextChannel | NewsChannel;

function withDefaults(row: MediaNotificationSettings | null, guildId: string): MediaNotificationSettings {
  return row ?? { guild_id: guildId, channel_id: null, enabled: false, include_anime: true, include_manga: true, last_run_at: null };
}

export async function getMediaNotificationSettings(guildId: string): Promise<MediaNotificationSettings> {
  const row = await queryOne<MediaNotificationSettings>(
    "SELECT guild_id::text, channel_id::text, enabled, include_anime, include_manga, last_run_at FROM media_notification_settings WHERE guild_id = $1",
    [guildId],
  );
  return withDefaults(row, guildId);
}

export async function setMediaNotificationSettings(
  guildId: string,
  patch: Partial<Pick<MediaNotificationSettings, "channel_id" | "enabled" | "include_anime" | "include_manga">>,
  actorId: string,
): Promise<MediaNotificationSettings> {
  const current = await getMediaNotificationSettings(guildId);
  const next = { ...current, ...patch };
  if (next.enabled && !next.channel_id) throw new Error("Choose a notification channel before enabling media notifications.");
  if (next.enabled && !next.include_anime && !next.include_manga) {
    throw new Error("Enable at least one media category before turning on notifications.");
  }
  await query(
    `INSERT INTO media_notification_settings
       (guild_id, channel_id, enabled, include_anime, include_manga, updated_by, updated_at)
     VALUES ($1,$2,$3,$4,$5,$6,NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       channel_id=EXCLUDED.channel_id, enabled=EXCLUDED.enabled,
       include_anime=EXCLUDED.include_anime, include_manga=EXCLUDED.include_manga,
       updated_by=EXCLUDED.updated_by, updated_at=NOW(), last_run_at=NULL`,
    [guildId, next.channel_id, next.enabled, next.include_anime, next.include_manga, actorId],
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
  if (!settings.enabled || !settings.channel_id) return;
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
  const follows = await query<GuildMediaFollow & { channel_id: string }>(
    "SELECT f.guild_id::text, f.anilist_id, f.title, f.site_url, f.cover_image, " +
    "f.next_episode, f.next_airing_at, f.last_notified_episode, f.followed_by::text, s.channel_id::text " +
    "FROM guild_media_follows f JOIN media_notification_settings s ON s.guild_id = f.guild_id " +
    "WHERE s.enabled = TRUE AND s.include_anime = TRUE AND s.channel_id IS NOT NULL " +
    "ORDER BY f.guild_id, f.title LIMIT 100",
  );
  const channelCache = new Map<string, NotificationChannel | null>();
  for (const follow of follows) {
    if (!await isGuildSetupComplete(follow.guild_id)) continue;
    const guild = client.guilds.cache.get(follow.guild_id);
    if (!guild) continue;
    const cacheKey = follow.guild_id + ":" + follow.channel_id;
    let channel = channelCache.get(cacheKey);
    if (channel === undefined) {
      channel = await getNotificationChannel(guild, follow.channel_id);
      channelCache.set(cacheKey, channel);
    }
    if (!channel) continue;
    try {
      const media = await aniList.getMediaById(Number(follow.anilist_id), "ANIME");
      if (!media || media.type !== "ANIME") continue;
      const latest = media.nextAiringEpisode ?? null;
      const dueEpisode = resolveDueFollowEpisode(follow, latest, now);
      let nextEpisode = latest?.episode ?? follow.next_episode;
      let nextAiringAt = latest ? new Date(latest.airingAt * 1000) : follow.next_airing_at;
      if (media.status === "FINISHED" || media.status === "CANCELLED") {
        nextEpisode = null;
        nextAiringAt = null;
      }
      if (dueEpisode !== null) {
        const embed = new EmbedBuilder()
          .setColor(0x5865f2)
          .setTitle(aniListMediaTitle(media).slice(0, 240))
          .setURL(media.siteUrl)
          .setDescription("Episode " + dueEpisode + " has reached its AniList scheduled airing time.")
          .addFields(
            { name: "Episode", value: String(dueEpisode), inline: true },
            { name: "Schedule", value: "Provider-dated airing", inline: true },
          )
          .setFooter({ text: "AniList · Server title follow" })
          .setTimestamp(now);
        if (media.coverImage) embed.setThumbnail(media.coverImage);
        await channel.send({
          embeds: [embed],
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setLabel("View on AniList").setStyle(ButtonStyle.Link).setURL(media.siteUrl),
          )],
          allowedMentions: { parse: [] },
        });
        await query(
          "UPDATE guild_media_follows SET title = $1, site_url = $2, cover_image = $3, " +
          "next_episode = $4, next_airing_at = $5, last_notified_episode = GREATEST(last_notified_episode, $6), " +
          "updated_at = NOW() WHERE guild_id = $7 AND anilist_id = $8",
          [aniListMediaTitle(media), media.siteUrl, media.coverImage, nextEpisode, nextAiringAt,
            dueEpisode, follow.guild_id, follow.anilist_id],
        );
      } else if (latest || nextEpisode === null) {
        await query(
          "UPDATE guild_media_follows SET title = $1, site_url = $2, cover_image = $3, " +
          "next_episode = $4, next_airing_at = $5, updated_at = NOW() " +
          "WHERE guild_id = $6 AND anilist_id = $7",
          [aniListMediaTitle(media), media.siteUrl, media.coverImage, nextEpisode, nextAiringAt,
            follow.guild_id, follow.anilist_id],
        );
      }
    } catch (error) {
      logger.warn("AniList title follow could not be checked or delivered", {
        guildId: follow.guild_id, mediaId: follow.anilist_id,
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

export async function runMediaNotificationCycle(client: Client, aniList: AniListClient, now = new Date()): Promise<void> {
  if (running || stopping) return;
  running = true;
  cycleFinished = new Promise<void>(resolve => { finishCycle = resolve; });
  try {
    try {
      const rows = await query<MediaNotificationSettings>(
        "SELECT guild_id::text, channel_id::text, enabled, include_anime, include_manga, last_run_at " +
        "FROM media_notification_settings WHERE enabled=TRUE AND channel_id IS NOT NULL",
      );
      const active: MediaNotificationSettings[] = [];
      for (const row of rows) {
        if (!ranWithinDay(row.last_run_at, now.getTime()) && await isGuildSetupComplete(row.guild_id)) active.push(row);
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
  void runMediaNotificationCycle(client, aniList);
  timer = setInterval(() => void runMediaNotificationCycle(client, aniList), 15 * 60 * 1000);
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

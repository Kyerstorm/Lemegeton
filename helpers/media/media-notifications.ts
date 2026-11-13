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
import { logger } from "../runtime/logger.js";
import { AniListClient, type AniListRecentlyFinishedMedia } from "../integration/anilist.js";
import type { BotConfig } from "../runtime/config.js";
import { query, queryOne } from "../../database.js";
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
    .setTitle((item.status === "FINISHED" ? "✅ " : "⚠️ ") + item.title.slice(0, 250))
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
    const rows = await query<MediaNotificationSettings>(
      "SELECT guild_id::text, channel_id::text, enabled, include_anime, include_manga, last_run_at FROM media_notification_settings WHERE enabled=TRUE AND channel_id IS NOT NULL",
    );
    const active: MediaNotificationSettings[] = [];
    for (const row of rows) {
      if (!ranWithinDay(row.last_run_at, now.getTime()) && await isGuildSetupComplete(row.guild_id)) active.push(row);
    }
    if (!active.length) return;
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
  } catch (error) {
    logger.error("Media notification scan failed", { reason: error instanceof Error ? error.message : "Unknown error" });
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

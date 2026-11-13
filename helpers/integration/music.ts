import {
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
  TextChannel,
  type Client,
} from "discord.js";
import type { QueryResultRow } from "pg";
import { query, transaction } from "../../database.js";
import type { BotConfig } from "../runtime/config.js";
import { logger } from "../runtime/logger.js";

export type MusicProvider = "spotify" | "youtube" | "soundcloud";

export interface MusicRelease {
  provider: MusicProvider;
  release_id: string;
  artist: string;
  title: string;
  url: string;
  release_date: string | null;
  image_url: string | null;
  description: string | null;
  kind: string;
}

export interface MusicTracker {
  id: string;
  guild_id: string;
  channel_id: string;
  artist_name: string;
  providers: MusicProvider[];
  spotify_target: string | null;
  youtube_target: string | null;
  soundcloud_target: string | null;
  mention_mode: "user" | "role" | "none";
  mention_user_id: string | null;
  mention_role_id: string | null;
  enabled: boolean;
  created_by: string;
  created_at: string;
  last_checked_at: string | null;
  seen_ids: string[];
}

export interface ResolvedMusicArtist {
  providers: MusicProvider[];
  spotify_target: string | null;
  youtube_target: string | null;
  soundcloud_target: string | null;
}

interface MusicTrackerRow extends QueryResultRow {
  id: string;
  guild_id: string;
  channel_id: string;
  artist_name: string;
  providers: string[];
  spotify_target: string | null;
  youtube_target: string | null;
  soundcloud_target: string | null;
  mention_mode: string;
  mention_user_id: string | null;
  mention_role_id: string | null;
  enabled: boolean;
  created_by: string;
  created_at: Date | string;
  last_checked_at: Date | string | null;
  seen_ids: string[] | null;
}

const MAX_TRACKERS_PER_GUILD = 25;
const MAX_SEEN_IDS = 75;
const REQUEST_TIMEOUT_MS = 15_000;
const SPOTIFY_API = "https://api.spotify.com/v1";
const SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token";
const YOUTUBE_API = "https://www.googleapis.com/youtube/v3";
const SOUNDCLOUD_API = "https://api-v2.soundcloud.com";

function timestampString(value: Date | string | null): string | null {
  if (!value) return null;
  return value instanceof Date ? value.toISOString() : value;
}

function isMusicProvider(value: string): value is MusicProvider {
  return value === "spotify" || value === "youtube" || value === "soundcloud";
}

function toTracker(row: MusicTrackerRow): MusicTracker {
  return {
    id: String(row.id),
    guild_id: String(row.guild_id),
    channel_id: String(row.channel_id),
    artist_name: row.artist_name,
    providers: Array.isArray(row.providers) ? row.providers.filter(isMusicProvider) : [],
    spotify_target: row.spotify_target,
    youtube_target: row.youtube_target,
    soundcloud_target: row.soundcloud_target,
    mention_mode: row.mention_mode === "role" || row.mention_mode === "none" ? row.mention_mode : "user",
    mention_user_id: row.mention_user_id ? String(row.mention_user_id) : null,
    mention_role_id: row.mention_role_id ? String(row.mention_role_id) : null,
    enabled: Boolean(row.enabled),
    created_by: String(row.created_by),
    created_at: timestampString(row.created_at) ?? new Date(0).toISOString(),
    last_checked_at: timestampString(row.last_checked_at),
    seen_ids: Array.isArray(row.seen_ids) ? row.seen_ids.map(String).slice(-MAX_SEEN_IDS) : [],
  };
}

const TRACKER_SELECT =
  "SELECT music_trackers.id, music_trackers.guild_id::text, music_trackers.channel_id::text, music_trackers.artist_name, music_trackers.providers, " +
  "music_trackers.spotify_target, music_trackers.youtube_target, music_trackers.soundcloud_target, music_trackers.mention_mode, " +
  "music_trackers.mention_user_id::text, music_trackers.mention_role_id::text, music_trackers.enabled, music_trackers.created_by::text, " +
  "music_trackers.created_at, music_trackers.last_checked_at, music_trackers.seen_ids FROM music_trackers ";

export function cleanMusicText(value: unknown, maximum = 1024): string {
  const text = String(value ?? "")
    .replace(/@everyone/gi, "@\u200beveryone")
    .replace(/@here/gi, "@\u200bhere")
    .replace(/[\r\n\t]+/g, " ")
    .trim()
    .replace(/([\\\x60*_{}\[\]()#+\-.!|])/g, "\\$1");
  return text.length > maximum ? text.slice(0, Math.max(0, maximum - 3)) + "..." : text;
}

export function extractSpotifyArtistId(value: string): string | null {
  const input = value.trim();
  if (/^[A-Za-z0-9]{10,30}$/.test(input)) return input;
  try {
    const url = new URL(input);
    if (!/(^|\.)spotify\.com$/i.test(url.hostname)) return null;
    const match = url.pathname.match(/^\/artist\/([A-Za-z0-9]{10,30})\/?$/i);
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}

export function extractYoutubeChannelId(value: string): string | null {
  const input = value.trim();
  if (/^UC[A-Za-z0-9_-]{20,30}$/.test(input)) return input;
  try {
    const url = new URL(input);
    if (!/(^|\.)youtube\.com$/i.test(url.hostname)) return null;
    const match = url.pathname.match(/^\/channel\/(UC[A-Za-z0-9_-]{20,30})\/?$/i);
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}

export function extractYoutubeHandle(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (!/(^|\.)youtube\.com$/i.test(url.hostname)) return null;
    const match = url.pathname.match(/^\/@([A-Za-z0-9_.-]{2,100})\/?$/);
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}

export function extractSoundCloudUserId(value: string): string | null {
  const match = value.match(/soundcloud:users:(\d+)/i);
  return match?.[1] ?? null;
}

function decodeXml(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/gi, "$1")
    .replace(/&#x([0-9a-f]+);/gi, (_, digits: string) => {
      const code = Number.parseInt(digits, 16);
      return code <= 0x10ffff ? String.fromCodePoint(code) : "";
    })
    .replace(/&#(\d+);/g, (_, digits: string) => {
      const code = Number.parseInt(digits, 10);
      return code <= 0x10ffff ? String.fromCodePoint(code) : "";
    })
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function readXmlTag(block: string, tag: string): string | null {
  const match = block.match(new RegExp("<" + tag + "\\b[^>]*>([\\s\\S]*?)</" + tag + ">", "i"));
  if (!match?.[1]) return null;
  return decodeXml(match[1].trim()).replace(/<[^>]+>/g, "").trim() || null;
}

export function parseSoundCloudFeed(xml: string, artist: string): MusicRelease[] {
  const items = [...xml.matchAll(/<item\b[^>]*>([\s\S]*?)<\/item>/gi)].slice(0, 5);
  const releases: MusicRelease[] = [];
  for (const item of items) {
    const block = item[1] ?? "";
    const title = readXmlTag(block, "title");
    const link = readXmlTag(block, "link");
    const guid = readXmlTag(block, "guid");
    const published = readXmlTag(block, "pubDate");
    if (!link) continue;
    try {
      const url = new URL(link);
      if (url.protocol !== "https:" || !/(^|\.)soundcloud\.com$/i.test(url.hostname)) continue;
      const date = published ? new Date(published) : null;
      releases.push({
        provider: "soundcloud",
        release_id: guid || url.toString(),
        artist,
        title: title || "New Track",
        url: url.toString(),
        release_date: date && Number.isFinite(date.getTime()) ? date.toISOString() : published,
        image_url: null,
        description: null,
        kind: "track",
      });
    } catch {
      continue;
    }
  }
  return releases;
}

export function musicReleaseKey(release: Pick<MusicRelease, "provider" | "release_id">): string {
  return release.provider + ":" + release.release_id;
}

export async function listMusicTrackers(guildId: string): Promise<MusicTracker[]> {
  const rows = await query<MusicTrackerRow>(
    TRACKER_SELECT + "WHERE music_trackers.guild_id = $1 ORDER BY music_trackers.created_at DESC, music_trackers.id",
    [guildId],
  );
  return rows.map(toTracker);
}

export async function getMusicTracker(guildId: string, trackerId: string): Promise<MusicTracker | null> {
  const rows = await query<MusicTrackerRow>(
    TRACKER_SELECT + "WHERE music_trackers.guild_id = $1 AND music_trackers.id = $2 LIMIT 1",
    [guildId, trackerId],
  );
  return rows[0] ? toTracker(rows[0]) : null;
}

export async function addMusicTracker(tracker: MusicTracker): Promise<void> {
  await transaction(async client => {
    await client.query("SELECT pg_advisory_xact_lock($1::bigint)", [tracker.guild_id]);
    const count = await client.query<{ count: string }>(
      "SELECT COUNT(*)::text AS count FROM music_trackers WHERE guild_id = $1",
      [tracker.guild_id],
    );
    if (Number(count.rows[0]?.count ?? 0) >= MAX_TRACKERS_PER_GUILD) {
      throw new Error("MUSIC_TRACKER_LIMIT");
    }
    await client.query(
      "INSERT INTO music_trackers (id, guild_id, channel_id, artist_name, providers, spotify_target, youtube_target, " +
      "soundcloud_target, mention_mode, mention_user_id, mention_role_id, enabled, created_by, created_at, last_checked_at, seen_ids) " +
      "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)",
      [
        tracker.id, tracker.guild_id, tracker.channel_id, tracker.artist_name, tracker.providers,
        tracker.spotify_target, tracker.youtube_target, tracker.soundcloud_target, tracker.mention_mode,
        tracker.mention_user_id, tracker.mention_role_id, tracker.enabled, tracker.created_by,
        tracker.created_at, tracker.last_checked_at, tracker.seen_ids.slice(-MAX_SEEN_IDS),
      ],
    );
  });
}

export async function updateMusicTracker(tracker: MusicTracker): Promise<void> {
  await query(
    "UPDATE music_trackers SET enabled = $3, last_checked_at = $4, seen_ids = $5, updated_at = NOW() " +
    "WHERE guild_id = $1 AND id = $2",
    [tracker.guild_id, tracker.id, tracker.enabled, tracker.last_checked_at, tracker.seen_ids.slice(-MAX_SEEN_IDS)],
  );
}

export async function deleteMusicTracker(guildId: string, trackerId: string): Promise<boolean> {
  const result = await query<{ id: string }>(
    "DELETE FROM music_trackers WHERE guild_id = $1 AND id = $2 RETURNING id",
    [guildId, trackerId],
  );
  return result.length > 0;
}

export class MusicRuntime {
  private spotifyToken: string | null = null;
  private spotifyTokenExpiresAt = 0;
  private readonly youtubeUploadPlaylists = new Map<string, { id: string; name: string }>();
  private timer: NodeJS.Timeout | undefined;
  private polling: Promise<void> | undefined;

  constructor(private readonly config: BotConfig) {}

  get pollIntervalMinutes(): number {
    return this.config.musicPollIntervalMinutes;
  }

  providerStatus(): { spotify: boolean; youtube: boolean; soundcloudSearch: boolean } {
    return {
      spotify: Boolean(this.config.spotifyClientId && this.config.spotifyClientSecret),
      youtube: Boolean(this.config.youtubeApiKey),
      soundcloudSearch: Boolean(this.config.soundcloudClientId),
    };
  }

  private async spotifyAccessToken(): Promise<string | null> {
    if (!this.config.spotifyClientId || !this.config.spotifyClientSecret) return null;
    if (this.spotifyToken && Date.now() < this.spotifyTokenExpiresAt - 60_000) return this.spotifyToken;
    try {
      const response = await fetch(SPOTIFY_TOKEN_URL, {
        method: "POST",
        headers: {
          Authorization: "Basic " + Buffer.from(this.config.spotifyClientId + ":" + this.config.spotifyClientSecret).toString("base64"),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ grant_type: "client_credentials" }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!response.ok) {
        logger.warn("Spotify client credentials request failed", { status: response.status });
        return null;
      }
      const payload = await response.json() as { access_token?: string; expires_in?: number };
      if (!payload.access_token) return null;
      this.spotifyToken = payload.access_token;
      this.spotifyTokenExpiresAt = Date.now() + Math.max(60, Number(payload.expires_in ?? 3600)) * 1000;
      return this.spotifyToken;
    } catch (error) {
      logger.warn("Spotify token request failed", { reason: error instanceof Error ? error.message : "Unknown error" });
      return null;
    }
  }

  private async spotifyGet(path: string, params: Record<string, string> = {}): Promise<Record<string, any> | null> {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const token = await this.spotifyAccessToken();
      if (!token) return null;
      const url = new URL(SPOTIFY_API + path);
      for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
      try {
        const response = await fetch(url, {
          headers: { Authorization: "Bearer " + token },
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        });
        if (response.status === 401) {
          this.spotifyToken = null;
          this.spotifyTokenExpiresAt = 0;
          continue;
        }
        if (!response.ok) {
          logger.warn("Spotify API request failed", { path, status: response.status });
          return null;
        }
        return await response.json() as Record<string, any>;
      } catch (error) {
        logger.warn("Spotify API request failed", { path, reason: error instanceof Error ? error.message : "Unknown error" });
        return null;
      }
    }
    return null;
  }

  private async resolveSpotify(target: string): Promise<string | null> {
    if (!this.providerStatus().spotify) return null;
    const directId = extractSpotifyArtistId(target);
    if (directId) {
      const artist = await this.spotifyGet("/artists/" + directId);
      return typeof artist?.id === "string" ? artist.id : null;
    }
    const result = await this.spotifyGet("/search", { q: target, type: "artist", limit: "1" });
    const items = result?.artists?.items;
    return Array.isArray(items) && typeof items[0]?.id === "string" ? items[0].id : null;
  }

  private async youtubeGet(endpoint: string, params: Record<string, string>): Promise<Record<string, any> | null> {
    if (!this.config.youtubeApiKey) return null;
    const url = new URL(YOUTUBE_API + "/" + endpoint);
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    url.searchParams.set("key", this.config.youtubeApiKey);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
      if (!response.ok) {
        logger.warn("YouTube Data API request failed", { endpoint, status: response.status });
        return null;
      }
      return await response.json() as Record<string, any>;
    } catch (error) {
      logger.warn("YouTube Data API request failed", { endpoint, reason: error instanceof Error ? error.message : "Unknown error" });
      return null;
    }
  }

  private async resolveYoutube(target: string): Promise<string | null> {
    if (!this.config.youtubeApiKey) return null;
    const directId = extractYoutubeChannelId(target);
    if (directId) return directId;
    const handle = extractYoutubeHandle(target);
    if (handle) {
      const result = await this.youtubeGet("channels", { part: "id,snippet", forHandle: handle });
      const id = result?.items?.[0]?.id;
      return typeof id === "string" ? id : null;
    }
    const result = await this.youtubeGet("search", { part: "snippet", q: target, type: "channel", maxResults: "1" });
    const id = result?.items?.[0]?.id?.channelId;
    return typeof id === "string" ? id : null;
  }

  private async resolveSoundCloud(target: string): Promise<string | null> {
    const directId = extractSoundCloudUserId(target);
    if (directId) return directId;
    let profileUrl: URL | null = null;
    try {
      const parsed = new URL(target);
      if (parsed.protocol === "https:" && /(^|\.)soundcloud\.com$/i.test(parsed.hostname) &&
          !parsed.username && !parsed.password && !parsed.port) profileUrl = parsed;
    } catch {
      profileUrl = null;
    }
    if (profileUrl) {
      try {
        let current = profileUrl;
        for (let redirect = 0; redirect <= 3; redirect += 1) {
          const response = await fetch(current, {
            redirect: "manual",
            signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
            headers: { "User-Agent": "Lemegeton-Music/1.0" },
          });
          if ([301, 302, 303, 307, 308].includes(response.status)) {
            const location = response.headers.get("location");
            if (!location || redirect === 3) return null;
            const next = new URL(location, current);
            if (next.protocol !== "https:" || !/(^|\.)soundcloud\.com$/i.test(next.hostname) ||
                next.username || next.password || next.port) return null;
            current = next;
            continue;
          }
          if (!response.ok) return null;
          return extractSoundCloudUserId(await response.text());
        }
        return null;
      } catch (error) {
        logger.warn("SoundCloud profile lookup failed", { reason: error instanceof Error ? error.message : "Unknown error" });
        return null;
      }
    }
    if (!this.config.soundcloudClientId) return null;
    const url = new URL(SOUNDCLOUD_API + "/users");
    url.searchParams.set("q", target);
    url.searchParams.set("client_id", this.config.soundcloudClientId);
    url.searchParams.set("limit", "1");
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
      if (!response.ok) return null;
      const payload = await response.json() as Record<string, any> | Record<string, any>[];
      const items = Array.isArray(payload) ? payload : payload.collection;
      const id = items?.[0]?.id;
      return id !== undefined && id !== null ? String(id) : null;
    } catch (error) {
      logger.warn("SoundCloud search failed", { reason: error instanceof Error ? error.message : "Unknown error" });
      return null;
    }
  }

  async resolveArtist(artist: string): Promise<ResolvedMusicArtist> {
    const [spotify, youtube, soundcloud] = await Promise.all([
      this.resolveSpotify(artist).catch(() => null),
      this.resolveYoutube(artist).catch(() => null),
      this.resolveSoundCloud(artist).catch(() => null),
    ]);
    const providers: MusicProvider[] = [];
    if (spotify) providers.push("spotify");
    if (youtube) providers.push("youtube");
    if (soundcloud) providers.push("soundcloud");
    return {
      providers,
      spotify_target: spotify,
      youtube_target: youtube,
      soundcloud_target: soundcloud,
    };
  }

  private async latestSpotify(artistId: string, artist: string): Promise<MusicRelease[]> {
    const result = await this.spotifyGet("/artists/" + artistId + "/albums", {
      include_groups: "album,single",
      limit: "10",
      market: "IE",
    });
    const items = Array.isArray(result?.items) ? result.items : [];
    return items
      .filter((item: Record<string, any>) => typeof item.id === "string" && typeof item.external_urls?.spotify === "string")
      .map((item: Record<string, any>): MusicRelease => ({
        provider: "spotify",
        release_id: item.id,
        artist: artist,
        title: String(item.name ?? "Unknown Release"),
        url: item.external_urls.spotify,
        release_date: typeof item.release_date === "string" ? item.release_date : null,
        image_url: typeof item.images?.[0]?.url === "string" ? item.images[0].url : null,
        description: null,
        kind: String(item.album_type ?? "release"),
      }))
      .sort((a: MusicRelease, b: MusicRelease) => Date.parse(b.release_date ?? "") - Date.parse(a.release_date ?? ""))
      .slice(0, 5);
  }

  private async latestYoutube(channelId: string, artist: string): Promise<MusicRelease[]> {
    let playlist = this.youtubeUploadPlaylists.get(channelId);
    if (!playlist) {
      const channel = await this.youtubeGet("channels", { part: "snippet,contentDetails", id: channelId });
      const item = channel?.items?.[0];
      const playlistId = item?.contentDetails?.relatedPlaylists?.uploads;
      if (typeof playlistId !== "string") return [];
      playlist = { id: playlistId, name: String(item?.snippet?.title ?? artist) };
      this.youtubeUploadPlaylists.set(channelId, playlist);
    }
    const result = await this.youtubeGet("playlistItems", {
      part: "snippet,contentDetails",
      playlistId: playlist.id,
      maxResults: "5",
    });
    const items = Array.isArray(result?.items) ? result.items : [];
    return items
      .map((item: Record<string, any>): MusicRelease | null => {
        const snippet = item.snippet ?? {};
        const videoId = snippet.resourceId?.videoId ?? item.contentDetails?.videoId;
        if (typeof videoId !== "string") return null;
        const thumbnails = snippet.thumbnails ?? {};
        const thumbnail = thumbnails.high ?? thumbnails.medium ?? thumbnails.default ?? {};
        return {
          provider: "youtube",
          release_id: videoId,
          artist: playlist?.name ?? artist,
          title: String(snippet.title ?? "New Upload"),
          url: "https://www.youtube.com/watch?v=" + videoId,
          release_date: typeof snippet.publishedAt === "string" ? snippet.publishedAt : null,
          image_url: typeof thumbnail.url === "string" ? thumbnail.url : null,
          description: typeof snippet.description === "string" ? snippet.description : null,
          kind: "video",
        };
      })
      .filter((release: MusicRelease | null): release is MusicRelease => release !== null);
  }

  private async latestSoundCloud(userId: string, artist: string): Promise<MusicRelease[]> {
    const url = "https://feeds.soundcloud.com/users/soundcloud:users:" + userId + "/sounds.rss";
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/rss+xml, application/xml, text/xml" },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!response.ok) {
        logger.warn("SoundCloud RSS request failed", { status: response.status });
        return [];
      }
      return parseSoundCloudFeed(await response.text(), artist);
    } catch (error) {
      logger.warn("SoundCloud RSS request failed", { reason: error instanceof Error ? error.message : "Unknown error" });
      return [];
    }
  }

  async latest(tracker: MusicTracker): Promise<MusicRelease[]> {
    const requests = tracker.providers.map(provider => {
      if (provider === "spotify" && tracker.spotify_target) {
        return this.latestSpotify(tracker.spotify_target, tracker.artist_name);
      }
      if (provider === "youtube" && tracker.youtube_target) {
        return this.latestYoutube(tracker.youtube_target, tracker.artist_name);
      }
      if (provider === "soundcloud" && tracker.soundcloud_target) {
        return this.latestSoundCloud(tracker.soundcloud_target, tracker.artist_name);
      }
      return Promise.resolve([] as MusicRelease[]);
    });
    const responses = await Promise.all(requests.map(request => request.catch(() => [] as MusicRelease[])));
    return responses.flat()
      .sort((a, b) => Date.parse(b.release_date ?? "") - Date.parse(a.release_date ?? ""))
      .slice(0, 15);
  }

  start(client: Client): void {
    if (this.timer) return;
    const poll = () => {
      if (this.polling) return;
      const task = this.poll(client).catch(error => {
        logger.error("Music release polling cycle failed", { reason: error instanceof Error ? error.message : "Unknown error" });
      });
      this.polling = task;
      void task.finally(() => {
        if (this.polling === task) this.polling = undefined;
      });
    };
    poll();
    this.timer = setInterval(poll, this.config.musicPollIntervalMinutes * 60_000);
    this.timer.unref();
    logger.info("Music release tracker scheduler started", { intervalMinutes: this.config.musicPollIntervalMinutes });
  }

  async stop(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
    await this.polling;
    this.polling = undefined;
  }

  private async sendRelease(channel: TextChannel, tracker: MusicTracker, release: MusicRelease): Promise<boolean> {
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle(providerName(release.provider) + " · New " + release.kind)
      .setDescription("## " + cleanMusicText(release.title, 250))
      .addFields(
        { name: "Artist", value: cleanMusicText(release.artist, 200), inline: true },
        { name: "Platform", value: providerName(release.provider), inline: true },
        { name: "Source", value: "[Open release](" + release.url + ")", inline: true },
      )
      .setURL(release.url);
    if (release.release_date) {
      embed.addFields({ name: "Released", value: cleanMusicText(release.release_date, 100), inline: true });
    }
    if (release.description) embed.addFields({ name: "Details", value: cleanMusicText(release.description, 700), inline: false });
    if (release.image_url) embed.setThumbnail(release.image_url);

    const mention = tracker.mention_mode === "user" && tracker.mention_user_id ? "<@" + tracker.mention_user_id + ">" : undefined;
    try {
      await channel.send({
        ...(mention ? { content: mention } : {}),
        embeds: [embed],
        allowedMentions: { parse: [], users: mention ? [tracker.mention_user_id!] : [], roles: [] },
      });
      return true;
    } catch (error) {
      logger.warn("Music release notification could not be sent", {
        guildId: tracker.guild_id,
        trackerId: tracker.id,
        channelId: tracker.channel_id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      return false;
    }
  }

  private async poll(client: Client): Promise<void> {
    const guildIds = [...client.guilds.cache.keys()];
    if (!guildIds.length) return;
    const rows = await query<MusicTrackerRow>(
      TRACKER_SELECT +
      "JOIN guild_retention_settings retention ON retention.guild_id = music_trackers.guild_id " +
      "JOIN guild_language_settings language ON language.guild_id = music_trackers.guild_id " +
      "WHERE music_trackers.guild_id = ANY($1::bigint[]) AND music_trackers.enabled = TRUE " +
      "AND retention.leave_action IN ('delete','retain') AND retention.deleted_at IS NULL " +
      "ORDER BY music_trackers.guild_id, music_trackers.created_at",
      [guildIds],
    );
    for (const row of rows) {
      const tracker = toTracker(row);
      try {
        const channelValue = await client.channels.fetch(tracker.channel_id).catch(() => null);
        if (!channelValue || channelValue.type !== ChannelType.GuildText || !client.user) continue;
        const channel = channelValue as TextChannel;
        const permissions = channel.permissionsFor(client.user);
        if (!permissions?.has([
          PermissionFlagsBits.ViewChannel,
          PermissionFlagsBits.SendMessages,
          PermissionFlagsBits.EmbedLinks,
        ])) continue;

        const releases = await this.latest(tracker);
        tracker.last_checked_at = new Date().toISOString();
        if (!releases.length) {
          await updateMusicTracker(tracker);
          continue;
        }

        const known = new Set(tracker.seen_ids);
        if (!known.size) {
          tracker.seen_ids = releases.map(musicReleaseKey).slice(-MAX_SEEN_IDS);
          await updateMusicTracker(tracker);
          continue;
        }

        const unseen = releases
          .filter(release => !known.has(musicReleaseKey(release)))
          .sort((a, b) => Date.parse(a.release_date ?? "") - Date.parse(b.release_date ?? ""));
        for (const release of unseen) {
          if (await this.sendRelease(channel, tracker, release)) {
            tracker.seen_ids.push(musicReleaseKey(release));
            tracker.seen_ids = tracker.seen_ids.slice(-MAX_SEEN_IDS);
          }
        }
        await updateMusicTracker(tracker);
      } catch (error) {
        logger.warn("Music release tracker check failed", {
          guildId: tracker.guild_id,
          trackerId: tracker.id,
          reason: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }
  }
}

let sharedRuntime: MusicRuntime | undefined;

export function getMusicRuntime(config: BotConfig): MusicRuntime {
  if (!sharedRuntime) sharedRuntime = new MusicRuntime(config);
  return sharedRuntime;
}

export function startMusicScheduler(client: Client, config: BotConfig): void {
  getMusicRuntime(config).start(client);
}

export async function stopMusicScheduler(): Promise<void> {
  await sharedRuntime?.stop();
  sharedRuntime = undefined;
}

export function providerName(provider: MusicProvider): string {
  if (provider === "spotify") return "Spotify";
  if (provider === "youtube") return "YouTube Music";
  return "SoundCloud";
}

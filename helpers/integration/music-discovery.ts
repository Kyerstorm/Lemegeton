import type { BotConfig } from "../runtime/config.js";
import { fetchProviderResponse } from "./provider-http.js";

const MUSICBRAINZ_API = "https://musicbrainz.org/ws/2";
const LASTFM_API = "https://ws.audioscrobbler.com/2.0/";
const SETLISTFM_API = "https://api.setlist.fm/rest/1.0";
const USER_AGENT = "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton)";
const REQUEST_TIMEOUT_MS = 10_000;
const CACHE_TTL_MS = 15 * 60_000;

export type MusicArtistResult = {
  id: string;
  name: string;
  type: string | null;
  country: string | null;
  beginArea: string | null;
  beginDate: string | null;
  disambiguation: string | null;
  score: number | null;
};

export type MusicLabelResult = {
  id: string;
  name: string;
  type: string | null;
  country: string | null;
  beginArea: string | null;
  beginDate: string | null;
  endDate: string | null;
  labelCode: string | null;
  disambiguation: string | null;
  score: number | null;
  sourceUrl: string;
};

export type MusicReleaseGroup = {
  id: string;
  title: string;
  type: string | null;
  secondaryTypes: string[];
  firstReleaseDate: string | null;
};

export type MusicChartEntry = {
  rank: number;
  title: string;
  artist: string;
  url: string | null;
  listeners: number | null;
  playcount: number | null;
  mbid: string | null;
};

export type MusicSetlist = {
  id: string;
  artist: string;
  venue: string;
  city: string | null;
  country: string | null;
  date: string | null;
  tour: string | null;
  songs: string[];
  url: string | null;
};

type JsonObject = Record<string, unknown>;

const cache = new Map<string, { expiresAt: number; value: unknown }>();
let musicBrainzQueue: Promise<void> = Promise.resolve();
let musicBrainzNextRequestAt = 0;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function string(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function number(value: unknown): number | null {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cached<T>(key: string): T | null {
  const entry = cache.get(key);
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) {
    cache.delete(key);
    return null;
  }
  return entry.value as T;
}

function remember<T>(key: string, value: T): T {
  if (cache.size >= 300) {
    const first = cache.keys().next().value;
    if (first) cache.delete(first);
  }
  cache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
  return value;
}

async function fetchJson(url: URL, headers: Record<string, string> = {}, fetcher: typeof fetch = globalThis.fetch): Promise<unknown> {
  const response = await fetchProviderResponse(fetcher, url, {
    headers: { Accept: "application/json", "User-Agent": USER_AGENT, ...headers },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) throw new Error("Music provider returned HTTP " + response.status + ".");
  return response.json() as Promise<unknown>;
}

async function cachedJson(url: URL, headers: Record<string, string> = {}, fetcher: typeof fetch = globalThis.fetch): Promise<unknown> {
  const key = url.toString();
  const hit = cached<unknown>(key);
  if (hit !== null) return hit;
  return remember(key, await fetchJson(url, headers, fetcher));
}

async function musicBrainzJson(path: string, fetcher: typeof fetch = globalThis.fetch, minimumIntervalMs = 1_100): Promise<unknown> {
  const url = MUSICBRAINZ_API + path;
  const hit = cached<unknown>(url);
  if (hit !== null) return hit;

  const task = musicBrainzQueue.then(async () => {
    const wait = Math.max(0, musicBrainzNextRequestAt - Date.now());
    if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
    const queuedHit = cached<unknown>(url);
    if (queuedHit !== null) return queuedHit;
    musicBrainzNextRequestAt = Date.now() + minimumIntervalMs;
    const result = await fetchJson(new URL(url), {}, fetcher);
    return remember(url, result);
  });
  musicBrainzQueue = task.then(() => undefined, () => undefined);
  return task;
}

export function parseMusicBrainzArtists(payload: unknown): MusicArtistResult[] {
  const artists = object(payload)?.artists;
  if (!Array.isArray(artists)) return [];
  return artists.flatMap(entry => {
    const artist = object(entry);
    const id = string(artist?.id);
    const name = string(artist?.name);
    if (!artist || !id || !name) return [];
    const lifeSpan = object(artist["life-span"]);
    const beginArea = object(artist["begin-area"]);
    return [{
      id,
      name,
      type: string(artist.type),
      country: string(artist.country),
      beginArea: string(beginArea?.name),
      beginDate: string(lifeSpan?.begin),
      disambiguation: string(artist.disambiguation),
      score: number(artist.score),
    }];
  });
}

export function parseMusicBrainzLabels(payload: unknown): MusicLabelResult[] {
  const labels = object(payload)?.labels;
  if (!Array.isArray(labels)) return [];
  return labels.flatMap(entry => {
    const label = object(entry);
    const id = string(label?.id);
    const name = string(label?.name);
    if (!label || !id || !/^[0-9a-f-]{36}$/i.test(id) || !name) return [];
    const lifeSpan = object(label["life-span"]);
    const beginArea = object(label["begin-area"]);
    return [{
      id,
      name,
      type: string(label.type),
      country: string(label.country),
      beginArea: string(beginArea?.name),
      beginDate: string(lifeSpan?.begin),
      endDate: string(lifeSpan?.end),
      labelCode: string(label["label-code"]),
      disambiguation: string(label.disambiguation),
      score: number(label.score),
      sourceUrl: "https://musicbrainz.org/label/" + id,
    }];
  }).slice(0, 10);
}

export function parseMusicBrainzReleaseGroups(payload: unknown): MusicReleaseGroup[] {
  const groups = object(payload)?.["release-groups"];
  if (!Array.isArray(groups)) return [];
  return groups.flatMap(entry => {
    const group = object(entry);
    const id = string(group?.id);
    const title = string(group?.title);
    if (!group || !id || !title) return [];
    const secondaryTypes = Array.isArray(group["secondary-types"])
      ? group["secondary-types"].filter((value): value is string => typeof value === "string")
      : [];
    return [{
      id,
      title,
      type: string(group["primary-type"]),
      secondaryTypes,
      firstReleaseDate: string(group["first-release-date"]),
    }];
  });
}

export function parseLastFmChart(payload: unknown, kind: "artists" | "tracks"): MusicChartEntry[] {
  const root = object(payload);
  const collection = object(root?.[kind]);
  const entries = collection?.[kind === "artists" ? "artist" : "track"];
  if (!Array.isArray(entries)) return [];
  return entries.flatMap((entry, index) => {
    const item = object(entry);
    const artist = kind === "artists" ? item : object(item?.artist);
    const title = string(kind === "artists" ? item?.name : item?.name);
    const artistName = string(artist?.name);
    if (!item || !title || !artistName) return [];
    return [{
      rank: number(item["@attr"] && object(item["@attr"])?.rank) ?? index + 1,
      title,
      artist: artistName,
      url: string(item.url),
      listeners: number(item.listeners),
      playcount: number(item.playcount),
      mbid: string(item.mbid) ?? string(artist?.mbid),
    }];
  });
}

export function parseSetlistFmSetlists(payload: unknown): MusicSetlist[] {
  const setlists = object(payload)?.setlist;
  if (!Array.isArray(setlists)) return [];
  return setlists.flatMap(entry => {
    const setlist = object(entry);
    const artist = object(setlist?.artist);
    const venue = object(setlist?.venue);
    const city = object(venue?.city);
    const id = string(setlist?.id);
    const artistName = string(artist?.name);
    const venueName = string(venue?.name);
    if (!setlist || !id || !artistName || !venueName) return [];
    const sets = Array.isArray(setlist.set) ? setlist.set : [];
    const songs = sets.flatMap(set => {
      const songSet = object(set);
      return Array.isArray(songSet?.song)
        ? songSet.song.flatMap(song => {
          const name = string(object(song)?.name);
          return name ? [name] : [];
        })
        : [];
    });
    return [{
      id,
      artist: artistName,
      venue: venueName,
      city: string(city?.name),
      country: string(object(city?.country)?.name),
      date: string(setlist.eventDate),
      tour: string(object(setlist.tour)?.name),
      songs,
      url: string(setlist.url),
    }];
  });
}

export class MusicDiscovery {
  constructor(
    private readonly config: BotConfig,
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly musicBrainzMinimumIntervalMs = 1_100,
  ) {}

  providerStatus(): { musicbrainz: boolean; lastfm: boolean; setlistfm: boolean } {
    return {
      musicbrainz: true,
      lastfm: Boolean(this.config.lastFmApiKey),
      setlistfm: Boolean(this.config.setlistFmApiKey),
    };
  }

  async searchArtists(query: string): Promise<MusicArtistResult[]> {
    const term = query.trim();
    if (!term || term.length > 100) return [];
    const phrase = term.replace(/\\/g, "\\\\").replace(/"/g, "\\\"");
    const params = new URLSearchParams({ query: "artist:\"" + phrase + "\"", fmt: "json", limit: "5" });
    const result = await musicBrainzJson("/artist?" + params.toString(), this.fetcher, this.musicBrainzMinimumIntervalMs);
    return parseMusicBrainzArtists(result);
  }

  async artist(id: string): Promise<MusicArtistResult | null> {
    if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
    const result = await musicBrainzJson("/artist/" + encodeURIComponent(id) + "?fmt=json", this.fetcher, this.musicBrainzMinimumIntervalMs);
    const parsed = parseMusicBrainzArtists({ artists: [result] });
    return parsed[0] ?? null;
  }

  async discography(id: string, offset = 0): Promise<MusicReleaseGroup[]> {
    if (!/^[0-9a-f-]{36}$/i.test(id)) return [];
    const params = new URLSearchParams({
      artist: id,
      type: "album|ep|single|compilation",
      fmt: "json",
      limit: "10",
      offset: String(Math.max(0, Math.min(500, Math.floor(offset)))),
    });
    const result = await musicBrainzJson("/release-group?" + params.toString(), this.fetcher, this.musicBrainzMinimumIntervalMs);
    return parseMusicBrainzReleaseGroups(result);
  }

  async searchLabels(query: string): Promise<MusicLabelResult[]> {
    const term = query.trim();
    if (term.length < 2 || term.length > 100) return [];
    const phrase = term.replace(/\\/g, "\\\\").replace(/"/g, "\\\"");
    const params = new URLSearchParams({ query: 'label:"' + phrase + '"', fmt: "json", limit: "10" });
    return parseMusicBrainzLabels(await musicBrainzJson("/label?" + params.toString(), this.fetcher, this.musicBrainzMinimumIntervalMs));
  }

  async label(id: string): Promise<MusicLabelResult | null> {
    if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
    const result = await musicBrainzJson("/label/" + encodeURIComponent(id) + "?fmt=json", this.fetcher, this.musicBrainzMinimumIntervalMs);
    return parseMusicBrainzLabels({ labels: [result] })[0] ?? null;
  }

  async charts(kind: "artists" | "tracks"): Promise<MusicChartEntry[]> {
    if (!this.config.lastFmApiKey) throw new Error("Last.fm is not configured.");
    const url = new URL(LASTFM_API);
    url.search = new URLSearchParams({
      method: kind === "artists" ? "chart.gettopartists" : "chart.gettoptracks",
      api_key: this.config.lastFmApiKey,
      format: "json",
      limit: "10",
      page: "1",
    }).toString();
    return parseLastFmChart(await cachedJson(url, {}, this.fetcher), kind);
  }

  async setlists(artistMbid: string, page = 1): Promise<MusicSetlist[]> {
    if (!this.config.setlistFmApiKey) throw new Error("setlist.fm is not configured.");
    if (!/^[0-9a-f-]{36}$/i.test(artistMbid)) return [];
    const url = new URL(SETLISTFM_API + "/artist/" + encodeURIComponent(artistMbid) + "/setlists");
    url.searchParams.set("p", String(Math.max(1, Math.min(20, Math.floor(page)))));
    return parseSetlistFmSetlists(await cachedJson(url, { "x-api-key": this.config.setlistFmApiKey }, this.fetcher));
  }
}

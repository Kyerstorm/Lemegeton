import { fetchProviderResponse } from "./provider-http.js";

export interface RoyalRoadChapter {
  title: string;
  url: string;
  publishedAt: string | null;
}

export interface RoyalRoadFiction {
  id: number;
  title: string;
  author: string | null;
  sourceUrl: string;
  feedUrl: string;
  chapters: RoyalRoadChapter[];
  latestUpdate: string | null;
  image: null;
}

function xmlText(value: string | undefined): string {
  if (!value) return "";
  return value.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x([0-9a-f]+);/gi, (_, hex: string) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, decimal: string) => String.fromCodePoint(Number(decimal)))
    .replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&apos;|&#39;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/\s+/g, " ").trim();
}

function tagValue(xml: string, tag: string): string {
  const match = new RegExp("<" + tag + "(?:\\s[^>]*)?>([\\s\\S]*?)</" + tag + ">", "i").exec(xml);
  return xmlText(match?.[1]);
}

function royalRoadUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "https:" || url.hostname !== "www.royalroad.com"
      || url.username || url.password || url.port || url.search || url.hash) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function parseRoyalRoadFictionId(value: string): number {
  const input = value.trim();
  let id: string | null = null;
  if (/^\d{1,10}$/.test(input)) id = input;
  else {
    const safe = royalRoadUrl(input);
    if (!safe) throw new Error("Use a Royal Road fiction ID or an HTTPS URL from www.royalroad.com.");
    const url = new URL(safe);
    const match = /^\/fiction\/(?:syndication\/)?(\d+)(?:\/[^/]*)?\/?$/.exec(url.pathname);
    id = match?.[1] ?? null;
  }
  const numeric = id ? Number(id) : NaN;
  if (!Number.isSafeInteger(numeric) || numeric < 1) {
    throw new Error("Use a Royal Road fiction page URL, RSS syndication URL, or numeric fiction ID.");
  }
  return numeric;
}

export function parseRoyalRoadFeed(value: unknown, fictionId: number): RoyalRoadFiction | null {
  if (typeof value !== "string" || value.length > 512_000 || !/^\s*(?:<\?xml[^>]*>\s*)?<rss\b/i.test(value)
    || /<!DOCTYPE|<!ENTITY/i.test(value)) return null;
  const channel = /<channel(?:\s[^>]*)?>([\s\S]*?)<\/channel>/i.exec(value)?.[1];
  if (!channel) return null;
  const channelTitle = tagValue(channel, "title");
  const title = channelTitle.replace(/^Latest updates of\s*\(/i, "").replace(/\)$/, "").trim();
  if (!title) return null;
  const channelLink = royalRoadUrl(tagValue(channel, "link"));
  const author = tagValue(channel, "author") || tagValue(channel, "managingEditor") || null;
  const chapters = [...channel.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)]
    .flatMap((match): RoyalRoadChapter[] => {
      const item = match[1] ?? "";
      const chapterTitle = tagValue(item, "title");
      const chapterUrl = royalRoadUrl(tagValue(item, "link"));
      if (!chapterTitle || !chapterUrl) return [];
      const parsedDate = Date.parse(tagValue(item, "pubDate"));
      return [{
        title: chapterTitle.slice(0, 180),
        url: chapterUrl,
        publishedAt: Number.isFinite(parsedDate) ? new Date(parsedDate).toISOString() : null,
      }];
    })
    .sort((a, b) => (b.publishedAt ?? "").localeCompare(a.publishedAt ?? ""))
    .slice(0, 5);
  const latestUpdate = chapters.find((chapter) => chapter.publishedAt)?.publishedAt ?? null;
  return {
    id: fictionId,
    title: title.slice(0, 200),
    author: author ? author.slice(0, 160) : null,
    sourceUrl: channelLink ?? "https://www.royalroad.com/fiction/" + fictionId,
    feedUrl: "https://www.royalroad.com/fiction/syndication/" + fictionId,
    chapters,
    latestUpdate,
    image: null,
  };
}

export class RoyalRoadClient {
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;

  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly minimumIntervalMs = 1_100,
  ) {}

  async getFiction(value: string): Promise<RoyalRoadFiction> {
    const id = parseRoyalRoadFictionId(value);
    const feedUrl = "https://www.royalroad.com/fiction/syndication/" + id;
    const previous = this.requestQueue;
    let release!: () => void;
    this.requestQueue = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, this.minimumIntervalMs - (Date.now() - this.lastRequestAt));
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
      this.lastRequestAt = Date.now();
      const response = await fetchProviderResponse(this.fetcher, feedUrl, {
        headers: { Accept: "application/rss+xml, application/xml, text/xml;q=0.9" },
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error("Royal Road RSS returned HTTP " + response.status + ".");
      const xml = await response.text();
      if (new TextEncoder().encode(xml).byteLength > 512_000) {
        throw new Error("The Royal Road RSS feed exceeded the 512 KB response limit.");
      }
      const fiction = parseRoyalRoadFeed(xml, id);
      if (!fiction) throw new Error("Royal Road did not return a valid public RSS feed for that fiction ID.");
      return fiction;
    } finally {
      release();
    }
  }
}

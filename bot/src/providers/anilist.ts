export type MediaType = "ANIME" | "MANGA";
type MediaSort = "SEARCH_MATCH" | "TRENDING_DESC";

type UnknownRecord = Record<string, unknown>;

export interface AniListMedia {
  id: number;
  type: MediaType;
  title: {
    romaji: string | null;
    english: string | null;
    native: string | null;
  };
  description: string | null;
  averageScore: number | null;
  siteUrl: string;
  status: string | null;
  format: string | null;
  episodes: number | null;
  chapters: number | null;
  volumes: number | null;
  startDate: {
    year: number | null;
    month: number | null;
    day: number | null;
  } | null;
  genres: string[];
  coverImage: {
    large: string | null;
  } | null;
}

export class AniListError extends Error {
  constructor(message: string, readonly statusCode?: number) {
    super(message);
    this.name = "AniListError";
  }
}

const MEDIA_SEARCH_QUERY = `
  query MediaSearch($search: String, $type: MediaType!, $sort: [MediaSort]) {
    Page(page: 1, perPage: 5) {
      media(search: $search, type: $type, sort: $sort) {
        id
        type
        title { romaji english native }
        description(asHtml: false)
        averageScore
        siteUrl
        status
        format
        episodes
        chapters
        volumes
        startDate { year month day }
        genres
        coverImage { large }
      }
    }
  }
`;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseMedia(value: unknown): AniListMedia | null {
  if (!isRecord(value)) return null;
  if (!Number.isSafeInteger(value.id) || typeof value.id !== "number" || value.id < 1) return null;
  if (value.type !== "ANIME" && value.type !== "MANGA") return null;

  const title = isRecord(value.title) ? value.title : {};
  const startDate = isRecord(value.startDate)
    ? {
        year: nullableNumber(value.startDate.year),
        month: nullableNumber(value.startDate.month),
        day: nullableNumber(value.startDate.day),
      }
    : null;
  const coverImage = isRecord(value.coverImage)
    ? { large: nullableString(value.coverImage.large) }
    : null;
  const siteUrl = nullableString(value.siteUrl);
  if (!siteUrl) return null;

  try {
    const parsedUrl = new URL(siteUrl);
    if (parsedUrl.protocol !== "https:" || parsedUrl.hostname !== "anilist.co") return null;
  } catch {
    return null;
  }

  return {
    id: value.id,
    type: value.type,
    title: {
      romaji: nullableString(title.romaji),
      english: nullableString(title.english),
      native: nullableString(title.native),
    },
    description: nullableString(value.description),
    averageScore: nullableNumber(value.averageScore),
    siteUrl,
    status: nullableString(value.status),
    format: nullableString(value.format),
    episodes: nullableNumber(value.episodes),
    chapters: nullableNumber(value.chapters),
    volumes: nullableNumber(value.volumes),
    startDate,
    genres: Array.isArray(value.genres)
      ? value.genres.filter((genre): genre is string => typeof genre === "string").slice(0, 20)
      : [],
    coverImage,
  };
}

export class AniListClient {
  constructor(
    private readonly endpoint = "https://graphql.anilist.co",
    private readonly timeoutMs = 10_000,
    private readonly fetcher: typeof fetch = globalThis.fetch,
  ) {}

  searchMedia(query: string, type: MediaType): Promise<AniListMedia[]> {
    return this.request({ search: query.trim(), type, sort: "SEARCH_MATCH" });
  }

  getTrending(type: MediaType): Promise<AniListMedia[]> {
    return this.request({ type, sort: "TRENDING_DESC" });
  }

  private async request(variables: {
    search?: string;
    type: MediaType;
    sort: MediaSort;
  }): Promise<AniListMedia[]> {
    let response: Response;
    try {
      response = await this.fetcher(this.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.strinfify({ query: MEDIA_SEARCH_QUERY, variables }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (error) {
      const timedOut = error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
      throw new AniListError(timedOut ? "AniList request timed out." : "AniList could not be reached.");
    }

    if (!response.ok) {
      throw new AniListError(`AniList returned HTTP ${response.status}.`, response.status);
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new AniListError("AniList returned an invalid response.");
    }

    if (!isRecord(payload)) throw new AniListError("AniList returned an invalid response.");
    if (Array.isArray(payload.errors) && payload.errors.length > 0) {
      throw new AniListError("AniList could not complete this search.");
    }

    const data = isRecord(payload.data) ? payload.data : null;
    const page = data && isRecord(data.Page) ? data.Page : null;
    const results = page && Array.isArray(page.media) ? page.media : [];
    return results.map(parseMedia).filter((media): media is AniListMedia => media !== null);
  }
}

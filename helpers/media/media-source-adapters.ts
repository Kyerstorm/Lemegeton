import {
  MEDIA_SOURCES,
  getMediaSource,
  type MediaSourceCategory,
  type MediaSourceDefinition,
} from "./media-source-registry.js";

export interface MediaSourceResearchLink {
  id: string;
  name: string;
  category: MediaSourceCategory;
  status: MediaSourceDefinition["status"];
  methods: MediaSourceDefinition["method"];
  url: string | null;
  notes: string;
}

type SearchUrlBuilder = (query: string) => string;

const SEARCH_URLS: Readonly<Record<string, SearchUrlBuilder>> = {
  "order-of-book-series": query => "https://orderofbookseries.com/?s=" + encodeURIComponent(query),
  "wookieepedia": query => "https://starwars.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "memory-alpha": query => "https://memory-alpha.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "tardis-wiki": query => "https://tardis.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "marvel-database": query => "https://marvel.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "dc-database": query => "https://dc.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "tolkien-gateway": query => "https://tolkiengateway.net/wiki/Special:Search?query=" + encodeURIComponent(query),
  "harry-potter-wiki": query => "https://harrypotter.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "a-song-of-ice-and-fire-wiki": query => "https://awoiaf.westeros.org/index.php?search=" + encodeURIComponent(query),
  "witcher-wiki": query => "https://witcher.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "narutopedia": query => "https://naruto.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "dragon-ball-wiki": query => "https://dragonball.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "one-piece-wiki": query => "https://onepiece.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "jojos-bizarre-encyclopedia": query => "https://jojowiki.com/Special:Search?query=" + encodeURIComponent(query),
  "pokemon-wiki": query => "https://pokemon.fandom.com/wiki/Special:Search?query=" + encodeURIComponent(query),
  "transformers-wiki": query => "https://tfwiki.net/wiki/Special:Search?search=" + encodeURIComponent(query),
  "myanimelist": query => "https://myanimelist.net/anime.php?q=" + encodeURIComponent(query),
  "anime-planet": query => "https://www.anime-planet.com/anime/all?name=" + encodeURIComponent(query),
  "mangaupdates": query => "https://www.mangaupdates.com/series.html?search=" + encodeURIComponent(query),
  "mangadex": query => "https://mangadex.org/search?q=" + encodeURIComponent(query),
  "anilist": query => "https://anilist.co/search/anime?search=" + encodeURIComponent(query),
  "anidb": query => "https://anidb.net/anime/?adb.search=" + encodeURIComponent(query),
  "kitsu": query => "https://kitsu.app/anime?filter[text]=" + encodeURIComponent(query),
  "shikimori": query => "https://shikimori.one/animes?search=" + encodeURIComponent(query),
  "tmdb": query => "https://www.themoviedb.org/search?query=" + encodeURIComponent(query),
  "thetvdb": query => "https://thetvdb.com/search?query=" + encodeURIComponent(query),
  "tvmaze": query => "https://www.tvmaze.com/search?q=" + encodeURIComponent(query),
  "trakt": query => "https://trakt.tv/search?query=" + encodeURIComponent(query),
  "imdb": query => "https://www.imdb.com/find/?q=" + encodeURIComponent(query),
  "goodreads": query => "https://www.goodreads.com/search?q=" + encodeURIComponent(query),
  "storygraph": query => "https://app.thestorygraph.com/browse?search_term=" + encodeURIComponent(query),
  "hardcover": query => "https://hardcover.app/search?q=" + encodeURIComponent(query),
  "comic-vine": query => "https://comicvine.gamespot.com/search/?q=" + encodeURIComponent(query),
  "google-books": query => "https://books.google.com/books?q=" + encodeURIComponent(query),
  "open-library": query => "https://openlibrary.org/search?q=" + encodeURIComponent(query),
  "isfdb": query => "https://www.isfdb.org/cgi-bin/se.cgi?arg=" + encodeURIComponent(query) + "&type=All",
  "worldcat": query => "https://search.worldcat.org/search?q=" + encodeURIComponent(query),
  "wikidata": query => "https://www.wikidata.org/w/index.php?search=" + encodeURIComponent(query),
  "reddit": query => "https://www.reddit.com/search/?q=" + encodeURIComponent(query),
  "musicbrainz": query => "https://musicbrainz.org/search?query=" + encodeURIComponent(query) + "&type=artist&method=indexed",
  "last-fm": query => "https://www.last.fm/search?q=" + encodeURIComponent(query),
  "setlist-fm": query => "https://www.setlist.fm/search?query=" + encodeURIComponent(query),
  "spotify": query => "https://open.spotify.com/search/" + encodeURIComponent(query),
  "youtube-data-api": query => "https://www.youtube.com/results?search_query=" + encodeURIComponent(query),
  "soundcloud": query => "https://soundcloud.com/search?q=" + encodeURIComponent(query),
};

function safeHomepage(source: MediaSourceDefinition): string | null {
  if (!source.homepage) return null;
  try {
    const url = new URL(source.homepage);
    return url.protocol === "https:" && !url.username && !url.password && !url.port
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

/**
 * Produces a research directory for the requested source inventory.
 * Search links are navigation only: they are never treated as returned
 * metadata, evidence, an API grant, or permission to scrape the destination.
 */
export function getMediaSourceResearchLinks(
  query: string,
  categories?: readonly MediaSourceCategory[],
): MediaSourceResearchLink[] {
  const term = query.trim().replace(/\s+/g, " ").slice(0, 100);
  const selected = (categories?.length
    ? MEDIA_SOURCES.filter(source => categories.includes(source.category))
    : [...MEDIA_SOURCES]).filter(source => source.id !== "novel-updates");

  return selected.map(source => {
    const homepage = safeHomepage(source);
    const builder = SEARCH_URLS[source.id];
    const url = term && builder ? builder(term) : homepage;
    return {
      id: source.id,
      name: source.name,
      category: source.category,
      status: source.status,
      methods: source.method,
      url,
      notes: source.notes,
    };
  });
}

export function getMediaSourceResearchLink(
  sourceId: string,
  query = "",
): MediaSourceResearchLink | null {
  const source = getMediaSource(sourceId);
  if (!source) return null;
  return getMediaSourceResearchLinks(query, [source.category]).find(item => item.id === source.id) ?? null;
}

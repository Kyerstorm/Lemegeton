export type MediaSourceStatus =
  | "implemented"
  | "credential-required"
  | "licensed-access"
  | "license-review"
  | "terms-review"
  | "mediawiki-conditional"
  | "manual-reference"
  | "needs-review"
  | "restricted-noncommercial"
  | "retired";

export type MediaSourceMethod =
  | "api"
  | "feed"
  | "dataset"
  | "mediawiki"
  | "public-reference"
  | "licensed-api"
  | "manual";

export type MediaSourceCategory =
  | "chronology"
  | "franchise-wiki"
  | "anime-manga"
  | "screen"
  | "books-comics"
  | "knowledge"
  | "community"
  | "music";

export interface MediaSourceDefinition {
  id: string;
  name: string;
  category: MediaSourceCategory;
  method: MediaSourceMethod[];
  status: MediaSourceStatus;
  homepage: string | null;
  notes: string;
}

const reviewedAt = "2026-11-27";

/**
 * Requested source inventory for Timeline and Industry.
 *
 * A source being listed does not imply that its content can be scraped or
 * redistributed. Conditional sources are enabled only after their current
 * access terms, attribution and licence are verified.
 */
export const MEDIA_SOURCES: readonly MediaSourceDefinition[] = [
  { id: "the-canonicle", name: "The Canonicle", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: "https://thecanonicle.com/en/", notes: "Use source-linked manual verification only until the site authorizes automated metadata access; do not reproduce descriptions, images or story text." },
  { id: "chronocanon", name: "ChronoCanon", category: "chronology", method: ["public-reference", "manual"], status: "needs-review", homepage: null, notes: "Franchise chronology reference named in the source inventory. Its canonical site and access method are not yet verified; do not infer a URL or build an adapter until confirmed." },
  { id: "chronelines", name: "Chronelines", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: "https://chronelines.com/", notes: "Use source-linked manual verification until automated access terms are confirmed. Keep in-world, release and medium orders separate." },
  { id: "chronologeek", name: "Chronologeek", category: "chronology", method: ["public-reference", "manual"], status: "needs-review", homepage: null, notes: "Canonical site, coverage and access method require verification before adding an adapter." },
  { id: "order-of-book-series", name: "Order of Book Series", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: "https://orderofbookseries.com/", notes: "Use source-linked manual verification until automated access terms are confirmed. Publication order is its default; in-story chronology remains unknown when absent." },
  { id: "comic-book-herald", name: "Comic Book Herald", category: "chronology", method: ["feed", "manual"], status: "manual-reference", homepage: "https://www.comicbookherald.com/", notes: "Editorial reading guidance, not official canon. The terms prohibit automated page scripts and limit site use to non-commercial purposes; only the unmodified RSS feed is eligible after explicit non-commercial confirmation." },
  { id: "official-franchise-timelines", name: "Official Franchise Timelines", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: null, notes: "Primary-source collection. Verify rights-holder ownership, continuity, edition and publication date for every entry." },
  { id: "official-episode-guides", name: "Official Episode Guides", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: null, notes: "Primary episode and broadcast sequence references. Preserve region and original broadcast context." },
  { id: "official-novel-series-guides", name: "Official Novel Series Guides", category: "chronology", method: ["public-reference", "manual"], status: "manual-reference", homepage: null, notes: "Primary volume and publication-order references. Keep official numbering distinct from in-world chronology." },

  { id: "wookieepedia", name: "Wookieepedia", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://starwars.fandom.com/", notes: "Use its configured MediaWiki API only after verifying current site terms, API availability, terms and attribution. Continuities must remain distinct." },
  { id: "memory-alpha", name: "Memory Alpha", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://memory-alpha.fandom.com/", notes: "Episode, film and production references. Verify API endpoint and site-specific policies before automated access." },
  { id: "tardis-wiki", name: "Tardis Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://tardis.fandom.com/", notes: "Cross-media Doctor Who references. Preserve separate continuities and verify site-specific access policy." },
  { id: "marvel-database", name: "Marvel Database", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://marvel.fandom.com/", notes: "Comic events, characters and alternate realities. Do not treat fan-maintained pages as official canon." },
  { id: "dc-database", name: "DC Database", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://dc.fandom.com/", notes: "Comic events, characters and continuities. Verify the actual wiki API endpoint and site terms." },
  { id: "tolkien-gateway", name: "Tolkien Gateway", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://tolkiengateway.net/", notes: "Tolkien bibliography and chronology. Verify local MediaWiki API, site terms, attribution and reuse terms." },
  { id: "harry-potter-wiki", name: "Harry Potter Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://harrypotter.fandom.com/", notes: "Wizarding World reference material. Use as community evidence, not a primary canon authority." },
  { id: "a-song-of-ice-and-fire-wiki", name: "A Song of Ice and Fire Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://awoiaf.westeros.org/", notes: "Book and television records need separate continuity labels and source citations." },
  { id: "witcher-wiki", name: "The Witcher Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://witcher.fandom.com/", notes: "Book, game and screen continuity references must not be merged as one canon." },
  { id: "narutopedia", name: "Narutopedia", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://naruto.fandom.com/", notes: "Manga, anime, film and game references. Record source continuity and source page revisions." },
  { id: "dragon-ball-wiki", name: "Dragon Ball Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://dragonball.fandom.com/", notes: "Separate manga, anime, films and game continuities; review site policies first." },
  { id: "one-piece-wiki", name: "One Piece Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://onepiece.fandom.com/", notes: "Arc and episode references are community-maintained. Retain citations and revisions." },
  { id: "jojos-bizarre-encyclopedia", name: "JoJo's Bizarre Encyclopedia", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://jojowiki.com/", notes: "Part, character and continuity references. Verify API configuration and terms." },
  { id: "pokemon-wiki", name: "Pokémon Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://pokemon.fandom.com/", notes: "Game, anime and film continuity must remain separate where source evidence differs." },
  { id: "transformers-wiki", name: "Transformers Wiki", category: "franchise-wiki", method: ["mediawiki", "public-reference"], status: "mediawiki-conditional", homepage: "https://tfwiki.net/", notes: "Transformers Wiki is an independent wiki; verify its API and policies rather than assuming Fandom configuration." },
  { id: "fandom-wikis", name: "Fandom Wikis", category: "franchise-wiki", method: ["public-reference", "manual"], status: "manual-reference", homepage: "https://www.fandom.com/", notes: "A source family, not a single database. Each individual wiki has its own identity, API configuration, access terms and attribution; select a specific wiki before automation." },

  { id: "myanimelist", name: "MyAnimeList", category: "anime-manga", method: ["api", "public-reference"], status: "credential-required", homepage: "https://myanimelist.net/", notes: "Use the official API only with an approved application and current terms. Keep MAL identifiers separate from AniList IDs." },
  { id: "anime-planet", name: "Anime-Planet", category: "anime-manga", method: ["public-reference"], status: "needs-review", homepage: "https://www.anime-planet.com/", notes: "No unrestricted API is assumed. Verify permission before any automated page extraction." },
  { id: "mangaupdates", name: "MangaUpdates", category: "anime-manga", method: ["public-reference"], status: "needs-review", homepage: "https://www.mangaupdates.com/", notes: "Specialist manga metadata. Verify current API/export, site terms before automation." },
  { id: "novel-updates", name: "Novel Updates", category: "anime-manga", method: ["public-reference"], status: "needs-review", homepage: "https://www.novelupdates.com/", notes: "Community-maintained webnovel catalogue; metadata-only discovery is always included and uses a targeted Botasaurus retry for detected Cloudflare challenges. The source-review status is separate from the runtime allowlist. Mature/adult-labelled entries are filtered; synopsis, reviews, artwork and chapter bodies are not extracted." },
  { id: "novelfire", name: "NovelFire", category: "books-comics", method: ["public-reference"], status: "terms-review", homepage: "https://novelfire.net/", notes: "A read-only metadata parser exists, but automated access remains disabled unless the deployment operator confirms current site terms and adds this ID to MEDIA_SOURCE_SCRAPE_ALLOWLIST. Do not fetch or redistribute chapter content." },
  { id: "novel-archive", name: "Novel Archive", category: "books-comics", method: ["public-reference"], status: "terms-review", homepage: "https://novelarchive.cc/", notes: "A read-only metadata parser exists, but automated access remains disabled unless the deployment operator confirms current site terms and adds this ID to MEDIA_SOURCE_SCRAPE_ALLOWLIST. Do not fetch or redistribute chapter content." },
  { id: "wuxia-click", name: "Wuxia Click", category: "books-comics", method: ["public-reference"], status: "terms-review", homepage: "https://wuxia.click/", notes: "A read-only metadata parser exists, but automated access remains disabled unless the deployment operator confirms current site terms and adds this ID to MEDIA_SOURCE_SCRAPE_ALLOWLIST. Do not fetch or redistribute chapter content." },
  { id: "noveli-to", name: "Noveli.to", category: "books-comics", method: ["public-reference"], status: "terms-review", homepage: "https://noveli.to/", notes: "A read-only metadata parser exists, but automated access remains disabled unless the deployment operator confirms current site terms and adds this ID to MEDIA_SOURCE_SCRAPE_ALLOWLIST. Do not fetch or redistribute chapter content." },
  { id: "mangadex", name: "MangaDex", category: "anime-manga", method: ["api"], status: "implemented", homepage: "https://mangadex.org/", notes: "Use the existing documented API client for metadata only. Do not download or redistribute chapter content." },
  { id: "anilist", name: "AniList", category: "anime-manga", method: ["api"], status: "implemented", homepage: "https://anilist.co/", notes: "Reuse the existing GraphQL client and stable AniList IDs." },
  { id: "anidb", name: "AniDB", category: "anime-manga", method: ["api", "public-reference"], status: "needs-review", homepage: "https://anidb.net/", notes: "Evaluate official API access and request conditions before implementing an adapter." },
  { id: "jikan", name: "Jikan", category: "anime-manga", method: ["api", "dataset"], status: "retired", homepage: "https://github.com/jikan-me/jikan-rest", notes: "The hosted public REST API was discontinued on 2026-10-01. Only consider a separately maintained/self-hosted deployment or dataset." },
  { id: "kitsu", name: "Kitsu", category: "anime-manga", method: ["api"], status: "implemented", homepage: "https://kitsu.app/", notes: "Reuse the existing catalogue API client; keep it distinct from unrelated Kitsu products." },
  { id: "shikimori", name: "Shikimori", category: "anime-manga", method: ["api"], status: "implemented", homepage: "https://shikimori.one/", notes: "Use the bounded read-only search adapter; only records with G, PG or PG-13 audience ratings enter member-facing results." },
  { id: "anime-news-network-encyclopedia", name: "Anime News Network Encyclopedia", category: "anime-manga", method: ["api", "public-reference"], status: "needs-review", homepage: "https://www.animenewsnetwork.com/encyclopedia/", notes: "Evaluate its documented encyclopedia API and usage conditions; preserve ANN entity links and attribution." },

  { id: "tmdb", name: "TMDB", category: "screen", method: ["api"], status: "implemented", homepage: "https://www.themoviedb.org/", notes: "Reuse the existing v3 client and follow TMDB API terms, branding and attribution requirements." },
  { id: "thetvdb", name: "TheTVDB", category: "screen", method: ["licensed-api"], status: "licensed-access", homepage: "https://thetvdb.com/", notes: "API key and current data licence/plan are required. Do not enable until deployment eligibility and attribution are configured." },
  { id: "tvmaze", name: "TVmaze", category: "screen", method: ["api"], status: "license-review", homepage: "https://www.tvmaze.com/api", notes: "Public API data is CC BY-SA. Attribution and ShareAlike obligations must be reviewed before combining or redistributing it." },
  { id: "trakt", name: "Trakt", category: "screen", method: ["api"], status: "credential-required", homepage: "https://trakt.tv/", notes: "Use documented API access and approved OAuth/client credentials. User-specific data requires authorized user consent." },
  { id: "imdb", name: "IMDb", category: "screen", method: ["dataset", "licensed-api"], status: "license-review", homepage: "https://www.imdb.com/", notes: "Prefer official datasets or licensed products. Do not assume a general free commercial metadata API or scrape the site." },

  { id: "goodreads", name: "Goodreads", category: "books-comics", method: ["public-reference"], status: "needs-review", homepage: "https://www.goodreads.com/", notes: "Verify current developer/API access and reuse rules. Use approved exports or citation-only links when no authorized API is available." },
  { id: "storygraph", name: "StoryGraph", category: "books-comics", method: ["public-reference"], status: "needs-review", homepage: "https://thestorygraph.com/", notes: "Verify documented API/export access and terms. Do not collect private account activity." },
  { id: "hardcover", name: "Hardcover", category: "books-comics", method: ["api"], status: "credential-required", homepage: "https://hardcover.app/", notes: "Use its documented API only with an authorized token and current access terms." },
  { id: "comic-vine", name: "Comic Vine", category: "books-comics", method: ["api"], status: "restricted-noncommercial", homepage: "https://comicvine.gamespot.com/api/", notes: "Its documented API states non-commercial use only. Do not enable in a commercial deployment without written permission." },
  { id: "publisher-websites", name: "Publisher Websites", category: "books-comics", method: ["feed", "public-reference", "manual"], status: "manual-reference", homepage: null, notes: "Primary sources. Prefer official APIs/feeds and permitted public metadata extraction; retain edition identifiers and canonical links." },
  { id: "google-books", name: "Google Books", category: "books-comics", method: ["api"], status: "implemented", homepage: "https://books.google.com/", notes: "Reuse the existing Google Books API client and preserve volume IDs, ISBNs and date precision." },
  { id: "open-library", name: "Open Library", category: "books-comics", method: ["api", "dataset"], status: "implemented", homepage: "https://openlibrary.org/", notes: "Reuse its API/datasets with caching, an identifying User-Agent and low request rates. Not a high-volume commercial catalogue feed." },
  { id: "bookbrainz", name: "BookBrainz", category: "books-comics", method: ["api", "dataset"], status: "implemented", homepage: "https://bookbrainz.org/", notes: "Use the documented /1/search API for work, edition and publisher records; the service is still evolving, so keep failures non-fatal and preserve BBIDs and source links." },
  { id: "isfdb", name: "ISFDB", category: "books-comics", method: ["dataset", "public-reference"], status: "needs-review", homepage: "https://www.isfdb.org/", notes: "Specialist bibliography. Check available access/dump options and licensing before automated use." },
  { id: "worldcat", name: "WorldCat", category: "books-comics", method: ["licensed-api"], status: "licensed-access", homepage: "https://www.worldcat.org/", notes: "OCLC access is subscription/licensing dependent. WorldCat Search API 1.0 support ended 2024-12-31; confirm current products before integration." },

  { id: "wikidata", name: "Wikidata", category: "knowledge", method: ["api", "dataset"], status: "implemented", homepage: "https://www.wikidata.org/", notes: "Use Wikibase search and the current WDQS v2 endpoint. Keep queries bounded, cache results and preserve property IDs." },

  { id: "tv-tropes", name: "TV Tropes", category: "community", method: ["public-reference"], status: "needs-review", homepage: "https://tvtropes.org/", notes: "Narrative context and discovery only. Do not treat tropes as canon, chronology or factual production metadata." },
  { id: "reddit", name: "Reddit", category: "community", method: ["api", "public-reference"], status: "credential-required", homepage: "https://www.reddit.com/", notes: "Use approved API/access methods and current platform terms. Community posts are evidence leads, not verified facts." },

  { id: "musicbrainz", name: "MusicBrainz", category: "music", method: ["api"], status: "implemented", homepage: "https://musicbrainz.org/", notes: "Reuse the shared REST client, identify Lemegeton with a meaningful User-Agent and keep the global queue at no more than one request per second." },
  { id: "last-fm", name: "Last.fm", category: "music", method: ["api"], status: "credential-required", homepage: "https://www.last.fm/api", notes: "Existing charts require an API key. Verify current terms and attribute global charts as provider data, not guild listening activity." },
  { id: "setlist-fm", name: "setlist.fm", category: "music", method: ["api"], status: "credential-required", homepage: "https://www.setlist.fm/", notes: "Existing read-side integration requires an API key. Preserve setlist.fm source links and review attribution and data-use terms." },
  { id: "spotify", name: "Spotify Web API", category: "music", method: ["api"], status: "credential-required", homepage: "https://developer.spotify.com/documentation/web-api", notes: "Existing identity matching depends on credentials. Recheck the 2026 development-mode user eligibility and endpoint restrictions before adding new features." },
  { id: "youtube-data-api", name: "YouTube Data API", category: "music", method: ["api"], status: "credential-required", homepage: "https://developers.google.com/youtube/v3", notes: "API key and quota required. Prefer channel uploads playlist reads over repeated searches; never download or redistribute video/audio." },
  { id: "soundcloud", name: "SoundCloud", category: "music", method: ["api", "feed"], status: "credential-required", homepage: "https://developers.soundcloud.com/docs/api/guide", notes: "Use documented API/RSS access only. Respect current app eligibility, token rules, endpoint limits and 429 responses." },
] as const satisfies readonly MediaSourceDefinition[];

export const MEDIA_SOURCE_REGISTRY_REVIEWED_AT = reviewedAt;

export function getMediaSource(id: string): MediaSourceDefinition | null {
  const normalized = id.trim().toLowerCase();
  return MEDIA_SOURCES.find(source => source.id === normalized) ?? null;
}

export function searchMediaSources(query: string): MediaSourceDefinition[] {
  const normalized = query.normalize("NFKC").trim().toLocaleLowerCase("en-US");
  if (!normalized) return [...MEDIA_SOURCES];
  return MEDIA_SOURCES.filter(source =>
    source.name.toLocaleLowerCase("en-US").includes(normalized)
    || source.id.includes(normalized)
    || source.notes.toLocaleLowerCase("en-US").includes(normalized),
  );
}

export function listMediaSourcesByStatus(status: MediaSourceStatus): MediaSourceDefinition[] {
  return MEDIA_SOURCES.filter(source => source.status === status);
}

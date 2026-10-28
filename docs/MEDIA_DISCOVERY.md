# Media Discovery, Franchises, and Community Events

This guide documents the provider-backed media discovery features. Providers remain authoritative for their own metadata; the bot does not infer release dates, adaptation arcs, ratings, or chapter-to-episode mappings that the source does not supply.

## Browse filters

Use **/browse** with a media category and a title for a detailed record. For TMDB movie/TV discovery, leave the title blank to receive a filtered list instead.

| Category | Supported filters |
| --- | --- |
| Anime and manga | Genre, AniList theme/tag, provider status, year range. Manga supports manga (Japan), manhwa (Korea), manhua (China), and provider-tagged webtoon subtypes using AniList origin/format metadata. Author and artist filters are available for manga/light-novel records when AniList staff roles expose the credit. Adult-flagged titles are excluded unless the user explicitly opts in from a Discord channel marked NSFW. |
| General novels and books | Genre/subject, author, publisher, language code, publication year range through Google Books query parameters. |
| Webnovels | Genre, author and status when supplied by live Novel Updates or Novel Phoenix results. |
| Movies and TV | TMDB genre, keyword/theme, original language code, status, release year range, runtime, director and cast filters. |

A filter that the selected metadata provider cannot support is rejected instead of silently returning unfiltered results. Browse applies filters to the provider's best matching title; when the title fails one of the filters, try a broader title or fewer filters.

AniList themes are rendered separately from genres. AniList spoiler-marked tags are called out; tags are not automatically treated as a complete content-warning system. NSFW access follows Discord's channel flag. Provider metadata can be incomplete, so these fields should not replace the original provider page.

## Franchise exploration

**/franchise** supports AniList anime/manga relationships, Google Books entries, and TMDB movie/TV entries.

- AniList relationship types are retained as provider metadata.
- TMDB movie collection members are labelled as collection members. When every collection member has a full release date, the bot shows a **release-order** list; it does not present that as in-universe chronology.
- AniList relations retain prequel, sequel, side-story, spin-off and other provider relation labels. An AniList release-order list is shown only when every linked entry and the current title have full start dates; no story chronology is inferred.
- TMDB movie/TV recommendations are labelled as recommendations, not confirmed sequels, prequels, adaptations, or a shared universe.
- Exact title matches on a second provider are listed as **unverified title matches**. Matching names alone do not prove an adaptation relationship.
- Google Books does not supply a dependable cross-media adaptation graph. In that case the result links to the book's metadata record rather than fabricating relationships.

No chapter-to-episode or volume-to-season mapping is guessed. Release-order and chronological-order guides should only be shown once a provider exposes those distinct orders.

## Cross-media similarity

**/similar** resolves a title through AniList, Novel Updates, Google Books or TMDB, then searches anime, manga, light novels, webnovels, general books, movies and television for candidates with overlapping provider-reported genres.

The result has separate sections for:
- **Provider-generated recommendations**, where AniList or TMDB supplies them.
- **Local genre-overlap matches**, ranked using a transparent set intersection and accompanied by the shared genre names.

The local ranking is a heuristic, not an AI-generated recommendation score. Providers with missing genre metadata may not yield local matches.

## TV season and episode guide

**/tv-guide title** displays TMDB's series summary, reported season list, creators, cast, runtime, status, US content rating when supplied, and next-episode information when available.

**/tv-guide title season:<number>** retrieves the selected season's episode records. Episode air dates and runtimes are shown only when TMDB supplies them, and episode synopsis text is spoiler-marked by default. The command links to TMDB as its source; it does not invent streaming availability.

## Release calendar

Run **/release-calendar** to open one interactive menu for the seven-day preview and this server's digest settings. Use **Preview next 7 days** to inspect provider-backed dates, **Configure digests** to open a modal for channel, frequency, categories, and region, or **Disable digests** to stop delivery for the current server. Configuration and disable actions require Manage Server permission.

Currently supported sources are AniList airing schedules for anime, TMDB upcoming movie dates (using the configured region), and TMDB TV next-episode dates. The feed has a short in-memory cache and bounded request timeouts, and each entry names its source. Adult-flagged anime is excluded. The calendar does not claim to contain manga chapter or novel volume announcements because the configured providers do not expose a dependable, unified release schedule for those categories.

## Reading Hub

Reading Club data is stored per guild. **/reading** is the single entry point for nominations, voting, selecting the next community read, scheduling a spoiler-aware discussion, and exploring reading order.

1. **Nominate a title** opens a modal for the work title and optional HTTPS publisher/metadata link. Supported nomination categories are manga, manhwa, manhua, webtoon, light novels, webnovels, and general books.
2. **View nominations** lists this guild's open nominations and vote totals. **Vote** records or changes the member's active vote in this guild.
3. A moderator can use **Select the next read** to choose the highest-voted open nomination automatically, or supply a nomination ID to override the vote. Remaining open nominations are closed.
4. **Schedule a discussion** creates a public thread for the selected read at a future ISO-8601 time that includes a timezone offset. The bot posts a reminder at the scheduled time.
5. **Explore reading order** uses the existing provider relationship resolver. It displays supported relationships without guessing chapter-to-episode mappings or equating release order with story chronology.

Discussion threads explicitly ask users to mark plot spoilers with Discord's spoiler syntax (||spoiler||). This feature coordinates shared community events only; it does not store personal reading progress.

## Media Night

**/media-night start** supports anime, manga, movies and TV, with optional genre, mood, year range, runtime and content-suitability filters. TMDB discovery requires TMDB_BEARER_TOKEN; AniList powers anime/manga candidate pools. A vote is stored per guild/channel and can be changed while it is open.

The family-friendly option is a best-effort metadata filter, not a parental-rating guarantee. Provider adult flags are excluded from the candidate pool. If too few titles meet the requested filters, no under-filled vote is created.

## Comparison

**/compare** compares two to four selected entries side by side, including mixed categories such as a webnovel, anime, film, and TV series in the same comparison. Choose a default category and use the per-title category overrides when needed. Ratings retain their provider/scale labels; fields differ by category rather than assuming that every media type has the same attributes.

## Configuration and operational notes

- Configure TMDB_BEARER_TOKEN for movie/TV search, franchise lookups, TV guides and TMDB-backed release-calendar categories.
- Google Books and AniList use the existing helpers already used elsewhere in the bot.
- Release-calendar settings, Reading Club nominations/votes, and Media Night sessions are persisted in the shared database and keyed by guild/channel as appropriate.
- Provider failures, unavailable metadata and missing release dates are treated as missing data. The bot does not make a failed source appear operational or manufacture metadata to fill gaps.

## Image asset storage

The bot uses a shared S3-compatible asset store and PostgreSQL `media_assets` registry. Configure `S3_BUCKET`, `S3_REGION`, and credentials; `S3_ENDPOINT_URL` is optional for AWS S3 and can point to R2, MinIO, or another S3-compatible endpoint. Keep this primary bucket private. Private images use short-lived signed URLs.

New Panels uploads use this store when configured, and `panels.media_asset_id` references their registry entries. Existing Discord-hosted panels continue to work without a bulk migration; when object storage is not configured, Panels retains its existing Discord-channel fallback. Newly uploaded Custom Role original images also use private object storage when configured and fall back to PostgreSQL otherwise. Existing records are retained; historical images are not automatically re-uploaded.

The `/3x3` generator and AniList staff-character collage can optionally publish their generated, non-sensitive composite images to a **separate** public bucket. Enable this only by setting both `S3_PUBLIC_BUCKET` and an HTTPS `S3_PUBLIC_BASE_URL` (usually a CDN URL). Never use that public bucket for custom-role source images, private uploads, or feedback attachments. Apply a lifecycle policy to generated-image prefixes to control retention. If public output storage is not configured, these commands continue sending Discord attachments.

## Shared cross-system relationship graph

Lemegeton uses a shared PostgreSQL relationship graph to connect the systems it already has instead of maintaining independent, command-only relationship lists.

- /franchise indexes relationships explicitly declared by AniList and TMDB collection membership. It then reads saved graph neighbors, approved links for the current server, safe title-linked Panels, approved public archive entries, and matching discussions or events from the current server.
- /similar stores provider recommendations and transparent genre-overlap recommendations as recommendation edges. It displays saved graph links separately from current provider results and from human-written entries in the approved recommendation board.
- /link-review adds an edge to the community graph only after a moderator approves a suggestion. Community edges remain scoped to the approving guild; global provider edges and recommendation edges are stored separately. The /link-suggest category list includes video games, and /game reads approved cross-media edges and matched community resources alongside its existing IGDB/Steam metadata.
- Approved archive entries and non-NSFW panel metadata are joined to a title when a conservative title or provider ID match is available. Reading Club nominations and active Media Night votes are also linked by exact title matches, with every nomination/session lookup restricted to the invoking guild. The graph does not copy or replace data from the existing archives.
- Discussions, adaptation polls, quizzes, and brackets are resolved only inside the invoking guild. A result from one guild cannot expose another guild's private event links.
- Missing optional archive tables do not take down the discovery command. Existing provider metadata remains the source of truth, and exact-title matches or recommendations are never promoted to confirmed adaptations.
- The graph schema is created idempotently through the existing PostgreSQL access layer. It uses indexes and a uniqueness constraint to avoid repeatedly adding the same relationship.

The graph is intentionally an integration layer, not a promise that every provider exposes every category or relation. AniList, TMDB, Google Books, Novel Updates, Novel Phoenix, Steam/IGDB, and community archives keep their own authoritative metadata and limitations.

## Connected media commands and community archives

The interactive /discovery-hub command is the entry point for media navigation and community features. /connections reuses the existing /franchise resolver and provider-specific relationship handling. The /reading command's reading-order action presents source-attributed relationships with an explicit warning that release order is not story chronology. Exact-title matches and recommendations remain unverified unless a provider declares a relationship.

### TMDB tools

- /browse supports title-free TMDB discovery with genre, theme/keyword, language, TV status, year range, runtime, director/cast, minimum rating, and sorting filters. Movie queries reuse the calling guild's /media-region setting; TV queries use TMDB's first-air date fields. Discovery results are bounded to the first results page and retain TMDB as their source.
- /where-to-watch reads the documented movie or TV watch-provider endpoint using the selected two-letter region. /media-region stores the server's default region in PostgreSQL; an individual query can override it.
- /person-credits uses TMDB person search and combined credits to display movie and TV work.
- /trailers uses the documented movie/TV videos endpoints and constructs links only for returned YouTube or Vimeo keys. Provider-returned video types and official flags are retained.
- /collection-guide resolves a movie, loads its belongs_to_collection reference, then displays TMDB collection parts by release date. This is not an assertion of in-universe chronology.
- /author-works queries Google Books by author. Results may include co-authored works and editions; this is not presented as a universal cross-provider bibliography.
- `/webnovel-updates` and `/browse` query live public search pages from Novel Updates and Novel Phoenix. Each provider is isolated so one provider failure does not discard results returned by the other.
- The scraper returns title links and available public metadata only; it does not fetch chapter text. Results explicitly marked Adult, Mature, Smut, Ecchi, Hentai, Erotica, NSFW, 18+, or explicit are filtered out.
- Provider markup and availability can change. A scraper timeout, access challenge, or unsupported layout is treated as a provider failure rather than proof that a title does not exist.


TMDB watch-provider data is powered by JustWatch. /where-to-watch labels the queried region and links to the provider-details URL when supplied; it does not manufacture direct streaming links. TMDB requests require TMDB_BEARER_TOKEN. Availability changes and should be verified with the provider.

/release-calendar's Configure digests modal accepts a two-letter region code for movie-release queries. Existing installations gain a release_region field using a non-destructive ALTER TABLE ADD COLUMN IF NOT EXISTS operation. The existing default remains US for compatibility. Anime airings still come from AniList and TV next-episode records from TMDB.

### Link suggestions and discussions

/link-suggest opens a guided menu for source category, target category, and relationship type, then opens a modal for both work titles, HTTPS metadata URLs, and evidence. The saved suggestion is scoped to the current guild. /link-review remains moderator-gated and supports listing, inspecting, approving, and rejecting pending suggestions. Approval is labelled community-verified, not provider-confirmed.

/discussion is the single command for spoiler-aware chapter, volume, episode, season, or general discussion threads. Choose the scope in the interactive menu and then submit the work title, explicit spoiler cutoff, and optional metadata URL through a modal. It posts a starter message and stores the discussion thread against the current guild; it does not infer cross-medium chapter/episode mappings.

### Community archives and events

The interactive **/archive** command unifies the community contribution archives in a Panels-inspired, card-based browser. Select an archive type and action, then use its buttons or modal form.

- **/archive** — browse, search, contribute, or randomly discover quotes, credited fanworks, moodboards, soundtracks, scenes, human-written recommendations, and spoiler-marked theories. The same menu provides personal submission history, entry reporting, submission review, and report moderation.
- **/panels** — the dedicated manga-panel archive with its existing image, search, filtering, and moderation interface.
- **/panel-of-the-day** — selects a non-NSFW record from the existing Panels table and persists one selection per server per date instead of maintaining a second panel database.
- **/media-bracket**, **/adaptation-vote**, and **/media-quiz** — persist server-scoped votes, polls, trivia questions, and user quiz sessions.

New community archive submissions start pending. Approval takes place in the originating guild; approved entries are shared across servers. Moderation and votes remain guild-scoped. Fanworks and soundtrack submissions require HTTPS links, and user-supplied links are not treated as proof of a media relationship. Quotes are limited to 280 characters; do not submit lyrics or long copyrighted passages. Archive entries link to external work and metadata rather than rehosting fan media or music.

### Database changes

New tables are initialized by their cogs and use the existing PostgreSQL access layer. They include connected_media_guild_settings, media_link_suggestions, connected_media_discussions, community_archive_entries, community_archive_reports, community_panel_daily_log, community_media_brackets, community_media_bracket_votes, community_adaptation_polls, community_adaptation_votes, community_media_quiz_questions and community_media_quiz_sessions. Existing archive tables and records are not copied or replaced.

These community features do not store personal reading or watching progress. Provider fields that are unavailable remain unavailable instead of being guessed.

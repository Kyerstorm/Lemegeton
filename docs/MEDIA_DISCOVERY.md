# Media Discovery, Franchises, and Community Events

This guide documents the provider-backed media discovery features. Providers remain authoritative for their own metadata; the bot does not infer release dates, adaptation arcs, ratings, or chapter-to-episode mappings that the source does not supply.

## Browse filters

Use **/browse** with a media category and a title, then fill the optional filters that apply to that category.

| Category | Supported filters |
| --- | --- |
| Anime and manga | Genre, AniList theme/tag, provider status, year range. Manga supports manga (Japan), manhwa (Korea), manhua (China), and provider-tagged webtoon subtypes using AniList origin/format metadata. Author and artist filters are available for manga/light-novel records when AniList staff roles expose the credit. Adult-flagged titles are excluded unless the user explicitly opts in from a Discord channel marked NSFW. |
| General novels and books | Genre/subject, author, publisher, language code, publication year range through Google Books query parameters. |
| Webnovels | Genre, author and status when those values can be parsed from Novel Updates results. |
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

**/similar** resolves a title through AniList, Google Books or TMDB, then searches anime, manga, books, movies and television for candidates with overlapping provider-reported genres.

The result has separate sections for:
- **Provider-generated recommendations**, where AniList or TMDB supplies them.
- **Local genre-overlap matches**, ranked using a transparent set intersection and accompanied by the shared genre names.

The local ranking is a heuristic, not an AI-generated recommendation score. Providers with missing genre metadata may not yield local matches.

## TV season and episode guide

**/tv-guide title** displays TMDB's series summary, reported season list, creators, cast, runtime, status, US content rating when supplied, and next-episode information when available.

**/tv-guide title season:<number>** retrieves the selected season's episode records. Episode air dates and runtimes are shown only when TMDB supplies them, and episode synopsis text is spoiler-marked by default. The command links to TMDB as its source; it does not invent streaming availability.

## Release calendar

The release calendar is configured separately by each Discord server.

- **/release-calendar preview** previews the next seven days.
- **/release-calendar preview categories:anime,movies** limits a preview to named categories.
- **/release-calendar configure channel frequency categories** configures a daily or weekly digest for that guild.
- **/release-calendar disable** disables that guild's digest.

Currently supported sources are AniList airing schedules for anime, TMDB upcoming movie dates (US region) and TMDB TV next-episode dates. The feed has a short in-memory cache and bounded request timeouts, and each entry names its source. Adult-flagged anime is excluded. The calendar does not claim to contain manga chapter or novel volume announcements because the configured providers do not expose a dependable, unified release schedule for those categories.

## Reading Club

Reading Club data is stored per guild.

1. **/reading-club nominate** records a title, category and optional HTTPS metadata/publisher link.
2. **/reading-club list** lists the guild's open nominations and vote totals.
3. **/reading-club vote** records or changes the member's active vote for that guild.
4. A moderator uses **/reading-club select** to select a nomination and close the other open nominations.
5. **/reading-club schedule** creates a public discussion thread at a moderator-specified ISO-8601 time that must include a timezone offset. The bot posts a reminder at the scheduled time.

Discussion threads explicitly ask users to mark plot spoilers with Discord's spoiler syntax (||spoiler||). This feature coordinates shared community events only; it does not store personal reading progress.

## Media Night

**/media-night start** supports anime, manga, movies and TV, with optional genre, mood, year range, runtime and content-suitability filters. TMDB discovery requires TMDB_BEARER_TOKEN; AniList powers anime/manga candidate pools. A vote is stored per guild/channel and can be changed while it is open.

The family-friendly option is a best-effort metadata filter, not a parental-rating guarantee. Provider adult flags are excluded from the candidate pool. If too few titles meet the requested filters, no under-filled vote is created.

## Comparison

**/compare** compares two to four selected entries from the same category, now including Novel Updates webnovels as well as the existing AniList, Google Books, TMDB and game providers. Ratings keep their provider/scale labels; fields differ according to the category rather than assuming that every media type has the same attributes.

## Configuration and operational notes

- Configure TMDB_BEARER_TOKEN for movie/TV search, franchise lookups, TV guides and TMDB-backed release-calendar categories.
- Google Books and AniList use the existing helpers already used elsewhere in the bot.
- Release-calendar settings, Reading Club nominations/votes, and Media Night sessions are persisted in the shared database and keyed by guild/channel as appropriate.
- Provider failures, unavailable metadata and missing release dates are treated as missing data. The bot does not make a failed source appear operational or manufacture metadata to fill gaps.

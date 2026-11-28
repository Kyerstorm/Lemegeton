# Command Expansions

Research and implementation review: 27 November 2026  
Target: `lemegeton-v3` only  
Status: implementation tracker and roadmap. Existing v3 behavior is documented separately from unfinished phases; a listed provider or requirement is not evidence that an integration is enabled or complete.

## Product direction

Lemegeton should grow through substantial, distinct systems rather than a large collection of small utility commands. Each system should provide a reason to use Lemegeton repeatedly: explore connected information, collaborate with other members, solve something together, preserve a community contribution, or manage a meaningful server process.

Keep the command model already used by v3:

- One top-level slash command for each system: `/timeline`, `/industry`, `/identify`, `/expedition`, `/casebook`, `/relay`, `/capsule`, `/council`, `/workshop` and `/exchange`.
- No slash-command subcommand groups. A command opens its own home panel and uses Discord buttons, selects, modals, paginated embeds and, where useful, threads for the workflows inside it.
- Do not turn every button into another public slash command. Keep the public command inventory understandable.
- A command should have a complete purpose and data model. It should not be a thin alias for another command or simply expose an external API response.
- Use Discord as the interaction surface. These are bot systems, not proposals for another web application.
- Keep the existing standalone `/help`, `/privacy` and `/feedback` commands separate.

### v3 architecture is authoritative

The v3 runtime is TypeScript on Node.js 22.9+ with discord.js. Use the shared libSQL database under `src/utility/database/libsql/` and the private RocksDB object store under `src/utility/database/rocksdb/`. Do not copy the old Python branch's PostgreSQL assumptions into this plan, add a second database, or revive the previous PostgreSQL wording from older drafts.

Relevant current boundaries:

- `src/commands/`: user-facing feature command modules.
- `src/registry.ts` and `src/deploy-commands.ts`: command registration and deployment.
- `helpers/integration/`: provider-specific API clients and response parsing.
- `helpers/runtime/` and the other existing helpers: shared application services, permissions, caching, embeds, diagnostics and media logic.
- `src/utility/database/libsql/`: persistent records and relational metadata.
- `src/utility/database/rocksdb/`: private binary/object storage where an actual attachment must be retained.
- `web/backend/` and `web/frontend/`: existing optional dashboard boundary. Do not make a dashboard necessary for these Discord commands to work.

The current v3 guidance names seven dashboard-configurable feature commands plus the protected settings command. Adding these ten systems will therefore require a deliberate update to the command registry, command-access metadata and dashboard command inventory when implementation begins. Do not assume that creating a command class automatically makes it deployable or configurable.

### Existing command responsibilities to preserve

| Existing system | Its responsibility | Do not duplicate it with |
|:--|:--|:--|
| Discover | Provider-backed media search, details and recommendations | Another media search wrapper |
| Archive | Server/global media archives, collections, trails and moderation | A second general archive |
| Community | Sessions, rankings, daily activity and release/community workflows | A second generic event or session engine |
| Play | Existing quick interactive games | A second collection of small minigames |
| Music | Music discovery, charts, concert setlists and guild release trackers | A listening-history or playback system |
| Profile | Provider connections, profile visibility and shared-interest features | Personal viewing/reading/playtime tracking |
| Settings | Server configuration and automation settings | Duplicate server configuration panels |
| Custom Roles | Custom role tooling | Another role picker |

### Shared engineering contract for all ten systems

1. **Guild isolation:** guild-created records, participation, content, settings and moderation actions must carry the correct `guild_id` end-to-end. Use a guild-scoped cache key for guild-owned state. A record created in one server must never appear in another server by accident.
2. **Intentional global data:** provider-sourced media facts can be cached globally when they are genuinely public and provider-owned. Keep the provider ID, source URL, retrieval time and attribution. Do not make guild annotations or private uploads global merely because the referenced media is global.
3. **Permissions:** use the project's shared permission helpers and command-access system. Recheck the actor, guild, role/permission and record ownership on every button, select and modal action. A hidden or disabled component is not an authorization boundary.
4. **Persistence:** Discord messages and in-memory maps are presentation/session state, not the source of truth. Persist anything that must survive a restart: cases, project state, submissions, ballots, event progress, revisions and scheduled releases.
5. **Attachments:** use the existing bounded attachment and RocksDB infrastructure where appropriate. Store object metadata and authorization in libSQL. Apply upload size/type limits and retention rules. Do not introduce S3 or a second object store.
6. **Interactions:** acknowledge long-running interactions promptly, defer where necessary, and edit/follow up through the correct interaction state. Paginate large results and respect Discord embed/component limits. Every expired, deleted or unauthorized workflow needs a clear response.
7. **Moderation:** provide report, hide, reject, restore or close paths appropriate to the system. Keep audit history for consequential moderator actions without logging secrets or unnecessary private content.
8. **Provider integrity:** do not invent facts, dates, credits, relationships or ratings. Distinguish provider-confirmed facts from community submissions, suggestions and unresolved claims.
9. **Retention:** follow the v3 guild retention gate and delete/retain semantics. A new system must not silently bypass member deletion, guild leave policy or user-requested deletion.
10. **Testing:** test the normal workflow, invalid input, unauthorized component actions, expiry/restart behavior, provider failure, and at least two guilds with different data. Add tests for the relevant state transitions, not only command registration.
11. **No speculative dependencies:** reuse existing clients and helpers first. Add a provider or package only after documenting the missing capability, terms, rate limits, credentials and fallback behavior.
12. **No personal progress tracking:** these systems must not add personal watching, reading, playtime or listening ledgers.

---

# New command systems

## 1. `/timeline` — Cross-Media Chronology

**Purpose:** a persistent, source-backed chronology of real-world media events. Members should be able to understand when a work was first published, when an adaptation was released, how a franchise developed, and how different releases relate to one another.

This is not a personal watch calendar, notification scheduler or simple list of upcoming releases. Its core value is connecting verified events across media types into one navigable history.

### Main experience

The command opens a Timeline home panel. Members can search for a title, franchise, creator, studio or company; choose a media category; or open a known chronology. Search results should resolve through existing media integrations wherever possible, then present a paginated event sequence.

A selected chronology should support:

- **Franchise view:** events grouped under a verified franchise or related-work identity.
- **Work view:** publication and release events for one specific work.
- **Adaptation view:** original work, adaptation announcement (only when sourced), adaptation release and later related releases.
- **Creator or studio view:** a dated catalogue of verified works and milestones.
- **Compare view:** compare two release orders without claiming that one is universally correct.
- **Source view:** inspect the provider and source record behind a date or relationship.

Each event should show its date precision, region/platform when relevant, event type and source. A year-only date must remain year-only; never convert it into an invented month or day.

### Event types

- First publication or first public release.
- Regional release or edition publication.
- Episode, season, film or game release.
- Platform/format release, port or remaster where confirmed.
- Music release, album, EP or single release.
- Book edition, translation or reprint.
- Adaptation or related-work release.
- Organization founding, rename or documented company change when viewed from an organization timeline.

Support several distinct sequence types as separate views over the same source-backed event records:

- **In-universe chronology:** when events happen inside the fictional world, including dated and relative events.
- **Publication order:** when books, manga chapters/volumes, comics, games and other works were first published.
- **Release/broadcast order:** when episodes, seasons, films, games, editions and music releases became available, with region/platform where relevant.
- **Recommended first-time order:** an editorial or official viewing/reading sequence, explicitly labelled as a recommendation rather than objective canon.
- **Adaptation order:** how original works and adaptations were published/released, while retaining the relationship and continuity each adaptation belongs to.
- **Series/continuity order:** a sequence within a named continuity, universe, reboot, edition or adaptation. Never silently merge incompatible continuities.
- **Cross-media order:** interleave novels, comics, manga, episodes, films and games only when a source establishes the order and scope.

Do not force in-universe events into calendar dates when the source gives only relative order. Keep the source's precision (exact date, month, year, season, relative interval or ordinal sequence). An absent chronological entry means the source did not establish it; it does not prove that no such event or order exists.

A timeline should show which sequence is being viewed and allow members to compare sequences without blending them. Official guides and primary material should be clearly distinguished from provider catalogue data, maintained reference wikis, community-edited timelines and individual interpretations.

### Data and provider plan

Reuse providers that already exist in v3:

| Source | Useful timeline data | Boundaries |
|:--|:--|:--|
| AniList | Anime/manga start dates, airing information, studios and related-work edges | Use AniList IDs and verified relation types. Missing dates stay unknown. |
| TMDB | Movie release dates, regional release information, TV seasons and episode air dates | Preserve region and date type. Respect TMDB attribution and terms. |
| IGDB | Game release dates, platforms and company links | Keep platform-specific release records distinct. |
| Google Books | Volume metadata, publisher, identifiers and published date | Dates may be year-only; preserve the precision returned. |
| MusicBrainz | Release groups, releases, first-release dates, labels and relationships | Group release editions correctly; follow its one-request-per-second rule. |
| Wikidata Query Service | Cross-domain discovery and enrichment for historical facts or relationships | Supplementary only. Data quality varies; query limits and the ongoing service migration must be respected. |
| Open Library | Individual book/work/edition lookups and publication details | Human-requested lookup with caching; not a bulk or high-traffic backend. |

Do not add another copy of an existing integration. Extend the relevant provider helper only when the current client lacks a required field or query.

### Resolution and conflicting dates

A timeline event must retain its source facts rather than overwrite them with a single guessed date. Store the provider identity, external ID, source URL, source date value, date precision, region/platform, event type and retrieval timestamp. If two reputable providers disagree, show the conflict or select a documented preferred source for that event type; do not silently average dates.

Resolve media relationships using provider IDs and verified relation edges. Do not connect works solely because their titles look similar. Manual relationship corrections should be explicit, source-backed and auditable.

### Permissions and ownership

- Public provider facts and their cache can be shared across guilds.
- Guild-created annotations, custom chronology collections and moderation decisions remain guild-scoped.
- A member may suggest a correction, but a suggestion must not rewrite provider data automatically.
- Only authorized moderators/editors may approve community corrections or hide abusive submissions.

### Completion criteria

- Members can search and browse a chronology without a dashboard.
- Results paginate and retain provider attribution.
- Date precision and region/platform distinctions survive normalization.
- Conflicting or missing dates are represented honestly.
- No false adaptation or franchise links are generated from title similarity.
- Provider outages do not prevent cached or independent provider results from displaying.

### Current v3 implementation (2026-11-27)

- `/timeline` is registered and provides category search, paginated selections, sequence controls, provider links and a source-correction modal.
- Current Timeline search adapters are AniList (anime/manga/light novels), TMDB (film/TV), IGDB (games), Google Books and Open Library (books), and MusicBrainz (artists).
- Release/publication metadata is normalized without inventing missing month or day precision. Retrieved sequence events are saved through `helpers/media/timeline-store.ts`; correction requests are stored separately and remain reviewable.
- AniList related-work edges are shown for adaptation, continuity and in-universe views. **The in-universe view is still not a true event-by-event fictional-world chronology**: provider relationship edges do not establish an in-world date and are never presented as canon chronology.
- Timeline's Franchise Wiki search combines individually enabled MediaWiki sources, operator-allowlisted chronology references and Wikidata entity search. In Continuity mode, Wikidata P155/P156/P179 edges appear as undated relative work-order records, with a source link and an explicit warning that they do not establish an in-world date.
- Guild members can submit date corrections with HTTPS evidence. Manage Server moderators can inspect a guild-scoped review queue, approve/reject pending suggestions and see approved annotations on the relevant provider record. Approval does not overwrite the provider's original date.
- Cached provider-event fallback is used when live providers return no events or fail, and the embed labels cached data.

Remaining gaps: verified event-by-event fictional-world dates and relative scene/event records; source-specific MediaWiki/Cargo adapters for dated episode/chapter/game events; automated cross-provider franchise/continuity identity resolution; automatic conflict detection between provider dates; and broader source-attributed event coverage. The current correction queue is manual moderation, not an automatic conflict detector.

---

## 2. `/industry` — Media Industry Directory

**Purpose:** an interconnected directory of the organizations that create, publish, distribute and release media. It focuses on companies and their documented relationships, not individual creator biographies and not a generic web search.

A member should be able to open a studio or publisher, understand what it does, inspect its known works, and follow verified relationships to parent companies, subsidiaries, networks, labels or partner organizations.

### Organization categories

- Animation studios and production committees where provider data supports them.
- Game developers and game publishers.
- Film and television production companies.
- Television networks and distributors.
- Book, manga and light-novel publishers.
- Music labels and release organizations.
- Media distributors and documented parent organizations.

Do not create a category when providers do not supply meaningful records for it. It is better to return a smaller verified directory than a large collection of unsupported guesses.

### Main experience

The command opens a searchable Industry home panel:

1. Search for an organization or select a category.
2. Resolve possible matches and show country, aliases, official website and provider identifiers.
3. Open an organization profile.
4. Browse its works, roles and related organizations.
5. Open a work to continue into Discover or Timeline.
6. Inspect source records and the confidence/provenance of each relationship.

Organization profiles should include, when available:

- Canonical name and known aliases.
- Organization type and country.
- Founded/active dates, with date precision.
- Official website and provider profile links.
- Parent/subsidiary or successor relationships where explicitly supported.
- Works grouped by media category and relationship type.
- Recent and historical works.
- Source records, last retrieval time and known data gaps.

### Provider strategy

| Source | Useful records | Notes |
|:--|:--|:--|
| IGDB | Game companies, developer/publisher roles, developed/published games, parent company, company status and change IDs | Strong starting point because the v3 project already has IGDB integration. Preserve company IDs and distinguish developer from publisher. |
| TMDB | Film/TV production companies and television networks, with company-linked title catalogues | Reuse the current TMDB client. Follow its attribution requirements. |
| AniList | Animation studios and anime associated with each studio | Reuse AniList studio queries; do not infer ownership of a production from a studio credit. |
| MusicBrainz | Record labels and release relationships | Reuse the existing MusicBrainz client and global throttle. A label credit is not automatically proof of corporate ownership. |
| Wikidata | Parent organizations, mergers, historical names and cross-domain references | Enrichment and discovery only. Require a traceable source and review questionable relationships. |
| Google Books | Publisher names on book editions | Useful for edition metadata, but publisher-name strings need identity resolution before becoming company records. |

An organization may have multiple provider identities. Preserve each identity separately and link them only after a strong match based on official links, known identifiers or reviewed evidence. Do not merge two companies because their names are similar.

### Relationship model

Support explicit, typed relationships rather than a free-form graph:

- Parent company / subsidiary.
- Developer / publisher.
- Production company / production credit.
- Network / television title.
- Record label / release.
- Publisher / edition.
- Successor or renamed organization, when documented.

Every edge needs a source and relationship type. Avoid implying that an organization owns, controls or employs another organization unless the source explicitly states that relationship.

### Guild features

The provider directory is global and read-only. Guilds may create private curated lists, request an organization correction, or nominate an organization for moderator review. These guild-created records must remain guild-scoped and must not alter provider-owned facts.

### Completion criteria

- Search resolves organizations without name-only merging.
- Profiles distinguish developer, publisher, production company, network, label and publisher roles.
- Works are linked through stable provider IDs.
- Every displayed relationship has provenance.
- Unknown parent-company or ownership information remains unknown.
- The system works with existing provider credentials and clearly degrades when an optional provider is unavailable.

### Current v3 implementation (2026-11-27)

- `/industry` is registered and supports category search, organization profiles, source links and relationship browsing.
- Current categories are anime studios (AniList), game companies (IGDB), screen production companies and TV networks (TMDB), music labels (MusicBrainz), and Wikidata knowledge-graph records.
- The provider clients preserve provider identifiers and use typed relationship records where the source exposes them. Wikidata parent/subsidiary and related-organization edges are displayed as sourced knowledge-graph relationships, not proof of legal ownership beyond the source record.
- The `publisher` category searches source-backed Google Books publisher records and BookBrainz publisher identities. Same-name records remain distinct; provider identities are not merged automatically.
- Guild members can pin source-backed organizations to a server directory and remove pins with Manage Server permission.
- Guild-scoped correction suggestions and proposed cross-provider identity links have a Manage Server review queue. Self-review is blocked. Approved corrections and identity links appear on organization profiles with evidence URLs; approved identity links remain associations and do not rewrite or merge provider records.

Remaining gaps: global provider identity reconciliation; label search coverage beyond existing MusicBrainz records; organization founding/renaming/successor history timelines; reviewable primary-source evidence for parent/subsidiary changes; and verified ownership/merger event history.

---

## Source inventory and integration strategy

The following sources were explicitly requested as part of the research coverage for `/timeline` and `/industry`. Treat every unique entry below as a source target to evaluate and integrate through the best available permitted method. They are not all interchangeable, and not every source applies to every title or media category. The repeated entries in the original list (Comic Book Herald, MyAnimeList, Anime-Planet, MangaUpdates, Novel Updates and MangaDex) are listed once here.

**Important distinction:** "integrate" means the source must be considered and represented in the source registry. Depending on its capabilities and usage rights, an integration may use an API, licensed API, MediaWiki API, feed, public dataset, permitted public-page extraction, manual source verification or a citation/link-only fallback. Do not pretend a source has an API or scrape permission that it does not have. An unavailable or restricted source must remain recorded with its limitation rather than being silently dropped.

### A. Dedicated chronology, reading-order and franchise-sequence sources

| Source | Intended contribution | Source treatment |
|:--|:--|:--|
| The Canonicle | In-story anime/manga timelines, watch orders, cross-timeline comparisons and cited event ordering | Direct chronology reference. Preserve its distinction between in-story events and original release order. |
| ChronoCanon | User-identified chronology/reference source | Validate the canonical site, ownership, coverage and access method before building an adapter; do not guess its URL or API. |
| Chronelines | In-world chronology compared with release order across series, games, anime and films | Direct chronology reference. Preserve its separate order types and source explanations. |
| Chronologeek | User-identified chronology/reference source | Validate the canonical site, coverage and access method before building an adapter; do not guess its URL or API. |
| Order of Book Series | Book-series publication order, in-story order where a source records one, author and recurring-character series | Book-series order reference. Preserve source-specific ordering and edition identity; its own About/FAQ pages explain where its sequence data comes from. |
| Comic Book Herald | Comic reading guides, event order, character reading sequences and publisher-specific guides | Curated editorial reading order. Record that it is editorial guidance, not automatically official canon. |
| Official Franchise Timelines | Primary in-universe chronology and continuity references published by rights holders or franchise owners | Highest-priority primary source when authentic and current. Record edition/date and named continuity. |
| Official Episode Guides | Official episode sequence, titles, air dates and episode-specific chronology where explicitly provided | Primary episode/broadcast source. Preserve region and original broadcast context. |
| Official Novel Series Guides | Official book/volume order, publication sequence and author/publisher-recommended reading sequences | Primary publication/order source. Separate official numbering from in-world chronology. |

### B. Franchise encyclopedias and community-maintained wikis

Use these for detailed franchise-specific event evidence, character relationships, issue/episode references, continuity notes, cross-media appearances and source trails. These sites are evidence sources, not automatically authoritative primary canon.

| Source | Main coverage |
|:--|:--|
| Wookieepedia | Star Wars films, television, novels, comics, games, timelines and continuity distinctions |
| Memory Alpha | Star Trek episodes, films, characters, production/release data and in-universe chronology |
| Tardis Wiki | Doctor Who television, audio, novels, comics, spin-offs and continuity references |
| Marvel Database | Marvel characters, comics, events, alternate realities and media appearances |
| DC Database | DC characters, comics, events, continuities and adaptations |
| Tolkien Gateway | Tolkien works, peoples, places, events, texts and internal chronology |
| Harry Potter Wiki | Wizarding World books, films, characters, events and dates |
| A Song of Ice and Fire Wiki | Book/TV franchise records, characters, events, houses and chronology |
| The Witcher Wiki | Witcher books, games, television adaptations, characters and continuity |
| Narutopedia | Naruto/Boruto manga, anime, films, characters and story events |
| Dragon Ball Wiki | Dragon Ball manga, anime, films, games and continuity/era distinctions |
| One Piece Wiki | One Piece manga, anime, films, specials and arc/episode relationships |
| JoJo's Bizarre Encyclopedia | JoJo manga, anime, parts, characters and continuity |
| Pokémon Wiki | Pokémon games, anime, films, characters and release/continuity references |
| Transformers Wiki | Transformers series, comics, films, games and separate continuities |
| Fandom Wikis | A source family, not one database. Resolve each relevant wiki to its canonical host and wiki identity before collecting data. |

Use the **MediaWiki API** where a listed wiki exposes a compatible MediaWiki installation and its terms/policies permit automated access. Discover each wiki's actual API endpoint instead of assuming every Fandom or independent wiki has identical configuration. Prefer structured page metadata, revision information, categories, links and concise factual fields over copying full article prose. Preserve page revision/source links for attribution and later review.

### C. Anime, manga and light-novel reference databases

| Source | Main coverage | Access/reuse direction |
|:--|:--|:--|
| MyAnimeList | Anime/manga catalogue, relationships, staff, publication and airing data | Evaluate the official MAL API and its current application approval/usage rules first. |
| Anime-Planet | Anime/manga catalogue, recommendations, staff and user-maintained lists | Evaluate official access and permitted public-page references; do not assume an unrestricted API. |
| MangaUpdates | Manga/manhwa/manhua series, authors, artists, publishers, serialization and scanlation/community metadata | Useful specialist cross-check. Verify available access methods and terms before automated extraction. |
| Novel Updates | Webnovel/light-novel series, authors, translators, publishers, genres and release/community references | Specialist webnovel source. Verify access method and terms; distinguish site/community metadata from publisher-confirmed facts. |
| MangaDex | Manga/manhwa/manhua titles, relationships, chapters, groups, authors/artists, languages and publication metadata | Prefer its documented API and current API rules. Do not download or redistribute chapter content. |
| AniList | Anime/manga catalogue, studios, staff, relations, airing and publication dates | Reuse the current v3 AniList GraphQL client; preserve AniList IDs and relation types. |
| AniDB | Anime catalogue, episodes, titles, relations, staff and release metadata | Evaluate the official AniDB API and its request/usage conditions before adding an adapter. |
| Jikan | MyAnimeList-derived anime/manga data and mappings | The public hosted Jikan REST service was discontinued on 1 October 2026. Treat Jikan as a self-hosted/maintained deployment or dataset target only if a current supported instance is available; do not build against the discontinued public host. |
| Kitsu | Anime/manga catalogue, canonical IDs, relationships and metadata | Verify that the documentation being used is for the media catalogue API, not an unrelated Kitsu production-management API with the same name. |
| Shikimori | Anime/manga catalogue, related works, genres, people and release information | Verify the current official API contract, authentication and rate limits before use. |
| Anime News Network Encyclopedia | Anime/manga encyclopedia records, staff, companies and related works | Evaluate its documented encyclopedia API and usage conditions; retain ANN entity links and source attribution. |

Where two anime/manga providers describe the same work, keep both provider IDs and their individual fields. Resolve equivalence using stable identifiers, aliases, format, staff and source evidence; do not merge on title text alone.

### D. Film, television and screen-media databases

| Source | Main coverage | Access/reuse direction |
|:--|:--|:--|
| TMDB | Films, TV, seasons, episodes, people, production companies, release dates and regional data | Reuse the existing v3 client. Follow current API terms and attribution requirements. |
| TheTVDB | Series, seasons, episodes, artwork and extended television metadata | API access uses its current licensed or user-supported model; obtain the appropriate project key and comply with its data licence. |
| TVmaze | TV shows, episodes, air dates, networks, people and schedules | Prefer its documented API, send an identifying User-Agent and comply with its CC BY-SA attribution/share-alike requirements. |
| Trakt | Movies, shows, episodes, release metadata, calendars and lists | Use its documented API and approved OAuth/client access; do not collect private user histories without authorization. |
| IMDb | Film/TV titles, episodes, cast/crew, release facts and identifiers | Evaluate official datasets or licensed access and their current usage restrictions. Do not assume a general free commercial metadata API. |

### E. Books, novels, comics and publication records

| Source | Main coverage | Access/reuse direction |
|:--|:--|:--|
| Goodreads | Books, editions, series, authors, publication and community catalogue references | Verify current developer/API availability and terms. If no approved data access exists, use a permitted reference/link or user-supplied record rather than assuming scraping is allowed. |
| StoryGraph | Book catalogue, editions, genres, content/reading metadata and community references | Verify API/export availability and terms. Do not collect private account activity. |
| Hardcover | Book catalogue, editions, series, authors and publisher metadata | Evaluate its documented API and current access requirements; keep its IDs and attribution. |
| Comic Vine | Comic characters, issues, volumes, people, publishers and series | Its documented API requires a key and currently states non-commercial use only. Confirm deployment eligibility before enabling it. |
| Publisher Websites | Official catalogues, series pages, volume/edition numbering, ISBNs, publication dates and author/publisher announcements | Treat as primary sources. Use official feeds/APIs or permitted public-page extraction; preserve the publisher's canonical page and edition identifiers. |
| Google Books | Books, volumes, ISBNs, publishers, authors, page counts and publication dates | Reuse the existing v3 Google Books helper and documented API; preserve volume IDs and date precision. |
| Open Library | Works, editions, authors, identifiers and publication records | Use its API/datasets under current guidance, with caching and sensible request rates. Not a high-volume substitute for a licensed catalogue. |
| BookBrainz | Book, edition, author, publisher and series entities | Evaluate its documented API/dumps and data licensing; keep entity IDs and source provenance. |
| ISFDB | Speculative fiction bibliographies, editions, publishers, series and publication history | Specialist bibliography source. Check available access/dump options and licensing before automated use. |
| WorldCat | Library catalogue records, editions, ISBN/OCLC identifiers and holding information | OCLC access is subscription/licensing dependent. WorldCat Search API 1.0 support ended on 31 December 2024; confirm the current product/API and project eligibility rather than using legacy endpoints. |

### F. Cross-domain structured knowledge

| Source | Main coverage | Access/reuse direction |
|:--|:--|:--|
| Wikidata | Cross-domain entities, aliases, dates, relationships, organizations, works and identifiers | Use the current Wikidata Query Service endpoint/version and observe query costs and rate limits. WDQS v2 is available while v1 migration support is scheduled through 30 June 2027; do not hard-code the legacy endpoint indefinitely. |

### G. Community and contextual sources

| Source | Main contribution | Evidence treatment |
|:--|:--|:--|
| TV Tropes | Narrative structure, trope references, recurring motifs and contextual cross-links | Discovery/context only. Do not treat trope classification as a canonical chronology or factual production credit. |
| Reddit | Community corrections, discussion leads, fan timelines, reading-order recommendations and disputed interpretations | Community evidence only. Attribute it, preserve thread links and distinguish opinion from verified fact. Use approved API/access methods and current platform rules. |

### Source access, scraping and evidence policy

- Build a source registry so every target above has an explicit status: not assessed, API available, licensed API required, feed/dataset available, public-page extraction under review, permitted scraper implemented, manual/citation-only, unavailable or retired.
- Do not silently drop a requested source because it lacks an API. Investigate documented APIs, licensed access, feeds, public datasets, MediaWiki APIs, permitted page extraction and manual source verification.
- Scraping is an approved engineering option when the individual source permits it. Prefer a documented API or licensed feed when it provides better coverage, provenance or stability, but do not prohibit page extraction categorically.
- A detected Cloudflare challenge may be handled through the isolated Botasaurus worker only when the individual scrape explicitly sets `cfBypass: true` and the source-specific access review allows that method. The flag remains false by default. Optional Cloudflare Turnstile solving requires `CAPTCHA_SOLVER_PROVIDER=twocaptcha` or `capsolver` plus `CAPTCHA_SOLVER_API_KEY`; keep challenge and solver timeouts bounded by the worker configuration.
- This narrowly scoped challenge flow does not permit bypassing login/authentication, paywalls, private or paid content, user/age/entitlement checks, explicit denials or bans, IP/network blocks, rate limits, or other source restrictions. Unsupported CAPTCHA types and unresolved challenges remain blocked. Never persist solver tokens or log solver credentials.
- Review the current API documentation, licence, attribution requirements and published access terms for each source before enabling its adapter. Record the date, evidence and conclusion in the source registry.

### API and scraping implementation status (2026-11-27)

The implementation is deliberately provider-specific. The source inventory records 64 targets in `helpers/media/media-source-registry.ts`; `tests/media-source-registry.test.ts` checks unique coverage, normalized lookup, and restricted or unavailable access states. A registry entry is not proof that the provider is already connected to a command.

| Layer | Current implementation | Boundary |
|:--|:--|:--|
| Shared HTTP/JSON transport | `helpers/integration/web-scraper.ts`: `fetchPublicPage`, `fetchJson`, `fetchMany`, `fetchSitemapUrls`, `crawlPublicSiteDetailed` and the bounded compatibility wrapper | Validates public HTTP(S) destinations, resolves and pins public addresses, validates every redirect target, bounds redirects, timeouts, retries, response bytes, text extraction, links, concurrency and crawl page counts. |
| Franchise MediaWiki API | `helpers/integration/mediawiki.ts`: 15 explicit wiki endpoints; Action API search and page lookup | Read-only page metadata and source links with same-host canonical URL checks, 10-second requests, 512 KiB response limits and a 15-minute/100-entry cache. This helper is not yet a Timeline event-date provider; a wiki page or revision is evidence, not proof of an in-world date. |
| Web-novel discovery | `helpers/integration/webnovel-discovery.ts`: four metadata parsers (NovelFire, Novel Archive, Wuxia Click and Noveli.to), invoked only through `MEDIA_SOURCE_SCRAPE_ALLOWLIST` | All four are registry-marked `terms-review` and disabled by default. Novel Updates remains disabled pending access review; ScribbleHub is not in the active provider list. Search does not fetch unapproved sources. Keep metadata-only scope, attribution and canonical source URLs; do not fetch or redistribute chapter content. |
| Timeline metadata APIs | Existing AniList, TMDB, IGDB, Google Books, Open Library and MusicDiscovery clients | Continue reusing the existing provider clients and stable provider identifiers. Provider relationships must not be promoted to confirmed in-world chronology without direct evidence. |

The shared scraper does **not** fetch or parse `robots.txt`. Removing that crawler gate does not grant permission to access or redistribute a source: authentication, API terms, licensing, attribution, rate limits and site-specific restrictions remain separate provider requirements. The narrowly scoped Cloudflare/Turnstile challenge path described above may be used only when source-specific review approves it; it does not override those requirements. Do not treat a successful HTTP response as permission to republish source material.

Current access decisions that must remain visible in code and command behaviour:

- The 15 MediaWiki endpoint definitions are an explicit adapter list, not a blanket grant for every wiki. Keep them conditional until each site's API availability, terms and attribution requirements have been reviewed.
- ChronoCanon and Chronologeek have no verified canonical homepage in the current inventory. Do not guess their domains or create adapters until the source identity is confirmed.
- Comic Book Herald is a manual/citation reference. Do not scrape or automate site extraction; only use its RSS feed as permitted by its current terms.
- Jikan's hosted REST API is retired; WorldCat access is licensed; TVmaze requires attribution/share-alike review; Comic Vine is restricted to non-commercial API use.
- The source registry distinguishes implemented, credential-required, licensed, terms-review, review-required, manual-reference and retired providers. The four webnovel metadata adapters are explicitly `terms-review`; production discovery passes the operator allowlist and makes no requests to disabled providers. Do not expose a source as ready merely because a parser or endpoint constant exists.

Focused tests live in `tests/web-scraper.test.ts`, `tests/mediawiki.test.ts`, `tests/webnovel-discovery.test.ts` and `tests/media-source-registry.test.ts`. Preserve the SSRF/redirect tests when changing extraction behaviour.

### Research notes requiring special attention

- [The Canonicle](https://thecanonicle.com/) and [Chronelines](https://chronelines.com/) explicitly distinguish in-story event order from release order; retain that distinction in the Timeline data model.
- [Order of Book Series](https://orderofbookseries.com/about/) says publication order is its default and shows a separate chronological view only where a source records an in-story sequence. Preserve missing chronology as unknown rather than inventing an order.
- [Jikan's public API discontinuation notice](https://github.com/jikan-me/jikan-rest/issues/613) states that its hosted public REST API was discontinued on 1 October 2026. A self-hosted/currently supported deployment is a separate integration decision.
- [Wikidata Query Service migration notes](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/Wikidata_Query_Help) describe the v2 migration. Use the current endpoint and keep the query adapter configurable.
- [WorldCat Search API information](https://www.oclc.org/developer/api/oclc-apis/worldcat-search-api.en.html) identifies the end of v1 support and subscription requirements. Reconfirm current OCLC products before implementation.
- [TheTVDB API information](https://thetvdb.com/api-information) describes its licensed and user-supported API access models.
- [TVmaze API terms](https://www.tvmaze.com/api) describe its API licensing and attribution/share-alike terms.
- [Comic Vine API](https://comicvine.gamespot.com/api/) currently describes the API as non-commercial. Check the actual deployment and licence before enabling it.

## 3. `/identify` — Community Media Identification Network

**Purpose:** help members identify a media work when they remember only fragments. This is a community-assisted identification system, not another catalogue search command.

Example: a member remembers a scene, character design, line, game mechanic, soundtrack or cover but cannot remember the title. They open an identification case and let other members submit evidence-backed candidates.

### Case creation

A member opens `/identify` and selects **Create case**. The modal collects:

- What they remember, in their own words.
- Media type, if known.
- Approximate year or era, if known.
- Language, region or platform, when relevant.
- Distinctive clues such as a character, setting, visual detail, lyric-free music description or gameplay mechanic.
- Optional Discord attachment(s) or source link(s).
- Whether the case should be visible to the whole server or only to a selected channel/thread.

All fields except a short description should be optional. People often do not know enough to fill out a form accurately.

### Candidate workflow

- Members submit candidate titles using provider-backed search or a manual candidate with a source link.
- Every candidate includes a short explanation of which clues it matches.
- Other members can support a candidate, challenge it with evidence, or suggest another candidate.
- The case owner can mark a candidate as correct, keep searching or close the case as unresolved.
- A moderator can merge duplicate cases, remove abusive content or close spam.
- Solved cases become searchable by their clues and verified result.
- The original requester can optionally allow the solved case to be discoverable outside the server; default visibility remains guild-only.

### Evidence and matching

Keep evidence separate from conclusions. A clue is user-supplied; a candidate is a suggestion; the final identification is confirmed only by the requester or an authorized moderator under the case rules. Do not invent an automatic confidence score that looks authoritative without a tested matching model.

Search should reuse Discover and existing media providers. If the title is unknown, the system should not silently turn every clue into a broad provider query and claim that the first result is correct.

### Discord experience

Use a case embed with buttons for **Candidates**, **Add candidate**, **Add evidence**, **Mark solved**, **Reopen** and **Report**. Use selects for candidate navigation and modals for descriptions. Large cases can use a dedicated Discord thread when the bot has permission; the persistent case record remains in libSQL even if the thread is deleted.

### Privacy and safety

- Do not support investigations into real people, doxxing, private identities or personal whereabouts.
- Keep cases about identifying media and creative works.
- Validate attachment types and sizes. Never fetch arbitrary user URLs without the project's existing safe-URL and SSRF protections.
- Do not permanently copy third-party media unnecessarily. Preserve links and limited case evidence according to retention rules.
- A case owner may close or request deletion of their case, subject to the server's moderation and retention policy.

### Completion criteria

- A case survives bot restarts and thread deletion.
- Candidate submissions are attributable and deduplicated.
- A solved answer is explicitly confirmed and searchable.
- Guild-only cases cannot leak into another guild.
- Unauthorized users cannot close, edit or delete another member's case.
- Upload and URL handling use existing security boundaries.

### Current v3 implementation (2026-11-27)

- `/identify` is a guild-only, button/modal-driven case system. A case can be visible server-wide or restricted to its creating channel; restricted reads and browse results are filtered by owner, channel or moderator permission.
- Members can submit manual candidates with HTTPS sources or search the connected, category-specific media providers. Provider results retain their source ID, provider ID and canonical URL; a member must still explain the clue match before a candidate is saved.
- Members can add source-linked evidence and support/challenge candidates. Feedback is not treated as an automatic identification.
- The case owner or an authorized moderator can mark a candidate as the answer, close a case as unresolved, or reopen a resolved/closed case. Members can report cases; Manage Messages/Manage Server moderators have a guild-scoped queue to review or dismiss reports.
- Solved cases can be searched by title or description. Case creation also surfaces same-title case suggestions without auto-merging records. Case, candidate, evidence, feedback and report records remain guild-scoped; focused tests cover restricted visibility, report review and cross-guild isolation.

Not implemented yet: Discord attachment upload/storage, duplicate-case merging and content-removal controls, configurable multi-channel/thread access rules, review audit notes, and public cross-guild sharing with explicit consent and moderation.

---

## 4. `/expedition` — Multiplayer Interactive Expeditions

**Purpose:** a persistent, team-based exploration and puzzle campaign system that runs through Discord interactions. It should feel like a coordinated expedition with stages and discoveries, not a set of unrelated minigames.

### Expedition structure

An expedition contains:

- A title, description, theme, creator and visibility.
- A participant limit and optional team structure.
- A sequence of stages or a branching route.
- Stage objectives and permitted puzzle types.
- Clues, optional hints and completion conditions.
- A start state, pause/resume state and completion state.
- A published results summary.

Possible stage formats include multiple-choice reasoning, ordering clues, matching related records, decoding a fictional in-game clue, finding a provider-backed media answer, or submitting a short written solution. Keep puzzles safe and fictional; do not create real-world dares, dangerous challenges or tasks that ask members to visit unsafe places.

### Member workflow

1. Browse open expeditions.
2. Join an available expedition or accept an invitation.
3. Join or create a team if the edition allows teams.
4. Open the current stage and review its clues.
5. Submit an answer through a modal or select.
6. Receive a correct/incorrect response or a hint according to the stage's rules.
7. Unlock the next stage when the required condition is met.
8. Review the final route, discoveries and team result.

The system should support both shared-progress expeditions and team-versus-team expeditions. Do not allow participants to bypass prerequisites by guessing a later stage's custom ID.

### Creator and moderator tools

- Draft, preview and publish an expedition.
- Add, edit and reorder stages before participants enter.
- Set participant limits and joining rules.
- Pause, resume, cancel or archive the expedition.
- Review submissions and handle a disputed answer.
- Replace a broken clue while preserving a revision record.
- View participation and stage completion statistics.

### Integration boundaries

Reuse Play only for existing simple game mechanics if a stage genuinely needs them; do not make Expedition a wrapper around Play. Reuse Community sessions where a live group event already fits. Use the shared background scheduling facility for timed stage transitions if required; do not implement a second scheduler or one timer per expedition.

### Completion criteria

- Every stage transition is persistent and atomic.
- Team/member access is checked on every action.
- A single guild's expedition state cannot be read or changed from another guild.
- Creators can preview and correct content before publication.
- Restarting the bot does not reset progress or duplicate stage announcements.
- A failed announcement does not corrupt the expedition's state.

### Current v3 implementation (2026-11-27)

- `/expedition` is registered and available through the normal command-access and guild feature-toggle gates.
- Creators can create a private draft, add sequential stages, publish it, and pause, resume or cancel it. Only the owner can browse or open the draft; members can browse published/paused expeditions, join, submit an answer in a modal, see their own progress and reveal the optional hint for the currently unlocked stage.
- Stage answers are verified with a keyed hash; the original answer is not returned to participants. `getExpedition` now returns only stages visible to the requesting participant. Owners can inspect their own full draft.
- Each guild and participant has separate persisted state. Publishing and joining lock the expedition row so the stage count and participant limit cannot be bypassed by concurrent actions. A participant is limited to five answer submissions per stage per minute, and an expedition becomes completed when its last active participant finishes. `EXPEDITION_ANSWER_SECRET` is a stable 32+ byte secret; creation is disabled until it is configured.

Not implemented yet: teams/team-vs-team, invitations, branching routes, editing/reordering stages, stage revision history, disputed-answer review, timed transitions, result announcements and richer stage types. Progress is sequential and individual in this implementation.

---

## 5. `/casebook` — Fictional Mystery Investigation System

**Purpose:** a structured mystery-solving experience where members investigate fictional cases through evidence, suspects, timelines and competing theories. Unlike `/identify`, it does not identify an existing anime, book or game. It manages a mystery designed to be solved.

### Case structure

A case may contain:

- Case introduction and premise.
- Fictional setting and known events.
- Evidence items and their discovery conditions.
- Fictional persons of interest/suspects.
- Relationships between evidence items.
- A chronological event board.
- Red herrings clearly separated from confirmed evidence.
- One or more valid solution paths.
- Optional hints and staged reveals.
- An answer key and final explanation.

The creator should be able to build a case privately, preview it, test every condition and publish it when ready.

### Investigation workflow

- Members join individually or form a team.
- The case opens with an initial briefing.
- Evidence is revealed at the start or unlocked through valid interactions.
- Members can open evidence, compare details, submit a theory and cite which evidence supports it.
- Teams can maintain a shared theory board.
- Hints can be requested under the case's configured rules.
- A final solution is submitted when the case permits it.
- Once the case closes, the bot publishes a spoiler-controlled explanation and outcome summary.

### Authoring and moderation

Provide a case builder with sections for premise, evidence, entities, clue relationships, reveal conditions and solution. Validate that every clue reference exists and that every required path can be reached before publication. Let moderators pause a case, hide unsafe content or roll back an edit.

### Clear boundary

This is strictly for fictional mysteries and invented characters. It must not be used to investigate real people, real crimes, private individuals, personal data or real-world whereabouts. Do not allow members to upload private information about someone as "evidence".

### Completion criteria

- Authors can preview a complete case before it becomes public.
- Evidence unlocks are deterministic and persisted.
- Teams cannot see another team's private theory state unless the case explicitly allows it.
- Spoiler controls are enforced on every view, not just the first embed.
- The answer key cannot be retrieved by ordinary participants before the reveal.
- Unsafe or real-person investigation content can be reported and removed.

### Current v3 implementation (2026-11-27)

- `/casebook` is registered and available through the normal command-access and guild feature-toggle gates.
- Authors can create a private draft with a premise, encrypted answer key and initial evidence, add more evidence, then publish. Only the author can open the draft; members can browse published/paused/closed cases. Authors can unlock evidence in order, pause/resume/cancel or close the case.
- Members can submit theories and cite evidence IDs. Before closure, a member sees only their own theory; the author can review all theories. Once closed, theories and red-herring classifications become visible, and the author can reveal the solution.
- The answer key is encrypted with AES-256-GCM using `CASEBOOK_SOLUTION_SECRET`. Case creation is disabled until this separate, stable 32+ byte secret is configured. The command states that cases must be fictional and must not target real people or private information.

Not implemented yet: teams/shared team theory boards, suspects and relationship graphs, event boards, conditional/branching evidence unlocks, multiple solution paths, author preview/testing, evidence editing/rollback, user reporting and moderator content review. The current theory scope is per-member, not team-based.

---

## 6. `/relay` — Turn-Based Collaborative Creation Chains

**Purpose:** let multiple members create one evolving work by contributing in sequence. The next contribution depends on the shared state left by previous contributors.

This is not live document editing. It is a structured turn-based chain with a clear contribution order, branching, attribution and revision history.

### Supported creation types

- Collaborative stories and fictional universes.
- Sequential worldbuilding.
- Community-written scenes or chapters.
- Shared character/location concepts.
- Multi-part thematic collections.
- Collaborative text-based creative experiments.

Do not make every media category mandatory. The initial implementation should focus on text and permitted links; image or file contribution can be added only through existing attachment support.

### Chain lifecycle

- A creator defines the chain title, premise, contribution format, turn limit, visibility and participation rules.
- Members join or are invited.
- The chain opens a contribution slot for the next eligible member.
- The member submits a contribution through a modal.
- The contribution is reviewed according to the chain's rules: automatic acceptance, owner approval or community review.
- Accepted contributions become part of the current canonical version.
- The next turn opens.
- When a chain reaches its configured end, the bot compiles the result and offers publication into Archive.

### Branching and revision

A chain may optionally allow a member to create an alternate branch from a selected accepted contribution. Branches must retain the parent version and contribution order so readers can understand where they diverged.

Edits should create revisions rather than silently overwrite accepted work. The creator or authorized moderators may reject or request a revision with a reason. Preserve author attribution unless the contributor explicitly chooses an available privacy option.

### Anti-abuse and permissions

- Limit contribution length and frequency.
- Prevent a user from taking another member's turn.
- Avoid allowing the chain owner to rewrite another member's contribution without a visible revision event.
- Give moderators the ability to hide or remove disallowed content.
- Keep chain and branch state guild-scoped.

### Completion criteria

- Turn ownership is enforced server-side.
- Accepted contributions are immutable snapshots with revision history.
- Branches preserve their parent relationship.
- Concurrent submissions cannot both claim the same turn.
- The final compilation can be opened as an Archive submission without duplicating the underlying content record.

### Current v3 implementation (2026-11-27)

- `/relay` creates guild-scoped text chains with owner or automatic acceptance, a contribution limit, join/browse/view controls and owner pause/resume/cancel actions.
- Turn ownership is enforced inside the write transaction using persisted member join order. The owner takes the first turn; subsequent turns rotate through joined members. A contribution cannot be submitted by another member while awaiting revision.
- Owner review can accept, reject or request a revision. Rejected turns advance; revision requests keep the same turn open for the original author. Resubmission stores the prior requested version, review note and author in `relay_contribution_revisions`, and the author/owner can inspect that history.
- The chain panel shows the next contributor. Chains, memberships, contributions and revision records are guild-scoped. Focused tests cover rotation, rejection advancement, guild isolation and revision ownership/history.

Not implemented yet: alternate branches, invitations, community review, moderator hide/remove controls, a final compilation/export, and Archive integration. Contributions are text-only; the current model does not provide the full branching/version graph described in the proposal.

---

## 7. `/capsule` — Time Capsules and Scheduled Reveals

**Purpose:** preserve messages and permitted attachments from a person or group, then reveal them at a date chosen by the capsule creator. A capsule can be personal, collaborative or guild-wide.

The value is the shared reveal: members contribute now, the capsule stays sealed, and its contents become visible when the configured release condition is met.

### Capsule types

- **Personal:** visible to its owner before sealing; revealed to the configured audience later.
- **Collaborative:** a group contributes to one capsule.
- **Guild capsule:** members with permission can contribute before the deadline.
- **Milestone capsule:** tied to a future date or a documented community milestone.

### Creation flow

- Choose a title, description and capsule type.
- Choose the release date/time and time zone.
- Choose who may contribute and who may view the reveal.
- Set whether contributions can be edited or withdrawn before sealing.
- Add text, supported Discord attachments or permitted external links.
- Review the reveal destination and audience.
- Seal the capsule.

After sealing, normal members must not be able to retrieve hidden contents through buttons, cached embeds, logs or another command path. The reveal should be performed by a persistent scheduled worker, not by an in-memory timer.

### Reveal behavior

- Display the title and contributor list before showing contents.
- Reveal the contents only after the configured release time has passed.
- Publish to the selected channel only if the bot still has the required permissions and the destination is still in the owning guild.
- If the channel is gone or unavailable, keep the capsule eligible for a safe retry and notify an authorized manager.
- Prevent duplicate reveal posts after retries or restarts.
- Let the owner cancel an unrevealed capsule when policy allows; record the cancellation.

### Storage, privacy and retention

- Keep metadata, ownership, guild scope and reveal state in libSQL.
- Keep binary attachments in the existing RocksDB object store with size and digest checks.
- Do not expose attachment URLs or object identifiers before release.
- Support user deletion and the v3 guild retention policy. A sealed capsule must not become an exception to delete/retain rules.
- Avoid a promise of cryptographic secrecy unless the actual implementation has a reviewed encryption and key-management design. "Sealed" means application access is blocked until reveal, not that the data is mathematically inaccessible to database operators.

### Completion criteria

- Capsules reveal exactly once, including after process restarts.
- No user-facing path can read content before release.
- Time zones and daylight-saving transitions are handled correctly.
- A deleted destination channel does not lose the capsule.
- Delete/retain semantics cover both metadata and attached objects.
- User-facing confirmation clearly explains who can see the capsule and when.

### Current v3 implementation (2026-11-27)

- `/capsule` creates a guild-scoped capsule from a text channel, with title, optional reveal message, future ISO timestamp and an audience of owner, contributors or the guild.
- Contributors can create or update one text contribution while the capsule is collecting. Only the owner can seal or cancel it; sealing closes contributions.
- A persistent worker claims due sealed capsules from libSQL, publishes guild-audience reveals to the stored guild channel and DMs owner/contributor audiences to their configured recipients. Successful delivery and message IDs are persisted; failed deliveries are marked for review.
- The data helper redacts reveal messages and contribution text until the capsule is revealed, then returns contents only to the configured audience. Owner-audience capsules are excluded from other members' browse/read results and accept contributions only from their owner. Focused tests cover sealed/revealed guild access, contributor-only access, owner-only boundaries, sealing, contribution updates, cancellation and guild isolation.
- Delivery is not exactly-once across a process crash after Discord accepts a send but before libSQL records success. Claims older than five minutes are now marked failed with an explicit unknown-delivery warning; the worker does not automatically resend them. Owners can see the failure detail and must inspect the destination before any manual recovery.
- The finalization query is guild- and claim-token-scoped, so stale workers cannot overwrite a newer claim. Regression tests cover successful finalization and stale-claim recovery.

Not implemented yet: attachments/RocksDB objects, a user-selectable time zone (the modal expects an ISO timestamp), editing/withdrawal controls beyond replacing one's own text, scheduled destination changes, manual reconciliation controls and safe retry controls. The current feature does not claim cryptographic secrecy.

---

## 8. `/council` — Structured Community Decisions

**Purpose:** a complete proposal and decision process for server communities. It is not a basic poll and should not become a duplicate of Community's existing quick voting/session features.

### Decision lifecycle

1. A member submits a proposal with a title, description, intended outcome and optional evidence/attachments.
2. The proposal enters a configurable review state.
3. Eligible members can discuss it during a deliberation period.
4. Members may submit amendments; the proposal owner or moderators can accept, reject or combine them with a recorded reason.
5. The final proposal is frozen for voting.
6. A ballot opens with configured eligibility, options, start/end time and quorum rules.
7. Voting closes automatically or through an authorized moderator action.
8. The result is calculated and published with a clear explanation of quorum and outcome.
9. The final decision and amendment history remain available for reference.

### Ballot options

Support a small, well-defined set of voting methods only after tests demonstrate correct behavior:

- Single choice.
- Multiple choice with a maximum selection count.
- Ranked choice as a later phase, with a fully tested tabulation method and transparent explanation.

Do not promise anonymity without a precise data model. A private/secret ballot can hide voter identities from public result displays while retaining a restricted voter receipt for duplicate-vote prevention and eligibility checks. Explain that distinction in the UI and privacy documentation.

### Governance controls

- Configure who can propose, deliberate, amend and vote.
- Allow server administrators to set eligibility based on current membership or an approved role.
- Recheck eligibility at ballot submission.
- Prevent duplicate ballots and submissions after the closing time.
- Freeze the proposal text and ballot configuration after voting starts.
- Permit cancellation or reopening only to authorized moderators, with a visible audit reason.
- Keep one guild's proposals and ballots entirely isolated from another guild.

### Discord output

The public message should summarize the proposal, status, deadlines and current discussion link. Voting controls can be private/ephemeral while the published outcome remains public. Keep intermediate results hidden when the configured ballot requires it.

### Completion criteria

- Proposal, amendment, ballot and outcome transitions are auditable.
- The final ballot cannot be edited after voting begins.
- Duplicate or late votes are rejected server-side.
- Quorum and ties are calculated deterministically.
- Public output never reveals identities for a secret ballot.
- The system is a decision tool, not a financial, wagering or prediction service.

### Current v3 implementation (2026-11-27)

- `/council` creates guild-scoped proposals with two to ten options, single- or multiple-choice voting, a configurable quorum and an owner-controlled lifecycle: review, deliberation, frozen and voting.
- Members can submit amendments; only the proposal owner can accept or reject them. Voting duration is configured when voting starts, and the owner or an authorized moderator can close an active ballot.
- Votes are persisted per guild/proposal/member. Vote validation and insert are serialized against closure, duplicate and late ballots are rejected, and voters can verify their one-time receipt without retrieving their ballot choices.
- The background worker checks expired ballots every minute and closes them through the same locked tally path used by manual closure. Final results record the tally, quorum and pass/fail outcome. Focused tests cover lifecycle, amendments, receipt verification, automatic deadline finalization and guild isolation.

Not implemented yet: ranked-choice tabulation, role-based voter eligibility, public deliberation threads, amendment merging, moderator audit notes for cancellation/reopening, and a cryptographically private ballot model. Current stored vote records retain voter IDs and ballot values; they must not be described as anonymous.

---

## 9. `/workshop` — Collaborative Project Studio

**Purpose:** provide a structured workspace for a group to produce a substantial project through sections, tasks, reviews and versioned submissions. It is designed for parallel work, unlike Relay's sequential contribution chain.

This is not a live Google Docs replacement. Discord modals and messages are suitable for submissions, reviews and project status; they are not a real-time collaborative editor.

### Project structure

- Project overview, owner, collaborators and visibility.
- Sections or work packages.
- Tasks and assigned contributors.
- Submission/revision history.
- Reviewers and approval requirements.
- Dependencies between sections.
- Milestones and project status.
- Final compilation or publication output.

Possible uses include a community guide, a media reference document, a collaborative research summary, an event programme or a multi-author creative publication.

### Contributor workflow

- A project owner creates a draft and adds sections.
- Contributors join or are invited.
- The owner assigns tasks or opens them for volunteers.
- A contributor submits a section revision.
- A reviewer approves it, requests changes or rejects it with a reason.
- The contributor submits another revision if needed.
- Approved sections appear in the project preview.
- When required sections are approved, the project owner publishes or exports the final compilation.

### Collaboration and review controls

- Role-based permissions for owner, editor, contributor and reviewer.
- Section-level assignment and ownership.
- Version history and comparison between revisions.
- Review comments and request-changes status.
- Dependency-aware progress summary.
- Project pause, archive and cancellation.
- Moderator controls for removing harmful content or resolving disputes.

### Export and Archive connection

The initial export should be a bounded text/Markdown compilation or a set of links, using existing document/output conventions. Do not create a new file-rendering service. When the project is complete, let the owner submit it to Archive through the existing Archive flow.

### Completion criteria

- Multiple contributors can work on different sections without overwriting each other.
- Only authorized roles can approve or publish.
- Revisions preserve their previous version and author.
- Project progress survives restarts.
- A final output is generated from approved sections only.
- The feature does not imply real-time editing or store unbounded files.

### Current v3 implementation (2026-11-27)

- `/workshop` creates guild-scoped projects. Owners can add sections and optionally assign a Discord user; contributors submit bounded text revisions for a section.
- Each revision is stored independently with its author and status. A section cannot accept a second revision while one is awaiting review; only the project owner can approve a pending revision or request changes, and a contributor cannot review their own submission. Reviews recheck that the project is still open. Project owners can pause, resume, complete, archive or cancel a project.
- Project and section views expose the current persisted content and revision state. Focused tests cover single-pending-revision enforcement, owner-only review and guild isolation.

Not implemented yet: invitations and multi-role permissions, section-level reviewer assignment, dependencies/milestones, revision comparison, moderator dispute controls, generated Markdown compilation and Archive export. It is a section/review workflow, not a live collaborative editor.

---

## 10. `/exchange` — Community Discovery Exchange

**Purpose:** let members request a specific kind of media recommendation and receive explanations from other members. Discover remains provider-driven; Exchange is human-powered and centered on matching a request to a useful answer.

This is not a marketplace, purchase flow or media library. No trading, payment or personal progress tracking is involved.

### Request creation

A member creates a request containing:

- Media category or categories.
- What they are looking for, in natural language.
- Preferred or excluded genres, themes, format, language or era when known.
- Optional length/complexity constraints.
- Examples of works they liked or want to avoid.
- Whether the request is visible to the whole guild or a restricted audience.
- Optional closing date.

Avoid a long mandatory questionnaire. The natural-language description should be enough to create a request; optional structured fields improve matching but must not block submission.

### Recommendation submission

Members can submit a candidate through provider-backed search or a manual title with a source link. Each submission should include a short explanation of why it fits the request, which preferences it satisfies, and any caveat. The requester can:

- Save a candidate to the request shortlist.
- Ask the contributor for clarification.
- Mark a candidate as a good match.
- Mark the request solved.
- Keep it open for more ideas.
- Close it without a match.

The system should never claim that a recommendation is objectively correct. It should surface the explanation and allow the request owner to decide.

### Matching and discovery

- Search open requests by media category and available filters.
- Surface requests that have not received a useful answer.
- Detect likely duplicate requests and suggest existing ones.
- Let contributors see what kinds of requests they can help with.
- Keep the best explanations with the candidate rather than ranking only by reaction count.
- Allow moderators to remove spam, advertising or abusive submissions.

### Integration

Reuse Discover's provider search and stable media IDs. Do not create a second catalogue or recommendation engine. Exchange stores the request, candidate reference, contributor's explanation and request-owner feedback. If a candidate is not resolved to a provider ID, label it as a manual/unverified suggestion.

### Completion criteria

- Requests and submissions are guild-scoped by default.
- Candidates retain stable provider IDs and source URLs when available.
- Manual suggestions are distinguishable from verified catalogue records.
- Request owners control whether their requests are public within the guild.
- Duplicate detection assists rather than silently merges user requests.
- No purchase, payment, wagering or personal media-progress functionality is added.

### Current v3 implementation (2026-11-27)

- `/exchange` creates guild-scoped recommendation requests with natural-language descriptions, optional media category/preferences and either guild-visible or owner-only visibility. Similar open requests are suggested after creation; records are never auto-merged.
- Members can add manual HTTPS/provider-ID suggestions or search the shared Discover providers from the request panel. Provider results retain source ID, provider ID and canonical URL and require a contributor explanation before saving.
- Request owners can shortlist recommendations, rate them as good matches or not a match, add optional candidate-specific clarifications, switch visibility while the request is open, and mark the request solved or closed.
- The helper enforces visibility on reads and contributions. Candidate submissions are capped at 50 per request and clarification posts at 10 per author/request. A member can report a recommendation once; Manage Messages/Manage Server moderators have a guild-scoped report queue to inspect, remove a recommendation or dismiss a report.
- Clarifications, owner feedback and reports persist across restarts. Focused tests cover multi-guild isolation, restricted visibility, owner-only rating, clarification limits, duplicate reports, similar-request suggestions and moderator removal.

Not implemented yet: multi-category requests, optional closing dates, category/filter browsing for contributors, request-owner deletion controls, report-review audit notes, and public cross-guild sharing with explicit consent and moderation.

---

# Shared implementation order and dependencies

The ten systems should not be implemented as one large batch. Finish and verify one complete system at a time. These dependencies are suggested implementation order, not a requirement to build a universal framework.

| Order | Command | Why this order |
|---:|:--|:--|
| 1 | `/timeline` | Reuses existing media provider integrations and establishes cross-provider event provenance. |
| 2 | `/industry` | Reuses IGDB, TMDB, AniList and MusicBrainz; benefits from the identity/provenance decisions made for Timeline. |
| 3 | `/identify` | A focused community workflow with clear case and candidate states. |
| 4 | `/exchange` | Reuses Discover's provider search while adding request and response ownership. |
| 5 | `/relay` | Introduces persistent turn-based collaborative content and revision control. |
| 6 | `/workshop` | Builds on proven revision and approval patterns but supports parallel sections. |
| 7 | `/capsule` | Needs robust scheduled jobs, attachment handling and retention verification. |
| 8 | `/council` | Needs tested proposal/ballot transitions and careful permissions. |
| 9 | `/expedition` | Needs persistent campaign progress, stage transitions and reliable announcements. |
| 10 | `/casebook` | Benefits from the expedition state model but needs a separate fictional evidence/reveal model. |

### Before implementing a new command

1. Inspect the current command registry and neighboring command implementation.
2. Check whether a suitable helper, permission function, provider or database query already exists.
3. Write down the system's record ownership: global provider facts, guild-owned state, member-owned submissions or restricted moderator data.
4. Define the state transitions and who is allowed to perform each transition.
5. Implement the smallest complete workflow before adding optional panels.
6. Add focused tests for two different guilds, invalid transitions, unauthorized component actions, restart recovery and cleanup.
7. Update the command registry, deploy command inventory, feature-access configuration, dashboard metadata, help/category information and documentation.
8. Run the relevant TypeScript typecheck, unit/integration tests and build. Run dashboard checks only if dashboard files or contracts changed.
9. Inspect the final diff and confirm no unrelated files or generated data changed.

---

# Music Command System expansion

## Current implementation (verified in v3 source)

The existing `/music` command combines discovery and guild release tracking. It currently has:

- Artist resolution across configured Spotify, YouTube and SoundCloud identities for release tracking.
- MusicBrainz artist search and artist identity information.
- MusicBrainz release-group/discography browsing.
- Last.fm global artist and track charts.
- setlist.fm artist setlists when its optional API key is configured.
- Guild-owned release trackers, with a current limit of 25 trackers per guild.
- A selected text channel for each tracker.
- Initial seeding of known releases so adding a tracker does not announce an entire back-catalogue.
- Duplicate release detection and a bounded seen-release history.
- Pause, resume, test/preview and remove actions.
- A background polling cycle that checks guild retention and feature-enabled state before sending notifications.
- Provider error isolation so one failed source does not automatically prevent other configured sources from responding.

The current Music implementation uses the shared libSQL database and existing provider helpers. The MusicBrainz discovery helper has a short in-process cache, a request timeout and a serialized request queue; its current queue is set slightly above one request per second.

**Permission note:** read-only Explore, Discography, Charts and Live panels are available to guild members without Manage Server. Tracker management actions (add/list, pause/resume, test, remove and destination selection) recheck Manage Server in their interaction handlers. Keep this separation: do not weaken the mutation checks, and keep the server feature-toggle gate intact.

## Intended command experience

Keep a single top-level `/music` command. Its home panel should group the following systems without turning them into separate slash commands:

### 1. Explore

- Search an artist or band by name.
- Use MusicBrainz identity and disambiguation data to distinguish artists with similar names.
- Show known country, begin area, begin date and provider identity when available.
- Display matched Spotify, YouTube and SoundCloud links only when verified.
- Open the artist's discography, selected releases, setlists and provider profile.
- Preserve MusicBrainz IDs and provider URLs to avoid resolving the same artist again on every panel action.

### 2. Discography

- Browse release groups instead of presenting every edition as a separate album.
- Separate albums, EPs, singles, compilations, live releases, soundtracks and other provider-defined types.
- Show first release date and release type only when the provider supplies them.
- Paginate results and keep the provider link available.
- Allow a member to open a release group and inspect its known releases/editions.
- Do not infer missing tracks, track order or release dates from other editions.

### 3. Charts

- Display global top artists and tracks from Last.fm.
- Label each result with its provider and chart scope/time window.
- Show chart position and provider-supplied listener/playcount fields only when available.
- Make it clear that a global chart is not a guild listening ranking.
- Do not collect Discord members' listening history or infer their listening habits.

### 4. Live

- Search setlists by artist using a resolved MusicBrainz ID when available.
- Show concert date, venue, city/country, tour and song order when supplied.
- Link to the original setlist.fm record.
- Clearly disable or explain this panel if the API key is missing or the provider is unavailable.
- Do not imply that every concert or setlist is represented.

### 5. Release Radar

This is a planned discovery panel, not a new polling system.

- Browse recent releases by an artist or across supported provider catalogues.
- Filter by album, EP, single and other provider-supported release types.
- Show upcoming releases only when a provider returns a reliable future release date or official announcement.
- Separate confirmed release dates from tentative or incomplete metadata.
- Reuse the same artist resolution and release-group deduplication used by Discography.
- Do not invent future releases or claim a release is upcoming based only on an expected schedule.

### 6. Trackers

Preserve the current per-guild tracking model:

- Add a tracker by artist name or supported provider profile.
- Select a valid destination text channel within the current guild.
- Review the resolved provider identities before saving.
- Seed existing release IDs without sending old announcements.
- List, inspect, test, pause, resume and remove trackers.
- Show last successful check, last notification, provider availability and next scheduled check where those values can be reliably calculated.
- Keep the current 25-tracker per-guild limit until a measured need justifies changing it.
- Support release-type filters and notification modes after the baseline tracker behavior is fully tested.
- Allow an optional role mention only after validating that the role belongs to the current guild and that the acting user can configure it.
- Limit mentions through explicit allowed-mentions settings. Never allow provider-sourced text to create arbitrary mentions.

### 7. Community

- Let a member create a release discussion using the existing Community session/thread flow.
- Allow a release spotlight to link to an existing Community session rather than making a duplicate session.
- Keep event votes and discussion participation inside Community.
- Do not introduce another event scheduler, generic poll system or music-specific social feed.
- Keep this integration optional: music discovery and trackers must continue working when Community is disabled.

## Provider plan and boundaries

| Provider | Intended use | Implementation notes |
|:--|:--|:--|
| MusicBrainz | Artist identity, release groups, releases, labels, recordings, works and relationships | Public read access does not require an API key, but usage is limited to one request per second per application. Send a meaningful User-Agent, keep the global queue and cache results. Commercial use requires a separate licence/plan review. |
| Last.fm | Global artist/track charts, artist top tracks and tags | API key required. Label chart scope and provider. Review current commercial/research terms before commercial deployment. Do not present global data as a server's own listening statistics. |
| setlist.fm | Artist setlists, tour, venue, city, date and song order | Optional API key. Keep original setlist links and attribution. Verify current licence/usage terms before enabling in a commercial deployment. |
| Spotify Web API | Artist identity, album/release metadata and outbound links where the current app mode permits | The 2026 developer-access changes affect development-mode eligibility and endpoint availability. Re-check the official migration guide and changelog before adding endpoints. Never add playback, stream ripping or downloads. |
| YouTube Data API | Channel identity, public upload playlist and video metadata | Search is quota-sensitive. Resolve a channel once, cache its uploads playlist ID and use playlist item reads for recurring release checks. Respect the project's configured quota and never expose the API key. |
| SoundCloud | Artist/user metadata and public release links; RSS feed for supported release updates | Use documented API endpoints and supported authentication. Do not depend on undocumented internal endpoints. Respect token expiry, 429 responses and current app registration/usage terms. |

A provider's presence in the table does not mean every endpoint is configured, available in the current app mode or licensed for every deployment. Keep optional provider status explicit and let an outage in one provider degrade only that provider's panel.

## Music implementation phases

### Phase A — Music discovery (implemented)

- MusicBrainz artist search and identity resolution.
- Artist overview and discography browsing.
- Release-group grouping to avoid duplicate album entries for every edition.
- Filters for primary and secondary release types where available.
- MusicBrainz IDs and provider URLs retained for cross-provider matching.
- Shared request queue and cache for MusicBrainz.

### Phase B — Charts (implemented)

- Last.fm global top artists and tracks.
- Artist top tracks and tags where available.
- Provider attribution and chart-scope labels.
- No local listening-history collection.

### Phase C — Live setlists (implemented)

- setlist.fm artist and setlist search.
- Date, venue, city, tour and song order where provided.
- Original setlist attribution and link.
- Clean disabled/unavailable behavior without an API key.

### Phase D — Tracker reliability and controls (partially implemented)

Implemented baseline: per-guild tracker limits, initial seeding without back-catalogue announcements, namespaced duplicate detection, bounded seen IDs, pause/resume/test/remove controls, a background polling cycle, feature/retention checks and provider error isolation.

Remaining work:
- Release-type filters and configurable notification modes.
- Provider health and last-successful-check information per tracker.
- Optional role mention configuration with guild membership and permission checks.
- Bounded retry and exponential/backoff behavior for transient failures and rate limits.
- Avoid synchronized provider bursts across many guilds.
- Keep tracker writes, destination channels and notification records guild-scoped and auditable.

### Phase E — Public discovery access (implemented for existing panels)

- Read-only Explore, Discography, Charts and Live interactions are available to normal guild members; tracker-management controls remain permission-gated. Release Radar is a separate unfinished phase.
- Keep tracker creation, removal, destination changes, role mentions and other guild-wide mutations behind Manage Server or the project's appropriate existing permission helper.
- Recheck permission in every button, select and modal action. A user must not gain tracker-management access through a message created by an administrator.
- Preserve the dashboard feature enable/disable behavior for the Music command.

### Phase F — Release Radar (planned)

- Build a recent-release view using the same normalized provider records as Discography and Trackers.
- Add supported media filters and artist search.
- Add date precision, region and provider attribution.
- Include future release entries only when the provider has a verifiable date/announcement.
- Cache public metadata and paginate rather than repeatedly querying providers during component navigation.

### Phase G — Community connection (planned)

- Add a release discussion action that creates or links to an existing Community session.
- Preserve Community as the owner of session membership, voting, discussion and event history.
- Store only the reference from the music release/artist to the Community session.
- Do not add a personal music library or user listening progress.

## Music reliability, privacy and testing

- Keep Spotify metadata/artwork attribution and provider links intact. Never download or stream-rip audio.
- Do not use provider music content to train AI or machine-learning models.
- Respect YouTube Data API quotas and cache channel/upload-playlist resolution.
- Maintain the MusicBrainz global request throttle and meaningful User-Agent.
- Avoid polling MusicBrainz for routine release change detection; use the services intended for each recurring tracker source.
- Respect provider rate limits, license terms, user consent and terms of service.
- Store only the account/provider identifiers required for a guild tracker. Music trackers are guild-owned, not a member's personal listening history.
- A provider outage must not stop other provider results or corrupt tracker state.
- Test new tracker behavior against two guilds, missing channels, bot permission changes, repeated provider results, 429 responses, timeouts, disabled features and process restart.
- Test that a failed Discord message does not incorrectly mark a release as announced.
- Test that disabling the Music feature prevents subsequent notifications for that guild.

---

# Research sources

These sources are starting points for implementation research. Re-check the current terms, endpoints, authentication model and rate limits when implementation begins; provider policies and API access can change. Do not treat the presence of a documentation URL as approval to use the service commercially.

## Timeline and Industry data

- [IGDB API documentation](https://api-docs.igdb.com/) — game and company entities; company records include developed/published works and parent-company references.
- [TMDB API getting started](https://developer.themoviedb.org/docs/getting-started) — current API authentication, supported resources and rate-limit guidance.
- [TMDB company search](https://developer.themoviedb.org/reference/search-company) — organization discovery.
- [TMDB company details](https://developer.themoviedb.org/reference/company-details) — production company records.
- [TMDB API FAQ and attribution](https://developer.themoviedb.org/docs/faq) — required attribution and branding guidance.
- [AniList GraphQL documentation](https://docs.anilist.co/guide/graphql/) — anime/manga, studio and relation queries.
- [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API) — artists, release groups, releases, labels and relationships.
- [MusicBrainz rate limiting](https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting) — one-request-per-second application limit and User-Agent requirements.
- [Wikidata Query Service API](https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/API) — cross-domain structured-data queries. Check the current v2 migration endpoints and query limits before implementation.
- [Wikidata data access guidance](https://www.wikidata.org/wiki/Help:Data_access) — when the query service is appropriate and when it is not.
- [Google Books API](https://developers.google.com/books/docs/v1/using) — volume search, publisher, identifiers and publication dates.
- [Google Books Volume resource](https://developers.google.com/books/docs/v1/reference/volumes) — available volume metadata fields.
- [Open Library API](https://openlibrary.org/developers/api) — book/work/edition lookups. Its API guidance asks applications to cache responses and not use the service as a bulk/high-traffic backend.

## Music metadata and discovery

- [Spotify February 2026 developer-access update](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security)
- [Spotify February 2026 migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
- [Spotify February 2026 endpoint changelog](https://developer.spotify.com/documentation/web-api/references/changes/february-2026)
- [Spotify artist albums endpoint](https://developer.spotify.com/documentation/web-api/reference/get-an-artists-albums)
- [Spotify search endpoint](https://developer.spotify.com/documentation/web-api/reference/search)
- [YouTube Data API overview and quota](https://developers.google.com/youtube/data/getting-started)
- [YouTube channels resource](https://developers.google.com/youtube/v3/docs/channels)
- [YouTube playlistItems list](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list)
- [SoundCloud API guide](https://developers.soundcloud.com/docs/api/guide)
- [SoundCloud API explorer](https://developers.soundcloud.com/docs/api/explorer/)
- [SoundCloud rate limits](https://developers.soundcloud.com/docs/api/rate-limits)
- [Last.fm API](https://www.last.fm/api)
- [Last.fm global artist chart](https://www.last.fm/api/show/chart.getTopArtists)
- [Last.fm global track chart](https://www.last.fm/api/show/chart.getTopTracks)
- [setlist.fm API](https://api.setlist.fm/docs/1.0/index.html)
- [setlist.fm artist setlists](https://api.setlist.fm/docs/1.0/resource__1.0_artist__mbid__setlists.html)

## Discord interaction references

- [Discord application commands](https://discord.com/developers/docs/interactions/application-commands)
- [Discord message components](https://discord.com/developers/docs/components/overview)
- [Discord modals](https://discord.com/developers/docs/interactions/modals)

These references describe platform capabilities and API contracts. They are not dependencies to copy into Lemegeton. Keep the existing Discord.js implementation, project security boundaries and interaction patterns.

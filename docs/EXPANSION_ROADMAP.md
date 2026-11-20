# Lemegeton v3 — Expansion roadmap and 100k TypeScript architecture budget

**Implementation branch:** lemegeton-v3  
**Existing Draft:** PR #17 — keep Draft  
**Public command surface:** seven feature environments plus standalone /help, /privacy and /feedback.

This document expands the fifty candidate environments already listed in Section 22 of the v3 specification into a dependency-aware delivery plan. It is a product and engineering target, not a commitment to build every item immediately or to pad the repository with generated, duplicated or empty code.

## 1. Product shape

Lemegeton should function as one connected media-and-community system. A title discovered through /discover can connect to a Knowledge Atlas node, an Archive contribution, a Community discussion, a Play round, a profile showcase and a permitted media alert. Each domain record has one canonical identity and explicit guild/global visibility.

The public command surface stays:

- **/discover** — media discovery, creator/franchise exploration, comparisons and Knowledge Atlas.
- **/archive** — community media contributions, panels, collections, trails and curation.
- **/community** — Daily Drop, rankings, sessions, discussions, tournaments and calendar.
- **/play** — media-first trivia, guessing, puzzle and group game experiences.
- **/profile** — supported provider connections, privacy, affinity and public contributions.
- **/custom-role** — role creation, picker and administrator controls.
- **/settings** — guild configuration, media alerts, authorized diagnostics and dashboard access.
- **/help, /privacy and /feedback** — always standalone.

The catalogue names below are internal environments and navigation labels, not additional slash commands.

## 2. The fifty expansion environments

**Status meanings:** **Completed** means the described user-facing environment is implemented in this branch; **Partially implemented** means a useful workflow exists but one or more stated capabilities or lifecycle requirements remain; **Planned** means there is no complete user-facing implementation yet. A helper, command option or database table alone is not completion evidence.

### Discovery — /discover

| # | Environment | Build target | Status |
|---:|---|---|---|
| 1 | Discovery Metropolis | Category-aware search, provider filters, browse, random, trending, detail cards, compare and recommendations. | **Completed** |
| 2 | Community Knowledge Atlas | Image-backed, permission-aware graph for works, creators, franchises, adaptations, Archive records and community edges, with provider-host allowlisting and bounded thumbnail rendering. | **Completed** |
| 3 | Creator Explorer | Provider-backed workographies across AniList staff, TMDB cast/crew, IGDB companies and Google Books author credits, with source-linked Atlas edges. | **Completed** |
| 4 | Franchise Explorer | Source-labelled franchise, sequel, prequel, collection-member and alternate-version relationships with filterable Atlas paths. | **Completed** |
| 5 | Adaptation Explorer | Source-to-adaptation paths across supported provider records, with relationship provenance and image-backed Atlas nodes. | **Completed** |
| 6 | Comparison Studio | Category-specific comparisons with missing-data handling, field-level source provenance and fair normalization. | **Completed** |
| 7 | Books & Editions | General books, novels, light novels and translations with supported ISBN, edition, publisher, language and volume details. | **Completed** |
| 8 | Availability Explorer | Regional TMDB streaming/rent/buy data, Google Books catalogue and digital-access fields, and Steam Store regional records with explicit provider attribution. | **Completed** |
| 9 | Media Release Explorer | Provider-dated AniList anime airings, TMDB film/TV releases and IGDB game release records, shown with source links and provider failure visibility. Unsupported release feeds remain explicitly unavailable. | **Completed** |
| 10 | Metadata Source Explorer | Provider IDs, source links, field coverage, missing metadata and reported freshness (explicitly unknown when providers do not supply it), alongside reviewable community relationship proposals. | **Completed** |

### Archive — /archive

| # | Environment | Build target | Status |
|---:|---|---|---|
| 11 | Archive Metropolis | Unified submit, browse, search, filter, review, edit, remove, configure and moderation workflows. | **Completed** |
| 12 | Collection Studio | Mixed-media collections, ordering, attribution, collaboration and publication controls. | **Completed** |
| 13 | Archive Trails | Curated paths with transitions linking panels, quotes, scenes, soundtracks, fanworks and theories. | **Completed** |
| 14 | Visual Archive Gallery | Approved category results, permission-checked image thumbnails, full image previews and attachment links. | **Completed** |
| 15 | Soundtrack Discovery | Soundtrack metadata, media links, creator browsing and curated soundtrack collections; no general music player. | **Completed** |
| 16 | Curation Studio | Featured collections, category indexes, spotlights, trails and curator attribution. | **Completed** |
| 17 | Community Spotlights | Approved older contributions, creator features and curated highlights surfaced through Community. | **Completed** |

### Community — /community

| # | Environment | Build target | Status |
|---:|---|---|---|
| 18 | Community Metropolis | One home for Daily Drop, rankings, sessions, discussions, competitions, calendar and showcases. | **Completed** |
| 19 | Daily Media Centre | Scheduled prompts, trivia, mystery titles, short quotes, changeable member polls, creator features and Archive spotlights with moderator-reviewed submissions. | **Completed** |
| 20 | Ranking Studio | Candidate submissions, voting rules, vote changes, closing, tie handling and historical results. | **Completed** |
| 21 | Tournament Centre | Brackets, elimination rounds, multi-stage voting and explicit tie/eligibility rules. | **Completed** |
| 22 | Session Centre | Watch, Read, Play and Discuss sessions with moderator-reviewed nominations, announcements, hosts, interactive RSVP/withdraw controls, waitlists and event history. | **Completed** |
| 23 | Discussion Centre | Media-linked discussions with spoiler boundaries for supported episode/chapter/volume/season units. | **Completed** |
| 24 | Media & Community Calendar | Provider-dated releases and community events in one timezone-aware filterable calendar with 7/14/30-day windows, source/category filters and guild timezone display. | **Completed** |
| 25 | Community Seasons | Configured periods automatically aggregate delivered Drops, closed rankings, in-period sessions, completed challenge/puzzle runs and overlapping server spotlights. Existing records are referenced and deduplicated, never copied. | **Completed** |
| 26 | Community Showcase | Visible collections, Trails, creative contributions, completed ranking results and event highlights. | **Completed** |

### Games — /play

| # | Environment | Build target | Status |
|---:|---|---|---|
| 27 | Interactive Game Metropolis | Game catalogue, solo/team/cooperative entry, guild-scoped active-session discovery, host-only resume, persistent round state, join controls and result presentation. | **Completed** |
| 28 | Trivia Arena | Source-backed trivia, four difficulty levels, optional two-to-four-choice questions, aliases, moderator review, provenance and solo/team/cooperative hosted rounds. | **Completed** |
| 29 | Mystery Media | Multi-layer, category-distinct clues for hidden works, franchises, creators, adaptations, characters and games, revealed by the host during a live round. | **Completed** |
| 30 | Guessing Arena | Media identification rounds with title, creator, release, franchise, adaptation, studio, platform, genre and game clues. | **Completed** |
| 31 | Team Games | Cooperative/competitive teams, membership, scoring and persistent round state. | **Completed** |
| 32 | Challenge Centre | Themed media discovery tasks, seasonal challenges and community puzzles with published rules. | **Completed** |
| 33 | Quiz Pack Studio | Guild-scoped pack creation and contributor/manager curation, source-backed questions, accepted answers, difficulty, immutable question revisions and atomic multi-question moderator review. | **Completed** |
| 34 | Media Puzzle Room | Media word puzzles, relation puzzles, franchise-connection puzzles and cooperative clue chains. | **Completed** |

### Profiles — /profile

| # | Environment | Build target | Status |
|---:|---|---|---|
| 35 | Profile Metropolis | Supported Discord/provider details, contributions, visibility and profile presentation. | **Completed** |
| 36 | Account Connection Centre | Link, unlink, inspect and consent-manage the supported AniList and Steam connections. | **Completed** |
| 37 | Media Affinity | Opt-in comparisons with transparent signals and privacy controls. | **Completed** |
| 38 | Community Taste Explorer | Aggregate, opt-in guild tastes with minimum cohort thresholds and no individual record exposure. | **Completed** |
| 39 | Contributor Centre | Recent approved Archive entries and active server-visible collection/Trail attribution, filtered to the current guild. | **Completed** |
| 40 | Community Creations | Browse member-created, moderated Archive work from canonical records. | **Completed** |
| 41 | Profile Showcase | Opt-in public profile with configured AniList/Steam summaries and recent public community work; no personal tracking. | **Completed** |

### Custom Roles — /custom-role

| # | Environment | Build target | Status |
|---:|---|---|---|
| 42 | Custom Role Metropolis | Existing member/admin role lifecycle, selection, assignment and configuration behind one command. | **Completed** |
| 43 | Role Design Studio | Supported role palettes, gradients, icons, previews and styling within Custom Roles only. | **Completed** |

### Media notifications and automation — /settings, /discover, /community

| # | Environment | Build target | Status |
|---:|---|---|---|
| 44 | Media Follow Centre | Guild-scoped subscriptions to AniList titles, creators, franchise relationships and genres, with change snapshots and delivery. | **Completed** |
| 45 | Media Alert Centre | Provider-dated anime, film, TV and game alerts, plus metadata-change alerts for followed manga and other AniList targets, with category controls, guild destinations, deduplication and retryable delivery. Book publication schedules remain provider-limited where no verified feed exists. | **Completed** |
| 46 | Media Digest Studio | Configurable daily/weekly media-only digests with category and individual followed-entity filters, entity-type controls, region, IANA timezone, local send time, destination, pause/resume, source attribution and retryable delivery. | **Completed** |
| 47 | Media Automation Studio | Hourly provider-dated release rules with per-rule idempotency, safe announcements, optional spoiler-aware discussions and guild-scoped Atlas links. | **Completed** |

### Atlas and operations — integrated views, not extra commands

| # | Environment | Build target | Status |
|---:|---|---|---|
| 48 | Graph Export Studio | Permission-filtered graph paths, creator/franchise and Archive collection maps exported as PNG, SVG and JSON. | **Completed** |
| 49 | Feature Diagnostics | Restricted channel and permission checks, live provider probes, private asset-bucket access and guild-scoped delivery-queue health. | **Completed** |
| 50 | Data & Backup Centre | Restricted private-S3 backups, digest and archive verification, plus an isolated PostgreSQL restore rehearsal using a separately configured target cluster. | **Completed** |

## 3. Media coverage strategy

The media model is category-aware. Shared mechanics may be reused, but provider fields, release meanings, edition identity and relationship types must remain specific to the media family. Provider coverage is evidence-driven: a category is not considered supported merely because a label, type or placeholder exists.

### 3.1 Provider coverage and current boundaries

| Media family | Primary source and supported use | Current coverage and known gap |
|---|---|---|
| Anime | AniList GraphQL for media search/details, alternate titles, formats/status, episodes, airings, studios, staff, tags, recommendations and provider-returned relations. | Implemented for discovery, creators, trailers, airing and relations. Do not treat every returned relation as an adaptation or story-order assertion. |
| Manga, manhwa and manhua | AniList for title metadata and provider relationships; MangaDex public API for supplemental safe-rated manga titles, creators, tags, demographics, language and covers. | Search uses AniList `type:MANGA, format:MANGA` and MangaDex `contentRating[]=safe`. Light novels are excluded from ordinary manga results. MangaDex is metadata-only here; no chapter bodies or page images are retrieved. |
| Light novels | AniList records queried as `type:MANGA` plus `format:NOVEL`, with Google Books used for print/edition metadata when indexed. | Search, random, trending and genre-query paths explicitly constrain manga to `format:MANGA` and light novels to `format:NOVEL`. The result category and provider format remain explicit. |
| General books and novels | Google Books Volumes API for search/edition data; Open Library Search API for bounded title and subject discovery; Crossref and Open Library ISBN lookup for exact identifiers and linked editions. | Search results are human-triggered, cached and rate-limited; Open Library is not a bulk backend. Crossref contributor roles remain tied to exact ISBN matches; Work IDs, volume IDs, ISBNs and editions remain separate. |
| Webnovels | Royal Road's official public, story-specific RSS syndication feed. | The Webnovels category accepts a numeric Royal Road fiction ID or an HTTPS fiction/syndication URL from www.royalroad.com. It displays the feed's story identity, author when present, recent chapter titles/links and publication timestamps. Royal Road does not expose a supported global title-search/trending catalogue through this feed; no HTML search scraping, chapter-body retrieval, or unsupported non-Royal-Road provider is used. |
| Video games | IGDB as the primary structured game metadata source; Steam remains a separate account/store identity where its documented APIs and terms permit. | IGDB search returns user rating, rating count, aggregated critic rating and review count when supplied. Company workographies retain developer/publisher/porting/supporting roles, platform names, platform- and region-specific release dates, plus ratings when present. Steam App IDs remain distinct from IGDB game IDs. |
| Film and television | TMDB for movie/TV discovery, credits, people, season/episode data, videos, collections, release data and regional watch-provider records. | Movie records include runtime and country-specific release certifications where TMDB supplies them. TV records include reported episode runtimes and country-specific content ratings. Missing regional entries remain unknown, not evidence that a certification or rating does not exist. |
| Future integrations | Only an official, documented API or feed whose access and intended use are allowed for this application. | Letterboxd remains conditional on written/API access approval for the intended feature. No Letterboxd scraping or unofficial client is a fallback. Crossref and Royal Road are supplemental, narrowly scoped sources; Open Library is not a general Lemegeton metadata backend. |

### 3.2 Provider selection and terms

- **AniList:** the official [API documentation](https://docs.anilist.co/), [Terms of Use](https://github.com/AniList/docs/blob/master/docs/guide/terms-of-use.md), and [rate-limit guide](https://github.com/AniList/docs/blob/master/docs/guide/rate-limiting.md) govern every request. Light novels use `type:MANGA` with `format:NOVEL`; ordinary manga uses `type:MANGA` with `format:MANGA`. The current rate-limit guide warns that the API is temporarily degraded to 30 requests per minute, while its normal documented limit is 90. Read the rate-limit response headers and live provider notice; never hard-code the normal limit as a guaranteed allowance. The terms prohibit API backup/storage and mass collection/hoarding, and restrict competing non-complementary services. Keep access query-driven and limited to the Discord discovery/community purpose, do not build a mirrored AniList dataset, and obtain provider confirmation before broad commercial/production scaling if the complementary-service boundary is unclear. Revenue above the provider's stated threshold requires a commercial licence.
- **TMDB:** use its [official API documentation](https://developer.themoviedb.org/docs), [rate-limit guidance](https://developer.themoviedb.org/docs/rate-limiting) and [API terms](https://www.themoviedb.org/documentation/api/terms-of-use). Attribute TMDB content in user-facing results. Its current terms limit cached TMDB information to no more than six months. The rate-limit page says the former fixed limit was removed, notes an approximate upper range and requires clients to respect 429 responses; treat those values as changeable rather than as a request budget.
- **IGDB:** use the [official IGDB API documentation](https://api-docs.igdb.com/). It uses Twitch application credentials and POST query bodies. The documented limit is four requests per second and at most eight open requests; respect 429 responses, keep concurrency bounded and apply a provider-aware request queue. IGDB game, company, involved-company, platform, genre, franchise and release-date records are separate entities; record the relationship type instead of flattening them into free-form credits.
- **Google Books:** use the [Volumes reference](https://developers.google.com/books/docs/v1/reference/volumes) and [official API guide](https://developers.google.com/books/docs/v1/using). Public volume search and lookup are read-only. Preserve the returned volume ID and ISBN-10/ISBN-13 values independently; do not turn an absent ISBN, series field or translator into an inferred value. Observe the project's configured API quota and surface quota failures as provider-unavailable states.
- **MangaDex:** use its [official API documentation](https://api.mangadex.org/docs) and [acceptable-use policy](https://gitlab.com/mangadex-pub/mangadex-api-docs/-/blob/main/index.md). Requests return metadata only, force `contentRating[]=safe`, credit MangaDex and link the source record. No chapter text or page images are retrieved. Its policy excludes ads and paid services; confirm compatibility before monetized functionality is introduced.
- **Steam:** use the [Steam Web API documentation](https://steamcommunity.com/dev) and [Steam Web API Terms of Use](https://steamcommunity.com/dev/apiterms) for documented endpoints. Access requires an API key and a registered application. The current Store search and appdetails adapter paths are not listed in the public Web API reference, so treat their response shape and availability as best-effort storefront behavior, not a guaranteed documented contract. Do not make them the canonical game metadata source; IGDB remains the structured game source. Verify the application's registration and permitted use before relying on Steam data in a release.
- **Letterboxd:** its [API access policy](https://letterboxd.com/api-beta/) says access is request-only and not guaranteed; its [API docs](https://api-docs.letterboxd.com/) distinguish public client-credentials access from member-authorized operations. The current access policy excludes several categories of private, personal, analysis and recommendation projects. Do not implement profile linking or scrape public profile pages unless the project has explicit access and the intended use is accepted by Letterboxd.
- **Open Library:** its [API usage guidelines](https://openlibrary.org/developers/api#usage) prioritize human-facing, low-volume lookup and prohibit bulk harvesting/high-traffic backend use. Lemegeton performs title/subject requests only in response to user commands, caches results for ten minutes, serializes requests at least 1.1 seconds apart, and retains exact ISBN-to-Work/edition lookup. It does not mirror the catalogue or scrape HTML. The Subjects API is experimental and remains optional.
- **Webnovels:** Royal Road's public story RSS feed is approved only for story-ID/official-URL lookups and the feed's title, chapter links and update timestamps. It is not a title-search API. Other platforms remain unsupported until a documented, permitted API/feed with stable IDs and update semantics is approved.

### 3.3 Stable identity, editions and relationship semantics

- Keep provider identity namespaced by provider, entity kind and stable provider ID. Examples include `anilist:anime:<id>`, `anilist:manga:<id>`, `google-books:volume:<id>`, `tmdb:movie:<id>`, `tmdb:tv:<id>`, `igdb:game:<id>` and `steam:app:<id>`. The same numeric ID from different providers or entity families is never interchangeable.
- Store the provider's canonical HTTPS URL with the provider ID. A title or fuzzy match is a search candidate, not a canonical identity. Only create cross-provider identity links when an explicit external ID or reviewed evidence supports them.
- Treat a Google Books volume as an edition/volume record. Keep ISBN-10, ISBN-13, language, publisher and publication date as distinct fields; different editions and translations must not be merged solely because their titles/authors resemble one another.
- Keep the following relationship sources distinct: provider-confirmed relationships, provider recommendations, locally ranked similarity, and moderator-approved community proposals. Community approval means community-verified in that guild, not provider-confirmed fact.
- Relationship labels must be precise. A franchise membership is not automatically an adaptation; a publication or release order is not automatically story chronology; platform availability is not platform exclusivity; a TV season/episode is not a film sequel.
- Where a provider lacks a field, use an explicit unavailable/unknown state. Never synthesize a date, rating, author, translator, edition, chapter count, creator credit, streaming provider or adaptation relationship.

### 3.4 Freshness, rate limits and failure behavior

- Provider requests are on-demand unless a documented schedule is needed for an enabled alert/digest. Do not mass-crawl or build a shadow catalogue. Cache only what each provider's current terms permit, with provider-specific retention rather than one shared TTL.
- Respect 429 responses, Retry-After, provider request budgets and concurrency ceilings. The existing bounded transient-response retry helper is a fallback for transient HTTP status codes, not a replacement for per-provider rate limiting or quota scheduling. Do not automatically retry authentication exchanges, mutations or malformed payloads.
- Preserve the difference between not found, provider not configured, provider rate-limited, malformed response, timeout and missing optional metadata. A failed provider must not erase results from another provider; label partial results and the unavailable source.
- Record retrieval time when available and use a provider-supplied update timestamp only when that provider actually returns one. Do not present a retrieval timestamp as the media's publication/release date or claim data is live when it is cached.
- Keep credentials server-side, scoped to the relevant provider and environment. Do not expose API keys in embeds, URLs shared with Discord, logs, client code or exported graph data.
- Provider attribution, source IDs and source links must remain visible on detail/comparison surfaces and survive Atlas/export projections. Exports must retain the same visibility filters as the view from which they were produced.

### 3.5 Provider onboarding gate

Before adding or expanding a provider, document and test: official API/feed and endpoint schema; the intended Lemegeton use against the current terms; authentication and credential ownership; stable IDs and entity distinctions; rate limits, concurrency and 429 behavior; permitted caching/retention and attribution; supported locales/regions; deletion/update semantics; and fixtures for missing, malformed and changed payloads. If any of those are unknown, the integration remains conditional or planned and must not be advertised as operational.

## 4. Dependency-aware implementation phases

The phase status below is a dated implementation audit, not a feature promise. It records the existing domain-delivery state found in lemegeton-v3 as of 2026-11-20; a command label or helper alone does not count as a completed workflow. The forward plan for the 100,000-line engineering milestone is the ten-phase sequence in Section 5.

### Phase status board

| Phase | Current status | Evidence already present | Main remaining exit gate |
|---|---|---|---|
| 0 — Migration integrity | **Code migration complete** | PR #17 records TypeScript parity, Python removal, branch synchronization and the migration disposition. | Live Discord, production database/storage/provider and dashboard OAuth acceptance. |
| 1 — Runtime, data and security | **Foundation implemented; acceptance in progress** | Config validation, guild setup gates, guild-scoped data, consent, issue logs, permission helpers, permanently protected Manage Server-only /language command, CI, backup rehearsal and diagnostics. | Target-environment permission/data/rollback tests and current-head CI. |
| 2 — Discovery and metadata | **In progress** | AniList, TMDB, IGDB, Steam, Google Books, comparisons, airing, trailers, creators, relations and regional availability have implementations and fixture tests. Google Books edition metadata now supports exact ISBN-10, ISBN-13 and stable volume-ID lookups, in addition to full edition details and source references. | Provider contract edge cases, provenance for future mixed-source fields/edges, and a supported webnovel metadata source. |
| 3 — Archive and contributions | **Code-level lifecycle coverage implemented; production storage acceptance pending** | Submissions, moderation/reports, private asset storage, cleanup, permission-filtered previews, collections, collaborators, Trails and entry/collection spotlights. PostgreSQL-backed tests exercise derived-view visibility; cleanup locking, concurrent claims and legacy Discord cleanup are covered by the S3 integration suite. | Owner-controlled Discord/S3 acceptance and backup/restore validation (Phase 8 release gate). |
| 4 — Community and games | **Code phase completed; live acceptance pending** | Daily Drop, rankings, sessions/RSVP, spoiler discussions, timezone-aware release/community calendar, guild-scoped Community Seasons, persistent solo/team/co-op games, reviewed quiz packs, seeded tournaments with withdrawal audit and stale-control protection, plus the current-guild Showcase. | Owner-controlled Discord acceptance and current-head CI; no production release is implied. |
| 5 — Profiles and Custom Roles | **Code phase completed; Discord acceptance pending** | Guild-scoped AniList/Steam linking and unlinking, view-time privacy gates, minimum-cohort affinity/taste, profile contribution attribution, Custom Role hierarchy validation, saved-role restore guard and lifecycle reconciliation. | Owner-controlled Discord role-hierarchy, departure/rejoin, provider-account and privacy acceptance. |
| 6 — Notifications and automation | **Code phase completed; live provider acceptance pending** | Guild-scoped follows, source-backed alerts, daily/weekly digests, bounded automation, per-guild rule inspection, pause/resume, idempotent provider-event keys, lease/claim-token delivery and retry limits. PostgreSQL tests cover concurrent claims, duplicate events, stale workers and pause recovery. | Owner-controlled provider/Discord acceptance; book/chapter/volume schedules remain conditional on a dependable approved feed. |
| 7 — Knowledge Atlas and dashboard | **Code phase completed; live acceptance pending** | Stable provider identity, conservative legacy backfill, guild-scoped multi-hop provider/community traversal, source/evidence/provider filters, deterministic clusters, shortest paths, bounded JSON/SVG/PNG exports, dashboard UI and SQLite-backed multi-instance Rust sessions. | Owner-controlled provider, OAuth, multi-worker VPS, image-host, backup/restore and live Discord acceptance. |
| 8 — Operations and launch | **Operational tooling implemented; live release gates open** | Docker/Compose, repository CI, health diagnostics, backup/restore rehearsal and a live-acceptance workflow exist. | Real credentials, production storage/database, Discord application and dashboard OAuth tests; owner-authorized release and rollback. |

Phase 0 code migration status does **not** mean the service is launched. Phase 8 cannot be marked complete from local mocks or GitHub CI alone.

### Phase 0 — migration integrity and branch convergence

**Objective:** establish one trustworthy TypeScript v3 baseline before feature expansion.

**Verified in this audit (2026-11-13):** the `lemegeton-v3` tree contains zero Python files and compares as 733 commits ahead / 0 behind `multi_guild`. The TypeScript bot workflow passed typecheck and all 216 tests; repository health passed. Frontend typecheck/build, frontend dependency audit and Rust tests passed on the same PR head. Docker image verification and the Rust dependency audit remain separate CI gates until their jobs finish. Standalone /help, /privacy and /feedback remain separate, and PR #17 remains the only implementation target.

**Remaining delivery:**
- Keep all work on PR #17 and re-check the base/head relationship before any release decision.
- Confirm each retained legacy command/workflow is either migrated, intentionally retired with a reason, or explicitly deferred.
- Re-run the full migration test set whenever a later phase changes the database, routing or interaction contract.
- Keep live-service acceptance separate from code parity; do not call a mocked provider test a live acceptance test.

**Exit criteria:**
1. The code migration disposition is complete and documented.
2. The branch is current with its intended base and contains no accidental changes to the base branch.
3. TypeScript build/tests, Rust/dashboard checks, Docker validation and repository health pass on the exact PR head.
4. The PR remains Draft until the owner accepts production cutover.

### Phase 1 — runtime, data and security foundation

**Objective:** make every later phase safe to run across multiple Discord servers.

**Already present:** typed runtime configuration; startup/shutdown and database initialization; guild retention/language setup gate; inviter-or-Manage Server policy; privacy consent; issue hashes/logging; guild-scoped persistence; transaction helpers; server diagnostics; per-provider timeout/configuration; S3-compatible private asset storage; CI and backup/restore rehearsal.

**Remaining delivery:**
- Exercise guild onboarding, bot departure, retention deletion/retention and re-invite flows against real Discord guilds and a disposable target-like database.
- Verify every interaction handler re-checks guild, owner/moderator and channel permissions at the action point. Autocomplete must not reveal protected setup choices to unauthorized members.
- Exercise migration rollback and backup restoration against the target PostgreSQL version/configuration, not only an isolated rehearsal.
- Verify credentials, member content, provider payloads and signed storage URLs never enter logs or diagnostics.
- Validate S3 upload, read, deletion, expired signed URL and failed-cleanup recovery with the real private bucket.
- Verify shutdown cancels schedulers, closes pools and does not acknowledge unprocessed deliveries as complete.

**Exit criteria:** tests prove guild A cannot read or mutate guild B's records; permission-sensitive component actions fail closed; database rollback/restore is verified; secrets are absent from logs; the exact PR head passes all automated workflows.

### Phase 2 — discovery and metadata quality

**Objective:** deliver accurate, source-attributed discovery across media families with reliable providers.

**Already present:** AniList anime/manga/light-novel search with explicit MANGA/NOVEL formats, creators, schedules, trailers and relationships; safe-rated MangaDex manga metadata; TMDB film/TV, IGDB and Steam discovery; Google Books and bounded Open Library title/subject/ISBN search; comparisons, cross-media ranking and relationship review.

**Completed in this implementation pass:** Books & Editions now uses documented Google Books volume fields: subtitle, all supported ISBN forms, language, print type, main category, series display/order metadata and safe preview/info links. Existing isbn remains a backward-compatible ISBN-13-then-ISBN-10 value. Discovery detail cards and side-by-side comparison entries now show the originating provider's stable record ID and an explicit HTTPS source-record link. Each current normalized result comes from one provider, so this source attribution applies to all provider-supplied fields on that record; missing provider fields remain explicitly unavailable. The active AniList, TMDB, IGDB read-query, Google Books and Steam discovery requests now use bounded retries for transient HTTP responses (408/425/429/5xx), honor usable Retry-After values, and surface network/timeouts and exhausted HTTP failures to their existing callers. Only read-only POST queries opt in; the IGDB token exchange is not retried.

**Remaining delivery:**
- For future views that combine multiple providers or community-derived data, label provenance at the individual field/relationship level and keep provider-confirmed facts distinct from recommendations and community proposals.
- Add provider-specific fixtures for network/timeouts, HTTP 429 with Retry-After seconds/date values, exhausted 5xx responses, malformed JSON/schema drift and incomplete payloads. Confirm each client surfaces a clear error or an explicit unavailable state; do not retry malformed payloads.
- Keep category-specific metadata distinct: manga chapters/serialization must not be presented as book volumes; game platforms must not be treated as TV distribution; movie collection membership must not imply story chronology.
- Complete edition grouping only when provider identifiers support it. Do not infer that two editions are the same work from title similarity alone.
- Webnovel title search uses NovelFire HTML search/detail pages and chapter JSON, Novel Archive JSON APIs, Wuxia Click `__NEXT_DATA__`, Novel Updates and ScribbleHub search/detail, and Noveli.to JSON search/detail. Royal Road uses user-supplied fiction IDs/URLs and public RSS. The TypeScript scraper supports bounded HTTP/Playwright, CSS and JSON-LD extraction, XML/RSS parsing, sitemap discovery, `robots-parser` Allow/Disallow/wildcard/crawl-delay rules, multi-URL fetches and same-site crawling. Cloudflare challenges are detected and blocked; no challenge bypass or CAPTCHA evasion is implemented.
- Add representative fixtures from each active provider and assert normalization with partial/missing data.

**Exit criteria:** each displayed metadata field has a source or is explicitly unavailable; relationship provenance is visible; comparison tests cover missing and incompatible fields; active webnovel providers are queried through their implemented HTML/JSON interfaces and have fixtures for partial or changed responses.

### Phase 3 — Archive and contribution workflows

**Objective:** make the Archive a reliable, attributed, permission-aware community contribution system.

**Already present:** the unified Archive command; category-specific contribution forms; upload classification/limits; moderation queues and reports; server/global visibility rules; S3-compatible storage and cleanup retries; collections, collection collaborators, ordered Trail entries and Trail browsing; scheduled curator-attributed spotlights with start/end windows, server/global scope, create/list/cancel controls and Community spotlight display.

**Completed in this pass:** category browse results now show permission-checked image thumbnails from private S3 assets or supported legacy Discord attachments. Opening an entry retains the full image preview and lists other attachments as links. Asset URLs are resolved only after the Archive query has enforced guild visibility; no duplicate gallery records or public asset URLs are introduced. Spotlight creation/listing/cancellation is implemented in `/archive`, and active spotlights are surfaced from `/community` using the contributor's approved Archive record rather than duplicated gallery data. Collection entries and Trail steps now support one-based reordering with owner/editor authorization, parent-row locking, and a safe two-phase Trail position rewrite; hidden or unapproved references stay excluded and are parked after visible items, so they cannot disturb current ordering. The Archive now has an approved category index, creator-aware soundtrack search and collection-feature scheduling with curator attribution, date windows and separate server/global moderation.

**Completed in this pass (20 November 2026):** a PostgreSQL-backed integration test exercises collection items, Trail steps, entry spotlights, collection spotlights and their indexes across two guild contexts. It verifies that global-to-server demotion, an originating-guild change, and a return to pending moderation immediately remove an entry from every derived view while preserving parent collections and Trails with zero visible entries where appropriate. Collection spotlights also require their collection to remain active.

Private asset cleanup now serializes against attachment linking by holding an update lock on the asset while checking references and deleting the remote object. The due-cleanup worker claims rows with FOR UPDATE SKIP LOCKED and a five-minute lease, preventing duplicate concurrent deletion attempts while allowing recovery after a worker exits. S3 deletion has a bounded timeout; legacy Discord cleanup treats already-missing channels/messages as successfully removed. The MinIO integration test covers concurrent claims, failed-delete retry recovery and both legacy missing-resource cases.

**Remaining delivery:**
- Run the PostgreSQL and MinIO integration suites on the exact PR head; CI results are the verification gate.
- Validate private upload, replacement, removal, failed deletion and cleanup recovery against the owner-controlled production-compatible bucket and Discord test guild.
- Keep soundtrack records limited to permitted metadata/links with source attribution; uploaded audio/video is not a licence to redistribute copyrighted media.

**Code exit criteria:** upload, review, browse, collection and Trail workflows have PostgreSQL-backed visibility coverage; removed/private/cross-guild/unapproved entries disappear from every derived view; global content requires configured permissions; remote asset cleanup is serialized, retryable and safe under concurrent workers.

**Live release gate:** validate private uploads, signed retrieval, replacement/removal, missing legacy Discord storage, failed S3 deletion and recovery against the owner-controlled Discord guild and production-compatible bucket. This remains part of Phase 8; local integration tests do not mark production acceptance complete.

Quiz Pack Studio stores four difficulty levels, allows the original contributor or a server manager to revise a question, preserves the previous version in an immutable snapshot, blocks edits while a question is used in an active game, and sends edits back through moderator review. `/play` displays difficulty and exposes revision history to authorized contributors/managers. This pass adds contributor/manager pack-title and description curation plus atomic bulk review of up to twelve pending questions per action. Trivia now exposes and scores its stored multiple-choice options; Guessing requires identification clues and Mystery requires at least two category-distinct layers.

### Phase 4 — Community and media games

**Objective:** deliver repeatable guild activities with clear ownership, durable state and fair results.

**Already present:** scheduled Daily Drop with approved contributions; rankings with candidate review/voting/results; Watch/Read/Play/Discuss sessions with RSVP and waitlist; spoiler-aware discussions; release calendars/digests; a category-aware game catalogue; persistent solo, competitive-team and cooperative game sessions with active-session discovery and host resume; source-linked Trivia with difficulty and optional multiple-choice scoring; category-distinct Mystery clue layers and Guessing identification rounds; contributor/manager Quiz Pack curation, question revisions and atomic bulk moderation; automatically balanced Team A/Team B competition; cooperative sessions with a shared Community Team score; single-elimination 4/8/16-candidate tournaments with locked ballots, round advancement and deterministic seed tiebreaks; Community Seasons that reference existing activity records.

**Completed in this pass:** `/community` includes a guild-scoped Showcase for active collections and Trails, approved individual Archive contributions, closed rankings, completed tournaments, past non-cancelled sessions and closed discussions. Archive entries are re-checked for approval and server/global visibility; contribution bodies and discussion prompts are deliberately omitted so approved spoiler-bearing text is not exposed in the index. The on-demand calendar merges provider-dated releases from AniList, TMDB and IGDB with sessions from the invoking guild, supports 7/14/30-day windows and release/community/category filters, and formats dates using the configured guild timezone while retaining Discord-local timestamps. Community Seasons automatically include delivered Daily Drops, closed rankings, sessions scheduled inside the configured period, completed challenge/puzzle runs and overlapping server spotlights. Explicit curated links are deduplicated against automatic entries; all entries resolve to the original guild-scoped records. Seasons are recorded as implemented rather than repeated as future work. `/play` now supports individual sessions, automatically balanced Team A/Team B competition and one cooperative Community Team; team membership and scores are persisted and leaderboard reads remain guild-scoped.

**Completed in this phase:** tournament candidates can be withdrawn by the creator or a server manager before any ballot is cast. The affected match becomes a recorded walkover, round advancement carries the remaining candidate forward, and the bracket audit records creation, withdrawal, advancement, completion and cancellation. The Tournament Centre exposes the recent guild-scoped history.

Game message controls now carry their expected round and clue index. The database-backed game service rejects stale answer forms, repeated clue reveals and duplicate next/finish actions under the session row lock. The new integration suite races duplicate clue reveals, round advances and answers, then verifies that only one state transition or answer is committed.

**Remaining delivery:**
- Continue expanding media-backed puzzle/challenge question formats only when their answer normalization, source provenance, spoiler handling, timeout and host-control rules are defined. Existing Trivia, Guessing, Mystery, Challenge and Puzzle modes remain distinct; no new question format is claimed by this phase.
- Validate host departure, expiry and Discord interaction behavior in the owner-controlled test guild during live acceptance.
- Keep RSVP and session history separate from individual watch/read/play completion. Do not introduce personal progress tracking.

**Exit criteria:** automated code-level exit gate passed on the current v3 head. Bot CI ran 416 tests: 411 passed, 0 failed, 5 skipped; TypeScript type-check passed. Activity ownership and guild-scoped persistence remain covered by the existing community test suites. Live Discord acceptance remains a separate release gate.

### Phase 5 — Profiles and Custom Roles

**Objective:** complete optional identity connections and contribution presentation without turning Lemegeton into a personal tracker.

**Already present:** guild-scoped AniList/Steam profile linking and unlinking; public-profile and sharing preferences; affinity and minimum-cohort guild taste; AniList leaderboard; custom-role creation/configuration, picker, image validation, hierarchy checks, lifecycle, restore and reconciliation.

**Completed in this pass:** the profile now shows up to five recent, approved, server-visible Archive entries, active server-visible collections owned or edited/contributed to by the member, and active server-visible Trails owned by the member. Queries remain scoped to the current guild and reuse canonical Archive records. The showcase is visible only through the existing public-profile gate (or the member's private preview). It does not add personal media lists or progress tracking.

**Completed in this pass (20 November 2026):** public profile eligibility and provider visibility are re-checked on every profile read; provider fetches are skipped when the member has hidden that provider; switching the public profile off immediately hides the profile except for the owner's explicit private preview. AniList and Steam unlink operations are verified against the next profile read and remain guild-scoped. Server Taste and affinity retain their separate opt-ins and minimum-cohort thresholds. Saved Custom Role restoration now fails closed when the bot lacks Manage Roles, the saved role is Discord-managed or @everyone, the bot's highest role is missing, or the saved role is at/above the bot's highest role. It leaves the saved record unchanged when assignment is unsafe.

**Regression coverage added:** PostgreSQL-backed privacy changes, provider visibility, private preview and unlink behavior; unit tests for missing permissions, managed roles, @everyone, unresolved hierarchy and unsafe saved-role position.

**Live acceptance remains separate:** verify these behaviors with the registered application, real provider accounts, role hierarchy changes and member departure/rejoin events. No production role operation or provider credential was exercised by local fixtures.

**Exit criteria:** every public field has a visibility rule; unlink and privacy changes take effect immediately; aggregate data respects minimum-cohort thresholds; role operations survive restart/reconciliation and never assign above the bot's role.

Daily Drop and scheduled release digests now use atomic database claims, expiring processing leases and claim ownership tokens. Stale workers cannot complete another worker's claim, expired claims recover after restarts, and failed deliveries stop retrying after eight attempts. Both queues share the same bounded retry policy. Broader provider coverage and follow targets remain outstanding.

### Phase 6 — media notifications and bounded automation

**Objective:** notify users/guilds about selected media changes and connect approved media workflows without becoming a generic reminder service.

**Already present:** guild-scoped AniList title, creator, franchise and genre subscriptions; followed anime episode alerts; AniList recently-finished/cancelled notices; provider-dated AniList anime, TMDB film/TV and IGDB game release alerts; per-guild category toggles and a configured alert destination; daily/weekly release digests with category filters, individual followed-entity selection or all/none controls, entity-type filters, region, IANA timezone, local send time and a distinct destination; durable claims, deduplication, bounded retries and pause/resume; and the allowlisted media automation rules in Phase 6's adjacent environment.

**Completed in this pass (20 November 2026):** PostgreSQL integration coverage now exercises concurrent rule claims and delivery claims, per-guild rule listing, cross-guild toggle rejection, stale rule-token rejection, HTTPS-only source URLs, duplicate provider-event suppression, retry claim replacement, stale-worker completion rejection, discussion creation idempotency, pause/resume delivery gating, and release-digest window claims. Digest pause atomically fails outstanding processing rows and invalidates their claim tokens; resuming the schedule does not silently requeue work explicitly failed by an administrator. Pure tests cover supported media categories and provider/source/title/time event identity.

**Live acceptance remains separate:** credentials, rate limits, real provider release changes, channel deletion/permission loss, Discord message/thread creation and multi-guild delivery need owner-controlled acceptance. No live provider or Discord application was exercised in this test pass.

**Remaining delivery:**
- Add book/chapter/volume publication schedules only after an approved provider supplies dependable dates or update events. No publication date is inferred from a catalogue record.
- Validate the configured AniList, TMDB and IGDB credentials and Discord destinations against live services; mocked/provider-fixture checks do not replace live acceptance.
- Re-check provider rate limits, terms, outages, changed release dates and removed destinations during live acceptance.
- Keep all scheduling media-only. No birthdays, general reminders, productivity tasks or unrelated automation.

**Exit criteria:** rules are bounded and per-guild, delivery is idempotent, every event can be traced to a provider/source, retries are safe, and a moderator can inspect/disable each active rule.

## Phase 7 — Knowledge Atlas and dashboard

**Objective:** make canonical media relationships explorable while preserving provenance, stable identity and guild visibility.

**Implemented architecture:** normalized media categories and title keys; provider, recommendation and community edges; provider namespace plus stable provider ID for both edge endpoints; deterministic bounded breadth-first graph traversal; cycle and duplicate-node handling; shortest-path search; source-kind, category, relationship, provider, provider-ID and evidence filters; deterministic category clusters; and SVG/PNG/JSON export. The Rust/Axum dashboard API remains the authorization boundary and calls the existing private TypeScript bridge; no second backend was introduced.

**Completed in this pass (20 November 2026):**
- Added an idempotent PostgreSQL legacy-edge backfill for known provider URL patterns: AniList, TMDB, Steam, Google Books, MangaDex, Kitsu and Open Library. It records identity only when the URL encodes an unambiguous provider ID. Duplicate identity pairs and unknown/slug-only URLs retain the title/category fallback rather than violating the uniqueness index.
- Expanded Atlas traversal so each bounded hop collects provider edges and approved guild-scoped community links. Guild/global visibility is applied in every database lookup, not only to the root.
- Added provider namespace, provider ID and evidence filters to relationship and graph filtering; search now includes source/evidence and canonical identity fields.
- Added deterministic category clusters and shortest-path targets. The dashboard exposes provider, provider-ID, relationship and evidence filters, path selection and JSON/SVG/PNG export.
- Added a bounded `/atlas` bridge route: validated guild/setup gate, provider identity validation, maximum depth 3, maximum 40 nodes, per-node query cap, export-size cap, source/provenance metadata and error handling. The Rust API validates categories, identity formats, public HTTPS URLs, query lengths, export formats and graph limits after authorizing the requested guild.
- SVG/PNG rendering includes source kind, provider identity and edge evidence. Image fetching only accepts the pre-approved provider image hosts, disables redirects and applies a timeout; exports operate on the already guild-filtered graph.
- Added unit, Rust API, dashboard bridge, renderer and PostgreSQL integration coverage for stable identity, ambiguous legacy data, filters, pathfinding, clusters, export provenance, guild scoping and invalid requests.

**Code phase status: complete.** The Atlas exit gate is satisfied at code level: traversal is bounded and deterministic; provider identity is stable where available; legacy uncertainty preserves fallback; filters and exports reuse the guild-scoped graph; and edges expose source kind/evidence.

**Live acceptance remains separate:** real provider metadata and media image hosts, Discord guild membership/setup, OAuth login across multiple Rust workers, VPS Nginx/systemd behaviour, backup/restore of SQLite WAL files and production latency still require owner-controlled acceptance. No deployment or production cutover is implied.

**Operational constraints:** PostgreSQL remains the authoritative bot/domain database. SQLite is a secondary local database only for Rust dashboard sessions, OAuth state, distributed request limits and token-refresh leases. Rust dashboard workers can share one SQLite WAL file on the same host and local persistent disk; do not put it on NFS or share it between hosts. Nginx uses `least_conn` for three loopback dashboard workers. Keep the Discord bot/gateway as a single service.

### Phase 8 — operational hardening and launch

**Objective:** prove the service can be deployed, observed, restored and rolled back safely.

**Already present:** TypeScript and dashboard/Rust workflows, repository-health workflow, production Dockerfile and Compose validation, startup checks, server diagnostics, PostgreSQL backup/restore rehearsal and a separate live-acceptance workflow.

**Diagnostics added in this pass:** `/settings` now probes PostgreSQL with a live `SELECT 1` and reports Discord gateway readiness/latency, configured delivery-channel permissions, and provider/object-storage configuration. Provider connectivity, object-level asset access and scheduled-job health are deliberately not labelled healthy because those live probes are not implemented.

**Remaining delivery:**
- Complete production-image build, container runtime contract, non-root/health-check validation and Rust dependency audit on the final PR head.
- Run live acceptance with the registered Discord application and representative multi-guild test servers.
- Validate the target PostgreSQL migration, backup/restore, rollback and retention-deletion behavior.
- Validate private S3-compatible upload/read/delete/recovery and signed URL expiry with production-like credentials.
- Validate each configured provider using real permitted credentials and rate limits. A missing optional credential must yield an explicit unavailable state, not fake data.
- Validate dashboard OAuth, bridge authentication, guild authorization and session expiry.
- Document operational owner, alert routing, backup cadence, restoration authority, rollback procedure and release checklist before cutover.

**Exit criteria:** automation is green on the exact commit; live Discord, storage, provider, database and OAuth tests are signed off by the owner; recovery is rehearsed; only then may the PR leave Draft and deployment be separately authorized.

### Phase dependency and work order

1. **Phase 0 → Phase 1:** migration integrity is the baseline; security/data gates must be met before exposing new workflows.
2. **Phase 2 → Phase 7:** metadata identifiers and provenance underpin canonical graph nodes/edges.
3. **Phase 3 + Phase 4 → Phase 7:** approved Archive and Community records become graph nodes only after visibility rules are enforced.
4. **Phase 4 → Phase 6:** scheduled activity and release records are reused by media digests and bounded automation.
5. **Phase 5 runs alongside Phases 3–4:** contributor/profile surfaces depend on approved public contributions, not duplicated profile storage.
6. **Phase 8 is continuous:** every phase adds or updates its own tests, diagnostics and recovery behavior; final release acceptance remains a separate gate.

A domain is not complete because its slash-command option exists. It closes only when behavior, state transitions, permissions, privacy, failure cases, tests and documentation meet its exit criteria. The 0–8 material above remains the dated implementation-status audit; future work toward the 100k milestone follows the ten phases in Section 5. Do not maintain a separate abbreviated progress checklist that duplicates either source.

## 5. 100,000-line TypeScript budget

The following is a long-range engineering allocation, not a deadline or reason to write filler. Count only authored, maintained TypeScript/TSX source and tests. Exclude generated code, dependencies, lockfiles, build output, vendored code, copied provider schemas and empty placeholders. The target can be reduced if the actual product does not require the code.

| Area | Planned TS/TSX LOC | What makes the code substantive |
|---|---:|---|
| Runtime, configuration, command routing and shared interaction infrastructure | 7,000 | Typed gateway lifecycle, component routing, authorization, error handling, structured logging and reusable Discord interaction state. |
| PostgreSQL domain layer, migrations and data compatibility | 8,000 | Guild-scoped repositories, constraints, transactional workflows, migrations, compatibility adapters and recovery tooling. |
| Provider integrations and metadata normalization | 10,000 | Typed AniList MANGA-vs-NOVEL filters; strict G/PG-rated Kitsu anime/manga JSON:API and safe-rated MangaDex metadata; Google Books and Open Library title/subject/ISBN search with shared checksum validation; Crossref editors/translators; IGDB alternative names, Steam and TMDB; article/main-content extraction, Open Graph and alternate-feed discovery, recursive bounded sitemap indexes, robots-aware site crawling with explicit per-URL failure reports, Retry-After-aware rate limits, XML/JSON-LD extraction and provider contract tests. Cloudflare challenge responses remain explicit blocked outcomes; no challenge circumvention or CAPTCHA evasion is implemented. |
| Discovery and media intelligence | 9,000 | Relevance-ranked cross-provider title search with AniList synonyms, Kitsu and MangaDex alternate titles, IGDB alternative names and Google Books subtitles; Kitsu anime/manga discovery alongside AniList and MangaDex; exact AniList MANGA/NOVEL separation; source-aware comparisons; cross-media recommendations using native genres, tags, subjects and categories, while provider-native recommendations stay separately attributed. |
| Community Archive and asset workflows | 8,000 | Submission/review, S3 storage, permissions, collections, trails, galleries, attribution and cleanup. |
| Community activities and scheduling | 8,000 | Daily Drop, rankings, tournaments, sessions, discussions, calendars, digests and idempotent delivery. |
| Media games and quiz systems | 6,000 | Game state machines, question packs, clue engines, teams, scoring, validation and moderation workflows. |
| Profiles and provider connections | 5,000 | Linking/revocation where supported, privacy, affinity, taste aggregates and contributor views. |
| Custom Roles | 6,000 | Lifecycle, hierarchy-safe role assignment, image processing, picker, validation, audit and admin controls. |
| Media subscriptions and automation | 5,000 | Title/entity subscriptions, alert policies, digests, delivery workers, workflow execution and audit events. |
| Knowledge Atlas and graph services | 9,000 | Graph identities, typed edges, provenance, multi-hop queries, pathfinding, projection, clustering, exports and visibility enforcement. |
| Next.js dashboard application | 7,000 | Authenticated Atlas and settings views, accessible components, API contracts and responsive application state. |
| Automated tests, fixtures and integration harnesses | 10,000 | Provider contracts, database integration, guild isolation, Discord interaction simulations, security regression and end-to-end journeys. |
| Operations, observability, deployment and release tooling | 2,000 | Health/readiness, diagnostics, backup verification, graceful shutdown, migration gates and container/release validation. |
| **Total** | **100,000** | **Meaningful, tested TypeScript/TSX only.** |

### Ten phases for the 100,000-line milestone

The allocations below regroup the existing budget into one forward sequence. They are **planned TS/TSX source and test budgets**, not measured current progress or minimum file counts. Cumulative ranges are targets for planning only; measure actual authored, maintained files from Git. Rust code remains Rust and does not count toward this TypeScript/TSX milestone.

| Phase | Focus | Planned allocation | Cumulative budget |
|---:|---|---:|---:|
| 1 | Runtime and shared interaction foundation | 7,000 | 0–7,000 |
| 2 | PostgreSQL domain and data compatibility | 8,000 | 7,000–15,000 |
| 3 | Provider integrations and safe data ingestion | 10,000 | 15,000–25,000 |
| 4 | Discovery and media intelligence | 9,000 | 25,000–34,000 |
| 5 | Community Archive and asset lifecycle | 8,000 | 34,000–42,000 |
| 6 | Community activities and media games | 14,000 | 42,000–56,000 |
| 7 | Profiles, provider identity and Custom Roles | 11,000 | 56,000–67,000 |
| 8 | Media subscriptions and bounded automation | 5,000 | 67,000–72,000 |
| 9 | Knowledge Atlas and dashboard experience | 16,000 | 72,000–88,000 |
| 10 | Tests, security verification and operations | 12,000 | 88,000–100,000 |
| **Total** | **All planned areas** | **100,000** | **100,000** |

#### Phase 1 — Runtime and shared interaction foundation (7,000)

Complete the Discord.js lifecycle, startup/shutdown, command and component routing, shared interaction state, permission rechecks, error handling, structured diagnostics and consistent loading/edit behavior. Preserve the compact command surface and the separate /help, /privacy and /feedback commands.

**Exit gate:** interactions acknowledge within Discord deadlines; privileged components re-check user, guild, channel and record permissions; shutdown and error paths are bounded and testable.

#### Phase 2 — PostgreSQL domain and data compatibility (8,000)

Complete canonical domain repositories, guild/global visibility boundaries, schema migrations, constraints, transaction helpers, idempotent writes, retention behavior, compatibility and restore/rollback tooling. Keep provider identity and community-owned records distinct.

**Exit gate:** two-guild integration tests prove isolation for reads, writes, deletes, caches, exports and scheduled work; migrations and restore rehearsals work against the target PostgreSQL version.

#### Phase 3 — Provider integrations and safe data ingestion (10,000)

Finish typed provider adapters, source identifiers, field-level provenance, timeouts, bounded retries, 429/Retry-After behavior, schema-drift fixtures and explicit unavailable states across AniList, MangaDex, Kitsu, IGDB, TMDB, Steam, Google Books, Open Library, Crossref and supported feeds. Keep the scraper bounded, robots-aware and restricted to permitted public sources. Challenges, authentication walls and CAPTCHA remain stop conditions.

**Exit gate:** every normalized field has an attributable source or is explicitly unavailable; provider contract tests cover partial, malformed, changed and rate-limited responses; no provider is advertised without a documented permitted access path.

#### Phase 4 — Discovery and media intelligence (9,000)

**Status: Completed — 19 November 2026.**

Category-aware multi-provider search, alternate-title matching and stable relevance ranking are implemented for the supported anime, manga, light-novel, book, webnovel, film, television and game categories. Search relevance includes provider-supplied aliases, synonyms, subtitles and original-language titles. Mixed-media comparisons keep each provider's native fields and rating scale instead of manufacturing a shared score. Franchise/adaptation and creator exploration retain provider relationship labels and source links; exact-title matches remain explicitly unverified. Local cross-media recommendations cover IGDB games through provider genre IDs and use normalized Dice overlap to limit metadata-volume bias. Each match identifies both metadata field types, and its overlap evidence is retained on the Knowledge Atlas relationship; provider-generated recommendations remain separate.

**Verification in this pass:** ranking tests cover absent title variants and stable ordering; cross-media tests cover missing labels, generic/non-matching metadata, duplicate candidates, field-type provenance and result limits; comparison tests prove mixed media categories remain distinct. Existing provider fixtures cover partial metadata and provider-specific rating scales. The command retains provider failure reporting and does not treat unavailable data as a negative fact.

**Exit gate:** category distinctions remain correct; comparison and ranking tests cover missing/incompatible metadata; displayed relationships retain source evidence and provenance.

**Completion evidence:** tests/title-matching.test.ts, tests/cross-media-recommendations.test.ts, tests/media-comparison.test.ts, tests/igdb-genre-search.test.ts, tests/atlas.test.ts, tests/open-library.test.ts, tests/tmdb.test.ts, tests/provider-coverage.test.ts, tests/metadata-source-audit.test.ts, and the /discover search, comparison, franchise, creator and similarity paths.

#### Phase 5 — Community Archive and asset lifecycle (8,000)

**Status: Completed — 20 November 2026.** PostgreSQL-backed coverage checks collection, Trail, entry spotlight and collection spotlight visibility across guild and moderation changes. Asset lifecycle coverage includes attachment linking/replacement/removal, row-locked cleanup, concurrent due-work claims, bounded S3 deletion and recovery, and missing legacy Discord channel/message cleanup.



Complete submission, review, moderation, reports, private S3-compatible storage, gallery previews, mixed-media collections, Trails, attribution, visibility transitions, asset replacement/deletion and failed-cleanup recovery.

**Exit gate:** private, unapproved or cross-guild entries disappear from every derived view and export; assets remain private; cleanup can recover after interrupted operations.

#### Phase 6 — Community activities and media games (14,000)

**Status: Completed — 20 November 2026.** Tournament withdrawal/walkover handling and bracket audit are implemented. Game answers, clues and round controls reject stale or duplicate actions with server-side state tokens. The current v3 head passes Bot CI (411 passed, 0 failed, 5 skipped) and TypeScript type-check. Existing media quiz modes remain separate; additional puzzle/challenge formats are a later scoped extension, not an unverified completion claim.



Harden Daily Drop, rankings, sessions, RSVP/waitlists, discussions, tournaments, community seasons, calendar and showcase. Expand media quizzes, clue systems, puzzle rounds, teams, scoring and persistent game sessions with explicit finite state machines.

**Exit gate:** repeated clicks and concurrent actions cannot duplicate votes, answers or transitions; every activity has ownership, expiry, moderation and recovery tests; no personal watch/read/play progress ledger is introduced.

#### Phase 7 — Profiles, provider identity and Custom Roles (11,000)

**Status: Code phase completed — 20 November 2026.**

AniList and Steam connections are guild-scoped, can be removed independently, and do not override profile consent. Public profile and provider visibility are evaluated on every read; hidden provider accounts are not fetched, public visibility can be revoked immediately, and the owner retains a private preview. Affinity and Server Taste are opt-in and retain minimum-cohort protections. Contribution attribution reuses approved, server-visible Archive records.

Custom Roles retain member/admin creation and removal workflows, role-name and icon validation, safe anchor placement, role hierarchy checks, event-driven member lifecycle, and periodic reconciliation. Saved-role restoration now rechecks Manage Roles, managed-role and position constraints before assigning an existing role; unsafe state remains saved for later recovery.

PostgreSQL and unit tests cover privacy changes, provider visibility, unlink behavior, guild isolation, minimum cohort, and the saved-role assignment guard.

**Exit gate:** code-level privacy and hierarchy checks are complete. Real provider connections, Discord role hierarchy, managed-role behavior, member departures/rejoins and permission changes still require owner-controlled live acceptance. No release or production cutover is implied.

#### Phase 8 — Media subscriptions and bounded automation (5,000)

**Status: Code phase completed — 20 November 2026.**

Guild-scoped subscriptions, provider-change snapshots, AniList/TMDB/IGDB release alerts, daily/weekly configurable digests, and bounded media-only automation are implemented. Automation rules are inspectable and pausable per guild; provider events are deduplicated using provider/source/title/time identity; workers use PostgreSQL `SKIP LOCKED`, expiring leases and claim tokens; deliveries have bounded retries and preserve the provider source URL. Pausing a digest fails its pending/processing deliveries and clears their claim tokens, while resuming the schedule does not revive those explicitly failed deliveries.

PostgreSQL integration tests cover competing rule and delivery workers, guild isolation, stale rule claims, HTTPS-only event sources, duplicate event suppression, retry token replacement, idempotent discussion creation, pause/resume, and terminal digest state. Pure tests cover category validation and provider-event identity.

**Exit gate:** code-level durability and idempotency coverage is complete. Live provider credential/rate-limit checks, channel deletion/permission loss, and real Discord announcements/discussions still require owner-controlled acceptance. Publication schedules for books, chapters and volumes remain unavailable unless an approved provider offers dependable dates or update events. No production cutover is implied.

#### Phase 9 — Knowledge Atlas and dashboard experience (16,000)

**Status: Code phase completed — 20 November 2026.**

Canonical provider identity now spans AniList, TMDB, Steam, Google Books, MangaDex, Kitsu and Open Library URL patterns, with a conservative one-time backfill for legacy edges. Unknown URLs and duplicate inferred pairs preserve title/category fallback. Atlas traversal combines provider and visible community links at every bounded hop, enforces guild/global scope, suppresses cycles and duplicate nodes, and caps the graph at three hops and forty nodes.

The UI and private bridge support search, category, source-kind, relationship, provider, provider-ID and evidence filters; category clustering; shortest-path selection; and bounded JSON/SVG/PNG export. The export carries the same filtered graph and source/evidence labels as the interactive view. Rust/Axum re-authorizes the guild and validates all Atlas parameters; the TypeScript bridge repeats guild membership and setup checks. Image fetches are restricted to approved HTTPS provider hosts, with redirects disabled and timeouts enforced.

Dashboard session/OAuth/rate-limit state now uses SQLite WAL, allowing three local Rust dashboard instances behind Nginx `least_conn` to share login and refresh coordination. PostgreSQL remains the bot's authoritative domain store. The documented topology keeps SQLite on local same-host storage and leaves the Discord gateway as one service.

Tests cover canonical identity, ambiguous legacy backfill, guild visibility, multi-hop cycles and node caps, provider/evidence filters, clusters, shortest paths, export provenance, API validation, bridge authorization and cross-instance SQLite state.

**Exit gate:** code-level Atlas and dashboard implementation is complete. Live provider, OAuth, production Nginx/systemd, WAL backup/restore, host filesystem and Discord acceptance remain under Phase 10/owner release verification. No production launch is implied.

#### Phase 10 — Tests, security verification and operations (12,000)

Invest in provider fixtures, PostgreSQL integration coverage, two-guild isolation, Discord interaction simulations, dashboard auth/session tests, browser tests, security regressions, observability, backup verification, deployment checks and release/rollback tooling. Add live acceptance only with owner-provided credentials and target environments.

**Exit gate:** the exact PR head passes required CI; dependency versions are locked and audited; staging security checks produce reviewable evidence; PostgreSQL and private-object restore are rehearsed; Discord/OAuth/provider acceptance is signed off before release.

### Open-source tooling and import policy

Prefer the existing dependencies before adding another package. The v3 runtime already includes undici, axios, Playwright, Cheerio, p-limit, p-retry, fast-xml-parser, robots-parser, sharp, the AWS S3 SDK, pg and Discord.js. The dashboard already uses Next.js/React and the existing Rust/Axum service. Add a new import only when a phase has a concrete gap, the project licence is compatible, the package is maintained and a focused test proves its value.

For security and verification, the practical candidates are:

- [CodeQL](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/) for source analysis across TypeScript, Rust and GitHub Actions; [Semgrep](https://github.com/semgrep/semgrep) can supplement it with project-specific rules for unscoped database access, missing component authorization and unsafe URL-fetch call paths.
- [OSV-Scanner](https://google.github.io/osv-scanner/) for open-source dependency advisories and [Trivy](https://trivy.dev/docs/latest/target/filesystem/) for filesystem/container vulnerabilities, secrets, misconfiguration and licence checks. These become materially more reproducible once package and Cargo lockfiles are committed.
- [OWASP ZAP Baseline](https://www.zaproxy.org/docs/docker/baseline-scan/) for passive web checks against an owner-controlled staging deployment. It is not a substitute for authorization tests or a full penetration test.
- Keep the existing npm audit and cargo audit checks, but cover the root bot dependency tree as well as the dashboard frontend and Rust backend.

Use [ARTEX](https://github.com/BaaRai/ARTEX) as a **security-methodology reference**, not as a dependency to embed into the bot: its scope gates, explicit task allow-lists, human approval boundaries, execution budgets and evidence-linked findings are useful design principles for a controlled security review. Re-check target scope at the enforcement boundary instead of trusting an upstream scanner or client assertion. Any active testing must stay within an owner-controlled, explicitly authorized environment.

Python, C++ or another language may be useful for a separate offline tool when it has a clear operational benefit, but adding another runtime solely to increase code volume would fragment this TypeScript/Rust application and would not count toward the 100k TS/TSX budget.



### Measurement rules

- The allocation is a planning envelope. It does not imply every subsystem must reach its allocation.
- A feature is counted only when it has working behavior, tests, error handling and documented ownership.
- Prefer shared domain services over duplicated command-specific logic.
- Tests count toward the target because a mature multi-guild bot needs meaningful regression and integration coverage.
- Do not split a file or expand comments merely to increase the count.
- If a provider or feature is unsupported, leave the corresponding budget unused rather than ship a stub.

## 6. Non-negotiable product and safety boundaries

- No personal watch/read/play progress, media streaks, episode/chapter completion history or personal media library.
- No generic reminders, birthday engine or unrelated productivity automation.
- No broad theme marketplace or general server customization suite; Custom Roles remain the selected customization feature.
- No invite analytics product, broad server analytics suite or general moderation platform.
- No unsupported storefront/API scraping. Prefer documented APIs and verified feeds.
- No general music player; Soundtrack Discovery stores and links permitted media metadata/curation.
- Global Archive and graph data require explicit visibility; guild-scoped data must not leak across servers.
- Provider facts, provider recommendations, local similarity results and community proposals must remain distinguishable.
- Keep the standalone /help, /privacy and /feedback commands independent.

## 7. Completion definition

A large TypeScript codebase is not the goal by itself. The goal is a reliable, secure and useful Discord product in which the fifty environments are connected through canonical media/community records, every selected legacy feature has an evidence-backed disposition, the bot works across multiple guilds, and operators can deploy and recover it safely.

The existing PR #17 remains Draft until the migration parity audit, automated checks, data compatibility and production acceptance are all complete.

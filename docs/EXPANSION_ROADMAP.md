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

### Discovery — /discover

| # | Environment | Build target |
|---:|---|---|
| 1 | Discovery Metropolis | Category-aware search, provider filters, browse, random, trending, detail cards, compare and recommendations. |
| 2 | Community Knowledge Atlas | Image-backed, permission-aware graph for works, creators, franchises, adaptations, Archive records and community edges. |
| 3 | Creator Explorer | Reliable author, artist, illustrator, editor, translator, studio, director, developer and publisher credits/workographies. |
| 4 | Franchise Explorer | Canonical franchise membership, sequels, prequels, spin-offs and alternate versions with source labels. |
| 5 | Adaptation Explorer | Source-to-adaptation paths across supported books, novels, manga, anime, games, film and TV. |
| 6 | Comparison Studio | Category-specific comparisons with missing-data handling, field-level source provenance and fair normalization. |
| 7 | Books & Editions | General books, novels, light novels and translations with supported ISBN, edition, publisher, language and volume details. |
| 8 | Availability Explorer | Verified streaming/catalogue/store availability with region and provider attribution; never infer absence from missing data. |
| 9 | Media Release Explorer | Supported episodes, chapters, volumes, webnovel updates, publications, films, TV and game release data. |
| 10 | Metadata Source Explorer | Provider IDs, data freshness where available, field provenance, missing metadata and community proposals. |

### Archive — /archive

| # | Environment | Build target |
|---:|---|---|
| 11 | Archive Metropolis | Unified submit, browse, search, filter, review, edit, remove, configure and moderation workflows. |
| 12 | Collection Studio | Mixed-media collections, ordering, attribution, collaboration and publication controls. |
| 13 | Archive Trails | Curated paths with transitions linking panels, quotes, scenes, soundtracks, fanworks and theories. |
| 14 | Visual Archive Gallery | **Core implemented in Archive browse:** approved category results now include permission-checked image thumbnails, with full image previews and attachment links in entry detail. |
| 15 | Soundtrack Discovery | Soundtrack metadata, media links, creator browsing and curated soundtrack collections; no general music player. |
| 16 | Curation Studio | Featured collections, category indexes, spotlights, trails and curator attribution. |
| 17 | Community Spotlights | Approved older contributions, creator features and curated highlights surfaced through Community. |

### Community — /community

| # | Environment | Build target |
|---:|---|---|
| 18 | Community Metropolis | One home for Daily Drop, rankings, sessions, discussions, competitions, calendar and showcases. |
| 19 | Daily Media Centre | Scheduled media prompts, trivia, mystery titles, quotes, polls, creator features and Archive spotlights. |
| 20 | Ranking Studio | Candidate submissions, voting rules, vote changes, closing, tie handling and historical results. |
| 21 | Tournament Centre | Brackets, elimination rounds, multi-stage voting and explicit tie/eligibility rules. |
| 22 | Session Centre | Watch, Read, Play and Discuss events with nominations, hosts, RSVP, waitlists and event history. |
| 23 | Discussion Centre | Media-linked discussions with spoiler boundaries for supported episode/chapter/volume/season units. |
| 24 | Media & Community Calendar | Provider-dated releases and community events in one timezone-aware filterable calendar. |
| 25 | Community Seasons | Configured periods combining existing Drops, rankings, sessions, challenges and spotlights without duplicate records. |
| 26 | Community Showcase | Published collections, trails, creative contributions, completed ranking results and event highlights. |

### Games — /play

| # | Environment | Build target |
|---:|---|---|
| 27 | Interactive Game Metropolis | Game catalogue, solo/team entry, join/resume controls, state persistence and result presentation. |
| 28 | Trivia Arena | Source-backed questions, difficulty, review, provenance and solo/team/hosted rounds. |
| 29 | Mystery Media | Layered clues for hidden works, franchises, creators, adaptations and games. |
| 30 | Guessing Arena | Title, creator, release period, franchise and other media-identification rounds. |
| 31 | Team Games | Cooperative/competitive teams, membership, scoring and persistent round state. |
| 32 | Challenge Centre | Themed media discovery tasks, seasonal challenges and community puzzles with published rules. |
| 33 | Quiz Pack Studio | Community question packs, answer keys, accepted alternatives, references, review and revision history. |
| 34 | Media Puzzle Room | Media word puzzles, relation puzzles, franchise-connection puzzles and cooperative clue chains. |

### Profiles — /profile

| # | Environment | Build target |
|---:|---|---|
| 35 | Profile Metropolis | Supported Discord/provider details, contributions, visibility and profile presentation. |
| 36 | Account Connection Centre | Link, unlink, inspect and consent-manage AniList, Steam and other verified connections. |
| 37 | Media Affinity | Opt-in comparisons with transparent signals and privacy controls. |
| 38 | Community Taste Explorer | Aggregate, opt-in guild tastes with minimum cohort thresholds and no individual record exposure. |
| 39 | Contributor Centre | **Implemented in profile:** recent approved Archive entries and active server-visible collection/Trail attribution, filtered to the current guild. |
| 40 | Community Creations | Browse member-created, moderated Archive work from canonical records. |
| 41 | Profile Showcase | **Core implemented:** opt-in public profile with configured AniList/Steam summaries and recent public community work; no personal tracking. |

### Custom Roles — /custom-role

| # | Environment | Build target |
|---:|---|---|
| 42 | Custom Role Metropolis | Existing member/admin role lifecycle, selection, assignment and configuration behind one command. |
| 43 | Role Design Studio | Supported role palettes, gradients, icons, previews and styling within Custom Roles only. |

### Media notifications and automation — /settings, /discover, /community

| # | Environment | Build target |
|---:|---|---|
| 44 | Media Follow Centre | Subscriptions to supported titles, creators, franchises and categories for release/metadata changes. |
| 45 | Media Alert Centre | Episode, chapter, publication, film, TV, game and verified catalogue updates. |
| 46 | Media Digest Studio | Daily/weekly media-only digests with category, entity, region, timezone and destination controls. |
| 47 | Media Automation Studio | Bounded, auditable, idempotent media-triggered workflows connecting releases, calendars, discussions and Atlas projections. |

### Atlas and operations — integrated views, not extra commands

| # | Environment | Build target |
|---:|---|---|
| 48 | Graph Export Studio | Permission-filtered graph paths, creator/franchise maps and Archive collection graphs in useful image formats. |
| 49 | Feature Diagnostics | Restricted checks for Discord permissions, channels, providers, assets, jobs and relevant services. |
| 50 | Data & Backup Centre | Authorized migration status, backup verification, recovery and selected data-safety reporting. |

## 3. Media coverage strategy

Media families remain distinct while reusing provider adapters only where fields and semantics genuinely overlap.

| Family | Planned depth |
|---|---|
| Anime | Titles, alternate titles, formats, episodes/airings, studios, seasons, creators, adaptations and release data. Continue AniList for supported data. |
| Manga | Manga, manhwa and manhua distinctions where provider data permits; chapters, volumes, authors, artists, serialization and adaptations. |
| Light novels | Authors, illustrators, publishers, language, volumes, editions and adaptation links where sourced. |
| Books and general novels | ISBNs, editions, publishers, translators, editors, publication dates, languages and series. |
| Webnovels | Author, supported platform, chapter count/update date, publication status and print/adaptation relationships. No scraping restricted catalogues. |
| Video games | Steam and IGDB integration, platforms, developers, publishers, release dates, genres, franchises and supported ratings. Extend existing helpers. |
| Film and television | TMDB-backed discovery, seasons, episodes, cast/crew, runtime, release dates and franchise links where provider coverage supports them. |
| Future integrations | Add providers only after official API access, terms, rate limits, stable IDs and credential model are verified. Letterboxd profile linking is a research item, not an assumption of unrestricted API access. |

## 4. Dependency-aware implementation phases

The phase status below is an implementation audit, not a feature promise. Status reflects code and tests found in lemegeton-v3 as of 2026-11-13. A command label or helper file alone does not count as a completed user workflow.

### Phase status board

| Phase | Current status | Evidence already present | Main remaining exit gate |
|---|---|---|---|
| 0 — Migration integrity | **Code migration complete** | PR #17 records TypeScript parity, Python removal, branch synchronization and the migration disposition. | Live Discord, production database/storage/provider and dashboard OAuth acceptance. |
| 1 — Runtime, data and security | **Foundation implemented; acceptance in progress** | Config validation, guild setup gates, guild-scoped data, consent, issue logs, permission helpers, permanently protected Manage Server-only /language command, CI, backup rehearsal and diagnostics. | Target-environment permission/data/rollback tests and current-head CI. |
| 2 — Discovery and metadata | **In progress** | AniList, TMDB, IGDB, Steam, Google Books, comparisons, airing, trailers, creators, relations and regional availability have implementations and fixture tests. Google Books edition metadata was expanded in this implementation pass. | Provenance at field level, provider contract edge cases, and a supported webnovel metadata source. |
| 3 — Archive and contributions | **Core workflows and gallery previews implemented; curation incomplete** | Submissions, moderation/reports, private asset storage, cleanup, permission-filtered image previews, collections, collaborators and Archive Trails. | Dedicated curation/spotlight workflow and end-to-end visibility tests for every share/export surface. |
| 4 — Community and games | **Core activities implemented; competition formats incomplete** | Daily Drop, ranked voting, sessions/RSVP, spoiler discussions, release calendars/digests, quiz packs and persistent game sessions exist. | Tournament brackets, community seasons/showcases, richer puzzle/challenge modes and interaction tests. |
| 5 — Profiles and Custom Roles | **Profile showcase implemented; live acceptance pending** | Guild-scoped AniList/Steam linking, privacy preferences, affinity/taste, leaderboard, recent approved contributions, active collections/Trails and custom-role lifecycle helpers. | Live Discord role-hierarchy/lifecycle acceptance and visibility regression tests. |
| 6 — Notifications and automation | **Basic scheduled delivery implemented; entity automation incomplete** | Completed/cancelled AniList notifications and guild release digests have scheduling/delivery paths. | Title/creator/franchise follows, more provider release kinds and bounded trigger workflows. |
| 7 — Knowledge Atlas and dashboard | **Bounded two-hop exploration implemented; advanced graph work incomplete** | Typed provider/recommendation/community edges, guild visibility filters, direct relationship lookup, tested breadth-first expansion (2 hops / 24 nodes), provenance-aware dashboard graph and static image render. | Stable provider-ID canonicalization, node/edge search, relationship filters, pathfinding, clustering, rich node details and permission-equivalent graph export. |
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

**Already present:** AniList anime/manga/light-novel search, creator credits, airing schedules, trailers, relations and recommendations; TMDB film/TV search, TV seasons/episodes, creators and regional watch-provider data; IGDB and Steam game discovery; Google Books search; media comparisons, cross-media ranking and relationship suggestion/review.

**Completed in this implementation pass:** Books & Editions now uses documented Google Books volume fields: subtitle, all supported ISBN forms, language, print type, main category, series display/order metadata and safe preview/info links. Existing isbn remains a backward-compatible ISBN-13-then-ISBN-10 value.

**Remaining delivery:**
- Add field-level provenance to detail cards and comparisons: source provider, stable provider ID, source link, and a clear unavailable/unsupported state.
- Verify provider-specific failure behavior for timeout, HTTP 429, transient 5xx, malformed payload, missing fields and schema drift. Retries must be bounded and respect Retry-After where applicable.
- Keep category-specific metadata distinct: manga chapters/serialization must not be presented as book volumes; game platforms must not be treated as TV distribution; movie collection membership must not imply story chronology.
- Complete edition grouping only when provider identifiers support it. Do not infer that two editions are the same work from title similarity alone.
- Webnovel metadata remains gated: do not scrape login-bound or undocumented platform endpoints. Add a provider only after its official public API/feed, access terms, rate limits and stable metadata identifiers are verified.
- Add representative fixtures from each active provider and assert normalization with partial/missing data.

**Exit criteria:** each displayed metadata field has a source or is explicitly unavailable; relationship provenance is visible; comparison tests cover missing and incompatible fields; unsupported webnovel integration is clearly deferred rather than presented as working.

### Phase 3 — Archive and contribution workflows

**Objective:** make the Archive a reliable, attributed, permission-aware community contribution system.

**Already present:** the unified Archive command; category-specific contribution forms; upload classification/limits; moderation queues and reports; server/global visibility rules; S3-compatible storage and cleanup retries; collections, collection collaborators, ordered Trail entries and Trail browsing.

**Completed in this pass:** category browse results now show permission-checked image thumbnails from private S3 assets or supported legacy Discord attachments. Opening an entry retains the full image preview and lists other attachments as links. Asset URLs are resolved only after the Archive query has enforced guild visibility; no duplicate gallery records or public asset URLs are introduced.

**Remaining delivery:**
- Add a dedicated curation/spotlight view over approved canonical Archive entries. Do not copy records into a second gallery database.
- Add explicit curation/spotlight records or a clear featured status, with curator attribution, publication window and guild/global scope.
- Ensure collection and Trail reads re-check each referenced entry's current visibility and moderation status. A previously approved collection must not keep showing an entry later made private or removed.
- Verify cross-guild references and global Archive access at each page, component, attachment and export action.
- Finish soundtrack records with permitted metadata/links and source attribution. Uploaded audio/video is not a licence to redistribute copyrighted media.
- Add lifecycle tests for asset replacement, deletion, missing legacy Discord attachment and failed private-object cleanup.

**Exit criteria:** upload, review, browse, collection and Trail workflows pass permission tests; removed/private entries disappear from every derived view; global content requires configured permissions and contributor visibility choice; storage cleanup is recoverable.

### Phase 4 — Community and media games

**Objective:** deliver repeatable guild activities with clear ownership, durable state and fair results.

**Already present:** scheduled Daily Drop with approved contributions; rankings with candidate review/voting/results; Watch/Read/Play/Discuss sessions with RSVP and waitlist; spoiler-aware discussions; release calendars/digests; quiz packs, question review and persistent game sessions.

**Remaining delivery:**
- Implement tournament brackets as a distinct bounded workflow: candidate eligibility, seeding, round state, vote windows, ties, withdrawals, audit and final results. Reuse ranking/user records where valid; do not model a bracket as an unstructured text poll.
- Add Community Seasons that reference existing Drops, rankings, sessions, challenges and spotlights rather than duplicating those records.
- Add a Community Showcase for finished, permission-checked Archive collections/Trails and completed event results.
- Extend Play with media-backed puzzle/challenge rounds only after answer normalization, source provenance, spoiler handling, timeout and host-control rules are defined.
- Test simultaneous votes/answers, repeated component clicks, expired sessions, host departure and guild isolation.
- Keep RSVP and session history separate from individual watch/read/play completion. Do not introduce personal progress tracking.

**Exit criteria:** each activity has a finite lifecycle and idempotent transitions; vote/answer state cannot be duplicated by repeated interactions; moderation and host permissions are tested; event records can be reused by calendar, Atlas and showcase without copies.

### Phase 5 — Profiles and Custom Roles

**Objective:** complete optional identity connections and contribution presentation without turning Lemegeton into a personal tracker.

**Already present:** guild-scoped AniList/Steam profile linking and unlinking; public-profile and sharing preferences; affinity and minimum-cohort guild taste; AniList leaderboard; custom-role creation/configuration, picker, image validation, hierarchy checks, lifecycle, restore and reconciliation.

**Completed in this pass:** the profile now shows up to five recent, approved, server-visible Archive entries, active server-visible collections owned or edited/contributed to by the member, and active server-visible Trails owned by the member. Queries remain scoped to the current guild and reuse canonical Archive records. The showcase is visible only through the existing public-profile gate (or the member's private preview). It does not add personal media lists or progress tracking.

**Remaining delivery:**
- Re-check profile visibility and connection consent on each view; unlink must remove tokens/associations and derived access.
- Verify custom-role assignment and recovery with real Discord role hierarchy, managed roles, member departures/rejoins, server boosts and permission changes.
- Provide explicit user-facing states when a provider cannot supply a field or the account connection has expired.

**Exit criteria:** every public field has a visibility rule; unlink and privacy changes take effect immediately; aggregate data respects minimum-cohort thresholds; role operations survive restart/reconciliation and never assign above the bot's role.

### Phase 6 — media notifications and bounded automation

**Objective:** notify users/guilds about selected media changes and connect approved media workflows without becoming a generic reminder service.

**Already present:** a 15-minute scan for recently finished/cancelled AniList anime/manga, delivery deduplication per guild/media, guild release-digest schedules for supported anime/TV/movie releases, timezone-aware scheduling and retryable delivery state.

**Remaining delivery:**
- Add subscriptions to provider-backed title, creator and franchise IDs with explicit per-guild destination and enable/disable controls.
- Expand alerts to chapter/volume/publication/game releases only when a provider exposes reliable release dates or update events. Never fabricate chapter dates.
- Add daily/weekly digest selection from followed entities and configured categories; preserve original provider timestamp and the guild timezone.
- Add a small explicit automation rule model for approved media triggers (e.g. a verified release may create a calendar item or discussion proposal). Each rule needs a trigger allowlist, target allowlist, preview, idempotency key, audit and disable control.
- Handle provider outage, duplicate events, changed release date and missing destination without losing or duplicating deliveries.
- Keep all scheduling media-only. No birthdays, general reminders, productivity tasks or unrelated automation.

**Exit criteria:** rules are bounded and per-guild, delivery is idempotent, every event can be traced to a provider/source, retries are safe, and a moderator can inspect/disable each active rule.

### Phase 7 — Knowledge Atlas and dashboard

**Objective:** make canonical media relationships explorable while preserving provenance and visibility.

**Already present:** normalized media categories/titles; stored provider, recommendation and community relationship edges; guild visibility filtering; direct relationship and related community-record lookup; a static PNG snapshot renderer; and a dashboard Atlas view.

**Completed in this implementation pass:** the dashboard Atlas bridge now performs deterministic breadth-first traversal for up to two relationship steps, capped at 24 nodes and eight queried relationships per node. Cycles and ancestor back-edges are suppressed, repeated nodes are deduplicated while alternative paths can remain visible, direct root relationships remain backward-compatible, and the guild-scoped lookup is applied again at every hop. The dashboard draws actual parent-to-node edges, labels node depth and exposes the truncation state. tests/atlas.test.ts covers cycle suppression, multi-hop discovery, node bounds and category/edition identity.

**Current limitation:** canonical identities are still derived from normalized title, category and optional HTTPS URL rather than provider IDs. Pathfinding, clustering, rich node details and graph export are not implemented.

**Remaining delivery:**
- Introduce stable canonical node identities using provider IDs where providers expose them, while retaining the normalized title/category/edition fallback. Preserve work-versus-edition distinctions.
- Add graph search and filters for relationship type, provider/community provenance and guild/global visibility.
- Expose edge evidence and source links. Community proposals must remain visibly different from provider-confirmed relationships and recommendations.
- Build graph pathfinding and focused views (creator, franchise, adaptation, collection) with caps that protect query cost.
- Re-check visibility at each traversal step and at render/export time; filtering only the root node is insufficient.
- Add image-backed node thumbnails only from approved provider URLs or permission-checked Archive assets.
- Complete graph export with size/node limits, source/provenance legend and the same permissions as interactive views.
- Keep the Rust/Axum service as the dashboard authorization/API boundary; do not add a second backend.

**Exit criteria:** graph traversal is bounded and deterministic; no cross-guild/private edge leaks through paths or exports; each edge shows source kind/evidence; traversal tests cover cycles, duplicate nodes and node limits; path/export tests cover hidden Archive entries and missing provider records.

### Phase 8 — operational hardening and launch

**Objective:** prove the service can be deployed, observed, restored and rolled back safely.

**Already present:** TypeScript and dashboard/Rust workflows, repository-health workflow, production Dockerfile and Compose validation, startup checks, server diagnostics, PostgreSQL backup/restore rehearsal and a separate live-acceptance workflow.

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

A phase is not complete because its slash-command option exists. It closes only when behavior, state transitions, permissions, privacy, failure cases, tests and documentation meet its exit criteria. The phase status board and detailed phase definitions above are the single source of truth; do not maintain a second abbreviated checklist that can drift out of sync.

## 5. 100,000-line TypeScript budget

The following is a long-range engineering allocation, not a deadline or reason to write filler. Count only authored, maintained TypeScript/TSX source and tests. Exclude generated code, dependencies, lockfiles, build output, vendored code, copied provider schemas and empty placeholders. The target can be reduced if the actual product does not require the code.

| Area | Planned TS/TSX LOC | What makes the code substantive |
|---|---:|---|
| Runtime, configuration, command routing and shared interaction infrastructure | 7,000 | Typed gateway lifecycle, component routing, authorization, error handling, structured logging and reusable Discord interaction state. |
| PostgreSQL domain layer, migrations and data compatibility | 8,000 | Guild-scoped repositories, constraints, transactional workflows, migrations, compatibility adapters and recovery tooling. |
| Provider integrations and metadata normalization | 10,000 | AniList, Steam, IGDB, Google Books, TMDB and approved future sources with typed responses, cache/rate-limit behavior and contract tests. |
| Discovery and media intelligence | 9,000 | Category-aware search, comparison, recommendations, creators, franchises, adaptations, releases, books and provenance. |
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

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
| 14 | Visual Archive Gallery | Permission-preserving visual category galleries and previews. |
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
| 39 | Contributor Centre | Permission-filtered public Archive contribution attribution. |
| 40 | Community Creations | Browse member-created, moderated Archive work from canonical records. |
| 41 | Profile Showcase | Curated opt-in presentation without personal watch/read/play libraries or progress tracking. |

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

## 4. Dependency-aware implementation sequence

### Phase 0 — migration integrity and branch convergence

- Resolve the existing PR's merge conflict with the current multi_guild base while preserving both branches' changes.
- Keep the current PR head as the only implementation target; do not create another PR.
- Complete the source-to-destination map from docs/MIGRATION_PARITY_AUDIT.md.
- Port missing regression coverage before broad feature expansion.
- Verify Docker, Compose, startup, database compatibility and the Rust/dashboard authorization boundary.
- Exit only when no retained production behavior is merely assumed to be migrated.

### Phase 1 — runtime, data and security foundation

- Complete configuration validation, gateway lifecycle, command registration, structured logging and error routing.
- Finish PostgreSQL schema/transaction parity, idempotent migrations, backup/recovery and guild-scoped repositories.
- Standardize provider timeouts, retries, caching and rate-limit handling without masking permanent failures.
- Enforce guild-only interactions where required, owner/moderator authorization, permission re-checks on components, and secrets/diagnostic redaction.
- Finish /help, /privacy and /feedback as independent, tested command modules; retain /log access restrictions.

### Phase 2 — discovery and metadata quality

- Close gaps in compare, airing, trailers, TV seasons/episodes, creator credits, franchise navigation, cross-media recommendations and regional availability.
- Complete Books & Editions and webnovel metadata only against supported sources.
- Implement source provenance per relationship and important field.
- Add provider fixture tests for missing data, invalid responses, timeouts, rate limits and changed schemas.

### Phase 3 — Archive and contribution workflows

- Complete legacy panel parity inside the unified Archive.
- Finish asset upload/type limits, S3 privacy, attachment lifecycle, review/moderation, collections, collaborators and Archive Trails.
- Add image gallery, soundtrack records and curation only through canonical Archive records.
- Re-check source visibility at every browse, share, global view and export operation.

### Phase 4 — Community and media games

- Complete Daily Drop, rankings, sessions, discussion, event calendar and release digest workflows.
- Add tournament brackets, community seasons and showcases using existing domain records.
- Expand trivia, mystery media, guessing rounds, team play, puzzle modes and reviewed community quiz packs.
- Keep event RSVP separate from personal media history; never infer member watch/read/play progress.

### Phase 5 — profiles and custom roles

- Finish provider connection and revocation flows, privacy defaults, opt-in affinity and aggregate taste.
- Verify custom-role member/admin lifecycle, role hierarchy, asset safety, picker reliability and cooldowns.
- Add contributor/profile showcase views from already public, permission-checked records.

### Phase 6 — media notifications and bounded automation

- Add title/creator/franchise subscriptions and more supported release kinds.
- Implement guild digests with timezone-aware scheduling, retries and idempotent delivery.
- Add explicit workflow rules with bounded triggers, dry-run/preview, audit trails and per-guild enablement.
- Do not create a general reminder engine or unrelated task automation.

### Phase 7 — Knowledge Atlas and dashboard

- Add stable graph identities, typed relationships, relationship evidence, deduplication and graph versioning.
- Deliver image-backed nodes only from approved provider assets or permission-checked Archive assets.
- Add multi-hop exploration, search, path finding, filters, clustering, node details and graph export.
- Expand Next.js views while keeping Rust/Axum as the authorization and API boundary; do not introduce a parallel backend.

### Phase 8 — operational hardening and launch

- Complete health/readiness checks, provider/job diagnostics, backup verification and recovery exercises.
- Run multi-guild integration tests, interaction tests, data compatibility tests, permissions tests and container validation.
- Verify rollback and cutover procedures with the production owner.
- Retire any remaining legacy runtime only after measured parity and successful deployment acceptance.

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

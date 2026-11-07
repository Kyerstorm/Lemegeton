# Lemegeton v3 — Product & Engineering Specification

**Status:** Approved product direction; implementation in progress  
**Target branch:** lemegeton-v3  
**Pull request:** #17 — keep Draft  
**Implementation status:** TypeScript runtime foundation and the first AniList-backed `/discover` vertical slice are implemented; remaining feature migrations and production cutover are not complete.  
**Product scope:** Media Intelligence, Community Archive, Community Activities, Interactive Media Games, Social & Profiles, Custom Roles, Media Notifications & Automation, Community Knowledge Atlas, and Operations & Infrastructure.

---

## 1. Product direction

Lemegeton v3 is a substantial redevelopment of the existing multi-guild Discord bot into a Discord-native media discovery and community platform. Its centre is media knowledge and community participation: discovering works, understanding how they connect, contributing to shared resources, taking part in activities, and exploring a community's accumulated knowledge.

Lemegeton should not feel like a miscellaneous utility bot or a list of unrelated commands. It should feel like a coherent application with a small, learnable command surface and deep feature interfaces behind each command.

The v3 ambition is substantial. A long-term codebase in the region of 200,000 lines may emerge from the breadth of real product behavior, provider integrations, reliability work, dashboard functionality, and focused tests. That number is an aspiration for the possible scale of the product, not a line-count acceptance criterion. Do not generate boilerplate, duplicate modules, artificial abstractions, or empty integrations to reach it.

### 1.1 Product pillars

The selected product pillars are:

1. **Media Intelligence** — search, browse, recommendations, comparisons, creators, franchises, adaptations, metadata, and release information across supported media types.
2. **Community Archive** — the existing archive expanded into a curated, collaborative, searchable, mixed-media knowledge repository.
3. **Community Activities** — one connected system for daily activities, rankings, sessions, discussions, competitions, and community events.
4. **Interactive Media Games** — media-themed quizzes, guessing games, challenges, and group activities.
5. **Social & Profiles** — provider links, media-aware profiles, affinity, opt-in aggregate community taste, and contribution attribution.
6. **Custom Roles** — retain the existing custom-role feature and its member/admin workflows; do not expand this into a general server-customization suite.
7. **Media Notifications & Automation** — automations and notifications strictly tied to media releases, media updates, community media activity, and relevant provider data. No general-purpose reminders or unrelated automation.
8. **Community Knowledge Atlas** — a visual, image-backed, Obsidian-inspired graph connecting media, creators, archive contributions, collections, discussions, and community activity.
9. **Operations & Infrastructure** — production reliability, observability, provider health, data safety, security, deployment, testing, and recovery.

These are the approved areas for the expanded v3 vision. A broad moderation product, generic server analytics suite, birthday system, reminder bot, theme marketplace, general-purpose AI assistant, and miscellaneous utility collection are not part of this approved expansion. Existing archive moderation, permissions, privacy, and operational safeguards remain necessary to run the selected features safely.

### 1.2 Core principles

- Keep the number of user-facing slash commands deliberately small. Each command should open a substantial feature environment rather than a shallow one-action response.
- Use Discord's native buttons, selects, modals, autocomplete, context menus, embeds, threads, events, and supported attachment interactions to make the feature environment navigable.
- Do not create separate slash commands for CRUD operations, content formats, filters, or small variations of the same workflow.
- Do not hide the entire bot behind one global command such as /lemegeton. Major feature areas remain independently discoverable.
- Preserve useful existing commands by expanding them, merging them into a more complete feature command, or explicitly documenting why they are out of scope.
- Keep media types distinct. Anime, manga, light novels, books, webnovels, films, television, and video games must retain their appropriate metadata.
- Preserve provider attribution and distinguish provider-confirmed relationships from recommendations, local matching, and community suggestions.
- Preserve contributor authorship, moderation state, source information, and visibility scope for community content.
- Enforce guild isolation for all guild-owned data and moderation operations.
- Do not introduce personal watching, reading, listening, or gaming progress tracking as a default product feature.
- Do not describe a feature as AI-powered unless it actually calls and depends on an AI model.
- Do not claim a provider, API field, Discord component, or integration works until its current support has been verified.

### 1.3 Explicit exclusions and boundaries

The selected scope does not include:

- A general-purpose reminder service or personal task scheduler.
- Birthday registration, birthday DMs, or birthday announcements.
- General server analytics, invite leaderboards, or a broad server-management product.
- A separate moderation bot, ban suite, or general-purpose AutoMod replacement.
- A general AI chat/persona system or speculative AI assistant.
- A theme marketplace or broad appearance-customization system.
- Personal media libraries, watch/read/play histories, chapter tracking, or completion tracking beyond existing provider data displays that do not become a Lemegeton progress product.
- Generic automation unrelated to media or the selected community systems.
- A second database, bot backend, permissions system, storage system, or authentication system.

This does not remove essential permissions, reporting, review queues, audit records, privacy controls, diagnostics, and security checks that are directly required by the selected features.

---

## 2. Technology and architecture

| Area | v3 direction |
|---|---|
| Discord bot | TypeScript on Node.js with Discord.js |
| Dashboard frontend | Next.js, React, and TypeScript |
| Dashboard API | Keep the existing Rust/Axum service initially |
| Structured data | Keep the existing PostgreSQL database |
| Media objects | Keep the existing S3-compatible storage and private/public separation |
| Metadata | Migrate and reuse existing provider integrations after verification |
| Background processing | Durable, idempotent jobs using the existing infrastructure where suitable |
| Hosting | Preserve the current deployment model until the migration audit establishes what must change |

The repository currently has a Python/discord.py bot. The dashboard is a React + TypeScript frontend built with Vite and served by the existing Rust/Axum service. The frontend migration therefore means replacing the Vite frontend with Next.js; it does **not** mean rewriting the Rust API or creating a second bot backend.

The existing PostgreSQL schema, S3 asset registry, private/public storage rules, OAuth2 flow, bot bridge, and deployment configuration must be inspected before changes are made. Reuse them where they still meet v3 requirements. Do not introduce a parallel database, storage layer, command registry, permission model, or authentication system.

### 2.1 Bot responsibilities

The TypeScript bot owns:

- The Discord gateway and application-command registration.
- The feature command entry points and interaction routing.
- Component interactions, modal submissions, and supported attachment flows.
- Guild and user authorization at the point of every consequential action.
- Provider calls through separate provider adapters.
- Durable media and community workflows.
- Media notifications, release schedules, and selected community scheduling.
- Discord messages, threads, events, polls, and supported media presentation.

Discord handlers should validate the interaction, resolve the actor and guild context, authorize the operation, call a domain operation, and present its result. Provider-specific logic must not be embedded in button callbacks or command presentation code.

### 2.1.1 Gateway intents and guild membership

The TypeScript runtime currently requests the `Guilds`, `GuildMembers`, `GuildMessages`, and `MessageContent` gateway intents. Enable the privileged **Server Members Intent** and **Message Content Intent** for the application in the Discord Developer Portal before deploying this runtime.

- `GuildMembers` is required for booster/allowed-role eligibility changes, member join/leave handling, and full-guild Custom Role reconciliation.
- `MessageContent` is used by the configured Community Archive upload-channel workflow.
- When the bot cannot fetch a complete member list, Custom Role reconciliation must fail closed: skip the automatic archive pass, log the reason, and leave saved roles untouched. Do not infer ineligibility from a partial cache.

The PostgreSQL startup migration widens the existing `booster_roles.discord_id`, `guild_id`, and `role_id` columns to `BIGINT` when that legacy table exists. This is a widening conversion that preserves existing rows and its primary key; the legacy table remains read-only during the one-time import.

### 2.2 Dashboard responsibilities

The dashboard remains the control plane for the running bot, not a second Discord client or an alternate command registry.

The Next.js frontend should provide larger-screen interfaces for:

- Media exploration and the Community Knowledge Atlas.
- Archive and collection management where a browser is more suitable.
- Selected community activity management.
- Media notification configuration.
- The existing custom-role administration experience where appropriate.
- Guild feature configuration and operational diagnostics relevant to the selected scope.

The Next.js frontend uses the existing authenticated Rust API and bot bridge. Preserve Discord OAuth2, fresh guild authorization checks, origin/CSRF protections, owner-only bot-wide information, private bridge authentication, audit history, and confirmation of actual Discord synchronization before reporting a setting change as successful.

### 2.3 Domain boundaries

Keep domain behavior separate enough that each system can be tested and evolved without building a universal framework:

- Media providers and metadata normalization.
- Media identity and relationship records.
- Archive entries, collections, contributions, and media links.
- Community activities, events, votes, and discussions.
- Interactive game rounds and question content.
- Provider account links and profile presentation.
- Custom-role domain behavior.
- Media notification subscriptions and delivery.
- Knowledge Atlas graph projection and visualization data.
- Infrastructure operations and observability.

Share code where a real common operation exists. Do not force unrelated media categories or community workflows into one generic model merely to reduce file count.

---

## 3. Command architecture: a small surface with deep feature environments

### 3.1 The metropolis principle

A command should represent a complete feature environment. It should not represent one database operation.

For example, /archive opens the archive environment. Members can browse, search, filter, submit, edit, remove, curate collections, inspect attribution, and manage permitted contributions from that one entry point. There should not be separate commands for archive add, archive delete, archive search, archive collections, and archive moderation.

Apply the same principle to media discovery, community activities, profile management, and the other selected systems.

A command may open a home panel with tabs, selects, buttons, paginated views, and modals. The interaction design should remain focused: members should see the relevant actions for the selected item and their permissions, not an enormous wall of buttons.

### 3.2 Proposed public command surface

The target command surface should be intentionally compact:

| Entry command | Feature environment | Existing commands and workflows absorbed |
|---|---|---|
| **/discover** | Media Intelligence and entry to the Knowledge Atlas | /browse, /recommendations, /random, /trending, /compare, /franchise, /connections, /game, /airing, /tv-guide, media-region selection, supported Steam discovery, media release exploration, and graph exploration |
| **/archive** | Community Archive and curated collections | Existing /archive and Panels behavior, panel browsing, quotes, fanworks, moodboards, soundtracks, scenes, recommendations, theories, collections, submissions, search, upload configuration, and archive review |
| **/community** | Community Activities | /daily, /rankings, /sessions, /discussion, /calendar, /reading, /media-night, /release-calendar, /media-bracket, /adaptation-vote, community polls, and Archive Throwbacks |
| **/play** | Interactive Media Games | /media-quiz and new media guessing, trivia, team, and challenge experiences |
| **/profile** | Social & Profiles | /profile, /login, /user, /affinity, /anilist-leaderboard, /server-taste, and supported Steam/AniList account-linking and profile displays |
| **/custom-role** | Custom Roles | Existing member custom-role panel and administrator custom-role panel, unified into one command |
| **/settings** | Selected feature configuration and the existing control plane | Existing /dashboard, dashboard section toggles, and relevant /server-config controls for the selected v3 systems |

This is the target architecture, not a mandate to preserve every old spelling or every undocumented behavior. During the repository audit, verify each command and map it to one of these destinations or to an explicit out-of-scope decision.

The Knowledge Atlas is a substantial view inside /discover, not an additional public slash command. Its graph can also be opened from relevant archive entries, profiles, media cards, collections, discussions, and the dashboard.

The command surface must not grow merely because another tab, content category, action, or provider is added. A genuinely independent feature may justify a new command only after showing that it cannot reasonably belong inside the existing feature environments.

### 3.3 Command home panels

Each command should provide:

- A clear title and short description of the feature environment.
- A small set of primary navigation choices.
- Permission-aware actions.
- A predictable Back, Cancel, Confirm, and Home flow.
- Search and filtering close to the relevant content.
- Paginated results and useful empty states.
- Private intermediate interactions and explicitly public publishing steps.
- Contextual shortcuts from related media, archive, profile, or community records.

Avoid a generic mega-menu shared by every command. Each command should have a visual and interaction structure suited to its own domain.

### 3.4 Discord interaction features

| Discord feature | Intended use |
|---|---|
| Buttons | Navigation, confirmation, pagination, voting, RSVP, selection, and common actions |
| String select menus | Media types, archive categories, graph filters, collection selection, activity choices, and navigation |
| User/role/channel selects | Session participants, selected custom-role setup, destination channels, and permission configuration |
| Modals | Structured submissions, collection creation, media correction proposals, ranking setup, session proposals, discussion details, and custom-role configuration |
| Autocomplete | Media titles, creators, tags, collections, graph nodes, and supported provider identities |
| Attachment input | Supported single-file submissions where Discord and Discord.js expose the capability |
| Embeds | Media cards, archive entries, collection details, event information, profile summaries, and status feedback |
| Ephemeral responses | Private search selections, personal confirmations, staged forms, and permission-specific feedback |
| Public messages and threads | Published archive entries, activity announcements, sessions, and discussions |
| Discord Scheduled Events | Community sessions when available and suitable, with an internal event fallback |
| Discord polls | Simple temporary polls where their limitations are appropriate; use persisted Lemegeton votes for rankings and competitions |
| Context menus | Shortcuts from a message or supported Discord object into an existing feature workflow |

Use only components supported by the Discord API and the installed Discord.js version. If a capability is unavailable in the target client or library version, use a supported multi-step interaction. Do not assume file uploads can be placed inside modals. Preserve the configured archive upload-channel fallback for multi-file submissions.

### 3.5 Interaction state and permissions

- Bind interaction state to the initiating user and guild where appropriate.
- Re-check current permissions on every consequential action; hiding a button is not authorization.
- Persist durable submissions, votes, events, graph changes, and moderation decisions in PostgreSQL.
- Do not rely on a process-local component collector as the only record of durable state.
- Give expired, stale, unauthorized, disabled, or already-completed interactions useful responses.
- Defer long-running provider work correctly and use bounded timeouts.
- Keep message layouts within Discord's current limits.
- Never expose private provider credentials, private S3 paths, or unauthorized guild data in component IDs, embeds, or logs.

---

## 4. Media Intelligence — /discover

Media Intelligence is one of the main product pillars. /discover should be capable of handling the full supported media discovery journey, from a simple title search to a detailed exploration of the relationships between works and their creators.

### 4.1 Supported media families

- Anime.
- Manga, manhwa, and manhua where provider metadata distinguishes them.
- Light novels.
- General novels and books.
- Webnovels.
- Films.
- Television.
- Video games.

Do not force every category into an anime-specific data model. Retain category-specific metadata, provider identifiers, edition differences, release structures, and unavailable-field behavior.

### 4.2 Search and browsing

The discovery environment should support:

- Search across the relevant providers for a selected media category.
- Provider-aware search results, with source attribution.
- Search by primary title, alternate title, original title, and supported identifiers.
- Category-specific filters and sorting.
- Genre, theme, creator, studio, author, publisher, platform, format, status, release period, and other fields only where the provider supports them.
- Pagination and result refinement without restarting a search.
- Search history only where useful to the immediate interaction; do not silently create a personal media tracking history.
- Duplicate result detection and provider identity matching.
- Clear indication when a result is a probable match rather than a confirmed identity.
- Missing metadata and provider outages presented without breaking unrelated results.

### 4.3 Media detail environments

A selected title should open a detailed card or panel containing the supported fields for its category.

Potential information includes:

- Primary and alternate titles.
- Synopsis and description.
- Category, format, status, and release dates.
- Genres, themes, tags, and classifications.
- Authors, artists, illustrators, editors, translators, directors, studios, developers, and publishers.
- Seasons, episodes, chapters, volumes, runtimes, and platforms where supported.
- Images, covers, posters, banners, and source links where licensed and available.
- Provider ratings and counts with source labels.
- Franchise, adaptation, sequel, prequel, and related-work links with provenance.
- Regional availability only when a reliable provider supplies it.
- Related archive collections, discussions, sessions, rankings, and Knowledge Atlas nodes.

A field must not be fabricated to make cards appear complete. The user interface should distinguish unavailable data from a value of zero or an empty category.

### 4.4 Recommendations and discovery paths

Absorb recommendations, trending, and random discovery into /discover.

Support:

- Provider-generated recommendations, clearly labeled as provider-generated.
- Local similarity calculated from explicit metadata such as shared genres, themes, creators, or franchises.
- Related-title discovery.
- Cross-media recommendations.
- Random discovery with media type, genre, status, release period, and other supported filters.
- Trending and popularity views where the provider supplies suitable data.
- Creator-based discovery.
- Franchise exploration.
- Discovery paths that move from one title to another through a visible reason for the relationship.

Do not label simple genre overlap as an AI recommendation. Do not present community preference as an objective quality score.

### 4.5 Comparison

Provide a guided comparison environment for two or more supported titles.

Comparison fields should be category-aware. Examples include publication/release status, creators, formats, studios, genres, platforms, runtime, source ratings, and supported release details.

The interface should:

- Make mismatched media categories explicit.
- Compare only fields with meaningful semantics.
- Show provider/source labels.
- Identify unavailable values.
- Avoid false precision when providers use different rating scales.
- Offer links to each title's full detail environment and Knowledge Atlas node.

### 4.6 Creator and franchise exploration

Provide creator-focused discovery for supported authors, artists, studios, publishers, directors, developers, and other provider-supplied credits.

A creator page may include:

- Identity and provider links.
- Supported biography and credit details.
- Works by media category.
- Franchises and related creators where confirmed.
- Community archive references and collections.
- Community discussions and sessions.
- A Knowledge Atlas graph focused on that creator.

Franchise exploration should distinguish official franchise/relationship records from local matches and community-suggested links.

### 4.7 Media relationships and evidence

Store and present relationship evidence distinctly:

1. **Provider-confirmed** — supplied by a provider as a declared relationship.
2. **Provider recommendation** — a recommendation, not a continuity or adaptation claim.
3. **Locally calculated** — a match based on explicit and documented metadata signals.
4. **Community proposal** — suggested by a member and awaiting review.
5. **Community verified** — reviewed and accepted by an appropriately authorized reviewer.

Relationship types may include adaptation, source material, sequel, prequel, spin-off, side story, alternate version, shared franchise, same creator, compilation, remake, and other well-defined relationships.

Every relationship should have a source, provenance, confidence or review state where applicable, and a way to correct or report a bad link. Shared genres, a similar title, a collection membership, or a community suggestion must not be represented as proof of continuity.

### 4.8 Metadata correction and quality

Allow members to submit corrections or missing-data proposals where a provider record is incomplete.

- Preserve the provider's original value.
- Store the proposed value and supporting source.
- Route proposals to a review process scoped to the relevant system.
- Keep an audit record of accepted or rejected corrections.
- Do not overwrite provider-owned fields at the provider source.
- Make community additions visibly distinct from provider data.
- Prevent a correction in one guild from silently changing another guild's independently scoped community content.

### 4.9 Existing gaming discovery

Extend the existing Steam and IGDB functionality rather than creating duplicate gaming systems.

Potential workflows include:

- Game search and detail pages.
- Developer and publisher exploration.
- Franchises and related games.
- Platforms, genres, and release information.
- Steam store matching where available.
- Supported Steam profile and library enrichment.
- Game recommendations from provider data or explicit metadata signals.
- Cross-media connections between games and other works.
- Media-based notifications for supported game releases or updates.

Provider account linking and profile display belong in /profile; title discovery belongs in /discover.

### 4.10 Provider integration rules

Migrate only provider adapters that exist and can be verified in the repository. The documented provider set includes AniList, TMDB, Google Books, Novel Updates, Novel Phoenix, NovelFire, Novelist, IGDB, and Steam, but documentation alone does not prove an adapter is complete or currently healthy.

For each adapter, verify:

- Authentication and secret requirements.
- Supported media categories and fields.
- Stable identifiers and matching behavior.
- Rate limits and terms.
- Pagination and error behavior.
- Timeout and retry policy.
- Image and asset usage restrictions.
- Attribution requirements.
- Whether the provider supports the requested relationship or recommendation semantics.

Provider failures must be isolated. A failure from one source must not prevent another source from returning results.

---

## 5. Community Archive — /archive

The existing unified /archive system remains the single entry point for all archive operations. Panels remain a category, not the product itself. The v3 design must not turn the archive back into a panels-only system or recreate a separate Panels command.

The archive should become a community-owned, searchable knowledge repository with strong collection, attribution, visibility, and contribution features.

### 5.1 Existing categories to preserve

- Manga panels.
- Quotes.
- Fanworks.
- Moodboards.
- Soundtracks.
- Scenes.
- Community recommendations.
- Theories.

Retain useful current category behavior and its existing per-guild configuration. A category is an entry type; it is not a separate command or collection.

### 5.2 Archive entry model

An archive entry should be able to preserve, as appropriate:

- Entry type and title.
- Description or contextual note.
- Linked media identity and category.
- Source URL and original creator/source attribution.
- Submitting member and original contributor.
- Tags and searchable metadata.
- Visibility scope.
- Moderation and review state.
- Upload object reference where applicable.
- Creation and update timestamps.
- Collection memberships.
- Relationship links to other archive entries and Knowledge Atlas nodes.

Keep the underlying record structured enough for search and graph relationships without forcing every category to use identical fields.

### 5.3 Mixed-media collections

A collection is a first-class curated container, not another archive category.

A collection may contain quotes, soundtrack links, panels, fanworks, recommendations, scenes, theories, and other supported archive entry types together.

Collections should support:

- Title, description, cover image, tags, creator attribution, and optional linked media.
- Multiple contributors with per-collection permissions.
- Add, remove, reorder, and annotate entries.
- Search by title, creator, category, tag, and linked media.
- Collection history and meaningful edit attribution.
- Public/global, server-only, and other explicitly supported scopes.
- Collaboration invitations where the scope and permissions allow them.
- Collection ownership transfer under clear rules.
- Duplicate-entry detection and merge suggestions.
- Collection reports and moderation.
- Export of the structured collection metadata and its permitted assets.
- A graph view showing its linked media and related collections.

A collection must display who contributed each item. Editing a collection must not erase original entry authorship.

### 5.4 Archive Trails

Introduce curated Archive Trails as a presentation layer over existing archive entries and collections.

A trail is an ordered path through related contributions. For example, a trail may begin with a scene, continue to a quote, link to a soundtrack, and end at a theory or discussion.

Trails should support:

- A title, introduction, cover, and creator attribution.
- Ordered entries and optional explanations between steps.
- Links to the underlying archive records.
- Version history and contributor credit.
- Search and discovery.
- Visibility and moderation rules inherited from every referenced entry.

A trail must not expose an entry that the viewer cannot access. If an item becomes private, deleted, or unavailable, the trail should display a safe unavailable state or be updated by its curator.

### 5.5 Collaboration and curation

- Invite collaborators to contribute to a collection or trail.
- Define owner, editor, and contributor permissions at the resource level.
- Preserve each contribution's creator.
- Show meaningful revision history.
- Allow curation suggestions without granting write access.
- Support featured collections and curated indexes.
- Allow members to report problematic entries.
- Let authorized reviewers approve, reject, hide, or restore submissions.
- Preserve a reason and audit history for consequential moderation actions.

These are archive-specific safety and moderation controls, not the beginning of a separate general-purpose moderation system.

### 5.6 Submission and upload workflows

- Use guided interaction steps for category, title, metadata, tags, source, attribution, description, and visibility.
- Explain visibility before accepting a contribution.
- Preserve configured upload channels for multi-file submissions.
- Allow guild administrators to enable or disable accepted image, audio, and video uploads independently.
- Images remain a supported archive format; audio and video remain opt-in per guild.
- Validate file type, size, source, and storage policy before accepting an upload.
- Apply safe filename handling, content-type validation, and storage limits.
- Preserve the existing private-original and public-generated-media separation in S3.
- Ask contributors to confirm they have the rights or permission required to share an upload.
- Do not make private uploads public by copying them into a public bucket or exposing permanent object URLs.
- Provide clear status for pending, approved, rejected, and removed submissions.

Use supported Discord attachment inputs where available. Do not assume file uploads can be added to a modal. For multi-file workflows, use the configured upload channel and then associate the uploaded files with the archive submission.

### 5.7 Server-only and global archive visibility

- Server-only entries are visible only to members with access to their owning guild's archive.
- Global entries are explicitly opted into global discovery and must satisfy the relevant sharing and moderation requirements.
- A guild moderator can moderate that guild's submissions but must not gain moderation authority over another guild's entries.
- Global visibility does not silently transfer ownership or moderation control to the submitting guild.
- Collections and trails must respect the visibility of every referenced entry.
- A global collection cannot disclose a private entry through its title, preview, graph, counts, or exported metadata.
- Re-check visibility at display time, not only at submission time.

### 5.8 Search, discovery, and archive relationships

- Search by text, category, creator, tag, linked media, and collection.
- Filter by visibility and review status where the viewer is authorized.
- Browse featured collections, recently approved contributions, and curated indexes.
- Show related archive entries through explicit links and shared media references.
- Allow a member to open the linked title in /discover.
- Allow graph navigation into the Knowledge Atlas.
- Provide useful empty states and pagination.
- Avoid treating a shared tag as proof of a meaningful relationship.

### 5.9 Archive Throwbacks and spotlights

Retain resurfacing of older approved contributions as a feature of the Archive and Community systems.

- Highlight entries, collections, trails, quotes, soundtracks, fanworks, theories, and other approved categories.
- Allow per-guild frequency, channel, category, and visibility settings.
- Preserve original contributor attribution and link to the archive record.
- Avoid repeating the same item too frequently.
- Respect current visibility, deletion, moderation, and permission state at the time of display.
- Do not scrape old Discord message history to manufacture archive entries.
- Allow a spotlight to open the entry, its collection, related media, and its Knowledge Atlas neighborhood.

---

## 6. Community Activities — /community

The current Daily Drop, Community Rankings, Unified Community Sessions, Discussions, Release Calendar, and community competition concepts should become one connected Community environment.

Do not expose a separate slash command for each activity type. /community opens a focused panel with sections such as Today, Events, Rankings, Sessions, Discussions, Calendar, and Archive Spotlights. These sections are navigation destinations inside one command, not separate command registrations.

### 6.1 Daily Drop

Daily Drop is one configurable system with multiple media-focused formats:

- Question of the Day about a supported work or creator.
- Quote of the Day from permitted or community-submitted sources.
- Media trivia.
- Daily media recommendation.
- Archive spotlight.
- Community poll about media.
- Mystery title or media clue.
- Creator, franchise, soundtrack, or adaptation spotlight.
- Daily media comparison.
- Community-submitted themed prompt.

Per-guild settings should include enabled formats, destination channel, schedule, timezone, submission permissions, review requirements, and whether content is sourced from approved archive entries or external provider metadata.

Use buttons for responses and voting, selects for formats, and guided forms for submissions. The scheduler must be timezone-aware, idempotent, and safe across restarts. Avoid mandatory streaks, punitive participation mechanics, and spam.

### 6.2 Community Rankings and competitions

Build community-created rankings rather than replacing them with bot-generated scores.

Examples include favourite anime, manga, light novels, games, soundtracks, adaptations, characters where supported, creators, or seasonal selections.

A ranking can support:

- Creation and configuration by an authorized member.
- Candidate submission and optional review.
- Candidate descriptions, cover art, and linked media records.
- Voting through buttons or selects.
- Vote changes until the configured closing point.
- Visible eligibility rules and closing time.
- Guild-specific rankings and explicitly configured shared rankings.
- Seasonal, monthly, and all-time views where enough data exists.
- Tie handling and published results.
- Ranking history and comparison with prior community polls.
- Graph links to the ranked works and their relationships.

Community competitions may include single-elimination brackets, multi-stage voting, and adaptation-versus-adaptation polls. Keep community preference distinct from provider ratings or factual metadata.

Votes must be persisted, scoped correctly, and protected against duplicate or unauthorized submissions. Do not create an individual media progress or popularity score from participation.

### 6.3 Unified Community Sessions

Unify the existing Reading Hub and Media Night into one session system with four activity types:

- **Watch** — films, episodes, or other supported screen media.
- **Read** — manga, novels, webnovels, or books.
- **Play** — video games and supported group activities.
- **Discuss** — a focused discussion around a work, topic, or community collection.

A session flow should support:

- Session proposal and nomination.
- Member voting where enabled.
- Host and co-host assignment.
- Scheduling and timezone-aware display.
- RSVP, attendance capacity, and waitlists where useful.
- Reminders tied only to the session event itself.
- A destination channel and discussion thread.
- Discord Scheduled Events when available and appropriate.
- An internal event calendar fallback.
- Cancellation and rescheduling with clear member updates.
- Post-session community poll or archive contribution.
- Public session history at the event/community level.

This is not a request to track each member's personal reading, watching, or playing progress. RSVP and event attendance are event operations, not personal media progress records.

### 6.4 Spoiler-aware discussions

Discussions are linked to supported media identities, archive entries, collections, sessions, or community events.

Capture:

- Media title and category.
- Discussion title and opening prompt.
- Episode, chapter, volume, season, or other boundary where relevant.
- Spoiler scope and warning text.
- Destination channel or thread.
- Opening and optional closing time.
- Creator/host attribution.
- Related archive and Knowledge Atlas links.

Make spoiler status visible before a member opens or joins a discussion. A spoiler boundary must be understandable and specific where the source metadata supports it.

Discussion tools may include topic prompts, polls, pinned context, related discussions, and moderator controls required to maintain the discussion. Do not turn this into a general-purpose forum platform.

### 6.5 Media release calendar

The Community environment should connect community events with supported media release dates.

- Browse upcoming supported media releases.
- Filter by category, title, provider, and timeframe.
- Distinguish episode schedules, chapter updates, publication dates, film releases, TV dates, and game releases.
- Show timezones clearly.
- Support guild-level media digests.
- Link release records to /discover and the Knowledge Atlas.
- Allow a release to seed a discussion or community session proposal.
- Show source and update freshness.
- Do not invent dates, schedules, or regional availability.

The calendar is a community navigation view, while title-level metadata remains owned by Media Intelligence.

### 6.6 Archive spotlights and community seasons

Community spotlights can surface approved archive contributions, trails, collections, and media relationships. A community season can connect a theme, a sequence of Daily Drops, rankings, sessions, discussions, and a final community showcase.

These are optional curation structures. They must reuse existing archive and community records rather than duplicating them into a separate seasonal content database.

### 6.7 Community activity history

Keep event and community history at the appropriate level:

- Past sessions and outcomes.
- Closed rankings and published results.
- Completed community competitions.
- Daily Drop archive.
- Published discussions and their related media.
- Community season showcases.
- Archive spotlights already published.

Do not convert this into per-user watch, read, play, or completion histories.

---

## 7. Interactive Media Games — /play

/ play is the entry point for interactive media-themed games. It should be a dedicated game environment, not a general-purpose casino or unrelated arcade. Games should reinforce media discovery and shared participation.

### 7.1 Media guessing games

Potential modes include:

- Guess the anime, manga, book, webnovel, film, TV series, or game from source-backed clues.
- Guess a title from alternate titles or a translated title.
- Identify a creator from selected works.
- Identify a franchise from connected titles.
- Guess the adaptation from its source material.
- Identify a work from a short, properly sourced synopsis clue.
- Guess the release decade or year from a set of clues.
- Guess a soundtrack or soundtrack-linked work where reliable metadata exists.
- Identify a character or creator where the provider has suitable records and image-use permissions.
- Daily mystery media, connected to Daily Drop.
- Community-created quiz packs with source attribution and moderation.

Clues must not copy long copyrighted passages. Use short factual clues, licensed/allowed images, provider metadata, or original community-written questions.

### 7.2 Trivia and quiz experiences

- Single-question and multi-round quizzes.
- Multiple-choice, select-menu, and short-answer formats.
- Solo, team, and shared-server play.
- Host-created quiz sessions.
- Community-submitted questions with source and review state.
- Category and difficulty filters.
- Session timers where appropriate.
- Clear scoring and tie rules.
- Round summaries and shareable results.
- Optional integration with Daily Drop and Community Sessions.

Question correctness and source provenance must be established before a question is included in a public question pool.

### 7.3 Group challenges

- Team trivia.
- Cooperative mystery solving.
- Media-themed word and association games.
- Guess-the-creator challenges.
- Franchise connection challenges.
- Timed discovery challenges.
- Community puzzle events.
- Seasonal challenge packs.
- Server-specific private games.

Game state must persist sufficiently to survive bot restarts when the game is intended to be durable. Ephemeral one-shot interactions may remain transient when losing them does not corrupt a community record.

### 7.4 Game integrity and fairness

- Define scoring and tie handling transparently.
- Prevent multiple answers from the same member where the mode allows one answer.
- Make round and session state authoritative in the database where persistence is required.
- Avoid hidden scoring changes.
- Do not introduce wagering, cash prizes, or gambling mechanics.
- Avoid engagement mechanics that punish members for not participating.
- Ensure public results do not disclose private profile data.
- Keep game questions source-linked and reportable.

### 7.5 Game content management

Community question packs should include:

- Category and difficulty.
- Supported media identity.
- Question and accepted answers.
- Source/provenance.
- Contributor attribution.
- Review state.
- Revision history.
- Duplicate detection.
- Report and correction workflow.

An edit to a question must not silently invalidate a game round already in progress.

---

## 8. Social & Profiles — /profile

/profile combines provider account linking, supported profile displays, affinity, and opt-in aggregate community taste. It is not a personal library or activity-tracking command.

### 8.1 Provider connections

Preserve and migrate the supported account-linking flows, including AniList and Steam where the current repository actually implements them.

- Link and unlink supported provider accounts.
- Show connection state and last successful verification where available.
- Handle expired or revoked authorization safely.
- Protect OAuth tokens and provider secrets.
- Allow members to view the current linked provider.
- Explain what profile information is visible to other members.
- Support privacy controls for linked-account display.
- Do not claim support for a provider until its actual flow has been audited.

### 8.2 Profile presentation

A profile may combine:

- Discord identity and selected public Discord information.
- Linked AniList or Steam information where enabled.
- Provider profile links.
- Provider-supplied statistics and favorites where supported.
- Supported profile artwork and metadata.
- Community contribution attribution.
- Approved archive collections and trails created by the member.
- Opt-in community participation highlights.
- Selected media interests where the source explicitly permits their display.

The profile must distinguish provider-supplied data from Lemegeton community records.

### 8.3 AniList and Steam integration

Preserve the useful existing AniList and Steam profile features after a behavior audit.

Potential profile views include:

- Supported AniList profile information.
- Favorites, achievements, and statistics where the API provides them and the user has allowed display.
- Supported Steam profile and game information.
- Cross-media discovery from linked provider information.
- Links into /discover, /archive, /community, and the Knowledge Atlas.

Do not make a member's full private provider data public. Do not introduce Lemegeton-owned progress tracking to replace the provider's own library or playtime information.

### 8.4 Affinity and shared interests

- Retain the AniList affinity concept where its underlying data is available and the required consent is present.
- Show how an affinity result was calculated at a high level.
- Avoid presenting a compatibility number as a serious judgment about people.
- Allow users to opt out of appearing in comparisons.
- Do not infer sensitive personal characteristics.
- Keep the comparison scoped to the selected users and the provider data they authorized.

### 8.5 Server taste

Server taste should be an opt-in aggregate view, not a surveillance or member-ranking system.

- Use only data that members have explicitly allowed to contribute.
- Aggregate and minimize the data.
- Avoid exposing individual provider records through aggregate outputs.
- Allow opt-out and removal from future aggregate calculations.
- Display how the aggregate was derived.
- Use it to support community discovery and shared recommendations, not to rank members.

### 8.6 Contributor identity

The Archive and Knowledge Atlas should link to contributor attribution where the contributor has chosen to make the relevant profile information visible.

A public contribution does not automatically authorize exposing a contributor's linked provider accounts or unrelated profile details.

---

## 9. Custom Roles — /custom-role

Keep the existing custom-role system and combine its member and administrator workflows behind one feature command.

The current code contains a substantial custom-role implementation and separate member/admin entry points. V3 should preserve and audit that behavior rather than replacing it with a generic role editor.

The single /custom-role command should present different available panels based on the invoking member's authorization:

- Eligible members can create, preview, style, update, activate, save, or manage their own supported custom role.
- Authorized administrators can configure the custom-role feature, role placement, allowed roles, channels, policy controls, and review operations that already belong to this feature.
- Members must not see or invoke privileged administrative operations.
- Permissions must be rechecked when an interaction is submitted.

Preserve the useful existing custom-role capabilities, safety checks, role hierarchy checks, naming restrictions, color/palette behavior, supported icons, booster eligibility, saved-role behavior, removal safeguards, and tests after inspecting the current implementation.

Do not expand this into a broad server appearance system, a role economy, general role marketplaces, or unrelated server-management features.

---

## 10. Media Notifications & Automation

Media notifications and automation are limited to supported media events and selected community media activity. They are not a general-purpose reminder, task, or automation platform.

### 10.1 Individual media subscriptions

Allow a member to opt into notifications for selected media identities or supported release categories.

Potential subscription targets:

- A specific anime or TV title.
- A supported airing/episode schedule.
- A manga, manhwa, manhua, or webnovel update when a provider supplies reliable chapter/update information.
- A book or light-novel publication event where a reliable release date exists.
- A film release or supported streaming-availability change.
- A game release or supported game update.
- A creator or franchise with supported new-work data.
- A community session or discussion connected to a followed media title, when the member explicitly opts in.

A subscription is a notification preference, not a statement of personal progress or ownership.

### 10.2 Guild media subscriptions and digests

Guilds may configure media-based channel notifications:

- Upcoming supported releases.
- Airing schedules.
- New episode or chapter updates where supported.
- New publication/release records.
- Selected game release/update information.
- Provider-supported streaming availability changes.
- Media events connected to the guild's sessions, rankings, or discussions.
- A digest of selected followed categories.

Settings may include destination channel, media categories, title filters, timezone, schedule, role mention policy, moderation/review requirements, and enabled/disabled state.

### 10.3 Media event automation

Automations may connect media data to selected Lemegeton community features.

Examples:

- A confirmed episode release can update a calendar entry and optionally open a linked discussion.
- A new supported release may create a Daily Drop suggestion or a session nomination.
- A completed community ranking may link its winning title to the Archive and Knowledge Atlas.
- A newly approved archive contribution may appear in a media-linked spotlight if its scope permits it.
- A provider-confirmed sequel or adaptation update may refresh the relevant Knowledge Atlas relationships.
- A selected release digest may be published to the guild's configured channel.

Each automation must be explicitly enabled and configurable. Do not create automatic public posts simply because a provider returned data.

### 10.4 Notification controls

- Member opt-in and opt-out.
- Per-title and per-category preferences.
- Guild-level destination and format controls.
- Timezone-aware scheduling.
- Sensible duplicate suppression.
- Quiet delivery windows only as a media-notification preference.
- Role mention controls and mention safety.
- Source and freshness display.
- Delivery failure visibility for administrators.
- Ability to pause or disable a subscription.
- Re-check privacy and visibility at delivery time.

No generic reminders, arbitrary natural-language scheduled messages, birthday reminders, or unrelated task automations should be added.

### 10.5 Delivery reliability

- Use durable jobs and persisted subscription state.
- Make event processing and delivery idempotent.
- Apply bounded retries and provider rate limits.
- Record delivery state sufficiently to avoid duplicate announcements.
- Recover jobs after restarts.
- Handle provider corrections and cancelled release dates.
- Avoid sending stale release data as if it were current.
- Respect per-guild configuration and member preferences.

---

## 11. Community Knowledge Atlas — visual media graph

The Community Knowledge Atlas is a major product pillar. It should combine media relationships and community-created knowledge into a visual graph inspired by the navigable graph experience of applications such as Obsidian.

This is not simply a text list of related titles or a graph-shaped embed. The graph should be an actual visual interface with connected nodes, edges, image-backed node previews, search, filters, navigation, and useful exports.

The Atlas is entered through the Graph/Atlas section of /discover and from relevant media, Archive, profile, collection, discussion, session, and dashboard views. It does not need its own additional slash command.

### 11.1 Graph node types

Potential node types include:

- Anime, manga, manhwa, manhua, light novels, books, webnovels, films, TV series, and games.
- Franchises, series, seasons, and supported media groupings.
- Creators, authors, artists, studios, directors, developers, and publishers.
- Characters or other entities only where a reliable provider supplies stable identity and useful relationships.
- Archive entries, collections, and Archive Trails.
- Community discussions and sessions.
- Community rankings, competitions, and selected Daily Drop records.
- Provider records and source references where they add real navigation value.

A node must represent a stable or intentionally versioned entity. Do not create a new node every time a search result is displayed.

### 11.2 Graph edge types

Relationships should be explicit and typed.

Examples:

- Adaptation of.
- Source material for.
- Sequel to.
- Prequel to.
- Spin-off of.
- Side story of.
- Alternate version of.
- Part of franchise.
- Created by.
- Written by.
- Illustrated by.
- Published by.
- Developed by.
- Same creator.
- Related work, with its evidence type shown.
- Community recommendation.
- Included in collection.
- Appears in Archive Trail.
- Discussed in.
- Featured in session.
- Included in ranking or competition.
- Referenced by a community contribution.

Every edge must carry its relationship type and provenance. Distinguish provider-confirmed edges, calculated links, community proposals, and community-verified edges. A recommended title must not be displayed as a confirmed sequel or adaptation.

### 11.3 Image-backed node design

Graph nodes should be visual, not anonymous dots wherever suitable imagery exists.

- Media nodes should use an available poster, cover, box art, or other provider-approved thumbnail.
- Creator nodes may use a provider-supplied portrait or a consistent generated placeholder where no image is available.
- Archive and collection nodes may use their approved cover or first suitable permitted image.
- Session and discussion nodes may use a linked media image or a consistent type marker.
- Nodes without imagery must remain legible and visually distinct.
- Image loading must respect provider and asset permissions.
- Private archive images must never be exposed through a public graph or thumbnail cache.

Use a consistent node style so users can identify category at a glance. Image-backed circles or rounded thumbnails, restrained labels, category markers, and clear edge styling are preferred over a crowded diagram of anonymous points.

### 11.4 Graph layouts and navigation

Support multiple views over the same underlying graph data:

- **Local graph** — selected node and its direct neighbors.
- **Focused graph** — an expanded neighborhood around a title, creator, franchise, collection, or archive item.
- **Path view** — a visible relationship path between two selected nodes, with each edge explained.
- **Franchise view** — a focused map of supported franchise entries and adaptations.
- **Creator view** — works and supported collaborations connected to a creator.
- **Community view** — permitted archive entries, collections, discussions, and sessions related to the selected media.
- **Temporal view** — release or publication chronology where reliable dates exist.
- **Guild view** — a guild-scoped community graph.
- **Global view** — explicitly shared public records and contributions only.

Graph controls should include pan, zoom, fit-to-view, center-on-node, node selection, search, hover/focus details, category filters, relationship filters, and navigation back to the previous focus.

### 11.5 Graph filters and clustering

- Filter by media category.
- Filter by relationship type.
- Filter by provider/source.
- Filter by evidence and review state.
- Filter by guild/global visibility.
- Filter by creator, franchise, genre, and supported metadata.
- Hide or show community-created nodes.
- Collapse or expand a franchise or creator cluster.
- Focus on a selected node and its neighborhood.
- Limit graph depth to avoid rendering an unbounded network.
- Search within the currently visible graph.
- Show why a node or edge appears in the view.

Clusters should be meaningful and explainable: franchise, creator, collection, media type, or another explicit relationship. Do not use unexplained visual clusters that imply factual relationships.

### 11.6 Discord and dashboard presentation

Discord messages do not provide a full freeform graph canvas. The Discord interaction should therefore present a useful graph snapshot and a focused navigation interface:

- Generate a readable graph image for the selected neighborhood.
- Use image-backed nodes and legible relationship edges.
- Provide selects or buttons to focus on a node, expand a neighborhood, filter categories, or open a related record.
- Provide a safe button/link to the interactive graph view when the authenticated dashboard can serve it.
- Re-check guild visibility and user authorization when opening a node or graph URL.

The Next.js dashboard should provide the full interactive canvas with pan, zoom, search, selection, filtering, and node detail panels. It should not be a separate graph database: it must render the same authorized graph projection used by the bot.

### 11.7 Graph exports and generated images

Support useful graph exports where practical:

- High-resolution PNG snapshots.
- SVG export where the renderer and asset policy permit it.
- Shareable focused graph images for Discord.
- A focused graph image for a collection, creator, franchise, or media title.
- A path image showing how two entities are connected.

Generated images must be render outputs of the graph data, not manually maintained copies. They must be reproducible and regenerated when the relevant data changes. Exports must respect visibility and image-use permissions.

### 11.8 Graph data, performance, and integrity

- Store authoritative media and community relationships in their domain records.
- Build graph projections from those records rather than maintaining conflicting duplicated facts.
- Use stable node identities and typed, versionable edge records.
- Avoid loading the entire global graph for every request.
- Query bounded neighborhoods and use pagination or graph expansion.
- Cache only projections that can be invalidated safely.
- Re-check visibility and moderation state when building and serving a graph.
- Remove or hide deleted/private nodes and edges from future renders.
- Ensure every visual edge can be explained by its source or evidence type.
- Prevent unauthorized guild data from appearing in a global layout, image cache, or export.

### 11.9 Atlas connections to the other systems

The Atlas should make the other pillars more discoverable:

- /discover opens a title or creator at its graph neighborhood.
- /archive exposes linked titles, collections, trails, and related archive entries.
- /community connects discussions, sessions, rankings, and release events to media nodes.
- /play can link a quiz question to its supported media node.
- /profile can show a member's public contribution nodes where permitted.
- /custom-role remains separate; role data does not become graph content.
- Media Notifications can link a release event to the affected media node.

---

## 12. /settings and the existing dashboard

/settings remains a focused configuration entry point for the selected v3 product scope. It is not approval to build the broader server-administration suite previously considered.

### 12.1 In-scope configuration

- Archive categories, visibility choices, upload acceptance, upload channels, and review roles.
- Community activity enablement, destinations, schedules, timezone, and participation settings.
- Ranking creation permissions and defaults.
- Session categories, event channel, and scheduling defaults.
- Discussion spoiler defaults and destinations.
- Media release digest categories and destination channels.
- Media notification settings and role mention policies.
- Knowledge Atlas guild/global visibility defaults and graph access.
- Custom-role feature configuration through the /custom-role environment.
- Relevant feature enablement, permission diagnostics, and audit history.

Configuration must be limited to features included in this specification. Do not expand /settings into a general analytics, moderation, invite-management, or server-customization suite.

### 12.2 Dashboard consolidation

The existing /dashboard and dashboard-section-toggle experience should be absorbed into /settings instead of creating parallel configuration entry points.

The external dashboard remains a Next.js application backed by the existing Rust/Axum API. The Discord command can open the focused in-Discord settings panel and, for authorized users, provide a link to the corresponding dashboard view.

The dashboard must preserve existing OAuth2, guild authorization, CSRF protections, private bot bridge, audit behavior, and actual synchronization checks. It must not trust a guild, role, channel, or member ID supplied by the browser without server-side authorization.

---

## 13. Operations & Infrastructure

This is a major engineering pillar, not another collection of user-facing slash commands. Its purpose is to make a large multi-guild bot dependable as the number of providers, scheduled jobs, community records, and interactions grows.

### 13.1 Runtime and application structure

- Use the selected TypeScript/Node.js/Discord.js runtime for the bot.
- Establish typed configuration and validation at startup.
- Use a consistent structured logging approach.
- Separate Discord interaction handlers from domain operations and provider adapters.
- Keep startup and shutdown behavior predictable.
- Handle Discord reconnects and transient service failures.
- Use graceful shutdown for durable workers and database connections.
- Avoid global mutable state for guild-owned domain data.
- Keep module boundaries aligned with real product domains.
- Do not add microservices unless a measurable operational need requires one.

### 13.2 Database reliability

- Preserve and inspect the current PostgreSQL implementation.
- Use explicit, versioned migrations.
- Keep guild ownership and visibility scope explicit.
- Enforce unique keys and foreign-key relationships where they protect real invariants.
- Use transactions for multi-record operations such as votes, collection changes, and graph relationship updates.
- Index actual search and relationship access patterns.
- Avoid unbounded full-table scans for user-facing interactions.
- Define retention and deletion behavior for user-linked data.
- Include migration rollback or recovery notes for risky schema changes.
- Test multi-guild isolation at repository and service boundaries.

### 13.3 S3 and asset infrastructure

- Preserve the existing S3-compatible storage model and asset registry.
- Maintain private-original and public-generated-media separation.
- Use bounded signed access where needed.
- Validate file type, size, and content metadata.
- Track references so deleted archive records do not leave uncontrolled public objects.
- Avoid orphaned object growth through safe lifecycle and cleanup policies.
- Keep image derivatives and graph exports tied to their source records.
- Re-check authorization before serving private assets.
- Do not expose object credentials or private permanent URLs.

### 13.4 Provider health and rate limits

- Isolate each provider adapter.
- Apply explicit timeouts and bounded retries.
- Respect provider rate limits and terms.
- Use caching with documented freshness and invalidation rules.
- Track provider request failures, rate-limit responses, and latency.
- Identify degraded providers without taking down unrelated discovery.
- Avoid retry storms and duplicate background requests.
- Provide a developer/operator view of provider health without exposing secrets.
- Do not scrape providers or add an adapter where doing so would violate provider terms or reliability requirements.

### 13.5 Background jobs and media automation

- Persist jobs that must survive restarts.
- Use idempotency keys or equivalent safeguards for repeatable processing.
- Track scheduled, running, completed, failed, and retried states.
- Avoid duplicate Discord announcements.
- Apply per-provider and per-guild delivery limits.
- Support safe cancellation and rescheduling.
- Record job ownership and relevant guild scope.
- Make stale or invalid release data recoverable.
- Separate media automation jobs from ordinary request handling.

### 13.6 Observability and diagnostics

Provide operational visibility for:

- Bot startup, shutdown, reconnect, and gateway status.
- Database connectivity and query failures.
- S3 connectivity and asset operations.
- Provider latency, failures, and rate-limit events.
- Queue depth and job failures.
- Discord interaction failures and expired interaction rates.
- Media notification delivery outcomes.
- Graph projection generation and rendering failures.
- Dashboard API availability and bridge health.
- Migration and backup status.

Logs should be structured and useful. Do not log tokens, OAuth codes, signed asset URLs, private message content, or unnecessary personal data.

### 13.7 Testing and quality gates

Testing is a core part of the 200k-scale ambition, not an afterthought.

- Unit tests for domain behavior and validation.
- Provider adapter tests using controlled fixtures.
- Integration tests for PostgreSQL transactions and migrations.
- S3 behavior tests using an appropriate test environment or controlled fakes.
- Discord interaction tests for authorization, component state, and error paths.
- Multi-guild isolation tests.
- Archive visibility and asset privacy tests.
- Graph edge provenance, scope, and export tests.
- Notification deduplication and job recovery tests.
- Community voting and session persistence tests.
- Custom-role permission and lifecycle tests.
- Dashboard authorization, CSRF, and bridge tests.
- Regression tests for recovered v2 behavior.
- Build, type-check, lint, and test gates in CI.

Do not create extensive test infrastructure for trivial changes. Add tests proportional to the behavior and risk being changed.

### 13.8 Backups and recovery

- Define PostgreSQL backup schedules and retention.
- Verify backups through restore exercises, not merely successful backup commands.
- Document S3 asset recovery and lifecycle behavior.
- Preserve migration history and deployment configuration.
- Define recovery steps for failed schema migrations.
- Make scheduled-job recovery safe after restart.
- Keep production cutover reversible until the new bot has passed parity checks.
- Protect backup access and never publish private user data in repository artifacts.

### 13.9 Security and privacy

- Store credentials in the deployment secret manager/environment, never source control.
- Preserve Discord OAuth2 and dashboard authorization boundaries.
- Protect private bot bridge authentication.
- Re-check permissions at action time.
- Validate Discord IDs, provider identifiers, URLs, uploads, and user-supplied metadata.
- Protect against SSRF when fetching external assets or provider images.
- Prevent cross-guild authorization and data leakage.
- Respect user unlinking, privacy export, and deletion requirements.
- Avoid unnecessary collection and retention of personal data.
- Review dependency updates and security advisories.
- Keep audit records for consequential settings and content actions without recording secrets.

### 13.10 Deployment and release management

- Preserve the current deployment model until a migration audit confirms required changes.
- Make the bot and dashboard build reproducible.
- Use health checks appropriate to each service.
- Separate required startup configuration from optional provider credentials.
- Fail clearly when required configuration is missing.
- Provide safe graceful shutdown and restart behavior.
- Verify bot command registration and dashboard compatibility before production cutover.
- Keep environment examples synchronized with actual configuration.
- Do not report a deployment or command sync as successful without confirming the result.

No separate public /ops command should be created. Operational views belong to authorized maintainers through the existing dashboard/security model and deployment observability.

---

## 14. Profiles, privacy, Terms, and community trust

On first use, show the current Terms of Service and privacy information before allowing access to features that require acceptance.

Record the accepted document version and timestamp. If the terms materially change, require acceptance of the new version before continuing. Members must be able to view the current terms again from the relevant profile or settings interface.

Explain archive visibility, global sharing, upload rules, attribution, and provider linking before the member confirms the relevant action.

### 14.1 User data controls

- Allow members to view supported linked-provider connections.
- Allow provider unlinking and revoke stored credentials where applicable.
- Provide appropriate export and deletion flows for Lemegeton-owned personal data.
- Explain what information is public, guild-scoped, global, or private.
- Respect opt-out from affinity and server taste features.
- Preserve contributor attribution where required by the shared content model, while respecting applicable privacy and removal rules.
- Keep provider-owned data distinct from Lemegeton-owned data.

### 14.2 Content and attribution

- Ask contributors to confirm they have rights or permission to submit uploads.
- Retain source and creator attribution.
- Avoid reproducing long copyrighted passages.
- Use provider images and artwork according to source terms.
- Keep community-written quiz clues and descriptions original.
- Provide a report and review path for problematic archive entries and graph relationships.
- Preserve a meaningful audit history for content edits and moderation decisions.

---

## 15. Existing command and feature migration inventory

Existing useful functionality must be mapped before implementation. This inventory is a migration checklist, not proof that every command or provider is currently working.

### 15.1 Current branch commands and destinations

| Existing command or feature | v3 destination | Migration intent |
|---|---|---|
| /browse | /discover | Expand into category-aware search and browsing |
| /recommendations | /discover | Merge provider and local recommendation paths with clear provenance |
| /random | /discover | Keep filtered random discovery |
| /trending | /discover | Keep supported trending views |
| /compare | /discover | Fold into comparison environment |
| /franchise | /discover and Atlas | Keep franchise exploration and graph view |
| /connections | /discover and Atlas | Preserve provider-declared media relationships |
| /game | /discover | Keep IGDB/Steam game discovery |
| /airing | /discover and /community | Preserve schedule information and link it to media releases |
| /tv-guide | /discover and /community | Preserve supported TV season and episode information |
| /media-region | /discover settings | Preserve regional media availability preference where supported |
| /server-taste | /profile | Preserve only as opt-in aggregate community taste |
| /reading | /community | Merge into Unified Community Sessions |
| /media-night | /community | Merge into Unified Community Sessions |
| /release-calendar | /community | Merge into media release calendar |
| /media-bracket | /community | Merge into community rankings and competitions |
| /adaptation-vote | /community | Merge into community rankings and competitions |
| /media-quiz | /play and /community | Interactive quiz games belong in /play; scheduled prompts may appear in Community |
| /panel-of-the-day | /community and /archive | Become an archive-backed Daily Drop/spotlight |
| /archive | /archive | Expand existing unified archive; Panels stays a category |
| /panel | /archive | Remove separate entry point and migrate all useful panel workflows |
| /dashboard | /settings | Consolidate the in-Discord settings entry point and link to the existing dashboard |
| dashboard-section-toggle | /settings | Absorb into the unified configuration interface |
| /custom-role | /custom-role | Preserve and expand the current member experience |
| /custom-role-admin | /custom-role | Merge privileged configuration into the same command with permission-aware panels |
| /profile | /profile | Preserve supported linked-provider and public profile views |
| /login | /profile | Merge supported provider account linking into profile management |
| /affinity | /profile | Preserve consent-based affinity comparison |
| /anilist-leaderboard | /profile or /community | Preserve only useful, privacy-respecting provider-based community summaries |
| /notifications | /discover and /profile | Replace broad notification preferences with media-only subscriptions and delivery controls |
| /server-config | /settings | Preserve configuration needed by selected v3 features; do not port unrelated server administration wholesale |
| /server-check | /settings | Retain diagnostics that directly validate selected v3 feature configuration |
| /server and /serverinfo | /settings | Keep only a concise server context/health view if still useful; do not build a server analytics product |
| /user and /userinfo | /profile | Merge supported public Discord information into profile presentation |
| /steam-profile | /profile | Preserve supported Steam profile display |
| /steam-recommendation | /discover | Merge into gaming discovery |
| /steam-game | /discover | Merge into game discovery |
| Free-game notifications | Media Notifications | Do not port the legacy monitor as-is: its Steam path parses storefront search responses and uses undocumented endpoints, while the Epic/GOG storefront feeds also lack a verified supported integration contract. Revisit only with a stable, permitted provider source. |
| Custom theme commands | Out of approved expansion | Do not build a general theme or appearance system |
| /invite-stats and /invite-leaderboard | Out of approved expansion | Do not build general invite analytics |
| /feedback | Out of approved expansion | Do not create a separate generic feedback product as part of this scope |
| /planned-features | Out of approved expansion | Do not recreate a generic voting backlog |
| /help and /discovery-hub | Native command discovery and contextual help | Do not add another top-level command hub |
| /library-backup | Out of approved expansion | Do not create a Lemegeton personal media library or progress system |
| /news and /test-twitter-scrape | Audit before any migration | Do not preserve brittle or unsupported scraping merely because an old command existed |
| Generic utilities and invite commands | Out of approved expansion | Do not increase command count with unrelated utilities |



The legacy free-game checker is deliberately not migrated in this phase. Its Steam implementation depends on storefront search parsing and undocumented endpoints; the current Steam Web API reference and Free to Keep documentation do not supply a general public promotions feed. The GOG developer documentation describes the Galaxy SDK rather than a supported public store-catalog API. See the [Steam Web API reference](https://partner.steamgames.com/doc/webapi), [Steam Free to Keep documentation](https://partner.steamgames.com/doc/marketing/discounts/freetokeep), and [GOG developer documentation](https://docs.gog.com/) for the published platform interfaces. Do not reintroduce these scrapers as a substitute for a stable provider integration.

### 15.2 Historical Lemegeton v2 commands

The separate lemegeton-v2 branch contains older commands and modules that must remain visible in the migration record so they are not silently forgotten.

| Historical v2 command or module | v3 disposition |
|---|---|
| /birthday and /birthdaymod | Historical feature; not in the selected v3 scope. Do not rebuild the birthday system as part of this expansion. |
| /changelog | Historical bot-operations feature; not part of the media notification system. Do not add a user-facing command solely for this. |
| /set_bot_updates_channel | Historical bot-operations configuration; not part of the selected media notification scope. |
| /nitro-role-set | Superseded by the current custom-role implementation; preserve useful role behavior through /custom-role after audit. |
| /dashboard-section-toggle | Absorb into /settings; do not retain as a separate command. |
| /server | Merge useful public server information into the limited /settings context where it remains relevant. |
| /user | Merge supported public user information into /profile. |
| /admin-login | Historical troubleshooting/admin login command; do not reintroduce as a public feature. |
| /login | Preserve supported provider linking through /profile. |
| /profile | Preserve supported profile display through /profile. |
| /browse | Preserve through /discover. |
| /recommendations | Preserve through /discover. |
| /trending | Preserve through /discover. |
| /random | Preserve through /discover. |
| /news | Audit the old Twitter/X monitoring behavior and provider/terms status before considering it. It is not automatically approved for v3. |
| /test-twitter-scrape | Development/test command; do not expose as a production feature. |
| /set-manga-completion-channel and /show-manga-completion-channel | Audit current behavior. Do not create personal completion tracking; only supported media release notifications belong in scope. |
| /library-backup | Not in the approved scope; do not recreate a Lemegeton personal library or progress-tracking system. |
| /steam-profile | Preserve supported provider profile information through /profile. |
| /steam-recommendation | Merge into /discover. |
| /steam-game | Merge into /discover. |
| /theme and /admin-guild-theme | Not in the approved expansion; do not create a general theme system. |
| /serverinfo | Merge only useful server context into /settings; no invite or activity analytics suite. |
| /server-config | Preserve only settings required by selected v3 features. |
| /invite-stats, /invite-leaderboard, and /invite-theme | Not in the approved expansion. |
| /anilist-leaderboard | Audit and retain only appropriate provider-based community summaries within /profile or /community. |
| /affinity | Preserve through /profile with consent and privacy controls. |
| /feedback | Not in the approved expansion. |
| /help | Replace command sprawl with Discord-native discoverability and contextual help. |
| /notifications | Narrow to media notifications and subscriptions only. |
| /say | General utility outside the selected scope. |
| /userinfo | Merge into /profile where useful. |
| /invite | General utility outside the selected scope. |
| /planned-features | Generic feature voting outside the selected scope. |
| /bot-moderators | Historical bot-wide administration; retain only the minimum maintainer authorization required by infrastructure, not as a user-facing feature. |
| /changelog | Historical command; see bot-operations disposition above. |
| /set-bot-updates-channel | Historical command; do not turn it into general announcements. |

The v2 README documents 35 commands in its command list, while the repository also contains additional test cogs and experimental modules. Source files and dynamically loaded cogs must be inspected; the README count is not a complete inventory.

### 15.3 Historical test and experimental modules

The v2 test area included a birthday cog and a GPT-oriented cog with /persona, /reset, and /image. These are historical experiments, not approved v3 product pillars. Do not automatically port them.

A historical AniList file utility module was referenced as alfiles.py, but its source could not be confirmed in the inspected v2 ref. Keep it recorded as an unresolved historical item; do not invent its behavior.

### 15.4 Historical backup moderation modules

The v2 branch contains backup modules for ban/appeals, clearing messages, channel locking, mute handling, verification, AutoMod, and AI moderation.

These are recovery references only. The selected v3 expansion does not authorize rebuilding them into a general moderation suite. Existing moderation/report/review controls needed to protect Archive and Community content remain in scope. Do not expose old backup commands as active product functionality without a separate decision and security audit.

### 15.5 Migration evidence and source of truth

Before porting a historical feature:

1. Inspect the source file and its callers.
2. Determine whether it was loaded, registered, or only stored as a backup/test.
3. Identify its database tables and data ownership.
4. Check multi-guild behavior and permission enforcement.
5. Check external services, provider terms, credentials, and current availability.
6. Identify the actual behavior worth preserving.
7. Map it to a selected v3 command or mark it out of scope.
8. Add a regression test for behavior that is migrated.

A README description, backup filename, or old command decorator is evidence of history, not proof of production readiness.

---

## 16. Data, multi-guild isolation, and privacy requirements

- Every guild-owned setting, event, vote, discussion, session, archive resource, and server-only graph element must include and enforce the invoking guild scope.
- Global records must use an explicit visibility scope and must not inherit the submitting guild's moderation permissions.
- Shared/global archive items and Knowledge Atlas projections must re-check visibility before display or export.
- Provider-linked profiles must respect user consent and provider authorization.
- Media notification subscriptions must be scoped to the member or guild that created them.
- Community voting must prevent duplicate or unauthorized votes according to the ranking's declared rules.
- Re-check current member permissions for sensitive actions, including component interactions originally displayed to an authorized member.
- Validate and normalize user input, uploaded assets, provider responses, graph identifiers, and external URLs.
- Bound external requests, use timeouts, respect provider rate limits, and isolate provider failures.
- Protect OAuth tokens, Discord credentials, S3 credentials, and bridge secrets; never expose them to the frontend or logs.
- Preserve private media originals and signed access patterns.
- Keep background jobs idempotent and resilient to restarts.
- Do not report a write, command sync, asset upload, graph export, or configuration change as successful until the relevant operation has actually succeeded.
- Preserve existing data and use focused, reversible migrations only where required.
- Keep dependency additions justified by a concrete requirement.

### 16.1 No personal media progress system

Lemegeton is a discovery and community platform, not a personal media-tracking service.

Do not add:

- A Lemegeton watch/read/play progress library.
- Personal episode, chapter, or volume completion tracking.
- Individual media streaks.
- Private media libraries as a core v3 feature.
- Individual activity histories inferred from community events.
- Progress-based leaderboards.

Provider information may be displayed when the member explicitly links and authorizes the provider. Community session RSVP and event attendance must not become personal media progress.

---

## 17. Migration plan

The redevelopment is staged so the new bot does not lose existing behavior during the rewrite.

### Current implementation checkpoint — 7 November 2026

The TypeScript/Node.js/Discord.js runtime now lives in `bot.ts`, with PostgreSQL access in `database.ts`, feature commands in `src/`, and shared providers/domain helpers in `helpers/`. All seven approved feature commands are registered, and the dashboard source is organized under `web/frontend/` and `web/backend/`. The implemented TypeScript workflows are still a staged migration rather than proof of full legacy parity; the Python runtime and its dependencies remain in place until the remaining command, background-job, schema, deployment, and data-compatibility checks pass.

Guild-level media completion notifications now have a durable PostgreSQL settings/delivery store and an administrator-controlled `/settings` panel. The current scanner covers only recently finished or cancelled anime and manga reported by AniList. Per-title subscriptions, additional provider release types, digest scheduling, and media-linked automation remain future migration work.

1. **Repository and behavior audit** — inventory all loaded cogs, commands, interactions, jobs, helpers, providers, schemas, dashboard endpoints, deployment scripts, permissions, and tests. Include both normal cogs and dynamically loaded test-cog paths. Identify which documented features are actually implemented.
2. **Command consolidation map** — produce the final mapping from existing commands to /discover, /archive, /community, /play, /profile, /custom-role, and /settings. Identify historical, test-only, backup, and out-of-scope commands. Do not implement additional command entry points merely to preserve old CRUD commands.
3. **TypeScript bot foundation** — establish the Node.js/Discord.js runtime, typed configuration, logging, error handling, test setup, and feature command routing with focused home panels.
4. **Data and domain layer** — port the existing PostgreSQL access and domain behavior without creating competing schemas. Add only migrations required for v3 records and graph relationships.
5. **Provider migration** — port and verify existing provider adapters independently, preserving supported fields, rate limits, error handling, and provenance.
6. **Media Intelligence** — migrate browsing, search, recommendations, random discovery, comparisons, creators, franchises, game discovery, supported release information, and relationship exploration into /discover.
7. **Community Archive** — migrate existing archive behavior first, then add mixed collections, Archive Trails, collaboration, graph links, and approved submission/search/moderation improvements.
8. **Community Activities** — unify Daily Drop, rankings, sessions, discussions, release calendar, competitions, and Archive Throwbacks inside /community.
9. **Interactive Media Games** — migrate the supported quiz behavior and implement selected source-backed media game modes through /play.
10. **Social & Profiles** — migrate supported provider linking, profile presentation, affinity, and opt-in aggregate server taste into /profile.
11. **Custom Roles** — preserve and consolidate the existing custom-role member/admin experience into one /custom-role command.
12. **Media Notifications & Automation** — implement title subscriptions, release digests, media update processing, and selected media-linked community automation.
13. **Community Knowledge Atlas** — establish stable graph identities and provenance, then deliver Discord graph snapshots and the interactive Next.js graph canvas with image-backed nodes.
14. **Next.js dashboard** — replace the current Vite frontend while retaining the Rust/Axum API and existing authorization model. Integrate the Atlas and selected configuration views.
15. **Operations & Infrastructure hardening** — complete observability, job reliability, backups, recovery, tests, deployment gates, and production diagnostics.
16. **Parity and production cutover** — test multi-guild isolation, providers, interactions, dashboard authorization, graph visibility, scheduled jobs, data compatibility, and deployment. Switch the live bot only after the selected feature inventory has acceptable parity.
17. **Retire the Python runtime** — remove the old runtime only after the TypeScript bot is running successfully and the migration has been explicitly verified. Do not delete legacy code early merely to make the repository look cleaner.

The order may change based on dependencies discovered during the audit, but the compact command surface, selected product scope, and preservation of existing useful behavior remain fixed requirements.

---

## 18. Acceptance criteria

The v3 redevelopment is ready for release only when:

### Command architecture
- The public slash-command surface is limited to the seven feature entry points: /discover, /archive, /community, /play, /profile, /custom-role, and /settings, unless a separately justified exception is approved.
- Daily, rankings, sessions, discussions, calendar, notifications, and Knowledge Atlas are not separate top-level slash commands.
- Archive CRUD operations are handled within /archive rather than separate commands.
- Existing commands are mapped to their new feature environments or explicitly recorded as out of scope.
- The user-facing interface remains navigable and does not overwhelm members with every possible action at once.

### Media Intelligence
- Supported media categories use appropriate metadata and provider identities.
- Search, browsing, recommendations, random discovery, comparisons, creators, franchises, and gaming discovery work through /discover.
- Provider provenance, local matches, and community suggestions remain distinct.
- Provider failures are isolated and produce useful feedback.
- No unsupported metadata or relationships are invented.

### Community Archive
- Existing archive categories and useful panel behavior are preserved.
- Mixed-media collections, Archive Trails, collaboration, attribution, search, and visibility work as specified.
- Image/audio/video acceptance is configurable per guild.
- S3 privacy separation is preserved.
- Global archive discovery respects the visibility and review state of every referenced item.
- Archive moderation cannot cross guild boundaries.

### Community Activities and Games
- Daily Drop, rankings, sessions, discussions, calendar, competitions, and Archive Throwbacks are navigable inside /community.
- Votes and event state persist and recover correctly.
- Sessions do not become personal reading/watching/playing progress records.
- Media games work through /play and use source-aware questions.
- Game scoring and eligibility rules are transparent and tested.

### Social & Profiles
- Supported provider linking and profile displays are migrated.
- Profile visibility and provider consent are respected.
- Affinity and server taste are opt-in and explainable.
- No private media library or Lemegeton-owned progress tracker is introduced.

### Custom Roles
- Existing member and administrator custom-role workflows are available through one /custom-role entry point.
- Existing role hierarchy, authorization, safety, palette, and persistence behavior is preserved and tested.

### Media Notifications and Atlas
- Notifications are media-based only and respect user and guild preferences.
- No general reminder or unrelated automation system is introduced.
- Media release jobs are timezone-aware, idempotent, and recover safely.
- Knowledge Atlas renders image-backed nodes and typed, provenance-aware edges.
- Discord graph snapshots and the interactive dashboard canvas respect guild/global visibility.
- Graph paths, filters, node selection, and exports work without exposing private records.

### Infrastructure and security
- Per-guild data and authorization boundaries are verified with tests.
- PostgreSQL migrations and S3 privacy behavior are preserved.
- Background jobs recover safely after restart and avoid duplicate announcements.
- Provider health and operational failures are observable.
- Backups have been restore-tested.
- The Next.js dashboard uses the existing Rust/Axum authorization boundary.
- Interaction failures, expired controls, missing permissions, provider outages, and disabled features produce clear feedback.
- CI runs the relevant type, build, lint, and test checks.
- Documentation and deployment instructions reflect the actual implementation.
- Python is not retired until parity and production cutover checks have passed.

---

## 19. Development rules for the v3 work

- Work on the existing lemegeton-v3 branch associated with PR #17. Do not create another PR for this effort.
- PR #17 must remain Draft until explicitly approved for review.
- Keep implementation changes focused and commits small and meaningful. Do not bundle unrelated refactors into the migration.
- Inspect current implementations, callers, and actual loaded cogs before porting or replacing behavior.
- Prefer the minimum code and dependencies needed for each phase.
- Do not artificially inflate line count or introduce empty modules to meet the 200,000-line ambition.
- Build real depth through provider correctness, domain behavior, strong interfaces, graph functionality, resilience, and tests.
- Add focused tests for changed behavior and reproduce existing bugs where practical.
- Run relevant checks and inspect the final diff before reporting completion.
- Never claim tests, builds, provider calls, or deployments succeeded unless they were actually run.
- Do not begin the implementation phases merely because this specification has been committed; this specification records the approved direction, not completion of the redevelopment.

---

## 20. Discord and platform references

- [Discord Application Commands](https://discord.com/developers/docs/interactions/application-commands)
- [Discord Message Components](https://discord.com/developers/docs/components/overview)
- [Discord Interactions](https://discord.com/developers/docs/interactions/overview)
- [Discord Developer Documentation](https://discord.com/developers/docs/)

Re-check the current Discord API and Discord.js support when implementing each component. Do not rely on obsolete component limits, unsupported modal inputs, or assumptions about Discord's rendering capabilities.

## 21. Historical repository references

The v3 migration audit should use the actual repository source as its authority. Useful starting points include:

- [Lemegeton v2 README and command catalogue](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/Lemegeton_v2/README.md)
- [V2 birthday module](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/cogs_test/General_Commands/birthday.py)
- [V2 changelog module](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/cogs/admin/changelog.py)
- [V2 moderation backup: ban and appeals](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/backup/ban.py)
- [V2 moderation backup: clear](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/backup/clear.py)
- [V2 moderation backup: lock](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/backup/lock.py)
- [V2 moderation backup: mute](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/backup/mute.py)
- [V2 AutoMod backup](https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v2/backup/automod.js)
- [Current unified Archive implementation](https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/cogs/media/community_archives.py)
- [Current Custom Roles implementation](https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/cogs/customization/custom_roles.py)
- [Existing dashboard implementation](https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/cogs_test/general_commands/dashboard.py)

These links are historical audit starting points, not implementation guarantees. Verify the current branch, actual callers, and behavior before porting anything.

---

## 22. Fifty candidate feature environments and command ideas

This catalogue records fifty substantial feature concepts raised during v3 planning. It is deliberately a catalogue of **feature environments, workflows, and specialist views**, not a plan to register fifty top-level Discord slash commands.

The approved public command surface remains the seven feature entry points in Section 3:

- `/discover`
- `/archive`
- `/community`
- `/play`
- `/profile`
- `/custom-role`
- `/settings`

Every idea below must be implemented inside the most suitable existing feature environment unless a later, explicit product decision justifies a new public command. Names such as `/atlas`, `/creators`, `/trails`, or `/trivia` are **planning labels and navigation concepts only**; they are not permission to create separate slash commands. Use contextual buttons, select menus, tabs, modals, autocomplete, message context actions, and dashboard views to expose the relevant workflows.

The list is a product backlog for evaluation and sequencing. Listing an idea does not by itself approve implementation, promise provider support, or override the scope exclusions and privacy rules elsewhere in this specification.

### 22.1 Media Intelligence — inside `/discover`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 1 | **Discovery Metropolis** | The main media discovery environment: multi-provider search, browse, filters, recommendations, random discovery, trending views, detailed title cards, comparisons, and cross-media exploration. It absorbs existing discovery commands rather than duplicating them. |
| 2 | **Community Knowledge Atlas** | An Obsidian-inspired visual graph of media, creators, franchises, adaptations, archive records, collections, discussions, and community activity. It provides image-backed nodes, typed relationships, zoom, pan, filters, search, path exploration, node details, and permission-aware navigation. The Atlas is a major view within `/discover`, with contextual entry points from related records and the dashboard. |
| 3 | **Creator Explorer** | Explore authors, artists, illustrators, editors, translators, studios, directors, developers, publishers, and their supported workographies. Show credits and collaborations only when supported by reliable provider data. |
| 4 | **Franchise Explorer** | Explore works belonging to a franchise, including sequels, prequels, spin-offs, side stories, alternate versions, and related entries. Label relationship provenance and avoid assuming that similarly named works belong to one franchise. |
| 5 | **Adaptation Explorer** | Explore source-to-adaptation relationships across manga, anime, novels, games, films, and television. Distinguish provider-confirmed links from community proposals and local matching. |
| 6 | **Comparison Studio** | Compare multiple works using category-aware fields such as format, creators, release data, genres, platforms, editions, and provider ratings. Explain which sources supplied each comparison field. |
| 7 | **Books & Editions** | Provide category-aware discovery for books, general novels, light novels, and translations, including ISBNs, publishers, editions, languages, illustrators, volume information, and publication histories where available. |
| 8 | **Availability Explorer** | Show supported streaming, regional catalogue, game storefront, and publisher availability. Require a reliable provider, identify the region and source, and distinguish unavailable information from confirmed absence. |
| 9 | **Media Release Explorer** | Explore upcoming and recent episodes, chapters, volumes, webnovel updates, publications, films, television releases, and games. Detailed title discovery lives in `/discover`; community scheduling and release views connect to `/community`. |
| 10 | **Metadata Source Explorer** | Inspect provider provenance, identifiers, field-level sources, freshness where available, missing metadata, and the distinction between provider facts, local matching, recommendations, and community-suggested relationships. |

### 22.2 Community Archive — inside `/archive`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 11 | **Archive Metropolis** | The complete existing Archive environment: browse, submit, search, filter, review, edit, remove, configure, and moderate permitted contributions across all supported archive categories. Preserve the unified Archive direction; Panels remains an archive category/workflow, not a competing command. |
| 12 | **Collection Studio** | Create and maintain mixed-media collections, reorder entries, add descriptions and source credits, invite collaborators, manage contribution permissions, and publish or unpublish collections. |
| 13 | **Archive Trails** | Build guided paths through archive entries. A trail can connect panels, quotes, scenes, soundtracks, fanworks, theories, and other permitted records with curator-authored transitions and explanations. |
| 14 | **Visual Archive Gallery** | Explore image-based archive material through galleries, visual category filters, collection previews, and media-linked displays. Gallery views must preserve the permissions and visibility of the underlying records. |
| 15 | **Soundtrack Discovery** | Explore soundtrack records and supported music metadata, connect soundtracks to media, browse by work or creator, and curate soundtrack collections. This is a media archive capability, not a general-purpose music player or unrelated music service. |
| 16 | **Curation Studio** | Maintain featured collections, curated indexes, category spotlights, Archive Trails, themed showcases, and community-selected highlights with clear curator attribution. |
| 17 | **Community Spotlights** | Surface approved contributions, older archive entries, notable collections, creator features, and media-linked highlights. Scheduling and publication are coordinated through `/community`; the source records remain in `/archive`. |

### 22.3 Community Activities — inside `/community`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 18 | **Community Metropolis** | The central environment for Daily Drop, rankings, sessions, discussions, tournaments, community seasons, calendar views, and selected community showcases. It consolidates existing activity commands and workflows rather than creating a command for each activity. |
| 19 | **Daily Media Centre** | Configure and participate in daily media prompts, mystery titles, trivia, quotes, media polls, recommendations, creator features, comparisons, and archive spotlights. Guild schedule, timezone, destination, and moderation settings remain explicit. |
| 20 | **Ranking Studio** | Create and manage community rankings, accept candidates, define voting rules, allow permitted vote changes, close voting, publish results, and explore historical rankings. |
| 21 | **Tournament Centre** | Run media brackets and structured competitions, including elimination rounds, multi-stage voting, character or creator competitions, and adaptation matchups. Rules, ties, eligibility, and voting windows must be defined for each tournament. |
| 22 | **Session Centre** | Coordinate Watch, Read, Play, and Discuss sessions with nominations, voting, hosts, co-hosts, RSVP, waitlists, event links, reminders associated with the event itself, and session history. Session participation must not become personal media-progress tracking. |
| 23 | **Discussion Centre** | Create and browse media-linked discussions with spoiler boundaries for episodes, chapters, volumes, seasons, and other supported units. Connect discussions to titles, archive entries, collections, and sessions. |
| 24 | **Media & Community Calendar** | Present supported media releases, community sessions, rankings, tournaments, discussions, and selected events in one filterable calendar. Preserve source dates, timezone, and event state. |
| 25 | **Community Seasons** | Run themed community periods containing scheduled Daily Drops, rankings, sessions, challenges, archive spotlights, and a final showcase. Season configuration must reuse existing activity records rather than duplicate them. |
| 26 | **Community Showcase** | Curate completed collections, Archive Trails, creative contributions, ranking outcomes, and event highlights. Public presentation must respect the sharing scope and review state of every included record. |

### 22.4 Interactive Media Games — inside `/play`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 27 | **Interactive Game Metropolis** | The main media-game environment: discover available game modes, start or join a game, select solo/team formats, manage supported game sessions, and present results. |
| 28 | **Trivia Arena** | Source-aware trivia across supported media categories, with solo, team, hosted, and multi-round formats. Questions need answer validation, difficulty, provenance, and review before community publication. |
| 29 | **Mystery Media** | Layered clues to identify a hidden work, franchise, creator, adaptation, or game. Support daily and hosted formats without exposing the answer through metadata or interaction payloads. |
| 30 | **Guessing Arena** | Title, creator, release-period, franchise, synopsis, and other media-identification rounds. Make accepted answers and normalization rules explicit. |
| 31 | **Team Games** | Create teams and run cooperative or competitive media challenges. Team membership, scoring, eligibility, and round state must persist reliably. |
| 32 | **Challenge Centre** | Timed or multi-stage media challenges, themed discovery tasks, seasonal challenges, and community puzzles with transparent rules and accessible time limits. |
| 33 | **Quiz Pack Studio** | Create, review, revise, curate, and share community quiz packs with answer keys, accepted alternatives, source references, difficulty, and revision history. |
| 34 | **Media Puzzle Room** | Media-themed word puzzles, relationship puzzles, franchise connection puzzles, clue chains, and cooperative problem-solving activities. Avoid adding generic non-media games to this product pillar without a separate decision. |

### 22.5 Social & Profiles — inside `/profile`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 35 | **Profile Metropolis** | Present supported Discord and provider profile information, connected accounts, opt-in media affinity, contribution attribution, visibility settings, and public profile presentation. |
| 36 | **Account Connection Centre** | Link, unlink, inspect, and manage supported AniList, Steam, and other verified provider connections. Show connection status and consent scope; protect tokens and credentials. |
| 37 | **Media Affinity** | Compare opt-in provider-supported interests between members, explain the comparison signals, and avoid treating an affinity score as a judgment about people. |
| 38 | **Community Taste Explorer** | Show opt-in aggregate media interests within a guild, including commonly shared interests and category-level trends, without exposing individual private records or introducing activity tracking. |
| 39 | **Contributor Centre** | Present a member's permitted public archive contributions, collections, trails, and other approved creative work with accurate attribution. |
| 40 | **Community Creations** | Provide a unified way to browse supported member-created archive content, fanworks, curated lists, and other approved contributions. Canonical content remains stored and moderated by the Archive. |
| 41 | **Profile Showcase** | Build a curated, opt-in public presentation of supported profile data and community contributions. It must not become a personal watch/read/play library or progress tracker. |

### 22.6 Custom Roles — inside `/custom-role`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 42 | **Custom Role Metropolis** | Retain the existing member and administrator custom-role experience behind one `/custom-role` entry point. Provide permission-aware creation, selection, assignment, styling, preview, and administration using the existing system's verified capabilities. |
| 43 | **Role Design Studio** | A deeper design workflow within Custom Roles for supported palettes, gradients, icons, previews, and role styling. This is a panel or sub-environment inside `/custom-role`, not another public slash command or a general server-theme system. |

### 22.7 Media Notifications & Automation — configuration through `/settings`, discovery through `/discover`, activity through `/community`

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 44 | **Media Follow Centre** | Subscribe to supported titles, creators, franchises, and media categories for relevant release or metadata updates. This is a notification subscription, not a personal library or progress tracker. |
| 45 | **Media Alert Centre** | Configure alerts for supported episodes, chapters, publications, films, television releases, game releases, provider updates, and streaming-availability changes. Allow user preferences and guild channel delivery rules where appropriate. |
| 46 | **Media Digest Studio** | Configure media-only digests, such as daily or weekly release summaries. Select supported categories, followed entities, region, timezone, destination, and presentation format. Do not add general reminders or unrelated digest content. |
| 47 | **Media Automation Studio** | Configure explicit media-linked workflows, such as a verified release updating the calendar, proposing a relevant session, opening a discussion proposal, or refreshing a Knowledge Atlas projection. Workflows must be bounded, auditable, idempotent, and limited to approved media/community triggers. |

### 22.8 Knowledge Atlas and Operations — integrated views, not extra public commands

| No. | Candidate environment | Intended capability |
|---:|---|---|
| 48 | **Graph Export Studio** | Export permission-filtered Knowledge Atlas views, focused franchise or creator maps, collection graphs, and relationship paths as supported image formats. Provide readable labels, useful sizing, and source/visibility safeguards. Export is a graph action inside the Atlas, not a separate slash command. |
| 49 | **Feature Diagnostics** | Provide authorized diagnostics for selected v3 features: missing Discord permissions, inaccessible channels, provider health, asset failures, job status, and relevant database/service health. Surface it through `/settings` and the authenticated dashboard, with sensitive operator details restricted. |
| 50 | **Data & Backup Centre** | Provide restricted operational visibility into migration status, backup verification, asset recovery, and selected data-safety reports. This is an operator/infrastructure capability, not a public member command or a replacement for deployment and backup tooling. |

### 22.9 Consolidation map

The fifty concepts route into the existing seven commands as follows:

| Public command | Environments owned |
|---|---|
| **/discover** | 1–10, plus Knowledge Atlas graph exploration and Graph Export Studio (2 and 48) |
| **/archive** | 11–16 and 40, with archive-backed parts of 17, 26, and 39 |
| **/community** | 17–26, including spotlights, daily activities, rankings, tournaments, sessions, discussions, calendar, seasons, and showcases |
| **/play** | 27–34 |
| **/profile** | 35–41 |
| **/custom-role** | 42–43 |
| **/settings** | Configuration for 44–47, plus authorized diagnostics (49) and restricted operational views (50) |

Some environments intentionally connect to more than one command. For example, a release can be discovered in `/discover`, followed for notifications through the media subscription system, and displayed in `/community`'s calendar. This is a shared domain workflow, not a reason to duplicate the underlying record or register more commands.

### 22.10 Rules for turning catalogue ideas into implementation

1. Keep the seven-command public surface as the default. A new top-level command requires a documented usability reason and explicit approval.
2. A candidate name with a slash prefix is a planning label unless it appears in the approved public command table in Section 3.
3. Prefer adding a focused view or action to an existing metropolis over creating a separate command.
4. Do not implement all fifty concepts at once. Sequence them by user value, data dependencies, provider support, security, and migration readiness.
5. Reuse canonical media, archive, community, profile, and graph records. Do not create duplicate data models for the same entity merely because it appears in multiple environments.
6. Keep media notifications and automation media-based only. Do not add birthdays, generic reminders, general-purpose task scheduling, or unrelated automation.
7. Keep Custom Roles as the only selected item from the broader server-customization category. Do not use this catalogue to introduce a theme marketplace or broad server administration suite.
8. The Knowledge Atlas must support image-backed nodes and readable graph views, but images are visual representations of permission-checked graph data, not an alternate source of truth.
9. Graph exports, spotlights, collections, community showcases, and global archive views must re-check source visibility at the point of display and export.
10. A candidate enters implementation only after its behavior, source of truth, permissions, failure cases, storage needs, and focused acceptance tests have been defined.
11. Preserve the distinction between a provider-confirmed fact, a provider-generated recommendation, a local similarity result, and a community-submitted suggestion.
12. The catalogue does not change the 200,000-line aspiration into a target to manufacture. Codebase size must arise from real implemented behavior, integrations, tests, and operational needs.


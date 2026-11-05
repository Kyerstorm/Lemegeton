# Lemegeton v3 — Product & Engineering Specification

**Status:** Approved direction; specification only  
**Target branch:** `lemegeton-v3`  
**Pull request:** #17 — keep Draft  
**Implementation status:** Not started

## 1. Product direction

Lemegeton v3 is a complete redevelopment of the existing multi-guild Discord bot. It remains focused on media discovery, reliable cross-media information, community-created resources, and shared experiences.

The bot should feel like one coherent Discord application rather than a collection of unrelated commands. Members should be able to discover media, contribute to shared resources, take part in community activities, and manage their server's Lemegeton experience without having to learn a long command list.

The project is not intended to become a personal watch/read/play tracker. It must not introduce individual progress tracking as a default product feature.

### Core principles

- One intuitive entry point, with the full feature set reached through Discord's native interaction UI.
- Media information must retain provider attribution and distinguish confirmed relationships from recommendations or community suggestions.
- Community content must retain authorship, moderation state, and visibility scope.
- Guild-owned settings and moderation remain isolated between servers.
- Existing useful functionality is migrated rather than discarded merely to simplify the redesign.
- No feature is described as AI-powered unless it actually uses an AI model.

## 2. Technology and architecture

| Area | v3 direction |
|---|---|
| Discord bot | TypeScript on Node.js with Discord.js |
| Dashboard frontend | Next.js, React, and TypeScript |
| Dashboard API | Keep the existing Rust/Axum service initially |
| Structured data | Keep the existing PostgreSQL database |
| Media objects | Keep the existing S3-compatible storage and privacy separation |
| Metadata | Migrate and reuse existing provider integrations |
| Hosting | Preserve the current deployment model until the migration audit establishes what must change |

The repository currently has a Python/discord.py bot. The dashboard is a React + TypeScript frontend built with Vite and served by the existing Rust/Axum service. The frontend migration therefore means replacing the Vite frontend with Next.js; it does **not** mean rewriting the Rust API or creating a second bot backend.

The existing PostgreSQL schema, S3 asset registry, private/public storage rules, OAuth2 flow, bot bridge, and deployment configuration must be inspected before changes are made. Reuse them where they still meet v3 requirements. Do not introduce a parallel database, storage layer, command registry, or authentication system.

### Bot responsibilities

The TypeScript bot owns the Discord gateway, application-command registration, component interactions, modal submissions, provider calls, scheduled community jobs, guild permissions, and Discord message/thread/event operations.

Provider-specific logic must remain separate from Discord UI handlers. Discord handlers should validate the interaction, authorize it, call a domain operation, and present the resulting state. Provider failures must not break unrelated features.

### Dashboard responsibilities

The dashboard remains a control plane for the running bot, not a second Discord client or an alternate command registry. The Next.js frontend uses the existing authenticated Rust API and bot bridge.

Preserve the current security properties: Discord OAuth2, fresh guild authorization checks, origin/CSRF protections, owner-only bot-wide information, private bridge authentication, audit history, and confirmation of actual Discord synchronization before reporting a setting change as successful.

## 3. Unified feature commands and Discord interaction design

### Command philosophy

Lemegeton should have **one slash command per major feature area**, not a separate slash command for every action within that feature.

For example, archive actions must not become separate commands such as `/archive add`, `/archive delete`, `/archive edit`, and `/archive search`. Members use the single `/archive` command, then choose the action through Discord's interaction UI.

Likewise, do not create separate commands for every Daily Drop format, ranking action, session action, or discovery operation. Each feature has one clear entry command and its workflows are handled through buttons, select menus, modals, autocomplete, and contextual controls.

This does **not** mean the entire bot is hidden behind one giant `/lemegeton` command. Feature-level commands remain directly discoverable and can open the relevant focused interface.

### Proposed command surface

The following is the intended command organisation. Names can be adjusted during the implementation audit to preserve useful existing naming and avoid Discord command-name conflicts.

| Feature command | Actions available inside that command |
|---|---|
| `/discover` | Search, browse, filter, recommendations, random discovery, comparisons, creator lookup, and media relationships |
| `/archive` | Browse, add/submit, edit, delete, search, filter, manage entries, create/manage mixed collections, report, review where authorized, and configure archive options |
| `/daily` | View today's drop, browse previous drops, submit content, answer polls/trivia, and configure schedules/formats where authorized |
| `/rankings` | Browse rankings, create, edit, close, submit candidates, vote, change a vote while open, and view results |
| `/sessions` | Browse sessions, propose, nominate, vote, schedule, RSVP, edit/cancel where authorized, and view session history |
| `/discussion` | Start, browse, join, manage, and moderate spoiler-aware discussions |
| `/calendar` | Browse releases and community events, filter categories, and configure guild digests where authorized |
| `/profile` | View supported profile information and manage supported provider links |
| `/settings` | Configure guild features, channels, roles, permissions, upload policies, schedules, and moderation defaults where authorized |

The table defines feature entry points, not a requirement to implement every listed operation before the initial migration is useful. The repository audit must map existing commands and workflows to these destinations and identify any genuinely distinct feature that needs its own entry point. Do not add a new command merely because an existing command currently has an add/delete subcommand.

### How a feature command works

A feature command opens a focused panel for that feature. For example, `/archive` opens the archive interface with available actions such as Browse, Submit, Search, Collections, and Manage. Selecting Submit opens a guided modal; selecting an existing entry presents permitted actions such as Edit or Delete. The same principle applies to the other feature commands.

Use optional command parameters only when they materially improve direct access, such as a media title with autocomplete or an attachment where Discord supports it. Do not create subcommands solely to represent CRUD actions. Keep the command itself useful without requiring a subcommand.

### Discord interaction features

| Discord feature | Intended use |
|---|---|
| Buttons | Navigation, confirmation, pagination, voting, RSVP, moderation decisions, and common actions |
| String select menus | Media categories, archive categories, filters, collection selection, ranking choices, and navigation |
| User/role/channel/mentionable selects | Session participants, moderator roles, destination channels, and permission configuration |
| Modals | Structured forms for archive submissions, collection creation, daily content, ranking setup, session proposals, discussions, reports, and configuration |
| Autocomplete | Fast media-title, author, tag, collection, and other supported search suggestions |
| Attachment input | Single-file submissions where the command flow supports it; use configured upload channels for multi-file workflows |
| Embeds | Consistent media cards, archive entries, rankings, event details, and status summaries |
| Ephemeral responses | Private search selections, form progress, personal confirmations, and moderation feedback |
| Public messages and threads | Published archive entries, community prompts, session announcements, and spoiler-aware discussion |
| Discord Scheduled Events | Session events when the guild and bot permissions support them; otherwise use the internal session calendar |
| Discord polls | Simple temporary polls where their limitations fit; use database-backed Lemegeton voting for rankings and other stateful competitions |

Use modal components supported by the Discord API and the installed Discord.js version. If a component is unavailable in the target client or library version, use a normal select/button step before the modal rather than making the whole workflow unavailable.

Do not attempt to put file uploads into a modal unless Discord exposes and the chosen library supports that exact component. File uploads must use supported attachment inputs or configured Discord channels. Preserve per-guild image/audio/video acceptance settings.

### Interaction quality and safety

- Keep navigation predictable, with clear Back, Cancel, Confirm, and Home actions.
- Use ephemeral messages for private or intermediate steps and publish only when a workflow explicitly calls for a shared result.
- Bind interaction state to the initiating user and guild where appropriate. Re-check permissions on every consequential action; hiding a button is not authorization.
- Store durable workflow state in PostgreSQL. Do not rely on a process-local component collector as the only record of a vote, submission, or scheduled event.
- Give expired, stale, unauthorized, or already-completed interactions a useful response.
- Defer long-running provider work correctly and use bounded timeouts.
- Keep component layouts within Discord's current component and message limits.
- Message context-menu actions may provide convenient shortcuts into a feature workflow, but they complement rather than replace the feature-level slash commands.

## 4. First-use onboarding, terms, and privacy

On first use, show the current Terms of Service and privacy information before allowing access to features that require acceptance.

Record the accepted document version and timestamp. If the terms materially change, require acceptance of the new version before continuing. Members must be able to view the current terms again from the hub.

Explain archive visibility and upload rules before accepting a contribution. Do not imply that a server-only submission is globally visible, or that a global contribution is controlled by the submitting server.

## 5. Media discovery

Bring all existing supported discovery features into `/discover`.

### Supported media families

- Anime and manga.
- Light novels, general novels, books, and supported editions.
- Webnovels.
- Movies and television.
- Video games.

### Discovery workflows

- Search and browse by media category with the filters and metadata actually supported by the relevant provider.
- Recommendations, random discovery, similar-title exploration, and comparisons.
- Franchise and cross-media relationship exploration.
- Supported release, season, episode, publication, creator, studio, genre, and platform information.
- Streaming availability by region where the provider supplies it.
- Author and creator work discovery.
- Supported Steam profile, library, store, and game enrichment features.
- Existing account linking and profile displays, including AniList and Steam where currently implemented.

Do not force every media category into an anime-specific data model. Preserve category-specific metadata and clearly mark unavailable fields.

### Provider provenance

Migrate the provider integrations actually present in the repository, including the existing AniList, TMDB, Google Books, webnovel-provider, IGDB, and Steam integrations where supported by the code.

The README documents Novel Updates, Novel Phoenix, NovelFire, and Novelist as separate webnovel sources. Verify each adapter and its current behavior before porting it; documentation alone is not proof that a provider is healthy or returns a particular field.

Keep these evidence types distinct:

- Provider-declared relationships.
- Provider-generated recommendations.
- Local matches calculated from explicit signals such as shared genre labels.
- Community-submitted relationships awaiting review.
- Community-verified relationships reviewed by authorized moderators.

A recommendation, title match, shared genre, collection membership, or community proposal must not be presented as proof of an adaptation, sequel, shared continuity, or chronology.

## 6. Community Archive — the signature system

The existing unified `/archive` system remains the single entry point for all archive operations. Panels remain an archive category; the design must not turn the archive back into a panels-only system or create a separate Panels command.

### Categories

Retain the existing categories and their useful behavior:

- Manga panels.
- Quotes.
- Fanworks.
- Moodboards.
- Soundtracks.
- Scenes.
- Community recommendations.
- Theories.

The category list should be extensible through the existing configuration approach, without creating speculative empty integrations.

### Collections as first-class records

A collection is not another archive category. It is a curated container that can include multiple archive entry types. For example, one collection may contain quotes, soundtrack links, fanworks, recommendations, and related media.

Collections should support:

- A title, description, cover where supported, creator attribution, and tags.
- Multiple entries from different archive categories.
- Search by title, creator, category, tag, and linked media.
- Add/remove entry actions with permission checks.
- Public, server-only, and other explicitly supported visibility scopes.
- A clear view of who contributed each item.
- Moderation and reporting consistent with the underlying entries.

### Submission, upload, and moderation

- Use guided modals for metadata, tags, source links, descriptions, and attribution.
- Allow guild administrators to enable or disable accepted image, audio, and video uploads independently.
- Preserve configured upload channels and the existing server-only versus global archive choice.
- Images remain a supported archive format; audio and video remain opt-in per guild.
- Validate file type, size, source, and storage policy before accepting an upload.
- Preserve the existing private-original and public-generated-media separation in S3.
- Keep review queues, moderator decisions, reports, and audit history.
- Ask contributors to confirm they have the rights or permission required to share an upload.
- Do not make private uploads public by copying them to a public bucket or by exposing permanent object URLs.

Global archive discovery must respect the configured sharing scope. A guild moderator may moderate that guild's submissions but must not gain moderation authority over another guild's resources.

## 7. Daily Drop

Daily Drop is one configurable system with multiple content formats, not a separate command for each format.

Supported formats:

- Question of the Day.
- Quote of the Day.
- Media trivia.
- Daily recommendation.
- Archive spotlight.
- Community poll.

Per-guild settings should include enabled formats, destination channel, posting schedule, timezone, submission permissions, moderation requirements, and whether members may contribute content.

Use modals for submissions and configuration, buttons for responses, and select menus for choosing formats or reviewing entries. The scheduler must be timezone-aware, idempotent, and safe across restarts. Avoid spam, mandatory streaks, or engagement mechanics that punish members for not participating.

## 8. Community Rankings

Build community-created rankings rather than replacing them with a bot-generated score.

Examples include favourite anime, manga, light novels, games, soundtracks, adaptations, or seasonal selections.

A ranking can support:

- Creation and configuration by an authorized member.
- Candidate submission and optional moderator approval.
- Voting through buttons or select menus.
- Vote changes until the configured closing point.
- A visible closing time and published results.
- Guild-specific rankings and explicitly configured shared rankings.
- Seasonal, monthly, and all-time views where enough data exists.
- Clear eligibility, duplicate-entry, and tie-handling rules.

Votes must be persisted, scoped correctly, and protected against duplicate or unauthorized submissions. Do not silently convert a community ranking into an individual user profile or progress tracker.

## 9. Unified Community Sessions

Unify the existing Reading Hub and Media Night into one session system with four activity types:

- **Watch** — films, episodes, or other supported screen media.
- **Read** — manga, novels, webnovels, or books.
- **Play** — games and supported group activities.
- **Discuss** — a focused discussion around a work, topic, or community collection.

A session flow should support nominations, voting where enabled, scheduling, timezone-aware display, RSVP, reminders, a destination channel, and a discussion thread. Use Discord Scheduled Events when available and appropriate, with an internal calendar fallback.

Keep session history at the event/community level. This is not a request to track each member's personal reading, watching, or playing progress.

## 10. Archive Throwbacks

Introduce a configurable resurfacing system for older approved community contributions.

- Highlight archive items, collections, quotes, soundtrack recommendations, fanworks, theories, and other approved categories.
- Allow per-guild frequency, channel, category, and visibility settings.
- Provide a link to the original archive entry and preserve contributor attribution.
- Avoid repeating the same item too frequently.
- Respect the entry's current visibility, deletion, moderation, and permission state at the time it is resurfaced.
- Do not scrape old Discord message history to manufacture archive entries.

## 11. Discussions, release calendar, and media relationships

These existing and proposed community workflows are accessed through their respective feature commands.

### Discussions

Create spoiler-aware discussion threads linked to a selected media item. Capture the title, type of discussion, episode/chapter/volume boundary where relevant, spoiler scope, destination, and opening prompt. Make spoiler status visible before a member opens or joins a discussion.

### Release calendar

Preserve supported media release information and guild-level digest configuration. Let administrators select the destination channel, media categories, timezone, and posting preferences. Only publish release data that the source actually provides; do not invent dates or mappings.

### Media relationships

Let members suggest a relationship with a source or explanation. Route suggestions to an appropriately scoped review queue. Store provenance and distinguish accepted community links from provider-confirmed links.

## 12. Profiles and community information

Retain existing supported profile-linking and public community information. The profile area may show linked providers, supported affinity/comparison outputs, contribution attribution, and eligible community participation summaries.

Do not introduce personal watch/read/play progress, private libraries, or individual tracking histories as part of this redevelopment.

## 13. Server administration and dashboard

### In-Discord administration

The `/settings` command should provide permission-gated guild configuration for:

- Enabled Archive categories and archive visibility modes.
- Accepted image, audio, and video uploads.
- Upload and review channels.
- Moderator roles and review permissions.
- Daily Drop formats, schedule, timezone, and channel.
- Ranking creation permissions and defaults.
- Session categories, announcement channel, and scheduling defaults.
- Discussion and spoiler defaults.
- Release calendar categories and destination.
- Existing command/configuration controls that remain relevant to the unified hub.
- Audit history and supported diagnostics.

Use Discord role and channel selectors where supported. Apply the existing authorization model and audit every consequential settings change.

### Next.js dashboard

Migrate the existing React + TypeScript/Vite frontend to Next.js. Preserve the existing Rust/Axum API and its OAuth2, guild authorization, CSRF, bot bridge, audit, and synchronization behavior initially.

The dashboard should provide the same relevant guild configuration and moderation capabilities as the in-Discord settings area, with a clearer larger-screen interface. Do not create a second permissions model. The browser must never be trusted solely because it supplied a guild, role, channel, or user ID.

## 14. Multi-guild, data, privacy, and security requirements

- Every guild-owned setting, event, vote, discussion, moderation action, and server-only archive resource must include and enforce the invoking guild scope.
- Shared/global records must use an explicit visibility scope and must not inherit the submitting guild's moderation permissions.
- Re-check current member permissions for sensitive actions, including component interactions that were originally displayed to an authorized member.
- Validate and normalize all user input and provider responses.
- Bound external requests, use timeouts, respect provider rate limits, and isolate provider failures.
- Protect OAuth tokens, Discord credentials, S3 credentials, and bridge secrets; never expose them to the frontend or logs.
- Preserve private media originals and signed access patterns. Do not make private objects public as a shortcut.
- Keep background jobs idempotent and resilient to restarts and duplicate delivery.
- Do not report a write, command sync, or configuration change as successful until the relevant operation has actually succeeded.
- Preserve existing data and use focused, reversible migrations only where required.
- Keep dependency additions justified by a concrete requirement.

## 15. Migration plan

The redevelopment is staged so the new bot does not lose existing behavior during the rewrite.

1. **Repository and behavior audit** — inventory all loaded cogs, commands, interactions, jobs, helpers, providers, schemas, dashboard endpoints, deployment scripts, permissions, and tests. Identify which README-documented features are actually implemented.
2. **TypeScript bot foundation** — establish the Node.js/Discord.js runtime, typed configuration, logging, error handling, test setup, and the feature-level command registry with focused entry panels.
3. **Data and domain layer** — port the existing PostgreSQL access and domain behavior without creating competing schemas. Add only the migrations required for new v3 records.
4. **Provider migration** — port and verify existing provider adapters independently, preserving their supported fields, rate limits, error handling, and provenance.
5. **Discovery workflows** — migrate browse, search, recommendations, random discovery, comparisons, relationships, creator lookups, movies/TV, games, Steam, and supported profile features into `/discover` and `/profile`.
6. **Archive** — migrate existing archive behavior first, then add first-class mixed collections and the approved submission/search/moderation improvements.
7. **Community systems** — implement Daily Drop, Community Rankings, Unified Community Sessions, Archive Throwbacks, discussions, and release calendar integration.
8. **Next.js dashboard** — replace the current Vite frontend while retaining the Rust/Axum API and existing authorization model.
9. **Parity and production cutover** — test multi-guild isolation, provider failures, interactions, data compatibility, dashboard authorization, scheduled jobs, and deployment. Switch the live bot only after the feature inventory has acceptable parity.
10. **Retire the Python runtime** — remove the old runtime only after the TypeScript bot is running successfully and the migration has been explicitly verified. Do not delete legacy code early merely to make the repository look cleaner.

The order may be adjusted by dependencies discovered in the audit, but the one-command-per-feature model and preservation of existing behavior remain fixed requirements.

## 16. Acceptance criteria

The v3 redevelopment is ready for release only when:

- The finished bot exposes one clear slash-command entry point per major feature area, as defined in the command-surface table.
- Archive actions such as submit/add, edit, delete, search, and collection management are handled inside `/archive`, not as separate slash commands or CRUD subcommands.
- Daily Drop, rankings, sessions, discussions, discovery, calendar, profiles, and settings each use their respective feature command and Discord interaction UI.
- Buttons, select menus, modals, autocomplete, and contextual actions provide the workflows within each feature command.
- Existing implemented features have a documented migration or retirement decision; no feature is silently lost.
- Archive categories, mixed collections, uploads, moderation, attribution, and server/global visibility work as specified.
- Per-guild data and moderation boundaries are verified with tests.
- Scheduled jobs are timezone-aware, idempotent, and recover safely after restart.
- Provider responses retain attribution and failures are isolated.
- The Next.js dashboard uses the existing Rust/Axum authorization boundary and does not bypass guild permission checks.
- Existing PostgreSQL data and S3 privacy behavior remain intact.
- Terms/privacy acceptance and upload-rights confirmation are enforced at the relevant workflow boundaries.
- Interaction failures, expired controls, missing permissions, unavailable providers, and disabled features produce clear feedback.
- Documentation, deployment instructions, and tests reflect the actual implementation.
- Python is not retired until parity and production cutover checks have passed.

## 17. Development rules for the v3 work

- Work on the existing `lemegeton-v3` branch associated with PR #17. Do not create another PR for this effort.
- PR #17 must remain Draft until explicitly approved for review.
- Keep implementation changes focused and make commits small and meaningful; do not bundle unrelated refactors into the migration.
- Inspect current implementations and callers before porting or replacing behavior.
- Prefer the minimum code and dependencies needed for each phase.
- Add focused tests for changed behavior and reproduce existing bugs where practical.
- Run relevant checks and inspect the final diff before reporting completion.
- Never claim tests, builds, provider calls, or deployments succeeded unless they were actually run.
- Do not begin the implementation phases merely because this specification has been committed; the specification commit records the approved direction, not completion of the redevelopment.

## 18. Discord API references

- [Discord Application Commands](https://discord.com/developers/docs/interactions/slash-commands)
- [Discord Message Components](https://discord.com/developers/docs/interactions/message-components)
- [Discord Developer documentation](https://discord.com/developers/docs/)

Discord's application-command model supports slash commands, context menus, and component-driven interactions. The v3 baseline uses one slash command per major feature and components for actions within each feature. Re-check the current API and Discord.js support when implementing each component; do not rely on obsolete component limits or unsupported modal inputs.

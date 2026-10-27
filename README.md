# Lemegeton

### A multi-guild Discord bot for connected media discovery, community systems, and server tooling.

Lemegeton brings anime, manga, light novels, books, webnovels, movies, television, and video games into one Discord-native discovery experience. It connects provider metadata with a provenance-aware relationship graph, community-curated archives, server-specific events, account features, customization, and an optional web dashboard.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white">
  <img alt="discord.py" src="https://img.shields.io/badge/discord.py-2.7.1-5865F2?logo=discord&logoColor=white">
  <img alt="Database" src="https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql&logoColor=white">
  <img alt="Dashboard" src="https://img.shields.io/badge/Dashboard-Rust%20%2B%20React-111827">
  <img alt="Multi-guild" src="https://img.shields.io/badge/Architecture-Multi--guild-0F766E">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-16A34A">
</p>

> **Project principle:** connect systems without pretending their data is interchangeable. A provider-confirmed adaptation, a provider recommendation, a genre-overlap match, and a moderator-approved community suggestion are different kinds of evidence.

---

## Contents

- [Architecture map](#architecture-map)
- [What Lemegeton does](#what-lemegeton-does)
- [Connected media discovery](#connected-media-discovery)
- [Community archives and events](#community-archives-and-events)
- [Accounts, gaming, and customization](#accounts-gaming-and-customization)
- [Dashboard and web surfaces](#dashboard-and-web-surfaces)
- [Image storage and privacy](#image-storage-and-privacy)
- [Multi-guild data boundaries](#multi-guild-data-boundaries)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Development and verification](#development-and-verification)
- [Repository map](#repository-map)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Architecture map

This is the high-level architecture of the implemented application. It deliberately shows the main execution paths and the connections between command interfaces, business logic, external metadata providers, PostgreSQL, object storage, and the optional web control plane. It is a system map, not a claim that every optional integration is configured or available in every deployment.

~~~mermaid
flowchart TB
    %% ============================================================
    %% LEMEGETON — CONNECTED COMMAND AND DATA ARCHITECTURE
    %% ============================================================

    subgraph ACTORS["01 · People and client surfaces"]
        MEMBER["Discord member"]
        MOD["Server moderator / administrator"]
        OWNER["Bot owner"]
        DISCORD["Discord client<br/>Slash commands · Selects · Modals · Buttons"]
        BROWSER["Web browser"]
    end

    subgraph GATEWAY["02 · Discord runtime and routing"]
        GATEWAY_API["Discord Gateway / Interactions API"]
        BOT["bot.py<br/>Bot lifecycle · Extension loading · Runtime hooks"]
        TREE["Application-command tree"]
        META["Command metadata registry<br/>command_meta · Sections · Enable policy"]
        ERRORS["Shared error handling<br/>Private response · Structured log context"]
        FEEDBACK["/feedback<br/>Bug reports and feature requests"]
    end

    subgraph COMMANDS["03 · Command and interaction layer"]
        HELP["/help<br/>Runtime-filtered dropdown"]
        HUB["/discovery-hub<br/>Guided command directory"]
        BROWSE["/browse<br/>Search · Filters · Sort"]
        FRANCHISE["/franchise<br/>Provider-attributed relationships"]
        CONNECTIONS["/connections<br/>Resolved title relationship view"]
        ORDER["/reading-order<br/>Known release relationships"]
        SIMILAR["/similar<br/>Related media and recommendations"]
        GAME["/game<br/>IGDB result + optional Steam enrichment"]
        TMDB_CMDS["Movie / TV commands<br/>Watch providers · Credits · Trailers<br/>Collections · Region"]
        BOOK_CMDS["Book / webnovel commands<br/>Author works · Novel Updates lookup"]
        COMMUNITY["Community commands<br/>Archives · Discussions · Polls · Quizzes"]
        PANELS["/panels<br/>Shared manga panel archive"]
        POTD["/panel-of-the-day<br/>Server's daily safe selection"]
        GRID["/3x3<br/>Generated image grids"]
        ANILIST_EMBED["AniList site embeds<br/>Entities · Staff / character collage"]
        CUSTOM_ROLE_UI["/custom-role<br/>Member role panel"]
        CUSTOM_ROLE_ADMIN["/custom-role-admin<br/>Server role administration"]
    end

    subgraph DOMAIN["04 · Shared application services"]
        ANILIST_HELPER["AniList helpers<br/>GraphQL · Search · Media details"]
        TMDB_HELPER["TMDB request helpers<br/>Search · Metadata · Availability"]
        BOOKS_HELPER["Google Books lookup"]
        NU_HELPER["Novel Updates scraper helper"]
        IGDB_HELPER["IGDB / Twitch authentication + search"]
        STEAM_HELPER["Steam search and store details"]
        MEDIA_GRAPH["helpers/media_graph.py<br/>Normalize titles · Store / query edges<br/>Retain relationship provenance"]
        MEDIA_STORAGE["helpers/media_storage.py<br/>S3-compatible upload · Registry<br/>Private signing · Public URL policy"]
        ROLE_SERVICE["Custom Roles service<br/>Role eligibility · Validation · Audit"]
        ERROR_SERVICE["command_error_handler.py<br/>Slash and component failure guidance"]
        COMMAND_POLICY["Guild command policy<br/>Runtime authorization and overrides"]
    end

    subgraph PROVIDERS["05 · External services and media sources"]
        ANILIST["AniList GraphQL API"]
        TMDB["The Movie Database API"]
        GOOGLE_BOOKS["Google Books API"]
        NOVEL_UPDATES["Novel Updates website / scraper"]
        IGDB["IGDB API"]
        STEAM["Steam Web API / Store"]
        DISCORD_CDN["Discord attachment / media delivery"]
        LLM["Optional configured model providers<br/>Only used by features that implement them"]
    end

    subgraph DATA["06 · PostgreSQL and application records"]
        DB["database.py<br/>Shared async PostgreSQL pool"]
        USERS["Account and user data<br/>Guild-aware records and preferences"]
        GUILD_CONFIG["Guild configuration<br/>Command settings · Roles · Channels"]
        GRAPH_TABLE[("media_relationship_graph")]
        SUGGESTIONS[("media_link_suggestions")]
        DISCUSSIONS[("connected_media_discussions")]
        ARCHIVE_TABLES[("Community archive / event tables")]
        PANEL_TABLES[("Panels · Tags · Moderation records")]
        ASSET_TABLE[("media_assets<br/>Object metadata and storage references")]
        CUSTOM_ROLE_TABLES[("Custom Role configuration<br/>Saved state and audit data")]
    end

    subgraph OBJECTS["07 · Image object storage"]
        PRIVATE_S3[("Private S3-compatible bucket<br/>Panel originals · Role icon originals")]
        PUBLIC_S3[("Separate public output bucket")]
        CDN["HTTPS public base URL / CDN"]
        FALLBACK["Legacy Discord-backed image path<br/>Used where the existing flow supports it"]
    end

    subgraph WEB["08 · Optional web control plane"]
        DASH_UI["dashboard-frontend/<br/>React + TypeScript + Vite"]
        RUST["dashboard-rs/<br/>Rust / Axum · OAuth session · CSRF"]
        BRIDGE["Narrow bot runtime bridge<br/>Live command registry and guild state"]
        PICKER["Python Custom Role picker<br/>Private listener behind dashboard proxy"]
        OAUTH["Discord OAuth2<br/>Identity and current guild permissions"]
    end

    subgraph OPS["09 · Operations and feedback"]
        LOGS["Module and runtime logs"]
        CI["GitHub Actions<br/>Python checks · Frontend checks<br/>Rust tests and audit"]
        DOCS["Documentation<br/>Media discovery · Dashboard · Deployment<br/>Security review · Custom Roles"]
    end

    %% User entry and runtime
    MEMBER --> DISCORD
    MOD --> DISCORD
    OWNER --> DISCORD
    DISCORD --> GATEWAY_API
    GATEWAY_API --> BOT
    BOT --> TREE
    TREE --> META
    TREE --> COMMANDS
    META --> COMMAND_POLICY
    HELP --> TREE
    HUB --> TREE
    COMMUNITY --> ERRORS

    %% Discovery command to domain flows
    BROWSE --> ANILIST_HELPER
    BROWSE --> TMDB_HELPER
    BROWSE --> BOOKS_HELPER
    BROWSE --> NU_HELPER
    FRANCHISE --> ANILIST_HELPER
    FRANCHISE --> TMDB_HELPER
    FRANCHISE --> MEDIA_GRAPH
    CONNECTIONS --> FRANCHISE
    ORDER --> FRANCHISE
    SIMILAR --> ANILIST_HELPER
    SIMILAR --> TMDB_HELPER
    SIMILAR --> BOOKS_HELPER
    SIMILAR --> NU_HELPER
    SIMILAR --> MEDIA_GRAPH
    GAME --> IGDB_HELPER
    GAME --> STEAM_HELPER
    GAME --> MEDIA_GRAPH
    TMDB_CMDS --> TMDB_HELPER
    BOOK_CMDS --> BOOKS_HELPER
    BOOK_CMDS --> NU_HELPER
    COMMUNITY --> MEDIA_GRAPH
    PANELS --> MEDIA_STORAGE
    PANELS --> PANEL_TABLES
    POTD --> PANEL_TABLES
    POTD --> MEDIA_STORAGE
    GRID --> MEDIA_STORAGE
    ANILIST_EMBED --> MEDIA_STORAGE
    CUSTOM_ROLE_UI --> ROLE_SERVICE
    CUSTOM_ROLE_ADMIN --> ROLE_SERVICE

    %% Provider boundaries
    ANILIST_HELPER --> ANILIST
    TMDB_HELPER --> TMDB
    BOOKS_HELPER --> GOOGLE_BOOKS
    NU_HELPER --> NOVEL_UPDATES
    IGDB_HELPER --> IGDB
    STEAM_HELPER --> STEAM
    ANILIST_EMBED --> ANILIST
    COMMUNITY -. "only when an implemented feature uses a model" .-> LLM

    %% Shared persistence
    MEDIA_GRAPH --> DB
    MEDIA_STORAGE --> DB
    ROLE_SERVICE --> DB
    PANELS --> DB
    COMMUNITY --> DB
    ANILIST_HELPER --> DB
    DB --> USERS
    DB --> GUILD_CONFIG
    DB --> GRAPH_TABLE
    DB --> SUGGESTIONS
    DB --> DISCUSSIONS
    DB --> ARCHIVE_TABLES
    DB --> PANEL_TABLES
    DB --> ASSET_TABLE
    DB --> CUSTOM_ROLE_TABLES
    MEDIA_GRAPH --> GRAPH_TABLE
    MEDIA_GRAPH --> SUGGESTIONS
    MEDIA_GRAPH --> DISCUSSIONS
    MEDIA_GRAPH --> ARCHIVE_TABLES
    MEDIA_STORAGE --> ASSET_TABLE

    %% Object storage and fallback paths
    MEDIA_STORAGE --> PRIVATE_S3
    MEDIA_STORAGE --> PUBLIC_S3
    PUBLIC_S3 --> CDN
    PANELS -. "legacy uploads / existing records" .-> FALLBACK
    FALLBACK --> DISCORD_CDN
    POTD -. "legacy attachment URL when present" .-> DISCORD_CDN
    PRIVATE_S3 -. "short-lived signed URL" .-> DISCORD_CDN

    %% Web control plane
    BROWSER --> DASH_UI
    DASH_UI --> RUST
    RUST --> OAUTH
    RUST --> BRIDGE
    BRIDGE --> BOT
    RUST --> PICKER
    PICKER --> ROLE_SERVICE
    ROLE_SERVICE --> CUSTOM_ROLE_TABLES
    ROLE_SERVICE --> PRIVATE_S3

    %% Diagnostics
    BOT --> ERRORS
    ERRORS --> ERROR_SERVICE
    ERROR_SERVICE --> LOGS
    ERRORS --> FEEDBACK
    MEDIA_GRAPH --> LOGS
    MEDIA_STORAGE --> LOGS
    ROLE_SERVICE --> LOGS
    CI --> DOCS

    %% Visual grouping
    classDef interaction fill:#111827,stroke:#64748b,color:#f8fafc
    classDef service fill:#172554,stroke:#60a5fa,color:#eff6ff
    classDef provider fill:#1f2937,stroke:#a78bfa,color:#f5f3ff
    classDef database fill:#052e2b,stroke:#2dd4bf,color:#ecfdf5
    classDef storage fill:#3f1d0b,stroke:#fb923c,color:#fff7ed
    classDef operations fill:#27272a,stroke:#a1a1aa,color:#fafafa

    class MEMBER,MOD,OWNER,DISCORD,BROWSER,GATEWAY_API interaction
    class BOT,TREE,META,HELP,HUB,BROWSE,FRANCHISE,CONNECTIONS,ORDER,SIMILAR,GAME,TMDB_CMDS,BOOK_CMDS,COMMUNITY,PANELS,POTD,GRID,ANILIST_EMBED,CUSTOM_ROLE_UI,CUSTOM_ROLE_ADMIN,DASH_UI,RUST,BRIDGE,PICKER,ERRORS,ERROR_SERVICE,COMMAND_POLICY service
    class ANILIST_HELPER,TMDB_HELPER,BOOKS_HELPER,NU_HELPER,IGDB_HELPER,STEAM_HELPER,ANILIST,TMDB,GOOGLE_BOOKS,NOVEL_UPDATES,IGDB,STEAM,DISCORD_CDN,LLM provider
    class DB,USERS,GUILD_CONFIG,GRAPH_TABLE,SUGGESTIONS,DISCUSSIONS,ARCHIVE_TABLES,PANEL_TABLES,ASSET_TABLE,CUSTOM_ROLE_TABLES database
    class MEDIA_STORAGE,PRIVATE_S3,PUBLIC_S3,CDN,FALLBACK storage
    class LOGS,CI,DOCS,FEEDBACK,OAUTH,MEDIA_GRAPH,ROLE_SERVICE,ANILIST_EMBED service
~~~

### How a cross-media lookup moves through the system

The relationship graph helps different systems discover links without replacing each provider's metadata model. The command resolves a title, calls the provider appropriate to the selected category, stores source-labeled relationships, and then adds eligible stored links and community resources. Errors or missing provider records should produce a limitation or no-result message, not fabricated relationships.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Discord member
    participant Cmd as Slash-command cog
    participant Provider as Metadata provider helper
    participant Graph as Media relationship graph
    participant DB as PostgreSQL
    participant UI as Discord response

    User->>Cmd: /franchise, /connections, /reading-order, /similar, or /game
    Cmd->>Provider: Search the selected media category
    alt Provider returns several plausible matches
        Provider-->>Cmd: Candidate records
        Cmd-->>User: Owner-bound title picker
        User->>Cmd: Select exact title
    else Provider returns one usable match
        Provider-->>Cmd: Resolved metadata
    end
    Cmd->>Provider: Fetch supported details and relationships
    Provider-->>Cmd: Provider metadata / relationships
    Cmd->>Graph: Record relationships with source provenance
    Graph->>DB: Deduplicated write and/or graph lookup
    DB-->>Graph: Saved links
    Graph-->>Cmd: Related titles and eligible community resources
    Cmd->>UI: Embed labels provider data vs recommendations/community links
    UI-->>User: Result plus source URLs and stated limitations

    opt Provider unavailable or unexpected failure
        Provider-->>Cmd: Timeout, invalid response, or no usable record
        Cmd->>UI: Safe error / fallback message
    end
~~~

### Image storage decisions

The storage path is deliberately different for private originals and generated, non-sensitive composites.

~~~mermaid
flowchart TD
    START["Image-producing or image-uploading command"]
    KIND{"What kind of image?"}
    ORIGINAL["User-supplied original<br/>Panel / Custom Role icon source"]
    GENERATED["Generated image<br/>3x3 grid / staff-character collage"]
    PVT{"Private S3 configuration valid?"}
    PUB{"Separate public bucket + HTTPS base URL valid?"}
    PRIVATE[("Private S3 bucket")]
    PUBLIC[("Public generated-output bucket")]
    SIGN["Short-lived signed URL"]
    CDN["Configured HTTPS base URL / CDN"]
    LEGACY["Existing Discord attachment path<br/>where supported"]
    META[("media_assets registry")]
    PRIVATE_RESPONSE["Render private asset reference"]
    PUBLIC_RESPONSE["Render public generated image"]
    FALLBACK["Keep existing Discord file attachment"]
    DENY["Do not expose private originals as public content"]

    START --> KIND
    KIND -->|Original upload| ORIGINAL
    KIND -->|Generated composite| GENERATED
    ORIGINAL --> PVT
    PVT -->|Yes| PRIVATE
    PRIVATE --> META
    META --> SIGN
    SIGN --> PRIVATE_RESPONSE
    PVT -->|No| LEGACY
    LEGACY --> PRIVATE_RESPONSE
    GENERATED --> PUB
    PUB -->|Yes| PUBLIC
    PUBLIC --> META
    PUBLIC --> CDN
    CDN --> PUBLIC_RESPONSE
    PUB -->|No| FALLBACK
    ORIGINAL -. "Must never be copied to public output by default" .-> DENY
~~~

---

## What Lemegeton does

### Connected media discovery

- **Anime and manga:** AniList-backed search, browsing, title details, supported relationships, and account-linked features.
- **Light novels, books, and webnovels:** category-aware discovery using the existing metadata providers and Novel Updates scraper path where supported.
- **Movies and television:** TMDB metadata, listed watch availability by region, credited-person filmographies, videos, collections, and available release information.
- **Video games:** IGDB metadata with optional Steam store enrichment. Steam data is added only when the game matching logic can identify a suitable result.
- **Cross-media links:** a shared relationship graph connects results and community resources while keeping provider evidence, recommendations, locally calculated similarity, and community-approved links distinct.
- **Interactive resolution:** title pickers help users choose between similarly named works instead of silently joining the wrong entries.

### Accounts and community features

- AniList account linking and rich user/profile displays.
- AniList activity and affinity tools and available leaderboard features.
- Shared manga Panels, attributed quotes, credited fanworks, moodboards, soundtrack links, memorable scenes, member-written recommendations, and spoiler-aware theories.
- Server-specific reading/discussion features, polls, brackets, adaptation votes, and source-linked quizzes where the relevant command is loaded.
- Feedback and bug-report submission through <code>/feedback</code>.

### Gaming and server management

- Steam profiles, game search, library-aware game features, and free-game checks where configured.
- Guild command configuration and the Discord <code>/dashboard</code>.
- Theme customization and per-server defaults.
- Custom Roles for eligible members, with a private role editor and web color picker.
- Invite analytics, server information, notification settings, and administrator/moderator tools.

> The running bot's <code>/help</code> dropdown is the best source for the exact commands that are registered and enabled in a particular deployment. This README describes the main systems, not a hard-coded command count.

---

## Connected media discovery

The cross-media commands reuse provider helpers and the shared relationship graph rather than creating independent data silos.

| Command | What it does | Important boundary |
| --- | --- | --- |
| <code>/browse</code> | Interactive search across supported media categories and metadata sources. | Filters and returned fields depend on the chosen media type and provider. |
| <code>/franchise</code> | Explore provider-declared relationships and supported franchise / collection information. | Provider recommendations and cross-provider title matches are labelled separately from confirmed relationships. |
| <code>/connections</code> | Resolve a title and browse its known related works. | Reuses the title resolver and a selection menu where needed. |
| <code>/reading-order</code> | Browse available publication/release relationships for books, webnovels, manga, anime, and related formats. | Release order is not automatically story chronology; chapter-to-episode mappings are not invented. |
| <code>/similar</code> | Find related works using available provider suggestions, local genre overlap, saved links, and eligible human-written community recommendations. | Different source types stay labelled; a shared genre is not proof of an adaptation. |
| <code>/link-suggest</code> | Submit a proposed relationship between two media entries. | A suggestion enters review; it is not trusted immediately. Metadata URLs must be HTTPS and the evidence explanation must meet the command's validation. |
| <code>/link-review</code> | List, inspect, approve, or reject relationship suggestions. | Requires Manage Server or Manage Messages. Community approval is not the same as provider confirmation. |
| <code>/discovery-hub</code> | Open a sectioned guide to discovery, novels, movies/TV, gaming, archives, and community events. | The hub filters command references against the commands currently registered. |
| <code>/game</code> | Search IGDB and add Steam store details when a suitable exact title match is available. | Fuzzy similarity alone does not establish that a Steam listing is the same game. |

### Movie, TV, book, and webnovel commands

- <code>/where-to-watch</code> queries listed streaming, rental, and purchase availability for a movie or TV title in the selected region. Availability can change and should be verified at the provider.
- <code>/person-credits</code> displays the TMDB filmography for a selected person.
- <code>/trailers</code> shows supported TMDB-listed YouTube and Vimeo videos for a selected movie or series.
- <code>/collection-guide</code> lists a TMDB movie collection and its available release dates.
- <code>/media-region</code> changes the server's default two-letter streaming region and requires Manage Server permission.
- <code>/author-works</code> searches Google Books for works attributed to an author.
- <code>/webnovel-updates</code> uses the existing Novel Updates scraper helper. Results depend on the source page and scraper remaining compatible.
- <code>/chapter-discussion</code> and <code>/episode-discussion</code> create spoiler-aware discussions for the current server.

Provider credentials and source availability vary. TMDB commands require <code>TMDB_BEARER_TOKEN</code>; game enrichment uses the available IGDB and Steam configuration. Missing provider data should be explained rather than guessed.

---

## Community archives and events

The archive layer makes community contributions discoverable while keeping the approval and reporting flows explicit.

| Command | Purpose |
| --- | --- |
| <code>/panels</code> | Browse, search, contribute to, or manage the shared manga Panel archive. |
| <code>/panel-of-the-day</code> | View the selected safe Panel for the current server's daily feature. |
| <code>/quotes</code> | Browse, search, randomize, or submit short attributed quotes. |
| <code>/fanworks</code> | Discover or submit credited fan art, edits, wallpapers, and videos. |
| <code>/moodboards</code> | Share themed boards built around multiple works. |
| <code>/soundtracks</code> | Index soundtrack links from legitimate music/video platforms. |
| <code>/scenes</code> | Save memorable scene references and optional source links. |
| <code>/recommendation-board</code> | Share human-written recommendations and reasons. |
| <code>/theories</code> | Share spoiler-marked theories with source attribution. |
| <code>/archive-mine</code> | Check your own submissions and their review state in the current server. |
| <code>/archive-review</code> | Review submissions from the server where they were submitted. |
| <code>/archive-report</code> | Report an approved entry to the current server's moderators. |
| <code>/archive-report-review</code> | Triage reports; removal is restricted to the originating server. |
| <code>/media-bracket</code> | Create a server-specific media bracket, vote, or view results. |
| <code>/adaptation-vote</code> | Poll between two versions and inspect community preferences. |
| <code>/media-quiz</code> | Add source-linked trivia, play a question, and submit an answer privately. |

Archive and event writes are backed by database records. Moderation decisions and event participation are scoped to the originating guild where applicable. A community-submitted relationship remains distinct from data asserted by AniList, TMDB, or another provider.

---

## Accounts, gaming, and customization

### AniList

Lemegeton uses the existing AniList integration for supported anime/manga data, profiles, personal-list features, and relationship metadata. Account linking is needed for commands that rely on a user's own AniList account; public provider searches do not necessarily require it.

### Gaming

- Steam profile, search, store enrichment, and available library-aware discovery.
- IGDB-first game metadata through the configured Twitch/IGDB API credentials.
- Free-game checks and notifications where the associated providers and configuration are available.
- Cross-media graph links can connect game results to related media and eligible community resources.

### Custom Roles

Custom Roles let eligible members style their own role and give administrators a controlled server setup panel. The feature includes name/color/icon editing, a private web color picker, eligibility and permission checks, saved state, audit information, and explicit confirmation for large removal operations.

- <code>/custom-role</code> opens the member's private panel.
- <code>/custom-role-admin</code> provides server setup, eligibility, anchor-role, channel, cooldown, moderation-log, and maintenance controls.
- The bot requires Manage Roles, and its role must be positioned correctly relative to the configured anchor.
- Enhanced role colors and icons depend on the server's actual Discord entitlements.
- Uploaded icon originals can use private S3 storage when it is configured; database fallback remains available where implemented.

Full setup details: [Custom Roles handoff guide](docs/HANDOFF_NOTES.md) · [Custom Roles specification](docs/CUSTOM_ROLES_SPEC.md).

---

## Dashboard and web surfaces

Lemegeton has separate but connected management interfaces.

### Discord dashboard

The <code>/dashboard</code> command organizes dashboard-managed application commands by section and can change a guild's command configuration. The inventory is built from the live command metadata registry; it is not supposed to be an independent, static list of commands.

### Web dashboard

The optional web control plane uses:

- **Rust / Axum** in <code>dashboard-rs/</code> for the public same-origin service, Discord OAuth2 session handling, CSRF/origin protections, and server-side authorization checks.
- **React + TypeScript + Vite** in <code>dashboard-frontend/</code> for the browser interface.
- A narrow internal bridge so the Rust service can request live bot operations without creating a second Discord client or command registry.
- The existing Python Custom Role picker behind a private listener and the Rust service's reverse-proxy path.

The dashboard revalidates current guild permissions and bot membership for guild-specific operations. It does not offer arbitrary shell execution, raw SQL, unrestricted code execution, or general-purpose cog reload controls. Keep internal bridge and picker listeners private.

Read [Web dashboard setup and security boundaries](docs/DASHBOARD.md), [security review](docs/SECURITY_AUDIT.md), or the [VPS/systemd/Nginx guide](deploy/vps/README.md).

---

## Image storage and privacy

The image-storage service is shared by the Panel archive, Custom Roles, generated grids, staff/character collages, and media-resource displays where integrated.

### Private originals

Configure <code>S3_BUCKET</code> with S3-compatible credentials for new Panel images and Custom Role icon originals. The PostgreSQL <code>media_assets</code> table stores metadata and references; the actual image bytes remain in object storage. Private assets are displayed through short-lived signed URLs, subject to the configured TTL.

Existing Discord-hosted Panels remain supported. Existing Custom Role image records are not automatically bulk-migrated just because S3 is added.

### Generated public output

The <code>/3x3</code> grid generator and the AniList staff/character collage output may use a **separate** public output destination:

- <code>S3_PUBLIC_BUCKET</code> — public or CDN-served destination for generated, non-sensitive imagery only.
- <code>S3_PUBLIC_BASE_URL</code> — valid HTTPS base URL for that destination.

The public output path is disabled unless the separate bucket and HTTPS base URL are valid. Generated outputs fall back to the prior Discord attachment path where implemented. The private and public bucket names must not be the same. Do not upload private originals or role icons to the public generated-output bucket.

| Setting | Purpose |
| --- | --- |
| <code>S3_BUCKET</code> | Private originals bucket. |
| <code>S3_ENDPOINT_URL</code> | Optional endpoint for Cloudflare R2, MinIO, or another S3-compatible service. |
| <code>S3_REGION</code> | S3 region; defaults to <code>us-east-1</code> in the current environment template. |
| <code>S3_ACCESS_KEY_ID</code> / <code>S3_SECRET_ACCESS_KEY</code> | Optional explicit access credentials; set both or neither. |
| <code>S3_SIGNED_URL_TTL_SECONDS</code> | Private signed-URL TTL; current storage helper bounds it to 60–3,600 seconds. |
| <code>S3_PUBLIC_BUCKET</code> | Separate output bucket for generated public imagery only. |
| <code>S3_PUBLIC_BASE_URL</code> | HTTPS base URL/CDN for the public output destination. |

Configure object lifecycle rules according to the retention requirements of your deployment, and keep credentials out of source control.

---

## Multi-guild data boundaries

Lemegeton is intended to run in multiple Discord servers from one bot process.

- **Guild configuration stays independent.** Role/channel settings, command overrides, discussion threads, polls, brackets, quiz sessions, and moderation queues use the current guild context where applicable.
- **Shared provider data stays attributed.** Provider records and public archive records can be discovered across features without becoming server-specific source facts.
- **Community-approved relationships stay scoped.** The graph stores provenance and guild ownership for community links so one server's approval is not represented as a global provider fact.
- **Shared media assets stay referenced.** The asset registry stores object metadata and foreign keys instead of large image bodies.
- **Live command visibility is runtime-based.** Help and the Discovery Hub avoid presenting unloaded commands as available, while the command policy and dashboard use the actual registry/implemented configuration paths.

Developers must pass guild context for guild-owned actions and avoid making moderation or event decisions using records from another server. Run isolation checks before accepting a change that alters data ownership or lookup queries.

---

## Quick start

### Requirements

- Python 3.13+.
- A Discord application and bot token.
- PostgreSQL connection access.
- Optional API credentials for the media providers or features you intend to use.
- Optional Node.js 22+ and a Rust toolchain if you intend to build the web dashboard.

### Run the bot locally

1. Clone the repository and enter its directory.
2. Create and activate a virtual environment.
3. Install Python dependencies.
4. Copy <code>.env.example</code> to <code>.env</code>.
5. Configure the Discord token and PostgreSQL connection.
6. Add optional provider credentials as required.
7. Run <code>python bot.py</code>.

~~~bash
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
# Edit .env; keep credentials private.
python bot.py
~~~

On Windows PowerShell, use <code>.venv\Scripts\Activate.ps1</code> to activate the virtual environment and copy the template with <code>Copy-Item .env.example .env</code>.

The bot needs a reachable PostgreSQL instance. <code>DATABASE_URL</code>, <code>POSTGRES_DSN</code>, or <code>POSTGRES_URL</code> can supply the connection URL; alternatively configure the individual <code>POSTGRES_HOST</code>, <code>POSTGRES_PORT</code>, <code>POSTGRES_DB</code>, <code>POSTGRES_USER</code>, and <code>POSTGRES_PASSWORD</code> values. The shared database layer creates the async PostgreSQL pool during startup.

---

## Configuration

Use <code>.env.example</code> as the complete reference for the current environment variable names. The table below highlights the main settings, not every optional tuning flag.

| Variable | Required for | Notes |
| --- | --- | --- |
| <code>DISCORD_TOKEN</code> | Bot startup | Secret from the Discord Developer Portal. Never commit it. |
| <code>DATABASE_URL</code> or <code>POSTGRES_DSN</code> | Persistent database features | PostgreSQL connection string. The supported PostgreSQL environment variables are also listed above. |
| <code>BOT_ID</code> | Optional bot identity configuration | Bot's Discord user/application ID where needed. |
| <code>GUILD_ID</code> | Optional primary-guild defaults | Do not use it as a substitute for runtime guild context. |
| <code>ADMIN_DISCORD_ID</code> | Owner/admin controls | Discord ID used by configured owner/admin checks. |
| <code>STEAM_API_KEY</code> | Steam API features | Optional Steam Web API key. |
| <code>IGDB_CLIENT_ID</code> + <code>IGDB_CLIENT_SECRET</code> | IGDB game metadata | Twitch/IGDB API application credentials. |
| <code>TMDB_BEARER_TOKEN</code> | TMDB movie/TV features | Read-access token; keep private. |
| <code>MDBLIST_API_KEY</code> | Optional enriched TMDB display | Adds supported Metacritic score fields where integrated. |
| <code>OPENAI_API_KEY</code>, <code>OPENROUTER_API_KEY</code>, <code>GEMINI_API_KEY</code>, <code>OLLAMA_HOST</code> | Only features that support the configured model provider | These variables do not mean every recommendation or graph operation is LLM-generated. |
| <code>S3_*</code> | Object-backed private originals / public generated output | Read the [storage section](#image-storage-and-privacy) before enabling a public bucket. |
| <code>DASHBOARD_*</code> | Optional web dashboard | Configure OAuth callback, public origin, cookie security, bridge secret, and internal listeners as documented in [docs/DASHBOARD.md](docs/DASHBOARD.md). |
| <code>CUSTOM_ROLES_*</code> | Custom Role settings | Feature limits and picker settings are documented in [docs/HANDOFF_NOTES.md](docs/HANDOFF_NOTES.md). |

In production, use HTTPS for the public dashboard and color picker, enable secure cookies, use a strong bridge secret, and keep internal service listeners inaccessible from the public network.

---

## Development and verification

Run commands from the repository root unless a tool's guide says otherwise. Do not treat a command listed here as evidence that it passed; use the actual command output or CI result.

### Python

~~~bash
python -m compileall -q bot.py web config.py cogs/utilities/help.py   cogs_test/general_commands/dashboard.py   cogs_test/general_commands/connected_media.py   cogs_test/general_commands/cross_media_recommendations.py   cogs_test/general_commands/discovery_hub.py   cogs_test/general_commands/franchise.py   cogs_test/general_commands/game.py   cogs/media/panel.py cogs/media/community_archives.py   cogs/media/three_by_three.py cogs/social/anilist_site_embed.py   helpers/media_storage.py helpers/media_graph.py   helpers/custom_roles/service.py helpers/custom_roles/storage.py   tests/test_media_storage.py tests/test_media_graph.py

python -m unittest discover -s tests -p "test_media_storage.py"
python -m unittest discover -s tests -p "test_media_graph.py"
python -m unittest discover -s tests -p "test_dashboard_bridge.py"
python -m unittest discover -s tests -p "test_custom_role_picker_server.py"
python -m unittest discover -s tests -p "test_rate_limit_memory.py"
python -m unittest discover -s tests -p "test_dashboard_assets.py"
python -m unittest discover -s tests -p "test_dashboard_command_policy.py"
~~~

### Web dashboard

~~~bash
npm install --prefix dashboard-frontend
npm run typecheck --prefix dashboard-frontend
npm audit --prefix dashboard-frontend --audit-level=high
npm run build --prefix dashboard-frontend
cargo test --workspace
cargo audit
~~~

The repository CI workflow runs applicable frontend checks, Rust tests/audit, Python compilation, and the focused regression suites when relevant files change.

### Engineering conventions

- Prefer asynchronous I/O for network and database operations.
- Reuse the existing provider helpers instead of implementing duplicate clients.
- Keep API/provider parsing separate from Discord response code where the existing architecture supports it.
- Pass the current guild ID to guild-owned data and permission-sensitive actions.
- Preserve provenance between provider data, recommendations, local ranking, and community submissions.
- Treat missing metadata, rate limits, malformed responses, timeouts, permission failures, and expired interactions as normal failure cases.
- Add focused tests when a change meaningfully alters data handling, authorization, provider parsing, persistence, or interaction behavior.
- Update <code>/help</code>, this README, and the relevant feature guide when a change adds commands or alters user-visible behavior.

---

## Repository map

~~~text
Lemegeton/
├── bot.py                              # Discord runtime, event/error routing, private service adapters
├── config.py                           # Environment-backed runtime defaults
├── database.py                         # Shared async PostgreSQL connection pool and query helpers
├── cogs/
│   ├── media/
│   │   ├── browse.py                   # Media browsing
│   │   ├── panel.py                    # Shared manga Panel archive
│   │   ├── community_archives.py       # Quotes, fanworks, polls, quizzes, reports, Panel of the Day
│   │   └── three_by_three.py           # Generated 3x3 grids
│   ├── social/
│   │   └── anilist_site_embed.py       # AniList URLs, entity embeds and staff/character output
│   └── utilities/                      # Help and utility command surfaces
├── cogs_test/
│   └── general_commands/
│       ├── connected_media.py          # TMDB utilities, relationships, discussions and link review
│       ├── cross_media_recommendations.py # Similarity and cross-provider recommendations
│       ├── discovery_hub.py             # Interactive media-discovery entry point
│       ├── franchise.py                # Provider-backed franchise resolver
│       ├── game.py                     # IGDB + optional Steam enrichment
│       └── dashboard.py                # Dashboard command registry and command metadata
├── helpers/
│   ├── anilist_helper.py               # AniList API helpers
│   ├── media_graph.py                  # Shared relationship graph
│   ├── media_storage.py                # Private/public S3-aware image storage
│   ├── command_error_handler.py        # Shared command/component failure reporting
│   ├── custom_roles/                   # Custom Role validation, persistence and storage
│   ├── igdb_helper.py                  # IGDB/Twitch API helper
│   └── steam_helper.py                 # Steam API helpers
├── dashboard-rs/                       # Rust/Axum web control plane
├── dashboard-frontend/                 # React + TypeScript + Vite source
├── web/                                # Python private web helpers and Custom Role picker
├── tests/                              # Focused regression and infrastructure tests
├── docs/                               # Feature, handoff, security and deployment guides
├── deploy/vps/                         # VPS/systemd/Nginx deployment notes
├── .env.example                        # Configuration template
└── requirements.txt                    # Python dependencies
~~~

The exact file inventory changes as extensions are added. Use the live command registry and each feature guide when in doubt.

---

## Documentation

| Guide | Contents |
| --- | --- |
| [Media discovery and community events](docs/MEDIA_DISCOVERY.md) | Cross-media relationships, source labels, recommendations, and community event boundaries. |
| [Dashboard guide](docs/DASHBOARD.md) | Dashboard architecture, configuration, local development, and deployment. |
| [Security review](docs/SECURITY_AUDIT.md) | Web dashboard trust boundaries and residual risks. |
| [Custom Roles setup](docs/HANDOFF_NOTES.md) | Role eligibility, server setup, color picker, deployment, and validation. |
| [Custom Roles specification](docs/CUSTOM_ROLES_SPEC.md) | Expected Custom Roles behavior and implementation contract. |
| [VPS deployment](deploy/vps/README.md) | systemd services, Nginx, TLS, and private listeners. |
| [Environment template](.env.example) | Current environment variable names and defaults. |

---

## Contributing

1. Inspect the existing implementation and related helpers before changing behavior.
2. Keep changes focused; do not refactor unrelated subsystems as part of a feature fix.
3. Preserve multi-guild authorization and scope checks.
4. Add or update focused tests for meaningful changes and run the relevant checks.
5. Update the Help dropdown and feature documentation if user-facing behavior changes.
6. Describe verification honestly in the pull request and list any provider credentials or external services that could not be tested.

Do not commit tokens, OAuth secrets, database URLs, S3 credentials, private signed URLs, or production logs.

---

## License

Lemegeton is released under the MIT License. See [docs/LICENSE](docs/LICENSE).

<p align="center"><strong>One Discord bot. Connected media. Server-scoped community systems.</strong></p>

<div align="center">

# L E M E G E T O N

[![Node.js](https://img.shields.io/badge/Node.js-22.9+-339933?logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![discord.js](https://img.shields.io/badge/discord.js-14-5865F2?logo=discord&logoColor=white)](https://discord.js.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Dashboard](https://img.shields.io/badge/Dashboard-Rust%20%2B%20Next.js-8B5CF6)](docs/DASHBOARD.md)
[![License](https://img.shields.io/badge/License-MIT-4CAF50)](docs/LICENSE)

### One Discord bot. Many media worlds. One connected community layer.

Discover anime, manga, novels, webnovels, films, television, and video games, then explore source-attributed connections and community features across servers.

</div>

---

## What Lemegeton does

Lemegeton is a multi-guild Discord bot focused on media discovery, recommendations, information, and community features.

- **Media discovery:** category-aware search and metadata from AniList, TMDB, Google Books, IGDB, and Steam where supported.
- **Community:** server-scoped archives, rankings, Daily Drops, sessions, discussions, and media games.
- **Profiles:** supported AniList and Steam connections, privacy controls, and server-local comparisons.
- **Custom Roles:** server configuration, member role controls, icons, and the private role picker.
- **Operations:** settings, diagnostic issue references, moderator tools, and an optional web dashboard.

Slash commands and their components are intended to be used in a Discord server, not in direct messages. Feature availability and stored community data are scoped by guild.

## Command map

| Command | Purpose |
|---|---|
| /discover | Search and explore supported media categories |
| /archive | Browse, submit, curate, and moderate community archive content |
| /community | Rankings, Daily Drops, sessions, discussions, and calendar |
| /play | Source-backed media quiz games |
| /profile | AniList/Steam connections, privacy, and server comparisons |
| /custom-role | Member Custom Roles and server administration |
| /settings | Configure supported features for the current server |
| /planned | Browse the development plan and moderator controls |
| /feedback | Submit ideas or report bugs with an optional issue reference |
| /log | Retrieve a server-scoped diagnostic record (bot moderators only) |
| /adminmoderators | Manage the bot-wide moderator list (restricted) |
| /help, /privacy | Standalone help and privacy information |
| /timestamp, /invite, /convertlinks | Server utility commands |

An error that is captured by the diagnostic handler receives a copyable SHA-512 issue reference. Include it in /feedback; authorized bot moderators can inspect the corresponding record with /log. Diagnostic details redact common credential fields.

## Architecture

~~~mermaid
flowchart TB
    Discord[Discord guild interactions] --> Bot[TypeScript / discord.js runtime]
    Bot --> Commands[Registered command handlers]
    Commands --> Providers[AniList / TMDB / Books / IGDB / Steam]
    Commands --> Database[(PostgreSQL)]
    Commands --> Objects[(S3-compatible media storage)]
    Dashboard[Next.js dashboard] --> Rust[Rust / Axum control plane]
    Rust --> Bridge[Private TypeScript bot bridge]
    Bridge --> Bot
~~~

- **Bot runtime:** Node.js 22+, TypeScript, and discord.js.
- **Persistence:** PostgreSQL through the shared TypeScript database layer.
- **Media storage:** configured S3-compatible storage for supported private/public assets.
- **Dashboard:** Next.js frontend and Rust/Axum API. The Rust service handles Discord OAuth, browser sessions, and guild authorization; its private bridge talks to the running TypeScript bot.
- **Custom Role picker:** a TypeScript service behind the dashboard's Rust proxy.

The dashboard is a control plane for the same running bot, not a second Discord gateway. It does not expose arbitrary shell execution or raw SQL controls.

## Getting started

### Requirements

- Node.js 22.9 or newer and npm.
- PostgreSQL.
- A Discord application and bot token.
- Rust and Cargo for the optional dashboard backend.
- Optional provider, S3, and OAuth credentials for the features being enabled.

### Install

~~~bash
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton
npm install --no-audit --no-fund
cp .env.example .env
~~~

On Windows PowerShell, use Copy-Item .env.example .env. Configure the required Discord and PostgreSQL settings in .env. Add only the provider and dashboard credentials you intend to use. Never commit environment files or real tokens.

### Build and run the bot

~~~bash
npm run typecheck
npm test
npm start
~~~

npm test builds the TypeScript project into dist/ before running the Node.js test suite. npm start launches dist/bot.js and loads .env when present.

To deploy the slash command definitions:

~~~bash
npm run deploy:commands
~~~

### Build and run the combined deployment

The combined startup script runs the compiled TypeScript bot and Rust dashboard:

~~~bash
npm install --prefix web/frontend --no-audit --no-fund
npm run typecheck --prefix web/frontend
npm run build --prefix web/frontend
cargo build --manifest-path web/backend/Cargo.toml --release
./scripts/start.sh
~~~

The startup script checks for dist/bot.js, the Next.js static export, and the Rust dashboard executable. It builds the TypeScript bot if its compiled output is missing and its dependencies are installed.

Docker and Railway use the same TypeScript/Rust runtime contract. For VPS deployment, use the separate hardened systemd services and Nginx configuration in deploy/vps/README.md.

## Configuration

.env.example is the environment-variable template. The main groups include:

| Variables | Purpose |
|---|---|
| DISCORD_TOKEN, BOT_ID / DISCORD_CLIENT_ID | Discord application authentication |
| DATABASE_URL / PostgreSQL connection variables | Shared PostgreSQL connection |
| ANILIST_API_URL, ANILIST_API_TIMEOUT | AniList client |
| TMDB_BEARER_TOKEN | TMDB metadata |
| IGDB_CLIENT_ID, IGDB_CLIENT_SECRET | IGDB metadata |
| STEAM_API_KEY | Supported Steam lookups |
| S3_* | Optional object-storage configuration |
| DASHBOARD_* | Rust dashboard, OAuth, sessions, and private bridge |
| CUSTOM_ROLES_* | Custom Roles and picker configuration |
| BOT_FEEDBACK_CHANNEL_ID | Optional channel for forwarding saved feedback |

The required values are validated by the TypeScript configuration and database modules at startup. A variable being present in the template does not mean every feature requires it.

## Development and verification

Run commands from the repository root.

~~~bash
npm run typecheck
npm test
bash -n scripts/start.sh
npm run typecheck --prefix web/frontend
npm run build --prefix web/frontend
cargo fmt --manifest-path web/backend/Cargo.toml -- --check
cargo test --manifest-path web/backend/Cargo.toml
~~~

The dashboard workflow also audits frontend/Rust dependencies and builds the production Docker image. Do not treat a command listed here as evidence that a check has passed; use the actual CI result for the commit being reviewed.

## Repository layout

~~~text
bot.ts                         Discord.js gateway, events, and runtime
database.ts                    PostgreSQL schema, pool, and transactions
src/                           Slash commands and interaction handlers
helpers/                       Provider clients and domain services
tests/                          TypeScript tests
scripts/start.sh                Combined bot/dashboard startup
scripts/repo-stats.mjs          Generated README statistics
web/frontend/                   Next.js / React dashboard
web/backend/                    Rust/Axum OAuth and dashboard API
Dockerfile                      Multi-stage Node.js, Next.js, and Rust image
docker-compose.yml              Hardened container deployment
railway.json / railway.toml     Hosted deployment configuration
.github/workflows/              TypeScript, dashboard, Rust, and container checks
~~~

## Repository statistics

The following block is refreshed by the repository-statistics workflow.

<!-- REPO-STATS:START -->
Statistics are generated from tracked text and source files after changes are integrated.
<!-- REPO-STATS:END -->

## Security and operational boundaries

- Use least-privilege Discord permissions and keep all credentials outside Git.
- Guild-owned records and moderation actions must retain their guild context.
- Diagnostic log lookups are restricted to bot moderators and remain server-scoped.
- Private media originals must not be made public through a convenience URL.
- The dashboard must verify current Discord identity and guild permissions for protected actions.
- Automated tests reduce risk but do not replace a production OAuth, HTTPS, permission, backup, and deployment review.

## Documentation

- [Media discovery](docs/MEDIA_DISCOVERY.md)
- [Dashboard setup and architecture](docs/DASHBOARD.md)
- [Security review](docs/SECURITY_AUDIT.md)
- [Custom Roles specification](docs/CUSTOM_ROLES_SPEC.md)
- [VPS deployment](deploy/vps/README.md)

## Contributing

Inspect existing command handlers, provider clients, database operations, and callers before changing behavior. Keep changes focused, maintain multi-guild isolation, add relevant TypeScript tests, and report only checks that actually ran successfully.

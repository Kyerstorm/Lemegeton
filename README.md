<div align="center">

<img src="assets/icons/lemegeton.svg" alt="Lemegeton" width="112" />

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icons/wordmark-dark.svg" />
  <img src="assets/icons/wordmark-light.svg" alt="Lemegeton" width="270" />
</picture>

<p><strong>DISCOVER · CONNECT · CREATE</strong></p>
<p>Media discovery and community, built for Discord.</p>

<p>
  <a href="docs/README.md">DOCS</a>
  &nbsp;·&nbsp;
  <a href="docs/ARCHITECTURE.md">ARCHITECTURE</a>
  &nbsp;·&nbsp;
  <a href="CONTRIBUTING.md">CONTRIBUTE</a>
  &nbsp;·&nbsp;
  <a href="SECURITY.md">SECURITY</a>
</p>

[![Quality](https://img.shields.io/github/actions/workflow/status/Kyerstorm/Lemegeton/ci-bot.yml?branch=lemegeton-v3&label=quality&style=flat-square)](https://github.com/Kyerstorm/Lemegeton/actions/workflows/ci-bot.yml)
[![Node.js](https://img.shields.io/badge/Node.js-22%2B-111111?style=flat-square&logo=nodedotjs&logoColor=white)](https://nodejs.org/)
[![discord.js](https://img.shields.io/badge/discord.js-14-111111?style=flat-square&logo=discord&logoColor=white)](https://discord.js.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%2B-111111?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![MIT](https://img.shields.io/badge/license-MIT-111111?style=flat-square)](docs/LICENSE)

</div>

---

## A MEDIA UNIVERSE, INSIDE DISCORD

Find the next thing your community will love—and the connections that make it even better. Lemegeton brings anime, manga, novels, books, webnovels, films, series and games into Discord, with cross-provider discovery, source-backed relationships, shared archives, daily activities, rankings, sessions and games.

**For server owners:** Give members one place to discover, contribute and take part.
**For developers:** Explore a multi-guild TypeScript/discord.js system backed by PostgreSQL, with dedicated provider integrations, automated tests and an optional Next.js + Rust dashboard.

## COMMANDS

| Command | Opens |
|:--|:--|
| `/discover` | Media search, browse, compare, and recommendations |
| `/archive` | Community collections, submissions, and curation |
| `/community` | Daily activities, rankings, sessions, and events |
| `/play` | Group quizzes and media games |
| `/profile` | Profiles, provider links, and privacy controls |
| `/custom-role` | Member Custom Roles and management |
| `/settings` | Guild configuration |
| `/music` | Artist releases and guild notifications |

`/language` completes server setup alongside the guild's data-retention choice. `/help`, `/privacy`, and `/feedback` remain standalone.

## SYSTEM MAP

<p align="center">
  <img src="assets/architecture.svg" alt="Lemegeton v3 system architecture" width="100%" />
</p>

## REPOSITORY STRUCTURE

The tree below lists every file and directory tracked on the `lemegeton-v3` branch at the time this README was updated. Generated build output, dependency folders, local environment files, and ignored runtime data are intentionally excluded.

### Top-level map

| Path | Responsibility |
|:--|:--|
| `bot.ts` | Discord client lifecycle, gateway events, workers, and private dashboard bridge startup |
| `database.ts` | PostgreSQL schema, queries, transactions, and persistence |
| `src/` | Discord command handlers, command registration, integrations, standalone commands, and utilities |
| `helpers/` | Shared domain services for archives, community, custom roles, providers, media, runtime, and security |
| `web/frontend/` | Next.js App Router dashboard and React/TypeScript interface |
| `web/backend/` | Rust/Axum dashboard service, OAuth, sessions, API, authorization, and SQLite state |
| `assets/` | Repository architecture diagram and Lemegeton brand SVGs |
| `data/` | Small committed data assets used by the application |
| `tests/` | Unit and integration tests for bot, providers, database, media, dashboard bridge, and security |
| `docs/` | Architecture, dashboard, privacy, security, operations, feature specifications, and roadmap |
| `scripts/` | Build/start, acceptance, and repository-statistics scripts |
| `deploy/` | VPS Nginx and systemd deployment configuration |
| `.github/workflows/` | CI, acceptance, dependency, code, secret, and container security workflows |

### Dashboard source layout

The committed dashboard currently uses a Next.js App Router frontend in `web/frontend/app/`, interactive React/TypeScript code in `web/frontend/src/App.tsx`, and a Rust/Axum backend in `web/backend/src/`. The existing picker is served through `web/picker.html`, `web/picker.js`, and `web/picker.css`. These are current tracked files, not a claim that the proposed dashboard redesign has already been implemented.

The dashboard redesign specification calls for a dedicated `Components/Icons/` library for animated SVG icons, reusable form controls, and a Discord-style `SaveChangesBar` with a grey **Reset** action and green **Save Changes** action. Save/reset state must be isolated per configuration section, preserve edits on failed saves, and require server-side authorization. The planned icon and component folders should only be added as implementation work lands; they are not represented as existing files in the tree below.

Rate limiting is part of the Rust dashboard service. The current session database path is configured by `DASHBOARD_SESSION_DB_PATH`; see [Dashboard documentation](docs/DASHBOARD.md) for the current session, OAuth-state, rate-limit, and refresh-lease storage description. Any future distributed limiter must coordinate across backend instances and must not rely on per-instance counters.

### Complete tracked tree

```text
Lemegeton/
├── .apm/
├── │   └── guides/
├── │       └── Task_Assignment_Guide.md
├── .claude/
├── │   └── settings.local.json
├── .dockerignore
├── .env.example
├── .gitattributes
├── .github/
├── │   └── workflows/
├── │       ├── acceptance-dashboard-oauth.yml
├── │       ├── acceptance-discord.yml
├── │       ├── acceptance-postgres-staging.yml
├── │       ├── acceptance-providers.yml
├── │       ├── acceptance-s3-live.yml
├── │       ├── ci-bot.yml
├── │       ├── ci-container.yml
├── │       ├── ci-dashboard-frontend.yml
├── │       ├── ci-dashboard-rust.yml
├── │       ├── ci-repo-hygiene.yml
├── │       ├── ci-scraper-security.yml
├── │       ├── security-codeql.yml
├── │       ├── security-dependencies.yml
├── │       ├── security-secrets.yml
├── │       ├── security-trivy.yml
├── │       └── security-workflows.yml
├── .gitignore
├── AGENTS.md
├── assets/
├── │   ├── architecture.svg
├── │   └── icons/
├── │       ├── github.svg
├── │       ├── lemegeton.svg
├── │       ├── wordmark-dark.svg
├── │       └── wordmark-light.svg
├── bot_pid.txt
├── bot.ts
├── Cargo.toml
├── config/
├── │   └── railway.json
├── CONTRIBUTING.md
├── data/
├── │   └── 3x3_gallery.json
├── database.ts
├── deploy/
├── │   └── vps/
├── │       ├── nginx/
├── │       │   ├── lemegeton-dashboard.conf
├── │       │   └── lemegeton-proxy-params.conf
├── │       ├── README.md
├── │       └── systemd/
├── │           ├── lemegeton-bot.service
├── │           ├── lemegeton-dashboard.service
├── │           └── lemegeton-dashboard@.service
├── docker-compose.yml
├── Dockerfile
├── docs/
├── │   ├── ARCHITECTURE.md
├── │   ├── CI.md
├── │   ├── COMMUNITY_GUIDELINES.md
├── │   ├── CUSTOM_ROLES_SPEC.md
├── │   ├── DASHBOARD.md
├── │   ├── DATA_BACKUPS.md
├── │   ├── EXPANSION_ROADMAP.md
├── │   ├── HANDOFF_NOTES.md
├── │   ├── ISSUE_REFERENCE_FORMAT.md
├── │   ├── Lemegeton v3.md
├── │   ├── LICENSE
├── │   ├── MEDIA_DISCOVERY.md
├── │   ├── PRIVACY_POLICY.md
├── │   ├── README.md
├── │   ├── SECURITY_AUDIT.md
├── │   ├── TERMS_OF_SERVICE.md
├── │   └── UX_GUIDELINES.md
├── helpers/
├── │   ├── archive/
├── │   │   ├── archive-access.ts
├── │   │   ├── archive-collections.ts
├── │   │   ├── archive-curation.ts
├── │   │   ├── archive-moderation.ts
├── │   │   └── archive.ts
├── │   ├── commands/
├── │   │   ├── command-errors.ts
├── │   │   ├── command.ts
├── │   │   └── moderation.ts
├── │   ├── community/
├── │   │   ├── community-automation.ts
├── │   │   ├── community-daily.ts
├── │   │   ├── community-rankings.ts
├── │   │   ├── community-reading.ts
├── │   │   ├── community-releases.ts
├── │   │   ├── community-sessions.ts
├── │   │   ├── community-showcase.ts
├── │   │   ├── community-tournaments.ts
├── │   │   ├── community.ts
├── │   │   └── delivery-retries.ts
├── │   ├── custom-roles/
├── │   │   ├── custom-role-images.ts
├── │   │   ├── custom-role-lifecycle.ts
├── │   │   ├── custom-role-picker-image-fetch.ts
├── │   │   ├── custom-role-picker-server.ts
├── │   │   ├── custom-role-picker-service.ts
├── │   │   ├── custom-role-picker-tokens.ts
├── │   │   ├── custom-role-validation.ts
├── │   │   └── custom-roles.ts
├── │   ├── embeds/
├── │   │   └── core.ts
├── │   ├── emoji.ts
├── │   ├── integration/
├── │   │   ├── anilist.ts
├── │   │   ├── atlas.ts
├── │   │   ├── crossref.ts
├── │   │   ├── google-books.ts
├── │   │   ├── igdb.ts
├── │   │   ├── kitsu.ts
├── │   │   ├── mangadex.ts
├── │   │   ├── music.ts
├── │   │   ├── open-library.ts
├── │   │   ├── provider-http.ts
├── │   │   ├── royal-road.ts
├── │   │   ├── steam.ts
├── │   │   ├── tmdb.ts
├── │   │   ├── translation.ts
├── │   │   ├── web-scraper.ts
├── │   │   └── webnovel-discovery.ts
├── │   ├── media/
├── │   │   ├── atlas-renderer.ts
├── │   │   ├── cross-media-recommendations.ts
├── │   │   ├── franchise-order.ts
├── │   │   ├── media-comparison.ts
├── │   │   ├── media-grid.ts
├── │   │   ├── media-link-suggestions.ts
├── │   │   ├── media-notifications.ts
├── │   │   ├── media-provenance.ts
├── │   │   ├── media-region.ts
├── │   │   ├── media-storage.ts
├── │   │   ├── metadata-source-audit.ts
├── │   │   └── title-matching.ts
├── │   ├── runtime/
├── │   │   ├── anilist-leaderboard.ts
├── │   │   ├── color-palette.ts
├── │   │   ├── config.ts
├── │   │   ├── dashboard-bridge.ts
├── │   │   ├── database-backups.ts
├── │   │   ├── discord.ts
├── │   │   ├── fake-loading.ts
├── │   │   ├── games.ts
├── │   │   ├── guild-retention.ts
├── │   │   ├── issue-logs.ts
├── │   │   ├── languages.ts
├── │   │   ├── logger.ts
├── │   │   ├── profile.ts
├── │   │   ├── server-diagnostics.ts
├── │   │   └── settings.ts
├── │   └── security/
├── │       ├── crypto-random.ts
├── │       ├── security.ts
├── │       └── terms-consent.ts
├── package.json
├── Procfile
├── railpack.json
├── railway.json
├── railway.toml
├── README.md
├── runtime.txt
├── scripts/
├── │   ├── acceptance/
├── │   │   └── discord.mjs
├── │   ├── repo-stats.mjs
├── │   └── start.sh
├── SECURITY.md
├── src/
├── │   ├── commands/
├── │   │   ├── archive.ts
├── │   │   ├── community.ts
├── │   │   ├── custom-role.ts
├── │   │   ├── discover.ts
├── │   │   ├── language.ts
├── │   │   ├── music.ts
├── │   │   ├── play.ts
├── │   │   ├── profile.ts
├── │   │   └── settings.ts
├── │   ├── deploy-commands.ts
├── │   ├── integrations/
├── │   │   ├── anilist-embed.ts
├── │   │   └── social-embed.ts
├── │   ├── registry.ts
├── │   ├── standalone/
├── │   │   ├── admin-login.ts
├── │   │   ├── feedback.ts
├── │   │   ├── help.ts
├── │   │   ├── log.ts
├── │   │   ├── moderators.ts
├── │   │   └── privacy.ts
├── │   └── utility/
├── │       ├── convertlinks.ts
├── │       ├── invite.ts
├── │       ├── planned.ts
├── │       └── timestamp.ts
├── TECH_STACK.md
├── tests/
├── │   ├── anilist-airing.test.ts
├── │   ├── anilist-creators.test.ts
├── │   ├── anilist-embeds.test.ts
├── │   ├── anilist-franchise.test.ts
├── │   ├── anilist-leaderboard.test.ts
├── │   ├── anilist-search.test.ts
├── │   ├── anilist-trailers.test.ts
├── │   ├── archive-curation.test.ts
├── │   ├── archive-lifecycle.integration.test.ts
├── │   ├── archive-moderation.test.ts
├── │   ├── archive-panels.test.ts
├── │   ├── archive-reordering.test.ts
├── │   ├── archive-settings.test.ts
├── │   ├── archive-visibility.test.ts
├── │   ├── atlas-renderer.test.ts
├── │   ├── atlas.test.ts
├── │   ├── color-palette.test.ts
├── │   ├── command-errors.test.ts
├── │   ├── community-automation.test.ts
├── │   ├── community-calendar.test.ts
├── │   ├── community-daily.test.ts
├── │   ├── community-game-idempotency.integration.test.ts
├── │   ├── community-media-night.test.ts
├── │   ├── community-reading.test.ts
├── │   ├── community-releases.test.ts
├── │   ├── community-season.test.ts
├── │   ├── community-sessions.test.ts
├── │   ├── community-showcase.test.ts
├── │   ├── community-tournament-lifecycle.integration.test.ts
├── │   ├── community-tournaments.test.ts
├── │   ├── core.test.ts
├── │   ├── cross-media-recommendations.test.ts
├── │   ├── crossref.test.ts
├── │   ├── custom_roles/
├── │   │   └── README.md
├── │   ├── custom-role-images.test.ts
├── │   ├── custom-role-picker-tokens.test.ts
├── │   ├── custom-role-threshold.test.ts
├── │   ├── custom-role-validation.test.ts
├── │   ├── dashboard-bridge.test.ts
├── │   ├── database-backups.test.ts
├── │   ├── database-schema.test.ts
├── │   ├── delivery-retries.test.ts
├── │   ├── emoji.test.ts
├── │   ├── fake-loading.test.ts
├── │   ├── franchise-order.test.ts
├── │   ├── games-team-selection.test.ts
├── │   ├── google-books.test.ts
├── │   ├── guild-retention.test.ts
├── │   ├── igdb-company.test.ts
├── │   ├── igdb-genre-search.test.ts
├── │   ├── igdb-release-dates.test.ts
├── │   ├── igdb-similar.test.ts
├── │   ├── issue-logs.test.ts
├── │   ├── kitsu.test.ts
├── │   ├── languages.test.ts
├── │   ├── mangadex.test.ts
├── │   ├── media-automation.test.ts
├── │   ├── media-clues.test.ts
├── │   ├── media-comparison.test.ts
├── │   ├── media-grid.test.ts
├── │   ├── media-link-suggestions.test.ts
├── │   ├── media-notifications.test.ts
├── │   ├── media-provenance.test.ts
├── │   ├── media-storage-s3.integration.test.ts
├── │   ├── media-storage.test.ts
├── │   ├── metadata-source-audit.test.ts
├── │   ├── music.test.ts
├── │   ├── open-library.test.ts
├── │   ├── provider-coverage.test.ts
├── │   ├── provider-http.test.ts
├── │   ├── providers-live.integration.test.ts
├── │   ├── quiz-pack-revisions.test.ts
├── │   ├── royal-road.test.ts
├── │   ├── runtime-config.test.ts
├── │   ├── server-diagnostics.test.ts
├── │   ├── social-embeds.test.ts
├── │   ├── steam-profile.test.ts
├── │   ├── steam-store.test.ts
├── │   ├── terms-consent.test.ts
├── │   ├── title-matching.test.ts
├── │   ├── tmdb.test.ts
├── │   ├── translation.test.ts
├── │   ├── web-scraper.test.ts
├── │   └── webnovel-discovery.test.ts
├── tsconfig.json
├── utils/
├── │   └── setup.bat
└── web/
├──     ├── backend/
├──     │   ├── Cargo.toml
├──     │   └── src/
├──     │       ├── api.rs
├──     │       ├── auth.rs
├──     │       ├── main.rs
├──     │       ├── state.rs
├──     │       ├── store.rs
├──     │       └── ui.rs
├──     ├── favicon.svg
├──     ├── frontend/
├──     │   ├── app/
├──     │   │   ├── globals.css
├──     │   │   ├── layout.tsx
├──     │   │   ├── login/
├──     │   │   │   └── page.tsx
├──     │   │   └── page.tsx
├──     │   ├── next-env.d.ts
├──     │   ├── next.config.ts
├──     │   ├── package.json
├──     │   ├── src/
├──     │   │   └── App.tsx
├──     │   └── tsconfig.json
├──     ├── picker.css
├──     ├── picker.html
├──     ├── picker.js
├──     └── theme.css
```

## INTEGRATIONS

**Media:** AniList · Kitsu · MangaDex · TMDB · IGDB · Steam · Google Books · Open Library · Crossref · Royal Road

**Optional:** Spotify · YouTube Data API · SoundCloud · S3-compatible media storage

Provider coverage, credentials, and returned fields vary by source. Recommendations, provider-declared relationships, local matches, and community-approved links remain separate evidence types.

## QUICK START

**Requirements:** Node.js 22.9+, npm, PostgreSQL, and a Discord application.

```bash
git clone https://github.com/Kyerstorm/Lemegeton.git
cd Lemegeton
npm install --no-audit --no-fund
cp .env.example .env
```

Configure the bot token and PostgreSQL connection in `.env`.

```bash
npm run typecheck
npm test
npm start
```

Register commands with `npm run deploy:commands`. The optional dashboard requires its own Next.js and Rust build; see [deployment](docs/DASHBOARD.md).

## DOCUMENTATION

| Guide | |
|:--|:--|
| [Architecture](docs/ARCHITECTURE.md) | Runtime, services, data flow, and guild boundaries |
| [Dashboard](docs/DASHBOARD.md) | Next.js, Rust/Axum, OAuth, and bridge |
| [Media discovery](docs/MEDIA_DISCOVERY.md) | Providers, relationships, and provenance |
| [Custom Roles](docs/CUSTOM_ROLES_SPEC.md) | Role lifecycle and configuration |
| [CI and verification](docs/CI.md) | Automated checks and live acceptance |
| [Security policy](SECURITY.md) | Vulnerability reporting |
| [Security review](docs/SECURITY_AUDIT.md) | Controls and residual risks |
| [Backups](docs/DATA_BACKUPS.md) | Recovery and verification |
| [Privacy](docs/PRIVACY_POLICY.md) | Data handling and retention |
| [Community guidelines](docs/COMMUNITY_GUIDELINES.md) | Submissions and moderation |
| [Contributing](CONTRIBUTING.md) | Development standards |
| [Terms](docs/TERMS_OF_SERVICE.md) · [License](docs/LICENSE) | |

## STATS

<p align="center">
  <a href="https://github.com/Kyerstorm/Lemegeton"><img src="https://img.shields.io/github/stars/Kyerstorm/Lemegeton?style=flat-square&label=stars&color=111111" alt="GitHub stars" /></a>
  <a href="https://github.com/Kyerstorm/Lemegeton/forks"><img src="https://img.shields.io/github/forks/Kyerstorm/Lemegeton?style=flat-square&label=forks&color=111111" alt="GitHub forks" /></a>
  <a href="https://github.com/Kyerstorm/Lemegeton/graphs/contributors"><img src="https://img.shields.io/github/contributors/Kyerstorm/Lemegeton?style=flat-square&label=contributors&color=111111" alt="Contributors" /></a>
  <img src="https://img.shields.io/github/repo-size/Kyerstorm/Lemegeton?style=flat-square&label=repository%20size&color=111111" alt="Repository size" />
  <img src="https://img.shields.io/github/last-commit/Kyerstorm/Lemegeton/lemegeton-v3?style=flat-square&label=last%20commit&color=111111" alt="Last commit" />
</p>

                        <!-- REPO-STATS:START -->
| Tracked files | Lines of code | Text characters |
|--:|--:|--:|
| 269 | 45,950 | 3,197,119 |

<!-- REPO-STATS:END -->

<div align="center">
  <sub>LEMEGETON / V3</sub>
</div>

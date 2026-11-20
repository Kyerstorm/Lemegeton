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

<sub>Tracked files after generated/cache exclusions · non-blank lines across source files · characters across tracked text files, excluding line breaks · refreshed 2026-11-20 15:52 UTC.</sub>
<!-- REPO-STATS:END -->

<div align="center">
  <sub>LEMEGETON / V3</sub>
</div>

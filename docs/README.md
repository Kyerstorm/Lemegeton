# Lemegeton documentation

Lemegeton v3 is a TypeScript/Node.js Discord bot with shared local libSQL persistence, private RocksDB media storage and an optional Next.js + Rust/Axum dashboard.

Start with the repository [README](../README.md) for the product overview and quick setup. Use the architecture guide when navigating code.

## Product and architecture

- [Architecture](ARCHITECTURE.md) — current runtime diagram, source map, data flow, and multi-guild boundaries.
- [Media Discovery](MEDIA_DISCOVERY.md) — providers, browsing, relationships, and source attribution.
- [Media Sources & Scraping](MEDIA_SOURCES.md) — all 64 source targets, access modes, scraper boundaries, webnovel adapters, Timeline evidence and Industry providers.
- [Botasaurus browser worker](../workers/botasaurus.py) — isolated optional browser worker; see its [container definition](../workers/Dockerfile) and [dependencies](../workers/requirements.txt).
- [Dashboard](DASHBOARD.md) — Next.js frontend, Rust API, Discord OAuth, private bridge, and deployment.
- [Data backups](DATA_BACKUPS.md) — backup verification and recovery boundaries.
- [Interaction and UX guidelines](UX_GUIDELINES.md) — Discord components, loading states, embeds, errors, accessibility, and motion.

## Legal, privacy, and security

- [Legal & Privacy index](legal/README.md) — public policies and internal procedures.
- [Privacy Policy](legal/PRIVACY_POLICY.md) — data processing, storage, and privacy rights.
- [Terms of Service](legal/TERMS_OF_SERVICE.md) — service conditions.
- [Community Guidelines](legal/COMMUNITY_GUIDELINES.md) — submissions, attribution, spoilers, and moderation.
- [DMCA & Copyright Policy](legal/DMCA.md) — permitted community uploads, copyright notices, counter-notifications, and operator requirements.
- [Copyright complaints](legal/COPYRIGHT_AND_CONTENT_COMPLAINTS.md) — rights-holder reporting process.
- [Security Policy](legal/SECURITY.md) — private vulnerability reporting.
- [BLA agent skill](../.agents/skills/blind-llm-agents/SKILL.md) — upstream BLA v3.6.0 workflow and format guidance.

## Development and operations

- [Contributing](../CONTRIBUTING.md) — setup, engineering expectations, tests, and review checklist.
- [CI and verification](CI.md) — automated quality gates and manual live acceptance.
- [VPS deployment](../deploy/vps/README.md) — systemd, Nginx, TLS, and runtime configuration.
- [GitHub Activity Tracker](GITHUB_TRACKER.md) — moderator-only activity command, grouped commit summaries and announcement configuration.
- [Issue reference format](ISSUE_REFERENCE_FORMAT.md) — SHA-512-derived diagnostic reference contract.
- [MIT License](LICENSE) — software licence.

## Historical references

- [Custom Roles specification](CUSTOM_ROLES_SPEC.md) — legacy pre-v3 implementation notes; consult the current source and dashboard guide for v3 behaviour.

The supported runtime entry point for the combined bot and dashboard is `scripts/start.sh`. The bot source is in `bot.ts`, `src/`, and `helpers/`; dashboard sources are in `web/frontend/` and `web/backend/`; tests are in `tests/`.

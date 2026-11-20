# Lemegeton documentation

Lemegeton v3 is a TypeScript/Node.js Discord bot with PostgreSQL persistence and an optional Next.js + Rust/Axum dashboard.

Start with the repository [README](../README.md) for the product overview and quick setup. Use the architecture guide when navigating code.

## Product and architecture

- [Architecture](ARCHITECTURE.md) — current runtime diagram, source map, data flow, and multi-guild boundaries.
- [Media Discovery](MEDIA_DISCOVERY.md) — providers, browsing, relationships, and source attribution.
- [Dashboard](DASHBOARD.md) — Next.js frontend, Rust API, Discord OAuth, private bridge, and deployment.
- [Data backups](DATA_BACKUPS.md) — backup verification and recovery boundaries.
- [Interaction and UX guidelines](UX_GUIDELINES.md) — Discord components, loading states, embeds, errors, accessibility, and motion.

## Security, privacy, and community

- [Repository security policy](../SECURITY.md) — how to privately report a vulnerability.
- [Security audit](SECURITY_AUDIT.md) — source-level findings, controls, and residual risks.
- [Privacy Policy](PRIVACY_POLICY.md) — data processing, storage, and retention.
- [Terms of Service](TERMS_OF_SERVICE.md) — service conditions.
- [Community Guidelines](COMMUNITY_GUIDELINES.md) — archive submissions, attribution, spoilers, and moderation.

## Development and operations

- [Contributing](../CONTRIBUTING.md) — setup, engineering expectations, tests, and review checklist.
- [CI and verification](CI.md) — automated quality gates and manual live acceptance.
- [VPS deployment](../deploy/vps/README.md) — systemd, Nginx, TLS, and runtime configuration.
- [Issue reference format](ISSUE_REFERENCE_FORMAT.md) — SHA-512-derived diagnostic reference contract.
- [MIT License](LICENSE) — software licence.

## Historical references

- [Custom Roles specification](CUSTOM_ROLES_SPEC.md) — legacy pre-v3 implementation notes; consult the current source and dashboard guide for v3 behaviour.
- [Lemegeton v3 specification](Lemegeton%20v3.md) — approved product direction, migration scope, and release acceptance criteria.

The supported runtime entry point for the combined bot and dashboard is `scripts/start.sh`. The bot source is in `bot.ts`, `src/`, and `helpers/`; dashboard sources are in `web/frontend/` and `web/backend/`; tests are in `tests/`.

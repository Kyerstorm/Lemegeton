# Lemegeton documentation

The current implementation is a TypeScript/Node.js Discord bot with a PostgreSQL data layer and an optional Next.js + Rust dashboard.

Start with the repository [README](../README.md) for installation and setup.

## Core guides

- [Interaction and UX guidelines](UX_GUIDELINES.md): loading states, component behaviour, embeds, and diagnostic responses.

- [Media Discovery](MEDIA_DISCOVERY.md): supported providers, browsing, relationships, and source attribution.
- [Dashboard](DASHBOARD.md): Discord OAuth, Rust API, TypeScript bridge, and deployment.
- [Security audit](SECURITY_AUDIT.md): authorization boundaries and operational checks.
- [Custom Roles](CUSTOM_ROLES_SPEC.md): server configuration and member controls.
- [VPS deployment](../deploy/vps/README.md): Node.js bot, Rust dashboard, systemd, and Nginx.

The supported runtime entry point is `scripts/start.sh`. It runs the compiled TypeScript bot from `dist/bot.js` alongside the Rust dashboard binary. The bot's source is in `bot.ts`, `src/`, and `helpers/`; tests are TypeScript under `tests/`.

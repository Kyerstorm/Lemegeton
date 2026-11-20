# Architecture

<p align="center">
  <img src="../assets/architecture.svg" alt="Lemegeton v3 system architecture" width="100%" />
</p>

This guide describes the current `lemegeton-v3` source tree.

## Execution path

1. Discord interactions enter the single `discord.js` client owned by `bot.ts`.
2. `src/registry.ts` registers feature commands, standalone commands, and utilities.
3. Command handlers call shared domain services in `helpers/`.
4. Services use `database.ts`, provider adapters, and configured S3-compatible media storage.
5. Responses and scheduled deliveries return through the bot's Discord client.

The optional dashboard is a separate control plane: the Next.js frontend calls the Rust/Axum service, which handles OAuth, sessions, and server-side authorization before forwarding approved operations through the private bridge in the running bot. It does not create another Discord gateway.

## Module map

| Area | Responsibility |
|:--|:--|
| `bot.ts` | Discord client, lifecycle, workers, and bridge startup |
| `database.ts` | PostgreSQL pool, schema, queries, and transactions |
| `src/registry.ts` | Command registration |
| `src/commands/` | Discover, Archive, Community, Play, Profile, Custom Roles, Settings, Language, and Music |
| `src/standalone/` | Help, privacy, feedback, and restricted operator commands |
| `src/utility/` | Link conversion, invite, timestamps, and planned-feature utility |
| `src/integrations/` | Message-driven AniList and social embeds |
| `helpers/archive/` | Collections, access, curation, visibility, and moderation |
| `helpers/community/` | Daily activities, rankings, sessions, releases, and delivery |
| `helpers/custom-roles/` | Role lifecycle, validation, icons, picker, and storage |
| `helpers/integration/` | Provider clients, HTTP policy, translation, and web discovery |
| `helpers/media/` | Search, relationships, provenance, comparisons, Atlas, and storage |
| `helpers/runtime/` | Configuration, guild retention, language, bridge, backups, and diagnostics |
| `helpers/security/` | Cryptographic utilities, consent, and security controls |
| `web/frontend/` · `web/backend/` | Next.js dashboard and Rust/Axum control plane |
| `tests/` · `.github/workflows/` | Bot, provider, storage, dashboard, security, and repository checks |

## Multi-guild boundaries

- Server-owned state must be keyed by the invoking `guild_id`; shared media metadata is not shared guild configuration.
- A guild must configure both its data-retention choice and language before normal feature commands and protected dashboard routes are available.
- Dashboard writes must re-check the authenticated Discord user, guild membership, and current server permissions. Browser-provided guild IDs and permission claims are not authority.
- Member-data cleanup continues to follow the configured retention policy.
- Private media objects stay private. Public generated output uses a separately configured destination.
- Provider-declared links, recommendations, local matches, and community-reviewed relationships remain distinct evidence types.

## Verification boundary

CI covers the bot, database-backed tests, storage integration tests, dashboard frontend, Rust service, and repository security checks. Live Discord interactions, OAuth application configuration, third-party credentials, production S3 access, and backup recovery still require deployment-specific acceptance.

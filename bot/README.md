# Lemegeton TypeScript bot

This directory contains the v3 Discord bot runtime, built with TypeScript, Node.js 22, and Discord.js 14. It is intentionally separate from the legacy Python runtime while the migration is underway.

## Requirements

- Node.js 22.9 or newer
- A Discord application and bot token
- An AniList API endpoint (the public endpoint is used by default)

## Configuration

The bot reads the repository root `.env` file when started through the npm scripts. It uses the existing environment names where possible:

| Variable | Required | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `BOT_ID` or `DISCORD_CLIENT_ID` | Yes | Discord application ID |
| `DISCORD_GUILD_ID` | No | Register commands to one development guild; omit for global registration |
| `ANILIST_API_URL` | No | AniList GraphQL endpoint |
| `ANILIST_API_TIMEOUT` | No | AniList request timeout in seconds; defaults to 10 |
| `LOG_LEVEL` | No | `debug`, `info`, `warn`, or `error`; defaults to `info` |

## Development

From this directory:

```sh
npm install --no-audit --no-fund
npm run typecheck
npm test
npm run build
```

Run the bot with `npm start`. Register the currently implemented commands with `npm run deploy:commands`. During development, set `DISCORD_GUILD_ID` so changes are registered to a test guild instead of globally.

## Migration boundary

The current implementation is the first TypeScript foundation and `/discover` vertical slice. It supports AniList anime/manga search and trending results. Other feature environments are migrated in their planned order; they are not represented by non-functional placeholder commands. The existing Python bot, PostgreSQL schema, Rust/Axum dashboard API, and S3 storage remain in place until each workflow has verified parity and the cutover acceptance checks pass.

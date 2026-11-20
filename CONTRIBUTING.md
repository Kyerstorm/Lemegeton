# Contributing

Thank you for helping improve Lemegeton. Contributions should strengthen the existing Discord-first product and preserve its multi-guild boundaries.

## Before changing code

1. Read the [README](README.md) and [architecture guide](docs/ARCHITECTURE.md).
2. Inspect the current command, shared helper, database operations, callers, and tests before editing.
3. Check [the v3 specification](docs/Lemegeton%20v3.md) when a product-scope decision is involved.
4. Keep changes focused. Do not introduce a duplicate provider client, database layer, command registry, or speculative abstraction.

The active v3 implementation is developed on `lemegeton-v3` in the existing Draft migration PR. Do not create a parallel PR for work already covered by that migration.

## Development setup

Use Node.js 22.9 or newer and PostgreSQL. From the repository root:

```bash
npm install --no-audit --no-fund
cp .env.example .env
npm run typecheck
npm test
```

The test suite builds the TypeScript project before running Node's test runner. Configure the disposable database and storage services required by the relevant CI workflow; do not point tests at production data.

For dashboard changes:

```bash
npm install --prefix web/frontend --no-audit --no-fund
npm run typecheck --prefix web/frontend
npm run build --prefix web/frontend
cargo fmt --manifest-path web/backend/Cargo.toml -- --check
cargo test --manifest-path web/backend/Cargo.toml
```

## Engineering expectations

- Keep Discord gateway ownership in the existing `bot.ts` process.
- Put user-facing feature commands in the existing command environment; keep `/help`, `/privacy`, and `/feedback` standalone.
- Reuse provider adapters and domain helpers. Keep provider-specific logic out of Discord callbacks.
- Scope server-owned reads, writes, queues, moderation, and cleanup to the invoking guild.
- Re-check actor permissions and guild context for component interactions; do not trust a component identifier as authorization.
- Keep provider-declared relationships, provider recommendations, local matching, and community submissions clearly distinguished.
- Keep private asset originals private and use the existing storage policy and cleanup path.
- Validate external input, bound network and file operations, and avoid logging secrets or unnecessary personal data.
- Preserve compatibility with existing data and document schema or configuration changes.

## Tests and documentation

Add or update focused tests for changed behavior, especially around permissions, guild isolation, provider failures, database boundaries, and privacy cleanup. Update user-facing guides and `.env.example` when commands, configuration, deployment, or data handling changes.

Run the relevant checks and report exactly what was executed. Do not describe an unrun test, live provider, OAuth flow, database migration, or deployment as verified.

## Pull request checklist

- [ ] The change has a clear scope and follows the current architecture.
- [ ] Guild-owned operations remain guild-scoped.
- [ ] Permissions are enforced in the runtime, not only in the interface.
- [ ] Relevant tests and quality checks have been run.
- [ ] Documentation and environment examples are current.
- [ ] Logs, screenshots, and test fixtures contain no credentials or private user data.

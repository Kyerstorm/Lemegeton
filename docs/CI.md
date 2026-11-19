# CI and repository verification

This guide describes the checks attached to the v3 implementation.

## Branch scope

Automated pushes are limited to `lemegeton-v3`. Pull-request workflows run for PRs targeting `multi_guild`, which is the current base of Draft PR #17. That base is used only as the PR target; CI does not push commits, generate stats, or deploy to `multi_guild`.

Live acceptance workflows are manual-only and each job is guarded to execute only when the selected ref is `lemegeton-v3`. GitHub requires a `workflow_dispatch` file to exist on the repository default branch before it can be manually dispatched. The current default branch is `multi_guild`, and this work deliberately changes only `lemegeton-v3`; therefore these new live workflows are defined on v3 but are not yet manually runnable through GitHub Actions. Do not copy them to `multi_guild` or change the default branch without explicit approval.

## Automated quality checks

| Workflow | Responsibility |
|---|---|
| `ci-bot.yml` | TypeScript type-check and complete Node test suite using disposable PostgreSQL 16 and MinIO services |
| `ci-dashboard-frontend.yml` | Next.js type-check, production static export, expected routes and emitted assets |
| `ci-dashboard-rust.yml` | Rust formatting, Clippy with warnings denied, test suite and release build |
| `ci-container.yml` | Startup script syntax, ShellCheck, Compose configuration, production Docker build, non-root user and runtime bundle contract |
| `ci-scraper-security.yml` | Isolated SSRF regression tests for URL validation, mapped IPv6, DNS answer validation and redirects |
| `ci-repo-hygiene.yml` | JSON and environment-template parsing, Node maintenance script syntax, shell syntax and whitespace checks |

The complete bot test suite uses temporary PostgreSQL and MinIO services. It does not use production credentials or data. Provider API and real Discord checks remain in the manual acceptance workflows.

## Automated security checks

| Workflow | Responsibility |
|---|---|
| `security-codeql.yml` | CodeQL security-extended and security-and-quality analysis for JavaScript/TypeScript, Rust and GitHub Actions |
| `security-dependencies.yml` | Root bot npm, dashboard npm and Rust Cargo advisory audits |
| `security-secrets.yml` | Gitleaks scan of current files and full Git history; PR comments are disabled |
| `security-trivy.yml` | Trivy filesystem scan for vulnerable dependencies, configuration mistakes and secrets |
| `security-workflows.yml` | actionlint syntax/expression checks and zizmor workflow supply-chain/permission analysis |

Action references in the new workflows are pinned to full commit SHAs. Jobs use read-only repository permissions by default. CodeQL receives only the `security-events: write` permission required to publish findings.

The dependency workflow generates temporary npm and Cargo lock graphs for auditing because the v3 repository currently has no committed root/frontend `package-lock.json` or workspace `Cargo.lock`. This catches advisories for the resolved tree in that run, but it does not provide reproducible dependency resolution between runs. Committing reviewed lockfiles and switching corresponding CI installs to `npm ci` remains a separate supply-chain improvement.

## Manual live acceptance

The following workflow definitions are ready for dedicated test accounts on the `lemegeton-v3` ref. They will become manually dispatchable only after the default-branch requirement above is resolved:

| Workflow | Required configuration |
|---|---|
| `acceptance-providers.yml` | Steam, IGDB and TMDB test credentials; Google Books key is optional |
| `acceptance-discord.yml` | Dedicated test bot, test guild, inviter, channel and moderator-guild IDs |
| `acceptance-dashboard-oauth.yml` | Discord OAuth client, exact redirect/public URLs and a 32+ character bridge secret |
| `acceptance-postgres-staging.yml` | Disposable staging database secret and the exact `DISPOSABLE_STAGING` confirmation |
| `acceptance-s3-live.yml` | Dedicated disposable HTTPS S3-compatible endpoint and test credentials |

The staging PostgreSQL workflow reads the explicitly confirmed source database, runs schema/migration tests, restores a dump into an isolated CI PostgreSQL service, then compares tables, columns, constraints, indexes, row counts and deterministic row digests. Do not point it at a production database.

## Known CI blocker at the time of this change

The current v3 branch has pre-existing provider-union TypeScript errors in `src/commands/discover.ts` (around lines 2635–2701). They were present before this CI reorganization. The bot type-check, full bot test build and production Docker build will continue to fail until those source errors are corrected. The focused scraper security suite runs independently so its regression tests still execute and report separately.

A green CI result is necessary but does not prove production OAuth configuration, live Discord permission behavior, external provider uptime, real S3 access policy, VPS firewall state or production backup recoverability. Those need owner-controlled staging acceptance.

# CI and repository verification

This guide describes the single GitHub Actions workflow used by the v3 implementation.

## Branch scope

The unified workflow is triggered by pushes to `lemegeton-v3`, pull requests targeting `multi_guild` (the base of Draft PR #17), and manual dispatch. CI does not push commits, generate stats, or deploy to `multi_guild`.

The workflow file is intentionally maintained only on `lemegeton-v3`. GitHub requires a `workflow_dispatch` definition to exist on the repository's default branch before it can be manually dispatched. The current default branch is `multi_guild`; this change does not modify it or make the manual-dispatch UI available yet. Do not copy the workflow to `multi_guild` or change the default branch without explicit approval.

## One workflow, one continuous run

`.github/workflows/ci.yml` is the only workflow definition. The 17 previous workflow files have been consolidated into this file.

The jobs are deliberately chained. No branch-wide concurrency cancellation is configured, so a newer push cannot cancel an earlier commit's pipeline. Each push to lemegeton-v3 receives its own run; GitHub may queue runs when runner capacity is busy. There are no artificial sleep steps or fabricated progress.

Every verification step is configured to preserve its raw failure outcome while allowing the rest of that job and downstream checks to continue. Each intermediate job therefore completes its check run without prematurely turning the commit red; the single `ci-result` job depends on every verification job and is the only job allowed to conclude the workflow as failed. This keeps the commit's overall status yellow/in progress until all configured checks finish, then publishes one final pass or failure. A manually cancelled workflow remains cancelled.

## Automated checks

| Stage | Checks |
|---|---|
| Bot | Root TypeScript type-check; native Rust and RocksDB addon build; emitted Node test suite |
| Dashboard frontend | Next.js type-check; unit/component tests; static production export; Chromium browser E2E; required routes and assets |
| Dashboard backend | Rust formatting check; Clippy with warnings denied; storage and workspace tests; optimized Rust build |
| Container | Startup script and ShellCheck; Compose validation; production Docker build; non-root runtime contract; hardened route/header smoke tests; Trivy image scan; Nuclei and OWASP ZAP DAST against a disposable local dashboard; validated CycloneDX image SBOM artifact |
| Repository hygiene | JSON parsing; `.env.example` validation; maintenance-script and shell syntax; whitespace check |
| Scraper security | URL, DNS, IPv6 and redirect SSRF regression tests |
| Reverse-engineering resilience | Synthetic prompt-injection, fabricated-claim, path/symlink and bounded-resource tests |
| BLA defense | Pinned BLA CLI packaging lint, source workorder generation and weave verification |
| CodeQL | Security-extended and security-and-quality analysis for JavaScript/TypeScript, C++, Python, Rust and GitHub Actions; compiles the RocksDB addon and Rust workspace for extraction |
| Dependency audit | Root npm, frontend npm, Rust Cargo and isolated Botasaurus Python dependency audits; script-disabled npm installs verify registry signatures and available provenance attestations |
| Secret detection | Gitleaks scan of current files and full Git history; PR comments disabled |
| Trivy | Full-filesystem and assembled production-image scans for vulnerabilities, configuration mistakes, secrets and licence findings across all severities; validated CycloneDX source and image SBOM artifacts retained for seven days |
| Workflow security | actionlint syntax/expression validation and pinned zizmor supply-chain/permissions audit |
| Semgrep | Security-audit and secrets rules |
| Python worker | Bandit static analysis plus pip-audit against the isolated worker requirements |
| DAST | Nuclei misconfiguration/exposure/CVE templates and OWASP ZAP full active scan against a fresh local dashboard container only; no production endpoints or persistent user data |

GitHub Actions are pinned to full commit SHAs. Downloaded scanner binaries are pinned to release versions and checked against SHA-256 digests. Repository permissions are read-only by default; CodeQL receives only the `security-events: write` permission needed to publish findings, and security tools receive only their required read permissions.

The dependency audit generates temporary npm and Cargo lock graphs because the v3 repository currently has no committed root/frontend `package-lock.json` or workspace `Cargo.lock`. For npm, CI installs the generated lock graph with lifecycle scripts disabled, verifies registry signatures and available provenance attestations with `npm audit signatures`, then checks advisories from low severity upward. Cargo audits fail on reported advisories. This verifies package-registry integrity within each run, but it does not provide reproducible dependency resolution between runs. Committing reviewed lockfiles remains a separate supply-chain improvement.

Trivy also publishes validated CycloneDX SBOMs for the source dependency tree and the final production image as seven-day workflow artifacts. These inventories make the shipped package set inspectable independently of the vulnerability scan.

The DAST checks never target a production URL. Nuclei runs from a checksum-verified v3.11.1 release binary and is restricted to misconfiguration, exposure and CVE templates while excluding intrusive, fuzzing, denial-of-service and brute-force tags. OWASP ZAP runs its active scan only against the newly started local dashboard test container, which uses disposable local storage and no production credentials; its raw report and scanner logs stay on the ephemeral runner, while the public job summary exposes only finding counts.

Shannon by Keygraph was evaluated as a direct AI-pentesting alternative. Its [official GitHub Action](https://github.com/KeygraphHQ/shannon-action) explicitly requires a private repository because assessment reports and logs can contain sensitive findings. This repository is public, so the Action is intentionally not configured. Shannon remains an option for a separately authorized private staging environment; it must never be pointed at production.

## Manual live acceptance

Manual dispatch also runs these live checks after the automated pipeline, in sequence. Each job requires the selected ref to be `lemegeton-v3`:

| Check | Required configuration |
|---|---|
| Dashboard OAuth | `DASHBOARD_CLIENT_ID`, `DASHBOARD_CLIENT_SECRET`, `DASHBOARD_REDIRECT_URI`, `DASHBOARD_PUBLIC_URL`, and a 32+ character `DASHBOARD_BRIDGE_SECRET` |
| Discord | `DISCORD_TOKEN`, `DISCORD_TEST_GUILD_ID`, `DISCORD_TEST_INVITER_ID`, `DISCORD_TEST_CHANNEL_ID`, and `DISCORD_TEST_MODERATOR_GUILD_ID` |
| Providers | Steam API key and test profile ID, IGDB client ID/secret, TMDB bearer token; Google Books key is optional |

These require dedicated test accounts and credentials. Because `workflow_dispatch` must exist on the default branch, they are not yet manually runnable from the Actions UI while this workflow exists only on `lemegeton-v3`.

## Runtime and provider coverage

The bot test suite uses disposable local libSQL and RocksDB directories. It does not require a PostgreSQL server, S3 endpoint, production credentials or remote data. Provider API and real Discord checks remain in manual acceptance.

Provider search results are normalized to the shared `SearchRecord` union before aggregation. This keeps Kitsu, MangaDex, Open Library, Google Books, IGDB and Steam results type-safe without widening provider-specific item types. Bot type-check, the full test build and the production image use the same root TypeScript project.

A green CI result is necessary but does not prove production OAuth configuration, live Discord permission behavior, external provider uptime, RocksDB filesystem permissions, VPS firewall state or production backup recoverability. Those require owner-controlled staging acceptance.

## Branch protection

Require only the final `Final CI status (after every check)` status check for this workflow. The individual jobs intentionally retain step-level findings without publishing an early failing job conclusion; the final gate evaluates every job's recorded outcome after all checks finish. Update old required checks that referenced the deleted workflows to this final check. Repository branch-protection settings are not changed by this commit.

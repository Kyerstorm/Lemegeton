# Custom Roles TypeScript test coverage

The legacy Python tests and fake Discord harness are not part of the v3 runtime and must not be run from this branch. This directory is retained only for this migration note; the executable suite is maintained in the root TypeScript test suite.

## Run

From the repository root:

```bash
npm test
```

The current offline Custom Roles tests are in `tests/custom-role-validation.test.ts`. They cover Unicode/custom emoji validation, hex color parsing, protected and reserved names, blocked-word normalization, word-list parsing, eligibility, channel restrictions, role-anchor hierarchy checks, and cooldown calculations. They do not require Discord credentials or PostgreSQL.

## Still requiring focused acceptance tests

The previous Python suite also exercised behavior that is not yet covered by this offline test file:

- PostgreSQL-backed save/update/delete, guild isolation, old booster-role import, and rollback.
- Member join/leave/update lifecycle, periodic reconciliation, role archive/restore, mass-removal approval, and snoozes.
- Discord permission checks, role hierarchy, channel restrictions, interaction ownership, and expired controls.
- Image processing limits, storage round trips, signed URLs, crop persistence, and picker-token lifecycle.
- Picker HTTP security, DNS/SSRF protection, rate/concurrency limits, forwarded-header handling, and proxy integration.
- Complete command/modal/button flows against Discord test doubles and a local PostgreSQL instance.

Do not treat the old Python README or its described scripts as runnable v3 tests. The remaining items must be ported to TypeScript with safe fake Discord objects and an isolated PostgreSQL test database before Custom Roles parity is accepted.

# Database backups

The Data & Backup Centre is available through `/settings action:data-backups` only to bot moderators in the configured operations server.

## Requirements

- A private S3-compatible bucket configured through the existing `S3_BUCKET`, `S3_REGION`, optional `S3_ENDPOINT_URL`, and credentials or workload identity settings.
- The runtime image includes `pg_dump` and `pg_restore` from `postgresql-client`.
- The database role must be allowed to read the schemas and tables included by `pg_dump`.

Backups are written as PostgreSQL custom-format archives under `database-backups/YYYY/MM/`. Objects are uploaded without a public ACL and request S3-managed AES-256 server-side encryption. A database metadata record stores the object key, size, SHA-256 digest, creator and verification state.

## Verification and recovery

After upload, Lemegeton downloads the object again, checks its size and SHA-256 digest, and runs `pg_restore --list` against the archive. The Verify action repeats those checks against a selected stored backup.

This is an archive-integrity check, not a complete restore rehearsal. The current panel never executes `pg_restore` against a live application database. Before production recovery, restore the archive into an isolated PostgreSQL instance of a compatible major version, validate application migrations and data integrity, and only then plan an owner-authorized cutover. Keep the existing database untouched during that rehearsal.

Failed dump, upload or verification operations are recorded as failed. The panel does not delete older backups automatically.

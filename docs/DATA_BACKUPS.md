# Database backups

The Data & Backup Centre is available through `/settings action:data-backups` only to bot moderators in the configured operations server.

## Requirements

- A private S3-compatible bucket configured through `S3_BUCKET`, `S3_REGION`, optional `S3_ENDPOINT_URL`, and explicit credentials or workload identity.
- The runtime image includes `pg_dump` and `pg_restore` from `postgresql-client`.
- The live database role must be allowed to read the schemas and tables included by `pg_dump`.
- Restore rehearsal is optional. Set `BACKUP_REHEARSAL_DATABASE_URL` to a dedicated PostgreSQL cluster on a different host or port from the live database. Its account needs `CREATEDB` permission, and the cluster must be compatible with the archived PostgreSQL major version.

Backups are written as PostgreSQL custom-format archives under `database-backups/YYYY/MM/`. Objects are uploaded without a public ACL and request S3-managed AES-256 server-side encryption. A database metadata record stores the object key, size, SHA-256 digest, creator and verification state.

## Verification and recovery

After upload, Lemegeton downloads the object again, checks its size and SHA-256 digest, and runs `pg_restore --list` against the archive. The Verify action repeats those checks against a selected stored backup.

When a separate rehearsal endpoint is configured, the restricted Rehearse action downloads and verifies the selected backup, creates a uniquely named temporary database on that endpoint, restores the complete archive in a single transaction, and checks that the restored public schema includes Lemegeton's core `guild_retention_settings` table. The bot closes its restore connection and drops the temporary database in its cleanup path. Rehearsal success is recorded with a timestamp; restore or cleanup errors are recorded as failed.

The endpoint is checked at startup configuration time to ensure its host and port do not match the live database. The rehearsal never runs `pg_restore` against the live application database. Do not give the rehearsal account access to the production cluster. The separate cluster should be isolated and protected; the endpoint URL and credentials are never displayed in Discord.

A rehearsal validates that the archive can be restored and contains core tables. It does not prove every external integration, row-level business invariant or a production cutover. Keep the existing database untouched during rehearsal and require an owner-authorized recovery plan for any live restore.

Failed dump, upload, verification, restore or cleanup operations are recorded. Older backups are not deleted automatically.

# Database backups

The Data & Backup Centre is available through `/settings action:data-backups` only to bot moderators in the configured operations server.

## Storage

- `LIBSQL_PATH` points to the shared local libSQL database used by the bot and Rust dashboard.
- `ROCKSDB_PATH` points to the private RocksDB object store.
- `BACKUP_DIRECTORY` selects the local directory for backup bundles; the default is `./data/backups`.
- Keep the database, object store and backup directory on persistent local storage. Restrict access to the bot service account and include the backup directory in the host's off-site backup policy.

Each backup is a compressed `.tar.gz` bundle containing a consistent libSQL snapshot and a RocksDB checkpoint. A metadata row records the bundle key, size, SHA-256 digest, creator, verification state and rehearsal result.

## Verification

After creating a bundle, Lemegeton verifies its size and SHA-256 digest, checks the bundled libSQL integrity result, and checks that the RocksDB checkpoint contains its required manifest files. The Verify action repeats those checks for a selected bundle.

The Rehearse action extracts a selected bundle into a temporary directory and repeats the integrity and checkpoint checks against the extracted copies. It does not replace the active database or RocksDB directory. A successful rehearsal therefore verifies bundle readability and component integrity; it is not a full application restore or a production cutover test.

Failed snapshot, packaging, verification, extraction or cleanup operations are recorded. Older backups are not deleted automatically.

## Recovery boundary

Do not extract a bundle over a running data directory. For recovery, stop the bot and dashboard, preserve the existing data directory, extract the bundle to a separate path, verify both stores, then follow an owner-approved restore procedure. Keep the original bundle and a separate off-host copy until the restored application has been checked.

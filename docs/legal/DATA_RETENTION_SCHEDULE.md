# Data Retention Schedule

**Internal operational document — review before each production deployment.**  
**Last reviewed: November 24, 2026**

This schedule records known lifecycle behavior in Lemegeton v3 and the retention decisions each deployment operator must configure. It is not evidence that a deletion job or expiry period exists unless the implementation and deployment have been tested.

## Retention principles

- Keep identifiable data only while needed for the documented feature, security purpose, or legal obligation.
- Use the shortest practical period and apply the same schedule to replicas, exports, logs, and backups where technically possible.
- A deletion request is not complete until the operator has considered local libSQL database, dashboard libSQL store, RocksDB object storage, legacy Discord storage channels, logs, provider tokens, exports, and backup expiry.
- Guild-level delete/retain choices are not a substitute for a complete retention schedule.
- Do not publish a specific retention period in the Privacy Policy until it is configured and verified in the deployed system.

## Known lifecycle behavior and required decisions

| Data category | Current known behavior | Required operator decision |
|---|---|---|
| Discord OAuth pending state | Short-lived state; the dashboard's OAuth state cookie expires after 10 minutes and is removed after callback. | Verify server-side pending-state expiry and cleanup in the deployed version. |
| Dashboard sessions and OAuth tokens | Server-side session store; expiry follows configured dashboard session lifetime. Logout removes the local session and attempts Discord token revocation. | Set and record session lifetime; verify expired-session and token cleanup. |
| Cookie preference record | Server-side libSQL record expires after 180 days. | Keep the configured expiry aligned with the public notice and test cleanup. |
| Optional remembered-server browser value | Stored only after opt-in; removed when preference is rejected or withdrawn. | Verify browser-side withdrawal and expiry behavior. |
| Guild settings and guild-owned records | When the bot leaves a guild, an authorised user selects delete or retain. An unset choice locks normal functionality. | Define how retained records are periodically reviewed and when they are deleted. |
| Member-scoped provider links and selected preferences | Leaving a guild removes the documented guild-scoped AniList/Steam links and selected profile/Archive browsing preferences. | Verify all user-linked tables and object references covered by member cleanup. |
| Archive contributions, discussions, votes, reports and collections | Not automatically deleted by the member-leave cleanup; subject to moderation, visibility and guild deletion choice. | Define per-record retention and deletion/withdrawal rules, including global records. |
| Uploaded archive media and Custom Role image objects | RocksDB object storage or a legacy private Discord storage channel, depending on guild configuration. | Define object expiry, orphan cleanup, deletion retries, and legacy-channel cleanup. |
| Feedback and issue diagnostics | May retain identifiers, timestamps and bounded error context; no universal expiry is established by this document. | Set a concrete log/diagnostic retention period and automate expiry. |
| libSQL/RocksDB and dashboard backups | Operator-managed under `BACKUP_DIRECTORY`; no universal backup expiry is asserted here. | Set backup frequency, retention, encryption, access restrictions and verified destruction schedule. |
| Provider-linked identifiers and cached metadata | Stored according to the feature and provider integration. | Identify each table/cache, define expiry, and delete credentials/tokens when unlinked or no longer needed. |
| Consent records | Bot policy acceptance is stored by user ID and policy versions. | Define retention after account deletion or withdrawal where applicable; retain only what is necessary to evidence acceptance. |

## Deployment release gate

Before a public deployment, the operator must complete every required decision above and record:

- Actual retention duration for each category.
- The job, query, or operational procedure that enforces it.
- Backup and replica expiry behavior.
- How deletion failures are detected, retried, and escalated.
- Who owns the task and the date it was last tested.

If a category has no defined retention period or deletion owner, treat that as an unresolved launch item rather than silently retaining it indefinitely.

## Review

Review this schedule when a new feature, provider, storage location, log field, or backup mechanism is introduced, and at least annually. Update the Privacy Policy whenever published retention statements change.

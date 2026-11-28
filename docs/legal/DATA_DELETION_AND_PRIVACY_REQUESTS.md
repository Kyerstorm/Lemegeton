# Data Deletion & Privacy Request Procedure

**Internal operational document — applies to the hosted deployment operated by the maintainers.**  
**Last reviewed: November 24, 2026**

## 1. Intake

Accept privacy requests through the private Support Server contact route linked by the bot's `/help` command. Do not ask users to publish identity documents, tokens, private messages, or sensitive evidence in a public channel.

Record only what is needed to manage the request:

- Date received and requested action.
- Requester's contact route and the Discord account/server identifiers needed to locate records.
- Whether the request concerns bot data, dashboard data, guild-controlled content, or an external provider.
- Verification steps, decision, response date, and any reason for a lawful restriction.

## 2. Verify and classify

Verify that the requester controls the relevant Discord account or is authorised to act for the data subject. Use proportionate verification; do not collect additional identity data by default.

Identify the operator's role for the relevant processing. A server owner may control some community purposes; the project operator may control service security, account consent, or hosted infrastructure; external providers control their own services. Route requests to the appropriate controller where the operator does not control the data.

## 3. Search and action

Search the systems actually used by the deployment:

- PostgreSQL records, including guild and user-scoped records.
- Dashboard SQLite sessions, OAuth states and cookie-preference records.
- Private S3-compatible objects and object metadata.
- Legacy private Discord storage channels, if configured.
- Operational logs, diagnostics, feedback, audit records, exports and backups.
- Provider credentials or account links held by Lemegeton.

For access or portability requests, export only the requester's data that the operator is authorised to disclose, in a commonly used structured format where required. Exclude other members' personal data, secrets, security-sensitive material, and information that may lawfully be withheld.

For correction, update inaccurate data where the operator controls it and notify relevant recipients where required.

For erasure, remove or irreversibly anonymise data where required and where no lawful exception applies. Check linked media objects and derived records. Where immediate removal from backups is not technically feasible, restrict backup access and ensure the data expires under the documented backup schedule; explain this limitation where required.

For restriction or objection, stop the affected processing where the law requires it, while preserving data only where a permitted exception applies. For consent withdrawal, stop future processing that relies on that consent; withdrawal does not make prior lawful processing unlawful.

## 4. Guild and member lifecycle

A member leaving a guild triggers the currently implemented cleanup for documented guild-scoped AniList/Steam links and selected profile and Archive browsing preferences. It does not automatically erase historical Archive contributions, feedback, or issue records.

When the bot leaves a guild, the authorised inviter or a member with Manage Server chooses delete or retain. If the choice is unset, normal functionality remains locked. A selected deletion is retried when external storage deletion temporarily fails. Verify database rows and stored objects after retries; do not assume a successful request merely because a queue item was created.

## 5. Response and escalation

Acknowledge and track the request. Where GDPR applies, respond without undue delay and normally within one month of receipt; extensions and refusals must meet the applicable legal conditions and be explained to the requester. Escalate complex, disputed, child-related, law-enforcement, or high-risk requests to the responsible operator and qualified legal/privacy support.

Tell the requester how to complain to the relevant supervisory authority. For Ireland, this is the [Data Protection Commission](https://www.dataprotection.ie/).

## 6. Completion record

Close a request only after recording:

- Systems and data categories searched.
- Actions completed, rejected, or referred and why.
- Storage, replicas, backups and external recipients considered.
- Date and method of response.
- Any follow-up expiry or retry still pending.

Do not store a full copy of the requester's identity documents in the request record. Restrict access to staff who need it.

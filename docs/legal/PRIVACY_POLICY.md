# Lemegeton Privacy Policy

**Effective date: November 28, 2026**

This notice describes information the current Lemegeton v3 implementation may process. What is involved depends on the features enabled by a server, providers configured by the operator, and whether the optional dashboard is used. The source code is available at [Kyerstorm/Lemegeton](https://github.com/Kyerstorm/Lemegeton).

## 1. Who operates the service

Lemegeton is an open-source project. The identity and contact details of the operator responsible for a particular hosted deployment must be supplied by that deployment's operator. For the current bot, contact the operator privately through the Support Server linked in the bot's help command.

A server owner may independently determine why and how their community uses Lemegeton and may have separate responsibilities for content and member information they submit or configure. The legal roles of the project operator, server owner, and infrastructure providers depend on the particular processing activity and deployment. Do not assume that one role applies to every activity.

**Before a hosted public launch, the operator must publish its legal name or organisation, a working privacy contact, and the relevant establishment/address details where required.** The Support Server route is a support channel, not a substitute for legally required controller identification.

## 2. Information processed

Depending on the feature, Lemegeton may process Discord user, guild, channel, message, interaction, and role IDs; usernames, display names and avatars; member data made available through Discord; command options, search terms and URLs; AniList or Steam account identifiers; server settings; archive submissions and attachments—including user-uploaded copyrighted media such as manga panels, comic pages, screenshots, and fan edits; collections, reports, votes, nominations, discussions and session records; feedback; and diagnostic issue records.

The bot requests the Discord Guilds, Guild Members, Guild Messages and Message Content intents. Member events support features such as Custom Roles and guild-scoped account cleanup. Message events support configured Archive uploads and supported link embeds. The bot does not claim that it cannot read message content delivered through the intents it requests, but it does not permanently archive every message it receives.

## 3. Purposes and legal bases

Information is used to provide requested bot and dashboard features, authenticate users, enforce guild permissions, store community contributions, protect the service, investigate errors and abuse, maintain security, and meet legal obligations.

The operator must document the applicable legal basis for each processing purpose before production use. Depending on the activity and the operator's role, a basis may include performance of a contract or steps requested before a contract, legitimate interests subject to a documented balancing assessment, consent where genuinely required, or compliance with a legal obligation. Do not treat consent as the default basis for every feature or rely on it where it cannot be freely given or withdrawn.

## 4. Storage and retention

The TypeScript bot stores feature records and server settings in the local libSQL database configured by `LIBSQL_PATH`. Archive media and Custom Role image objects are stored in the local RocksDB object store configured by `ROCKSDB_PATH`, unless a guild still uses a migrated legacy private Discord storage channel. The Archive intake channel is separate from the private storage destination. The operator must protect the database, object-store directories, and backups with appropriate host-level access controls.

The optional dashboard uses Discord OAuth2 when enabled. Dashboard session state and OAuth tokens are held server-side in the dashboard's libSQL store rather than exposed to the browser. Operational logs and diagnostic records may contain identifiers, command names, timestamps, and bounded error context. Common credential fields and token-like values are redacted from diagnostics, but users should not submit secrets in commands, uploads, or feedback.

A member leaving one guild has their guild-scoped AniList/Steam links and selected profile and Archive browsing preferences removed for that guild. Historical Archive contributions, feedback, and issue records are not automatically removed by that member cleanup. When the bot leaves a server, the server's authorised inviter or a member with Manage Server chooses whether guild data should be deleted or retained. An unset choice keeps normal functionality locked; a selected deletion is retried if an external storage deletion temporarily fails. The retention-policy record is kept so a future re-invite does not silently change the previous choice.

There is no single retention period covering every database row, Discord message, log, provider record, backup, or stored file. Retention also depends on the server operator and deployment configuration. The [Data Retention Schedule](DATA_RETENTION_SCHEDULE.md) identifies known lifecycle behavior and the periods that each operator must configure and verify. Operators must maintain backups and delete them according to a documented retention policy.

## 5. Dashboard cookies and browser storage

When the optional web dashboard is enabled, it uses a small number of first-party cookies and browser storage items:

- **Essential session cookie:** On HTTPS deployments the dashboard sets `__Host-lemegeton_session`. It contains a random opaque session identifier; the session and OAuth tokens remain in the server-side session store and are not placed in browser-readable storage. The cookie is host-only, uses `Path=/`, `Secure`, `HttpOnly`, and `SameSite=Lax`, and expires according to the configured dashboard session lifetime. Local development on localhost uses a non-`__Host-` name because browsers require `Secure` for that prefix.
- **Essential OAuth state cookie:** A short-lived, HttpOnly, SameSite=Lax cookie protects the Discord OAuth2 callback against cross-site request forgery. It expires after ten minutes and is removed after the callback.
- **Cookie choice record:** The dashboard stores an opaque random identifier in an HttpOnly, SameSite=Lax cookie (Secure on HTTPS). The matching server-side libSQL record contains only the optional preference, consent version, decision time, and expiry; it is not linked to a Discord user ID or IP address. This record expires after 180 days and is needed to remember and apply the visitor's choice.
- **Optional functional storage:** If you select “Remember my selected server”, the dashboard stores the last selected Discord server ID in this browser's local storage. This makes the dashboard restore that selection on a later visit. It is not required for dashboard operation. It is not read or written unless enabled, and it is removed when the preference is rejected or withdrawn.

Essential cookies support sign-in, protect the OAuth flow, and retain your cookie decision. They cannot be switched off through the preference controls while using the dashboard. Optional functional storage is off until you choose to enable it. You can accept all available optional storage, reject it, or configure the preference separately. A persistent Cookie settings control lets you change or withdraw that choice later; withdrawing it disables and removes the remembered-server value.

The current dashboard does not use analytics or advertising cookies or third-party advertising trackers. If optional technologies are introduced later, this notice and the preference controls must be updated before they are activated.

## 6. External services and recipients

Depending on the feature and deployment configuration, a lookup may send a title, search phrase, category, public URL, ISBN, provider identifier or linked account identifier to Discord, AniList, Kitsu, MangaDex, Steam, IGDB, TMDB, Google Books, Crossref, Open Library, MusicBrainz, Last.fm, setlist.fm, NovelFire, Noveli.to, Novel Archive, Wuxia Click, Novel Updates, ScribbleHub or Royal Road. Optional music integrations may contact Spotify, YouTube Data API or SoundCloud. Optional translation integrations may send the selected text and language pair to an operator-supplied MADLAD, NLLB or LibreTranslate endpoint, DeepL or Google Cloud Translation. If configured, the optional Cloudflare Turnstile solver may send a public challenge page URL, Turnstile site key, and operator API credential to 2Captcha or CapSolver. These are integration possibilities, not a statement that every provider is enabled in every deployment.

Only information needed for the selected feature should be sent. Each provider controls its own service and privacy practices. See the [Third-Party Services & Disclosure](THIRD_PARTY_DISCLOSURE.md) for the integration families and data sent. The provider names are not a verified list of legal entities or subprocessors for every deployment.

The operator must maintain the [Subprocessor Register](SUBPROCESSORS.md) for the actual deployment, including the legal entity, service, processing role, processing location, transfer mechanism where relevant, and applicable contractual terms. A provider is not a subprocessor merely because Lemegeton can call its API; the role must be assessed for each service and processing activity.

## 7. International transfers

Discord, hosting providers, database providers, object-storage providers, and media services may process information in countries outside the user's country. The operator must identify the actual locations and transfer arrangements for its deployment. Where applicable, international transfers must use a lawful transfer mechanism and any required supplementary safeguards. The operator must not claim that data stays in a particular country unless the deployment and providers verify that claim.

## 8. Security and encryption

Lemegeton is **not end-to-end encrypted (E2EE)**. The bot and authorised operators need to process data required for the requested feature. Supported external requests use HTTPS. The libSQL database and RocksDB object store are local deployment files, so their confidentiality depends on host permissions, disk protection, and secure backups. A legacy Discord storage channel must remain private and grant the bot only the permissions needed to store and retrieve its files.

These controls do not guarantee that every hosting provider, operator device, backup, or external service is configured securely. Encryption in transit is not E2EE.

Copyright reports and counter-notifications may contain contact details, signatures, statements, copies or references to disputed material, and correspondence. The operator should restrict access to personnel handling the report and retain only what is reasonably needed for review, legal obligations, dispute handling, and abuse prevention.

## 9. Privacy rights and requests

Depending on the operator's role and the law that applies, individuals may have rights to access, correct, delete, restrict, object to, or receive a portable copy of personal data, and to withdraw consent where processing relies on consent. Rights are subject to legal conditions and exceptions.

There is not currently one self-service export or deletion command covering every data store and external provider. To make a request, contact the operator privately through the Support Server linked in the bot's help command. Include the Discord account and server context needed to locate the relevant records, but do not post identity documents, passwords, tokens, or sensitive information in public channels. The operator may ask for proportionate information to verify the request.

The operator should respond within the time required by applicable law, explain any lawful limitation or refusal, and provide the route to complain to the relevant supervisory authority. For users in Ireland, the supervisory authority is the [Data Protection Commission](https://www.dataprotection.ie/). The [Data Deletion & Privacy Request Procedure](DATA_DELETION_AND_PRIVACY_REQUESTS.md) describes the internal handling process.

## 10. Children

Lemegeton is a Discord bot and is subject to Discord's age requirements and the laws applicable to the operator and users. The operator must not knowingly collect information from a child where doing so would be unlawful. Server owners are responsible for configuring their communities and channels in accordance with applicable law and Discord rules.

## 11. Access, sharing, and open source

Lemegeton does not sell personal data or provide third parties with blanket access to the application's database. Infrastructure vendors and external providers may process the information necessary to deliver their services. A valid legal request may require an operator or provider to disclose data it controls, subject to applicable law.

The MIT licence applies to the software source code; it does not make hosted databases, private archive files, or users' submissions public. User submissions and third-party works remain subject to their own rights; see the [Intellectual Property Notice](INTELLECTUAL_PROPERTY.md) and [Open-Source & Third-Party Licences](OPEN_SOURCE_LICENSES.md). Actual processing depends on the deployment, enabled features, and its operator's configuration.

## 12. Changes and contact

This notice may be updated when features, providers, processing purposes, or legal requirements change. The effective date at the top identifies the current published version. For questions or privacy requests, contact the operator privately through the Support Server linked by the bot's help command.

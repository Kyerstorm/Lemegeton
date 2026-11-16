# Lemegeton Privacy Policy

**Effective date: November 12, 2026**

This notice describes information the current Lemegeton v3 implementation may process. What is involved depends on the features enabled by a server, the providers configured by the operator, and whether the optional dashboard is used. The source code is available at [Kyerstorm/Lemegeton](https://github.com/Kyerstorm/Lemegeton).

## Information processed

Depending on the feature, Lemegeton may process Discord user, guild, channel, message, interaction, and role IDs; usernames, display names and avatars; member data made available through Discord; command options, search terms and URLs; AniList or Steam account identifiers; server settings; archive submissions and attachments; collections, reports, votes, nominations, discussions and session records; feedback; and diagnostic issue records.

The bot requests the Discord Guilds, Guild Members, Guild Messages and Message Content intents. Member events support features such as Custom Roles and guild-scoped account cleanup. Message events support configured Archive uploads and supported link embeds. The bot does not claim that it cannot read message content delivered through the intents it requests, but it does not permanently archive every message it receives.

## Storage and retention

The TypeScript bot stores feature records and server settings in PostgreSQL. Archive media is stored according to the server's existing configuration: a guild with a migrated legacy private storage channel continues using that channel; a guild without a legacy storage setting uses the configured private S3-compatible storage. The Archive intake channel is a separate setting and is not used as the private storage destination. Custom Role image originals use private object storage when that feature is configured.

The optional dashboard uses Discord OAuth2 when enabled. Dashboard session state and OAuth tokens are held by the dashboard service rather than exposed to the browser. Operational logs and diagnostic records may contain identifiers, command names, timestamps, and bounded error context. Common credential fields and token-like values are redacted from diagnostics, but users should not submit secrets in commands, uploads, or feedback.

A member leaving one guild has their guild-scoped AniList/Steam links and selected profile and Archive browsing preferences removed for that guild. Historical Archive contributions, feedback, and issue records are not automatically removed by that member cleanup. When the bot leaves a server, the server's authorised inviter or a member with Manage Server chooses whether guild data should be deleted or retained. An unset choice keeps normal functionality locked; a selected deletion is retried if an external storage deletion temporarily fails. The retention-policy record is kept so a future re-invite does not silently change the previous choice.

There is no single retention period covering every database row, Discord message, log, provider record, backup, or stored file. Retention also depends on the server operator and deployment configuration. The operator should maintain backups and delete them according to their own retention policy.

## External services

Supported media features may send relevant search terms, URLs, provider identifiers, or linked account identifiers to AniList, Steam, IGDB, TMDB, and Google Books. Discord is used to deliver commands, interactions, messages, attachments, and OAuth2. Hosting, PostgreSQL, and configured private object-storage providers process information required to operate the deployment. Only the data needed for a selected feature should be sent to its provider. Each external provider controls its own service and privacy practices.

## Security and encryption

Lemegeton is **not end-to-end encrypted (E2EE)**. The bot and authorised operators need to process data required for the requested feature. Supported external requests use HTTPS. Production PostgreSQL connections can require TLS with certificate verification. Archive objects and Custom Role image originals are stored as private objects when S3-compatible storage is used; access is provided through short-lived URLs or server-side handling. A legacy Discord storage channel must remain private and grant the bot only the permissions needed to store and retrieve its files.

These controls do not guarantee that every hosting provider, operator device, backup, or external service is configured securely. Encryption in transit is not E2EE.

## Privacy requests and contact

There is not currently one self-service export or deletion command covering every data store and external provider. For a privacy request, contact the operator privately through the Support Server linked in the bot's help command. Do not use public feedback channels for confidential requests: feedback is delivered to the configured server channel and may be discussed there.

## Access, sharing, and open source

Lemegeton does not sell personal data or provide third parties with blanket access to the application's database. Infrastructure vendors and external providers may process the information necessary to deliver their services. A valid legal request may require an operator or provider to disclose data it controls, subject to applicable law.

The MIT licence applies to the software source code; it does not make hosted databases, private archive files, or users' submissions public. Actual processing depends on the deployment, enabled features, and its operator's configuration.

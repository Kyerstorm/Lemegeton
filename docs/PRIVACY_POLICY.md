# Lemegeton Privacy Policy

**Effective date: November 3, 2026**

This notice describes information the currently implemented Lemegeton bot may process. Features, providers, and deployment settings affect what is involved. The source code is available at [Kyerstorm/Lemegeton](https://github.com/Kyerstorm/Lemegeton).

## Information processed

Depending on the features used, Lemegeton may process Discord user, guild, channel, message, interaction, and role IDs; usernames and display names; avatars; member and invite metadata; command options and search terms; source links and provider identifiers; account names used for AniList or Steam linking; server configuration; moderation and audit events; community submissions, tags, reports, votes, and discussions; and feedback text or optional attachments.

The running bot is configured with Discord's Message Content and Members intents. It can receive message-content fields and member data/events that Discord makes available. Specific listeners inspect supported links and messages to provide their features. This does not mean every message is permanently archived, but it would be inaccurate to claim the bot cannot read messages it receives.

## Logs and records

Application logs may contain user and guild IDs, display names, command names, timestamps, exception text, and diagnostic context. Feature-specific records may include provider usernames/IDs, invite codes, submission content, moderation actions, or feedback identifiers.

The main application uses PostgreSQL for many feature records and server settings. The optional GPT responder uses a separate local SQLite database for per-user/per-guild conversation history. Feedback text and attachments are sent to the configured Discord feedback channel and may be discussed in a server thread. Panel and Custom Role image originals use a private S3-compatible bucket when configured; generated grids or collages may use a separately configured public bucket. The optional web dashboard keeps Discord profile/session data and OAuth tokens server-side in process memory for the session lifetime. The first-use agreement gate stores the user's Discord ID, the accepted Terms of Service, Privacy Policy, and Community Guidelines versions, and the acceptance timestamp.

## External services

Commands may send relevant search terms, URLs, account names, or provider identifiers to Discord, AniList, Steam, IGDB, TMDB, Google Books, Novel Updates, Novel Phoenix, NovelFire, Novelist, configured AI/chat providers, hosting providers, database providers, or object-storage providers. Only the providers needed by the chosen feature should receive its request. Each provider operates under its own terms and privacy policy.

## Encryption

Lemegeton is **not end-to-end encrypted (E2EE)**. The bot needs readable data to perform the feature requested, and the running service and authorised operators may access information available to that service. Supported remote database connections use TLS with certificate and hostname verification, and supported HTTPS connections protect data in transit. Encryption in transit is not E2EE. The project cannot verify the at-rest encryption or backup configuration of every deployment.

## Retention and requests

There is no single retention period for all logs, database records, GPT conversation history, Discord feedback messages, provider-side copies, or stored files. The main bot clears its local log files during startup, but that does not automatically erase the other records described above. Some records are removed by feature-specific cleanup or operator action; other records may remain until the relevant system or operator deletes them.

There is not currently one self-service export or deletion command covering every data store. For a privacy request, contact the operator privately through the Support Server linked in the bot's help command. Do not use the feedback command for confidential requests: feedback is posted to the configured channel and may receive a public thread.

## Access, sharing, and open source

The MIT licence does not make a hosted database public, and it does not give outside companies automatic access to user records. Lemegeton does not sell personal data or provide companies with blanket database access. Infrastructure vendors and external providers may process information required to deliver their services. A valid, binding legal request may require an operator or infrastructure provider to disclose data it controls; any response should be limited to what applicable law requires, and notice is provided only where legally permitted.

You can inspect the implementation in the [public GitHub repository](https://github.com/Kyerstorm/Lemegeton). The actual behaviour of a deployment depends on its operator, enabled features, and configuration.

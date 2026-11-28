# Third-Party Services & Disclosure

**Last reviewed: November 28, 2026**

Lemegeton connects to third-party platforms and metadata services when a user invokes a feature that needs them, or when an operator enables an optional integration. Actual recipients depend on deployed configuration. This is an integration disclosure, not a statement that every named provider is a contractual subprocessor.

## Discord

Discord provides the bot platform, interactions, messages, attachments, guild/member context and, when enabled, dashboard OAuth2 sign-in. Discord receives the information needed to deliver those platform functions under its own terms and privacy documentation.

## Media metadata and discovery

Depending on the feature, a lookup may send a title, search phrase, category, public URL, ISBN, provider identifier or linked account identifier to:

- AniList and Kitsu
- MangaDex
- Steam and IGDB
- TMDB
- Google Books, Crossref and Open Library

A request is made only for the selected lookup or integration. Linked account identifiers are used only by features that support and have configured that linkage.

## Webnovel sources

Selected public searches and lookups may contact NovelFire, Noveli.to, Novel Archive, Wuxia Click, Novel Updates, ScribbleHub or Royal Road. Requests can contain the title or URL being looked up. Royal Road lookups use its public fiction feed. These are external content sources; their availability and terms are controlled by their respective operators.

## Optional Cloudflare Turnstile challenge solving

When an operator enables the optional Turnstile solver, the configured provider is either 2Captcha or CapSolver. The selected provider receives the public challenge page URL, the Cloudflare Turnstile site key, and the operator's API credential for task creation and polling. It returns a challenge token that the isolated Botasaurus worker uses transiently on the challenged page. The solver integration does not send Discord credentials, browser session cookies, or Lemegeton database records to the solver. Avoid sensitive query parameters in challenge URLs, and review the provider's privacy terms, processing role, and transfer arrangements before enabling it. This integration is disabled when `CAPTCHA_SOLVER_PROVIDER` is unset.

## Music services

Music discovery can contact MusicBrainz, Last.fm and setlist.fm. Optional operator-configured features may also contact Spotify, YouTube Data API or SoundCloud. Requests may include artist names, track/album search terms, provider identifiers or the identifiers needed for the selected feature. Optional services are not necessarily enabled in every deployment.

## Translation services

If an operator configures translation, the text selected for translation and its source/target language may be sent to the configured provider. Supported integrations include operator-supplied MADLAD, NLLB or LibreTranslate endpoints, DeepL and Google Cloud Translation. Do not submit passwords, tokens, private messages or other sensitive content for translation.

## Hosting, storage and other infrastructure

The deployment operator chooses the hosting, network, database, backup and storage environment. Those vendors may process service and operational data as required to run that deployment. Their identity, legal entity, locations, processing role, contractual terms and transfer safeguards must be recorded for the actual deployment in the internal [Subprocessor & Service Provider Register](SUBPROCESSORS.md). This repository does not assert that a vendor is a processor merely because it hosts a service.

## What is shared

A provider receives only the information needed for the particular request, which can include a search term, URL, media identifier, linked external account identifier, or text submitted for translation. The provider's own service may also process ordinary connection and request metadata. Review the provider's own privacy terms for its handling, retention and disclosure practices.

Providers may act as independent controllers, processors, or in another capacity depending on the service and the actual arrangement. The operator must assess that role service-by-service. This disclosure does not grant a provider blanket access to Lemegeton's database and does not mean that all listed integrations are enabled.

Lemegeton does not sell personal data. The current dashboard does not use analytics or advertising cookies. Any material change to providers, purposes or data sent must be reflected in this notice and the [Privacy Policy](PRIVACY_POLICY.md).

## Related documents

- [Privacy Policy](PRIVACY_POLICY.md)
- [Subprocessor & Service Provider Register](SUBPROCESSORS.md) — internal deployment record
- [Data Protection Compliance Record](DATA_PROTECTION_COMPLIANCE.md) — internal readiness record

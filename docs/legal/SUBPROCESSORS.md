# Subprocessor & Service Provider Register

**Internal operational register — deployment-specific.**  
**Last reviewed: November 24, 2026**

This is a register template and integration inventory, not confirmation that every listed provider is a subprocessor for every deployment. The operator must identify the actual legal entity, service, processing role, data location, contract, and transfer mechanism before production use.

## Infrastructure and platform services

| Service category | Provider / entity | Processing | Location | Contract / DPA | Transfer basis | Status |
|---|---|---|---|---|---|---|
| Discord platform and OAuth2 | Discord, Inc. / applicable Discord entity | Commands, interactions, guild/member identifiers, messages and OAuth | Verify provider terms | Review applicable terms | Verify for deployment | Verify |
| Application hosting | Fill per deployment | Bot/dashboard runtime, logs and network data | Fill | Fill | Fill | Required |
| Local libSQL database | Deployment operator | Feature records, account links, guild settings and community content | Deployment host | Operator-managed | Verify host | Required |
| RocksDB object store | Local deployment storage | Archive media and Custom Role image objects | Deployment host | Operator-managed | Verify host | Required |
| Dashboard session storage | Hosted with Rust dashboard service; libSQL | OAuth sessions, state, rate-limit and cookie preference records | Deployment host | Operator-managed | Verify host | Verify |

## Media and metadata integrations

| Provider / service | Feature or request data | Account linkage | Deployment enabled? | Contract / transfer review |
|---|---|---|---|---|
| AniList | Media metadata and relevant search/linked account identifiers | Optional | Verify | Review provider terms |
| MangaDex | Manga metadata, title/category queries | No account link asserted here | Verify | Review provider terms |
| Steam | Supported profile/game information and linked account identifier | Optional | Verify | Review provider terms |
| IGDB | Game metadata queries | No account link asserted here | Verify | Review provider terms |
| TMDB | Film/TV metadata queries | No account link asserted here | Verify | Review provider terms |
| Google Books | Book metadata and search/ISBN queries | No account link asserted here | Verify | Review provider terms |
| Crossref / Open Library | Book or publication metadata and ISBN/title queries | No account link asserted here | Verify | Review provider terms |
| NovelFire, Noveli.to, Novel Archive, Wuxia Click, Novel Updates, ScribbleHub, Royal Road | Selected public webnovel lookup/search requests | No account link asserted here | Verify | Review provider terms and scraping restrictions |
| Spotify, YouTube Data API, SoundCloud | Optional music discovery and artist/release features | Depends on configured API/auth flow | Verify | Review provider terms |

## Required completion fields

For each provider actually enabled, record:

- Full legal entity name and country of establishment.
- Service name, purpose, categories of data, and whether it receives personal data.
- Whether the provider acts as a processor, independent controller, or another role for the relevant activity.
- Hosting/processing locations and onward subprocessors.
- Contract, data processing terms, security commitments and deletion terms.
- International transfer mechanism and supplementary safeguards where applicable.
- Date assessed, owner, and next review date.

Do not list a provider as a contracted subprocessor until the relevant agreement and processing role have been checked. Remove integrations that are not enabled by the deployment from the live subprocessor notice where appropriate. Update the public Privacy Policy when actual recipients or purposes materially change.

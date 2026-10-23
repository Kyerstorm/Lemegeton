# Seven additional Lemegeton commands

These commands live under cogs_test/general_commands and are discovered by the existing recursive cogs_test loader. They do not change the primary cogs implementation.

- /server-taste action:report|opt-in|opt-out category:ANIME|MANGA reads only linked accounts for the invoking guild. Participation is opt-in and stored by guild/user pair. It counts each genre and eligible non-spoiler tag once per account. Aggregate interests remain hidden until at least three public samples succeed.
- /server-check is a read-only, Manage Server-gated diagnostics report for the current guild and invocation channel. It checks channel permissions and the existing bot-updates / invite-notification channel settings; refresh is scoped to the original guild and channel.
- /game title: searches IGDB using existing Twitch client credentials, requests extended game metadata, and adds Steam details only for an exact title match.
- /media-night start category:ANIME|MANGA candidates:2..5 duration:5..240 starts public community voting. /media-night close session_id: action:close|cancel ends it. Sessions are persisted in PostgreSQL, scoped by guild and channel, restored after bot restarts, and expire automatically. Votes can be changed while open; ties are reported as ties.
- /compare first: second: category:ANIME|MANGA|BOOK|MOVIE|TV|GAME compares provider results. When title searches are ambiguous, select the intended result on both sides. Scores keep their provider attribution and no combined winner is calculated.
- /franchise title: category:ANIME|MANGA opens provider-supplied AniList relationship links, paginated with buttons. Labels are provider-defined; the command does not claim a definitive viewing or reading order.
- /airing accepts optional title, day, season, and year filters. Expected schedule timestamps are rendered with Discord UTC timestamps and described as subject to change.

## Providers, configuration, and limitations

No new package dependencies or API credentials are introduced. IGDB game detail and game comparison require the existing IGDB_CLIENT_ID and IGDB_CLIENT_SECRET. Movie and television comparisons use the existing TMDB_BEARER_TOKEN; critic/user Metacritic scores are shown only when the existing MDBLIST_API_KEY returns corresponding records. AniList schedule and relationship information depends on provider availability and coverage.

The new persistent state consists of a guild-scoped server_taste_opt_ins table and a media_night_sessions table with guild/channel/host scope. Both are initialized idempotently through the shared PostgreSQL helper. The airing display timezone defaults to UTC because no existing user-specific timezone preference was identified.

The cogs_test directory is experimental in this repository. The standard startup loader discovers these cogs and the existing startup flow synchronizes the slash commands. The commands have not been live-tested against a connected Discord bot or production credentials as part of this change.

# GitHub Activity Tracker

The bot exposes one moderator-only slash command: `/github`. It is registered only in `BOT_MODERATOR_GUILD_ID` and every action also checks the configured administrator or the `bot_moderators` table.

## Actions

- **Recent commits** — privately previews the latest commits (1–20) with one combined total for additions, deletions and distinct file paths.
- **Tracker status** — shows the repository, branch, polling interval, announcement channel and last tracked commit.
- **Check for new commits** — compares the current branch with the stored commit cursor and returns one consolidated activity summary. When an update channel is configured, the same summary is published there.

The summary lists recent commit subjects beneath the combined totals. Statistics are looked up for up to 20 commits per batch. If a batch contains more than 20 commits or GitHub omits some details, the embed identifies the partial coverage; the sampled statistics come from the newest commits in that batch.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_REPO` | `Kyerstorm/Lemegeton` | Repository in `owner/name` format. |
| `GITHUB_BRANCH` | `lemegeton-v3` | Branch to monitor. |
| `GITHUB_TOKEN` | Empty | Optional GitHub token for higher API rate limits. |
| `GITHUB_POLL_MINUTES` | `10` | Background polling interval, in minutes. |
| `GITHUB_UPDATE_CHANNEL_ID` | Empty | Optional destination for automatic activity announcements. |

Automatic announcements require both `BOT_MODERATOR_GUILD_ID` and `GITHUB_UPDATE_CHANNEL_ID`. The update channel must be a text or announcement channel inside the configured moderator server, and the bot must have View Channel, Send Messages and Embed Links permissions there. No other guild receives GitHub announcements.

On first startup, the tracker stores the current branch head as its baseline; it does not publish the repository's previous history. If the stored commit is no longer present in the most recent 100 commits, the tracker resets its baseline without replaying the older history. State is stored per repository and branch in `github_tracker_state`.

Without an update channel, automatic polling is disabled. The three `/github` actions remain available to authorised bot moderators, and **Check for new commits** returns its grouped result privately.

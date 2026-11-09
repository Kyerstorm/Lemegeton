# Interaction and UX Guidelines

These guidelines keep the Discord bot's interactions consistent, responsive, and easy to understand. They apply to slash commands, buttons, select menus, modals, scheduled deliveries, and dashboard-triggered bot actions.

## Interaction principles

- Keep the interface purposeful. Use concise labels and short response copy; do not bury the result beneath long explanations.
- Reuse the shared embed builders and palette rather than introducing one-off visual systems.
- Use the central emoji palette in `helpers/emoji.ts`. Do not scatter raw custom emoji IDs through commands.
- Preserve the guild context for every server-owned action. Private account or diagnostic information must not be exposed in public channel responses.
- Keep `/help`, `/privacy`, and `/feedback` as standalone commands. `/log`, `/moderators`, and `/planned` are also standalone moderator commands and must remain restricted to the configured moderator server.

## Loading and progress states

Use `loadingMessage(activity)` from `helpers/emoji.ts` for loading copy so the loading indicator stays consistent. The palette provides a valid Unicode loading fallback; do not add a made-up Discord emoji ID.

Vary the activity text to match the real operation rather than repeating a generic “Loading...” message. Examples:

- `⏳ Searching supported media...`
- `⏳ Fetching provider details...`
- `⏳ Preparing your archive preview...`
- `⏳ Saving your changes...`
- `⏳ Gathering community results...`
- `⏳ Building the comparison...`

The variation is presentation, not simulated progress. Do not add artificial delays, pretend that a step has completed, or rotate through messages while the underlying operation is idle. Update the message when the real operation reaches a meaningful stage.

## Discord response lifecycle

1. Perform cheap validation and permission checks before starting provider or database work.
2. For work that may exceed Discord's initial response window, acknowledge promptly with `deferReply` or `deferUpdate`.
3. Choose ephemeral responses for private, personal, or diagnostic information. Keep ordinary guild results visible in the channel when they benefit the community.
4. Edit the deferred response with the final result instead of sending a second unrelated response.
5. Acknowledge each interaction exactly once. Guard against duplicate button submissions and disable or otherwise protect controls while a mutation is in flight.
6. Do not leave a loading response behind after success, failure, cancellation, or timeout.

Use the correct acknowledgement for the interaction type: `deferUpdate` when only the existing component message is being updated, and `deferReply` when producing a separate response. Never defer an interaction and then attempt a second initial reply.

## Embeds and components

- Use the shared embed helpers and semantic palette states for success, warning, error, and informational results.
- Keep titles descriptive and body copy brief. Put secondary metadata in fields rather than large blocks of prose.
- Preserve provider attribution and source links when showing external media metadata.
- Use consistent button labels and ordering. Navigation controls should be predictable; destructive actions should be clearly distinguished and require the appropriate confirmation.
- Do not communicate status through colour or emoji alone. Keep text labels understandable without decorative symbols.
- Prefer editing the current message when a user changes a filter, page, selection, or vote; avoid creating duplicate result messages.

## Errors and diagnostics

- Route unexpected interaction failures through the shared diagnostic logging path.
- Return a short, user-safe error message and the generated issue reference when available. Direct users to include that reference in `/feedback`.
- Never expose tokens, environment variables, SQL details, provider credentials, or raw stack traces in user-facing messages.
- Do not swallow an error after showing a success state.

## Acceptance checks for new interactions

- The interaction is acknowledged within Discord's response window and exactly once.
- Loading copy uses the shared helper and describes the operation honestly.
- Success, cancellation, timeout, and failure all leave a clear final state.
- Rapid repeated clicks cannot create duplicate writes or votes.
- Guild permissions and private/public visibility are correct.
- Long provider calls fail gracefully and produce a diagnostic reference where appropriate.
- Tests cover the interaction's state transitions and failure path where the logic can be exercised without a live Discord session.

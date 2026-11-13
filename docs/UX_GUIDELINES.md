# Interaction and UX Guidelines

These guidelines are the product contract for every Lemegeton surface: Discord commands, components, scheduled deliveries, media presentations, the Next.js dashboard and the Rust/Axum API boundary. Apply them to new work and when touching existing flows. The goal is a coherent, low-friction media and community experience—not more panels, copy or decorative effects.

## 1. Product principles

- Make the next useful action obvious. Prefer one clear primary action over a row of competing choices.
- Keep Discord commands as focused entry points into the larger command experiences. Keep /help, /privacy and /feedback independent.
- Use concise labels and direct copy. Avoid repeated introductions, excessive metadata, filler text and decorative status language.
- Keep the interface consistent across commands, embeds and dashboard pages. A new surface must reuse existing patterns unless the current pattern cannot represent the task.
- Never imply that an unfinished, unavailable or unverified integration works. Clearly distinguish configured, reachable, degraded and unavailable states.
- Preserve the product boundary: media discovery, community archives, events and games. Do not add personal watch/read/play tracking or generic productivity/reminder features as a side effect of UX work.

## 2. Discord interaction contract

### Before work begins

1. Validate interaction context, guild setup, actor permissions and input before provider or database work.
2. Enforce authorization twice where appropriate: Discord command default permissions for discoverability, plus runtime permission checks in the handler. A command that must always exist must also be protected from dashboard toggles and command-reset operations.
3. Keep all guild-owned reads and writes scoped to the invoking guild. Re-check the guild and actor on every button, modal and select-menu interaction; never trust a component custom ID as authorization.
4. Use ephemeral replies for private settings, consent, account links, permission failures, diagnostics and actions that reveal personal or administrative data. Use public responses when the result is intended for the server.

### Acknowledgement and progress

- Acknowledge each interaction exactly once.
- Complete cheap validation before acknowledging. For operations that may exceed Discord's initial response window, use deferReply or deferUpdate promptly.
- Use deferUpdate when the current component message is the result being changed. Use deferReply when producing a separate response.
- Edit the deferred response/message for the final result. Do not create a second, unrelated response for a normal completion.
- Use loadingMessage(activity) from helpers/emoji.ts for bot loading copy. Name the real operation. Do not simulate progress, add artificial delays or leave a spinner after completion.
- Every success, failure, cancellation and timeout path must leave a useful final state. Handle expired component interactions without exposing raw Discord or provider errors.

### Components and state

- Keep interaction state transitions explicit: idle, loading, success, failed, cancelled or expired as appropriate.
- Protect mutations against duplicate submissions and rapid repeated clicks. Use database constraints, transactions, idempotency keys or a short-lived in-flight guard according to the operation.
- Re-check permission, guild ownership, target existence and current record status before destructive or privileged actions.
- Confirm irreversible or consequential operations. Make cancellation safe and visible.
- Disable controls only while the related action is in flight or when the action is genuinely unavailable. Explain the reason for a disabled action in nearby text.
- Keep navigation predictable. Edit the current message for paging, filtering, selections and votes where practical; do not flood channels with replacement messages.

## 3. Discord embeds and copy

- Use shared embed builders and semantic colors from the existing helpers. Avoid introducing one-off embed palettes.
- Use descriptive titles, short descriptions and fields for secondary facts. Respect Discord embed, field and component limits before sending.
- Keep the primary action and the subject of the response near the top. Put provider IDs, timestamps and secondary context lower in the presentation.
- Preserve provider attribution and usable source links. Do not convert recommendations or community submissions into provider-confirmed facts.
- Use plain-language status labels alongside color or symbols. Color and emoji must never be the only indication of success, warning, failure, permission or provenance.
- Sanitize provider/user text before placing it in embeds. Bound lengths, neutralize unsafe markup and restrict outbound media links to validated HTTPS URLs where required.
- Avoid long copyrighted excerpts. Prefer a short synopsis or metadata with attribution.

## 4. Shared emoji and visual language

- helpers/emoji.ts is the single source of bot emoji values and names. Command and helper files must import from it rather than embedding emoji values or Discord custom-emoji IDs.
- Keep the current palette Unicode-based. Future animated/custom replacements should be made by changing the central palette only; do not scatter custom IDs across commands.
- Keep icons consistent by meaning: success, failure, loading, warning, navigation, media category and provenance should not change semantics between commands.
- Do not use emoji as a substitute for a button label, accessible name or explicit status text.
- Reuse the shared embed colors and controls. Do not add decorative visual systems or per-command theme variants.

## 5. Dashboard experience

- Keep the Next.js client responsible for presentation and local interaction state. The Rust/Axum API remains the authenticated authorization boundary; the Node bridge remains internal and secret-authenticated.
- Never let a client-only hidden button or disabled switch act as the security control. Enforce protected-command and guild permissions in the API/bridge as well as in the UI.
- Scope every server query and mutation to a guild the signed-in user can currently manage. Revalidate access on each request, not only at login or initial page load.
- Show loading, stale, unavailable and confirmed states distinctly. Cached/last-known telemetry must never be labelled live.
- For mutations, show the pending state, require confirmation when consequential and report success only after the server confirms the change.
- Keep the selected server visible in the page context. Switching servers must clear previous server data immediately so content cannot briefly appear under the wrong guild.
- Provide responsive layouts for narrow screens. Preserve the core action and server context without horizontal page scrolling.
- Keep focus visible, labels explicit and navigation usable by keyboard. Use semantic buttons/links and accessible names for icon-only controls.

## 6. Accessibility, readability and motion

- Target at least 40 px for dashboard controls and 44 px for primary touch navigation where layout permits. Discord component sizing is controlled by Discord, so use clear labels and avoid unnecessary adjacent controls.
- Use readable body text and avoid important metadata below 11 px. Do not shrink text to fit dense panels; remove or reflow lower-priority content instead.
- Maintain strong text/background contrast. Never communicate state through monochrome brightness, color or animation alone.
- Every input needs a visible or programmatic label. Every icon-only control needs an accessible name. Decorative icons and motion must be hidden from assistive technology.
- Keep keyboard focus visible and ensure tab order follows the visual reading order.
- Respect prefers-reduced-motion for all animation and transitions, not only decorative marquee effects. Do not put information exclusively in motion.
- Use touch-friendly spacing and avoid hover-only interactions. Test the dashboard at narrow/mobile widths as well as desktop.

## 7. Localization

- Translate static bot UI copy using the guild's configured language service. Keep English as the reliable fallback when translation is unavailable or malformed.
- Do not translate user-submitted content, provider titles, author/creator names, URLs, identifiers, ISBNs, platform names or source evidence unless an integration explicitly supplies a localized field.
- Preserve placeholders, Markdown, URLs, Discord mentions, IDs, code blocks and number/date meaning when translating.
- Do not use a translation result to alter permissions, command names, option values, database keys or provider facts.
- Keep the language selection server-wide and permission-gated. Only members with Manage Server may use /language; the command remains registered and permanently protected from dashboard disabling.

## 8. Errors, diagnostics and privacy

- Return a short, actionable, user-safe error. When an issue reference exists, include it and direct the user to /feedback.
- Never expose credentials, tokens, environment values, SQL statements, internal bridge secrets, stack traces or raw provider payloads in Discord or the dashboard.
- Log enough structured context to diagnose failures—guild, command, issue reference and safe provider category—without logging secrets or unnecessary personal data.
- Do not swallow errors after showing success. If an audit write is intentionally best-effort, make that behavior explicit in logs and keep the primary mutation result truthful.
- Explain the scope and consequence before collecting consent or performing retention/deletion actions. Keep account unlinking and privacy controls understandable and reversible where possible.
- Do not show private Archive assets, unpublished community submissions or cross-guild data in graph nodes, previews, images, exports or deep links.

## 9. Media provenance and uncertainty

- Keep provider facts, provider recommendations, locally calculated similarities and community-submitted relationships visibly distinct.
- Preserve provider name, stable identifier, source URL and relevant source timestamp where available. When a provider does not expose a field, label it unavailable rather than guessing.
- Preserve work/edition and media-category distinctions. Do not merge different editions just because titles match.
- Mark approximate, estimated or inferred fields. Never present them as provider-confirmed facts.
- Re-check visibility for every graph traversal hop, image fetch, export and community reference—not just the selected root node.

## 10. UX acceptance checklist

A changed interaction is ready only when applicable checks pass:

- [ ] Permission and guild context are checked before work and re-checked on every component mutation.
- [ ] Public/private visibility is intentional and matches the data being shown.
- [ ] The interaction is acknowledged exactly once and within Discord's response window.
- [ ] Loading text describes real work; all terminal paths leave a clear state.
- [ ] Duplicate clicks/submissions cannot create duplicate writes, votes or deliveries.
- [ ] Destructive operations have explicit confirmation and a safe cancellation path.
- [ ] Errors are actionable and contain no secrets or raw stack traces.
- [ ] Provider/community provenance, source links and unavailable states are clear.
- [ ] Emoji values come from the shared Unicode palette.
- [ ] Dashboard controls have accessible labels, visible focus, reduced-motion support and a usable mobile layout.
- [ ] Guild isolation, privacy visibility, limits and failure cases have focused regression tests.
- [ ] Documentation and the Expansion Roadmap reflect actual behavior; planned work is not marked complete merely because a UI option exists.

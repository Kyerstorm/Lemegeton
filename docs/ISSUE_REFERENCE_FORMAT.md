# Issue reference format

This is a fixed user-facing contract shared by automatic diagnostics, `/feedback`, and the bot-moderator-only `/log` command.

## Format

- Exactly **40 characters**.
- Lowercase hexadecimal (`0-9`, `a-f`).
- No prefix, separator, numeric counter, or shortened display form.
- The 40 characters are the first 40 hexadecimal characters of a SHA-512 digest. The digest input includes 32 cryptographically random bytes, a freshly generated UUID, the Discord interaction ID, and the affected user ID.
- A new reference is generated for every issue occurrence. The database primary key and bounded collision retry are the final uniqueness guard.

This is intentionally a 40-character SHA-512-derived reference. Do not change it to a 128-character full digest, a sequential value (for example `Q120`), a UUID by itself, or a different hash format without an explicit product decision.

## User flow

Generated references are lowercase. Input validation trims surrounding whitespace and accepts uppercase hexadecimal by normalizing it to lowercase before lookup.

1. When a guild interaction fails, the bot attempts to store a sanitized diagnostic record and shows the 40-character reference.
2. The user can paste that reference into the optional issue-reference field in `/feedback`.
3. `/feedback` validates the exact 40-character format and confirms that the reference belongs to the submitting guild before attaching it to feedback.
4. Bot moderators use `/log` in the configured operations server. The command authorizes the bot moderator and looks up the globally unique reference, allowing support across guilds without exposing the lookup to ordinary members.

The diagnostic record remains guild-scoped. Moderator lookup is intentionally cross-guild only after the bot-moderator authorization checks. Diagnostic details must continue to be sanitized before storage and display.

## Change checklist

When touching issue references, update and test all of these together:

- `helpers/runtime/issue-logs.ts`: generator and validator.
- `database.ts`: `issue_logs.issue_hash` check constraint.
- `src/standalone/feedback.ts`: modal max length, placeholder, validation text, and originating-guild check.
- `src/standalone/log.ts`: required option length, help text, and moderator authorization.
- `tests/issue-logs.test.ts`: exact length, hex format, per-occurrence uniqueness, and invalid-length cases.

Never make only the generator change. The schema, both command surfaces, and tests must keep the same 40-character contract.

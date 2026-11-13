import test from "node:test";
import assert from "node:assert/strict";
import {
  createIssueHash, isIssueHash, sanitizeIssueDetails, serializeIssueError,
  serializeIssueLogRecord, type IssueLogRecord,
} from "../helpers/runtime/issue-logs.js";

test("issue references keep the exact 40-character SHA-512-derived format and remain unique", () => {
  const first = createIssueHash("interaction-1", "user-1", "guild-1");
  const second = createIssueHash("interaction-1", "user-1", "guild-1");
  const otherUser = createIssueHash("interaction-1", "user-2", "guild-1");
  const otherGuild = createIssueHash("interaction-1", "user-1", "guild-2");
  assert.equal(first.length, 40); assert.match(first, /^[a-f0-9]{40}$/);
  assert.notEqual(first, second); assert.notEqual(first, otherUser); assert.notEqual(first, otherGuild);
  assert.equal(isIssueHash(first), true);
  assert.equal(isIssueHash(" " + first.toUpperCase() + " "), true);
  assert.equal(isIssueHash("a".repeat(40)), true);
  assert.equal(isIssueHash("a".repeat(128)), false);
  assert.equal(isIssueHash("a".repeat(39)), false);
  assert.equal(isIssueHash("g".repeat(40)), false);
  assert.equal(isIssueHash("not-a-hash"), false);
  const issued = new Set(Array.from({ length: 2_000 }, (_, index) =>
    createIssueHash("interaction-" + index, "user-" + (index % 17), "guild-" + (index % 5))));
  assert.equal(issued.size, 2_000);
});
test("diagnostic sanitization redacts nested secrets, bearer values and common credential formats", () => {
  const details = sanitizeIssueDetails({
    command: "discover", token: "do-not-store",
    options: [{ name: "api_key", value: "secret-value" }, { name: "query", value: "Frieren" }],
    error: { message: "Authorization: Bearer very-secret-token-value" },
    endpoint: "https://example.invalid/path?access_token=private-value&tab=1",
    leakedCredential: "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
  });
  assert.equal(details.token, "[REDACTED]");
  assert.equal((details.options as Array<Record<string, unknown>>)[0]?.value, "[REDACTED]");
  assert.equal((details.options as Array<Record<string, unknown>>)[1]?.value, "Frieren");
  assert.doesNotMatch(String((details.error as Record<string, unknown>).message), /very-secret/);
  assert.doesNotMatch(String(details.endpoint), /private-value/);
  assert.doesNotMatch(String(details.leakedCredential), /ghp_/);
});
test("diagnostic sanitization bounds circular, deeply nested and oversized values", () => {
  const circular: Record<string, unknown> = { label: "root" }; circular.self = circular;
  let nested: Record<string, unknown> = {}; const root = nested;
  for (let depth = 0; depth < 12; depth += 1) { const next: Record<string, unknown> = {}; nested.next = next; nested = next; }
  nested.value = "too deep";
  const details = sanitizeIssueDetails({ circular, nested: root, oversized: "x".repeat(60_000) });
  assert.equal((details.circular as Record<string, unknown>).self, "[Circular reference]");
  assert.match(JSON.stringify(details.nested), /Maximum diagnostic depth reached/);
  assert.ok(JSON.stringify(details).length < 55_000);
});
test("error serialization retains codes and causes before sanitizing credential values", () => {
  const root = new Error("Outer failure");
  Object.assign(root, { code: 50013, status: 403, cause: new Error("Authorization: Bearer hidden-value") });
  const serialized = serializeIssueError(root);
  assert.equal(serialized.name, "Error"); assert.equal(serialized.code, 50013); assert.equal(serialized.status, 403);
  const sanitized = sanitizeIssueDetails({ error: serialized });
  assert.doesNotMatch(JSON.stringify(sanitized), /hidden-value/);
});
test("/log JSON export contains the exact reference and sanitized full record context", () => {
  const record = {
    issue_hash: "a".repeat(40), guild_id: "12345678901234567", user_id: "22345678901234567",
    username: "Member", interaction_id: "32345678901234567", channel_id: "42345678901234567",
    command_name: "/discover", details: { error: { name: "TypeError", message: "bad response" }, token: "private", messageId: "52345678901234567" },
    created_at: new Date("2026-11-11T00:00:00.000Z"),
  } as IssueLogRecord;
  const exported = JSON.parse(serializeIssueLogRecord(record)) as Record<string, unknown>;
  assert.equal(exported.issueReference, record.issue_hash); assert.equal(exported.command, "/discover");
  assert.equal((exported.details as Record<string, unknown>).token, "[REDACTED]");
  assert.equal((exported.details as Record<string, unknown>).messageId, "52345678901234567");
});

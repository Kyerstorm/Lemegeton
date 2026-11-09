import test from "node:test";
import assert from "node:assert/strict";
import { createIssueHash, isIssueHash, sanitizeIssueDetails } from "../helpers/runtime/issue-logs.js";

test("new issue references use 128-character SHA-512 hex and remain unique", () => {
  const first = createIssueHash("interaction-1", "user-1");
  const second = createIssueHash("interaction-1", "user-1");
  const otherUser = createIssueHash("interaction-1", "user-2");
  assert.equal(first.length, 128);
  assert.match(first, /^[a-f0-9]{128}$/);
  assert.notEqual(first, second);
  assert.notEqual(first, otherUser);
  assert.equal(isIssueHash(first), true);
  assert.equal(isIssueHash(" " + first.toUpperCase() + " "), true);
  assert.equal(isIssueHash("a5f322fe4eaf90a58c92291f68dee87d2c3c648f"), true); // Legacy SHA-1 references remain readable.
  assert.equal(isIssueHash("a".repeat(128)), true);
  assert.equal(isIssueHash("a".repeat(39)), false);
  assert.equal(isIssueHash("g".repeat(40)), false);
  assert.equal(isIssueHash("not-a-hash"), false);

  const issued = new Set(Array.from({ length: 2_000 }, (_, index) => createIssueHash("interaction-" + index, "user-" + (index % 17))));
  assert.equal(issued.size, 2_000);
});

test("diagnostic details redact secrets recursively and in stack text", () => {
  const details = sanitizeIssueDetails({
    command: "discover",
    token: "do-not-store",
    options: [{ name: "api_key", value: "secret-value" }, { name: "query", value: "Frieren" }],
    error: { message: "Authorization: Bearer very-secret-token-value" },
  });
  assert.equal(details.token, "[REDACTED]");
  assert.equal((details.options as Array<Record<string, unknown>>)[0]?.value, "[REDACTED]");
  assert.equal((details.options as Array<Record<string, unknown>>)[1]?.value, "Frieren");
  assert.doesNotMatch(String((details.error as Record<string, unknown>).message), /very-secret/);
});

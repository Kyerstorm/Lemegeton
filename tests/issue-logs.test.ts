import test from "node:test";
import assert from "node:assert/strict";
import { createIssueHash, isIssueHash, sanitizeIssueDetails } from "../helpers/issue-logs.js";

test("issue references are unique 128-character SHA-512 strings", () => {
  const first = createIssueHash("interaction-1");
  const second = createIssueHash("interaction-1");
  assert.equal(first.length, 128);
  assert.match(first, /^[a-f0-9]{128}$/);
  assert.notEqual(first, second);
  assert.equal(isIssueHash(first), true);
  assert.equal(isIssueHash("not-a-hash"), false);
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

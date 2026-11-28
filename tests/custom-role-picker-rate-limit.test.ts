import test from "node:test";
import assert from "node:assert/strict";
import { MAX_RATE_LIMIT_KEYS, rateLimitCount, recordRateLimit } from "../helpers/custom-roles/picker-rate-limit.js";

test("rate-limit identity maps enforce a hard capacity", () => {
  const buckets = new Map<string, number[]>();
  for (let index = 0; index < MAX_RATE_LIMIT_KEYS; index += 1) {
    assert.equal(recordRateLimit(buckets, "source-" + index, 60_000, 100), true);
  }
  assert.equal(buckets.size, MAX_RATE_LIMIT_KEYS);
  assert.equal(recordRateLimit(buckets, "new-source", 60_000, 100), false);
  assert.equal(buckets.size, MAX_RATE_LIMIT_KEYS);
  assert.equal(rateLimitCount(buckets, "source-0", 60_000, 100), 1);
});

test("expired identities are pruned before a new key is rejected", () => {
  const buckets = new Map<string, number[]>();
  for (let index = 0; index < MAX_RATE_LIMIT_KEYS; index += 1) {
    assert.equal(recordRateLimit(buckets, "source-" + index, 1_000, 100), true);
  }
  assert.equal(recordRateLimit(buckets, "new-source", 1_000, 10_101), true);
  assert.equal(buckets.size, 1);
  assert.equal(rateLimitCount(buckets, "source-0", 1_000, 10_101), 0);
});

test("an existing identity continues to use its bounded rolling window at capacity", () => {
  const buckets = new Map<string, number[]>();
  for (let index = 0; index < MAX_RATE_LIMIT_KEYS; index += 1) {
    assert.equal(recordRateLimit(buckets, "source-" + index, 1_000, 100), true);
  }
  assert.equal(recordRateLimit(buckets, "source-0", 1_000, 101), true);
  assert.equal(rateLimitCount(buckets, "source-0", 1_000, 101), 2);
  assert.equal(buckets.size, MAX_RATE_LIMIT_KEYS);
});

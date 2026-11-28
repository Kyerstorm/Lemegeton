import test from "node:test";
import assert from "node:assert/strict";
import { resolveDeliveryRetry } from "../helpers/community/delivery-retries.js";

test("delivery retry delay increases from the configured base", () => {
  assert.deepEqual(resolveDeliveryRetry(0, 1), { attempts: 1, status: "pending", delayMinutes: 1 });
  assert.deepEqual(resolveDeliveryRetry(3, 5), { attempts: 4, status: "pending", delayMinutes: 20 });
});

test("delivery retries become terminal on the eighth failed attempt", () => {
  assert.deepEqual(resolveDeliveryRetry(6, 1), { attempts: 7, status: "pending", delayMinutes: 7 });
  assert.deepEqual(resolveDeliveryRetry(7, 1), { attempts: 8, status: "failed", delayMinutes: 8 });
});

test("delivery retry delay is capped and invalid policy values are rejected", () => {
  assert.deepEqual(resolveDeliveryRetry(19, 5), { attempts: 20, status: "failed", delayMinutes: 50 });
  assert.throws(() => resolveDeliveryRetry(-1, 1), /non-negative/);
  assert.throws(() => resolveDeliveryRetry(0, 0), /positive integer/);
  assert.throws(() => resolveDeliveryRetry(0, 1, 0), /positive safe integer/);
});

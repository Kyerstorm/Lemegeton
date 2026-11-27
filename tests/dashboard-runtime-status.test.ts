import assert from "node:assert/strict";
import test from "node:test";
import {
  gatewayStatusDescription,
  gatewayStatusLabel,
} from "../web/frontend/src/Components/Features/Overview/format.js";

test("gateway status labels distinguish every reported health state", () => {
  assert.equal(gatewayStatusLabel("online", true), "Connected");
  assert.equal(gatewayStatusLabel("degraded", true), "Degraded");
  assert.equal(gatewayStatusLabel("offline", false), "Offline");
  assert.equal(gatewayStatusLabel("connecting", false), "Connecting");
  assert.equal(gatewayStatusLabel("unknown", false), "Unknown");
});

test("gateway labels do not infer a connected state from an incomplete payload", () => {
  assert.equal(gatewayStatusLabel(undefined, false), "Not ready");
  assert.equal(gatewayStatusLabel("online", false), "Not ready");
  assert.equal(gatewayStatusLabel("custom-state", true), "Connected");
});

test("gateway descriptions preserve the operational meaning of each state", () => {
  assert.equal(
    gatewayStatusDescription("offline").includes("disconnected"),
    true,
  );
  assert.equal(
    gatewayStatusDescription("connecting").includes("has not reached"),
    true,
  );
  assert.equal(
    gatewayStatusDescription("degraded").includes("degraded"),
    true,
  );
  assert.equal(
    gatewayStatusDescription("unknown", "Bridge unavailable"),
    "Bridge unavailable",
  );
});

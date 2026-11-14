import test from "node:test";
import assert from "node:assert/strict";
import { fetchProviderResponse } from "../helpers/integration/provider-http.js";

test("provider HTTP retries bounded transient responses then returns success", async () => {
  let calls = 0;
  const waits: number[] = [];
  const response = await fetchProviderResponse(async () => {
    calls += 1;
    return calls === 1 ? new Response("busy", { status: 503 }) : new Response("ok", { status: 200 });
  }, "https://provider.example/items", {}, { maxAttempts: 2, sleep: async ms => { waits.push(ms); } });
  assert.equal(response.status, 200);
  assert.equal(calls, 2);
  assert.deepEqual(waits, [200]);
});

test("provider HTTP honors Retry-After and does not retry beyond its bounded wait", async () => {
  let calls = 0;
  const waits: number[] = [];
  const response = await fetchProviderResponse(async () => {
    calls += 1;
    return new Response("rate limited", { status: 429, headers: { "Retry-After": "2" } });
  }, "https://provider.example/items", {}, { sleep: async ms => { waits.push(ms); } });
  assert.equal(response.status, 429);
  assert.equal(calls, 2);
  assert.deepEqual(waits, [2_000]);

  calls = 0;
  const delayed = await fetchProviderResponse(async () => {
    calls += 1;
    return new Response("rate limited", { status: 429, headers: { "Retry-After": "60" } });
  }, "https://provider.example/items", {}, { sleep: async ms => { waits.push(ms); } });
  assert.equal(delayed.status, 429);
  assert.equal(calls, 1);
});

test("provider HTTP does not retry non-idempotent POST requests unless explicitly enabled", async () => {
  let calls = 0;
  const fetcher = async () => { calls += 1; return new Response("unavailable", { status: 503 }); };
  await fetchProviderResponse(fetcher, "https://provider.example/query", { method: "POST" }, { sleep: async () => undefined });
  assert.equal(calls, 1);
  await fetchProviderResponse(fetcher, "https://provider.example/query", { method: "POST" }, { retryPost: true, maxAttempts: 2, sleep: async () => undefined });
  assert.equal(calls, 3);
});

test("provider HTTP exposes network and timeout errors without retrying", async () => {
  let calls = 0;
  await assert.rejects(fetchProviderResponse(async () => {
    calls += 1;
    throw new Error("request timed out");
  }, "https://provider.example/items", {}, { sleep: async () => undefined }), /timed out/);
  assert.equal(calls, 1);
});

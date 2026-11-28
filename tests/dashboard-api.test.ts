import assert from "node:assert/strict";
import test from "node:test";
import {
  api,
  DashboardApiError,
} from "../web/frontend/src/Lib/api.ts";

const originalFetch = globalThis.fetch;
const originalWindow = Reflect.get(globalThis, "window");

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow === undefined) {
    Reflect.deleteProperty(globalThis, "window");
  } else {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: originalWindow,
    });
  }
});

test("dashboard GET requests use same-origin credentials without adding CSRF headers", async () => {
  let request: RequestInit | undefined;
  globalThis.fetch = async (_input, init) => {
    request = init;
    return new Response(JSON.stringify({ ready: true }), { status: 200 });
  };

  const result = await api<{ ready: boolean }>("/api/bootstrap");
  const headers = new Headers(request?.headers);

  assert.deepEqual(result, { ready: true });
  assert.equal(request?.method, "GET");
  assert.equal(request?.credentials, "same-origin");
  assert.equal(request?.cache, "no-store");
  assert.equal(headers.has("X-CSRF-Token"), false);
  assert.equal(headers.has("Content-Type"), false);
});

test("dashboard write requests attach JSON and the supplied CSRF token", async () => {
  let request: RequestInit | undefined;
  globalThis.fetch = async (_input, init) => {
    request = init;
    return new Response(JSON.stringify({ saved: true }), { status: 200 });
  };

  const result = await api<{ saved: boolean }>("/api/guilds/123/commands", "csrf-token", {
    method: "PUT",
    body: JSON.stringify({ revision: "r1" }),
  });
  const headers = new Headers(request?.headers);

  assert.deepEqual(result, { saved: true });
  assert.equal(request?.method, "PUT");
  assert.equal(headers.get("Content-Type"), "application/json");
  assert.equal(headers.get("X-CSRF-Token"), "csrf-token");
});

test("expired sessions redirect to login and retain the 401 status", async () => {
  let redirectedTo = "";
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { assign: (url: string) => { redirectedTo = url; } } },
  });
  globalThis.fetch = async () => new Response("{}", { status: 401 });

  await assert.rejects(
    api("/api/bootstrap"),
    (error: unknown) => error instanceof DashboardApiError && error.status === 401,
  );
  assert.equal(redirectedTo, "/login");
});

test("403 responses retain a server string but never stringify malformed error payloads", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { detail: "private" } }), { status: 403 });

  await assert.rejects(
    api("/api/guilds/123/overview"),
    (error: unknown) => error instanceof DashboardApiError
      && error.status === 403
      && error.message.includes("not authorized")
      && !error.message.includes("[object Object]"),
  );

  globalThis.fetch = async () => new Response(JSON.stringify({ error: "Owner permission required." }), { status: 403 });
  await assert.rejects(
    api("/api/integrations"),
    (error: unknown) => error instanceof DashboardApiError
      && error.status === 403
      && error.message === "Owner permission required.",
  );
});

test("rate limit responses parse numeric Retry-After headers", async () => {
  globalThis.fetch = async () => new Response("{}", {
    status: 429,
    headers: { "retry-after": "12" },
  });

  await assert.rejects(
    api("/api/integrations"),
    (error: unknown) => error instanceof DashboardApiError
      && error.status === 429
      && error.retryAfter === 12
      && error.message.includes("12 seconds"),
  );
});

test("rate limit responses parse HTTP-date Retry-After headers", async () => {
  const retryAt = Date.now() + 20_000;
  globalThis.fetch = async () => new Response("{}", {
    status: 429,
    headers: { "retry-after": new Date(retryAt).toUTCString() },
  });

  await assert.rejects(
    api("/api/integrations"),
    (error: unknown) => error instanceof DashboardApiError
      && error.status === 429
      && error.retryAfter !== undefined
      && error.retryAfter > 0
      && error.retryAfter <= 20,
  );
});

test("network failures are reported as retryable offline errors", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("fetch failed");
  };

  await assert.rejects(
    api("/api/bootstrap"),
    (error: unknown) => error instanceof DashboardApiError
      && error.status === 0
      && error.message.includes("offline or unreachable"),
  );
});

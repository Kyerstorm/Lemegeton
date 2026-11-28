import assert from "node:assert/strict";
import test from "node:test";
import {
  BotasaurusBlockedError,
  BotasaurusUnavailableError,
  BotasaurusWorkerError,
  configureBotasaurusBridgeForTests,
  scrapeManyWithBotasaurus,
  scrapeWithBotasaurus,
  listBotasaurusJobs,
  getBotasaurusWorkerStats,
  cancelBotasaurusJob,
  deleteBotasaurusJob,
  downloadBotasaurusJobExport,
} from "../helpers/integration/botasaurus-bridge.js";

const page = {
  url: "https://example.com/page",
  canonicalUrl: "https://example.com/page",
  title: "Example page",
  description: "Public metadata",
  fields: { heading: "Example" },
  statusCode: 200,
  engine: "obscura" as const,
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("Botasaurus bridge submits scoped jobs and returns an Obscura result", async () => {
  const calls: Array<{ url: string; method: string; authorization: string | null }> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    calls.push({
      url: url.toString(),
      method: init?.method ?? "GET",
      authorization: new Headers(init?.headers).get("authorization"),
    });
    if (url.pathname === "/v1/jobs") return response({ jobId: "job-1", status: "queued" }, 202);
    return response({ jobId: "job-1", status: "succeeded", result: page });
  };

  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "t".repeat(32),
    fetchImpl,
  });
  try {
    const result = await scrapeWithBotasaurus("https://example.com/page", {
      timeoutMs: 2000,
      cacheScope: { guildId: "guild-1", userId: "user-1" },
    });
    assert.equal(result.engine, "obscura");
    assert.equal(result.title, "Example page");
    assert.equal(calls.length, 2);
    assert.ok(calls.every(call => call.authorization === "Bearer " + "t".repeat(32)));
    assert.ok(calls[1]?.url.includes("guild_id=guild-1"));
    assert.ok(calls[1]?.url.includes("user_id=user-1"));
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("Botasaurus bridge preserves blocked challenge results", async () => {
  const fetchImpl: typeof fetch = async input => {
    const path = new URL(String(input)).pathname;
    if (path === "/v1/jobs") return response({ jobId: "job-blocked", status: "queued" }, 202);
    return response({
      jobId: "job-blocked",
      status: "failed",
      blocked: true,
      error: "Scraping stopped after Cloudflare challenge.",
    });
  };
  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "s".repeat(32),
    fetchImpl,
  });
  try {
    await assert.rejects(
      () => scrapeWithBotasaurus("https://example.com/page"),
      BotasaurusBlockedError,
    );
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("remote Botasaurus workers require HTTPS and a strong token", async () => {
  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "http://scraper.example.test:8765",
    token: "s".repeat(32),
    fetchImpl: async () => response({}),
  });
  try {
    await assert.rejects(
      () => scrapeWithBotasaurus("https://example.com/page"),
      BotasaurusUnavailableError,
    );
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("Botasaurus bridge rejects results outside the requested host", async () => {
  const fetchImpl: typeof fetch = async input => {
    const path = new URL(String(input)).pathname;
    if (path === "/v1/jobs") return response({ jobId: "job-host", status: "queued" }, 202);
    return response({
      jobId: "job-host",
      status: "succeeded",
      result: { ...page, url: "https://other.example/page" },
    });
  };
  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "v".repeat(32),
    fetchImpl,
  });
  try {
    await assert.rejects(
      () => scrapeWithBotasaurus("https://example.com/page"),
      BotasaurusWorkerError,
    );
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("Botasaurus task API batches scoped jobs and preserves per-item rejections", async () => {
  const submitted: Array<{ url: string; method: string; body: string | null }> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    submitted.push({
      url: url.toString(),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : null,
    });
    if (url.pathname === "/v1/jobs/batch") {
      return response({
        accepted: [
          { index: 0, jobId: "batch-0", url: "https://example.com/one", status: "queued" },
          { index: 1, jobId: "batch-1", url: "https://example.com/two", status: "queued" },
        ],
        rejected: [{ index: 2, error: "The target URL is not allowed." }],
      }, 202);
    }
    const jobId = url.pathname.split("/").at(-1);
    if (jobId === "batch-0" || jobId === "batch-1") {
      return response({ jobId, status: "succeeded", result: page });
    }
    return response({ error: "Unexpected test route." }, 404);
  };

  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "b".repeat(32),
    fetchImpl,
  });
  try {
    const results = await scrapeManyWithBotasaurus([
      "https://example.com/one",
      "https://example.com/two",
      "file:///etc/passwd",
    ], { cacheScope: { guildId: "guild-batch", userId: "user-batch" } });

    assert.equal(results.length, 3);
    assert.ok("result" in results[0]!);
    assert.ok("result" in results[1]!);
    assert.equal("error" in results[2]! ? results[2]!.error : null, "The target URL is not allowed.");
    const batchRequest = submitted.find(call => new URL(call.url).pathname === "/v1/jobs/batch");
    assert.ok(batchRequest);
    assert.equal(batchRequest.method, "POST");
    assert.deepEqual(JSON.parse(batchRequest.body!).scope, {
      guild_id: "guild-batch",
      user_id: "user-batch",
    });
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("Botasaurus task API exposes scoped listing, statistics, cancellation, deletion and exports", async () => {
  const calls: string[] = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    calls.push((init?.method ?? "GET") + " " + url.pathname + url.search);
    if (url.pathname === "/v1/jobs" && (init?.method ?? "GET") === "GET") {
      return response({
        items: [{ jobId: "job-list", status: "succeeded", createdAt: 1, updatedAt: 2, blocked: false }],
        total: 1,
        limit: 10,
        offset: 0,
      });
    }
    if (url.pathname === "/v1/jobs/stats") {
      return response({
        counts: { queued: 0, running: 0, succeeded: 1, failed: 0, cancelled: 0 },
        total: 1,
        maxWorkers: 2,
        maxQueue: 32,
      });
    }
    if (url.pathname === "/v1/jobs/job-cancel") return response({ cancelled: true });
    if (url.pathname === "/v1/jobs/job-delete/record") return response({ deleted: true });
    if (url.pathname === "/v1/jobs/job-export/export") {
      return new Response("title\nExample\n", {
        status: 200,
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": 'attachment; filename="botasaurus-job-export.csv"',
        },
      });
    }
    return response({ error: "Unexpected test route." }, 404);
  };

  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "m".repeat(32),
    fetchImpl,
  });
  try {
    const scope = { guildId: "guild-api", userId: "user-api" };
    const jobs = await listBotasaurusJobs({ cacheScope: scope, limit: 10 });
    const stats = await getBotasaurusWorkerStats(scope);
    assert.equal(jobs.total, 1);
    assert.equal(stats.counts.succeeded, 1);
    assert.equal(await cancelBotasaurusJob("job-cancel", scope), true);
    assert.equal(await deleteBotasaurusJob("job-delete", scope), true);
    const exported = await downloadBotasaurusJobExport("job-export", "csv", scope);
    assert.equal(exported.contentType, "text/csv; charset=utf-8");
    assert.equal(exported.filename, "botasaurus-job-export.csv");
    assert.match(new TextDecoder().decode(exported.data), /Example/);
    assert.ok(calls.every(call => call.includes("guild_id=guild-api") && call.includes("user_id=user-api")));
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});


test("Botasaurus bridge enables Cloudflare handling by default and supports per-request opt-out", async () => {
  const submitted: Array<Record<string, unknown>> = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname === "/v1/jobs") {
      submitted.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return response({ jobId: "job-default", status: "queued" }, 202);
    }
    return response({ jobId: "job-default", status: "succeeded", result: page });
  };
  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "d".repeat(32),
    fetchImpl,
  });
  try {
    await scrapeWithBotasaurus("https://example.com/default");
    await scrapeWithBotasaurus("https://example.com/disabled", { cfBypass: false });
    assert.equal((submitted[0]?.options as Record<string, unknown>).cfBypass, true);
    assert.equal((submitted[1]?.options as Record<string, unknown>).cfBypass, false);
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

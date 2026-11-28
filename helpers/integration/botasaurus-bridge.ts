import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { isIP } from "node:net";
import { isPublicUnicastAddress } from "../security/public-address.js";

export interface BotasaurusBridgeOptions {
  timeoutMs?: number;
  selectors?: Record<string, string>;
  includeText?: boolean;
  maxTextChars?: number;
  includeStructuredData?: boolean;
  includeArticle?: boolean;
  includeLinks?: boolean;
  includeHtml?: boolean;
  cacheScope?: {
    guildId?: string;
    userId?: string;
  };
  cfBypass?: boolean;
}

export interface BotasaurusPageResult {
  url: string;
  canonicalUrl: string;
  title: string;
  description: string;
  fields: Record<string, string | string[]>;
  statusCode: number;
  engine: "obscura" | "chromium";
  image?: string | null;
  siteName?: string | null;
  author?: string | null;
  publishedAt?: string | null;
  feeds?: Array<{ title: string | null; type: string; url: string }>;
  article?: {
    title: string;
    description: string | null;
    image: string | null;
    author: string | null;
    publishedAt: string | null;
    content: string;
    readTimeSeconds: number | null;
  };
  text?: string;
  structuredData?: Record<string, unknown>[];
  links?: Array<{ text: string; url: string }>;
  html?: string;
}

type BridgeMode = "auto" | "local" | "remote" | "disabled";

interface BridgeOverrides {
  mode?: BridgeMode;
  workerUrl?: string;
  token?: string;
  pythonPath?: string;
  scriptPath?: string;
  fetchImpl?: typeof fetch;
}

interface WorkerJobResponse {
  jobId: string;
  status: string;
  result?: BotasaurusPageResult | null;
  error?: string;
  blocked?: boolean;
}

interface WorkerConnection {
  baseUrl: string;
  token: string;
  fetchImpl: typeof fetch;
}

export type BotasaurusJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface BotasaurusJobSummary {
  jobId: string;
  status: BotasaurusJobStatus;
  createdAt: number;
  updatedAt: number;
  error?: string | null;
  blocked: boolean;
}

export interface BotasaurusJobListOptions {
  cacheScope?: BotasaurusBridgeOptions["cacheScope"];
  status?: BotasaurusJobStatus;
  limit?: number;
  offset?: number;
}

export interface BotasaurusJobPage {
  items: BotasaurusJobSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface BotasaurusJobDetails extends BotasaurusJobSummary {
  result?: BotasaurusPageResult | null;
}

export interface BotasaurusWorkerStats {
  counts: Record<BotasaurusJobStatus, number>;
  total: number;
  maxWorkers: number;
  maxQueue: number;
}

export type BotasaurusManyResult =
  | { url: string; result: BotasaurusPageResult }
  | { url: string; error: string; blocked: boolean };

export interface BotasaurusExport {
  contentType: string;
  filename: string | null;
  data: Uint8Array;
}

export class BotasaurusUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BotasaurusUnavailableError";
  }
}

export class BotasaurusBlockedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BotasaurusBlockedError";
  }
}

export class BotasaurusWorkerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BotasaurusWorkerError";
  }
}

let overrides: BridgeOverrides = {};
let localWorker: { process: ChildProcess; connection: WorkerConnection } | undefined;
let localStartup: Promise<WorkerConnection> | undefined;

export function configureBotasaurusBridgeForTests(value: BridgeOverrides | null): void {
  overrides = value ?? {};
}

function env(name: string, fallback = ""): string {
  return process.env[name] ?? fallback;
}

function readMode(): BridgeMode {
  const value = overrides.mode ?? env("BOTASAURUS_MODE", "auto").toLowerCase();
  if (value === "local" || value === "remote" || value === "disabled" || value === "auto") return value;
  return "auto";
}

function isPrivateWorkerAddress(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".internal") || host.endsWith(".local")) return true;
  if (isIP(host)) return !isPublicUnicastAddress(host);
  return !host.includes(".") && host.length > 0;
}

function normalizeRemoteUrl(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new BotasaurusUnavailableError("BOTASAURUS_WORKER_URL is not a valid URL.");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password
    || parsed.search || parsed.hash || (parsed.pathname !== "/" && parsed.pathname !== "")) {
    throw new BotasaurusUnavailableError("The Botasaurus worker URL must be a root HTTP(S) endpoint without credentials or query parameters.");
  }
  if (parsed.protocol === "http:" && !isPrivateWorkerAddress(parsed.hostname)) {
    throw new BotasaurusUnavailableError("Remote Botasaurus workers must use HTTPS. Private local/container endpoints may use HTTP.");
  }
  return parsed.toString().replace(/\/+$/, "");
}

async function reservePort(): Promise<number> {
  const server = createServer();
  await new Promise<void>((resolvePromise, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject);
      resolvePromise();
    });
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    server.close();
    throw new BotasaurusUnavailableError("Could not reserve a local worker port.");
  }
  const port = address.port;
  await new Promise<void>(resolvePromise => server.close(() => resolvePromise()));
  return port;
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await response.json();
    return value && typeof value === "object" ? value as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function requestSignal(timeoutMs: number): AbortSignal {
  return AbortSignal.timeout(Math.max(1000, Math.min(timeoutMs, 65000)));
}

async function workerFetch(
  connection: WorkerConnection,
  path: string,
  init: RequestInit = {},
  timeoutMs = 5000,
): Promise<Response> {
  try {
    return await connection.fetchImpl(connection.baseUrl + path, {
      ...init,
      headers: {
        Accept: "application/json",
        Authorization: "Bearer " + connection.token,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
      signal: requestSignal(timeoutMs),
    });
  } catch (error) {
    throw new BotasaurusUnavailableError(
      "The Botasaurus worker could not be reached: " + (error instanceof Error ? error.message : String(error)),
    );
  }
}

async function waitForLocalWorker(connection: WorkerConnection, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new BotasaurusUnavailableError("The local Botasaurus worker exited during startup.");
    }
    try {
      const response = await connection.fetchImpl(connection.baseUrl + "/health", {
        method: "GET",
        signal: requestSignal(1000),
      });
      if (response.ok) return;
    } catch {
      // The local HTTP listener may need a short moment to bind.
    }
    await delay(250);
  }
  throw new BotasaurusUnavailableError("The local Botasaurus worker did not become ready.");
}

async function startLocalWorker(): Promise<WorkerConnection> {
  if (localWorker && localWorker.process.exitCode === null && localWorker.process.signalCode === null) {
    return localWorker.connection;
  }
  if (localStartup) return localStartup;

  localStartup = (async () => {
    const pythonPath = overrides.pythonPath ?? env("BOTASAURUS_PYTHON", process.platform === "win32" ? "python" : "python3");
    const scriptPath = resolve(overrides.scriptPath ?? env("BOTASAURUS_WORKER_SCRIPT", resolve(process.cwd(), "workers/botasaurus.py")));
    if (!existsSync(scriptPath)) {
      throw new BotasaurusUnavailableError("The local workers/botasaurus.py file is not present.");
    }

    const port = await reservePort();
    const token = randomBytes(32).toString("hex");
    const baseUrl = "http://127.0.0.1:" + port;
    const fetchImpl = overrides.fetchImpl ?? fetch;
    const child = spawn(pythonPath, [scriptPath, "serve"], {
      cwd: process.cwd(),
      windowsHide: true,
      stdio: "ignore",
      env: {
        ...process.env,
        BOTASAURUS_HOST: "127.0.0.1",
        BOTASAURUS_PORT: String(port),
        BOTASAURUS_WORKER_TOKEN: token,
        ...(env("BOTASAURUS_CACHE_DIR") ? {} : { BOTASAURUS_CACHE_DIR: resolve(process.cwd(), "data/botasaurus-cache") }),
      },
    });
    const connection = { baseUrl, token, fetchImpl };
    try {
      const startupError = new Promise<never>((_, reject) => child.once("error", reject));
      await Promise.race([waitForLocalWorker(connection, child), startupError]);
    } catch (error) {
      child.kill();
      throw new BotasaurusUnavailableError(
        "Could not start the local Botasaurus worker: " + (error instanceof Error ? error.message : String(error)),
      );
    }
    localWorker = { process: child, connection };
    child.once("exit", () => {
      if (localWorker?.process === child) localWorker = undefined;
    });
    return connection;
  })().finally(() => {
    localStartup = undefined;
  });
  return localStartup;
}

async function resolveWorker(): Promise<WorkerConnection> {
  const mode = readMode();
  if (mode === "disabled") throw new BotasaurusUnavailableError("The Botasaurus browser worker is disabled.");

  if (mode === "local") return startLocalWorker();

  const configuredUrl = overrides.workerUrl ?? env("BOTASAURUS_WORKER_URL");
  if (configuredUrl) {
    const token = overrides.token ?? env("BOTASAURUS_WORKER_TOKEN");
    if (token.length < 32) {
      throw new BotasaurusUnavailableError("BOTASAURUS_WORKER_TOKEN must contain at least 32 characters for remote workers.");
    }
    return {
      baseUrl: normalizeRemoteUrl(configuredUrl),
      token,
      fetchImpl: overrides.fetchImpl ?? fetch,
    };
  }
  if (mode === "remote") {
    throw new BotasaurusUnavailableError("BOTASAURUS_WORKER_URL is required in remote mode.");
  }
  return startLocalWorker();
}

function encodeScope(options: BotasaurusBridgeOptions): { guild_id: string; user_id: string } {
  const guildId = options.cacheScope?.guildId || "global";
  const userId = options.cacheScope?.userId || "system";
  if (guildId.length > 64 || userId.length > 64) {
    throw new BotasaurusWorkerError("The scraper scope is invalid.");
  }
  return { guild_id: guildId, user_id: userId };
}

function encodeOptions(options: BotasaurusBridgeOptions): Record<string, unknown> {
  return {
    timeoutMs: options.timeoutMs,
    selectors: options.selectors ?? {},
    includeText: options.includeText !== false,
    maxTextChars: options.maxTextChars,
    includeStructuredData: options.includeStructuredData === true,
    includeArticle: options.includeArticle === true,
    includeLinks: options.includeLinks === true,
    includeHtml: options.includeHtml === true,
    cfBypass: options.cfBypass === true,
  };
}

function scopeQuery(scope: { guild_id: string; user_id: string }): string {
  const query = new URLSearchParams({
    guild_id: scope.guild_id,
    user_id: scope.user_id,
  });
  return "?" + query.toString();
}

function workerError(payload: Record<string, unknown>, fallback: string): BotasaurusWorkerError {
  return new BotasaurusWorkerError(typeof payload.error === "string" ? payload.error : fallback);
}

async function waitForBotasaurusJob(
  connection: WorkerConnection,
  jobId: string,
  url: string,
  scope: { guild_id: string; user_id: string },
  timeoutMs: number,
): Promise<BotasaurusPageResult> {
  const query = scopeQuery(scope);
  const deadline = Date.now() + timeoutMs + 12000;
  let pollDelay = 250;
  try {
    while (Date.now() < deadline) {
      const response = await workerFetch(
        connection,
        "/v1/jobs/" + encodeURIComponent(jobId) + query,
        {},
        5000,
      );
      const job = await readJson(response) as unknown as WorkerJobResponse;
      if (!response.ok) throw workerError(job as Record<string, unknown>, "The Botasaurus job could not be retrieved.");
      if (job.status === "succeeded") return validateWorkerResult(job.result, url);
      if (job.status === "failed") {
        if (job.blocked) throw new BotasaurusBlockedError(job.error || "The target site presented an access challenge.");
        throw new BotasaurusWorkerError(job.error || "The Botasaurus browser job failed.");
      }
      if (job.status === "cancelled") throw new BotasaurusWorkerError("The Botasaurus browser job was cancelled.");
      await delay(pollDelay);
      pollDelay = Math.min(1000, pollDelay + 150);
    }
    throw new BotasaurusWorkerError("The Botasaurus browser job exceeded its time limit.");
  } catch (error) {
    await workerFetch(
      connection,
      "/v1/jobs/" + encodeURIComponent(jobId) + query,
      { method: "DELETE" },
      3000,
    ).catch(() => undefined);
    throw error;
  }
}

function validateWorkerResult(value: unknown, requestedUrl: string): BotasaurusPageResult {
  if (!value || typeof value !== "object") {
    throw new BotasaurusWorkerError("The Botasaurus worker returned an invalid result.");
  }
  const result = value as Partial<BotasaurusPageResult>;
  const required = ["url", "canonicalUrl", "title", "description", "fields", "statusCode", "engine"] as const;
  if (required.some(key => result[key] === undefined || result[key] === null)) {
    throw new BotasaurusWorkerError("The Botasaurus worker returned incomplete page metadata.");
  }
  let requested: URL;
  let received: URL;
  try {
    requested = new URL(requestedUrl);
    received = new URL(result.url as string);
  } catch {
    throw new BotasaurusWorkerError("The Botasaurus worker returned an invalid page URL.");
  }
  if (requested.hostname.toLowerCase() !== received.hostname.toLowerCase()
    || !["http:", "https:"].includes(received.protocol)
    || !["", "80", "443"].includes(received.port)
    || received.username || received.password) {
    throw new BotasaurusWorkerError("The Botasaurus worker returned a page outside the validated host.");
  }
  if (typeof result.canonicalUrl !== "string"
    || typeof result.title !== "string" || typeof result.description !== "string"
    || !result.fields || typeof result.fields !== "object" || Array.isArray(result.fields)
    || !Number.isInteger(result.statusCode)
    || (result.links !== undefined && (!Array.isArray(result.links)
      || result.links.some(link => !link || typeof link.text !== "string" || typeof link.url !== "string")))
    || (result.feeds !== undefined && (!Array.isArray(result.feeds)
      || result.feeds.some(feed => !feed || typeof feed.url !== "string" || typeof feed.type !== "string")))
  ) {
    throw new BotasaurusWorkerError("The Botasaurus worker returned malformed page metadata.");
  }
  const sameHostUrl = (candidate: unknown): boolean => {
    if (typeof candidate !== "string") return true;
    try {
      const parsed = new URL(candidate);
      return ["http:", "https:"].includes(parsed.protocol)
        && ["", "80", "443"].includes(parsed.port)
        && parsed.hostname.toLowerCase() === requested.hostname.toLowerCase()
        && !parsed.username && !parsed.password;
    } catch {
      return false;
    }
  };
  if (!sameHostUrl(result.canonicalUrl) || !sameHostUrl(result.image)
    || (result.links ?? []).some(link => !sameHostUrl(link.url))
    || (result.feeds ?? []).some(feed => !sameHostUrl(feed.url))) {
    throw new BotasaurusWorkerError("The Botasaurus worker returned a URL outside the validated host.");
  }
  if (result.engine !== "obscura" && result.engine !== "chromium") {
    throw new BotasaurusWorkerError("The Botasaurus worker returned an unknown browser engine.");
  }
  return result as BotasaurusPageResult;
}

export async function scrapeWithBotasaurus(
  url: string,
  options: BotasaurusBridgeOptions = {},
): Promise<BotasaurusPageResult> {
  const connection = await resolveWorker();
  const scope = encodeScope(options);
  const timeoutMs = Math.max(1000, Math.min(options.timeoutMs ?? 20000, 60000));
  const submit = await workerFetch(connection, "/v1/jobs", {
    method: "POST",
    body: JSON.stringify({ url, options: encodeOptions(options), scope }),
  }, 5000);
  const submitted = await readJson(submit);
  if (submit.status === 429) throw new BotasaurusWorkerError("The Botasaurus browser queue is full.");
  if (!submit.ok || typeof submitted.jobId !== "string") {
    throw workerError(submitted, "The Botasaurus worker rejected the scrape job.");
  }
  return waitForBotasaurusJob(connection, submitted.jobId, url, scope, timeoutMs);
}

export async function scrapeManyWithBotasaurus(
  urls: string[],
  options: BotasaurusBridgeOptions = {},
): Promise<BotasaurusManyResult[]> {
  const connection = await resolveWorker();
  const scope = encodeScope(options);
  const timeoutMs = Math.max(1000, Math.min(options.timeoutMs ?? 20000, 60000));
  const results: Array<BotasaurusManyResult | undefined> = new Array(urls.length);

  for (let offset = 0; offset < urls.length; offset += 16) {
    const batch = urls.slice(offset, offset + 16);
    const response = await workerFetch(connection, "/v1/jobs/batch", {
      method: "POST",
      body: JSON.stringify({
        scope,
        jobs: batch.map(url => ({ url, options: encodeOptions(options) })),
      }),
    }, 5000);
    const submission = await readJson(response);
    if (!response.ok || !Array.isArray(submission.accepted) || !Array.isArray(submission.rejected)) {
      const error = workerError(submission, "The Botasaurus worker rejected the batch.");
      for (let index = 0; index < batch.length; index += 1) {
        results[offset + index] = {
          url: batch[index]!,
          error: error.message,
          blocked: false,
        };
      }
      continue;
    }

    for (const rejected of submission.rejected as Array<{ index: number; error?: string }>) {
      const index = Number(rejected.index);
      if (Number.isInteger(index) && index >= 0 && index < batch.length) {
        results[offset + index] = {
          url: batch[index]!,
          error: typeof rejected.error === "string" ? rejected.error : "The Botasaurus worker rejected this job.",
          blocked: false,
        };
      }
    }

    const accepted = submission.accepted as Array<{ index: number; jobId: string }>;
    await Promise.all(accepted.map(async item => {
      if (!Number.isInteger(item.index) || item.index < 0 || item.index >= batch.length || typeof item.jobId !== "string") return;
      const url = batch[item.index]!;
      try {
        results[offset + item.index] = {
          url,
          result: await waitForBotasaurusJob(connection, item.jobId, url, scope, timeoutMs),
        };
      } catch (error) {
        results[offset + item.index] = {
          url,
          error: error instanceof Error ? error.message : String(error),
          blocked: error instanceof BotasaurusBlockedError,
        };
      }
    }));
  }

  return results.map((item, index) => item ?? {
    url: urls[index]!,
    error: "The Botasaurus worker did not return a result for this job.",
    blocked: false,
  });
}

export async function listBotasaurusJobs(options: BotasaurusJobListOptions = {}): Promise<BotasaurusJobPage> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope: options.cacheScope });
  const query = new URLSearchParams({
    ...scope,
    limit: String(Math.max(1, Math.min(Math.floor(options.limit ?? 50), 100))),
    offset: String(Math.max(0, Math.min(Math.floor(options.offset ?? 0), 100000))),
  });
  if (options.status) query.set("status", options.status);
  const response = await workerFetch(connection, "/v1/jobs?" + query.toString());
  const payload = await readJson(response);
  if (!response.ok || !Array.isArray(payload.items) || !Number.isInteger(payload.total)) {
    throw workerError(payload, "The Botasaurus worker could not list jobs.");
  }
  return payload as unknown as BotasaurusJobPage;
}

export async function getBotasaurusJob(
  jobId: string,
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<BotasaurusJobDetails> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(
    connection,
    "/v1/jobs/" + encodeURIComponent(jobId) + scopeQuery(scope),
  );
  const payload = await readJson(response);
  if (!response.ok || typeof payload.jobId !== "string" || typeof payload.status !== "string") {
    throw workerError(payload, "The Botasaurus job could not be retrieved.");
  }
  return payload as unknown as BotasaurusJobDetails;
}

export async function getBotasaurusJobResult(
  jobId: string,
  requestedUrl: string,
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<BotasaurusPageResult> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(
    connection,
    "/v1/jobs/" + encodeURIComponent(jobId) + "/result" + scopeQuery(scope),
  );
  const payload = await readJson(response);
  if (!response.ok) throw workerError(payload, "The Botasaurus job result is unavailable.");
  return validateWorkerResult(payload, requestedUrl);
}

export async function getBotasaurusWorkerStats(
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<BotasaurusWorkerStats> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(connection, "/v1/jobs/stats" + scopeQuery(scope));
  const payload = await readJson(response);
  if (!response.ok || !payload.counts || typeof payload.counts !== "object") {
    throw workerError(payload, "The Botasaurus worker statistics are unavailable.");
  }
  return payload as unknown as BotasaurusWorkerStats;
}

export async function cancelBotasaurusJob(
  jobId: string,
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<boolean> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(
    connection,
    "/v1/jobs/" + encodeURIComponent(jobId) + scopeQuery(scope),
    { method: "DELETE" },
  );
  if (response.status === 404) return false;
  const payload = await readJson(response);
  if (!response.ok || payload.cancelled !== true) throw workerError(payload, "The Botasaurus job could not be cancelled.");
  return true;
}

export async function cancelBotasaurusJobs(
  jobIds: string[],
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<{ cancelled: string[]; notFound: string[] }> {
  if (jobIds.length < 1 || jobIds.length > 100) {
    throw new BotasaurusWorkerError("Bulk cancellation requires between 1 and 100 job identifiers.");
  }
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(connection, "/v1/jobs/cancel", {
    method: "POST",
    body: JSON.stringify({ scope, jobIds: [...new Set(jobIds)] }),
  });
  const payload = await readJson(response);
  if (!response.ok || !Array.isArray(payload.cancelled) || !Array.isArray(payload.notFound)) {
    throw workerError(payload, "The Botasaurus jobs could not be cancelled.");
  }
  return {
    cancelled: payload.cancelled as string[],
    notFound: payload.notFound as string[],
  };
}

export async function deleteBotasaurusJobs(
  jobIds: string[],
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<{ deleted: string[]; skipped: string[] }> {
  if (jobIds.length < 1 || jobIds.length > 100) {
    throw new BotasaurusWorkerError("Bulk deletion requires between 1 and 100 job identifiers.");
  }
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(connection, "/v1/jobs/delete", {
    method: "POST",
    body: JSON.stringify({ scope, jobIds: [...new Set(jobIds)] }),
  });
  const payload = await readJson(response);
  if (!response.ok || !Array.isArray(payload.deleted) || !Array.isArray(payload.skipped)) {
    throw workerError(payload, "The Botasaurus jobs could not be deleted.");
  }
  return {
    deleted: payload.deleted as string[],
    skipped: payload.skipped as string[],
  };
}

export async function deleteBotasaurusJob(
  jobId: string,
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<boolean> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const response = await workerFetch(
    connection,
    "/v1/jobs/" + encodeURIComponent(jobId) + "/record" + scopeQuery(scope),
    { method: "DELETE" },
  );
  if (response.status === 404 || response.status === 409) return false;
  const payload = await readJson(response);
  if (!response.ok || payload.deleted !== true) throw workerError(payload, "The Botasaurus job could not be deleted.");
  return true;
}

export async function downloadBotasaurusJobExport(
  jobId: string,
  format: "json" | "csv" | "excel" = "json",
  cacheScope?: BotasaurusBridgeOptions["cacheScope"],
): Promise<BotasaurusExport> {
  const connection = await resolveWorker();
  const scope = encodeScope({ cacheScope });
  const query = scopeQuery(scope) + "&format=" + encodeURIComponent(format);
  const response = await workerFetch(
    connection,
    "/v1/jobs/" + encodeURIComponent(jobId) + "/export" + query,
  );
  if (!response.ok) {
    const payload = await readJson(response);
    throw workerError(payload, "The Botasaurus job export could not be downloaded.");
  }
  const disposition = response.headers.get("content-disposition");
  const filename = disposition?.match(/filename="([^"]+)"/i)?.[1] ?? null;
  return {
    contentType: response.headers.get("content-type") ?? "application/octet-stream",
    filename,
    data: new Uint8Array(await response.arrayBuffer()),
  };
}

export async function stopBotasaurusWorker(): Promise<void> {
  const worker = localWorker;
  localWorker = undefined;
  if (!worker || worker.process.exitCode !== null || worker.process.signalCode !== null) return;
  await new Promise<void>(resolvePromise => {
    const timer = setTimeout(() => {
      worker.process.kill("SIGKILL");
      resolvePromise();
    }, 3000);
    worker.process.once("exit", () => {
      clearTimeout(timer);
      resolvePromise();
    });
    worker.process.kill("SIGTERM");
  });
}

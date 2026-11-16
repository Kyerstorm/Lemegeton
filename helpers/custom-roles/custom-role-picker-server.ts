import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { isIP } from "node:net";
import type { Client } from "discord.js";
import type { BotConfig } from "../runtime/config.js";
import { isGuildRetentionConfigured } from "../runtime/guild-retention.js";
import { logger } from "../runtime/logger.js";
import {
  allowPickerCall,
  clearPickerLinks,
  createPickerLink,
  lookupPickerLink,
  pickerLinkExpiry,
  touchPickerLink,
  type PickerLink,
} from "./custom-role-picker-tokens.js";
import {
  buildPickerState,
  pickerImageContentType,
  pickerIconSource,
  pickerPalette,
  pickerRemoveIcon,
  pickerSetColor,
  pickerSetEmoji,
  pickerSetImage,
  pickerSetName,
  resolvePickerContext,
} from "./custom-role-picker-service.js";
import { processCustomRoleIconImage } from "./custom-role-images.js";
import { fetchExternalImage } from "./custom-role-picker-image-fetch.js";
export { isPublicImageAddress } from "./custom-role-picker-image-fetch.js";

const BASE = "/custom-roles";
const MAX_JSON_BODY = 16 * 1024;
const MULTIPART_OVERHEAD = 64 * 1024;
const FETCH_LIMIT = 6;
const FETCH_WINDOW_MS = 60_000;
const FAILED_LIMIT = 30;
const FAILED_WINDOW_MS = 600_000;
const MAX_TRACKED = 10_000;
const IMAGE_CONCURRENCY = 3;
const EXPIRED_MESSAGE = "This link expired. Run /custom-role and press Color picker to make a new one.";
const BUSY_MESSAGE = "I'm handling a lot of images right now. Try again in a few seconds.";
const STATIC_TYPES: Record<string, string> = {
  "picker.css": "text/css; charset=utf-8",
  "picker.js": "application/javascript; charset=utf-8",
  "theme.css": "text/css; charset=utf-8",
  "favicon.svg": "image/svg+xml",
};

const failedAttempts = new Map<string, number[]>();
const linkFetches = new Map<string, number[]>();
let imageInFlight = 0;
let server: Server | null = null;

function expiryHeaders(link?: PickerLink): Record<string, string> {
  if (!link) return {};
  const expiry = pickerLinkExpiry(link);
  return {
    "X-Picker-Expires-At": String(expiry.expires_at),
    "X-Picker-Max-Expires-At": String(expiry.max_expires_at),
  };
}

function secureHeaders(response: ServerResponse): void {
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("X-Frame-Options", "DENY");
  response.setHeader("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  response.setHeader(
    "Content-Security-Policy",
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  );
}

function jsonResponse(
  response: ServerResponse,
  status: number,
  body: Record<string, unknown>,
  link?: PickerLink,
): void {
  const payload = link ? { ...body, ...pickerLinkExpiry(link) } : body;
  const bytes = Buffer.from(JSON.stringify(payload));
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(bytes.length),
    ...expiryHeaders(link),
  });
  response.end(bytes);
}

function cleanMessage(message: string): string {
  return message
    .replace(/<t:\d+(?::[tTdDfFR])?>/g, "a short time")
    .replace(/<@&\d+>/g, "a role")
    .replace(/<@!?\d+>/g, "a member")
    .replace(/<#\d+>/g, "a channel")
    .replace(/\*\*/g, "")
    .replaceAll(String.fromCharCode(96), "");
}

function errorResponse(
  response: ServerResponse,
  status: number,
  code: string,
  message: string,
  link?: PickerLink,
): void {
  jsonResponse(response, status, { ok: false, error: code, message: cleanMessage(message) }, link);
}

function header(request: IncomingMessage, name: string): string {
  const value = request.headers[name.toLowerCase()];
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

function originAllowed(request: IncomingMessage, config: BotConfig): boolean {
  const origin = header(request, "origin").trim().replace(/\/+$/, "").toLowerCase();
  return Boolean(origin) && origin === new URL(config.customRolesPublicUrl).origin.toLowerCase();
}

function rateCount(buckets: Map<string, number[]>, key: string, windowMs: number, now: number): number {
  const cutoff = now - windowMs;
  if (buckets.size > MAX_TRACKED) {
    for (const [candidate, entries] of buckets) {
      if (!entries.length || entries[entries.length - 1]! <= cutoff) buckets.delete(candidate);
    }
  }
  const entries = buckets.get(key);
  if (!entries) return 0;
  while (entries.length && entries[0]! <= cutoff) entries.shift();
  if (!entries.length) {
    buckets.delete(key);
    return 0;
  }
  return entries.length;
}

function recordRate(buckets: Map<string, number[]>, key: string, windowMs: number, now: number): void {
  rateCount(buckets, key, windowMs, now);
  const entries = buckets.get(key) ?? [];
  entries.push(now);
  buckets.set(key, entries);
}

function clientAddress(request: IncomingMessage, config: BotConfig): string {
  if (config.customRolesTrustProxy) {
    const raw = header(request, "x-forwarded-for");
    const values = raw.split(",").map(value => value.trim()).filter(Boolean);
    if (values.length) return values[values.length - 1]!;
  }
  return request.socket.remoteAddress ?? "unknown";
}

async function collectBody(request: IncomingMessage, limit: number): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of request) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    total += bytes.length;
    if (total > limit) throw new Error("too_big");
    chunks.push(bytes);
  }
  return Buffer.concat(chunks, total);
}

async function jsonBody(request: IncomingMessage): Promise<Record<string, unknown>> {
  if (!header(request, "content-type").toLowerCase().startsWith("application/json")) throw new Error("json_only");
  const raw = await collectBody(request, MAX_JSON_BODY);
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new Error("bad_json");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("bad_json");
  return value as Record<string, unknown>;
}

function parseMultipart(contentType: string, body: Buffer): { image: Buffer | null; crop: string | null } {
  const match = /(?:^|;)\s*boundary=(?:"([^"]+)"|([^;\s]+))/i.exec(contentType);
  const boundary = match?.[1] ?? match?.[2];
  if (!boundary || boundary.length > 200) throw new Error("bad_upload");
  const delimiter = Buffer.from("--" + boundary);
  let cursor = body.indexOf(delimiter);
  if (cursor < 0) throw new Error("bad_upload");
  const fields: { image: Buffer | null; crop: string | null } = { image: null, crop: null };
  let partCount = 0;

  while (cursor >= 0) {
    cursor += delimiter.length;
    if (body.subarray(cursor, cursor + 2).toString() === "--") break;
    if (body.subarray(cursor, cursor + 2).toString() === "\r\n") cursor += 2;
    const headerEnd = body.indexOf(Buffer.from("\r\n\r\n"), cursor);
    if (headerEnd < 0) throw new Error("bad_upload");
    const disposition = body.subarray(cursor, headerEnd).toString("latin1");
    const name = /content-disposition:\s*form-data;[^\r\n]*?name="([^"]+)"/i.exec(disposition)?.[1];
    const dataStart = headerEnd + 4;
    const next = body.indexOf(Buffer.concat([Buffer.from("\r\n"), delimiter]), dataStart);
    if (next < 0) throw new Error("bad_upload");
    const data = body.subarray(dataStart, next);
    partCount += 1;
    if (partCount > 2) throw new Error("bad_upload");
    if (name === "image" && fields.image === null) fields.image = data;
    else if (name === "crop" && fields.crop === null) fields.crop = data.toString("utf8");
    else throw new Error("bad_upload");
    cursor = next + 2;
  }
  return fields;
}

function parseCrop(raw: string | null): { x: number; y: number; size: number } | undefined {
  if (raw === null) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("bad_crop");
  }
  if (!value || typeof value !== "object") throw new Error("bad_crop");
  const record = value as Record<string, unknown>;
  const x = record.x, y = record.y, size = record.size;
  if (![x, y, size].every(item => typeof item === "number" && Number.isSafeInteger(item))) throw new Error("bad_crop");
  return { x: x as number, y: y as number, size: size as number };
}

function tokenForRequest(url: URL, request: IncomingMessage): string {
  const forbidden = new Set(["token", "t", "access_token", "auth", "key"]);
  for (const key of url.searchParams.keys()) {
    if (forbidden.has(key.toLowerCase())) throw new Error("token_in_url");
  }
  const value = header(request, "authorization");
  return /^Bearer\s+/i.test(value) ? value.replace(/^Bearer\s+/i, "").trim() : "";
}

async function authorize(
  url: URL,
  request: IncomingMessage,
  response: ServerResponse,
  config: BotConfig,
  client: Client,
  write: boolean,
): Promise<{ link: PickerLink; context: Awaited<ReturnType<typeof resolvePickerContext>> } | null> {
  let token = "";
  try {
    token = tokenForRequest(url, request);
  } catch {
    errorResponse(response, 400, "token_in_url", "The link token must be sent in the Authorization header, not in the address.");
    return null;
  }
  const link = lookupPickerLink(token);
  if (!link) {
    const ip = clientAddress(request, config);
    const now = Date.now();
    if (rateCount(failedAttempts, ip, FAILED_WINDOW_MS, now) >= FAILED_LIMIT) {
      errorResponse(response, 429, "too_many_attempts", "Too many invalid links. Try again in a few minutes.");
      return null;
    }
    recordRate(failedAttempts, ip, FAILED_WINDOW_MS, now);
    errorResponse(response, 401, "expired", EXPIRED_MESSAGE);
    return null;
  }
  if (!allowPickerCall(link, write)) {
    errorResponse(response, 429, "rate_limited", "Slow down a little — try again in a minute.", link);
    return null;
  }
  const guild = client.guilds.cache.get(link.guildId);
  if (!guild) {
    errorResponse(response, 503, "guild_unavailable", "The server isn't available right now. Try again soon.", link);
    return null;
  }
  if (!await isGuildRetentionConfigured(guild.id)) {
    errorResponse(response, 423, "setup_required", "Choose the server data-retention setting before using this picker.", link);
    return null;
  }
  try {
    const context = await resolvePickerContext(guild, link.userId);
    return { link, context };
  } catch (error) {
    errorResponse(response, 403, "not_allowed", error instanceof Error ? error.message : "Custom Roles is not available.", link);
    return null;
  }
}

async function updateResponse(
  response: ServerResponse,
  link: PickerLink,
  client: Client,
  config: BotConfig,
  guildId: string,
  userId: string,
  result: { ok: boolean; message: string; notes?: string[] },
): Promise<void> {
  touchPickerLink(link);
  let state: Record<string, unknown> | null = null;
  if (result.ok) {
    if (!config.customRolePickerEnabled) throw new Error("The web Color picker is disabled in this deployment.");
  if (!server?.listening) throw new Error("The web Color picker is still starting. Try again in a moment.");
  const guild = client.guilds.cache.get(guildId);
    if (guild) {
      try {
        const fresh = await resolvePickerContext(guild, userId);
        state = await buildPickerState(fresh, config);
      } catch {
        state = null;
      }
    }
  }
  jsonResponse(response, 200, {
    ok: result.ok,
    message: cleanMessage(result.message),
    notes: (result.notes ?? []).map(cleanMessage),
    state,
  }, link);
}

async function imageResponse(response: ServerResponse, bytes: Buffer, link: PickerLink): Promise<void> {
  const contentType = pickerImageContentType(bytes);
  if (!contentType) {
    errorResponse(response, 404, "no_icon", "The saved icon image is no longer available.", link);
    return;
  }
  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": String(bytes.length),
    "Content-Disposition": "attachment",
    ...expiryHeaders(link),
  });
  response.end(bytes);
}

async function handleRequest(
  request: IncomingMessage,
  response: ServerResponse,
  client: Client,
  config: BotConfig,
): Promise<void> {
  secureHeaders(response);
  const method = request.method ?? "GET";
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  const path = url.pathname;

  if ((path === BASE || path === BASE + "/") && method === "GET") {
    try {
      const page = await readFile(resolve(process.cwd(), "web", "picker.html"));
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Content-Length": String(page.length) });
      response.end(page);
    } catch {
      errorResponse(response, 503, "unavailable", "The Custom Roles picker page is not installed.");
    }
    return;
  }

  if (path.startsWith(BASE + "/static/") && method === "GET") {
    const filename = path.slice((BASE + "/static/").length);
    const contentType = STATIC_TYPES[filename];
    if (!contentType) {
      errorResponse(response, 404, "not_found", "Not found.");
      return;
    }
    try {
      const asset = await readFile(resolve(process.cwd(), "web", filename));
      response.writeHead(200, { "Content-Type": contentType, "Content-Length": String(asset.length) });
      response.end(asset);
    } catch {
      errorResponse(response, 404, "not_found", "Not found.");
    }
    return;
  }

  if (!path.startsWith(BASE + "/api/")) {
    errorResponse(response, 404, "not_found", "Not found.");
    return;
  }

  const apiPath = path.slice((BASE + "/api/").length);
  const readRoutes = new Set(["state", "palette", "icon/source"]);
  const writeRoutes = new Set(["color", "name", "icon", "icon/emoji", "icon/fetch"]);
  const removeIcon = apiPath === "icon" && method === "DELETE";
  const write = (writeRoutes.has(apiPath) && method === "POST") || removeIcon;
  const read = readRoutes.has(apiPath) && method === "GET";
  if (!write && !read) {
    errorResponse(response, 404, "not_found", "Not found.");
    return;
  }
  if (write && !originAllowed(request, config)) {
    errorResponse(response, 403, "cross_origin", "Requests must come from the configured dashboard origin.");
    return;
  }

  const authorized = await authorize(url, request, response, config, client, write);
  if (!authorized) return;
  const { link, context } = authorized;

  if (apiPath === "state") {
    const state = await buildPickerState(context, config);
    touchPickerLink(link);
    jsonResponse(response, 200, { ok: true, state }, link);
    return;
  }

  if (apiPath === "palette") {
    try {
      const colors = await pickerPalette(context);
      touchPickerLink(link);
      jsonResponse(response, 200, { ok: true, colors: colors.map(color => "#" + color.toString(16).padStart(6, "0").toUpperCase()) }, link);
    } catch (error) {
      touchPickerLink(link);
      jsonResponse(response, 200, {
        ok: false,
        message: cleanMessage(error instanceof Error ? error.message : "I couldn't read colors from your avatar."),
        colors: [],
      }, link);
    }
    return;
  }

  if (apiPath === "icon/source") {
    const source = await pickerIconSource(context);
    if (!source) {
      errorResponse(response, 404, "no_icon", "Your role doesn't have an image icon to edit.", link);
      return;
    }
    touchPickerLink(link);
    await imageResponse(response, source, link);
    return;
  }

  if (apiPath === "color" && method === "POST") {
    try {
      const body = await jsonBody(request);
      const result = await pickerSetColor(context, body);
      await updateResponse(response, link, client, config, context.guild.id, context.member.id, result);
    } catch (error) {
      const code = error instanceof Error ? error.message : "bad_json";
      if (code === "json_only") errorResponse(response, 415, code, "Send JSON (Content-Type: application/json).", link);
      else if (code === "too_big") errorResponse(response, 413, code, "That request is too big.", link);
      else errorResponse(response, 400, "bad_json", "That request couldn't be read.", link);
    }
    return;
  }

  if (apiPath === "name" && method === "POST") {
    try {
      const body = await jsonBody(request);
      const result = await pickerSetName(context, body.name);
      await updateResponse(response, link, client, config, context.guild.id, context.member.id, result);
    } catch (error) {
      const code = error instanceof Error ? error.message : "bad_json";
      const status = code === "json_only" ? 415 : code === "too_big" ? 413 : 400;
      errorResponse(response, status, code, code === "too_big" ? "That request is too big." : "That request couldn't be read.", link);
    }
    return;
  }

  if (apiPath === "icon/emoji" && method === "POST") {
    try {
      const body = await jsonBody(request);
      const result = await pickerSetEmoji(context, body.emoji);
      await updateResponse(response, link, client, config, context.guild.id, context.member.id, result);
    } catch (error) {
      const code = error instanceof Error ? error.message : "bad_json";
      const status = code === "json_only" ? 415 : code === "too_big" ? 413 : 400;
      errorResponse(response, status, code, "That request couldn't be read.", link);
    }
    return;
  }

  if (apiPath === "icon" && method === "DELETE") {
    const result = await pickerRemoveIcon(context);
    await updateResponse(response, link, client, config, context.guild.id, context.member.id, result);
    return;
  }

  if (apiPath === "icon" && method === "POST") {
    if (imageInFlight >= IMAGE_CONCURRENCY) {
      errorResponse(response, 503, "busy", BUSY_MESSAGE, link);
      return;
    }
    imageInFlight += 1;
    try {
      const contentType = header(request, "content-type");
      if (!contentType.toLowerCase().startsWith("multipart/form-data")) {
        errorResponse(response, 415, "multipart_only", "Send the image as multipart/form-data.", link);
        return;
      }
      const max = config.customRoleIconSourceMaxBytes;
      const body = await collectBody(request, max + MULTIPART_OVERHEAD);
      const fields = parseMultipart(contentType, body);
      if (!fields.image?.length) {
        errorResponse(response, 400, "no_image", "Choose an image first.", link);
        return;
      }
      if (fields.image.length > max) {
        errorResponse(response, 413, "too_big", "Images can be at most " + Math.ceil(max / (1024 * 1024)) + " MB.", link);
        return;
      }
      const crop = parseCrop(fields.crop);
      const result = await pickerSetImage(context, fields.image, crop);
      await updateResponse(response, link, client, config, context.guild.id, context.member.id, result);
    } catch (error) {
      const code = error instanceof Error ? error.message : "bad_upload";
      if (code === "too_big") errorResponse(response, 413, code, "That upload is too big.", link);
      else if (code === "bad_crop") errorResponse(response, 400, code, "That crop isn't valid. Try cropping again.", link);
      else if (code === "json_only") errorResponse(response, 415, code, "Send the image as multipart/form-data.", link);
      else if (code === "bad_upload") errorResponse(response, 400, code, "That upload couldn't be read.", link);
      else {
        touchPickerLink(link);
        jsonResponse(response, 200, { ok: false, message: cleanMessage(code), notes: [], state: null }, link);
      }
    } finally {
      imageInFlight = Math.max(0, imageInFlight - 1);
    }
    return;
  }

  if (apiPath === "icon/fetch" && method === "POST") {
    try {
      const body = await jsonBody(request);
      if (!context.guild.features.includes("ROLE_ICONS")) {
        errorResponse(response, 403, "no_icons", "Role icons need Discord's Role Icons server feature (Boost Level 2).", link);
        return;
      }
      const fetchKey = context.guild.id + ":" + context.member.id;
      const now = Date.now();
      if (rateCount(linkFetches, fetchKey, FETCH_WINDOW_MS, now) >= FETCH_LIMIT) {
        errorResponse(response, 429, "too_many_fetches", "That's a lot of links in a row. Wait a minute and try again.", link);
        return;
      }
      recordRate(linkFetches, fetchKey, FETCH_WINDOW_MS, now);
      if (imageInFlight >= IMAGE_CONCURRENCY) {
        errorResponse(response, 503, "busy", BUSY_MESSAGE, link);
        return;
      }
      imageInFlight += 1;
      try {
        const fetched = await fetchExternalImage(body.url, config.customRoleIconSourceMaxBytes);
        await processCustomRoleIconImage(fetched.bytes);
        touchPickerLink(link);
        response.writeHead(200, {
          "Content-Type": fetched.contentType,
          "Content-Length": String(fetched.bytes.length),
          "Content-Disposition": "attachment",
          ...expiryHeaders(link),
        });
        response.end(fetched.bytes);
      } finally {
        imageInFlight = Math.max(0, imageInFlight - 1);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "I couldn't download that image.";
      touchPickerLink(link);
      jsonResponse(response, 422, { ok: false, message: cleanMessage(message) }, link);
    }
    return;
  }
}

export async function createCustomRolePickerLink(
  guildId: string,
  userId: string,
  client: Client,
  config: BotConfig,
): Promise<{ url: string; expiresAt: number; maxExpiresAt: number }> {
  const guild = client.guilds.cache.get(guildId);
  if (!guild) throw new Error("This server isn't available right now.");
  if (!await isGuildRetentionConfigured(guildId)) throw new Error("Choose the server data-retention setting before using this picker.");
  await resolvePickerContext(guild, userId);
  const created = createPickerLink(guildId, userId, config);
  return {
    url: config.customRolesPublicUrl + BASE + "#" + created.token,
    expiresAt: created.expiresAt,
    maxExpiresAt: created.maxExpiresAt,
  };
}

export async function startCustomRolePicker(client: Client, config: BotConfig): Promise<void> {
  if (!config.customRolePickerEnabled || server) return;
  const host = config.customRolePickerHost;
  const allowed = host === "localhost" || host === "::1" || isIP(host) === 4 && host.startsWith("127.");
  if (!allowed) throw new Error("The Custom Roles picker may only bind to a loopback IP address.");
  const next = createServer((request, response) => {
    void handleRequest(request, response, client, config).catch(error => {
      logger.error("Custom Roles picker request failed", {
        path: request.url?.split("?")[0] ?? "/",
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      if (!response.headersSent) errorResponse(response, 500, "internal", "The picker couldn't complete that request.");
      else response.destroy();
    });
  });
  await new Promise<void>((resolveListen, reject) => {
    const onError = (error: Error) => reject(error);
    next.once("error", onError);
    next.listen(config.customRolePickerPort, host, () => {
      next.off("error", onError);
      resolveListen();
    });
  });
  server = next;
  logger.info("Custom Roles picker is listening on loopback behind the Rust dashboard proxy", {
    host,
    port: config.customRolePickerPort,
  });
}

export async function stopCustomRolePicker(): Promise<void> {
  const current = server;
  server = null;
  failedAttempts.clear();
  linkFetches.clear();
  clearPickerLinks();
  if (!current) return;
  await new Promise<void>(resolveClose => current.close(() => resolveClose()));
}

export function customRolePickerReady(): boolean {
  return Boolean(server?.listening);
}

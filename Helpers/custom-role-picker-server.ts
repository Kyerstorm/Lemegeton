import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { lookup as dnsLookup, type LookupAddress, type LookupFunction } from "node:dns";
import { isIP } from "node:net";
import https from "node:https";
import type { Client } from "discord.js";
import type { BotConfig } from "./config.js";
import { logger } from "./logger.js";
import {
  allowPickerCall,
  clearPickerLinksForTests,
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

const BASE = "/custom-roles";
const MAX_JSON_BODY = 2048;
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

function errorResponse(
  response: ServerResponse,
  status: number,
  code: string,
  message: string,
  link?: PickerLink,
): void {
  const clean = message
    .replace(/<t:\d+(?::[tTdDfFR])?>/g, "a short time")
    .replace(/<@&\d+>/g, "a role")
    .replace(/<@!?\d+>/g, "a member")
    .replace(/<#\d+>/g, "a channel")
    .replace(/\*\*/g, "")
    .replaceAll(String.fromCharCode(96), "");
  jsonResponse(response, status, { ok: false, error: code, message: clean }, link);
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
  if (!header(request, "content-type").toLowerCase().startsWith("application/json")) {
    throw new Error("json_only");
  }
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
  if (![x, y, size].every(item => typeof item === "number" && Number.isSafeInteger(item))) {
    throw new Error("bad_crop");
  }
  return { x: x as number, y: y as number, size: size as number };
}

function publicIpv4(address: string): boolean {
  const parts = address.split(".").map(Number);
  if (parts.length !== 4 || parts.some(value => !Number.isInteger(value) || value < 0 || value > 255)) return false;
  const a = parts[0]!, b = parts[1]!, c = parts[2]!;
  if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
  if (a === 100 && b >= 64 && b <= 127) return false;
  if (a === 169 && b === 254) return false;
  if (a === 172 && b >= 16 && b <= 31) return false;
  if (a === 192 && (b === 168 || (b === 0 && (c === 0 || c === 2)) || (b === 88 && c === 99))) return false;
  if (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) return false;
  if (a === 203 && b === 0 && c === 113) return false;
  if (a === 255) return false;
  return true;
}

function ipv6Groups(address: string): number[] | null {
  const value = address.toLowerCase().split("%", 1)[0] ?? "";
  if (isIP(value) !== 6 || value.includes(".")) return null;
  const halves = value.split("::");
  if (halves.length > 2) return null;
  const left = halves[0] ? halves[0]!.split(":").filter(Boolean) : [];
  const right = halves.length === 2 && halves[1] ? halves[1]!.split(":").filter(Boolean) : [];
  if (halves.length === 1 && left.length !== 8) return null;
  const missing = halves.length === 2 ? 8 - left.length - right.length : 0;
  if (halves.length === 2 && missing < 1) return null;
  const pieces = [...left, ...Array.from({ length: missing }, () => "0"), ...right];
  if (pieces.length !== 8) return null;
  const groups = pieces.map(part => Number.parseInt(part, 16));
  if (groups.some(group => !Number.isInteger(group) || group < 0 || group > 0xffff)) return null;
  return groups;
}

export function isPublicImageAddress(address: string): boolean {
  const version = isIP(address);
  if (version === 4) return publicIpv4(address);
  if (version !== 6) return false;
  const groups = ipv6Groups(address);
  if (!groups) return false;
  const first = groups[0]!;
  const second = groups[1]!;
  if (first < 0x2000 || first > 0x3fff) return false;
  if (first === 0x2001 && (second <= 0x01ff || second === 0x0db8)) return false;
  if (first === 0x2002) return false;
  return true;
}

async function fetchExternalImage(
  rawUrl: unknown,
  maxBytes: number,
): Promise<{ bytes: Buffer; contentType: "image/png" | "image/jpeg"; host: string }> {
  if (typeof rawUrl !== "string" || !rawUrl.trim()) throw new Error("Paste a link to a PNG or JPEG image.");
  if (rawUrl.length > 2048 || /[\s\x00-\x1f]/.test(rawUrl)) throw new Error("That link is too long or contains hidden characters.");
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error("That doesn't look like a valid link.");
  }
  if (url.protocol !== "https:") throw new Error("Only https:// links work.");
  if (url.username || url.password) throw new Error("Links with a username or password aren't allowed.");
  if (url.port && url.port !== "443") throw new Error("Only links on the normal https port (443) work.");
  const host = url.hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "").toLowerCase();
  if (!host || host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")) {
    throw new Error("That link points to a private or local network address, which isn't allowed.");
  }

  let addresses: LookupAddress[];
  try {
    addresses = await dnsLookup(host, { all: true, verbatim: true });
  } catch {
    throw new Error("I couldn't find that website. Check the link.");
  }
  if (!addresses.length || addresses.some(item => !isPublicImageAddress(item.address))) {
    throw new Error("That link points to a private or local network address, which isn't allowed.");
  }

  const pinnedLookup = ((hostname: string, options: { all?: boolean }, callback: (...args: unknown[]) => void) => {
    if (hostname.replace(/\.$/, "").toLowerCase() !== host) {
      callback(new Error("Unexpected host"), undefined);
      return;
    }
    if (options?.all) callback(null, addresses);
    else callback(null, addresses[0]!.address, addresses[0]!.family);
  }) as unknown as LookupFunction;
  const agent = new https.Agent({ keepAlive: false, lookup: pinnedLookup });

  try {
    const result = await new Promise<{ bytes: Buffer; contentType: "image/png" | "image/jpeg" }>((resolveResult, reject) => {
      const request = https.request(url, {
        method: "GET",
        agent,
        timeout: 10_000,
        headers: { Accept: "image/png, image/jpeg", "User-Agent": "LemegetonCustomRoles/1.0" },
      }, incoming => {
        const status = incoming.statusCode ?? 0;
        const contentType = String(incoming.headers["content-type"] ?? "").split(";")[0]!.trim().toLowerCase();
        const lengthHeader = incoming.headers["content-length"];
        const contentLength = lengthHeader ? Number(lengthHeader) : null;
        if (status >= 300 && status < 400) {
          incoming.resume();
          reject(new Error("That link redirects somewhere else. Use the image's own address."));
          return;
        }
        if (status !== 200) {
          incoming.resume();
          reject(new Error("The website answered with an error (" + status + ")."));
          return;
        }
        if (contentType !== "image/png" && contentType !== "image/jpeg") {
          incoming.resume();
          reject(new Error("That link isn't a PNG or JPEG image."));
          return;
        }
        if (contentLength !== null && (!Number.isSafeInteger(contentLength) || contentLength > maxBytes)) {
          incoming.resume();
          reject(new Error("That image is larger than the allowed " + Math.ceil(maxBytes / (1024 * 1024)) + " MB."));
          return;
        }
        const chunks: Buffer[] = [];
        let total = 0;
        incoming.on("data", chunk => {
          const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
          total += bytes.length;
          if (total > maxBytes) {
            incoming.destroy(new Error("That image is larger than the allowed upload size."));
            return;
          }
          chunks.push(bytes);
        });
        incoming.on("end", () => resolveResult({
          bytes: Buffer.concat(chunks, total),
          contentType: contentType as "image/png" | "image/jpeg",
        }));
        incoming.on("error", reject);
      });
      request.on("timeout", () => request.destroy(new Error("That website took too long (over 10 seconds).")));
      request.on("error", reject);
      request.end();
    });
    return { ...result, host };
  } finally {
    agent.destroy();
  }
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
  try {
    const context = await resolvePickerContext(guild, link.userId);
    return { link, context };
  } catch (error) {
    errorResponse(response, 403, "not_allowed", error instanceof Error ? error.message : "Custom Roles is not available.", link);
    return null;
  }
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

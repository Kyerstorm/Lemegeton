import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { timingSafeEqual } from "node:crypto";
import { isIP } from "node:net";
import type { Client, Guild } from "discord.js";
import type { FeatureCommand } from "./command.js";
import type { BotConfig } from "./config.js";
import { FEATURE_NAMES, getFeatureSettings, isFeatureName, setFeatureEnabled, type FeatureName } from "./settings.js";
import { query, queryOne } from "../database.js";
import { logger, readRecentLogs } from "./logger.js";

const MAX_BODY_BYTES = 64 * 1024;
const PROTECTED_COMMANDS = new Set(["settings"]);
const SECTIONS: Record<string, string> = {
  discover: "Discovery",
  archive: "Archive",
  community: "Community",
  play: "Games",
  profile: "Profile",
  "custom-role": "Custom Roles",
  settings: "Server settings",
};

let server: Server | null = null;
let startedAt = Date.now();
const guildLocks = new Map<string, Promise<void>>();
let hasBeenReady = false;

export function isDashboardGuildId(value: unknown): value is string {
  return typeof value === "string" && /^\d{17,20}$/.test(value);
}

function errorResponse(response: ServerResponse, status: number, message: string): void {
  const body = Buffer.from(JSON.stringify({ error: message }));
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(body.length),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

function jsonResponse(response: ServerResponse, status: number, value: unknown): void {
  const body = Buffer.from(JSON.stringify(value));
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": String(body.length),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(body);
}

export function dashboardSecretMatches(supplied: string, expected: string): boolean {
  const left = Buffer.from(supplied, "utf8");
  const right = Buffer.from(expected, "utf8");
  return left.length === right.length && timingSafeEqual(left, right);
}

async function readJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  const type = String(request.headers["content-type"] ?? "").split(";")[0]?.trim().toLowerCase();
  if (type !== "application/json") throw new Error("Expected application/json.");
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += bytes.length;
    if (size > MAX_BODY_BYTES) throw new Error("Request body is too large.");
    chunks.push(bytes);
  }
  let value: unknown;
  try {
    value = JSON.parse(Buffer.concat(chunks, size).toString("utf8"));
  } catch {
    throw new Error("Invalid JSON body.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected a JSON object.");
  return value as Record<string, unknown>;
}

export function dashboardCommandRows(commands: FeatureCommand[], settings: Awaited<ReturnType<typeof getFeatureSettings>>) {
  return commands.map(command => {
    const definition = command.data.toJSON();
    const name = command.data.name;
    const feature = isFeatureName(name) ? name : null;
    return {
      fullname: name,
      name,
      description: definition.description || "No description provided.",
      section: SECTIONS[name] ?? "Other",
      type: "slash",
      scope: "global",
      aliases: [],
      required_permissions: null,
      protected: PROTECTED_COMMANDS.has(name),
      enabled: feature ? settings[feature] : true,
    };
  });
}

function guildFor(client: Client, guildId: string): Guild | null {
  if (!isDashboardGuildId(guildId)) return null;
  return client.guilds.cache.get(guildId) ?? null;
}

async function recordAudit(guildId: string, actorId: string, action: string, details: string): Promise<void> {
  await query(
    "INSERT INTO dashboard_audit_log (guild_id, actor_id, action, details) VALUES ($1,$2,$3,$4)",
    [guildId, actorId, action.slice(0, 64), details.slice(0, 2000)],
  );
}

async function syncGlobalCommands(client: Client, commands: FeatureCommand[]): Promise<number> {
  if (!client.application) throw new Error("The Discord application is not ready.");
  const registered = await client.application.commands.set(commands.map(command => command.data.toJSON()));
  return registered.size;
}

async function withGuildLock<T>(guildId: string, operation: () => Promise<T>): Promise<T> {
  const prior = guildLocks.get(guildId) ?? Promise.resolve();
  let release!: () => void;
  const current = new Promise<void>(resolve => { release = resolve; });
  const chain = prior.then(() => current);
  guildLocks.set(guildId, chain);
  await prior;
  try {
    return await operation();
  } finally {
    release();
    if (guildLocks.get(guildId) === chain) guildLocks.delete(guildId);
  }
}

async function health(client: Client, commands: FeatureCommand[]): Promise<Record<string, unknown>> {
  const ready = client.isReady();
  if (ready) hasBeenReady = true;
  const latency = ready && client.ws.ping >= 0 ? client.ws.ping : null;
  const status = ready ? latency !== null && latency >= 500 ? "degraded" : "online" : hasBeenReady ? "offline" : "connecting";
  return {
    status,
    ready,
    latency_ms: latency,
    guild_count: client.guilds.cache.size,
    extension_count: commands.length,
    extensions: commands.map(command => command.data.name),
    uptime_seconds: Math.max(0, Math.floor((Date.now() - startedAt) / 1000)),
    node_version: process.versions.node,
    checked_at: Math.floor(Date.now() / 1000),
  };
}

async function guilds(client: Client): Promise<Record<string, unknown>[]> {
  return [...client.guilds.cache.values()]
    .map(guild => ({
      id: guild.id,
      name: guild.name,
      icon: guild.iconURL({ extension: "png", size: 64 }),
      member_count: guild.memberCount ?? null,
    }))
    .sort((left, right) => String(left.name).localeCompare(String(right.name)));
}

async function overview(
  client: Client,
  commands: FeatureCommand[],
  guild: Guild,
): Promise<Record<string, unknown>> {
  const settings = await getFeatureSettings(guild.id);
  const rows = dashboardCommandRows(commands, settings);
  const state = await health(client, commands);
  return {
    guild: { id: guild.id, name: guild.name },
    bot: {
      ready: state.ready,
      status: state.status,
      latency_ms: state.latency_ms,
      guild_count: state.guild_count,
      member_count: guild.memberCount ?? null,
      extension_count: commands.length,
      extensions: commands.map(command => command.data.name),
    },
    commands: {
      total: rows.length,
      enabled: rows.filter(row => row.enabled).length,
      disabled: rows.filter(row => !row.enabled).length,
    },
  };
}

async function commandList(commands: FeatureCommand[], guildId: string): Promise<Record<string, unknown>> {
  return { commands: dashboardCommandRows(commands, await getFeatureSettings(guildId)) };
}

async function setCommand(
  request: IncomingMessage,
  response: ServerResponse,
  client: Client,
  commands: FeatureCommand[],
  guild: Guild,
  fullname: string,
): Promise<void> {
  await withGuildLock(guild.id, async () => {
    let body: Record<string, unknown>;
    try {
      body = await readJson(request);
    } catch (error) {
      errorResponse(response, 400, error instanceof Error ? error.message : "Invalid request body.");
      return;
    }
    if (typeof body.enabled !== "boolean" || !validSnowflake(String(body.actor_id ?? ""))) {
      errorResponse(response, 400, "enabled must be a boolean and actor_id must be a valid Discord ID.");
      return;
    }
    const feature = fullname as FeatureName;
    if (!isFeatureName(fullname) || !commands.some(command => command.data.name === fullname)) {
      errorResponse(response, 404, "Command is not registered for dashboard management.");
      return;
    }
    if (PROTECTED_COMMANDS.has(fullname)) {
      errorResponse(response, 403, "This system command is protected.");
      return;
    }
    const before = await getFeatureSettings(guild.id);
    const previous = before[feature];
    if (previous === body.enabled) {
      jsonResponse(response, 200, { fullname, enabled: previous, synced: true });
      return;
    }
    try {
      await setFeatureEnabled(guild.id, feature, body.enabled, String(body.actor_id));
      await syncGlobalCommands(client, commands);
      await recordAudit(
        guild.id,
        String(body.actor_id),
        "toggle_command",
        fullname + " -> " + (body.enabled ? "enabled" : "disabled"),
      );
    } catch (error) {
      await setFeatureEnabled(guild.id, feature, previous, String(body.actor_id)).catch(() => undefined);
      logger.error("Dashboard command toggle failed", {
        guildId: guild.id,
        command: fullname,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      errorResponse(response, 503, "The command change failed. The previous configuration was restored where possible.");
      return;
    }
    jsonResponse(response, 200, { fullname, enabled: body.enabled, synced: true });
  });
}

async function syncGuild(
  request: IncomingMessage,
  response: ServerResponse,
  client: Client,
  commands: FeatureCommand[],
  guild: Guild,
): Promise<void> {
  await withGuildLock(guild.id, async () => {
    let body: Record<string, unknown>;
    try {
      body = await readJson(request);
    } catch (error) {
      errorResponse(response, 400, error instanceof Error ? error.message : "Invalid request body.");
      return;
    }
    if (!isDashboardGuildId(String(body.actor_id ?? ""))) {
      errorResponse(response, 400, "Invalid dashboard actor.");
      return;
    }
    try {
      const count = await syncGlobalCommands(client, commands);
      await recordAudit(guild.id, String(body.actor_id), "sync_commands", "Published the v3 slash command registry.");
      jsonResponse(response, 200, { synced: count, ok: true });
    } catch (error) {
      logger.error("Dashboard command synchronization failed", {
        guildId: guild.id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      errorResponse(response, 502, "Discord did not confirm command synchronization.");
    }
  });
}

async function resetGuild(
  request: IncomingMessage,
  response: ServerResponse,
  client: Client,
  commands: FeatureCommand[],
  guild: Guild,
): Promise<void> {
  await withGuildLock(guild.id, async () => {
    let body: Record<string, unknown>;
    try {
      body = await readJson(request);
    } catch (error) {
      errorResponse(response, 400, error instanceof Error ? error.message : "Invalid request body.");
      return;
    }
    if (!isDashboardGuildId(String(body.actor_id ?? ""))) {
      errorResponse(response, 400, "Invalid dashboard actor.");
      return;
    }
    const actorId = String(body.actor_id);
    const before = await getFeatureSettings(guild.id);
    try {
      for (const feature of FEATURE_NAMES) await setFeatureEnabled(guild.id, feature, true, actorId);
      await syncGlobalCommands(client, commands);
      await recordAudit(guild.id, actorId, "reset_dashboard", "Reset v3 feature settings to their enabled defaults.");
    } catch (error) {
      for (const feature of FEATURE_NAMES) {
        await setFeatureEnabled(guild.id, feature, before[feature], actorId).catch(() => undefined);
      }
      logger.error("Dashboard reset failed", {
        guildId: guild.id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      errorResponse(response, 503, "Reset failed. The previous configuration was restored where possible.");
      return;
    }
    jsonResponse(response, 200, { ok: true, reset: true });
  });
}

async function auditEntries(guildId: string): Promise<Record<string, unknown>[]> {
  const rows = await query<{
    id: string;
    actor_id: string;
    action: string;
    details: string;
    created_at: Date | string;
  }>(
    "SELECT id::text,actor_id::text,action,details,created_at FROM dashboard_audit_log WHERE guild_id=$1 ORDER BY created_at DESC LIMIT 25",
    [guildId],
  );
  return rows.map(row => ({
    id: row.id,
    ts: row.created_at instanceof Date ? row.created_at.toISOString() : new Date(row.created_at).toISOString(),
    actor_id: row.actor_id,
    action: row.action,
    details: row.details,
  }));
}

async function databaseResources(guildId: string): Promise<Record<string, unknown>[]> {
  const [features, archives, customRoles, users, assets] = await Promise.all([
    queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM guild_feature_settings WHERE guild_id=$1", [guildId]),
    queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM community_archive_entries WHERE created_guild_id=$1", [guildId]),
    queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM custom_role_records WHERE guild_id=$1", [guildId]),
    queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM users WHERE guild_id=$1", [guildId]),
    queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM media_assets WHERE guild_id=$1", [guildId]),
  ]);
  return [
    { name: "Guild feature settings", purpose: "Per-server v3 command availability", state: "Available", detail: String(features?.count ?? "0") + " feature overrides" },
    { name: "Community archive", purpose: "Guild-scoped archive entries", state: "Available", detail: String(archives?.count ?? "0") + " entries" },
    { name: "Custom Roles", purpose: "Member role settings and restoration state", state: "Available", detail: String(customRoles?.count ?? "0") + " member records" },
    { name: "Media profiles", purpose: "Guild-scoped AniList and Steam connections", state: "Available", detail: String(users?.count ?? "0") + " linked profiles" },
    { name: "Media assets", purpose: "Private S3 asset registry", state: "Available", detail: String(assets?.count ?? "0") + " registered assets" },
  ];
}

function integrations(config: BotConfig): Record<string, unknown>[] {
  return [
    { name: "AniList", configured: Boolean(config.anilistApiUrl), detail: "Anime, manga and light-novel metadata" },
    { name: "Steam", configured: Boolean(config.steamApiKey), detail: "Game and player metadata" },
    { name: "IGDB", configured: Boolean(config.igdbClientId && config.igdbClientSecret), detail: "Video-game metadata and artwork" },
    { name: "TMDB", configured: Boolean(config.tmdbBearerToken), detail: "Film and television metadata" },
    { name: "Google Books", configured: Boolean(config.googleBooksApiKey), detail: "Book and edition metadata" },
    { name: "Private S3 storage", configured: Boolean(process.env.S3_BUCKET), detail: "Private archive and role-icon assets" },
  ];
}

async function handleRequest(
  request: IncomingMessage,
  response: ServerResponse,
  client: Client,
  commands: FeatureCommand[],
  config: BotConfig,
  secret: string,
): Promise<void> {
  const authorization = String(request.headers.authorization ?? "");
  const supplied = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!dashboardSecretMatches(supplied, secret)) {
    errorResponse(response, 401, "Unauthorized internal dashboard request.");
    return;
  }
  if (request.method === "GET" && request.url === "/health") {
    jsonResponse(response, 200, await health(client, commands));
    return;
  }
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/guilds") {
    jsonResponse(response, 200, await guilds(client));
    return;
  }
  if (request.method === "GET" && url.pathname === "/integrations") {
    jsonResponse(response, 200, { integrations: integrations(config) });
    return;
  }
  if (request.method === "GET" && url.pathname === "/logs") {
    const file = url.searchParams.get("file") ?? "bot.log";
    if (!["bot.log", "dashboard.log", "error.log"].includes(file)) {
      errorResponse(response, 400, "That log file is not available.");
      return;
    }
    const entries = readRecentLogs(250);
    const content = entries.map(entry => {
      const context = entry.context ? " " + JSON.stringify(entry.context) : "";
      return entry.timestamp + " " + entry.level.toUpperCase() + " " + entry.message + context;
    }).join("\n");
    jsonResponse(response, 200, { name: file, content: content || "No in-memory log entries are available yet." });
    return;
  }

  let match = /^\/guilds\/(\d{17,20})\/overview$/.exec(url.pathname);
  if (request.method === "GET" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    jsonResponse(response, 200, await overview(client, commands, guild));
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/commands$/.exec(url.pathname);
  if (request.method === "GET" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    jsonResponse(response, 200, await commandList(commands, guild.id));
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/commands\/(.+)$/.exec(url.pathname);
  if (request.method === "PUT" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    let fullname: string;
    try { fullname = decodeURIComponent(match[2]!); } catch { errorResponse(response, 400, "Invalid command name."); return; }
    await setCommand(request, response, client, commands, guild, fullname);
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/sync$/.exec(url.pathname);
  if (request.method === "POST" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    await syncGuild(request, response, client, commands, guild);
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/reset$/.exec(url.pathname);
  if (request.method === "POST" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    await resetGuild(request, response, client, commands, guild);
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/audit$/.exec(url.pathname);
  if (request.method === "GET" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    jsonResponse(response, 200, { entries: await auditEntries(guild.id) });
    return;
  }
  match = /^\/guilds\/(\d{17,20})\/database$/.exec(url.pathname);
  if (request.method === "GET" && match) {
    const guild = guildFor(client, match[1]!);
    if (!guild) { errorResponse(response, 404, "The bot is no longer in this server."); return; }
    jsonResponse(response, 200, { resources: await databaseResources(guild.id) });
    return;
  }
  errorResponse(response, 404, "Dashboard bridge route not found.");
}

export async function startDashboardBridge(
  client: Client,
  commands: FeatureCommand[],
  config: BotConfig,
): Promise<void> {
  if (server) return;
  const secret = process.env.DASHBOARD_BRIDGE_SECRET?.trim() ?? "";
  if (Buffer.byteLength(secret, "utf8") < 32) {
    logger.warn("Dashboard bot bridge disabled; DASHBOARD_BRIDGE_SECRET must contain at least 32 bytes.");
    return;
  }
  const hostRaw = process.env.DASHBOARD_BRIDGE_HOST?.trim() || "127.0.0.1";
  const host = hostRaw === "[::1]" ? "::1" : hostRaw;
  const hostParts = host.split(".").map(Number);
  const loopbackV4 = isIP(host) === 4 && hostParts.length === 4 && hostParts[0] === 127;
  if (!(host === "localhost" || host === "::1" || loopbackV4)) {
    throw new Error("DASHBOARD_BRIDGE_HOST must be a loopback address.");
  }
  const port = Number(process.env.DASHBOARD_BRIDGE_PORT ?? "8091");
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535) throw new Error("DASHBOARD_BRIDGE_PORT must be a valid TCP port.");
  startedAt = Date.now();
  hasBeenReady = client.isReady();
  const next = createServer((request, response) => {
    void handleRequest(request, response, client, commands, config, secret).catch(error => {
      logger.error("Dashboard bridge request failed", {
        path: request.url?.split("?")[0] ?? "/",
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      if (!response.headersSent) errorResponse(response, 500, "The bot could not complete this request.");
      else response.destroy();
    });
  });
  await new Promise<void>((resolveListen, reject) => {
    const failed = (error: Error) => reject(error);
    next.once("error", failed);
    next.listen(port, host, () => {
      next.off("error", failed);
      resolveListen();
    });
  });
  server = next;
  logger.info("Private dashboard bot bridge listening on loopback", { host, port });
}

export async function stopDashboardBridge(): Promise<void> {
  const current = server;
  server = null;
  guildLocks.clear();
  if (!current) return;
  await new Promise<void>(resolveClose => current.close(() => resolveClose()));
}

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "./Components/Icons";
import { BrandMark } from "./Components/Brand/BrandMark";

type Page = "overview" | "commands" | "atlas" | "extensions" | "audit" | "diagnostics" | "logs" | "integrations" | "database";
type User = { id: string; username: string; global_name?: string | null; avatar?: string | null };
type Guild = { id: string; name: string; icon?: string | null; administrator?: boolean; member_count?: number | null };
type Command = { fullname: string; name?: string; description?: string; section?: string; type?: string; scope?: string; enabled: boolean; protected?: boolean; required_permissions?: string | boolean | null };
type AuditEntry = { action?: string; details?: string; actor_name?: string; actor_id?: string; ts?: string };
type Overview = { bot?: { ready?: boolean; status?: string; latency_ms?: number | null; member_count?: number | null; guild_count?: number | null; extension_count?: number | null } };
type SystemStatus = { status?: string; ready?: boolean; reason?: string; observed_at?: number; last_known?: Record<string, any> | null; uptime_seconds?: number | null; node_version?: string; extensions?: string[]; latency_ms?: number | null; guild_count?: number | null; extension_count?: number | null };
type Resource = { name?: string; purpose?: string; detail?: string; state?: string };
type Integration = { name?: string; detail?: string; configured?: boolean };
type Toast = { id: number; message: string; error: boolean };
type Confirmation = { title: string; message: string; actionLabel: string; run: () => Promise<void> };
type Bootstrap = { user: User; guilds: Guild[]; csrf_token: string; selected_guild_id?: string };
type CommandResponse = { commands: Command[]; revision: string };
type CommandAccessPolicy = {
  role_mode: "everyone" | "include" | "exclude";
  role_ids: string[];
  channel_mode: "all" | "include" | "exclude";
  channel_ids: string[];
  revision: number;
};
type CommandAccessResponse = {
  roles: { id: string; name: string }[];
  channels: { id: string; name: string; type: number }[];
  policies: Record<string, CommandAccessPolicy>;
};
type ListResponse<T> = { entries?: T[] };
type AtlasRelation = {
  title: string; category: string; url: string | null; relationType: string;
  source: string; sourceKind: "provider" | "recommendation" | "community";
  provider?: string | null; providerId?: string | null; evidence?: string | null;
};
type AtlasGraphNode = {
  id: string; title: string; category: string; url: string | null; depth: number;
  provider?: string | null; providerId?: string | null; imageUrl?: string | null;
  sourceKind?: AtlasRelation["sourceKind"]; sourceLabel?: string; relationType?: string;
};
type AtlasGraphEdge = {
  from: string; to: string; relationType: string; sourceLabel: string;
  sourceKind: AtlasRelation["sourceKind"]; evidence?: string | null;
};
type AtlasResponse = {
  root: { title: string; category: string; url: string | null; provider?: string | null; providerId?: string | null };
  relationships: AtlasRelation[];
  graph?: { rootId: string; nodes: AtlasGraphNode[]; edges: AtlasGraphEdge[]; truncated: boolean };
  clusters?: { category: string; nodeIds: string[]; count: number }[];
  path?: { nodes: AtlasGraphNode[]; edges: AtlasGraphEdge[] } | null;
  export?: { filename: string; mimeType: string; base64: string };
};

const PAGES: { id: Page; label: string; icon: IconName; eyebrow: string; subtitle: string }[] = [
  { id: "overview", label: "Overview", icon: "overview", eyebrow: "LIVE CONTROL / 01", subtitle: "A clear view of bot health and the current server configuration." },
  { id: "commands", label: "Commands", icon: "commands", eyebrow: "COMMAND REGISTRY / 02", subtitle: "Control registered slash commands, scoped to the selected Discord server." },
  { id: "atlas", label: "Knowledge Atlas", icon: "atlas", eyebrow: "MEDIA GRAPH / 03", subtitle: "Explore source-attributed media relationships and the connections approved by this server." },
  { id: "extensions", label: "Extensions", icon: "extensions", eyebrow: "BOT MODULES / 03", subtitle: "Review the extension inventory reported by the live bot process." },
  { id: "audit", label: "Audit history", icon: "audit", eyebrow: "CHANGE RECORD / 04", subtitle: "Review recorded dashboard configuration changes for this server." },
  { id: "diagnostics", label: "Diagnostics", icon: "diagnostics", eyebrow: "HEALTH & TELEMETRY / 05", subtitle: "Inspect the bot gateway, runtime version, uptime, and last-known status." },
  { id: "logs", label: "Runtime logs", icon: "logs", eyebrow: "RUNTIME OUTPUT / 06", subtitle: "Read recent operational logs. This view is restricted to dashboard owners." },
  { id: "integrations", label: "Integrations", icon: "integrations", eyebrow: "CONNECTED SERVICES / 07", subtitle: "Check configuration presence without exposing credential values." },
  { id: "database", label: "Persistence", icon: "database", eyebrow: "PERSISTENCE / 08", subtitle: "Inspect the saved resources supporting per-guild command settings." }
];

async function api<T>(path: string, csrf = "", init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", csrf);
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, method, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new Error("The dashboard service could not be reached. Check the connection and retry.");
  }
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Your session expired. Sign in again.");
  }
  const data: any = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.error || ("Request failed (" + response.status + ")."));
  return data as T;
}

function number(value: number | null | undefined): string {
  return value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toLocaleString();
}
function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(Number(seconds))) return "Unavailable";
  const value = Math.max(0, Number(seconds));
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = Math.floor(value % 60);
  return (days ? days + "d " : "") + hours + "h " + minutes + "m " + secs + "s";
}
function timeAgo(value?: string): string {
  if (!value) return "Unknown time";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const elapsed = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
  if (elapsed < 60) return "Just now";
  if (elapsed < 3600) return Math.floor(elapsed / 60) + "m ago";
  if (elapsed < 86400) return Math.floor(elapsed / 3600) + "h ago";
  return Math.floor(elapsed / 86400) + "d ago";
}
function timestamp(value?: number): string {
  return value ? new Date(value * 1000).toLocaleString() : "Unavailable";
}
function errorMessage(value: unknown): string {
  return value instanceof Error ? value.message : "Something went wrong. Please retry.";
}

function commandGuideUrl(command: Command): string {
  const name = (command.fullname || command.name || "").trim().toLowerCase().split(/\s+/)[0];
  const mediaGuide = "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/MEDIA_DISCOVERY.md";
  const readmeGuide = "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/README.md#command-map";
  const guideAnchors: Record<string, string> = {
    franchise: "#franchise-exploration",
    similar: "#cross-media-similarity",
    "tv-guide": "#tv-season-and-episode-guide",
    "release-calendar": "#release-calendar",
    "reading-club": "#reading-club",
    "media-night": "#media-night",
    compare: "#comparison",
  };
  if (name === "dashboard") {
    return "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/DASHBOARD.md#capabilities-and-boundaries";
  }
  if (name === "custom-role" || name === "custom-role-admin") {
    return "https://github.com/Kyerstorm/Lemegeton/blob/multi_guild/docs/HANDOFF_NOTES.md";
  }
  if (guideAnchors[name]) return mediaGuide + guideAnchors[name];
  if (["browse", "connections", "reading-order", "where-to-watch", "trailers", "collection-guide", "media-region", "episode-discussion", "chapter-discussion", "author-works", "webnovel-updates"].includes(name)) {
    return mediaGuide;
  }
  return readmeGuide;
}

function SectionHeading(props: { eyebrow: string; title: React.ReactNode; subtitle: string; actions?: React.ReactNode }) {
  return <div className="page-heading">
    <div className="page-heading-copy">
      <p className="eyebrow">{props.eyebrow}</p>
      <h1>{props.title}</h1>
      <p className="lede">{props.subtitle}</p>
    </div>
    {props.actions ? <div className="heading-actions">{props.actions}</div> : null}
  </div>;
}
function Panel(props: { eyebrow?: string; title: string; index?: string; action?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return <article className={"panel " + (props.className || "")}>
    {props.eyebrow || props.index || props.action ? <div className="panel-heading">
      <div>{props.eyebrow ? <p className="eyebrow">{props.eyebrow}</p> : null}<h2>{props.title}</h2></div>
      {props.action || (props.index ? <span className="panel-index">{props.index}</span> : null)}
    </div> : <div className="panel-heading"><h2>{props.title}</h2></div>}
    {props.children}
  </article>;
}
function Empty(props: { children: React.ReactNode; loading?: boolean }) {
  return <div className={"empty-state" + (props.loading ? " loading-state" : "")}>{props.loading ? <span className="spinner" aria-hidden="true" /> : null}{props.children}</div>;
}
function StatusPill(props: { ok?: boolean; children: React.ReactNode }) {
  return <span className={"status-pill " + (props.ok === true ? "is-good" : props.ok === false ? "is-bad" : "is-neutral")}><i aria-hidden="true" />{props.children}</span>;
}
function Button({ tone = "secondary", className, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "quiet" }) {
  return <button {...props} className={"button " + tone + (className ? " " + className : "")}>{children}</button>;
}
function LoginPage() {
  const [cancelled, setCancelled] = useState(false);
  useEffect(() => setCancelled(new URLSearchParams(window.location.search).get("error") === "cancelled"), []);
  return <main className="login-wrap">
    <div className="login-orbit orbit-one" aria-hidden="true" /><div className="login-orbit orbit-two" aria-hidden="true" />
    <section className="login-card">
      <a className="brand login-brand" href="/" aria-label="Lemegeton home"><BrandMark /><span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span></a>
      <div className="login-kicker"><span className="signal-dot online" /> PRIVATE ADMINISTRATION <span className="braille-mini" aria-hidden="true">⠿⠗⠿⠿⠿</span></div>
      <h1>Control the<br /><span>moving parts.</span></h1>
      <p className="login-copy">Manage command access, review server activity, and inspect runtime health through your existing Discord permissions.</p>
      {cancelled ? <div className="inline-notice">Sign-in was cancelled. Nothing has been changed.</div> : null}
      <a className="button primary login-button" href="/oauth/start">Continue with Discord <span aria-hidden="true">↗</span></a>
      <div className="login-separator"><span />SECURE DISCORD SIGN-IN<span /></div>
      <div className="login-assurances"><span><b>01</b> Server permissions checked on every request</span><span><b>02</b> Configuration scoped per guild</span><span><b>03</b> Secret values stay server-side</span></div>
      <div className="login-foot"><span>LEMEGETON / ACCESS</span><span>SESSION PROTECTED</span></div>
    </section>
  </main>;
}

export default function App() {
  const pathname = usePathname();
  const isLogin = pathname === "/login";
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [guildId, setGuildId] = useState("");
  const [csrf, setCsrf] = useState("");
  const [page, setPage] = useState<Page>("overview");
  const [overview, setOverview] = useState<Overview>({});
  const [system, setSystem] = useState<SystemStatus>({});
  const [commands, setCommands] = useState<Command[]>([]);
  const [savedCommands, setSavedCommands] = useState<Command[]>([]);
  const [commandRevision, setCommandRevision] = useState("");
  const [savingCommands, setSavingCommands] = useState(false);
  const [commandError, setCommandError] = useState("");
  const [accessTarget, setAccessTarget] = useState("");
  const [accessOptions, setAccessOptions] = useState<CommandAccessResponse | null>(null);
  const [accessDraft, setAccessDraft] = useState<CommandAccessPolicy | null>(null);
  const [accessOriginal, setAccessOriginal] = useState<CommandAccessPolicy | null>(null);
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessSaving, setAccessSaving] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [logText, setLogText] = useState("");
  const [logName, setLogName] = useState("bot.log");
  const [logFile, setLogFile] = useState("bot.log");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [commandState, setCommandState] = useState("All");
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [operationBusy, setOperationBusy] = useState(false);
  const [atlasTitle, setAtlasTitle] = useState("");
  const [atlasCategory, setAtlasCategory] = useState("ANIME");
  const [atlasResult, setAtlasResult] = useState<AtlasResponse | null>(null);
  const [atlasLoading, setAtlasLoading] = useState(false);
  const [atlasError, setAtlasError] = useState("");
  const [atlasCategoryFilter, setAtlasCategoryFilter] = useState("All");
  const [atlasSourceFilter, setAtlasSourceFilter] = useState("All");
  const [atlasProviderFilter, setAtlasProviderFilter] = useState("All");
  const [atlasProviderIdFilter, setAtlasProviderIdFilter] = useState("");
  const [atlasRelationshipFilter, setAtlasRelationshipFilter] = useState("All");
  const [atlasEvidenceFilter, setAtlasEvidenceFilter] = useState("");
  const [atlasPathTarget, setAtlasPathTarget] = useState("");
  const [atlasExportBusy, setAtlasExportBusy] = useState("");
  const [atlasZoom, setAtlasZoom] = useState(100);
  const refreshGeneration = useRef(0);
  const atlasRequestGeneration = useRef(0);
  const atlasDeepLinkConsumed = useRef(false);
  const activeGuildIdRef = useRef("");

  const pushToast = useCallback((message: string, error = false) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((current) => [...current.slice(-3), { id, message, error }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4400);
  }, []);

  const currentGuild = useMemo(() => guilds.find((item) => String(item.id) === String(guildId)), [guilds, guildId]);
  const commandDraftDirty = useMemo(() => {
    if (commands.length !== savedCommands.length) return true;
    const saved = new Map(savedCommands.map((item) => [item.fullname, item.enabled]));
    return commands.some(item => saved.get(item.fullname) !== item.enabled);
  }, [commands, savedCommands]);
  const commandDraftDirtyRef = useRef(false);
  useEffect(() => { commandDraftDirtyRef.current = commandDraftDirty; }, [commandDraftDirty]);
  const accessDraftDirty = useMemo(() => {
    if (!accessDraft || !accessOriginal) return false;
    return accessDraft.role_mode !== accessOriginal.role_mode
      || accessDraft.channel_mode !== accessOriginal.channel_mode
      || accessDraft.role_ids.join(",") !== accessOriginal.role_ids.join(",")
      || accessDraft.channel_ids.join(",") !== accessOriginal.channel_ids.join(",");
  }, [accessDraft, accessOriginal]);
  const selectGuild = useCallback((nextId: string) => {
    if (!guilds.some((guild) => String(guild.id) === String(nextId))) return;
    if (commandDraftDirtyRef.current && !window.confirm("Discard unsaved command changes before switching servers?")) return;
    activeGuildIdRef.current = String(nextId);
    refreshGeneration.current += 1;
    atlasRequestGeneration.current += 1;
    setAtlasResult(null);
    setAtlasError("");
    setAtlasLoading(false);
    try { window.localStorage.setItem("lemegeton:selected-guild", String(nextId)); } catch { /* storage may be disabled */ }
    setGuildId(String(nextId));
    setConfirmation(null);
    setOverview({});
    setCommands([]);
    setSavedCommands([]);
    setCommandRevision("");
    setCommandError("");
    setAccessTarget("");
    setAccessOptions(null);
    setAccessDraft(null);
    setAccessOriginal(null);
    setAccessLoading(false);
    setAccessSaving(false);
    setAudit([]);
    setResources([]);
    setUpdatedAt(null);
    setRefreshing(false);
  }, [guilds]);
  const categories = useMemo(() => Array.from(new Set(commands.map((item) => item.section || "Other"))).sort((a, b) => a.localeCompare(b)), [commands]);
  const filteredCommands = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return commands.filter((item) => {
      const text = [item.fullname, item.name, item.description, item.section, item.type, item.scope].join(" ").toLowerCase();
      const stateMatch = commandState === "All"
        || (commandState === "Protected" && Boolean(item.protected))
        || (commandState === "Enabled" && Boolean(item.enabled) && !item.protected)
        || (commandState === "Disabled" && !item.enabled && !item.protected);
      return (category === "All" || (item.section || "Other") === category) && stateMatch && text.includes(needle);
    });
  }, [commands, search, category, commandState]);

  const loadAudit = useCallback(async (id = guildId, quiet = false) => {
    if (!id || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
    try {
      const data = await api<ListResponse<AuditEntry>>("/api/guilds/" + encodeURIComponent(id) + "/audit", csrf);
      if (activeGuildIdRef.current && activeGuildIdRef.current !== String(id)) return;
      setAudit(data.entries || []);
    } catch (error) {
      if (!quiet) pushToast(errorMessage(error), true);
    }
  }, [csrf, guildId, pushToast]);

  const refreshData = useCallback(async (id = guildId, quiet = false) => {
    if (!id || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
    const requestGeneration = ++refreshGeneration.current;
    setRefreshing(true);
    const results = await Promise.allSettled([
      api<Overview>("/api/guilds/" + encodeURIComponent(id) + "/overview", csrf),
      api<CommandResponse>("/api/guilds/" + encodeURIComponent(id) + "/commands", csrf),
      api<SystemStatus>("/api/system", csrf),
      api<ListResponse<AuditEntry>>("/api/guilds/" + encodeURIComponent(id) + "/audit", csrf)
    ] as const);
    if (requestGeneration !== refreshGeneration.current || activeGuildIdRef.current !== String(id)) return;
    const [overviewResult, commandsResult, systemResult, auditResult] = results;
    if (overviewResult.status === "fulfilled") setOverview(overviewResult.value || {});
    else if (!quiet) pushToast(errorMessage(overviewResult.reason), true);
    if (commandsResult.status === "fulfilled") {
      if (!commandDraftDirtyRef.current || commandsResult.value.revision === commandRevision) {
        setCommands(commandsResult.value.commands || []);
        setSavedCommands(commandsResult.value.commands || []);
        setCommandRevision(commandsResult.value.revision || "");
      }
      setCommandError("");
    } else {
      setCommandError(errorMessage(commandsResult.reason));
      if (!quiet) pushToast(errorMessage(commandsResult.reason), true);
    }
    if (systemResult.status === "fulfilled") setSystem(systemResult.value || {});
    else if (!quiet) pushToast(errorMessage(systemResult.reason), true);
    if (auditResult.status === "fulfilled") setAudit(auditResult.value.entries || []);
    else if (!quiet) pushToast(errorMessage(auditResult.reason), true);
    setUpdatedAt(Date.now());
    setRefreshing(false);
  }, [csrf, guildId, pushToast, commandRevision]);

  const loadSystem = useCallback(async () => {
    try { setSystem(await api<SystemStatus>("/api/system", csrf)); }
    catch (error) { pushToast(errorMessage(error), true); }
  }, [csrf, pushToast]);

  const loadDatabase = useCallback(async () => {
    if (!guildId) return;
    const requestedGuild = guildId;
    try {
      const data = await api<{ resources?: Resource[] }>("/api/guilds/" + encodeURIComponent(requestedGuild) + "/database", csrf);
      if (activeGuildIdRef.current && activeGuildIdRef.current !== String(requestedGuild)) return;
      setResources(data.resources || []);
    } catch (error) {
      if (activeGuildIdRef.current && activeGuildIdRef.current !== String(requestedGuild)) return;
      pushToast(errorMessage(error), true);
      setResources([]);
    }
  }, [csrf, guildId, pushToast]);

  const loadIntegrations = useCallback(async () => {
    try {
      const data = await api<{ integrations?: Integration[] }>("/api/integrations", csrf);
      setIntegrations(data.integrations || []);
    } catch (error) { pushToast(errorMessage(error), true); setIntegrations([]); }
  }, [csrf, pushToast]);

  const loadLogs = useCallback(async (file = logFile) => {
    try {
      const data = await api<{ name?: string; content?: string }>("/api/logs?file=" + encodeURIComponent(file), csrf);
      setLogName(data.name || file);
      setLogText(data.content || "No log entries found.");
    } catch (error) { setLogText(errorMessage(error)); }
  }, [csrf, logFile]);

  useEffect(() => {
    if (isLogin) { setInitialLoading(false); return; }
    let active = true;
    api<Bootstrap>("/api/bootstrap").then((data) => {
      if (!active) return;
      setUser(data.user);
      const availableGuilds = data.guilds || [];
      setGuilds(availableGuilds);
      setCsrf(data.csrf_token || "");
      let rememberedGuild = "";
      try { rememberedGuild = window.localStorage.getItem("lemegeton:selected-guild") || ""; } catch { /* storage may be disabled */ }
      const canSelect = (candidate: unknown) => candidate != null && availableGuilds.some((guild) => String(guild.id) === String(candidate));
      const selected = String([rememberedGuild, data.selected_guild_id, availableGuilds[0]?.id].find(canSelect) || "");
      activeGuildIdRef.current = selected;
      setGuildId(selected);
      if (!selected) pushToast("No server is available where the bot is present and you have Manage Server or Administrator permission.", true);
    }).catch((error) => {
      if (active) pushToast(errorMessage(error), true);
    }).finally(() => { if (active) setInitialLoading(false); });
    return () => { active = false; };
  }, [isLogin, pushToast]);

  useEffect(() => {
    if (!guildId || isLogin || !csrf) return;
    void refreshData(guildId, true);
    const timer = window.setInterval(() => {
      if (!document.hidden) void refreshData(guildId, true);
    }, 45000);
    return () => window.clearInterval(timer);
  }, [guildId, csrf, isLogin, refreshData]);

  useEffect(() => {
    if (!guildId || isLogin) return;
    if (page === "audit") void loadAudit(guildId, true);
    if (page === "extensions" || page === "diagnostics") void loadSystem();
    if (page === "database") void loadDatabase();
    if (page === "logs") void loadLogs(logFile);
    if (page === "integrations") void loadIntegrations();
  }, [page, guildId, isLogin, logFile, loadAudit, loadSystem, loadDatabase, loadLogs, loadIntegrations]);

  const settleConfirmation = (confirmed: boolean) => {
    const item = confirmation;
    setConfirmation(null);
    if (confirmed && item) {
      void (async () => {
        setOperationBusy(true);
        try { await item.run(); }
        finally { setOperationBusy(false); }
      })();
    }
  };

  const synchronizeCommands = () => {
    if (!guildId || operationBusy) return;
    setConfirmation({
      title: "Publish slash commands",
      message: "Synchronize registered dashboard-managed commands for " + (currentGuild?.name || "this server") + " with Discord. Unrelated commands are not unregistered.",
      actionLabel: "Publish commands",
      run: async () => {
        try {
          const result = await api<{ synced?: number }>("/api/guilds/" + encodeURIComponent(guildId) + "/sync", csrf, { method: "POST", body: "{}" });
          pushToast("Discord synchronization completed for " + (result.synced == null ? "the enabled" : number(result.synced)) + " commands.");
          await refreshData(guildId, true);
        } catch (error) { pushToast(errorMessage(error), true); }
      }
    });
  };

  const resetCommands = () => {
    if (!guildId || operationBusy) return;
    setConfirmation({
      title: "Reset server overrides",
      message: "Reset saved command configuration for " + (currentGuild?.name || "this server") + " and synchronize the resulting defaults? This cannot be undone from the dashboard.",
      actionLabel: "Reset overrides",
      run: async () => {
        try {
          await api("/api/guilds/" + encodeURIComponent(guildId) + "/reset", csrf, { method: "POST", body: "{}" });
          await refreshData(guildId, true);
          pushToast("Server command overrides reset and synchronized.");
        } catch (error) { pushToast(errorMessage(error), true); }
      }
    });
  };

  const toggleCommand = (command: Command) => {
    if (!guildId || command.protected || savingCommands) return;
    setCommands((items) => items.map((item) =>
      item.fullname === command.fullname ? { ...item, enabled: !item.enabled } : item
    ));
  };

  const resetCommandDraft = () => {
    setCommands(savedCommands.map(item => ({ ...item })));
  };

  const saveCommandDraft = async () => {
    if (!guildId || !commandDraftDirty || savingCommands || !commandRevision) return;
    const requestedGuild = guildId;
    const baseline = new Map(savedCommands.map(item => [item.fullname, item.enabled]));
    const updates = commands
      .filter(item => !item.protected && baseline.get(item.fullname) !== item.enabled)
      .map(item => ({ fullname: item.fullname, enabled: item.enabled }));
    if (!updates.length) return;
    setSavingCommands(true);
    try {
      const result = await api<CommandResponse>("/api/guilds/" + encodeURIComponent(requestedGuild) + "/commands", csrf, {
        method: "PUT",
        body: JSON.stringify({ expected_revision: commandRevision, updates }),
      });
      if (activeGuildIdRef.current !== requestedGuild) return;
      setCommands(result.commands || []);
      setSavedCommands(result.commands || []);
      setCommandRevision(result.revision || "");
      pushToast("Saved and synchronized " + updates.length + " command change" + (updates.length === 1 ? "" : "s") + ".");
      void loadAudit(requestedGuild, true);
    } catch (error) {
      pushToast(errorMessage(error), true);
    } finally {
      if (activeGuildIdRef.current === requestedGuild) setSavingCommands(false);
    }
  };

  useEffect(() => {
    if (!commandDraftDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [commandDraftDirty]);

  const openCommandAccess = async (command: Command) => {
    if (!guildId || command.protected || accessLoading || accessSaving) return;
    const requestedGuild = guildId;
    setAccessTarget(command.fullname);
    setAccessLoading(true);
    setAccessOptions(null);
    setAccessDraft(null);
    setAccessOriginal(null);
    try {
      const result = await api<CommandAccessResponse>(
        "/api/guilds/" + encodeURIComponent(requestedGuild) + "/command-access", csrf,
      );
      if (activeGuildIdRef.current !== requestedGuild) return;
      const policy = result.policies?.[command.fullname] || {
        role_mode: "everyone", role_ids: [], channel_mode: "all", channel_ids: [], revision: 0,
      };
      setAccessOptions(result);
      setAccessDraft({ ...policy, role_ids: [...policy.role_ids], channel_ids: [...policy.channel_ids] });
      setAccessOriginal({ ...policy, role_ids: [...policy.role_ids], channel_ids: [...policy.channel_ids] });
    } catch (error) {
      pushToast(errorMessage(error), true);
    } finally {
      if (activeGuildIdRef.current === requestedGuild) setAccessLoading(false);
    }
  };

  const closeCommandAccess = () => {
    if (accessDraftDirty && !window.confirm("Discard unsaved access rules?")) return;
    setAccessTarget("");
    setAccessOptions(null);
    setAccessDraft(null);
    setAccessOriginal(null);
  };

  const resetCommandAccess = () => {
    if (!accessOriginal) return;
    setAccessDraft({ ...accessOriginal, role_ids: [...accessOriginal.role_ids], channel_ids: [...accessOriginal.channel_ids] });
  };

  const saveCommandAccess = async () => {
    if (!guildId || !accessTarget || !accessDraft || !accessDraftDirty || accessSaving) return;
    const requestedGuild = guildId;
    const target = accessTarget;
    setAccessSaving(true);
    try {
      const result = await api<{ policy: CommandAccessPolicy }>(
        "/api/guilds/" + encodeURIComponent(requestedGuild) + "/command-access/" + encodeURIComponent(target),
        csrf,
        {
          method: "PUT",
          body: JSON.stringify({
            expected_revision: accessDraft.revision,
            role_mode: accessDraft.role_mode,
            role_ids: accessDraft.role_ids,
            channel_mode: accessDraft.channel_mode,
            channel_ids: accessDraft.channel_ids,
          }),
        },
      );
      if (activeGuildIdRef.current !== requestedGuild) return;
      setAccessDraft(result.policy);
      setAccessOriginal(result.policy);
      pushToast("Access rules saved for /" + target + ".");
      void loadAudit(requestedGuild, true);
    } catch (error) {
      pushToast(errorMessage(error), true);
    } finally {
      if (activeGuildIdRef.current === requestedGuild) setAccessSaving(false);
    }
  };

  const copyCommandInvocation = async (command: Command) => {
    const invocation = "/" + (command.fullname || command.name || "").trim();
    if (invocation.length < 2) {
      pushToast("This registry entry has no command name to copy.", true);
      return;
    }
    try {
      await navigator.clipboard.writeText(invocation);
      pushToast("Copied " + invocation + " — paste it into Discord to run the command.");
    } catch {
      pushToast("Clipboard access is unavailable. Command: " + invocation, true);
    }
  };

  const logout = async () => {
    try {
      await api("/api/logout", csrf, { method: "POST", body: "{}" });
      window.location.assign("/login");
    } catch (error) { pushToast(errorMessage(error), true); }
  };

  const searchAtlas = useCallback(async (
    title = atlasTitle,
    mediaCategory = atlasCategory,
    mediaUrl?: string | null,
    extra: Record<string, string> = {},
  ) => {
    const cleanTitle = title.trim();
    if (!guildId || !cleanTitle) {
      setAtlasError("Enter a media title to explore its connections.");
      return;
    }
    const requestedGuild = guildId;
    const requestId = ++atlasRequestGeneration.current;
    const params = new URLSearchParams({ title: cleanTitle, category: mediaCategory });
    if (mediaUrl) params.set("url", mediaUrl);
    for (const [key, value] of Object.entries(extra)) {
      if (value.trim()) params.set(key, value.trim());
    }
    setAtlasTitle(cleanTitle);
    setAtlasCategory(mediaCategory);
    setAtlasLoading(true);
    setAtlasError("");
    try {
      const result = await api<AtlasResponse>(
        "/api/guilds/" + encodeURIComponent(requestedGuild) + "/atlas?" + params.toString(),
        csrf,
      );
      if (requestId !== atlasRequestGeneration.current || activeGuildIdRef.current !== requestedGuild) return;
      setAtlasResult(result);
    } catch (error) {
      if (requestId !== atlasRequestGeneration.current || activeGuildIdRef.current !== requestedGuild) return;
      setAtlasError(errorMessage(error));
      setAtlasResult(null);
    } finally {
      if (requestId === atlasRequestGeneration.current) setAtlasLoading(false);
    }
  }, [atlasCategory, atlasTitle, csrf, guildId]);

  const atlasFilters = () => ({
    filter_category: atlasCategoryFilter === "All" ? "" : atlasCategoryFilter,
    source_kind: atlasSourceFilter === "All" ? "" : atlasSourceFilter,
    provider_filter: atlasProviderFilter === "All" ? "" : atlasProviderFilter,
    provider_id_filter: atlasProviderIdFilter,
    relationship_type: atlasRelationshipFilter === "All" ? "" : atlasRelationshipFilter,
    evidence: atlasEvidenceFilter,
  });

  const downloadAtlas = async (format: "json" | "svg" | "png") => {
    if (!atlasResult || !guildId || atlasExportBusy) return;
    setAtlasExportBusy(format);
    try {
      const params = new URLSearchParams({
        title: atlasResult.root.title,
        category: atlasResult.root.category,
        export: format,
        max_depth: "3",
        max_nodes: "40",
        ...atlasFilters(),
      });
      if (atlasResult.root.url) params.set("url", atlasResult.root.url);
      if (atlasResult.root.provider) params.set("provider", atlasResult.root.provider);
      if (atlasResult.root.providerId) params.set("provider_id", atlasResult.root.providerId);
      if (atlasPathTarget) {
        const target = atlasGraphNodes.find(node => node.id === atlasPathTarget);
        if (target) {
          params.set("target_title", target.title);
          params.set("target_category", target.category);
          if (target.url) params.set("target_url", target.url);
          if (target.provider) params.set("target_provider", target.provider);
          if (target.providerId) params.set("target_provider_id", target.providerId);
        }
      }
      const payload = await api<AtlasResponse>(
        "/api/guilds/" + encodeURIComponent(guildId) + "/atlas?" + params.toString(),
        csrf,
      );
      let blob: Blob;
      let filename = "lemegeton-atlas.json";
      if (format === "json") {
        blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      } else {
        if (!payload.export?.base64) throw new Error("The Atlas export did not return an image.");
        const binary = window.atob(payload.export.base64);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        blob = new Blob([bytes], { type: payload.export.mimeType });
        filename = payload.export.filename;
      }
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      pushToast(errorMessage(error), true);
    } finally {
      setAtlasExportBusy("");
    }
  };

  useEffect(() => {
    if (!guildId || !csrf || isLogin || atlasDeepLinkConsumed.current) return;
    const params = new URLSearchParams(window.location.search);
    const title = params.get("atlas_title");
    if (!title) {
      atlasDeepLinkConsumed.current = true;
      return;
    }
    const requestedGuild = params.get("atlas_guild_id");
    if (requestedGuild && requestedGuild !== guildId) {
      if (guilds.some((item) => String(item.id) === requestedGuild)) {
        selectGuild(requestedGuild);
      } else {
        atlasDeepLinkConsumed.current = true;
        setPage("atlas");
        setAtlasError("This Atlas link belongs to a server where your account does not have dashboard access.");
      }
      return;
    }
    const requestedCategory = params.get("atlas_category") || "ANIME";
    const allowedCategories = ["ANIME", "MANGA", "LIGHT_NOVEL", "WEBNOVEL", "BOOK", "MOVIE", "TV", "GAME", "CREATOR", "FRANCHISE", "ARCHIVE_ENTRY", "ARCHIVE_COLLECTION", "DISCUSSION", "ACTIVITY"];
    if (!allowedCategories.includes(requestedCategory)) {
      atlasDeepLinkConsumed.current = true;
      setPage("atlas");
      setAtlasError("This Atlas link uses an unsupported media category.");
      return;
    }
    atlasDeepLinkConsumed.current = true;
    setPage("atlas");
    void searchAtlas(title, requestedCategory, params.get("atlas_url"));
  }, [atlasCategory, atlasTitle, csrf, guildId, guilds, isLogin, searchAtlas, selectGuild]);

  const navigate = (next: Page) => {
    if (commandDraftDirty && next !== "commands"
      && !window.confirm("Discard unsaved command changes before leaving this page?")) return;
    setPage(next);
    setMobileNav(false);
  };
  const selectedPage = PAGES.find((item) => item.id === page) || PAGES[0];

  if (isLogin) return <LoginPage />;

  const bot = overview.bot || {};
  const enabled = commands.filter((item) => item.enabled).length;
  const disabled = Math.max(0, commands.length - enabled);
  const percent = commands.length ? Math.round(enabled * 100 / commands.length) : 0;
  const runtimeStatus = system.status === "unknown" ? "UNKNOWN" : String(system.status || (bot.ready ? "online" : "connecting")).toUpperCase();
  const runtimeOnline = Boolean(bot.ready) && system.status !== "unknown";
  const lastKnown = system.last_known || null;
  const atlasRootId = atlasResult?.graph?.rootId ?? "root";
  const atlasGraphNodes: AtlasGraphNode[] = atlasResult
    ? atlasResult.graph?.nodes ?? [
        { id: atlasRootId, ...atlasResult.root, depth: 0 },
        ...atlasResult.relationships.map((item, index) => ({
          id: "direct-" + index, title: item.title, category: item.category, url: item.url,
          depth: 1, sourceKind: item.sourceKind, sourceLabel: item.source, relationType: item.relationType,
          provider: item.provider, providerId: item.providerId,
        })),
      ]
    : [];
  const atlasCategories = Array.from(new Set(atlasGraphNodes.filter(item => item.depth > 0).map(item => item.category))).sort();
  const atlasProviders = Array.from(new Set(atlasGraphNodes.map(item => item.provider).filter((value): value is string => Boolean(value)))).sort();
  const atlasCandidateNodes = atlasGraphNodes.filter(item =>
    item.depth > 0
    && (atlasCategoryFilter === "All" || item.category === atlasCategoryFilter)
    && (atlasProviderFilter === "All" || item.provider === atlasProviderFilter),
  );
  const atlasCandidateIds = new Set([atlasRootId, ...atlasCandidateNodes.map(item => item.id)]);
  const atlasVisibleEdges = (atlasResult?.graph?.edges ?? (atlasResult?.relationships ?? []).map((item, index) => ({
    from: atlasRootId, to: "direct-" + index, relationType: item.relationType, sourceLabel: item.source, sourceKind: item.sourceKind,
    evidence: item.evidence,
  }))).filter(edge => {
    const from = atlasGraphNodes.find(node => node.id === edge.from);
    const to = atlasGraphNodes.find(node => node.id === edge.to);
    const evidenceQuery = atlasEvidenceFilter.trim().toLocaleLowerCase("en-US");
    return (atlasSourceFilter === "All" || edge.sourceKind === atlasSourceFilter)
      && (atlasRelationshipFilter === "All" || edge.relationType.toLocaleLowerCase("en-US").includes(atlasRelationshipFilter.toLocaleLowerCase("en-US")))
      && (!evidenceQuery || (edge.evidence ?? "").toLocaleLowerCase("en-US").includes(evidenceQuery))
      && (atlasProviderFilter === "All" || from?.provider === atlasProviderFilter || to?.provider === atlasProviderFilter)
      && (!atlasProviderIdFilter.trim() || from?.providerId === atlasProviderIdFilter.trim() || to?.providerId === atlasProviderIdFilter.trim())
      && atlasCandidateIds.has(edge.from) && atlasCandidateIds.has(edge.to);
  });
  const atlasConnectedIds = new Set([atlasRootId]);
  for (const edge of atlasVisibleEdges) { atlasConnectedIds.add(edge.from); atlasConnectedIds.add(edge.to); }
  const atlasVisibleNodes = atlasCandidateNodes.filter(item => atlasConnectedIds.has(item.id));
  const atlasNodePositions = new Map<string, { x: number; y: number }>([[atlasRootId, { x: 50, y: 50 }]]);
  for (const depth of [1, 2, 3]) {
    const group = atlasVisibleNodes.filter(item => item.depth === depth);
    group.forEach((item, index) => {
      const angle = (index / Math.max(group.length, 1)) * Math.PI * 2 - Math.PI / 2 + (depth % 2) * 0.12;
      const radius = Math.min(45, 23 + (depth - 1) * 20);
      atlasNodePositions.set(item.id, { x: 50 + Math.cos(angle) * radius, y: 50 + Math.sin(angle) * radius });
    });
  }
  const atlasNodes = atlasVisibleNodes.map(item => ({
    ...item,
    x: atlasNodePositions.get(item.id)?.x ?? 50,
    y: atlasNodePositions.get(item.id)?.y ?? 50,
  }));
  const atlasVisibleRelationships = (atlasResult?.relationships ?? []).filter(item =>
    (atlasCategoryFilter === "All" || item.category === atlasCategoryFilter)
    && (atlasSourceFilter === "All" || item.sourceKind === atlasSourceFilter)
    && (atlasProviderFilter === "All" || item.provider === atlasProviderFilter)
    && (!atlasProviderIdFilter.trim() || item.providerId === atlasProviderIdFilter.trim())
    && (atlasRelationshipFilter === "All" || item.relationType.toLocaleLowerCase("en-US").includes(atlasRelationshipFilter.toLocaleLowerCase("en-US")))
    && (!atlasEvidenceFilter.trim() || (item.evidence ?? "").toLocaleLowerCase("en-US").includes(atlasEvidenceFilter.trim().toLocaleLowerCase("en-US"))),
  );

  if (initialLoading) return <main className="boot-screen"><span className="boot-mark">L.</span><span className="spinner" /><p>Establishing a secure session</p><small>LEMEGETON / CONTROL PLANE</small></main>;

  return <div className="app-shell">
    <aside className={"sidebar" + (mobileNav ? " mobile-open" : "")} id="sidebar">
      <a className="brand" href="/" aria-label="Lemegeton dashboard home"><span className="brand-mark">L.</span><span className="brand-copy"><strong>LEMEGETON</strong><small>BOT CONTROL</small></span></a>
      <div className="sidebar-rule" />
      <p className="nav-label">WORKSPACE <span>/ 01</span></p>
      <nav className="main-nav" aria-label="Dashboard navigation">
        {PAGES.map((item) => <button key={item.id} type="button" className={"nav-item" + (page === item.id ? " active" : "")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}>
          <span className="nav-glyph" aria-hidden="true"><Icon name={item.icon} size={17} /></span><span>{item.label}</span>
          {item.id === "commands" ? <span className="nav-count">{commands.length || "—"}</span> : null}
          {item.id === "atlas" ? <span className="nav-count">↗</span> : null}
        </button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-system"><span className={"signal-dot" + (runtimeOnline ? " online" : "")} /><div><strong>{system.status === "unknown" ? "Bot signal unavailable" : bot.ready ? "Gateway connected" : "Bot connecting"}</strong><small>{system.status === "unknown" ? "STATUS / UNKNOWN" : "SYSTEM / " + runtimeStatus}</small></div></div>
      <button className="signout" type="button" onClick={() => void logout()}>Sign out <span aria-hidden="true">↗</span></button>
    </aside>
    <button className={"mobile-scrim" + (mobileNav ? " active" : "")} aria-label="Close navigation" onClick={() => setMobileNav(false)} />
    <main className="main">
      <header className="topbar">
        <button className="icon-button mobile-menu" type="button" aria-label="Open navigation" aria-expanded={mobileNav} onClick={() => setMobileNav((value) => !value)}><Icon name="menu" size={17} /></button>
        <div className="breadcrumb"><span>CONTROL</span><span className="breadcrumb-divider">/</span><strong>{selectedPage.label}</strong></div>
        <div className="topbar-right">
          <label className="guild-control"><span>SERVER</span><select value={guildId} onChange={(event) => selectGuild(event.target.value)} aria-label="Select Discord server" disabled={!guilds.length}>
            {!guilds.length ? <option value="">No manageable servers</option> : guilds.map((guild) => <option key={guild.id} value={guild.id}>{guild.name}</option>)}
          </select></label>
          <button className={"icon-button" + (refreshing ? " spinning" : "")} type="button" onClick={() => void refreshData(guildId)} aria-label="Refresh dashboard" title="Refresh dashboard" disabled={!guildId || refreshing}><Icon name="refresh" size={17} /></button>
          <div className="account" aria-label="Signed-in Discord account"><span className="avatar">{(user?.global_name || user?.username || "?").slice(0, 1).toUpperCase()}</span><span className="account-copy"><strong>{user?.global_name || user?.username || "Discord account"}</strong><small>DISCORD / VERIFIED</small></span></div>
        </div>
      </header>
      <div className="braille-band" aria-hidden="true">
        <span className="braille-track braille-track-a">⠿⠗⠿⠿⠶⠿⠿⠾⠿⠿⠿⠷⠿⠿⠿⠿⠿⠿</span>
        <span className="braille-band-label">LEMEGETON / LIVE SIGNAL</span>
        <span className="braille-track braille-track-b">⠿⠿⠷⠿⠿⠿⠿⠗⠿⠿⠶⠿⠿⠿⠾⠿⠿</span>
      </div>

      {page === "overview" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Bot <span>overview.</span></>} subtitle={selectedPage.subtitle} actions={<><Button onClick={() => navigate("audit")}>View activity <span aria-hidden="true">↗</span></Button><Button tone="primary" onClick={() => void synchronizeCommands()} disabled={operationBusy || !guildId}>Publish commands <span aria-hidden="true">↗</span></Button></>} />
        <div className="status-strip"><span className="strip-signal" /><span>STATUS / {runtimeStatus}</span><span className="strip-separator">—</span><span>{system.status === "unknown" ? (system.reason || "Live bot data is unavailable.") : bot.ready ? "The Discord gateway reports a live connection." : "The bot process is reachable and waiting for gateway readiness."}</span><time>{updatedAt ? new Date(updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "NOT CHECKED"}</time></div>
        <div className="metric-grid">
          <article className="metric"><div className="metric-label">MANAGED COMMANDS <span>01</span></div><strong className="metric-value">{system.status === "unknown" ? "—" : number(commands.length)}</strong><p><span>{system.status === "unknown" ? "Live state unavailable" : number(enabled) + " enabled"}</span><span className="metric-dot">·</span><span>{system.status === "unknown" ? "Reconnect bot bridge" : number(disabled) + " disabled"}</span></p></article>
          <article className="metric"><div className="metric-label">SERVER MEMBERS <span>02</span></div><strong className="metric-value">{number(bot.member_count)}</strong><p>Selected Discord server</p></article>
          <article className="metric"><div className="metric-label">BOT GUILDS <span>03</span></div><strong className="metric-value">{system.status === "unknown" ? "—" : number(bot.guild_count ?? system.guild_count)}</strong><p>Visible to your account</p></article>
          <article className="metric"><div className="metric-label">GATEWAY LATENCY <span>04</span></div><strong className="metric-value">{bot.latency_ms == null || system.status === "unknown" ? "—" : Math.round(bot.latency_ms)}<small>ms</small></strong><p>{bot.ready ? "Gateway connected" : "Waiting for gateway"}</p></article>
        </div>
        <div className="content-grid">
          <Panel eyebrow="PROCESS STATUS" title="Runtime signal" index="A / 04" className="panel-large">
            <div className="runtime-body"><div className={"runtime-mark" + (runtimeOnline ? " is-online" : "")}><span>⠿</span><i /></div><div className="runtime-copy"><p className="runtime-state">{system.status === "unknown" ? (lastKnown ? "Last known / " + String(lastKnown.status || "Unknown") : "Live status unknown") : bot.ready ? "Discord gateway connected" : "Discord gateway connecting"}</p><p className="muted">{system.status === "unknown" ? (system.reason || "The bot bridge is unreachable. Live control operations may be unavailable.") : "Dashboard HTTP availability and Discord gateway health are tracked separately."}</p><div className="runtime-flags"><StatusPill ok={Boolean(bot.ready) && system.status !== "unknown"}>GATEWAY / {system.status === "unknown" ? "UNKNOWN" : bot.ready ? "ONLINE" : "NOT READY"}</StatusPill><StatusPill ok={system.status !== "unknown"}>BRIDGE / {system.status === "unknown" ? "UNREACHABLE" : "CONNECTED"}</StatusPill></div></div></div>
            <div className="runtime-data"><div><small>PROCESS UPTIME</small><strong>{duration(system.uptime_seconds)}</strong></div><div><small>NODE RUNTIME</small><strong>{system.node_version || "Unavailable"}</strong></div><div><small>COMMAND REGISTRY</small><strong>{number(system.extensions?.length ?? 0)}</strong></div></div>
            {system.status === "unknown" && lastKnown?.observed_at ? <p className="footnote compact">Last observed {timestamp(Number(lastKnown.observed_at))}. This is cached status, not a live reading.</p> : null}
          </Panel>
          <Panel eyebrow="RECENT CHANGES" title="Audit history" action={<button className="text-button" type="button" onClick={() => navigate("audit")}>All events ↗</button>}>
            <ActivityList entries={audit.slice(0, 5)} />
          </Panel>
          <Panel eyebrow="EFFECTIVE CONFIGURATION" title="Command access">
            <div className="distribution-label"><strong>{system.status === "unknown" ? "—" : percent + "%"}</strong><span>of managed commands enabled</span></div><svg className="distribution-track" viewBox="0 0 100 6" role="img" aria-label="Share of managed commands enabled"><rect className="distribution-track-bg" width="100" height="6" rx="3" /><rect className="distribution-track-fill" width={system.status === "unknown" ? 0 : percent} height="6" rx="3" /></svg><div className="distribution-meta"><span>Enabled {system.status === "unknown" ? "—" : enabled}</span><span>Disabled {system.status === "unknown" ? "—" : disabled}</span></div>
          </Panel>
          <Panel eyebrow="SELECTED SERVER" title="Guild context" index="G / 01">
            <dl className="definition-list"><div><dt>Server</dt><dd>{currentGuild?.name || "—"}</dd></div><div><dt>Guild ID</dt><dd className="mono">{guildId || "—"}</dd></div><div><dt>Your permission</dt><dd>{currentGuild?.administrator ? "Administrator" : user ? "Manage Server" : "Unknown"}</dd></div><div><dt>Bot membership</dt><dd>{currentGuild ? "Connected" : "Unavailable"}</dd></div></dl>
          </Panel>
        </div>
      </section> : null}

      {page === "commands" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Command <span>access.</span></>} subtitle="Changes apply to this guild and are confirmed only after the live bot synchronizes with Discord. Protected system commands stay enabled." actions={<><Button onClick={() => void resetCommands()} disabled={operationBusy || !guildId}>Server defaults</Button><Button tone="primary" onClick={() => void synchronizeCommands()} disabled={operationBusy || !guildId}>Publish commands ↗</Button></>} />
        <div className="command-toolbar"><label className="search-field"><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, description, category…" autoComplete="off" /></label><label className="filter-control"><span>CATEGORY</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="All">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label className="filter-control"><span>STATE</span><select value={commandState} onChange={(event) => setCommandState(event.target.value)}><option value="All">All states</option><option value="Enabled">Enabled</option><option value="Disabled">Disabled</option><option value="Protected">Protected</option></select></label></div>
        <div className="command-summary"><span>{filteredCommands.length} of {commands.length} registered commands</span><span>PER-GUILD CONFIGURATION</span></div>
        <div className="command-list">{commands.length === 0 ? (commandError ? <Empty>{commandError}</Empty> : refreshing ? <Empty loading>Reading the live command registry…</Empty> : <Empty>No dashboard-managed commands were returned.</Empty>) : filteredCommands.length === 0 ? <Empty>No commands match this search and filter.</Empty> : filteredCommands.map((command) => <article className="command-row" key={command.fullname}>
          <div className="command-main"><a className="command-name command-name-link" href={commandGuideUrl(command)} target="_blank" rel="noreferrer" aria-label={"Open usage guide for /" + (command.fullname || command.name)} title="Open the relevant command guide"><span className="command-prefix">/</span>{command.fullname || command.name}<span className="command-link-glyph" aria-hidden="true">↗</span></a><p className="command-description">{command.description || "No description provided."}</p><div className="command-tags"><span className="tag">{command.section || "Other"}</span><span className="tag">{command.type || "slash"}</span><span className="tag">{command.scope || "guild"}</span>{command.protected ? <span className="tag tag-protected">Protected</span> : null}{command.required_permissions ? <span className="tag">Discord permission gate</span> : null}</div><div className="command-actions"><button className="command-copy" type="button" onClick={() => void copyCommandInvocation(command)} title={"Copy /" + (command.fullname || command.name)} aria-label={"Copy invocation for /" + (command.fullname || command.name)}>▣ <span>Copy command</span></button><a className="command-guide" href={commandGuideUrl(command)} target="_blank" rel="noreferrer">Usage guide <span aria-hidden="true">↗</span></a><button className="command-access-open" type="button" onClick={() => void openCommandAccess(command)} disabled={Boolean(command.protected) || accessLoading || accessSaving} aria-label={"Configure access for /" + command.fullname}><span aria-hidden="true">◇</span> Access rules</button></div></div>
          <div className="command-state"><StatusPill ok={command.enabled && !command.protected}>{command.protected ? "Protected / always on" : command.enabled ? "Enabled" : "Disabled"}</StatusPill></div>
          <button className={"switch" + (command.enabled ? " checked" : "")} role="switch" type="button" aria-checked={Boolean(command.enabled)} aria-label={"Toggle " + command.fullname} disabled={Boolean(command.protected) || savingCommands || operationBusy} onClick={() => toggleCommand(command)}><span /></button>
        </article>)}</div>
        <p className="footnote">Changes remain local until saved. The bot rechecks the server revision before publishing; protected commands cannot be changed.</p>
        {accessTarget ? <div className="access-overlay">
          <section className="access-dialog" role="dialog" aria-modal="true" aria-labelledby="command-access-title">
            <div className="access-heading"><div><p className="eyebrow">COMMAND POLICY</p><h2 id="command-access-title">Access for <span>/{accessTarget}</span></h2><p>Rules are checked by the bot on every command and component interaction.</p></div><button type="button" className="access-close" onClick={closeCommandAccess} aria-label="Close access editor">×</button></div>
            {accessLoading ? <Empty loading>Loading this server’s roles and channels…</Empty> : accessOptions && accessDraft ? <>
              <div className="access-grid">
                <div className="access-field"><label htmlFor="access-role-mode">WHO CAN USE IT</label><select id="access-role-mode" value={accessDraft.role_mode} onChange={event => setAccessDraft(current => current ? { ...current, role_mode: event.target.value as CommandAccessPolicy["role_mode"] } : current)}><option value="everyone">Everyone</option><option value="include">Only selected roles</option><option value="exclude">Everyone except selected roles</option></select><select aria-label="Select roles" multiple size={7} value={accessDraft.role_ids} onChange={event => setAccessDraft(current => current ? { ...current, role_ids: Array.from(event.currentTarget.selectedOptions, option => option.value) } : current)}>{accessOptions.roles.map(role => <option key={role.id} value={role.id}>{role.name}</option>)}</select><small>With “Only selected roles”, an empty selection blocks everyone. Excluded roles are denied.</small></div>
                <div className="access-field"><label htmlFor="access-channel-mode">WHERE CAN IT RUN</label><select id="access-channel-mode" value={accessDraft.channel_mode} onChange={event => setAccessDraft(current => current ? { ...current, channel_mode: event.target.value as CommandAccessPolicy["channel_mode"] } : current)}><option value="all">All supported channels</option><option value="include">Only selected channels</option><option value="exclude">All except selected channels</option></select><select aria-label="Select channels" multiple size={7} value={accessDraft.channel_ids} onChange={event => setAccessDraft(current => current ? { ...current, channel_ids: Array.from(event.currentTarget.selectedOptions, option => option.value) } : current)}>{accessOptions.channels.map(channel => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}</select><small>Only server text-capable channels are listed. An empty include list denies all channels.</small></div>
              </div>
              <div className="access-footer"><span>{accessDraftDirty ? "Unsaved policy changes" : "Policy is up to date"}</span><div><button type="button" className="command-reset" onClick={resetCommandAccess} disabled={!accessDraftDirty || accessSaving}>Reset</button><button type="button" className="command-save" onClick={() => void saveCommandAccess()} disabled={!accessDraftDirty || accessSaving}>{accessSaving ? "Saving…" : "Save Changes"}</button></div></div>
            </> : <div className="access-load-error"><p>Role and channel settings could not be loaded.</p><button type="button" className="command-reset" onClick={closeCommandAccess}>Close</button></div>}
          </section>
        </div> : null}
        {commandDraftDirty ? <div className="command-savebar" role="region" aria-label="Unsaved command changes">
          <span><strong>Unsaved changes</strong><small>{commands.filter(item => !item.protected && savedCommands.find(saved => saved.fullname === item.fullname)?.enabled !== item.enabled).length} command settings changed</small></span>
          <div><button type="button" className="command-reset" onClick={resetCommandDraft} disabled={savingCommands}>Reset</button><button type="button" className="command-save" onClick={() => void saveCommandDraft()} disabled={savingCommands || !commandRevision}>{savingCommands ? "Saving…" : "Save Changes"}</button></div>
        </div> : null}
      </section> : null}

            {page === "atlas" ? <section className="page">
        <SectionHeading
          eyebrow={selectedPage.eyebrow}
          title={<>Knowledge <span>Atlas.</span></>}
          subtitle="Follow confirmed provider relationships and server-approved community links. Select a connected node to expand another local neighborhood."
          actions={<StatusPill ok={Boolean(atlasResult)}>{atlasResult ? atlasResult.relationships.length + " CONNECTIONS" : "GUILD-SCOPED"}</StatusPill>}
        />
        <Panel eyebrow="FIND A MEDIA NODE" title="Explore a title">
          <form className="atlas-search" onSubmit={(event) => { event.preventDefault(); void searchAtlas(); }}>
            <label className="atlas-search-title">
              <span>MEDIA TITLE</span>
              <input
                type="search"
                value={atlasTitle}
                onChange={(event) => setAtlasTitle(event.target.value)}
                maxLength={256}
                placeholder="Search a title, for example Frieren"
                autoComplete="off"
                required
              />
            </label>
            <label className="filter-control atlas-category">
              <span>CATEGORY</span>
              <select value={atlasCategory} onChange={(event) => setAtlasCategory(event.target.value)}>
                <option value="ANIME">Anime</option>
                <option value="MANGA">Manga</option>
                <option value="LIGHT_NOVEL">Light novel</option>
                <option value="WEBNOVEL">Webnovel</option>
                <option value="BOOK">Book</option>
                <option value="MOVIE">Film</option>
                <option value="TV">Television</option>
                <option value="GAME">Video game</option>
                <option value="CREATOR">Creator</option>
                <option value="FRANCHISE">Franchise</option>
                <option value="ARCHIVE_ENTRY">Archive entry</option>
                <option value="ARCHIVE_COLLECTION">Archive collection</option>
                <option value="DISCUSSION">Discussion</option>
                <option value="ACTIVITY">Community activity</option>
              </select>
            </label>
            <Button tone="primary" type="submit" disabled={atlasLoading || !guildId}>
              {atlasLoading ? "Mapping…" : "Explore connections ↗"}
            </Button>
          </form>
          {atlasError ? <p className="atlas-error" role="alert">{atlasError}</p> : null}
        </Panel>

        {atlasLoading && !atlasResult ? <Panel eyebrow="GRAPH PROJECTION" title="Building the local graph"><Empty loading>Looking up authorized relationships for this server…</Empty></Panel> : null}
        {atlasResult ? <>
          <Panel eyebrow={"MULTI-HOP GRAPH / " + String(atlasNodes.length + 1) + " NODES"} title={atlasResult.root.title} index={atlasResult.root.category}>
            <p className="atlas-explainer">Explore up to two recorded relationship steps from this title. Every community-sourced edge is looked up within the selected server; provider facts and recommendations remain separately labelled.</p>
            <div className="atlas-tools">
              <label className="filter-control"><span>MEDIA TYPE</span><select value={atlasCategoryFilter} onChange={(event) => setAtlasCategoryFilter(event.target.value)}><option value="All">All categories</option>{atlasCategories.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select></label>
              <label className="filter-control"><span>PROVENANCE</span><select value={atlasSourceFilter} onChange={(event) => setAtlasSourceFilter(event.target.value)}><option value="All">All sources</option><option value="provider">Provider</option><option value="recommendation">Recommendation</option><option value="community">Community</option></select></label>
              <label className="filter-control"><span>PROVIDER IDENTITY</span><select value={atlasProviderFilter} onChange={(event) => setAtlasProviderFilter(event.target.value)}><option value="All">All providers</option>{atlasProviders.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
              <label className="filter-control"><span>PROVIDER RECORD ID</span><input type="search" value={atlasProviderIdFilter} onChange={(event) => setAtlasProviderIdFilter(event.target.value)} maxLength={128} placeholder="Stable provider ID" /></label>
              <label className="filter-control"><span>RELATIONSHIP</span><select value={atlasRelationshipFilter} onChange={(event) => setAtlasRelationshipFilter(event.target.value)}><option value="All">All relations</option><option value="adaptation">Adaptation</option><option value="franchise">Franchise</option><option value="sequel">Sequel</option><option value="prequel">Prequel</option><option value="related">Related</option><option value="discussed in">Discussed in</option><option value="included in">Included in</option></select></label>
              <label className="filter-control atlas-evidence-filter"><span>EDGE EVIDENCE</span><input type="search" value={atlasEvidenceFilter} onChange={(event) => setAtlasEvidenceFilter(event.target.value)} maxLength={200} placeholder="Search evidence or source text" /></label>
              <div className="atlas-path-tools"><label className="filter-control"><span>FIND PATH TO</span><select value={atlasPathTarget} onChange={(event) => setAtlasPathTarget(event.target.value)}><option value="">Choose a connected node</option>{atlasVisibleNodes.map(node => <option key={node.id} value={node.id}>{node.title}</option>)}</select></label><Button disabled={!atlasPathTarget || atlasLoading} onClick={() => {
                const target = atlasVisibleNodes.find(node => node.id === atlasPathTarget);
                if (target) void searchAtlas(atlasResult.root.title, atlasResult.root.category, atlasResult.root.url, {
                  provider: atlasResult.root.provider ?? "", provider_id: atlasResult.root.providerId ?? "",
                  target_title: target.title, target_category: target.category, target_url: target.url ?? "",
                  target_provider: target.provider ?? "", target_provider_id: target.providerId ?? "",
                  ...atlasFilters(),
                });
              }}>Find shortest path</Button></div>
              <div className="atlas-export-tools"><span>EXPORT GRAPH</span><Button disabled={Boolean(atlasExportBusy)} onClick={() => void downloadAtlas("json")}>{atlasExportBusy === "json" ? "Preparing…" : "JSON"}</Button><Button disabled={Boolean(atlasExportBusy)} onClick={() => void downloadAtlas("svg")}>{atlasExportBusy === "svg" ? "Preparing…" : "SVG"}</Button><Button disabled={Boolean(atlasExportBusy)} onClick={() => void downloadAtlas("png")}>{atlasExportBusy === "png" ? "Preparing…" : "PNG"}</Button></div>
              <div className="atlas-zoom"><span>ZOOM</span><Button onClick={() => setAtlasZoom((value) => Math.max(80, value - 10))} disabled={atlasZoom <= 80} aria-label="Zoom out">−</Button><strong>{atlasZoom}%</strong><Button onClick={() => setAtlasZoom((value) => Math.min(140, value + 10))} disabled={atlasZoom >= 140} aria-label="Zoom in">+</Button><Button onClick={() => setAtlasZoom(100)}>Fit</Button></div>
            </div>
            {atlasNodes.length ? <div className="atlas-graph" role="group" aria-label={"Multi-hop media relationships connected to " + atlasResult.root.title}>
              <div className="atlas-graph-content" style={{ transform: "scale(" + atlasZoom / 100 + ")" }}>
                <svg className="atlas-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  {atlasVisibleEdges.map((edge, index) => {
                    const from = atlasNodePositions.get(edge.from);
                    const to = atlasNodePositions.get(edge.to);
                    return from && to ? <line key={edge.from + edge.to + edge.sourceKind + index}
                      x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                      className={"atlas-edge " + edge.sourceKind} /> : null;
                  })}
                </svg>
                <div className="atlas-root-node">
                  <span className="atlas-node-category">{atlasResult.root.category.replaceAll("_", " ")}</span>
                  <strong>{atlasResult.root.title}</strong>
                  {atlasResult.root.url ? <a href={atlasResult.root.url} target="_blank" rel="noreferrer">Provider ↗</a> : null}
                </div>
                {atlasNodes.map((node) => <button
                  key={node.id}
                  type="button"
                  className={"atlas-node " + (node.sourceKind || "provider")}
                  style={{ left: node.x + "%", top: node.y + "%" }}
                  title={node.title + " · " + (node.relationType || "Connected media")}
                  onClick={() => void searchAtlas(node.title, node.category, node.url, { provider: node.provider ?? "", provider_id: node.providerId ?? "" })}
                  disabled={atlasLoading}
                >
                  <span>LEVEL {node.depth} · {node.category.replaceAll("_", " ")}</span>
                  <strong>{node.title}</strong>
                </button>)}
              </div>
            </div> : <Empty>{atlasResult.graph?.truncated ? "The graph was bounded before any visible nodes remained. Adjust the filters or explore another title." : atlasResult.relationships.length ? "No connections match these filters." : "No connections have been recorded for this title yet. Explore another title or check back after supported provider relationships are indexed."}</Empty>}
            {atlasResult.clusters?.length ? <div className="atlas-clusters"><span>MEDIA CLUSTERS</span>{atlasResult.clusters.map(cluster => <button type="button" key={cluster.category} onClick={() => setAtlasCategoryFilter(cluster.category)}>{cluster.category.replaceAll("_", " ")} <strong>{cluster.count}</strong></button>)}</div> : null}
            {atlasResult.path?.edges.length ? <p className="atlas-path-summary">Shortest path: {atlasResult.path.nodes.map(node => node.title).join(" → ")}</p> : null}
            {atlasResult.graph?.truncated ? <p className="footnote compact">This graph reached its node limit. Explore a connected node to inspect its neighborhood.</p> : null}
            <div className="atlas-legend">
              <span><i className="provider" /> Provider-confirmed</span>
              <span><i className="recommendation" /> Recommendation</span>
              <span><i className="community" /> Community-sourced</span>
            </div>
          </Panel>
          {atlasResult.relationships.length ? <Panel eyebrow="RECORDED EDGES" title="Connections" index={atlasVisibleRelationships.length + " SHOWN"}>
            <div className="atlas-connections">
              {atlasVisibleRelationships.map((relation, index) => <article className="atlas-connection" key={relation.title + relation.category + index}>
                <div className="atlas-connection-main">
                  <span className={"atlas-source " + relation.sourceKind}>{relation.sourceKind.replaceAll("_", " ")}</span>
                  <strong>{relation.title}</strong>
                  <small>{relation.category.replaceAll("_", " ")} · {relation.relationType}</small>
                  <small>Source: {relation.source}</small>
                  {relation.provider && relation.providerId ? <small>Provider ID: {relation.provider}:{relation.providerId}</small> : null}
                  {relation.evidence ? <small>Evidence: {relation.evidence}</small> : null}
                </div>
                <div className="atlas-connection-actions">
                  <Button onClick={() => void searchAtlas(relation.title, relation.category, relation.url)} disabled={atlasLoading}>Open node ↗</Button>
                  {relation.url ? <a className="atlas-provider-link" href={relation.url} target="_blank" rel="noreferrer">Source record ↗</a> : null}
                </div>
              </article>)}
            </div>
          </Panel> : null}
        </> : !atlasLoading ? <Panel eyebrow="GRAPH PROJECTION" title="Start with a media title"><Empty>The Atlas shows direct recorded relationships for the selected title. Community relationships stay scoped to this server.</Empty></Panel> : null}
      </section> : null}

      {page === "extensions" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Loaded <span>extensions.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadSystem()} disabled={refreshing}>Refresh status ↻</Button>} />
        <Panel eyebrow="ACTIVE PROCESS" title="Extension inventory" index={(system.extensions || []).length + " REPORTED"}>
          {system.extensions?.length ? <div className="extension-list">{system.extensions.map((name) => <div className="extension-row" key={name}><code>{name}</code><StatusPill ok>Loaded / live process</StatusPill></div>)}</div> : <Empty loading={refreshing}>{system.status === "unknown" ? "The live extension inventory is unavailable." : "No loaded extensions were reported."}</Empty>}
        </Panel>
        <p className="footnote">An extension appearing here means the current bot process reports it as loaded. Runtime load/unload/reload controls are intentionally omitted to avoid interrupting core bot operations.</p>
      </section> : null}

      {page === "audit" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Nothing <span>unaccounted.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadAudit(guildId)} disabled={refreshing}>Refresh history ↻</Button>} />
        <Panel eyebrow="PERSISTED EVENTS" title="Audit trail" index="25 MOST RECENT"><ActivityList entries={audit} /></Panel>
      </section> : null}

      {page === "diagnostics" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Under the <span>surface.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadSystem()} disabled={refreshing}>Check now ↻</Button>} />
        <div className="content-grid"><Panel eyebrow="STATUS SNAPSHOT" title="Runtime details" index="LIVE"><dl className="definition-list diagnostic-list"><div><dt>Dashboard bridge</dt><dd><StatusPill ok={system.status !== "unknown"}>{system.status === "unknown" ? "Unreachable" : "Responding"}</StatusPill></dd></div><div><dt>Discord gateway</dt><dd>{system.ready ? "Connected" : "Not ready"}</dd></div><div><dt>Gateway latency</dt><dd>{system.latency_ms == null ? "Unavailable" : Math.round(system.latency_ms) + " ms"}</dd></div><div><dt>Connected bot guilds</dt><dd>{number(system.guild_count)}</dd></div><div><dt>Registered commands</dt><dd>{number(system.extensions?.length ?? 0)}</dd></div><div><dt>Node runtime</dt><dd>{system.node_version || "Unavailable"}</dd></div><div><dt>Process uptime</dt><dd>{duration(system.uptime_seconds)}</dd></div><div><dt>Observation time</dt><dd>{timestamp(system.observed_at)}</dd></div>{lastKnown ? <><div><dt>Last-known status</dt><dd>{String(lastKnown.status || "Unknown")}</dd></div><div><dt>Last-known observation</dt><dd>{timestamp(Number(lastKnown.observed_at))}</dd></div></> : null}</dl></Panel><Panel eyebrow="BOUNDARIES" title="Service availability"><div className="note-block"><strong>Two separate signals.</strong><p>Dashboard HTTP availability does not mean the Discord gateway is connected. Cached observations are labelled and never presented as live status.</p></div><div className="note-block"><strong>Control operations require the bot.</strong><p>When the bridge or Discord synchronization is unavailable, command changes fail safely rather than showing false success.</p></div></Panel></div>
      </section> : null}

      {page === "logs" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Logs, without <span>guesswork.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadLogs(logFile)} disabled={refreshing}>Refresh log ↻</Button>} />
        <Panel eyebrow="FILE READER" title={logName} className="log-panel" action={<label className="filter-control"><span>LOG SOURCE</span><select value={logFile} onChange={(event) => setLogFile(event.target.value)}><option value="bot.log">bot.log</option><option value="dashboard.log">dashboard.log</option></select></label>}><pre className="log-output" tabIndex={0}>{logText || "Loading log output…"}</pre></Panel>
      </section> : null}

      {page === "integrations" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Integration <span>status.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadIntegrations()} disabled={refreshing}>Refresh ↻</Button>} />
        <Panel eyebrow="BOT-WIDE CONFIGURATION" title="Provider availability" index="OWNER ONLY">
          {integrations.length ? <div className="extension-list">{integrations.map((item, index) => <div className="extension-row" key={(item.name || "integration") + index}><div><code>{item.name || "Integration"}</code><p className="command-description">{item.detail || "No additional details."}</p></div><StatusPill ok={Boolean(item.configured)}>{item.configured ? "Configured" : "Not configured"}</StatusPill></div>)}</div> : <Empty>Integration information is unavailable, or no services were reported.</Empty>}
        </Panel>
        <p className="footnote">Only configuration presence is displayed. Credential values and tokens are never returned to the browser.</p>
      </section> : null}

      {page === "database" ? <section className="page">
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>State that <span>survives.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => void loadDatabase()} disabled={refreshing}>Refresh ↻</Button>} />
        <Panel eyebrow="PERSISTED RESOURCES" title="Storage overview"><div className="table-scroll"><table><thead><tr><th>RESOURCE</th><th>PURPOSE / DETAILS</th><th>STATE</th></tr></thead><tbody>{resources.length ? resources.map((row, index) => <tr key={(row.name || "resource") + index}><td>{row.name || "—"}</td><td>{row.purpose || "—"}<small>{row.detail || ""}</small></td><td><StatusPill ok={String(row.state || "").toLowerCase() === "available"}>{row.state || "Unknown"}</StatusPill></td></tr>) : <tr><td colSpan={3}><Empty>Persistence resources are unavailable or none were reported.</Empty></td></tr>}</tbody></table></div></Panel>
      </section> : null}

      <footer className="page-footer"><span>LEMEGETON / CONTROL PLANE</span><span>{system.status === "unknown" ? "LIVE BOT DATA UNAVAILABLE" : "PRIVATE SESSION · DATA REFRESHED"}</span></footer>
    </main>
    <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">{toasts.map((toast) => <div key={toast.id} className={"toast" + (toast.error ? " error" : "")}><span>{toast.error ? "!" : "✓"}</span>{toast.message}<button type="button" aria-label="Dismiss notification" onClick={() => setToasts((items) => items.filter((item) => item.id !== toast.id))}>×</button></div>)}</div>
    {confirmation ? <div className="modal-scrim" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><p className="eyebrow">CONFIRM ACTION</p><h2 id="confirm-title">{confirmation.title}</h2><p>{confirmation.message}</p><div className="dialog-actions"><Button onClick={() => settleConfirmation(false)}>Cancel</Button><Button tone="primary" onClick={() => settleConfirmation(true)} disabled={operationBusy}>{confirmation.actionLabel}</Button></div></section></div> : null}
  </div>;
}

function ActivityList(props: { entries: AuditEntry[] }) {
  if (!props.entries.length) return <Empty>No audit events have been recorded for this server yet.</Empty>;
  return <div className="activity-list">{props.entries.map((entry, index) => <div className="activity-row" key={(entry.ts || "event") + index}><span className="activity-glyph" aria-hidden="true">·</span><div className="activity-copy"><strong>{String(entry.action || "Administrative action").replaceAll("_", " ")}</strong><small>{entry.details || "No additional details"} · by {entry.actor_name || entry.actor_id || "Unknown account"}</small></div><time className="activity-time" title={entry.ts || ""}>{timeAgo(entry.ts)}</time></div>)}</div>;
}

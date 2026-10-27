import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Page = "overview" | "commands" | "extensions" | "audit" | "diagnostics" | "logs" | "integrations" | "database";
type User = { id: string; username: string; global_name?: string | null; avatar?: string | null };
type Guild = { id: string; name: string; icon?: string | null; administrator?: boolean; member_count?: number | null };
type Command = { fullname: string; name?: string; description?: string; section?: string; type?: string; scope?: string; enabled: boolean; protected?: boolean; required_permissions?: string | boolean | null };
type AuditEntry = { action?: string; details?: string; actor_name?: string; actor_id?: string; ts?: string };
type Overview = { bot?: { ready?: boolean; status?: string; latency_ms?: number | null; member_count?: number | null; guild_count?: number | null; extension_count?: number | null } };
type SystemStatus = { status?: string; ready?: boolean; reason?: string; observed_at?: number; last_known?: Record<string, any> | null; uptime_seconds?: number | null; python_version?: string; extensions?: string[]; latency_ms?: number | null; guild_count?: number | null; extension_count?: number | null };
type Resource = { name?: string; purpose?: string; detail?: string; state?: string };
type Integration = { name?: string; detail?: string; configured?: boolean };
type Toast = { id: number; message: string; error: boolean };
type Confirmation = { title: string; message: string; actionLabel: string; run: () => Promise<void> };
type Bootstrap = { user: User; guilds: Guild[]; csrf_token: string; selected_guild_id?: string };
type CommandResponse = { commands: Command[] };
type ListResponse<T> = { entries?: T[] };

const PAGES: { id: Page; label: string; glyph: string; eyebrow: string; subtitle: string }[] = [
  { id: "overview", label: "Overview", glyph: "◫", eyebrow: "LIVE CONTROL / 01", subtitle: "A clear view of bot health and the current server configuration." },
  { id: "commands", label: "Commands", glyph: "⌘", eyebrow: "COMMAND REGISTRY / 02", subtitle: "Control registered slash commands, scoped to the selected Discord server." },
  { id: "extensions", label: "Extensions", glyph: "▦", eyebrow: "BOT MODULES / 03", subtitle: "Review the extension inventory reported by the live bot process." },
  { id: "audit", label: "Audit history", glyph: "◷", eyebrow: "CHANGE RECORD / 04", subtitle: "Review recorded dashboard configuration changes for this server." },
  { id: "diagnostics", label: "Diagnostics", glyph: "⌁", eyebrow: "HEALTH & TELEMETRY / 05", subtitle: "Inspect the bot gateway, runtime version, uptime, and last-known status." },
  { id: "logs", label: "Runtime logs", glyph: "≡", eyebrow: "RUNTIME OUTPUT / 06", subtitle: "Read recent operational logs. This view is restricted to dashboard owners." },
  { id: "integrations", label: "Integrations", glyph: "⟷", eyebrow: "CONNECTED SERVICES / 07", subtitle: "Check configuration presence without exposing credential values." },
  { id: "database", label: "Persistence", glyph: "▤", eyebrow: "PERSISTENCE / 08", subtitle: "Inspect the saved resources supporting per-guild command settings." }
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
  if (name === "dashboard" || name === "dashboard-section-toggle") {
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
  const cancelled = new URLSearchParams(window.location.search).get("error") === "cancelled";
  return <main className="login-wrap">
    <div className="login-orbit orbit-one" aria-hidden="true" /><div className="login-orbit orbit-two" aria-hidden="true" />
    <section className="login-card">
      <a className="brand login-brand" href="/" aria-label="Lemegeton home"><span className="brand-mark">L.</span><span className="brand-copy"><strong>LEMEGETON</strong><small>CONTROL PLANE</small></span></a>
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
  const isLogin = window.location.pathname === "/login";
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [guildId, setGuildId] = useState("");
  const [csrf, setCsrf] = useState("");
  const [page, setPage] = useState<Page>("overview");
  const [overview, setOverview] = useState<Overview>({});
  const [system, setSystem] = useState<SystemStatus>({});
  const [commands, setCommands] = useState<Command[]>([]);
  const [commandError, setCommandError] = useState("");
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
  const [busyCommand, setBusyCommand] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [operationBusy, setOperationBusy] = useState(false);
  const refreshGeneration = useRef(0);
  const activeGuildIdRef = useRef("");

  const pushToast = useCallback((message: string, error = false) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((current) => [...current.slice(-3), { id, message, error }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4400);
  }, []);

  const currentGuild = useMemo(() => guilds.find((item) => String(item.id) === String(guildId)), [guilds, guildId]);
  const selectGuild = useCallback((nextId: string) => {
    if (!guilds.some((guild) => String(guild.id) === String(nextId))) return;
    activeGuildIdRef.current = String(nextId);
    refreshGeneration.current += 1;
    try { window.localStorage.setItem("lemegeton:selected-guild", String(nextId)); } catch { /* storage may be disabled */ }
    setGuildId(String(nextId));
    setOverview({});
    setCommands([]);
    setCommandError("");
    setBusyCommand("");
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
      setCommands(commandsResult.value.commands || []);
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
  }, [csrf, guildId, pushToast]);

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

  const toggleCommand = async (command: Command) => {
    if (!guildId || command.protected || busyCommand) return;
    const requestedGuild = guildId;
    setBusyCommand(command.fullname);
    const desired = !command.enabled;
    try {
      const result = await api<{ enabled?: boolean }>("/api/guilds/" + encodeURIComponent(requestedGuild) + "/commands/" + encodeURIComponent(command.fullname), csrf, {
        method: "PUT", body: JSON.stringify({ enabled: desired })
      });
      if (activeGuildIdRef.current !== requestedGuild) return;
      setCommands((items) => items.map((item) => item.fullname === command.fullname ? { ...item, enabled: result.enabled == null ? desired : Boolean(result.enabled) } : item));
      pushToast("/" + command.fullname + " " + (result.enabled == null ? (desired ? "enabled" : "disabled") : (result.enabled ? "enabled" : "disabled")) + " and synchronized.");
      void loadAudit(requestedGuild, true);
    } catch (error) { pushToast(errorMessage(error), true); }
    finally { if (activeGuildIdRef.current === requestedGuild) setBusyCommand(""); }
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

  const navigate = (next: Page) => { setPage(next); setMobileNav(false); };
  const selectedPage = PAGES.find((item) => item.id === page) || PAGES[0];

  if (isLogin) return <LoginPage />;

  const bot = overview.bot || {};
  const enabled = commands.filter((item) => item.enabled).length;
  const disabled = Math.max(0, commands.length - enabled);
  const percent = commands.length ? Math.round(enabled * 100 / commands.length) : 0;
  const runtimeStatus = system.status === "unknown" ? "UNKNOWN" : String(system.status || (bot.ready ? "online" : "connecting")).toUpperCase();
  const runtimeOnline = Boolean(bot.ready) && system.status !== "unknown";
  const lastKnown = system.last_known || null;

  if (initialLoading) return <main className="boot-screen"><span className="boot-mark">L.</span><span className="spinner" /><p>Establishing a secure session</p><small>LEMEGETON / CONTROL PLANE</small></main>;

  return <div className="app-shell">
    <aside className={"sidebar" + (mobileNav ? " mobile-open" : "")} id="sidebar">
      <a className="brand" href="/" aria-label="Lemegeton dashboard home"><span className="brand-mark">L.</span><span className="brand-copy"><strong>LEMEGETON</strong><small>BOT CONTROL</small></span></a>
      <div className="sidebar-rule" />
      <p className="nav-label">WORKSPACE <span>/ 01</span></p>
      <nav className="main-nav" aria-label="Dashboard navigation">
        {PAGES.map((item) => <button key={item.id} type="button" className={"nav-item" + (page === item.id ? " active" : "")} onClick={() => navigate(item.id)} aria-current={page === item.id ? "page" : undefined}>
          <span className="nav-glyph" aria-hidden="true">{item.glyph}</span><span>{item.label}</span>
          {item.id === "commands" ? <span className="nav-count">{commands.length || "—"}</span> : null}
        </button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-system"><span className={"signal-dot" + (runtimeOnline ? " online" : "")} /><div><strong>{system.status === "unknown" ? "Bot signal unavailable" : bot.ready ? "Gateway connected" : "Bot connecting"}</strong><small>{system.status === "unknown" ? "STATUS / UNKNOWN" : "SYSTEM / " + runtimeStatus}</small></div></div>
      <button className="signout" type="button" onClick={() => void logout()}>Sign out <span aria-hidden="true">↗</span></button>
    </aside>
    <button className={"mobile-scrim" + (mobileNav ? " active" : "")} aria-label="Close navigation" onClick={() => setMobileNav(false)} />
    <main className="main">
      <header className="topbar">
        <button className="icon-button mobile-menu" type="button" aria-label="Open navigation" aria-expanded={mobileNav} onClick={() => setMobileNav((value) => !value)}>☰</button>
        <div className="breadcrumb"><span>CONTROL</span><span className="breadcrumb-divider">/</span><strong>{selectedPage.label}</strong></div>
        <div className="topbar-right">
          <label className="guild-control"><span>SERVER</span><select value={guildId} onChange={(event) => selectGuild(event.target.value)} aria-label="Select Discord server" disabled={!guilds.length}>
            {!guilds.length ? <option value="">No manageable servers</option> : guilds.map((guild) => <option key={guild.id} value={guild.id}>{guild.name}</option>)}
          </select></label>
          <button className={"icon-button" + (refreshing ? " spinning" : "")} type="button" onClick={() => void refreshData(guildId)} aria-label="Refresh dashboard" title="Refresh dashboard" disabled={!guildId || refreshing}>↻</button>
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
            <div className="runtime-data"><div><small>PROCESS UPTIME</small><strong>{duration(system.uptime_seconds)}</strong></div><div><small>PYTHON RUNTIME</small><strong>{system.python_version || "Unavailable"}</strong></div><div><small>LOADED EXTENSIONS</small><strong>{number(system.extension_count ?? bot.extension_count)}</strong></div></div>
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
        <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Command <span>access.</span></>} subtitle="Changes apply to this guild and are confirmed only after the live bot synchronizes with Discord. Protected system commands stay enabled." actions={<><Button onClick={() => void resetCommands()} disabled={operationBusy || !guildId}>Reset overrides</Button><Button tone="primary" onClick={() => void synchronizeCommands()} disabled={operationBusy || !guildId}>Publish commands ↗</Button></>} />
        <div className="command-toolbar"><label className="search-field"><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, description, category…" autoComplete="off" /></label><label className="filter-control"><span>CATEGORY</span><select value={category} onChange={(event) => setCategory(event.target.value)}><option value="All">All categories</option>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label className="filter-control"><span>STATE</span><select value={commandState} onChange={(event) => setCommandState(event.target.value)}><option value="All">All states</option><option value="Enabled">Enabled</option><option value="Disabled">Disabled</option><option value="Protected">Protected</option></select></label></div>
        <div className="command-summary"><span>{filteredCommands.length} of {commands.length} registered commands</span><span>PER-GUILD CONFIGURATION</span></div>
        <div className="command-list">{commands.length === 0 ? (commandError ? <Empty>{commandError}</Empty> : refreshing ? <Empty loading>Reading the live command registry…</Empty> : <Empty>No dashboard-managed commands were returned.</Empty>) : filteredCommands.length === 0 ? <Empty>No commands match this search and filter.</Empty> : filteredCommands.map((command) => <article className="command-row" key={command.fullname}>
          <div className="command-main"><a className="command-name command-name-link" href={commandGuideUrl(command)} target="_blank" rel="noreferrer" aria-label={"Open usage guide for /" + (command.fullname || command.name)} title="Open the relevant command guide"><span className="command-prefix">/</span>{command.fullname || command.name}<span className="command-link-glyph" aria-hidden="true">↗</span></a><p className="command-description">{command.description || "No description provided."}</p><div className="command-tags"><span className="tag">{command.section || "Other"}</span><span className="tag">{command.type || "slash"}</span><span className="tag">{command.scope || "guild"}</span>{command.protected ? <span className="tag tag-protected">Protected</span> : null}{command.required_permissions ? <span className="tag">Discord permission gate</span> : null}</div><div className="command-actions"><button className="command-copy" type="button" onClick={() => void copyCommandInvocation(command)} title={"Copy /" + (command.fullname || command.name)} aria-label={"Copy invocation for /" + (command.fullname || command.name)}>▣ <span>Copy command</span></button><a className="command-guide" href={commandGuideUrl(command)} target="_blank" rel="noreferrer">Usage guide <span aria-hidden="true">↗</span></a></div></div>
          <div className="command-state"><StatusPill ok={command.enabled && !command.protected}>{command.protected ? "Protected / always on" : command.enabled ? "Enabled" : "Disabled"}</StatusPill></div>
          <button className={"switch" + (command.enabled ? " checked" : "")} role="switch" type="button" aria-checked={Boolean(command.enabled)} aria-label={"Toggle " + command.fullname} disabled={Boolean(command.protected) || busyCommand === command.fullname || operationBusy} onClick={() => void toggleCommand(command)}><span /></button>
        </article>)}</div>
        <p className="footnote">Only explicitly registered dashboard-managed application commands appear here. Prefix commands and extension load/unload operations are not implied to be manageable.</p>
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
        <div className="content-grid"><Panel eyebrow="STATUS SNAPSHOT" title="Runtime details" index="LIVE"><dl className="definition-list diagnostic-list"><div><dt>Dashboard bridge</dt><dd><StatusPill ok={system.status !== "unknown"}>{system.status === "unknown" ? "Unreachable" : "Responding"}</StatusPill></dd></div><div><dt>Discord gateway</dt><dd>{system.ready ? "Connected" : "Not ready"}</dd></div><div><dt>Gateway latency</dt><dd>{system.latency_ms == null ? "Unavailable" : Math.round(system.latency_ms) + " ms"}</dd></div><div><dt>Connected bot guilds</dt><dd>{number(system.guild_count)}</dd></div><div><dt>Loaded extensions</dt><dd>{number(system.extension_count)}</dd></div><div><dt>Python runtime</dt><dd>{system.python_version || "Unavailable"}</dd></div><div><dt>Process uptime</dt><dd>{duration(system.uptime_seconds)}</dd></div><div><dt>Observation time</dt><dd>{timestamp(system.observed_at)}</dd></div>{lastKnown ? <><div><dt>Last-known status</dt><dd>{String(lastKnown.status || "Unknown")}</dd></div><div><dt>Last-known observation</dt><dd>{timestamp(Number(lastKnown.observed_at))}</dd></div></> : null}</dl></Panel><Panel eyebrow="BOUNDARIES" title="Service availability"><div className="note-block"><strong>Two separate signals.</strong><p>Dashboard HTTP availability does not mean the Discord gateway is connected. Cached observations are labelled and never presented as live status.</p></div><div className="note-block"><strong>Control operations require the bot.</strong><p>When the bridge or Discord synchronization is unavailable, command changes fail safely rather than showing false success.</p></div></Panel></div>
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

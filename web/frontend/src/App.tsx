"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { ACTION_FEEDBACK_EVENT, api, errorMessage, reportRuntimeIssue, requestErrorStatus, type ActionFeedbackDetail } from "./Lib/api";
import type {
  AtlasGraphEdge,
  AtlasGraphNode,
  AtlasRelation,
  AtlasResponse,
  AuditEntry,
  Bootstrap,
  Command,
  CommandAccessPolicy,
  CommandAccessResponse,
  CommandResponse,
  Confirmation,
  CookiePreferences,
  DashboardConsent,
  DashboardSection,
  DashboardServerSettings,
  Guild,
  Integration,
  ListResponse,
  Overview,
  Resource,
  SectionLoadState,
  SystemStatus,
  Toast,
  User,
} from "./Types/dashboard";
import { DashboardOverlays } from "./Components/Layout/DashboardOverlays";
import { ExtensionsPage } from "./Components/Features/Extensions/ExtensionsPage";
import { AuditHistory } from "./Components/Features/Activity/AuditHistory";
import { DiagnosticsPage } from "./Components/Features/Diagnostics/DiagnosticsPage";
import { RuntimeLogs } from "./Components/Features/Logs/RuntimeLogs";
import { IntegrationsPage } from "./Components/Features/Integrations/IntegrationsPage";
import { DatabaseStatus } from "./Components/Features/Persistence/DatabaseStatus";
import { DashboardShell } from "./Components/Layout/DashboardShell";
import { Sidebar } from "./Components/Layout/Sidebar";
import { Topbar } from "./Components/Layout/Topbar";
import { MobileNavigation } from "./Components/Layout/MobileNavigation";
import { LoginScreen } from "./Components/Features/Authentication/LoginScreen";
import { SessionProvider } from "./Components/Features/Authentication/useSession";
import { SessionGuard } from "./Components/Features/Authentication/SessionGuard";
import { ConsentProvider } from "./Components/Features/Consent/useConsent";
import { ConsentGate } from "./Components/Features/Consent/ConsentGate";
import { UnsavedChangesDialog } from "./Components/Forms/UnsavedChangesDialog";
import { ReceiptThankYou } from "./Components/Feedback/ReceiptThankYou";
import { PAGES, type Page } from "./Components/Layout/navigation";
import { number } from "./Components/Features/Overview/format";
import { Icon, type IconName } from "./Components/Icons";
import { Button, Empty, Card, SectionHeading, StatusPill } from "./Components/UI";
import { DashboardSkeleton } from "./Components/Feedback/LoadingState";
import { OverviewPage } from "./Components/Features/Overview/OverviewPage";
import { KnowledgeAtlasPage } from "./Components/Features/KnowledgeAtlas/KnowledgeAtlasPage";
import { CommandsPage } from "./Components/Features/Commands/CommandsPage";
import { ArchiveSettingsPage } from "./Components/Features/Archive/ArchiveSettingsPage";
import { ServerSettingsPage } from "./Components/Features/Settings/ServerSettingsPage";
import { useCommandSettings } from "./Components/Features/Commands/useCommandSettings";



function createInitialSectionLoadStates(): Record<DashboardSection, SectionLoadState> {
  return {
    overview: { loading: true, loaded: false, error: "", errorStatus: null },
    commands: { loading: true, loaded: false, error: "", errorStatus: null },
    system: { loading: true, loaded: false, error: "", errorStatus: null },
    audit: { loading: true, loaded: false, error: "", errorStatus: null },
    logs: { loading: true, loaded: false, error: "", errorStatus: null },
    integrations: { loading: true, loaded: false, error: "", errorStatus: null },
    database: { loading: true, loaded: false, error: "", errorStatus: null },
  };
}


function commandGuideUrl(command: Command): string {
  const name = (command.fullname || command.name || "").trim().toLowerCase().split(/\s+/)[0];
  const mediaGuide = "https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/docs/MEDIA_DISCOVERY.md";
  const readmeGuide = "https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/README.md#command-map";
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
    return "https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/docs/DASHBOARD.md#capabilities-and-boundaries";
  }
  if (name === "custom-role" || name === "custom-role-admin") {
    return "https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/docs/HANDOFF_NOTES.md";
  }
  if (guideAnchors[name]) return mediaGuide + guideAnchors[name];
  if (["browse", "connections", "reading-order", "where-to-watch", "trailers", "collection-guide", "media-region", "episode-discussion", "chapter-discussion", "author-works", "webnovel-updates"].includes(name)) {
    return mediaGuide;
  }
  return readmeGuide;
}

export default function App() {
  const pathname = usePathname();
  const isLogin = pathname === "/login";
  const routeSegments = (pathname || "").split("/").filter(Boolean);
  const routeUserId = routeSegments.length === 2 ? routeSegments[0] : "";
  const routeGuildId = routeSegments.length === 2 ? routeSegments[1] : "";
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [guildId, setGuildId] = useState("");
  const [csrf, setCsrf] = useState("");
  const [page, setPage] = useState<Page>("overview");
  const [overview, setOverview] = useState<Overview>({});
  const [system, setSystem] = useState<SystemStatus>({});
  const [commands, setCommands] = useState<Command[]>([]);
  const [archiveSettingsDirty, setArchiveSettingsDirty] = useState(false);
  const [serverSettingsDirty, setServerSettingsDirty] = useState(false);
  const [serverSetupComplete, setServerSetupComplete] = useState(false);
  const [savedCommands, setSavedCommands] = useState<Command[]>([]);
  const [commandRevision, setCommandRevision] = useState("");
  const [savingCommands, setSavingCommands] = useState(false);
  const [commandError, setCommandError] = useState("");
  const [accessTarget, setAccessTarget] = useState("");
  const [accessOptions, setAccessOptions] = useState<CommandAccessResponse | null>(null);
  const [accessError, setAccessError] = useState("");
  const [accessErrorStatus, setAccessErrorStatus] = useState<number | null>(null);
  const [accessDraft, setAccessDraft] = useState<CommandAccessPolicy | null>(null);
  const [accessOriginal, setAccessOriginal] = useState<CommandAccessPolicy | null>(null);
  const [accessLoading, setAccessLoading] = useState(false);
  const [accessSaving, setAccessSaving] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [auditCursor, setAuditCursor] = useState<string | null>(null);
  const [auditHasMore, setAuditHasMore] = useState(false);
  const [resources, setResources] = useState<Resource[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [logText, setLogText] = useState("");
  const [logName, setLogName] = useState("Recent runtime events");
  const [logFile, setLogFile] = useState<"bot.log" | "dashboard.log">("bot.log");
  const logFileRef = useRef<"bot.log" | "dashboard.log">("bot.log");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [commandState, setCommandState] = useState("All");
  const [initialLoading, setInitialLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [sectionStates, setSectionLoadStates] = useState<Record<DashboardSection, SectionLoadState>>(createInitialSectionLoadStates);
  const setSectionLoadState = useCallback((section: DashboardSection, next: Partial<SectionLoadState>) => {
    setSectionLoadStates((current) => ({ ...current, [section]: { ...current[section], ...next } }));
  }, []);
  const [mobileNav, setMobileNav] = useState(false);
  const [thankYouOpen, setThankYouOpen] = useState(false);
  useEffect(() => {
    const syncThankYouDialog = () => setThankYouOpen(window.location.hash === "#thank-you");
    syncThankYouDialog();
    window.addEventListener("hashchange", syncThankYouDialog);
    return () => window.removeEventListener("hashchange", syncThankYouDialog);
  }, []);
  const closeThankYou = useCallback(() => {
    setThankYouOpen(false);
    if (window.location.hash === "#thank-you") {
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    }
  }, []);
  const [serverPickerOpen, setServerPickerOpen] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<{ type: "guild"; guildId: string } | { type: "page"; page: Page } | { type: "close-access" } | null>(null);
  const [botModerator, setBotModerator] = useState(false);
  const [preferencesAllowed, setPreferencesAllowed] = useState<boolean | null>(null);
  const [cookiePreferencesSaved, setCookiePreferencesSaved] = useState(false);
  const [consent, setConsent] = useState<DashboardConsent | null>(null);
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentChecking, setConsentChecking] = useState(false);
  const [consentError, setConsentError] = useState("");
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
  const auditRequestGeneration = useRef(0);
  const atlasRequestGeneration = useRef(0);
  const logsRequestGeneration = useRef(0);
  const atlasDeepLinkConsumed = useRef(false);
  const activeGuildIdRef = useRef("");
  const configurationDraftDirtyRef = useRef(false);
  const cookiePreferenceRevision = useRef(0);
  const preferencesAllowedRef = useRef<boolean | null>(null);

  const pushToast = useCallback((message: string, error = false) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((current) => [...current.slice(-3), { id, message, error }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 4400);
  }, []);

  const lastRuntimeReportAt = useRef(0);
  useEffect(() => {
    if (isLogin || !guildId || !csrf) return;

    const report = (message: string, stack: string) => {
      const now = Date.now();
      if (now - lastRuntimeReportAt.current < 10_000) return;
      lastRuntimeReportAt.current = now;
      void reportRuntimeIssue(
        guildId,
        csrf,
        "dashboard-runtime",
        message.slice(0, 2_000),
        stack.slice(0, 12_000),
      ).then(reference => {
        if (reference) {
          pushToast(
            "The dashboard encountered an unexpected error. Reference: " + reference
              + ". Please open a GitHub issue if this continues.",
            true,
          );
        } else {
          pushToast("The dashboard encountered an unexpected error. Please retry.", true);
        }
      });
    };

    const handleError = (event: ErrorEvent) => {
      report(
        event.message || "An unexpected browser error occurred.",
        event.error instanceof Error ? event.error.stack || "" : "",
      );
    };
    const handleRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      report(
        reason instanceof Error ? reason.message : String(reason ?? "An unhandled asynchronous error occurred."),
        reason instanceof Error ? reason.stack || "" : "",
      );
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, [csrf, guildId, isLogin, pushToast]);

  useEffect(() => {
    const handleActionFeedback = (event: Event) => {
      const detail = (event as CustomEvent<ActionFeedbackDetail>).detail;
      if (!detail) return;
      if (detail.phase === "start") {
        detail.target?.classList.add("action-pending");
        detail.target?.setAttribute("aria-busy", "true");
        setToasts(current => [...current.slice(-3), {
          id: detail.id,
          message: detail.message,
          error: false,
          pending: true,
        }]);
        return;
      }
      detail.target?.classList.remove("action-pending");
      detail.target?.removeAttribute("aria-busy");
      setToasts(current => current.filter(item => item.id !== detail.id));
      if (detail.successMessage) pushToast(detail.successMessage);
    };

    window.addEventListener(ACTION_FEEDBACK_EVENT, handleActionFeedback);
    return () => window.removeEventListener(ACTION_FEEDBACK_EVENT, handleActionFeedback);
  }, [pushToast]);

  useEffect(() => {
    const updateCookiePreferences = (event: Event) => {
      const detail = (event as CustomEvent<{ rememberServer?: boolean }>).detail;
      const allowed = detail?.rememberServer === true;
      cookiePreferenceRevision.current += 1;
      preferencesAllowedRef.current = allowed;
      setPreferencesAllowed(allowed);
      setCookiePreferencesSaved(true);
    };
    window.addEventListener("lemegeton:cookie-consent", updateCookiePreferences);
    return () => window.removeEventListener("lemegeton:cookie-consent", updateCookiePreferences);
  }, []);

  useEffect(() => {
    if (preferencesAllowed === null || !cookiePreferencesSaved) return;
    try {
      if (!preferencesAllowed) window.localStorage.removeItem("lemegeton:selected-guild");
      else if (guildId) window.localStorage.setItem("lemegeton:selected-guild", String(guildId));
    } catch { /* browser storage may be disabled */ }
  }, [preferencesAllowed, cookiePreferencesSaved, guildId]);

  const currentGuild = useMemo(() => guilds.find((item) => String(item.id) === String(guildId)), [guilds, guildId]);
  const commandDraftDirty = useMemo(() => {
    if (commands.length !== savedCommands.length) return true;
    const saved = new Map(savedCommands.map((item) => [item.fullname, item.enabled]));
    return commands.some(item => saved.get(item.fullname) !== item.enabled);
  }, [commands, savedCommands]);
  const commandDraftDirtyRef = useRef(false);
  useEffect(() => { commandDraftDirtyRef.current = commandDraftDirty; }, [commandDraftDirty]);
  const configurationDraftDirty = archiveSettingsDirty || serverSettingsDirty;
  useEffect(() => { configurationDraftDirtyRef.current = configurationDraftDirty; }, [configurationDraftDirty]);
  const accessDraftDirty = useMemo(() => {
    if (!accessDraft || !accessOriginal) return false;
    return accessDraft.role_mode !== accessOriginal.role_mode
      || accessDraft.channel_mode !== accessOriginal.channel_mode
      || accessDraft.role_ids.join(",") !== accessOriginal.role_ids.join(",")
      || accessDraft.channel_ids.join(",") !== accessOriginal.channel_ids.join(",");
  }, [accessDraft, accessOriginal]);
  const applyGuildSelection = useCallback((nextId: string) => {
    if (!guilds.some((guild) => String(guild.id) === String(nextId) && guild.bot_installed)) return;
    activeGuildIdRef.current = String(nextId);
    refreshGeneration.current += 1;
    atlasRequestGeneration.current += 1;
    setAtlasResult(null);
    setAtlasError("");
    setAtlasLoading(false);
    setGuildId(String(nextId));
    setPage("settings");
    setServerSetupComplete(false);
    setArchiveSettingsDirty(false);
    setServerSettingsDirty(false);
    if (user?.id) window.history.pushState({}, "", "/" + encodeURIComponent(user.id) + "/" + encodeURIComponent(nextId) + "/");
    setConfirmation(null);
    setOverview({});
    setCommands([]);
    setSavedCommands([]);
    setCommandRevision("");
    setCommandError("");
    setAccessTarget("");
    setAccessOptions(null);
    setAccessError("");
    setAccessErrorStatus(null);
    setAccessDraft(null);
    setAccessOriginal(null);
    setAccessLoading(false);
    setAccessSaving(false);
    auditRequestGeneration.current += 1;
    setAudit([]);
    setAuditCursor(null);
    setAuditHasMore(false);
    setResources([]);
    setSectionLoadStates((current) => ({
      ...current,
      overview: { loading: true, loaded: false, error: "", errorStatus: null },
      commands: { loading: true, loaded: false, error: "", errorStatus: null },
      system: { loading: true, loaded: false, error: "", errorStatus: null },
      audit: { loading: true, loaded: false, error: "", errorStatus: null },
      database: { loading: true, loaded: false, error: "", errorStatus: null },
    }));
    setUpdatedAt(null);
    setRefreshing(false);
  }, [guilds, user?.id]);

  const selectGuild = useCallback((nextId: string) => {
    if (!guilds.some((guild) => String(guild.id) === String(nextId) && guild.bot_installed)) return;
    if (commandDraftDirtyRef.current || accessDraftDirty || configurationDraftDirtyRef.current) {
      setPendingNavigation({ type: "guild", guildId: nextId });
      return;
    }
    applyGuildSelection(nextId);
  }, [accessDraftDirty, applyGuildSelection, guilds]);
  const completePendingNavigation = useCallback(() => {
    const pending = pendingNavigation;
    setPendingNavigation(null);
    if (!pending) return;
    if (pending.type === "guild") {
      applyGuildSelection(pending.guildId);
    } else if (pending.type === "page") {
      setArchiveSettingsDirty(false);
      setServerSettingsDirty(false);
      setPage(pending.page);
      setMobileNav(false);
    } else {
      setAccessTarget("");
      setAccessOptions(null);
      setAccessError("");
      setAccessErrorStatus(null);
      setAccessDraft(null);
      setAccessOriginal(null);
    }
  }, [applyGuildSelection, pendingNavigation]);
  const { categories, filteredCommands } = useCommandSettings(commands, { search, category, state: commandState });

  const loadAudit = useCallback(async (id = guildId, quiet = false, cursor?: string, append = false) => {
    if (!id || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
    const requestId = ++auditRequestGeneration.current;
    const params = new URLSearchParams({ limit: "25" });
    if (cursor) params.set("cursor", cursor);
    setSectionLoadState("audit", { loading: true, error: "", errorStatus: null });
    try {
      const data = await api<ListResponse<AuditEntry>>(
        "/api/guilds/" + encodeURIComponent(id) + "/audit?" + params.toString(),
        csrf,
      );
      if (requestId !== auditRequestGeneration.current || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
      const pageEntries = data.entries || [];
      setAudit(current => append ? [...current, ...pageEntries] : pageEntries);
      setAuditCursor(data.next_cursor || null);
      setAuditHasMore(data.has_more ?? Boolean(data.next_cursor));
      setSectionLoadState("audit", { loading: false, loaded: true, error: "", errorStatus: null });
    } catch (error) {
      if (requestId !== auditRequestGeneration.current || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
      setSectionLoadState("audit", { loading: false, error: errorMessage(error), errorStatus: requestErrorStatus(error) });
      if (!quiet) pushToast(errorMessage(error), true);
    }
  }, [csrf, guildId, pushToast, setSectionLoadState]);

  const refreshData = useCallback(async (id = guildId, quiet = false) => {
    if (!id || (activeGuildIdRef.current && activeGuildIdRef.current !== String(id))) return;
    const requestGeneration = ++refreshGeneration.current;
    const auditPageRequest = ++auditRequestGeneration.current;
    setRefreshing(true);
    setCommandError("");
    setSectionLoadState("overview", { loading: true, error: "", errorStatus: null });
    setSectionLoadState("commands", { loading: true, error: "", errorStatus: null });
    setSectionLoadState("system", { loading: true, error: "", errorStatus: null });
    setSectionLoadState("audit", { loading: true, error: "", errorStatus: null });
    const results = await Promise.allSettled([
      api<Overview>("/api/guilds/" + encodeURIComponent(id) + "/overview", csrf),
      api<CommandResponse>("/api/guilds/" + encodeURIComponent(id) + "/commands", csrf),
      api<SystemStatus>("/api/system", csrf),
      api<ListResponse<AuditEntry>>("/api/guilds/" + encodeURIComponent(id) + "/audit?limit=25", csrf)
    ] as const);
    if (requestGeneration !== refreshGeneration.current || activeGuildIdRef.current !== String(id)) return;
    const [overviewResult, commandsResult, systemResult, auditResult] = results;
    if (overviewResult.status === "fulfilled") {
      setOverview(overviewResult.value || {});
      setSectionLoadState("overview", { loading: false, loaded: true, error: "", errorStatus: null });
    } else {
      setSectionLoadState("overview", { loading: false, error: errorMessage(overviewResult.reason), errorStatus: requestErrorStatus(overviewResult.reason) });
      if (!quiet) pushToast(errorMessage(overviewResult.reason), true);
    }
    if (commandsResult.status === "fulfilled") {
      if (!commandDraftDirtyRef.current || commandsResult.value.revision === commandRevision) {
        setCommands(commandsResult.value.commands || []);
        setSavedCommands(commandsResult.value.commands || []);
        setCommandRevision(commandsResult.value.revision || "");
      }
      setCommandError("");
      setSectionLoadState("commands", { loading: false, loaded: true, error: "", errorStatus: null });
    } else {
      setCommandError(errorMessage(commandsResult.reason));
      setSectionLoadState("commands", { loading: false, error: errorMessage(commandsResult.reason), errorStatus: requestErrorStatus(commandsResult.reason) });
      if (!quiet) pushToast(errorMessage(commandsResult.reason), true);
    }
    if (systemResult.status === "fulfilled") {
      setSystem(systemResult.value || {});
      setSectionLoadState("system", { loading: false, loaded: true, error: "", errorStatus: null });
    } else {
      setSectionLoadState("system", { loading: false, error: errorMessage(systemResult.reason), errorStatus: requestErrorStatus(systemResult.reason) });
      if (!quiet) pushToast(errorMessage(systemResult.reason), true);
    }
    if (auditPageRequest === auditRequestGeneration.current) {
      if (auditResult.status === "fulfilled") {
        setAudit(auditResult.value.entries || []);
        setAuditCursor(auditResult.value.next_cursor || null);
        setAuditHasMore(auditResult.value.has_more ?? Boolean(auditResult.value.next_cursor));
        setSectionLoadState("audit", { loading: false, loaded: true, error: "", errorStatus: null });
      } else {
        setSectionLoadState("audit", { loading: false, error: errorMessage(auditResult.reason), errorStatus: requestErrorStatus(auditResult.reason) });
        if (!quiet) pushToast(errorMessage(auditResult.reason), true);
      }
    }
    setUpdatedAt(Date.now());
    setRefreshing(false);
  }, [csrf, guildId, pushToast, commandRevision, setSectionLoadState]);

  const loadSystem = useCallback(async () => {
    setSectionLoadState("system", { loading: true, error: "", errorStatus: null });
    try {
      setSystem(await api<SystemStatus>("/api/system", csrf));
      setSectionLoadState("system", { loading: false, loaded: true, error: "", errorStatus: null });
    } catch (error) {
      setSectionLoadState("system", { loading: false, error: errorMessage(error), errorStatus: requestErrorStatus(error) });
      pushToast(errorMessage(error), true);
    }
  }, [csrf, pushToast, setSectionLoadState]);

  const loadDatabase = useCallback(async () => {
    if (!guildId) return;
    const requestedGuild = guildId;
    setSectionLoadState("database", { loading: true, error: "", errorStatus: null });
    try {
      const data = await api<{ resources?: Resource[] }>("/api/guilds/" + encodeURIComponent(requestedGuild) + "/database", csrf);
      if (activeGuildIdRef.current && activeGuildIdRef.current !== String(requestedGuild)) return;
      setResources(data.resources || []);
      setSectionLoadState("database", { loading: false, loaded: true, error: "", errorStatus: null });
    } catch (error) {
      if (activeGuildIdRef.current && activeGuildIdRef.current !== String(requestedGuild)) return;
      setSectionLoadState("database", { loading: false, error: errorMessage(error), errorStatus: requestErrorStatus(error) });
      pushToast(errorMessage(error), true);
    }
  }, [csrf, guildId, pushToast, setSectionLoadState]);

  const loadIntegrations = useCallback(async () => {
    setSectionLoadState("integrations", { loading: true, error: "", errorStatus: null });
    try {
      const data = await api<{ integrations?: Integration[] }>("/api/integrations", csrf);
      setIntegrations(data.integrations || []);
      setSectionLoadState("integrations", { loading: false, loaded: true, error: "", errorStatus: null });
    } catch (error) {
      setSectionLoadState("integrations", { loading: false, error: errorMessage(error), errorStatus: requestErrorStatus(error) });
      pushToast(errorMessage(error), true);
    }
  }, [csrf, pushToast, setSectionLoadState]);

  const loadLogs = useCallback(async (file: "bot.log" | "dashboard.log" = logFileRef.current) => {
    const requestGeneration = ++logsRequestGeneration.current;
    const switching = file !== logFileRef.current;
    logFileRef.current = file;
    setLogFile(file);
    setSectionLoadState("logs", {
      loading: true,
      error: "",
      errorStatus: null,
      ...(switching ? { loaded: false } : {}),
    });
    if (switching) {
      setLogText("");
      setLogName(file === "bot.log" ? "Bot runtime events" : "Dashboard service events");
    }
    try {
      const data = await api<{ name?: string; content?: string }>(
        "/api/logs?file=" + encodeURIComponent(file),
        csrf,
      );
      if (requestGeneration !== logsRequestGeneration.current || logFileRef.current !== file) return;
      setLogName(data.name || (file === "bot.log" ? "Bot runtime events" : "Dashboard service events"));
      setLogText(data.content || "No runtime log entries found.");
      setSectionLoadState("logs", { loading: false, loaded: true, error: "", errorStatus: null });
    } catch (error) {
      if (requestGeneration !== logsRequestGeneration.current || logFileRef.current !== file) return;
      setSectionLoadState("logs", { loading: false, error: errorMessage(error), errorStatus: requestErrorStatus(error) });
    }
  }, [csrf, setSectionLoadState]);

  useEffect(() => {
    if (isLogin) { setInitialLoading(false); return; }
    let active = true;
    api<Bootstrap>("/api/bootstrap").then(async (data) => {
      if (!active) return;
      setUser(data.user);
      const availableGuilds = data.guilds || [];
      setGuilds(availableGuilds);
      setCsrf(data.csrf_token || "");
      setBotModerator(data.bot_moderator === true);
      let consentStatus: DashboardConsent;
      try {
        consentStatus = await api<DashboardConsent>("/api/consent");
      } catch (error) {
        if (active) {
          setConsentError(errorMessage(error));
          pushToast(errorMessage(error), true);
        }
        return;
      }
      if (!active) return;
      setConsent(consentStatus);
      setConsentError("");
      let rememberServer = false;
      let preferenceSaved = false;
      const preferenceRevision = cookiePreferenceRevision.current;
      try {
        const cookiePreferences = await api<CookiePreferences>("/api/cookies");
        preferenceSaved = cookiePreferences.saved === true;
        rememberServer = preferenceSaved && cookiePreferences.remember_server === true;
        if (cookiePreferenceRevision.current !== preferenceRevision) {
          rememberServer = preferencesAllowedRef.current === true;
          preferenceSaved = true;
        } else {
          preferencesAllowedRef.current = rememberServer;
          if (active) setPreferencesAllowed(rememberServer);
        }
      } catch {
        if (cookiePreferenceRevision.current !== preferenceRevision) {
          rememberServer = preferencesAllowedRef.current === true;
          preferenceSaved = true;
        } else {
          preferencesAllowedRef.current = false;
          if (active) setPreferencesAllowed(false);
        }
      }
      if (!active) return;
      setCookiePreferencesSaved(preferenceSaved);
      let rememberedGuild = "";
      if (rememberServer) {
        try { rememberedGuild = window.localStorage.getItem("lemegeton:selected-guild") || ""; }
        catch { /* browser storage may be disabled */ }
      }
      const canSelect = (candidate: unknown) => candidate != null && availableGuilds.some((guild) => String(guild.id) === String(candidate) && guild.bot_installed);
      if (routeUserId && data.user.id !== routeUserId) {
        window.location.assign("/login");
        return;
      }
      const deepLinkedGuild = routeGuildId && routeUserId === data.user.id
        ? availableGuilds.find(guild => String(guild.id) === routeGuildId && guild.bot_installed)
        : undefined;
      if (routeGuildId && routeUserId && !deepLinkedGuild) {
        window.location.assign("/");
        return;
      }
      const selected = String([deepLinkedGuild?.id, rememberedGuild, data.selected_guild_id, availableGuilds.find(guild => guild.bot_installed)?.id].find(canSelect) || "");
      if (availableGuilds.length && !routeGuildId) setServerPickerOpen(true);
      activeGuildIdRef.current = selected;
      setGuildId(selected);
      setServerSetupComplete(false);
      if (!selected && availableGuilds.length) pushToast("No installed server is available where you have dashboard access.");
      else if (!selected && data.bot_moderator !== true) pushToast("No server is available where you have Manage Server or Administrator permission.", true);
    }).catch((error) => {
      if (active) {
        setBootstrapError(errorMessage(error));
        pushToast(errorMessage(error), true);
      }
    }).finally(() => { if (active) setInitialLoading(false); });
    return () => { active = false; };
  }, [isLogin, pushToast, routeUserId, routeGuildId]);

  useEffect(() => {
    if (!guildId || isLogin || !csrf) return;
    let active = true;
    const requestedGuild = guildId;
    api<DashboardServerSettings>("/api/guilds/" + encodeURIComponent(requestedGuild) + "/settings", csrf)
      .then(result => {
        if (!active || activeGuildIdRef.current !== requestedGuild) return;
        setServerSetupComplete(result.setup_complete);
        if (!result.setup_complete || !currentGuild?.can_manage_server) setPage("settings");
        else setPage("overview");
      })
      .catch(error => {
        if (active && activeGuildIdRef.current === requestedGuild) pushToast(errorMessage(error), true);
      });
    return () => { active = false; };
  }, [guildId, csrf, isLogin, currentGuild?.can_manage_server, pushToast]);

  useEffect(() => {
    if (!guildId || isLogin || !csrf || !serverSetupComplete || !currentGuild?.can_manage_server) return;
    void refreshData(guildId, true);
    const timer = window.setInterval(() => {
      if (!document.hidden) void refreshData(guildId, true);
    }, 45000);
    return () => window.clearInterval(timer);
  }, [guildId, csrf, isLogin, serverSetupComplete, currentGuild?.can_manage_server, refreshData]);

  useEffect(() => {
    if (isLogin) return;
    if (page === "logs" && botModerator) void loadLogs();
    if (page === "integrations" && botModerator) void loadIntegrations();
    if (!guildId) return;
    if (page === "database") void loadDatabase();
  }, [page, guildId, botModerator, isLogin, loadDatabase, loadLogs, loadIntegrations]);

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
      destructive: true,
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
    if (!guildId || command.protected || !command.configurable || savingCommands) return;
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
      .filter(item => !item.protected && item.configurable && baseline.get(item.fullname) !== item.enabled)
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
    if (!commandDraftDirty && !accessDraftDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [accessDraftDirty, commandDraftDirty]);

  const openCommandAccess = async (command: Command) => {
    if (!guildId || command.protected || accessLoading || accessSaving) return;
    const requestedGuild = guildId;
    setAccessTarget(command.fullname);
    setAccessLoading(true);
    setAccessError("");
    setAccessErrorStatus(null);
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
      if (activeGuildIdRef.current === requestedGuild) {
        setAccessError(errorMessage(error));
        setAccessErrorStatus(requestErrorStatus(error));
      }
    } finally {
      if (activeGuildIdRef.current === requestedGuild) setAccessLoading(false);
    }
  };

  const closeCommandAccess = () => {
    if (accessDraftDirty) {
      setPendingNavigation({ type: "close-access" });
      return;
    }
    setAccessTarget("");
    setAccessOptions(null);
    setAccessError("");
    setAccessErrorStatus(null);
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


  const retryConsent = async () => {
    if (consentChecking) return;
    setConsentChecking(true);
    setConsentError("");
    try {
      const result = await api<DashboardConsent>("/api/consent");
      setConsent(result);
    } catch (error) {
      setConsentError(errorMessage(error));
    } finally {
      setConsentChecking(false);
    }
  };

  const acceptConsent = async () => {
    if (!csrf || consentSaving) return;
    setConsentSaving(true);
    setConsentError("");
    try {
      const result = await api<DashboardConsent>("/api/consent", csrf, {
        method: "POST",
        body: JSON.stringify({ accepted: true }),
      });
      setConsent(result);
    } catch (error) {
      setConsentError(errorMessage(error));
    } finally {
      setConsentSaving(false);
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

  const canManageServer = currentGuild?.can_manage_server === true;
  const navigate = (next: Page) => {
    if ((next === "logs" || next === "integrations") && !botModerator) return;
    if (next !== page && (commandDraftDirty || accessDraftDirty || configurationDraftDirty)) {
      setPendingNavigation({ type: "page", page: next });
      return;
    }
    if (guildId && !serverSetupComplete && next !== "settings") {
      pushToast("Complete the server retention and language setup before opening other dashboard sections.", true);
      setPage("settings");
      setMobileNav(false);
      return;
    }
    if (guildId && !canManageServer && next !== "settings" && !(botModerator && (next === "logs" || next === "integrations"))) {
      pushToast("Manage Server or Administrator permission is required for this section.", true);
      return;
    }
    setPage(next);
    setMobileNav(false);
  };
  const selectedPage = PAGES.find((item) => item.id === page) || PAGES[0];
  const showModeratorPage = botModerator && (page === "logs" || page === "integrations");
  const showSystemPage = (Boolean(guildId) && (page === "registry" || page === "audit" || page === "diagnostics" || page === "database")) || showModeratorPage;

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

  if (initialLoading) return <DashboardSkeleton />;

  if (isLogin) return <LoginScreen />;

  return (
    <SessionProvider value={{ user, guilds, guildId, csrf, botModerator, loading: initialLoading, error: bootstrapError }}>
      <ConsentProvider value={{
        consent,
        saving: consentSaving,
        checking: consentChecking,
        error: consentError,
        onRetry: () => { void retryConsent(); },
        onAccept: () => { void acceptConsent(); },
        onDecline: () => { void logout(); },
      }}>
        <SessionGuard onRetry={() => window.location.reload()}>
          {!consent || !consent.accepted ? <ConsentGate /> : (
            <DashboardShell
              pageKey={page}
              sidebar={<Sidebar
                page={page}
                mobileNav={mobileNav}
                commandCount={commands.length}
                runtimeOnline={runtimeOnline}
                systemStatus={system.status}
                botReady={Boolean(bot.ready)}
                runtimeStatus={runtimeStatus}
                botModerator={botModerator}
                canManageServer={canManageServer}
                onNavigate={navigate}
                onCloseNavigation={() => setMobileNav(false)}
                onLogout={() => { void logout(); }}
              />}
              mobileNavigation={<MobileNavigation open={mobileNav} onClose={() => setMobileNav(false)} />}
              topbar={<Topbar
                selectedPage={selectedPage}
                mobileNav={mobileNav}
                refreshing={refreshing}
                guildId={canManageServer && serverSetupComplete ? guildId : ""}
                currentGuild={currentGuild}
                serverPickerOpen={serverPickerOpen}
                user={user}
                onToggleNavigation={() => setMobileNav(value => !value)}
                onOpenServerPicker={() => setServerPickerOpen(true)}
                onRefresh={() => { void refreshData(guildId); }}
              />}
              footer={<footer className="page-footer"><span>LEMEGETON / CONTROL PLANE</span><span>{system.status === "unknown" ? "LIVE BOT DATA UNAVAILABLE" : "PRIVATE SESSION · DATA REFRESHED"}</span></footer>}
              overlays={<>
                <DashboardOverlays
                  toasts={toasts}
                  serverPickerOpen={serverPickerOpen}
                  guilds={guilds}
                  confirmation={confirmation}
                  operationBusy={operationBusy}
                  onDismissToast={id => setToasts(items => items.filter(item => item.id !== id))}
                  onCloseServerPicker={() => setServerPickerOpen(false)}
                  onSelectGuild={id => { selectGuild(id); setServerPickerOpen(false); }}
                  onSettleConfirmation={settleConfirmation}
                />
                <UnsavedChangesDialog
                  open={Boolean(pendingNavigation)}
                  description={pendingNavigation?.type === "guild"
                    ? "Switching servers discards the unsaved drafts in the current configuration section."
                    : pendingNavigation?.type === "close-access"
                      ? "Close this editor and discard the unsaved role and channel access rules?"
                      : "Leave this configuration section and discard its unsaved changes?"}
                  confirmLabel={pendingNavigation?.type === "guild"
                    ? "Discard and switch"
                    : pendingNavigation?.type === "close-access" ? "Discard access rules" : "Leave page"}
                  destructive={pendingNavigation?.type !== "page"}
                  onKeepEditing={() => setPendingNavigation(null)}
                  onDiscard={completePendingNavigation}
                />
                {thankYouOpen ? <ReceiptThankYou onContinue={closeThankYou} /> : null}
              </>}
            >
      <div className="braille-band" aria-hidden="true">
        <span className="braille-track braille-track-a">⠿⠗⠿⠿⠶⠿⠿⠾⠿⠿⠿⠷⠿⠿⠿⠿⠿⠿</span>
        <span className="braille-band-label">LEMEGETON / LIVE SIGNAL</span>
        <span className="braille-track braille-track-b">⠿⠿⠷⠿⠿⠿⠿⠗⠿⠿⠶⠿⠿⠿⠾⠿⠿</span>
      </div>

      {guildId ? <>
      {page === "overview" ? <OverviewPage
        selectedPage={selectedPage}
        bot={bot}
        system={system}
        systemLoading={sectionStates.system.loading}
        systemLoaded={sectionStates.system.loaded}
        systemError={sectionStates.system.error}
        systemErrorStatus={sectionStates.system.errorStatus}
        onRetrySystem={() => { void loadSystem(); }}
        updatedAt={updatedAt}
        runtimeStatus={runtimeStatus}
        commandsCount={commands.length}
        loading={sectionStates.overview.loading}
        loaded={sectionStates.overview.loaded}
        error={sectionStates.overview.error}
        errorStatus={sectionStates.overview.errorStatus}
        onRetry={() => { void refreshData(guildId); }}
        enabled={enabled}
        disabled={disabled}
        percent={percent}
        runtimeOnline={runtimeOnline}
        currentGuild={currentGuild}
        guildId={guildId}
        user={user}
        audit={audit}
        auditLoading={sectionStates.audit.loading}
        auditLoaded={sectionStates.audit.loaded}
        auditError={sectionStates.audit.error}
        auditErrorStatus={sectionStates.audit.errorStatus}
        onRetryAudit={() => { void loadAudit(guildId); }}
        operationBusy={operationBusy}
        onNavigate={navigate}
        onPublishCommands={() => { void synchronizeCommands(); }}
      /> : null}
      {page === "commands" ? <CommandsPage
        eyebrow={selectedPage.eyebrow}
        canManageServer={canManageServer}
        onNavigate={navigate}
        guildId={guildId}
        commands={commands}
        filteredCommands={filteredCommands}
        categories={categories}
        search={search}
        setSearch={setSearch}
        category={category}
        setCategory={setCategory}
        commandState={commandState}
        setCommandState={setCommandState}
        commandError={commandError}
        loading={sectionStates.commands.loading}
        loaded={sectionStates.commands.loaded}
        errorStatus={sectionStates.commands.errorStatus}
        onRetry={() => { void refreshData(guildId); }}
        commandGuideUrl={commandGuideUrl}
        onCopyCommand={copyCommandInvocation}
        onOpenCommandAccess={openCommandAccess}
        accessLoading={accessLoading}
        accessError={accessError}
        accessErrorStatus={accessErrorStatus}
        onRetryAccess={() => { const target = commands.find((command) => command.fullname === accessTarget); if (target) void openCommandAccess(target); }}
        accessSaving={accessSaving}
        savingCommands={savingCommands}
        operationBusy={operationBusy}
        onToggleCommand={toggleCommand}
        onResetCommands={resetCommands}
        onSynchronizeCommands={synchronizeCommands}
        commandDraftDirty={commandDraftDirty}
        savedCommands={savedCommands}
        commandRevision={commandRevision}
        onResetCommandDraft={resetCommandDraft}
        onSaveCommandDraft={saveCommandDraft}
        accessTarget={accessTarget}
        accessOptions={accessOptions}
        accessDraft={accessDraft}
        setAccessDraft={setAccessDraft}
        accessDraftDirty={accessDraftDirty}
        onCloseCommandAccess={closeCommandAccess}
        onResetCommandAccess={resetCommandAccess}
        onSaveCommandAccess={saveCommandAccess}
      /> : null}
      {page === "archive" && canManageServer && serverSetupComplete ? <ArchiveSettingsPage
        guildId={guildId}
        csrf={csrf}
        canManageServer={canManageServer}
        onNavigate={navigate}
        onDirtyChange={setArchiveSettingsDirty}
      /> : null}
      {page === "settings" ? <ServerSettingsPage
        guildId={guildId}
        csrf={csrf}
        canManageServer={canManageServer}
        onNavigate={navigate}
        onDirtyChange={setServerSettingsDirty}
        onSaved={result => {
          setServerSetupComplete(result.setup_complete);
          if (result.setup_complete && canManageServer) {
            setPage("overview");
          }
        }}
      /> : null}
      {page === "atlas" && canManageServer && serverSetupComplete ? <KnowledgeAtlasPage
        selectedPage={selectedPage}
        guildId={guildId}
        atlasResult={atlasResult}
        atlasTitle={atlasTitle}
        setAtlasTitle={setAtlasTitle}
        atlasCategory={atlasCategory}
        setAtlasCategory={setAtlasCategory}
        atlasLoading={atlasLoading}
        atlasError={atlasError}
        searchAtlas={searchAtlas}
        atlasNodes={atlasNodes}
        atlasVisibleEdges={atlasVisibleEdges}
        atlasCategories={atlasCategories}
        atlasProviders={atlasProviders}
        atlasCategoryFilter={atlasCategoryFilter}
        setAtlasCategoryFilter={setAtlasCategoryFilter}
        atlasSourceFilter={atlasSourceFilter}
        setAtlasSourceFilter={setAtlasSourceFilter}
        atlasProviderFilter={atlasProviderFilter}
        setAtlasProviderFilter={setAtlasProviderFilter}
        atlasProviderIdFilter={atlasProviderIdFilter}
        setAtlasProviderIdFilter={setAtlasProviderIdFilter}
        atlasRelationshipFilter={atlasRelationshipFilter}
        setAtlasRelationshipFilter={setAtlasRelationshipFilter}
        atlasEvidenceFilter={atlasEvidenceFilter}
        setAtlasEvidenceFilter={setAtlasEvidenceFilter}
        atlasPathTarget={atlasPathTarget}
        setAtlasPathTarget={setAtlasPathTarget}
        atlasVisibleNodes={atlasVisibleNodes}
        atlasFilters={atlasFilters}
        atlasExportBusy={atlasExportBusy}
        downloadAtlas={downloadAtlas}
        atlasZoom={atlasZoom}
        setAtlasZoom={setAtlasZoom}
        atlasNodePositions={atlasNodePositions}
        atlasVisibleRelationships={atlasVisibleRelationships}
      /> : null}

      </> : showModeratorPage ? null : <section className="page server-empty-state">
        <div className="server-empty-mark"><Icon name="server" size={24} /></div>
        {botModerator ? <>
          <p className="eyebrow">BOT MODERATOR / ACCESS</p>
          <h1>Operations, without<br /><span>a selected server.</span></h1>
          <p>Your bot-moderator access includes the restricted runtime and integration views. Server-specific controls appear after selecting a server you can manage.</p>
          <button className="command-save" type="button" onClick={() => navigate("logs")}>Open runtime logs</button>
          <button className="command-reset" type="button" onClick={() => navigate("integrations")}>View integrations</button>
        </> : <>
          <p className="eyebrow">SERVER CONNECTION / READY</p>
          <h1>Choose a server<br /><span>to get started.</span></h1>
          <p>Your Discord servers are listed with their current Lemegeton connection status. Servers without the bot are dimmed and can be invited directly.</p>
          <button className="command-save" type="button" onClick={() => setServerPickerOpen(true)}><Icon name="server" size={15} />View your servers</button>
        </>}
      </section>}
      {showSystemPage && page === "registry" ? <ExtensionsPage selectedPage={selectedPage} system={system} state={sectionStates.system} onLoadSystem={() => { void loadSystem(); }} /> : null}
      {showSystemPage && page === "audit" ? (
        <AuditHistory
          selectedPage={selectedPage}
          guildId={guildId}
          entries={audit}
          state={sectionStates.audit}
          hasMore={auditHasMore}
          onLoad={id => { void loadAudit(id); }}
          onLoadMore={id => { if (auditCursor) void loadAudit(id, false, auditCursor, true); }}
        />
      ) : null}
      {showSystemPage && page === "diagnostics" ? <DiagnosticsPage selectedPage={selectedPage} system={system} state={sectionStates.system} onLoadSystem={() => { void loadSystem(); }} /> : null}
      {showSystemPage && page === "logs" ? <RuntimeLogs
        selectedPage={selectedPage}
        state={sectionStates.logs}
        logName={logName}
        logText={logText}
        file={logFile}
        onChangeFile={file => { void loadLogs(file); }}
        onLoad={() => { void loadLogs(); }}
      /> : null}
      {showSystemPage && page === "integrations" ? <IntegrationsPage selectedPage={selectedPage} integrations={integrations} state={sectionStates.integrations} onLoad={() => { void loadIntegrations(); }} /> : null}
      {showSystemPage && page === "database" ? <DatabaseStatus selectedPage={selectedPage} resources={resources} state={sectionStates.database} onLoad={() => { void loadDatabase(); }} /> : null}
            </DashboardShell>
          )}
        </SessionGuard>
      </ConsentProvider>
    </SessionProvider>
  );
}

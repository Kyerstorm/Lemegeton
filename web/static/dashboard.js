(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = { user: null, guilds: [], guild: null, commands: [], audit: [], page: "overview", filter: "All", busy: false };
  const titles = { overview: "Overview", commands: "Commands", audit: "Audit trail", system: "System health", logs: "Runtime logs", database: "Data overview" };

  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    if (response.status === 401) { window.location.assign("/login"); throw new Error("Your session expired. Sign in again."); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }
  function toast(message, error = false) {
    const el = document.createElement("div"); el.className = "toast" + (error ? " error" : ""); el.textContent = message;
    $("#toastStack").append(el); window.setTimeout(() => el.remove(), 3600);
  }
  function setText(selector, value) { const node = $(selector); if (node) node.textContent = value == null || value === "" ? "—" : String(value); }
  function fmt(value) { return Number(value || 0).toLocaleString(); }
  function safe(value) { return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[ch]); }
  function timeAgo(value) {
    if (!value) return "Unknown time";
    const date = new Date(value); if (Number.isNaN(date.getTime())) return String(value);
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return "Just now";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.floor(seconds / 3600) + "h ago";
    return Math.floor(seconds / 86400) + "d ago";
  }
  function switchPage(name) {
    if (!titles[name]) return;
    state.page = name;
    $$("[data-view]").forEach(node => node.classList.toggle("hidden", node.dataset.view !== name));
    $$(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.page === name));
    setText("#breadcrumb", titles[name]);
    if (name === "commands") renderCommands();
    if (name === "audit") loadAudit();
    if (name === "system") loadSystem();
    if (name === "logs") loadLogs();
  }
  function selectedGuild() { return state.guilds.find(g => String(g.id) === String(state.guild)); }
  async function loadBootstrap() {
    const data = await api("/api/bootstrap");
    state.user = data.user; state.guilds = data.guilds || [];
    setText("#userName", state.user.global_name || state.user.username);
    setText("#userAvatar", (state.user.global_name || state.user.username || "?").slice(0, 1).toUpperCase());
    setText("#welcomeName", (state.user.global_name || state.user.username || "back.").split(" ")[0] + ".");
    const picker = $("#guildPicker"); picker.replaceChildren();
    if (!state.guilds.length) {
      const opt = new Option("No manageable servers", ""); picker.add(opt); picker.disabled = true;
      throw new Error("No servers were found where you have Manage Server permission and the bot is present.");
    }
    state.guild = data.selected_guild_id && state.guilds.some(g => String(g.id) === String(data.selected_guild_id)) ? String(data.selected_guild_id) : String(state.guilds[0].id);
    for (const guild of state.guilds) picker.add(new Option(guild.name, String(guild.id)));
    picker.value = state.guild;
    picker.addEventListener("change", async () => {
      state.guild = picker.value;
      await refreshAll();
      toast("Switched server context.");
    });
    await refreshAll();
  }
  async function refreshAll() {
    if (!state.guild) return;
    const guild = selectedGuild();
    setText("#guildNameValue", guild?.name);
    setText("#guildIdValue", state.guild);
    setText("#guildPermissionValue", guild?.administrator ? "Administrator" : "Manage Server");
    setText("#metricGuilds", fmt(state.guilds.length));
    setText("#connectionLabel", "Connected to dashboard");
    try {
      const [overview, commands] = await Promise.all([
        api(`/api/guilds/${state.guild}/overview`),
        api(`/api/guilds/${state.guild}/commands`)
      ]);
      state.commands = commands.commands || [];
      paintOverview(overview);
      renderCommands();
      await loadAudit(true);
      setText("#lastRefresh", new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    } catch (error) { toast(error.message, true); }
  }
  function paintOverview(data) {
    const bot = data.bot || {};
    const total = state.commands.length;
    const enabled = state.commands.filter(c => c.enabled).length;
    setText("#metricCommands", fmt(total));
    setText("#metricCommandEnabled", `${fmt(enabled)} enabled`);
    setText("#metricMembers", bot.member_count == null ? "Unavailable" : fmt(bot.member_count));
    setText("#metricLatency", bot.latency_ms == null ? "— ms" : `${Math.round(bot.latency_ms)} ms`);
    setText("#gatewayState", bot.ready ? "Gateway connected" : "Gateway unavailable");
    setText("#runtimePill", bot.ready ? "OPERATIONAL" : "OFFLINE");
    setText("#runtimeTitle", bot.ready ? "The bot is connected" : "The bot is not ready");
    setText("#runtimeDescription", bot.ready ? "The Discord gateway is connected. This status is reported by the live bot process." : "The process is running but has not reported a ready Discord connection.");
    setText("#healthGuilds", fmt(bot.guild_count));
    setText("#healthCogs", fmt(bot.extension_count));
    setText("#chartEnabledLabel", `Enabled commands ${enabled}`);
    setText("#chartDisabledLabel", `Disabled commands ${Math.max(0, total - enabled)}`);
    setText("#commandCount", fmt(total));
    setText("#guildHeading", selectedGuild()?.name);
    const pct = total ? enabled / total : 0;
    const points = Array.from({ length: 7 }, (_, i) => {
      const x = 40 + i * (440 / 6);
      const y = 130 - pct * 100 * (0.74 + 0.26 * (i / 6));
      return [x, y];
    });
    const path = points.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
    $("#chartLinePath").setAttribute("d", path);
    $("#chartFillPath").setAttribute("d", path + "L480 130H40Z");
    $("#chartDots").innerHTML = points.filter((_, i) => i % 2 === 1).map(p => `<circle class="chart-dot" cx="${p[0]}" cy="${p[1]}" r="3.5"/>`).join("");
    $("#chartTooltip").textContent = `${enabled} enabled · ${total - enabled} disabled`;
  }
  function renderCommands() {
    const list = $("#commandList"); if (!list) return;
    const query = ($("#commandSearch")?.value || "").toLowerCase().trim();
    const filtered = state.commands.filter(cmd => (state.filter === "All" || cmd.section === state.filter || (state.filter === "Other" && !["General", "Media", "Administration"].includes(cmd.section))) && `${cmd.fullname} ${cmd.name} ${cmd.description} ${cmd.section}`.toLowerCase().includes(query));
    if (!filtered.length) { list.innerHTML = '<div class="empty-state">No commands match this filter.</div>'; return; }
    list.innerHTML = filtered.map(cmd => `<article class="command-row">
      <div><div class="command-name"><span class="slash">/</span>${safe(cmd.fullname || cmd.name)}</div><p class="command-description">${safe(cmd.description || "No description provided.")}</p><div class="command-tags"><span class="tag">${safe(cmd.section || "Other")}</span>${cmd.protected ? '<span class="tag">Protected</span>' : ""}</div></div>
      <span class="command-state">${cmd.protected ? "Always enabled" : (cmd.enabled ? "Enabled" : "Disabled")}</span>
      <button class="toggle" role="switch" aria-checked="${cmd.enabled ? "true" : "false"}" aria-label="${safe(cmd.fullname)}" ${cmd.protected ? "disabled title=\"Protected command\"" : ""} data-command="${safe(cmd.fullname)}"></button>
    </article>`).join("");
    $$("[data-command]").forEach(button => button.addEventListener("click", async () => {
      const cmd = state.commands.find(item => item.fullname === button.dataset.command);
      if (!cmd || cmd.protected || button.disabled) return;
      button.disabled = true;
      try {
        const result = await api(`/api/guilds/${state.guild}/commands/${encodeURIComponent(cmd.fullname)}`, { method: "PUT", body: JSON.stringify({ enabled: !cmd.enabled }) });
        cmd.enabled = Boolean(result.enabled);
        renderCommands();
        toast(`/${cmd.fullname} ${cmd.enabled ? "enabled" : "disabled"} for this server.`);
        const total = state.commands.length, enabled = state.commands.filter(c => c.enabled).length;
        setText("#metricCommandEnabled", `${fmt(enabled)} enabled`);
        setText("#chartEnabledLabel", `Enabled commands ${enabled}`);
        setText("#chartDisabledLabel", `Disabled commands ${total - enabled}`);
      } catch (error) { toast(error.message, true); button.disabled = false; }
    }));
  }
  function renderActivity(entries, target) {
    const node = $(target); if (!node) return;
    if (!entries?.length) { node.innerHTML = '<div class="empty-state">No audit entries have been recorded for this server yet.</div>'; return; }
    node.innerHTML = entries.map((entry, index) => {
      const action = String(entry.action || "Administrative action").replaceAll("_", " ");
      const kind = /reset|remove|delete/i.test(action) ? "gold" : /toggle|enable|disable|sync/i.test(action) ? "mint" : "";
      return `<div class="activity-row"><span class="activity-icon ${kind}">${kind === "gold" ? "↻" : kind === "mint" ? "✓" : "◷"}</span><div class="activity-copy"><strong>${safe(action)}</strong><span>${safe(entry.details || "No additional details")} · by ${safe(entry.actor_name || entry.actor_id || "Unknown user")}</span></div><time class="activity-time">${safe(timeAgo(entry.ts || entry.created_at))}</time></div>`;
    }).join("");
  }
  async function loadAudit(quiet = false) {
    try {
      const data = await api(`/api/guilds/${state.guild}/audit`);
      state.audit = data.entries || [];
      renderActivity(state.audit.slice(0, 5), "#overviewActivity");
      renderActivity(state.audit, "#auditList");
    } catch (error) { if (!quiet) toast(error.message, true); }
  }
  async function loadSystem() {
    try {
      const data = await api("/api/system");
      const values = [
        ["Discord gateway", data.ready ? "Connected" : "Not ready"],
        ["Gateway latency", data.latency_ms == null ? "Unavailable" : Math.round(data.latency_ms) + " ms"],
        ["Connected guilds", data.guild_count],
        ["Loaded extensions", data.extension_count],
        ["Python runtime", data.python_version || "Unavailable"],
        ["Process uptime", data.uptime || "Unavailable"]
      ];
      $("#systemValues").innerHTML = values.map(([k,v]) => `<div class="key-value-row"><span>${safe(k)}</span><strong>${safe(v ?? "—")}</strong></div>`).join("");
      setText("#systemState", data.ready ? "CONNECTED" : "NOT READY");
      setText("#extensionCount", `${(data.extensions || []).length} loaded`);
      $("#extensionList").innerHTML = (data.extensions || []).length ? data.extensions.map(name => `<div class="extension-row"><code>${safe(name)}</code><span class="state-ok">Loaded</span></div>`).join("") : '<div class="empty-state">No loaded extensions were reported.</div>';
    } catch (error) { toast(error.message, true); }
  }
  async function loadLogs() {
    try {
      const file = $("#logPicker").value;
      const data = await api(`/api/logs?file=${encodeURIComponent(file)}`);
      setText("#logFilename", data.name || file);
      $("#logText").textContent = data.content || "No log entries found.";
    } catch (error) { $("#logText").textContent = error.message; }
  }
  async function syncCommands() {
    const button = $("#syncButton") || $("#syncButtonCommands");
    if (state.busy) return;
    state.busy = true; if (button) button.disabled = true;
    try {
      const data = await api(`/api/guilds/${state.guild}/sync`, { method: "POST", body: "{}" });
      toast(`Synchronized ${data.synced ?? "the"} commands with Discord.`);
      await refreshAll();
    } catch (error) { toast(error.message, true); }
    finally { state.busy = false; if (button) button.disabled = false; }
  }
  async function resetCommands() {
    if (!window.confirm("Reset this server’s command settings to the defaults?")) return;
    try {
      await api(`/api/guilds/${state.guild}/reset`, { method: "POST", body: "{}" });
      await refreshAll(); toast("Command configuration reset.");
    } catch (error) { toast(error.message, true); }
  }
  function bind() {
    $("#mainNav").addEventListener("click", e => { const button = e.target.closest("[data-page]"); if (button) switchPage(button.dataset.page); });
    $$("[data-jump]").forEach(button => button.addEventListener("click", () => switchPage(button.dataset.jump)));
    $("#commandFilters").addEventListener("click", e => { const button = e.target.closest("[data-filter]"); if (!button) return; state.filter = button.dataset.filter; $$("#commandFilters button").forEach(b => b.classList.toggle("active", b === button)); renderCommands(); });
    $("#commandSearch").addEventListener("input", renderCommands);
    $("#refreshButton").addEventListener("click", () => refreshAll().then(() => toast("Dashboard refreshed.")));
    $("#syncButton").addEventListener("click", syncCommands);
    $("#syncButtonCommands").addEventListener("click", syncCommands);
    $("#resetButton").addEventListener("click", resetCommands);
    $("#openAudit").addEventListener("click", () => switchPage("audit"));
    $("#refreshAudit").addEventListener("click", () => loadAudit());
    $("#refreshSystem").addEventListener("click", loadSystem);
    $("#refreshLogs").addEventListener("click", loadLogs);
    $("#logPicker").addEventListener("change", loadLogs);
  }
  async function start() {
    bind();
    try { await loadBootstrap(); }
    catch (error) { toast(error.message, true); setText("#connectionLabel", "Connection issue"); }
  }
  document.addEventListener("DOMContentLoaded", start);
})();
use axum::{
    body::Body,
    extract::Path,
    http::{header, StatusCode},
    response::{Html, IntoResponse, Response},
};

const DASHBOARD_HTML: &str = r####"<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#080808">
  <title>Lemegeton / Control</title>
  <link rel="stylesheet" href="/static/dashboard.css">
  <script src="/static/dashboard.js" defer></script>
</head>
<body>
  <div class="shell" id="appShell">
    <aside class="sidebar" id="sidebar">
      <a class="brand" href="/" aria-label="Lemegeton dashboard home">
        <span class="brand-mark" aria-hidden="true">L.</span>
        <span class="brand-copy"><strong>LEMEGETON</strong><small>BOT CONTROL</small></span>
      </a>
      <div class="sidebar-rule"></div>
      <p class="nav-label">WORKSPACE / 01</p>
      <nav id="mainNav" aria-label="Dashboard navigation">
        <button class="nav-item active" type="button" data-page="overview"><span class="nav-glyph">⌂</span>Overview</button>
        <button class="nav-item" type="button" data-page="commands"><span class="nav-glyph">⌘</span>Commands<span class="nav-count" id="commandCount">—</span></button>
        <button class="nav-item" type="button" data-page="extensions"><span class="nav-glyph">▦</span>Extensions</button>
        <button class="nav-item" type="button" data-page="audit"><span class="nav-glyph">◷</span>Audit history</button>
        <button class="nav-item" type="button" data-page="diagnostics"><span class="nav-glyph">⌁</span>Diagnostics</button>
        <button class="nav-item" type="button" data-page="logs"><span class="nav-glyph">≡</span>Runtime logs</button>
        <button class="nav-item" type="button" data-page="integrations"><span class="nav-glyph">⟷</span>Integrations</button>
        <button class="nav-item" type="button" data-page="database"><span class="nav-glyph">▤</span>Persistence</button>
      </nav>
      <div class="sidebar-fill"></div>
      <div class="sidebar-system">
        <span class="signal-dot" id="sidebarSignal"></span>
        <div><strong id="connectionLabel">Checking bot bridge</strong><small id="connectionTime">STATUS / UNKNOWN</small></div>
      </div>
      <button class="signout" id="logoutButton" type="button">Sign out <span aria-hidden="true">↗</span></button>
    </aside>
    <div class="mobile-scrim" id="mobileScrim"></div>

    <main class="main">
      <header class="topbar">
        <button class="icon-button mobile-menu" id="mobileMenuButton" type="button" aria-label="Open navigation" aria-expanded="false">☰</button>
        <div class="breadcrumb"><span>CONTROL</span><span class="breadcrumb-divider">/</span><strong id="breadcrumb">Overview</strong></div>
        <div class="topbar-right">
          <label class="guild-control"><span>SERVER</span><select id="guildPicker" aria-label="Select Discord server"><option value="">Loading…</option></select></label>
          <button class="icon-button" id="refreshButton" type="button" aria-label="Refresh dashboard" title="Refresh dashboard">↻</button>
          <div class="account" aria-label="Signed-in Discord account"><span class="avatar" id="userAvatar">·</span><span><strong id="userName">Loading account</strong><small id="userRole">DISCORD ACCOUNT</small></span></div>
        </div>
      </header>

      <section class="page" data-view="overview">
        <div class="page-heading">
          <div><p class="eyebrow">LIVE CONTROL / 01</p><h1>Bot <span>overview.</span></h1><p class="lede">Current runtime information and the effective command configuration for the selected server.</p></div>
          <div class="heading-actions"><button class="button secondary" id="openAudit" type="button">View activity <span aria-hidden="true">↗</span></button><button class="button primary" id="syncButton" type="button">Publish commands <span aria-hidden="true">↗</span></button></div>
        </div>
        <div class="status-strip"><span class="unicode-spinner" aria-hidden="true">⠿</span><span id="runtimePill">STATUS / CHECKING</span><span class="strip-separator">—</span><span id="runtimeDescription">Reading status from the bot process.</span><time id="lastRefresh">NOT CHECKED</time></div>
        <div class="metric-grid">
          <article class="metric"><div class="metric-label">MANAGED COMMANDS <span>01</span></div><strong class="metric-value" id="metricCommands">—</strong><p><span id="metricEnabled">— enabled</span><span class="metric-dot">·</span><span id="metricDisabled">— disabled</span></p></article>
          <article class="metric"><div class="metric-label">GUILD MEMBERS <span>02</span></div><strong class="metric-value" id="metricMembers">—</strong><p>Selected Discord server</p></article>
          <article class="metric"><div class="metric-label">BOT GUILDS <span>03</span></div><strong class="metric-value" id="metricGuilds">—</strong><p>Guilds visible to your account</p></article>
          <article class="metric"><div class="metric-label">GATEWAY LATENCY <span>04</span></div><strong class="metric-value" id="metricLatency">—<small>ms</small></strong><p id="gatewayState">Waiting for gateway status</p></article>
        </div>
        <div class="content-grid">
          <article class="panel panel-large">
            <div class="panel-heading"><div><p class="eyebrow">PROCESS STATUS</p><h2>Runtime signal</h2></div><span class="panel-index">A / 04</span></div>
            <div class="runtime-body"><div class="runtime-mark" aria-hidden="true"><span>⠿</span><i></i></div><div><p class="runtime-state" id="runtimeTitle">Waiting for a response</p><p class="muted" id="runtimeCopy">The dashboard and Discord gateway are tracked separately.</p><div class="runtime-flags"><span id="flagGateway">GATEWAY / UNKNOWN</span><span id="flagBridge">BRIDGE / UNKNOWN</span></div></div></div>
            <div class="runtime-data"><div><small>PROCESS UPTIME</small><strong id="runtimeUptime">—</strong></div><div><small>PYTHON RUNTIME</small><strong id="runtimePython">—</strong></div><div><small>LOADED EXTENSIONS</small><strong id="runtimeExtensions">—</strong></div></div>
          </article>
          <article class="panel">
            <div class="panel-heading"><div><p class="eyebrow">RECENT CHANGES</p><h2>Audit history</h2></div><button class="text-button" data-jump="audit" type="button">All events ↗</button></div>
            <div class="activity-list" id="overviewActivity"><p class="empty-state">Reading saved audit history…</p></div>
          </article>
          <article class="panel">
            <div class="panel-heading"><div><p class="eyebrow">EFFECTIVE CONFIGURATION</p><h2>Command access</h2></div><button class="text-button" data-jump="commands" type="button">Manage ↗</button></div>
            <div class="distribution"><div class="distribution-label"><strong id="availabilityPercent">—</strong><span>commands enabled</span></div><div class="distribution-track" role="img" aria-label="Share of commands enabled"><span id="enabledBar"></span></div><div class="distribution-meta"><span id="chartEnabledLabel">Enabled —</span><span id="chartDisabledLabel">Disabled —</span></div></div>
          </article>
          <article class="panel">
            <div class="panel-heading"><div><p class="eyebrow">SELECTED SERVER</p><h2>Guild context</h2></div><span class="panel-index">G / 01</span></div>
            <dl class="definition-list"><div><dt>Server</dt><dd id="guildNameValue">—</dd></div><div><dt>Guild ID</dt><dd id="guildIdValue">—</dd></div><div><dt>Your permission</dt><dd id="guildPermissionValue">—</dd></div><div><dt>Bot membership</dt><dd id="guildMembership">Unknown</dd></div></dl>
          </article>
        </div>
      </section>

      <section class="page hidden" data-view="commands">
        <div class="page-heading"><div><p class="eyebrow">COMMAND REGISTRY / 02</p><h1>Command <span>access.</span></h1><p class="lede">Changes apply to this guild and are confirmed only after the live bot synchronizes with Discord. Protected system commands stay enabled.</p></div><div class="heading-actions"><button class="button secondary" id="resetButton" type="button">Reset server overrides</button><button class="button primary" id="syncButtonCommands" type="button">Publish commands ↗</button></div></div>
        <div class="command-toolbar"><label class="search-field"><span aria-hidden="true">⌕</span><input id="commandSearch" type="search" placeholder="Search command name or description…" autocomplete="off"></label><label class="filter-control"><span>CATEGORY</span><select id="commandFilterCategory" aria-label="Filter by command category"><option value="All">All categories</option></select></label><label class="filter-control"><span>STATE</span><select id="commandFilterState" aria-label="Filter by enabled state"><option value="All">All states</option><option value="Enabled">Enabled</option><option value="Disabled">Disabled</option><option value="Protected">Protected</option></select></label></div>
        <div class="command-summary"><span id="commandResultCount">Commands are loaded from the live bot registry.</span><span>PER-GUILD CONFIGURATION</span></div>
        <div class="command-list" id="commandList"><div class="loading-state"><span class="unicode-spinner" aria-hidden="true">⠿</span> Reading command registry…</div></div>
        <p class="footnote">This registry exposes the slash commands explicitly registered for dashboard management. Prefix commands and runtime extension unloading are not implied to be manageable here.</p>
      </section>

      <section class="page hidden" data-view="extensions">
        <div class="page-heading"><div><p class="eyebrow">BOT MODULES / 03</p><h1>Loaded <span>extensions.</span></h1><p class="lede">Runtime extension status reported by the Python bot. Modules are informational here; load/unload/reload is intentionally not exposed because it can interrupt core bot operations.</p></div><button class="button secondary" id="refreshSystem" type="button">Refresh status ↻</button></div>
        <div class="panel"><div class="panel-heading"><div><p class="eyebrow">ACTIVE PROCESS</p><h2>Extension inventory</h2></div><span class="panel-index" id="extensionCount">—</span></div><div class="extension-list" id="extensionList"><p class="empty-state">Loading live extensions…</p></div></div>
        <p class="footnote">An extension appearing in this list means the current bot process reports it as loaded. It does not imply that safe runtime reloading is supported.</p>
      </section>

      <section class="page hidden" data-view="audit">
        <div class="page-heading"><div><p class="eyebrow">CHANGE RECORD / 04</p><h1>Nothing <span>unaccounted.</span></h1><p class="lede">Recorded dashboard configuration changes for the selected server.</p></div><button class="button secondary" id="refreshAudit" type="button">Refresh history ↻</button></div>
        <div class="panel"><div class="panel-heading"><div><p class="eyebrow">PERSISTED EVENTS</p><h2>Audit trail</h2></div><span class="panel-index">25 MOST RECENT</span></div><div class="activity-list activity-list-full" id="auditList"><p class="empty-state">Loading audit entries…</p></div></div>
      </section>

      <section class="page hidden" data-view="diagnostics">
        <div class="page-heading"><div><p class="eyebrow">HEALTH & TELEMETRY / 05</p><h1>Under the <span>surface.</span></h1><p class="lede">Bot gateway status, runtime version, uptime, and the last observed status when the bridge is unavailable.</p></div><button class="button secondary" id="refreshDiagnostics" type="button">Check now ↻</button></div>
        <div class="content-grid"><article class="panel"><div class="panel-heading"><div><p class="eyebrow">STATUS SNAPSHOT</p><h2>Runtime details</h2></div><span class="panel-index">LIVE</span></div><dl class="definition-list" id="diagnosticValues"><div><dt>Gateway</dt><dd>Checking…</dd></div></dl></article><article class="panel"><div class="panel-heading"><div><p class="eyebrow">BOUNDARIES</p><h2>Service availability</h2></div></div><div class="note-block"><strong>Two separate signals.</strong><p>Dashboard HTTP availability does not mean the Discord gateway is connected. A cached observation is labelled with its timestamp and is not presented as live status.</p></div><div class="note-block"><strong>Control operations require the bot.</strong><p>When the bridge or Discord synchronization is unavailable, command changes fail safely rather than showing a false success.</p></div></article></div>
      </section>

      <section class="page hidden" data-view="logs">
        <div class="page-heading"><div><p class="eyebrow">RUNTIME OUTPUT / 06</p><h1>Logs, without <span>guesswork.</span></h1><p class="lede">Recent log output. Access is restricted to configured dashboard owners because logs may include operational details.</p></div><button class="button secondary" id="refreshLogs" type="button">Refresh log ↻</button></div>
        <div class="panel log-panel"><div class="log-toolbar"><div><p class="eyebrow">FILE READER</p><h2 id="logFilename">bot.log</h2></div><label class="filter-control"><span>LOG SOURCE</span><select id="logPicker" aria-label="Select runtime log"><option value="bot.log">bot.log</option><option value="dashboard.log">dashboard.log</option></select></label></div><pre id="logText" tabindex="0">Loading log output…</pre></div>
      </section>

      <section class="page hidden" data-view="integrations">
        <div class="page-heading"><div><p class="eyebrow">CONNECTED SERVICES / 07</p><h1>Integration <span>status.</span></h1><p class="lede">Only configuration presence is shown. Credentials and secret values are never returned to the browser.</p></div><button class="button secondary" id="refreshIntegrations" type="button">Refresh ↻</button></div>
        <div class="panel"><div class="panel-heading"><div><p class="eyebrow">BOT-WIDE CONFIGURATION</p><h2>Provider availability</h2></div><span class="panel-index">OWNER ONLY</span></div><div class="extension-list" id="integrationList"><p class="empty-state">Checking integration configuration…</p></div></div>
      </section>

      <section class="page hidden" data-view="database">
        <div class="page-heading"><div><p class="eyebrow">PERSISTENCE / 08</p><h1>State that <span>survives.</span></h1><p class="lede">The existing shared PostgreSQL storage used by the bot for guild command overrides and audit entries.</p></div><button class="button secondary" id="refreshDatabase" type="button">Refresh ↻</button></div>
        <div class="panel"><div class="panel-heading"><div><p class="eyebrow">PERSISTED RESOURCES</p><h2>Storage overview</h2></div></div><div class="table-scroll"><table><thead><tr><th>RESOURCE</th><th>PURPOSE / DETAILS</th><th>STATE</th></tr></thead><tbody id="databaseRows"><tr><td colspan="3">Loading resources…</td></tr></tbody></table></div></div>
      </section>
      <footer class="page-footer"><span>LEMEGETON / CONTROL PLANE</span><span id="footerStatus">PRIVATE SESSION · LIVE DATA WHERE AVAILABLE</span></footer>
    </main>
  </div>
  <div class="toast-stack" id="toastStack" role="status" aria-live="polite" aria-atomic="false"></div>
  <dialog class="confirm-dialog" id="confirmDialog" aria-labelledby="confirmTitle"><form method="dialog"><p class="eyebrow">CONFIRM ACTION</p><h2 id="confirmTitle">Review change</h2><p id="confirmMessage">Confirm this operation.</p><div class="dialog-actions"><button class="button secondary" value="cancel">Cancel</button><button class="button primary" id="confirmAccept" value="confirm">Confirm</button></div></form></dialog>
</body>
</html>
"####;
const LOGIN_HTML: &str = r####"<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#080808"><title>Sign in / Lemegeton</title><link rel="stylesheet" href="/static/dashboard.css"></head>
<body class="login-body">
  <main class="login-shell">
    <a class="brand login-brand" href="/" aria-label="Lemegeton home"><span class="brand-mark">L.</span><span class="brand-copy"><strong>LEMEGETON</strong><small>BOT CONTROL</small></span></a>
    <div class="login-art" aria-hidden="true"><div class="art-grid"></div><div class="art-circle"></div><div class="art-cross">+</div><div class="art-code">0101<br>1010<br>0011</div><div class="art-word">L / 01</div></div>
    <p class="eyebrow">PRIVATE ADMINISTRATION / AUTH 01</p>
    <h1>Control begins<br>with <span>verification.</span></h1>
    <p class="login-description">Manage the real Lemegeton bot through your Discord identity. Server permissions are checked again whenever you perform an operation.</p>
    <a class="button primary login-button" href="/oauth/start">Continue with Discord <span aria-hidden="true">↗</span></a>
    <p class="login-foot">This dashboard never asks for your Discord password. OAuth requests only identity and the guild list required to verify server-management access. Bot tokens and provider credentials never enter the browser.</p>
    <div class="login-bottom"><span>LEMEGETON / CONTROL PLANE</span><span>AUTHENTICATED ACCESS ONLY</span></div>
  </main>
</body>
</html>
"####;
const DASHBOARD_CSS: &str = r####":root{color-scheme:dark;--bg:#080808;--surface:#101010;--surface-2:#151515;--surface-3:#1b1b1b;--line:#282828;--line-strong:#414141;--text:#f2f2f2;--soft:#b7b7b7;--muted:#777;--dim:#505050;--ease:cubic-bezier(.2,.8,.2,1);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-synthesis:none;text-rendering:optimizeLegibility}
*{box-sizing:border-box}
html{min-height:100%;background:var(--bg);scroll-behavior:smooth}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-size:13px;line-height:1.55;-webkit-font-smoothing:antialiased}
button,input,select{font:inherit}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.48}
a{color:inherit;text-decoration:none}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,pre:focus-visible{outline:2px solid #eee;outline-offset:3px}
::selection{background:#eee;color:#080808}
.hidden{display:none!important}
.shell{min-height:100vh;display:grid;grid-template-columns:248px minmax(0,1fr)}
.sidebar{height:100vh;position:sticky;top:0;display:flex;flex-direction:column;padding:25px 17px 14px;border-right:1px solid var(--line);background:#0b0b0b;z-index:20;overflow-y:auto}
.brand{display:flex;align-items:center;gap:11px;padding:0 7px 24px}
.brand-mark{display:grid;place-items:center;width:37px;height:37px;border:1px solid #4a4a4a;color:#fff;font:italic 26px Georgia,serif;letter-spacing:-.08em}
.brand-copy strong{display:block;font-size:11px;font-weight:700;letter-spacing:.16em}
.brand-copy small{display:block;margin-top:3px;color:var(--muted);font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}
.sidebar-rule{height:1px;background:var(--line);margin-bottom:25px}
.nav-label,.eyebrow{margin:0;color:#818181;font:10px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.13em;text-transform:uppercase}
.nav-label{padding:0 10px 12px}
.sidebar nav{display:grid;gap:3px}
.nav-item{display:flex;align-items:center;gap:10px;min-height:41px;padding:9px 10px;border:1px solid transparent;background:transparent;color:#a1a1a1;text-align:left;transition:color .16s,border-color .16s,background .16s}
.nav-item:hover{background:#131313;color:#fff}
.nav-item.active{color:#fff;border-color:#343434;background:#171717}
.nav-glyph{display:inline-grid;place-items:center;width:17px;color:#858585;font-size:15px}
.nav-item.active .nav-glyph{color:#fff}
.nav-count{margin-left:auto;color:#8e8e8e;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}
.sidebar-fill{flex:1;min-height:30px}
.sidebar-system{display:flex;align-items:center;gap:10px;padding:14px 7px;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.signal-dot{width:7px;height:7px;background:#8a8a8a;flex:none}
.signal-dot.online{background:#f0f0f0}
.sidebar-system strong,.sidebar-system small{display:block;overflow-wrap:anywhere}
.sidebar-system strong{font-size:10px;font-weight:600}
.sidebar-system small{margin-top:3px;color:var(--muted);font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
.signout{display:flex;justify-content:space-between;margin-top:12px;padding:9px 8px;border:0;background:transparent;color:#858585;text-align:left}
.signout:hover{color:#fff}
.main{min-width:0}
.topbar{height:72px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 clamp(18px,3vw,44px);border-bottom:1px solid var(--line);background:#0a0a0a}
.breadcrumb{display:flex;align-items:center;gap:11px;color:#777;font:10px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.09em}
.breadcrumb strong{color:#eee;font-weight:500;letter-spacing:0}
.breadcrumb-divider{color:#454545}
.topbar-right{display:flex;align-items:center;gap:12px;min-width:0}
.guild-control,.filter-control{display:grid;gap:4px;min-width:160px}
.guild-control>span,.filter-control>span{color:var(--muted);font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}
.guild-control select,.filter-control select{max-width:240px;padding:7px 28px 7px 9px;border:1px solid var(--line-strong);border-radius:0;background:#111;color:var(--text);font-size:11px}
.icon-button{display:grid;place-items:center;width:35px;height:35px;border:1px solid var(--line-strong);background:#111;color:#c8c8c8;font-size:16px}
.icon-button:hover{background:#1a1a1a;color:#fff}
.account{display:flex;align-items:center;gap:9px;padding-left:4px;min-width:0}
.avatar{display:grid;place-items:center;width:31px;height:31px;flex:none;border:1px solid #414141;background:#161616;color:#eee;font-size:12px}
.account strong,.account small{display:block;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.account strong{font-size:10px;font-weight:600}
.account small{margin-top:3px;color:var(--muted);font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
.mobile-menu,.mobile-scrim{display:none}
.page{width:min(100%,1540px);padding:32px clamp(18px,3vw,44px) 30px;margin:0 auto;animation:page-in .24s var(--ease) both}
.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:23px}
h1{margin:10px 0 9px;font-size:clamp(30px,3.1vw,44px);line-height:1.08;letter-spacing:-.06em;font-weight:560}
h1 span{color:#777;font-weight:450}
.lede{max-width:690px;margin:0;color:#959595;font-size:12px;line-height:1.75}
.heading-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
.button{display:inline-flex;align-items:center;justify-content:center;gap:12px;min-height:37px;padding:9px 13px;border:1px solid #494949;border-radius:0;background:#111;color:#e5e5e5;font-size:10px;font-weight:600;transition:background .16s,border-color .16s,transform .16s}
.button:hover{border-color:#888;background:#1a1a1a}
.button:active{transform:translateY(1px)}
.button.primary{background:#f0f0f0;border-color:#f0f0f0;color:#080808}
.button.primary:hover{background:#fff}
.status-strip{display:flex;align-items:center;gap:11px;min-height:44px;padding:10px 12px;margin-bottom:13px;border:1px solid var(--line);background:#0d0d0d;color:#aaa;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}
.status-strip #runtimePill{color:#eee;white-space:nowrap}
.status-strip #runtimeDescription{font-family:inherit;color:#8a8a8a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status-strip time{margin-left:auto;color:#777;white-space:nowrap;font-size:9px}
.strip-separator{color:#4c4c4c}
.unicode-spinner{display:inline-block;color:#eee;font-size:15px;min-width:1em;text-align:center}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:13px}
.metric{min-width:0;padding:16px 16px 15px;border:1px solid var(--line);background:var(--surface);animation:page-in .4s var(--ease) both}
.metric:nth-child(2){animation-delay:.025s}.metric:nth-child(3){animation-delay:.05s}.metric:nth-child(4){animation-delay:.075s}
.metric-label{display:flex;justify-content:space-between;gap:6px;color:#a4a4a4;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em}
.metric-label span{color:#555}
.metric-value{display:flex;align-items:baseline;gap:6px;margin:17px 0 6px;font-size:clamp(25px,2.4vw,34px);line-height:1;letter-spacing:-.06em;font-weight:500;font-variant-numeric:tabular-nums}
.metric-value small{font-size:11px;letter-spacing:0;color:#888;font-weight:400}
.metric p{margin:0;color:#777;font-size:10px}
.metric-dot{padding:0 5px;color:#4d4d4d}
.number-changed{animation:number-shift .32s var(--ease) both}
.content-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(280px,.9fr);gap:13px;align-items:start}
.panel{min-width:0;border:1px solid var(--line);background:#0e0e0e}
.panel-large{grid-column:auto}
.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;padding:17px 18px 15px;border-bottom:1px solid var(--line)}
.panel-heading h2{margin:6px 0 0;font-size:13px;font-weight:550;letter-spacing:-.02em}
.panel-index{color:#666;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em}
.text-button{padding:2px 0;border:0;background:transparent;color:#aaa;font-size:10px}
.text-button:hover{color:#fff}
.runtime-body{display:flex;align-items:center;gap:19px;padding:22px 18px 19px}
.runtime-mark{position:relative;display:grid;place-items:center;width:68px;height:68px;flex:none;border:1px solid #484848;color:#eee;font-size:26px}
.runtime-mark i{position:absolute;right:-3px;bottom:5px;width:7px;height:7px;background:#888;border:1px solid #0e0e0e}
.runtime-state{margin:0 0 5px;font-size:15px;font-weight:550;letter-spacing:-.025em}
.muted{max-width:460px;margin:0;color:#888;font-size:11px;line-height:1.7}
.runtime-flags{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.runtime-flags span{padding:4px 6px;border:1px solid #313131;color:#aaa;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
.runtime-data{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid var(--line)}
.runtime-data div{min-width:0;padding:12px 13px;border-right:1px solid var(--line)}
.runtime-data div:last-child{border-right:0}
.runtime-data small,.runtime-data strong{display:block}
.runtime-data small{color:#777;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.07em}
.runtime-data strong{margin-top:6px;overflow-wrap:anywhere;color:#ddd;font-size:12px;font-weight:500}
.activity-list{min-width:0;padding:2px 17px}
.activity-row{display:grid;grid-template-columns:24px minmax(0,1fr) auto;align-items:start;gap:10px;padding:13px 0;border-bottom:1px solid #222}
.activity-row:last-child{border-bottom:0}
.activity-glyph{display:grid;place-items:center;width:23px;height:23px;border:1px solid #363636;color:#d2d2d2;font-size:11px}
.activity-copy{min-width:0}
.activity-copy strong{display:block;font-size:11px;font-weight:550;text-transform:capitalize}
.activity-copy small{display:block;margin-top:4px;color:#858585;font-size:10px;line-height:1.6;overflow-wrap:anywhere}
.activity-time{padding-top:2px;color:#666;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}
.empty-state,.loading-state{padding:23px 4px;color:#777;font-size:11px;line-height:1.8}
.loading-state{display:flex;align-items:center;gap:10px}
.distribution{padding:18px}
.distribution-label{display:flex;align-items:baseline;gap:10px}
.distribution-label strong{font-size:34px;letter-spacing:-.06em;font-weight:500;font-variant-numeric:tabular-nums}
.distribution-label span{color:#888;font-size:11px}
.distribution-track{height:5px;margin:17px 0 12px;background:#242424;border:1px solid #333}
.distribution-track span{display:block;width:0;height:100%;background:#eee;transition:width .28s var(--ease)}
.distribution-meta{display:flex;justify-content:space-between;gap:10px;color:#777;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
.definition-list{margin:0;padding:5px 17px 12px}
.definition-list>div{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:11px 0;border-bottom:1px solid #222}
.definition-list>div:last-child{border-bottom:0}
.definition-list dt{color:#818181;font-size:11px}
.definition-list dd{margin:0;text-align:right;color:#dedede;font-size:11px;overflow-wrap:anywhere}
.command-toolbar{display:flex;align-items:flex-end;gap:10px;margin:18px 0 10px}
.search-field{display:flex;align-items:center;gap:10px;flex:1;min-width:160px;min-height:40px;padding:0 12px;border:1px solid var(--line-strong);background:#101010;color:#999}
.search-field>span{font-size:17px}
.search-field input{width:100%;min-width:0;border:0;outline:0;background:transparent;color:#eee;font-size:11px}
.search-field input:focus-visible{outline:0}
.filter-control{min-width:135px}
.filter-control select{width:100%;max-width:none;min-height:40px;font-size:10px}
.command-summary{display:flex;justify-content:space-between;gap:10px;padding:10px 2px;color:#777;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em}
.command-list{border:1px solid var(--line);background:#0d0d0d}
.command-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(90px,auto) 46px;align-items:center;gap:15px;padding:15px 16px;border-bottom:1px solid #252525}
.command-row:last-child{border-bottom:0}
.command-name{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#eee;overflow-wrap:anywhere}
.command-name .command-prefix{color:#777;margin-right:4px}
.command-description{margin:5px 0 8px;color:#858585;font-size:10px;line-height:1.6;overflow-wrap:anywhere}
.command-tags{display:flex;gap:5px;flex-wrap:wrap}
.tag{padding:3px 6px;border:1px solid #333;color:#929292;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
.command-state{color:#aaa;font:10px ui-monospace,SFMono-Regular,Menlo,monospace}
.switch{position:relative;justify-self:end;width:39px;height:22px;padding:0;border:1px solid #535353;border-radius:0;background:#242424}
.switch:after{content:"";position:absolute;top:4px;left:4px;width:12px;height:12px;background:#aaa;transition:transform .17s var(--ease),background .17s}
.switch[aria-checked="true"]{background:#eee;border-color:#eee}
.switch[aria-checked="true"]:after{transform:translateX(17px);background:#080808}
.switch:disabled{opacity:.45}
.extension-list{padding:5px 17px}
.extension-row{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:13px 0;border-bottom:1px solid #242424}
.extension-row:last-child{border-bottom:0}
.extension-row code{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;color:#ddd;overflow-wrap:anywhere}
.extension-state{display:flex;align-items:center;gap:7px;color:#aaa;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}
.extension-state:before{content:"";width:5px;height:5px;background:#ccc}
.note-block{padding:15px 18px;border-bottom:1px solid var(--line)}
.note-block:last-child{border-bottom:0}
.note-block strong{font-size:11px;font-weight:550}
.note-block p{margin:5px 0 0;color:#888;font-size:11px;line-height:1.7}
.log-panel{overflow:hidden}
.log-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:15px;padding:17px;border-bottom:1px solid var(--line)}
.log-toolbar h2{margin:5px 0 0;font-size:13px;font-weight:550}
#logText{max-height:66vh;min-height:260px;margin:0;padding:17px;overflow:auto;background:#090909;color:#bebebe;font:10px/1.8 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.table-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;text-align:left}
th,td{padding:13px 16px;border-bottom:1px solid #242424;vertical-align:top}
th{color:#777;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em}
td{font-size:11px;color:#d1d1d1}
td:nth-child(2){color:#888}
td small{display:block;margin-top:4px;color:#777}
.footnote{margin:12px 2px;color:#777;font-size:10px;line-height:1.7}
.page-footer{display:flex;justify-content:space-between;gap:15px;padding-top:20px;margin-top:15px;border-top:1px solid var(--line);color:#555;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em}
.toast-stack{position:fixed;right:17px;bottom:17px;z-index:70;display:grid;gap:8px;width:min(360px,calc(100vw - 34px))}
.toast{padding:12px 14px;border:1px solid #505050;background:#161616;color:#eee;box-shadow:0 8px 28px #0009;font-size:11px;animation:page-in .16s var(--ease) both}
.toast.error{border-color:#777;background:#191919}
.confirm-dialog{width:min(420px,calc(100vw - 28px));padding:0;border:1px solid #4a4a4a;border-radius:0;background:#101010;color:#eee}
.confirm-dialog::backdrop{background:#000b}
.confirm-dialog form{padding:22px}
.confirm-dialog h2{margin:9px 0;font-size:21px;letter-spacing:-.04em}
.confirm-dialog form>p:not(.eyebrow){color:#999;font-size:12px;line-height:1.7}
.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
.login-body{display:grid;place-items:center;padding:32px 18px;background:#080808}
.login-shell{width:min(570px,100%);padding:clamp(20px,5vw,44px);border:1px solid #292929;background:#0b0b0b}
.login-brand{padding:0 0 28px}
.login-art{height:190px;position:relative;overflow:hidden;margin-bottom:29px;border:1px solid #242424;background:#0c0c0c}
.art-grid{position:absolute;inset:0;background-image:radial-gradient(#383838 .7px,transparent .7px);background-size:12px 12px;opacity:.4}
.art-circle{position:absolute;left:50%;top:50%;width:126px;height:126px;border:1px solid #666;border-radius:50%;transform:translate(-50%,-50%)}
.art-circle:before,.art-circle:after{content:"";position:absolute;inset:10px;border:1px dashed #515151;border-radius:50%}
.art-circle:after{inset:-16px;border-style:solid;border-color:#292929}
.art-cross{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:40px;color:#eee;font-weight:200}
.art-code{position:absolute;left:18px;top:18px;color:#636363;font:10px/1.9 ui-monospace,SFMono-Regular,Menlo,monospace}
.art-word{position:absolute;right:17px;bottom:13px;color:#666;font:10px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em}
.login-shell h1{margin-top:13px;font-size:clamp(35px,6vw,53px)}
.login-description{max-width:430px;color:#999;font-size:12px;line-height:1.8}
.login-button{margin:13px 0 10px;min-height:44px;padding:0 17px}
.login-foot{margin:20px 0 0;color:#777;font-size:10px;line-height:1.8}
.login-bottom{display:flex;justify-content:space-between;gap:10px;margin-top:27px;padding-top:14px;border-top:1px solid #252525;color:#5e5e5e;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.06em}
@keyframes page-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@keyframes number-shift{0%{opacity:.45;transform:translateY(3px)}100%{opacity:1;transform:translateY(0)}}
@media(max-width:1180px){.shell{grid-template-columns:222px minmax(0,1fr)}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid{grid-template-columns:minmax(0,1fr)}.panel-large{grid-column:auto}}
@media(max-width:760px){.shell{display:block}.sidebar{position:fixed;left:0;top:0;width:min(290px,84vw);height:100dvh;transform:translateX(-102%);transition:transform .2s var(--ease);box-shadow:14px 0 30px #0006}.sidebar.mobile-open{transform:translateX(0)}.mobile-scrim{position:fixed;inset:0;background:#000a;z-index:19}.mobile-scrim.active{display:block}.topbar{height:auto;min-height:68px;padding:12px 16px;gap:10px}.mobile-menu{display:grid;flex:none}.breadcrumb{display:none}.topbar-right{flex:1;justify-content:flex-end;gap:8px}.guild-control{min-width:90px;max-width:155px}.guild-control select{max-width:155px;min-width:0}.account{max-width:36px;gap:0}.account>span:not(.avatar){display:none}.page{padding:25px 15px 22px}.page-heading{display:block}.heading-actions{justify-content:flex-start;margin-top:17px}.metric-grid{gap:8px}.metric{padding:13px}.metric-label{font-size:8px}.metric-value{font-size:27px}.status-strip{flex-wrap:wrap;gap:8px}.status-strip #runtimeDescription{flex-basis:calc(100% - 40px);order:4}.status-strip time{margin-left:auto}.command-toolbar{align-items:stretch;flex-direction:column}.filter-control,.filter-control select{width:100%}.command-row{grid-template-columns:minmax(0,1fr) 44px;gap:8px;padding:13px}.command-state{grid-column:1;grid-row:2}.command-row .switch{grid-column:2;grid-row:1/3}.activity-row{grid-template-columns:24px minmax(0,1fr);gap:9px}.activity-time{grid-column:2}.runtime-data{grid-template-columns:1fr}.runtime-data div{border-right:0;border-bottom:1px solid var(--line)}.runtime-data div:last-child{border-bottom:0}.page-footer{flex-direction:column}.login-shell{padding:23px 18px}.login-bottom{flex-direction:column}.panel-heading{padding:15px}.activity-list{padding:2px 13px}}
@media(max-width:420px){.topbar{flex-wrap:wrap}.topbar-right{width:100%;justify-content:space-between}.guild-control{flex:1;max-width:none}.guild-control select{width:100%;max-width:none}.account{max-width:31px}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metric-label{letter-spacing:0}.metric-label span{display:none}.distribution-meta{font-size:8px}.runtime-body{gap:12px;padding:17px 13px}.runtime-mark{width:54px;height:54px}.command-summary{flex-direction:column}.dialog-actions .button{flex:1}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}.number-changed{animation:none!important}}
"####;
const DASHBOARD_JS: &str = r####"(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"];
  const state = { user:null, guilds:[], guild:null, commands:[], audit:[], csrf:"", page:"overview", timer:null, confirmAction:null, busy:false, refreshing:false };
  const titles = { overview:"Overview",commands:"Commands",extensions:"Extensions",audit:"Audit history",diagnostics:"Diagnostics",logs:"Runtime logs",integrations:"Integrations",database:"Persistence" };
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  async function api(path, options={}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (["POST","PUT","PATCH","DELETE"].includes(method)) {
      headers["Content-Type"] = "application/json";
      headers["X-CSRF-Token"] = state.csrf;
    }
    let response;
    try { response = await fetch(path,{...options,method,headers,credentials:"same-origin",cache:"no-store"}); }
    catch (_) { throw new Error("The dashboard service could not be reached."); }
    if (response.status === 401) { window.location.assign("/login"); throw new Error("Your session expired. Sign in again."); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ("Request failed (" + response.status + ")."));
    return data;
  }
  function safe(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }
  function fmt(value) { return value == null || value === "" ? "—" : Number(value).toLocaleString(); }
  function timeAgo(value) {
    if (!value) return "Unknown time";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    const s = Math.max(0,Math.floor((Date.now()-date.getTime())/1000));
    if (s < 60) return "Just now";
    if (s < 3600) return Math.floor(s/60)+"m ago";
    if (s < 86400) return Math.floor(s/3600)+"h ago";
    return Math.floor(s/86400)+"d ago";
  }
  function setText(selector, value) {
    const node = $(selector); if (!node) return;
    const next = value == null || value === "" ? "—" : String(value);
    if (node.textContent === next) return;
    const animate = !reducedMotion && /^[-+]?\d[\d,.]*(?:\s?(?:ms|%))?$/.test(next) && node.textContent !== "—";
    node.textContent = next;
    if (animate) { node.classList.remove("number-changed"); void node.offsetWidth; node.classList.add("number-changed"); }
  }
  function toast(message, error=false) {
    const stack=$("#toastStack"); if(!stack)return;
    const item=document.createElement("div"); item.className="toast"+(error?" error":""); item.textContent=message;
    stack.append(item); window.setTimeout(()=>item.remove(),4200);
  }
  function setBusy(busy) {
    state.busy=busy;
    $$(".unicode-spinner").forEach(node=>node.dataset.active=busy?"true":"false");
    if(state.timer){ window.clearInterval(state.timer); state.timer=null; }
    if(busy&&!reducedMotion) {
      let i=0;
      state.timer=window.setInterval(()=>{$$(".unicode-spinner").forEach(node=>{if(node.dataset.active==="true")node.textContent=frames[i%frames.length];});i++;},90);
    }
  }
  function currentGuild(){return state.guilds.find(g=>String(g.id)===String(state.guild));}
  function switchPage(name) {
    if(!titles[name])return;
    closeMobileNav(); state.page=name;
    $$("[data-view]").forEach(node=>node.classList.toggle("hidden",node.dataset.view!==name));
    $$(".nav-item").forEach(node=>node.classList.toggle("active",node.dataset.page===name));
    setText("#breadcrumb",titles[name]);
    if(name==="commands")renderCommands();
    if(name==="audit")loadAudit();
    if(name==="extensions"||name==="diagnostics")loadSystem();
    if(name==="logs")loadLogs();
    if(name==="integrations")loadIntegrations();
    if(name==="database")loadDatabase();
  }
  async function loadBootstrap() {
    setBusy(true);
    try {
      const data=await api("/api/bootstrap");
      state.user=data.user; state.guilds=data.guilds||[]; state.csrf=data.csrf_token||"";
      setText("#userName",state.user.global_name||state.user.username);
      setText("#userAvatar",(state.user.global_name||state.user.username||"?").slice(0,1).toUpperCase());
      setText("#userRole","DISCORD / VERIFIED");
      const picker=$("#guildPicker"); picker.replaceChildren();
      if(!state.guilds.length){picker.add(new Option("No manageable servers",""));picker.disabled=true;throw new Error("No server is available where you have permission and the bot is present.");}
      state.guild=String(data.selected_guild_id||state.guilds[0].id);
      for(const guild of state.guilds)picker.add(new Option(guild.name,String(guild.id)));
      picker.value=state.guild;
      setText("#metricGuilds",fmt(state.guilds.length));
      setText("#connectionLabel","Dashboard session active");
      picker.disabled=false;
      await refreshAll();
    } finally {setBusy(false);}
  }
  async function refreshAll() {
    if(!state.guild||state.refreshing)return;
    state.refreshing=true;
    const guild=currentGuild();
    setText("#guildNameValue",guild?.name);
    setText("#guildIdValue",state.guild);
    setText("#guildPermissionValue",guild?.administrator?"Administrator":(state.user&&state.user.id?"Manage Server":"Unknown"));
    setText("#metricGuilds",fmt(state.guilds.length));
    setBusy(true);
    try {
      const [overviewResult,commandsResult,systemResult] = await Promise.all([
        api("/api/guilds/"+encodeURIComponent(state.guild)+"/overview").then(value=>({value})).catch(error=>({error})),
        api("/api/guilds/"+encodeURIComponent(state.guild)+"/commands").then(value=>({value})).catch(error=>({error})),
        api("/api/system").then(value=>({value})).catch(error=>({error}))
      ]);
      const system=systemResult.value||{status:"unknown",ready:false,reason:"The bot status service could not be reached.",last_known:null};
      if(commandsResult.value) {
        state.commands=commandsResult.value.commands||[];
        renderCommands();
      } else {
        toast(commandsResult.error.message,true);
        $("#commandList").innerHTML='<div class="empty-state">'+safe(commandsResult.error.message)+'</div>';
        setText("#commandResultCount","The live command registry is unavailable.");
        setText("#metricCommands","Unavailable");
        setText("#metricEnabled","Unavailable");
        setText("#metricDisabled","Unavailable");
        setText("#chartEnabledLabel","Command state unavailable");
        setText("#chartDisabledLabel","Command state unavailable");
        setText("#availabilityPercent","—");
        setText("#availabilityTotal","Unavailable");
        $("#enabledBar").style.width="0%";
      }
      if(overviewResult.value) {
        paintOverview(overviewResult.value,system);
      } else {
        paintOverview({bot:system.status==="unknown"?(system.last_known||{}):system},system);
        setText("#metricMembers","Unavailable");
        if(system.status!=="unknown")toast(overviewResult.error.message,true);
      }
      if(!commandsResult.value&&system.status!=="unknown") {
        setText("#metricCommands","Unavailable");
        setText("#metricEnabled","Command state unavailable");
        setText("#metricDisabled","Command state unavailable");
        setText("#chartEnabledLabel","Command state unavailable");
        setText("#chartDisabledLabel","Command state unavailable");
        setText("#availabilityPercent","—");
        setText("#availabilityTotal","Unavailable");
        $("#enabledBar").style.width="0%";
      }
      if(commandsResult.value)renderCommands();
      await loadAudit(true);
      setText("#lastRefresh",new Date().toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}));
      setText("#footerStatus",system.status==="unknown"?"LIVE BOT DATA UNAVAILABLE":"SESSION ACTIVE · DATA REFRESHED");
    } catch(error) {
      toast(error.message,true);
      setText("#runtimePill","STATUS / UNAVAILABLE");
      setText("#runtimeDescription","Live bot data could not be refreshed.");
      setText("#connectionLabel","Status unavailable");
      setText("#footerStatus","LIVE DATA UNAVAILABLE");
    } finally {state.refreshing=false;setBusy(false);}
  }
  function paintOverview(overview,system) {
    const bot=overview.bot||{};
    const total=state.commands.length;
    const enabled=state.commands.filter(c=>c.enabled).length;
    setText("#metricCommands",fmt(total)); setText("#metricEnabled",fmt(enabled)+" enabled"); setText("#metricDisabled",fmt(total-enabled)+" disabled");
    setText("#metricMembers",bot.member_count==null?"Unavailable":fmt(bot.member_count));
    setText("#metricLatency",bot.latency_ms==null?"— ms":Math.round(bot.latency_ms)+" ms");
    setText("#gatewayState",bot.ready?"Gateway connected":"Gateway not ready");
    const gatewayStatus=String(system.status==="unknown"?(bot.status||(bot.ready?"online":"connecting")):system.status).toLowerCase();
    setText("#runtimePill","STATUS / "+gatewayStatus.toUpperCase());
    setText("#runtimeTitle",gatewayStatus==="degraded"?"Gateway connection degraded":gatewayStatus==="offline"?"Discord gateway offline":bot.ready?"Discord gateway connected":"Discord gateway connecting");
    setText("#runtimeDescription",gatewayStatus==="degraded"?"The Discord gateway is connected but latency is elevated.":gatewayStatus==="offline"?"The bot was ready previously but is no longer connected to the Discord gateway.":bot.ready?"The bot process reports a live gateway connection.":"The bot process is reachable and is waiting for a ready gateway.");
    setText("#runtimeCopy","HTTP dashboard availability and Discord gateway health are separate signals.");
    setText("#healthGuilds",fmt(bot.guild_count));
    setText("#runtimeUptime",system.uptime_seconds==null?"Unavailable":duration(system.uptime_seconds));
    setText("#runtimePython",system.python_version||"Unavailable");
    setText("#runtimeExtensions",fmt(bot.extension_count));
    setText("#flagGateway","GATEWAY / "+(bot.ready?"ONLINE":"NOT READY"));
    setText("#flagBridge","BRIDGE / CONNECTED");
    setText("#guildMembership","Connected");
    setText("#commandCount",fmt(total));
    const pct=total?Math.round(enabled/total*100):0;
    $("#enabledBar").style.width=pct+"%";
    setText("#availabilityPercent",pct+"%");
    setText("#chartEnabledLabel","Enabled "+enabled);
    setText("#chartDisabledLabel","Disabled "+(total-enabled));
    if(system.status==="unknown") {
      const cached=system.last_known||null;
      const cachedStatus=cached?String(cached.status|| (cached.ready?"online":"unknown")).toUpperCase():"UNKNOWN";
      setText("#runtimePill","STATUS / UNKNOWN");
      setText("#runtimeTitle",cached?"LAST KNOWN / "+cachedStatus:"LIVE STATUS UNKNOWN");
      setText("#runtimeDescription",system.reason||"The bot bridge is unreachable. Live bot operations are unavailable.");
      setText("#runtimeCopy","Live gateway status is unavailable. Any last-known state is labelled with its observation time.");
      setText("#metricLatency","Unavailable");
      setText("#metricMembers","Unavailable");
      setText("#metricGuilds","Unavailable");
      setText("#metricCommands","Unavailable");
      setText("#metricEnabled","Command state unavailable");
      setText("#metricDisabled","Command state unavailable");
      setText("#availabilityPercent","—");
      setText("#availabilityTotal","Unavailable");
      setText("#chartEnabledLabel","Live command state unavailable");
      setText("#chartDisabledLabel","Live command state unavailable");
      $("#enabledBar").style.width="0%";
      setText("#flagGateway",cached?"LAST KNOWN / "+cachedStatus:"GATEWAY / UNKNOWN");
      setText("#flagBridge","BRIDGE / UNREACHABLE");
      setText("#connectionLabel","Bot status unavailable");
      setText("#connectionTime",cached&&cached.observed_at?"LAST SEEN / "+new Date(cached.observed_at*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"STATUS / UNKNOWN");
    } else {
      setText("#connectionLabel",gatewayStatus==="degraded"?"Gateway degraded":gatewayStatus==="offline"?"Gateway offline":bot.ready?"Discord gateway online":"Bot process connecting");
      setText("#connectionTime",system.observed_at?"OBSERVED / "+new Date(system.observed_at*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"STATUS / LIVE");
    }
    $("#sidebarSignal").classList.toggle("online",Boolean(bot.ready));
    setText("#availabilityTotal",fmt(total));
  }
  function duration(seconds) {
    const value=Math.max(0,Number(seconds)||0);
    const d=Math.floor(value/86400), h=Math.floor(value%86400/3600), m=Math.floor(value%3600/60), s=Math.floor(value%60);
    return (d?d+"d ":"")+(h+"h "+m+"m "+s+"s");
  }
  function renderCommands() {
    const list=$("#commandList"); if(!list)return;
    const query=($("#commandSearch").value||"").trim().toLowerCase();
    const category=$("#commandFilterCategory").value||"All";
    const wantedState=$("#commandFilterState").value||"All";
    const result=state.commands.filter(cmd=>{
      const searchable=[cmd.fullname,cmd.name,cmd.description,cmd.section,cmd.type,cmd.scope].join(" ").toLowerCase();
      const stateOk=wantedState==="All"||(wantedState==="Protected"&&cmd.protected)||(wantedState==="Enabled"&&cmd.enabled&&!cmd.protected)||(wantedState==="Disabled"&&!cmd.enabled&&!cmd.protected);
      return (category==="All"||cmd.section===category)&&stateOk&&searchable.includes(query);
    });
    setText("#commandResultCount",result.length+" of "+state.commands.length+" registered commands");
    if(!result.length){list.innerHTML='<div class="empty-state">No commands match this search and filter.</div>';return;}
    list.innerHTML=result.map(cmd=>'<article class="command-row"><div><div class="command-name"><span class="command-prefix">/</span>'+safe(cmd.fullname||cmd.name)+'</div><p class="command-description">'+safe(cmd.description||"No description provided.")+'</p><div class="command-tags"><span class="tag">'+safe(cmd.section||"Other")+'</span><span class="tag">'+safe(cmd.type||"slash")+'</span><span class="tag">'+safe(cmd.scope||"guild")+'</span>'+(cmd.protected?'<span class="tag">Protected</span>':"")+(cmd.required_permissions?'<span class="tag">Discord default permissions</span>':"")+'</div></div><div class="command-state">'+(cmd.protected?"Protected / always on":(cmd.enabled?"Enabled":"Disabled"))+'</div><button class="switch" type="button" role="switch" aria-checked="'+(cmd.enabled?"true":"false")+'" aria-label="'+safe("Toggle "+cmd.fullname)+'" data-command="'+safe(cmd.fullname)+'" '+(cmd.protected?'disabled title="Protected system command"':"")+'></button></article>').join("");
    $$("[data-command]").forEach(button=>button.addEventListener("click",()=>toggleCommand(button)));
  }
  async function toggleCommand(button) {
    const command=state.commands.find(item=>item.fullname===button.dataset.command);
    if(!command||command.protected||button.disabled)return;
    const desired=!command.enabled;
    button.disabled=true;
    try {
      const result=await api("/api/guilds/"+encodeURIComponent(state.guild)+"/commands/"+encodeURIComponent(command.fullname),{method:"PUT",body:JSON.stringify({enabled:desired})});
      command.enabled=Boolean(result.enabled);
      renderCommands();
      toast("/"+command.fullname+" "+(command.enabled?"enabled":"disabled")+" and synchronized.");
      paintCommandTotals();
      await loadAudit(true);
    } catch(error) {toast(error.message,true);button.disabled=false;}
  }
  function paintCommandTotals() {
    const total=state.commands.length, enabled=state.commands.filter(c=>c.enabled).length;
    setText("#metricCommands",fmt(total));setText("#metricEnabled",fmt(enabled)+" enabled");setText("#metricDisabled",fmt(total-enabled)+" disabled");
    setText("#chartEnabledLabel","Enabled "+enabled);setText("#chartDisabledLabel","Disabled "+(total-enabled));
    setText("#availabilityPercent",(total?Math.round(enabled/total*100):0)+"%");setText("#availabilityTotal",fmt(total));
    $("#enabledBar").style.width=(total?enabled/total*100:0)+"%";
  }
  function renderActivity(entries,target) {
    const node=$(target);if(!node)return;
    if(!entries?.length){node.innerHTML='<p class="empty-state">No audit events have been recorded for this server yet.</p>';return;}
    node.innerHTML=entries.map(entry=>{
      const action=String(entry.action||"Administrative action").replaceAll("_"," ");
      return '<div class="activity-row"><span class="activity-glyph" aria-hidden="true">·</span><div class="activity-copy"><strong>'+safe(action)+'</strong><small>'+safe(entry.details||"No additional details")+' · by '+safe(entry.actor_name||entry.actor_id||"Unknown account")+'</small></div><time class="activity-time" title="'+safe(entry.ts||"")+'">'+safe(timeAgo(entry.ts))+'</time></div>';
    }).join("");
  }
  async function loadAudit(quiet=false) {
    if(!state.guild)return;
    try {const data=await api("/api/guilds/"+encodeURIComponent(state.guild)+"/audit");state.audit=data.entries||[];renderActivity(state.audit.slice(0,5),"#overviewActivity");renderActivity(state.audit,"#auditList");}
    catch(error){if(!quiet){toast(error.message,true);const node=$("#auditList");if(node)node.innerHTML='<p class="empty-state">'+safe(error.message)+'</p>';}}
  }
  async function loadSystem() {
    try {
      const data=await api("/api/system");
      const extensions=data.extensions||[];
      setText("#extensionCount",extensions.length+" REPORTED");
      $("#extensionList").innerHTML=extensions.length?extensions.map(name=>'<div class="extension-row"><code>'+safe(name)+'</code><span class="extension-state">Loaded / live process</span></div>').join(""):'<p class="empty-state">No loaded extensions were reported.</p>';
      const rows=[
        ["Dashboard bridge",data.status==="unknown"?"Unreachable":"Responding"],
        ["Discord gateway",data.ready?"Connected":"Not ready"],
        ["Gateway latency",data.latency_ms==null?"Unavailable":Math.round(data.latency_ms)+" ms"],
        ["Connected bot guilds",data.guild_count==null?"Unavailable":fmt(data.guild_count)],
        ["Loaded extensions",fmt(data.extension_count)],
        ["Python runtime",data.python_version||"Unavailable"],
        ["Process uptime",data.uptime_seconds==null?"Unavailable":duration(data.uptime_seconds)],
        ["Observation time",data.observed_at?new Date(data.observed_at*1000).toLocaleString():"Unavailable"],
      ];
      if(data.last_known){rows.push(["Last-known status",String(data.last_known.status||"Unknown")]);rows.push(["Last-known observation",data.last_known.observed_at?new Date(data.last_known.observed_at*1000).toLocaleString():"Unknown"]); }
      $("#diagnosticValues").innerHTML=rows.map(([key,value])=>'<div><dt>'+safe(key)+'</dt><dd>'+safe(value)+'</dd></div>').join("");
      setText("#runtimeUptime",data.uptime_seconds==null?"Unavailable":duration(data.uptime_seconds));
      setText("#runtimePython",data.python_version||"Unavailable");
      setText("#runtimeExtensions",fmt(data.extension_count));
    } catch(error) {toast(error.message,true);}
  }
  async function loadDatabase() {
    if(!state.guild)return;
    try {
      const data=await api("/api/guilds/"+encodeURIComponent(state.guild)+"/database");
      const rows=data.resources||[];
      $("#databaseRows").innerHTML=rows.length?rows.map(row=>'<tr><td>'+safe(row.name)+'</td><td>'+safe(row.purpose)+'<small>'+safe(row.detail||"")+'</small></td><td>'+safe(row.state)+'</td></tr>').join(""):'<tr><td colspan="3">No persistence resources reported.</td></tr>';
    } catch(error) {$("#databaseRows").innerHTML='<tr><td colspan="3">'+safe(error.message)+'</td></tr>';}
  }
  async function loadLogs() {
    try {const file=$("#logPicker").value;const data=await api("/api/logs?file="+encodeURIComponent(file));setText("#logFilename",data.name||file);$("#logText").textContent=data.content||"No log entries found.";}
    catch(error){$("#logText").textContent=error.message;}
  }
  async function loadIntegrations() {
    try {
      const data=await api("/api/integrations"), rows=data.integrations||[];
      $("#integrationList").innerHTML=rows.length?rows.map(item=>'<div class="extension-row"><div><code>'+safe(item.name)+'</code><p class="command-description">'+safe(item.detail||"")+'</p></div><span class="extension-state">'+(item.configured?"Configured":"Not configured")+'</span></div>').join(""):'<p class="empty-state">No integrations reported.</p>';
    } catch(error){$("#integrationList").innerHTML='<p class="empty-state">'+safe(error.message)+'</p>';}
  }
  async function syncCommands() {
    if(state.busy||!state.guild)return;
    const dialog=$("#confirmDialog");
    $("#confirmTitle").textContent="Publish slash commands";
    $("#confirmMessage").textContent="Synchronize the registered dashboard-managed commands for "+(currentGuild()?.name||"this server")+" with Discord. This does not unregister unrelated commands.";
    const confirmed=await askConfirm();
    if(!confirmed)return;
    setBusy(true);
    try {const data=await api("/api/guilds/"+encodeURIComponent(state.guild)+"/sync",{method:"POST",body:"{}"});toast("Discord synchronization completed for "+(data.synced??"the")+" enabled commands.");await refreshAll();}
    catch(error){toast(error.message,true);}
    finally{setBusy(false);}
  }
  function askConfirm() {
    return new Promise(resolve=>{
      const dialog=$("#confirmDialog"),accept=$("#confirmAccept");
      const onClose=()=>resolve(dialog.returnValue==="confirm");
      dialog.addEventListener("close",onClose,{once:true});
      accept.onclick=()=>{dialog.close("confirm");};
      dialog.showModal();
    });
  }
  async function resetCommands() {
    $("#confirmTitle").textContent="Reset server command overrides";
    $("#confirmMessage").textContent="Reset the saved command configuration for "+(currentGuild()?.name||"this server")+" and synchronize the resulting defaults? This cannot be undone from the dashboard.";
    if(!await askConfirm())return;
    setBusy(true);
    try {await api("/api/guilds/"+encodeURIComponent(state.guild)+"/reset",{method:"POST",body:"{}"});await refreshAll();toast("Server command overrides reset and synchronized.");}
    catch(error){toast(error.message,true);}
    finally{setBusy(false);}
  }
  function closeMobileNav() {$("#sidebar").classList.remove("mobile-open");$("#mobileScrim").classList.remove("active");$("#mobileMenuButton").setAttribute("aria-expanded","false");}
  function bind() {
    $("#mobileMenuButton").addEventListener("click",()=>{const opened=$("#sidebar").classList.toggle("mobile-open");$("#mobileScrim").classList.toggle("active",opened);$("#mobileMenuButton").setAttribute("aria-expanded",String(opened));});
    $("#mobileScrim").addEventListener("click",closeMobileNav);
    $("#mainNav").addEventListener("click",event=>{const button=event.target.closest("[data-page]");if(button)switchPage(button.dataset.page);});
    $$("[data-jump]").forEach(button=>button.addEventListener("click",()=>switchPage(button.dataset.jump)));
    $("#guildPicker").addEventListener("change",async event=>{state.guild=event.target.value;await refreshAll();toast("Switched server context.");});
    $("#refreshButton").addEventListener("click",async()=>{await refreshAll();toast("Dashboard refresh completed.");});
    $("#syncButton").addEventListener("click",syncCommands);$("#syncButtonCommands").addEventListener("click",syncCommands);
    $("#resetButton").addEventListener("click",resetCommands);
    $("#openAudit").addEventListener("click",()=>switchPage("audit"));
    $("#refreshAudit").addEventListener("click",loadAudit);
    $("#refreshSystem").addEventListener("click",loadSystem);$("#refreshDiagnostics").addEventListener("click",loadSystem);
    $("#refreshLogs").addEventListener("click",loadLogs);$("#logPicker").addEventListener("change",loadLogs);
    $("#refreshIntegrations").addEventListener("click",loadIntegrations);$("#refreshDatabase").addEventListener("click",loadDatabase);
    $("#commandSearch").addEventListener("input",renderCommands);$("#commandFilterCategory").addEventListener("change",renderCommands);$("#commandFilterState").addEventListener("change",renderCommands);
    $("#logoutButton").addEventListener("click",async()=>{try{await api("/api/logout",{method:"POST",body:"{}"});window.location.assign("/login");}catch(error){toast(error.message,true);}});
    document.addEventListener("visibilitychange",()=>{if(!document.hidden&&state.guild)refreshAll();});
  }
  async function start() {
    bind();
    try {
      await loadBootstrap();
      const categories=[...new Set(state.commands.map(item=>item.section||"Other"))].sort((a,b)=>a.localeCompare(b));
      const filter=$("#commandFilterCategory");for(const category of categories)filter.add(new Option(category,category));
      window.setInterval(()=>{if(!document.hidden&&state.guild)refreshAll();},45000);
    } catch(error) {
      toast(error.message,true);setText("#connectionLabel","Connection issue");setText("#connectionTime","STATUS / UNKNOWN");
      setText("#footerStatus","DASHBOARD DATA UNAVAILABLE");
    } finally {setBusy(false);}
  }
  document.addEventListener("DOMContentLoaded",start);
})();
"####;

pub fn dashboard_html() -> Html<&'static str> {
    Html(DASHBOARD_HTML)
}

pub fn login_html() -> Html<&'static str> {
    Html(LOGIN_HTML)
}

pub async fn static_asset(Path(filename): Path<String>) -> Response {
    let (content_type, contents) = match filename.as_str() {
        "dashboard.css" => ("text/css; charset=utf-8", DASHBOARD_CSS),
        "dashboard.js" => ("application/javascript; charset=utf-8", DASHBOARD_JS),
        _ => return (StatusCode::NOT_FOUND, "Asset not found").into_response(),
    };
    Response::builder()
        .header(header::CONTENT_TYPE, content_type)
        .body(Body::from(contents))
        .unwrap_or_else(|_| (StatusCode::INTERNAL_SERVER_ERROR, "Could not serve asset").into_response())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn browser_assets_are_compiled_into_the_rust_application() {
        assert!(DASHBOARD_HTML.contains("data-view=\"overview\""));
        assert!(DASHBOARD_HTML.contains("/static/dashboard.css"));
        assert!(DASHBOARD_HTML.contains("/static/dashboard.js"));
        assert!(LOGIN_HTML.contains("/oauth/start"));
        assert!(DASHBOARD_CSS.contains("@media(max-width:760px)"));
        assert!(DASHBOARD_CSS.contains("prefers-reduced-motion:reduce"));
        assert!(DASHBOARD_JS.contains("X-CSRF-Token"));
        assert!(DASHBOARD_JS.contains("state.refreshing=false"));
    }
}

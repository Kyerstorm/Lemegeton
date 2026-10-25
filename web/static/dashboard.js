(() => {
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

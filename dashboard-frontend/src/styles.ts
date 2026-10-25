export const DASHBOARD_CSS = String.raw`
:root{color-scheme:dark;--bg:#090a09;--surface:#101210;--surface-2:#151815;--surface-3:#1b1f1b;--line:#282d28;--line-soft:#202420;--text:#eff1ed;--muted:#8c948a;--soft:#b8beb5;--accent:#d9ff72;--accent-dim:#9bb74f;--danger:#ff8585;--font:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--mono:"SFMono-Regular",Consolas,"Liberation Mono",monospace;--radius:15px;font-synthesis:none;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
*{box-sizing:border-box}
html{min-width:320px;background:var(--bg);scroll-behavior:smooth}
body{margin:0;min-width:320px;min-height:100vh;background:radial-gradient(ellipse at 70% -15%,#1b2117 0%,transparent 43%),var(--bg);color:var(--text);font-family:var(--font);font-size:14px;line-height:1.5}
button,input,select{font:inherit}
button,a,select,input{outline-offset:3px}
button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent)}
button{color:inherit}
a{color:inherit;text-decoration:none}
button:disabled{opacity:.45;cursor:not-allowed!important}
.app-shell{min-height:100vh}
.sidebar{position:fixed;inset:0 auto 0 0;width:248px;display:flex;flex-direction:column;padding:27px 17px 17px;background:rgba(12,14,12,.94);border-right:1px solid var(--line-soft);z-index:30;backdrop-filter:blur(18px)}
.brand{display:flex;align-items:center;gap:12px;padding:0 9px 24px}
.brand-mark{display:grid;place-items:center;width:41px;height:41px;border:1px solid #4c5940;border-radius:12px;background:linear-gradient(145deg,#222b1b,#11140f);color:var(--accent);font-size:20px;font-weight:750;letter-spacing:-2px}
.brand-copy{display:flex;flex-direction:column;gap:3px}
.brand-copy strong{font-size:12px;letter-spacing:.19em;font-weight:750}
.brand-copy small{font:9px var(--mono);letter-spacing:.16em;color:var(--muted)}
.sidebar-rule{height:1px;background:var(--line);margin:0 9px 23px}
.nav-label{margin:0 12px 11px;color:#6e766b;font:10px var(--mono);letter-spacing:.1em}.nav-label span{color:#474e44}
.main-nav{display:grid;gap:4px}
.nav-item{display:flex;align-items:center;gap:12px;width:100%;border:1px solid transparent;border-radius:10px;background:transparent;color:#939b91;text-align:left;padding:11px 12px;cursor:pointer;transition:background .18s,border-color .18s,color .18s}
.nav-item:hover{background:#171b16;color:var(--text)}
.nav-item.active{background:#1a2017;border-color:#2c3525;color:var(--text)}
.nav-item.active .nav-glyph{color:var(--accent)}
.nav-glyph{width:18px;color:#687064;text-align:center;font-size:17px}
.nav-count{margin-left:auto;color:var(--accent);font:10px var(--mono)}
.sidebar-spacer{flex:1;min-height:30px}
.sidebar-system{display:flex;align-items:center;gap:11px;padding:13px 11px;border:1px solid var(--line);border-radius:11px;background:#101310;margin-bottom:12px;min-width:0}
.signal-dot{width:7px;height:7px;border-radius:50%;background:#737a70;box-shadow:0 0 0 4px #292d26;flex:none}
.signal-dot.online{background:var(--accent);box-shadow:0 0 0 4px #293222,0 0 14px #b7e75c55}
.sidebar-system div{display:flex;flex-direction:column;gap:3px;min-width:0}
.sidebar-system strong{font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sidebar-system small{color:var(--muted);font:9px var(--mono);letter-spacing:.06em}
.signout{display:flex;justify-content:space-between;align-items:center;width:100%;padding:10px 12px;border:0;background:transparent;color:#899187;cursor:pointer;border-radius:9px;text-align:left}
.signout:hover{background:#191c18;color:var(--text)}
.main{margin-left:248px;min-width:0;padding:0 36px 22px}
.topbar{height:86px;display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line-soft)}
.breadcrumb{display:flex;align-items:center;gap:11px;min-width:0}
.breadcrumb>span:first-child{font:10px var(--mono);letter-spacing:.14em;color:#70786d}
.breadcrumb-divider{color:#4a5047}
.breadcrumb strong{font-size:12px;font-weight:600;color:#d8ddd4}
.topbar-right{display:flex;align-items:center;gap:14px}
.guild-control{display:flex;align-items:center;gap:9px;padding:8px 11px;border:1px solid var(--line);border-radius:10px;background:#111411}
.guild-control>span,.filter-control>span{color:#858d81;font:9px var(--mono);letter-spacing:.1em;white-space:nowrap}
select{max-width:240px;color:var(--text);background-color:transparent;border:0;min-width:0;cursor:pointer}
select option{background:#171a16;color:var(--text)}
.icon-button{display:grid;place-items:center;width:37px;height:37px;border:1px solid var(--line);border-radius:10px;background:#111411;color:#9ba397;font-size:20px;cursor:pointer;transition:background .2s,color .2s,border-color .2s}
.icon-button:hover{color:var(--accent);border-color:#49553a;background:#171c14}
.icon-button.spinning{animation:rotate .8s linear infinite}
.account{display:flex;align-items:center;gap:9px;padding-left:5px}
.avatar{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#273020;border:1px solid #3d4932;color:var(--accent);font-size:13px;font-weight:700}
.account-copy{display:flex;flex-direction:column;gap:2px;max-width:140px}
.account-copy strong{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.account-copy small{font:9px var(--mono);letter-spacing:.06em;color:var(--muted)}
.mobile-menu,.mobile-scrim{display:none}
.page{padding:34px 0 0;max-width:1600px;margin:0 auto;animation:fade-in .25s ease both}
.page-heading{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:25px}
.page-heading-copy{min-width:0}
.eyebrow{margin:0 0 10px;color:#8b9483;font:10px var(--mono);letter-spacing:.13em;text-transform:uppercase}
.page-heading h1{margin:0;font-size:clamp(29px,3vw,42px);line-height:1.12;letter-spacing:-.055em;font-weight:650}
.page-heading h1 span{color:#7f8976;font-weight:450}
.lede{margin:12px 0 0;color:#929a8e;max-width:660px;font-size:13px;line-height:1.75}
.heading-actions{display:flex;gap:9px;align-items:center;flex:none}
.button{display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:39px;padding:0 14px;border:1px solid var(--line);border-radius:9px;background:#151815;color:#c0c7bb;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;transition:transform .16s,background .16s,border-color .16s,color .16s}
.button:hover:not(:disabled){background:#20251e;border-color:#40483a;color:var(--text);transform:translateY(-1px)}
.button.primary{background:var(--accent);border-color:var(--accent);color:#161b11}
.button.primary:hover:not(:disabled){background:#e5ffa4;border-color:#e5ffa4;color:#11160e}
.button.quiet{background:transparent;border-color:transparent}
.button.quiet:hover:not(:disabled){background:#1b1e1a}
.status-strip{display:flex;align-items:center;gap:10px;min-height:44px;padding:8px 13px;border:1px solid #30372a;border-radius:10px;background:linear-gradient(90deg,#171d13,#111410);color:#9ea796;font-size:11px;margin:0 0 17px}
.status-strip>span:nth-child(2){font:10px var(--mono);letter-spacing:.04em;color:#c6d2b7;white-space:nowrap}
.strip-signal{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px #d9ff7266;flex:none}
.strip-separator{color:#50584a}
.status-strip time{margin-left:auto;white-space:nowrap;color:#697264;font:9px var(--mono)}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:14px}
.metric{border:1px solid var(--line);border-radius:var(--radius);padding:17px 17px 15px;background:linear-gradient(145deg,#131613,#0f110f);min-width:0;min-height:142px}
.metric-label{display:flex;justify-content:space-between;gap:10px;color:#8f978b;font:9px var(--mono);letter-spacing:.05em}
.metric-label span{color:#4e5748}
.metric-value{display:block;margin:17px 0 10px;font-size:32px;line-height:1;font-weight:600;letter-spacing:-.055em;color:#ecf0e8}
.metric-value small{font:12px var(--mono);letter-spacing:0;color:#8d9589;margin-left:6px}
.metric p{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin:0;color:#788174;font-size:10px}
.metric-dot{color:#495044}
.content-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px}
.panel{min-width:0;border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(145deg,#131613,#101210);padding:20px}
.panel-large{grid-row:span 1}
.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:20px;min-width:0}
.panel-heading .eyebrow{margin-bottom:6px}
.panel-heading h2{margin:0;font-size:15px;letter-spacing:-.025em;font-weight:600}
.panel-index{color:#67705f;font:9px var(--mono);letter-spacing:.06em;white-space:nowrap}
.runtime-body{display:flex;align-items:center;gap:17px;padding:8px 0 23px}
.runtime-mark{position:relative;display:grid;place-items:center;flex:none;width:62px;height:62px;border:1px solid #30372c;border-radius:17px;background:radial-gradient(circle at 40% 30%,#242c1e,#121510);color:#95a187;font-size:28px}
.runtime-mark span{animation:orbit 8s linear infinite}
.runtime-mark i{position:absolute;width:7px;height:7px;border-radius:50%;right:9px;top:9px;background:#7a8174}
.runtime-mark.is-online i{background:var(--accent);box-shadow:0 0 12px #d9ff72aa}
.runtime-copy{min-width:0}
.runtime-state{margin:0 0 5px;font-size:13px;font-weight:650}
.muted{margin:0;color:#899184;font-size:11px;line-height:1.65}
.runtime-flags{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.status-pill{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#151815;color:#9ba294;font:9px var(--mono);letter-spacing:.015em}
.status-pill i{width:5px;height:5px;border-radius:50%;background:#757d70;flex:none}
.status-pill.is-good{border-color:#35412d;background:#1a2115;color:#c6e79a}.status-pill.is-good i{background:var(--accent)}
.status-pill.is-bad{border-color:#4c302f;background:#241817;color:#ffaaaa}.status-pill.is-bad i{background:var(--danger)}
.status-pill.is-neutral i{background:#788071}
.runtime-data{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;border-top:1px solid var(--line);padding-top:17px}
.runtime-data>div{min-width:0;display:flex;flex-direction:column;gap:7px}
.runtime-data small{color:#75806f;font:9px var(--mono);letter-spacing:.04em}
.runtime-data strong{font-size:12px;font-weight:600;overflow-wrap:anywhere}
.footnote{color:#747d70;font-size:11px;line-height:1.7;margin:17px 0 0}
.footnote.compact{margin-top:12px}
.text-button{border:0;background:transparent;padding:0;color:var(--accent-dim);font-size:10px;cursor:pointer;white-space:nowrap}
.text-button:hover{color:var(--accent)}
.distribution-label{display:flex;align-items:baseline;gap:9px;margin-top:6px}
.distribution-label strong{font-size:29px;font-weight:600;letter-spacing:-.045em}
.distribution-label span{font-size:11px;color:#879080}
.distribution-track{display:block;width:100%;height:6px;margin:17px 0 11px;border-radius:99px;overflow:hidden}
.distribution-track-bg{fill:#282d25}
.distribution-track-fill{fill:var(--accent);transition:width .3s ease}
.distribution-meta{display:flex;justify-content:space-between;gap:10px;color:#798272;font-size:10px}
.definition-list{margin:0}
.definition-list>div{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--line-soft)}
.definition-list>div:last-child{border-bottom:0;padding-bottom:0}
.definition-list dt{color:#818a7d;font-size:11px}
.definition-list dd{margin:0;max-width:63%;text-align:right;font-size:11px;color:#d0d6ca;overflow-wrap:anywhere}
.mono{font-family:var(--mono);font-size:10px!important;color:#8f9b84!important}
.activity-list{display:flex;flex-direction:column}
.activity-row{display:grid;grid-template-columns:15px minmax(0,1fr) auto;gap:9px;align-items:start;padding:13px 0;border-bottom:1px solid var(--line-soft)}
.activity-row:first-child{padding-top:0}
.activity-row:last-child{border-bottom:0;padding-bottom:0}
.activity-glyph{display:grid;place-items:center;width:15px;height:22px;color:var(--accent);font-size:22px;line-height:1}
.activity-copy{min-width:0;display:flex;flex-direction:column;gap:4px}
.activity-copy strong{font-weight:600;font-size:11px;text-transform:capitalize;overflow-wrap:anywhere}
.activity-copy small{color:#7f887b;font-size:10px;line-height:1.6;overflow-wrap:anywhere}
.activity-time{color:#737b6e;font:9px var(--mono);white-space:nowrap;padding-top:3px}
.empty-state{padding:22px 12px;border:1px dashed #2b3028;border-radius:10px;color:#7d8678;font-size:11px;text-align:center;line-height:1.7}
.loading-state{display:flex;align-items:center;justify-content:center;gap:10px}
.spinner{display:inline-block;width:14px;height:14px;border:1px solid #536044;border-top-color:var(--accent);border-radius:50%;animation:rotate .8s linear infinite}
.command-toolbar{display:grid;grid-template-columns:minmax(200px,1fr) minmax(160px,220px) minmax(130px,170px);gap:10px;margin-bottom:14px}
.search-field,.filter-control{display:flex;align-items:center;gap:9px;min-width:0;border:1px solid var(--line);border-radius:9px;background:#111411;padding:0 12px}
.search-field>span{font-size:20px;color:#7c8675}
.search-field input{width:100%;min-width:0;height:41px;background:transparent;border:0;color:var(--text);outline:none;font-size:11px}
.search-field input::placeholder{color:#656e60}
.filter-control{justify-content:space-between;padding:0 11px}
.filter-control select{width:100%;height:40px;font-size:11px;text-align:right}
.filter-control>span{flex:none}
.command-summary{display:flex;justify-content:space-between;gap:12px;margin:0 2px 10px;color:#7f887b;font-size:10px}
.command-summary span:last-child{font:9px var(--mono);letter-spacing:.07em;color:#6b7565}
.command-list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;background:#101210}
.command-row{display:grid;grid-template-columns:minmax(0,1fr) auto 43px;gap:20px;align-items:center;padding:17px 18px;border-bottom:1px solid var(--line-soft)}
.command-row:last-child{border-bottom:0}
.command-row:hover{background:#141714}
.command-main{min-width:0}
.command-name{font:12px var(--mono);font-weight:600;overflow-wrap:anywhere;color:#e6ebdf}
.command-prefix{color:var(--accent);margin-right:5px}
.command-description{margin:7px 0 0;color:#858e80;font-size:11px;line-height:1.65;overflow-wrap:anywhere}
.command-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.tag{padding:3px 6px;border:1px solid #2a3027;border-radius:5px;background:#171a16;color:#8b9584;font:9px var(--mono)}
.tag-protected{border-color:#4a4a2d;color:#d6d88f;background:#202016}
.command-state{justify-self:end}
.switch{position:relative;width:38px;height:22px;padding:0;border:1px solid #42483e;border-radius:99px;background:#262a24;cursor:pointer;transition:background .2s,border-color .2s}
.switch span{position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#858d7f;transition:transform .2s,background .2s}
.switch.checked{background:#374724;border-color:#596c3d}
.switch.checked span{transform:translateX(16px);background:var(--accent)}
.extension-list{display:flex;flex-direction:column}
.extension-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:15px 0;border-bottom:1px solid var(--line-soft)}
.extension-row:first-child{padding-top:0}
.extension-row:last-child{border:0;padding-bottom:0}
.extension-row code{color:#d9dfd2;font:11px var(--mono);overflow-wrap:anywhere}
.extension-row .command-description{margin-top:4px}
.diagnostic-list>div{align-items:center}
.note-block{padding:15px 0;border-bottom:1px solid var(--line-soft)}
.note-block:first-of-type{padding-top:0}
.note-block:last-child{padding-bottom:0;border-bottom:0}
.note-block strong{font-size:12px}
.note-block p{margin:7px 0 0;color:#838c7e;font-size:11px;line-height:1.8}
.log-panel .panel-heading{align-items:center}
.log-output{min-height:320px;max-height:560px;overflow:auto;margin:0;padding:16px;border:1px solid #242a22;border-radius:9px;background:#080908;color:#a9b29f;font:11px/1.75 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;tab-size:2}
.table-scroll{width:100%;overflow-x:auto}
table{width:100%;border-collapse:collapse;text-align:left;min-width:500px}
th{padding:0 12px 13px;color:#77816e;font:9px var(--mono);letter-spacing:.07em}
td{padding:14px 12px;border-top:1px solid var(--line-soft);font-size:11px;color:#c0c8b9;vertical-align:top}
td small{display:block;margin-top:5px;color:#7e8878;font-size:10px;line-height:1.6}
.page-footer{display:flex;justify-content:space-between;gap:16px;padding:29px 0 7px;color:#596153;font:9px var(--mono);letter-spacing:.06em}
.toast-stack{position:fixed;right:20px;bottom:20px;z-index:80;display:flex;flex-direction:column;gap:8px;width:min(390px,calc(100vw - 32px))}
.toast{display:flex;align-items:flex-start;gap:10px;padding:12px 12px;border:1px solid #3a4430;border-radius:10px;background:#171d14;box-shadow:0 12px 36px #0008;color:#d5e3c8;font-size:11px;line-height:1.6;animation:toast-in .2s ease both}
.toast>span{display:grid;place-items:center;width:18px;height:18px;border-radius:50%;flex:none;background:#34442a;color:var(--accent);font-weight:700}
.toast button{margin-left:auto;padding:0 3px;background:transparent;border:0;color:#9ca593;font-size:17px;cursor:pointer}
.toast.error{border-color:#543b39;background:#241817;color:#f1ceca}
.toast.error>span{background:#472725;color:var(--danger)}
.modal-scrim{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:20px;background:#030403cc;backdrop-filter:blur(8px)}
.confirm-dialog{width:min(470px,100%);padding:25px;border:1px solid #3a4135;border-radius:16px;background:#111410;box-shadow:0 24px 80px #000b;animation:fade-in .16s ease both}
.confirm-dialog h2{margin:0;font-size:22px;letter-spacing:-.04em}
.confirm-dialog>p:not(.eyebrow){margin:12px 0 22px;color:#8f9888;font-size:12px;line-height:1.8}
.dialog-actions{display:flex;justify-content:flex-end;gap:8px}
.boot-screen{display:flex;min-height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:16px;color:#899282}
.boot-mark{display:grid;place-items:center;width:55px;height:55px;border:1px solid #3f4934;border-radius:15px;color:var(--accent);font-size:24px;font-weight:700}
.boot-screen p{margin:4px 0 0;font-size:12px}
.boot-screen small{font:9px var(--mono);letter-spacing:.1em;color:#5e6758}
.login-wrap{position:relative;isolation:isolate;display:grid;place-items:center;min-height:100vh;padding:36px 18px;overflow:hidden}
.login-orbit{position:absolute;border:1px solid #293323;border-radius:50%;z-index:-1;pointer-events:none}
.orbit-one{width:min(900px,115vw);aspect-ratio:1;transform:translate(28%,6%);box-shadow:inset 0 0 120px #192016}
.orbit-two{width:min(600px,85vw);aspect-ratio:1;transform:translate(28%,6%);border-style:dashed;opacity:.65}
.login-card{width:min(510px,100%);padding:34px;border:1px solid #2c3328;border-radius:21px;background:linear-gradient(145deg,#141713f5,#0c0e0bf5);box-shadow:0 28px 90px #0009}
.login-brand{padding:0 0 31px;border-bottom:1px solid var(--line)}
.login-kicker{display:flex;align-items:center;gap:10px;margin:29px 0 14px;color:#8f9a83;font:9px var(--mono);letter-spacing:.12em}
.login-kicker .signal-dot{width:6px;height:6px}
.login-card h1{margin:0;font-size:clamp(37px,9vw,52px);line-height:1.03;letter-spacing:-.065em;font-weight:650}
.login-card h1 span{color:#7f8b74;font-weight:450}
.login-copy{margin:18px 0 25px;max-width:400px;color:#9aa393;font-size:13px;line-height:1.85}
.login-button{width:100%;min-height:48px;font-size:12px}
.inline-notice{padding:10px 12px;margin:0 0 16px;border:1px solid #464531;border-radius:8px;background:#202015;color:#d7d7a6;font-size:11px}
.login-separator{display:flex;align-items:center;gap:10px;margin:24px 0 17px;color:#68715f;font:8px var(--mono);letter-spacing:.09em;white-space:nowrap}
.login-separator span{height:1px;background:var(--line);flex:1}
.login-assurances{display:grid;gap:11px}
.login-assurances>span{display:flex;align-items:center;gap:10px;color:#8a9383;font-size:10px}
.login-assurances b{display:grid;place-items:center;width:23px;height:23px;border:1px solid #30392a;border-radius:7px;color:var(--accent);font:9px var(--mono)}
.login-foot{display:flex;justify-content:space-between;gap:10px;margin-top:28px;padding-top:17px;border-top:1px solid var(--line);font:8px var(--mono);letter-spacing:.06em;color:#636c5d}
@keyframes fade-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
@keyframes toast-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
@keyframes rotate{to{transform:rotate(360deg)}}
@keyframes orbit{to{transform:rotate(360deg)}}
@media(max-width:1250px){.main{padding:0 25px 22px}.sidebar{width:225px}.main{margin-left:225px}.metric{padding:15px}.metric-value{font-size:28px}.account-copy{max-width:105px}.topbar-right{gap:9px}}
@media(max-width:960px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid{grid-template-columns:minmax(0,1fr)}.panel-large{grid-row:auto}.page-heading{align-items:flex-start;flex-direction:column}.heading-actions{width:100%;flex-wrap:wrap}.topbar{height:75px}.account-copy{display:none}}
@media(max-width:760px){.sidebar{width:min(290px,84vw);transform:translateX(-105%);transition:transform .24s ease;box-shadow:none}.sidebar.mobile-open{transform:translateX(0);box-shadow:20px 0 80px #0009}.mobile-scrim{position:fixed;inset:0;z-index:25;display:block;width:100%;height:100%;border:0;background:#0009;opacity:0;pointer-events:none;transition:opacity .2s}.mobile-scrim.active{opacity:1;pointer-events:auto}.main{margin-left:0;padding:0 18px 20px}.mobile-menu{display:grid}.topbar{gap:12px}.breadcrumb{margin-right:auto}.topbar-right{gap:7px}.guild-control{padding:7px 8px;max-width:190px}.guild-control>span{display:none}.guild-control select{max-width:150px}.page{padding-top:25px}.page-heading h1{font-size:34px}.lede{font-size:12px}.status-strip{align-items:flex-start;flex-wrap:wrap}.status-strip time{width:100%;margin-left:16px}.command-toolbar{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}.command-row{grid-template-columns:minmax(0,1fr) 40px;gap:10px;padding:15px}.command-state{grid-column:1;grid-row:2;justify-self:start}.switch{grid-column:2;grid-row:1;justify-self:end}.command-tags{gap:5px}.metric{min-height:132px}.page-footer{font-size:8px}.account{display:none}}
@media(max-width:480px){.main{padding-right:13px;padding-left:13px}.topbar{height:69px}.breadcrumb>span:first-child,.breadcrumb-divider{display:none}.breadcrumb strong{font-size:11px}.icon-button{width:33px;height:33px}.guild-control{max-width:150px}.guild-control select{max-width:125px;font-size:10px}.metric-grid{gap:8px}.metric{padding:13px 12px;min-height:128px}.metric-label{font-size:8px}.metric-value{font-size:26px;margin-top:16px}.metric p{font-size:9px}.page-heading h1{font-size:31px}.heading-actions .button{flex:1;padding:0 9px}.status-strip{font-size:10px}.panel{padding:15px}.runtime-body{align-items:flex-start;gap:12px}.runtime-mark{width:48px;height:48px;border-radius:13px;font-size:23px}.runtime-data{grid-template-columns:1fr;gap:13px}.runtime-data>div{flex-direction:row;align-items:baseline;justify-content:space-between}.activity-row{grid-template-columns:12px minmax(0,1fr);gap:7px}.activity-time{grid-column:2;padding:0}.command-toolbar{grid-template-columns:1fr}.search-field{grid-column:auto}.filter-control{min-height:40px}.command-summary{align-items:flex-start;flex-direction:column;gap:5px}.command-row{padding:14px 12px}.extension-row{align-items:flex-start;flex-direction:column;gap:8px}.login-card{padding:24px 20px}.login-foot{font-size:7px}.confirm-dialog{padding:20px}.dialog-actions .button{flex:1}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
`;

export const DASHBOARD_CSS = String.raw`
:root{color-scheme:dark;--bg:#000;--surface:#090909;--surface-2:#111;--surface-3:#191919;--line:#2a2a2a;--line-soft:#1c1c1c;--text:#f5f5f5;--muted:#929292;--soft:#c9c9c9;--accent:#fff;--accent-dim:#bdbdbd;--danger:#bdbdbd;--font:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--mono:"SFMono-Regular",Consolas,"Liberation Mono",monospace;--radius:15px;font-synthesis:none;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
*{box-sizing:border-box}
html{min-width:320px;background:var(--bg);scroll-behavior:smooth}
body{margin:0;min-width:320px;min-height:100vh;background:radial-gradient(ellipse at 70% -15%,#1f1f1f 0%,transparent 43%),var(--bg);color:var(--text);font-family:var(--font);font-size:14px;line-height:1.5}
button,input,select{font:inherit}
button,a,select,input{outline-offset:3px}
button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--accent)}
button{color:inherit}
a{color:inherit;text-decoration:none}
button:disabled{opacity:.45;cursor:not-allowed!important}
.app-shell{min-height:100vh}
.sidebar{position:fixed;inset:0 auto 0 0;width:248px;display:flex;flex-direction:column;padding:27px 17px 17px;background:rgba(12,14,12,.94);border-right:1px solid var(--line-soft);z-index:30;backdrop-filter:blur(18px)}
.brand{display:flex;align-items:center;gap:12px;padding:0 9px 24px}
.brand-mark{display:grid;place-items:center;width:41px;height:41px;border:1px solid #545454;border-radius:12px;background:linear-gradient(145deg,#282828,#131313);color:var(--accent);font-size:20px;font-weight:750;letter-spacing:-2px}
.brand-copy{display:flex;flex-direction:column;gap:3px}
.brand-copy strong{font-size:12px;letter-spacing:.19em;font-weight:750}
.brand-copy small{font:9px var(--mono);letter-spacing:.16em;color:var(--muted)}
.sidebar-rule{height:1px;background:var(--line);margin:0 9px 23px}
.nav-label{margin:0 12px 11px;color:#747474;font:10px var(--mono);letter-spacing:.1em}.nav-label span{color:#4c4c4c}
.main-nav{display:grid;gap:4px}
.nav-item{display:flex;align-items:center;gap:12px;width:100%;border:1px solid transparent;border-radius:10px;background:transparent;color:#999999;text-align:left;padding:11px 12px;cursor:pointer;transition:background .18s,border-color .18s,color .18s}
.nav-item:hover{background:#1a1a1a;color:var(--text)}
.nav-item.active{background:#1e1e1e;border-color:#323232;color:var(--text)}
.nav-item.active .nav-glyph{color:var(--accent)}
.nav-glyph{width:18px;color:#6d6d6d;text-align:center;font-size:17px}
.nav-count{margin-left:auto;color:var(--accent);font:10px var(--mono)}
.sidebar-spacer{flex:1;min-height:30px}
.sidebar-system{display:flex;align-items:center;gap:11px;padding:13px 11px;border:1px solid var(--line);border-radius:11px;background:#121212;margin-bottom:12px;min-width:0}
.signal-dot{width:7px;height:7px;border-radius:50%;background:#787878;box-shadow:0 0 0 4px #2c2c2c;flex:none}
.signal-dot.online{background:var(--accent);box-shadow:0 0 0 4px #2f2f2f,0 0 14px #d3d3d355}
.sidebar-system div{display:flex;flex-direction:column;gap:3px;min-width:0}
.sidebar-system strong{font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sidebar-system small{color:var(--muted);font:9px var(--mono);letter-spacing:.06em}
.signout{display:flex;justify-content:space-between;align-items:center;width:100%;padding:10px 12px;border:0;background:transparent;color:#8f8f8f;cursor:pointer;border-radius:9px;text-align:left}
.signout:hover{background:#1b1b1b;color:var(--text)}
.main{margin-left:248px;min-width:0;padding:0 36px 22px}
.topbar{height:86px;display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line-soft)}
.breadcrumb{display:flex;align-items:center;gap:11px;min-width:0}
.breadcrumb>span:first-child{font:10px var(--mono);letter-spacing:.14em;color:#767676}
.breadcrumb-divider{color:#4e4e4e}
.breadcrumb strong{font-size:12px;font-weight:600;color:#dbdbdb}
.topbar-right{display:flex;align-items:center;gap:14px}
.guild-control{display:flex;align-items:center;gap:9px;padding:8px 11px;border:1px solid var(--line);border-radius:10px;background:#131313}
.guild-control>span,.filter-control>span{color:#8a8a8a;font:9px var(--mono);letter-spacing:.1em;white-space:nowrap}
select{max-width:240px;color:var(--text);background-color:transparent;border:0;min-width:0;cursor:pointer}
select option{background:#191919;color:var(--text)}
.icon-button{display:grid;place-items:center;width:37px;height:37px;border:1px solid var(--line);border-radius:10px;background:#131313;color:#a0a0a0;font-size:20px;cursor:pointer;transition:background .2s,color .2s,border-color .2s}
.icon-button:hover{color:var(--accent);border-color:#505050;background:#1a1a1a}
.icon-button.spinning{animation:rotate .8s linear infinite}
.account{display:flex;align-items:center;gap:9px;padding-left:5px}
.avatar{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#2d2d2d;border:1px solid #454545;color:var(--accent);font-size:13px;font-weight:700}
.account-copy{display:flex;flex-direction:column;gap:2px;max-width:140px}
.account-copy strong{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.account-copy small{font:9px var(--mono);letter-spacing:.06em;color:var(--muted)}
.mobile-menu,.mobile-scrim{display:none}
.page{padding:34px 0 0;max-width:1600px;margin:0 auto;animation:fade-in .25s ease both}
.page-heading{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;margin-bottom:25px}
.page-heading-copy{min-width:0}
.eyebrow{margin:0 0 10px;color:#919191;font:10px var(--mono);letter-spacing:.13em;text-transform:uppercase}
.page-heading h1{margin:0;font-size:clamp(29px,3vw,42px);line-height:1.12;letter-spacing:-.055em;font-weight:650}
.page-heading h1 span{color:#868686;font-weight:450}
.lede{margin:12px 0 0;color:#979797;max-width:660px;font-size:13px;line-height:1.75}
.heading-actions{display:flex;gap:9px;align-items:center;flex:none}
.button{display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:39px;padding:0 14px;border:1px solid var(--line);border-radius:9px;background:#171717;color:#c5c5c5;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;transition:transform .16s,background .16s,border-color .16s,color .16s}
.button:hover:not(:disabled){background:#232323;border-color:#454545;color:var(--text);transform:translateY(-1px)}
.button.primary{background:var(--accent);border-color:var(--accent);color:#191919}
.button.primary:hover:not(:disabled){background:#f3f3f3;border-color:#f3f3f3;color:#141414}
.button.quiet{background:transparent;border-color:transparent}
.button.quiet:hover:not(:disabled){background:#1d1d1d}
.status-strip{display:flex;align-items:center;gap:10px;min-height:44px;padding:8px 13px;border:1px solid #353535;border-radius:10px;background:linear-gradient(90deg,#1b1b1b,#131313);color:#a4a4a4;font-size:11px;margin:0 0 17px}
.status-strip>span:nth-child(2){font:10px var(--mono);letter-spacing:.04em;color:#cdcdcd;white-space:nowrap}
.strip-signal{width:6px;height:6px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px #ededed66;flex:none}
.strip-separator{color:#555555}
.status-strip time{margin-left:auto;white-space:nowrap;color:#6f6f6f;font:9px var(--mono)}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:14px}
.metric{border:1px solid var(--line);border-radius:var(--radius);padding:17px 17px 15px;background:linear-gradient(145deg,#151515,#101010);min-width:0;min-height:142px}
.metric-label{display:flex;justify-content:space-between;gap:10px;color:#949494;font:9px var(--mono);letter-spacing:.05em}
.metric-label span{color:#545454}
.metric-value{display:block;margin:17px 0 10px;font-size:32px;line-height:1;font-weight:600;letter-spacing:-.055em;color:#efefef}
.metric-value small{font:12px var(--mono);letter-spacing:0;color:#929292;margin-left:6px}
.metric p{display:flex;flex-wrap:wrap;align-items:center;gap:5px;margin:0;color:#7e7e7e;font-size:10px}
.metric-dot{color:#4e4e4e}
.content-grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px}
.panel{min-width:0;border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(145deg,#151515,#111111);padding:20px}
.panel-large{grid-row:span 1}
.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:20px;min-width:0}
.panel-heading .eyebrow{margin-bottom:6px}
.panel-heading h2{margin:0;font-size:15px;letter-spacing:-.025em;font-weight:600}
.panel-index{color:#6d6d6d;font:9px var(--mono);letter-spacing:.06em;white-space:nowrap}
.runtime-body{display:flex;align-items:center;gap:17px;padding:8px 0 23px}
.runtime-mark{position:relative;display:grid;place-items:center;flex:none;width:62px;height:62px;border:1px solid #353535;border-radius:17px;background:radial-gradient(circle at 40% 30%,#292929,#141414);color:#9d9d9d;font-size:28px}
.runtime-mark span{animation:orbit 8s linear infinite}
.runtime-mark i{position:absolute;width:7px;height:7px;border-radius:50%;right:9px;top:9px;background:#7f7f7f}
.runtime-mark.is-online i{background:var(--accent);box-shadow:0 0 12px #edededaa}
.runtime-copy{min-width:0}
.runtime-state{margin:0 0 5px;font-size:13px;font-weight:650}
.muted{margin:0;color:#8e8e8e;font-size:11px;line-height:1.65}
.runtime-flags{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.status-pill{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:#171717;color:#a0a0a0;font:9px var(--mono);letter-spacing:.015em}
.status-pill i{width:5px;height:5px;border-radius:50%;background:#7a7a7a;flex:none}
.status-pill.is-good{border-color:#3d3d3d;background:#1f1f1f;color:#dadada}.status-pill.is-good i{background:var(--accent)}
.status-pill.is-bad{border-color:#363636;background:#1a1a1a;color:#bcbcbc}.status-pill.is-bad i{background:var(--danger)}
.status-pill.is-neutral i{background:#7d7d7d}
.runtime-data{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;border-top:1px solid var(--line);padding-top:17px}
.runtime-data>div{min-width:0;display:flex;flex-direction:column;gap:7px}
.runtime-data small{color:#7c7c7c;font:9px var(--mono);letter-spacing:.04em}
.runtime-data strong{font-size:12px;font-weight:600;overflow-wrap:anywhere}
.footnote{color:#7a7a7a;font-size:11px;line-height:1.7;margin:17px 0 0}
.footnote.compact{margin-top:12px}
.text-button{border:0;background:transparent;padding:0;color:var(--accent-dim);font-size:10px;cursor:pointer;white-space:nowrap}
.text-button:hover{color:var(--accent)}
.distribution-label{display:flex;align-items:baseline;gap:9px;margin-top:6px}
.distribution-label strong{font-size:29px;font-weight:600;letter-spacing:-.045em}
.distribution-label span{font-size:11px;color:#8d8d8d}
.distribution-track{display:block;width:100%;height:6px;margin:17px 0 11px;border-radius:99px;overflow:hidden}
.distribution-track-bg{fill:#2b2b2b}
.distribution-track-fill{fill:var(--accent);transition:width .3s ease}
.distribution-meta{display:flex;justify-content:space-between;gap:10px;color:#7f7f7f;font-size:10px}
.definition-list{margin:0}
.definition-list>div{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid var(--line-soft)}
.definition-list>div:last-child{border-bottom:0;padding-bottom:0}
.definition-list dt{color:#878787;font-size:11px}
.definition-list dd{margin:0;max-width:63%;text-align:right;font-size:11px;color:#d4d4d4;overflow-wrap:anywhere}
.mono{font-family:var(--mono);font-size:10px!important;color:#979797!important}
.activity-list{display:flex;flex-direction:column}
.activity-row{display:grid;grid-template-columns:15px minmax(0,1fr) auto;gap:9px;align-items:start;padding:13px 0;border-bottom:1px solid var(--line-soft)}
.activity-row:first-child{padding-top:0}
.activity-row:last-child{border-bottom:0;padding-bottom:0}
.activity-glyph{display:grid;place-items:center;width:15px;height:22px;color:var(--accent);font-size:22px;line-height:1}
.activity-copy{min-width:0;display:flex;flex-direction:column;gap:4px}
.activity-copy strong{font-weight:600;font-size:11px;text-transform:capitalize;overflow-wrap:anywhere}
.activity-copy small{color:#858585;font-size:10px;line-height:1.6;overflow-wrap:anywhere}
.activity-time{color:#787878;font:9px var(--mono);white-space:nowrap;padding-top:3px}
.empty-state{padding:22px 12px;border:1px dashed #2e2e2e;border-radius:10px;color:#838383;font-size:11px;text-align:center;line-height:1.7}
.loading-state{display:flex;align-items:center;justify-content:center;gap:10px}
.spinner{display:inline-block;width:14px;height:14px;border:1px solid #5b5b5b;border-top-color:var(--accent);border-radius:50%;animation:rotate .8s linear infinite}
.command-toolbar{display:grid;grid-template-columns:minmax(200px,1fr) minmax(160px,220px) minmax(130px,170px);gap:10px;margin-bottom:14px}
.search-field,.filter-control{display:flex;align-items:center;gap:9px;min-width:0;border:1px solid var(--line);border-radius:9px;background:#131313;padding:0 12px}
.search-field>span{font-size:20px;color:#838383}
.search-field input{width:100%;min-width:0;height:41px;background:transparent;border:0;color:var(--text);outline:none;font-size:11px}
.search-field input::placeholder{color:#6b6b6b}
.filter-control{justify-content:space-between;padding:0 11px}
.filter-control select{width:100%;height:40px;font-size:11px;text-align:right}
.filter-control>span{flex:none}
.command-summary{display:flex;justify-content:space-between;gap:12px;margin:0 2px 10px;color:#858585;font-size:10px}
.command-summary span:last-child{font:9px var(--mono);letter-spacing:.07em;color:#727272}
.command-list{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;background:#111111}
.command-row{display:grid;grid-template-columns:minmax(0,1fr) auto 43px;gap:20px;align-items:center;padding:17px 18px;border-bottom:1px solid var(--line-soft)}
.command-row:last-child{border-bottom:0}
.command-row:hover{background:#161616}
.command-main{min-width:0}
.command-name{font:12px var(--mono);font-weight:600;overflow-wrap:anywhere;color:#e9e9e9}
.command-prefix{color:var(--accent);margin-right:5px}
.command-description{margin:7px 0 0;color:#8b8b8b;font-size:11px;line-height:1.65;overflow-wrap:anywhere}
.command-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.tag{padding:3px 6px;border:1px solid #2e2e2e;border-radius:5px;background:#191919;color:#929292;font:9px var(--mono)}
.tag-protected{border-color:#484848;color:#d2d2d2;background:#1f1f1f}
.command-state{justify-self:end}
.switch{position:relative;width:38px;height:22px;padding:0;border:1px solid #464646;border-radius:99px;background:#292929;cursor:pointer;transition:background .2s,border-color .2s}
.switch span{position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#8a8a8a;transition:transform .2s,background .2s}
.switch.checked{background:#414141;border-color:#656565}
.switch.checked span{transform:translateX(16px);background:var(--accent)}
.extension-list{display:flex;flex-direction:column}
.extension-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:15px 0;border-bottom:1px solid var(--line-soft)}
.extension-row:first-child{padding-top:0}
.extension-row:last-child{border:0;padding-bottom:0}
.extension-row code{color:#dddddd;font:11px var(--mono);overflow-wrap:anywhere}
.extension-row .command-description{margin-top:4px}
.diagnostic-list>div{align-items:center}
.note-block{padding:15px 0;border-bottom:1px solid var(--line-soft)}
.note-block:first-of-type{padding-top:0}
.note-block:last-child{padding-bottom:0;border-bottom:0}
.note-block strong{font-size:12px}
.note-block p{margin:7px 0 0;color:#898989;font-size:11px;line-height:1.8}
.log-panel .panel-heading{align-items:center}
.log-output{min-height:320px;max-height:560px;overflow:auto;margin:0;padding:16px;border:1px solid #282828;border-radius:9px;background:#090909;color:#afafaf;font:11px/1.75 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;tab-size:2}
.table-scroll{width:100%;overflow-x:auto}
table{width:100%;border-collapse:collapse;text-align:left;min-width:500px}
th{padding:0 12px 13px;color:#7e7e7e;font:9px var(--mono);letter-spacing:.07em}
td{padding:14px 12px;border-top:1px solid var(--line-soft);font-size:11px;color:#c5c5c5;vertical-align:top}
td small{display:block;margin-top:5px;color:#858585;font-size:10px;line-height:1.6}
.page-footer{display:flex;justify-content:space-between;gap:16px;padding:29px 0 7px;color:#5e5e5e;font:9px var(--mono);letter-spacing:.06em}
.toast-stack{position:fixed;right:20px;bottom:20px;z-index:80;display:flex;flex-direction:column;gap:8px;width:min(390px,calc(100vw - 32px))}
.toast{display:flex;align-items:flex-start;gap:10px;padding:12px 12px;border:1px solid #404040;border-radius:10px;background:#1b1b1b;box-shadow:0 12px 36px #0008;color:#dedede;font-size:11px;line-height:1.6;animation:toast-in .2s ease both}
.toast>span{display:grid;place-items:center;width:18px;height:18px;border-radius:50%;flex:none;background:#3f3f3f;color:var(--accent);font-weight:700}
.toast button{margin-left:auto;padding:0 3px;background:transparent;border:0;color:#a2a2a2;font-size:17px;cursor:pointer}
.toast.error{border-color:#404040;background:#1a1a1a;color:#d5d5d5}
.toast.error>span{background:#2e2e2e;color:var(--danger)}
.modal-scrim{position:fixed;inset:0;z-index:90;display:grid;place-items:center;padding:20px;background:#040404cc;backdrop-filter:blur(8px)}
.confirm-dialog{width:min(470px,100%);padding:25px;border:1px solid #3f3f3f;border-radius:16px;background:#131313;box-shadow:0 24px 80px #000b;animation:fade-in .16s ease both}
.confirm-dialog h2{margin:0;font-size:22px;letter-spacing:-.04em}
.confirm-dialog>p:not(.eyebrow){margin:12px 0 22px;color:#959595;font-size:12px;line-height:1.8}
.dialog-actions{display:flex;justify-content:flex-end;gap:8px}
.boot-screen{display:flex;min-height:100vh;flex-direction:column;align-items:center;justify-content:center;gap:16px;color:#8f8f8f}
.boot-mark{display:grid;place-items:center;width:55px;height:55px;border:1px solid #454545;border-radius:15px;color:var(--accent);font-size:24px;font-weight:700}
.boot-screen p{margin:4px 0 0;font-size:12px}
.boot-screen small{font:9px var(--mono);letter-spacing:.1em;color:#646464}
.login-wrap{position:relative;isolation:isolate;display:grid;place-items:center;min-height:100vh;padding:36px 18px;overflow:hidden}
.login-orbit{position:absolute;border:1px solid #303030;border-radius:50%;z-index:-1;pointer-events:none}
.orbit-one{width:min(900px,115vw);aspect-ratio:1;transform:translate(28%,6%);box-shadow:inset 0 0 120px #1e1e1e}
.orbit-two{width:min(600px,85vw);aspect-ratio:1;transform:translate(28%,6%);border-style:dashed;opacity:.65}
.login-card{width:min(510px,100%);padding:34px;border:1px solid #313131;border-radius:21px;background:linear-gradient(145deg,#161616f5,#0d0d0df5);box-shadow:0 28px 90px #0009}
.login-brand{padding:0 0 31px;border-bottom:1px solid var(--line)}
.login-kicker{display:flex;align-items:center;gap:10px;margin:29px 0 14px;color:#969696;font:9px var(--mono);letter-spacing:.12em}
.login-kicker .signal-dot{width:6px;height:6px}
.login-card h1{margin:0;font-size:clamp(37px,9vw,52px);line-height:1.03;letter-spacing:-.065em;font-weight:650}
.login-card h1 span{color:#878787;font-weight:450}
.login-copy{margin:18px 0 25px;max-width:400px;color:#a0a0a0;font-size:13px;line-height:1.85}
.login-button{width:100%;min-height:48px;font-size:12px}
.inline-notice{padding:10px 12px;margin:0 0 16px;border:1px solid #444444;border-radius:8px;background:#1f1f1f;color:#d3d3d3;font-size:11px}
.login-separator{display:flex;align-items:center;gap:10px;margin:24px 0 17px;color:#6e6e6e;font:8px var(--mono);letter-spacing:.09em;white-space:nowrap}
.login-separator span{height:1px;background:var(--line);flex:1}
.login-assurances{display:grid;gap:11px}
.login-assurances>span{display:flex;align-items:center;gap:10px;color:#909090;font-size:10px}
.login-assurances b{display:grid;place-items:center;width:23px;height:23px;border:1px solid #363636;border-radius:7px;color:var(--accent);font:9px var(--mono)}
.login-foot{display:flex;justify-content:space-between;gap:10px;margin-top:28px;padding-top:17px;border-top:1px solid var(--line);font:8px var(--mono);letter-spacing:.06em;color:#696969}
@keyframes fade-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
@keyframes toast-in{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
@keyframes rotate{to{transform:rotate(360deg)}}
@keyframes orbit{to{transform:rotate(360deg)}}
@media(max-width:1250px){.main{padding:0 25px 22px}.sidebar{width:225px}.main{margin-left:225px}.metric{padding:15px}.metric-value{font-size:28px}.account-copy{max-width:105px}.topbar-right{gap:9px}}
@media(max-width:960px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid{grid-template-columns:minmax(0,1fr)}.panel-large{grid-row:auto}.page-heading{align-items:flex-start;flex-direction:column}.heading-actions{width:100%;flex-wrap:wrap}.topbar{height:75px}.account-copy{display:none}}
@media(max-width:760px){.sidebar{width:min(290px,84vw);transform:translateX(-105%);transition:transform .24s ease;box-shadow:none}.sidebar.mobile-open{transform:translateX(0);box-shadow:20px 0 80px #0009}.mobile-scrim{position:fixed;inset:0;z-index:25;display:block;width:100%;height:100%;border:0;background:#0009;opacity:0;pointer-events:none;transition:opacity .2s}.mobile-scrim.active{opacity:1;pointer-events:auto}.main{margin-left:0;padding:0 18px 20px}.mobile-menu{display:grid}.topbar{gap:12px}.breadcrumb{margin-right:auto}.topbar-right{gap:7px}.guild-control{padding:7px 8px;max-width:190px}.guild-control>span{display:none}.guild-control select{max-width:150px}.page{padding-top:25px}.page-heading h1{font-size:34px}.lede{font-size:12px}.status-strip{align-items:flex-start;flex-wrap:wrap}.status-strip time{width:100%;margin-left:16px}.command-toolbar{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}.command-row{grid-template-columns:minmax(0,1fr) 40px;gap:10px;padding:15px}.command-state{grid-column:1;grid-row:2;justify-self:start}.switch{grid-column:2;grid-row:1;justify-self:end}.command-tags{gap:5px}.metric{min-height:132px}.page-footer{font-size:8px}.account{display:none}}
@media(max-width:480px){.main{padding-right:13px;padding-left:13px}.topbar{height:69px}.breadcrumb>span:first-child,.breadcrumb-divider{display:none}.breadcrumb strong{font-size:11px}.icon-button{width:33px;height:33px}.guild-control{max-width:150px}.guild-control select{max-width:125px;font-size:10px}.metric-grid{gap:8px}.metric{padding:13px 12px;min-height:128px}.metric-label{font-size:8px}.metric-value{font-size:26px;margin-top:16px}.metric p{font-size:9px}.page-heading h1{font-size:31px}.heading-actions .button{flex:1;padding:0 9px}.status-strip{font-size:10px}.panel{padding:15px}.runtime-body{align-items:flex-start;gap:12px}.runtime-mark{width:48px;height:48px;border-radius:13px;font-size:23px}.runtime-data{grid-template-columns:1fr;gap:13px}.runtime-data>div{flex-direction:row;align-items:baseline;justify-content:space-between}.activity-row{grid-template-columns:12px minmax(0,1fr);gap:7px}.activity-time{grid-column:2;padding:0}.command-toolbar{grid-template-columns:1fr}.search-field{grid-column:auto}.filter-control{min-height:40px}.command-summary{align-items:flex-start;flex-direction:column;gap:5px}.command-row{padding:14px 12px}.extension-row{align-items:flex-start;flex-direction:column;gap:8px}.login-card{padding:24px 20px}.login-foot{font-size:7px}.confirm-dialog{padding:20px}.dialog-actions .button{flex:1}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
/* Command references: make each registered slash command a real, usable destination. */
.command-name-link{display:inline-flex;align-items:center;gap:7px;max-width:100%;color:#e9e9e9;text-decoration:none;transition:color .16s ease}
.command-name-link:hover{color:var(--accent)}
.command-name-link:focus-visible{outline:2px solid var(--accent);outline-offset:4px;border-radius:4px}
.command-link-glyph{color:var(--accent);font:10px var(--mono);opacity:.8}
.command-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:12px}
.command-copy,.command-guide{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:29px;padding:6px 9px;border:1px solid #353535;border-radius:7px;background:#181818;color:#c0c0c0;font:9px var(--mono);letter-spacing:.025em;cursor:pointer;transition:background .16s ease,border-color .16s ease,color .16s ease}
.command-guide{background:transparent;color:#a8a8a8;text-decoration:none}
.command-copy:hover,.command-guide:hover{border-color:#6d6d6d;background:#252525;color:var(--accent)}
.command-copy:focus-visible,.command-guide:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media(max-width:760px){.command-actions{gap:7px;margin-top:10px}.command-copy,.command-guide{min-height:31px;padding:7px 8px}}
@media(max-width:480px){.command-actions{gap:6px}.command-copy,.command-guide{font-size:8px;padding:7px 7px}}


/* Monochrome redesign: precise contrast, restrained motion, and braille as a live signal motif. */
html{background:#000;color-scheme:dark}
body{background:radial-gradient(ellipse at 72% -18%,#171717 0%,transparent 45%),#000;color:#f5f5f5}
.sidebar{background:rgba(0,0,0,.96);border-right-color:#262626}
.brand-mark{border-color:#666;background:linear-gradient(145deg,#262626,#070707);color:#fff;box-shadow:inset 0 0 0 1px #ffffff08}
.nav-item:hover,.nav-item.active{background:#151515;border-color:#333;color:#fff}
.nav-item.active .nav-glyph,.nav-item:hover .nav-glyph{color:#fff}
.sidebar-system,.guild-control,.icon-button,.panel,.metric,.command-row,.confirm-dialog,.login-card{background-color:#090909;border-color:#292929}
.button{background:#111;border-color:#383838;color:#e5e5e5}
.button:hover:not(:disabled){background:#242424;border-color:#666;color:#fff}
.button.primary{background:#fff;border-color:#fff;color:#000}
.button.primary:hover:not(:disabled){background:#dcdcdc;border-color:#dcdcdc;color:#000}
.status-strip{background:linear-gradient(90deg,#171717,#080808);border-color:#393939;color:#c4c4c4}
.status-strip>span:nth-child(2),.breadcrumb strong,.metric-value,.command-name-link{color:#f5f5f5}
.strip-signal,.signal-dot.online{background:#fff;box-shadow:0 0 0 4px #ffffff12,0 0 16px #ffffff22}
.metric{background:linear-gradient(145deg,#151515,#080808)}
.panel{background:linear-gradient(145deg,#101010,#080808)}
.panel:hover,.metric:hover{border-color:#484848}
.runtime-mark{border-color:#424242;background:radial-gradient(circle at 50% 50%,#202020,#050505)}
.runtime-mark.is-online{border-color:#777;box-shadow:0 0 0 1px #ffffff0a,0 0 30px #ffffff0b}
.distribution-track-fill{fill:#fff}
.switch.checked{background:#fafafa;border-color:#fff}
.switch.checked span{background:#050505}
.status-pill.is-good{color:#fff;border-color:#555;background:#171717}
.status-pill.is-bad{color:#c8c8c8;border-color:#4a4a4a;background:#171717}
.command-row:hover{border-color:#505050;background:#111}
.command-copy,.command-guide{border-color:#363636;background:#0e0e0e;color:#d4d4d4}
.command-copy:hover,.command-guide:hover{border-color:#777;background:#1a1a1a;color:#fff}
.tag-protected{border-color:#5b5b5b;color:#fff;background:#1e1e1e}
.topbar{border-bottom-color:#1b1b1b}
.guild-control:focus-within,.filter-control:focus-within,.search-field:focus-within{border-color:#888;box-shadow:0 0 0 3px #ffffff0c}
:where(button,a,input,select,textarea,[tabindex]):focus-visible{outline:2px solid #fff;outline-offset:3px}
.page{animation:page-rise .44s cubic-bezier(.2,.7,.2,1) both}
.panel,.metric,.command-row,.extension-row,.activity-row{transition:border-color .22s ease,background-color .22s ease,transform .22s ease}
.command-row:hover{transform:translateY(-1px)}
.button:active:not(:disabled),.icon-button:active:not(:disabled){transform:translateY(1px)}
.login-wrap{background:radial-gradient(ellipse at 76% 25%,#131313 0%,transparent 43%),#000}
.login-orbit{border-color:#292929}
.login-card{background:linear-gradient(145deg,#111,#050505);border-color:#393939;box-shadow:0 28px 100px #000}
.login-card h1 span{color:#a9a9a9}
.login-kicker,.login-copy,.login-assurances>span{color:#b0b0b0}
.login-separator,.login-foot,.boot-screen small{color:#777}
.braille-band{position:relative;display:flex;align-items:center;justify-content:space-between;gap:20px;min-height:31px;margin:0 0 3px;overflow:hidden;border-bottom:1px solid #171717;color:#878787;font:9px var(--mono);letter-spacing:.16em}
.braille-band::before{position:absolute;inset:0;content:"";pointer-events:none;background-image:radial-gradient(#888 .7px,transparent .85px);background-size:8px 8px;opacity:.09;mask-image:linear-gradient(90deg,transparent,#000 14%,#000 86%,transparent)}
.braille-track{position:relative;display:block;max-width:37%;overflow:hidden;white-space:nowrap;font-family:system-ui,sans-serif;font-size:15px;letter-spacing:.16em;line-height:1.1;opacity:.7}
.braille-track-a{animation:braille-drift 19s linear infinite}
.braille-track-b{animation:braille-drift-reverse 24s linear infinite;opacity:.4}
.braille-band-label{position:relative;flex:none;color:#a9a9a9;font-size:8px;letter-spacing:.17em}
.braille-mini{margin-left:auto;font:14px system-ui,sans-serif;letter-spacing:.12em;color:#fff;animation:braille-flicker 4.6s steps(1,end) infinite}
.runtime-mark span{display:inline-block;font-family:system-ui,sans-serif;animation:braille-pulse 6.2s steps(1,end) infinite}
.runtime-mark.is-online span{animation-duration:4.1s}
.runtime-mark i{background:#fff}
.spinner{border-color:#3d3d3d;border-top-color:#fff}
.toast{background:#101010;border-color:#414141}
.toast.error{border-color:#626262;background:#171717;color:#f0f0f0}
.confirm-dialog{box-shadow:0 24px 90px #000}
@keyframes page-rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:translateY(0)}}
@keyframes braille-drift{0%{transform:translateX(0);opacity:.42}50%{opacity:.78}100%{transform:translateX(9px);opacity:.42}}
@keyframes braille-drift-reverse{0%{transform:translateX(4px);opacity:.25}50%{opacity:.58}100%{transform:translateX(-8px);opacity:.25}}
@keyframes braille-flicker{0%,16%,18%,64%,68%,100%{opacity:.45}17%,65%{opacity:1}34%,53%{opacity:.72}}
@keyframes braille-pulse{0%,14%,25%,43%,71%,100%{opacity:.72;transform:translateY(0)}16%,45%,73%{opacity:1;transform:translateY(-1px)}18%,48%,76%{opacity:.5;transform:translateY(0)}}
@media(max-width:760px){.braille-track{max-width:28%;font-size:13px}.braille-band-label{font-size:7px}.braille-band{gap:8px}}
@media(prefers-reduced-motion:reduce){.braille-track,.braille-mini,.runtime-mark span,.page{animation:none!important;transform:none!important}}

`;

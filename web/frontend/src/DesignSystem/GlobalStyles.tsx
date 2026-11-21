const GLOBAL_STYLES = String.raw`
:root {
  color-scheme:dark;
  --bg:#000;
  --surface:#090909;
  --surface-2:#111;
  --surface-3:#191919;
  --line:#2a2a2a;
  --line-soft:#1c1c1c;
  --text:#f5f5f5;
  --muted:#929292;
  --soft:#c9c9c9;
  --accent:#fff;
  --accent-dim:#bdbdbd;
  --danger:#bdbdbd;
  --font:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",monospace;
  --radius:15px;
  font-synthesis:none;
  text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased
}
* {
  box-sizing:border-box
}
html {
  min-width:320px;
  background:var(--bg);
  scroll-behavior:smooth
}
body {
  margin:0;
  min-width:320px;
  min-height:100vh;
  background:radial-gradient(ellipse at 70% -15%,#1f1f1f 0%,transparent 43%),var(--bg);
  color:var(--text);
  font-family:var(--font);
  font-size:14px;
  line-height:1.5
}
button,input,select {
  font:inherit
}
button,a,select,input {
  outline-offset:3px
}
button:focus-visible,a:focus-visible,select:focus-visible,input:focus-visible {
  outline:2px solid var(--accent)
}
button {
  color:inherit
}
a {
  color:inherit;
  text-decoration:none
}
button:disabled {
  opacity:.45;
  cursor:not-allowed!important
}
.app-shell {
  min-height:100vh
}
.sidebar {
  position:fixed;
  inset:0 auto 0 0;
  width:248px;
  display:flex;
  flex-direction:column;
  padding:27px 17px 17px;
  background:rgba(0,0,0,.96);
  border-right:1px solid var(--line-soft);
  z-index:30;
  backdrop-filter:blur(18px)
}
.brand {
  display:flex;
  align-items:center;
  gap:12px;
  padding:0 9px 24px
}
.brand-mark {
  display:grid;
  place-items:center;
  width:41px;
  height:41px;
  border:1px solid #545454;
  border-radius:12px;
  background:linear-gradient(145deg,#282828,#131313);
  color:var(--accent);
  font-size:20px;
  font-weight:750;
  letter-spacing:-2px
}
.brand-copy {
  display:flex;
  flex-direction:column;
  gap:3px
}
.brand-copy strong {
  font-size:12px;
  letter-spacing:.19em;
  font-weight:750
}
.brand-copy small {
  font:9px var(--mono);
  letter-spacing:.16em;
  color:var(--muted)
}
.sidebar-rule {
  height:1px;
  background:var(--line);
  margin:0 9px 23px
}
.nav-label {
  margin:0 12px 11px;
  color:#747474;
  font:10px var(--mono);
  letter-spacing:.1em
}
.nav-label span {
  color:#4c4c4c
}
.main-nav {
  display:grid;
  gap:4px
}
.nav-item {
  display:flex;
  align-items:center;
  gap:12px;
  width:100%;
  border:1px solid transparent;
  border-radius:10px;
  background:transparent;
  color:#999999;
  text-align:left;
  padding:11px 12px;
  cursor:pointer;
  transition:background .18s,border-color .18s,color .18s
}
.nav-item:hover {
  background:#1a1a1a;
  color:var(--text)
}
.nav-item.active {
  background:#1e1e1e;
  border-color:#323232;
  color:var(--text)
}
.nav-item.active .nav-glyph {
  color:var(--accent)
}
.nav-glyph {
  width:18px;
  color:#6d6d6d;
  text-align:center;
  font-size:17px
}
.nav-count {
  margin-left:auto;
  color:var(--accent);
  font:10px var(--mono)
}
.sidebar-spacer {
  flex:1;
  min-height:30px
}
.sidebar-system {
  display:flex;
  align-items:center;
  gap:11px;
  padding:13px 11px;
  border:1px solid var(--line);
  border-radius:11px;
  background:#121212;
  margin-bottom:12px;
  min-width:0
}
.signal-dot {
  width:7px;
  height:7px;
  border-radius:50%;
  background:#787878;
  box-shadow:0 0 0 4px #2c2c2c;
  flex:none
}
.signal-dot.online {
  background:var(--accent);
  box-shadow:0 0 0 4px #2f2f2f,0 0 14px #d3d3d355
}
.sidebar-system div {
  display:flex;
  flex-direction:column;
  gap:3px;
  min-width:0
}
.sidebar-system strong {
  font-size:11px;
  font-weight:600;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis
}
.sidebar-system small {
  color:var(--muted);
  font:9px var(--mono);
  letter-spacing:.06em
}
.signout {
  display:flex;
  justify-content:space-between;
  align-items:center;
  width:100%;
  padding:10px 12px;
  border:0;
  background:transparent;
  color:#8f8f8f;
  cursor:pointer;
  border-radius:9px;
  text-align:left
}
.signout:hover {
  background:#1b1b1b;
  color:var(--text)
}
.main {
  margin-left:248px;
  min-width:0;
  padding:0 36px 22px
}
.topbar {
  height:86px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  border-bottom:1px solid var(--line-soft)
}
.breadcrumb {
  display:flex;
  align-items:center;
  gap:11px;
  min-width:0
}
.breadcrumb>span:first-child {
  font:10px var(--mono);
  letter-spacing:.14em;
  color:#767676
}
.breadcrumb-divider {
  color:#4e4e4e
}
.breadcrumb strong {
  font-size:12px;
  font-weight:600;
  color:#dbdbdb
}
.topbar-right {
  display:flex;
  align-items:center;
  gap:14px
}
.guild-control {
  display:flex;
  align-items:center;
  gap:9px;
  padding:8px 11px;
  border:1px solid var(--line);
  border-radius:10px;
  background:#131313
}
.guild-control>span,.filter-control>span {
  color:#8a8a8a;
  font:9px var(--mono);
  letter-spacing:.1em;
  white-space:nowrap
}
select {
  max-width:240px;
  color:var(--text);
  background-color:transparent;
  border:0;
  min-width:0;
  cursor:pointer
}
select option {
  background:#191919;
  color:var(--text)
}
.icon-button {
  display:grid;
  place-items:center;
  width:37px;
  height:37px;
  border:1px solid var(--line);
  border-radius:10px;
  background:#131313;
  color:#a0a0a0;
  font-size:20px;
  cursor:pointer;
  transition:background .2s,color .2s,border-color .2s
}
.icon-button:hover {
  color:var(--accent);
  border-color:#505050;
  background:#1a1a1a
}
.icon-button.spinning {
  animation:rotate .8s linear infinite
}
.account {
  display:flex;
  align-items:center;
  gap:9px;
  padding-left:5px
}
.avatar {
  display:grid;
  place-items:center;
  width:34px;
  height:34px;
  border-radius:50%;
  background:#2d2d2d;
  border:1px solid #454545;
  color:var(--accent);
  font-size:13px;
  font-weight:700
}
.account-copy {
  display:flex;
  flex-direction:column;
  gap:2px;
  max-width:140px
}
.account-copy strong {
  font-size:11px;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
  font-weight:600
}
.account-copy small {
  font:9px var(--mono);
  letter-spacing:.06em;
  color:var(--muted)
}
.mobile-menu,.mobile-scrim {
  display:none
}
.page {
  padding:34px 0 0;
  max-width:1600px;
  margin:0 auto;
  animation:fade-in .25s ease both
}
.page-heading {
  display:flex;
  justify-content:space-between;
  align-items:flex-end;
  gap:24px;
  margin-bottom:25px
}
.page-heading-copy {
  min-width:0
}
.eyebrow {
  margin:0 0 10px;
  color:#919191;
  font:10px var(--mono);
  letter-spacing:.13em;
  text-transform:uppercase
}
.page-heading h1 {
  margin:0;
  font-size:clamp(29px,3vw,42px);
  line-height:1.12;
  letter-spacing:-.055em;
  font-weight:650
}
.page-heading h1 span {
  color:#868686;
  font-weight:450
}
.lede {
  margin:12px 0 0;
  color:#979797;
  max-width:660px;
  font-size:13px;
  line-height:1.75
}
.heading-actions {
  display:flex;
  gap:9px;
  align-items:center;
  flex:none
}
.button {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:10px;
  min-height:39px;
  padding:0 14px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#171717;
  color:#c5c5c5;
  font-size:11px;
  font-weight:600;
  cursor:pointer;
  white-space:nowrap;
  transition:transform .16s,background .16s,border-color .16s,color .16s
}
.button:hover:not(:disabled) {
  background:#232323;
  border-color:#454545;
  color:var(--text);
  transform:translateY(-1px)
}
.button.primary {
  background:var(--accent);
  border-color:var(--accent);
  color:#191919
}
.button.primary:hover:not(:disabled) {
  background:#f3f3f3;
  border-color:#f3f3f3;
  color:#141414
}
.button.quiet {
  background:transparent;
  border-color:transparent
}
.button.quiet:hover:not(:disabled) {
  background:#1d1d1d
}
.status-strip {
  display:flex;
  align-items:center;
  gap:10px;
  min-height:44px;
  padding:8px 13px;
  border:1px solid #353535;
  border-radius:10px;
  background:linear-gradient(90deg,#1b1b1b,#131313);
  color:#a4a4a4;
  font-size:11px;
  margin:0 0 17px
}
.status-strip>span:nth-child(2) {
  font:10px var(--mono);
  letter-spacing:.04em;
  color:#cdcdcd;
  white-space:nowrap
}
.strip-signal {
  width:6px;
  height:6px;
  border-radius:50%;
  background:var(--accent);
  box-shadow:0 0 10px #ededed66;
  flex:none
}
.strip-separator {
  color:#555555
}
.status-strip time {
  margin-left:auto;
  white-space:nowrap;
  color:#6f6f6f;
  font:9px var(--mono)
}
.metric-grid {
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:13px;
  margin-bottom:14px
}
.metric {
  border:1px solid var(--line);
  border-radius:var(--radius);
  padding:17px 17px 15px;
  background:linear-gradient(145deg,#151515,#101010);
  min-width:0;
  min-height:142px
}
.metric-label {
  display:flex;
  justify-content:space-between;
  gap:10px;
  color:#949494;
  font:9px var(--mono);
  letter-spacing:.05em
}
.metric-label span {
  color:#545454
}
.metric-value {
  display:block;
  margin:17px 0 10px;
  font-size:32px;
  line-height:1;
  font-weight:600;
  letter-spacing:-.055em;
  color:#efefef
}
.metric-value small {
  font:12px var(--mono);
  letter-spacing:0;
  color:#929292;
  margin-left:6px
}
.metric p {
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:5px;
  margin:0;
  color:#7e7e7e;
  font-size:10px
}
.metric-dot {
  color:#4e4e4e
}
.content-grid {
  display:grid;
  grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);
  gap:14px
}
.panel {
  min-width:0;
  border:1px solid var(--line);
  border-radius:var(--radius);
  background:linear-gradient(145deg,#151515,#111111);
  padding:20px
}
.panel-large {
  grid-row:span 1
}
.panel-heading {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:14px;
  margin-bottom:20px;
  min-width:0
}
.panel-heading .eyebrow {
  margin-bottom:6px
}
.panel-heading h2 {
  margin:0;
  font-size:15px;
  letter-spacing:-.025em;
  font-weight:600
}
.panel-index {
  color:#6d6d6d;
  font:9px var(--mono);
  letter-spacing:.06em;
  white-space:nowrap
}
.runtime-body {
  display:flex;
  align-items:center;
  gap:17px;
  padding:8px 0 23px
}
.runtime-mark {
  position:relative;
  display:grid;
  place-items:center;
  flex:none;
  width:62px;
  height:62px;
  border:1px solid #353535;
  border-radius:17px;
  background:radial-gradient(circle at 40% 30%,#292929,#141414);
  color:#9d9d9d;
  font-size:28px
}
.runtime-mark span {
  animation:orbit 8s linear infinite
}
.runtime-mark i {
  position:absolute;
  width:7px;
  height:7px;
  border-radius:50%;
  right:9px;
  top:9px;
  background:#7f7f7f
}
.runtime-mark.is-online i {
  background:var(--accent);
  box-shadow:0 0 12px #edededaa
}
.runtime-copy {
  min-width:0
}
.runtime-state {
  margin:0 0 5px;
  font-size:13px;
  font-weight:650
}
.muted {
  margin:0;
  color:#8e8e8e;
  font-size:11px;
  line-height:1.65
}
.runtime-flags {
  display:flex;
  flex-wrap:wrap;
  gap:7px;
  margin-top:12px
}
.status-pill {
  display:inline-flex;
  align-items:center;
  gap:6px;
  white-space:nowrap;
  padding:5px 8px;
  border:1px solid var(--line);
  border-radius:6px;
  background:#171717;
  color:#a0a0a0;
  font:9px var(--mono);
  letter-spacing:.015em
}
.status-pill i {
  width:5px;
  height:5px;
  border-radius:50%;
  background:#7a7a7a;
  flex:none
}
.status-pill.is-good {
  border-color:#3d3d3d;
  background:#1f1f1f;
  color:#dadada
}
.status-pill.is-good i {
  background:var(--accent)
}
.status-pill.is-bad {
  border-color:#363636;
  background:#1a1a1a;
  color:#bcbcbc
}
.status-pill.is-bad i {
  background:var(--danger)
}
.status-pill.is-neutral i {
  background:#7d7d7d
}
.runtime-data {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:10px;
  border-top:1px solid var(--line);
  padding-top:17px
}
.runtime-data>div {
  min-width:0;
  display:flex;
  flex-direction:column;
  gap:7px
}
.runtime-data small {
  color:#7c7c7c;
  font:9px var(--mono);
  letter-spacing:.04em
}
.runtime-data strong {
  font-size:12px;
  font-weight:600;
  overflow-wrap:anywhere
}
.footnote {
  color:#7a7a7a;
  font-size:11px;
  line-height:1.7;
  margin:17px 0 0
}
.footnote.compact {
  margin-top:12px
}
.text-button {
  border:0;
  background:transparent;
  padding:0;
  color:var(--accent-dim);
  font-size:10px;
  cursor:pointer;
  white-space:nowrap
}
.text-button:hover {
  color:var(--accent)
}
.distribution-label {
  display:flex;
  align-items:baseline;
  gap:9px;
  margin-top:6px
}
.distribution-label strong {
  font-size:29px;
  font-weight:600;
  letter-spacing:-.045em
}
.distribution-label span {
  font-size:11px;
  color:#8d8d8d
}
.distribution-track {
  display:block;
  width:100%;
  height:6px;
  margin:17px 0 11px;
  border-radius:99px;
  overflow:hidden
}
.distribution-track-bg {
  fill:#2b2b2b
}
.distribution-track-fill {
  fill:var(--accent);
  transition:width .3s ease
}
.distribution-meta {
  display:flex;
  justify-content:space-between;
  gap:10px;
  color:#7f7f7f;
  font-size:10px
}
.definition-list {
  margin:0
}
.definition-list>div {
  display:flex;
  justify-content:space-between;
  gap:16px;
  padding:12px 0;
  border-bottom:1px solid var(--line-soft)
}
.definition-list>div:last-child {
  border-bottom:0;
  padding-bottom:0
}
.definition-list dt {
  color:#878787;
  font-size:11px
}
.definition-list dd {
  margin:0;
  max-width:63%;
  text-align:right;
  font-size:11px;
  color:#d4d4d4;
  overflow-wrap:anywhere
}
.mono {
  font-family:var(--mono);
  font-size:10px!important;
  color:#979797!important
}
.activity-list {
  display:flex;
  flex-direction:column
}
.activity-row {
  display:grid;
  grid-template-columns:15px minmax(0,1fr) auto;
  gap:9px;
  align-items:start;
  padding:13px 0;
  border-bottom:1px solid var(--line-soft)
}
.activity-row:first-child {
  padding-top:0
}
.activity-row:last-child {
  border-bottom:0;
  padding-bottom:0
}
.activity-glyph {
  display:grid;
  place-items:center;
  width:15px;
  height:22px;
  color:var(--accent);
  font-size:22px;
  line-height:1
}
.activity-copy {
  min-width:0;
  display:flex;
  flex-direction:column;
  gap:4px
}
.activity-copy strong {
  font-weight:600;
  font-size:11px;
  text-transform:capitalize;
  overflow-wrap:anywhere
}
.activity-copy small {
  color:#858585;
  font-size:10px;
  line-height:1.6;
  overflow-wrap:anywhere
}
.activity-time {
  color:#787878;
  font:9px var(--mono);
  white-space:nowrap;
  padding-top:3px
}
.empty-state {
  padding:22px 12px;
  border:1px dashed #2e2e2e;
  border-radius:10px;
  color:#838383;
  font-size:11px;
  text-align:center;
  line-height:1.7
}
.loading-state {
  display:flex;
  align-items:center;
  justify-content:center;
  gap:10px
}
.spinner {
  display:inline-block;
  width:14px;
  height:14px;
  border:1px solid #5b5b5b;
  border-top-color:var(--accent);
  border-radius:50%;
  animation:rotate .8s linear infinite
}
.command-toolbar {
  display:grid;
  grid-template-columns:minmax(200px,1fr) minmax(160px,220px) minmax(130px,170px);
  gap:10px;
  margin-bottom:14px
}
.search-field,.filter-control {
  display:flex;
  align-items:center;
  gap:9px;
  min-width:0;
  border:1px solid var(--line);
  border-radius:9px;
  background:#131313;
  padding:0 12px
}
.search-field>span {
  font-size:20px;
  color:#838383
}
.search-field input {
  width:100%;
  min-width:0;
  height:41px;
  background:transparent;
  border:0;
  color:var(--text);
  outline:none;
  font-size:11px
}
.search-field input::placeholder {
  color:#6b6b6b
}
.filter-control {
  justify-content:space-between;
  padding:0 11px
}
.filter-control select {
  width:100%;
  height:40px;
  font-size:11px;
  text-align:right
}
.filter-control>span {
  flex:none
}
.command-summary {
  display:flex;
  justify-content:space-between;
  gap:12px;
  margin:0 2px 10px;
  color:#858585;
  font-size:10px
}
.command-summary span:last-child {
  font:9px var(--mono);
  letter-spacing:.07em;
  color:#727272
}
.command-list {
  display:flex;
  flex-direction:column;
  border:1px solid var(--line);
  border-radius:var(--radius);
  overflow:hidden;
  background:#111111
}
.command-row {
  display:grid;
  grid-template-columns:minmax(0,1fr) auto 43px;
  gap:20px;
  align-items:center;
  padding:17px 18px;
  border-bottom:1px solid var(--line-soft)
}
.command-row:last-child {
  border-bottom:0
}
.command-row:hover {
  background:#161616
}
.command-main {
  min-width:0
}
.command-name {
  font:12px var(--mono);
  font-weight:600;
  overflow-wrap:anywhere;
  color:#e9e9e9
}
.command-prefix {
  color:var(--accent);
  margin-right:5px
}
.command-description {
  margin:7px 0 0;
  color:#8b8b8b;
  font-size:11px;
  line-height:1.65;
  overflow-wrap:anywhere
}
.command-tags {
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin-top:9px
}
.tag {
  padding:3px 6px;
  border:1px solid #2e2e2e;
  border-radius:5px;
  background:#191919;
  color:#929292;
  font:9px var(--mono)
}
.tag-protected {
  border-color:#484848;
  color:#d2d2d2;
  background:#1f1f1f
}
.command-state {
  justify-self:end
}
.switch {
  position:relative;
  width:38px;
  height:22px;
  padding:0;
  border:1px solid #464646;
  border-radius:99px;
  background:#292929;
  cursor:pointer;
  transition:background .2s,border-color .2s
}
.switch span {
  position:absolute;
  top:3px;
  left:3px;
  width:14px;
  height:14px;
  border-radius:50%;
  background:#8a8a8a;
  transition:transform .2s,background .2s
}
.switch.checked {
  background:#414141;
  border-color:#656565
}
.switch.checked span {
  transform:translateX(16px);
  background:var(--accent)
}
.extension-list {
  display:flex;
  flex-direction:column
}
.extension-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
  padding:15px 0;
  border-bottom:1px solid var(--line-soft)
}
.extension-row:first-child {
  padding-top:0
}
.extension-row:last-child {
  border:0;
  padding-bottom:0
}
.extension-row code {
  color:#dddddd;
  font:11px var(--mono);
  overflow-wrap:anywhere
}
.extension-row .command-description {
  margin-top:4px
}
.diagnostic-list>div {
  align-items:center
}
.note-block {
  padding:15px 0;
  border-bottom:1px solid var(--line-soft)
}
.note-block:first-of-type {
  padding-top:0
}
.note-block:last-child {
  padding-bottom:0;
  border-bottom:0
}
.note-block strong {
  font-size:12px
}
.note-block p {
  margin:7px 0 0;
  color:#898989;
  font-size:11px;
  line-height:1.8
}
.log-panel .panel-heading {
  align-items:center
}
.log-output {
  min-height:320px;
  max-height:560px;
  overflow:auto;
  margin:0;
  padding:16px;
  border:1px solid #282828;
  border-radius:9px;
  background:#090909;
  color:#afafaf;
  font:11px/1.75 var(--mono);
  white-space:pre-wrap;
  overflow-wrap:anywhere;
  tab-size:2
}
.table-scroll {
  width:100%;
  overflow-x:auto
}
table {
  width:100%;
  border-collapse:collapse;
  text-align:left;
  min-width:500px
}
th {
  padding:0 12px 13px;
  color:#7e7e7e;
  font:9px var(--mono);
  letter-spacing:.07em
}
td {
  padding:14px 12px;
  border-top:1px solid var(--line-soft);
  font-size:11px;
  color:#c5c5c5;
  vertical-align:top
}
td small {
  display:block;
  margin-top:5px;
  color:#858585;
  font-size:10px;
  line-height:1.6
}
.page-footer {
  display:flex;
  justify-content:space-between;
  gap:16px;
  padding:29px 0 7px;
  color:#5e5e5e;
  font:9px var(--mono);
  letter-spacing:.06em
}
.toast-stack {
  position:fixed;
  right:20px;
  bottom:20px;
  z-index:80;
  display:flex;
  flex-direction:column;
  gap:8px;
  width:min(390px,calc(100vw - 32px))
}
.toast {
  display:flex;
  align-items:flex-start;
  gap:10px;
  padding:12px 12px;
  border:1px solid #404040;
  border-radius:10px;
  background:#1b1b1b;
  box-shadow:0 12px 36px #0008;
  color:#dedede;
  font-size:11px;
  line-height:1.6;
  animation:toast-in .2s ease both
}
.toast>span {
  display:grid;
  place-items:center;
  width:18px;
  height:18px;
  border-radius:50%;
  flex:none;
  background:#3f3f3f;
  color:var(--accent);
  font-weight:700
}
.toast button {
  margin-left:auto;
  padding:0 3px;
  background:transparent;
  border:0;
  color:#a2a2a2;
  font-size:17px;
  cursor:pointer
}
.toast.error {
  border-color:#404040;
  background:#1a1a1a;
  color:#d5d5d5
}
.toast.error>span {
  background:#2e2e2e;
  color:var(--danger)
}
.modal-scrim {
  position:fixed;
  inset:0;
  z-index:90;
  display:grid;
  place-items:center;
  padding:20px;
  background:#040404cc;
  backdrop-filter:blur(8px)
}
.confirm-dialog {
  width:min(470px,100%);
  padding:25px;
  border:1px solid #3f3f3f;
  border-radius:16px;
  background:#131313;
  box-shadow:0 24px 80px #000b;
  animation:fade-in .16s ease both
}
.confirm-dialog h2 {
  margin:0;
  font-size:22px;
  letter-spacing:-.04em
}
.confirm-dialog>p:not(.eyebrow) {
  margin:12px 0 22px;
  color:#959595;
  font-size:12px;
  line-height:1.8
}
.dialog-actions {
  display:flex;
  justify-content:flex-end;
  gap:8px
}
.boot-screen {
  display:flex;
  min-height:100vh;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:16px;
  color:#8f8f8f
}
.boot-mark {
  display:grid;
  place-items:center;
  width:55px;
  height:55px;
  border:1px solid #454545;
  border-radius:15px;
  color:var(--accent);
  font-size:24px;
  font-weight:700
}
.boot-screen p {
  margin:4px 0 0;
  font-size:12px
}
.boot-screen small {
  font:9px var(--mono);
  letter-spacing:.1em;
  color:#646464
}
.login-wrap {
  position:relative;
  isolation:isolate;
  display:grid;
  place-items:center;
  min-height:100vh;
  padding:36px 18px;
  overflow:hidden
}
.login-orbit {
  position:absolute;
  border:1px solid #303030;
  border-radius:50%;
  z-index:-1;
  pointer-events:none
}
.orbit-one {
  width:min(900px,115vw);
  aspect-ratio:1;
  transform:translate(28%,6%);
  box-shadow:inset 0 0 120px #1e1e1e
}
.orbit-two {
  width:min(600px,85vw);
  aspect-ratio:1;
  transform:translate(28%,6%);
  border-style:dashed;
  opacity:.65
}
.login-card {
  width:min(510px,100%);
  padding:34px;
  border:1px solid #313131;
  border-radius:21px;
  background:linear-gradient(145deg,#161616f5,#0d0d0df5);
  box-shadow:0 28px 90px #0009
}
.login-brand {
  padding:0 0 31px;
  border-bottom:1px solid var(--line)
}
.login-kicker {
  display:flex;
  align-items:center;
  gap:10px;
  margin:29px 0 14px;
  color:#969696;
  font:9px var(--mono);
  letter-spacing:.12em
}
.login-kicker .signal-dot {
  width:6px;
  height:6px
}
.login-card h1 {
  margin:0;
  font-size:clamp(37px,9vw,52px);
  line-height:1.03;
  letter-spacing:-.065em;
  font-weight:650
}
.login-card h1 span {
  color:#878787;
  font-weight:450
}
.login-copy {
  margin:18px 0 25px;
  max-width:400px;
  color:#a0a0a0;
  font-size:13px;
  line-height:1.85
}
.login-button {
  width:100%;
  min-height:48px;
  font-size:12px
}
.inline-notice {
  padding:10px 12px;
  margin:0 0 16px;
  border:1px solid #444444;
  border-radius:8px;
  background:#1f1f1f;
  color:#d3d3d3;
  font-size:11px
}
.login-separator {
  display:flex;
  align-items:center;
  gap:10px;
  margin:24px 0 17px;
  color:#6e6e6e;
  font:8px var(--mono);
  letter-spacing:.09em;
  white-space:nowrap
}
.login-separator span {
  height:1px;
  background:var(--line);
  flex:1
}
.login-assurances {
  display:grid;
  gap:11px
}
.login-assurances>span {
  display:flex;
  align-items:center;
  gap:10px;
  color:#909090;
  font-size:10px
}
.login-assurances b {
  display:grid;
  place-items:center;
  width:23px;
  height:23px;
  border:1px solid #363636;
  border-radius:7px;
  color:var(--accent);
  font:9px var(--mono)
}
.login-foot {
  display:flex;
  justify-content:space-between;
  gap:10px;
  margin-top:28px;
  padding-top:17px;
  border-top:1px solid var(--line);
  font:8px var(--mono);
  letter-spacing:.06em;
  color:#696969
}
@keyframes fade-in {
  from {
    opacity:0;
    transform:translateY(5px)
  }
  to {
    opacity:1;
    transform:translateY(0)
  }
}
@keyframes toast-in {
  from {
    opacity:0;
    transform:translateY(5px)
  }
  to {
    opacity:1;
    transform:translateY(0)
  }
}
@keyframes rotate {
  to {
    transform:rotate(360deg)
  }
}
@keyframes orbit {
  to {
    transform:rotate(360deg)
  }
}
@media(max-width:1250px) {
  .main {
    padding:0 25px 22px
  }
  .sidebar {
    width:225px
  }
  .main {
    margin-left:225px
  }
  .metric {
    padding:15px
  }
  .metric-value {
    font-size:28px
  }
  .account-copy {
    max-width:105px
  }
  .topbar-right {
    gap:9px
  }
}
@media(max-width:960px) {
  .metric-grid {
    grid-template-columns:repeat(2,minmax(0,1fr))
  }
  .content-grid {
    grid-template-columns:minmax(0,1fr)
  }
  .panel-large {
    grid-row:auto
  }
  .page-heading {
    align-items:flex-start;
    flex-direction:column
  }
  .heading-actions {
    width:100%;
    flex-wrap:wrap
  }
  .topbar {
    height:75px
  }
  .account-copy {
    display:none
  }
}
@media(max-width:760px) {
  .sidebar {
    width:min(290px,84vw);
    transform:translateX(-105%);
    transition:transform .24s ease;
    box-shadow:none
  }
  .sidebar.mobile-open {
    transform:translateX(0);
    box-shadow:20px 0 80px #0009
  }
  .mobile-scrim {
    position:fixed;
    inset:0;
    z-index:25;
    display:block;
    width:100%;
    height:100%;
    border:0;
    background:#0009;
    opacity:0;
    pointer-events:none;
    transition:opacity .2s
  }
  .mobile-scrim.active {
    opacity:1;
    pointer-events:auto
  }
  .main {
    margin-left:0;
    padding:0 18px 20px
  }
  .mobile-menu {
    display:grid
  }
  .topbar {
    gap:12px
  }
  .breadcrumb {
    margin-right:auto
  }
  .topbar-right {
    gap:7px
  }
  .guild-control {
    padding:7px 8px;
    max-width:190px
  }
  .guild-control>span {
    display:none
  }
  .guild-control select {
    max-width:150px
  }
  .page {
    padding-top:25px
  }
  .page-heading h1 {
    font-size:34px
  }
  .lede {
    font-size:12px
  }
  .status-strip {
    align-items:flex-start;
    flex-wrap:wrap
  }
  .status-strip time {
    width:100%;
    margin-left:16px
  }
  .command-toolbar {
    grid-template-columns:1fr 1fr
  }
  .search-field {
    grid-column:1/-1
  }
  .command-row {
    grid-template-columns:minmax(0,1fr) 40px;
    gap:10px;
    padding:15px
  }
  .command-state {
    grid-column:1;
    grid-row:2;
    justify-self:start
  }
  .switch {
    grid-column:2;
    grid-row:1;
    justify-self:end
  }
  .command-tags {
    gap:5px
  }
  .metric {
    min-height:132px
  }
  .page-footer {
    font-size:8px
  }
  .account {
    display:none
  }
}
@media(max-width:480px) {
  .main {
    padding-right:13px;
    padding-left:13px
  }
  .topbar {
    height:69px
  }
  .breadcrumb>span:first-child,.breadcrumb-divider {
    display:none
  }
  .breadcrumb strong {
    font-size:11px
  }
  .icon-button {
    width:33px;
    height:33px
  }
  .guild-control {
    max-width:150px
  }
  .guild-control select {
    max-width:125px;
    font-size:10px
  }
  .metric-grid {
    gap:8px
  }
  .metric {
    padding:13px 12px;
    min-height:128px
  }
  .metric-label {
    font-size:8px
  }
  .metric-value {
    font-size:26px;
    margin-top:16px
  }
  .metric p {
    font-size:9px
  }
  .page-heading h1 {
    font-size:31px
  }
  .heading-actions .button {
    flex:1;
    padding:0 9px
  }
  .status-strip {
    font-size:10px
  }
  .panel {
    padding:15px
  }
  .runtime-body {
    align-items:flex-start;
    gap:12px
  }
  .runtime-mark {
    width:48px;
    height:48px;
    border-radius:13px;
    font-size:23px
  }
  .runtime-data {
    grid-template-columns:1fr;
    gap:13px
  }
  .runtime-data>div {
    flex-direction:row;
    align-items:baseline;
    justify-content:space-between
  }
  .activity-row {
    grid-template-columns:12px minmax(0,1fr);
    gap:7px
  }
  .activity-time {
    grid-column:2;
    padding:0
  }
  .command-toolbar {
    grid-template-columns:1fr
  }
  .search-field {
    grid-column:auto
  }
  .filter-control {
    min-height:40px
  }
  .command-summary {
    align-items:flex-start;
    flex-direction:column;
    gap:5px
  }
  .command-row {
    padding:14px 12px
  }
  .extension-row {
    align-items:flex-start;
    flex-direction:column;
    gap:8px
  }
  .login-card {
    padding:24px 20px
  }
  .login-foot {
    font-size:7px
  }
  .confirm-dialog {
    padding:20px
  }
  .dialog-actions .button {
    flex:1
  }
}
@media(prefers-reduced-motion:reduce) {
  *,*::before,*::after {
    scroll-behavior:auto!important;
    animation-duration:.01ms!important;
    animation-iteration-count:1!important;
    transition-duration:.01ms!important
  }
}
/* Command references: make each registered slash command a real, usable destination. */
.command-name-link {
  display:inline-flex;
  align-items:center;
  gap:7px;
  max-width:100%;
  color:#e9e9e9;
  text-decoration:none;
  transition:color .16s ease
}
.command-name-link:hover {
  color:var(--accent)
}
.command-name-link:focus-visible {
  outline:2px solid var(--accent);
  outline-offset:4px;
  border-radius:4px
}
.command-link-glyph {
  color:var(--accent);
  font:10px var(--mono);
  opacity:.8
}
.command-actions {
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:8px;
  margin-top:12px
}
.command-copy,.command-guide {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  min-height:29px;
  padding:6px 9px;
  border:1px solid #353535;
  border-radius:7px;
  background:#181818;
  color:#c0c0c0;
  font:9px var(--mono);
  letter-spacing:.025em;
  cursor:pointer;
  transition:background .16s ease,border-color .16s ease,color .16s ease
}
.command-guide {
  background:transparent;
  color:#a8a8a8;
  text-decoration:none
}
.command-copy:hover,.command-guide:hover {
  border-color:#6d6d6d;
  background:#252525;
  color:var(--accent)
}
.command-copy:focus-visible,.command-guide:focus-visible {
  outline:2px solid var(--accent);
  outline-offset:3px
}
@media(max-width:760px) {
  .command-actions {
    gap:7px;
    margin-top:10px
  }
  .command-copy,.command-guide {
    min-height:31px;
    padding:7px 8px
  }
}
@media(max-width:480px) {
  .command-actions {
    gap:6px
  }
  .command-copy,.command-guide {
    font-size:8px;
    padding:7px 7px
  }
}
/* Monochrome redesign: precise contrast, restrained motion, and braille as a live signal motif. */
html {
  background:#000;
  color-scheme:dark
}
body {
  background:radial-gradient(ellipse at 72% -18%,#171717 0%,transparent 45%),#000;
  color:#f5f5f5
}
.sidebar {
  background:rgba(0,0,0,.96);
  border-right-color:#262626
}
.brand-mark {
  border-color:#666;
  background:linear-gradient(145deg,#262626,#070707);
  color:#fff;
  box-shadow:inset 0 0 0 1px #ffffff08
}
.nav-item:hover,.nav-item.active {
  background:#151515;
  border-color:#333;
  color:#fff
}
.nav-item.active .nav-glyph,.nav-item:hover .nav-glyph {
  color:#fff
}
.sidebar-system,.guild-control,.icon-button,.panel,.metric,.command-row,.confirm-dialog,.login-card {
  background-color:#090909;
  border-color:#292929
}
.button {
  background:#111;
  border-color:#383838;
  color:#e5e5e5
}
.button:hover:not(:disabled) {
  background:#242424;
  border-color:#666;
  color:#fff
}
.button.primary {
  background:#fff;
  border-color:#fff;
  color:#000
}
.button.primary:hover:not(:disabled) {
  background:#dcdcdc;
  border-color:#dcdcdc;
  color:#000
}
.status-strip {
  background:linear-gradient(90deg,#171717,#080808);
  border-color:#393939;
  color:#c4c4c4
}
.status-strip>span:nth-child(2),.breadcrumb strong,.metric-value,.command-name-link {
  color:#f5f5f5
}
.strip-signal,.signal-dot.online {
  background:#fff;
  box-shadow:0 0 0 4px #ffffff12,0 0 16px #ffffff22
}
.metric {
  background:linear-gradient(145deg,#151515,#080808)
}
.panel {
  background:linear-gradient(145deg,#101010,#080808)
}
.panel:hover,.metric:hover {
  border-color:#484848
}
.runtime-mark {
  border-color:#424242;
  background:radial-gradient(circle at 50% 50%,#202020,#050505)
}
.runtime-mark.is-online {
  border-color:#777;
  box-shadow:0 0 0 1px #ffffff0a,0 0 30px #ffffff0b
}
.distribution-track-fill {
  fill:#fff
}
.switch.checked {
  background:#fafafa;
  border-color:#fff
}
.switch.checked span {
  background:#050505
}
.status-pill.is-good {
  color:#fff;
  border-color:#555;
  background:#171717
}
.status-pill.is-bad {
  color:#c8c8c8;
  border-color:#4a4a4a;
  background:#171717
}
.command-row:hover {
  border-color:#505050;
  background:#111
}
.command-copy,.command-guide {
  border-color:#363636;
  background:#0e0e0e;
  color:#d4d4d4
}
.command-copy:hover,.command-guide:hover {
  border-color:#777;
  background:#1a1a1a;
  color:#fff
}
.tag-protected {
  border-color:#5b5b5b;
  color:#fff;
  background:#1e1e1e
}
.topbar {
  border-bottom-color:#1b1b1b
}
.guild-control:focus-within,.filter-control:focus-within,.search-field:focus-within {
  border-color:#888;
  box-shadow:0 0 0 3px #ffffff0c
}
:where(button,a,input,select,textarea,[tabindex]):focus-visible {
  outline:2px solid #fff;
  outline-offset:3px
}
.page {
  animation:page-rise .44s cubic-bezier(.2,.7,.2,1) both
}
.panel,.metric,.command-row,.extension-row,.activity-row {
  transition:border-color .22s ease,background-color .22s ease,transform .22s ease
}
.command-row:hover {
  transform:translateY(-1px)
}
.button:active:not(:disabled),.icon-button:active:not(:disabled) {
  transform:translateY(1px)
}
.login-wrap {
  background:radial-gradient(ellipse at 76% 25%,#131313 0%,transparent 43%),#000
}
.login-orbit {
  border-color:#292929
}
.login-card {
  background:linear-gradient(145deg,#111,#050505);
  border-color:#393939;
  box-shadow:0 28px 100px #000
}
.login-card h1 span {
  color:#a9a9a9
}
.login-kicker,.login-copy,.login-assurances>span {
  color:#b0b0b0
}
.login-separator,.login-foot,.boot-screen small {
  color:#777
}
.braille-band {
  position:relative;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  min-height:31px;
  margin:0 0 3px;
  overflow:hidden;
  border-bottom:1px solid #171717;
  color:#878787;
  font:9px var(--mono);
  letter-spacing:.16em
}
.braille-band::before {
  position:absolute;
  inset:0;
  content:"";
  pointer-events:none;
  background-image:radial-gradient(#888 .7px,transparent .85px);
  background-size:8px 8px;
  opacity:.09;
  mask-image:linear-gradient(90deg,transparent,#000 14%,#000 86%,transparent)
}
.braille-track {
  position:relative;
  display:block;
  max-width:37%;
  overflow:hidden;
  white-space:nowrap;
  font-family:system-ui,sans-serif;
  font-size:15px;
  letter-spacing:.16em;
  line-height:1.1;
  opacity:.7
}
.braille-track-a {
  animation:braille-drift 19s linear infinite
}
.braille-track-b {
  animation:braille-drift-reverse 24s linear infinite;
  opacity:.4
}
.braille-band-label {
  position:relative;
  flex:none;
  color:#a9a9a9;
  font-size:8px;
  letter-spacing:.17em
}
.braille-mini {
  margin-left:auto;
  font:14px system-ui,sans-serif;
  letter-spacing:.12em;
  color:#fff;
  animation:braille-flicker 4.6s steps(1,end) infinite
}
.runtime-mark span {
  display:inline-block;
  font-family:system-ui,sans-serif;
  animation:braille-pulse 6.2s steps(1,end) infinite
}
.runtime-mark.is-online span {
  animation-duration:4.1s
}
.runtime-mark i {
  background:#fff
}
.spinner {
  border-color:#3d3d3d;
  border-top-color:#fff
}
.toast {
  background:#101010;
  border-color:#414141
}
.toast.error {
  border-color:#626262;
  background:#171717;
  color:#f0f0f0
}
.confirm-dialog {
  box-shadow:0 24px 90px #000
}
@keyframes page-rise {
  from {
    opacity:0;
    transform:translateY(9px)
  }
  to {
    opacity:1;
    transform:translateY(0)
  }
}
@keyframes braille-drift {
  0% {
    transform:translateX(0);
    opacity:.42
  }
  50% {
    opacity:.78
  }
  100% {
    transform:translateX(9px);
    opacity:.42
  }
}
@keyframes braille-drift-reverse {
  0% {
    transform:translateX(4px);
    opacity:.25
  }
  50% {
    opacity:.58
  }
  100% {
    transform:translateX(-8px);
    opacity:.25
  }
}
@keyframes braille-flicker {
  0%,16%,18%,64%,68%,100% {
    opacity:.45
  }
  17%,65% {
    opacity:1
  }
  34%,53% {
    opacity:.72
  }
}
@keyframes braille-pulse {
  0%,14%,25%,43%,71%,100% {
    opacity:.72;
    transform:translateY(0)
  }
  16%,45%,73% {
    opacity:1;
    transform:translateY(-1px)
  }
  18%,48%,76% {
    opacity:.5;
    transform:translateY(0)
  }
}
@media(max-width:760px) {
  .braille-track {
    max-width:28%;
    font-size:13px
  }
  .braille-band-label {
    font-size:7px
  }
  .braille-band {
    gap:8px
  }
}
@media(prefers-reduced-motion:reduce) {
  .braille-track,.braille-mini,.runtime-mark span,.page {
    animation:none!important;
    transform:none!important
  }
}
/* Knowledge Atlas: a bounded, guild-authorized one-hop graph. */
.atlas-search {
  display:grid;
  grid-template-columns:minmax(220px,1fr) minmax(150px,210px) auto;
  align-items:end;
  gap:12px
}
.atlas-search-title {
  display:grid;
  gap:7px;
  min-width:0
}
.atlas-search-title>span,.atlas-category>span {
  color:#8a8a8a;
  font:9px var(--mono);
  letter-spacing:.1em
}
.atlas-search-title input {
  width:100%;
  min-height:42px;
  padding:0 12px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#101010;
  color:var(--text);
  font-size:12px
}
.atlas-category {
  min-height:42px;
  padding:0 11px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#101010;
  display:grid;
  align-content:center;
  gap:2px
}
.atlas-category select {
  width:100%;
  max-width:none;
  font-size:12px
}
.atlas-error {
  margin:12px 0 0;
  color:#d1d1d1;
  font-size:11px
}
.atlas-explainer {
  margin:-7px 0 15px;
  color:#8e8e8e;
  font-size:11px;
  line-height:1.7
}
.atlas-graph {
  position:relative;
  isolation:isolate;
  width:100%;
  height:clamp(360px,48vw,560px);
  overflow:hidden;
  border:1px solid #292929;
  border-radius:13px;
  background:radial-gradient(circle at center,#1a1a1a 0,#0b0b0b 48%,#050505 100%);
  background-image:radial-gradient(#525252 .7px,transparent .9px),radial-gradient(ellipse at center,#1a1a1a 0,#0b0b0b 54%,#050505 100%);
  background-size:13px 13px,auto
}
.atlas-edges {
  position:absolute;
  inset:0;
  width:100%;
  height:100%;
  z-index:0;
  overflow:visible
}
.atlas-edge {
  stroke:#6f6f6f;
  stroke-width:.35;
  stroke-dasharray:1.5 1.2;
  opacity:.7
}
.atlas-edge.recommendation {
  stroke-dasharray:2.5 1.5;
  opacity:.55
}
.atlas-edge.community {
  stroke:#fff;
  stroke-width:.45;
  opacity:.9
}
.atlas-root-node,.atlas-node {
  position:absolute;
  z-index:1;
  transform:translate(-50%,-50%);
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:4px;
  width:clamp(112px,17%,160px);
  min-height:82px;
  padding:10px;
  border:1px solid #777;
  border-radius:12px;
  background:linear-gradient(145deg,#252525,#101010);
  color:#f4f4f4;
  text-align:center;
  box-shadow:0 12px 35px #000b;
  overflow-wrap:anywhere
}
.atlas-root-node {
  left:50%;
  top:50%;
  width:clamp(130px,21%,190px);
  min-height:105px;
  border-color:#eee;
  background:linear-gradient(145deg,#3a3a3a,#171717);
  box-shadow:0 0 0 5px #ffffff0c,0 16px 42px #000c
}
.atlas-root-node strong,.atlas-node strong {
  font-size:11px;
  line-height:1.3;
  font-weight:650
}
.atlas-root-node a {
  color:#c7c7c7;
  font:9px var(--mono)
}
.atlas-node {
  cursor:pointer;
  transition:border-color .16s ease,background .16s ease,box-shadow .16s ease
}
.atlas-node:hover:not(:disabled) {
  border-color:#fff;
  background:#262626;
  box-shadow:0 0 0 3px #ffffff12,0 12px 35px #000b
}
.atlas-node.provider {
  border-color:#696969
}
.atlas-node.recommendation {
  border-style:dashed;
  border-color:#686868
}
.atlas-node.community {
  border-color:#fff;
  box-shadow:0 0 0 2px #ffffff16,0 12px 35px #000b
}
.atlas-node>span,.atlas-node-category {
  color:#aaa;
  font:8px var(--mono);
  letter-spacing:.07em;
  text-transform:uppercase
}
.atlas-legend {
  display:flex;
  flex-wrap:wrap;
  gap:16px;
  margin-top:15px;
  color:#999;
  font:9px var(--mono)
}
.atlas-legend span {
  display:inline-flex;
  align-items:center;
  gap:7px
}
.atlas-legend i {
  width:8px;
  height:8px;
  border:1px solid #999;
  border-radius:50%;
  background:#555
}
.atlas-legend i.recommendation {
  border-style:dashed;
  background:transparent
}
.atlas-legend i.community {
  border-color:#fff;
  background:#fff
}
.atlas-connections {
  display:grid
}
.atlas-connection {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
  padding:14px 0;
  border-top:1px solid #242424
}
.atlas-connection:first-child {
  border-top:0;
  padding-top:0
}
.atlas-connection-main {
  display:grid;
  gap:4px;
  min-width:0
}
.atlas-connection-main strong {
  font-size:12px;
  overflow-wrap:anywhere
}
.atlas-connection-main small {
  color:#888;
  font-size:10px
}
.atlas-source {
  width:max-content;
  padding:3px 6px;
  border:1px solid #555;
  border-radius:5px;
  color:#c8c8c8;
  font:8px var(--mono);
  text-transform:uppercase
}
.atlas-source.recommendation {
  border-style:dashed
}
.atlas-source.community {
  border-color:#fff;
  color:#fff
}
.atlas-connection-actions {
  display:flex;
  align-items:center;
  justify-content:flex-end;
  flex-wrap:wrap;
  gap:10px;
  flex:none
}
.atlas-connection-actions .button {
  min-height:32px
}
.atlas-provider-link {
  color:#aaa;
  font:9px var(--mono);
  white-space:nowrap
}
.atlas-provider-link:hover {
  color:#fff
}
@media(max-width:760px) {
  .atlas-search {
    grid-template-columns:1fr 1fr
  }
  .atlas-search-title {
    grid-column:1/-1
  }
  .atlas-search>.button {
    grid-column:1/-1;
    width:100%
  }
  .atlas-graph {
    height:440px
  }
  .atlas-node {
    width:108px;
    min-height:68px;
    padding:7px
  }
  .atlas-node strong {
    font-size:9px
  }
  .atlas-root-node {
    width:126px;
    min-height:88px
  }
  .atlas-connection {
    align-items:flex-start;
    flex-direction:column
  }
  .atlas-connection-actions {
    justify-content:flex-start
  }
}
@media(max-width:420px) {
  .atlas-graph {
    height:390px
  }
  .atlas-node {
    width:92px;
    min-height:62px
  }
  .atlas-root-node {
    width:112px;
    min-height:82px
  }
  .atlas-node strong {
    font-size:8px
  }
}
.atlas-tools {
  display:flex;
  align-items:end;
  flex-wrap:wrap;
  gap:10px;
  margin:0 0 14px
}
.atlas-tools .filter-control {
  min-width:150px;
  min-height:41px;
  padding:0 10px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#101010;
  display:grid;
  align-content:center;
  gap:2px
}
.atlas-tools .filter-control select {
  width:100%;
  max-width:none;
  font-size:11px
}
.atlas-zoom {
  display:flex;
  align-items:center;
  gap:6px;
  margin-left:auto
}
.atlas-zoom>span {
  margin-right:4px;
  color:#8a8a8a;
  font:9px var(--mono);
  letter-spacing:.1em
}
.atlas-zoom>strong {
  min-width:38px;
  text-align:center;
  color:#bbb;
  font:10px var(--mono)
}
.atlas-zoom .button {
  min-height:33px;
  min-width:33px;
  padding:0 9px
}
.atlas-graph-content {
  position:absolute;
  inset:0;
  transform-origin:center center;
  transition:transform .18s ease
}
@media(max-width:760px) {
  .atlas-tools {
    align-items:stretch
  }
  .atlas-tools .filter-control {
    flex:1;
    min-width:135px
  }
  .atlas-zoom {
    width:100%;
    margin-left:0;
    justify-content:flex-end
  }
}
@media(prefers-reduced-motion:reduce) {
  .atlas-graph-content {
    transition:none
  }
}
/* Interaction and accessibility floor for the Nothing OS control surface. */
:where(button,a,input,select,textarea,[role="button"],[role="switch"]) {
  -webkit-tap-highlight-color:transparent
}
.button {
  min-height:40px
}
.icon-button {
  width:40px;
  height:40px
}
.nav-item,.signout {
  min-height:44px
}
.filter-control select,.guild-control select {
  min-height:40px
}
.command-copy,.command-guide {
  min-height:40px;
  display:inline-flex;
  align-items:center
}
.eyebrow,.metric-label,.sidebar-system small,.account-copy small,.filter-control>span,.guild-control>span,.panel-index,.activity-time,.atlas-legend,.atlas-source,.atlas-provider-link,.page-footer {
  font-size:11px
}
.lede,.command-description,.footnote,.atlas-explainer,.empty-state,.login-copy,.login-assurances>span {
  font-size:12px
}
:where(button,a,input,select,textarea,[tabindex]):focus-visible {
  outline:2px solid #fff;
  outline-offset:3px
}
:where(button,a,input,select,textarea,[role="button"],[role="switch"]) {
  scroll-margin:12px
}
@media(prefers-reduced-motion:reduce) {
  *,*::before,*::after {
    animation-duration:.01ms!important;
    animation-iteration-count:1!important;
    scroll-behavior:auto!important;
    transition-duration:.01ms!important
  }
}
@media(max-width:760px) {
  .main {
    padding-left:18px;
    padding-right:18px
  }
  .page-heading {
    align-items:flex-start;
    flex-direction:column;
    gap:14px
  }
  .heading-actions {
    flex-wrap:wrap
  }
  .atlas-graph {
    height:440px
  }
  .atlas-root-node {
    width:120px;
    min-height:88px;
    padding:8px
  }
  .atlas-node {
    width:clamp(104px,27%,140px);
    min-height:72px;
    padding:8px
  }
}
/* Keep important metadata legible across dense control panels. */
.metric p,.text-button,.distribution-meta,.mono,.activity-copy small,.command-summary,td small, .status-strip,.login-foot,.command-copy,.command-guide,.atlas-connection-main small, .atlas-node strong,.atlas-node>span,.atlas-root-node a,.guild-control select {
  font-size:11px
}
/* Knowledge Atlas — canonical identity, provenance filters and bounded exports */
.atlas-path-tools,.atlas-export-tools,.atlas-clusters {
  display:flex;
  align-items:end;
  gap:10px;
  flex-wrap:wrap;
  margin-top:12px
}
.atlas-export-tools {
  align-items:center;
  padding-top:10px;
  border-top:1px solid #303030
}
.atlas-export-tools>span,.atlas-clusters>span {
  font-size:10px;
  letter-spacing:.14em;
  color:#999
}
.atlas-path-tools .filter-control {
  min-width:min(280px,100%)
}
.atlas-evidence-filter {
  min-width:min(260px,100%)
}
.atlas-clusters {
  align-items:center
}
.atlas-clusters button {
  display:flex;
  gap:8px;
  align-items:center;
  background:#111;
  border:1px solid #383838;
  color:#ccc;
  border-radius:6px;
  padding:7px 10px;
  font:inherit;
  font-size:11px;
  cursor:pointer
}
.atlas-clusters button strong {
  color:#fff
}
.atlas-path-summary {
  padding:10px 12px;
  border-left:2px solid #fff;
  background:#101010;
  color:#ddd;
  font-size:12px;
  line-height:1.6
}
.atlas-connection small {
  display:block;
  color:#999;
  margin-top:4px
}
.atlas-path-tools .filter-control,.atlas-tools .filter-control {
  min-width:170px
}
.atlas-provider-id-filter input {
  max-width:190px
}
.command-savebar {
  position:sticky;
  bottom:12px;
  z-index:45;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
  margin:18px 0 0;
  padding:12px 14px;
  border:1px solid #343434;
  border-radius:12px;
  background:rgba(17,17,17,.96);
  box-shadow:0 14px 38px #0009;
  backdrop-filter:blur(16px)
}
.command-savebar>span {
  display:grid;
  gap:3px;
  min-width:0
}
.command-savebar strong {
  font-size:11px;
  font-weight:650;
  color:#f1f1f1
}
.command-savebar small {
  font-size:10px;
  color:#929292
}
.command-savebar>div,.access-footer>div {
  display:flex;
  align-items:center;
  gap:8px
}
.command-reset,.command-save {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  min-height:36px;
  padding:0 13px;
  border:1px solid transparent;
  border-radius:8px;
  font-size:11px;
  font-weight:650;
  cursor:pointer;
  transition:background .16s,border-color .16s,transform .16s
}
.command-reset {
  background:#4e5054;
  border-color:#5e6065;
  color:#f0f0f0
}
.command-reset:hover:not(:disabled) {
  background:#61646a;
  border-color:#777a80
}
.command-save {
  background:#248046;
  border-color:#2b9653;
  color:#fff
}
.command-save:hover:not(:disabled) {
  background:#2b9653;
  border-color:#35a962
}
.command-reset:disabled,.command-save:disabled {
  opacity:.45;
  cursor:not-allowed
}
.command-access-open {
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:5px 8px;
  border:1px solid #333;
  border-radius:7px;
  background:#111;
  color:#aaa;
  font-size:10px;
  cursor:pointer
}
.command-access-open:hover:not(:disabled) {
  border-color:#5d5d5d;
  color:#f3f3f3;
  background:#1b1b1b
}
.access-overlay {
  position:fixed;
  inset:0;
  z-index:95;
  display:grid;
  place-items:center;
  padding:20px;
  background:#000c;
  backdrop-filter:blur(9px)
}
.access-dialog {
  width:min(760px,100%);
  max-height:min(760px,calc(100vh - 40px));
  overflow:auto;
  padding:23px;
  border:1px solid #393939;
  border-radius:15px;
  background:#101010;
  box-shadow:0 24px 90px #000d
}
.access-heading {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:16px;
  margin-bottom:22px
}
.access-heading .eyebrow {
  margin-bottom:7px
}
.access-heading h2 {
  margin:0;
  font-size:21px;
  letter-spacing:-.04em
}
.access-heading h2 span {
  color:#aaa;
  font-weight:450
}
.access-heading p:not(.eyebrow) {
  margin:8px 0 0;
  color:#919191;
  font-size:11px;
  line-height:1.7
}
.access-close {
  display:grid;
  place-items:center;
  width:34px;
  height:34px;
  flex:none;
  border:1px solid #333;
  border-radius:8px;
  background:#181818;
  color:#aaa;
  cursor:pointer
}
.access-close:hover {
  color:#fff;
  border-color:#555
}
.access-grid {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:15px
}
.access-field {
  display:flex;
  flex-direction:column;
  gap:9px;
  min-width:0
}
.access-field>label {
  color:#999;
  font:9px var(--mono);
  letter-spacing:.1em
}
.access-field>select {
  width:100%;
  max-width:none;
  min-height:38px;
  padding:7px 9px;
  border:1px solid #333;
  border-radius:8px;
  background:#141414;
  color:#eee;
  font-size:11px
}
.access-field>select[multiple] {
  height:176px;
  overflow:auto;
  padding:5px
}
.access-field>select[multiple] option {
  padding:6px;
  border-radius:4px
}
.access-field>select[multiple] option:checked {
  background:#393939 linear-gradient(0deg,#393939,#393939);
  color:#fff
}
.access-field>small {
  color:#777;
  font-size:10px;
  line-height:1.6
}
.access-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-top:22px;
  padding-top:15px;
  border-top:1px solid #292929
}
.access-footer>span {
  color:#929292;
  font-size:10px
}
.access-load-error {
  padding:15px;
  border:1px solid #392b2b;
  border-radius:9px;
  color:#bbb;
  font-size:12px
}
.access-load-error p {
  margin:0 0 12px
}
.overview-scene {
  position:relative;
  height:0;
  z-index:0;
  pointer-events:none
}
.overview-scene>div {
  position:absolute;
  right:clamp(12px,9vw,130px);
  top:-118px;
  width:136px;
  height:132px;
  opacity:.58
}
@media(max-width:800px) {
  .overview-scene {
    display:none
  }
  .access-dialog {
    padding:17px
  }
  .access-grid {
    grid-template-columns:1fr
  }
}
@media(max-width:480px) {
  .command-savebar {
    align-items:flex-start;
    flex-direction:column
  }
  .command-savebar>div {
    width:100%
  }
  .command-savebar button {
    flex:1
  }
  .access-footer {
    align-items:flex-start;
    flex-direction:column
  }
  .access-footer>div {
    width:100%
  }
  .access-footer button {
    flex:1
  }
}
.server-picker-trigger {
  display:flex;
  align-items:center;
  gap:8px;
  min-width:150px;
  max-width:270px;
  min-height:34px;
  padding:0 10px;
  border:1px solid #303030;
  border-radius:8px;
  background:#121212;
  color:#e9e9e9;
  text-align:left;
  cursor:pointer
}
.server-picker-trigger strong {
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  font-size:11px;
  font-weight:600
}
.server-picker-trigger>svg {
  flex:none;
  color:#aaa
}
.server-picker-caret {
  margin-left:auto;
  color:#777;
  font-size:15px
}
.server-state-mark {
  display:inline-block;
  width:7px;
  height:7px;
  flex:none;
  border-radius:50%;
  background:#39ca76;
  box-shadow:0 0 0 3px #39ca7620
}
.server-picker-trigger .server-state-mark {
  margin-left:2px
}
.server-picker-dialog {
  width:min(590px,100%)
}
.server-picker-list {
  display:grid;
  gap:7px;
  max-height:min(54vh,500px);
  overflow-y:auto;
  padding-right:2px
}
.server-picker-option {
  display:flex;
  align-items:center;
  gap:12px;
  width:100%;
  min-height:62px;
  padding:10px 12px;
  border:1px solid #303030;
  border-radius:9px;
  background:#161616;
  color:#eee;
  text-align:left;
  cursor:pointer
}
.server-picker-option:hover:not(.is-uninstalled) {
  border-color:#666;
  background:#1d1d1d
}
.server-picker-icon {
  display:grid;
  place-items:center;
  width:34px;
  height:34px;
  flex:none;
  border:1px solid #333;
  border-radius:8px;
  color:#bdbdbd
}
.server-picker-name {
  display:grid;
  gap:4px;
  min-width:0;
  flex:1
}
.server-picker-name strong {
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  font-size:12px;
  font-weight:600
}
.server-picker-name small {
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  color:#777;
  font-size:9px;
  font-family:var(--mono)
}
.server-picker-connected {
  display:flex;
  align-items:center;
  gap:7px;
  color:#8a8a8a;
  font-size:10px;
  white-space:nowrap
}
.server-picker-option.is-uninstalled {
  background:#111;
  color:#777;
  border-color:#292929;
  cursor:default
}
.server-picker-option.is-uninstalled .server-picker-icon {
  color:#666;
  border-color:#292929
}
.server-picker-option.is-uninstalled .server-picker-name strong {
  color:#898989
}
.server-invite-link {
  display:inline-flex;
  align-items:center;
  gap:6px;
  min-height:30px;
  padding:0 9px;
  border:1px solid #414141;
  border-radius:7px;
  color:#bcbcbc;
  text-decoration:none;
  font-size:10px;
  white-space:nowrap
}
.server-invite-link:hover {
  border-color:#777;
  color:#fff
}
.server-picker-missing {
  font-size:10px;
  color:#666
}
.server-empty-state {
  min-height:60vh;
  display:flex;
  align-items:flex-start;
  justify-content:center;
  flex-direction:column;
  gap:14px
}
.server-empty-mark {
  display:grid;
  place-items:center;
  width:52px;
  height:52px;
  border:1px solid #363636;
  border-radius:13px;
  background:#151515;
  color:#bdbdbd
}
.server-empty-state h1 {
  margin:0;
  font-size:clamp(32px,5vw,52px);
  line-height:1.02;
  letter-spacing:-.055em
}
.server-empty-state h1 span {
  color:#747474
}
.server-empty-state>p:not(.eyebrow) {
  max-width:440px;
  margin:0 0 4px;
  color:#888;
  font-size:12px;
  line-height:1.8
}
@media(max-width:680px) {
  .server-picker-trigger {
    min-width:0;
    max-width:175px
  }
  .server-picker-option {
    gap:8px;
    padding:9px
  }
  .server-picker-connected {
    font-size:0
  }
  .server-invite-link {
    padding:0 7px
  }
}
.policy-gate {
  min-height:100vh;
  display:grid;
  place-items:center;
  padding:26px;
  background:#090909;
  color:#eee
}
.policy-gate-card {
  width:min(590px,100%);
  padding:clamp(22px,5vw,42px);
  border:1px solid #303030;
  border-radius:17px;
  background:#101010;
  box-shadow:0 30px 100px #0009
}
.policy-brand {
  margin-bottom:34px
}
.policy-kicker {
  display:flex;
  align-items:center;
  gap:9px;
  margin-bottom:18px;
  color:#8d8d8d;
  font:9px var(--mono);
  letter-spacing:.1em
}
.policy-gate-card h1 {
  margin:0;
  font-size:clamp(37px,7vw,58px);
  line-height:.98;
  letter-spacing:-.06em
}
.policy-gate-card h1 span {
  color:#777
}
.policy-intro {
  max-width:440px;
  margin:17px 0 23px;
  color:#999;
  font-size:12px;
  line-height:1.8
}
.policy-links {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:8px;
  margin-bottom:19px
}
.policy-links a {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:6px;
  min-width:0;
  min-height:42px;
  padding:8px 9px;
  border:1px solid #353535;
  border-radius:8px;
  background:#171717;
  color:#d4d4d4;
  text-decoration:none;
  font-size:10px
}
.policy-links a:hover {
  border-color:#666;
  color:#fff
}
.policy-links a svg {
  flex:none;
  color:#858585
}
.policy-checklist {
  display:grid;
  gap:8px
}
.policy-check {
  display:flex;
  align-items:center;
  gap:11px;
  min-height:60px;
  padding:10px 12px;
  border:1px solid #303030;
  border-radius:9px;
  background:#151515;
  cursor:pointer
}
.policy-check input {
  position:absolute;
  width:1px;
  height:1px;
  opacity:0
}
.policy-checkmark {
  display:grid;
  place-items:center;
  width:19px;
  height:19px;
  flex:none;
  border:1px solid #555;
  border-radius:5px;
  color:transparent
}
.policy-check input:checked+.policy-checkmark {
  border-color:#299454;
  background:#248046;
  color:#fff
}
.policy-check input:focus-visible+.policy-checkmark {
  outline:2px solid #fff;
  outline-offset:3px
}
.policy-check-copy {
  display:grid;
  gap:5px;
  min-width:0
}
.policy-check-copy strong {
  color:#dedede;
  font-size:11px;
  font-weight:550
}
.policy-check-copy small {
  color:#757575;
  font:8px var(--mono);
  letter-spacing:.08em
}
.policy-accept {
  display:flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  width:100%;
  min-height:43px;
  margin-top:18px;
  border:1px solid #2b9653;
  border-radius:9px;
  background:#248046;
  color:#fff;
  font-size:12px;
  font-weight:650;
  cursor:pointer
}
.policy-accept:hover:not(:disabled) {
  background:#2b9653
}
.policy-accept:disabled {
  opacity:.38;
  cursor:not-allowed
}
.policy-note {
  margin:12px 0 0;
  color:#757575;
  font-size:10px;
  line-height:1.7;
  text-align:center
}
.policy-error {
  margin:10px 0 0;
  color:#e2a0a0;
  font-size:11px
}
.policy-unavailable {
  display:grid;
  gap:7px;
  padding:14px;
  border:1px solid #493939;
  border-radius:9px;
  background:#1a1313
}
.policy-unavailable strong {
  color:#eee;
  font-size:12px
}
.policy-unavailable span {
  color:#a8a8a8;
  font-size:11px;
  line-height:1.6
}
.policy-decline {
  display:block;
  margin:18px auto 0;
  padding:5px 8px;
  border:0;
  background:transparent;
  color:#8a8a8a;
  font-size:10px;
  cursor:pointer
}
.policy-decline:hover {
  color:#fff
}
.policy-foot {
  display:flex;
  justify-content:space-between;
  gap:12px;
  margin-top:24px;
  padding-top:13px;
  border-top:1px solid #292929;
  color:#656565;
  font:8px var(--mono);
  letter-spacing:.08em
}
@media(max-width:520px) {
  .policy-links {
    grid-template-columns:1fr
  }
  .policy-links a {
    min-height:38px
  }
  .policy-gate-card {
    padding:21px
  }
}
/* Shared SVG icon motion. Movement is hover/focus driven and reduced-motion safe. */
.icon-svg {
  display: inline-block;
  flex: none;
  overflow: visible;
  vertical-align: -0.16em;
  transform-origin: center;
  transition: transform 220ms cubic-bezier(.2,.8,.2,1), color 180ms ease;
}
.icon-svg .icon-glyph {
  transform-box: fill-box;
  transform-origin: center;
}
.icon-svg .icon-glyph > * {
  transform-box: fill-box;
  transform-origin: center;
}
button:hover .icon-svg.icon-animated,
a:hover .icon-svg.icon-animated,
button:focus-visible .icon-svg.icon-animated,
a:focus-visible .icon-svg.icon-animated {
  transform: translateY(-1px) scale(1.04);
}
button:active .icon-svg.icon-animated,
a:active .icon-svg.icon-animated {
  transform: scale(.94);
}
.icon-svg.icon-arrow-up-right .icon-glyph,
.icon-svg.icon-external-link .icon-glyph {
  transition: transform 220ms cubic-bezier(.2,.8,.2,1);
}
a:hover .icon-svg.icon-arrow-up-right .icon-glyph,
button:hover .icon-svg.icon-arrow-up-right .icon-glyph,
a:hover .icon-svg.icon-external-link .icon-glyph,
button:hover .icon-svg.icon-external-link .icon-glyph {
  transform: translate(1.5px,-1.5px);
}
button:hover .icon-svg.icon-refresh .icon-glyph,
a:hover .icon-svg.icon-refresh .icon-glyph,
button:focus-visible .icon-svg.icon-refresh .icon-glyph,
a:focus-visible .icon-svg.icon-refresh .icon-glyph,
button:hover .icon-svg.icon-retry .icon-glyph,
a:hover .icon-svg.icon-retry .icon-glyph {
  animation: icon-rotate 650ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-overview rect,
a:hover .icon-svg.icon-overview rect {
  animation: icon-tile-pop 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-overview rect:nth-child(2),
a:hover .icon-svg.icon-overview rect:nth-child(2) {
  animation-delay: 35ms;
}
button:hover .icon-svg.icon-overview rect:nth-child(3),
a:hover .icon-svg.icon-overview rect:nth-child(3) {
  animation-delay: 70ms;
}
button:hover .icon-svg.icon-overview rect:nth-child(4),
a:hover .icon-svg.icon-overview rect:nth-child(4) {
  animation-delay: 105ms;
}
button:hover .icon-svg.icon-commands path:first-child,
a:hover .icon-svg.icon-commands path:first-child {
  animation: icon-command-shift 380ms ease both;
}
button:hover .icon-svg.icon-commands path:nth-child(2),
a:hover .icon-svg.icon-commands path:nth-child(2) {
  animation: icon-command-shift 380ms 45ms ease both reverse;
}
button:hover .icon-svg.icon-atlas circle,
a:hover .icon-svg.icon-atlas circle {
  animation: icon-node-pop 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-atlas circle:nth-of-type(2),
a:hover .icon-svg.icon-atlas circle:nth-of-type(2) {
  animation-delay: 35ms;
}
button:hover .icon-svg.icon-atlas circle:nth-of-type(3),
a:hover .icon-svg.icon-atlas circle:nth-of-type(3) {
  animation-delay: 70ms;
}
button:hover .icon-svg.icon-atlas circle:nth-of-type(4),
a:hover .icon-svg.icon-atlas circle:nth-of-type(4) {
  animation-delay: 105ms;
}
button:hover .icon-svg.icon-atlas circle:nth-of-type(5),
a:hover .icon-svg.icon-atlas circle:nth-of-type(5) {
  animation-delay: 140ms;
}
button:hover .icon-svg.icon-extensions rect,
a:hover .icon-svg.icon-extensions rect {
  animation: icon-tile-pop 390ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-extensions rect:nth-child(2),
a:hover .icon-svg.icon-extensions rect:nth-child(2) {
  animation-delay: 40ms;
}
button:hover .icon-svg.icon-extensions rect:nth-child(3),
a:hover .icon-svg.icon-extensions rect:nth-child(3) {
  animation-delay: 80ms;
}
button:hover .icon-svg.icon-extensions path,
a:hover .icon-svg.icon-extensions path {
  animation: icon-node-pop 390ms 120ms ease both;
}
button:hover .icon-svg.icon-audit path,
a:hover .icon-svg.icon-audit path {
  animation: icon-audit-sweep 460ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-logs path,
a:hover .icon-svg.icon-logs path {
  animation: icon-row-slide 360ms ease both;
}
button:hover .icon-svg.icon-logs path:nth-child(2),
a:hover .icon-svg.icon-logs path:nth-child(2) {
  animation-delay: 45ms;
}
button:hover .icon-svg.icon-logs path:nth-child(3),
a:hover .icon-svg.icon-logs path:nth-child(3) {
  animation-delay: 90ms;
}
button:hover .icon-svg.icon-integrations circle,
a:hover .icon-svg.icon-integrations circle {
  animation: icon-node-pop 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-integrations circle:nth-of-type(2),
a:hover .icon-svg.icon-integrations circle:nth-of-type(2) {
  animation-delay: 65ms;
}
button:hover .icon-svg.icon-database ellipse,
a:hover .icon-svg.icon-database ellipse {
  animation: icon-database-pulse 520ms ease both;
}
button:hover .icon-svg.icon-menu .icon-glyph,
a:hover .icon-svg.icon-menu .icon-glyph {
  animation: icon-menu-sweep 340ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-home .icon-glyph,
a:hover .icon-svg.icon-home .icon-glyph {
  animation: icon-home-rise 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-save path:nth-child(2),
a:hover .icon-svg.icon-save path:nth-child(2) {
  animation: icon-save-press 420ms ease both;
}
button:hover .icon-svg.icon-reset .icon-glyph,
a:hover .icon-svg.icon-reset .icon-glyph {
  animation: icon-rotate 520ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-shield-check .icon-glyph,
a:hover .icon-svg.icon-shield-check .icon-glyph,
button:hover .icon-svg.icon-shield .icon-glyph,
a:hover .icon-svg.icon-shield .icon-glyph {
  animation: icon-shield-pulse 480ms ease both;
}
button:hover .icon-svg.icon-upload path:first-child,
a:hover .icon-svg.icon-upload path:first-child {
  animation: icon-arrow-lift 380ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-image circle,
a:hover .icon-svg.icon-image circle {
  animation: icon-node-pop 380ms ease both;
}
button:hover .icon-svg.icon-image path,
a:hover .icon-svg.icon-image path {
  animation: icon-image-pan 420ms ease both;
}
button:hover .icon-svg.icon-palette circle,
a:hover .icon-svg.icon-palette circle {
  animation: icon-node-pop 360ms ease both;
}
button:hover .icon-svg.icon-palette circle:nth-of-type(2),
a:hover .icon-svg.icon-palette circle:nth-of-type(2) {
  animation-delay: 45ms;
}
button:hover .icon-svg.icon-palette circle:nth-of-type(3),
a:hover .icon-svg.icon-palette circle:nth-of-type(3) {
  animation-delay: 90ms;
}
button:hover .icon-svg.icon-search circle,
a:hover .icon-svg.icon-search circle {
  animation: icon-search-pulse 420ms ease both;
}
button:hover .icon-svg.icon-check .icon-glyph,
a:hover .icon-svg.icon-check .icon-glyph,
button:hover .icon-svg.icon-check-circle .icon-glyph,
a:hover .icon-svg.icon-check-circle .icon-glyph {
  animation: icon-draw-check 480ms ease both;
}
button:hover .icon-svg.icon-sparkles .icon-glyph,
a:hover .icon-svg.icon-sparkles .icon-glyph {
  animation: icon-sparkle 520ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-activity .icon-glyph,
a:hover .icon-svg.icon-activity .icon-glyph,
button:hover .icon-svg.icon-diagnostics .icon-glyph,
a:hover .icon-svg.icon-diagnostics .icon-glyph {
  animation: icon-wave 520ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-copy rect:first-child,
a:hover .icon-svg.icon-copy rect:first-child {
  transform: translate(-1px,-1px);
}
button:hover .icon-svg.icon-copy rect:nth-child(2),
a:hover .icon-svg.icon-copy rect:nth-child(2) {
  transform: translate(1px,1px);
}
.icon-svg.icon-copy rect {
  transition: transform 180ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-role circle,
a:hover .icon-svg.icon-role circle {
  animation: icon-node-pop 360ms ease both;
}
button:hover .icon-svg.icon-channel path,
a:hover .icon-svg.icon-channel path {
  animation: icon-channel-slide 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-lock path,
a:hover .icon-svg.icon-lock path {
  animation: icon-shackle-open 380ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-server rect,
a:hover .icon-svg.icon-server rect {
  animation: icon-server-rack 420ms ease both;
}
button:hover .icon-svg.icon-server rect:nth-child(2),
a:hover .icon-svg.icon-server rect:nth-child(2) {
  animation-delay: 65ms;
}
button:hover .icon-svg.icon-chevron-right .icon-glyph,
a:hover .icon-svg.icon-chevron-right .icon-glyph {
  animation: icon-chevron-slide 300ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-close .icon-glyph,
a:hover .icon-svg.icon-close .icon-glyph {
  animation: icon-close-turn 240ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-alert-circle .icon-glyph,
a:hover .icon-svg.icon-alert-circle .icon-glyph {
  animation: icon-alert-nudge 340ms ease both;
}

@keyframes icon-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(180deg);
  }
}
@keyframes icon-command-shift {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(1px);
  }
}
@keyframes icon-node-pop {
  0% {
    transform: scale(.82);
    opacity: .55;
  }
  70% {
    transform: scale(1.12);
    opacity: 1;
  }
  100% {
    transform: scale(1);
  }
}
@keyframes icon-tile-pop {
  0% {
    transform: scale(.88);
    opacity: .55;
  }
  65% {
    transform: scale(1.08);
    opacity: 1;
  }
  100% {
    transform: scale(1);
  }
}
@keyframes icon-audit-sweep {
  from {
    transform: rotate(-12deg);
  }
  to {
    transform: rotate(0deg);
  }
}
@keyframes icon-row-slide {
  from {
    transform: translateX(-1.5px);
    opacity: .65;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
@keyframes icon-menu-sweep {
  0% {
    transform: scaleX(1);
  }
  55% {
    transform: scaleX(.78);
  }
  100% {
    transform: scaleX(1);
  }
}
@keyframes icon-home-rise {
  from {
    transform: translateY(1px);
  }
  to {
    transform: translateY(-1px);
  }
}
@keyframes icon-save-press {
  0%,100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1px);
  }
}
@keyframes icon-shield-pulse {
  0%,100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.07);
  }
}
@keyframes icon-arrow-lift {
  from {
    transform: translateY(1px);
  }
  to {
    transform: translateY(-2px);
  }
}
@keyframes icon-image-pan {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(1px);
  }
}
@keyframes icon-search-pulse {
  0% {
    transform: scale(.92);
  }
  70% {
    transform: scale(1.08);
  }
  100% {
    transform: scale(1);
  }
}
@keyframes icon-draw-check {
  0% {
    opacity: .65;
    transform: scale(.94);
  }
  70% {
    opacity: 1;
    transform: scale(1.06);
  }
  100% {
    transform: scale(1);
  }
}
@keyframes icon-sparkle {
  0% {
    transform: rotate(0deg) scale(.96);
  }
  55% {
    transform: rotate(12deg) scale(1.08);
  }
  100% {
    transform: rotate(0deg) scale(1);
  }
}
@keyframes icon-wave {
  0% {
    transform: translateX(0);
  }
  35% {
    transform: translateX(1px);
  }
  70% {
    transform: translateX(-1px);
  }
  100% {
    transform: translateX(0);
  }
}
@keyframes icon-database-pulse {
  0%,100% {
    transform: scaleY(1);
  }
  55% {
    transform: scaleY(.82);
  }
}
@keyframes icon-channel-slide {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(1px);
  }
}
@keyframes icon-shackle-open {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(-1px);
  }
}
@keyframes icon-server-rack {
  0%,100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-1px);
  }
}
@keyframes icon-chevron-slide {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(1.5px);
  }
}
@keyframes icon-close-turn {
  from {
    transform: rotate(-8deg);
  }
  to {
    transform: rotate(0deg);
  }
}
@keyframes icon-alert-nudge {
  0%,100% {
    transform: translateX(0);
  }
  35% {
    transform: translateX(-1px);
  }
  70% {
    transform: translateX(1px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .icon-svg, .icon-svg *, button:hover .icon-svg, a:hover .icon-svg {
    animation: none !important;
    transition: none !important;
    transform: none !important;
  }
}
`;

export function GlobalStyles() {
  return <style dangerouslySetInnerHTML={{ __html: GLOBAL_STYLES }} />;
}

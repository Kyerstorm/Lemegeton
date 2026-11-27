import { ResponsiveStyles } from "./responsive";
import { designTokens } from "./Tokens";
import { typography } from "./Typography";
import { motion } from "./Motion";

const GLOBAL_STYLES = String.raw`
:root {
  color-scheme:dark;
  --bg:${designTokens.color.background};
  --surface:${designTokens.color.surface};
  --surface-2:${designTokens.color.surfaceRaised};
  --surface-3:${designTokens.color.surfaceHover};
  --line:${designTokens.color.border};
  --line-soft:${designTokens.color.borderSubtle};
  --text:${designTokens.color.text};
  --muted:${designTokens.color.muted};
  --soft:${designTokens.color.subtle};
  --accent:${designTokens.color.accent};
  --accent-dim:${designTokens.color.accentMuted};
  --success:${designTokens.color.success};
  --warning:${designTokens.color.warning};
  --danger:${designTokens.color.danger};
  --font:var(--font-ui);
  --mono:var(--font-mono);
  --font-caption:${typography.size.caption};
  --font-small:${typography.size.small};
  --font-body:${typography.size.body};
  --font-heading:${typography.size.heading};
  --radius:${designTokens.radius.panel};
  --radius-control:${designTokens.radius.control};
  --radius-compact:${designTokens.radius.compact};
  --space-compact:${designTokens.spacing.compact};
  --space-control:${designTokens.spacing.control};
  --space-section:${designTokens.spacing.section};
  --space-page:${designTokens.spacing.page};
  --target-min:${designTokens.interaction.minimumTarget};
  --motion-fast:${motion.duration.fast};
  --motion-normal:${motion.duration.normal};
  --motion-slow:${motion.duration.slow};
  font-synthesis:none;
  text-rendering:optimizeLegibility;
  -webkit-font-smoothing:antialiased
}
* {
  box-sizing:border-box
}
html {
  min-width:0;
  background:var(--bg);
  scroll-behavior:smooth
}
body {
  margin:0;
  min-width:0;
  min-height:100vh;
  background:var(--bg);
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
:where(button,a):active:not(:disabled):not([aria-disabled="true"]) {
  filter:brightness(.9)
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
  background:var(--bg);
  border-right:1px solid var(--line-soft);
  z-index:30;
  backdrop-filter:none
}
.brand {
  display:flex;
  align-items:center;
  gap:12px;
  padding:0 9px 24px
}
.sidebar-brand-row {
  display:flex;
  align-items:center;
  gap:6px;
  min-width:0;
  padding:0 4px 24px
}
.sidebar-brand-row .brand {
  flex:1;
  min-width:0;
  display:flex;
  align-items:center;
  gap:10px;
  padding:0
}
.sidebar-brand-row .brand-copy {
  min-width:0
}
.brand-mark {
  display:grid;
  place-items:center;
  width:41px;
  height:41px;
  border:1px solid #545454;
  border-radius:12px;
  background:var(--surface-2);
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
  min-height:44px;
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
  background:var(--surface-3);
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
  min-height:44px;
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
  width:44px;
  height:44px;
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
.overview-brand-art {
  display:flex;
  justify-content:center;
  align-items:center;
  gap:clamp(12px,2vw,24px);
  flex-wrap:wrap;
  margin:0 0 18px;
  min-height:80px
}
.overview-brand-art img {
  display:block;
  flex:0 1 360px;
  min-width:0;
  width:min(100%,360px);
  height:auto;
  aspect-ratio:3/1;
  object-fit:contain
}
.overview-brand-static {
  display:block;
  flex:0 1 360px;
  min-width:0;
  width:min(100%,360px);
  color:var(--text);
  font-size:clamp(22px,4vw,36px);
  font-weight:700;
  letter-spacing:.22em;
  line-height:1.2;
  text-align:center
}
.overview-particles {
  flex:0 1 148px;
  width:clamp(108px,22vw,148px);
  min-width:108px
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
.page-heading h1 > span > span {
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
  min-height:var(--target-min);
  padding:0 15px;
  border:1px solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:var(--soft);
  font-size:var(--font-small);
  font-weight:600;
  cursor:pointer;
  white-space:nowrap;
  transition:background var(--motion-fast),border-color var(--motion-fast),color var(--motion-fast)
}
.button:hover:not(:disabled) {
  background:#232323;
  border-color:#454545;
  color:var(--text);
  transform:none
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
  background:var(--line-soft)
}
.status-strip {
  display:flex;
  align-items:center;
  gap:10px;
  min-height:44px;
  padding:8px 13px;
  border:1px solid #353535;
  border-radius:10px;
  background:var(--surface-2);
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
.strip-signal.is-muted {
  background:#777;
  box-shadow:none
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
  background:var(--surface);
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
  background:var(--surface);
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
  background:var(--surface-2);
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
  padding:6px 9px;
  border:1px solid var(--line);
  border-radius:var(--radius-compact);
  background:var(--surface-2);
  color:var(--muted);
  font:var(--font-caption) var(--font-ui);
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
  border-color:#294533;
  background:#102015;
  color:var(--success)
}
.status-pill.is-good i {
  background:var(--success)
}
.status-pill.is-bad {
  border-color:#533333;
  background:#211515;
  color:var(--danger)
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
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:12px
}
.empty-skeleton {
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:8px;
  width:min(100%,320px)
}
.skeleton {
  display:block;
  flex:none;
  max-width:100%;
  overflow:hidden;
  border-radius:6px;
  background:linear-gradient(100deg,#171717 20%,#292929 42%,#171717 64%);
  background-size:250% 100%;
  animation:skeleton-shimmer 1.45s ease-in-out infinite
}
@keyframes skeleton-shimmer {
  0% { background-position:100% 0 }
  100% { background-position:-150% 0 }
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
  height:var(--target-min);
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
  height:var(--target-min);
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
  background:var(--surface-2)
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
  width:44px;
  height:28px;
  padding:0;
  border:1px solid #464646;
  border-radius:99px;
  background:#292929;
  cursor:pointer;
  transition:background var(--motion-fast),border-color var(--motion-fast)
}
.switch span {
  position:absolute;
  top:5px;
  left:5px;
  width:16px;
  height:16px;
  border-radius:50%;
  background:#8a8a8a;
  transition:transform var(--motion-fast),background var(--motion-fast)
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
.dashboard-skeleton {
  pointer-events:none;
  user-select:none
}
.dashboard-skeleton .sidebar {
  overflow:hidden
}
.dashboard-skeleton .brand {
  align-items:center
}
.dashboard-skeleton .brand-copy {
  display:flex;
  flex-direction:column;
  gap:7px
}
.dashboard-skeleton .nav-item {
  cursor:default
}
.dashboard-skeleton .sidebar-system {
  align-items:center
}
.dashboard-skeleton .topbar {
  justify-content:space-between
}
.dashboard-skeleton .topbar-right {
  display:flex;
  align-items:center;
  gap:12px
}
.dashboard-skeleton .skeleton-band {
  display:flex;
  align-items:center;
  justify-content:center;
  height:34px;
  opacity:.6
}
.dashboard-skeleton .skeleton-heading {
  align-items:flex-end
}
.dashboard-skeleton .skeleton-heading .page-heading-copy {
  display:flex;
  flex-direction:column;
  gap:13px
}
.dashboard-skeleton .skeleton-status {
  gap:13px
}
.dashboard-skeleton .metric {
  display:flex;
  flex-direction:column;
  justify-content:space-between
}
.dashboard-skeleton .metric-value-skeleton {
  margin:16px 0 9px
}
.dashboard-skeleton .skeleton-panel {
  display:flex;
  flex-direction:column;
  gap:12px;
  min-height:190px
}
.dashboard-skeleton .skeleton-panel .panel-heading {
  margin-bottom:7px
}
.dashboard-skeleton .skeleton-panel .panel-heading>div {
  display:flex;
  flex-direction:column;
  gap:8px
}
.dashboard-skeleton .skeleton-divider {
  width:100%;
  height:1px;
  margin:7px 0;
  background:var(--line)
}
.dashboard-skeleton .skeleton-inline {
  display:flex;
  justify-content:space-between;
  gap:12px
}
.skeleton-inline {
  display:flex;
  align-items:center;
  gap:8px
}
.overview-skeleton {
  display:grid;
  gap:14px
}
.overview-skeleton .metric-value-skeleton {
  margin:16px 0 9px
}
.overview-skeleton-panel {
  display:flex;
  flex-direction:column;
  gap:12px;
  min-height:180px
}
.overview-skeleton-panel .panel-heading {
  margin-bottom:7px
}
.overview-skeleton-panel .panel-heading>div {
  display:flex;
  flex-direction:column;
  gap:8px
}
.command-skeleton-list .command-row {
  cursor:default
}
.command-skeleton-list .command-main {
  display:flex;
  flex-direction:column;
  gap:10px
}
.command-skeleton-list .command-main>.skeleton {
  margin-top:3px
}
.atlas-graph-skeleton {
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:22px;
  min-height:235px;
  padding:25px 12px
}
.atlas-skeleton-orbit {
  position:relative;
  display:flex;
  align-items:center;
  justify-content:space-around;
  gap:10px;
  width:100%
}
.atlas-skeleton-orbit::before {
  position:absolute;
  top:50%;
  right:10%;
  left:10%;
  border-top:1px solid var(--line);
  content:""
}
.atlas-skeleton-orbit .skeleton {
  z-index:1
}
.atlas-skeleton-footer {
  display:flex;
  flex-direction:column;
  align-self:flex-start;
  gap:10px;
  width:100%
}
.activity-list-skeleton .activity-row {
  align-items:center
}
.activity-list-skeleton .activity-copy {
  display:flex;
  flex-direction:column;
  gap:8px
}
.section-error {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  margin:0 0 13px;
  padding:12px 13px;
  border:1px solid #493737;
  border-radius:10px;
  background:#171111
}
.section-error strong {
  color:#ededed;
  font-size:11px;
  font-weight:650
}
.section-error p {
  margin:4px 0 0;
  color:#b3a0a0;
  font-size:11px;
  line-height:1.6;
  overflow-wrap:anywhere
}
.system-skeleton-rows {
  display:grid;
  gap:12px
}
.system-skeleton-rows .extension-row {
  gap:12px
}
.system-skeleton-rows .extension-row>.skeleton:first-child {
  flex:0 1 62%
}
.system-diagnostics-skeleton .panel {
  display:flex;
  flex-direction:column;
  gap:12px
}
.log-skeleton {
  display:grid;
  gap:13px;
  padding:15px 4px
}
.database-skeleton {
  display:grid;
  gap:0;
  padding:4px 0
}
.database-skeleton-row {
  display:grid;
  grid-template-columns:minmax(0,.8fr) minmax(0,1.7fr) minmax(68px,.6fr);
  align-items:center;
  gap:16px;
  padding:13px 8px;
  border-bottom:1px solid var(--line-soft)
}

.sr-only {
  position:absolute;
  width:1px;
  height:1px;
  padding:0;
  margin:-1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
  border:0
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
  background:var(--surface-3);
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


/* Monochrome redesign: precise contrast, restrained motion, and braille as a live signal motif. */
html {
  background:#000;
  color-scheme:dark
}
body {
  background:radial-gradient(ellipse at 72% -18%,#171717 0%,transparent 45%),#000;
  color:var(--text)
}
.sidebar {
  background:rgba(0,0,0,.96);
  border-right-color:#262626
}
.brand-mark {
  border-color:#666;
  background:linear-gradient(145deg,#262626,#070707);
  color:var(--accent);
  box-shadow:inset 0 0 0 1px #ffffff08
}
.nav-item:hover,.nav-item.active {
  background:#151515;
  border-color:#333;
  color:var(--accent)
}
.nav-item.active .nav-glyph,.nav-item:hover .nav-glyph {
  color:var(--accent)
}
.sidebar-system,.guild-control,.icon-button,.panel,.metric,.command-row,.confirm-dialog,.login-card {
  background-color:#090909;
  border-color:#292929
}
.button {
  background:var(--surface-2);
  border-color:#383838;
  color:#e5e5e5
}
.button:hover:not(:disabled) {
  background:#242424;
  border-color:#666;
  color:var(--accent)
}
.button.primary {
  background:var(--accent);
  border-color:var(--accent);
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
  color:var(--text)
}
.strip-signal,.signal-dot.online {
  background:var(--accent);
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
  background:radial-gradient(circle at 50% 50%,#202020,var(--bg))
}
.runtime-mark.is-online {
  border-color:#777;
  box-shadow:0 0 0 1px #ffffff0a,0 0 30px #ffffff0b
}
.distribution-track-fill {
  fill:var(--accent)
}
.switch.checked {
  background:#fafafa;
  border-color:var(--accent)
}
.switch.checked span {
  background:var(--bg)
}
.status-pill.is-good {
  color:var(--accent);
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
  background:var(--surface-2)
}
.command-copy,.command-guide {
  border-color:#363636;
  background:#0e0e0e;
  color:#d4d4d4
}
.command-copy:hover,.command-guide:hover {
  border-color:#777;
  background:#1a1a1a;
  color:var(--accent)
}
.tag-protected {
  border-color:#5b5b5b;
  color:var(--accent);
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
  outline:2px solid var(--accent);
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
  background:linear-gradient(145deg,var(--surface-2),var(--bg));
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
  font-family:var(--font-braille);
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
  font:14px var(--font-braille);
  letter-spacing:.12em;
  color:var(--accent);
  animation:braille-flicker 4.6s steps(1,end) infinite
}
.runtime-mark span {
  display:inline-block;
  font-family:var(--font-braille);
  animation:braille-pulse 6.2s steps(1,end) infinite
}
.runtime-mark.is-online span {
  animation-duration:4.1s
}
.runtime-mark i {
  background:var(--accent)
}
.spinner {
  border-color:#3d3d3d;
  border-top-color:var(--accent)
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
  min-height:var(--target-min);
  padding:0 12px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#101010;
  color:var(--text);
  font-size:12px
}
.atlas-category {
  min-height:var(--target-min);
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
  background:radial-gradient(circle at center,#1a1a1a 0,var(--surface) 48%,var(--bg) 100%);
  background-image:radial-gradient(#525252 .7px,transparent .9px),radial-gradient(ellipse at center,#1a1a1a 0,var(--surface) 54%,var(--bg) 100%);
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
  stroke:var(--accent);
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
  border-color:var(--accent);
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
  border-color:var(--accent);
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
  border-color:var(--accent);
  background:var(--accent)
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
  border-color:var(--accent);
  color:var(--accent)
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
  min-height:var(--target-min)
}
.atlas-provider-link {
  color:#aaa;
  font:9px var(--mono);
  white-space:nowrap
}
.atlas-provider-link:hover {
  color:var(--accent)
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
  min-height:var(--target-min);
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
  min-height:var(--target-min);
  min-width:var(--target-min);
  padding:0 9px
}
.atlas-graph-content {
  position:absolute;
  inset:0;
  transform-origin:center center;
  transition:transform .18s ease
}


/* Interaction and accessibility floor for the Nothing OS control surface. */
:where(button,a,input,select,textarea,[role="button"],[role="switch"]) {
  -webkit-tap-highlight-color:transparent
}
.button {
  min-height:var(--target-min)
}
.icon-button {
  width:var(--target-min);
  height:var(--target-min)
}
.nav-item,.signout {
  min-height:44px
}
.filter-control select,.guild-control select {
  min-height:var(--target-min)
}
.command-copy,.command-guide {
  min-height:var(--target-min);
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
  outline:2px solid var(--accent);
  outline-offset:3px
}
:where(button,a,input,select,textarea,[role="button"],[role="switch"]) {
  scroll-margin:12px
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
  background:var(--surface-2);
  border:1px solid #383838;
  color:#ccc;
  border-radius:6px;
  padding:7px 10px;
  font:inherit;
  font-size:11px;
  cursor:pointer
}
.atlas-clusters button strong {
  color:var(--accent)
}
.atlas-path-summary {
  padding:10px 12px;
  border-left:2px solid var(--accent);
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
  min-height:var(--target-min);
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
  color:var(--accent)
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
  background:var(--surface-2);
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
  width:44px;
  height:44px;
  flex:none;
  border:1px solid #333;
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:#aaa;
  cursor:pointer
}
.access-close:hover {
  color:var(--accent);
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
  min-height:var(--target-min);
  padding:7px 10px;
  border:1px solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:#eee;
  font-size:12px
}
.access-field-select-control {
  display:flex;
  flex-direction:column;
  gap:9px;
  min-width:0
}
.access-field-select-control select {
  width:100%;
  max-width:none;
  min-height:var(--target-min);
  padding:7px 10px;
  border:1px solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:#eee;
  font-size:12px
}
.form-control-hint {
  color:#777;
  font-size:10px;
  line-height:1.6
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
  color:var(--accent)
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
.access-footer .save-changes-copy {
  color:#929292;
  font-size:10px
}
.access-footer .save-changes-copy small {
  display:block;
  margin-top:3px;
  color:#858585;
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


.server-picker-trigger {
  display:flex;
  align-items:center;
  gap:8px;
  min-width:150px;
  max-width:270px;
  min-height:var(--target-min);
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
  display:flex;
  align-items:center;
  margin-left:auto;
  color:#777
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
  background:var(--line-soft)
}
.server-picker-icon {
  display:grid;
  place-items:center;
  width:34px;
  height:34px;
  flex:none;
  border:1px solid #333;
  border-radius:8px;
  color:var(--accent-dim)
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
  background:var(--surface-2);
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
  min-height:var(--target-min);
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
  color:var(--accent)
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
  color:var(--accent-dim)
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
  min-height:var(--target-min);
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
  color:var(--accent)
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
  color:var(--accent)
}
.policy-check input:focus-visible+.policy-checkmark {
  outline:2px solid var(--accent);
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
  min-height:var(--target-min);
  margin-top:18px;
  border:1px solid #2b9653;
  border-radius:9px;
  background:#248046;
  color:var(--accent);
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
  color:var(--accent)
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
.icon-svg.icon-chevron-down .icon-glyph {
  transition: transform 220ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-chevron-down .icon-glyph,
button[aria-expanded="true"] .icon-svg.icon-chevron-down .icon-glyph {
  transform: translateY(1.5px);
}
button:hover .icon-svg.icon-animated, a:hover .icon-svg.icon-animated, button:focus-visible .icon-svg.icon-animated, a:focus-visible .icon-svg.icon-animated {
  transform: translateY(-1px) scale(1.04);
}
button:active .icon-svg.icon-animated, a:active .icon-svg.icon-animated {
  transform: scale(.94);
}
.icon-svg.icon-arrow-up-right .icon-glyph, .icon-svg.icon-external-link .icon-glyph {
  transition: transform 220ms cubic-bezier(.2,.8,.2,1);
}
a:hover .icon-svg.icon-arrow-up-right .icon-glyph, button:hover .icon-svg.icon-arrow-up-right .icon-glyph, a:hover .icon-svg.icon-external-link .icon-glyph, button:hover .icon-svg.icon-external-link .icon-glyph {
  transform: translate(1.5px,-1.5px);
}
button:hover .icon-svg.icon-refresh .icon-glyph, a:hover .icon-svg.icon-refresh .icon-glyph {
  animation: icon-rotate 650ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-overview rect, a:hover .icon-svg.icon-overview rect {
  animation: icon-tile-pop 420ms cubic-bezier(.2,.8,.2,1) both;
}
button:hover .icon-svg.icon-overview rect:nth-child(2), a:hover .icon-svg.icon-overview rect:nth-child(2) {
  animation-delay: 35ms;
}
button:hover .icon-svg.icon-overview rect:nth-child(3), a:hover .icon-svg.icon-overview rect:nth-child(3) {
  animation-delay: 70ms;
}
button:hover .icon-svg.icon-overview rect:nth-child(4), a:hover .icon-svg.icon-overview rect:nth-child(4) {
  animation-delay: 105ms;
}
button:hover .icon-svg.icon-server circle, a:hover .icon-svg.icon-server circle {
  animation: icon-signal 520ms ease both;
}
button:hover .icon-svg.icon-server circle:nth-of-type(2), a:hover .icon-svg.icon-server circle:nth-of-type(2) {
  animation-delay: 75ms;
}
button:hover .icon-svg.icon-copy rect:first-child, a:hover .icon-svg.icon-copy rect:first-child {
  transform: translate(-1px,-1px);
}
button:hover .icon-svg.icon-copy rect:nth-child(2), a:hover .icon-svg.icon-copy rect:nth-child(2) {
  transform: translate(1px,1px);
}
.icon-svg.icon-copy rect {
  transition: transform 180ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-search circle, a:hover .icon-svg.icon-search circle {
  animation: icon-search-pulse 420ms ease both;
}
button:hover .icon-svg.icon-check .icon-glyph, a:hover .icon-svg.icon-check .icon-glyph, button:hover .icon-svg.icon-check-circle .icon-glyph, a:hover .icon-svg.icon-check-circle .icon-glyph {
  animation: icon-draw-check 480ms ease both;
}
button:hover .icon-svg.icon-sparkles .icon-glyph, a:hover .icon-svg.icon-sparkles .icon-glyph {
  animation: icon-sparkle 520ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-activity .icon-glyph, a:hover .icon-svg.icon-activity .icon-glyph, button:hover .icon-svg.icon-diagnostics .icon-glyph, a:hover .icon-svg.icon-diagnostics .icon-glyph {
  animation: icon-wave 520ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-database ellipse, a:hover .icon-svg.icon-database ellipse {
  animation: icon-database-pulse 520ms ease both;
}
button:hover .icon-svg.icon-shield-check .icon-glyph, a:hover .icon-svg.icon-shield-check .icon-glyph {
  animation: icon-shield-pulse 480ms ease both;
}
button:hover .icon-svg.icon-close .icon-glyph, a:hover .icon-svg.icon-close .icon-glyph {
  animation: icon-close-turn 240ms cubic-bezier(.2,.8,.2,1);
}
button:hover .icon-svg.icon-alert-circle .icon-glyph, a:hover .icon-svg.icon-alert-circle .icon-glyph {
  animation: icon-alert-nudge 340ms ease both;
}

.icon-svg .icon-glyph > * {
  transform-box: fill-box;
  transform-origin: center;
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

button:focus-visible .icon-svg.icon-refresh .icon-glyph,
a:focus-visible .icon-svg.icon-refresh .icon-glyph,
button:hover .icon-svg.icon-retry .icon-glyph,
a:hover .icon-svg.icon-retry .icon-glyph {
  animation: icon-rotate 650ms cubic-bezier(.2,.8,.2,1);
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

@keyframes icon-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(180deg);
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
@keyframes icon-signal {
  0%,100% {
    opacity: 1;
  }
  45% {
    opacity: .35;
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
@keyframes icon-shield-pulse {
  0%,100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.07);
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


.login-v2 {
  position:relative;
  isolation:isolate;
  display:flex;
  flex-direction:column;
  min-height:100vh;
  min-height:100svh;
  padding:24px clamp(22px,4.7vw,76px) 18px;
  overflow:hidden;
  background:var(--bg);
  color:#f1f1f1;
}
.login-v2::before {
  position:absolute;
  z-index:-2;
  inset:0;
  content:"";
  background:var(--bg);
}
.login-v2::after {
  position:absolute;
  z-index:-1;
  inset:0;
  content:"";
  pointer-events:none;
  opacity:.22;
  background-image:none;
}
.login-v2-topline,.login-v2-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
}
.login-v2-topline {
  position:relative;
  z-index:2;
  min-height:48px;
}
.login-v2-brand {
  display:inline-flex;
  align-items:center;
  gap:12px;
  color:#f3f3f3;
  text-decoration:none;
}
.login-v2-brand .brand-mark {
  display:grid;
  place-items:center;
  width:40px;
  height:40px;
  border:1px solid #333;
  border-radius:11px;
  background:var(--surface);
}
.login-v2-brand>span:last-child {
  display:grid;
  gap:4px;
}
.login-v2-brand strong {
  font-size:12px;
  letter-spacing:.13em;
  line-height:1;
}
.login-v2-brand small,.login-v2-version,.login-v2-eyebrow,.login-v2-visual-caption,.login-v2-footer {
  color:#818181;
  font:9px var(--mono);
  letter-spacing:.12em;
}
.login-v2-brand small {
  color:#6d6d6d;
  font-size:8px;
}
.login-v2-version {
  text-align:right;
}
.login-v2-layout {
  display:grid;
  grid-template-columns:minmax(340px,.88fr) minmax(420px,1.12fr);
  align-items:center;
  gap:clamp(24px,4vw,76px);
  width:100%;
  max-width:1500px;
  flex:1;
  margin:0 auto;
}
.login-v2-copy {
  position:relative;
  z-index:2;
  width:100%;
  max-width:590px;
  padding:54px 0 64px;
}
.login-v2-eyebrow {
  display:flex;
  align-items:center;
  gap:10px;
  margin:0 0 27px;
  color:#b0b0b0;
}
.login-v2-eyebrow i {
  width:6px;
  height:6px;
  border-radius:50%;
  background:#e6e6e6;

}
.login-v2-eyebrow span {
  color:#656565;
}
.login-v2-copy h1 {
  margin:0;
  font-size:clamp(52px,6.2vw,91px);
  font-weight:560;
  line-height:.96;
  letter-spacing:-.078em;
}
.login-v2-copy h1 span {
  color:#7e7e7e;
  font-weight:430;
}
.login-v2-description {
  max-width:420px;
  margin:25px 0 31px;
  color:#a0a0a0;
  font-size:14px;
  line-height:1.85;
}
.login-v2-form {
  width:min(420px,100%);
  margin:0;
}
.login-v2-submit {
  display:flex;
  align-items:center;
  justify-content:space-between;
  width:100%;
  min-height:56px;
  padding:0 19px;
  border:1px solid #e4e4e4;
  border-radius:8px;
  background:#ededed;
  color:#080808;
  font-size:13px;
  font-weight:650;
  transition:background 180ms ease,border-color 180ms ease,transform 180ms ease;
}
.login-v2-submit:hover {
  border-color:var(--accent);
  background:var(--accent);
  color:#000;
  transform:translateY(-2px);
}
.login-v2-submit:active {
  transform:translateY(0);
}
.login-v2-submit .icon-svg {
  color:var(--surface-2);
}
.login-v2-agreement {
  display:flex;
  align-items:flex-start;
  gap:10px;
  width:min(420px,100%);
  margin:11px 0 0;
  padding:12px 13px;
  border:1px solid #303030;
  border-radius:8px;
  background:var(--surface-2);
  color:#aaa;
  font-size:11px;
  line-height:1.75;
}
.login-v2-agreement>.icon-svg {
  flex:0 0 auto;
  margin-top:2px;
  color:#d0d0d0;
}
.login-v2-agreement p {
  min-width:0;
  margin:0;
}
.login-v2-agreement a {
  color:#e0e0e0;
  text-decoration:underline;
  text-decoration-color:#555;
  text-underline-offset:3px;
}
.login-v2-agreement a:hover {
  color:var(--accent);
  text-decoration-color:var(--accent);
}
.login-v2-policy {
  max-width:420px;
  margin:13px 0 0;
  color:#777;
  font-size:10px;
  line-height:1.8;
}
.login-v2-policy a {
  color:#c3c3c3;
  text-decoration:underline;
  text-decoration-color:#555;
  text-underline-offset:3px;
}
.login-v2-policy a:hover {
  color:var(--accent);
  text-decoration-color:var(--accent);
}
.login-v2-notice {
  max-width:420px;
  margin:0 0 16px;
  padding:11px 13px;
  border:1px solid #3b3b3b;
  border-radius:7px;
  background:var(--surface-2);
  color:#d3d3d3;
  font-size:11px;
}
.login-v2-assurances {
  display:grid;
  gap:11px;
  margin-top:39px;
}
.login-v2-assurances span {
  display:flex;
  align-items:center;
  gap:11px;
  color:#8d8d8d;
  font-size:10px;
}
.login-v2-assurances b {
  display:grid;
  place-items:center;
  width:23px;
  height:23px;
  border:1px solid #333;
  border-radius:6px;
  color:#d0d0d0;
  font:8px var(--mono);
}
.login-v2-visual {
  position:relative;
  display:grid;
  place-items:center;
  width:100%;
  height:min(66vw,760px);
  min-height:500px;
  max-height:760px;
  overflow:hidden;
  border:1px solid #1c1c1c;
  border-radius:18px;
  background:var(--surface);
  box-shadow:none;
}
.login-v2-visual::before,.login-v2-visual::after {
  position:absolute;
  inset:9%;
  border:1px solid #ffffff12;
  border-radius:50%;
  content:"";
  pointer-events:none;
}
.login-v2-visual::after {
  inset:19%;
  border-style:dashed;
  border-color:#ffffff18;
  transform:rotate(-22deg) scaleX(1.18);
}
.login-v2-visual-grid {
  position:absolute;
  inset:0;
  opacity:.24;
  background-image:linear-gradient(#ffffff0b 1px,transparent 1px),linear-gradient(90deg,#ffffff0b 1px,transparent 1px);
  background-size:40px 40px;
  mask-image:radial-gradient(ellipse,#000 20%,transparent 72%);
}
.login-v2-visual canvas {
  position:relative;
  z-index:1;
  width:100%!important;
  height:100%!important;
}
.login-v2-visual>svg {
  position:relative;
  z-index:1;
  width:min(70%,480px);
  height:auto;
}
.login-v2-visual-caption {
  position:absolute;
  z-index:2;
  right:22px;
  bottom:20px;
  left:22px;
  display:flex;
  justify-content:space-between;
  gap:14px;
  font-size:8px;
  color:#6c6c6c;
}
.login-v2-footer {
  position:relative;
  z-index:2;
  padding-top:14px;
  border-top:1px solid #222;
  font-size:8px;
}






.cookie-consent {
  position:fixed;
  z-index:2200;
  right:18px;
  bottom:18px;
  left:18px;
  width:min(980px,calc(100vw - 36px));
  margin:0 auto;
  overflow:hidden;
  border:1px solid #343434;
  border-radius:15px;
  background:rgba(10,10,10,.97);
  color:#ededed;
  box-shadow:0 24px 90px #000b,0 2px 12px #0008;
  backdrop-filter:blur(22px);
  -webkit-backdrop-filter:blur(22px);
  animation:cookie-consent-enter 260ms cubic-bezier(.2,.8,.2,1) both;
}
.cookie-consent-inner {
  display:grid;
  gap:15px;
  padding:21px 23px 19px;
}
.cookie-consent-copy {
  max-width:760px;
}
.cookie-consent-eyebrow {
  display:flex;
  align-items:center;
  gap:8px;
  margin:0 0 9px;
  color:#858585;
  font:8px var(--mono);
  letter-spacing:.14em;
}
.cookie-consent-eyebrow span,.legal-kicker span {
  width:6px;
  height:6px;
  flex:0 0 6px;
  border-radius:50%;
  background:#dedede;
  box-shadow:0 0 12px #fff5;
}
.cookie-consent-copy h2 {
  margin:0 0 7px;
  color:var(--text);
  font-size:20px;
  font-weight:570;
  letter-spacing:-.045em;
}
.cookie-consent-copy>p:last-child {
  max-width:720px;
  margin:0;
  color:#999;
  font-size:11px;
  line-height:1.75;
}
.cookie-consent a {
  color:#dedede;
  text-decoration:underline;
  text-decoration-color:#595959;
  text-underline-offset:3px;
}
.cookie-consent a:hover {
  color:var(--accent);
  text-decoration-color:var(--accent);
}
.cookie-consent-actions {
  display:flex;
  align-items:center;
  justify-content:flex-end;
  flex-wrap:wrap;
  gap:8px;
}
.cookie-consent-button {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:132px;
  min-height:var(--target-min);
  padding:0 14px;
  border:1px solid #3b3b3b;
  border-radius:7px;
  background:var(--surface-2);
  color:#ddd;
  font-size:10px;
  font-weight:580;
  cursor:pointer;
  transition:background 160ms ease,border-color 160ms ease,color 160ms ease,transform 160ms ease;
}
.cookie-consent-button:hover:not(:disabled) {
  border-color:#777;
  background:#1b1b1b;
  color:var(--accent);
  transform:translateY(-1px);
}
.cookie-consent-button:focus-visible,.cookie-consent-reopen:focus-visible {
  outline:2px solid #eee;
  outline-offset:3px;
}
.cookie-consent-button:disabled {
  cursor:wait;
  opacity:.55;
}
.cookie-consent-button.cookie-consent-primary {
  border-color:#e5e5e5;
  background:#e8e8e8;
  color:#080808;
}
.cookie-consent-button.cookie-consent-primary:hover:not(:disabled) {
  border-color:var(--accent);
  background:var(--accent);
  color:#000;
}
.cookie-consent-options {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:9px;
}
.cookie-consent-option {
  display:flex;
  align-items:flex-start;
  gap:13px;
  min-width:0;
  padding:13px 14px;
  border:1px solid #292929;
  border-radius:9px;
  background:#101010;
}
.cookie-consent-option strong {
  display:block;
  margin:0 0 5px;
  color:#e5e5e5;
  font-size:11px;
  font-weight:590;
}
.cookie-consent-option p {
  margin:0;
  color:#858585;
  font-size:10px;
  line-height:1.65;
}
.cookie-consent-option-state {
  flex:0 0 auto;
  padding:5px 7px;
  border:1px solid #363636;
  border-radius:5px;
  color:#aaa;
  font:7px var(--mono);
  letter-spacing:.08em;
}
.cookie-consent-toggle {
  align-items:center;
  cursor:pointer;
}
.cookie-consent-switch {
  position:relative;
  flex:0 0 35px;
  width:35px;
  height:20px;
  margin-top:1px;
}
.cookie-consent-switch input {
  position:absolute;
  width:1px;
  height:1px;
  opacity:0;
}
.cookie-consent-switch>span {
  position:absolute;
  inset:0;
  border:1px solid #484848;
  border-radius:20px;
  background:#242424;
  transition:background 160ms ease,border-color 160ms ease;
}
.cookie-consent-switch>span::after {
  position:absolute;
  top:3px;
  left:3px;
  width:12px;
  height:12px;
  border-radius:50%;
  background:#aaa;
  content:"";
  transition:transform 160ms ease,background 160ms ease;
}
.cookie-consent-switch input:checked+span {
  border-color:#ddd;
  background:#d9d9d9;
}
.cookie-consent-switch input:checked+span::after {
  background:#080808;
  transform:translateX(15px);
}
.cookie-consent-switch input:focus-visible+span {
  outline:2px solid #eee;
  outline-offset:3px;
}
.cookie-consent-note {
  grid-column:1 / -1;
  margin:0;
  color:#727272;
  font-size:9px;
}
.cookie-consent-error {
  margin:0;
  color:#f0b0b0;
  font-size:10px;
  line-height:1.6;
}
.cookie-consent-reopen {
  position:fixed;
  z-index:2199;
  right:18px;
  bottom:18px;
  min-height:var(--target-min);
  padding:0 12px;
  border:1px solid #3b3b3b;
  border-radius:7px;
  background:rgba(12,12,12,.95);
  color:#aaa;
  box-shadow:0 8px 28px #0007;
  backdrop-filter:blur(14px);
  font:8px var(--mono);
  letter-spacing:.06em;
  cursor:pointer;
  transition:color 160ms ease,border-color 160ms ease,background 160ms ease;
}
.cookie-consent-reopen:hover {
  border-color:#777;
  background:#171717;
  color:var(--accent);
}
@keyframes cookie-consent-enter {
  from { opacity:0; transform:translateY(12px); }
  to { opacity:1; transform:translateY(0); }
}

.legal-page {
  min-height:100vh;
  min-height:100svh;
  padding:24px clamp(20px,5vw,76px) 18px;
  background:var(--bg);
  color:#e9e9e9;
}
.legal-header,.legal-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  width:100%;
  max-width:1280px;
  margin:0 auto;
}
.legal-header {
  min-height:48px;
}
.legal-brand {
  display:inline-flex;
  align-items:center;
  gap:11px;
  color:#eee;
  text-decoration:none;
}
.legal-brand-mark {
  display:grid;
  place-items:center;
  width:38px;
  height:38px;
  border:1px solid #393939;
  border-radius:10px;
  background:#101010;
  color:#eee;
  font-size:19px;
  font-weight:650;
}
.legal-brand>span:last-child {
  display:grid;
  gap:4px;
}
.legal-brand strong {
  font-size:11px;
  letter-spacing:.13em;
}
.legal-brand small,.legal-back,.legal-kicker,.legal-footer {
  color:#767676;
  font:8px var(--mono);
  letter-spacing:.1em;
}
.legal-brand small {
  font-size:7px;
}
.legal-back {
  color:#b2b2b2;
  text-decoration:none;
}
.legal-back:hover {
  color:var(--accent);
}
.legal-back span {
  margin-left:5px;
}
.legal-document {
  width:100%;
  max-width:850px;
  margin:clamp(58px,9vh,110px) auto 90px;
}
.legal-kicker {
  display:flex;
  align-items:center;
  gap:9px;
  margin-bottom:26px;
}
.legal-kicker span {
  width:5px;
  height:5px;
  flex-basis:5px;
}
.legal-content h1 {
  margin:0 0 19px;
  color:#f4f4f4;
  font-size:clamp(38px,5.2vw,64px);
  font-weight:560;
  line-height:1.02;
  letter-spacing:-.065em;
}
.legal-content h2 {
  margin:43px 0 13px;
  padding-top:21px;
  border-top:1px solid #252525;
  color:#eee;
  font-size:19px;
  font-weight:560;
  letter-spacing:-.035em;
}
.legal-content h3 {
  margin:25px 0 10px;
  color:#dcdcdc;
  font-size:14px;
  font-weight:600;
}
.legal-content h4 {
  margin:19px 0 8px;
  color:#d2d2d2;
  font-size:12px;
  font-weight:600;
}
.legal-content p,.legal-content li {
  color:#a1a1a1;
  font-size:13px;
  line-height:1.9;
}
.legal-content p {
  margin:0 0 17px;
}
.legal-content strong {
  color:#e2e2e2;
  font-weight:620;
}
.legal-content a {
  color:#e0e0e0;
  text-decoration:underline;
  text-decoration-color:#595959;
  text-underline-offset:3px;
  overflow-wrap:anywhere;
}
.legal-content a:hover {
  color:var(--accent);
  text-decoration-color:var(--accent);
}
.legal-content ul,.legal-content ol {
  display:grid;
  gap:9px;
  margin:0 0 20px;
  padding-left:22px;
}
.legal-content li {
  padding-left:4px;
}
.legal-content code {
  padding:2px 5px;
  border:1px solid #2b2b2b;
  border-radius:4px;
  background:var(--surface-2);
  color:#d9d9d9;
  font:11px var(--mono);
  overflow-wrap:anywhere;
}
.legal-content hr {
  height:1px;
  margin:25px 0;
  border:0;
  background:#242424;
}
.legal-document-nav {
  display:flex;
  flex-wrap:wrap;
  gap:9px;
  margin-top:53px;
  padding-top:18px;
  border-top:1px solid #282828;
}
.legal-document-nav a {
  padding:9px 11px;
  border:1px solid #303030;
  border-radius:7px;
  color:#aaa;
  font-size:10px;
  text-decoration:none;
  transition:color 150ms ease,border-color 150ms ease;
}
.legal-document-nav a:hover {
  border-color:#686868;
  color:var(--accent);
}
.legal-footer {
  min-height:33px;
  padding-top:13px;
  border-top:1px solid #222;
  color:#606060;
  font-size:7px;
}






.ui-tabs {
  display:flex;
  flex-wrap:wrap;
  gap:5px;
  padding:4px;
  border:1px solid var(--line);
  border-radius:9px;
  background:#101010;
}
.ui-tab {
  min-height:var(--target-min);
  padding:0 13px;
  border:1px solid transparent;
  border-radius:var(--radius-compact);
  background:transparent;
  color:var(--muted);
  font-size:var(--font-caption);
  cursor:pointer;
}
.ui-tab:hover:not(:disabled) { color:var(--text); background:var(--surface-3); }
.ui-tab.active { color:var(--text); background:var(--surface-3); border-color:var(--line); }
.ui-tooltip { position:relative; display:inline-flex; align-items:center; }
.ui-tooltip::after {
  position:absolute;
  z-index:100;
  left:50%;
  bottom:calc(100% + 8px);
  width:max-content;
  max-width:240px;
  padding:6px 8px;
  border:1px solid #383838;
  border-radius:6px;
  background:var(--surface-2);
  color:#e8e8e8;
  content:attr(data-tooltip);
  font-size:10px;
  line-height:1.4;
  pointer-events:none;
  opacity:0;
  transform:translate(-50%,3px);
  transition:opacity 140ms ease,transform 140ms ease;
}
.ui-tooltip:hover::after,.ui-tooltip:focus-within::after { opacity:1; transform:translate(-50%,0); }
.ui-data-table { width:100%; border-collapse:collapse; }
.ui-data-table th { text-align:left; }
.form-field,.form-section { display:grid; gap:8px; min-width:0; }
.form-field-error { color:#bcbcbc; font-size:10px; }
.form-section { gap:13px; }
.form-section-heading h3 { margin:0; font-size:12px; font-weight:600; }
.form-section-heading p { margin:5px 0 0; color:var(--muted); font-size:10px; line-height:1.6; }
.feedback-state {
  display:flex;
  align-items:flex-start;
  gap:12px;
  padding:13px;
  border:1px solid var(--line);
  border-radius:10px;
  background:var(--surface-2);
  color:#d9d9d9;
}
.feedback-state-icon { display:grid; place-items:center; flex:none; width:29px; height:29px; border:1px solid #373737; border-radius:8px; color:#c7c7c7; }
.feedback-state-copy { min-width:0; flex:1; }
.feedback-state-copy strong { display:block; font-size:11px; font-weight:620; }
.feedback-state-copy p { margin:5px 0 0; color:#969696; font-size:10px; line-height:1.65; overflow-wrap:anywhere; }
.loading-state-block { display:grid; gap:12px; }
.loading-state-row { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:10px 0; border-bottom:1px solid var(--line-soft); }
.guild-picker-overview { display:flex; flex-direction:column; gap:3px; }
.guild-picker-overview strong { color:#ddd; font-size:10px; font-weight:600; }
.guild-picker-overview span { color:#777; font-size:9px; }
.button-destructive { background:#d5d5d5!important; border-color:#d5d5d5!important; color:var(--surface-2)!important; }
.button-destructive:hover:not(:disabled) { background:var(--accent)!important; border-color:var(--accent)!important; color:#000!important; }


.configuration-nav {
  display:flex;
  align-items:center;
  gap:5px;
  width:max-content;
  max-width:100%;
  overflow-x:auto;
  margin:0 0 22px;
  padding:4px;
  border:1px solid #292929;
  border-radius:10px;
  background:#090909;
}
.configuration-tab {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  min-height:44px;
  padding:0 13px;
  border:1px solid transparent;
  border-radius:var(--radius-compact);
  background:transparent;
  color:var(--muted);
  font:11px var(--font-ui);
  cursor:pointer;
  white-space:nowrap;
  transition:background 160ms ease,color 160ms ease,border-color 160ms ease;
}
.configuration-tab:hover { background:#151515; color:#ddd; }
.configuration-tab.active { border-color:#333; background:#1a1a1a; color:var(--accent); }
.configuration-grid {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:15px;
  margin-bottom:15px;
}
.configuration-choice-grid {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:8px;
}
.configuration-choice {
  display:flex;
  align-items:center;
  gap:10px;
  min-width:0;
  min-height:44px;
  padding:9px 11px;
  border:1px solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:#d2d2d2;
  font-size:11px;
  cursor:pointer;
  transition:border-color 150ms ease,background 150ms ease;
}
.configuration-choice:has(input:checked) { border-color:#525252; background:#151515; color:var(--accent); }
.configuration-choice input {
  flex:none;
  width:14px;
  height:14px;
  margin:0;
  accent-color:#e4e4e4;
}
.configuration-choice input:disabled { cursor:not-allowed; }
.configuration-fields {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:16px;
}
.configuration-select {
  width:100%;
  min-width:0;
  min-height:44px;
  padding:8px 11px;
  border:1px solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface-2);
  color:#ededed;
  font:12px var(--font-ui);
}
.configuration-select:disabled { opacity:.48; cursor:not-allowed; }
.configuration-note {
  margin:15px 0 0;
  padding:11px 13px;
  border-left:2px solid #5c5c5c;
  background:#101010;
  color:#a5a5a5;
  font-size:10px;
  line-height:1.65;
}
.configuration-page .panel { min-width:0; }
.configuration-page .form-section { min-width:0; }
.configuration-page .save-changes-copy { min-width:0; }




/* The orb is a compact activity signal; page-level layout remains skeleton-led. */
.activity-orb {
  display:inline-grid;
  width:20px;
  height:20px;
  flex:0 0 20px;
  place-items:center;
}
.activity-orb canvas {
  display:block;
}
.atlas-loading-status {
  display:flex;
  align-items:center;
  gap:10px;
  min-height:35px;
  margin:0 0 10px;
  color:#999;
  font-size:10px;
  line-height:1.5;
}

/* Destructive actions require a sustained hold, not a single accidental click. */
.hold-confirm-button {
  position:relative;
  min-width:150px;
  overflow:hidden;
  touch-action:none;
  user-select:none;
  cursor:pointer;
  border-color:#554040!important;
  background:#211515!important;
  color:#ededed!important;
}
.hold-confirm-button:hover:not(:disabled) {
  border-color:#805252!important;
  background:#2b1919!important;
  color:var(--accent)!important;
}
.hold-confirm-button.is-confirmed {
  border-color:#5b5b5b!important;
  background:#272727!important;
  color:#f1f1f1!important;
}
.hold-confirm-button:disabled {
  cursor:not-allowed;
}
.hold-confirm-content {
  position:relative;
  z-index:1;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  white-space:nowrap;
}
.hold-confirm-overlay {
  position:absolute;
  z-index:2;
  inset:0;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 12px;
  background:#713535;
  color:var(--accent);
  pointer-events:none;
}

/* A restrained signature flourish anchors the dashboard overview. */
.overview-signature {
  display:flex;
  align-items:center;
  justify-content:flex-end;
  min-height:42px;
  margin:8px 3px 0;
  overflow:hidden;
  color:#858585;
  opacity:.42;
}
.dqnamo-signature-stroke {
  fill:none;
  stroke:currentColor;
  stroke-linecap:round;
  stroke-linejoin:round;
  stroke-dasharray:1;
  stroke-dashoffset:1;
  animation-name:dqnamo-draw-signature;
  animation-fill-mode:forwards;
}
@keyframes dqnamo-draw-signature {
  to { stroke-dashoffset:0; }
}

/* Receipt-printer inspired appreciation page. */
.thank-you-page {
  position:fixed;
  inset:0;
  z-index:100;
  display:flex;
  min-height:100vh;
  min-height:100svh;
  max-height:100vh;
  max-height:100dvh;
  overflow-y:auto;
  overscroll-behavior:contain;
  align-items:center;
  justify-content:center;
  padding:30px 18px;
  background:rgba(7,7,7,.9);
  color:#ededed;
  -webkit-backdrop-filter:blur(16px);
  backdrop-filter:blur(16px);
}
.thank-you-shell {
  width:min(100%,480px);
}
.thank-you-header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  margin:0 0 22px;
}
.thank-you-brand {
  display:inline-flex;
  align-items:center;
  gap:10px;
  min-width:0;
  color:#eee;
  text-decoration:none;
}
.thank-you-brand>span:last-child {
  display:grid;
  gap:3px;
}
.thank-you-brand strong {
  font-size:10px;
  letter-spacing:.16em;
}
.thank-you-brand small,.thank-you-reference {
  color:#777;
  font:8px var(--mono);
  letter-spacing:.08em;
}
.thank-you-brand-mark {
  display:grid;
  width:34px;
  height:34px;
  place-items:center;
  border:1px solid #3c3c3c;
  border-radius:9px;
  background:var(--surface-2);
  color:#eee;
  font-size:17px;
  font-weight:700;
}
.thank-you-machine {
  position:relative;
  overflow:hidden;
  padding:20px 18px 13px;
  border:1px solid #353535;
  border-radius:19px;
  background:linear-gradient(145deg,#191919,#0c0c0c 64%);
  box-shadow:0 28px 90px #000a,inset 0 1px 0 #ffffff12,inset 0 -1px 0 #000;
}
.thank-you-machine-header,.thank-you-machine-footer {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  color:#777;
  font:8px var(--mono);
  letter-spacing:.1em;
}
.thank-you-machine-header {
  min-height:25px;
  margin:0 2px 16px;
}
.thank-you-screen {
  display:grid;
  justify-items:center;
  gap:11px;
  padding:23px 16px 20px;
  border:1px solid #353535;
  border-radius:11px;
  background:
    radial-gradient(ellipse at 50% 10%,var(--line-soft),transparent 75%),
    #070707;
  box-shadow:inset 0 2px 14px #000b,inset 0 1px 0 #ffffff08;
  text-align:center;
}
.thank-you-screen-label {
  color:#777;
  font:8px var(--mono);
  letter-spacing:.16em;
}
.thank-you-screen h1 {
  margin:0;
  color:#f1f1f1;
  font-size:clamp(30px,8vw,42px);
  font-weight:570;
  letter-spacing:-.07em;
  line-height:1;
}
.thank-you-screen-status {
  display:inline-flex;
  align-items:center;
  gap:7px;
  color:#b8b8b8;
  font:8px var(--mono);
  letter-spacing:.12em;
}
.thank-you-printer-slot {
  height:9px;
  margin:16px 19px 0;
  border:1px solid var(--bg);
  border-radius:5px;
  background:#030303;
  box-shadow:inset 0 2px 4px #000,0 1px 0 #ffffff0c;
}
.thank-you-paper-wrap {
  height:328px;
  margin:0 18px;
  overflow:hidden;
  perspective:700px;
}
.thank-you-paper {
  position:relative;
  min-height:345px;
  padding:25px 25px 23px;
  background:
    repeating-linear-gradient(0deg,#00000004 0,#00000004 1px,transparent 1px,transparent 4px),
    #efeee8;
  color:var(--surface-2);
  font-family:var(--mono);
  clip-path:polygon(0 0,100% 0,100% 98%,98% 100%,96% 98%,94% 100%,92% 98%,90% 100%,88% 98%,86% 100%,84% 98%,82% 100%,80% 98%,78% 100%,76% 98%,74% 100%,72% 98%,70% 100%,68% 98%,66% 100%,64% 98%,62% 100%,60% 98%,58% 100%,56% 98%,54% 100%,52% 98%,50% 100%,48% 98%,46% 100%,44% 98%,42% 100%,40% 98%,38% 100%,36% 98%,34% 100%,32% 98%,30% 100%,28% 98%,26% 100%,24% 98%,22% 100%,20% 98%,18% 100%,16% 98%,14% 100%,12% 98%,10% 100%,8% 98%,6% 100%,4% 98%,2% 100%,0 98%);
  animation:thank-you-paper-feed 1.6s cubic-bezier(.2,.8,.2,1) both;
}
@keyframes thank-you-paper-feed {
  from { transform:translateY(-94%); }
  to { transform:translateY(0); }
}
.thank-you-paper-kicker,.thank-you-paper-foot {
  margin:0;
  color:#686868;
  font-size:8px;
  letter-spacing:.1em;
  text-align:center;
}
.thank-you-paper-rule {
  height:1px;
  margin:15px 0;
  background:repeating-linear-gradient(90deg,#8c8b85 0 4px,transparent 4px 7px);
}
.thank-you-paper h2 {
  margin:17px 0 13px;
  color:#101010;
  font-size:35px;
  font-weight:800;
  letter-spacing:-.08em;
  line-height:.9;
  text-align:center;
}
.thank-you-paper-copy {
  max-width:310px;
  margin:0 auto;
  color:#393939;
  font-family:var(--font);
  font-size:12px;
  line-height:1.75;
  text-align:center;
}
.thank-you-paper-meta {
  display:grid;
  gap:7px;
  color:#4d4d4d;
  font-size:8px;
  letter-spacing:.07em;
  text-align:center;
}
.thank-you-paper-foot {
  margin-top:19px;
  font-size:7px;
}
.thank-you-machine-footer {
  padding:15px 4px 0;
}
.thank-you-footer {
  display:grid;
  justify-items:center;
  gap:12px;
  margin-top:20px;
}
.thank-you-footer .button {
  min-width:185px;
}
.thank-you-footer p {
  margin:0;
  color:#777;
  font-size:9px;
  text-align:center;
}




.logo-trace-loader {
  display:block;
  flex:0 0 auto;
  overflow:visible;
  isolation:isolate;
}
.logo-trace-loader [data-logo-fill] {
  will-change:opacity;
}
@keyframes logo-trace-loader-loop {
  to { stroke-dashoffset:-1; }
}
@keyframes logo-trace-loader-close {
  to { stroke-dashoffset:0; }
}
.dqnamo-signature-word {
  fill:currentColor;
  font-family:var(--font-display);
  font-style:italic;
  font-weight:420;
  letter-spacing:-.055em;
  opacity:0;
  clip-path:inset(0 100% 0 0);
  animation-name:dqnamo-write-wordmark;
  animation-fill-mode:forwards;
  animation-timing-function:cubic-bezier(.16,1,.3,1);
}
@keyframes dqnamo-write-wordmark {
  0% { opacity:0; clip-path:inset(0 100% 0 0); }
  8% { opacity:1; }
  100% { opacity:1; clip-path:inset(0 0 0 0); }
}
.dashboard-scroll-progress { position:fixed; top:0; left:248px; right:0; z-index:90; height:2px; overflow:hidden; background:#ffffff12; pointer-events:none; }
.dashboard-scroll-progress-fill { width:100%; height:100%; background:linear-gradient(90deg,#777,var(--accent)); }
.dashboard-page-transition { min-width:0; }
.overview-enter { will-change:opacity,transform; }
.button-glow-wrap { position:relative; display:inline-flex; isolation:isolate; border-radius:9px; }
.button-glow-layer { inset:-5px !important; opacity:.68; }
.button-glow-target { position:relative; z-index:1; }
.overview-spinning-stamp { width:52px; height:52px; flex:none; margin-right:10px; opacity:.8; }
.server-connection-label { color:#adadad; font:8px var(--mono); letter-spacing:.07em; white-space:nowrap; }
.text-shimmer { display:inline-block; color:var(--base-color,#9b9b9b); background:linear-gradient(110deg,var(--base-color,#9b9b9b) 35%,var(--base-gradient-color,var(--accent)) 50%,var(--base-color,#9b9b9b) 65%); background-size:200% 100%; background-clip:text; -webkit-background-clip:text; -webkit-text-fill-color:transparent; animation:text-shimmer-wave 2s linear infinite; }
@keyframes text-shimmer-wave { to { background-position:-200% 0; } }

.eyt { position:relative; display:inline-grid; place-items:center; width:var(--eyt-size,100px); height:var(--eyt-size,100px); flex:none; isolation:isolate; }
.eyt-ball { display:block; width:100%; height:100%; overflow:visible; user-select:none; -webkit-tap-highlight-color:transparent; }
.eyt-body { fill:var(--surface-2); stroke:var(--line); stroke-width:1.5; }
.eyt-eye { fill:var(--text); pointer-events:none; }
.eyt-ball[data-poke] { cursor:pointer; }
.eyt-ball[data-poke]:focus-visible { outline:2px solid var(--accent); outline-offset:4px; border-radius:50%; }
.eyt-say { position:absolute; z-index:2; inset-block-start:calc(100% + 8px); inset-inline-end:-8px; display:inline-flex; align-items:center; max-width:min(210px,calc(100vw - 32px)); min-height:32px; padding:7px 10px; overflow:hidden; border:1px solid var(--tint,var(--line)); border-radius:9px; background:var(--surface-2); color:var(--text); font:11px/1.4 var(--font); white-space:nowrap; opacity:0; transform:translateY(-4px) scale(.98); transform-origin:top right; pointer-events:none; transition:opacity .16s ease,transform .16s ease; }
.eyt-say>span:first-child { overflow:hidden; text-overflow:ellipsis; }
.eyt-say[data-on="true"] { opacity:1; transform:translateY(0) scale(1); }
.eyt-caret { display:inline-block; flex:none; width:5px; height:1em; margin-inline-start:3px; background:var(--tint,var(--accent)); animation:eyt-caret-blink .8s steps(1,end) infinite; }
@keyframes eyt-caret-blink { 50% { opacity:0; } }
.ptc { width:min(100%,480px); max-width:100%; min-width:0; margin-inline:auto; }
.ptc-canvas { display:block; width:100%; height:auto; aspect-ratio:6 / 5; color:var(--text); cursor:pointer; touch-action:pan-y; border-radius:var(--radius-control); }
.ptc-canvas:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
@media (orientation:landscape) and (max-height:520px) and (max-width:1000px) {
  .main { padding-right:20px; padding-left:20px; }
  .topbar { height:64px; }
  .page { padding-top:20px; }
  .overview-brand-art { min-height:58px; margin-bottom:12px; }
  .overview-brand-art img, .overview-brand-static { flex-basis:250px; width:min(100%,250px); }
  .thank-you-page { align-items:flex-start; padding-top:14px; padding-bottom:14px; }
  .thank-you-paper-wrap { height:220px; }
}
@media (prefers-reduced-motion:reduce) {
  .text-shimmer { animation:none; }
  .overview-enter { will-change:auto; }
  .eyt-say { transition:none; }
  .eyt-caret { animation:none; }
}
/* Shared interaction feedback and consistent action geometry. */
.toast-stack { top:max(12px,env(safe-area-inset-top)); bottom:auto; }
.toast { align-items:center; white-space:pre-line; }
.toast-message { min-width:0; overflow-wrap:anywhere; }
.toast .activity-orb {
  display:inline-grid;
  place-items:center;
  flex:none;
  width:20px;
  height:20px;
  border-radius:0;
  background:transparent;
}
.toast-issue-link {
  display:inline-block;
  margin-left:6px;
  color:var(--accent);
  text-decoration:underline;
  text-underline-offset:3px;
  white-space:nowrap;
}
.button.primary,
.command-save,
.policy-accept {
  position:relative;
  isolation:isolate;
}
.button.primary .button-glow,
.command-save .command-save-glow,
.policy-accept .policy-button-glow {
  opacity:.22 !important;
  filter:blur(14px) !important;
}
.button.primary .button-content,
.save-button-content,
.policy-button-content {
  position:relative;
  z-index:1;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  transition:transform .18s ease;
}
.action-pending .button-content,
.action-pending .save-button-content,
.action-pending .policy-button-content {
  transform:translateX(3px);
}
.button.primary { overflow:visible; }
.command-save { overflow:visible; }
.command-save .save-button-content { min-height:20px; }
.command-save .activity-orb,
.policy-accept .activity-orb { flex:none; }
.policy-accept { min-height:44px; overflow:visible; }
.policy-decline { min-height:44px; padding:8px 12px; }
.hiw-hero-actions { align-items:stretch; }
.hiw-hero-actions > .hiw-button {
  display:inline-flex;
  min-height:44px;
  align-items:center;
  justify-content:center;
  box-sizing:border-box;
}
.hiw-nav-cta,
.hiw-mobile-menu-button {
  display:inline-flex;
  min-height:44px;
  min-width:44px;
  align-items:center;
  justify-content:center;
  box-sizing:border-box;
}
.hiw-mobile-menu-dashboard { min-height:44px; display:flex; align-items:center; justify-content:center; }
@media (prefers-reduced-motion:reduce) {
  .button.primary .button-content,
  .save-button-content,
  .policy-button-content { transition:none; }
  .action-pending .button-content,
  .action-pending .save-button-content,
  .action-pending .policy-button-content { transform:none; }
}

/* Recovery actions stay grouped and wrap cleanly on narrow screens. */
.feedback-state-actions {
  display:flex;
  align-items:center;
  justify-content:flex-end;
  flex-wrap:wrap;
  gap:6px;
  margin-left:auto;
}
.feedback-state-report { min-height:var(--target-min); }
@media (max-width:560px) {
  .feedback-state { flex-wrap:wrap; }
  .feedback-state-actions {
    width:100%;
    margin-left:41px;
    justify-content:flex-start;
  }
}

/* Apply reduced-motion preferences to every CSS-driven interaction. */
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto !important; }
  *, *::before, *::after {
    animation-duration:.01ms !important;
    animation-delay:0s !important;
    animation-iteration-count:1 !important;
    transition-duration:.01ms !important;
    transition-delay:0s !important;
    scroll-behavior:auto !important;
  }
}

`;

export function GlobalStyles() {
  return <><style dangerouslySetInnerHTML={{ __html: GLOBAL_STYLES }} /><ResponsiveStyles /></>;
}

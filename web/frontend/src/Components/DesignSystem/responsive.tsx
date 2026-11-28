const RESPONSIVE_STYLES = String.raw`
@media(prefers-reduced-motion:reduce) {
  .skeleton {
    animation:none;
    background-position:50% 0
  }
}

@media(max-width:700px) {
  .section-error {
    align-items:flex-start;
    flex-direction:column
  }
  .atlas-skeleton-orbit {
    gap:6px
  }
  .database-skeleton-row {
    grid-template-columns:minmax(0,.8fr) minmax(0,1.4fr) minmax(62px,.6fr);
    gap:9px;
    padding-right:2px;
    padding-left:2px
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
    width:44px;
    height:44px
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

@media (prefers-reduced-motion: reduce) {
  .icon-svg, .icon-svg *, button:hover .icon-svg, a:hover .icon-svg {
    animation: none !important;
    transition: none !important;
    transform: none !important;
  }
}

@media(max-width:960px) {
  .login-v2-layout {
    grid-template-columns:minmax(0,1fr) minmax(300px,.8fr);
    gap:24px;
  }
  .login-v2-copy h1 {
    font-size:clamp(48px,7vw,70px);
  }
  .login-v2-visual {
    min-height:420px;
  }
}

@media(max-width:800px) {
  .login-v2 {
    padding:19px 21px 16px;
  }
  .login-v2-layout {
    display:block;
    position:relative;
    min-height:calc(100vh - 112px);
    min-height:calc(100svh - 112px);
  }
  .login-v2-copy {
    max-width:570px;
    padding:clamp(90px,20vh,180px) 0 100px;
  }
  .login-v2-copy h1 {
    font-size:clamp(50px,10vw,76px);
  }
  .login-v2-visual {
    position:absolute;
    z-index:-1;
    top:4%;
    right:-28%;
    width:92vw;
    height:92vw;
    min-height:0;
    max-height:none;
    border:0;
    border-radius:50%;
    opacity:.34;
    box-shadow:none;
    background:radial-gradient(circle,#252525 0%,#09090900 67%);
  }
  .login-v2-visual::before {
    inset:18%;
  }
  .login-v2-visual::after {
    inset:29%;
  }
  .login-v2-visual-grid,.login-v2-visual-caption {
    display:none;
  }
  .login-v2-footer {
    font-size:7px;
  }
}

@media(max-width:520px) {
  .login-v2-version {
    font-size:7px;
  }
  .login-v2-copy {
    padding-top:120px;
  }
  .login-v2-description {
    max-width:340px;
    font-size:12px;
  }
  .login-v2-assurances {
    margin-top:29px;
  }
  .login-v2-footer {
    align-items:flex-start;
    flex-direction:column;
    gap:7px;
  }
}

@media(prefers-reduced-motion:reduce) {
  .login-v2-submit {
    transition:none;
  }
}

@media(max-width:760px) {
  .cookie-consent {
    right:10px;
    bottom:10px;
    left:10px;
    width:calc(100vw - 20px);
    border-radius:12px;
  }
  .cookie-consent-inner {
    gap:12px;
    padding:16px 15px 14px;
  }
  .cookie-consent-copy h2 {
    font-size:18px;
  }
  .cookie-consent-copy>p:last-child {
    font-size:10px;
  }
  .cookie-consent-actions {
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:7px;
  }
  .cookie-consent-button {
    min-width:0;
    min-height:var(--target-min);
    padding:0 8px;
    font-size:9px;
  }
  .cookie-consent-button:last-child:nth-child(3) {
    grid-column:1 / -1;
  }
  .cookie-consent-options {
    grid-template-columns:1fr;
  }
  .cookie-consent-note {
    grid-column:auto;
  }
  .cookie-consent-reopen {
    right:10px;
    bottom:10px;
  }
  .legal-page {
    padding:17px 19px 15px;
  }
  .legal-document {
    margin:62px auto 65px;
  }
  .legal-content h2 {
    margin-top:34px;
    font-size:17px;
  }
  .legal-content p,.legal-content li {
    font-size:12px;
    line-height:1.85;
  }
  .legal-footer {
    align-items:flex-start;
    flex-direction:column;
    justify-content:center;
    gap:7px;
  }
}

@media(max-width:420px) {
  .cookie-consent-actions {
    grid-template-columns:1fr;
  }
  .cookie-consent-button:last-child:nth-child(3) {
    grid-column:auto;
  }
  .legal-back {
    font-size:7px;
  }
}

@media(prefers-reduced-motion:reduce) {
  .cookie-consent {
    animation:none;
  }
  .cookie-consent-button,.cookie-consent-switch>span,.cookie-consent-switch>span::after,.cookie-consent-reopen,.legal-document-nav a {
    transition:none;
  }
}

@media(prefers-reduced-motion:reduce) {
  .ui-tooltip::after { transition:none; }
  .ui-tab { transition:none; }
}

@media(max-width:680px) {
  .configuration-grid,.configuration-fields { grid-template-columns:minmax(0,1fr); }
  .configuration-choice-grid { grid-template-columns:minmax(0,1fr); }
  .configuration-nav { width:100%; }
  .configuration-tab { flex:1 0 auto; padding:0 10px; }
}

@media(prefers-reduced-motion:reduce) {
  .configuration-tab,.configuration-choice { transition:none; }
}

@media(max-width:480px) {
  .thank-you-page { padding:22px 14px; }
  .thank-you-machine { padding:16px 12px 12px; }
  .thank-you-paper-wrap { margin:0 13px; height:318px; }
  .thank-you-paper { padding:23px 17px; }
  .thank-you-reference { font-size:7px; }
}

@media(prefers-reduced-motion:reduce) {
  .dqnamo-signature-stroke {
    animation-duration:1ms!important;
    animation-delay:0s!important;
  }
  .thank-you-paper {
    animation:none;
    transform:none;
  }
  .hold-confirm-overlay {
    transition:none!important;
  }
}

:root {
  --dashboard-gutter: clamp(12px, 2.5vw, 48px);
  --dashboard-safe-top: env(safe-area-inset-top, 0px);
  --dashboard-safe-right: env(safe-area-inset-right, 0px);
  --dashboard-safe-bottom: env(safe-area-inset-bottom, 0px);
  --dashboard-safe-left: env(safe-area-inset-left, 0px);
}
html,
body {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
body,
.app-shell {
  overflow-x: clip;
}
.app-shell {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.main,
.page,
.content-grid,
.metric-grid,
.panel,
.panel-heading,
.page-heading,
.page-heading-copy,
.topbar,
.topbar-right,
.guild-control,
.heading-actions,
.page-footer {
  min-width: 0;
  max-width: 100%;
}
.main {
  width: auto;
  max-width: none;
  padding-left: clamp(12px, 2.5vw, 48px);
  padding-right: clamp(12px, 2.5vw, 48px);
}
.page {
  width: 100%;
  container-name: dashboard-page;
  container-type: inline-size;
}
img,
video,
canvas,
iframe,
svg {
  max-width: 100%;
}
button,
input,
select,
textarea {
  min-width: 0;
  max-width: 100%;
}
pre,
code,
td,
th,
.activity-copy,
.breadcrumb,
.page-heading-copy,
.panel,
.panel-heading,
.section-error {
  overflow-wrap: anywhere;
}
.page-heading,
.panel-heading,
.section-error,
.page-footer {
  flex-wrap: wrap;
}
.heading-actions {
  flex-wrap: wrap;
  max-width: 100%;
}
.table-scroll,
.log-output {
  max-width: 100%;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}
.modal-scrim {
  min-height: 100%;
  padding: max(12px, var(--dashboard-safe-top)) max(12px, var(--dashboard-safe-right)) max(12px, var(--dashboard-safe-bottom)) max(12px, var(--dashboard-safe-left));
}
.confirm-dialog,
.access-dialog {
  min-width: 0;
  max-width: 100%;
  max-height: calc(100vh - 24px);
  max-height: calc(100dvh - 24px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
.sidebar {
  max-height: 100vh;
  max-height: 100dvh;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.overview-signature {
  max-width: 100%;
}

/* Tablet portrait and foldable inner displays use the mobile navigation. */
@media (max-width: 820px) {
  .sidebar {
    width: min(290px, 84vw);
    transform: translateX(-105%);
    transition: transform .24s ease;
    box-shadow: none;
  }
  .sidebar.mobile-open {
    transform: translateX(0);
    box-shadow: 20px 0 80px #0009;
  }
  .mobile-scrim {
    position: fixed;
    inset: 0;
    z-index: 25;
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
    background: #0009;
    opacity: 0;
    pointer-events: none;
    transition: opacity .2s;
  }
  .mobile-scrim.active {
    opacity: 1;
    pointer-events: auto;
  }
  .mobile-menu {
    display: grid;
  }
  .main {
    margin-left: 0;
    padding-left: max(14px, var(--dashboard-safe-left));
    padding-right: max(14px, var(--dashboard-safe-right));
  }
  .topbar {
    min-height: 70px;
    height: auto;
    gap: 12px;
    padding-block: 12px;
  }
  .topbar-right {
    min-width: 0;
    gap: 8px;
  }
  .account {
    display: none;
  }
  .guild-control {
    max-width: min(190px, 42vw);
  }
  .guild-control select {
    max-width: min(150px, 30vw);
  }
  .page {
    padding-top: 26px;
  }
  .page-heading {
    align-items: flex-start;
  }
  .heading-actions {
    width: 100%;
  }
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .content-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 520px) {
  .main {
    padding-left: max(10px, var(--dashboard-safe-left));
    padding-right: max(10px, var(--dashboard-safe-right));
    padding-bottom: max(18px, var(--dashboard-safe-bottom));
  }
  .topbar {
    flex-wrap: wrap;
    min-height: 66px;
    gap: 8px;
  }
  .breadcrumb {
    flex: 1 1 auto;
    min-width: 0;
  }
  .topbar-right {
    flex: 1 1 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
  }
  .guild-control {
    max-width: min(190px, calc(100vw - 104px));
  }
  .guild-control select {
    max-width: min(150px, calc(100vw - 160px));
  }
  .heading-actions {
    align-items: stretch;
  }
  .heading-actions .button {
    flex: 1 1 auto;
  }
  .panel {
    padding: clamp(12px, 3.5vw, 16px);
  }
  .metric {
    min-width: 0;
  }
  .page-footer {
    gap: 8px;
    flex-direction: column;
  }
  .confirm-dialog,
  .access-dialog {
    padding: 16px;
  }
}
@media (max-width: 360px) {
  .main {
    padding-left: max(8px, var(--dashboard-safe-left));
    padding-right: max(8px, var(--dashboard-safe-right));
  }
  .topbar {
    align-items: center;
  }
  .topbar-right {
    gap: 6px;
  }
  .guild-control {
    max-width: min(164px, calc(100vw - 96px));
    padding: 6px 7px;
  }
  .guild-control select {
    max-width: min(126px, calc(100vw - 154px));
    font-size: 10px;
  }
  .metric-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .metric {
    min-height: 112px;
  }
  .page-heading h1 {
    font-size: clamp(26px, 9vw, 31px);
    overflow-wrap: anywhere;
  }
  .button {
    white-space: normal;
    text-align: center;
  }
}
@media (min-width: 1920px) {
  .main {
    padding-left: clamp(48px, 3.5vw, 88px);
    padding-right: clamp(48px, 3.5vw, 88px);
  }
  .page {
    max-width: 1800px;
  }
  .metric-grid,
  .content-grid {
    gap: clamp(14px, 1vw, 24px);
  }
}
@container dashboard-page (max-width: 680px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .content-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .heading-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
@container dashboard-page (max-width: 340px) {
  .metric-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-height: 520px) and (max-width: 820px) {
  .sidebar {
    padding-top: 14px;
    padding-bottom: max(12px, var(--dashboard-safe-bottom));
  }
  .brand {
    padding-bottom: 14px;
  }
  .sidebar-rule {
    margin-bottom: 12px;
  }
  .sidebar-spacer {
    min-height: 12px;
  }
  .confirm-dialog,
  .access-dialog {
    max-height: calc(100vh - 16px);
    max-height: calc(100dvh - 16px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .logo-trace-loader [data-logo-trace] {
    display: none !important;
  }
  .logo-trace-loader [data-logo-fill] {
    opacity: 1 !important;
    transition: none !important;
  }
  .dqnamo-signature-word {
    animation: none !important;
    clip-path: none !important;
    opacity: 1 !important;
  }
}

@media (max-width: 1250px) { .dashboard-scroll-progress { left:225px; } }
@media (max-width: 820px) { .dashboard-scroll-progress { left:0; } }

/* Keep the closed off-canvas navigation out of keyboard and screen-reader order. */
@media (max-width: 820px) {
  .sidebar {
    visibility: hidden;
    transition: transform .24s ease, visibility 0s linear .24s;
  }
  .sidebar.mobile-open {
    visibility: visible;
    transition: transform .24s ease, visibility 0s linear 0s;
  }
}

`;

export function ResponsiveStyles() {
  return <style dangerouslySetInnerHTML={{ __html: RESPONSIVE_STYLES }} />;
}

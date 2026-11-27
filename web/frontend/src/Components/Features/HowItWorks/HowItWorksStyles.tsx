const styles = String.raw`
.hiw-page {
  --hiw-bg: #050505;
  --hiw-surface: #0b0b0b;
  --hiw-raised: #111111;
  --hiw-hover: #181818;
  --hiw-line: #292929;
  --hiw-line-soft: #1d1d1d;
  --hiw-text: #f5f5f5;
  --hiw-soft: #c9c9c9;
  --hiw-muted: #929292;
  --hiw-white: #ffffff;
  position: relative;
  min-height: 100vh;
  overflow: clip;
  background: var(--hiw-bg);
  color: var(--hiw-text);
  font-family: var(--font-ui);
  isolation: isolate;
}
.hiw-page * { box-sizing: border-box; }
.hiw-page a { color: inherit; text-decoration: none; }
.hiw-page button, .hiw-page a { -webkit-tap-highlight-color: transparent; }
.hiw-page a:focus-visible, .hiw-page summary:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 4px;
  border-radius: 4px;
}
.hiw-progress { position: fixed; inset: 0 0 auto; z-index: 1000; height: 2px; pointer-events: none; }
.hiw-progress > * { width: 100%; }
.hiw-nav {
  position: sticky;
  top: 0;
  z-index: 120;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 76px;
  padding: 0 clamp(20px, 5vw, 72px);
  border-bottom: 1px solid #ffffff12;
  background: rgba(5,5,5,.82);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}
.hiw-brand { display: inline-flex; align-items: center; gap: 11px; min-width: max-content; }
.hiw-brand .brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  overflow: hidden;
  border: 1px solid #393939;
  border-radius: 10px;
  background: #111;
}
.hiw-brand > span:last-child { display: grid; gap: 3px; }
.hiw-brand strong { font-size: 10px; font-weight: 760; letter-spacing: .2em; }
.hiw-brand small { color: #777; font: 8px var(--font-mono); letter-spacing: .12em; }
.hiw-nav-links { display: flex; align-items: center; justify-content: center; gap: clamp(16px, 3vw, 36px); }
.hiw-nav-links a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 44px;
  color: #919191;
  font-size: 11px;
  transition: color .18s ease;
}
.hiw-nav-links a:hover, .hiw-nav-links a.is-current { color: #fff; }
.hiw-nav-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid #454545;
  border-radius: 8px;
  background: #f2f2f2;
  color: #111 !important;
  font-size: 11px;
  font-weight: 650;
  transition: background .2s ease, transform .2s ease;
}
.hiw-nav-cta:hover { background: #fff; transform: translateY(-1px); }
.hiw-hero {
  position: relative;
  display: flex;
  min-height: min(810px, calc(100svh - 76px));
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  border-bottom: 1px solid var(--hiw-line-soft);
  background:
    radial-gradient(ellipse at 50% 30%, #171717 0, #090909 42%, #050505 76%);
  isolation: isolate;
}
.hiw-spotlight { position: absolute; inset: 0; z-index: -1; overflow: hidden; pointer-events: auto; }
.hiw-spotlight-base, .hiw-spotlight-focus {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(255,255,255,.22) .7px, transparent .8px);
  background-size: 24px 24px;
  mask-image: radial-gradient(ellipse at 50% 48%, #000 0, transparent 78%);
}
.hiw-spotlight-base { opacity: .14; }
.hiw-spotlight-focus { opacity: .64; background-image: radial-gradient(rgba(255,255,255,.7) 1px, transparent 1.2px); }
.hiw-path-flow { position: absolute; inset: auto -5% 2%; width: 110%; height: 280px; z-index: -1; opacity: .75; pointer-events: none; }
.hiw-hero-glow { position: absolute; inset: 15% 24% 18%; z-index: -1; opacity: .14; filter: saturate(0); pointer-events: none; }
.hiw-hero-content {
  position: relative;
  z-index: 2;
  width: min(100% - 44px, 1050px);
  margin: 0 auto;
  padding: 112px 0 118px;
  text-align: center;
}
.hiw-eyebrow {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 17px;
  color: #999;
  font: 9px var(--font-mono);
  letter-spacing: .14em;
  line-height: 1.6;
  text-transform: uppercase;
}
.hiw-hero-eyebrow { justify-content: center; margin-bottom: 26px; }
.hiw-live-mark { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: #e7e7e7; box-shadow: 0 0 0 4px #ffffff12, 0 0 18px #ffffff66; }
.hiw-eyebrow-divider { color: #555; }
.hiw-hero h1 {
  margin: 0;
  color: #f6f6f6;
  font-size: clamp(48px, 8.3vw, 94px);
  font-weight: 550;
  letter-spacing: -.075em;
  line-height: .99;
}
.hiw-hero h1 span { color: #8e8e8e; font-weight: 430; }
.hiw-hero-copy {
  max-width: 610px;
  margin: 26px auto 0;
  color: #a4a4a4;
  font-size: clamp(13px, 1.2vw, 15px);
  line-height: 1.85;
}
.hiw-hero-actions { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 30px; }
.hiw-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 46px;
  padding: 0 17px;
  border: 1px solid #363636;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 620;
  transition: background .2s ease, border-color .2s ease, transform .2s ease, color .2s ease;
}
.hiw-button:hover { transform: translateY(-2px); }
.hiw-button-primary { border-color: #efefef; background: #f1f1f1; color: #111 !important; }
.hiw-button-primary:hover { background: #fff; }
.hiw-button-quiet { background: #111111a8; color: #d3d3d3 !important; }
.hiw-button-quiet:hover { border-color: #666; background: #1b1b1b; color: #fff !important; }
.hiw-hero-meta { display: flex; justify-content: center; flex-wrap: wrap; gap: clamp(17px, 4vw, 44px); margin-top: 72px; color: #686868; font: 8px var(--font-mono); letter-spacing: .13em; }
.hiw-hero-bottom {
  position: absolute;
  right: clamp(20px, 5vw, 72px);
  bottom: 23px;
  left: clamp(20px, 5vw, 72px);
  display: flex;
  justify-content: space-between;
  gap: 14px;
  color: #666;
  font: 8px var(--font-mono);
  letter-spacing: .12em;
}
.hiw-hero-bottom span:last-child { display: inline-flex; align-items: center; gap: 7px; }
.hiw-section { width: min(100% - 48px, 1160px); margin: 0 auto; padding: 118px 0; }
.hiw-section-heading { display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 20px; margin-bottom: 44px; }
.hiw-index { padding-top: 4px; color: #666; font: 10px var(--font-mono); letter-spacing: .08em; }
.hiw-section-heading .hiw-eyebrow { margin-bottom: 12px; }
.hiw-section-heading h2 {
  max-width: 740px;
  margin: 0;
  color: #f0f0f0;
  font-size: clamp(30px, 4.4vw, 48px);
  font-weight: 530;
  letter-spacing: -.06em;
  line-height: 1.08;
}
.hiw-section-copy { max-width: 650px; margin: 15px 0 0; color: #929292; font-size: 13px; line-height: 1.8; }
.hiw-activity-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 13px; }
.hiw-activity-card {
  position: relative;
  min-height: 236px;
  padding: 24px 23px;
  overflow: hidden;
  border: 1px solid var(--hiw-line);
  border-radius: 13px;
  background: linear-gradient(145deg, #121212, #090909);
  transition: border-color .22s ease, transform .22s ease, background .22s ease;
}
.hiw-activity-card:hover { border-color: #5a5a5a; transform: translateY(-3px); background: linear-gradient(145deg, #181818, #0b0b0b); }
.hiw-card-index { position: absolute; top: 23px; right: 23px; color: #5c5c5c; font: 9px var(--font-mono); }
.hiw-activity-icon { display: grid; place-items: center; width: 42px; height: 42px; margin-bottom: 31px; border: 1px solid #3b3b3b; border-radius: 11px; background: #1a1a1a; color: #eee; }
.hiw-activity-card h3 { margin: 0; font-size: 19px; font-weight: 580; letter-spacing: -.04em; }
.hiw-activity-card p { max-width: 290px; margin: 9px 0 0; color: #929292; font-size: 11px; line-height: 1.75; }
.hiw-card-rule { position: absolute; right: 23px; bottom: 23px; left: 23px; height: 1px; background: linear-gradient(90deg, #7776, transparent); }
.hiw-architecture { border-top: 1px solid var(--hiw-line-soft); }
.hiw-diagram-frame, .hiw-branch-frame, .hiw-provider-frame, .hiw-origin-frame, .hiw-atlas-frame {
  overflow: hidden;
  border: 1px solid #303030;
  border-radius: 15px;
  background: radial-gradient(ellipse at 50% 0, #171717, #0b0b0b 62%);
  box-shadow: 0 24px 70px #0005, inset 0 1px 0 #ffffff08;
}
.hiw-diagram-topline {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-height: 45px;
  align-items: center;
  padding: 0 19px;
  border-bottom: 1px solid #ffffff12;
  color: #777;
  font: 8px var(--font-mono);
  letter-spacing: .1em;
}
.hiw-data-diagram {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px minmax(0, 1fr);
  align-items: center;
  gap: 28px;
  min-height: 390px;
  padding: 34px clamp(18px, 4vw, 48px) 48px;
  overflow: hidden;
}
.hiw-data-diagram > svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.hiw-data-side { position: relative; z-index: 2; display: grid; gap: 13px; }
.hiw-flow-node {
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 72px;
  padding: 12px;
  border: 1px solid #303030;
  border-radius: 9px;
  background: #101010ed;
  box-shadow: 0 6px 24px #0005;
}
.hiw-flow-node > span:last-child { display: grid; min-width: 0; gap: 4px; }
.hiw-flow-node strong { color: #ddd; font-size: 10px; font-weight: 620; }
.hiw-flow-node small { color: #777; font-size: 9px; line-height: 1.5; }
.hiw-node-icon { display: grid; place-items: center; flex: 0 0 34px; width: 34px; height: 34px; border: 1px solid #414141; border-radius: 8px; background: #1a1a1a; color: #d9d9d9; }
.hiw-data-core {
  position: relative;
  z-index: 2;
  display: flex;
  min-height: 205px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 9px;
  overflow: hidden;
  border: 1px solid #545454;
  border-radius: 14px;
  background: linear-gradient(150deg, #222, #0d0d0d 68%);
  box-shadow: 0 20px 55px #0009, inset 0 1px 0 #ffffff16;
  isolation: isolate;
}
.hiw-data-core > :not(.hiw-glow-layer), .hiw-atlas-center > :not(.hiw-glow-layer) { position: relative; z-index: 1; }
.hiw-glow-layer { z-index: 0 !important; }
.hiw-core-mark { display: grid; place-items: center; width: 54px; height: 54px; margin-bottom: 4px; border: 1px solid #555; border-radius: 13px; background: #161616; }
.hiw-data-core strong { font-size: 12px; font-weight: 650; }
.hiw-data-core small { color: #9a9a9a; font: 9px var(--font-mono); }
.hiw-core-caption { margin-top: 7px; color: #656565; font: 7px var(--font-mono); letter-spacing: .1em; text-transform: uppercase; }
.hiw-diagram-note { margin: 0; padding: 0 20px 19px; color: #777; font-size: 9px; line-height: 1.7; }
.hiw-data-diagram .hiw-diagram-note { position: absolute; right: 0; bottom: 0; left: 0; }
.hiw-two-column { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(260px, .75fr); align-items: start; gap: 48px; margin-top: 68px; }
.hiw-two-column > div:first-child > .hiw-eyebrow { margin-bottom: 18px; }
.hiw-flowlist { position: relative; display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.hiw-flowlist::before { position: absolute; top: 18px; bottom: 18px; left: 17px; width: 1px; background: linear-gradient(#777, #292929); content: ""; }
.hiw-flowlist li {
  position: relative;
  display: flex;
  align-items: center;
  gap: 15px;
  min-height: 76px;
  padding: 13px 15px;
  border: 1px solid #292929;
  border-radius: 10px;
  background: #0b0b0b;
  transition: border-color .2s ease, background .2s ease;
}
.hiw-flowlist li:hover { border-color: #555; background: #111; }
.hiw-flowlist-number { position: relative; z-index: 1; display: grid; place-items: center; flex: 0 0 34px; width: 34px; height: 34px; border: 1px solid #4a4a4a; border-radius: 50%; background: #101010; color: #cfcfcf; font: 9px var(--font-mono); }
.hiw-flowlist-copy { display: grid; flex: 1; gap: 4px; min-width: 0; }
.hiw-flowlist-copy strong { color: #dedede; font-size: 11px; font-weight: 620; }
.hiw-flowlist-copy small { color: #858585; font-size: 10px; line-height: 1.55; }
.hiw-flowlist li > svg { flex: 0 0 auto; color: #666; }
.hiw-side-note { position: sticky; top: 110px; padding: 25px; border: 1px solid #303030; border-radius: 13px; background: linear-gradient(145deg, #141414, #090909); }
.hiw-note-icon { display: grid; place-items: center; width: 42px; height: 42px; margin-bottom: 26px; border: 1px solid #494949; border-radius: 10px; background: #1c1c1c; }
.hiw-side-note h3 { margin: 0; font-size: 22px; font-weight: 560; letter-spacing: -.05em; line-height: 1.15; }
.hiw-side-note > p:not(.hiw-eyebrow) { color: #909090; font-size: 11px; line-height: 1.8; }
.hiw-side-note .hiw-note-foot { margin-top: 20px; padding-top: 16px; border-top: 1px solid #282828; color: #bbb !important; }
.hiw-commands { border-top: 1px solid var(--hiw-line-soft); }
.hiw-branch { padding: 26px 26px 0; }
.hiw-branch-root { position: relative; z-index: 2; display: flex; align-items: center; justify-content: center; gap: 12px; width: min(100%, 340px); min-height: 67px; margin: 0 auto; border: 1px solid #555; border-radius: 10px; background: #171717; }
.hiw-branch-root > span:last-child { display: grid; gap: 4px; }
.hiw-branch-root strong { font: 11px var(--font-mono); }
.hiw-branch-root small { color: #888; font-size: 9px; }
.hiw-branch > svg { display: block; width: 100%; height: 88px; overflow: visible; }
.hiw-branch > svg path { fill: none; stroke: #555; stroke-width: 1.2; stroke-dasharray: 4 6; }
.hiw-branch-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding-bottom: 20px; }
.hiw-branch-node { min-height: 103px; padding: 15px; border: 1px solid #303030; border-radius: 9px; background: #101010; transition: background .2s ease, border-color .2s ease, transform .2s ease; }
.hiw-branch-node:hover { border-color: #555; background: #171717; transform: translateY(-2px); }
.hiw-branch-node strong { display: block; margin-bottom: 7px; color: #eee; font: 10px var(--font-mono); }
.hiw-branch-node small { display: block; color: #828282; font-size: 9px; line-height: 1.6; }
.hiw-branch + .hiw-diagram-note { padding-top: 0; }
.hiw-standalone { display: flex; align-items: flex-start; gap: 22px; margin: 19px 0 0 78px; padding: 17px 19px; border: 1px solid #292929; border-radius: 10px; background: #090909; }
.hiw-standalone > span { flex: 0 0 auto; color: #777; font: 8px var(--font-mono); letter-spacing: .1em; }
.hiw-standalone p { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin: 0; color: #888; font-size: 10px; line-height: 1.7; }
.hiw-standalone code { color: #ddd; font: 9px var(--font-mono); }
.hiw-standalone i { width: 3px; height: 3px; border-radius: 50%; background: #555; }
.hiw-dashboard { border-top: 1px solid var(--hiw-line-soft); }
.hiw-dashboard-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(255px, .7fr); gap: 14px; align-items: stretch; margin-bottom: 14px; }
.hiw-dashboard-copy { overflow: hidden; border: 1px solid #303030; border-radius: 14px; background: #0b0b0b; }
.hiw-pipeline { position: relative; display: grid; gap: 0; padding: 17px 24px 22px 26px; }
.hiw-pipeline-track { position: absolute; top: 42px; bottom: 57px; left: 46px; width: 1px; background: linear-gradient(#aaa, #333); }
.hiw-pipeline-track span { position: absolute; top: 0; left: -1px; width: 3px; height: 48px; border-radius: 3px; background: #eee; box-shadow: 0 0 15px #fff8; animation: hiw-pipeline-scan 5s linear infinite; }
.hiw-pipeline-stage { position: relative; display: flex; align-items: flex-start; gap: 17px; min-height: 82px; padding: 12px 0; }
.hiw-pipeline-number { position: relative; z-index: 1; display: grid; place-items: center; flex: 0 0 40px; width: 40px; height: 40px; border: 1px solid #4c4c4c; border-radius: 50%; background: #111; color: #ddd; font: 9px var(--font-mono); }
.hiw-pipeline-stage > div { padding-top: 4px; }
.hiw-pipeline-stage strong { color: #e4e4e4; font-size: 11px; font-weight: 650; }
.hiw-pipeline-stage p { max-width: 500px; margin: 5px 0 0; color: #858585; font-size: 9px; line-height: 1.6; }
.hiw-dashboard-aside { position: relative; display: flex; flex-direction: column; align-items: flex-start; padding: 27px 25px; overflow: hidden; border: 1px solid #333; border-radius: 14px; background: linear-gradient(145deg, #181818, #0a0a0a); }
.hiw-dashboard-mark { display: grid; place-items: center; width: 58px; height: 58px; margin-bottom: 27px; border: 1px solid #484848; border-radius: 13px; background: #111; }
.hiw-dashboard-aside h3 { margin: 0; color: #eee; font-size: clamp(22px, 2.5vw, 30px); font-weight: 560; letter-spacing: -.055em; line-height: 1.12; }
.hiw-dashboard-aside > p:not(.hiw-eyebrow) { color: #888; font-size: 10px; line-height: 1.8; }
.hiw-text-link { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; margin-top: auto; padding-top: 10px; color: #ddd !important; font-size: 10px; }
.hiw-text-link:hover { color: #fff !important; text-decoration: underline !important; text-underline-offset: 4px; }
.hiw-origin-frame { margin-top: 14px; }
.hiw-origin { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 22px; }
.hiw-origin-node { position: relative; display: flex; min-height: 155px; flex-direction: column; align-items: flex-start; padding: 17px; border: 1px solid #303030; border-radius: 10px; background: #101010; }
.hiw-origin-index { position: absolute; top: 16px; right: 16px; color: #656565; font: 8px var(--font-mono); }
.hiw-origin-node .hiw-node-icon { margin-bottom: 17px; }
.hiw-origin-node strong { margin-bottom: 6px; color: #ddd; font-size: 10px; }
.hiw-origin-node small { color: #828282; font-size: 9px; line-height: 1.6; }
.hiw-origin-storage { grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 44px; border: 1px solid #393939; border-radius: 8px; background: #151515; color: #c3c3c3; font: 9px var(--font-mono); }
.hiw-integrations { border-top: 1px solid var(--hiw-line-soft); }
.hiw-provider-categories { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 22px 22px 0; }
.hiw-provider-card { display: grid; gap: 8px; min-height: 91px; padding: 15px; border: 1px solid #303030; border-radius: 9px; background: #101010; }
.hiw-provider-dot { width: 6px; height: 6px; border-radius: 50%; background: #cfcfcf; box-shadow: 0 0 0 4px #ffffff0d; }
.hiw-provider-card strong { color: #ddd; font-size: 10px; font-weight: 650; }
.hiw-provider-card small { color: #858585; font-size: 9px; line-height: 1.5; }
.hiw-provider-merge { position: relative; display: grid; place-items: end center; min-height: 150px; padding: 0 22px 12px; }
.hiw-provider-merge svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.hiw-provider-merge path { fill: none; stroke: #636363; stroke-width: 1.2; stroke-dasharray: 4 7; opacity: .6; animation: hiw-provider-flow 14s linear infinite; }
.hiw-provider-core { position: relative; z-index: 1; display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 9px; max-width: 420px; min-height: 56px; padding: 12px 18px; border: 1px solid #505050; border-radius: 10px; background: #191919; box-shadow: 0 13px 35px #0009; }
.hiw-provider-core strong { color: #eee; font-size: 10px; }
.hiw-provider-core small { flex: 0 0 100%; color: #888; font-size: 8px; text-align: center; }
.hiw-provider-frame > .hiw-diagram-note { padding: 0 22px 20px; }
.hiw-storage-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; margin-top: 14px; }
.hiw-storage-card { min-height: 185px; padding: 22px; border: 1px solid #2e2e2e; border-radius: 12px; background: linear-gradient(145deg, #131313, #090909); }
.hiw-storage-card .hiw-node-icon { margin-bottom: 20px; }
.hiw-storage-card .hiw-eyebrow { margin-bottom: 7px; }
.hiw-storage-card h3 { margin: 0; font-size: 17px; font-weight: 590; letter-spacing: -.04em; }
.hiw-storage-card p:last-child { max-width: 460px; margin: 9px 0 0; color: #888; font-size: 10px; line-height: 1.7; }
.hiw-brand-loop-heading { display: flex; justify-content: space-between; gap: 16px; margin: 44px 0 14px; color: #686868; font: 8px var(--font-mono); letter-spacing: .12em; }
.hiw-brand-loop { position: relative; overflow: hidden; padding: 22px 0; border-top: 1px solid #292929; border-bottom: 1px solid #292929; mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent); }
.hiw-brand-track { display: flex; width: max-content; align-items: center; gap: 0; }
.hiw-brand-track span { display: inline-flex; align-items: center; gap: 0; padding: 0 28px; color: #b6b6b6; font: 11px var(--font-mono); letter-spacing: -.02em; white-space: nowrap; }
.hiw-brand-track span::after { width: 4px; height: 4px; margin-left: 55px; border-radius: 50%; background: #666; content: ""; }
.hiw-atlas-section { border-top: 1px solid var(--hiw-line-soft); }
.hiw-atlas { position: relative; min-height: 440px; overflow: hidden; background: radial-gradient(ellipse at 50% 48%, #1b1b1b 0, #0d0d0d 34%, #090909 78%); }
.hiw-atlas > svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.hiw-atlas-node { position: absolute; z-index: 1; display: flex; align-items: center; gap: 8px; transform: translate(-50%, -50%); }
.hiw-atlas-node span { width: 8px; height: 8px; border: 1px solid #ddd; border-radius: 50%; background: #777; box-shadow: 0 0 18px #fff6; }
.hiw-atlas-node small { padding: 5px 8px; border: 1px solid #383838; border-radius: 6px; background: #0b0b0bdb; color: #aaa; font: 8px var(--font-mono); white-space: nowrap; }
.hiw-atlas-center { position: absolute; top: 50%; left: 50%; z-index: 2; display: flex; width: 180px; min-height: 145px; flex-direction: column; align-items: center; justify-content: center; gap: 8px; overflow: hidden; border: 1px solid #555; border-radius: 13px; background: #181818; box-shadow: 0 20px 70px #000b; transform: translate(-50%, -50%); isolation: isolate; }
.hiw-atlas-center > *:not(.motion-div) { position: relative; z-index: 1; }
.hiw-atlas-center > span { display: grid; place-items: center; width: 42px; height: 42px; border: 1px solid #444; border-radius: 10px; background: #222; }
.hiw-atlas-center strong { font-size: 11px; }
.hiw-atlas-center small { color: #888; font: 8px var(--font-mono); }
.hiw-atlas-frame > .hiw-diagram-note { padding-top: 0; }
.hiw-faq { border-top: 1px solid var(--hiw-line-soft); }
.hiw-faq-layout { display: grid; grid-template-columns: minmax(220px, .65fr) minmax(0, 1.35fr); gap: 62px; align-items: start; }
.hiw-faq-intro { position: sticky; top: 110px; padding-top: 8px; }
.hiw-faq-symbol { display: grid; place-items: center; width: 50px; height: 50px; margin-bottom: 24px; border: 1px solid #454545; border-radius: 12px; background: #141414; }
.hiw-faq-intro h3 { max-width: 250px; margin: 0; font-size: 24px; font-weight: 570; letter-spacing: -.05em; line-height: 1.12; }
.hiw-faq-intro p { max-width: 270px; margin: 12px 0; color: #888; font-size: 10px; line-height: 1.8; }
.hiw-faq-list { border-top: 1px solid #333; }
.hiw-faq-item { border-bottom: 1px solid #303030; }
.hiw-faq-item summary { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 68px; color: #e1e1e1; font-size: 12px; font-weight: 580; cursor: pointer; list-style: none; }
.hiw-faq-item summary::-webkit-details-marker { display: none; }
.hiw-faq-item summary > svg { flex: 0 0 auto; color: #858585; transition: transform .2s ease; }
.hiw-faq-item[open] summary > svg { transform: rotate(180deg); }
.hiw-faq-answer { overflow: hidden; }
.hiw-faq-answer p { max-width: 680px; margin: -2px 38px 21px 0; color: #929292; font-size: 10px; line-height: 1.85; }
.hiw-cta-section { position: relative; display: grid; min-height: 410px; place-items: center; overflow: hidden; border-top: 1px solid #292929; border-bottom: 1px solid #292929; background: radial-gradient(ellipse at 50% 40%, #1c1c1c 0, #0c0c0c 55%, #060606 100%); isolation: isolate; }
.hiw-stream-lines { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .64; z-index: -1; }
.hiw-cta-glow { position: absolute; inset: 6% 25%; z-index: -1; opacity: .15; filter: saturate(0); pointer-events: none; }
.hiw-cta-content { position: relative; z-index: 1; width: min(100% - 40px, 720px); padding: 100px 0; text-align: center; }
.hiw-cta-content > .hiw-eyebrow { justify-content: center; }
.hiw-cta-content h2 { margin: 0; font-size: clamp(34px, 5.2vw, 58px); font-weight: 540; letter-spacing: -.065em; line-height: 1.05; }
.hiw-cta-content h2 span { color: #8e8e8e; }
.hiw-cta-content > p:not(.hiw-eyebrow) { max-width: 500px; margin: 16px auto 0; color: #969696; font-size: 11px; line-height: 1.8; }
.hiw-footer { display: grid; grid-template-columns: minmax(220px, 1.5fr) repeat(2, minmax(130px, .65fr)); gap: 50px; width: min(100% - 48px, 1160px); margin: 0 auto; padding: 60px 0 22px; }
.hiw-footer-brand p { max-width: 310px; margin: 16px 0 0; color: #777; font-size: 10px; line-height: 1.75; }
.hiw-footer-column { display: grid; align-content: start; gap: 12px; }
.hiw-footer-column > strong { margin: 5px 0 7px; color: #777; font: 8px var(--font-mono); letter-spacing: .12em; }
.hiw-footer-column a { width: fit-content; color: #9a9a9a; font-size: 10px; transition: color .18s ease; }
.hiw-footer-column a:hover { color: #fff; }
.hiw-footer-bottom { grid-column: 1 / -1; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 18px; padding-top: 19px; border-top: 1px solid #292929; color: #666; font: 8px var(--font-mono); letter-spacing: .08em; }
.hiw-footer-bottom a { color: #aaa; }
.hiw-footer-bottom a:hover { color: #fff; }
@keyframes hiw-provider-flow { to { stroke-dashoffset: -120; } }
@keyframes hiw-pipeline-scan { 0% { transform: translateY(0); opacity: .2; } 50% { opacity: 1; } 100% { transform: translateY(170px); opacity: .2; } }

@media (max-width: 900px) {
  .hiw-section { padding: 88px 0; }
  .hiw-data-diagram { grid-template-columns: minmax(0, 1fr) 190px minmax(0, 1fr); gap: 15px; padding-right: 20px; padding-left: 20px; }
  .hiw-flow-node { padding: 9px; gap: 8px; }
  .hiw-flow-node small { font-size: 8px; }
  .hiw-dashboard-grid { grid-template-columns: minmax(0, 1.2fr) minmax(225px, .8fr); }
  .hiw-faq-layout { gap: 35px; }
}
@media (max-width: 700px) {
  .hiw-nav { min-height: 66px; padding: 0 17px; gap: 12px; }
  .hiw-nav-links { gap: 13px; }
  .hiw-nav-links a { font-size: 9px; }
  .hiw-nav-cta { min-height: 38px; padding: 0 10px; font-size: 9px; }
  .hiw-brand .brand-mark { width: 34px; height: 34px; }
  .hiw-brand strong { font-size: 9px; }
  .hiw-brand small { font-size: 7px; }
  .hiw-hero { min-height: 680px; }
  .hiw-hero-content { width: min(100% - 34px, 1050px); padding: 105px 0 110px; }
  .hiw-hero h1 { font-size: clamp(43px, 11vw, 68px); }
  .hiw-hero-copy { max-width: 490px; font-size: 12px; }
  .hiw-hero-meta { margin-top: 55px; font-size: 7px; }
  .hiw-hero-bottom { right: 17px; left: 17px; font-size: 7px; }
  .hiw-section { width: min(100% - 34px, 1160px); padding: 76px 0; }
  .hiw-section-heading { grid-template-columns: 34px minmax(0, 1fr); gap: 10px; margin-bottom: 30px; }
  .hiw-section-heading h2 { font-size: clamp(29px, 7vw, 42px); }
  .hiw-section-copy { font-size: 11px; }
  .hiw-activity-grid { grid-template-columns: 1fr; }
  .hiw-activity-card { min-height: 190px; }
  .hiw-activity-icon { margin-bottom: 21px; }
  .hiw-data-diagram { grid-template-columns: 1fr; gap: 12px; padding: 18px 16px 49px; }
  .hiw-data-diagram > svg { display: none; }
  .hiw-data-core { grid-row: 1; min-height: 170px; }
  .hiw-data-side { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .hiw-flow-node { min-height: 72px; }
  .hiw-flow-node strong { font-size: 9px; }
  .hiw-flow-node small { font-size: 8px; }
  .hiw-diagram-topline { min-height: 41px; padding: 0 12px; font-size: 7px; }
  .hiw-two-column { grid-template-columns: 1fr; gap: 24px; margin-top: 48px; }
  .hiw-side-note { position: static; }
  .hiw-branch { padding: 18px 14px 0; }
  .hiw-branch > svg { display: none; }
  .hiw-branch-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding-top: 16px; }
  .hiw-branch-node { min-height: 105px; padding: 12px; }
  .hiw-standalone { display: block; margin-left: 0; }
  .hiw-standalone p { margin-top: 11px; }
  .hiw-dashboard-grid { grid-template-columns: 1fr; }
  .hiw-dashboard-aside { min-height: 280px; }
  .hiw-origin { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 12px; gap: 8px; }
  .hiw-origin-node { min-height: 145px; padding: 12px; }
  .hiw-provider-categories { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 12px 12px 0; gap: 8px; }
  .hiw-provider-card { min-height: 100px; padding: 11px; }
  .hiw-storage-grid { grid-template-columns: 1fr; }
  .hiw-brand-loop-heading { font-size: 7px; }
  .hiw-brand-track span { padding: 0 18px; font-size: 9px; }
  .hiw-brand-track span::after { margin-left: 35px; }
  .hiw-atlas { min-height: 350px; }
  .hiw-atlas-node small { font-size: 7px; }
  .hiw-atlas-center { width: 145px; min-height: 125px; }
  .hiw-faq-layout { grid-template-columns: 1fr; gap: 30px; }
  .hiw-faq-intro { position: static; }
  .hiw-faq-intro h3 { max-width: none; }
  .hiw-footer { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 35px 20px; width: min(100% - 34px, 1160px); padding-top: 45px; }
  .hiw-footer-brand { grid-column: 1 / -1; }
  .hiw-footer-bottom { gap: 9px 18px; font-size: 7px; }
}
@media (max-width: 390px) {
  .hiw-nav-links { gap: 8px; }
  .hiw-nav-links a { font-size: 8px; }
  .hiw-nav-cta { display: none; }
  .hiw-hero-eyebrow { font-size: 7px; letter-spacing: .09em; }
  .hiw-hero-meta { gap: 12px; }
  .hiw-atlas-node small { padding: 4px 5px; font-size: 6px; }
  .hiw-atlas-center { width: 128px; }
  .hiw-origin-storage { font-size: 7px; }
}
@media (prefers-reduced-motion: reduce) {
  .hiw-page *, .hiw-page *::before, .hiw-page *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
  .hiw-activity-card:hover, .hiw-branch-node:hover, .hiw-button:hover { transform: none; }
}



/* Imported ReactVibe components — monochrome Lemegeton adaptation */
.hiw-page .hiw-nav { z-index: 120; }
.hiw-mobile-menu-button {
  display:none;
  place-items:center;
  width:42px;
  height:42px;
  border:1px solid #383838;
  border-radius:9px;
  background:#101010;
  color:#eee;
  cursor:pointer;
}
.hiw-mobile-menu {
  position:absolute;
  top:calc(100% + 1px);
  right:0;
  left:0;
  display:flex;
  min-height:calc(100svh - 66px);
  flex-direction:column;
  padding:22px 22px 28px;
  border-bottom:1px solid #343434;
  background:rgba(5,5,5,.98);
  backdrop-filter:blur(20px);
}
.hiw-mobile-menu-top {
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:15px;
  padding-bottom:19px;
  border-bottom:1px solid #292929;
  color:#777;
  font:8px var(--font-mono);
  letter-spacing:.12em;
}
.hiw-mobile-menu-top button {
  display:grid;
  place-items:center;
  width:40px;
  height:40px;
  border:1px solid #414141;
  border-radius:8px;
  background:#111;
  color:#ddd;
}
.hiw-mobile-menu > a:not(.hiw-mobile-menu-dashboard) {
  display:flex;
  align-items:center;
  justify-content:space-between;
  min-height:82px;
  border-bottom:1px solid #282828;
  color:#e7e7e7;
  font-size:clamp(25px,7vw,37px);
  font-weight:520;
  letter-spacing:-.055em;
}
.hiw-mobile-menu-dashboard {
  display:flex;
  justify-content:center;
  align-items:center;
  gap:9px;
  min-height:48px;
  margin-top:auto;
  border:1px solid #eee;
  border-radius:8px;
  background:#eee;
  color:#111 !important;
  font-size:11px;
  font-weight:650;
}
.hiw-launch-hero {
  position:relative;
  z-index:2;
  width:min(100% - 44px,1050px);
  margin:0 auto;
  padding:112px 0 118px;
  text-align:center;
}
.hiw-launch-glow {
  position:absolute;
  inset:10% 23% 5%;
  z-index:-1;
  opacity:.14;
  filter:saturate(0);
  pointer-events:none;
}
.hiw-launch-hero .hiw-hero-eyebrow { justify-content:center; margin-bottom:26px; }
.hiw-launch-hero h1 {
  margin:0;
  color:#f6f6f6;
  font-size:clamp(48px,8.3vw,94px);
  font-weight:550;
  letter-spacing:-.075em;
  line-height:.99;
}
.hiw-launch-hero h1 span { color:#8e8e8e; font-weight:430; }
.hiw-launch-hero .hiw-hero-copy {
  max-width:610px;
  margin:26px auto 0;
  color:#a4a4a4;
  font-size:clamp(13px,1.2vw,15px);
  line-height:1.85;
}
.hiw-launch-hero .hiw-hero-meta { margin-top:72px; }
.hiw-pathflow {
  position:absolute;
  inset:auto -5% 1%;
  z-index:-1;
  width:110%;
  height:360px;
  overflow:hidden;
  opacity:.76;
  pointer-events:none;
}
.hiw-pathflow svg { display:block; width:100%; height:100%; }
.hiw-spotlight { z-index:-2; }
.hiw-spotlight-base { opacity:.15; }
.hiw-spotlight-focus { opacity:.58; }
.hiw-data-diagram { grid-template-columns:minmax(0,1fr) 220px minmax(0,1fr); }
.hiw-data-core { isolation:isolate; }
.hiw-data-core .hiw-glow-layer { z-index:0 !important; }
.hiw-core-mark { position:relative; z-index:1; }
.hiw-data-core > strong,.hiw-data-core > small,.hiw-data-core > .hiw-core-caption { position:relative; z-index:1; }
.hiw-branch { padding:24px 20px 0; }
.hiw-branch > svg { display:block; width:100%; height:300px; margin:-8px 0 -7px; overflow:visible; }
.hiw-branch-root { min-height:68px; }
.hiw-branch-grid {
  display:grid;
  align-items:stretch;
  gap:9px;
  padding:0 0 20px;
}
.hiw-branch-node { min-width:0; min-height:128px; }
.hiw-branch-node-icon { display:grid; place-items:center; width:29px; height:29px; margin-bottom:12px; border:1px solid #393939; border-radius:7px; color:#d5d5d5; background:#171717; }
.hiw-branch-node strong { white-space:nowrap; }
.hiw-branch-node small { line-height:1.55; }
.hiw-branch > .hiw-diagram-note { padding-top:0; }
.hiw-pipeline { padding:17px 18px 22px; }
.hiw-pipeline-track { display:none; }
.hiw-pipeline-canvas {
  position:relative;
  width:100%;
  min-width:680px;
  height:365px;
  overflow:hidden;
}
.hiw-pipeline-canvas > svg { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
.hiw-pipeline-card {
  position:absolute;
  z-index:2;
  display:flex;
  width:178px;
  min-height:128px;
  flex-direction:column;
  align-items:flex-start;
  justify-content:center;
  gap:8px;
  padding:15px;
  border:1px solid #373737;
  border-radius:11px;
  background:#111;
  box-shadow:0 12px 30px #0007;
}
.hiw-pipeline-source { top:115px; left:1%; }
.hiw-pipeline-gate { top:115px; left:39%; border-color:#555; background:linear-gradient(145deg,#1b1b1b,#101010); }
.hiw-pipeline-card .hiw-node-icon { width:32px; height:32px; flex-basis:32px; }
.hiw-pipeline-card strong { color:#eee; font-size:11px; }
.hiw-pipeline-card small { color:#888; font-size:9px; line-height:1.5; }
.hiw-pipeline-gate-badge { margin-top:2px; color:#a3a3a3; font:7px var(--font-mono); letter-spacing:.1em; }
.hiw-pipeline-destinations {
  position:absolute;
  top:30px;
  right:1%;
  bottom:24px;
  display:flex;
  width:26%;
  flex-direction:column;
  justify-content:space-between;
  gap:9px;
}
.hiw-pipeline-destination {
  display:flex;
  align-items:center;
  gap:10px;
  min-height:88px;
  padding:11px;
  border:1px solid #303030;
  border-radius:9px;
  background:#0d0d0d;
  transition:border-color .2s,background .2s;
}
.hiw-pipeline-destination.is-active { border-color:#777; background:#181818; }
.hiw-pipeline-destination > span:last-child { display:grid; min-width:0; gap:4px; }
.hiw-pipeline-destination strong { color:#ddd; font-size:10px; }
.hiw-pipeline-destination small { color:#808080; font-size:8px; line-height:1.5; }
.hiw-dashboard-copy > .hiw-diagram-note { padding-top:0; }
.hiw-origin {
  position:relative;
  display:block;
  min-height:390px;
  padding:15px 20px 20px;
  overflow:hidden;
  background:radial-gradient(ellipse at 50% 25%,#151515,#0b0b0b 70%);
}
.hiw-origin-root {
  position:relative;
  z-index:2;
  display:flex;
  width:min(100%,245px);
  min-height:100px;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:7px;
  margin:0 auto;
  border:1px solid #4b4b4b;
  border-radius:11px;
  background:#171717;
  box-shadow:0 13px 35px #0008;
}
.hiw-origin-root-icon { display:grid; place-items:center; width:36px; height:36px; border:1px solid #404040; border-radius:8px; background:#202020; }
.hiw-origin-root strong { color:#eee; font-size:11px; }
.hiw-origin-root small { color:#888; font:8px var(--font-mono); }
.hiw-origin > svg { position:absolute; inset:0; z-index:1; width:100%; height:100%; pointer-events:none; }
.hiw-origin-nodes {
  position:absolute;
  z-index:2;
  right:18px;
  bottom:20px;
  left:18px;
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:10px;
}
.hiw-origin-node {
  min-height:126px;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:8px;
  padding:12px;
  border:1px solid #303030;
  border-radius:9px;
  background:#101010;
  text-align:center;
}
.hiw-origin-node .hiw-node-icon { margin:0; }
.hiw-origin-node strong { color:#ddd; font-size:9px; }
.hiw-origin-node small { color:#818181; font-size:8px; line-height:1.45; }
.hiw-origin-frame > .hiw-diagram-note { padding-top:0; }
.hiw-converge {
  position:relative;
  display:grid;
  grid-template-columns:minmax(0,1fr) 180px minmax(0,.6fr);
  align-items:center;
  gap:15px;
  min-height:480px;
  padding:24px;
  overflow:hidden;
}
.hiw-converge-sources { position:relative; z-index:2; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
.hiw-converge-source {
  display:flex;
  align-items:center;
  gap:9px;
  min-height:86px;
  padding:11px;
  border:1px solid #303030;
  border-radius:9px;
  background:#111;
}
.hiw-converge-source > span:last-child { display:grid; gap:5px; min-width:0; }
.hiw-converge-source strong { color:#ddd; font-size:9px; }
.hiw-converge-source small { color:#858585; font-size:8px; line-height:1.5; }
.hiw-converge-wires { position:absolute; inset:0; z-index:1; pointer-events:none; }
.hiw-converge-wires svg { width:100%; height:100%; }
.hiw-converge-core {
  position:relative;
  z-index:2;
  display:flex;
  min-height:180px;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:9px;
  padding:15px;
  border:1px solid #555;
  border-radius:12px;
  background:linear-gradient(145deg,#202020,#101010);
  box-shadow:0 18px 55px #0009;
  text-align:center;
}
.hiw-converge-core > .hiw-node-icon { margin-bottom:3px; }
.hiw-converge-core strong { color:#eee; font-size:10px; }
.hiw-converge-core small { color:#8b8b8b; font-size:8px; line-height:1.5; }
.hiw-converge-output {
  position:relative;
  z-index:2;
  display:grid;
  justify-items:center;
  gap:9px;
  padding:18px;
  border:1px solid #363636;
  border-radius:10px;
  background:#101010;
  text-align:center;
}
.hiw-converge-output strong { color:#ddd; font-size:10px; }
.hiw-converge-output small { color:#848484; font-size:8px; line-height:1.6; }
.hiw-provider-dot { width:7px; height:7px; border-radius:50%; background:#ddd; box-shadow:0 0 0 5px #fff1; }
.hiw-converge > .hiw-diagram-note { position:absolute; right:0; bottom:0; left:0; z-index:3; padding:0 22px 17px; }
.hiw-stream-frame { position:relative; margin-top:18px; overflow:hidden; border:1px solid #303030; border-radius:13px; background:#0b0b0b; }
.hiw-stream-frame > .hiw-diagram-topline { position:relative; z-index:2; }
.hiw-stream {
  position:relative;
  min-height:165px;
  overflow:hidden;
  pointer-events:none;
}
.hiw-stream svg { position:absolute; inset:0; width:100%; height:100%; }
.hiw-stream-provider { min-height:150px; opacity:.72; }
.hiw-brand-loop-section { position:relative; z-index:2; margin-top:0; padding:0 0 14px; }
.hiw-brand-loop-section .hiw-brand-loop-heading { margin:0 0 12px; padding:0 20px; }
.hiw-brand-loop { border-color:#292929; }
.hiw-nexus {
  position:relative;
  min-height:500px;
  overflow:hidden;
  background:radial-gradient(ellipse at 50% 50%,#1a1a1a 0,#0d0d0d 38%,#090909 80%);
}
.hiw-nexus > svg { position:absolute; inset:0; width:100%; height:100%; }
.hiw-nexus-node {
  position:absolute;
  z-index:2;
  display:flex;
  width:150px;
  min-height:94px;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:6px;
  padding:12px;
  border:1px solid #373737;
  border-radius:10px;
  background:#111e;
  box-shadow:0 10px 28px #0008;
  text-align:center;
  transform:translate(-50%,-50%);
}
.hiw-nexus-node .hiw-node-icon { width:30px; height:30px; flex-basis:30px; }
.hiw-nexus-node strong { color:#ddd; font-size:9px; }
.hiw-nexus-node small { color:#888; font-size:8px; line-height:1.45; }
.hiw-nexus-center {
  position:absolute;
  top:50%;
  left:50%;
  z-index:3;
  display:flex;
  width:180px;
  min-height:150px;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  gap:9px;
  overflow:hidden;
  border:1px solid #555;
  border-radius:14px;
  background:#181818;
  box-shadow:0 18px 60px #000b;
  transform:translate(-50%,-50%);
  isolation:isolate;
}
.hiw-nexus-center > .hiw-glow-layer { z-index:0 !important; }
.hiw-nexus-center > *:not(.hiw-glow-layer) { position:relative; z-index:1; }
.hiw-nexus-center-icon { display:grid; place-items:center; width:42px; height:42px; border:1px solid #444; border-radius:10px; background:#222; }
.hiw-nexus-center strong { color:#eee; font-size:11px; }
.hiw-nexus-center small { color:#888; font:8px var(--font-mono); }
.hiw-atlas-frame > .hiw-diagram-note { padding-top:0; }
.hiw-flowlist { position:relative; display:block; width:100%; }
.hiw-flowlist-scroll { display:grid; gap:8px; max-height:430px; overflow-y:auto; outline:none; scrollbar-width:none; }
.hiw-flowlist-scroll::-webkit-scrollbar { display:none; }
.hiw-flowlist-scroll:focus-visible { outline:2px solid #aaa; outline-offset:4px; border-radius:10px; }
.hiw-flowlist-item {
  display:flex;
  width:100%;
  min-height:76px;
  align-items:center;
  gap:13px;
  padding:12px 14px;
  border:1px solid #303030;
  border-radius:9px;
  background:#0d0d0d;
  color:#ddd;
  text-align:left;
  cursor:pointer;
  transition:border-color .18s,background .18s;
}
.hiw-flowlist-item:hover,.hiw-flowlist-item.is-selected { border-color:#666; background:#161616; }
.hiw-flowlist-number { display:grid; place-items:center; width:33px; height:33px; flex:0 0 33px; border:1px solid #444; border-radius:50%; color:#ccc; font:9px var(--font-mono); }
.hiw-flowlist-copy { display:grid; flex:1; min-width:0; gap:5px; }
.hiw-flowlist-copy strong { color:#ddd; font-size:10px; font-weight:620; }
.hiw-flowlist-copy small { color:#858585; font-size:9px; line-height:1.55; }
.hiw-flowlist-item > svg { flex:0 0 auto; color:#777; }
.hiw-flowlist-fade { position:absolute; z-index:3; right:0; left:0; height:48px; pointer-events:none; transition:opacity .2s; }
.hiw-flowlist-fade-top { top:0; background:linear-gradient(#0b0b0b,transparent); }
.hiw-flowlist-fade-bottom { bottom:0; background:linear-gradient(transparent,#0b0b0b); }
.hiw-brand-loop-section .hiw-brand-loop-track { will-change:transform; }
.hiw-resolve { display:grid; grid-template-columns:minmax(220px,.65fr) minmax(0,1.35fr); gap:62px; align-items:start; }
.hiw-resolve-aside { position:sticky; top:110px; padding-top:8px; }
.hiw-resolve-mark { position:relative; display:grid; place-items:center; width:50px; height:50px; margin-bottom:24px; overflow:hidden; border:1px solid #454545; border-radius:12px; background:#141414; isolation:isolate; }
.hiw-resolve-mark > .hiw-glow-layer { z-index:0 !important; }
.hiw-resolve-mark > span { position:relative; z-index:1; }
.hiw-resolve-aside h3 { max-width:260px; margin:0; color:#eee; font-size:24px; font-weight:570; letter-spacing:-.05em; line-height:1.12; }
.hiw-resolve-aside p { max-width:270px; margin:12px 0; color:#888; font-size:10px; line-height:1.8; }
.hiw-resolve-list { border-top:1px solid #333; }
.hiw-resolve-item { border-bottom:1px solid #303030; }
.hiw-resolve-item > button {
  display:flex;
  width:100%;
  min-height:68px;
  justify-content:space-between;
  align-items:center;
  gap:20px;
  border:0;
  background:transparent;
  color:#e1e1e1;
  font-size:12px;
  font-weight:580;
  text-align:left;
  cursor:pointer;
}
.hiw-resolve-item > button svg { flex:0 0 auto; color:#858585; }
.hiw-resolve-item.is-open > button { color:#fff; }
.hiw-resolve-answer { overflow:hidden; }
.hiw-resolve-answer p { max-width:680px; margin:0 38px 21px 0; color:#929292; font-size:10px; line-height:1.85; }
.hiw-flux-cta {
  position:relative;
  display:flex;
  min-height:410px;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  overflow:hidden;
  padding:92px 20px;
  border-top:1px solid #292929;
  border-bottom:1px solid #292929;
  background:linear-gradient(135deg,#151515,#090909 60%,#1b1b1b);
  text-align:center;
  isolation:isolate;
}
.hiw-flux-grid {
  position:absolute;
  inset:0;
  z-index:-1;
  opacity:.22;
  background-image:radial-gradient(#fff 1px,transparent 1.2px);
  background-size:24px 24px;
  mask-image:radial-gradient(ellipse at center,#000,transparent 78%);
}
.hiw-flux-cta > .hiw-eyebrow { justify-content:center; }
.hiw-flux-cta h2 { margin:0; color:#eee; font-size:clamp(34px,5.2vw,58px); font-weight:540; letter-spacing:-.065em; line-height:1.05; }
.hiw-flux-cta h2 span { color:#8e8e8e; }
.hiw-flux-description { max-width:500px; margin:16px auto 0; color:#969696; font-size:11px; line-height:1.8; }
.hiw-flux-cta .hiw-hero-actions { margin-top:26px; }
.hiw-flux-primary { border-color:#fff; color:#fff !important; background:#222; }
.hiw-flux-primary:hover { color:#fff !important; border-color:#fff; filter:brightness(1.15); }
.hiw-signature { width:100%; background:#050505; }
.hiw-signature-main {
  display:grid;
  grid-template-columns:minmax(240px,1.5fr) repeat(2,minmax(145px,.65fr));
  gap:50px;
  width:min(100% - 48px,1160px);
  margin:0 auto;
  padding:60px 0 40px;
}
.hiw-signature-brand p { max-width:320px; margin:16px 0 0; color:#777; font-size:10px; line-height:1.75; }
.hiw-signature-note { display:block; margin-top:18px; color:#626262; font:8px var(--font-mono); letter-spacing:.09em; }
.hiw-signature-column { display:grid; align-content:start; gap:12px; }
.hiw-signature-column > strong { margin:5px 0 7px; color:#777; font:8px var(--font-mono); letter-spacing:.12em; }
.hiw-signature-column a { display:inline-flex; align-items:center; gap:5px; width:fit-content; color:#999; font-size:10px; transition:color .18s; }
.hiw-signature-column a:hover { color:#fff; }
.hiw-signature-bottom {
  display:flex;
  justify-content:space-between;
  flex-wrap:wrap;
  gap:12px;
  width:min(100% - 48px,1160px);
  margin:0 auto;
  padding:19px 0 22px;
  border-top:1px solid #292929;
  color:#666;
  font:8px var(--font-mono);
  letter-spacing:.08em;
}
.hiw-signature-bottom a { color:#aaa; }
.hiw-signature-bottom a:hover { color:#fff; }

@media (max-width:900px) {
  .hiw-data-diagram { grid-template-columns:minmax(0,1fr) 190px minmax(0,1fr); }
  .hiw-converge { grid-template-columns:minmax(0,1fr) 150px minmax(0,.55fr); gap:8px; padding:15px; }
  .hiw-converge-source { padding:8px; }
  .hiw-converge-source strong { font-size:8px; }
  .hiw-converge-source small { font-size:7px; }
  .hiw-converge-core { padding:10px; }
  .hiw-resolve { gap:35px; }
}
@media (max-width:700px) {
  .hiw-nav-links,.hiw-nav-cta { display:none; }
  .hiw-mobile-menu-button { display:grid; }
  .hiw-launch-hero { width:min(100% - 34px,1050px); padding:105px 0 104px; }
  .hiw-launch-hero h1 { font-size:clamp(43px,11vw,68px); }
  .hiw-launch-hero .hiw-hero-copy { font-size:12px; }
  .hiw-launch-hero .hiw-hero-meta { margin-top:54px; }
  .hiw-pathflow { height:290px; opacity:.48; }
  .hiw-data-diagram { grid-template-columns:1fr; gap:12px; padding:18px 16px 49px; }
  .hiw-data-diagram > svg { display:none; }
  .hiw-data-core { grid-row:1; min-height:160px; }
  .hiw-data-side { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .hiw-flow-node { min-height:72px; }
  .hiw-flow-node strong { font-size:9px; }
  .hiw-flow-node small { font-size:8px; }
  .hiw-branch { padding:17px 12px 0; overflow-x:auto; }
  .hiw-branch-root { min-width:260px; }
  .hiw-branch > svg { width:1000px; height:250px; }
  .hiw-branch-grid { min-width:1000px; }
  .hiw-standalone { margin-left:0; }
  .hiw-pipeline { overflow-x:auto; }
  .hiw-pipeline-canvas { width:760px; min-width:760px; transform-origin:top left; }
  .hiw-origin { min-height:540px; }
  .hiw-origin > svg { height:100%; }
  .hiw-origin-nodes { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .hiw-origin-node { min-height:100px; }
  .hiw-converge { display:flex; flex-direction:column; gap:12px; padding:12px 12px 52px; }
  .hiw-converge-sources { width:100%; grid-template-columns:repeat(2,minmax(0,1fr)); }
  .hiw-converge-wires { display:none; }
  .hiw-converge-core { width:min(100%,260px); min-height:120px; }
  .hiw-converge-output { width:min(100%,260px); }
  .hiw-nexus { min-height:430px; }
  .hiw-nexus-node { width:112px; min-height:82px; padding:8px; gap:5px; }
  .hiw-nexus-node strong { font-size:8px; }
  .hiw-nexus-node small { font-size:7px; }
  .hiw-nexus-center { width:142px; min-height:128px; }
  .hiw-nexus-center strong { font-size:10px; }
  .hiw-flowlist-scroll { max-height:380px; }
  .hiw-flowlist-item { min-height:70px; padding:10px; gap:9px; }
  .hiw-flowlist-copy strong { font-size:9px; }
  .hiw-flowlist-copy small { font-size:8px; }
  .hiw-resolve { grid-template-columns:1fr; gap:25px; }
  .hiw-resolve-aside { position:static; }
  .hiw-resolve-aside h3 { max-width:none; }
  .hiw-flux-cta { min-height:365px; padding:75px 17px; }
  .hiw-signature-main { grid-template-columns:repeat(2,minmax(0,1fr)); gap:35px 20px; width:min(100% - 34px,1160px); padding-top:45px; }
  .hiw-signature-brand { grid-column:1 / -1; }
  .hiw-signature-bottom { width:min(100% - 34px,1160px); font-size:7px; }
}
@media (prefers-reduced-motion:reduce) {
  .hiw-page *, .hiw-page *::before, .hiw-page *::after {
    scroll-behavior:auto !important;
    animation-duration:.01ms !important;
    animation-iteration-count:1 !important;
    transition-duration:.01ms !important;
  }
}
`;

export function HowItWorksStyles() {
  return <style id="how-it-works-styles" dangerouslySetInnerHTML={{ __html: styles }} />;
}

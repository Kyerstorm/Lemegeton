import { useDialogFocus } from "../Hooks/useDialogFocus";
import { Icon } from "../Icons";
import { LogoTraceLoader } from "../UI/LogoTraceLoader";
import { Watcher } from "../UI";
import { PAGES, type Page } from "./navigation";

export interface DashboardSidebarProps {
  page: Page;
  mobileNav: boolean;
  commandCount: number;
  runtimeOnline: boolean;
  systemStatus?: string;
  botReady: boolean;
  botModerator: boolean;
  canManageServer: boolean;
  runtimeStatus: string;
  onNavigate: (page: Page) => void;
  onCloseNavigation: () => void;
  onLogout: () => void;
}

export function Sidebar({
  page,
  mobileNav,
  commandCount,
  runtimeOnline,
  systemStatus,
  botReady,
  botModerator,
  canManageServer,
  runtimeStatus,
  onNavigate,
  onCloseNavigation,
  onLogout,
}: DashboardSidebarProps) {
  const sidebarRef = useDialogFocus(mobileNav, ".main-nav .nav-item", onCloseNavigation);

  return (
    <aside
      ref={sidebarRef}
      className={"sidebar" + (mobileNav ? " mobile-open" : "")}
      id="sidebar"
      role={mobileNav ? "dialog" : undefined}
      aria-modal={mobileNav || undefined}
      aria-label={mobileNav ? "Dashboard navigation" : undefined}
      tabIndex={-1}
    >
      <div className="sidebar-brand-row">
        <a className="brand" href="/" aria-label="Lemegeton dashboard home"><span className="brand-mark"><LogoTraceLoader size={33} strokeWidth={16} loading={false} isComplete ariaLabel="Lemegeton logo" /></span><span className="brand-copy"><strong>LEMEGETON</strong><small className="brand-tagline">MULTI-GUILD CONTROL</small></span></a>
        <Watcher size={30} shape="Circle" eyes="Dots" eyeScale={0.85} follow={55} bounce={25} within=".app-shell" />
      </div>
      <div className="sidebar-rule" />
      <p className="nav-label">WORKSPACE <span>/ 01</span></p>
      <nav className="main-nav" aria-label="Dashboard navigation">
        {PAGES.filter((item) => (botModerator || (item.id !== "logs" && item.id !== "integrations"))
          && (canManageServer || item.id === "settings" || (botModerator && (item.id === "logs" || item.id === "integrations")))).map((item) => <button key={item.id} type="button" className={"nav-item" + (page === item.id ? " active" : "")} onClick={() => onNavigate(item.id)} aria-current={page === item.id ? "page" : undefined}>
          <span className="nav-glyph" aria-hidden="true"><Icon name={item.icon} size={17} /></span><span>{item.label}</span>
          {item.id === "commands" ? <span className="nav-count">{commandCount || "—"}</span> : null}
          {item.id === "atlas" ? <span className="nav-count"><Icon name="arrow-up-right" size={12} /></span> : null}
        </button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-system"><span className={"signal-dot" + (runtimeOnline ? " online" : "")} /><div><strong>{systemStatus === "unknown" ? "Bot signal unavailable" : botReady ? "Gateway connected" : "Bot connecting"}</strong><small>{systemStatus === "unknown" ? "STATUS / UNKNOWN" : "SYSTEM / " + runtimeStatus}</small></div></div>
      <button className="signout" type="button" onClick={onLogout}>Sign out <Icon name="arrow-up-right" size={13} /></button>
    </aside>
  );
}

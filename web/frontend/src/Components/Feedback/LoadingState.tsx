import type { CSSProperties } from "react";
import { LogoTraceLoader } from "../UI/LogoTraceLoader";

export interface SkeletonProps {
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
  radius?: CSSProperties["borderRadius"];
  className?: string;
}

export function Skeleton({ width, height, radius, className }: SkeletonProps) {
  const style: CSSProperties = {
    ...(width === undefined ? {} : { width }),
    ...(height === undefined ? {} : { height }),
    ...(radius === undefined ? {} : { borderRadius: radius }),
  };
  return <span className={"skeleton" + (className ? " " + className : "")} style={style} aria-hidden="true" />;
}

export function LoadingState({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div className="loading-state-block" role="status" aria-live="polite" aria-label={label}>
      {Array.from({ length: Math.max(1, Math.min(rows, 8)) }, (_, index) => (
        <div className="loading-state-row" key={index}>
          <Skeleton width={index % 2 ? "44%" : "62%"} height={9} />
          <Skeleton width="24%" height={18} radius={99} />
        </div>
      ))}
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="app-shell dashboard-skeleton" role="status" aria-live="polite" aria-label="Preparing the Lemegeton dashboard">
      <aside className="sidebar" aria-hidden="true">
        <div className="brand">
          <LogoTraceLoader size={41} strokeWidth={18} loading ariaLabel="Loading Lemegeton logo" />
          <span className="brand-copy"><Skeleton width={108} height={9} /><Skeleton width={74} height={7} /></span>
        </div>
        <div className="sidebar-rule" />
        <div className="nav-label"><Skeleton width={92} height={8} /></div>
        <nav className="main-nav">{Array.from({ length: 9 }, (_, index) => (
          <div className="nav-item" key={index}><Skeleton width={17} height={17} radius={4} /><Skeleton width={index === 2 || index === 4 || index === 6 ? 104 : 82} height={9} /></div>
        ))}</nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-system"><Skeleton width={8} height={8} radius="50%" /><span className="brand-copy"><Skeleton width={112} height={8} /><Skeleton width={76} height={7} /></span></div>
        <Skeleton width="100%" height={36} radius={9} />
      </aside>
      <main className="main">
        <header className="topbar" aria-hidden="true"><Skeleton width={124} height={9} /><div className="topbar-right"><Skeleton width={158} height={36} radius={9} /><Skeleton width={36} height={36} radius={9} /><Skeleton width={124} height={36} radius={20} /></div></header>
        <div className="braille-band skeleton-band" aria-hidden="true"><Skeleton width="100%" height={10} /></div>
        <section className="page" aria-hidden="true">
          <div className="page-heading skeleton-heading"><div className="page-heading-copy"><Skeleton width={92} height={8} /><Skeleton width="min(360px, 78%)" height={38} /><Skeleton width="min(520px, 92%)" height={9} /></div><div className="heading-actions"><Skeleton width={106} height={39} radius={9} /><Skeleton width={142} height={39} radius={9} /></div></div>
          <div className="status-strip skeleton-status"><Skeleton width={7} height={7} radius="50%" /><Skeleton width={104} height={8} /><Skeleton width="42%" height={8} /><Skeleton width={54} height={8} /></div>
          <div className="metric-grid">{Array.from({ length: 4 }, (_, index) => <article className="metric" key={index}><Skeleton width="62%" height={8} /><Skeleton width="42%" height={31} className="metric-value-skeleton" /><Skeleton width="76%" height={8} /></article>)}</div>
          <div className="content-grid">
            <article className="panel panel-large skeleton-panel"><div className="panel-heading"><div><Skeleton width={90} height={8} /><Skeleton width={138} height={14} /></div><Skeleton width={46} height={8} /></div><Skeleton width={74} height={74} radius={18} /><Skeleton width="72%" height={9} /><Skeleton width="90%" height={8} /><Skeleton width="54%" height={8} /><div className="skeleton-divider" /><div className="skeleton-inline"><Skeleton width="27%" height={8} /><Skeleton width="27%" height={8} /><Skeleton width="27%" height={8} /></div></article>
            <article className="panel skeleton-panel"><div className="panel-heading"><div><Skeleton width={90} height={8} /><Skeleton width={118} height={14} /></div></div><Skeleton width="100%" height={12} /><Skeleton width="92%" height={12} /><Skeleton width="76%" height={12} /><Skeleton width="86%" height={12} /></article>
            <article className="panel skeleton-panel"><div className="panel-heading"><div><Skeleton width={100} height={8} /><Skeleton width={126} height={14} /></div></div><Skeleton width="46%" height={30} /><Skeleton width="100%" height={6} /><div className="skeleton-inline"><Skeleton width="35%" height={8} /><Skeleton width="35%" height={8} /></div></article>
            <article className="panel skeleton-panel"><div className="panel-heading"><div><Skeleton width={88} height={8} /><Skeleton width={116} height={14} /></div></div><Skeleton width="100%" height={9} /><Skeleton width="82%" height={9} /><Skeleton width="92%" height={9} /></article>
          </div>
        </section>
      </main>
      <span className="sr-only">Loading dashboard content.</span>
    </div>
  );
}

import type { ReactNode } from "react";
import { InView, ScrollProgress } from "../UI";

export interface DashboardShellProps {
  pageKey: string;
  sidebar: ReactNode;
  topbar: ReactNode;
  mobileNavigation?: ReactNode;
  overlays?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

export function DashboardShell({ pageKey, sidebar, topbar, mobileNavigation, overlays, footer, children }: DashboardShellProps) {
  return (
    <div className="app-shell">
      {sidebar}
      {mobileNavigation}
      <main className="main">
        <div className="dashboard-scroll-progress" aria-hidden="true">
          <ScrollProgress className="dashboard-scroll-progress-fill" />
        </div>
        {topbar}
        <InView
          key={pageKey}
          className="dashboard-page-transition"
          variants={{
            hidden: { opacity: 0, y: 6 },
            visible: { opacity: 1, y: 0 },
          }}
          transition={{ duration: 0.2, ease: "easeOut" }}
        >
          {children}
        </InView>
        {footer}
      </main>
      {overlays}
    </div>
  );
}

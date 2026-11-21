import type { ReactNode } from "react";

export interface StatusPillProps {
  ok?: boolean;
  children: ReactNode;
}

export function StatusPill({ ok, children }: StatusPillProps) {
  const statusClass = ok === true ? "is-good" : ok === false ? "is-bad" : "is-neutral";

  return (
    <span className={"status-pill " + statusClass}>
      <i aria-hidden="true" />
      {children}
    </span>
  );
}

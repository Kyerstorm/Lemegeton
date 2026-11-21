import type { ReactNode } from "react";

export interface EmptyProps {
  children: ReactNode;
  loading?: boolean;
}

export function Empty({ children, loading = false }: EmptyProps) {
  return (
    <div className={"empty-state" + (loading ? " loading-state" : "")}>
      {loading ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </div>
  );
}

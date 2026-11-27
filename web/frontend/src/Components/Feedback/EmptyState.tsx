import type { ReactNode } from "react";
import { Skeleton } from "./LoadingState";

export interface EmptyStateProps {
  children: ReactNode;
  loading?: boolean;
}

export function EmptyState({ children, loading = false }: EmptyStateProps) {
  return (
    <div className={"empty-state" + (loading ? " loading-state" : "")} role={loading ? "status" : undefined} aria-live={loading ? "polite" : undefined}>
      {children}
      {loading ? (
        <span className="empty-skeleton" aria-hidden="true">
          <Skeleton width="78%" height={8} />
          <Skeleton width="56%" height={8} />
        </span>
      ) : null}
    </div>
  );
}

export const Empty = EmptyState;

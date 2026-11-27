"use client";

import type { ReactNode } from "react";
import { useSession } from "./useSession";
import { DashboardSkeleton } from "../../Feedback/LoadingState";
import { ErrorState } from "../../Feedback/ErrorState";
import { LoginScreen } from "./LoginScreen";

export function SessionGuard({ children, onRetry }: { children: ReactNode; onRetry: () => void }) {
  const session = useSession();
  if (session.loading) return <DashboardSkeleton />;
  if (session.error) return <ErrorState title="Could not establish your dashboard session." description={session.error} onRetry={onRetry} />;
  if (!session.user) return <LoginScreen />;
  return <>{children}</>;
}

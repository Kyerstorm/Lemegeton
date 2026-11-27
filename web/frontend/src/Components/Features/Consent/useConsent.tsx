"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { DashboardConsent } from "../../../Types/dashboard";

export interface ConsentState {
  consent: DashboardConsent | null;
  saving: boolean;
  checking: boolean;
  error: string;
  onRetry: () => void;
  onAccept: () => void;
  onDecline: () => void;
}

const ConsentContext = createContext<ConsentState | null>(null);

export function ConsentProvider({ value, children }: { value: ConsentState; children: ReactNode }) {
  return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>;
}

export function useConsent(): ConsentState {
  const value = useContext(ConsentContext);
  if (!value) throw new Error("useConsent must be used inside ConsentProvider.");
  return value;
}

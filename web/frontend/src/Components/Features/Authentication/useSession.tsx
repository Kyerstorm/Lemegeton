"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Guild, User } from "../../../Types/dashboard";

export interface DashboardSession {
  user: User | null;
  guilds: Guild[];
  guildId: string;
  csrf: string;
  botModerator: boolean;
  loading: boolean;
  error: string;
}

const SessionContext = createContext<DashboardSession | null>(null);

export function SessionProvider({ value, children }: { value: DashboardSession; children: ReactNode }) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): DashboardSession {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider.");
  return value;
}

"use client";

import { createContext, useContext, type ReactNode } from "react";

export type DashboardTheme = "monochrome";
const ThemeContext = createContext<DashboardTheme>("monochrome");

export function ThemeProvider({ children }: { children: ReactNode }) {
  return <ThemeContext.Provider value="monochrome">{children}</ThemeContext.Provider>;
}

export function useTheme(): DashboardTheme {
  return useContext(ThemeContext);
}

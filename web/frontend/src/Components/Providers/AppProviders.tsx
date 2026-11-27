import type { ReactNode } from "react";
import { GlobalStyles } from "../DesignSystem/GlobalStyles";
import { SensoryUIProvider } from "../DesignSystem/SensoryUI/config/provider";
import { CookieConsentManager } from "../Features/Consent/CookieConsentManager";
import { ThemeProvider } from "../DesignSystem/ThemeProvider";
import { SensoryInteractions } from "./SensoryInteractions";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <SensoryUIProvider config={{ theme: "minimal", volume: 0.18, reducedMotion: "inherit" }}>
      <>
        <GlobalStyles />
        <ThemeProvider>{children}</ThemeProvider>
        <CookieConsentManager />
        <SensoryInteractions />
      </>
    </SensoryUIProvider>
  );
}

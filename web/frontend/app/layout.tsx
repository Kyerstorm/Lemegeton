import type { Metadata } from "next";
import "../src/Components/DesignSystem/fonts.css";
import "../src/Components/Features/Status/status.css";
import { AppProviders } from "../src/Components/Providers/AppProviders";

export const metadata: Metadata = {
  title: "Lemegeton / Control",
  description: "Private control plane for the Lemegeton Discord bot.",
  robots: { index: false, follow: false },
  icons: { icon: "/icon.svg", apple: "/apple-touch-icon.png" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppProviders>{children}</AppProviders></body></html>;
}

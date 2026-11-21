import type { Metadata } from "next";
import { GlobalStyles } from "../src/DesignSystem/GlobalStyles";

export const metadata: Metadata = {
  title: "Lemegeton / Control",
  description: "Private control plane for the Lemegeton Discord bot.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><GlobalStyles />{children}</body></html>;
}

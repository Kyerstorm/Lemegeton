import type { Metadata } from "next";
import { HowItWorksPage } from "../../src/Components/Features/HowItWorks/HowItWorksPage";
import { HowItWorksStyles } from "../../src/Components/Features/HowItWorks/HowItWorksStyles";

export const metadata: Metadata = {
  title: "How Lemegeton works",
  description: "Explore Lemegeton's Discord bot architecture, multi-guild design, provider integrations, storage boundaries and optional web dashboard.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/how-it-works" },
};

export default function HowItWorksRoute() {
  return (
    <>
      <HowItWorksStyles />
      <HowItWorksPage />
    </>
  );
}

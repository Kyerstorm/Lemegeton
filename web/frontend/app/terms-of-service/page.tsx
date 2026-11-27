import type { Metadata } from "next";
import { PolicyPage } from "../../src/Components/Features/Consent/PolicyPage";

export const metadata: Metadata = {
  title: "Terms of Service | Lemegeton",
  robots: { index: true, follow: true },
  alternates: { canonical: "/terms-of-service" },
};

export default function TermsOfServicePage() {
  return <PolicyPage filename="TERMS_OF_SERVICE.md" />;
}

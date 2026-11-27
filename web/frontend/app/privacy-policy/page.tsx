import type { Metadata } from "next";
import { PolicyPage } from "../../src/Components/Features/Consent/PolicyPage";

export const metadata: Metadata = {
  title: "Privacy Policy | Lemegeton",
  robots: { index: true, follow: true },
  alternates: { canonical: "/privacy-policy" },
};

export default function PrivacyPolicyPage() {
  return <PolicyPage filename="PRIVACY_POLICY.md" />;
}

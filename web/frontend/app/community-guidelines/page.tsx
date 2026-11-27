import type { Metadata } from "next";
import { PolicyPage } from "../../src/Components/Features/Consent/PolicyPage";

export const metadata: Metadata = {
  title: "Community Guidelines | Lemegeton",
  robots: { index: true, follow: true },
  alternates: { canonical: "/community-guidelines" },
};

export default function CommunityGuidelinesPage() {
  return <PolicyPage filename="COMMUNITY_GUIDELINES.md" />;
}

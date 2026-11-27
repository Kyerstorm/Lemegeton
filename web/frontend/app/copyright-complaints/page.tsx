import type { Metadata } from "next";
import { PolicyPage } from "../../src/Components/Features/Consent/PolicyPage";

export const metadata: Metadata = {
  title: "Copyright & Content Complaints | Lemegeton",
  robots: { index: true, follow: true },
  alternates: { canonical: "/copyright-complaints" },
};

export default function CopyrightComplaintsPage() {
  return <PolicyPage filename="COPYRIGHT_AND_CONTENT_COMPLAINTS.md" />;
}

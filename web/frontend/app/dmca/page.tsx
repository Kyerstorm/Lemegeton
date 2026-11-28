import type { Metadata } from "next";
import { PolicyPage } from "../../src/Components/Features/Consent/PolicyPage";

export const metadata: Metadata = {
  title: "DMCA & Copyright Policy | Lemegeton",
  robots: { index: true, follow: true },
  alternates: { canonical: "/dmca" },
};

export default function DmcaPage() {
  return <PolicyPage filename="DMCA.md" />;
}

import type { Metadata } from "next";
import { StatusPage } from "../../src/Components/Features/Status/StatusPage";

export const metadata: Metadata = {
  title: "System status | Lemegeton",
  description: "Live availability checks for Lemegeton services.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/status" },
};

export default function StatusPageRoute() {
  return <StatusPage />;
}

import type { Metadata } from "next";
import App from "../src/App";

export const metadata: Metadata = {
  title: "Dashboard | Lemegeton",
  description: "Manage your Lemegeton bot across Discord servers.",
  robots: { index: false, follow: false },
  alternates: { canonical: "/" },
};

export default function DashboardPage() {
  return <App />;
}

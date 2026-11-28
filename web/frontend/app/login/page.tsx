import type { Metadata } from "next";
import App from "../../src/App";

export const metadata: Metadata = {
  title: "Sign in | Lemegeton",
  description: "Sign in with Discord to manage your Lemegeton servers.",
  robots: { index: false, follow: false },
  alternates: { canonical: "/login" },
};

export default function LoginPage() {
  return <App />;
}

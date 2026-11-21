import type { Metadata } from "next";
import { CustomRolesClient } from "../../src/Components/CustomRoles/CustomRolesClient";

export const metadata: Metadata = {
  title: "Custom Role Studio · Lemegeton",
  description: "Securely customize your Lemegeton server role.",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

export default function CustomRolesPage() {
  return <CustomRolesClient />;
}

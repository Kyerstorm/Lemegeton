import type { Metadata } from "next";
import { RoleStudio } from "../../src/Components/Features/CustomRoles/RoleStudio";

export const metadata: Metadata = {
  title: "Custom Role Studio · Lemegeton",
  description: "Securely customize your Lemegeton server role.",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
  alternates: { canonical: "/custom-roles" },
};

export default function CustomRolesPage() {
  return <RoleStudio />;
}

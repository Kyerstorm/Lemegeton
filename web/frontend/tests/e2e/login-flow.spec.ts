import { expect, test } from "@playwright/test";

test("login explains Discord access and links the required policies", async ({ page }) => {
  await page.goto("/login");

  const heading = page.getByRole("heading", { name: /One place/ });
  await expect(heading).toBeVisible();
  await expect(heading).toContainText("Every server.");
  const continueButton = page.getByRole("button", { name: /Continue with Discord/ });
  await expect(continueButton).toBeVisible();

  const form = page.locator("form.login-v2-form");
  await expect(form).toHaveAttribute("action", "/oauth/start");
  await expect(form).toHaveAttribute("method", "post");

  const agreement = page.getByRole("note", { name: "Sign-in agreement" });
  await expect(agreement.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms-of-service");
  await expect(agreement.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy-policy");
  await expect(agreement.getByRole("link", { name: "Community Guidelines" })).toHaveAttribute("href", "/community-guidelines");
  await expect(page.getByRole("link", { name: "SYSTEM STATUS" })).toHaveAttribute("href", "/status");

  // OAuth is intentionally not submitted by this isolated browser test.
});

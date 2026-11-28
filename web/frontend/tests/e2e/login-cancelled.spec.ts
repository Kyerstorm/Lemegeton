import { expect, test } from "@playwright/test";

test("a cancelled Discord sign-in returns a clear, non-destructive notice", async ({ page }) => {
  await page.goto("/login?error=cancelled");

  await expect(page.getByText("Sign-in was cancelled. Nothing has been changed.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Continue with Discord/ })).toBeVisible();
  await expect(page.locator("form.login-v2-form")).toHaveAttribute("action", "/oauth/start");
});

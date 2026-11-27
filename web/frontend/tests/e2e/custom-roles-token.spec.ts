import { expect, test } from "@playwright/test";

test("the picker moves a fragment token to a bearer header and clears it on expiry", async ({ page }) => {
  const token = "opaque-e2e-picker-token";
  let requestUrl = "";
  let authorization = "";

  await page.route("**/custom-roles/api/state", async route => {
    requestUrl = route.request().url();
    authorization = route.request().headers().authorization || "";
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ message: "The test picker link has expired." }),
    });
  });

  await page.goto(`/custom-roles/#${token}`);

  await expect(page.locator("#problem-title")).toHaveText("This link expired");
  await expect(page.locator("#problem")).toBeVisible();
  await expect.poll(() => new URL(page.url()).hash).toBe("");
  expect(requestUrl).toContain("/custom-roles/api/state");
  expect(requestUrl).not.toContain(token);
  expect(authorization).toBe(`Bearer ${token}`);
  expect(await page.evaluate(() => window.sessionStorage.getItem("customRolePickerToken"))).toBeNull();
});

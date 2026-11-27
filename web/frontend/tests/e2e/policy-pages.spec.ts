import { expect, test } from "@playwright/test";

test("legal pages render their source text and preserve internal policy links", async ({ page, request }) => {
  await page.goto("/terms-of-service");

  const terms = page.locator(".legal-content");
  await expect(terms.getByRole("heading", { level: 1, name: "Lemegeton Terms of Service" })).toBeVisible();

  await terms.getByRole("link", { name: "Privacy Policy", exact: true }).first().click();
  await expect(page).toHaveURL(/\/privacy-policy$/);

  const privacy = page.locator(".legal-content");
  await expect(privacy.getByRole("heading", { level: 1, name: "Lemegeton Privacy Policy" })).toBeVisible();
  const policyNavigation = page.getByRole("navigation", { name: "Legal documents" });
  await expect(policyNavigation.getByRole("link", { name: "Community Guidelines" })).toHaveAttribute(
    "href",
    "/community-guidelines",
  );
});


test("policy and public guide slash variants redirect to extensionless URLs", async ({ request }) => {
  for (const path of [
    "/login/",
    "/how-it-works/",
    "/terms-of-service/",
    "/privacy-policy/",
    "/community-guidelines/",
    "/copyright-complaints/",
    "/dmca/",
  ]) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), path).toBe(308);
    expect(response.headers().location, path).toBe(path.slice(0, -1));
  }

  const legacyGuide = await request.get("/How-it-works/", { maxRedirects: 0 });
  expect(legacyGuide.status()).toBe(308);
  expect(legacyGuide.headers().location).toBe("/how-it-works");
});

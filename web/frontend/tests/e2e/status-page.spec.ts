import { expect, test } from "@playwright/test";

test("the public status page renders real response fields and can refresh", async ({ page }) => {
  let checks = 0;
  await page.route("**/api/status", async route => {
    checks += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "operational",
        observed_at: 1795680000,
        components: [{
          id: "dashboard-api",
          name: "Dashboard API",
          status: "operational",
          detail: "Authenticated dashboard requests are responding.",
          latency_ms: 28,
        }],
      }),
    });
  });

  await page.goto("/status");
  await expect(page).toHaveURL(/\/status$/);
  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();
  await expect(page.getByText("Dashboard API")).toBeVisible();
  await expect(page.getByText("28 ms")).toBeVisible();
  await expect.poll(() => checks).toBe(1);

  await page.getByRole("button", { name: "Refresh" }).click();
  await expect.poll(() => checks).toBe(2);
});


test("legacy status URLs redirect to the clean public route", async ({ request }) => {
  for (const path of ["/status/", "/status.html", "/status/index.html"]) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), path).toBe(308);
    expect(response.headers().location, path).toBe("/status");
  }
});

import { expect, test } from "@playwright/test";

const snapshot = {
  status: "operational",
  observed_at: 1795680000,
  components: [{
    id: "dashboard-api",
    name: "Dashboard API",
    status: "operational",
    detail: "Authenticated dashboard requests are responding.",
    latency_ms: 28,
  }],
};

test("a failed first status check can recover after a manual refresh", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/status", async route => {
    requests += 1;
    if (requests === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "Unavailable" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    });
  });

  await page.goto("/status");
  await expect(page.getByRole("heading", { name: "Live status unavailable" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh" }).click();

  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();
  await expect(page.getByText("Dashboard API")).toBeVisible();
  expect(requests).toBe(2);
});

test("a failed refresh marks the previous successful snapshot as stale", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/status", async route => {
    requests += 1;
    if (requests > 1) {
      await route.fulfill({ status: 503, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    });
  });

  await page.goto("/status");
  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh" }).click();

  await expect(page.getByText("Showing the last successful check. The latest refresh failed.")).toBeVisible();
  await expect(page.getByText("Dashboard API")).toBeVisible();
  expect(requests).toBe(2);
});


test("the status skeleton remains visible on throttled mobile hardware while a slow response is pending", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let releaseResponse!: () => void;
  const responsePending = new Promise<void>(resolve => {
    releaseResponse = resolve;
  });

  await page.route("**/api/status", async route => {
    await responsePending;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(snapshot),
    });
  });

  await page.goto("/status");

  const browserSession = await page.context().newCDPSession(page);
  await browserSession.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await browserSession.send("Network.enable");
  await browserSession.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 450,
    downloadThroughput: 400 * 1024 / 8,
    uploadThroughput: 100 * 1024 / 8,
    connectionType: "cellular3g",
  });

  await expect(page.getByRole("heading", { name: "Checking Lemegeton systems" })).toBeVisible();
  await expect(page.locator(".status-loading")).toBeVisible();
  releaseResponse();
  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();
});

test("the public status page has no horizontal overflow in a short landscape viewport", async ({ page }) => {
  await page.setViewportSize({ width: 844, height: 390 });
  await page.route("**/api/status", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(snapshot),
  }));

  await page.goto("/status");
  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();
  const overflowsHorizontally = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflowsHorizontally).toBe(false);
});

test("the status page compacts its vertical spacing on short landscape screens", async ({ page }) => {
  await page.setViewportSize({ width: 844, height: 390 });
  await page.route("**/api/status", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(snapshot),
  }));

  await page.goto("/status");
  await expect(page.getByRole("heading", { name: "All monitored systems operational" })).toBeVisible();

  const spacing = await page.locator(".status-header").evaluate(element => ({
    marginBottom: getComputedStyle(element).marginBottom,
    shellPaddingTop: getComputedStyle(document.querySelector(".status-page-shell")!).paddingTop,
  }));
  expect(spacing).toEqual({ marginBottom: "20px", shellPaddingTop: "12px" });
});

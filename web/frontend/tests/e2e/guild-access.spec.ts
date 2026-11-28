import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("a guild absent from the caller's permitted guild list is not opened", async ({ page }) => {
  const fixture = await installDashboardMocks(page);

  await page.goto(`/${dashboardFixture.userId}/${dashboardFixture.inaccessibleGuildId}/`);

  await expect.poll(() => new URL(page.url()).pathname).toBe("/");
  await expect.poll(() => fixture.settingsRequests.length).toBeGreaterThan(0);
  expect(fixture.settingsRequests).not.toContain(dashboardFixture.inaccessibleGuildId);
  expect(fixture.settingsRequests).toContain(dashboardFixture.guildId);
});

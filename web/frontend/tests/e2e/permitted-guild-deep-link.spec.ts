import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("a permitted, installed guild can be opened through its deep link", async ({ page }) => {
  const fixture = await installDashboardMocks(page);

  await page.goto("/" + dashboardFixture.userId + "/" + dashboardFixture.guildId + "/");

  await expect.poll(() => fixture.settingsRequests.includes(dashboardFixture.guildId)).toBe(true);
  await expect(page).toHaveURL(
    new RegExp("/" + dashboardFixture.userId + "/" + dashboardFixture.guildId + "/$"),
  );
  expect(fixture.settingsRequests).not.toContain(dashboardFixture.inaccessibleGuildId);
});

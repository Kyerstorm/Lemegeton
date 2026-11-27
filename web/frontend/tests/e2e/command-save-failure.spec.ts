import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("a rejected command save keeps the user's draft available for retry", async ({ page }) => {
  const fixture = await installDashboardMocks(page, { commandSaveStatus: 409 });
  await page.goto("/" + dashboardFixture.userId + "/" + dashboardFixture.guildId + "/");

  const navigation = page.getByRole("navigation", { name: "Dashboard navigation" });
  await navigation.getByRole("button", { name: "Commands" }).click();

  const browseSwitch = page.getByRole("switch", { name: "Toggle browse" });
  await expect(browseSwitch).toHaveAttribute("aria-checked", "true");
  await browseSwitch.click();
  await expect(browseSwitch).toHaveAttribute("aria-checked", "false");

  await page.getByRole("button", { name: "Save Changes" }).click();

  await expect(page.locator(".toast-stack")).toContainText("The command revision is stale.");
  await expect(browseSwitch).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("region", { name: "Unsaved command changes" })).toBeVisible();
  expect(fixture.commandSaves).toHaveLength(1);
});

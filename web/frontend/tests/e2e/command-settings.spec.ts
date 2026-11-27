import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("a command change stays local until explicitly saved", async ({ page }) => {
  const fixture = await installDashboardMocks(page);
  await page.goto(`/${dashboardFixture.userId}/${dashboardFixture.guildId}/`);

  const navigation = page.getByRole("navigation", { name: "Dashboard navigation" });
  await navigation.getByRole("button", { name: "Commands" }).click();

  const browseSwitch = page.getByRole("switch", { name: "Toggle browse" });
  await expect(browseSwitch).toBeVisible();
  await expect(browseSwitch).toHaveAttribute("aria-checked", "true");

  await browseSwitch.click();
  await expect(browseSwitch).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("region", { name: "Unsaved command changes" })).toBeVisible();

  await page.getByRole("button", { name: "Save Changes" }).click();
  await expect.poll(() => fixture.commandSaves.length).toBe(1);
  expect(fixture.commandSaves[0]).toEqual({
    expected_revision: "revision-1",
    updates: [{ fullname: "browse", enabled: false }],
  });
  await expect(page.getByText("Saved and synchronized 1 command change.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Unsaved command changes" })).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe(`/${dashboardFixture.userId}/${dashboardFixture.guildId}/`);
});

import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("audit history appends older cursor pages without replacing recent events", async ({ page }) => {
  await installDashboardMocks(page);
  const requestedCursors: string[] = [];

  await page.route(
    "**/api/guilds/23456789012345678/audit**",
    async route => {
      const cursor = new URL(route.request().url()).searchParams.get("cursor");
      requestedCursors.push(cursor ?? "");

      const entries = cursor
        ? [{
            id: "98",
            action: "older_event",
            details: "Older audit event",
            actor_name: "Test moderator",
            ts: "2026-11-25T10:00:00.000Z",
          }]
        : [
            {
              id: "100",
              action: "recent_event",
              details: "Most recent audit event",
              actor_name: "Test moderator",
              ts: "2026-11-26T10:00:00.000Z",
            },
            {
              id: "99",
              action: "previous_event",
              details: "Previous audit event",
              actor_name: "Test moderator",
              ts: "2026-11-26T09:00:00.000Z",
            },
          ];

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          entries,
          next_cursor: cursor ? null : "98",
          has_more: !cursor,
        }),
      });
    },
  );

  await page.goto(`/${dashboardFixture.userId}/${dashboardFixture.guildId}/`);
  const navigation = page.getByRole("navigation", { name: "Dashboard navigation" });
  await navigation.getByRole("button", { name: "Audit history" }).click();

  await expect(page.getByText("Most recent audit event")).toBeVisible();
  await expect(page.getByText("Previous audit event")).toBeVisible();
  await page.getByRole("button", { name: /Load older events/ }).click();

  await expect(page.getByText("Older audit event")).toBeVisible();
  await expect(page.getByText("Most recent audit event")).toBeVisible();
  await expect(page.getByText("Previous audit event")).toBeVisible();
  await expect(page.getByRole("button", { name: /Load older events/ })).toHaveCount(0);
  expect(requestedCursors).toContain("98");
});

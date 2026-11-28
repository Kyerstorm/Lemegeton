import { expect, test } from "@playwright/test";
import { dashboardFixture, installDashboardMocks } from "./dashboard-fixture";

test("the former Garden route redirects and its wordmark lives in Overview", async ({ page, request }) => {
  const response = await request.get("/garden/", { maxRedirects: 0 });
  expect(response.status()).toBe(308);
  expect(response.headers().location).toBe("/");

  await installDashboardMocks(page);
  await page.goto(`/${dashboardFixture.userId}/${dashboardFixture.guildId}/`);
  const wordmark = page.locator(".overview-brand-art img[alt=\"Lemegeton typed botanical wordmark\"]");
  await expect(wordmark).toBeVisible();
  await expect(wordmark).toHaveAttribute("src", "/brand/lemegeton-garden.gif");
});

test("the animated Garden wordmark GIF is an exported brand asset", async ({ request }) => {
  const gif = await request.get("/brand/lemegeton-garden.gif");
  expect(gif.ok()).toBe(true);
  expect(gif.headers()["content-type"]).toContain("image/gif");
  expect((await gif.body()).subarray(0, 6).toString("ascii")).toBe("GIF89a");

});

test("monochrome wordmarks and the app icon are exported SVG assets", async ({ request }) => {
  for (const path of ["/brand/mark-light.svg", "/brand/mark-dark.svg", "/brand/wordmark-light.svg", "/brand/wordmark-dark.svg", "/brand/discord.svg", "/brand/texture-grid.svg", "/icon.svg"]) {
    const response = await request.get(path);
    expect(response.ok(), path).toBe(true);
    expect(response.headers()["content-type"]).toContain("image/svg+xml");
    expect(await response.text()).toContain("<svg");
  }

  const appleTouchIcon = await request.get("/apple-touch-icon.png");
  expect(appleTouchIcon.ok()).toBe(true);
  expect(appleTouchIcon.headers()["content-type"]).toContain("image/png");
  expect((await appleTouchIcon.body()).subarray(0, 8)).toEqual(
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );

  const lightMark = await request.get("/brand/mark-light.svg");
  expect(await lightMark.text()).toContain("/brand/lemegeton.svg");
  const darkMark = await request.get("/brand/mark-dark.svg");
  expect(await darkMark.text()).toContain('filter="invert(1)"');

  const lightWordmark = await request.get("/brand/wordmark-light.svg");
  expect(await lightWordmark.text()).toContain("LEMEGETON");
  const darkWordmark = await request.get("/brand/wordmark-dark.svg");
  expect(await darkWordmark.text()).toContain("LEMEGETON");
});


test("reduced-motion preference uses a static wordmark fallback", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installDashboardMocks(page);
  await page.goto(`/${dashboardFixture.userId}/${dashboardFixture.guildId}/`);
  await expect(page.locator(".overview-brand-static")).toHaveText("LEMEGETON");
  await expect(page.locator(".overview-brand-art img")).toHaveCount(0);
});

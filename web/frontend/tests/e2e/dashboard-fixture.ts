import type { Page } from "@playwright/test";

export const dashboardFixture = {
  userId: "12345678901234567",
  guildId: "23456789012345678",
  inaccessibleGuildId: "34567890123456789",
};

const command = {
  fullname: "browse",
  name: "browse",
  description: "Discover media across supported providers.",
  section: "Discover",
  type: "slash",
  scope: "guild",
  enabled: true,
  configurable: true,
  protected: false,
};

export async function installDashboardMocks(page: Page, options: { commandSaveStatus?: number } = {}) {
  const commandSaves: Array<{ expected_revision?: string; updates?: Array<{ fullname: string; enabled: boolean }> }> = [];
  const settingsRequests: string[] = [];

  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    const match = path.match(/^\/api\/guilds\/([^/]+)\/settings$/);
    if (match) settingsRequests.push(match[1]!);
  });

  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/bootstrap") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: { id: dashboardFixture.userId, username: "dashboard-test", global_name: "Dashboard Test" },
          guilds: [{
            id: dashboardFixture.guildId,
            name: "Test server",
            bot_installed: true,
            can_manage_server: true,
          }],
          selected_guild_id: dashboardFixture.guildId,
          csrf_token: "e2e-csrf",
          bot_moderator: false,
        }),
      });
      return;
    }

    if (path === "/api/consent") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          accepted: true,
          versions: { terms: "v1", privacy: "v1", guidelines: "v1" },
          policies: [],
        }),
      });
      return;
    }

    if (path === "/api/cookies") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ saved: false, remember_server: false, consent_version: "v1" }),
      });
      return;
    }

    if (path.endsWith("/settings") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          settings: { leave_action: "retain", language_code: "en" },
          setup_complete: true,
          can_choose_retention: true,
          can_manage_server: true,
          languages: [{ code: "en", label: "English" }],
        }),
      });
      return;
    }

    if (path.endsWith("/overview") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ bot: { ready: true, status: "online", latency_ms: 34, member_count: 120, guild_count: 1 } }),
      });
      return;
    }

    if (path.endsWith("/commands") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ commands: [command], revision: "revision-1" }),
      });
      return;
    }

    if (path.endsWith("/commands") && method === "PUT") {
      const payload = JSON.parse(request.postData() || "{}") as {
        expected_revision?: string;
        updates?: Array<{ fullname: string; enabled: boolean }>;
      };
      commandSaves.push(payload);
      if (options.commandSaveStatus && options.commandSaveStatus >= 400) {
        await route.fulfill({
          status: options.commandSaveStatus,
          contentType: "application/json",
          body: JSON.stringify({ error: "The command revision is stale." }),
        });
        return;
      }
      const enabled = payload.updates?.find(update => update.fullname === command.fullname)?.enabled ?? command.enabled;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ commands: [{ ...command, enabled }], revision: "revision-2" }),
      });
      return;
    }

    if (path === "/api/system" && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "operational", ready: true, reason: "", observed_at: 1795680000 }),
      });
      return;
    }

    if (path.endsWith("/audit") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ entries: [] }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: "No E2E fixture exists for this endpoint." }),
    });
  });

  return { commandSaves, settingsRequests };
}

import test from "node:test";
import assert from "node:assert/strict";
import { createServer as createNetServer } from "node:net";
import type { Client, Guild } from "discord.js";
import type { FeatureCommand } from "../helpers/commands/command.js";
import type { BotConfig } from "../helpers/runtime/config.js";
import { LanguageCommand } from "../src/commands/language.js";
import {
  dashboardCommandRows,
  dashboardSecretMatches,
  isDashboardGuildId,
  startDashboardBridge,
  stopDashboardBridge,
} from "../helpers/runtime/dashboard-bridge.js";

async function availablePort(): Promise<number> {
  const server = createNetServer();
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve());
  });
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const port = address.port;
  await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  return port;
}

test("/language is visible as protected and always enabled in dashboard command controls", () => {
  const rows = dashboardCommandRows([new LanguageCommand()], {
    discover: true, archive: true, community: true, play: true, profile: true, "custom-role": true,
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.name, "language");
  assert.equal(rows[0]?.protected, true);
  assert.equal(rows[0]?.enabled, true);
  assert.equal(rows[0]?.required_permissions, String(1 << 5));
});

test("dashboard bridge validates guild identifiers and compares bearer secrets safely", () => {
  assert.equal(isDashboardGuildId("12345678901234567"), true);
  assert.equal(isDashboardGuildId("1234567890123456"), false);
  assert.equal(isDashboardGuildId("123456789012345678901"), false);
  assert.equal(isDashboardGuildId("1234567890123456x"), false);
  assert.equal(isDashboardGuildId(12345678901234567), false);
  assert.equal(dashboardSecretMatches("a".repeat(40), "a".repeat(40)), true);
  assert.equal(dashboardSecretMatches("a".repeat(40), "b".repeat(40)), false);
  assert.equal(dashboardSecretMatches("short", "a".repeat(40)), false);
});

test("dashboard bridge rejects absent and incorrect bearer secrets and serves authenticated guild data", async () => {
  const port = await availablePort();
  const secret = "acceptance-bridge-secret-".padEnd(48, "x");
  const guild = {
    id: "12345678901234567",
    name: "Acceptance Guild",
    iconURL: () => "https://cdn.discordapp.com/icons/12345678901234567/icon.png",
    memberCount: 12,
  };
  const client = {
    isReady: () => true,
    guilds: { cache: new Map([[guild.id, guild]]) },
    ws: { ping: 24 },
  } as unknown as Client;
  const config = {
    dashboardBridgeSecret: secret,
    dashboardBridgeHost: "127.0.0.1",
    dashboardBridgePort: port,
  } as BotConfig;

  await startDashboardBridge(client, [] as FeatureCommand[], config);
  try {
    const url = "http://127.0.0.1:" + port + "/guilds";
    const missing = await fetch(url);
    assert.equal(missing.status, 401);

    const incorrect = await fetch(url, { headers: { Authorization: "Bearer " + "z".repeat(secret.length) } });
    assert.equal(incorrect.status, 401);

    const accepted = await fetch(url, { headers: { Authorization: "Bearer " + secret } });
    assert.equal(accepted.status, 200);
    const payload = await accepted.json() as Array<{ id: string; name: string; member_count: number }>;
    assert.deepEqual(payload, [{
      id: guild.id,
      name: guild.name,
      icon: "https://cdn.discordapp.com/icons/12345678901234567/icon.png",
      member_count: 12,
    }]);
  } finally {
    await stopDashboardBridge();
  }
});

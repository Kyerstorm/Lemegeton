import { REST, Routes } from "discord.js";
import { loadConfig } from "./config.js";
import { createCommandRegistry } from "./commands/registry.js";
import { logger } from "./logger.js";

async function deployCommands(): Promise<void> {
  const config = loadConfig();
  const commands = createCommandRegistry(config).map((command) => command.data.toJSON());
  const rest = new REST({ version: "10" }).setToken(config.discordToken);
  const route = config.guildId
    ? Routes.applicationGuildCommands(config.applicationId, config.guildId)
    : Routes.applicationCommands(config.applicationId);

  await rest.put(route, { body: commands });
  logger.info("Discord application commands deployed", {
    count: commands.length,
    scope: config.guildId ? "guild" : "global",
  });
}

void deployCommands().catch((error: unknown) => {
  logger.error("Discord command deployment failed", {
    reason: error instanceof Error ? error.message : "Unknown error",
  });
  process.exitCode = 1;
});

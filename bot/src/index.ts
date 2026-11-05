import {
  Client,
  Events,
  GatewayIntentBits,
  MessageFlags,
  type Interaction,
} from "discord.js";
import { loadConfig } from "./config.js";
import { createCommandRegistry } from "./commands/registry.js";
import { logger } from "./logger.js";

const config = loadConfig();
const commands = createCommandRegistry(config);
const commandByName = new Map(commands.map((command) => [command.data.name, command]));
const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once(Events.ClientReady, (readyClient) => {
  logger.info("Lemegeton TypeScript bot connected", {
    user: readyClient.user.tag,
    commands: commands.map((command) => command.data.name),
  });
});

async function routeInteraction(interaction: Interaction): Promise<void> {
  try {
    if (interaction.isChatInputCommand()) {
      const command = commandByName.get(interaction.commandName);
      if (!command) {
        await interaction.reply({ content: "That command is not available in this rollout.", flags: MessageFlags.Ephemeral });
        return;
      }
      await command.execute(interaction);
      return;
    }

    if (interaction.isButton() || interaction.isModalSubmit()) {
      const commandName = interaction.customId.split(":", 1)[0];
      const command = commandByName.get(commandName ?? "");
      if (!command) return;

      const handled = interaction.isButton()
        ? await command.handleButton?.(interaction)
        : await command.handleModal?.(interaction);
      if (!handled && !interaction.replied && !interaction.deferred) {
        await interaction.reply({ content: "This control is no longer available. Reopen the command and try again.", flags: MessageFlags.Ephemeral });
      }
    }
  } catch (error) {
    logger.error("Discord interaction failed", {
      command: interaction.isChatInputCommand() ? interaction.commandName : undefined,
      interactionId: interaction.id,
      reason: error instanceof Error ? error.message : "Unknown error",
    });

    if (interaction.isRepliable()) {
      const content = "Lemegeton could not complete that action. Please try again in a moment.";
      try {
        if (interaction.deferred) {
          await interaction.editReply({ content, embeds: [], components: [] });
        } else if (interaction.replied) {
          await interaction.followUp({ content, flags: MessageFlags.Ephemeral });
        } else {
          await interaction.reply({ content, flags: MessageFlags.Ephemeral });
        }
      } catch (replyError) {
        logger.warn("Could not send interaction failure response", {
          reason: replyError instanceof Error ? replyError.message : "Unknown error",
        });
      }
    }
  }
}

client.on(Events.InteractionCreate, (interaction) => {
  void routeInteraction(interaction);
});

let shuttingDown = false;
function shutdown(signal: NodeJS.Signals): void {
  if (shuttingDown) return;
  shuttingDown = true;
  logger.info("Shutting down Lemegeton TypeScript bot", { signal });
  client.destroy();
}

process.once("SIGINT", () => shutdown("SIGINT"));
process.once("SIGTERM", () => shutdown("SIGTERM"));

void client.login(config.discordToken).catch((error: unknown) => {
  logger.error("Discord login failed", {
    reason: error instanceof Error ? error.message : "Unknown error",
  });
  process.exitCode = 1;
});

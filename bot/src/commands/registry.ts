import type { BotConfig } from "../config.js";
import { createDiscoverCommand } from "./discover.js";
import type { BotCommand } from "./types.js";

export function createCommandRegistry(config: BotConfig): BotCommand[] {
  const commands: BotCommand[] = [createDiscoverCommand(config)];
  const names = new Set<string>();

  for (const command of commands) {
    const name = command.data.name;
    if (names.has(name)) {
      throw new Error(`Duplicate slash command registered: ${name}`);
    }
    names.add(name);
  }

  return commands;
}

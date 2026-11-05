import type {
  ButtonInteraction,
  ChatInputCommandInteraction,
  ModalSubmitInteraction,
  SlashCommandBuilder,
} from "discord.js";

export interface BotCommand {
  data: Pick<SlashCommandBuilder, "name" | "toJSON">;
  execute(interaction: ChatInputCommandInteraction): Promise<void>;
  handleButton?(interaction: ButtonInteraction): Promise<boolean>;
  handleModal?(interaction: ModalSubmitInteraction): Promise<boolean>;
}

import type {
  AutocompleteInteraction, ButtonInteraction, ChatInputCommandInteraction, Message,
  ModalSubmitInteraction, RoleSelectMenuInteraction, ChannelSelectMenuInteraction, SlashCommandBuilder, StringSelectMenuInteraction,
} from "discord.js";

export interface FeatureCommand {
  data: Pick<SlashCommandBuilder, "name" | "toJSON">;
  execute(interaction: ChatInputCommandInteraction): Promise<void>;
  handleButton?(interaction: ButtonInteraction): Promise<boolean>;
  handleSelect?(interaction: StringSelectMenuInteraction | RoleSelectMenuInteraction | ChannelSelectMenuInteraction): Promise<boolean>;
  handleModal?(interaction: ModalSubmitInteraction): Promise<boolean>;
  handleAutocomplete?(interaction: AutocompleteInteraction): Promise<void>;
  handleMessage?(message: Message): Promise<void>;
}

import { EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction } from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
export class HelpCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("help").setDescription("View Lemegeton commands and feature groups");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Lemegeton · Command guide").setDescription("Every command is available inside a Discord server. Use the action options and interactive controls to open each feature workflow.").addFields(
      { name: "Media", value: "`/discover` Search supported media providers and explore related works.", inline: false },
      { name: "Community", value: "`/community` Create and join community sessions, rankings and discussions.", inline: false },
      { name: "Archive", value: "`/archive` Browse, contribute to and moderate the server archive.", inline: false },
      { name: "Games", value: "`/play` Run source-backed community quiz sessions.", inline: false },
      { name: "Profiles", value: "`/profile` Connect AniList or Steam and manage server-local privacy settings.", inline: false },
      { name: "Server configuration", value: "`/settings` Enable or disable feature environments for this server.", inline: false },
      { name: "Utilities", value: "`/help` Command guide · `/privacy` Data-use notice · `/feedback` Report a bug or share an idea.", inline: false },
    ).setFooter({ text: "Moderator diagnostics: /log · requires server moderation permissions" });
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
  }
}
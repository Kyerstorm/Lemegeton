import { EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction } from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
export class PrivacyCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("privacy").setDescription("Read how Lemegeton handles data and diagnostics");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Lemegeton · Privacy notice").setDescription("Lemegeton processes information needed to run Discord commands and the features a server enables.").addFields(
      { name: "Information processed", value: "Discord user, server, channel and interaction identifiers; command options; content submitted to community features; and provider account identifiers supplied when linking services.", inline: false },
      { name: "Storage", value: "Bot feature records and server settings are stored in PostgreSQL. Private media uploads use the configured private S3-compatible storage. Discord messages and feedback are also subject to Discord retention.", inline: false },
      { name: "External providers", value: "Searches and linked-account lookups may send the relevant search terms or account identifiers to AniList, Steam, Google Books, TMDB or IGDB, depending on the feature used.", inline: false },
      { name: "Diagnostics", value: "Unhandled interaction failures receive a random SHA-512 issue hash. Diagnostic records are scoped to the server that generated them; server moderators can retrieve them with `/log`. Sensitive option keys such as tokens, passwords and API keys are redacted before storage.", inline: false },
      { name: "Important", value: "Lemegeton is not end-to-end encrypted. Do not submit passwords, authentication tokens or information you do not want processed by Discord, the bot operator or the provider needed for a feature.", inline: false },
    ).setFooter({ text: "Review the repository privacy documentation for deployment-specific details." });
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
  }
}
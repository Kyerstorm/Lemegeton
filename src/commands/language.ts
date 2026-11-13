import {
  EmbedBuilder,
  MessageFlags,
  PermissionFlagsBits,
  SlashCommandBuilder,
  type AutocompleteInteraction,
  type ChatInputCommandInteraction,
} from "discord.js";
import { query } from "../../database.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import {
  canConfigureGuildLeaveAction,
  getGuildRetentionSettings,
} from "../../helpers/runtime/guild-retention.js";
import {
  getGuildLanguage,
  searchSupportedLanguages,
  setGuildLanguage,
} from "../../helpers/runtime/languages.js";
import { logger } from "../../helpers/runtime/logger.js";
import { translateUiText } from "../../helpers/integration/translation.js";

export class LanguageCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("language")
    .setDescription("Set this server's required language.")
    .addStringOption((option) =>
      option
        .setName("language")
        .setDescription("Search and select the server language")
        .setRequired(true)
        .setAutocomplete(true),
    );

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({
        content: "The server language can only be configured inside a Discord server.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const retention = await getGuildRetentionSettings(interaction.guildId);
    const canManageServer = interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false;
    if (!canConfigureGuildLeaveAction(retention.invited_by, interaction.user.id, canManageServer)) {
      await interaction.reply({
        content: "Only the person who invited Lemegeton or a member with Manage Server permission can change the server language.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const selectedCode = interaction.options.getString("language", true);
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const previous = await getGuildLanguage(interaction.guildId);
    const language = await setGuildLanguage(interaction.guildId, selectedCode, interaction.user.id);

    try {
      await query(
        "INSERT INTO dashboard_audit_log (guild_id, actor_id, action, details) VALUES ($1,$2,$3,$4)",
        [interaction.guildId, interaction.user.id, "language.update", "language=" + language.code],
      );
    } catch (error) {
      logger.warn("Server language audit event could not be recorded", {
        guildId: interaction.guildId,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }

    const title = await translateUiText("Server language saved", language.code);
    const description = await translateUiText("Lemegeton's required server language is now **" + language.label + "**.", language.code);
    const embed = new EmbedBuilder()
      .setColor(0x57f287)
      .setTitle(title)
      .setDescription(description)
      .addFields(
        { name: "Language", value: language.name, inline: true },
        { name: "Language code", value: language.code, inline: true },
        { name: "Previous language", value: previous?.label ?? "Not configured", inline: true },
      )
      .setFooter({ text: "This setting applies to the entire server. Run /language again to change it." });

    await interaction.editReply({ embeds: [embed] });
  }

  async handleAutocomplete(interaction: AutocompleteInteraction): Promise<void> {
    const focused = interaction.options.getFocused();
    const choices = searchSupportedLanguages(focused)
      .map((language) => ({
        name: (language.label + " (" + language.code + ")").slice(0, 100),
        value: language.code,
      }));
    await interaction.respond(choices);
  }
}

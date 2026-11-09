import {
  EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/command.js";
import { loadingMessage } from "../../helpers/emoji.js";
import { findIssueLog, isIssueHash } from "../../helpers/issue-logs.js";
import { isBotModerator } from "../../helpers/moderation.js";

function display(value: unknown, limit = 950): string {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? String(value);
  return text.replace(/`/g, "'").slice(0, limit) || "Unavailable";
}
export class LogCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("log")
    .setDescription("Inspect a diagnostic issue reference (bot moderators only)")
    .addStringOption((option) => option.setName("issue_hash")
      .setDescription("Paste the 40-character issue reference")
      .setMinLength(40).setMaxLength(128).setRequired(true));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const hash = interaction.options.getString("issue_hash", true).trim().toLowerCase();
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "You are not authorised to inspect diagnostic logs.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (!isIssueHash(hash)) {
      await interaction.reply({ content: "Enter a valid 40-character hexadecimal issue reference (or a legacy 128-character reference).", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ content: loadingMessage("Finding the diagnostic record…"), flags: MessageFlags.Ephemeral });
    const record = await findIssueLog(hash, interaction.guildId!);
    if (!record) {
      await interaction.editReply("No matching issue record was found in this server.");
      return;
    }

    const details = record.details ?? {};
    const error = details.error && typeof details.error === "object" ? details.error as Record<string, unknown> : {};
    const context = Object.fromEntries(Object.entries(details).filter(([key]) => key !== "error"));
    const embed = new EmbedBuilder().setColor(0xed4245).setTitle("Diagnostic issue record")
      .setDescription(`**Issue reference**\n\`${record.issue_hash}\``)
      .addFields(
        { name: "Occurred", value: display(record.created_at), inline: true },
        { name: "Command / action", value: display(record.command_name, 200), inline: true },
        { name: "Affected user", value: `${display(record.username, 100)}\n${record.user_id}`, inline: true },
        { name: "Channel", value: record.channel_id ? `<#${record.channel_id}>` : "Unavailable", inline: true },
        { name: "Interaction ID", value: display(record.interaction_id, 100), inline: true },
        { name: "Error", value: display(error.message, 950), inline: false },
        { name: "Context", value: display(context, 950), inline: false },
        { name: "Stack trace", value: `\`\`\`\n${display(error.stack, 950)}\n\`\`\``, inline: false },
      ).setFooter({ text: `Server-scoped diagnostics · ${record.guild_id}` });
    await interaction.editReply({ content: null, embeds: [embed] });
  }
}

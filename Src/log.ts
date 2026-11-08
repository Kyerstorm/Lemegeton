import {
  EmbedBuilder,
  MessageFlags,
  PermissionFlagsBits,
  SlashCommandBuilder,
  type ChatInputCommandInteraction,
} from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
import {emoji} from "../Helpers/emoji.js";
import { findIssueLog } from "../Helpers/issue-logs.js";

function canViewIssueLog(interaction: ChatInputCommandInteraction): boolean {
  const permissions = interaction.memberPermissions;
  return Boolean(
    permissions?.has(PermissionFlagsBits.Administrator)
    || permissions?.has(PermissionFlagsBits.ManageGuild)
    || permissions?.has(PermissionFlagsBits.ManageMessages),
  );
}

function clip(value: unknown, max = 1_000): string {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? String(value);
  return text.length > max ? `${text.slice(0, max - 18)}\n… [truncated]` : text;
}

export class LogCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("log")
    .setDescription("Inspect a detailed issue report from this server")
    .addStringOption((option) => option
      .setName("hash")
      .setDescription("The 128-character SHA-512 issue hash")
      .setMinLength(128)
      .setMaxLength(128)
      .setRequired(true));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "This command is only available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (!canViewIssueLog(interaction)) {
      await interaction.reply({ content: "Manage Server, Manage Messages or Administrator permission is required.", flags: MessageFlags.Ephemeral });
      return;
    }

    const hash = interaction.options.getString("hash", true).trim().toLowerCase();
    if (!/^[a-f0-9]{128}$/.test(hash)) {
      await interaction.reply({ content: "Paste the complete 128-character SHA-512 issue hash.", flags: MessageFlags.Ephemeral });
      return;
    }

    await interaction.deferReply({ content: emoji.loading + " Loading issue diagnostics…", flags: MessageFlags.Ephemeral });
    const record = await findIssueLog(hash, interaction.guildId);
    if (!record) {
      await interaction.editReply({ content: "No issue with that hash exists in this server. Check the copied hash and try again." });
      return;
    }

    const details = record.details ?? {};
    const error = (details.error ?? {}) as Record<string, unknown>;
    const context = (details.interaction ?? {}) as Record<string, unknown>;
    const occurredAt = new Date(record.created_at).toISOString();
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle("Issue diagnostics")
      .setDescription("Private server-scoped diagnostic record. Sensitive option values are redacted before storage.")
      .addFields(
        { name: "Issue hash", value: "```" + record.issue_hash.trim() + "```", inline: false },
        { name: "Occurred", value: `<t:${Math.floor(new Date(occurredAt).getTime() / 1_000)}:F>`, inline: true },
        { name: "User", value: `<@${record.user_id}> · \`${record.user_id}\``, inline: true },
        { name: "Event", value: clip(details.event ?? "interaction", 200), inline: true },
        { name: "Command / control", value: clip(context.commandName ?? context.customId ?? "unknown", 200), inline: true },
        { name: "Channel", value: context.channelId ? `<#${String(context.channelId)}>\n\`${String(context.channelId)}\`` : "Unavailable", inline: true },
        { name: "Error", value: clip(`${String(error.name ?? "Error")}: ${String(error.message ?? "No message")}`, 1_000), inline: false },
        { name: "Interaction context", value: "```json" + String.fromCharCode(10) + clip(context, 900) + String.fromCharCode(10) + "```", inline: false },
        { name: "Stack trace", value: "```text" + String.fromCharCode(10) + clip(error.stack ?? "No stack trace was recorded.", 900) + String.fromCharCode(10) + "```", inline: false },
      )
      .setFooter({ text: `Lemegeton diagnostics · UUID digest ${record.uuid_hash.slice(0, 16)}…` })
      .setTimestamp(new Date(occurredAt));

    await interaction.editReply({ embeds: [embed], allowedMentions: { parse: [] } });
  }
}

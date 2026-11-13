import {
  AttachmentBuilder, EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { loadingMessage } from "../../helpers/emoji.js";
import {
  findIssueLog, isIssueHash, sanitizeIssueDetails, serializeIssueLogRecord,
} from "../../helpers/runtime/issue-logs.js";
import { isBotModerator, isModeratorCommandGuild } from "../../helpers/commands/moderation.js";

function display(value: unknown, limit = 950): string {
  let text: string;
  try { text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? String(value); }
  catch { text = String(value); }
  return text.replace(/@everyone|@here/g, "[mention]").replace(/<@&?\d+>/g, "[mention]")
    .replace(/[\u0060]/g, "'").slice(0, limit) || "Unavailable";
}
export class LogCommand implements FeatureCommand {
  constructor(private readonly moderatorGuildId: string | null, private readonly administratorId: string | null = null) {}
  readonly data = new SlashCommandBuilder().setName("log")
    .setDescription("Inspect a diagnostic issue reference (bot moderators only)")
    .addStringOption(option => option.setName("issue_hash")
      .setDescription("Paste the 40-character hexadecimal issue reference")
      .setMinLength(40).setMaxLength(40).setRequired(true));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isModeratorCommandGuild(interaction.guildId, this.moderatorGuildId)) {
      await interaction.reply({ content: "This command is available only in the configured bot operations server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const hash = interaction.options.getString("issue_hash", true).trim().toLowerCase();
    if (!await isBotModerator(interaction.user.id, this.administratorId)) {
      await interaction.reply({ content: "You are not authorised to inspect diagnostic logs.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (!isIssueHash(hash)) {
      await interaction.reply({ content: "Enter a valid 40-character hexadecimal reference.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ content: loadingMessage("Finding the diagnostic record…"), flags: MessageFlags.Ephemeral });
    const record = await findIssueLog(hash);
    if (!record) { await interaction.editReply("No matching diagnostic record was found."); return; }

    const details = sanitizeIssueDetails(record.details ?? {});
    const error = details.error && typeof details.error === "object" ? details.error as Record<string, unknown> : {};
    const context = Object.fromEntries(Object.entries(details).filter(([key]) => key !== "error"));
    const occurredAt = record.created_at instanceof Date ? record.created_at : new Date(record.created_at);
    const occurred = Number.isNaN(occurredAt.getTime()) ? display(record.created_at, 200) : occurredAt.toISOString();
    const sourceMessageId = typeof context.messageId === "string" ? context.messageId : "";
    const validSnowflake = (value: string | null): value is string => Boolean(value && /^\d{17,20}$/.test(value));
    const sourceUrl = validSnowflake(sourceMessageId) && validSnowflake(record.guild_id) && validSnowflake(record.channel_id)
      ? "https://discord.com/channels/" + record.guild_id + "/" + record.channel_id + "/" + sourceMessageId : null;
    const errorCode = error.code === undefined ? "Unavailable" : display(error.code, 100);
    const errorStatus = error.status === undefined ? "Unavailable" : display(error.status, 100);
    const embed = new EmbedBuilder().setColor(0xed4245).setTitle("Diagnostic issue record")
      .setDescription("**Issue reference**\n" + String.fromCharCode(96) + record.issue_hash + String.fromCharCode(96) +
        "\nFull sanitized context and stack data are attached as JSON.")
      .setTimestamp(Number.isNaN(occurredAt.getTime()) ? new Date() : occurredAt)
      .addFields(
        { name: "Occurred (UTC)", value: occurred, inline: true },
        { name: "Command / action", value: display(record.command_name, 200), inline: true },
        { name: "Error type", value: display(error.name, 180), inline: true },
        { name: "Error code / status", value: "Code: " + errorCode + "\nStatus: " + errorStatus, inline: true },
        { name: "Affected user", value: display(record.username, 100) + "\nID: " + record.user_id, inline: true },
        { name: "Origin server", value: record.guild_id, inline: true },
        { name: "Channel", value: record.channel_id ? "<#" + record.channel_id + ">\n" + record.channel_id : "Unavailable", inline: true },
        { name: "Interaction / message ID", value: display(record.interaction_id, 100), inline: true },
        { name: "Error message", value: display(error.message, 950), inline: false },
        { name: "Cause", value: display(error.cause ?? error.errors ?? "None recorded", 950), inline: false },
        { name: "Context", value: display(context, 950), inline: false },
        { name: "Stack trace", value: display(error.stack, 950), inline: false },
        ...(sourceUrl ? [{ name: "Source message", value: "[Open originating message](" + sourceUrl + ")", inline: false }] : []),
      );
    const diagnosticFile = new AttachmentBuilder(Buffer.from(serializeIssueLogRecord(record), "utf8"), {
      name: "issue-" + record.issue_hash + ".json", description: "Full sanitized diagnostic record",
    });
    await interaction.editReply({ content: null, embeds: [embed], files: [diagnosticFile], allowedMentions: { parse: [] } });
  }
}

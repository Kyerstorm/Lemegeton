import {
  ActionRowBuilder, EmbedBuilder, MessageFlags, ModalBuilder, SlashCommandBuilder,
  TextInputBuilder, TextInputStyle, type ChatInputCommandInteraction, type ModalSubmitInteraction,
} from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";
import { loadingMessage } from "../helpers/emoji.js";
import { findIssueLog, isIssueHash } from "../helpers/issue-logs.js";
import { logger } from "../helpers/logger.js";
import { query } from "../database.js";

function feedbackModal(): ModalBuilder {
  return new ModalBuilder().setCustomId("feedback:submit").setTitle("Send feedback").addComponents(
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("category").setLabel("Type: Ideas or Bugs")
        .setStyle(TextInputStyle.Short).setMaxLength(10).setRequired(true),
    ),
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("issue_hash").setLabel("Issue reference (optional)")
        .setStyle(TextInputStyle.Short).setMaxLength(128).setRequired(false)
        .setPlaceholder("Paste the 40-character reference shown with an error"),
    ),
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("description").setLabel("What happened or what would you improve?")
        .setStyle(TextInputStyle.Paragraph).setMinLength(10).setMaxLength(3000).setRequired(true),
    ),
  );
}
export class FeedbackCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("feedback").setDescription("Submit an idea or report a problem");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> { await interaction.showModal(feedbackModal()); }
  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId !== "feedback:submit") return false;
    const category = interaction.fields.getTextInputValue("category").trim().toLowerCase();
    const description = interaction.fields.getTextInputValue("description").trim();
    const issueHash = interaction.fields.getTextInputValue("issue_hash").trim().toLowerCase();
    if (!["idea", "ideas", "bug", "bugs"].includes(category)) {
      await interaction.reply({ content: "Choose **Ideas** or **Bugs** as the feedback type.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (issueHash && !isIssueHash(issueHash)) {
      await interaction.reply({ content: "That issue reference must be a 40-character hexadecimal reference (or a legacy 128-character reference).", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (issueHash && !await findIssueLog(issueHash, interaction.guildId!)) {
      await interaction.reply({ content: "I couldn't find that issue reference in this server. Check the copied hash and try again.", flags: MessageFlags.Ephemeral });
      return true;
    }

    await interaction.reply({ content: loadingMessage("Sending your feedback…"), flags: MessageFlags.Ephemeral });
    const normalizedCategory = category.startsWith("idea") ? "ideas" : "bugs";
    const inserted = await query<{ id: string }>(
      `INSERT INTO bot_feedback (guild_id, user_id, category, description, issue_hash)
       VALUES ($1, $2, $3, $4, $5) RETURNING id`,
      [interaction.guildId, interaction.user.id, normalizedCategory, description, issueHash || null],
    );
    const feedbackId = inserted[0]?.id;
    if (!feedbackId) {
      await interaction.editReply("The feedback could not be saved. Please try again.");
      return true;
    }

    const channelId = process.env.BOT_FEEDBACK_CHANNEL_ID?.trim();
    if (channelId) {
      try {
        const channel = await interaction.client.channels.fetch(channelId);
        if (channel?.isTextBased() && "send" in channel) {
          const embed = new EmbedBuilder()
            .setColor(normalizedCategory === "bugs" ? 0xed4245 : 0x57f287)
            .setTitle(`New ${normalizedCategory === "bugs" ? "bug report" : "idea"} · #${feedbackId}`)
            .setDescription(description.slice(0, 4000))
            .addFields(
              { name: "Submitted by", value: `${interaction.user.tag} (${interaction.user.id})`, inline: true },
              { name: "Server", value: interaction.guild?.name ?? interaction.guildId!, inline: true },
              ...(issueHash ? [{ name: "Issue reference", value: `\`${issueHash}\``, inline: false }] : []),
            ).setTimestamp();
          await channel.send({ embeds: [embed], allowedMentions: { parse: [] } });
        }
      } catch (error) {
        logger.warn("Feedback was stored but could not be forwarded to the configured channel", {
          feedbackId, reason: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }
    await interaction.editReply(`Feedback **#${feedbackId}** was saved. Thank you for helping improve Lemegeton.`);
    return true;
  }
}

import { ActionRowBuilder, EmbedBuilder, MessageFlags, ModalBuilder, SlashCommandBuilder, TextInputBuilder, TextInputStyle, type ChatInputCommandInteraction, type ModalSubmitInteraction, type TextChannel } from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
import {emoji} from "../Helpers/emoji.js";
function feedbackModal(): ModalBuilder {
  return new ModalBuilder().setCustomId("feedback:submit").setTitle("Send feedback").addComponents(
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("category").setLabel("Type: bug or idea").setStyle(TextInputStyle.Short).setMaxLength(10).setRequired(true)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("description").setLabel("What happened or what should change?").setStyle(TextInputStyle.Paragraph).setMaxLength(2000).setRequired(true)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("issue_hash").setLabel("Issue hash (optional)").setStyle(TextInputStyle.Short).setMaxLength(128).setRequired(false).setPlaceholder("Paste the SHA-512 hash shown with the error"))
  );
}
export class FeedbackCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("feedback").setDescription("Send a bug report or feature idea to the Lemegeton team");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) { await interaction.reply({ content: "Feedback can only be submitted from a server.", flags: MessageFlags.Ephemeral }); return; }
    await interaction.showModal(feedbackModal());
  }
  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId !== "feedback:submit" || !interaction.guildId) return false;
    const category = interaction.fields.getTextInputValue("category").trim().toLowerCase();
    const description = interaction.fields.getTextInputValue("description").trim();
    const issueHash = interaction.fields.getTextInputValue("issue_hash").trim().toLowerCase();
    if (!["bug", "bugs", "idea", "ideas"].includes(category)) { await interaction.reply({ content: "Feedback type must be bug or idea.", flags: MessageFlags.Ephemeral }); return true; }
    if (!description) { await interaction.reply({ content: "Add a description before submitting.", flags: MessageFlags.Ephemeral }); return true; }
    if (issueHash && !/^[a-f0-9]{128}$/.test(issueHash)) { await interaction.reply({ content: "The issue hash must be the complete 128-character SHA-512 value.", flags: MessageFlags.Ephemeral }); return true; }
    const channelId = process.env.BOT_FEEDBACK_CHANNEL_ID?.trim() ?? "";
    if (!/^\d{17,20}$/.test(channelId)) { await interaction.reply({ content: "The feedback destination is not configured. Please contact a server administrator.", flags: MessageFlags.Ephemeral }); return true; }
    await interaction.deferReply({ content: emoji.loading + " Sending feedback…", flags: MessageFlags.Ephemeral });
    const destination = await interaction.client.channels.fetch(channelId);
    if (!destination?.isTextBased() || !("send" in destination)) { await interaction.editReply({ content: "The feedback destination is unavailable right now." }); return true; }
    const embed = new EmbedBuilder().setColor(category.startsWith("bug") ? 0xed4245 : 0x57f287).setTitle(category.startsWith("bug") ? "Bug report" : "Feature idea").setDescription(description.slice(0, 4000)).addFields(
      { name: "Server", value: (interaction.guild?.name ?? "Unknown") + " (" + interaction.guildId + ")", inline: true },
      { name: "Submitted by", value: interaction.user.username + " (" + interaction.user.id + ")", inline: true },
      ...(issueHash ? [{ name: "Issue hash", value: "```" + issueHash + "```", inline: false }] : [])
    ).setTimestamp();
    await (destination as TextChannel).send({ embeds: [embed], allowedMentions: { parse: [] } });
    await interaction.editReply({ content: "Feedback submitted. Thank you for helping improve Lemegeton." });
    return true;
  }
}
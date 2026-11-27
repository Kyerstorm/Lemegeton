import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder,
  SlashCommandBuilder, StringSelectMenuBuilder, TextInputBuilder, TextInputStyle,
  type ButtonInteraction, type ChatInputCommandInteraction, type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import {
  addExpeditionStage, createExpedition, getExpedition, joinExpedition, listExpeditions,
  publishExpedition, setExpeditionStatus, submitExpeditionAnswer,
} from "../../helpers/community/expedition.js";

function expeditionModal(customId: string, title: string, fields: Array<{
  id: string; label: string; paragraph?: boolean; required?: boolean; max?: number;
}>): ModalBuilder {
  const modal = new ModalBuilder().setCustomId(customId).setTitle(title.slice(0, 45));
  for (const field of fields.slice(0, 5)) {
    modal.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId(field.id).setLabel(field.label.slice(0, 45))
        .setStyle(field.paragraph ? TextInputStyle.Paragraph : TextInputStyle.Short)
        .setMaxLength(field.max ?? 200).setRequired(field.required ?? false)
        .setPlaceholder("Optional"),
    ));
  }
  return modal;
}

export class ExpeditionCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("expedition")
    .setDescription("Build and play persistent, multi-stage community expeditions.");
  private readonly answerSecret: string | null;

  constructor(config: BotConfig) {
    this.answerSecret = config.expeditionAnswerSecret;
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Expeditions are available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ ...this.homePayload(), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("expedition:")) return false;
    const [, action, expeditionId] = interaction.customId.split(":");
    if (!interaction.guildId) {
      await interaction.reply({ content: "Expeditions are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "home") {
      await interaction.update(this.homePayload());
      return true;
    }
    if (action === "create") {
      if (!this.answerSecret) {
        await interaction.reply({ content: "Expedition creation is disabled until EXPEDITION_ANSWER_SECRET is configured (32+ bytes).", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(expeditionModal("expedition:create-submit", "Create an expedition", [
        { id: "title", label: "Expedition title", required: true, max: 180 },
        { id: "description", label: "Theme and expedition briefing", required: true, paragraph: true, max: 1_000 },
        { id: "limit", label: "Participant limit (2–200)", max: 3 },
      ]));
      return true;
    }
    if (action === "browse") {
      await interaction.deferUpdate();
      await interaction.editReply(await this.browsePayload(interaction.guildId, interaction.user.id));
      return true;
    }
    if (!expeditionId) return false;
    const item = await getExpedition(interaction.guildId, expeditionId, interaction.user.id);
    if (!item) {
      await interaction.reply({ content: "That expedition was not found in this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "view") {
      await interaction.update(this.detailPayload(item, interaction.user.id));
      return true;
    }
    if (action === "join") {
      const joined = await joinExpedition(interaction.guildId, expeditionId, interaction.user.id);
      if (!joined) {
        await interaction.reply({ content: "You may already be a participant, or this expedition is full or closed.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const updated = await getExpedition(interaction.guildId, expeditionId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    if (action === "add-stage") {
      if (!this.answerSecret) {
        await interaction.reply({ content: "Stage creation is unavailable until EXPEDITION_ANSWER_SECRET is configured.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(expeditionModal("expedition:stage-submit:" + expeditionId, "Add an expedition stage", [
        { id: "title", label: "Stage title", required: true, max: 180 },
        { id: "prompt", label: "Stage prompt", required: true, paragraph: true, max: 1_000 },
        { id: "answer", label: "Expected answer", required: true, max: 180 },
        { id: "hint", label: "Optional hint", max: 300 },
      ]));
      return true;
    }
    if (action === "publish") {
      await publishExpedition({ guildId: interaction.guildId, expeditionId, ownerId: interaction.user.id });
      const updated = await getExpedition(interaction.guildId, expeditionId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    if (action === "hint") {
      const currentStage = item.stages.find(stage => stage.position === item.viewerProgress?.current_stage);
      await interaction.reply({
        content: currentStage?.hint ? "Hint: " + currentStage.hint : "There is no hint for your current stage.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "answer") {
      if (!this.answerSecret || item.expedition.status !== "open" || item.viewerProgress?.status !== "active") {
        await interaction.reply({ content: "You cannot submit an answer for this expedition right now.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(expeditionModal("expedition:answer-submit:" + expeditionId, "Submit your answer", [
        { id: "answer", label: "Your answer", required: true, max: 180 },
      ]));
      return true;
    }
    if (action === "pause" || action === "resume" || action === "cancel") {
      const status = action === "pause" ? "paused" : action === "resume" ? "open" : "cancelled";
      await setExpeditionStatus({ guildId: interaction.guildId, expeditionId, ownerId: interaction.user.id, status });
      const updated = await getExpedition(interaction.guildId, expeditionId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId !== "expedition:list") return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Expeditions are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const id = interaction.values[0];
    const item = id ? await getExpedition(interaction.guildId, id, interaction.user.id) : null;
    if (!item) {
      await interaction.reply({ content: "That expedition is no longer available.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.update(this.detailPayload(item, interaction.user.id));
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("expedition:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Expeditions are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "expedition:create-submit") {
        const rawLimit = interaction.fields.getTextInputValue("limit").trim();
        const limit = rawLimit ? Number(rawLimit) : 20;
        if (!Number.isInteger(limit) || limit < 2 || limit > 200) {
          await interaction.reply({ content: "Participant limit must be a whole number between 2 and 200.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await createExpedition({
          guildId: interaction.guildId,
          ownerId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          description: interaction.fields.getTextInputValue("description"),
          participantLimit: limit,
        });
        await interaction.reply({
          content: "Expedition draft **#" + id + "** created. Add stages before publishing.",
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("expedition:view:" + id).setLabel("Open expedition").setStyle(ButtonStyle.Primary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      const [, action, expeditionId] = interaction.customId.split(":");
      if (!expeditionId || !this.answerSecret) {
        await interaction.reply({ content: "The expedition action is not configured.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "stage-submit") {
        await addExpeditionStage({
          guildId: interaction.guildId,
          expeditionId,
          ownerId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          prompt: interaction.fields.getTextInputValue("prompt"),
          answer: interaction.fields.getTextInputValue("answer"),
          hint: interaction.fields.getTextInputValue("hint"),
          answerSecret: this.answerSecret,
        });
        await interaction.reply({
          content: "Stage added to expedition **#" + expeditionId + "**. Continue adding stages or publish it.",
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("expedition:view:" + expeditionId).setLabel("Open expedition").setStyle(ButtonStyle.Primary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (action === "answer-submit") {
        const result = await submitExpeditionAnswer({
          guildId: interaction.guildId,
          expeditionId,
          userId: interaction.user.id,
          answer: interaction.fields.getTextInputValue("answer"),
          answerSecret: this.answerSecret,
        });
        const updated = await getExpedition(interaction.guildId, expeditionId, interaction.user.id);
        const message = !result.correct
          ? "That answer does not match the current stage. You can try again."
          : result.completed
            ? "Expedition complete. Your progress has been saved."
            : "Correct. Stage " + result.nextStage + " is now unlocked.";
        await interaction.reply({
          content: message,
          ...(updated ? { embeds: this.detailPayload(updated, interaction.user.id).embeds, components: this.detailPayload(updated, interaction.user.id).components } : {}),
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
    } catch (error) {
      throw error;
    }
    return false;
  }

  private homePayload() {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Expeditions")
      .setDescription("Build a persistent, multi-stage challenge for your community. Stage answers stay private and each participant advances independently.");
    if (!this.answerSecret) embed.addFields({ name: "Creation unavailable", value: "Configure EXPEDITION_ANSWER_SECRET (32+ bytes) to enable new expeditions." });
    return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("expedition:create").setLabel("Create expedition").setStyle(ButtonStyle.Primary).setDisabled(!this.answerSecret),
      new ButtonBuilder().setCustomId("expedition:browse").setLabel("Browse expeditions").setStyle(ButtonStyle.Secondary),
    )] };
  }

  private async browsePayload(guildId: string, viewerId: string) {
    const items = await listExpeditions(guildId, viewerId);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Server expeditions")
      .setDescription(items.map(item => "**#" + item.id + " · " + item.title + "**\n" + item.status + " · " + item.stage_count + " stage(s) · " + item.participant_count + " participant(s)").join("\n\n").slice(0, 3_900)
        || "There are no expeditions to show in this server.");
    if (!items.length) return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("expedition:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    )] };
    const select = new StringSelectMenuBuilder().setCustomId("expedition:list").setPlaceholder("Open an expedition")
      .addOptions(items.map(item => ({
        label: ("#" + item.id + " · " + item.title).slice(0, 100),
        value: item.id,
        description: item.status + " · " + item.stage_count + " stage(s)",
      })));
    return { embeds: [embed], components: [
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("expedition:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ] };
  }

  private detailPayload(item: NonNullable<Awaited<ReturnType<typeof getExpedition>>>, viewerId: string) {
    const expedition = item.expedition;
    const isOwner = expedition.owner_id === viewerId;
    const progress = item.viewerProgress;
    const embed = new EmbedBuilder().setColor(expedition.status === "completed" ? EMBED_COLOURS.success : EMBED_COLOURS.primary)
      .setTitle("#" + expedition.id + " · " + expedition.title)
      .setDescription(expedition.description.slice(0, 2_000))
      .addFields(
        { name: "Status", value: expedition.status, inline: true },
        { name: "Stages", value: String(item.stages.length), inline: true },
        { name: "Participants", value: String(item.participants.length), inline: true },
      );
    for (const stage of item.stages.slice(0, 8)) {
      embed.addFields({ name: "Stage " + stage.position + " · " + stage.title, value: stage.prompt.slice(0, 700) });
    }
    if (progress?.status === "active") {
      embed.addFields({ name: "Your progress", value: "Stage " + progress.current_stage + " is unlocked.", inline: false });
    } else if (progress?.status === "completed") {
      embed.addFields({ name: "Your progress", value: "You have completed this expedition.", inline: false });
    }
    const buttons: ButtonBuilder[] = [];
    if (expedition.status === "draft" && isOwner) {
      buttons.push(
        new ButtonBuilder().setCustomId("expedition:add-stage:" + expedition.id).setLabel("Add stage").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("expedition:publish:" + expedition.id).setLabel("Publish").setStyle(ButtonStyle.Success),
      );
    } else if (expedition.status === "open" && !progress) {
      buttons.push(new ButtonBuilder().setCustomId("expedition:join:" + expedition.id).setLabel("Join expedition").setStyle(ButtonStyle.Primary));
    } else if (expedition.status === "open" && progress?.status === "active") {
      buttons.push(new ButtonBuilder().setCustomId("expedition:answer:" + expedition.id).setLabel("Submit answer").setStyle(ButtonStyle.Primary));
      const currentStage = item.stages.find(stage => stage.position === progress.current_stage);
      if (currentStage?.hint) buttons.push(new ButtonBuilder().setCustomId("expedition:hint:" + expedition.id).setLabel("Show hint").setStyle(ButtonStyle.Secondary));
    }
    if (isOwner && expedition.status === "open") {
      buttons.push(new ButtonBuilder().setCustomId("expedition:pause:" + expedition.id).setLabel("Pause").setStyle(ButtonStyle.Secondary));
    } else if (isOwner && expedition.status === "paused") {
      buttons.push(new ButtonBuilder().setCustomId("expedition:resume:" + expedition.id).setLabel("Resume").setStyle(ButtonStyle.Secondary));
    }
    if (isOwner && ["draft", "open", "paused"].includes(expedition.status)) {
      buttons.push(new ButtonBuilder().setCustomId("expedition:cancel:" + expedition.id).setLabel("Cancel").setStyle(ButtonStyle.Danger));
    }
    return { embeds: [embed], components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.length ? buttons.slice(0, 5) : [
        new ButtonBuilder().setCustomId("expedition:browse").setLabel("Browse expeditions").setStyle(ButtonStyle.Secondary),
      ]),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("expedition:browse").setLabel("Back to list").setStyle(ButtonStyle.Secondary)),
    ] };
  }
}

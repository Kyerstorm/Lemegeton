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
  addCasebookEvidence, closeCasebookCase, createCasebookCase, getCasebookCase, listCasebookCases,
  publishCasebookCase, revealCasebookSolution, setCasebookStatus, submitCasebookTheory,
  unlockNextCasebookEvidence,
} from "../../helpers/community/casebook.js";

function casebookModal(customId: string, title: string, fields: Array<{
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

export class CasebookCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("casebook")
    .setDescription("Create and solve fictional, evidence-based community mysteries.");
  private readonly solutionSecret: string | null;

  constructor(config: BotConfig) {
    this.solutionSecret = config.casebookSolutionSecret;
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Casebooks are available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ ...this.homePayload(), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("casebook:")) return false;
    const [, action, caseId] = interaction.customId.split(":");
    if (!interaction.guildId) {
      await interaction.reply({ content: "Casebooks are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "home") {
      await interaction.update(this.homePayload());
      return true;
    }
    if (action === "create") {
      if (!this.solutionSecret) {
        await interaction.reply({ content: "Case creation is disabled until CASEBOOK_SOLUTION_SECRET is configured (32+ bytes).", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(casebookModal("casebook:create-submit", "Create a fictional case", [
        { id: "title", label: "Case title", required: true, max: 180 },
        { id: "premise", label: "Fictional premise", required: true, paragraph: true, max: 2_000 },
        { id: "solution", label: "Private answer key", required: true, paragraph: true, max: 2_000 },
        { id: "clue_title", label: "First evidence title", required: true, max: 180 },
        { id: "clue_description", label: "First evidence description", required: true, paragraph: true, max: 1_000 },
      ]));
      return true;
    }
    if (action === "browse") {
      await interaction.deferUpdate();
      await interaction.editReply(await this.browsePayload(interaction.guildId));
      return true;
    }
    if (!caseId) return false;
    const item = await getCasebookCase(interaction.guildId, caseId, interaction.user.id);
    if (!item) {
      await interaction.reply({ content: "That case was not found in this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "view") {
      await interaction.update(this.detailPayload(item, interaction.user.id));
      return true;
    }
    if (action === "add-evidence") {
      await interaction.showModal(casebookModal("casebook:evidence-submit:" + caseId, "Add case evidence", [
        { id: "title", label: "Evidence title", required: true, max: 180 },
        { id: "description", label: "Evidence description", required: true, paragraph: true, max: 1_000 },
        { id: "red_herring", label: "Red herring? yes or no", max: 3 },
      ]));
      return true;
    }
    if (action === "publish") {
      await publishCasebookCase({ guildId: interaction.guildId, caseId, authorId: interaction.user.id });
      const updated = await getCasebookCase(interaction.guildId, caseId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    if (action === "unlock") {
      const clue = await unlockNextCasebookEvidence({ guildId: interaction.guildId, caseId, authorId: interaction.user.id });
      const updated = await getCasebookCase(interaction.guildId, caseId, interaction.user.id);
      const payload = updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload();
      if (clue) payload.embeds[0]?.addFields({ name: "New evidence unlocked", value: "**" + clue.title + "**\n" + clue.description });
      else payload.embeds[0]?.addFields({ name: "No further evidence", value: "All evidence has already been revealed." });
      await interaction.update(payload);
      return true;
    }
    if (action === "theory") {
      await interaction.showModal(casebookModal("casebook:theory-submit:" + caseId, "Submit a case theory", [
        { id: "theory", label: "Your theory", required: true, paragraph: true, max: 1_500 },
        { id: "evidence_ids", label: "Evidence IDs, separated by commas", max: 300 },
      ]));
      return true;
    }
    if (action === "close") {
      await closeCasebookCase({ guildId: interaction.guildId, caseId, actorId: interaction.user.id });
      const updated = await getCasebookCase(interaction.guildId, caseId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    if (action === "pause" || action === "resume" || action === "cancel") {
      const status = action === "pause" ? "paused" : action === "resume" ? "published" : "cancelled";
      await setCasebookStatus({ guildId: interaction.guildId, caseId, authorId: interaction.user.id, status });
      const updated = await getCasebookCase(interaction.guildId, caseId, interaction.user.id);
      await interaction.update(updated ? this.detailPayload(updated, interaction.user.id) : this.homePayload());
      return true;
    }
    if (action === "reveal") {
      if (!this.solutionSecret) {
        await interaction.reply({ content: "The solution key is unavailable until CASEBOOK_SOLUTION_SECRET is configured.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const solution = await revealCasebookSolution({
        guildId: interaction.guildId, caseId, actorId: interaction.user.id, solutionSecret: this.solutionSecret,
      });
      await interaction.reply({ content: "Solution: ||" + solution.slice(0, 1_900) + "||", flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId !== "casebook:list") return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Casebooks are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const id = interaction.values[0];
    const item = id ? await getCasebookCase(interaction.guildId, id, interaction.user.id) : null;
    if (!item) {
      await interaction.reply({ content: "That case is no longer available.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.update(this.detailPayload(item, interaction.user.id));
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("casebook:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Casebooks are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "casebook:create-submit") {
        if (!this.solutionSecret) {
          await interaction.reply({ content: "Case creation is disabled until CASEBOOK_SOLUTION_SECRET is configured.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await createCasebookCase({
          guildId: interaction.guildId,
          authorId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          premise: interaction.fields.getTextInputValue("premise"),
          solution: interaction.fields.getTextInputValue("solution"),
          solutionSecret: this.solutionSecret,
        });
        await addCasebookEvidence({
          guildId: interaction.guildId,
          caseId: id,
          authorId: interaction.user.id,
          title: interaction.fields.getTextInputValue("clue_title"),
          description: interaction.fields.getTextInputValue("clue_description"),
        });
        await interaction.reply({
          content: "Case draft **#" + id + "** created with its first evidence item. Publish it when the evidence is ready.",
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("casebook:view:" + id).setLabel("Open case").setStyle(ButtonStyle.Primary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      const [, action, caseId] = interaction.customId.split(":");
      if (!caseId) return false;
      if (action === "evidence-submit") {
        const rawRedHerring = interaction.fields.getTextInputValue("red_herring").trim().toLowerCase();
        if (rawRedHerring && rawRedHerring !== "yes" && rawRedHerring !== "no") {
          await interaction.reply({ content: "Red herring must be yes or no.", flags: MessageFlags.Ephemeral });
          return true;
        }
        await addCasebookEvidence({
          guildId: interaction.guildId,
          caseId,
          authorId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          description: interaction.fields.getTextInputValue("description"),
          redHerring: rawRedHerring === "yes",
        });
        await interaction.reply({
          content: "Evidence added to draft **#" + caseId + "**.",
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("casebook:view:" + caseId).setLabel("Open case").setStyle(ButtonStyle.Primary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (action === "theory-submit") {
        const evidenceIds = interaction.fields.getTextInputValue("evidence_ids").split(",")
          .map(value => value.trim()).filter(Boolean);
        const id = await submitCasebookTheory({
          guildId: interaction.guildId,
          caseId,
          authorId: interaction.user.id,
          theory: interaction.fields.getTextInputValue("theory"),
          citedEvidenceIds: evidenceIds,
        });
        await interaction.reply({ content: "Your theory was submitted as **#" + id + "**.", flags: MessageFlags.Ephemeral });
        return true;
      }
    } catch (error) {
      throw error;
    }
    return false;
  }

  private homePayload() {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Casebook")
      .setDescription("Create a fictional mystery, reveal evidence in stages, and compare theories. This is only for invented characters and events—never use it to investigate real people, crimes or private information.");
    if (!this.solutionSecret) embed.addFields({ name: "Creation unavailable", value: "Configure CASEBOOK_SOLUTION_SECRET (32+ bytes) to enable new cases." });
    return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("casebook:create").setLabel("Create case").setStyle(ButtonStyle.Primary).setDisabled(!this.solutionSecret),
      new ButtonBuilder().setCustomId("casebook:browse").setLabel("Browse cases").setStyle(ButtonStyle.Secondary),
    )] };
  }

  private async browsePayload(guildId: string) {
    const items = await listCasebookCases(guildId);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Server casebooks")
      .setDescription(items.map(item => "**#" + item.id + " · " + item.title + "**\n" + item.status + " · " + item.evidence_count + " evidence item(s) · " + item.theory_count + " theory/theories").join("\n\n").slice(0, 3_900)
        || "There are no published cases in this server.");
    if (!items.length) return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("casebook:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    )] };
    const select = new StringSelectMenuBuilder().setCustomId("casebook:list").setPlaceholder("Open a case")
      .addOptions(items.map(item => ({
        label: ("#" + item.id + " · " + item.title).slice(0, 100),
        value: item.id,
        description: item.status + " · " + item.evidence_count + " evidence item(s)",
      })));
    return { embeds: [embed], components: [
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("casebook:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ] };
  }

  private detailPayload(item: NonNullable<Awaited<ReturnType<typeof getCasebookCase>>>, viewerId: string) {
    const caseItem = item.case;
    const isAuthor = caseItem.author_id === viewerId;
    const embed = new EmbedBuilder().setColor(caseItem.status === "closed" ? EMBED_COLOURS.success : EMBED_COLOURS.primary)
      .setTitle("#" + caseItem.id + " · " + caseItem.title)
      .setDescription(caseItem.premise.slice(0, 2_000))
      .addFields(
        { name: "Status", value: caseItem.status, inline: true },
        { name: "Evidence", value: String(item.evidence.length), inline: true },
        { name: "Theories", value: String(item.theories.length), inline: true },
      );
    for (const evidence of item.evidence.slice(0, 8)) {
      embed.addFields({
        name: "Evidence " + evidence.unlock_order + " · #" + evidence.id + " · " + evidence.title,
        value: evidence.description.slice(0, 700),
      });
    }
    if (caseItem.status === "closed" && item.evidence.some(entry => entry.is_red_herring === true)) {
      embed.addFields({ name: "Red herrings", value: "The evidence classifications are revealed because this case is closed." });
    }
    const buttons: ButtonBuilder[] = [];
    if (caseItem.status === "draft" && isAuthor) {
      buttons.push(
        new ButtonBuilder().setCustomId("casebook:add-evidence:" + caseItem.id).setLabel("Add evidence").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("casebook:publish:" + caseItem.id).setLabel("Publish").setStyle(ButtonStyle.Success),
      );
    } else if (caseItem.status === "published") {
      buttons.push(new ButtonBuilder().setCustomId("casebook:theory:" + caseItem.id).setLabel("Submit theory").setStyle(ButtonStyle.Primary));
      if (isAuthor) {
        buttons.push(
          new ButtonBuilder().setCustomId("casebook:unlock:" + caseItem.id).setLabel("Unlock evidence").setStyle(ButtonStyle.Secondary),
          new ButtonBuilder().setCustomId("casebook:close:" + caseItem.id).setLabel("Close case").setStyle(ButtonStyle.Danger),
        );
      }
    } else if (caseItem.status === "paused" && isAuthor) {
      buttons.push(new ButtonBuilder().setCustomId("casebook:resume:" + caseItem.id).setLabel("Resume").setStyle(ButtonStyle.Secondary));
    }
    if (isAuthor && ["draft", "published", "paused"].includes(caseItem.status)) {
      buttons.push(new ButtonBuilder().setCustomId("casebook:cancel:" + caseItem.id).setLabel("Cancel").setStyle(ButtonStyle.Danger));
      if (caseItem.status === "published") buttons.push(new ButtonBuilder().setCustomId("casebook:pause:" + caseItem.id).setLabel("Pause").setStyle(ButtonStyle.Secondary));
    }
    if (caseItem.status === "closed" && isAuthor && this.solutionSecret) {
      buttons.push(new ButtonBuilder().setCustomId("casebook:reveal:" + caseItem.id).setLabel("Reveal solution").setStyle(ButtonStyle.Success));
    }
    return { embeds: [embed], components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.length ? buttons.slice(0, 5) : [
        new ButtonBuilder().setCustomId("casebook:browse").setLabel("Browse cases").setStyle(ButtonStyle.Secondary),
      ]),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("casebook:browse").setLabel("Back to list").setStyle(ButtonStyle.Secondary)),
    ] };
  }
}

import { randomUUID } from "node:crypto";
import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder,
  SlashCommandBuilder, StringSelectMenuBuilder, TextInputBuilder, TextInputStyle,
  PermissionFlagsBits,
  type ButtonInteraction, type ChatInputCommandInteraction, type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { MediaSourceClients, type MediaSourceSearchCategory, type MediaSourceSearchRecord } from "../../helpers/integration/media-source-clients.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import {
  addIdentifyCandidate, addIdentifyEvidence, closeIdentifyCase, createIdentifyCase,
  findSimilarIdentifyCases, getIdentifyCase, getIdentifyCaseReport, listIdentifyCaseReports,
  listIdentifyCases, reportIdentifyCase, reopenIdentifyCase, reviewIdentifyCaseReport,
  searchSolvedIdentifyCases, solveIdentifyCase, voteIdentifyCandidate,
} from "../../helpers/community/identify.js";

function modal(customId: string, title: string, fields: Array<{
  id: string; label: string; style?: TextInputStyle; required?: boolean; max?: number; placeholder?: string;
}>): ModalBuilder {
  const result = new ModalBuilder().setCustomId(customId).setTitle(title.slice(0, 45));
  for (const field of fields.slice(0, 5)) {
    result.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId(field.id).setLabel(field.label.slice(0, 45))
        .setStyle(field.style ?? TextInputStyle.Short)
        .setMaxLength(field.max ?? 200)
        .setRequired(field.required ?? false)
        .setPlaceholder(field.placeholder ?? "Optional"),
    ));
  }
  return result;
}

function isManager(interaction: ButtonInteraction | StringSelectMenuInteraction | ModalSubmitInteraction): boolean {
  return Boolean(interaction.memberPermissions?.has(PermissionFlagsBits.ManageMessages)
    || interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)
    || interaction.memberPermissions?.has(PermissionFlagsBits.Administrator));
}

interface IdentifySearchSession {
  ownerId: string;
  guildId: string;
  caseId: string;
  records: MediaSourceSearchRecord[];
  createdAt: number;
}

const IDENTIFY_SESSION_TTL_MS = 15 * 60_000;

export class IdentifyCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("identify")
    .setDescription("Open and solve community media identification cases.");

  private readonly mediaSources: MediaSourceClients;
  private readonly searchSessions = new Map<string, IdentifySearchSession>();

  constructor(config: BotConfig) {
    this.mediaSources = new MediaSourceClients(config);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Identification cases are available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({
      ...this.homePayload(Boolean(interaction.memberPermissions?.has(PermissionFlagsBits.ManageMessages)
        || interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)
        || interaction.memberPermissions?.has(PermissionFlagsBits.Administrator))),
      flags: MessageFlags.Ephemeral,
    });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("identify:")) return false;
    const [, action, caseId, candidateId, stance] = interaction.customId.split(":");
    if (!interaction.guildId) {
      await interaction.reply({ content: "Identification cases are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (action === "home") {
      await interaction.update(this.homePayload(isManager(interaction)));
      return true;
    }
    if (action === "reports") {
      if (!isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to review identification reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(await this.reportQueuePayload(interaction.guildId));
      return true;
    }
    if (action === "report-reviewed" || action === "report-dismissed") {
      if (!caseId || !isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to review identification reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        const updated = await reviewIdentifyCaseReport({
          guildId: interaction.guildId,
          reportId: caseId,
          reviewerId: interaction.user.id,
          decision: action === "report-reviewed" ? "reviewed" : "dismissed",
        });
        await interaction.update(await this.reportQueuePayload(
          interaction.guildId,
          updated ? "Report #" + caseId + " was updated." : "That report is no longer pending.",
        ));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The report could not be updated.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "solved-search") {
      await interaction.showModal(modal("identify:solved-search", "Search solved cases", [
        { id: "query", label: "Title, clue or remembered detail", required: true, max: 100 },
      ]));
      return true;
    }
    if (action === "create") {
      await interaction.showModal(modal("identify:create-submit", "Create identification case", [
        { id: "title", label: "Short title or question", required: true, max: 180 },
        { id: "description", label: "What do you remember?", required: true, style: TextInputStyle.Paragraph, max: 1_000 },
        { id: "category", label: "Media type (optional)", max: 50 },
        { id: "era", label: "Approximate year or era (optional)", max: 40 },
        { id: "visibility", label: "Visibility: guild or channel", max: 20, placeholder: "guild" },
      ]));
      return true;
    }
    if (action === "browse") {
      await interaction.deferUpdate();
      await interaction.editReply(await this.browsePayload(
        interaction.guildId,interaction.user.id,interaction.channelId,isManager(interaction),
      ));
      return true;
    }
    if (!caseId) return false;

    const current = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
    if (!current) {
      await interaction.reply({ content: "That case was not found in this server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (action === "view") {
      await interaction.update(this.casePayload(current));
      return true;
    }
    if (action === "candidate") {
      await interaction.showModal(modal("identify:candidate-submit:" + caseId, "Add a candidate", [
        { id: "title", label: "Candidate title", required: true, max: 200 },
        { id: "source", label: "HTTPS source link (required for manual candidates)", max: 500 },
        { id: "provider", label: "Provider name (optional)", max: 80 },
        { id: "provider_id", label: "Provider ID (optional)", max: 160 },
        { id: "explanation", label: "Which clues does it match?", required: true, style: TextInputStyle.Paragraph, max: 500 },
      ]));
      return true;
    }
    if (action === "provider-search") {
      await interaction.showModal(modal("identify:provider-search:" + caseId, "Search media providers", [
        { id: "query", label: "Title or remembered title fragment", required: true, max: 100 },
        { id: "category", label: "Category: anime, manga, book or music", max: 20 },
      ]));
      return true;
    }
    if (action === "evidence") {
      await interaction.showModal(modal("identify:evidence-submit:" + caseId, "Add evidence", [
        { id: "description", label: "Evidence and what it supports", required: true, style: TextInputStyle.Paragraph, max: 500 },
        { id: "source", label: "HTTPS evidence link (optional)", max: 500 },
      ]));
      return true;
    }
    if (action === "report") {
      await interaction.showModal(modal("identify:report-submit:" + caseId, "Report case", [
        { id: "reason", label: "Reason for report", required: true, style: TextInputStyle.Paragraph, max: 500 },
      ]));
      return true;
    }
    if (action === "close" || action === "reopen") {
      try {
        if (action === "close") {
          await closeIdentifyCase({ guildId: interaction.guildId, caseId, actorId: interaction.user.id, canModerate: isManager(interaction), unresolved: true });
        } else {
          await reopenIdentifyCase({ guildId: interaction.guildId, caseId, actorId: interaction.user.id, canModerate: isManager(interaction) });
        }
        await interaction.update(this.casePayload((await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction)))!));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The case could not be updated.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "vote" && candidateId && (stance === "support" || stance === "challenge")) {
      try {
        await voteIdentifyCandidate({ guildId: interaction.guildId, caseId, candidateId, userId: interaction.user.id, stance });
        const refreshed = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
        const candidate = refreshed?.candidates.find(item => item.id === candidateId);
        await interaction.reply({
          content: candidate
            ? "Feedback recorded for **" + candidate.title + "**. Support and challenge counts are community feedback, not an automatic answer."
            : "Feedback was recorded.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "Feedback could not be recorded.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "solve" && candidateId) {
      try {
        await solveIdentifyCase({ guildId: interaction.guildId, caseId, candidateId, actorId: interaction.user.id, canModerate: isManager(interaction) });
        await interaction.update(this.casePayload((await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction)))!));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The case could not be solved.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("identify:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Identification cases are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (interaction.customId === "identify:report-list") {
      if (!isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to inspect reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const reportId = interaction.values[0];
      const report = reportId ? await getIdentifyCaseReport(interaction.guildId,reportId) : null;
      if (!report || report.status !== "pending") {
        await interaction.reply({ content: "That report is no longer pending.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.reportDetailPayload(report));
      return true;
    }
    if (interaction.customId.startsWith("identify:provider-list:")) {
      const token = interaction.customId.slice("identify:provider-list:".length);
      const session = this.getSearchSession(token,interaction.user.id,interaction.guildId);
      const index = Number(interaction.values[0]);
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      const access = session ? await getIdentifyCase(interaction.guildId,session.caseId,interaction.user.id,interaction.channelId,isManager(interaction)) : null;
      if (!session || !record || !access) {
        await interaction.reply({ content: "This provider search expired or the case is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(modal("identify:provider-explain:" + token + ":" + index,"Explain provider match",[
        { id: "explanation", label: "Which clues does this match?", required: true, style: TextInputStyle.Paragraph, max: 500 },
      ]));
      return true;
    }
    if (interaction.customId === "identify:solved-list") {
      const caseId = interaction.values[0];
      const item = caseId ? await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction)) : null;
      if (!item || item.case.status !== "solved") {
        await interaction.reply({ content: "That solved case is no longer available in this channel.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.casePayload(item));
      return true;
    }
    if (interaction.customId === "identify:case-list") {
      const caseId = interaction.values[0];
      const item = caseId ? await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction)) : null;
      if (!item) {
        await interaction.reply({ content: "That case is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.casePayload(item));
      return true;
    }
    if (interaction.customId.startsWith("identify:candidate-list:")) {
      const caseId = interaction.customId.slice("identify:candidate-list:".length);
      const candidateId = interaction.values[0];
      const item = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
      const candidate = item?.candidates.find(entry => entry.id === candidateId);
      if (!item || !candidate) {
        await interaction.reply({ content: "That candidate is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.candidatePayload(item.case.id, candidate));
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("identify:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Identification cases are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "identify:create-submit") {
        const visibilityValue = interaction.fields.getTextInputValue("visibility").trim().toLowerCase();
        const visibility = ["channel","restricted"].includes(visibilityValue) ? "restricted" : "guild";
        const id = await createIdentifyCase({
          guildId: interaction.guildId,
          ownerId: interaction.user.id,
          channelId: interaction.channelId,
          visibility,
          title: interaction.fields.getTextInputValue("title"),
          description: interaction.fields.getTextInputValue("description"),
          mediaCategory: interaction.fields.getTextInputValue("category"),
          yearHint: interaction.fields.getTextInputValue("era"),
        });
        const similar = await findSimilarIdentifyCases({
          guildId: interaction.guildId,
          title: interaction.fields.getTextInputValue("title"),
          viewerId: interaction.user.id,
          channelId: interaction.channelId,
          excludeCaseId: id,
        });
        await interaction.reply({
          content: "Identification case **#" + id + "** was created. Visibility: "
            + (visibility === "restricted" ? "this channel only" : "this server")
            + (similar.length ? "\n\n**Potentially similar cases:** " + similar.map(item => "#" + item.id + " · " + item.title).join(" | ") : ""),
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("identify:view:" + id).setLabel("Open case").setStyle(ButtonStyle.Primary),
            new ButtonBuilder().setCustomId("identify:browse").setLabel("Browse cases").setStyle(ButtonStyle.Secondary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (interaction.customId === "identify:solved-search") {
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        const solved = await searchSolvedIdentifyCases({
          guildId: interaction.guildId,
          queryText: interaction.fields.getTextInputValue("query"),
          viewerId: interaction.user.id,
          channelId: interaction.channelId,
          canModerate: isManager(interaction),
        });
        await interaction.editReply(this.solvedSearchPayload(solved));
        return true;
      }
      if (interaction.customId.startsWith("identify:provider-explain:")) {
        const [, , token, indexText] = interaction.customId.split(":");
        const session = token ? this.getSearchSession(token, interaction.user.id, interaction.guildId) : null;
        const index = Number(indexText);
        const record = session && Number.isInteger(index) ? session.records[index] : null;
        const access = session ? await getIdentifyCase(interaction.guildId,session.caseId,interaction.user.id,interaction.channelId,isManager(interaction)) : null;
        if (!session || !record || !access) {
          await interaction.reply({ content: "This provider search expired or the case is no longer available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await addIdentifyCandidate({
          guildId: interaction.guildId,
          caseId: session.caseId,
          submittedBy: interaction.user.id,
          title: record.title,
          sourceUrl: record.url,
          provider: record.sourceId,
          providerId: record.providerId,
          explanation: interaction.fields.getTextInputValue("explanation"),
        });
        this.searchSessions.delete(token!);
        await interaction.reply({
          content: "Provider-backed candidate **#" + id + "** was added from " + record.sourceName + ". It remains a suggestion.",
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (interaction.customId.startsWith("identify:provider-search:")) {
        const caseId = interaction.customId.slice("identify:provider-search:".length);
        const access = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
        if (!access) {
          await interaction.reply({ content: "That case is not available in this channel or server.", flags: MessageFlags.Ephemeral });
          return true;
        }
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        const query = interaction.fields.getTextInputValue("query").trim();
        const categoryText = (interaction.fields.getTextInputValue("category").trim() || access.case.media_category || "").toLowerCase();
        const category: MediaSourceSearchCategory | null = categoryText.includes("anime") ? "anime"
          : categoryText.includes("manga") || categoryText.includes("light novel") ? "manga"
            : categoryText.includes("book") || categoryText.includes("novel") ? "book"
              : categoryText.includes("music") ? "music"
                : null;
        if (!category) {
          await interaction.editReply("Choose anime, manga, book or music in the category field.");
          return true;
        }
        const records = await this.mediaSources.search(query,category);
        if (!records.length) {
          await interaction.editReply("No provider-backed records were returned. Try a different title or add a manual HTTPS source.");
          return true;
        }
        this.pruneSearchSessions();
        const token = randomUUID().replaceAll("-","").slice(0,12);
        this.searchSessions.set(token,{
          ownerId:interaction.user.id,guildId:interaction.guildId,caseId,
          records:records.slice(0,25),createdAt:Date.now(),
        });
        await interaction.editReply(this.providerSearchPayload(token,records));
        return true;
      }
      const [, action, caseId] = interaction.customId.split(":");
      if (!caseId) return false;
      const accessible = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
      if (!accessible) {
        await interaction.reply({ content: "That case is not available in this channel or server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "candidate-submit") {
        const provider = interaction.fields.getTextInputValue("provider").trim();
        const providerId = interaction.fields.getTextInputValue("provider_id").trim();
        const source = interaction.fields.getTextInputValue("source").trim();
        if (!source && (!provider || !providerId)) {
          await interaction.reply({ content: "Add an HTTPS source link, or provide both a provider name and provider ID.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await addIdentifyCandidate({
          guildId: interaction.guildId, caseId, submittedBy: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          sourceUrl: source || undefined, provider: provider || undefined, providerId: providerId || undefined,
          explanation: interaction.fields.getTextInputValue("explanation"),
        });
        const item = await getIdentifyCase(interaction.guildId,caseId,interaction.user.id,interaction.channelId,isManager(interaction));
        await interaction.reply({
          content: "Candidate **#" + id + "** was added. It remains a suggestion until the case owner confirms it.",
          components: item ? this.casePayload(item).components : [],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (action === "evidence-submit") {
        const id = await addIdentifyEvidence({
          guildId: interaction.guildId, caseId, submittedBy: interaction.user.id,
          description: interaction.fields.getTextInputValue("description"),
          sourceUrl: interaction.fields.getTextInputValue("source").trim() || undefined,
        });
        await interaction.reply({ content: "Evidence #" + id + " was attached to the case.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "report-submit") {
        await reportIdentifyCase({
          guildId: interaction.guildId, caseId, reportedBy: interaction.user.id,
          reason: interaction.fields.getTextInputValue("reason"),
        });
        await interaction.reply({ content: "The case was reported to this server's moderators.", flags: MessageFlags.Ephemeral });
        return true;
      }
    } catch (error) {
      const content = error instanceof Error ? error.message : "The identification action could not be completed.";
      if (interaction.deferred || interaction.replied) {
        await interaction.editReply({ content, embeds: [], components: [] });
      } else {
        await interaction.reply({ content, flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    return false;
  }

  private homePayload(canModerate = false) {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Media identification")
      .setDescription("Create a case when you remember fragments of a creative work but not its title. Members can submit evidence-backed candidates; only the case owner or a moderator can confirm the result.");
    return { embeds: [embed], components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("identify:create").setLabel("Create case").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("identify:browse").setLabel("Browse open cases").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("identify:solved-search").setLabel("Search solved").setStyle(ButtonStyle.Secondary),
      ),
      ...(canModerate ? [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("identify:reports").setLabel("Review reports").setStyle(ButtonStyle.Secondary),
      )] : []),
    ] };
  }

  private async browsePayload(guildId: string, viewerId: string, channelId: string | null, canModerate: boolean) {
    const cases = await listIdentifyCases(guildId,15,viewerId,channelId,canModerate);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Open identification cases")
      .setDescription(cases.map(item =>
        "**#" + item.id + " · " + item.title + "**\n" + (item.media_category ?? "Media type unknown")
          + " · " + item.candidate_count + " candidate(s)",
      ).join("\n\n").slice(0, 3_900) || "There are no open identification cases in this server.");
    if (!cases.length) {
      return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("identify:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
      )] };
    }
    const select = new StringSelectMenuBuilder().setCustomId("identify:case-list").setPlaceholder("Open a case")
      .addOptions(cases.map(item => ({ label: ("#" + item.id + " · " + item.title).slice(0, 100), value: item.id })));
    return { embeds: [embed], components: [
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("identify:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ] };
  }

  private casePayload(item: NonNullable<Awaited<ReturnType<typeof getIdentifyCase>>>) {
    const current = item.case;
    const embed = new EmbedBuilder().setColor(current.status === "solved" ? EMBED_COLOURS.success : EMBED_COLOURS.primary)
      .setTitle("#" + current.id + " · " + current.title)
      .setDescription(current.description.slice(0, 3_500))
      .addFields(
        { name: "Status", value: current.status, inline: true },
        { name: "Media type", value: current.media_category ?? "Unknown", inline: true },
        { name: "Era", value: current.year_hint ?? "Unknown", inline: true },
      );
    if (current.solved_candidate_id) {
      const answer = item.candidates.find(candidate => candidate.id === current.solved_candidate_id);
      if (answer) embed.addFields({ name: "Confirmed result", value: answer.source_url ? "[" + answer.title + "](" + answer.source_url + ")" : answer.title });
    }
    if (item.candidates.length) {
      embed.addFields({ name: "Candidates", value: item.candidates.slice(0, 10).map(candidate =>
        "**#" + candidate.id + " " + candidate.title + "** · +" + candidate.support_count + " / −" + candidate.challenge_count
          + (candidate.status === "accepted" ? " · Confirmed" : ""),
      ).join("\n").slice(0, 1_000) });
    }
    if (item.evidence.length) {
      embed.addFields({ name: "Evidence", value: item.evidence.slice(0, 8).map(evidence =>
        "• " + evidence.description.slice(0, 130) + (evidence.source_url ? " ([source](" + evidence.source_url + "))" : ""),
      ).join("\n").slice(0, 1_000) });
    }
    const buttons: ButtonBuilder[] = [
      new ButtonBuilder().setCustomId("identify:report:" + current.id).setLabel("Report").setStyle(ButtonStyle.Secondary),
    ];
    if (current.status === "open") {
      buttons.unshift(
        new ButtonBuilder().setCustomId("identify:candidate:" + current.id).setLabel("Add candidate").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("identify:provider-search:" + current.id).setLabel("Search providers").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("identify:evidence:" + current.id).setLabel("Add evidence").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("identify:close:" + current.id).setLabel("Close unresolved").setStyle(ButtonStyle.Danger),
      );
    } else {
      buttons.push(new ButtonBuilder().setCustomId("identify:reopen:" + current.id).setLabel("Reopen").setStyle(ButtonStyle.Secondary));
    }
    const components: Array<ActionRowBuilder<ButtonBuilder> | ActionRowBuilder<StringSelectMenuBuilder>> = [
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons),
    ];
    const active = item.candidates.filter(candidate => candidate.status === "active");
    if (active.length) {
      const select = new StringSelectMenuBuilder().setCustomId("identify:candidate-list:" + current.id).setPlaceholder("Inspect candidate")
        .addOptions(active.slice(0, 25).map(candidate => ({
          label: ("#" + candidate.id + " · " + candidate.title).slice(0, 100),
          description: ("+" + candidate.support_count + " support · " + candidate.challenge_count + " challenge").slice(0, 100),
          value: candidate.id,
        })));
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("identify:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components };
  }

  private async reportQueuePayload(guildId: string, notice?: string) {
    const reports = await listIdentifyCaseReports(guildId);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Pending identification reports")
      .setDescription([
        ...(notice ? [notice,""] : []),
        reports.map(report => "**#" + report.id + " · Case #" + report.case_id + " · " + report.case_title + "**\n"
          + report.reason.slice(0,250) + " · reported by <@" + report.reported_by + ">",
        ).join("\n\n") || "There are no pending identification reports in this server.",
      ].join("\n").slice(0,3_800));
    const components: Array<ActionRowBuilder<StringSelectMenuBuilder> | ActionRowBuilder<ButtonBuilder>> = [];
    if (reports.length) {
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("identify:report-list").setPlaceholder("Inspect a report")
          .addOptions(reports.slice(0,25).map(report => ({
            label: ("#" + report.id + " · " + report.case_title).slice(0,100),
            description: report.reason.slice(0,100),
            value: report.id,
          }))),
      ));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("identify:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds:[embed],components };
  }

  private reportDetailPayload(report: NonNullable<Awaited<ReturnType<typeof getIdentifyCaseReport>>>) {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Report #" + report.id + " · Case #" + report.case_id)
      .setDescription("**" + report.case_title + "**\n" + report.reason + "\nReported by <@" + report.reported_by + ">")
      .addFields({ name:"Status",value:report.status,inline:true });
    return { embeds:[embed],components:[
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("identify:report-reviewed:" + report.id).setLabel("Mark reviewed").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("identify:report-dismissed:" + report.id).setLabel("Dismiss").setStyle(ButtonStyle.Danger),
        new ButtonBuilder().setCustomId("identify:reports").setLabel("Back to queue").setStyle(ButtonStyle.Secondary),
      ),
    ] };
  }

  private providerSearchPayload(token: string, records: MediaSourceSearchRecord[]) {
    const options = records.slice(0,25).map((record,index) => ({
      label: record.title.slice(0,100),
      description: (record.sourceName + " · " + (record.date ?? "Date not supplied")).slice(0,100),
      value: String(index),
    }));
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Provider candidate search")
      .setDescription(records.slice(0,10).map((record,index) =>
        (index+1) + ". **[" + record.title.slice(0,120) + "](" + record.url + ")**\n"
          + record.sourceName + " · " + (record.summary ?? "No provider summary supplied").slice(0,180),
      ).join("\n\n").slice(0,3_800) || "No provider records were returned.");
    return { embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("identify:provider-list:" + token)
          .setPlaceholder("Choose a provider-backed candidate").addOptions(options),
      ),
    ] };
  }

  private solvedSearchPayload(records: Array<{id:string;title:string;description:string;media_category:string|null}>) {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Solved identification cases")
      .setDescription(records.map(item => "**#" + item.id + " · " + item.title + "**\n"
        + (item.media_category ?? "Media type unknown") + " · " + item.description.slice(0,150),
      ).join("\n\n").slice(0,3_800) || "No solved cases matched that search.");
    if (!records.length) return { embeds:[embed],components:[] };
    return { embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("identify:solved-list").setPlaceholder("Open a solved case")
          .addOptions(records.slice(0,25).map(item=>({label:("#"+item.id+" · "+item.title).slice(0,100),value:item.id}))),
      ),
    ] };
  }

  private getSearchSession(token: string, ownerId: string, guildId: string): IdentifySearchSession | null {
    const session = this.searchSessions.get(token);
    if (!session || session.ownerId !== ownerId || session.guildId !== guildId
      || Date.now() - session.createdAt > IDENTIFY_SESSION_TTL_MS) {
      this.searchSessions.delete(token);
      return null;
    }
    return session;
  }

  private pruneSearchSessions(): void {
    const now = Date.now();
    for (const [token,session] of this.searchSessions) {
      if (now - session.createdAt > IDENTIFY_SESSION_TTL_MS) this.searchSessions.delete(token);
    }
    while (this.searchSessions.size > 100) {
      const oldest = this.searchSessions.keys().next().value;
      if (!oldest) break;
      this.searchSessions.delete(oldest);
    }
  }

  private candidatePayload(caseId: string, candidate: {
    id: string; title: string; source_url: string | null; provider: string | null; provider_id: string | null;
    explanation: string; support_count: number; challenge_count: number; status: string;
  }) {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle(candidate.title.slice(0, 256))
      .setDescription(candidate.explanation)
      .addFields(
        { name: "Source", value: candidate.source_url ? "[Open source](" + candidate.source_url + ")" : candidate.provider + " · " + candidate.provider_id, inline: true },
        { name: "Community feedback", value: candidate.support_count + " support · " + candidate.challenge_count + " challenge", inline: true },
      );
    const controls = [
      new ButtonBuilder().setCustomId("identify:vote:" + caseId + ":" + candidate.id + ":support").setLabel("Support").setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId("identify:vote:" + caseId + ":" + candidate.id + ":challenge").setLabel("Challenge").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("identify:solve:" + caseId + ":" + candidate.id).setLabel("Confirm result").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("identify:view:" + caseId).setLabel("Back to case").setStyle(ButtonStyle.Secondary),
    ];
    return { embeds: [embed], components: [new ActionRowBuilder<ButtonBuilder>().addComponents(controls)] };
  }
}

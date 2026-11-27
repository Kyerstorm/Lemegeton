import { randomUUID } from "node:crypto";
import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder,
  SlashCommandBuilder, StringSelectMenuBuilder, TextInputBuilder, TextInputStyle,
  PermissionFlagsBits,
  type ButtonInteraction, type ChatInputCommandInteraction, type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { MediaSourceClients, type MediaSourceSearchCategory, type MediaSourceSearchRecord } from "../../helpers/integration/media-source-clients.js";
import {
  addExchangeCandidate, addExchangeClarification, closeExchangeRequest, createExchangeRequest,
  findSimilarExchangeRequests, getExchangeCandidateReport, getExchangeRequest,
  listExchangeCandidateReports, listExchangeRequests, rateExchangeCandidate,
  removeExchangeCandidate, reportExchangeCandidate, reviewExchangeCandidateReport,
  setExchangeCandidateShortlist, setExchangeRequestVisibility,
} from "../../helpers/community/exchange.js";

function exchangeModal(customId: string, title: string, fields: Array<{
  id: string; label: string; paragraph?: boolean; required?: boolean; max?: number;
}>): ModalBuilder {
  const builder = new ModalBuilder().setCustomId(customId).setTitle(title.slice(0, 45));
  for (const field of fields.slice(0,5)) {
    builder.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId(field.id).setLabel(field.label.slice(0,45))
        .setStyle(field.paragraph ? TextInputStyle.Paragraph : TextInputStyle.Short)
        .setMaxLength(field.max ?? 200)
        .setRequired(field.required ?? false)
        .setPlaceholder("Optional"),
    ));
  }
  return builder;
}

function isManager(interaction: ButtonInteraction | StringSelectMenuInteraction | ModalSubmitInteraction | ChatInputCommandInteraction): boolean {
  return Boolean(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)
    || interaction.memberPermissions?.has(PermissionFlagsBits.ManageMessages)
    || interaction.memberPermissions?.has(PermissionFlagsBits.Administrator));
}

interface ExchangeSearchSession {
  ownerId: string;
  guildId: string;
  requestId: string;
  records: MediaSourceSearchRecord[];
  createdAt: number;
}

const EXCHANGE_SESSION_TTL_MS = 15 * 60_000;

export class ExchangeCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("exchange")
    .setDescription("Request and share human-powered media recommendations in this server.");

  private readonly mediaSources: MediaSourceClients;
  private readonly searchSessions = new Map<string, ExchangeSearchSession>();

  constructor(config: BotConfig) {
    this.mediaSources = new MediaSourceClients(config);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Exchange is available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ ...this.homePayload(isManager(interaction)), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("exchange:")) return false;
    const [, action, requestId] = interaction.customId.split(":");
    if (!interaction.guildId) {
      await interaction.reply({ content: "Exchange is available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (action === "home") {
      await interaction.update(this.homePayload(isManager(interaction)));
      return true;
    }
    if (action === "reports") {
      if (!isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to review Exchange reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(await this.reportQueuePayload(interaction.guildId));
      return true;
    }
    if (action === "report-dismissed" || action === "report-remove") {
      if (!requestId || !isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to review Exchange reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const report = await getExchangeCandidateReport(interaction.guildId, requestId);
      if (!report || report.status !== "pending") {
        await interaction.reply({ content: "That recommendation report is no longer pending.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        if (action === "report-remove") {
          await removeExchangeCandidate({
            guildId: interaction.guildId,
            requestId: report.request_id,
            candidateId: report.candidate_id,
            actorId: interaction.user.id,
            canModerate: true,
          });
        }
        await reviewExchangeCandidateReport({
          guildId: interaction.guildId,
          reportId: report.id,
          reviewerId: interaction.user.id,
          decision: action === "report-remove" ? "reviewed" : "dismissed",
        });
        await interaction.update(await this.reportQueuePayload(
          interaction.guildId,
          action === "report-remove"
            ? "Recommendation #" + report.candidate_id + " was removed."
            : "Report #" + report.id + " was dismissed.",
        ));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The report could not be reviewed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "create") {
      await interaction.showModal(exchangeModal("exchange:create-submit", "Create recommendation request", [
        { id: "title", label: "Short request title", required: true, max: 180 },
        { id: "description", label: "What are you looking for?", required: true, paragraph: true, max: 1_000 },
        { id: "category", label: "Media category (optional)", max: 60 },
        { id: "preferences", label: "Preferences (use Avoid: for exclusions)", max: 500 },
        { id: "visibility", label: "Visibility: guild or restricted", max: 20, placeholder: "guild" },
      ]));
      return true;
    }
    if (action === "browse") {
      await interaction.deferUpdate();
      await interaction.editReply(await this.browsePayload(interaction.guildId, interaction.user.id));
      return true;
    }
    if (!requestId) return false;
    const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
    if (!item) {
      await interaction.reply({ content: "That request is not available in this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const isOwner = item.request.owner_id === interaction.user.id;
    if (action === "view") {
      await interaction.update(this.requestPayload(item, interaction.user.id));
      return true;
    }
    if (action === "candidate") {
      await interaction.showModal(exchangeModal("exchange:candidate-submit:" + requestId, "Recommend a work", [
        { id: "title", label: "Media title", required: true, max: 200 },
        { id: "source", label: "HTTPS source link (or provide provider ID)", max: 500 },
        { id: "provider", label: "Provider name (optional)", max: 80 },
        { id: "provider_id", label: "Provider ID (optional)", max: 160 },
        { id: "explanation", label: "Why does it fit the request?", required: true, paragraph: true, max: 500 },
      ]));
      return true;
    }
    if (action === "provider-search") {
      await interaction.showModal(exchangeModal("exchange:provider-search:" + requestId, "Search media providers", [
        { id: "query", label: "Title or remembered title fragment", required: true, max: 100 },
        { id: "category", label: "Category: anime, manga, book or music", max: 20 },
      ]));
      return true;
    }
    if (action === "clarify") {
      await interaction.showModal(exchangeModal("exchange:clarify-submit:" + requestId, "Ask or provide clarification", [
        { id: "message", label: "Clarification or answer", required: true, paragraph: true, max: 800 },
        { id: "candidate_id", label: "Recommendation ID (optional)", max: 20 },
      ]));
      return true;
    }
    if (action === "visibility") {
      if (!isOwner) {
        await interaction.reply({ content: "Only the request owner can change request visibility.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        const visibility = item.request.visibility === "guild" ? "restricted" : "guild";
        await setExchangeRequestVisibility({
          guildId: interaction.guildId,
          requestId,
          ownerId: interaction.user.id,
          visibility,
        });
        const updated = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        await interaction.update(this.requestPayload(updated!, interaction.user.id));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "Request visibility could not be changed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "shortlist" && item.candidates.length) {
      await interaction.reply({
        content: "Use the shortlist selector on the request panel to change saved recommendations.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "solve" || action === "close") {
      try {
        await closeExchangeRequest({
          guildId: interaction.guildId,
          requestId,
          actorId: interaction.user.id,
          canModerate: isManager(interaction),
          solved: action === "solve",
        });
        const updated = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        await interaction.update(this.requestPayload(updated!, interaction.user.id));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The request could not be closed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("exchange:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Exchange is available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (interaction.customId === "exchange:report-list") {
      if (!isManager(interaction)) {
        await interaction.reply({ content: "Manage Messages permission is required to inspect Exchange reports.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const reportId = interaction.values[0];
      const report = reportId ? await getExchangeCandidateReport(interaction.guildId, reportId) : null;
      if (!report || report.status !== "pending") {
        await interaction.reply({ content: "That recommendation report is no longer pending.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.reportDetailPayload(report));
      return true;
    }

    if (interaction.customId === "exchange:request-list") {
      const requestId = interaction.values[0];
      const item = requestId ? await getExchangeRequest(interaction.guildId, requestId, interaction.user.id) : null;
      if (!item) {
        await interaction.reply({ content: "That request is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(this.requestPayload(item, interaction.user.id));
      return true;
    }

    if (interaction.customId.startsWith("exchange:provider-list:")) {
      const token = interaction.customId.slice("exchange:provider-list:".length);
      const session = this.getSearchSession(token, interaction.user.id, interaction.guildId);
      const index = Number(interaction.values[0]);
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      const item = session ? await getExchangeRequest(interaction.guildId, session.requestId, interaction.user.id) : null;
      if (!session || !record || !item) {
        await interaction.reply({ content: "This provider search expired or the request is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(exchangeModal(
        "exchange:provider-explain:" + token + ":" + index,
        "Explain provider recommendation",
        [{ id: "explanation", label: "Why does this fit the request?", required: true, paragraph: true, max: 500 }],
      ));
      return true;
    }

    if (interaction.customId.startsWith("exchange:recommendation-list:")) {
      const requestId = interaction.customId.slice("exchange:recommendation-list:".length);
      const candidateId = interaction.values[0];
      const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
      const candidate = item?.candidates.find(entry => entry.id === candidateId);
      if (!item || !candidate) {
        await interaction.reply({ content: "That recommendation is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        await setExchangeCandidateShortlist({
          guildId: interaction.guildId,
          requestId,
          candidateId,
          ownerId: interaction.user.id,
          shortlisted: !candidate.is_shortlisted,
        });
        const updated = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        await interaction.update(this.requestPayload(updated!, interaction.user.id));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The shortlist could not be updated.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }

    if (interaction.customId.startsWith("exchange:feedback-list:")) {
      const requestId = interaction.customId.slice("exchange:feedback-list:".length);
      const [candidateId, feedback] = (interaction.values[0] ?? "").split("|");
      if (!candidateId || (feedback !== "good_match" && feedback !== "not_match")) {
        await interaction.reply({ content: "Choose a valid recommendation rating.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        await rateExchangeCandidate({
          guildId: interaction.guildId,
          requestId,
          candidateId,
          ownerId: interaction.user.id,
          feedback,
        });
        const updated = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        if (!updated) throw new Error("That request is no longer available.");
        await interaction.update(this.requestPayload(updated, interaction.user.id));
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The recommendation rating could not be saved.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }

    if (interaction.customId.startsWith("exchange:report-candidate:")) {
      const requestId = interaction.customId.slice("exchange:report-candidate:".length);
      const candidateId = interaction.values[0];
      const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
      if (!candidateId || !item?.candidates.some(candidate => candidate.id === candidateId)) {
        await interaction.reply({ content: "That recommendation is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(exchangeModal(
        "exchange:report-submit:" + requestId + ":" + candidateId,
        "Report recommendation",
        [{ id: "reason", label: "Why should moderators review this?", required: true, paragraph: true, max: 500 }],
      ));
      return true;
    }

    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("exchange:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Exchange is available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "exchange:create-submit") {
        const visibilityText = interaction.fields.getTextInputValue("visibility").trim().toLowerCase();
        const visibility = visibilityText === "restricted" ? "restricted" : "guild";
        const requestId = await createExchangeRequest({
          guildId: interaction.guildId,
          ownerId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          description: interaction.fields.getTextInputValue("description"),
          mediaCategory: interaction.fields.getTextInputValue("category"),
          preferences: interaction.fields.getTextInputValue("preferences").split(/\bAvoid:/i)[0]?.trim(),
          exclusions: interaction.fields.getTextInputValue("preferences").match(/\bAvoid:(.*)$/is)?.[1]?.trim(),
          visibility,
        });
        const similar = await findSimilarExchangeRequests({
          guildId: interaction.guildId,
          title: interaction.fields.getTextInputValue("title"),
          viewerId: interaction.user.id,
          excludeRequestId: requestId,
        });
        await interaction.reply({
          content: "Recommendation request **#" + requestId + "** is now open. Visibility: "
            + (visibility === "restricted" ? "owner only" : "this server")
            + (similar.length ? "\n\n**Similar requests:** " + similar.map(item => "#" + item.id + " · " + item.title).join(" | ") : ""),
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("exchange:view:" + requestId).setLabel("Open request").setStyle(ButtonStyle.Primary),
            new ButtonBuilder().setCustomId("exchange:browse").setLabel("Browse requests").setStyle(ButtonStyle.Secondary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }

      if (interaction.customId.startsWith("exchange:provider-search:")) {
        const requestId = interaction.customId.slice("exchange:provider-search:".length);
        const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        if (!item) {
          await interaction.reply({ content: "That request is not available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        const query = interaction.fields.getTextInputValue("query").trim();
        const categoryText = (interaction.fields.getTextInputValue("category").trim() || item.request.media_category || "").toLowerCase();
        const category: MediaSourceSearchCategory | null = categoryText.includes("anime") ? "anime"
          : categoryText.includes("manga") || categoryText.includes("light novel") ? "manga"
            : categoryText.includes("book") || categoryText.includes("novel") ? "book"
              : categoryText.includes("music") ? "music" : null;
        if (!category) {
          await interaction.editReply("Choose anime, manga, book or music in the category field.");
          return true;
        }
        const records = await this.mediaSources.search(query, category);
        if (!records.length) {
          await interaction.editReply("No provider-backed records were returned. Try a more specific title or submit a manual HTTPS suggestion.");
          return true;
        }
        this.pruneSearchSessions();
        const token = randomUUID().replaceAll("-", "").slice(0, 12);
        this.searchSessions.set(token, {
          ownerId: interaction.user.id,
          guildId: interaction.guildId,
          requestId,
          records: records.slice(0, 25),
          createdAt: Date.now(),
        });
        await interaction.editReply(this.providerSearchPayload(token, records));
        return true;
      }

      if (interaction.customId.startsWith("exchange:provider-explain:")) {
        const [, , token, indexText] = interaction.customId.split(":");
        const session = token ? this.getSearchSession(token, interaction.user.id, interaction.guildId) : null;
        const index = Number(indexText);
        const record = session && Number.isInteger(index) ? session.records[index] : null;
        const item = session ? await getExchangeRequest(interaction.guildId, session.requestId, interaction.user.id) : null;
        if (!session || !record || !item) {
          await interaction.reply({ content: "This provider search expired or the request is no longer available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await addExchangeCandidate({
          guildId: interaction.guildId,
          requestId: session.requestId,
          submittedBy: interaction.user.id,
          title: record.title,
          sourceUrl: record.url,
          provider: record.sourceId,
          providerId: record.providerId,
          explanation: interaction.fields.getTextInputValue("explanation"),
        });
        this.searchSessions.delete(token!);
        await interaction.reply({
          content: "Provider-backed recommendation **#" + id + "** was added from " + record.sourceName + ". The owner decides whether it fits.",
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }

      if (interaction.customId.startsWith("exchange:clarify-submit:")) {
        const requestId = interaction.customId.slice("exchange:clarify-submit:".length);
        const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        if (!item) {
          await interaction.reply({ content: "That request is not available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const candidateId = interaction.fields.getTextInputValue("candidate_id").trim();
        const id = await addExchangeClarification({
          guildId: interaction.guildId,
          requestId,
          authorId: interaction.user.id,
          message: interaction.fields.getTextInputValue("message"),
          candidateId: candidateId || undefined,
        });
        await interaction.reply({ content: "Clarification #" + id + " was added to the request.", flags: MessageFlags.Ephemeral });
        return true;
      }

      if (interaction.customId.startsWith("exchange:report-submit:")) {
        const [, , requestId, candidateId] = interaction.customId.split(":");
        if (!requestId || !candidateId || !await getExchangeRequest(interaction.guildId, requestId, interaction.user.id)) {
          await interaction.reply({ content: "That request or recommendation is no longer available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await reportExchangeCandidate({
          guildId: interaction.guildId,
          requestId,
          candidateId,
          reportedBy: interaction.user.id,
          reason: interaction.fields.getTextInputValue("reason"),
        });
        await interaction.reply({ content: "Recommendation report #" + id + " was sent to this server's moderators.", flags: MessageFlags.Ephemeral });
        return true;
      }

      const [, action, requestId] = interaction.customId.split(":");
      if (action === "candidate-submit" && requestId) {
        const provider = interaction.fields.getTextInputValue("provider").trim();
        const providerId = interaction.fields.getTextInputValue("provider_id").trim();
        const sourceUrl = interaction.fields.getTextInputValue("source").trim();
        const item = await getExchangeRequest(interaction.guildId, requestId, interaction.user.id);
        if (!item) {
          await interaction.reply({ content: "That request is not available.", flags: MessageFlags.Ephemeral });
          return true;
        }
        const id = await addExchangeCandidate({
          guildId: interaction.guildId,
          requestId,
          submittedBy: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          sourceUrl: sourceUrl || undefined,
          provider: provider || undefined,
          providerId: providerId || undefined,
          explanation: interaction.fields.getTextInputValue("explanation"),
        });
        await interaction.reply({
          content: "Recommendation **#" + id + "** was added. The request owner decides whether it fits.",
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("exchange:view:" + requestId).setLabel("Open request").setStyle(ButtonStyle.Primary),
          )],
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
    } catch (error) {
      const content = error instanceof Error ? error.message : "The Exchange action could not be completed.";
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
      .setTitle("Community Exchange")
      .setDescription("Ask for a recommendation and let other members explain why a work might fit. Discover remains provider-driven; Exchange records member suggestions and the request owner's feedback.");
    return { embeds: [embed], components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("exchange:create").setLabel("Create request").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("exchange:browse").setLabel("Browse requests").setStyle(ButtonStyle.Secondary),
      ),
      ...(canModerate ? [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("exchange:reports").setLabel("Review reports").setStyle(ButtonStyle.Secondary),
      )] : []),
    ] };
  }

  private async browsePayload(guildId: string,viewerId: string) {
    const requests = await listExchangeRequests(guildId,15,viewerId);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle("Open recommendation requests")
      .setDescription(requests.map(item =>
        "**#" + item.id + " · " + item.title + "**\n" + (item.media_category ?? "Any media")
          + " · " + item.candidate_count + " recommendation(s)",
      ).join("\n\n").slice(0,3_900) || "There are no open requests in this server.");
    if (!requests.length) return { embeds: [embed], components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("exchange:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ] };
    const select = new StringSelectMenuBuilder().setCustomId("exchange:request-list").setPlaceholder("Open a request")
      .addOptions(requests.map(item => ({ label: ("#" + item.id + " · " + item.title).slice(0,100), value: item.id })));
    return { embeds: [embed], components: [
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select),
      new ActionRowBuilder<ButtonBuilder>().addComponents(new ButtonBuilder().setCustomId("exchange:home").setLabel("Back").setStyle(ButtonStyle.Secondary)),
    ] };
  }

  private requestPayload(item: NonNullable<Awaited<ReturnType<typeof getExchangeRequest>>>,viewerId:string) {
    const request = item.request;
    const isOwner = request.owner_id === viewerId;
    const embed = new EmbedBuilder().setColor(request.status === "solved" ? EMBED_COLOURS.success : EMBED_COLOURS.primary)
      .setTitle("#" + request.id + " · " + request.title)
      .setDescription(request.description.slice(0,2_500))
      .addFields(
        { name: "Category", value: request.media_category ?? "Any media", inline: true },
        { name: "Status", value: request.status, inline: true },
        { name: "Visibility", value: request.visibility === "restricted" ? "Owner only" : "Guild", inline: true },
        { name: "Preferences", value: request.preferences ?? "Not specified", inline: false },
      );
    if (request.exclusions) embed.addFields({ name: "Avoid", value: request.exclusions, inline: false });
    if (item.candidates.length) {
      embed.addFields({
        name: "Recommendations",
        value: item.candidates.slice(0,10).map(candidate =>
          (candidate.is_shortlisted ? "Shortlisted · " : "")
          + "**#" + candidate.id + " " + candidate.title + "**\n"
          + candidate.explanation.slice(0,180)
          + (candidate.caveat ? " · Note: " + candidate.caveat.slice(0,100) : "")
          + (candidate.owner_feedback ? " · Owner: " + (candidate.owner_feedback === "good_match" ? "good match" : "not a match") : "")
          + (candidate.source_url ? " · [Source](" + candidate.source_url + ")" : ""),
        ).join("\n\n").slice(0,3_000),
      });
    }
    if (item.clarifications.length) {
      embed.addFields({
        name: "Clarifications",
        value: item.clarifications.slice(-5).map(entry =>
          "<@" + entry.author_id + ">" + (entry.candidate_id ? " · Recommendation #" + entry.candidate_id : "")
          + "\n" + entry.message.slice(0,300),
        ).join("\n\n").slice(0,1_000),
      });
    }

    const buttons: ButtonBuilder[] = [
      new ButtonBuilder().setCustomId("exchange:browse").setLabel("Browse").setStyle(ButtonStyle.Secondary),
    ];
    if (request.status === "open") {
      buttons.unshift(
        new ButtonBuilder().setCustomId("exchange:candidate:" + request.id).setLabel("Recommend a work").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("exchange:provider-search:" + request.id).setLabel("Search providers").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("exchange:clarify:" + request.id).setLabel("Clarify").setStyle(ButtonStyle.Secondary),
      );
    }
    if (isOwner && request.status === "open") {
      buttons.push(new ButtonBuilder().setCustomId("exchange:visibility:" + request.id)
        .setLabel(request.visibility === "guild" ? "Make private" : "Share with guild").setStyle(ButtonStyle.Secondary));
    }
    const rows: Array<ActionRowBuilder<ButtonBuilder> | ActionRowBuilder<StringSelectMenuBuilder>> = [
      new ActionRowBuilder<ButtonBuilder>().addComponents(buttons),
    ];
    if (request.status === "open" && isOwner) {
      rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("exchange:solve:" + request.id).setLabel("Mark solved").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("exchange:close:" + request.id).setLabel("Close request").setStyle(ButtonStyle.Secondary),
      ));
    }
    if (request.status === "open" && isOwner && item.candidates.length) {
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("exchange:recommendation-list:" + request.id)
          .setPlaceholder("Shortlist or remove a shortlist")
          .addOptions(item.candidates.slice(0,25).map(candidate => ({
            label: ("#" + candidate.id + " · " + candidate.title).slice(0,100),
            description: candidate.is_shortlisted ? "Currently shortlisted" : "Not shortlisted",
            value: candidate.id,
          }))),
      ));
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("exchange:feedback-list:" + request.id)
          .setPlaceholder("Rate a recommendation")
          .addOptions(item.candidates.slice(0,12).flatMap(candidate => [
            {
              label: ("Good match · #" + candidate.id + " " + candidate.title).slice(0,100),
              description: "Tell contributors this recommendation fits",
              value: candidate.id + "|good_match",
            },
            {
              label: ("Not a match · #" + candidate.id + " " + candidate.title).slice(0,100),
              description: "Tell contributors this recommendation does not fit",
              value: candidate.id + "|not_match",
            },
          ])),
      ));
    }
    if (request.status === "open" && item.candidates.length) {
      rows.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("exchange:report-candidate:" + request.id)
          .setPlaceholder("Report a recommendation")
          .addOptions(item.candidates.slice(0,25).map(candidate => ({
            label: ("#" + candidate.id + " · " + candidate.title).slice(0,100),
            description: (candidate.provider ?? "Manual suggestion").slice(0,100),
            value: candidate.id,
          }))),
      ));
    }
    return { embeds: [embed], components: rows };
  }

  private providerSearchPayload(token: string, records: MediaSourceSearchRecord[]) {
    const options = records.slice(0,25).map((record,index) => ({
      label: record.title.slice(0,100),
      description: (record.sourceName + " · " + (record.date ?? "Date not supplied")).slice(0,100),
      value: String(index),
    }));
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Provider recommendation search")
      .setDescription(records.slice(0,10).map((record,index) =>
        (index+1) + ". **[" + record.title.slice(0,120) + "](" + record.url + ")**\n"
          + record.sourceName + " · " + (record.summary ?? "No provider summary supplied").slice(0,180),
      ).join("\n\n").slice(0,3_800) || "No provider records were returned.");
    return { embeds:[embed],components:[
      new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("exchange:provider-list:" + token)
          .setPlaceholder("Choose a provider-backed recommendation").addOptions(options),
      ),
    ] };
  }

  private async reportQueuePayload(guildId:string,notice?:string) {
    const reports = await listExchangeCandidateReports(guildId);
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Pending Exchange reports")
      .setDescription([
        ...(notice ? [notice,""] : []),
        reports.map(report =>
          "**#" + report.id + " · " + report.title + "**\n"
            + "Request #" + report.request_id + " · " + report.reason.slice(0,240)
            + " · reported by <@" + report.reported_by + ">",
        ).join("\n\n") || "There are no pending recommendation reports in this server.",
      ].join("\n").slice(0,3_800));
    const components: Array<ActionRowBuilder<StringSelectMenuBuilder> | ActionRowBuilder<ButtonBuilder>> = [];
    if (reports.length) {
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("exchange:report-list").setPlaceholder("Inspect a report")
          .addOptions(reports.slice(0,25).map(report => ({
            label: ("#" + report.id + " · " + report.title).slice(0,100),
            description: ("Request #" + report.request_id + " · " + report.reason).slice(0,100),
            value: report.id,
          }))),
      ));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("exchange:home").setLabel("Back").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds:[embed],components };
  }

  private reportDetailPayload(report: NonNullable<Awaited<ReturnType<typeof getExchangeCandidateReport>>>) {
    const embed = new EmbedBuilder().setColor(EMBED_COLOURS.primary)
      .setTitle("Report #" + report.id + " · Recommendation #" + report.candidate_id)
      .setDescription("**" + report.title + "**\nRequest #" + report.request_id + "\n"
        + report.reason + "\nReported by <@" + report.reported_by + ">")
      .addFields({ name:"Status",value:report.status,inline:true });
    return { embeds:[embed],components:[
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("exchange:report-remove:" + report.id).setLabel("Remove recommendation").setStyle(ButtonStyle.Danger),
        new ButtonBuilder().setCustomId("exchange:report-dismissed:" + report.id).setLabel("Dismiss report").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("exchange:reports").setLabel("Back to queue").setStyle(ButtonStyle.Secondary),
      ),
    ] };
  }

  private getSearchSession(token:string,ownerId:string,guildId:string):ExchangeSearchSession|null {
    const session = this.searchSessions.get(token);
    if (!session || session.ownerId !== ownerId || session.guildId !== guildId
      || Date.now() - session.createdAt > EXCHANGE_SESSION_TTL_MS) {
      this.searchSessions.delete(token);
      return null;
    }
    return session;
  }

  private pruneSearchSessions():void {
    const now = Date.now();
    for (const [token,session] of this.searchSessions) {
      if (now - session.createdAt > EXCHANGE_SESSION_TTL_MS) this.searchSessions.delete(token);
    }
    while (this.searchSessions.size > 100) {
      const oldest = this.searchSessions.keys().next().value;
      if (!oldest) break;
      this.searchSessions.delete(oldest);
    }
  }

}

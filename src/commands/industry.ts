import { randomUUID } from "node:crypto";
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  PermissionFlagsBits,
  ModalBuilder,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { AniListClient, type AniListPublicEntity } from "../../helpers/integration/anilist.js";
import { IgdbClient, type IgdbCompany } from "../../helpers/integration/igdb.js";
import { TmdbClient, type TmdbOrganization } from "../../helpers/integration/tmdb.js";
import { MusicDiscovery, type MusicLabelResult } from "../../helpers/integration/music-discovery.js";
import { WikidataClient, type WikidataEntity } from "../../helpers/integration/wikidata.js";
import { MediaSourceClients, type MediaSourceSearchRecord } from "../../helpers/integration/media-source-clients.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import {
  pinIndustryOrganization,
  listIndustryPins,
  removeIndustryPin,
  createIndustryCorrectionRequest,
  createIndustryIdentityLinkRequest,
  listPendingIndustryCorrections,
  getIndustryCorrectionRequest,
  reviewIndustryCorrectionRequest,
  listPendingIndustryIdentityLinks,
  getIndustryIdentityLinkRequest,
  reviewIndustryIdentityLinkRequest,
  listApprovedIndustryCorrections,
  listApprovedIndustryIdentityLinks,
} from "../../helpers/media/industry-directory.js";
import { getMediaSourceResearchLinks } from "../../helpers/media/media-source-adapters.js";

type IndustryCategory = "anime-studio" | "game-company" | "screen-company" | "tv-network" | "music-label" | "publisher" | "knowledge";

type IndustryRecord =
  | { kind: "anime-studio"; item: AniListPublicEntity }
  | { kind: "game-company"; item: IgdbCompany }
  | { kind: "screen-company"; item: TmdbOrganization }
  | { kind: "tv-network"; item: TmdbOrganization; discoveredFrom: string }
  | { kind: "music-label"; item: MusicLabelResult }
  | { kind: "knowledge"; item: WikidataEntity }
  | { kind: "source"; item: MediaSourceSearchRecord };

interface IndustrySession {
  ownerId: string;
  guildId: string;
  records: IndustryRecord[];
  createdAt: number;
}

const SESSION_TTL_MS = 15 * 60_000;

function nameOf(record: IndustryRecord): string {
  if (record.kind === "knowledge") return record.item.label;
  if (record.kind === "source") return record.item.title;
  return record.item.name;
}

function sourceOf(record: IndustryRecord): string {
  switch (record.kind) {
    case "anime-studio": return record.item.url;
    case "game-company": return record.item.sourceUrl;
    case "screen-company":
    case "tv-network": return record.item.sourceUrl;
    case "music-label": return record.item.sourceUrl;
    case "knowledge": return record.item.url;
    case "source": return record.item.url;
  }
}

function categoryTitle(category: IndustryCategory): string {
  const labels: Record<IndustryCategory, string> = {
    "anime-studio": "Animation studios",
    "game-company": "Game developers and publishers",
    "screen-company": "Film and television companies",
    "tv-network": "Television networks",
    "music-label": "Music labels",
    publisher: "Book publishers",
    knowledge: "Wikidata organizations",
  };
  return labels[category];
}

function correctionModal(token: string, index: number): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("industry:correction:" + token + ":" + index)
    .setTitle("Suggest organization correction")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("field").setLabel("Field name")
          .setStyle(TextInputStyle.Short).setMaxLength(80).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("value").setLabel("Proposed value")
          .setStyle(TextInputStyle.Paragraph).setMaxLength(1_000).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("evidence").setLabel("HTTPS evidence URL")
          .setStyle(TextInputStyle.Short).setMaxLength(500).setRequired(true),
      ),
    );
}

function searchModal(category: IndustryCategory): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("industry:search:" + category)
    .setTitle(("Search " + categoryTitle(category)).slice(0, 45))
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder()
        .setCustomId("query")
        .setLabel("Organization or company name")
        .setStyle(TextInputStyle.Short)
        .setMinLength(2)
        .setMaxLength(100)
        .setRequired(true),
    ));
}

function identityLinkModal(token: string, index: number, title: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("industry:link:" + token + ":" + index)
    .setTitle(("Link provider identity · " + title).slice(0, 45))
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("target").setLabel("Target provider:id")
          .setStyle(TextInputStyle.Short).setMaxLength(220).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("name").setLabel("Target organization name")
          .setStyle(TextInputStyle.Short).setMaxLength(200).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("url").setLabel("Canonical target HTTPS URL")
          .setStyle(TextInputStyle.Short).setMaxLength(500).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("evidence").setLabel("HTTPS evidence for identity match")
          .setStyle(TextInputStyle.Short).setMaxLength(500).setRequired(true),
      ),
    );
}

function industryReviewModal(kind: "correction" | "identity", id: string, title: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("industry:review:" + kind + ":" + id)
    .setTitle(("Review " + kind + " #" + id).slice(0, 45))
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("decision").setLabel("Decision: approve or reject")
          .setStyle(TextInputStyle.Short).setMinLength(6).setMaxLength(8).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("note").setLabel("Review note (optional)")
          .setStyle(TextInputStyle.Paragraph).setMaxLength(500).setRequired(false),
      ),
    );
}

function safeField(value: string | null | undefined, fallback = "Not supplied"): string {
  const clean = value?.trim();
  return clean ? clean.slice(0, 950) : fallback;
}

export class IndustryCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("industry")
    .setDescription("Explore studios, developers, publishers, networks, production companies and music labels.");

  private readonly anilist: AniListClient;
  private readonly igdb: IgdbClient;
  private readonly tmdb: TmdbClient;
  private readonly music: MusicDiscovery;
  private readonly mediaSources: MediaSourceClients;
  private readonly wikidata = new WikidataClient();
  private readonly sessions = new Map<string, IndustrySession>();

  constructor(config: BotConfig) {
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
    this.music = new MusicDiscovery(config);
    this.mediaSources = new MediaSourceClients(config);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.reply({
      ...this.homePayload(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false),
      flags: MessageFlags.Ephemeral,
    });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("industry:")) return false;
    const [, action, token, indexValue] = interaction.customId.split(":");
    if (action === "home") {
      await interaction.update(this.homePayload(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false));
      return true;
    }
    if (action === "review") {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review Industry submissions.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const [corrections, links] = await Promise.all([
        listPendingIndustryCorrections(interaction.guildId),
        listPendingIndustryIdentityLinks(interaction.guildId),
      ]);
      await interaction.update(this.reviewQueuePayload(corrections, links));
      return true;
    }
    if (action === "link" && token && indexValue) {
      const session = this.getSession(token, interaction.user.id, interaction.guildId);
      const index = Number(indexValue);
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      if (!record) {
        await interaction.reply({ content: "This organization selection expired. Search again to propose a provider link.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(identityLinkModal(token, index, nameOf(record)));
      return true;
    }
    if (action === "correct" && token && indexValue) {
      const session = this.getSession(token, interaction.user.id, interaction.guildId);
      const index = Number(indexValue);
      if (!session?.records[index]) {
        await interaction.reply({ content: "This organization selection expired. Search again to suggest a correction.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(correctionModal(token, index));
      return true;
    }
    if (action === "pins") {
      if (!interaction.guildId) {
        await interaction.reply({ content: "The server directory is only available inside a server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const pins = await listIndustryPins(interaction.guildId);
      await interaction.update(this.pinsPayload(
        pins,
        interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false,
      ));
      return true;
    }
    if (action === "search" && token) {
      await interaction.showModal(searchModal(token as IndustryCategory));
      return true;
    }
    if (action === "pin" && token && indexValue) {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to pin organizations.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const session = this.getSession(token, interaction.user.id, interaction.guildId);
      const index = Number(indexValue);
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      if (!record) {
        await interaction.reply({ content: "This organization selection expired. Search again to pin it.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const identity = this.providerIdentity(record);
      const inserted = await pinIndustryOrganization({
        guildId: interaction.guildId,
        provider: identity.provider,
        providerId: identity.providerId,
        displayName: nameOf(record),
        category: record.kind === "source"
          ? record.item.organizationType === "Animation studio" ? "anime-studio"
            : record.item.organizationType === "Television network" ? "tv-network" : "publisher"
          : record.kind,
        sourceUrl: sourceOf(record),
        pinnedBy: interaction.user.id,
      });
      await interaction.reply({
        content: inserted ? "**" + nameOf(record) + "** was added to this server's Industry directory." : "**" + nameOf(record) + "** is already pinned in this server's directory.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId.startsWith("industry:review:")) {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review Industry submissions.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const [, , kind, requestId] = interaction.customId.split(":");
      const decision = interaction.fields.getTextInputValue("decision").trim().toLowerCase();
      if ((kind !== "correction" && kind !== "identity") || !requestId
        || (decision !== "approve" && decision !== "reject")) {
        await interaction.reply({ content: "Enter a valid submission type and either approve or reject.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        const input = {
          guildId: interaction.guildId,
          requestId,
          reviewerId: interaction.user.id,
          decision: decision === "approve" ? "approved" as const : "rejected" as const,
          note: interaction.fields.getTextInputValue("note"),
        };
        const updated = kind === "correction"
          ? await reviewIndustryCorrectionRequest(input)
          : await reviewIndustryIdentityLinkRequest(input);
        await interaction.reply({
          content: updated
            ? "Industry " + kind + " #" + requestId + " was " + decision + "d. Provider data was not modified."
            : "That Industry submission is no longer pending in this server.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The Industry submission could not be reviewed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (interaction.customId.startsWith("industry:link:")) {
      const [, , token, indexText] = interaction.customId.split(":");
      const session = token ? this.getSession(token, interaction.user.id, interaction.guildId) : null;
      const index = Number(indexText);
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      if (!record || !interaction.guildId) {
        await interaction.reply({ content: "This organization selection expired. Search again to propose a provider link.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const target = interaction.fields.getTextInputValue("target").trim();
      const separator = target.indexOf(":");
      if (separator < 1 || separator === target.length - 1) {
        await interaction.reply({ content: "Enter the target as provider:id, for example igdb:company:123.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const identity = this.providerIdentity(record);
      try {
        const id = await createIndustryIdentityLinkRequest({
          guildId: interaction.guildId,
          sourceProvider: identity.provider,
          sourceProviderId: identity.providerId,
          sourceName: nameOf(record),
          sourceUrl: sourceOf(record),
          targetProvider: target.slice(0, separator),
          targetProviderId: target.slice(separator + 1),
          targetName: interaction.fields.getTextInputValue("name"),
          targetUrl: interaction.fields.getTextInputValue("url"),
          evidenceUrl: interaction.fields.getTextInputValue("evidence"),
          createdBy: interaction.user.id,
        });
        await interaction.reply({
          content: id
            ? "Provider identity link #" + id + " was submitted for this server's moderator review. The records remain separate until approved."
            : "That provider identity link is already present in this server.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The provider identity link could not be saved.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (interaction.customId.startsWith("industry:correction:")) {
      const [, , token, indexText] = interaction.customId.split(":");
      const index = Number(indexText);
      const session = token ? this.getSession(token, interaction.user.id, interaction.guildId) : null;
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      if (!record || !interaction.guildId) {
        await interaction.reply({ content: "This organization selection expired. Search again to suggest a correction.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const identity = this.providerIdentity(record);
      try {
        const id = await createIndustryCorrectionRequest({
          guildId: interaction.guildId,
          provider: identity.provider,
          providerId: identity.providerId,
          organizationName: nameOf(record),
          fieldName: interaction.fields.getTextInputValue("field"),
          proposedValue: interaction.fields.getTextInputValue("value"),
          evidenceUrl: interaction.fields.getTextInputValue("evidence"),
          createdBy: interaction.user.id,
        });
        await interaction.reply({
          content: id ? "Correction suggestion #" + id + " was submitted to this server's moderators. Provider data has not been changed." : "The correction could not be saved.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The correction could not be saved.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (!interaction.customId.startsWith("industry:search:")) return false;
    const category = interaction.customId.slice("industry:search:".length) as IndustryCategory;
    const query = interaction.fields.getTextInputValue("query").trim();
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    try {
      const records = await this.search(query, category);
      if (!records.length) {
        await interaction.editReply({ content: "No matching organizations were returned by the connected provider. Check the provider's source directory and try another category." });
        return true;
      }
      const token = randomUUID().replaceAll("-", "").slice(0, 12);
      this.pruneSessions();
      this.sessions.set(token, {
        ownerId: interaction.user.id,
        guildId: interaction.guildId ?? "dm",
        records,
        createdAt: Date.now(),
      });
      await interaction.editReply(this.resultsPayload(token, category, records));
    } catch (error) {
      await interaction.editReply({ content: error instanceof Error ? error.message : "The selected organization provider is temporarily unavailable." });
    }
    return true;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId === "industry:review-select") {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review Industry submissions.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const value = interaction.values[0] ?? "";
      const [kind, requestId] = value.split(":");
      if (!requestId || (kind !== "correction" && kind !== "identity")) {
        await interaction.reply({ content: "Choose a valid Industry submission.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const request = kind === "correction"
        ? await getIndustryCorrectionRequest(interaction.guildId, requestId)
        : await getIndustryIdentityLinkRequest(interaction.guildId, requestId);
      if (!request || request.status !== "pending") {
        await interaction.reply({ content: "That Industry submission is no longer pending in this server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (request.created_by === interaction.user.id) {
        await interaction.reply({ content: "You cannot review your own Industry submission.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const title = kind === "correction"
        ? (request as Awaited<ReturnType<typeof getIndustryCorrectionRequest>>)?.organization_name ?? "organization"
        : (request as Awaited<ReturnType<typeof getIndustryIdentityLinkRequest>>)?.source_name ?? "organization";
      await interaction.showModal(industryReviewModal(kind, requestId, title));
      return true;
    }
    if (interaction.customId === "industry:unpin") {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to remove directory entries.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const pinId = interaction.values[0];
      if (!pinId) {
        await interaction.reply({ content: "Select an organization to remove.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      const removed = await removeIndustryPin(interaction.guildId, pinId);
      const pins = await listIndustryPins(interaction.guildId);
      await interaction.editReply(this.pinsPayload(
        pins,
        interaction.memberPermissions.has(PermissionFlagsBits.ManageGuild),
        removed ? "The organization was removed from this server's directory." : "That organization was already removed.",
      ));
      return true;
    }
    if (!interaction.customId.startsWith("industry:select:")) return false;
    const token = interaction.customId.slice("industry:select:".length);
    const session = this.getSession(token, interaction.user.id, interaction.guildId);
    const index = Number(interaction.values[0]);
    if (!session || !Number.isInteger(index) || !session.records[index]) {
      await interaction.reply({ content: "This Industry selection expired. Open /industry again.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.deferUpdate();
    await interaction.editReply(await this.profilePayload(
      token,
      session.records[index]!,
      session.guildId === "dm" ? null : session.guildId,
    ));
    return true;
  }

  private homePayload(canReview = false) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Industry directory")
      .setDescription([
        "Discover the organizations behind media: studios, game companies, screen production, networks and music labels.",
        "",
        "Profiles keep provider identities separate. Similar names are not merged without evidence, and missing credits remain missing.",
      ].join("\n"));
    const categories: Array<[string, IndustryCategory]> = [
      ["Animation studios", "anime-studio"],
      ["Game companies", "game-company"],
      ["Film / TV companies", "screen-company"],
      ["TV networks", "tv-network"],
      ["Music labels", "music-label"],
      ["Book publishers", "publisher"],
      ["Wikidata", "knowledge"],
    ];
    const rows = categories.reduce<ActionRowBuilder<ButtonBuilder>[]>((result, item, index) => {
      const rowIndex = Math.floor(index / 3);
      result[rowIndex] ??= new ActionRowBuilder<ButtonBuilder>();
      result[rowIndex]!.addComponents(new ButtonBuilder()
        .setCustomId("industry:search:" + item[1])
        .setLabel(item[0])
        .setStyle(ButtonStyle.Secondary));
      return result;
    }, []);
    rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("industry:pins").setLabel("Server directory").setStyle(ButtonStyle.Secondary),
      ...(canReview ? [new ButtonBuilder().setCustomId("industry:review").setLabel("Review submissions").setStyle(ButtonStyle.Secondary)] : []),
    ));
    return { embeds: [embed], components: rows };
  }

  private reviewQueuePayload(
    corrections: Awaited<ReturnType<typeof listPendingIndustryCorrections>>,
    links: Awaited<ReturnType<typeof listPendingIndustryIdentityLinks>>,
  ) {
    const items = [
      ...corrections.map(request => ({
        value: "correction:" + request.id,
        label: ("Correction #" + request.id + " · " + request.organization_name).slice(0, 100),
        description: (request.field_name + " · " + request.proposed_value).slice(0, 100),
      })),
      ...links.map(request => ({
        value: "identity:" + request.id,
        label: ("Identity #" + request.id + " · " + request.source_name).slice(0, 100),
        description: (request.source_provider + " → " + request.target_provider + ": " + request.target_name).slice(0, 100),
      })),
    ].slice(0, 25);
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Pending Industry submissions")
      .setDescription(items.length
        ? items.map(item => "**" + item.label + "**\n" + item.description).join("\n\n").slice(0, 3_800)
        : "There are no pending Industry corrections or identity links for this server.");
    const components: Array<ActionRowBuilder<StringSelectMenuBuilder> | ActionRowBuilder<ButtonBuilder>> = [];
    if (items.length) {
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId("industry:review-select")
          .setPlaceholder("Choose a submission to review")
          .addOptions(items.map(item => ({ label: item.label, description: item.description, value: item.value }))),
      ));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("industry:home").setLabel("Industry home").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components };
  }

  private pinsPayload(
    pins: Awaited<ReturnType<typeof listIndustryPins>>,
    canManage: boolean,
    status?: string,
  ) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Server industry directory")
      .setDescription([
        ...(status ? [status, ""] : []),
        pins.map((pin, index) =>
          (index + 1) + ". **[" + pin.displayName + "](" + pin.sourceUrl + ")**\n"
            + pin.category.replaceAll("-", " ") + " · " + pin.provider,
        ).join("\n\n") || "This server has not pinned any organizations yet.",
      ].join("\n").slice(0, 4_000));
    const components: Array<ActionRowBuilder<ButtonBuilder> | ActionRowBuilder<StringSelectMenuBuilder>> = [];
    if (canManage && pins.length) {
      const select = new StringSelectMenuBuilder()
        .setCustomId("industry:unpin")
        .setPlaceholder("Select an organization to remove")
        .setMinValues(1)
        .setMaxValues(1)
        .addOptions(pins.slice(0, 25).map(pin => ({
          label: pin.displayName.slice(0, 100),
          description: (pin.category.replaceAll("-", " ") + " · " + pin.provider).slice(0, 100),
          value: pin.id,
        })));
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("industry:home").setLabel("Industry home").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components };
  }

  private resultsPayload(token: string, category: IndustryCategory, records: IndustryRecord[]) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(categoryTitle(category))
      .setDescription(records.slice(0, 10).map((record, index) =>
        (index + 1) + ". **[" + nameOf(record).slice(0, 100) + "](" + sourceOf(record) + ")**\n"
          + this.recordProvider(record),
      ).join("\n\n").slice(0, 4000));
    const select = new StringSelectMenuBuilder()
      .setCustomId("industry:select:" + token)
      .setPlaceholder("Choose an organization")
      .addOptions(records.slice(0, 25).map((record, index) => ({
        label: nameOf(record).slice(0, 100),
        description: this.recordProvider(record).slice(0, 100),
        value: String(index),
      })));
    return {
      embeds: [embed],
      components: [new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
    };
  }

  private async search(query: string, category: IndustryCategory): Promise<IndustryRecord[]> {
    if (query.length < 2 || query.length > 100) return [];
    switch (category) {
      case "anime-studio": {
        const [anilist, external] = await Promise.all([
          this.anilist.searchStudios(query),
          this.mediaSources.searchOrganizations(query),
        ]);
        return [
          ...anilist.map(item => ({ kind: "anime-studio", item }) as IndustryRecord),
          ...external.filter(item => item.organizationType === "Animation studio")
            .map(item => ({ kind: "source", item }) as IndustryRecord),
        ].slice(0, 25);
      }
      case "game-company":
        return (await this.igdb.searchCompanies(query)).map(item => ({ kind: "game-company", item }));
      case "screen-company":
        return (await this.tmdb.searchCompanies(query)).map(item => ({ kind: "screen-company", item }));
      case "tv-network": {
        const shows = await this.tmdb.search(query, "tv");
        const resolved = await Promise.allSettled(shows.slice(0, 6).map(async show => ({
          title: show.title,
          networks: await this.tmdb.networksForTv(show.id),
        })));
        const unique = new Map<string, IndustryRecord>();
        for (const result of resolved) {
          if (result.status !== "fulfilled") continue;
          for (const item of result.value.networks) {
            unique.set("tmdb:" + item.id, { kind: "tv-network", item, discoveredFrom: result.value.title });
          }
        }
        const external = await this.mediaSources.searchOrganizations(query);
        for (const item of external.filter(source => source.organizationType === "Television network")) {
          unique.set("media-source:" + item.sourceId + ":" + item.providerId, { kind: "source", item });
        }
        return [...unique.values()].slice(0, 20);
      }
      case "music-label":
        return (await this.music.searchLabels(query)).map(item => ({ kind: "music-label", item }));
      case "publisher":
        return (await this.mediaSources.searchOrganizations(query))
          .filter(item => item.organizationType === "Publisher")
          .map(item => ({ kind: "source", item }));
      case "knowledge":
        return (await this.wikidata.searchEntities(query)).map(item => ({ kind: "knowledge", item }));
    }
  }

  private async profilePayload(token: string, record: IndustryRecord, guildId: string | null) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(nameOf(record).slice(0, 256))
      .setURL(sourceOf(record));
    const related: Array<{ title: string; url: string; role: string }> = [];

    switch (record.kind) {
      case "anime-studio": {
        const studio = await this.anilist.getPublicEntity(record.item.id, "STUDIO").catch(() => null);
        const item = studio ?? record.item;
        embed.setDescription(safeField(item.description, "AniList does not supply a studio description."));
        embed.addFields(
          { name: "Type", value: item.isAnimationStudio === true ? "Animation studio" : "Studio (type not confirmed)", inline: true },
          { name: "Provider ID", value: String(item.id), inline: true },
          { name: "Provider", value: "AniList", inline: true },
        );
        for (const work of item.works) related.push({ title: work.title, url: work.url, role: work.type + (work.role ? " · " + work.role : "") });
        if (item.image) embed.setThumbnail(item.image);
        break;
      }
      case "game-company": {
        const explorer = await this.igdb.getCompanyExplorer(record.item.id);
        const company = explorer?.company ?? record.item;
        embed.setDescription(safeField(company.description, "IGDB does not supply a company description."));
        embed.addFields(
          { name: "Provider ID", value: String(company.id), inline: true },
          { name: "Provider", value: "IGDB", inline: true },
          { name: "Website", value: safeField(company.websites[0] ?? null), inline: true },
        );
        for (const credit of explorer?.credits ?? []) {
          related.push({ title: credit.title, url: credit.sourceUrl, role: credit.roles.join(" / ") || "Company credit" });
        }
        if (company.logo) embed.setThumbnail(company.logo);
        if (explorer?.truncated) embed.setFooter({ text: "Showing the first 20 company credits." });
        break;
      }
      case "screen-company": {
        const company = await this.tmdb.companyDetails(record.item.id) ?? record.item;
        embed.setDescription(safeField(company.headquarters, "Headquarters not supplied") + " · "
          + safeField(company.originCountry, "Country unknown"));
        embed.addFields(
          { name: "Provider ID", value: String(company.id), inline: true },
          { name: "Provider", value: "TMDB", inline: true },
          { name: "Homepage", value: safeField(company.homepage), inline: true },
          { name: "Parent company", value: company.parentCompany?.name ?? "Not supplied", inline: true },
        );
        const [movies, shows] = await Promise.allSettled([
          this.tmdb.companyMedia(company.id, "movie"),
          this.tmdb.companyMedia(company.id, "tv"),
        ]);
        if (movies.status === "fulfilled") {
          for (const item of movies.value.slice(0, 8)) related.push({ title: item.title, url: item.sourceUrl, role: "Film production credit" });
        }
        if (shows.status === "fulfilled") {
          for (const item of shows.value.slice(0, 8)) related.push({ title: item.title, url: item.sourceUrl, role: "Television production credit" });
        }
        if (company.logo) embed.setThumbnail(company.logo);
        break;
      }
      case "tv-network": {
        const network = await this.tmdb.networkDetails(record.item.id) ?? record.item;
        embed.setDescription("Television network. Discovered through the network credits on **" + record.discoveredFrom.slice(0, 120) + "**.");
        embed.addFields(
          { name: "Provider ID", value: String(network.id), inline: true },
          { name: "Provider", value: "TMDB", inline: true },
          { name: "Country", value: safeField(network.originCountry), inline: true },
          { name: "Headquarters", value: safeField(network.headquarters), inline: true },
          { name: "Homepage", value: safeField(network.homepage), inline: true },
        );
        for (const show of await this.tmdb.networkShows(network.id).catch(() => [])) {
          related.push({ title: show.title, url: show.sourceUrl, role: "Network-associated series" });
        }
        if (network.logo) embed.setThumbnail(network.logo);
        break;
      }
      case "music-label": {
        const label = await this.music.label(record.item.id).catch(() => null) ?? record.item;
        embed.setDescription(safeField(label.disambiguation, "MusicBrainz label record."));
        embed.addFields(
          { name: "Label type", value: safeField(label.type), inline: true },
          { name: "Country", value: safeField(label.country), inline: true },
          { name: "Label code", value: safeField(label.labelCode), inline: true },
          { name: "Founded", value: safeField(label.beginDate), inline: true },
          { name: "Ended", value: safeField(label.endDate), inline: true },
          { name: "Provider ID", value: label.id, inline: true },
        );
        break;
      }
      case "knowledge": {
        const relations = await this.wikidata.organizationRelations(record.item.id).catch(() => []);
        embed.setDescription(safeField(record.item.description, "Wikidata does not supply a description."));
        embed.addFields(
          { name: "Wikidata ID", value: record.item.id, inline: true },
          { name: "Entity page", value: record.item.url, inline: false },
        );
        for (const relation of relations) {
          if (relation.subjectId === record.item.id) {
            related.push({
              title: relation.objectLabel ?? relation.objectId,
              url: "https://www.wikidata.org/wiki/" + relation.objectId,
              role: relation.propertyId === "P749" ? "Parent organization" : "Subsidiary",
            });
          } else {
            related.push({
              title: relation.subjectLabel ?? relation.subjectId,
              url: "https://www.wikidata.org/wiki/" + relation.subjectId,
              role: relation.propertyId === "P749" ? "Parent organization" : "Subsidiary",
            });
          }
        }
        break;
      }
      case "source": {
        embed.setDescription(safeField(record.item.summary, "The provider does not supply an organization description."));
        embed.addFields(
          { name: "Organization type", value: record.item.organizationType ?? "Organization", inline: true },
          { name: "Provider", value: record.item.sourceName, inline: true },
          { name: "Provider ID", value: record.item.providerId.slice(0, 100), inline: true },
          ...(record.item.attribution ? [{ name: "Attribution", value: record.item.attribution, inline: false }] : []),
        );
        break;
      }
    }

    if (guildId) {
      const identity = this.providerIdentity(record);
      const [corrections, identityLinks] = await Promise.all([
        listApprovedIndustryCorrections({ guildId, provider: identity.provider, providerId: identity.providerId }),
        listApprovedIndustryIdentityLinks({ guildId, provider: identity.provider, providerId: identity.providerId }),
      ]);
      if (corrections.length) {
        embed.addFields({
          name: "Guild-reviewed corrections",
          value: corrections.map(item => "**" + item.field_name + ":** " + item.proposed_value
            + " · [Evidence](" + item.evidence_url + ")").join("\n").slice(0, 1_000),
          inline: false,
        });
      }
      if (identityLinks.length) {
        embed.addFields({
          name: "Guild-reviewed provider identities",
          value: identityLinks.map(item => "[" + item.name + "](" + item.url + ") · "
            + item.provider + ":" + item.provider_id + " · [Evidence](" + item.evidence_url + ")").join("\n").slice(0, 1_000),
          inline: false,
        });
      }
    }
    embed.addFields({
      name: related.length ? "Related works and organizations" : "Associated records",
      value: related.slice(0, 12).map(item =>
        "[" + item.title.slice(0, 150) + "](" + item.url + ") · " + item.role.slice(0, 80),
      ).join("\n").slice(0, 1_000) || "The provider does not currently return linked credits for this record.",
      inline: false,
    });
    const referenceCategories = record.kind === "anime-studio"
      ? ["anime-manga", "chronology", "franchise-wiki"] as const
      : record.kind === "game-company"
        ? ["franchise-wiki", "knowledge"] as const
        : record.kind === "screen-company" || record.kind === "tv-network"
          ? ["screen", "franchise-wiki", "knowledge"] as const
          : record.kind === "music-label"
            ? ["music"] as const
            : record.kind === "source" && record.item.organizationType === "Publisher"
              ? ["books-comics", "chronology"] as const
              : ["knowledge"] as const;
    const sourceLinks = getMediaSourceResearchLinks(nameOf(record), referenceCategories)
      .filter(source => source.url && source.id !== (record.kind === "source" ? record.item.sourceId : ""))
      .slice(0, 5);
    if (sourceLinks.length) {
      embed.addFields({
        name: "Additional source references",
        value: sourceLinks.map(source => "[" + source.name + "](" + source.url + ") · " + source.status).join("\n").slice(0, 1_000),
        inline: false,
      });
    }
    const components = [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("industry:home").setLabel("Industry home").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("industry:correct:" + token + ":" + this.getTokenRecordIndex(token, record)).setLabel("Suggest correction").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("industry:link:" + token + ":" + this.getTokenRecordIndex(token, record)).setLabel("Suggest provider link").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("industry:pin:" + token + ":" + this.getTokenRecordIndex(token, record)).setLabel("Pin to server directory").setStyle(ButtonStyle.Secondary),
      ),
    ];
    return { embeds: [embed], components };
  }

  private getTokenRecordIndex(token: string, record: IndustryRecord): number {
    return this.sessions.get(token)?.records.indexOf(record) ?? -1;
  }

  private providerIdentity(record: IndustryRecord): { provider: string; providerId: string } {
    switch (record.kind) {
      case "anime-studio": return { provider: "anilist:studio", providerId: String(record.item.id) };
      case "game-company": return { provider: "igdb:company", providerId: String(record.item.id) };
      case "screen-company": return { provider: "tmdb:company", providerId: String(record.item.id) };
      case "tv-network": return { provider: "tmdb:network", providerId: String(record.item.id) };
      case "music-label": return { provider: "musicbrainz:label", providerId: record.item.id };
      case "knowledge": return { provider: "wikidata:entity", providerId: record.item.id };
      case "source": return { provider: "media-source:" + record.item.sourceId, providerId: record.item.providerId };
    }
  }

  private recordProvider(record: IndustryRecord): string {
    switch (record.kind) {
      case "anime-studio": return "AniList · Animation studio metadata";
      case "game-company": return "IGDB · Developer / publisher credits";
      case "screen-company": return "TMDB · Film and television production";
      case "tv-network": return "TMDB · Network credit, discovered from " + record.discoveredFrom;
      case "music-label": return "MusicBrainz · Label metadata";
      case "knowledge": return "Wikidata · Knowledge graph entity";
      case "source": return record.item.sourceName + " · " + (record.item.organizationType ?? "Organization metadata");
    }
  }

  private getSession(token: string, ownerId: string, guildId: string | null): IndustrySession | null {
    const session = this.sessions.get(token);
    if (!session || session.ownerId !== ownerId || session.guildId !== (guildId ?? "dm")
      || Date.now() - session.createdAt > SESSION_TTL_MS) {
      this.sessions.delete(token);
      return null;
    }
    return session;
  }

  private pruneSessions(): void {
    const now = Date.now();
    for (const [token, session] of this.sessions) {
      if (now - session.createdAt > SESSION_TTL_MS) this.sessions.delete(token);
    }
    while (this.sessions.size > 200) {
      const oldest = this.sessions.keys().next().value;
      if (oldest === undefined) break;
      this.sessions.delete(oldest);
    }
  }
}

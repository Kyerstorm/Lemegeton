import { randomUUID } from "node:crypto";
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  PermissionFlagsBits,
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
import { AniListClient, type AniListMedia } from "../../helpers/integration/anilist.js";
import { TmdbClient, type TmdbMedia } from "../../helpers/integration/tmdb.js";
import { IgdbClient, type IgdbGame } from "../../helpers/integration/igdb.js";
import { GoogleBooksClient, type GoogleBook } from "../../helpers/integration/google-books.js";
import { OpenLibraryClient, type OpenLibraryWork } from "../../helpers/integration/open-library.js";
import { KitsuClient, type KitsuMedia } from "../../helpers/integration/kitsu.js";
import { MangaDexClient, type MangaDexMedia } from "../../helpers/integration/mangadex.js";
import { MusicDiscovery, type MusicArtistResult, type MusicReleaseGroup } from "../../helpers/integration/music-discovery.js";
import { MediaSourceClients, type MediaSourceSearchRecord } from "../../helpers/integration/media-source-clients.js";
import { WikidataClient, type WikidataEntity } from "../../helpers/integration/wikidata.js";
import { aniListReleaseOrder, tmdbCollectionReleaseOrder } from "../../helpers/media/franchise-order.js";
import { normalizeTimelineDate, sortTimelineEvents, timelineDateFromParts, wikidataSequenceEvents, type TimelineEvent } from "../../helpers/media/timeline-events.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import {
  saveTimelineEvents,
  listTimelineEvents,
  createTimelineCorrectionRequest,
  listTimelineCorrectionRequests,
  getTimelineCorrectionRequest,
  reviewTimelineCorrectionRequest,
  listApprovedTimelineCorrections,
  type TimelineSequenceType,
  type TimelineCorrectionRequest,
} from "../../helpers/media/timeline-store.js";
import { getMediaSourceResearchLinks } from "../../helpers/media/media-source-adapters.js";

type TimelineCategory = "anime" | "manga" | "light-novel" | "screen" | "game" | "book" | "music" | "franchise-wiki";
type TimelineRecord =
  | { kind: "anilist"; category: "anime" | "manga" | "light-novel"; item: AniListMedia }
  | { kind: "tmdb"; category: "movie" | "tv"; item: TmdbMedia }
  | { kind: "igdb"; category: "game"; item: IgdbGame }
  | { kind: "google-books"; category: "book"; item: GoogleBook }
  | { kind: "open-library"; category: "book"; item: OpenLibraryWork }
  | { kind: "musicbrainz"; category: "music"; item: MusicArtistResult }
  | { kind: "kitsu"; category: "anime" | "manga"; item: KitsuMedia }
  | { kind: "mangadex"; category: "manga"; item: MangaDexMedia }
  | { kind: "external"; category: MediaSourceSearchRecord["category"]; item: MediaSourceSearchRecord }
  | { kind: "wikidata"; category: "franchise-wiki"; item: WikidataEntity };

type SequenceType = "release" | "publication" | "adaptation" | "continuity" | "in-universe";

interface TimelineSession {
  ownerId: string;
  guildId: string;
  records: TimelineRecord[];
  createdAt: number;
}

const SESSION_TTL_MS = 15 * 60_000;

function titleOf(record: TimelineRecord): string {
  switch (record.kind) {
    case "anilist": return record.item.title.english ?? record.item.title.romaji ?? record.item.title.native ?? "Untitled";
    case "tmdb": return record.item.title;
    case "igdb": return record.item.title;
    case "google-books": return record.item.title;
    case "open-library": return record.item.title;
    case "musicbrainz": return record.item.name;
    case "kitsu": return record.item.title;
    case "mangadex": return record.item.title;
    case "external": return record.item.title;
    case "wikidata": return record.item.label;
  }
}

function sourceOf(record: TimelineRecord): string {
  switch (record.kind) {
    case "anilist": return record.item.siteUrl;
    case "tmdb": return record.item.sourceUrl;
    case "igdb": return record.item.sourceUrl;
    case "google-books": return record.item.sourceUrl;
    case "open-library": return record.item.sourceUrl;
    case "musicbrainz": return "https://musicbrainz.org/artist/" + record.item.id;
    case "kitsu": return record.item.sourceUrl;
    case "mangadex": return record.item.sourceUrl;
    case "external": return record.item.url;
    case "wikidata": return record.item.url;
  }
}

function dateOf(record: TimelineRecord) {
  switch (record.kind) {
    case "anilist": return timelineDateFromParts(record.item.startDate);
    case "tmdb": return normalizeTimelineDate(record.item.releaseDate);
    case "igdb": return normalizeTimelineDate(record.item.releaseDate);
    case "google-books": return normalizeTimelineDate(record.item.publishedDate);
    case "open-library": return normalizeTimelineDate(record.item.firstPublishYear ? String(record.item.firstPublishYear) : null);
    case "musicbrainz": return normalizeTimelineDate(record.item.beginDate);
    case "kitsu": return normalizeTimelineDate(record.item.startDate);
    case "mangadex": return normalizeTimelineDate(record.item.year ? String(record.item.year) : null);
    case "external": return normalizeTimelineDate(record.item.category === "community" ? null : record.item.date);
    case "wikidata": return normalizeTimelineDate(null);
  }
}

function correctionModal(token: string, index: number, mode: SequenceType): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("timeline:correction:" + token + ":" + index + ":" + mode)
    .setTitle("Suggest a chronology correction")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("date").setLabel("Correct date (YYYY, YYYY-MM or YYYY-MM-DD)")
          .setStyle(TextInputStyle.Short).setMinLength(4).setMaxLength(10).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("evidence").setLabel("HTTPS evidence URL")
          .setStyle(TextInputStyle.Short).setMaxLength(500).setRequired(true),
      ),
    );
}

function reviewCorrectionModal(request: TimelineCorrectionRequest): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("timeline:review:" + request.id)
    .setTitle(("Review correction #" + request.id).slice(0, 45))
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("decision").setLabel("Decision: approve or reject")
          .setStyle(TextInputStyle.Short).setMinLength(6).setMaxLength(8).setRequired(true),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("note").setLabel("Moderator note (optional)")
          .setStyle(TextInputStyle.Paragraph).setMaxLength(500).setRequired(false),
      ),
    );
}

function searchModal(category: TimelineCategory): ModalBuilder {
  const title = category === "light-novel" ? "Search light novels" : "Search " + category.replace("-", " ");
  return new ModalBuilder()
    .setCustomId("timeline:search:" + category)
    .setTitle(title.slice(0, 45))
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder()
        .setCustomId("query")
        .setLabel("Title, franchise, artist or creator")
        .setStyle(TextInputStyle.Short)
        .setMinLength(2)
        .setMaxLength(100)
        .setRequired(true),
    ));
}

function sourceLabel(record: TimelineRecord): string {
  switch (record.kind) {
    case "anilist": return "AniList";
    case "tmdb": return "TMDB";
    case "igdb": return "IGDB";
    case "google-books": return "Google Books";
    case "open-library": return "Open Library";
    case "musicbrainz": return "MusicBrainz";
    case "kitsu": return "Kitsu";
    case "mangadex": return "MangaDex";
    case "external": return record.item.sourceName;
    case "wikidata": return "Wikidata";
  }
}

function event(
  id: string,
  title: string,
  date: ReturnType<typeof normalizeTimelineDate>,
  eventType: string,
  sourceName: string,
  sourceUrl: string,
  description: string | null = null,
  sequenceType: TimelineEvent["sequenceType"] = "release",
): TimelineEvent {
  return { id, title, description, date, eventType, sourceName, sourceUrl, sequenceType };
}

export class TimelineCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("timeline")
    .setDescription("Explore source-backed media chronology across books, anime, games, film, television and music.");

  private readonly anilist: AniListClient;
  private readonly tmdb: TmdbClient;
  private readonly igdb: IgdbClient;
  private readonly books: GoogleBooksClient;
  private readonly openLibrary: OpenLibraryClient;
  private readonly music: MusicDiscovery;
  private readonly kitsu = new KitsuClient();
  private readonly mangaDex = new MangaDexClient();
  private readonly mediaSources: MediaSourceClients;
  private readonly wikidata: WikidataClient;
  private readonly sessions = new Map<string, TimelineSession>();

  constructor(private readonly config: BotConfig) {
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
    this.igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
    this.books = new GoogleBooksClient(config.googleBooksApiKey);
    this.openLibrary = new OpenLibraryClient();
    this.music = new MusicDiscovery(config);
    this.mediaSources = new MediaSourceClients(config);
    this.wikidata = new WikidataClient();
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.reply({
      ...this.homePayload(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false),
      flags: MessageFlags.Ephemeral,
    });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("timeline:")) return false;
    const [, action, value, sequence] = interaction.customId.split(":");
    if (action === "home") {
      await interaction.update(this.homePayload(interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false));
      return true;
    }
    if (action === "review") {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review chronology corrections.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const requests = await listTimelineCorrectionRequests(interaction.guildId);
      await interaction.update(this.reviewQueuePayload(requests));
      return true;
    }
    if (action === "correct" && value && sequence) {
      const [indexText, modeText] = sequence.split("-");
      const index = Number(indexText);
      const mode = modeText as SequenceType;
      if (!Number.isInteger(index) || !["release","publication","adaptation","continuity","in-universe"].includes(mode)) {
        await interaction.reply({ content: "That chronology selection is invalid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const session = this.getSession(value, interaction.user.id, interaction.guildId);
      if (!session?.records[index]) {
        await interaction.reply({ content: "This Timeline selection expired. Search again to suggest a correction.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (!interaction.guildId) {
        await interaction.reply({ content: "Chronology corrections are scoped to a server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(correctionModal(value, index, mode));
      return true;
    }
    if (action === "search" && value) {
      await interaction.showModal(searchModal(value as TimelineCategory));
      return true;
    }
    if (action === "view" && value && sequence) {
      const session = this.getSession(value, interaction.user.id, interaction.guildId);
      if (!session) {
        await interaction.reply({ content: "This Timeline view expired. Open /timeline again.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const selected = Number(sequence.split("-")[0]);
      const mode = sequence.slice(sequence.indexOf("-") + 1) as SequenceType;
      if (!Number.isInteger(selected) || !session.records[selected]) {
        await interaction.reply({ content: "That Timeline selection is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      await interaction.editReply(await this.detailPayload(value, session.records[selected]!, mode, interaction.guildId));
      return true;
    }
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId.startsWith("timeline:review:")) {
      const requestId = interaction.customId.slice("timeline:review:".length);
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review chronology corrections.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const decision = interaction.fields.getTextInputValue("decision").trim().toLowerCase();
      if (decision !== "approve" && decision !== "reject") {
        await interaction.reply({ content: "Enter either approve or reject.", flags: MessageFlags.Ephemeral });
        return true;
      }
      try {
        const updated = await reviewTimelineCorrectionRequest({
          guildId: interaction.guildId,
          requestId,
          reviewerId: interaction.user.id,
          decision: decision === "approve" ? "approved" : "rejected",
          note: interaction.fields.getTextInputValue("note"),
        });
        await interaction.reply({
          content: updated
            ? "Chronology correction #" + requestId + " was " + decision + "d. Provider data remains unchanged."
            : "That correction is no longer pending in this server.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The correction could not be reviewed.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (interaction.customId.startsWith("timeline:correction:")) {
      const [, , token, indexText, modeText] = interaction.customId.split(":");
      const index = Number(indexText);
      const mode = modeText as SequenceType;
      const session = token ? this.getSession(token, interaction.user.id, interaction.guildId) : null;
      const record = session && Number.isInteger(index) ? session.records[index] : null;
      if (!record || !interaction.guildId || !["release","publication","adaptation","continuity","in-universe"].includes(mode)) {
        await interaction.reply({ content: "This correction request expired or is no longer valid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const proposedDate = interaction.fields.getTextInputValue("date").trim();
      const evidenceUrl = interaction.fields.getTextInputValue("evidence").trim();
      const identity = this.providerIdentity(record);
      try {
        const id = await createTimelineCorrectionRequest({
          guildId: interaction.guildId,
          provider: identity.provider,
          providerId: identity.providerId,
          entityTitle: titleOf(record),
          sequenceType: mode,
          eventKey: "selected:" + sourceOf(record),
          proposedDate,
          evidenceUrl,
          createdBy: interaction.user.id,
        });
        await interaction.reply({
          content: id ? "Correction suggestion #" + id + " was submitted for this server's moderators. Provider data has not been changed." : "The correction could not be saved.",
          flags: MessageFlags.Ephemeral,
        });
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "The correction could not be saved.", flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (!interaction.customId.startsWith("timeline:search:")) return false;
    const category = interaction.customId.slice("timeline:search:".length) as TimelineCategory;
    const query = interaction.fields.getTextInputValue("query").trim();
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    try {
      const records = await this.search(query, category);
      if (!records.length) {
        await interaction.editReply({ content: "No matching records were returned by the connected providers. Try a more specific title or another category." });
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
      await interaction.editReply(this.resultsPayload(token, records));
    } catch (error) {
      await interaction.editReply({ content: error instanceof Error ? error.message : "The selected providers are temporarily unavailable." });
    }
    return true;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId === "timeline:review-select") {
      if (!interaction.guildId || !interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Manage Server permission is required to review chronology corrections.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const requestId = interaction.values[0];
      const request = requestId ? await getTimelineCorrectionRequest(interaction.guildId, requestId) : null;
      if (!request || request.status !== "pending") {
        await interaction.reply({ content: "That correction is no longer pending in this server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (request.created_by === interaction.user.id) {
        await interaction.reply({ content: "You cannot review your own chronology correction.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(reviewCorrectionModal(request));
      return true;
    }
    if (!interaction.customId.startsWith("timeline:select:")) return false;
    const token = interaction.customId.slice("timeline:select:".length);
    const session = this.getSession(token, interaction.user.id, interaction.guildId);
    const index = Number(interaction.values[0]);
    if (!session || !Number.isInteger(index) || !session.records[index]) {
      await interaction.reply({ content: "This Timeline selection expired. Open /timeline again.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.deferUpdate();
    await interaction.editReply(await this.detailPayload(token, session.records[index]!, "release", interaction.guildId));
    return true;
  }

  private homePayload(canReview = false) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Timeline")
      .setDescription([
        "Explore how works and franchises connect across media.",
        "",
        "**Choose a source category to begin.** Dates retain the precision returned by each provider. Release order is not the same as in-universe chronology.",
      ].join("\n"));
    const categories: Array<[string, TimelineCategory]> = [
      ["Anime", "anime"], ["Manga", "manga"], ["Light novels", "light-novel"],
      ["Film & TV", "screen"], ["Games", "game"], ["Books", "book"], ["Music", "music"],
      ["Franchise wikis", "franchise-wiki"],
    ];
    const rows = categories.reduce<ActionRowBuilder<ButtonBuilder>[]>((result, item, index) => {
      const rowIndex = Math.floor(index / 4);
      result[rowIndex] ??= new ActionRowBuilder<ButtonBuilder>();
      result[rowIndex]!.addComponents(new ButtonBuilder()
        .setCustomId("timeline:search:" + item[1])
        .setLabel(item[0])
        .setStyle(ButtonStyle.Secondary));
      return result;
    }, []);
    if (canReview) {
      rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("timeline:review").setLabel("Review corrections").setStyle(ButtonStyle.Secondary),
      ));
    }
    return { embeds: [embed], components: rows };
  }

  private reviewQueuePayload(requests: TimelineCorrectionRequest[]) {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Pending chronology corrections")
      .setDescription(requests.length
        ? requests.map(request => "**#" + request.id + " · " + request.entity_title.slice(0, 100) + "**\n"
          + request.proposed_value + " · " + request.sequence_type + " · by <@" + request.created_by + ">\n"
          + "[Evidence](" + request.evidence_url + ")").join("\n\n").slice(0, 3_800)
        : "There are no pending chronology corrections for this server.");
    const components: Array<ActionRowBuilder<StringSelectMenuBuilder> | ActionRowBuilder<ButtonBuilder>> = [];
    if (requests.length) {
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder()
          .setCustomId("timeline:review-select")
          .setPlaceholder("Choose a correction to review")
          .addOptions(requests.slice(0, 25).map(request => ({
            label: ("#" + request.id + " · " + request.entity_title).slice(0, 100),
            description: (request.proposed_value + " · " + request.sequence_type).slice(0, 100),
            value: request.id,
          }))),
      ));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("timeline:home").setLabel("Timeline home").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components };
  }

  private resultsPayload(token: string, records: TimelineRecord[]) {
    const options = records.slice(0, 25).map((record, index) => ({
      label: titleOf(record).slice(0, 100),
      description: (sourceLabel(record) + " · " + dateOf(record).label).slice(0, 100),
      value: String(index),
    }));
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle("Timeline search")
      .setDescription(records.slice(0, 10).map((record, index) => {
        return (index + 1) + ". **[" + titleOf(record).slice(0, 100) + "](" + sourceOf(record) + ")**\n"
          + sourceLabel(record) + " · " + dateOf(record).label;
      }).join("\n\n").slice(0, 4000));
    const select = new StringSelectMenuBuilder()
      .setCustomId("timeline:select:" + token)
      .setPlaceholder("Choose a work or artist")
      .addOptions(options);
    return {
      embeds: [embed],
      components: [new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
    };
  }

  private async search(query: string, category: TimelineCategory): Promise<TimelineRecord[]> {
    const tasks: Array<Promise<TimelineRecord[]>> = [];
    if (category === "franchise-wiki") {
      const [wikiRecords, chronology, wikidataEntities] = await Promise.all([
        this.mediaSources.searchEnabledMediaWikis(query),
        this.mediaSources.searchChronologyReferences(query),
        this.wikidata.searchEntities(query),
      ]);
      if (!wikiRecords.length && !chronology.length && !wikidataEntities.length
        && !this.config.mediaWikiEnabledSources.length && !this.config.mediaSourceScrapeAllowlist.length) {
        throw new Error("No franchise wikis or chronology sources are enabled for automated search.");
      }
      return [
        ...wikiRecords.map(item => ({ kind: "external", category: item.category, item }) as TimelineRecord),
        ...chronology.map(item => ({ kind: "external", category: item.category, item }) as TimelineRecord),
        ...wikidataEntities.map(item => ({ kind: "wikidata", category: "franchise-wiki", item }) as TimelineRecord),
      ].slice(0, 25);
    }
    if (category === "anime" || category === "manga" || category === "light-novel") {
      const type = category === "anime" ? "ANIME" : "MANGA";
      tasks.push(this.anilist.search(query, type, category === "light-novel")
        .then(items => items.map(item => ({ kind: "anilist", category, item }) as TimelineRecord)));
      if (category !== "light-novel") {
        const kitsuType = category === "anime" ? "anime" : "manga";
        tasks.push(this.kitsu.search(query, kitsuType)
          .then(items => items.map(item => ({ kind: "kitsu", category: kitsuType, item }) as TimelineRecord)));
        if (category === "manga") {
          tasks.push(this.mangaDex.search(query)
            .then(items => items.map(item => ({ kind: "mangadex", category: "manga", item }) as TimelineRecord)));
        }
      }
    } else if (category === "screen") {
      tasks.push(
        this.tmdb.search(query, "movie").then(items => items.map(item => ({ kind: "tmdb", category: "movie", item }) as TimelineRecord)),
        this.tmdb.search(query, "tv").then(items => items.map(item => ({ kind: "tmdb", category: "tv", item }) as TimelineRecord)),
      );
    } else if (category === "game") {
      tasks.push(this.igdb.search(query).then(items => items.map(item => ({ kind: "igdb", category: "game", item }) as TimelineRecord)));
    } else if (category === "book") {
      tasks.push(
        this.books.search(query).then(items => items.map(item => ({ kind: "google-books", category: "book", item }) as TimelineRecord)),
        this.openLibrary.searchTitle(query).then(items => items.map(item => ({ kind: "open-library", category: "book", item }) as TimelineRecord)),
      );
    } else if (category === "music") {
      tasks.push(this.music.searchArtists(query).then(items => items.map(item => ({ kind: "musicbrainz", category: "music", item }) as TimelineRecord)));
    }
    if (category === "anime" || category === "manga" || category === "book" || category === "music") {
      tasks.push(this.mediaSources.search(query, category)
        .then(items => items.map(item => ({ kind: "external", category: item.category, item }) as TimelineRecord)));
    }
    tasks.push(this.mediaSources.searchChronologyReferences(query)
      .then(items => items.map(item => ({ kind: "external", category: item.category, item }) as TimelineRecord)));
    const settled = await Promise.allSettled(tasks);
    const records = settled.flatMap(result => result.status === "fulfilled" ? result.value : []);
    if (!records.length && settled.every(result => result.status === "rejected")) {
      throw new Error("All providers for this category are unavailable or not configured.");
    }
    const unique = new Map<string, TimelineRecord>();
    for (const record of records) {
      const key = record.kind === "external"
        ? "external:" + record.item.sourceId + ":" + record.item.providerId
        : record.kind + ":" + sourceOf(record);
      if (!unique.has(key)) unique.set(key, record);
    }
    return [...unique.values()].slice(0, 25);
  }

  private async detailPayload(token: string, record: TimelineRecord, mode: SequenceType, guildId: string | null) {
    const identity = this.providerIdentity(record);
    let events: TimelineEvent[] = [];
    let providerError: unknown = null;
    try {
      events = await this.buildEvents(record, mode);
    } catch (error) {
      providerError = error;
    }

    let usingCachedEvents = false;
    if (events.length) {
      await saveTimelineEvents({
        provider: identity.provider,
        providerId: identity.providerId,
        sequenceType: mode,
        events: events.map(item => ({ ...item, sequenceType: mode })),
      });
    } else {
      try {
        events = await listTimelineEvents(identity.provider, identity.providerId, mode);
        usingCachedEvents = events.length > 0;
      } catch (error) {
        if (providerError) throw providerError;
        throw error;
      }
    }
    if (!events.length && providerError) throw providerError;
    const sequenceLabels: Record<SequenceType, string> = {
      release: "Release / broadcast",
      publication: "Publication",
      adaptation: "Adaptations",
      continuity: "Continuity links",
      "in-universe": "In-universe order",
    };
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(titleOf(record).slice(0, 256))
      .setURL(sourceOf(record))
      .setDescription("**Sequence:** " + sequenceLabels[mode] + "\n"
        + "**Source:** " + sourceLabel(record) + "\n"
        + "**Date precision:** dates are shown only as supplied by the source."
        + (usingCachedEvents ? "\n**Data:** cached provider events; live retrieval was unavailable." : ""));
    if (record.kind === "anilist") {
      embed.addFields(
        { name: "Format", value: record.item.format ?? "Unknown", inline: true },
        { name: "Status", value: record.item.status ?? "Unknown", inline: true },
        { name: "Studios", value: record.item.studios.join(", ").slice(0, 900) || "Not supplied", inline: false },
      );
      if (record.item.coverImage) embed.setThumbnail(record.item.coverImage);
    } else if (record.kind === "tmdb") {
      embed.addFields(
        { name: "Category", value: record.category === "movie" ? "Film" : "Television", inline: true },
        { name: "Status", value: record.item.status ?? "Unknown", inline: true },
        { name: "First release", value: dateOf(record).label, inline: true },
      );
      if (record.item.image) embed.setThumbnail(record.item.image);
    } else if (record.kind === "igdb") {
      embed.addFields(
        { name: "Platforms", value: record.item.platforms.slice(0, 8).join(", ") || "Not supplied", inline: false },
        { name: "Developers", value: record.item.developers.slice(0, 5).join(", ") || "Not supplied", inline: true },
        { name: "Publishers", value: record.item.publishers.slice(0, 5).join(", ") || "Not supplied", inline: true },
      );
      if (record.item.image) embed.setThumbnail(record.item.image);
    } else if (record.kind === "google-books") {
      embed.addFields(
        { name: "Publisher", value: record.item.publisher ?? "Unknown", inline: true },
        { name: "ISBN", value: record.item.isbn13 ?? record.item.isbn10 ?? "Not supplied", inline: true },
        { name: "Language", value: record.item.language ?? "Unknown", inline: true },
      );
      if (record.item.image) embed.setThumbnail(record.item.image);
    } else if (record.kind === "open-library") {
      embed.addFields(
        { name: "Authors", value: record.item.authors.join(", ").slice(0, 900) || "Unknown", inline: true },
        { name: "Publishers", value: record.item.publishers.join(", ").slice(0, 900) || "Unknown", inline: true },
        { name: "First published", value: dateOf(record).label, inline: true },
      );
      if (record.item.coverUrl) embed.setThumbnail(record.item.coverUrl);
    } else if (record.kind === "kitsu") {
      embed.addFields(
        { name: "Format", value: record.item.format ?? "Unknown", inline: true },
        { name: "Status", value: record.item.status ?? "Unknown", inline: true },
        { name: "Age rating", value: record.item.ageRating, inline: true },
        { name: "Genres", value: record.item.genres.slice(0, 8).join(", ") || "Not supplied", inline: false },
      );
      if (record.item.image) embed.setThumbnail(record.item.image);
    } else if (record.kind === "mangadex") {
      embed.addFields(
        { name: "Authors", value: record.item.authors.slice(0, 5).join(", ") || "Unknown", inline: true },
        { name: "Artists", value: record.item.artists.slice(0, 5).join(", ") || "Unknown", inline: true },
        { name: "Status", value: record.item.status ?? "Unknown", inline: true },
        { name: "Language", value: record.item.originalLanguage ?? "Unknown", inline: true },
        { name: "Publication year", value: record.item.year ? String(record.item.year) : "Not supplied", inline: true },
      );
      if (record.item.coverUrl) embed.setThumbnail(record.item.coverUrl);
    } else if (record.kind === "external") {
      embed.setDescription(record.item.summary ?? "The provider returned a source-linked record without a description.");
      embed.addFields(
        { name: "Source", value: record.item.sourceName, inline: true },
        { name: "Category", value: record.item.category, inline: true },
        { name: "Provider ID", value: record.item.providerId.slice(0, 100), inline: true },
        { name: "Date", value: dateOf(record).label, inline: true },
        ...(record.item.attribution ? [{ name: "Attribution", value: record.item.attribution, inline: false }] : []),
      );
    } else if (record.kind === "wikidata") {
      embed.addFields(
        { name: "Wikidata ID", value: record.item.id, inline: true },
        { name: "Description", value: record.item.description ?? "Not supplied", inline: false },
        { name: "Date", value: "No calendar date supplied", inline: true },
      );
    } else {
      embed.addFields(
        { name: "Artist type", value: record.item.type ?? "Unknown", inline: true },
        { name: "Origin", value: [record.item.beginArea, record.item.country].filter(Boolean).join(", ") || "Unknown", inline: true },
        { name: "Active since", value: dateOf(record).label, inline: true },
      );
    }
    const eventLines = events.slice(0, 12).map(item =>
      (item.date.label === "Date not supplied" ? "—" : item.date.label) + " · **" + item.title.slice(0, 120) + "**"
      + " · " + item.eventType + " · [" + item.sourceName + "](" + item.sourceUrl + ")",
    );
    embed.addFields({
      name: events.length ? "Source-backed events" : "No verified events for this sequence",
      value: eventLines.join("\n").slice(0, 1_000) || "The connected providers do not establish this sequence for the selected work.",
      inline: false,
    });
    const referenceCategories = record.kind === "tmdb"
        ? ["screen", "franchise-wiki", "knowledge"] as const
        : record.kind === "igdb"
          ? ["franchise-wiki", "knowledge"] as const
          : record.kind === "google-books" || record.kind === "open-library"
            ? ["books-comics", "chronology"] as const
            : record.kind === "musicbrainz"
              ? ["music"] as const
              : record.kind === "external"
                ? record.item.category === "screen" ? ["screen", "franchise-wiki", "knowledge"] as const
                  : record.item.category === "book" ? ["books-comics", "chronology"] as const
                    : record.item.category === "music" ? ["music"] as const
                      : ["anime-manga", "chronology", "franchise-wiki"] as const
                : ["anime-manga", "chronology", "franchise-wiki"] as const;
    const references = getMediaSourceResearchLinks(titleOf(record), referenceCategories)
      .filter(source => source.url)
      .slice(0, 6);
    if (references.length) {
      embed.addFields({
        name: "Additional source references",
        value: references.map(source => "[" + source.name + "](" + source.url + ") · " + source.status).join("\n").slice(0, 1_000),
        inline: false,
      });
    }
    if (guildId) {
      const corrections = await listApprovedTimelineCorrections({
        guildId,
        provider: identity.provider,
        providerId: identity.providerId,
        sequenceType: mode,
        eventKey: "selected:" + sourceOf(record),
      });
      if (corrections.length) {
        embed.addFields({
          name: "Guild-reviewed date corrections",
          value: corrections.map(item => item.proposed_value + " · [Evidence](" + item.evidence_url + ")").join("\n").slice(0, 900),
          inline: false,
        });
      }
    }
    if (events.length) embed.setFooter({ text: events.length + " event(s) · Provider records, not an asserted universal canon order" });
    const buttons = [
      ["Release", "release"], ["Publication", "publication"], ["Adaptation", "adaptation"],
      ["Continuity", "continuity"], ["In-universe", "in-universe"],
    ].map(([label, value]) => new ButtonBuilder()
      .setCustomId("timeline:view:" + token + ":" + valueOfIndex(record, this.getTokenRecordIndex(token, record)) + "-" + value)
      .setLabel(label!)
      .setStyle(value === mode ? ButtonStyle.Primary : ButtonStyle.Secondary));
    const components: ActionRowBuilder<ButtonBuilder>[] = [];
    for (let i = 0; i < buttons.length; i += 5) components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(buttons.slice(i, i + 5)));
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("timeline:correct:" + token + ":" + this.getTokenRecordIndex(token, record) + "-" + mode)
        .setLabel("Suggest correction").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("timeline:home").setLabel("Timeline home").setStyle(ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components };
  }

  private async buildEvents(record: TimelineRecord, mode: SequenceType): Promise<TimelineEvent[]> {
    const events: TimelineEvent[] = [];
    const selectedTitle = titleOf(record);
    const selectedSource = sourceLabel(record);
    if (mode === "release" || mode === "publication") {
      const date = dateOf(record);
      if (date.label !== "Date not supplied") events.push(event(
        "selected:" + sourceOf(record),
        selectedTitle,
        date,
        mode === "publication" ? "First publication / edition" : "First release",
        selectedSource,
        sourceOf(record),
        null,
        mode,
      ));
    }
    if (record.kind === "anilist") {
      const relationships = record.item.relations;
      for (const relation of relationships) {
        const relevant = mode === "adaptation"
          ? ["ADAPTATION", "SOURCE", "CHARACTER"].includes(relation.relation.toUpperCase())
          : mode === "continuity" || mode === "in-universe"
            ? ["PREQUEL", "SEQUEL", "PARENT", "SIDE_STORY", "ALTERNATIVE", "SPIN_OFF"].includes(relation.relation.toUpperCase())
            : (mode === "release" || mode === "publication");
        if (!relevant) continue;
        events.push(event(
          "anilist:" + relation.id,
          relation.title,
          timelineDateFromParts(relation.startDate),
          relation.relation.replaceAll("_", " "),
          "AniList",
          relation.url,
          mode === "in-universe" ? "Provider relationship only; this does not establish a calendar date inside the fictional world." : null,
          mode === "publication" ? "publication" : mode,
        ));
      }
      if ((mode === "release" || mode === "publication") && relationships.length) {
        const order = aniListReleaseOrder({
          title: selectedTitle,
          url: sourceOf(record),
          startDate: record.item.startDate,
        }, relationships.map(item => ({
          title: item.title,
          url: item.url,
          startDate: item.startDate,
        })));
        if (order) {
          return order.flatMap(item => item.url ? [event(
            "ordered:" + item.url,
            item.title,
            normalizeTimelineDate(item.date),
            "Provider related-work release date",
            "AniList",
            item.url,
            null,
            mode,
          )] : []);
        }
      }
    } else if (record.kind === "tmdb") {
      if (mode === "release" && record.category === "movie") {
        try {
          const collection = await this.tmdb.collectionForMovie(record.item.id);
          if (collection) {
            const order = tmdbCollectionReleaseOrder(collection.items);
            if (order) {
              return order.flatMap(item => item.url ? [event(
                "tmdb:" + item.url,
                item.title,
                normalizeTimelineDate(item.date),
                "Collection film release",
                "TMDB",
                item.url,
                null,
                "release",
              )] : []);
            }
          }
        } catch {
          // A collection lookup is supplemental; the selected film date remains available.
        }
      }
      if (mode === "release" && record.category === "tv") {
        try {
          const details = await this.tmdb.tvDetails(record.item.id);
          if (details) {
            const seasons = await Promise.allSettled(details.seasons.slice(0, 4).map(season => this.tmdb.tvSeason(record.item.id, season.seasonNumber)));
            for (const result of seasons) {
              if (result.status !== "fulfilled" || !result.value) continue;
              for (const episode of result.value.episodes.slice(0, 20)) {
                if (!episode.airDate) continue;
                events.push(event(
                  "tmdb-episode:" + episode.sourceUrl,
                  result.value.name + " · " + episode.name,
                  normalizeTimelineDate(episode.airDate),
                  "Episode broadcast",
                  "TMDB",
                  episode.sourceUrl,
                  null,
                  "release",
                ));
              }
            }
          }
        } catch {
          // TV detail/season lookups are supplemental to the first-air date.
        }
      }
    } else if (record.kind === "musicbrainz" && (mode === "release" || mode === "publication")) {
      try {
        const releases: MusicReleaseGroup[] = await this.music.discography(record.item.id);
        for (const release of releases) {
          events.push(event(
            "musicbrainz-release:" + release.id,
            release.title,
            normalizeTimelineDate(release.firstReleaseDate),
            release.type ?? "Music release",
            "MusicBrainz",
            "https://musicbrainz.org/release-group/" + release.id,
            null,
            "release",
          ));
        }
      } catch {
        // Artist details remain available when discography retrieval is unavailable.
      }
    } else if (record.kind === "wikidata" && mode === "continuity") {
      try {
        const relations = await this.wikidata.sequenceRelations(record.item.id);
        events.push(...wikidataSequenceEvents(relations));
      } catch {
        // Keep the Wikidata entity usable when the optional sequence query is unavailable.
      }
    }
    return sortTimelineEvents(events).slice(0, 25);
  }

  private providerIdentity(record: TimelineRecord): { provider: string; providerId: string } {
    switch (record.kind) {
      case "anilist": return { provider: "anilist:" + record.item.type.toLowerCase(), providerId: String(record.item.id) };
      case "tmdb": return { provider: "tmdb:" + record.category, providerId: String(record.item.id) };
      case "igdb": return { provider: "igdb:game", providerId: String(record.item.id) };
      case "google-books": return { provider: "google-books:volume", providerId: record.item.id };
      case "open-library": return { provider: "open-library:work", providerId: record.item.workId };
      case "musicbrainz": return { provider: "musicbrainz:artist", providerId: record.item.id };
      case "kitsu": return { provider: "kitsu:" + record.category, providerId: record.item.id };
      case "mangadex": return { provider: "mangadex:manga", providerId: record.item.id };
      case "external": return { provider: "media-source:" + record.item.sourceId, providerId: record.item.providerId };
      case "wikidata": return { provider: "wikidata:entity", providerId: record.item.id };
    }
  }

  private getSession(token: string, ownerId: string, guildId: string | null): TimelineSession | null {
    const session = this.sessions.get(token);
    if (!session || session.ownerId !== ownerId || session.guildId !== (guildId ?? "dm")
      || Date.now() - session.createdAt > SESSION_TTL_MS) {
      this.sessions.delete(token);
      return null;
    }
    return session;
  }

  private getTokenRecordIndex(token: string, record: TimelineRecord): number {
    return this.sessions.get(token)?.records.indexOf(record) ?? -1;
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

function valueOfIndex(record: TimelineRecord, index: number): string {
  return String(Math.max(0, index));
}

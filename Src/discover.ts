import { randomInt } from "node:crypto";
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  SlashCommandBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
import type { BotConfig } from "../Helpers/config.js";
import { AniListClient, type AniListMedia, type AniListMediaType } from "../Helpers/anilist.js";
import { GoogleBooksClient, type GoogleBook } from "../Helpers/google-books.js";
import { IgdbClient, type IgdbGame } from "../Helpers/igdb.js";
import { homeEmbed, navigationButtons } from "../Helpers/discord.js";
import { TmdbClient, type TmdbMedia } from "../Helpers/tmdb.js";
import { cleanText } from "../Helpers/security.js";

type Category = "all" | "anime" | "manga" | "light_novel" | "book" | "movie" | "tv" | "game";
type SearchRecord =
  | { provider: "AniList"; category: "anime" | "manga" | "light_novel"; item: AniListMedia }
  | { provider: "Google Books"; category: "book"; item: GoogleBook }
  | { provider: "TMDB"; category: "movie" | "tv"; item: TmdbMedia }
  | { provider: "IGDB"; category: "game"; item: IgdbGame };

const CATEGORIES: Array<{ label: string; value: Category; emoji: string }> = [
  { label: "All media", value: "all", emoji: "🌐" },
  { label: "Anime", value: "anime", emoji: "📺" },
  { label: "Manga", value: "manga", emoji: "📚" },
  { label: "Light novels", value: "light_novel", emoji: "📖" },
  { label: "Books", value: "book", emoji: "📕" },
  { label: "Films", value: "movie", emoji: "🎬" },
  { label: "Television", value: "tv", emoji: "📡" },
  { label: "Games", value: "game", emoji: "🎮" },
];

function categoryLabel(category: Category): string {
  return CATEGORIES.find((item) => item.value === category)?.label ?? "Media";
}

function safeDescription(value: string | null | undefined, limit = 900): string {
  const cleaned = cleanText((value ?? "").replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&").replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">"), limit);
  return cleaned || "No description supplied by the metadata provider.";
}

function anilistRecord(item: AniListMedia, category: "anime" | "manga" | "light_novel"): SearchRecord {
  return { provider: "AniList", category, item };
}

function toEmbed(record: SearchRecord): EmbedBuilder {
  if (record.provider === "AniList") {
    const item = record.item;
    const title = item.title.english ?? item.title.romaji ?? item.title.native ?? "Untitled";
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle(title.slice(0, 256))
      .setURL(item.siteUrl)
      .setDescription(safeDescription(item.description))
      .addFields(
        { name: "Provider", value: "AniList", inline: true },
        { name: "Type", value: record.category === "light_novel" ? "Light novel" : record.category, inline: true },
        { name: "Format", value: item.format?.replaceAll("_", " ") ?? "Unavailable", inline: true },
        { name: "Status", value: item.status?.replaceAll("_", " ") ?? "Unavailable", inline: true },
        { name: item.type === "ANIME" ? "Episodes" : "Chapters", value: String(item.episodes ?? item.chapters ?? "Unavailable"), inline: true },
        { name: "Score", value: item.averageScore === null ? "Not rated" : `${item.averageScore}/100`, inline: true },
        { name: "Genres", value: item.genres.slice(0, 8).join(" · ") || "Unavailable", inline: false },
      )
      .setFooter({ text: `AniList · Source metadata` });
    if (item.startDate?.year) embed.addFields({ name: "Release year", value: String(item.startDate.year), inline: true });
    if (item.studios.length) embed.addFields({ name: "Studios", value: item.studios.join(", ").slice(0, 900), inline: false });
    if (item.staff.length) embed.addFields({ name: "Creators / staff", value: item.staff.join(", ").slice(0, 900), inline: false });
    if (item.relations.length) {
      embed.addFields({
        name: "Provider relationships",
        value: item.relations.slice(0, 5).map((relation) => `[${relation.title}](${relation.url}) · ${relation.relation.replaceAll("_", " ")}`).join("\n").slice(0, 1000),
        inline: false,
      });
    }
    if (item.coverImage) embed.setThumbnail(item.coverImage);
    if (item.bannerImage) embed.setImage(item.bannerImage);
    return embed;
  }

  if (record.provider === "Google Books") {
    const item = record.item;
    const embed = new EmbedBuilder()
      .setColor(0x4285f4)
      .setTitle(item.title.slice(0, 256))
      .setURL(item.sourceUrl)
      .setDescription(safeDescription(item.description))
      .addFields(
        { name: "Provider", value: "Google Books", inline: true },
        { name: "Authors", value: item.authors.join(", ") || "Unavailable", inline: true },
        { name: "Publisher", value: item.publisher ?? "Unavailable", inline: true },
        { name: "Published", value: item.publishedDate ?? "Unavailable", inline: true },
        { name: "Pages", value: String(item.pageCount ?? "Unavailable"), inline: true },
        { name: "ISBN", value: item.isbn ?? "Unavailable", inline: true },
        { name: "Categories", value: item.categories.join(", ") || "Unavailable", inline: false },
      )
      .setFooter({ text: "Google Books · Source metadata" });
    if (item.image) embed.setThumbnail(item.image);
    return embed;
  }

  if (record.provider === "TMDB") {
    const item = record.item;
    const embed = new EmbedBuilder()
      .setColor(0x01b4e4)
      .setTitle(item.title.slice(0, 256))
      .setURL(item.sourceUrl)
      .setDescription(safeDescription(item.overview))
      .addFields(
        { name: "Provider", value: "TMDB", inline: true },
        { name: "Category", value: item.category === "movie" ? "Film" : "Television", inline: true },
        { name: "Release", value: item.releaseDate ?? "Unavailable", inline: true },
        { name: "Rating", value: item.rating === null ? "Not rated" : `${item.rating.toFixed(1)}/10 (TMDB)`, inline: true },
        { name: "Status", value: item.status ?? "Unavailable", inline: true },
      )
      .setFooter({ text: "TMDB · Source metadata" });
    if (item.image) embed.setThumbnail(item.image);
    return embed;
  }

  const item = record.item;
  const embed = new EmbedBuilder()
    .setColor(0x9147ff)
    .setTitle(item.title.slice(0, 256))
    .setURL(item.sourceUrl)
    .setDescription(safeDescription(item.summary))
    .addFields(
      { name: "Provider", value: "IGDB", inline: true },
      { name: "First release", value: item.releaseDate ?? "Unavailable", inline: true },
      { name: "Genres", value: item.genres.join(", ") || "Unavailable", inline: false },
      { name: "Platforms", value: item.platforms.join(", ") || "Unavailable", inline: false },
      { name: "Developers", value: item.developers.join(", ") || "Unavailable", inline: true },
      { name: "Publishers", value: item.publishers.join(", ") || "Unavailable", inline: true },
    )
    .setFooter({ text: "IGDB · Source metadata" });
  if (item.image?.startsWith("https://")) embed.setThumbnail(item.image);
  return embed;
}

function detailsButtons(record: SearchRecord): ActionRowBuilder<ButtonBuilder>[] {
  if (record.provider !== "AniList") return [];
  return [new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId(`discover:recommend:${record.item.type}:${record.item.id}`)
      .setLabel("Related recommendations")
      .setStyle(ButtonStyle.Secondary),
  )];
}

function searchModal(category: Category): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(`discover:search:${category}`)
    .setTitle(`Search ${categoryLabel(category)}`)
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder()
          .setCustomId("query")
          .setLabel("Title or search phrase")
          .setPlaceholder("Enter a title")
          .setStyle(TextInputStyle.Short)
          .setMinLength(2)
          .setMaxLength(100)
          .setRequired(true),
      ),
    );
}

function homePanel(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const embed = homeEmbed(
    "Media Intelligence",
    "Explore media through the sources that actually provide it. Choose a category to search, browse trending titles or discover a random work. Provider attribution stays attached to every result.",
    [
      { name: "Anime & manga", value: "AniList", inline: true },
      { name: "Books & light novels", value: "Google Books / AniList", inline: true },
      { name: "Films & television", value: "TMDB", inline: true },
      { name: "Video games", value: "IGDB, with Steam account support in /profile", inline: true },
    ],
  );
  const rows: ActionRowBuilder<ButtonBuilder>[] = [];
  for (let offset = 0; offset < CATEGORIES.length; offset += 4) {
    const row = new ActionRowBuilder<ButtonBuilder>();
    for (const category of CATEGORIES.slice(offset, offset + 4)) {
      row.addComponents(new ButtonBuilder()
        .setCustomId(`discover:search:${category.value}`)
        .setLabel(category.label)
        .setEmoji(category.emoji)
        .setStyle(ButtonStyle.Primary));
    }
    rows.push(row);
  }
  const explore = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("discover:trending:anime").setLabel("Trending anime").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:trending:manga").setLabel("Trending manga").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:trending:movie").setLabel("Trending films").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:random:all").setLabel("Surprise me").setStyle(ButtonStyle.Secondary),
  );
  const random = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("discover:random:anime").setLabel("Random anime").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:random:manga").setLabel("Random manga").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:random:book").setLabel("Random book").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:random:game").setLabel("Random game").setStyle(ButtonStyle.Secondary),
  );
  rows.push(explore, random);
  return { embeds: [embed], components: rows };
}

export class DiscoverCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("discover")
    .setDescription("Explore media across supported metadata providers")
    .addStringOption((option) => option.setName("query").setDescription("Search for a title").setMinLength(2).setMaxLength(100))
    .addStringOption((option) => option.setName("category").setDescription("Media category").addChoices(
      ...CATEGORIES.map((category) => ({ name: category.label, value: category.value })),
    ))
    .addStringOption((option) => option.setName("compare_to").setDescription("Second title to compare against").setMinLength(2).setMaxLength(100));

  private readonly anilist: AniListClient;
  private readonly books: GoogleBooksClient;
  private readonly tmdb: TmdbClient;
  private readonly igdb: IgdbClient;

  constructor(config: BotConfig) {
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.books = new GoogleBooksClient(config.googleBooksApiKey);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
    this.igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const query = interaction.options.getString("query")?.trim();
    const compareTo = interaction.options.getString("compare_to")?.trim();
    const category = (interaction.options.getString("category") ?? "anime") as Category;
    if (!query) {
      const home = homePanel();
      await interaction.reply({ ...home, flags: MessageFlags.Ephemeral });
      return;
    }
    if (compareTo) {
      await this.compareAndRespond(interaction, query, compareTo, category);
      return;
    }
    await this.searchAndRespond(interaction, query, category);
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const [, action, categoryValue, maybeId] = interaction.customId.split(":");
    if (action === "search" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.showModal(searchModal(categoryValue as Category));
      return true;
    }
    if (action === "trending" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const results = await this.fetchTrending(categoryValue as Category);
      await this.presentResults(interaction, results, `Trending ${categoryLabel(categoryValue as Category)}`);
      return true;
    }
    if (action === "random" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const results = await this.fetchTrending(categoryValue as Category);
      const selected = results.length ? [results[randomInt(results.length)]!] : [];
      await this.presentResults(interaction, selected, `Random discovery · ${categoryLabel(categoryValue as Category)}`);
      return true;
    }
    if (action === "recommend" && (categoryValue === "ANIME" || categoryValue === "MANGA") && maybeId) {
      const mediaId = Number(maybeId);
      if (!Number.isSafeInteger(mediaId) || mediaId < 1) {
        await interaction.reply({ content: "That media reference is invalid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const results = await this.anilist.recommendations(mediaId, categoryValue as AniListMediaType);
      await this.presentResults(interaction, results.map((item) => anilistRecord(item, categoryValue === "ANIME" ? "anime" : "manga")), "Related AniList recommendations");
      return true;
    }
    if (action === "home") {
      await interaction.update(homePanel());
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    const [, action, categoryValue] = interaction.customId.split(":");
    if (action !== "search" || !CATEGORIES.some((item) => item.value === categoryValue)) return false;
    await this.searchAndRespond(interaction, interaction.fields.getTextInputValue("query"), categoryValue as Category);
    return true;
  }

  private async compareAndRespond(
    interaction: ChatInputCommandInteraction,
    firstTitle: string,
    secondTitle: string,
    category: Category,
  ): Promise<void> {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const [first, second] = await Promise.all([
      this.fetchSearch(firstTitle, category),
      this.fetchSearch(secondTitle, category),
    ]);
    const left = first[0];
    const right = second[0];
    if (!left || !right) {
      await interaction.editReply({
        content: "Both titles need a matching metadata-provider result before they can be compared.",
        embeds: [],
      });
      return;
    }
    await interaction.editReply({
      content: `Comparison · ${categoryLabel(category)}\nThe records below come from their original metadata providers. Missing fields are not inferred.`,
      embeds: [toEmbed(left), toEmbed(right)],
      components: [],
      allowedMentions: { parse: [] },
    });
  }

  private async searchAndRespond(
    interaction: ChatInputCommandInteraction | ModalSubmitInteraction,
    query: string,
    category: Category,
  ): Promise<void> {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const results = await this.fetchSearch(query, category);
    await this.presentResults(interaction, results, `Search results · ${categoryLabel(category)}`);
  }

  private async fetchSearch(query: string, category: Category): Promise<SearchRecord[]> {
    if (category === "all") {
      const providers = await Promise.allSettled([
        this.anilist.search(query, "ANIME").then((items) => items.map((item) => anilistRecord(item, "anime"))),
        this.anilist.search(query, "MANGA").then((items) => items.map((item) => anilistRecord(item, "manga"))),
        this.anilist.search(query, "MANGA", true).then((items) => items.map((item) => anilistRecord(item, "light_novel"))),
        this.books.search(query).then((items) => items.map((item) => ({ provider: "Google Books" as const, category: "book" as const, item }))),
        this.tmdb.search(query, "movie").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "movie" as const, item }))),
        this.tmdb.search(query, "tv").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "tv" as const, item }))),
        this.igdb.search(query).then((items) => items.map((item) => ({ provider: "IGDB" as const, category: "game" as const, item }))),
      ]);
      return providers.flatMap((provider) => provider.status === "fulfilled" ? provider.value : []);
    }
    switch (category) {
      case "anime": return (await this.anilist.search(query, "ANIME")).map((item) => anilistRecord(item, "anime"));
      case "manga": return (await this.anilist.search(query, "MANGA")).map((item) => anilistRecord(item, "manga"));
      case "light_novel": return (await this.anilist.search(query, "MANGA", true)).map((item) => anilistRecord(item, "light_novel"));
      case "book": return (await this.books.search(query)).map((item) => ({ provider: "Google Books", category: "book", item }));
      case "movie": return (await this.tmdb.search(query, "movie")).map((item) => ({ provider: "TMDB", category: "movie", item }));
      case "tv": return (await this.tmdb.search(query, "tv")).map((item) => ({ provider: "TMDB", category: "tv", item }));
      case "game": return (await this.igdb.search(query)).map((item) => ({ provider: "IGDB", category: "game", item }));
    }
  }

  private async fetchTrending(category: Category): Promise<SearchRecord[]> {
    if (category === "all") {
      const providers = await Promise.allSettled([
        this.anilist.trending("ANIME").then((items) => items.map((item) => anilistRecord(item, "anime"))),
        this.anilist.trending("MANGA").then((items) => items.map((item) => anilistRecord(item, "manga"))),
        this.books.search("popular fiction").then((items) => items.map((item) => ({ provider: "Google Books" as const, category: "book" as const, item }))),
        this.tmdb.trending("movie").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "movie" as const, item }))),
        this.tmdb.trending("tv").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "tv" as const, item }))),
        this.igdb.search("popular").then((items) => items.map((item) => ({ provider: "IGDB" as const, category: "game" as const, item }))),
      ]);
      return providers.flatMap((provider) => provider.status === "fulfilled" ? provider.value : []);
    }
    switch (category) {
      case "anime": return (await this.anilist.trending("ANIME")).map((item) => anilistRecord(item, "anime"));
      case "manga": return (await this.anilist.trending("MANGA")).map((item) => anilistRecord(item, "manga"));
      case "light_novel": return (await this.anilist.search("light novel", "MANGA", true)).map((item) => anilistRecord(item, "light_novel"));
      case "book": return (await this.books.search("popular fiction")).map((item) => ({ provider: "Google Books", category: "book", item }));
      case "movie": return (await this.tmdb.trending("movie")).map((item) => ({ provider: "TMDB", category: "movie", item }));
      case "tv": return (await this.tmdb.trending("tv")).map((item) => ({ provider: "TMDB", category: "tv", item }));
      case "game": return (await this.igdb.search("popular")).map((item) => ({ provider: "IGDB", category: "game", item }));
    }
  }

  private async presentResults(
    interaction: ButtonInteraction | ChatInputCommandInteraction | ModalSubmitInteraction,
    results: SearchRecord[],
    title: string,
  ): Promise<void> {
    if (!results.length) {
      await interaction.editReply({ embeds: [homeEmbed("No results found", "The selected provider returned no matching records. Try a more specific title or a different category.")] });
      return;
    }
    const embeds = results.slice(0, 10).map(toEmbed);
    const first = results[0];
    const components = first ? detailsButtons(first) : [];
    if (components.length) components.push(navigationButtons("discover", [{ id: "home", label: "Back to discovery" }]));
    await interaction.editReply({
      content: title,
      embeds,
      components,
      allowedMentions: { parse: [] },
    });
  }
}

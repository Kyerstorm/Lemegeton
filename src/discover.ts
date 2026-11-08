import { secureRandBelow } from "../helpers/crypto-random.js";
import {
  ActionRowBuilder,
  AttachmentBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
  type RoleSelectMenuInteraction,
  type ChannelSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";
import type { BotConfig } from "../helpers/config.js";
import { AniListClient, type AniListMedia, type AniListMediaType, type AniListSearchFilters, type AniListCreator } from "../helpers/anilist.js";
import {SteamClient,type SteamStoreGame} from "../helpers/steam.js";
import { GoogleBooksClient, type GoogleBook } from "../helpers/google-books.js";
import { IgdbClient, type IgdbGame } from "../helpers/igdb.js";
import { homeEmbed, navigationButtons } from "../helpers/discord.js";
import { TmdbClient, type TmdbMedia } from "../helpers/tmdb.js";
import { getGuildMediaRegion } from "../helpers/media-region.js";
import { cleanText } from "../helpers/security.js";
import { findAtlasRelationships, recordProviderRelationships } from "../helpers/atlas.js";
import { renderAtlasSnapshot } from "../helpers/atlas-renderer.js";
import { logger } from "../helpers/logger.js";
import { loadingMessage } from "../helpers/emoji.js";


type Category = "all" | "anime" | "manga" | "light_novel" | "book" | "movie" | "tv" | "game";
type DiscoverFilters = AniListSearchFilters;
type SearchRecord =
  | { provider: "AniList"; category: "anime" | "manga" | "light_novel"; item: AniListMedia }
  | { provider: "Google Books"; category: "book"; item: GoogleBook }
  | { provider: "TMDB"; category: "movie" | "tv"; item: TmdbMedia }
  | { provider: "IGDB"; category: "game"; item: IgdbGame }
  | { provider: "Steam"; category: "game"; item: SteamStoreGame };

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

function randomOne<T>(items: T[]): T[] {
  return items.length ? [items[secureRandBelow(items.length)]!] : [];
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
    if(item.trailer)embed.addFields({name:"Official trailer",value:`[Watch on ${item.trailer.site}](${item.trailer.url})`,inline:true});
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

  if (record.provider === "Steam") {
    const item=record.item;
    const price=item.isFree?"Free to Play":item.price?`${item.price.final} · US store`: "Price unavailable";
    const embed=new EmbedBuilder().setColor(item.isFree?0x2ecc71:0x5865f2)
      .setTitle(item.title.slice(0,256)).setURL(`https://store.steampowered.com/app/${item.appId}`)
      .setDescription(safeDescription(item.shortDescription,500))
      .addFields(
        {name:"Provider",value:"Steam Store",inline:true},
        {name:"Price",value:price,inline:true},
        {name:"Release",value:item.comingSoon?"Coming soon":item.releaseDate??"Unavailable",inline:true},
        {name:"Genres",value:item.genres.join(", ")||"Unavailable",inline:false},
        {name:"Platforms",value:item.platforms.join(", ")||"Unavailable",inline:true},
        {name:"Developers",value:item.developers.join(", ")||"Unavailable",inline:true},
        {name:"Publishers",value:item.publishers.join(", ")||"Unavailable",inline:true},
      ).setFooter({text:"Steam Store · US store metadata"});
    if(item.headerImage)embed.setImage(item.headerImage);
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
  if (record.provider === "AniList") {
    return [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`discover:recommend:${record.item.type}:${record.item.id}`)
        .setLabel("Related recommendations")
        .setStyle(ButtonStyle.Secondary),
    )];
  }
  if(record.provider==="IGDB"&&record.category==="game"){
    return [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId(`discover:similar:game:${record.item.id}`).setLabel("Similar games").setStyle(ButtonStyle.Secondary),
    )];
  }
  return [];
}

function creatorSearchModal():ModalBuilder{
 return new ModalBuilder().setCustomId("discover:creator-search").setTitle("Explore a creator").addComponents(
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("query").setLabel("Creator name").setPlaceholder("Writer, artist or voice actor").setStyle(TextInputStyle.Short).setMinLength(2).setMaxLength(80).setRequired(true)),
 );
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
      { name: "Video games", value: "IGDB + Steam Store; account data in /profile", inline: true },
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
    new ButtonBuilder().setCustomId("discover:creator").setLabel("Creator Explorer").setStyle(ButtonStyle.Secondary),
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
    .addStringOption((option) => option.setName("compare_to").setDescription("Second title to compare against").setMinLength(2).setMaxLength(100))
    .addStringOption((option) => option.setName("genre").setDescription("AniList genre filter").addChoices(
      ...["Action","Adventure","Comedy","Drama","Fantasy","Horror","Mystery","Psychological","Romance","Sci-Fi","Thriller"].map(value=>({name:value,value})),
    ))
    .addIntegerOption((option) => option.setName("year_from").setDescription("Earliest release year").setMinValue(1970).setMaxValue(2100))
    .addIntegerOption((option) => option.setName("year_to").setDescription("Latest release year").setMinValue(1970).setMaxValue(2100))
    .addStringOption((option) => option.setName("status").setDescription("AniList status").addChoices(
      ...["FINISHED","RELEASING","NOT_YET_RELEASED","CANCELLED","HIATUS"].map(value=>({name:value.replaceAll("_"," "),value})),
    ))
    .addStringOption((option) => option.setName("media_format").setDescription("AniList format").addChoices(
      ...["TV","TV_SHORT","MOVIE","SPECIAL","OVA","ONA","MANGA","NOVEL","ONE_SHOT"].map(value=>({name:value.replaceAll("_"," "),value})),
    ))
    .addStringOption((option) => option.setName("season").setDescription("Anime season").addChoices(
      {name:"Winter",value:"WINTER"},{name:"Spring",value:"SPRING"},{name:"Summer",value:"SUMMER"},{name:"Fall",value:"FALL"},
    ))
    .addIntegerOption((option) => option.setName("season_year").setDescription("Anime season year").setMinValue(1970).setMaxValue(2100))
    .addStringOption((option) => option.setName("view").setDescription("Choose a discovery view").addChoices(
      { name: "Search results", value: "search" },
      { name: "Knowledge Atlas", value: "atlas" },
      { name: "Creator Explorer", value: "creators" },
      { name: "Where to watch", value: "availability" },
      { name: "Trailers and videos", value: "videos" },
      { name: "Movie collection guide", value: "collection" },
    ))
    .addStringOption((option) => option.setName("region").setDescription("Two-letter availability region, for example IE or US").setMinLength(2).setMaxLength(2));

  private readonly config: BotConfig;
  private readonly anilist: AniListClient;
  private readonly books: GoogleBooksClient;
  private readonly tmdb: TmdbClient;
  private readonly igdb: IgdbClient;
  private readonly steam:SteamClient;

  constructor(config: BotConfig) {
    this.config = config;
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.books = new GoogleBooksClient(config.googleBooksApiKey);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
    this.igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
    this.steam=new SteamClient(config.steamApiKey);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const query = interaction.options.getString("query")?.trim();
    const compareTo = interaction.options.getString("compare_to")?.trim();
    const category = (interaction.options.getString("category") ?? "anime") as Category;
    const view = interaction.options.getString("view") ?? "search";
    const filters: DiscoverFilters = {
      genre:interaction.options.getString("genre")??undefined,
      yearFrom:interaction.options.getInteger("year_from")??undefined,
      yearTo:interaction.options.getInteger("year_to")??undefined,
      status:interaction.options.getString("status")??undefined,
      format:interaction.options.getString("media_format")??undefined,
      season:interaction.options.getString("season")??undefined,
      seasonYear:interaction.options.getInteger("season_year")??undefined,
    };
    const hasFilters=Object.values(filters).some(value=>value!==undefined);
    if(filters.yearFrom&&filters.yearTo&&filters.yearFrom>filters.yearTo){
      await interaction.reply({content:"The earliest release year cannot be later than the latest release year.",flags:MessageFlags.Ephemeral});return;
    }
    if(hasFilters&&!["anime","manga","light_novel"].includes(category)){
      await interaction.reply({content:"These filters are provided by AniList and apply to anime, manga and light novels. Choose one of those categories.",flags:MessageFlags.Ephemeral});return;
    }
    if((filters.season||filters.seasonYear)&&category!=="anime"){
      await interaction.reply({content:"Season and season year filters apply to anime only.",flags:MessageFlags.Ephemeral});return;
    }
    if(filters.format){
      const allowed=category==="anime"?["TV","TV_SHORT","MOVIE","SPECIAL","OVA","ONA"]:category==="manga"?["MANGA","ONE_SHOT","NOVEL"]:["NOVEL"];
      if(!allowed.includes(filters.format)){
        await interaction.reply({content:"That format is not supported by the selected media category.",flags:MessageFlags.Ephemeral});return;
      }
    }
    if (!query) {
      const home = homePanel();
      await interaction.reply({ ...home, flags: MessageFlags.Ephemeral });
      return;
    }
    if(view==="creators"){
      await this.creatorAndRespond(interaction,query,category);
      return;
    }
    if (view === "atlas") {
      await this.atlasAndRespond(interaction, query, category, filters);
      return;
    }
    if (view === "collection") {
      if (category !== "movie") {
        await interaction.reply({content:"Collection guides require the Films category.",flags:MessageFlags.Ephemeral});
        return;
      }
      await this.tmdbCollectionSelectionAndRespond(interaction, query);
      return;
    }
    if (view === "availability" || view === "videos") {
      if (category !== "movie" && category !== "tv") {
        await interaction.reply({content:"Where-to-watch and video views require the Films or Television category.",flags:MessageFlags.Ephemeral});
        return;
      }
      const region = (interaction.options.getString("region") ?? await getGuildMediaRegion(interaction.guildId)).trim().toUpperCase();
      if (!/^[A-Z]{2}$/.test(region)) {
        await interaction.reply({content:"Region must be a two-letter country code, such as IE or US.",flags:MessageFlags.Ephemeral});
        return;
      }
      await this.tmdbSelectionAndRespond(interaction, query, category, view, region);
      return;
    }
    if (compareTo) {
      await this.compareAndRespond(interaction, query, compareTo, category, filters);
      return;
    }
    await this.searchAndRespond(interaction, query, category, filters);
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const [, action, categoryValue, maybeId] = interaction.customId.split(":");
    if(action==="creator"){
      await interaction.showModal(creatorSearchModal());
      return true;
    }
    if (action === "search" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.showModal(searchModal(categoryValue as Category));
      return true;
    }
    if (action === "trending" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
      const results = await this.fetchTrending(categoryValue as Category);
      await this.presentResults(interaction, results, `Trending ${categoryLabel(categoryValue as Category)}`);
      return true;
    }
    if (action === "random" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
      const results = await this.fetchRandom(categoryValue as Category);
      await this.presentResults(interaction, results, `Random discovery · ${categoryLabel(categoryValue as Category)}`);
      return true;
    }
    if (action === "recommend" && (categoryValue === "ANIME" || categoryValue === "MANGA") && maybeId) {
      const mediaId = Number(maybeId);
      if (!Number.isSafeInteger(mediaId) || mediaId < 1) {
        await interaction.reply({ content: "That media reference is invalid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
      const results = await this.anilist.recommendations(mediaId, categoryValue as AniListMediaType);
      await this.presentResults(interaction, results.map((item) => anilistRecord(item, categoryValue === "ANIME" ? "anime" : "manga")), "Related AniList recommendations");
      return true;
    }
    if(action==="similar"&&categoryValue==="game"&&maybeId){
      const gameId=Number(maybeId);
      if(!Number.isSafeInteger(gameId)||gameId<1){await interaction.reply({content:"That game reference is invalid.",flags:MessageFlags.Ephemeral});return true;}
      await interaction.reply({content:loadingMessage("Finding similar games…"),flags:MessageFlags.Ephemeral});
      const games=await this.igdb.similarGames(gameId);
      await this.presentResults(interaction,games.map(item=>({provider:"IGDB" as const,category:"game" as const,item})),"Similar games · IGDB relationships");
      return true;
    }
    if (action === "home") {
      await interaction.update(homePanel());
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction | RoleSelectMenuInteraction | ChannelSelectMenuInteraction): Promise<boolean> {
    if (!interaction.isStringSelectMenu()) return false;
    const [scope, action, categoryValue, region] = interaction.customId.split(":");
    if (scope !== "discover") return false;
    if (action === "tmdb-person") {
      const selectedId = interaction.values[0] ?? "";
      const personId = Number(selectedId);
      if (!/^\\d+$/.test(selectedId) || !Number.isSafeInteger(personId) || personId < 1) {
        await interaction.reply({content:"That TMDB person reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const personName = interaction.component.options.find((option) => option.value === selectedId)?.label ?? "Person";
      await interaction.deferUpdate();
      const credits = await this.tmdb.personCredits(personId);
      const description = credits.length
        ? credits.map((credit) => {
          const role = credit.role ? " · "+cleanText(credit.role,100) : "";
          const date = credit.releaseDate ? " · "+credit.releaseDate : "";
          return "["+cleanText(credit.title,180).replace(/[\\[\\]]/g,"")+"]("+credit.sourceUrl+") · "+credit.category.toUpperCase()+date+role;
        }).join("\\n").slice(0,4000)
        : "TMDB did not return combined movie or television credits for this person.";
      const embed = homeEmbed("Credits · "+personName,description).setURL("https://www.themoviedb.org/person/"+personId)
        .setFooter({text:"TMDB · Cast and crew credits deduplicated by work"});
      await interaction.editReply({content:"Person Credits · "+personName,embeds:[embed],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],allowedMentions:{parse:[]}});
      return true;
    }
    if (action === "tmdb-collection") {
      const selectedId = interaction.values[0] ?? "";
      const movieId = Number(selectedId);
      if (!/^\\d+$/.test(selectedId) || !Number.isSafeInteger(movieId) || movieId < 1) {
        await interaction.reply({content:"That TMDB movie reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const movieTitle = interaction.component.options.find((option) => option.value === selectedId)?.label ?? "Selected film";
      await interaction.deferUpdate();
      const collection = await this.tmdb.collectionForMovie(movieId);
      if (!collection) {
        await interaction.editReply({content:"TMDB does not list this film as a member of a collection.",embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]});
        return true;
      }
      const description = collection.items.length
        ? collection.items.map((item) => "["+cleanText(item.title,180).replace(/[\\[\\]]/g,"")+"]("+item.sourceUrl+") · "+(item.releaseDate??"Date unavailable")).join("\\n").slice(0,4000)
        : "TMDB returned no member films for this collection.";
      const embed = homeEmbed("Collection · "+collection.name,description).setURL(collection.sourceUrl)
        .setFooter({text:"TMDB collection membership · Release dates do not establish story chronology"});
      if (collection.image) embed.setThumbnail(collection.image);
      await interaction.editReply({content:"Collection guide · "+movieTitle,embeds:[embed],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],allowedMentions:{parse:[]}});
      return true;
    }
    if (action !== "tmdb-watch" && action !== "tmdb-videos") return false;
    if ((categoryValue !== "movie" && categoryValue !== "tv") || !region || !/^[A-Z]{2}$/.test(region)) {
      await interaction.reply({content:"That TMDB selection is invalid. Reopen /discover and try again.",flags:MessageFlags.Ephemeral});
      return true;
    }
    const selectedId = interaction.values[0] ?? "";
    const mediaId = Number(selectedId);
    if (!/^\d+$/.test(selectedId) || !Number.isSafeInteger(mediaId) || mediaId < 1) {
      await interaction.reply({content:"That TMDB title reference is invalid.",flags:MessageFlags.Ephemeral});
      return true;
    }
    const selectedTitle = interaction.component.options.find((option) => option.value === selectedId)?.label ?? "Selected title";
    await interaction.deferUpdate();
    if (action === "tmdb-watch") {
      const availability = await this.tmdb.watchAvailability(mediaId, categoryValue, region);
      if (!availability) {
        await interaction.editReply({
          content:"TMDB has no watch-provider record for this title in " + region + ". This does not prove that the title is unavailable.",
          embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        });
        return true;
      }
      const embed = homeEmbed(
        ("Where to watch · " + selectedTitle).slice(0,256),
        "Region: " + region + ". Provider data can change; verify current availability with the listed service.",
        availability.groups.map((group) => ({name:group.label,value:group.providers.join(", ").slice(0,1024),inline:false})),
      ).setFooter({text:"TMDB metadata · Watch-provider data powered by JustWatch"});
      if (availability.link) embed.setURL(availability.link);
      if (!availability.groups.length) {
        embed.setDescription("TMDB returned a regional record but no provider categories. This does not prove that the title is unavailable.");
      }
      await interaction.editReply({
        content:"Availability · " + selectedTitle,
        embeds:[embed],
        components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        allowedMentions:{parse:[]},
      });
      return true;
    }
    const videos = await this.tmdb.videos(mediaId, categoryValue);
    const embed = homeEmbed(
      ("Videos · " + selectedTitle).slice(0,256),
      videos.length
        ? videos.map((video) => "[" + cleanText(video.name,160).replace(/[\[\]]/g,"") + "](" + video.url + ") · " + video.type + " · " + video.site + (video.official ? " · Official" : "")).join("\n").slice(0,4000)
        : "TMDB has no supported YouTube or Vimeo video records for this title.",
    ).setFooter({text:"TMDB video metadata · Video type and official flag are shown as returned"});
    await interaction.editReply({
      content:"Trailer and video results · " + selectedTitle,
      embeds:[embed],
      components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
      allowedMentions:{parse:[]},
    });
    return true;
  }

  private async tmdbCollectionSelectionAndRespond(
    interaction: ChatInputCommandInteraction,
    query: string,
  ): Promise<void> {
    await interaction.reply({content:loadingMessage("Searching TMDB…"),flags:MessageFlags.Ephemeral});
    const results = await this.tmdb.search(query,"movie");
    if (!results.length) {
      await interaction.editReply({content:"TMDB returned no matching films.",embeds:[],components:[]});
      return;
    }
    const select = new StringSelectMenuBuilder()
      .setCustomId("discover:tmdb-collection")
      .setPlaceholder("Choose the exact film")
      .addOptions(results.slice(0,25).map((item)=>({
        label:item.title.slice(0,100),
        description:(item.releaseDate??"Release date unavailable")+" · TMDB #"+item.id,
        value:String(item.id),
      })));
    await interaction.editReply({
      content:"Choose the film whose TMDB collection you want to inspect.",
      embeds:[],
      components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
    });
  }

  private async tmdbSelectionAndRespond(
    interaction: ChatInputCommandInteraction,
    query: string,
    category: "movie" | "tv",
    action: "availability" | "videos",
    region: string,
  ): Promise<void> {
    await interaction.reply({content:loadingMessage("Searching TMDB…"),flags:MessageFlags.Ephemeral});
    const results = await this.tmdb.search(query, category);
    if (!results.length) {
      await interaction.editReply({content:"TMDB returned no matching titles.",embeds:[],components:[]});
      return;
    }
    const select = new StringSelectMenuBuilder()
      .setCustomId("discover:" + (action === "availability" ? "tmdb-watch" : "tmdb-videos") + ":" + category + ":" + region)
      .setPlaceholder("Choose the exact TMDB title")
      .addOptions(results.slice(0,25).map((item) => ({
        label:item.title.slice(0,100),
        description:(item.releaseDate ?? "Release date unavailable") + " · TMDB #" + item.id,
        value:String(item.id),
      })));
    await interaction.editReply({
      content:action === "availability"
        ? "Choose the exact title to inspect watch providers in " + region + "."
        : "Choose the exact title to inspect TMDB-listed videos.",
      embeds:[],
      components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
    });
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    const [, action, categoryValue] = interaction.customId.split(":");
    if(action==="creator-search"){
      await this.creatorAndRespond(interaction,interaction.fields.getTextInputValue("query"));
      return true;
    }
    if (action !== "search" || !CATEGORIES.some((item) => item.value === categoryValue)) return false;
    await this.searchAndRespond(interaction, interaction.fields.getTextInputValue("query"), categoryValue as Category);
    return true;
  }

  private async creatorAndRespond(
    interaction:ChatInputCommandInteraction|ModalSubmitInteraction,
    query:string,
    category:Category="anime",
  ):Promise<void>{
    await interaction.reply({content:loadingMessage("Exploring creators…"),flags:MessageFlags.Ephemeral});
    if(category==="book"){
      const books=await this.books.search("inauthor:"+query.trim());
      const embeds=books.slice(0,10).map((book)=>homeEmbed(
        book.title.slice(0,256),
        [
          book.authors.length?"Authors: "+book.authors.join(", "):"Author metadata unavailable",
          book.publisher?"Publisher: "+book.publisher:"",
          book.publishedDate?"Published: "+book.publishedDate:"",
          book.isbn?"ISBN: "+book.isbn:"",
        ].filter(Boolean).join("\n"),
        [{name:"Google Books",value:"[Open edition]("+book.sourceUrl+")",inline:false}],
      ).setFooter({text:"Google Books · Author-attributed editions"}));
      await interaction.editReply({
        content:embeds.length?"Author works · "+query.trim().slice(0,80):"Google Books returned no works attributed to that author.",
        embeds,
        components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        allowedMentions:{parse:[]},
      });
      return;
    }
    if(category==="movie"||category==="tv"){
      const people=await this.tmdb.searchPeople(query);
      if(!people.length){
        await interaction.editReply({content:"TMDB returned no matching credited people.",embeds:[],components:[]});
        return;
      }
      const select=new StringSelectMenuBuilder()
        .setCustomId("discover:tmdb-person")
        .setPlaceholder("Choose the exact credited person")
        .addOptions(people.slice(0,10).map((person)=>({
          label:person.name.slice(0,100),
          description:"TMDB person #"+person.id,
          value:String(person.id),
        })));
      await interaction.editReply({
        content:"Choose the exact person to inspect their combined movie and television credits.",
        embeds:[],
        components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
      });
      return;
    }
    const creators=await this.anilist.searchCreators(query);
    if(!creators.length){await interaction.editReply({content:"AniList returned no matching creators.",embeds:[],components:[]});return;}
    const embeds=creators.slice(0,10).map(creator=>{
      const embed=homeEmbed(creator.name,safeDescription(creator.description,1200),[
        {name:"Occupations",value:creator.occupations.join(", ")||"Unavailable",inline:true},
        {name:"Years active",value:creator.yearsActive.length?creator.yearsActive.join(" – "):"Unavailable",inline:true},
        {name:"Known work",value:creator.media.slice(0,5).map(item=>`[${item.title}](${item.url}) · ${item.role}`).join("\n")||"No linked media returned",inline:false},
      ]).setURL(creator.url).setFooter({text:"AniList · Creator metadata"});
      if(creator.image)embed.setThumbnail(creator.image);
      return embed;
    });
    await interaction.editReply({content:`Creator Explorer · ${query.trim().slice(0,80)}`,embeds,components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],allowedMentions:{parse:[]}});
  }

  private async compareAndRespond(
    interaction: ChatInputCommandInteraction,
    firstTitle: string,
    secondTitle: string,
    category: Category,
    filters: DiscoverFilters = {},
  ): Promise<void> {
    await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
    const [first, second] = await Promise.all([
      this.fetchSearch(firstTitle, category, filters),
      this.fetchSearch(secondTitle, category, filters),
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
    filters: DiscoverFilters = {},
  ): Promise<void> {
    await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
    const results = await this.fetchSearch(query, category, filters);
    await this.presentResults(interaction, results, `Search results · ${categoryLabel(category)}`);
  }

  private async atlasAndRespond(interaction: ChatInputCommandInteraction, query: string, category: Category, filters: DiscoverFilters = {}): Promise<void> {
    await interaction.reply({ content: loadingMessage("Loading media results…"), flags: MessageFlags.Ephemeral });
    const results = await this.fetchSearch(query, category, filters);
    await this.saveProviderEdges(results);
    const first = results[0];
    if (!first) {
      await interaction.editReply({ content: "No provider record was found, so the Atlas has no node to open.", embeds: [] });
      return;
    }
    const title = this.recordTitle(first);
    const mediaCategory = this.recordCategory(first);
    const relationships = await findAtlasRelationships(interaction.guildId, title, mediaCategory, this.recordUrl(first), 20);
    const embed = toEmbed(first).setTitle(`Knowledge Atlas · ${title}`.slice(0,256))
      .setDescription("A source-attributed view of recorded relationships. Provider links are global; community links are visible only inside the server that approved them.");
    if (relationships.length) {
      for (const relation of relationships.slice(0,20)) {
        const label = relation.url ? `[${relation.title.slice(0,180)}](${relation.url})` : relation.title.slice(0,180);
        embed.addFields({name:`${relation.relationType} · ${relation.category}`.slice(0,256),
          value:`${label}\nSource: ${relation.source}`.slice(0,1024),inline:false});
      }
    } else {
      embed.addFields({name:"No recorded connections yet",value:"This provider has not supplied related-work edges for this title, and this server has not approved any community links yet.",inline:false});
    }
    embed.setFooter({text:"Knowledge Atlas · Provider provenance and guild-scoped community links"});
    const files: AttachmentBuilder[] = [];
    if (relationships.length) {
      try {
        const image = await renderAtlasSnapshot(title, mediaCategory, relationships);
        embed.setImage("attachment://knowledge-atlas.png");
        files.push(new AttachmentBuilder(image, { name: "knowledge-atlas.png" }));
      } catch (error) {
        logger.warn("Knowledge Atlas graph snapshot could not be rendered", {
          reason: error instanceof Error ? error.message : "Unknown error",
        });
      }
    }
    const dashboardUrl = new URL(this.config.customRolesPublicUrl);
    dashboardUrl.searchParams.set("atlas_title", title);
    dashboardUrl.searchParams.set("atlas_category", mediaCategory.toUpperCase());
    dashboardUrl.searchParams.set("atlas_guild_id", interaction.guildId ?? "");
    const mediaUrl = this.recordUrl(first);
    if (mediaUrl) dashboardUrl.searchParams.set("atlas_url", mediaUrl);
    await interaction.editReply({
      embeds:[embed],
      files,
      components:[
        navigationButtons("discover",[{id:"home",label:"Back to discovery"}]),
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder()
            .setLabel("Open dashboard Atlas")
            .setStyle(ButtonStyle.Link)
            .setURL(dashboardUrl.toString()),
        ),
      ],
      allowedMentions:{parse:[]},
    });
  }

  private recordTitle(record: SearchRecord): string {
    if (record.provider === "AniList") return record.item.title.english ?? record.item.title.romaji ?? record.item.title.native ?? "Untitled";
    return record.item.title;
  }

  private recordCategory(record: SearchRecord): string {
    return record.category;
  }

  private recordUrl(record: SearchRecord): string {
    if(record.provider==="AniList")return record.item.siteUrl;
    if(record.provider==="Steam")return `https://store.steampowered.com/app/${record.item.appId}`;
    return record.item.sourceUrl;
  }

  private async saveProviderEdges(results: SearchRecord[]): Promise<void> {
    const writes = results.flatMap((record) => record.provider === "AniList" ? [
      recordProviderRelationships({
        sourceTitle:this.recordTitle(record),sourceCategory:record.category,sourceUrl:record.item.siteUrl,
        sourceLabel:"AniList provider relationships",
        relations:record.item.relations.map((relation) => ({
          title:relation.title,category:relation.category,url:relation.url,relationshipType:relation.relation,
        })),
      }),
    ] : []);
    await Promise.allSettled(writes);
  }

  private async fetchSearch(query: string, category: Category, filters: DiscoverFilters = {}): Promise<SearchRecord[]> {
    if (category === "all") {
      const providers = await Promise.allSettled([
        this.anilist.search(query, "ANIME").then((items) => items.map((item) => anilistRecord(item, "anime"))),
        this.anilist.search(query, "MANGA").then((items) => items.map((item) => anilistRecord(item, "manga"))),
        this.anilist.search(query, "MANGA", true).then((items) => items.map((item) => anilistRecord(item, "light_novel"))),
        this.books.search(query).then((items) => items.map((item) => ({ provider: "Google Books" as const, category: "book" as const, item }))),
        this.tmdb.search(query, "movie").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "movie" as const, item }))),
        this.tmdb.search(query, "tv").then((items) => items.map((item) => ({ provider: "TMDB" as const, category: "tv" as const, item }))),
        this.igdb.search(query).then((items) => items.map((item) => ({ provider: "IGDB" as const, category: "game" as const, item }))),
        this.steam.searchStoreGames(query).then((items)=>items.map((item)=>({provider:"Steam" as const,category:"game" as const,item}))),
      ]);
      return providers.flatMap((provider) => provider.status === "fulfilled" ? provider.value : []);
    }
    switch (category) {
      case "anime": return (await this.anilist.search(query, "ANIME", false, filters)).map((item) => anilistRecord(item, "anime"));
      case "manga": return (await this.anilist.search(query, "MANGA", false, filters)).map((item) => anilistRecord(item, "manga"));
      case "light_novel": return (await this.anilist.search(query, "MANGA", true, filters)).map((item) => anilistRecord(item, "light_novel"));
      case "book": return (await this.books.search(query)).map((item) => ({ provider: "Google Books", category: "book", item }));
      case "movie": return (await this.tmdb.search(query, "movie")).map((item) => ({ provider: "TMDB", category: "movie", item }));
      case "tv": return (await this.tmdb.search(query, "tv")).map((item) => ({ provider: "TMDB", category: "tv", item }));
      case "game": {
        const [igdb,steam]=await Promise.allSettled([this.igdb.search(query),this.steam.searchStoreGames(query)]);
        return [
          ...(igdb.status==="fulfilled"?igdb.value.map((item)=>({provider:"IGDB" as const,category:"game" as const,item})):[]),
          ...(steam.status==="fulfilled"?steam.value.map((item)=>({provider:"Steam" as const,category:"game" as const,item})):[]),
        ];
      }
    }
  }

  private async fetchRandom(category: Category): Promise<SearchRecord[]> {
    const categories: Exclude<Category, "all">[] = category === "all"
      ? ["anime", "manga", "light_novel", "book", "movie", "tv", "game"]
      : [category];
    const load = async (item: Exclude<Category, "all">): Promise<SearchRecord[]> => {
      switch (item) {
        case "anime": return (await this.anilist.random("ANIME")).map((media) => anilistRecord(media, "anime"));
        case "manga": return (await this.anilist.random("MANGA")).map((media) => anilistRecord(media, "manga"));
        case "light_novel": return (await this.anilist.random("MANGA", true)).map((media) => anilistRecord(media, "light_novel"));
        case "book": return randomOne(await this.books.search("popular fiction")).map((media) => ({ provider: "Google Books", category: "book", item: media }));
        case "movie": return randomOne(await this.tmdb.trending("movie")).map((media) => ({ provider: "TMDB", category: "movie", item: media }));
        case "tv": return randomOne(await this.tmdb.trending("tv")).map((media) => ({ provider: "TMDB", category: "tv", item: media }));
        case "game": {
          const [igdb,steam]=await Promise.allSettled([this.igdb.search("popular"),this.steam.searchStoreGames("top sellers")]);
          return [
            ...(igdb.status==="fulfilled"?randomOne(igdb.value).map((item)=>({provider:"IGDB" as const,category:"game" as const,item})):[]),
            ...(steam.status==="fulfilled"?randomOne(steam.value).map((item)=>({provider:"Steam" as const,category:"game" as const,item})):[]),
          ];
        }
      }
    };
    const batches = await Promise.allSettled(categories.map(load));
    return batches.flatMap((batch) => {
      if (batch.status !== "fulfilled" || !batch.value.length) return [];
      return [batch.value[secureRandBelow(batch.value.length)]!];
    });
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
        this.steam.searchStoreGames("top sellers").then((items)=>items.map((item)=>({provider:"Steam" as const,category:"game" as const,item}))),
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
      case "game": {
        const [igdb,steam]=await Promise.allSettled([this.igdb.search("popular"),this.steam.searchStoreGames("top sellers")]);
        return [
          ...(igdb.status==="fulfilled"?igdb.value.map((item)=>({provider:"IGDB" as const,category:"game" as const,item})):[]),
          ...(steam.status==="fulfilled"?steam.value.map((item)=>({provider:"Steam" as const,category:"game" as const,item})):[]),
        ];
      }
    }
  }

  private async presentResults(
    interaction: ButtonInteraction | ChatInputCommandInteraction | ModalSubmitInteraction,
    results: SearchRecord[],
    title: string,
  ): Promise<void> {
    await this.saveProviderEdges(results);
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

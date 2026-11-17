import { secureRandBelow } from "../../helpers/security/crypto-random.js";
import {
  ActionRowBuilder,
  AttachmentBuilder,
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
  type RoleSelectMenuInteraction,
  type ChannelSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { AniListClient, type AniListAiring, type AniListAiringFilters, type AniListMedia, type AniListMediaType, type AniListSearchFilters, type AniListCreator } from "../../helpers/integration/anilist.js";
import {SteamClient,type SteamStoreGame} from "../../helpers/integration/steam.js";
import { GoogleBooksClient, type GoogleBook } from "../../helpers/integration/google-books.js";
import { CrossrefClient } from "../../helpers/integration/crossref.js";
import { OpenLibraryClient } from "../../helpers/integration/open-library.js";
import { RoyalRoadClient } from "../../helpers/integration/royal-road.js";
import { WebNovelDiscoveryClient, type WebNovelMedia } from "../../helpers/integration/webnovel-discovery.js";
import { IgdbClient, type IgdbGame } from "../../helpers/integration/igdb.js";
import { homeEmbed, navigationButtons } from "../../helpers/runtime/discord.js";
import { TmdbClient, type TmdbMedia, type TmdbTvSeason } from "../../helpers/integration/tmdb.js";
import { getGuildMediaRegion } from "../../helpers/media/media-region.js";
import { cleanText, safeDisplay } from "../../helpers/security/security.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import {
  filterAtlasGraph,
  filterAtlasRelations,
  findAtlasCommunityLinks,
  findAtlasGraph,
  findAtlasPath,
  findAtlasRelationships,
  normalizeAtlasTitle,
  type AtlasGraphPath,
  type AtlasGraphResult,
  recordAtlasRelationship,
  recordProviderRelationships,
} from "../../helpers/integration/atlas.js";
import { aniListReleaseOrder, tmdbCollectionReleaseOrder } from "../../helpers/media/franchise-order.js";
import {
  createMediaLinkSuggestion,
  getPendingMediaLinkSuggestion,
  listPendingMediaLinkSuggestions,
  MEDIA_LINK_RELATIONSHIPS,
  reviewMediaLinkSuggestion,
} from "../../helpers/media/media-link-suggestions.js";
import { renderAtlasGraphSnapshot, renderAtlasGraphSvgSnapshot } from "../../helpers/media/atlas-renderer.js";
import { logger } from "../../helpers/runtime/logger.js";
import { emoji, loadingMessage } from "../../helpers/emoji.js";
import { parseGridSourceUrls, parseGridTitles, renderMediaGrid, type MediaGridSource } from "../../helpers/media/media-grid.js";
import { parseMediaComparisonEntries, type MediaComparisonCategory } from "../../helpers/media/media-comparison.js";
import { formatMetadataSourceReference } from "../../helpers/media/media-provenance.js";
import { auditMetadataSource, type MetadataSourceAuditInput } from "../../helpers/media/metadata-source-audit.js";
import { upcomingProviderReleases } from "../../helpers/community/community-sessions.js";
import { rankCrossMediaCandidates, recommendationGenreLabels, type CrossMediaCandidate } from "../../helpers/media/cross-media-recommendations.js";



async function atlasExportFiles(
  title: string,
  category: string,
  graph: AtlasGraphResult,
  fileBaseName: string,
  path: AtlasGraphPath | null = null,
): Promise<{ files: AttachmentBuilder[]; image: string }> {
  const [png, svg] = await Promise.all([
    renderAtlasGraphSnapshot(title, category, graph, path),
    renderAtlasGraphSvgSnapshot(title, category, graph, path),
  ]);
  const root = graph.nodes.find(node => node.id === graph.rootId) ?? null;
  const payload = Buffer.from(JSON.stringify({
    root, nodes: graph.nodes, edges: graph.edges,
    truncated: graph.truncated, highlightedPath: path?.edges ?? [],
    generatedAt: new Date().toISOString(),
  }, null, 2));
  return {
    files: [
      new AttachmentBuilder(png, { name: fileBaseName + ".png" }),
      new AttachmentBuilder(svg, { name: fileBaseName + ".svg" }),
      new AttachmentBuilder(payload, { name: fileBaseName + ".json" }),
    ],
    image: "attachment://" + fileBaseName + ".png",
  };
}

type Category = "all" | "anime" | "manga" | "light_novel" | "book" | "webnovel" | "movie" | "tv" | "game";
type DiscoverFilters = AniListSearchFilters;
type SearchRecord =
  | { provider: "AniList"; category: "anime" | "manga" | "light_novel"; item: AniListMedia }
  | { provider: "Google Books"; category: "book"; item: GoogleBook }
  | { provider: "Royal Road"; category: "webnovel"; item: Awaited<ReturnType<RoyalRoadClient["getFiction"]>> }
| { provider: "NovelFire"; category: "webnovel"; item: WebNovelMedia }
| { provider: "Novel Archive"; category: "webnovel"; item: WebNovelMedia }
| { provider: "Wuxia Click"; category: "webnovel"; item: WebNovelMedia }
| { provider: "Novel Updates"; category: "webnovel"; item: WebNovelMedia }
| { provider: "ScribbleHub"; category: "webnovel"; item: WebNovelMedia }
| { provider: "Noveli.to"; category: "webnovel"; item: WebNovelMedia }
  | { provider: "TMDB"; category: "movie" | "tv"; item: TmdbMedia }
  | { provider: "IGDB"; category: "game"; item: IgdbGame }
  | { provider: "Steam"; category: "game"; item: SteamStoreGame };

const CATEGORIES: Array<{ label: string; value: Category; emoji: string }> = [
  { label: "All media", value: "all", emoji: emoji.globe },
  { label: "Anime", value: "anime", emoji: emoji.anime },
  { label: "Manga", value: "manga", emoji: emoji.mangaDiscovery },
  { label: "Light novels", value: "light_novel", emoji: emoji.lightNovelDiscovery },
  { label: "Books", value: "book", emoji: emoji.book },
  { label: "Webnovels", value: "webnovel", emoji: emoji.book },
  { label: "Films", value: "movie", emoji: emoji.movie },
  { label: "Television", value: "tv", emoji: emoji.television },
  { label: "Games", value: "game", emoji: emoji.game },
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

function webNovelRecord(item: WebNovelMedia): SearchRecord {
switch (item.provider) {
case "NovelFire": return { provider: "NovelFire", category: "webnovel", item };
case "Novel Archive": return { provider: "Novel Archive", category: "webnovel", item };
case "Wuxia Click": return { provider: "Wuxia Click", category: "webnovel", item };
case "Novel Updates": return { provider: "Novel Updates", category: "webnovel", item };
case "ScribbleHub": return { provider: "ScribbleHub", category: "webnovel", item };
case "Noveli.to": return { provider: "Noveli.to", category: "webnovel", item };
}
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
    embed.addFields({ name: "Source record", value: formatMetadataSourceReference("AniList", item.id, item.siteUrl), inline: false });
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
        { name: "Subtitle", value: item.subtitle ?? "Unavailable", inline: false },
        { name: "Authors", value: item.authors.join(", ") || "Unavailable", inline: true },
        { name: "Publisher", value: item.publisher ?? "Unavailable", inline: true },
        { name: "Published", value: item.publishedDate ?? "Unavailable", inline: true },
        { name: "Language / format", value: [item.language?.toUpperCase(), item.printType].filter(Boolean).join(" · ") || "Unavailable", inline: true },
        { name: "Pages", value: String(item.pageCount ?? "Unavailable"), inline: true },
        { name: "ISBN-13", value: item.isbn13 ?? "Unavailable", inline: true },
        { name: "ISBN-10", value: item.isbn10 ?? "Unavailable", inline: true },
        { name: "Series", value: [item.seriesBookTitle, item.seriesDisplayNumber, item.seriesOrder ? "Order " + item.seriesOrder : null].filter(Boolean).join(" · ") || "Unavailable", inline: true },
        { name: "Categories", value: item.categories.join(", ") || item.mainCategory || "Unavailable", inline: false },
        { name: "Catalogue region", value: item.catalogueRegion ?? "Not reported", inline: true },
        { name: "Reading access", value: item.viewability ?? "Not reported", inline: true },
        { name: "Digital formats", value: [
          item.pdfAvailable === null ? "PDF not reported" : item.pdfAvailable ? "PDF available" : "PDF unavailable",
          item.epubAvailable === null ? "EPUB not reported" : item.epubAvailable ? "EPUB available" : "EPUB unavailable",
        ].join(" · "), inline: false },
        { name: "Store status", value: item.saleability ?? "Not reported", inline: true },
        { name: "eBook", value: item.isEbook === null ? "Not reported" : item.isEbook ? "Yes" : "No", inline: true },
        { name: "Public domain", value: item.publicDomain === null ? "Not reported" : item.publicDomain ? "Yes" : "No", inline: true },
        ...(item.buyUrl ? [{ name: "Store record", value: "[Open provider store record](" + item.buyUrl + ")", inline: false }] : []),
      )
      .setFooter({ text: "Google Books · Source metadata" });
    embed.addFields({ name: "Source record", value: formatMetadataSourceReference("Google Books", item.id, item.sourceUrl), inline: false });
    if (item.image) embed.setThumbnail(item.image);
    if (item.previewUrl) embed.addFields({ name: "Preview", value: "[Open preview](" + item.previewUrl + ")", inline: true });
    if (item.infoUrl && item.infoUrl !== item.sourceUrl) embed.addFields({ name: "Edition details", value: "[Open Google Books record](" + item.infoUrl + ")", inline: true });
    return embed;
  }

  if (record.provider === "Royal Road") {
    const item = record.item;
    const chapters = item.chapters.slice(0, 3).map((chapter) =>
      "[" + safeDisplay(chapter.title, 160) + "](" + chapter.url + ")"
        + (chapter.publishedAt ? " · <t:" + Math.floor(new Date(chapter.publishedAt).getTime() / 1000) + ":R>" : ""),
    ).join("\n");
    const embed = new EmbedBuilder().setColor(0x2d6b52)
      .setTitle(item.title.slice(0, 256))
      .setURL(item.sourceUrl)
      .setDescription("Public story metadata from the Royal Road RSS feed. Chapter text is not retrieved.")
      .addFields(
        { name: "Provider", value: "Royal Road RSS", inline: true },
        { name: "Fiction ID", value: String(item.id), inline: true },
        { name: "Author", value: item.author ?? "Not reported in feed", inline: true },
        { name: "Latest update", value: item.latestUpdate ? "<t:" + Math.floor(new Date(item.latestUpdate).getTime() / 1000) + ":F>" : "Not reported", inline: false },
        { name: "Recent chapter links", value: (chapters || "No chapter entries were included in this feed.").slice(0, 1024), inline: false },
      )
      .setFooter({ text: "Royal Road · Public story-specific RSS metadata" });
    embed.addFields({ name: "Source record", value: formatMetadataSourceReference("Royal Road", item.id, item.sourceUrl), inline: false });
    return embed;
  }

if (record.provider === "NovelFire" || record.provider === "Novel Archive" || record.provider === "Wuxia Click" || record.provider === "Novel Updates" || record.provider === "ScribbleHub" || record.provider === "Noveli.to") {
const item = record.item;
const embed = new EmbedBuilder()
.setColor(0x5865f2)
.setTitle(item.title.slice(0, 256))
.setURL(item.sourceUrl)
.setDescription(safeDescription(item.description))
.addFields(
{ name: "Provider", value: item.provider, inline: true },
{ name: "Author", value: item.author ?? "Not reported", inline: true },
{ name: "Status", value: item.status ?? "Not reported", inline: true },
{ name: "Chapters", value: item.chapterCount === null ? "Not reported" : item.chapterCount.toLocaleString(), inline: true },
{ name: "Rating", value: item.rating === null ? "Not reported" : String(item.rating), inline: true },
{ name: "Genres", value: item.genres.slice(0, 8).join(" · ") || "Not reported", inline: false },
...(item.latestChapters.length ? [{ name: "Recent chapter titles", value: item.latestChapters.slice(0, 5).join("\n").slice(0, 1_000), inline: false }] : []),
...(item.latestUpdate ? [{ name: "Last update", value: item.latestUpdate, inline: true }] : []),
)
.setFooter({ text: item.provider + " · Web-novel metadata" });
embed.addFields({ name: "Source record", value: formatMetadataSourceReference(item.provider, item.sourceUrl, item.sourceUrl), inline: false });
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
        { name: item.category === "movie" ? "Runtime" : "Episode runtimes", value: item.category === "movie"
          ? (item.runtime ? item.runtime + " minutes" : "Not reported")
          : (item.episodeRuntimes.length ? item.episodeRuntimes.join(" / ") + " minutes" : "Not reported"), inline: true },
        ...(item.certifications.length ? [{
          name: "Regional release certifications",
          value: item.certifications.slice(0, 8).map(entry =>
            entry.region + ": " + entry.certification + (entry.releaseDate ? " · " + entry.releaseDate.slice(0, 10) : ""),
          ).join("\n").slice(0, 1024),
          inline: false,
        }] : []),
        ...(item.contentRatings.length ? [{
          name: "Regional TV content ratings",
          value: item.contentRatings.slice(0, 8).map(entry => entry.region + ": " + entry.rating).join("\n").slice(0, 1024),
          inline: false,
        }] : []),
      )
      .setFooter({ text: "TMDB · Source metadata · Country-specific ratings are shown only when supplied" });
    embed.addFields({ name: "Source record", value: formatMetadataSourceReference("TMDB", item.id, item.sourceUrl), inline: false });
    if (item.image) embed.setThumbnail(item.image);
    return embed;
  }

  if (record.provider === "Steam") {
    const item=record.item;
    const price=item.isFree?"Free to Play":item.price?`${item.price.final} · ${item.priceRegion} store`: "Price unavailable";
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
      ).setFooter({text:"Steam Store · "+item.priceRegion+" store metadata"});
    embed.addFields({name:"Source record",value:formatMetadataSourceReference("Steam Store",item.appId,"https://store.steampowered.com/app/"+item.appId),inline:false});
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
      { name: "User rating", value: item.rating === null ? "Not rated" : item.rating.toFixed(1) + "/100 · " + item.ratingCount + " rating(s)", inline: true },
      { name: "Critic rating", value: item.aggregatedRating === null ? "Not rated" : item.aggregatedRating.toFixed(1) + "/100 · " + item.aggregatedRatingCount + " review(s)", inline: true },
    )
    .setFooter({ text: "IGDB · Source metadata · Ratings retain IGDB's 0–100 scale" });
  embed.addFields({ name: "Source record", value: formatMetadataSourceReference("IGDB", item.id, item.sourceUrl), inline: false });
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
  if (record.provider === "TMDB") {
    return [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId(`discover:tmdb-details:${record.category}:${record.item.id}`)
        .setLabel("Full runtime and rating details").setStyle(ButtonStyle.Secondary),
    )];
  }
  if(record.provider==="IGDB"&&record.category==="game"){
    return [new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId(`discover:similar:game:${record.item.id}`).setLabel("Similar games").setStyle(ButtonStyle.Secondary),
    )];
  }
  return [];
}

function compareSearchModal():ModalBuilder{
 return new ModalBuilder().setCustomId("discover:compare-search").setTitle("Compare media titles").addComponents(
  new ActionRowBuilder<TextInputBuilder>().addComponents(
   new TextInputBuilder().setCustomId("entries").setLabel("2–4 entries · category | title")
    .setPlaceholder("anime | Your Name\nbook | Dune\ngame | Hades").setStyle(TextInputStyle.Paragraph)
    .setMinLength(10).setMaxLength(800).setRequired(true),
  ),
 );
}
function airingSearchModal():ModalBuilder{
 return new ModalBuilder().setCustomId("discover:airing-search").setTitle("Upcoming anime episodes").addComponents(
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("title").setLabel("Anime title (optional)").setPlaceholder("Leave blank for all anime").setStyle(TextInputStyle.Short).setMaxLength(100).setRequired(false)),
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("season").setLabel("Season (optional)").setPlaceholder("Winter, Spring, Summer or Fall").setStyle(TextInputStyle.Short).setMaxLength(10).setRequired(false)),
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("year").setLabel("Season year (optional)").setPlaceholder("2026").setStyle(TextInputStyle.Short).setMaxLength(4).setRequired(false)),
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("day").setLabel("UTC weekday (optional)").setPlaceholder("Monday through Sunday").setStyle(TextInputStyle.Short).setMaxLength(9).setRequired(false)),
  new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("days").setLabel("Upcoming window in days").setPlaceholder("7 (maximum 14)").setStyle(TextInputStyle.Short).setMaxLength(2).setRequired(false)),
 );
}
function creatorCategorySelect(): ActionRowBuilder<StringSelectMenuBuilder> {
  return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId("discover:creator-category")
      .setPlaceholder("Choose a media family")
      .addOptions(
        { label: "Anime staff", value: "anime" },
        { label: "Manga creators", value: "manga" },
        { label: "Light novel creators", value: "light_novel" },
        { label: "Book authors", value: "book" },
        { label: "Film cast and crew", value: "movie" },
        { label: "TV cast and crew", value: "tv" },
        { label: "Game developers and publishers", value: "game" },
      ),
  );
}

function creatorSearchModal(category: Category): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("discover:creator-search:" + category)
    .setTitle("Explore " + categoryLabel(category) + " creators")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("query").setLabel("Creator or company name")
          .setPlaceholder("Enter an exact or partial name").setStyle(TextInputStyle.Short)
          .setMinLength(2).setMaxLength(80).setRequired(true),
      ),
    );
}

function searchModal(category: Category): ModalBuilder {
  const isWebnovel = category === "webnovel";
  return new ModalBuilder()
    .setCustomId(`discover:search:${category}`)
    .setTitle(`Search ${categoryLabel(category)}`)
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder()
          .setCustomId("query")
          .setLabel(isWebnovel ? "Webnovel title or Royal Road ID / URL" : "Title or search phrase")
          .setPlaceholder(isWebnovel ? "Search a webnovel title or enter a Royal Road fiction ID" : "Enter a title")
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
      { name: "Webnovels", value: "NovelFire · Novel Archive · Wuxia Click · Novel Updates · ScribbleHub · Royal Road", inline: true },
    ],
  );
  const rows: ActionRowBuilder<ButtonBuilder>[] = [];
  for (let offset = 0; offset < CATEGORIES.length; offset += 5) {
    const row = new ActionRowBuilder<ButtonBuilder>();
    for (const category of CATEGORIES.slice(offset, offset + 5)) {
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
    new ButtonBuilder().setCustomId("discover:compare").setLabel("Compare media").setStyle(ButtonStyle.Secondary),
  );
  const schedules = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("discover:airing").setLabel("Upcoming anime episodes").setStyle(ButtonStyle.Secondary),
  );
  rows.push(explore, random, schedules);
  return { embeds: [embed], components: rows };
}

export class DiscoverCommand implements FeatureCommand {
  private readonly airingSessions = new Map<string, {
    ownerId: string;
    filters: AniListAiringFilters;
    entries: AniListAiring[];
    page: number;
    timeout: NodeJS.Timeout;
  }>();
  private readonly comparisonSessions = new Map<string, {
    ownerId:string;
    sides:Array<{category:MediaComparisonCategory;title:string;results:SearchRecord[];selected:number}>;
    timeout:NodeJS.Timeout;
  }>();
  readonly data = new SlashCommandBuilder()
    .setName("discover")
    .setDescription("Explore media across supported metadata providers")
    .addStringOption((option) => option.setName("query").setDescription("Search for a title").setMinLength(2).setMaxLength(100))
    .addStringOption((option) => option.setName("grid_titles").setDescription("Nine titles or exact AniList/IGDB URLs, one per line").setMaxLength(2_000))
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
      { name: "Random media", value: "random" },
      { name: "Trending media", value: "trending" },
      { name: "Franchise Explorer", value: "franchise" },
      { name: "Adaptation Explorer", value: "adaptations" },
      { name: "Metadata Source Explorer", value: "metadata" },
      { name: "Media Release Explorer", value: "releases" },
      { name: "Exact book edition lookup", value: "edition" },
      { name: "3×3 media cover grid", value: "grid" },
      { name: "Cross-media similarity", value: "similar" },
      { name: "Knowledge Atlas", value: "atlas" },
      { name: "Creator Explorer", value: "creators" },
      { name: "Availability Explorer", value: "availability" },
      { name: "Trailers and videos", value: "videos" },
      { name: "Movie collection guide", value: "collection" },
      { name: "TV season and episode guide", value: "tv-guide" },
      { name: "Suggest a community relationship", value: "suggest-link" },
      { name: "Review server relationship suggestions", value: "review-links" },
    ))
    .addStringOption((option) => option.setName("region").setDescription("Two-letter availability region, for example IE or US").setMinLength(2).setMaxLength(2))
    .addStringOption((option) => option.setName("source_title").setDescription("Relationship source title").setMaxLength(200))
    .addStringOption((option) => option.setName("source_category").setDescription("Source media category").addChoices(
      ...[["Anime","ANIME"],["Manga / manhwa / manhua","MANGA"],["Light novel","LIGHT_NOVEL"],["Book","BOOK"],["Webnovel","WEBNOVEL"],["Movie","MOVIE"],["TV series","TV"],["Video game","GAME"]].map(([name,value])=>({name:name!,value:value!})),
    ))
    .addStringOption((option) => option.setName("source_url").setDescription("HTTPS metadata page for the source title").setMaxLength(1_000))
    .addStringOption((option) => option.setName("relationship").setDescription("Proposed relationship type").addChoices(
      ...MEDIA_LINK_RELATIONSHIPS.map((value)=>({name:value.replace(/\\b\\w/g,(letter)=>letter.toUpperCase()),value})),
    ))
    .addStringOption((option) => option.setName("target_title").setDescription("Related media title").setMaxLength(200))
    .addStringOption((option) => option.setName("target_category").setDescription("Related media category").addChoices(
      ...[["Anime","ANIME"],["Manga / manhwa / manhua","MANGA"],["Light novel","LIGHT_NOVEL"],["Book","BOOK"],["Webnovel","WEBNOVEL"],["Movie","MOVIE"],["TV series","TV"],["Video game","GAME"]].map(([name,value])=>({name:name!,value:value!})),
    ))
    .addStringOption((option) => option.setName("target_url").setDescription("HTTPS metadata page for the related title").setMaxLength(1_000))
    .addStringOption((option) => option.setName("evidence").setDescription("Evidence for the proposed relationship (minimum 15 characters)").setMaxLength(1_500))
    .addIntegerOption((option) => option.setName("suggestion_id").setDescription("Suggestion ID for inspection or review").setMinValue(1))
    .addStringOption((option) => option.setName("decision").setDescription("Review decision").addChoices(
      {name:"List pending",value:"list"},{name:"Inspect",value:"inspect"},{name:"Approve",value:"approved"},{name:"Reject",value:"rejected"},
    ))
    .addStringOption((option) => option.setName("reason").setDescription("Optional moderator review note").setMaxLength(1_000));

  private readonly config: BotConfig;
  private readonly anilist: AniListClient;
  private readonly books: GoogleBooksClient;
  private readonly tmdb: TmdbClient;
  private readonly igdb: IgdbClient;
  private readonly steam:SteamClient;
  private readonly crossref: CrossrefClient;
  private readonly openLibrary: OpenLibraryClient;
  private readonly royalRoad: RoyalRoadClient;
private readonly webNovels: WebNovelDiscoveryClient;

  constructor(config: BotConfig) {
    this.config = config;
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.books = new GoogleBooksClient(config.googleBooksApiKey);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
    this.igdb = new IgdbClient(config.igdbClientId, config.igdbClientSecret);
    this.steam=new SteamClient(config.steamApiKey);
    this.crossref = new CrossrefClient();
    this.openLibrary = new OpenLibraryClient();
    this.royalRoad = new RoyalRoadClient();
this.webNovels = new WebNovelDiscoveryClient();
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const query = interaction.options.getString("query")?.trim();
    const compareTo = interaction.options.getString("compare_to")?.trim();
    const view = interaction.options.getString("view") ?? "search";
    const category = (interaction.options.getString("category") ?? (view === "edition" ? "book" : "anime")) as Category;
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
    if (category === "webnovel" && view !== "search") {
      await interaction.reply({
        content:"Webnovel title search uses the connected metadata sources. You can also enter a Royal Road fiction ID or official story URL.",
        flags:MessageFlags.Ephemeral,
      });
      return;
    }
    if (view === "metadata") {
      await this.metadataSourcesAndRespond(interaction, query ?? "");
      return;
    }
    if (view === "releases") {
      await this.releaseExplorerAndRespond(interaction, category);
      return;
    }
    if (view === "random" || view === "trending") {
      await interaction.reply({ content: loadingMessage(view === "random" ? "Finding a random media pick…" : "Loading trending media…"), flags: MessageFlags.Ephemeral });
      try {
        const results = view === "random" ? await this.fetchRandom(category) : await this.fetchTrending(category);
        await this.presentResults(interaction, results, view === "random" ? "Random media picks" : "Trending media");
      } catch (error) {
        await interaction.editReply({ content: error instanceof Error ? error.message : "The discovery provider could not load this view.", embeds: [], components: [] });
      }
      return;
    }
    if (view === "suggest-link") {
      await this.suggestRelationshipAndRespond(interaction);
      return;
    }
    if (view === "review-links") {
      await this.reviewRelationshipAndRespond(interaction);
      return;
    }
    if (view === "grid") {
      if (!["anime", "manga", "light_novel", "game"].includes(category)) {
        await interaction.reply({ content: "The 3×3 grid supports anime, manga, light novels and IGDB games.", flags: MessageFlags.Ephemeral });
        return;
      }
      const rawTitles = interaction.options.getString("grid_titles") ?? "";
      let titles: string[];
      let sources: MediaGridSource[] | null;
      try {
        titles = parseGridTitles(rawTitles);
        sources = parseGridSourceUrls(titles);
      } catch (error) {
        await interaction.reply({ content: error instanceof Error ? error.message : "Enter nine titles or provider URLs, one per line.", flags: MessageFlags.Ephemeral });
        return;
      }
      await this.mediaGridAndRespond(interaction, titles, category as "anime" | "manga" | "light_novel" | "game", sources);
      return;
    }
    if (!query) {
      const home = homePanel();
      await interaction.reply({ ...home, flags: MessageFlags.Ephemeral });
      return;
    }
    if (view === "edition") {
      if (category !== "book") {
        await interaction.reply({ content: "Exact edition lookup requires the Books category.", flags: MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({
        content: loadingMessage("Looking up the exact book edition…"),
        flags: MessageFlags.Ephemeral,
      });
      try {
        const editions = await this.books.findEdition(query);
        const enriched = await Promise.all(editions.slice(0, 5).map(async (edition) => {
          const isbn = edition.isbn13 ?? edition.isbn10;
          if (!isbn) return { edition, crossref: [], family: null };
          const [credits, family] = await Promise.allSettled([
            this.crossref.findByIsbn(isbn),
            this.openLibrary.findEditionFamily(isbn),
          ]);
          return {
            edition,
            crossref: credits.status === "fulfilled" ? credits.value : [],
            family: family.status === "fulfilled" ? family.value : null,
          };
        }));
        const embeds = enriched.map(({ edition, crossref, family }) => {
          const embed = toEmbed({ provider: "Google Books", category: "book", item: edition });
          const credits = crossref.flatMap(match => [
            ...match.editors.map(person => "Editor: " + person.name),
            ...match.translators.map(person => "Translator: " + person.name),
          ]);
          embed.addFields({
            name: "Crossref · exact ISBN contributor credits",
            value: (credits.length
              ? credits.slice(0, 12).join("\n").slice(0, 850) + "\nSource: " + crossref.map(item => item.sourceUrl).slice(0, 2).join(" · ")
              : "No Crossref editor or translator record explicitly matched this ISBN.").slice(0, 1024),
            inline: false,
          });
          embed.addFields({
            name: "Open Library · work and edition identity",
            value: (family
              ? family.editions.slice(0, 8).map(item =>
                  "[" + safeDisplay(item.title, 100) + "](" + item.sourceUrl + ")"
                    + (item.editionName ? " · " + safeDisplay(item.editionName, 60) : "")
                    + (item.publishDate ? " · " + safeDisplay(item.publishDate, 40) : ""),
                ).join("\n").slice(0, 850)
                  + "\nWork: " + family.workUrl + " · " + family.editionCount + " edition(s)"
                  + (family.truncated ? " · first 50 shown" : "")
              : "No unambiguous Open Library work ID was returned for this ISBN. No title-based edition merge was attempted.").slice(0, 1024),
            inline: false,
          });
          return embed;
        });
        await interaction.editReply({
          content: editions.length
            ? "Exact Google Books edition match · " + query.slice(0, 80) + " · Crossref and Open Library enrichment"
            : "Google Books returned no exact ISBN or volume-ID match. Try the other identifier printed on the edition.",
          embeds,
          components: [navigationButtons("discover", [{ id: "home", label: "Back to discovery" }])],
          allowedMentions: { parse: [] },
        });
      } catch (error) {
        await interaction.editReply({
          content: error instanceof Error ? error.message : "The exact book edition could not be retrieved.",
          embeds: [],
          components: [navigationButtons("discover", [{ id: "home", label: "Back to discovery" }])],
          allowedMentions: { parse: [] },
        });
      }
      return;
    }
    if(view==="creators"){
      await this.creatorAndRespond(interaction,query,category);
      return;
    }
    if (view === "franchise" || view === "adaptations") {
      await this.atlasAndRespond(
        interaction,
        query,
        category,
        filters,
        interaction.options.getString("target_title"),
        interaction.options.getString("target_category"),
        interaction.options.getString("target_url"),
        view === "franchise" ? "franchise" : "adaptation",
      );
      return;
    }
    if (view === "similar") {
      if (category === "all" || category === "webnovel") {
        await interaction.reply({ content: "Choose a category with provider-reported genre metadata to find cross-media matches.", flags: MessageFlags.Ephemeral });
        return;
      }
      await this.crossMediaSimilarityAndRespond(interaction, query, category);
      return;
    }
    if (view === "atlas") {
      await this.atlasAndRespond(
        interaction,
        query,
        category,
        filters,
        interaction.options.getString("target_title"),
        interaction.options.getString("target_category"),
        interaction.options.getString("target_url"),
        interaction.options.getString("relationship"),
      );
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
    if (view === "tv-guide") {
      if (category !== "tv") {
        await interaction.reply({content:"The season and episode guide requires the Television category.",flags:MessageFlags.Ephemeral});
        return;
      }
      await this.tmdbTvGuideSelectionAndRespond(interaction,query);
      return;
    }
    if (view === "availability" && category === "book") {
      const region = (interaction.options.getString("region") ?? await getGuildMediaRegion(interaction.guildId)).trim().toUpperCase();
      if (!/^[A-Z]{2}$/.test(region)) {
        await interaction.reply({ content:"Region must be a two-letter country code, such as IE or US.", flags:MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ content:loadingMessage("Checking the Google Books regional catalogue…"), flags:MessageFlags.Ephemeral });
      try {
        const books = await this.books.search(query, region);
        await this.presentResults(
          interaction,
          books.map(item=>({provider:"Google Books" as const,category:"book" as const,item})),
          "Google Books catalogue · "+region+" · Provider-reported catalogue and digital access, not a purchase guarantee",
        );
      } catch (error) {
        await interaction.editReply({ content:error instanceof Error?error.message:"The Google Books catalogue could not be checked.", embeds:[], components:[] });
      }
      return;
    }
    if (view === "availability" && category === "game") {
      const region = (interaction.options.getString("region") ?? await getGuildMediaRegion(interaction.guildId)).trim().toUpperCase();
      if (!/^[A-Z]{2}$/.test(region)) {
        await interaction.reply({ content:"Region must be a two-letter country code, such as IE or US.", flags:MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ content:loadingMessage("Checking the Steam Store catalogue…"), flags:MessageFlags.Ephemeral });
      try {
        const games = await this.steam.searchStoreGames(query,5,region);
        await this.presentResults(
          interaction,
          games.map(item=>({provider:"Steam" as const,category:"game" as const,item})),
          "Steam Store catalogue · "+region+" · Regional price and store record, not a universal availability guarantee",
        );
      } catch (error) {
        await interaction.editReply({ content:error instanceof Error?error.message:"Steam Store availability could not be checked.", embeds:[], components:[] });
      }
      return;
    }
    if (view === "availability" || view === "videos") {
      if (category !== "movie" && category !== "tv") {
        await interaction.reply({content:"Choose Books for regional catalogue access, Films or Television for streaming links, or Video Games for the Steam Store catalogue.",flags:MessageFlags.Ephemeral});
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
    if (action === "tmdb-details") {
      const category = categoryValue === "movie" || categoryValue === "tv" ? categoryValue : null;
      const id = Number(maybeId);
      if (!category || !/^\d+$/.test(maybeId ?? "") || !Number.isSafeInteger(id) || id < 1) {
        await interaction.reply({ content:"That TMDB details reference is invalid.", flags:MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      try {
        const item = await this.tmdb.details(id, category);
        if (!item) {
          await interaction.editReply({ content:"TMDB no longer returns that title.", embeds:[], components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])] });
          return true;
        }
        await interaction.editReply({
          content:"TMDB full details · runtime and country-specific ratings where supplied",
          embeds:[toEmbed({provider:"TMDB",category,item})],
          components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
          allowedMentions:{parse:[]},
        });
      } catch (error) {
        await interaction.editReply({
          content:error instanceof Error ? error.message : "TMDB could not load the full title details.",
          embeds:[],
          components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        });
      }
      return true;
    }
    if(action==="airing"){
      await interaction.showModal(airingSearchModal());
      return true;
    }
    if(action==="compare"){
      await interaction.showModal(compareSearchModal());
      return true;
    }
    if(action==="compare-submit"){
      const session=this.comparisonSessions.get(categoryValue??"");
      if(!session||session.ownerId!==interaction.user.id){
        await interaction.reply({content:"That comparison session has expired or belongs to another user. Open /discover again.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.deferUpdate();
      const fields=session.sides.map(side=>{
        const record=side.results[side.selected]!;
        const details=toEmbed(record).data.fields?.filter(field=>field.name!=="Provider")
          .map(field=>field.name+": "+field.value).join("\n")??"No additional provider metadata was supplied.";
        return{
          name:(categoryLabel(side.category)+" · "+this.recordTitle(record)).slice(0,256),
          value:("Provider: "+record.provider+"\nSource: "+this.recordUrl(record)+"\n"+details).slice(0,1024),
          inline:true,
        };
      });
      const embed=homeEmbed(
        "Media comparison",
        "Compare provider-reported information side by side. Missing fields are not inferred and no overall winner is calculated.",
        fields,
      ).setFooter({text:"AniList · Google Books · TMDB · IGDB · Steam · Source metadata only"});
      clearTimeout(session.timeout);
      this.comparisonSessions.delete(categoryValue??"");
      await interaction.editReply({
        content:"Comparison · "+session.sides.length+" titles",
        embeds:[embed],
        components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        allowedMentions:{parse:[]},
      });
      return true;
    }
    if(action==="airing-page"||action==="airing-refresh"){
      const session=this.airingSessions.get(categoryValue??"");
      if(!session||session.ownerId!==interaction.user.id){
        await interaction.reply({content:"That airing session has expired or belongs to another user. Open /discover again.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.deferUpdate();
      if(action==="airing-refresh"){
        try{
          session.entries=await this.anilist.searchUpcomingAirings(session.filters);
          session.page=0;
        }catch(error){
          const reference=await createInteractionIssueLog(interaction,"/discover",error,{action:"airing-refresh"});
          const message="AniList could not refresh the airing schedule. Try again shortly.";
          await interaction.editReply({content:reference?message+"\n\n"+issueHashNotice(reference):message,embeds:[],components:[]});
          return true;
        }
      }else{
        const page=Number(maybeId);
        if(!Number.isSafeInteger(page)||page<0||page>=Math.max(1,Math.ceil(session.entries.length/5))){
          await interaction.editReply({content:"That airing page is no longer available. Refresh the schedule.",embeds:[],components:[]});
          return true;
        }
        session.page=page;
      }
      await interaction.editReply(this.airingPage(categoryValue??"",session));
      return true;
    }
    if(action==="creator"){
      await interaction.reply({content:"Choose the media family for creator or company credits.",components:[creatorCategorySelect()],flags:MessageFlags.Ephemeral});
      return true;
    }
    if (action === "search" && CATEGORIES.some((item) => item.value === categoryValue)) {
      await interaction.showModal(searchModal(categoryValue as Category));
      return true;
    }
    if (action === "tv-page") {
      const showId=Number(categoryValue), seasonNumber=Number(maybeId), page=Number(interaction.customId.split(":")[4]??0);
      if(!Number.isSafeInteger(showId)||showId<1||!Number.isSafeInteger(seasonNumber)||seasonNumber<0||!Number.isSafeInteger(page)||page<0){
        await interaction.reply({content:"That TV guide page reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.deferUpdate();
      const [show,season]=await Promise.all([this.tmdb.tvDetails(showId),this.tmdb.tvSeason(showId,seasonNumber)]);
      if(!show||!season){
        await interaction.editReply({content:"TMDB could not load this TV season. Reopen the guide and try again.",embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]});
        return true;
      }
      const view=this.tvSeasonPage(show.name,season,page);
      await interaction.editReply({content:"TV Guide · "+show.name,embeds:[view.embed],components:view.components,allowedMentions:{parse:[]}});
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
    if (action === "creator-map") {
      const selectedName = interaction.values[0]?.trim();
      if (!selectedName || !interaction.guildId) {
        await interaction.reply({ content: "That creator selection is invalid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      const creators = await this.anilist.searchCreators(selectedName);
      const creator = creators.find(item => normalizeAtlasTitle(item.name) === normalizeAtlasTitle(selectedName));
      if (!creator) {
        await interaction.editReply({ content: "AniList no longer returns that creator record.", embeds: [], components: [navigationButtons("discover",[{id:"home",label:"Back to discovery"}])] });
        return true;
      }
      await recordProviderRelationships({
        sourceTitle: creator.name, sourceCategory: "CREATOR", sourceUrl: creator.url,
        sourceImageUrl: creator.image, sourceLabel: "AniList staff and creator credits",
        relations: creator.media.map(item => ({
          title: item.title, category: item.type === "ANIME" ? "ANIME" : "MANGA",
          url: item.url, imageUrl: item.image, relationshipType: item.role,
        })),
      });
      const graph = await findAtlasGraph(interaction.guildId, {
        title: creator.name, category: "CREATOR", url: creator.url, imageUrl: creator.image,
      }, { maxDepth: 3, maxNodes: 32, perNodeLimit: 12 });
      const exported = await atlasExportFiles(creator.name, "CREATOR", graph, "creator-atlas");
      const embed = homeEmbed("Creator Knowledge Map", creator.name, [
        { name: "Connected graph", value: graph.nodes.length + " nodes · " + graph.edges.length + " credit connections" + (graph.truncated ? " · more results omitted by graph limits" : ""), inline: false },
        { name: "Sources", value: "AniList creator credits · provider-attributed relationships", inline: false },
      ]).setImage(exported.image).setURL(creator.url);
      if (creator.image) embed.setThumbnail(creator.image);
      await interaction.editReply({
        content: "Creator Atlas · " + creator.name.slice(0,80), embeds: [embed], files: exported.files,
        components: [navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        allowedMentions: { parse: [] },
      });
      return true;
    }
    if (action === "creator-category") {
      const selectedCategory = interaction.values[0];
      if (!selectedCategory || !CATEGORIES.some((item) => item.value === selectedCategory && item.value !== "all")) {
        await interaction.reply({ content: "Choose a supported media family.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(creatorSearchModal(selectedCategory as Category));
      return true;
    }
    if(action==="compare-select"){
      const session=this.comparisonSessions.get(categoryValue??"");
      const sideIndex=Number(region);
      if(!session||session.ownerId!==interaction.user.id){
        await interaction.reply({content:"That comparison session has expired or belongs to another user.",flags:MessageFlags.Ephemeral});
        return true;
      }
      if(!Number.isSafeInteger(sideIndex)||sideIndex<0||sideIndex>=session.sides.length){
        await interaction.reply({content:"That comparison selection is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const selected=Number(interaction.values[0]);
      if(!Number.isSafeInteger(selected)||selected<0||selected>=session.sides[sideIndex]!.results.length){
        await interaction.reply({content:"That provider result is no longer available.",flags:MessageFlags.Ephemeral});
        return true;
      }
      session.sides[sideIndex]!.selected=selected;
      await interaction.deferUpdate();
      await interaction.editReply(this.comparisonSelectionPanel(categoryValue??"",session));
      return true;
    }
    if (action === "tmdb-tv-guide") {
      const selectedId=interaction.values[0]??"";
      const showId=Number(selectedId);
      if(!/^\d+$/.test(selectedId)||!Number.isSafeInteger(showId)||showId<1){
        await interaction.reply({content:"That TMDB series reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.deferUpdate();
      const show=await this.tmdb.tvDetails(showId);
      if(!show){
        await interaction.editReply({content:"TMDB did not return details for this series.",embeds:[],components:[]});
        return true;
      }
      const fields=[
        {name:"Status",value:show.status??"Unavailable",inline:true},
        {name:"Seasons",value:String(show.numberOfSeasons),inline:true},
        {name:"Episodes",value:String(show.numberOfEpisodes),inline:true},
        {name:"Episode runtime",value:show.episodeRuntimes.length?show.episodeRuntimes.map(value=>value+" min").join(", "):"Unavailable",inline:true},
        {name:"Created by",value:show.creators.join(", ")||"Unavailable",inline:true},
        {name:"Networks",value:show.networks.join(", ")||"Unavailable",inline:true},
        ...(show.nextEpisode?[{name:"Next episode",value:cleanText(show.nextEpisode.name,120)+" · "+(show.nextEpisode.airDate??"Date unavailable")+" · "+show.nextEpisode.sourceUrl,inline:false}]:[]),
      ];
      const embed=homeEmbed(show.name,show.overview?cleanText(show.overview,900):"No series overview was supplied by TMDB.",fields).setURL(show.sourceUrl);
      if(show.image)embed.setThumbnail(show.image);
      const components:ActionRowBuilder<StringSelectMenuBuilder|ButtonBuilder>[]=[];
      if(show.seasons.length){
        const select=new StringSelectMenuBuilder().setCustomId("discover:tmdb-tv-season:"+showId)
          .setPlaceholder("Choose a season")
          .addOptions(show.seasons.map(season=>({
            label:season.name.slice(0,100),
            description:season.episodeCount+" episode(s)"+(season.airDate?" · "+season.airDate:""),
            value:String(season.seasonNumber),
          })));
        components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
      }
      components.push(navigationButtons("discover",[{id:"home",label:"Back to discovery"}]));
      await interaction.editReply({content:"TV Guide · "+show.name,embeds:[embed],components,allowedMentions:{parse:[]}});
      return true;
    }
    if (action === "tmdb-tv-season") {
      const showId=Number(interaction.customId.split(":")[2]);
      const seasonValue=interaction.values[0]??"";
      const seasonNumber=Number(seasonValue);
      if(!Number.isSafeInteger(showId)||showId<1||!/^\d+$/.test(seasonValue)||!Number.isSafeInteger(seasonNumber)||seasonNumber<0||seasonNumber>100){
        await interaction.reply({content:"That TV season reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.deferUpdate();
      const [show,season]=await Promise.all([this.tmdb.tvDetails(showId),this.tmdb.tvSeason(showId,seasonNumber)]);
      if(!show||!season){
        await interaction.editReply({content:"TMDB could not load that season.",embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]});
        return true;
      }
      const view=this.tvSeasonPage(show.name,season,0);
      await interaction.editReply({content:"TV Guide · "+show.name,embeds:[view.embed],components:view.components,allowedMentions:{parse:[]}});
      return true;
    }
    if (action === "igdb-company") {
      const rawId = interaction.values[0] ?? "";
      const companyId = Number(rawId);
      if (!/^\d+$/.test(rawId) || !Number.isSafeInteger(companyId) || companyId < 1) {
        await interaction.reply({ content: "That IGDB company reference is invalid.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      const result = await this.igdb.getCompanyExplorer(companyId);
      if (!result) {
        await interaction.editReply({
          content: "IGDB no longer returns that company. Search again from Creator Explorer.",
          embeds:[],
          components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        });
        return true;
      }
      await recordProviderRelationships({
        sourceTitle:result.company.name,sourceCategory:"CREATOR",sourceUrl:result.company.sourceUrl,
        sourceImageUrl:result.company.logo,sourceLabel:"IGDB developer and publisher credits",
        relations:result.credits.map(credit=>({
          title:credit.title,category:"GAME",url:credit.sourceUrl,imageUrl:credit.image,
          relationshipType:credit.roles.join(" / ").toLowerCase()+" credit",
        })),
      });
      const works = result.credits.slice(0,10).map((credit) => {
        const roles = credit.roles.join(" / ");
        const release = credit.releaseDate ? " · First release " + credit.releaseDate : "";
        const score = credit.rating === null ? "" : " · IGDB " + credit.rating.toFixed(1) + "/100";
        const critic = credit.aggregatedRating === null ? "" : " · Critics " + credit.aggregatedRating.toFixed(1) + "/100";
        const platforms = credit.platforms.length ? " · " + credit.platforms.slice(0,5).join(", ") : "";
        const dates = credit.releases.slice(0,3).map(item =>
          (item.platform ?? "Platform unspecified") + " · " + item.date + (item.region ? " · " + item.region : ""),
        );
        return "[" + safeDisplay(credit.title,120) + "](" + credit.sourceUrl + ") · " + roles + release
          + score + critic + platforms + (dates.length ? "\n" + dates.join("\n") : "");
      }).join("\n\n").slice(0,3900);
      const graph = await findAtlasGraph(interaction.guildId, {
        title: result.company.name, category: "CREATOR", url: result.company.sourceUrl, imageUrl: result.company.logo,
      }, { maxDepth: 3, maxNodes: 32, perNodeLimit: 12 });
      const exported = await atlasExportFiles(result.company.name, "CREATOR", graph, "developer-atlas");
      const fields = [
        { name: "IGDB company", value: "#" + result.company.id + " · [Open source record](" + result.company.sourceUrl + ")", inline: true },
        {
          name: "Known game credits",
          value: works || "IGDB returned no developer, publisher, porting or supporting credits for this company.",
          inline: false,
        },
        ...(result.company.websites.length ? [{
          name: "Company websites",
          value: result.company.websites.slice(0,3).map((url,index) => "[Website " + (index+1) + "](" + url + ")").join(" · "),
          inline: false,
        }] : []),
        ...(result.truncated ? [{
          name: "Coverage",
          value: "Showing the first 10 works from a larger IGDB credit list. Refine the company search to inspect another company record.",
          inline: false,
        }] : []),
      ];
      const embed = homeEmbed(
        safeDisplay(result.company.name,240),
        safeDescription(result.company.description,1_200),
        fields,
      ).setFooter({text:"IGDB · Company and involved-company credits"});
      if (result.company.logo) embed.setThumbnail(result.company.logo);
      await interaction.editReply({
        content:"Developer and publisher workography · " + safeDisplay(result.company.name,100),
        embeds:[embed.setImage(exported.image)],
        files: exported.files,
        components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
        allowedMentions:{parse:[]},
      });
      return true;
    }
    if (action === "tmdb-person") {
      const selectedId = interaction.values[0] ?? "";
      const personId = Number(selectedId);
      if (!/^\d+$/.test(selectedId) || !Number.isSafeInteger(personId) || personId < 1) {
        await interaction.reply({content:"That TMDB person reference is invalid.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const personName = interaction.component.options.find((option) => option.value === selectedId)?.label ?? "Person";
      await interaction.deferUpdate();
      const [personMatches, credits] = await Promise.all([
        this.tmdb.searchPeople(personName),
        this.tmdb.personCredits(personId),
      ]);
      const person = personMatches.find(candidate => candidate.id === personId);
      await recordProviderRelationships({
        sourceTitle:personName,sourceCategory:"CREATOR",sourceUrl:person?.sourceUrl,
        sourceImageUrl:person?.image,sourceLabel:"TMDB cast and crew credits",
        relations:credits.map(credit=>({
          title:credit.title,category:credit.category==="movie"?"MOVIE":"TV",
          url:credit.sourceUrl,imageUrl:credit.image,relationshipType:credit.role??"cast or crew credit",
        })),
      });
      const graph = await findAtlasGraph(interaction.guildId, {
        title: personName, category: "CREATOR",
        url: person?.sourceUrl ?? "https://www.themoviedb.org/person/" + personId,
        imageUrl: person?.image,
      }, { maxDepth: 3, maxNodes: 32, perNodeLimit: 12 });
      const exported = await atlasExportFiles(personName, "CREATOR", graph, "tmdb-person-atlas");
      const description = credits.length
        ? credits.map((credit) => {
          const role = credit.role ? " · "+cleanText(credit.role,100) : "";
          const date = credit.releaseDate ? " · "+credit.releaseDate : "";
          return "["+cleanText(credit.title,180).replace(/[\[\]]/g,"")+"]("+credit.sourceUrl+") · "+credit.category.toUpperCase()+date+role;
        }).join("\n").slice(0,4000)
        : "TMDB did not return combined movie or television credits for this person.";
      const embed = homeEmbed("Credits · "+personName,description).setURL("https://www.themoviedb.org/person/"+personId)
        .setFooter({text:"TMDB · Cast and crew credits deduplicated by work"});
      await interaction.editReply({content:"Person Credits · "+personName,embeds:[embed.setImage(exported.image)],files:exported.files,components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],allowedMentions:{parse:[]}});
      return true;
    }
    if (action === "tmdb-collection") {
      const selectedId = interaction.values[0] ?? "";
      const movieId = Number(selectedId);
      if (!/^\d+$/.test(selectedId) || !Number.isSafeInteger(movieId) || movieId < 1) {
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
        ? collection.items.map((item) => "["+cleanText(item.title,180).replace(/[\[\]]/g,"")+"]("+item.sourceUrl+") · "+(item.releaseDate??"Date unavailable")).join("\n").slice(0,4000)
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

  private async tmdbTvGuideSelectionAndRespond(interaction: ChatInputCommandInteraction,query:string):Promise<void>{
    await interaction.reply({content:loadingMessage("Searching TV series…"),flags:MessageFlags.Ephemeral});
    const results=await this.tmdb.search(query,"tv");
    if(!results.length){
      await interaction.editReply({content:"TMDB returned no matching TV series.",embeds:[],components:[]});
      return;
    }
    const select=new StringSelectMenuBuilder().setCustomId("discover:tmdb-tv-guide")
      .setPlaceholder("Choose the exact TV series")
      .addOptions(results.slice(0,25).map(item=>({
        label:item.title.slice(0,100),
        description:(item.releaseDate??"First air date unavailable")+" · TMDB #"+item.id,
        value:String(item.id),
      })));
    await interaction.editReply({content:"Choose a series to inspect its status, creators, networks and season guide.",embeds:[],components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)]});
  }

  private tvSeasonPage(showName:string,season:TmdbTvSeason,page:number):{
    embed:EmbedBuilder;
    components:ActionRowBuilder<ButtonBuilder>[];
  }{
    const pageSize=6;
    const totalPages=Math.max(1,Math.ceil(season.episodes.length/pageSize));
    const current=Math.min(page,totalPages-1);
    const visible=season.episodes.slice(current*pageSize,(current+1)*pageSize);
    const description=visible.map(episode=>{
      const metadata=[episode.airDate??"Date not announced",episode.runtime?episode.runtime+" min":""].filter(Boolean).join(" · ");
      const synopsis=episode.overview?"\n||"+cleanText(episode.overview,280)+"||":"\n||Episode synopsis unavailable.||";
      return "**E"+episode.episodeNumber+" · "+cleanText(episode.name,120)+"**\n"+metadata+synopsis;
    }).join("\n\n")||"TMDB has not listed episode entries for this season.";
    const embed=homeEmbed(showName+" · "+season.name,description)
      .setURL(season.sourceUrl)
      .setFooter({text:"TMDB episode metadata · Synopsis text is spoiler-marked · Page "+(current+1)+"/"+totalPages});
    const buttons=new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("discover:tv-page:"+season.showId+":"+season.seasonNumber+":"+(current-1)).setLabel("Previous").setStyle(ButtonStyle.Secondary).setDisabled(current===0),
      new ButtonBuilder().setCustomId("discover:tv-page:"+season.showId+":"+season.seasonNumber+":"+(current+1)).setLabel("Next").setStyle(ButtonStyle.Secondary).setDisabled(current>=totalPages-1),
    );
    return {embed,components:[buttons,navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]};
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
    if(action==="compare-search"){
      let entries:ReturnType<typeof parseMediaComparisonEntries>;
      try{
        entries=parseMediaComparisonEntries(interaction.fields.getTextInputValue("entries"));
      }catch(error){
        await interaction.reply({content:error instanceof Error?error.message:"Enter two to four valid comparison entries.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await interaction.reply({content:loadingMessage("Finding matching media…"),flags:MessageFlags.Ephemeral});
      const lookups=await Promise.allSettled(entries.map(entry=>this.fetchSearch(entry.title,entry.category)));
      const providerFailures=lookups.flatMap(result=>result.status==="rejected"?[result.reason]:[]);
      const failedInputs=lookups.flatMap((result,index)=>result.status==="rejected"?[entries[index]?.title ?? "unknown title"]:[]);
      const issueHash=providerFailures.length
        ? await createInteractionIssueLog(interaction,"/discover",
            new AggregateError(providerFailures,"One or more media comparison lookups failed."),
            {action:"media-comparison",failedInputs})
        : null;
      const missing=entries.flatMap((entry,index)=>{
        const result=lookups[index];
        return !result||result.status!=="fulfilled"||!result.value.length
          ?[categoryLabel(entry.category)+" · "+entry.title]:[];
      });
      if(missing.length){
        await interaction.editReply({
          content:"No usable provider result was found for: "+missing.join("; ")+". Check the title or provider configuration, then try again."
            +(issueHash?"\n\n"+issueHashNotice(issueHash):""),
          embeds:[],components:[],
        });
        return true;
      }
      const sessionId=interaction.id;
      const sides=entries.map((entry,index)=>({
        category:entry.category,title:entry.title,
        results:(lookups[index] as PromiseFulfilledResult<SearchRecord[]>).value.slice(0,25),
        selected:0,
      }));
      const timeout=setTimeout(()=>this.comparisonSessions.delete(sessionId),180_000);
      timeout.unref();
      const session={ownerId:interaction.user.id,sides,timeout};
      this.comparisonSessions.set(sessionId,session);
      await interaction.editReply(this.comparisonSelectionPanel(sessionId,session));
      return true;
    }
    if(action==="airing-search"){
      const title=interaction.fields.getTextInputValue("title").trim()||undefined;
      const seasonInput=interaction.fields.getTextInputValue("season").trim().toUpperCase();
      const yearInput=interaction.fields.getTextInputValue("year").trim();
      const dayInput=interaction.fields.getTextInputValue("day").trim();
      const daysInput=interaction.fields.getTextInputValue("days").trim();
      const days=daysInput?Number(daysInput):7;
      const year=yearInput?Number(yearInput):undefined;
      const validDays=Number.isInteger(days)&&days>=1&&days<=14;
      const validYear=year===undefined||(Number.isInteger(year)&&year>=1970&&year<=2100);
      const validSeason=!seasonInput||["WINTER","SPRING","SUMMER","FALL"].includes(seasonInput);
      const validDay=!dayInput||["MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY","SATURDAY","SUNDAY"].includes(dayInput.toUpperCase());
      if(!validDays||!validYear||!validSeason||!validDay){
        await interaction.reply({content:"Use a 1–14 day window, a year from 1970–2100, a valid season, and a weekday from Monday to Sunday.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const filters:AniListAiringFilters={
        ...(title?{title}:{}),
        ...(seasonInput?{season:seasonInput}:{}),
        ...(year!==undefined?{year}:{}),
        ...(dayInput?{day:dayInput}:{}),
        days,
      };
      await interaction.reply({content:loadingMessage("Loading upcoming anime episodes…"),flags:MessageFlags.Ephemeral});
      try{
        const entries=await this.anilist.searchUpcomingAirings(filters);
        const sessionId=interaction.id;
        const timeout=setTimeout(()=>this.airingSessions.delete(sessionId),180_000);
        timeout.unref();
        this.airingSessions.set(sessionId,{ownerId:interaction.user.id,filters,entries,page:0,timeout});
        await interaction.editReply(this.airingPage(sessionId,this.airingSessions.get(sessionId)!));
      }catch(error){
        const reference=await createInteractionIssueLog(interaction,"/discover",error,{action:"airing-search",filters});
        const message="AniList could not load the airing schedule. Try again shortly.";
        await interaction.editReply({content:reference?message+"\n\n"+issueHashNotice(reference):message});
      }
      return true;
    }
    if(action==="creator-search"){
      const category = CATEGORIES.some((item) => item.value === categoryValue && item.value !== "all")
        ? categoryValue as Category
        : "anime";
      await this.creatorAndRespond(interaction,interaction.fields.getTextInputValue("query"),category);
      return true;
    }
    if (action !== "search" || !CATEGORIES.some((item) => item.value === categoryValue)) return false;
    await this.searchAndRespond(interaction, interaction.fields.getTextInputValue("query"), categoryValue as Category);
    return true;
  }

  private async suggestRelationshipAndRespond(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({content:"Community media relationships are scoped to a server.",flags:MessageFlags.Ephemeral});
      return;
    }
    const sourceTitle=interaction.options.getString("source_title");
    const sourceCategory=interaction.options.getString("source_category");
    const sourceUrl=interaction.options.getString("source_url");
    const relationship=interaction.options.getString("relationship");
    const targetTitle=interaction.options.getString("target_title");
    const targetCategory=interaction.options.getString("target_category");
    const targetUrl=interaction.options.getString("target_url");
    const evidence=interaction.options.getString("evidence");
    if(!sourceTitle||!sourceCategory||!sourceUrl||!relationship||!targetTitle||!targetCategory||!targetUrl||!evidence){
      await interaction.reply({content:"Choose Suggest a community relationship and provide both titles, categories, HTTPS metadata links, relationship type and evidence.",flags:MessageFlags.Ephemeral});
      return;
    }
    try {
      const id=await createMediaLinkSuggestion(interaction.guildId,interaction.user.id,{
        sourceTitle,sourceCategory,sourceUrl,relationship,targetTitle,targetCategory,targetUrl,evidence,
      });
      await interaction.reply({content:`Media relationship suggestion #${id} was saved for moderator review in this server. It is not provider-confirmed metadata.`,flags:MessageFlags.Ephemeral});
    } catch(error) {
      const issueHash=await createInteractionIssueLog(interaction,"/discover",error,{action:"suggest-link"});
      const message=error instanceof Error?error.message:"The media relationship suggestion could not be saved.";
      await interaction.reply({content:issueHash?message+"\n\n"+issueHashNotice(issueHash):message,flags:MessageFlags.Ephemeral});
    }
  }

  private async reviewRelationshipAndRespond(interaction: ChatInputCommandInteraction): Promise<void> {
    if(!interaction.guildId){
      await interaction.reply({content:"Media relationship review is scoped to a server.",flags:MessageFlags.Ephemeral});
      return;
    }
    const permissions=interaction.memberPermissions;
    if(!permissions?.has(PermissionFlagsBits.ManageGuild)&&!permissions?.has(PermissionFlagsBits.ManageMessages)){
      await interaction.reply({content:"Manage Server or Manage Messages permission is required to review media relationships.",flags:MessageFlags.Ephemeral});
      return;
    }
    const decision=interaction.options.getString("decision")??"list";
    const suggestionId=interaction.options.getInteger("suggestion_id");
    if(decision==="list"){
      const pending=await listPendingMediaLinkSuggestions(interaction.guildId);
      const fields=pending.slice(0,10).map((item)=>({
        name:"#"+item.id+" · "+cleanText(item.source_title,100),
        value:cleanText(item.relationship_type,60)+" → "+cleanText(item.target_title,120)+"\nSubmitted by <@"+item.submitter_id+">",
        inline:false,
      }));
      await interaction.reply({
        embeds:[homeEmbed("Pending media relationship suggestions",fields.length?"Inspect a suggestion before approving or rejecting it.":"There are no pending media relationship suggestions.",fields)],
        flags:MessageFlags.Ephemeral,
        allowedMentions:{parse:[]},
      });
      return;
    }
    if(!suggestionId){
      await interaction.reply({content:"Provide suggestion_id. Use decision: list to view pending suggestions.",flags:MessageFlags.Ephemeral});
      return;
    }
    if(decision==="inspect"){
      const suggestion=await getPendingMediaLinkSuggestion(interaction.guildId,String(suggestionId));
      if(!suggestion){
        await interaction.reply({content:"No pending suggestion with that ID exists in this server.",flags:MessageFlags.Ephemeral});
        return;
      }
      const embed=homeEmbed("Media relationship suggestion #"+suggestion.id,
        "The proposal is pending. Approval means community-verified in this server, not provider-confirmed.",[
          {name:"Source",value:"["+cleanText(suggestion.source_title,180)+"]("+suggestion.source_url+") · "+suggestion.source_category,inline:false},
          {name:"Relationship",value:cleanText(suggestion.relationship_type,100),inline:true},
          {name:"Target",value:"["+cleanText(suggestion.target_title,180)+"]("+suggestion.target_url+") · "+suggestion.target_category,inline:false},
          {name:"Submitter evidence",value:cleanText(suggestion.evidence,1_000),inline:false},
        ]).setFooter({text:"Submitted by "+suggestion.submitter_id});
      await interaction.reply({embeds:[embed],flags:MessageFlags.Ephemeral,allowedMentions:{parse:[]}});
      return;
    }
    if(decision!=="approved"&&decision!=="rejected"){
      await interaction.reply({content:"Choose List, Inspect, Approve or Reject.",flags:MessageFlags.Ephemeral});
      return;
    }
    const reviewed=await reviewMediaLinkSuggestion({
      guildId:interaction.guildId,
      suggestionId:String(suggestionId),
      reviewerId:interaction.user.id,
      decision,
      reason:interaction.options.getString("reason")??undefined,
    });
    if(!reviewed){
      await interaction.reply({content:"That suggestion was already reviewed or does not exist in this server.",flags:MessageFlags.Ephemeral});
      return;
    }
    const result=decision==="approved"
      ?"approved as a community-verified relationship in this server (not provider-confirmed)"
      :"rejected";
    await interaction.reply({content:`Suggestion #${suggestionId} was ${result}.`,flags:MessageFlags.Ephemeral});
  }

  private async releaseExplorerAndRespond(
    interaction: ChatInputCommandInteraction,
    category: Category,
  ): Promise<void> {
    const categories: Array<"anime" | "tv" | "movies" | "games"> =
      category === "game" ? ["games"]
        : category === "movie" ? ["movies"]
        : category === "tv" ? ["tv"]
        : category === "anime" ? ["anime"]
        : category === "all" ? ["anime", "tv", "movies", "games"]
        : [];
    if (!categories.length) {
      await interaction.reply({ content: "Choose Anime, Films, Television, Games or All media for provider-dated releases.", flags: MessageFlags.Ephemeral });
      return;
    }
    const from = new Date();
    const to = new Date(from.getTime() + 30 * 24 * 60 * 60 * 1000);
    const region = (interaction.options.getString("region") ?? await getGuildMediaRegion(interaction.guildId)).trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(region)) {
      await interaction.reply({ content: "Region must be a two-letter country code, such as IE or US.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ content: loadingMessage("Loading provider-dated releases…"), flags: MessageFlags.Ephemeral });
    try {
      const calendar = await upcomingProviderReleases(
        this.anilist, this.tmdb, from, to, region, categories, this.igdb,
      );
      const embeds = calendar.results.slice(0, 10).map(item => {
        const timestamp = Math.floor(new Date(item.when).getTime() / 1000);
        return homeEmbed(item.title, item.provider + " · <t:" + timestamp + ":F>", [
          { name: "Provider source", value: "[Open release record](" + item.url + ")", inline: false },
        ]).setURL(item.url).setFooter({ text: "Provider-dated result · 30-day window" });
      });
      await interaction.editReply({
        content: (calendar.results.length
          ? calendar.results.length + " dated release(s) returned"
          : "No dated releases were returned for this window") +
          (calendar.unavailableProviders.length ? "\nUnavailable providers: " + calendar.unavailableProviders.join(", ") : ""),
        embeds,
        components: [navigationButtons("discover", [{ id: "home", label: "Back to discovery" }])],
        allowedMentions: { parse: [] },
      });
    } catch (error) {
      await interaction.editReply({ content: error instanceof Error ? error.message : "The release providers could not be queried.", embeds: [], components: [] });
    }
  }

  private metadataAuditFields(record: SearchRecord): MetadataSourceAuditInput {
    if (record.provider === "AniList") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.id, url: item.siteUrl,
        fields: { description:item.description, releaseDate:item.startDate?.year, creators:item.staffCredits, genres:item.genres, image:item.coverImage } };
    }
    if (record.provider === "Google Books") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.id, url: item.sourceUrl,
        fields: { description:item.description, releaseDate:item.publishedDate, creators:item.authors, genres:item.categories, image:item.image } };
    }
    if (record.provider === "TMDB") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.id, url: item.sourceUrl,
        fields: { description:item.overview, releaseDate:item.releaseDate, creators:undefined, genres:item.genres, image:item.image } };
    }
if (record.provider === "NovelFire" || record.provider === "Novel Archive" || record.provider === "Wuxia Click" || record.provider === "Novel Updates" || record.provider === "ScribbleHub") {
const item = record.item;
return { provider: record.provider, category: record.category, id: item.sourceUrl, url: item.sourceUrl,
fields: { description:item.description, releaseDate:item.latestUpdate, creators:item.author ? [item.author] : [], genres:item.genres, image:item.image, rating:item.rating, chapterCount:item.chapterCount } };
}
    if (record.provider === "Royal Road") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.id, url: item.sourceUrl,
        fields: { releaseDate:item.latestUpdate, creators:item.author ? [item.author] : [] } };
    }
    if (record.provider === "IGDB") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.id, url: item.sourceUrl,
        fields: { description:item.summary, releaseDate:item.releaseDate, creators:[...item.developers,...item.publishers], genres:item.genres, image:item.image, rating:item.rating, aggregatedRating:item.aggregatedRating } };
    }
    if (record.provider === "Steam") {
      const item = record.item;
      return { provider: record.provider, category: record.category, id: item.appId, url:this.recordUrl(record),
        fields: { description:item.shortDescription, releaseDate:item.releaseDate, creators:[...item.developers,...item.publishers], genres:item.genres, image:item.headerImage } };
    }
    throw new Error("Unsupported metadata source provider.");
  }

  private async metadataSourcesAndRespond(
    interaction: ChatInputCommandInteraction,
    query: string,
  ): Promise<void> {
    if (!query) {
      await interaction.reply({ content:"Enter a title to inspect provider metadata and missing fields.", flags:MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ content:loadingMessage("Comparing provider metadata…"), flags:MessageFlags.Ephemeral });
    const results = await this.fetchSearch(query,"all");
    if (!results.length) {
      await interaction.editReply({ content:"No providers returned a source record for that title.", embeds:[], components:[] });
      return;
    }
    const exact = results.filter(record=>normalizeAtlasTitle(this.recordTitle(record))===normalizeAtlasTitle(query));
    const selected = (exact.length?exact:results).slice(0,8);
    const audits = selected.map(record=>auditMetadataSource(this.metadataAuditFields(record)));
    const embeds = selected.map((record,index)=>{
      const audit=audits[index]!;
      const embed=homeEmbed(this.recordTitle(record),
        "Provider-backed metadata coverage. Missing values mean that provider did not return that field for this record; they do not prove the information does not exist.",
        [
          {name:"Provider record",value:formatMetadataSourceReference(audit.provider,audit.id,audit.url),inline:false},
          {name:"Reported fields",value:audit.presentFields.map(value=>value.replace(/([A-Z])/g," $1").toLowerCase()).join(" · ")||"None of the compared fields",inline:false},
          {name:"Missing fields",value:audit.missingFields.map(value=>value.replace(/([A-Z])/g," $1").toLowerCase()).join(" · ")||"No gaps in this comparison",inline:false},
          {name:"Freshness",value:"Not reported by provider",inline:true},
        ]).setURL(audit.url).setFooter({text:audit.provider+" · "+audit.category+" · source metadata"});
      const image=this.recordImage(record);
      if(image)embed.setThumbnail(image);
      return embed;
    });
    await interaction.editReply({
      content:(exact.length?"Exact-title provider matches":"Related search matches · exact cross-provider match was not found")+
        " · "+selected.length+" source record(s)",
      embeds,components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])],
      allowedMentions:{parse:[]},
    });
  }

  private async creatorAndRespond(
    interaction:ChatInputCommandInteraction|ModalSubmitInteraction,
    query:string,
    category:Category="anime",
  ):Promise<void>{
    await interaction.reply({content:loadingMessage("Exploring creators…"),flags:MessageFlags.Ephemeral});
    if(category==="webnovel"){
      await interaction.editReply({content:"Webnovel providers do not expose a shared creator directory. Search a title to view its author and source metadata.",embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]});
      return;
    }
    if(category==="book"){
      const books=await this.books.search("inauthor:"+query.trim());
      const authorUrl="https://books.google.com/books?as_authors="+encodeURIComponent(query.trim());
      await recordProviderRelationships({
        sourceTitle:query.trim(),sourceCategory:"CREATOR",sourceUrl:authorUrl,
        sourceLabel:"Google Books author-attributed editions",
        relations:books.slice(0,20).map(book=>({
          title:book.title,category:"BOOK",url:book.sourceUrl,imageUrl:book.image,relationshipType:"author credit",
        })),
      });
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
      const graph = await findAtlasGraph(interaction.guildId, {
        title: query.trim(), category: "CREATOR", url: authorUrl,
      }, { maxDepth: 2, maxNodes: 24, perNodeLimit: 8 });
      const files = graph.nodes.length > 1 ? await atlasExportFiles(query.trim(), "CREATOR", graph, "author-atlas") : null;
      const graphEmbed = files
        ? new EmbedBuilder().setColor(0x5865f2).setTitle("Author Knowledge Map")
          .setDescription(graph.nodes.length + " nodes · " + graph.edges.length + " attributed-work connections")
          .setImage(files.image)
        : null;
      await interaction.editReply({
        content:embeds.length?"Author works · "+query.trim().slice(0,80):"Google Books returned no works attributed to that author.",
        embeds: [...embeds, ...(graphEmbed ? [graphEmbed] : [])].slice(0,10),
        files: files?.files ?? [],
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
    if(category==="game"){
      const companies=await this.igdb.searchCompanies(query);
      if(!companies.length){
        await interaction.editReply({content:"IGDB returned no matching game development or publishing companies.",embeds:[],components:[navigationButtons("discover",[{id:"home",label:"Back to discovery"}])]});
        return;
      }
      const select=new StringSelectMenuBuilder()
        .setCustomId("discover:igdb-company")
        .setPlaceholder("Choose the exact game company")
        .addOptions(companies.slice(0,10).map((company)=>({
          label:company.name.slice(0,100),
          description:"IGDB company #"+company.id,
          value:String(company.id),
        })));
      await interaction.editReply({
        content:"Choose the exact company to inspect its developer and publisher credits.",
        embeds:[],
        components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
        allowedMentions:{parse:[]},
      });
      return;
    }
    const creators=await this.anilist.searchCreators(query);
    if(!creators.length){await interaction.editReply({content:"AniList returned no matching creators.",embeds:[],components:[]});return;}
    await Promise.allSettled(creators.map(creator=>recordProviderRelationships({
      sourceTitle:creator.name,sourceCategory:"CREATOR",sourceUrl:creator.url,sourceImageUrl:creator.image,
      sourceLabel:"AniList staff and creator credits",
      relations:creator.media.map(item=>({
        title:item.title,category:item.type==="ANIME"?"ANIME":"MANGA",url:item.url,
        imageUrl:item.image,relationshipType:item.role,
      })),
    })));
    const embeds=creators.slice(0,10).map(creator=>{
      const embed=homeEmbed(creator.name,safeDescription(creator.description,1200),[
        {name:"Occupations",value:creator.occupations.join(", ")||"Unavailable",inline:true},
        {name:"Years active",value:creator.yearsActive.length?creator.yearsActive.join(" – "):"Unavailable",inline:true},
        {name:"Known work",value:creator.media.slice(0,5).map(item=>`[${item.title}](${item.url}) · ${item.role}`).join("\n")||"No linked media returned",inline:false},
      ]).setURL(creator.url).setFooter({text:"AniList · Creator metadata"});
      if(creator.image)embed.setThumbnail(creator.image);
      return embed;
    });
    const creatorOptions = creators.slice(0,10)
      .filter((creator,index,list) => list.findIndex(item => item.name === creator.name) === index)
      .map(creator => ({
        label: creator.name.slice(0,100),
        description: creator.occupations.slice(0,2).join(" · ").slice(0,100) || "AniList creator record",
        value: creator.name.slice(0,100),
      }));
    const components: Array<ActionRowBuilder<StringSelectMenuBuilder | ButtonBuilder>> = [];
    if (creatorOptions.length) {
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
        new StringSelectMenuBuilder().setCustomId("discover:creator-map")
          .setPlaceholder("Export a creator relationship map").addOptions(creatorOptions),
      ));
    }
    components.push(navigationButtons("discover",[{id:"home",label:"Back to discovery"}]));
    await interaction.editReply({content:`Creator Explorer · ${query.trim().slice(0,80)}`,embeds,components,allowedMentions:{parse:[]}});
  }

  private async mediaGridAndRespond(
    interaction: ChatInputCommandInteraction,
    titles: string[],
    category: "anime" | "manga" | "light_novel" | "game",
    sources: MediaGridSource[] | null = null,
  ): Promise<void> {
    await interaction.reply({
      content: loadingMessage("Resolving the nine media covers…"),
      flags: MessageFlags.Ephemeral,
    });
    const fallbackTitle = (source: MediaGridSource): string =>
      source.kind === "game" ? source.slug.replaceAll("-", " ") : source.kind + " #" + source.id;
    const items = sources
      ? await Promise.all(sources.map(async source => {
          const fallback = fallbackTitle(source);
          try {
            if (source.kind === "anime" || source.kind === "manga") {
              const record = await this.anilist.getMediaById(source.id, source.kind === "anime" ? "ANIME" : "MANGA");
              return {
                title: record?.title.english ?? record?.title.romaji ?? record?.title.native ?? fallback,
                image: record?.coverImage ?? null,
              };
            }
            if (source.kind === "character") {
              const record = await this.anilist.getPublicEntity(source.id, "CHARACTER");
              return { title: record?.name ?? fallback, image: record?.image ?? null };
            }
            const records = await this.igdb.search(source.slug);
            const record = records.find(item => {
              try {
                const url = new URL(item.sourceUrl);
                return (url.hostname === "igdb.com" || url.hostname === "www.igdb.com")
                  && url.pathname.replace(/\/$/, "") === "/games/" + source.slug;
              } catch {
                return false;
              }
            });
            return { title: record?.title ?? fallback, image: record?.image ?? null };
          } catch {
            return { title: fallback, image: null };
          }
        }))
      : await Promise.all(titles.map(async title => {
          try {
            if (category === "game") {
              const record = (await this.igdb.search(title))[0];
              return { title: record?.title ?? title, image: record?.image ?? null };
            }
            const records = await this.anilist.search(title, category === "anime" ? "ANIME" : "MANGA", category === "light_novel");
            const record = records[0];
            return {
              title: record?.title.english ?? record?.title.romaji ?? record?.title.native ?? title,
              image: record?.coverImage ?? null,
            };
          } catch {
            return { title, image: null };
          }
        }));
    const image = await renderMediaGrid(items);
    const unresolved = items.filter(item => !item.image).length;
    const description = unresolved
      ? `${9 - unresolved} of 9 covers were found. Missing covers use safe placeholders.`
      : "Nine provider-backed covers, arranged in a 3×3 grid.";
    const firstSource = sources?.[0];
    const label = firstSource?.kind === "character" ? "Characters"
      : firstSource?.kind === "game" ? "Games"
      : firstSource ? categoryLabel(firstSource.kind)
      : categoryLabel(category);
    const embed = homeEmbed(`3×3 · ${label}`, description)
      .setImage("attachment://media-grid.png");
    await interaction.editReply({
      content: "",
      embeds: [embed],
      files: [new AttachmentBuilder(image, { name: "media-grid.png" })],
      components: [],
      allowedMentions: { parse: [] },
    });
  }

  private async crossMediaSimilarityAndRespond(
    interaction: ChatInputCommandInteraction,
    query: string,
    category: Exclude<Category, "all" | "webnovel">,
  ): Promise<void> {
    await interaction.reply({
      content: loadingMessage("Finding source-backed cross-media matches…"),
      flags: MessageFlags.Ephemeral,
    });

    const seeds = await this.fetchSearch(query, category);
    const first = seeds[0];
    if (!first) {
      await interaction.editReply({ content: "No starting title was returned by the selected provider.", embeds: [], components: [] });
      return;
    }

    let seed: SearchRecord = first;
    if (seed.provider === "AniList") {
      seed = { ...seed, item: await this.anilist.getMediaById(seed.item.id, seed.item.type) ?? seed.item };
    } else if (seed.provider === "TMDB") {
      seed = { ...seed, item: await this.tmdb.details(seed.item.id, seed.item.category) ?? seed.item };
    }

    const seedTitle = this.recordTitle(seed);
    const seedUrl = this.recordUrl(seed);
    const seedCategory = seed.category as CrossMediaCandidate["category"];
    const seedGenres: string[] = seed.provider === "AniList"
      ? [
          ...seed.item.genres,
          ...seed.item.tags.filter(tag => !tag.isSpoiler && (tag.rank ?? 0) >= 75).map(tag => tag.name),
        ]
      : seed.provider === "Google Books"
        ? seed.item.categories
        : seed.provider === "Royal Road"
          ? []
          : seed.item.genres;
    const genreLabels = recommendationGenreLabels([...new Set(seedGenres)]);
    const localLookups: Array<Promise<CrossMediaCandidate[]>> = [];

    if (genreLabels.length) {
      const aniListGenres = genreLabels.map(label => label === "Science Fiction" ? "Sci-Fi" : label);
      localLookups.push(
        this.anilist.searchByGenres("ANIME", aniListGenres).then(items => items.map(item => ({
          title: item.title.english ?? item.title.romaji ?? item.title.native ?? "Untitled",
          category: "anime" as const, provider: "AniList", url: item.siteUrl, genres: item.genres,
        }))),
        this.anilist.searchByGenres("MANGA", aniListGenres).then(items => items
          .filter(item => item.format !== "NOVEL")
          .map(item => ({
            title: item.title.english ?? item.title.romaji ?? item.title.native ?? "Untitled",
            category: "manga" as const, provider: "AniList", url: item.siteUrl, genres: item.genres,
          }))),
        this.anilist.searchByGenres("MANGA", aniListGenres, [], true).then(items => items.map(item => ({
          title: item.title.english ?? item.title.romaji ?? item.title.native ?? "Untitled",
          category: "light_novel" as const, provider: "AniList", url: item.siteUrl, genres: item.genres,
        }))),
        ...genreLabels.map(label => this.books.searchBySubject(label).then(items => items.map(item => ({
          title: item.title, category: "book" as const, provider: "Google Books", url: item.sourceUrl, genres: item.categories,
        })))),
        this.tmdb.discoverByGenres("movie", genreLabels).then(items => items.map(item => ({
          title: item.title, category: "movie" as const, provider: "TMDB", url: item.sourceUrl, genres: item.genres,
        }))),
        this.tmdb.discoverByGenres("tv", genreLabels).then(items => items.map(item => ({
          title: item.title, category: "tv" as const, provider: "TMDB", url: item.sourceUrl, genres: item.genres,
        }))),
      );
    }

    const localResults: CrossMediaCandidate[] = [];
    const settled = await Promise.allSettled(localLookups);
    for (const result of settled) {
      if (result.status === "fulfilled") localResults.push(...result.value);
      else logger.warn("Cross-media provider lookup failed", {
        category,
        reason: result.reason instanceof Error ? result.reason.message : "Unknown provider error",
      });
    }
    const ranked = rankCrossMediaCandidates(seedTitle, seedCategory, seedGenres, localResults, 10);

    let providerRecommendations: SearchRecord[] = [];
    try {
      if (seed.provider === "AniList") {
        providerRecommendations = (await this.anilist.recommendations(seed.item.id, seed.item.type))
          .map(item => ({ provider: "AniList" as const, category: seed.category, item }));
      } else if (seed.provider === "TMDB") {
        providerRecommendations = (await this.tmdb.recommendations(seed.item.id, seed.item.category))
          .map(item => ({ provider: "TMDB" as const, category: seed.category, item }));
      } else if (seed.provider === "IGDB") {
        providerRecommendations = (await this.igdb.similarGames(seed.item.id))
          .map(item => ({ provider: "IGDB" as const, category: "game" as const, item }));
      }
    } catch (error) {
      logger.warn("Provider-native recommendations could not be loaded", {
        provider: seed.provider,
        reason: error instanceof Error ? error.message : "Unknown provider error",
      });
    }

    const sourceCategory = ({
      anime: "ANIME", manga: "MANGA", light_novel: "LIGHT_NOVEL",
      book: "BOOK", movie: "MOVIE", tv: "TV", game: "GAME",
    } as const)[seedCategory];
    const writes = await Promise.allSettled(ranked.map(candidate => recordAtlasRelationship({
      sourceTitle: seedTitle,
      sourceCategory,
      sourceUrl: seedUrl,
      targetTitle: candidate.title,
      targetCategory: ({
        anime: "ANIME", manga: "MANGA", light_novel: "LIGHT_NOVEL",
        book: "BOOK", movie: "MOVIE", tv: "TV", game: "GAME",
      } as const)[candidate.category],
      targetUrl: candidate.url,
      relationshipType: "genre overlap",
      sourceKind: "recommendation",
      sourceLabel: "Genre overlap recommendation",
    })));
    for (const write of writes) {
      if (write.status === "rejected") logger.debug("Cross-media recommendation relationship was not saved", {
        reason: write.reason instanceof Error ? write.reason.message : "Unknown error",
      });
    }

    const embed = homeEmbed(
      "Cross-media matches · " + seedTitle,
      "Local matches are ranked by the number of shared provider-reported genres. This is a transparent metadata heuristic, not an AI score.",
    ).setURL(seedUrl);
    if (ranked.length) {
      embed.addFields({
        name: "Shared-genre matches",
        value: ranked.map((item, index) => {
          const label = item.url ? `[${item.title}](${item.url})` : item.title;
          return `**${index + 1}. ${item.category.replaceAll("_", " ")} · ${label}**\n${item.provider} · Shared genres: ${item.sharedGenres.join(", ")}`;
        }).join("\n\n").slice(0, 4_000),
        inline: false,
      });
    }
    if (providerRecommendations.length) {
      embed.addFields({
        name: "Provider-generated recommendations · separate source",
        value: providerRecommendations.slice(0, 5).map(item => {
          const title = this.recordTitle(item);
          const url = this.recordUrl(item);
          return `• ${url ? `[${title}](${url})` : title} · ${item.provider}`;
        }).join("\n").slice(0, 1_000),
        inline: false,
      });
    }
    if (!ranked.length && !providerRecommendations.length) {
      embed.setDescription("No comparable provider genre metadata or provider-generated recommendations were returned for this title.");
    }
    embed.setFooter({ text: "Sources: AniList · Google Books · TMDB · IGDB · No Novel Updates scraping or inferred adaptations" });
    await interaction.editReply({ content: "", embeds: [embed], components: [], allowedMentions: { parse: [] } });
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

  private async atlasAndRespond(
    interaction: ChatInputCommandInteraction,
    query: string,
    category: Category,
    filters: DiscoverFilters = {},
    targetTitle: string | null = null,
    targetCategory: string | null = null,
    targetUrl: string | null = null,
    relationshipFilter: string | null = null,
  ): Promise<void> {
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
    let collectionReleaseOrder:ReturnType<typeof tmdbCollectionReleaseOrder>=null;
    let collectionName:string|null=null;
    if(first.provider==="TMDB"&&first.category==="movie"){
      try{
        const collection=await this.tmdb.collectionForMovie(first.item.id);
        if(collection){
          collectionName=collection.name;
          collectionReleaseOrder=tmdbCollectionReleaseOrder(collection.items);
          const relations=collection.items
            .filter(item=>item.id!==first.item.id)
            .map(item=>({
              title:item.title,
              category:"MOVIE" as const,
              url:item.sourceUrl,
              relationshipType:"collection member",
            }));
          await recordProviderRelationships({
            sourceTitle:title,
            sourceCategory:"MOVIE",
            sourceUrl:this.recordUrl(first),
            sourceImageUrl:this.recordImage(first),
            sourceLabel:("TMDB collection membership · "+collection.name).slice(0,100),
            relations,
          });
        }
      }catch(error){
        logger.warn("TMDB collection relationships could not be indexed in Atlas",{
          reason:error instanceof Error?error.message:"Unknown error",
        });
      }
    }
    try{
      const matches=await this.fetchSearch(title,"all");
      const exactMatches=matches.filter(record=>
        record.category!==first.category
        &&normalizeAtlasTitle(this.recordTitle(record))===normalizeAtlasTitle(title)
        &&this.recordUrl(record)!==this.recordUrl(first)
      ).slice(0,12);
      await Promise.allSettled(exactMatches.map(record=>recordAtlasRelationship({
        sourceTitle:title,
        sourceCategory:mediaCategory,
        sourceUrl:this.recordUrl(first),
        sourceImageUrl:this.recordImage(first),
        targetTitle:this.recordTitle(record),
        targetCategory:record.category,
        targetUrl:this.recordUrl(record),
        targetImageUrl:this.recordImage(record),
        relationshipType:"exact-title match (unverified adaptation)",
        sourceKind:"recommendation",
        sourceLabel:"Cross-provider exact-title match; not a verified adaptation",
      })));
    }catch(error){
      logger.warn("Cross-provider exact-title Atlas enrichment failed",{
        reason:error instanceof Error?error.message:"Unknown error",
      });
    }
    const [providerRelationships, communityRelationships] = await Promise.all([
      findAtlasRelationships(interaction.guildId, title, mediaCategory, this.recordUrl(first), 20),
      findAtlasCommunityLinks(interaction.guildId, title, mediaCategory, this.recordUrl(first), first.provider === "AniList" ? String(first.item.id) : null, 20),
    ]);
    const rootUrl = this.recordUrl(first);
    const graph = await findAtlasGraph(
      interaction.guildId,
      { title, category: mediaCategory, url: rootUrl, imageUrl: this.recordImage(first) },
      { maxDepth: 3, maxNodes: 24, perNodeLimit: 8 },
    );
    const graphFilters = {
      ...(targetTitle && !targetCategory ? { query: targetTitle } : {}),
      ...(relationshipFilter ? { relationshipType: relationshipFilter } : {}),
    };
    const filteredGraph = filterAtlasGraph(graph, graphFilters);
    const selectedCommunity = filterAtlasRelations(communityRelationships, graphFilters);
    const relationships = [...filteredGraph.directRelationships, ...selectedCommunity].slice(0, 20);
    const path = targetTitle && targetCategory
      ? findAtlasPath(graph, { title: targetTitle, category: targetCategory, url: targetUrl })
      : null;
    const embed = toEmbed(first).setTitle(`Knowledge Atlas · ${title}`.slice(0,256))
      .setDescription("Provider-confirmed relationships are global, recommendations are explicitly unverified, and community links remain limited to their originating server.");
    embed.addFields({
      name: "Connected graph",
      value: filteredGraph.nodes.length + " nodes · " + filteredGraph.edges.length + " connections · up to 3 relationship steps"
        + (filteredGraph.truncated ? " · additional branches omitted by graph limits" : ""),
      inline: false,
    });
    if (targetTitle && targetCategory) {
      embed.addFields({
        name: "Shortest path · " + safeDisplay(targetTitle, 100),
        value: path
          ? path.edges.map((edge, index) => {
              const from = path.nodes[index]?.title ?? "Unknown";
              const to = path.nodes[index + 1]?.title ?? "Unknown";
              return safeDisplay(from, 90) + " — " + safeDisplay(edge.relationType, 60) + " → " + safeDisplay(to, 90)
                + " · " + safeDisplay(edge.sourceLabel, 60);
            }).join("\n").slice(0, 1024)
          : "No path was found within the bounded graph for the selected category and title.",
        inline: false,
      });
    } else if (targetTitle) {
      embed.addFields({
        name: "Atlas filter",
        value: "Matching " + filteredGraph.nodes.length + " nodes and " + filteredGraph.edges.length + " connections for “" + safeDisplay(targetTitle, 100) + "”.",
        inline: false,
      });
    }
    if (relationships.length) {
      for (const relation of relationships.slice(0,20)) {
        const label = relation.url ? `[${relation.title.slice(0,180)}](${relation.url})` : relation.title.slice(0,180);
        embed.addFields({name:`${relation.relationType} · ${relation.category}`.slice(0,256),
          value:`${label}\nSource: ${relation.source}`.slice(0,1024),inline:false});
      }
    } else {
      embed.addFields({name:"No recorded connections yet",value:"This provider has not supplied related-work edges for this title, and this server has not approved any community links yet.",inline:false});
    }
    if(first.provider==="AniList"){
      const order=aniListReleaseOrder(
        {title,url:first.item.siteUrl,startDate:first.item.startDate},
        first.item.relations,
      );
      if(order){
        embed.addFields({
          name:"AniList release order · not story chronology",
          value:order.map((item,index)=>(index+1)+". "+(item.url?"["+item.title+"]("+item.url+")":item.title)+" · "+item.date).join("\\n").slice(0,1024),
          inline:false,
        });
      }
    }
    if(collectionReleaseOrder){
      embed.addFields({
        name:("TMDB collection release order"+(collectionName?" · "+collectionName:"")+" · not story chronology").slice(0,256),
        value:collectionReleaseOrder.map((item,index)=>(index+1)+". "+(item.url?"["+item.title+"]("+item.url+")":item.title)+" · "+item.date).join("\\n").slice(0,1024),
        inline:false,
      });
    }
    embed.setFooter({text:"Knowledge Atlas · Provider provenance and guild-scoped community links"});
    let files: AttachmentBuilder[] = [];
    if (filteredGraph.nodes.length > 1 && filteredGraph.edges.length > 0) {
      try {
        const exported = await atlasExportFiles(title, mediaCategory, filteredGraph, "knowledge-atlas", path);
        embed.setImage(exported.image);
        files = exported.files;
      } catch (error) {
        logger.warn("Knowledge Atlas graph export could not be rendered", {
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
    if (targetTitle && targetCategory) {
      dashboardUrl.searchParams.set("atlas_target_title", targetTitle);
      dashboardUrl.searchParams.set("atlas_target_category", targetCategory);
      if (targetUrl) dashboardUrl.searchParams.set("atlas_target_url", targetUrl);
    }
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

  private recordImage(record: SearchRecord): string | null {
    if (record.provider === "AniList") return record.item.coverImage;
    if (record.provider === "Steam") return record.item.headerImage;
    return record.item.image;
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
        sourceImageUrl:record.item.coverImage,
        sourceLabel:"AniList provider relationships",
        relations:record.item.relations.map((relation) => ({
          title:relation.title,category:relation.category,url:relation.url,imageUrl:relation.image,relationshipType:relation.relation,
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
        this.webNovels.search(query).then(items => items.map(webNovelRecord)),
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
case "webnovel": {
if (/^\d+$/.test(query.trim()) || /^https?:\/\/www\.royalroad\.com\/fiction\/\d+/i.test(query.trim())) {
return [{ provider: "Royal Road", category: "webnovel", item: await this.royalRoad.getFiction(query) }];
}
return (await this.webNovels.search(query)).map(webNovelRecord);
}
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
        case "webnovel": return [];
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
      case "webnovel": return [];
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
  private airingPage(sessionId:string,session:{ownerId:string;filters:AniListAiringFilters;entries:AniListAiring[];page:number;timeout:NodeJS.Timeout}){
    const totalPages=Math.max(1,Math.ceil(session.entries.length/5));
    const visible=session.entries.slice(session.page*5,session.page*5+5);
    const fields=visible.map(entry=>({
      name:(cleanText(entry.title,180)+" · Episode "+entry.episode).slice(0,256),
      value:"Your local time: <t:"+entry.airingAt+":F> · <t:"+entry.airingAt+":R>\nUTC: "+new Date(entry.airingAt*1000).toISOString().replace("T"," ").slice(0,16)
        +"\n"+[entry.format,entry.status,entry.season?(entry.season+" "+(entry.seasonYear??"")):null].filter(Boolean).join(" · ").slice(0,300),
      inline:false,
    }));
    const embed=homeEmbed(
      "Upcoming anime episodes",
      session.entries.length
        ? "AniList schedule · "+session.entries.length+" matching episode(s). Times are provided in UTC; Discord also displays them in your local timezone."
        : "AniList returned no upcoming episodes for these filters. Try another title, season or date window.",
      fields,
    ).setFooter({text:"AniList · Page "+(session.page+1)+"/"+totalPages+" · Schedule may change"});
    const controls=new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("discover:airing-page:"+sessionId+":"+Math.max(0,session.page-1)).setLabel("Previous").setStyle(ButtonStyle.Secondary).setDisabled(session.page===0),
      new ButtonBuilder().setCustomId("discover:airing-page:"+sessionId+":"+Math.min(totalPages-1,session.page+1)).setLabel("Next").setStyle(ButtonStyle.Secondary).setDisabled(session.page>=totalPages-1),
      new ButtonBuilder().setCustomId("discover:airing-refresh:"+sessionId).setLabel("Refresh").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("discover:home").setLabel("Discover").setStyle(ButtonStyle.Secondary),
    );
    return {content:"Airing schedule",embeds:[embed],components:[controls],allowedMentions:{parse:[]}};
  }
  private comparisonSelectionPanel(sessionId:string,session:{ownerId:string;sides:Array<{category:MediaComparisonCategory;title:string;results:SearchRecord[];selected:number}>;timeout:NodeJS.Timeout}){
    const fields=session.sides.map((side,index)=>{
      const selected=side.results[side.selected]!;
      return{
        name:(index+1)+". "+categoryLabel(side.category)+" · "+side.title,
        value:"Selected: "+this.recordTitle(selected)+"\nProvider: "+selected.provider+"\n"+this.recordUrl(selected),
        inline:false,
      };
    });
    const embed=homeEmbed(
      "Choose comparison results",
      "Select the exact provider result for each title, then compare. Search results remain attributed to their original source.",
      fields,
    );
    const components:Array<ActionRowBuilder<StringSelectMenuBuilder|ButtonBuilder>>=[];
    for(let index=0;index<session.sides.length;index++){
      const side=session.sides[index]!;
      const select=new StringSelectMenuBuilder()
        .setCustomId("discover:compare-select:"+sessionId+":"+index)
        .setPlaceholder("Choose "+(index+1)+". "+side.title.slice(0,65))
        .addOptions(side.results.slice(0,25).map((record,resultIndex)=>({
          label:this.recordTitle(record).slice(0,100),
          description:record.provider.slice(0,100),
          value:String(resultIndex),
          default:resultIndex===side.selected,
        })));
      components.push(new ActionRowBuilder<StringSelectMenuBuilder|ButtonBuilder>().addComponents(select));
    }
    components.push(new ActionRowBuilder<StringSelectMenuBuilder|ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("discover:compare-submit:"+sessionId).setLabel("Compare selected titles").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("discover:home").setLabel("Cancel").setStyle(ButtonStyle.Secondary),
    ));
    return {content:"Select each title",embeds:[embed],components,allowedMentions:{parse:[]}};
  }

}

import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  ModalBuilder,
  MessageFlags,
  SlashCommandBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import type { BotConfig } from "../config.js";
import type { BotCommand } from "./types.js";
import { AniListClient, type AniListMedia, type MediaType } from "../providers/anilist.js";

function titleFor(media: AniListMedia): string {
  return media.title.english || media.title.romaji || media.title.native || "Untitled media";
}

function cleanDescription(value: string | null): string {
  if (!value) return "No description supplied by AniList.";
  const cleaned = value
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.length > 350 ? `${cleaned.slice(0, 347).trimEnd()}…` : cleaned || "No description supplied by AniList.";
}

function mediaEmbed(media: AniListMedia): EmbedBuilder {
  const countLabel = media.type === "ANIME" ? "Episodes" : "Chapters";
  const count = media.type === "ANIME" ? media.episodes : media.chapters;
  const fields = [
    { name: "Format", value: media.format?.replaceAll("_", " ") || "Unknown", inline: true },
    { name: "Status", value: media.status?.replaceAll("_", " ") || "Unknown", inline: true },
    { name: countLabel, value: count == null ? "Unknown" : String(count), inline: true },
    ...(media.type === "MANGA" ? [{ name: "Volumes", value: media.volumes == null ? "Unknown" : String(media.volumes), inline: true }] : []),
    { name: "Score", value: media.averageScore == null ? "Not rated" : `${media.averageScore}/100`, inline: true },
  ];

  const embed = new EmbedBuilder()
    .setTitle(titleFor(media).slice(0, 256))
    .setURL(media.siteUrl)
    .setDescription(cleanDescription(media.description))
    .addFields(fields)
    .setFooter({ text: `AniList · ${media.type === "ANIME" ? "Anime" : "Manga"}${media.startDate?.year ? ` · ${media.startDate.year}` : ""}` });

  if (media.coverImage?.large) embed.setThumbnail(media.coverImage.large);
  if (media.genres.length > 0) {
    embed.addFields({ name: "Genres", value: media.genres.slice(0, 6).join(" · ").slice(0, 1024) || "Unknown" });
  }
  return embed;
}

function mediaResults(media: AniListMedia[], type: MediaType): EmbedBuilder[] {
  if (media.length === 0) {
    return [new EmbedBuilder()
      .setTitle("No results found")
      .setDescription(`AniList did not return any ${type === "ANIME" ? "anime" : "manga"} matching that request.`)
      .setFooter({ text: "AniList" })];
  }
  return media.map(mediaEmbed);
}

function searchModal(type: MediaType): ModalBuilder {
  const input = new TextInputBuilder()
    .setCustomId("query")
    .setLabel(type === "ANIME" ? "Anime title" : "Manga title")
    .setPlaceholder("Enter a title to search")
    .setStyle(TextInputStyle.Short)
    .setMinLength(2)
    .setMaxLength(100)
    .setRequired(true);

  return new ModalBuilder()
    .setCustomId(`discover:search:${type}`)
    .setTitle(`Search ${type === "ANIME" ? "anime" : "manga"}`)
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(input));
}

function homePanel(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const embed = new EmbedBuilder()
    .setTitle("Media Discovery")
    .setDescription("Search AniList or explore its current trending titles. More providers, comparisons, franchise exploration, and the Knowledge Atlas will be migrated into this space in later v3 stages.")
    .addFields(
      { name: "Anime", value: "Search titles and browse trending anime.", inline: true },
      { name: "Manga", value: "Search titles and browse trending manga.", inline: true },
    )
    .setFooter({ text: "Lemegeton v3 · Media Intelligence" });

  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("discover:search:ANIME").setLabel("Search anime").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("discover:trending:ANIME").setLabel("Trending anime").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("discover:search:MANGA").setLabel("Search manga").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("discover:trending:MANGA").setLabel("Trending manga").setStyle(ButtonStyle.Secondary),
  );
  return { embeds: [embed], components: [row] };
}

async function deliverSearch(
  interaction: ChatInputCommandInteraction | ModalSubmitInteraction,
  client: AniListClient,
  query: string,
  type: MediaType,
): Promise<void> {
  await interaction.deferReply({ flags: MessageFlags.Ephemeral });
  const results = await client.searchMedia(query, type);
  await interaction.editReply({ embeds: mediaResults(results, type) });
}

export function createDiscoverCommand(config: BotConfig): BotCommand {
  const anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);

  return {
    data: new SlashCommandBuilder()
      .setName("discover")
      .setDescription("Search and explore anime and manga")
      .addStringOption((option) => option
        .setName("query")
        .setDescription("Title to search for")
        .setMinLength(2)
        .setMaxLength(100)
        .setRequired(false))
      .addStringOption((option) => option
        .setName("type")
        .setDescription("Media category")
        .addChoices(
          { name: "Anime", value: "ANIME" },
          { name: "Manga", value: "MANGA" },
        )
        .setRequired(false)),

    async execute(interaction: ChatInputCommandInteraction): Promise<void> {
      const query = interaction.options.getString("query")?.trim();
      if (!query) {
        await interaction.reply({ ...homePanel(), flags: MessageFlags.Ephemeral });
        return;
      }

      const type = (interaction.options.getString("type") || "ANIME") as MediaType;
      await deliverSearch(interaction, anilist, query, type);
    },

    async handleButton(interaction: ButtonInteraction): Promise<boolean> {
      const [, action, rawType] = interaction.customId.split(":");
      if (rawType !== "ANIME" && rawType !== "MANGA") return false;
      const type: MediaType = rawType;

      if (action === "search") {
        await interaction.showModal(searchModal(type));
        return true;
      }

      if (action === "trending") {
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        const results = await anilist.getTrending(type);
        await interaction.editReply({ embeds: mediaResults(results, type) });
        return true;
      }

      return false;
    },

    async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
      const [, action, rawType] = interaction.customId.split(":");
      if (action !== "search" || (rawType !== "ANIME" && rawType !== "MANGA")) return false;
      await deliverSearch(interaction, anilist, interaction.fields.getTextInputValue("query"), rawType);
      return true;
    },
  };
}

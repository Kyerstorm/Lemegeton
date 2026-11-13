import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelSelectMenuBuilder,
  ChannelType,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  PermissionsBitField,
  RoleSelectMenuBuilder,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type AutocompleteInteraction,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ChannelSelectMenuInteraction,
  type GuildMember,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
  type RoleSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import { homeEmbed } from "../../helpers/runtime/discord.js";
import {
  ARCHIVE_CATEGORIES,
  searchArchiveTags,
  finishArchiveUpload,
  getArchiveEntry,
  getArchiveSettings,
  getPanelOfTheDay,
  getLastArchiveCategory,
  getOwnSubmissions,
  isArchiveCategory,
  listArchiveEntries,
  deleteArchiveEntry,
  updateArchiveEntry,
  saveArchiveSettings,
  saveArchiveChannelSetting,
  saveArchiveModeratorRole,
  rememberArchiveCategory,
  submitArchiveEntry,
  parsePanelChapterCaption,
  parseAniListMangaReference,
  type ArchiveCategory,
  type ArchiveEntry,
  type ArchiveVisibility
} from "../../helpers/archive/archive.js";
import {
  canModerateArchive,
  isGlobalArchiveModerator,
  listPendingEntries,
  moderateArchiveEntry,
  addArchiveReport,
  listArchiveReports,
  reviewArchiveReport
} from "../../helpers/archive/archive-moderation.js";
import {
  addEntryToCollection,
  addEntryToTrail,
  addCollectionCollaborator,
  removeCollectionCollaborator,
  removeEntryFromCollection,
  getArchiveTrailSteps,
  listArchiveCollections,
  listArchiveTrails,
  getCollectionItems,
  saveArchiveCollection,
  saveArchiveTrail
} from "../../helpers/archive/archive-collections.js";
import { query, queryOne } from "../../database.js";
import { deleteArchiveAsset, resolveLegacyArchiveAttachmentUrl, signedArchiveAssetUrl, storeArchiveUpload, classifyArchiveUpload } from "../../helpers/media/media-storage.js";
import { cleanText, isGuildManager, isValidHttpsUrl, safeDisplay } from "../../helpers/security/security.js";
import { logger } from "../../helpers/runtime/logger.js";

const ACTIONS = [
  { name: "Browse approved entries", value: "browse" },
  { name: "Panel of the Day", value: "panel-of-the-day" },
  { name: "Search the archive", value: "search" },
  { name: "Submit a contribution", value: "submit" },
  { name: "My submissions", value: "mine" },
  { name: "Edit my submission", value: "edit" },
  { name: "Delete a submission", value: "delete" },
  { name: "Report an entry", value: "report" },
  { name: "Review submissions", value: "review" },
  { name: "Review reports", value: "report-review" },
  { name: "Configure the archive", value: "configure" },
  { name: "Create a collection", value: "collection-create" },
  { name: "Add to a collection", value: "collection-add" },
  { name: "Remove from a collection", value: "collection-remove" },
  { name: "Invite collection collaborator", value: "collection-invite" },
  { name: "Remove collection collaborator", value: "collection-remove-member" },
  { name: "Browse collections", value: "collection-list" },
  { name: "Create an Archive Trail", value: "trail-create" },
  { name: "Add to a Trail", value: "trail-add" },
  { name: "Browse Archive Trails", value: "trail-list" },
  { name: "Open an Archive Trail", value: "trail-open" },
  { name: "Finish an upload", value: "finish-upload" },
] as const;

const MEDIA_TYPES = [
  { name: "Anime", value: "Anime" },
  { name: "Manga / manhwa / manhua", value: "Manga" },
  { name: "Light novel", value: "Light novel" },
  { name: "Webnovel", value: "Webnovel" },
  { name: "Book", value: "Book" },
  { name: "Film", value: "Movie" },
  { name: "Television", value: "TV" },
  { name: "Video game", value: "Game" },
  { name: "Other", value: "Other" },
];

function categoryLabel(category: ArchiveCategory): string {
  return ARCHIVE_CATEGORIES.find((item) => item.value === category)?.label ?? category;
}

function spoilerContent(value: string, spoiler: boolean): string {
  return spoiler ? `||${value}||` : value;
}

function entryEmbed(entry: ArchiveEntry): EmbedBuilder {
  const tags = Array.isArray(entry.tags) ? entry.tags : [];
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle(`#${entry.id} · ${safeDisplay(entry.title, 220)}`)
    .setDescription(spoilerContent(entry.content, entry.spoiler).slice(0, 3_500))
    .addFields(
      { name: "Category", value: categoryLabel(entry.archive_type), inline: true },
      { name: "Media", value: entry.media_type || "Other", inline: true },
      { name: "Visibility", value: entry.visibility === "global" ? "Global" : "This server", inline: true },
      { name: "Contributor", value: `<@${entry.created_by}>`, inline: true },
    )
    .setFooter({ text: "Community Archive · Approved, attributed contribution" });
  if(entry.chapter_number)embed.addFields({name:"Chapter",value:entry.chapter_number,inline:true});
  if (entry.source_title) embed.addFields({ name: "Work / source", value: safeDisplay(entry.source_title, 250), inline: true });
  if (entry.creator) embed.addFields({ name: "Original creator", value: safeDisplay(entry.creator, 250), inline: true });
  if (entry.source_url) embed.addFields({ name: "Source", value: `[Open original source](${entry.source_url})`, inline: false });
  if (entry.archive_type === "panels" && entry.linked_media_provider === "AniList" && entry.linked_media_id && /^\d{1,12}$/.test(entry.linked_media_id)) {
    embed.addFields({ name: "Linked media", value: `[Open AniList manga](https://anilist.co/manga/${entry.linked_media_id})`, inline: false });
  }
  if (tags.length) embed.addFields({ name: "Tags", value: tags.map((tag) => safeDisplay(tag, 40)).join(" · ").slice(0, 900), inline: false });
  return embed;
}

function submitModal(category: ArchiveCategory, visibility: ArchiveVisibility): ModalBuilder {
  const title = new TextInputBuilder().setCustomId("title").setLabel("Entry title").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(200);
  const content = new TextInputBuilder().setCustomId("content").setLabel("Description / contribution").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(3_000);
  const sourceLabel = category === "quotes" ? "Source work title" : category === "fanworks" ? "HTTPS source link" : category === "soundtracks" ? "HTTPS music link (optional)" : "Work / source (optional)";
  const source = new TextInputBuilder().setCustomId("source").setLabel(sourceLabel).setStyle(TextInputStyle.Short).setRequired(category === "quotes" || category === "fanworks").setMaxLength(1_000);
  const creator = new TextInputBuilder().setCustomId("creator").setLabel(category === "fanworks" ? "Original creator / handle" : "Creator attribution (optional)").setStyle(TextInputStyle.Short).setRequired(category === "fanworks").setMaxLength(200);
  const tags = new TextInputBuilder().setCustomId("tags").setLabel("Tags (comma separated, optional)").setStyle(TextInputStyle.Short).setRequired(false).setMaxLength(400);
  // Keep the modal within Discord's five text-input limit. Source URL and media type remain available
  // through the slash-command form, while the home panel presents the quick submission path.
  return new ModalBuilder()
    .setCustomId(`archive:submit:${category}:${visibility}`)
    .setTitle(`Submit · ${categoryLabel(category)}`)
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(title),
      new ActionRowBuilder<TextInputBuilder>().addComponents(content),
      new ActionRowBuilder<TextInputBuilder>().addComponents(source),
      new ActionRowBuilder<TextInputBuilder>().addComponents(creator),
      new ActionRowBuilder<TextInputBuilder>().addComponents(tags),
    );
}

function quickPanelModal(): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("archive:quick-panel")
    .setTitle("Quick submit · Manga Panel")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("title").setLabel("Panel title").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(200),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("chapter_caption").setLabel("Chapter number and optional caption").setPlaceholder("Chapter 12 — Final battle").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(500),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("source_url").setLabel("AniList manga ID or HTTPS URL (optional)").setStyle(TextInputStyle.Short).setRequired(false).setMaxLength(500),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("tags").setLabel("Tags (comma separated, optional)").setStyle(TextInputStyle.Short).setRequired(false).setMaxLength(400),
      ),
    );
}

function archiveUsualPrompt(category: ArchiveCategory): {
  embeds: EmbedBuilder[];
  components: ActionRowBuilder<ButtonBuilder>[];
} {
  const embed = homeEmbed(
    "Welcome back to the Archive",
    "Your last contribution was **" + categoryLabel(category) + "**. Open that submission flow again, or choose something else?",
  );
  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("archive:usual:yes:" + category).setLabel("Yes · " + categoryLabel(category)).setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId("archive:usual:no").setLabel("Something else").setStyle(ButtonStyle.Secondary),
  );
  return { embeds: [embed], components: [row] };
}

function reportModal(entryId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(`archive:report:${entryId}`)
    .setTitle("Report Archive entry")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("reason").setLabel("What should moderators review?").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(500),
    ));
}

function configureModal(categories: string[], uploadTypes: string[]): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("archive:configure")
    .setTitle("Archive server settings")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("categories").setLabel("Enabled categories (comma separated)").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(300).setValue(categories.join(",")),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("uploads").setLabel("Accepted uploads: image, audio, video").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(40).setValue(uploadTypes.join(",")),
      ),
    );
}

function archiveHome(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const embed = homeEmbed(
    "Community Archive",
    "A server-owned library of attributed contributions. Manga panels are one category alongside quotes, fanworks, moodboards, soundtracks, scenes, recommendations and theories. Approved global entries are shown only when their contributors explicitly opted into global visibility.",
    ARCHIVE_CATEGORIES.slice(0, 4).map((category) => ({ name: category.emoji + " " + category.label, value: "A searchable Archive category.", inline: true })),
  );
  const row1 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("archive:browse").setLabel("Browse").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("archive:search").setLabel("Search").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("archive:submit").setLabel("Contribute").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId("archive:mine").setLabel("My submissions").setStyle(ButtonStyle.Secondary),
  );
  const row2 = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("archive:collections").setLabel("Collections").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("archive:trails").setLabel("Archive Trails").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("archive:report").setLabel("Report an entry").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("archive:review").setLabel("Review queue").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("archive:configure").setLabel("Configure").setStyle(ButtonStyle.Secondary),
  );
  return { embeds: [embed], components: [row1, row2] };
}

function categorySelect(customId: string): ActionRowBuilder<StringSelectMenuBuilder> {
  return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId(customId)
      .setPlaceholder("Choose an Archive category")
      .addOptions(ARCHIVE_CATEGORIES.map((category) => ({
        label: category.label,
        value: category.value,
        emoji: category.emoji,
      }))),
  );
}

function entrySelect(entries: ArchiveEntry[]): ActionRowBuilder<StringSelectMenuBuilder> {
  return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId("archive:open-entry")
      .setPlaceholder("Open an Archive contribution")
      .addOptions(entries.slice(0, 25).map((entry) => ({
        label: `#${entry.id} · ${entry.title}`.slice(0, 100),
        value: entry.id,
        description: categoryLabel(entry.archive_type).slice(0, 100),
      }))),
  );
}

export class ArchiveCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("archive")
    .setDescription("Browse, contribute to and curate the Community Archive")
    .addStringOption((option) => option.setName("action").setDescription("Archive action").addChoices(...ACTIONS))
    .addStringOption((option) => option.setName("category").setDescription("Contribution category").addChoices(
      ...ARCHIVE_CATEGORIES.map((category) => ({ name: category.label, value: category.value })),
    ))
    .addStringOption((option) => option.setName("title").setDescription("Entry or collection title").setMaxLength(200))
    .addStringOption((option) => option.setName("content").setDescription("Description or contribution").setMaxLength(3_000))
    .addStringOption((option) => option.setName("chapter_caption").setDescription("For Manga Panels: Chapter 12 — caption, or N/A").setMaxLength(500))
    .addStringOption((option) => option.setName("source_title").setDescription("Linked work / source title").setMaxLength(200))
    .addStringOption((option) => option.setName("creator").setDescription("Original creator / contributor").setMaxLength(200))
    .addStringOption((option) => option.setName("source_url").setDescription("HTTPS source URL").setMaxLength(1_000))
    .addStringOption((option) => option.setName("media_type").setDescription("Linked media category").addChoices(...MEDIA_TYPES))
    .addStringOption((option) => option.setName("tags").setDescription("Search and select one or more tags").setMaxLength(400).setAutocomplete(true))
    .addStringOption((option) => option.setName("visibility").setDescription("Publication scope").addChoices(
      { name: "This server", value: "server" },
      { name: "Global (explicit sharing)", value: "global" },
    ))
    .addBooleanOption((option) => option.setName("spoiler").setDescription("Mark the content as a spoiler"))
    .addStringOption((option) => option.setName("keyword").setDescription("Search phrase").setMaxLength(100))
    .addStringOption((option) => option.setName("entry_id").setDescription("Archive entry ID"))
    .addStringOption((option) => option.setName("decision").setDescription("Review decision").addChoices(
      { name: "Approve", value: "approve" },
      { name: "Reject", value: "reject" },
      { name: "Remove", value: "remove" },
      { name: "Dismiss report", value: "dismiss" },
    ))
    .addStringOption((option) => option.setName("reason").setDescription("Report or moderation reason").setMaxLength(500))
    .addAttachmentOption((option) => option.setName("file").setDescription("Optional media upload (private storage)"))
    .addStringOption((option) => option.setName("collection_id").setDescription("Collection ID"))
    .addStringOption((option) => option.setName("trail_id").setDescription("Archive Trail ID"))
    .addStringOption((option) => option.setName("note").setDescription("Curator annotation").setMaxLength(500))
    .addStringOption((option) => option.setName("report_id").setDescription("Archive report ID"))
    .addStringOption((option) => option.setName("member_id").setDescription("Discord member ID for collection collaboration"))
    .addStringOption((option) => option.setName("collaboration_role").setDescription("Collection collaborator permission").addChoices(
      { name: "Editor", value: "editor" },
      { name: "Contributor", value: "contributor" },
    ));

  async handleAutocomplete(interaction: AutocompleteInteraction): Promise<void> {
    const focused = interaction.options.getFocused(true);
    if (focused.name !== "tags") {
      await interaction.respond([]);
      return;
    }
    const parts = String(focused.value).split(",");
    const query = parts.pop()?.trim() ?? "";
    const selected = parts.map((tag) => tag.trim()).filter(Boolean);
    const prefix = selected.length ? `${selected.join(", ")}, ` : "";
    const choices = searchArchiveTags(query, selected)
      .filter((tag) => prefix.length + tag.length <= 100)
      .map((tag) => ({ name: tag, value: `${prefix}${tag}` }));
    await interaction.respond(choices);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "The Community Archive is server-scoped.", flags: MessageFlags.Ephemeral });
      return;
    }
    const action = interaction.options.getString("action") ?? "home";
    const guildId = interaction.guildId;
    const userId = interaction.user.id;
    try {
      switch (action) {
        case "home": {
          const [previous, archiveSettings] = await Promise.all([
            getLastArchiveCategory(guildId, userId),
            getArchiveSettings(guildId),
          ]);
          const usual = previous && archiveSettings.enabledCategories.includes(previous) ? previous : null;
          await interaction.reply({
            ...(usual ? archiveUsualPrompt(usual) : archiveHome()),
            flags: MessageFlags.Ephemeral,
          });
          return;
        }
        case "browse": await this.browse(interaction, interaction.options.getString("category") as ArchiveCategory | null); return;
        case "panel-of-the-day": await this.showPanelOfTheDay(interaction); return;
        case "search": {
          const keyword = interaction.options.getString("keyword") ?? "";
          const entries = await listArchiveEntries(guildId, interaction.options.getString("category") as ArchiveCategory | undefined, keyword, 0, 5);
          await this.presentEntries(interaction, entries, keyword ? `Search · ${keyword}` : "Recent approved entries");
          return;
        }
        case "submit": {
          const category = interaction.options.getString("category") as ArchiveCategory | null;
          const title = interaction.options.getString("title");
          const content = interaction.options.getString("content");
          if (!category || !isArchiveCategory(category)) throw new Error("Choose an Archive category.");
          if (!title || (category !== "panels" && !content)) {
            await interaction.reply({
              content: "Choose a category and fill in the required details. Manga Panels also need a chapter caption and image attachment.",
              components: [categorySelect("archive:submit-category")],
              flags: MessageFlags.Ephemeral,
            });
            return;
          }
          await this.submitFromCommand(interaction, category);
          return;
        }
        case "mine": await this.showMine(interaction); return;
        case "edit": {
          const entryId = interaction.options.getString("entry_id");
          if (!entryId) throw new Error("Provide entry_id.");
          const chapterInput = interaction.options.getString("chapter_caption");
          const chapterEdit = chapterInput !== null ? parsePanelChapterCaption(chapterInput) : null;
          await updateArchiveEntry(guildId, userId, entryId, {
            title: interaction.options.getString("title") ?? undefined,
            content: chapterEdit?.caption ?? interaction.options.getString("content") ?? undefined,
            sourceTitle: interaction.options.getString("source_title") ?? undefined,
            creator: interaction.options.getString("creator") ?? undefined,
            sourceUrl: interaction.options.getString("source_url") ?? undefined,
            tags: interaction.options.getString("tags")?.split(","),
            spoiler: interaction.options.getBoolean("spoiler") ?? undefined,
            chapterNumber: chapterEdit?.chapterNumber,
          });
          await interaction.reply({ content: `Entry #${entryId} updated. Previously approved entries have returned to moderation review.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "delete": {
          const entryId = interaction.options.getString("entry_id");
          if (!entryId) throw new Error("Provide entry_id.");
          const global = interaction.options.getString("visibility") === "global";
          if (global && !isGlobalArchiveModerator(userId)) {
            throw new Error("Only configured global Archive moderators can delete global entries.");
          }
          const entry = await getArchiveEntry(guildId, entryId, true, global);
          if (!entry) throw new Error("That Archive entry was not found in the selected visibility scope.");
          const member = await interaction.guild!.members.fetch(userId);
          const canModerate = await canModerateArchive(member, guildId, global ? "global" : "server");
          await deleteArchiveEntry(guildId, userId, entryId, canModerate, global, interaction.client);
          await interaction.reply({ content: `Entry #${entryId} was deleted.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "report": {
          const entryId = interaction.options.getString("entry_id");
          const reason = interaction.options.getString("reason");
          if (!entryId || !reason) throw new Error("Provide both entry_id and a reason when reporting.");
          await addArchiveReport(guildId, userId, entryId, reason);
          await interaction.reply({ content: "Your report has been sent to this server's Archive moderators.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "review": await this.showReviewQueue(interaction); return;
        case "report-review": {
          const reportId = interaction.options.getString("report_id");
          const decision = interaction.options.getString("decision");
          const visibility = interaction.options.getString("visibility") ?? "server";
          const reason = interaction.options.getString("reason") ?? "";
          if (!reportId || (decision !== "dismiss" && decision !== "remove")) throw new Error("Provide report_id and decision (dismiss/remove).");
          const global = visibility === "global";
          if (global) {
            if (!isGlobalArchiveModerator(userId)) throw new Error("Only configured global Archive moderators can review global reports.");
          } else {
            const member = await interaction.guild!.members.fetch(userId);
            if (!await canModerateArchive(member, guildId, "server")) throw new Error("Archive moderation permission is required.");
          }
          await reviewArchiveReport(guildId, reportId, userId, decision, reason, global);
          await interaction.reply({ content: decision === "remove" ? "Report actioned and entry removed." : "Report dismissed.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "configure": await this.configure(interaction); return;
        case "collection-create": {
          const title = interaction.options.getString("title");
          if (!title) throw new Error("Provide a collection title.");
          const visibility = (interaction.options.getString("visibility") ?? "server") as ArchiveVisibility;
          if (visibility === "global" && !isGlobalArchiveModerator(userId)) {
            throw new Error("Global collections can only be published by configured global Archive moderators. You can create a server-only collection.");
          }
          const collectionId = await saveArchiveCollection(guildId, userId, title, interaction.options.getString("content") ?? "", visibility);
          await interaction.reply({ content: `Created collection **${safeDisplay(title)}** (#${collectionId}). Add approved entries with /archive action:collection-add collection_id:${collectionId} entry_id:...`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "collection-add": {
          const collectionId = interaction.options.getString("collection_id");
          const entryId = interaction.options.getString("entry_id");
          if (!collectionId || !entryId) throw new Error("Provide collection_id and entry_id.");
          await addEntryToCollection(guildId, userId, collectionId, entryId, interaction.options.getString("note") ?? "");
          await interaction.reply({ content: "Added the contribution to the collection. Its original contributor attribution is preserved.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "collection-remove": {
          const collectionId = interaction.options.getString("collection_id");
          const entryId = interaction.options.getString("entry_id");
          if (!collectionId || !entryId) throw new Error("Provide collection_id and entry_id.");
          await removeEntryFromCollection(guildId, userId, collectionId, entryId);
          await interaction.reply({ content: "Removed that entry from the collection.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "collection-invite": {
          const collectionId = interaction.options.getString("collection_id");
          const memberId = interaction.options.getString("member_id");
          const role = interaction.options.getString("collaboration_role") as "editor" | "contributor" | null;
          if (!collectionId || !memberId || !/^\\d{17,20}$/.test(memberId) || !role) throw new Error("Provide collection_id, a valid member_id and role.");
          const member = await interaction.guild!.members.fetch(memberId).catch(() => null);
          if (!member) throw new Error("That member is not in this server.");
          await addCollectionCollaborator(guildId, userId, collectionId, memberId, role);
          await interaction.reply({ content: `Added <@${memberId}> to the collection as ${role}.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "collection-remove-member": {
          const collectionId = interaction.options.getString("collection_id");
          const memberId = interaction.options.getString("member_id");
          if (!collectionId || !memberId || !/^\\d{17,20}$/.test(memberId)) throw new Error("Provide collection_id and a valid member_id.");
          await removeCollectionCollaborator(guildId, userId, collectionId, memberId);
          await interaction.reply({ content: `Removed <@${memberId}> from the collection.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "collection-list": await this.showCollections(interaction); return;
        case "trail-create": {
          const title = interaction.options.getString("title");
          if (!title) throw new Error("Provide a Trail title.");
          const visibility = (interaction.options.getString("visibility") ?? "server") as ArchiveVisibility;
          if (visibility === "global" && !isGlobalArchiveModerator(userId)) {
            throw new Error("Global Trails can only be created by configured global Archive moderators.");
          }
          const id = await saveArchiveTrail(guildId, userId, title, interaction.options.getString("content") ?? "", visibility);
          await interaction.reply({ content: `Created Archive Trail #${id}. Add approved entries with /archive action:trail-add trail_id:${id} entry_id:...`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "trail-add": {
          const trailId = interaction.options.getString("trail_id");
          const entryId = interaction.options.getString("entry_id");
          if (!trailId || !entryId) throw new Error("Provide trail_id and entry_id.");
          await addEntryToTrail(guildId, userId, trailId, entryId, interaction.options.getString("note") ?? "");
          await interaction.reply({ content: "Added the contribution to the Trail. Entry visibility will be checked again when the Trail is opened.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "trail-list": await this.showTrails(interaction); return;
        case "trail-open": {
          const trailId = interaction.options.getString("trail_id");
          if (!trailId) throw new Error("Provide trail_id.");
          await this.openTrail(interaction, trailId);
          return;
        }
        case "finish-upload": {
          const entryId = interaction.options.getString("entry_id");
          if (!entryId) throw new Error("Provide the pending submission's entry_id.");
          await finishArchiveUpload(guildId, userId, entryId);
          const entry=await getArchiveEntry(guildId,entryId,true);
          const notified=entry?await this.notifyModerationChannel(
            interaction.client,guildId,entryId,entry.title,entry.archive_type,entry.visibility,entry.content,entry.source_title??undefined,entry.source_url??undefined,
          ):false;
          await interaction.reply({
            content:`Archive submission #${entryId} is now awaiting moderator review.${notified?" Moderators have been notified.":" Moderators can review it from /archive → Review queue."}`,
            flags:MessageFlags.Ephemeral,
          });
          return;
        }
        default: throw new Error("That Archive action is not available.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The Archive could not complete that action.";
      const issueHash = await createInteractionIssueLog(interaction, "/archive", error);
      const response = issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message;
      if (interaction.deferred || interaction.replied) await interaction.followUp({ content: response, flags: MessageFlags.Ephemeral });
      else await interaction.reply({ content: response, flags: MessageFlags.Ephemeral });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, value, scope] = interaction.customId.split(":");
    if (action === "usual") {
      if (value === "no") {
        await interaction.reply({ ...archiveHome(), flags: MessageFlags.Ephemeral });
        return true;
      }
      if (value !== "yes" || !scope || !isArchiveCategory(scope)) return false;
      await interaction.showModal(scope === "panels" ? quickPanelModal() : submitModal(scope,"server"));
      return true;
    }
    if (action === "configure-clear-moderator-role") {
      if (!isGuildManager(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to change Archive settings.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await saveArchiveModeratorRole(interaction.guildId, interaction.user.id, null);
      await interaction.reply({content:"The Archive moderator role was cleared.",flags:MessageFlags.Ephemeral});
      return true;
    }
    if (action === "configure-types" || action === "configure-clear-upload" || action === "configure-clear-moderation") {
      if (!isGuildManager(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to change Archive settings.",flags:MessageFlags.Ephemeral});
        return true;
      }
      if (action === "configure-types") {
        const settings=await getArchiveSettings(interaction.guildId);
        await interaction.showModal(configureModal(settings.enabledCategories,settings.uploadTypes));
        return true;
      }
      const kind=action==="configure-clear-upload"?"upload":"moderation";
      await saveArchiveChannelSetting(interaction.guildId,interaction.user.id,kind,null);
      await interaction.reply({content:kind==="upload"?"The Archive upload channel was cleared.":"The Archive moderation channel was cleared.",flags:MessageFlags.Ephemeral});
      return true;
    }
    if (action === "approve" || action === "reject") {
      if (!value || (scope !== "server" && scope !== "global")) return false;
      const member = await interaction.guild!.members.fetch(interaction.user.id);
      const visibility = scope as ArchiveVisibility;
      if (!await canModerateArchive(member, interaction.guildId, visibility)) {
        await interaction.reply({ content: "You do not have moderation permission for this Archive scope.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await moderateArchiveEntry(interaction.guildId, interaction.user.id, value, action === "approve" ? "approve" : "reject", "Reviewed from the Archive moderation panel.", visibility === "global");
      await interaction.reply({ content: action === "approve" ? "Archive submission approved." : "Archive submission rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if ((action === "report-dismiss" || action === "report-remove") && value && (scope === "server" || scope === "global")) {
      const member = await interaction.guild!.members.fetch(interaction.user.id);
      const global = scope === "global";
      if (global ? !isGlobalArchiveModerator(interaction.user.id) : !await canModerateArchive(member, interaction.guildId, "server")) {
        await interaction.reply({ content: "You do not have permission to review reports in this scope.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await reviewArchiveReport(interaction.guildId, value, interaction.user.id, action === "report-remove" ? "remove" : "dismiss", "Reviewed from the Archive report queue.", global);
      await interaction.reply({ content: action === "report-remove" ? "The reported entry was removed." : "The report was dismissed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    switch (action) {
      case "browse":
        await interaction.reply({ content: "Choose a category to browse.", components: [categorySelect("archive:browse-category")], flags: MessageFlags.Ephemeral });
        return true;
      case "search":
        await interaction.showModal(new ModalBuilder().setCustomId("archive:search").setTitle("Search the Archive")
          .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
            new TextInputBuilder().setCustomId("keyword").setLabel("Search words").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(100),
          )));
        return true;
      case "submit":
        await interaction.reply({ content: "Choose a category for your contribution.", components: [categorySelect("archive:submit-category")], flags: MessageFlags.Ephemeral });
        return true;
      case "mine": await this.showMine(interaction); return true;
      case "collections": await this.showCollections(interaction); return true;
      case "trails": await this.showTrails(interaction); return true;
      case "report":
        await interaction.showModal(new ModalBuilder().setCustomId("archive:report")
          .setTitle("Report an Archive entry")
          .addComponents(
            new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("entry_id").setLabel("Entry ID").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(20)),
            new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("reason").setLabel("Reason for report").setStyle(TextInputStyle.Paragraph).setRequired(true).setMaxLength(500)),
          ));
        return true;
      case "review": await this.showReviewQueue(interaction); return true;
      case "report-review": await this.showReportQueue(interaction); return true;
      case "configure": await this.openConfigure(interaction); return true;
      case "finish":
        if (!value) return false;
        try {
          await finishArchiveUpload(interaction.guildId, interaction.user.id, value);
          const entry=await getArchiveEntry(interaction.guildId,value,true);
          const notified=entry?await this.notifyModerationChannel(
            interaction.client,interaction.guildId,value,entry.title,entry.archive_type,entry.visibility,entry.content,entry.source_title??undefined,entry.source_url??undefined,
          ):false;
          await interaction.reply({
            content: `Submission #${value} is now awaiting moderator review.${notified?" Moderators have been notified.":" Moderators can review it from /archive → Review queue."}`,
            flags: MessageFlags.Ephemeral,
          });
        } catch (error) {
          const message = error instanceof Error ? error.message : "Could not finish the upload.";
          const issueHash = await createInteractionIssueLog(interaction, "/archive", error, { action: "finish-upload" });
          await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
        }
        return true;
      case "open-entry":
        return false;
      case "report-entry":
        if (!value) return false;
        await interaction.showModal(reportModal(value));
        return true;
      case "collection-open":
        if (!value) return false;
        await this.showCollectionItems(interaction, value);
        return true;
      default: return false;
    }
  }

  async handleSelect(interaction: StringSelectMenuInteraction | ChannelSelectMenuInteraction | RoleSelectMenuInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [prefix, action] = interaction.customId.split(":");
    if (prefix !== "archive") return false;
    if (interaction.isRoleSelectMenu()) {
      if (action !== "configure-moderator-role") return false;
      if (!isGuildManager(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to change Archive settings.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const role = interaction.roles.first();
      if (!role || role.id === interaction.guildId) {
        await interaction.reply({content:"Choose a normal server role. @everyone cannot moderate the Archive.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await saveArchiveModeratorRole(interaction.guildId, interaction.user.id, role.id);
      await interaction.reply({content:"Archive moderation now accepts the configured role <@&"+role.id+">.",flags:MessageFlags.Ephemeral});
      return true;
    }
    if (interaction.isChannelSelectMenu()) {
      if (action !== "configure-upload" && action !== "configure-moderation") return false;
      if (!isGuildManager(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to change Archive channels.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const selectedChannel=interaction.channels.first();
      if (!selectedChannel || (selectedChannel.type !== ChannelType.GuildText && selectedChannel.type !== ChannelType.GuildAnnouncement)) {
        await interaction.reply({content:"Choose a normal text or announcement channel from this server.",flags:MessageFlags.Ephemeral});
        return true;
      }
      const kind=action==="configure-upload"?"upload":"moderation";
      await saveArchiveChannelSetting(interaction.guildId,interaction.user.id,kind,selectedChannel.id);
      await interaction.reply({
        content:kind==="upload"
          ? "Archive media uploads will now be received in <#"+selectedChannel.id+">."
          : "New Archive submissions will now be sent to <#"+selectedChannel.id+"> for moderation.",
        flags:MessageFlags.Ephemeral,
      });
      return true;
    }
    const selected = interaction.values[0];
    if (!selected) return false;
    if (action === "browse-category" && isArchiveCategory(selected)) {
      const entries = await listArchiveEntries(interaction.guildId, selected, undefined, 0, 5);
      await this.presentEntries(interaction, entries, categoryLabel(selected));
      return true;
    }
    if(action==="submit-category"&&selected==="panels"){
      await interaction.reply({content:"Manga Panels require an image attachment and a chapter caption. Use /archive with action:submit, category:panels, title, chapter_caption, optional source_url (AniList ID or URL), tags, and file.",flags:MessageFlags.Ephemeral});
      return true;
    }
    if (action === "submit-category" && isArchiveCategory(selected)) {
      await interaction.showModal(submitModal(selected, "server"));
      return true;
    }
    if (action === "open-entry") {
      const entry = await getArchiveEntry(interaction.guildId, selected);
      if (!entry) {
        await interaction.reply({ content: "That contribution is no longer visible here.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await this.showEntry(interaction, entry);
      return true;
    }
    if (action === "collection-open") {
      await this.showCollectionItems(interaction, selected);
      return true;
    }
    if (action === "trail-open") {
      await this.openTrail(interaction, selected);
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [prefix, action, category, visibility] = interaction.customId.split(":");
    if (prefix !== "archive") return false;
    try {
      if (action === "submit" && category && isArchiveCategory(category)) {
        const source = interaction.fields.getTextInputValue("source");
        const creator = interaction.fields.getTextInputValue("creator");
        const tags = interaction.fields.getTextInputValue("tags");
        const settings = await getArchiveSettings(interaction.guildId);
        const title = interaction.fields.getTextInputValue("title");
        const body = interaction.fields.getTextInputValue("content");
        const sourceUrl = category === "fanworks" || (category === "soundtracks" && source.trim().startsWith("https://")) ? source : undefined;
        const needsUpload = category === "soundtracks" && !sourceUrl;
        if(needsUpload&&!settings.uploadChannelId) throw new Error("A server manager must configure the Archive upload channel before submitting media without a source link.");
        const sourceTitle = category === "quotes" ? source : category === "soundtracks" && !sourceUrl ? source : undefined;
        const id = await submitArchiveEntry({
          guildId: interaction.guildId,
          userId: interaction.user.id,
          category,
          title,
          content: body,
          sourceTitle,
          creator: category === "fanworks" ? creator : undefined,
          mediaType: "Other",
          sourceUrl,
          tags: tags.split(","),
          spoiler: category === "theories",
          visibility: (visibility ?? "server") as ArchiveVisibility,
          needsUpload,
        });
        await rememberArchiveCategory(interaction.guildId,interaction.user.id,category);
        const settingsAfterSubmit = await getArchiveSettings(interaction.guildId);
        const moderationPosted = !needsUpload
          ? await this.notifyModerationChannel(interaction.client,interaction.guildId,id,title,category,(visibility ?? "server") as ArchiveVisibility,body,sourceTitle,sourceUrl)
          : false;
        const uploadText = needsUpload
          ? settingsAfterSubmit.uploadChannelId
            ? `\nUpload the media in <#${settingsAfterSubmit.uploadChannelId}> and then press **Finish upload** below.`
            : "\nA server manager must configure the Archive upload channel before media can be added."
          : "";
        const moderationText = !needsUpload
          ? moderationPosted ? "\nThe moderators have been notified." : "\nModerators can review it from /archive → Review queue."
          : "";
        await interaction.reply({
          content: `Saved Archive submission #${id}. It is pending review; it will not appear in public browsing until approved.${uploadText}${moderationText}`,
          ...(needsUpload ? { components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId(`archive:finish:${id}`).setLabel("Finish upload").setStyle(ButtonStyle.Success),
          )] } : {}),
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (action === "quick-panel") {
        const title=interaction.fields.getTextInputValue("title").trim();
        const chapter=parsePanelChapterCaption(interaction.fields.getTextInputValue("chapter_caption"));
        const mangaReference=parseAniListMangaReference(interaction.fields.getTextInputValue("source_url"));
        const settings=await getArchiveSettings(interaction.guildId);
        if(!settings.uploadTypes.includes("image")) throw new Error("This server has not enabled image uploads for the Archive.");
        if(!settings.uploadChannelId) throw new Error("A server manager must configure the Archive upload channel before using the quick Manga Panels flow.");
        const id=await submitArchiveEntry({
          guildId:interaction.guildId,
          userId:interaction.user.id,
          category:"panels",
          title,
          content:chapter.caption,
          mediaType:"Manga",
          sourceUrl:mangaReference.url??undefined,
          tags:interaction.fields.getTextInputValue("tags").split(","),
          spoiler:false,
          visibility:"server",
          needsUpload:true,
          chapterNumber:chapter.chapterNumber,
          linkedMediaProvider:mangaReference.id?"AniList":undefined,
          linkedMediaId:mangaReference.id??undefined,
        });
        await rememberArchiveCategory(interaction.guildId,interaction.user.id,"panels");
        await interaction.reply({
          content:`Created Manga Panels submission #${id}. Upload the image(s) in <#${settings.uploadChannelId}> and then press Finish upload below.`,
          components:[new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId(`archive:finish:${id}`).setLabel("Finish upload").setStyle(ButtonStyle.Success),
          )],
          flags:MessageFlags.Ephemeral,
        });
        return true;
      }
      if (action === "search") {
        const keyword = interaction.fields.getTextInputValue("keyword");
        const entries = await listArchiveEntries(interaction.guildId, undefined, keyword, 0, 5);
        await this.presentEntries(interaction, entries, `Search · ${keyword}`);
        return true;
      }
      if (action === "report") {
        const entryId = category || interaction.fields.getTextInputValue("entry_id").trim();
        await addArchiveReport(
          interaction.guildId,
          interaction.user.id,
          entryId,
          interaction.fields.getTextInputValue("reason"),
        );
        await interaction.reply({ content: "Your report has been sent to the server Archive moderators.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "configure") {
        if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required to change Archive settings.");
        const categories = interaction.fields.getTextInputValue("categories").split(",").map((value) => value.trim()).filter(Boolean);
        const uploads = interaction.fields.getTextInputValue("uploads").split(",").map((value) => value.trim()).filter(Boolean);
        if (!categories.every(isArchiveCategory)) throw new Error("One or more categories are invalid.");
        await saveArchiveSettings(interaction.guildId, interaction.user.id, categories, uploads);
        await interaction.reply({ content: "Archive categories and accepted upload types have been updated for this server.", flags: MessageFlags.Ephemeral });
        return true;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The Archive could not complete that action.";
      const issueHash = await createInteractionIssueLog(interaction, "/archive", error, { action: "modal-submit" });
      await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  private async notifyModerationChannel(
    client: ChatInputCommandInteraction["client"],
    guildId: string,
    entryId: string,
    title: string,
    category: ArchiveCategory,
    visibility: ArchiveVisibility,
    content: string,
    sourceTitle?: string,
    sourceUrl?: string,
  ): Promise<boolean> {
    const settings = await getArchiveSettings(guildId);
    if (!settings.moderationChannelId) return false;
    try {
      const channel = await client.channels.fetch(settings.moderationChannelId);
      if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
        logger.warn("Archive moderation channel is no longer a normal text channel", {
          guildId, channelId: settings.moderationChannelId,
        });
        return false;
      }
      const embed = homeEmbed(
        "Archive submission · #" + entryId,
        safeDisplay(title, 180),
        [
          { name: "Category", value: categoryLabel(category), inline: true },
          { name: "Visibility", value: visibility === "global" ? "Global" : "This server", inline: true },
          { name: "Submitted by", value: "<@" + (await queryOne<{ created_by: string }>(
            "SELECT created_by::text FROM community_archive_entries WHERE id = $1 AND created_guild_id = $2",
            [entryId, guildId],
          ))?.created_by + ">", inline: true },
          ...(sourceTitle ? [{ name: "Work / source", value: safeDisplay(sourceTitle, 200), inline: true }] : []),
          ...(sourceUrl ? [{ name: "Source link", value: "[Open metadata source](" + sourceUrl + ")", inline: false }] : []),
          { name: "Contribution", value: safeDisplay(content || "Media attachment submitted.", 900), inline: false },
        ],
      ).setFooter({ text: "Pending moderator review · Entry visibility is not public until approved" });
      const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("archive:approve:" + entryId + ":" + visibility).setLabel("Approve").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId("archive:reject:" + entryId + ":" + visibility).setLabel("Reject").setStyle(ButtonStyle.Danger),
      );
      await (channel as import("discord.js").TextChannel | import("discord.js").NewsChannel).send({
        embeds: [embed],
        components: [row],
        allowedMentions: { parse: [] },
      });
      return true;
    } catch (error) {
      logger.warn("Archive submission was saved but could not be posted to its moderation channel", {
        guildId,
        channelId: settings.moderationChannelId,
        entryId,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
      return false;
    }
  }

  private async submitFromCommand(interaction: ChatInputCommandInteraction, category: ArchiveCategory): Promise<void> {
    const title = interaction.options.getString("title", true);
    const content = interaction.options.getString("content") ?? "";
    const visibility = (interaction.options.getString("visibility") ?? "server") as ArchiveVisibility;
    const submittedSourceUrl = interaction.options.getString("source_url") ?? "";
    const attachment = interaction.options.getAttachment("file");
    const settings = await getArchiveSettings(interaction.guildId!);
    const panelChapter = category === "panels" ? parsePanelChapterCaption(interaction.options.getString("chapter_caption") ?? "") : null;
    const panelReference = category === "panels" ? parseAniListMangaReference(submittedSourceUrl) : null;
    if (category === "panels") {
      if (!attachment) throw new Error("Manga Panels require an image attachment.");
      if (!settings.uploadTypes.includes("image")) throw new Error("This server has not enabled image uploads for the Archive.");
      const probe = classifyArchiveUpload(category, { name: attachment.name, contentType: attachment.contentType ?? "application/octet-stream", bytes: Buffer.from([1]) });
      if (probe.kind !== "image") throw new Error("Manga Panels accept image attachments only.");
      if (attachment.size > 20 * 1024 * 1024) throw new Error("Archive uploads are limited to 20 MB.");
    }
    const sourceUrl = category === "panels" ? (panelReference?.url ?? undefined)
      : category === "fanworks" || (category === "soundtracks" && submittedSourceUrl.trim().startsWith("https://")) ? submittedSourceUrl : undefined;
    const needsUpload = category === "panels" || (category === "soundtracks" && !sourceUrl);
    if(needsUpload&&!attachment&&!settings.uploadChannelId) throw new Error("A server manager must configure the Archive upload channel before submitting media without a direct attachment.");
    const entryContent = category === "panels" ? [panelChapter!.caption, content].filter(Boolean).join("\n\n") : content;
    const sourceTitle = interaction.options.getString("source_title") ?? undefined;
    const entryId = await submitArchiveEntry({
      guildId: interaction.guildId!,
      userId: interaction.user.id,
      category,
      title,
      content: entryContent,
      sourceTitle,
      creator: interaction.options.getString("creator") ?? undefined,
      mediaType: category === "panels" ? "Manga" : interaction.options.getString("media_type") ?? "Other",
      sourceUrl: sourceUrl ?? undefined,
      tags: (interaction.options.getString("tags") ?? "").split(","),
      spoiler: interaction.options.getBoolean("spoiler") ?? category === "theories",
      visibility,
      needsUpload,
      chapterNumber: panelChapter?.chapterNumber,
      linkedMediaProvider: panelReference?.id ? "AniList" : undefined,
      linkedMediaId: panelReference?.id ?? undefined,
    });
    await rememberArchiveCategory(interaction.guildId!, interaction.user.id, category);
    let savedFile = false;
    if (attachment) {
      const kind = classifyArchiveUpload(category, {
        name: attachment.name,
        contentType: attachment.contentType ?? "application/octet-stream",
        bytes: Buffer.from([1]),
      }).kind;
      if (category === "panels" && kind !== "image") throw new Error("Manga Panels accept image attachments only.");
      if (!settings.uploadTypes.includes(kind)) throw new Error(`This server has not enabled ${kind} uploads.`);
      if (attachment.size > 20 * 1024 * 1024) throw new Error("Archive uploads are limited to 20 MB.");
      const response = await fetch(attachment.url, { signal: AbortSignal.timeout(15_000) });
      if (!response.ok) throw new Error("Discord could not provide the attachment bytes.");
      const bytes = Buffer.from(await response.arrayBuffer());
      const assetId = await storeArchiveUpload(interaction.guildId!, interaction.user.id, category, {
        name: attachment.name, contentType: attachment.contentType ?? "application/octet-stream", bytes,
      }, settings.uploadTypes, { client: interaction.client, legacyStorageChannelId: settings.legacyStorageChannelId });
      await query(
        "INSERT INTO community_archive_entry_assets (entry_id, asset_id, position, uploaded_by) VALUES ($1, $2, 1, $3)",
        [entryId, assetId, interaction.user.id],
      );
      await query(
        "UPDATE community_archive_entries SET media_asset_id = $1, attachment_filename = $2, attachment_content_type = $3 WHERE id = $4",
        [assetId, attachment.name, attachment.contentType ?? null, entryId],
      );
      if (needsUpload) await finishArchiveUpload(interaction.guildId!, interaction.user.id, entryId);
      savedFile = true;
    }
    const moderationPosted = !needsUpload || savedFile
      ? await this.notifyModerationChannel(
          interaction.client,interaction.guildId!,entryId,title,category,visibility,entryContent,sourceTitle,sourceUrl ?? undefined,
        )
      : false;
    const uploadNotice = needsUpload && !savedFile
      ? settings.uploadChannelId
        ? " Upload the required media in <#" + settings.uploadChannelId + "> and then press Finish upload."
        : " The server manager must configure an Archive upload channel before you can send the media."
      : "";
    const moderationNotice = !needsUpload || savedFile
      ? moderationPosted ? " The moderators have been notified." : " Moderators can review it from /archive → Review queue."
      : "";
    await interaction.reply({
      content: `Saved Archive submission #${entryId}. It is pending review and is not public until approved.${uploadNotice}${moderationNotice}`,
      flags: MessageFlags.Ephemeral,
    });
  }

  private async browse(interaction: ChatInputCommandInteraction, category: ArchiveCategory | null): Promise<void> {
    if (!category) {
      await interaction.reply({ content: "Choose a category to browse.", components: [categorySelect("archive:browse-category")], flags: MessageFlags.Ephemeral });
      return;
    }
    const entries = await listArchiveEntries(interaction.guildId!, category, undefined, 0, 5);
    await this.presentEntries(interaction, entries, categoryLabel(category));
  }

  private async presentEntries(
    interaction: ButtonInteraction | ChatInputCommandInteraction | ModalSubmitInteraction | StringSelectMenuInteraction,
    entries: ArchiveEntry[],
    title: string,
  ): Promise<void> {
    if (!entries.length) {
      await interaction.reply({ content: `No approved contributions found for **${title}**. You can submit an entry from the Archive home panel.`, flags: MessageFlags.Ephemeral });
      return;
    }
    const visibleEntries = entries.slice(0, 5);
    const embeds = await Promise.all(visibleEntries.map(async (entry) => {
      const embed = entryEmbed(entry);
      const media = await this.resolveEntryMedia(interaction, entry);
      if (media.imageUrl) embed.setThumbnail(media.imageUrl);
      return embed;
    }));
    const components = [entrySelect(visibleEntries)];
    await interaction.reply({
      content: `**${title}** · ${visibleEntries.length} shown`,
      embeds,
      components,
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async resolveEntryMedia(
    interaction: ButtonInteraction | ChatInputCommandInteraction | ModalSubmitInteraction | StringSelectMenuInteraction,
    entry: ArchiveEntry,
  ): Promise<{ imageUrl: string | null; attachmentUrls: string[] }> {
    const assets = await query<{ asset_id: string; content_type: string }>(
      `SELECT m.id::text AS asset_id, m.content_type
       FROM media_assets m
       LEFT JOIN community_archive_entry_assets attached
         ON attached.entry_id = $1 AND attached.asset_id = m.id
       WHERE m.id = $2 OR attached.entry_id IS NOT NULL
       ORDER BY CASE WHEN m.id = $2 THEN 0 ELSE attached.position END ASC, m.id ASC
       LIMIT 5`,
      [entry.id, entry.media_asset_id],
    );
    const resolved = await Promise.all(assets.map(async (asset) => ({
      contentType: asset.content_type.toLowerCase(),
      url: await signedArchiveAssetUrl(Number(asset.asset_id), interaction.client, entry.created_guild_id).catch(() => null),
    })));
    const image = resolved.find((asset) => asset.url && asset.contentType.startsWith("image/"));
    const attachmentUrls = resolved
      .filter((asset) => asset.url && asset !== image)
      .map((asset) => asset.url!);

    if (!image?.url && !attachmentUrls.length && entry.storage_channel_id && entry.storage_message_id) {
      const legacyUrl = await resolveLegacyArchiveAttachmentUrl(
        interaction.client, entry.created_guild_id, entry.storage_channel_id, entry.storage_message_id, entry.attachment_filename,
      ).catch(() => null);
      if (legacyUrl) {
        if (/\.(?:png|jpe?g|gif|webp|avif)$/i.test(entry.attachment_filename ?? "")) {
          return { imageUrl: legacyUrl, attachmentUrls };
        }
        attachmentUrls.push(legacyUrl);
      }
    }

    if (!image?.url && !attachmentUrls.length && entry.attachment_url?.startsWith("https://")) {
      if (/\.(?:png|jpe?g|gif|webp|avif)(?:[?#].*)?$/i.test(entry.attachment_url)) {
        return { imageUrl: entry.attachment_url, attachmentUrls };
      }
      attachmentUrls.push(entry.attachment_url);
    }

    return { imageUrl: image?.url ?? null, attachmentUrls };
  }

  private async showEntry(
    interaction: ButtonInteraction | StringSelectMenuInteraction,
    entry: ArchiveEntry,
  ): Promise<void> {
    const embed = entryEmbed(entry);
    const media = await this.resolveEntryMedia(interaction, entry);
    if (media.imageUrl) embed.setImage(media.imageUrl);
    if (media.attachmentUrls.length) {
      embed.addFields({
        name: "Attachments",
        value: media.attachmentUrls.map((url, index) => `[Open file ${index + 1}](${url})`).join("\n").slice(0, 1024),
        inline: false,
      });
    }
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId(`archive:report-entry:${entry.id}`).setLabel("Report").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("archive:collections").setLabel("Collections").setStyle(ButtonStyle.Secondary),
    );
    await interaction.reply({ embeds: [embed], components: [row], flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
  }

  private async showPanelOfTheDay(interaction: ChatInputCommandInteraction): Promise<void> {
    const entry = await getPanelOfTheDay(interaction.guildId!, interaction.user.id);
    if (!entry) {
      await interaction.reply({ content: "No approved, safe Manga Panels with an available image can be featured today.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embed = entryEmbed(entry).setFooter({ text: "Panel of the Day · Selected once per server per day · Safe, approved Archive entry" });
    let imageUrl: string | null = null;
    if (entry.media_asset_id) imageUrl = await signedArchiveAssetUrl(Number(entry.media_asset_id), interaction.client, entry.created_guild_id).catch(() => null);
    if (!imageUrl) {
      const asset = await queryOne<{ asset_id: string }>("SELECT asset_id FROM community_archive_entry_assets WHERE entry_id = $1 ORDER BY position ASC LIMIT 1", [entry.id]);
      if (asset) imageUrl = await signedArchiveAssetUrl(Number(asset.asset_id), interaction.client, entry.created_guild_id).catch(() => null);
    }
    if (!imageUrl && entry.storage_channel_id && entry.storage_message_id) {
      imageUrl = await resolveLegacyArchiveAttachmentUrl(
        interaction.client, entry.created_guild_id, entry.storage_channel_id, entry.storage_message_id, entry.attachment_filename,
      );
    }
    if (!imageUrl && entry.attachment_url?.startsWith("https://")) imageUrl = entry.attachment_url;
    if (imageUrl) embed.setImage(imageUrl);
    await interaction.reply({ embeds: [embed], allowedMentions: { parse: [] } });
  }
  private async showMine(
    interaction: ChatInputCommandInteraction | ButtonInteraction,
  ): Promise<void> {
    if (!interaction.guildId) return;
    const entries = await getOwnSubmissions(interaction.guildId, interaction.user.id);
    if (!entries.length) {
      await interaction.reply({ content: "You have not submitted anything to this server's Archive yet.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embeds = entries.slice(0, 5).map((entry) => new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle(`#${entry.id} · ${safeDisplay(entry.title)}`)
      .setDescription(`**${entry.status}** · ${categoryLabel(entry.archive_type)}\n${safeDisplay(entry.content, 500)}`)
      .setFooter({ text: `Submitted ${new Date(entry.created_at).toLocaleDateString()}` }));
    await interaction.reply({ embeds, flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
  }

  private async showReviewQueue(
    interaction: ChatInputCommandInteraction | ButtonInteraction,
  ): Promise<void> {
    if (!interaction.guildId || !interaction.member || !("permissions" in interaction.member)) {
      await interaction.reply({ content: "Archive review is available in a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const member = interaction.member as GuildMember;
    const global = isGlobalArchiveModerator(interaction.user.id);
    const canLocal = member.permissions.has(PermissionsBitField.Flags.Administrator)
      || member.permissions.has(PermissionsBitField.Flags.ManageGuild)
      || member.permissions.has(PermissionsBitField.Flags.ManageMessages);
    if (!canLocal && !global) {
      const role = await queryOne<{ moderator_role_id: string | null }>("SELECT moderator_role_id FROM guild_archive_settings WHERE guild_id = $1", [interaction.guildId]).catch(() => null);
      if (!role?.moderator_role_id || !member.roles.cache.has(role.moderator_role_id)) {
        await interaction.reply({ content: "Archive moderator permissions are required.", flags: MessageFlags.Ephemeral });
        return;
      }
    }
    const [localEntries, globalEntries] = await Promise.all([
      canLocal ? listPendingEntries(interaction.guildId, "server") : [],
      global ? listPendingEntries(interaction.guildId, "global") : [],
    ]);
    const items = [...localEntries, ...globalEntries].slice(0, 10);
    if (!items.length) {
      await interaction.reply({ content: "There are no pending submissions in the moderation scopes you can review.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embeds = items.slice(0, 5).map((entry) => new EmbedBuilder()
      .setColor(0xf0b232)
      .setTitle(`#${entry.id} · ${safeDisplay(entry.title)}`)
      .setDescription(`${categoryLabel(entry.archive_type)} · ${entry.visibility} · submitter <@${entry.created_by}>\n${safeDisplay(entry.content, 500)}`));
    const first = items[0]!;
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId(`archive:approve:${first.id}:${first.visibility}`).setLabel("Approve first").setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId(`archive:reject:${first.id}:${first.visibility}`).setLabel("Reject first").setStyle(ButtonStyle.Danger),
    );
    await interaction.reply({ embeds, components: [row], flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
  }

  private async configure(interaction: ChatInputCommandInteraction): Promise<void> {
    await this.openConfigure(interaction);
  }

  private async openConfigure(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to configure the Archive.", flags: MessageFlags.Ephemeral });
      return;
    }
    const settings = await getArchiveSettings(interaction.guildId!);
    const embed = homeEmbed(
      "Archive · Server settings",
      "Choose normal text or announcement channels. The upload channel receives private media uploads for pending contributions; the moderation channel receives new submission cards with approve/reject controls.",
      [
        {name:"Upload channel",value:settings.uploadChannelId?"<#"+settings.uploadChannelId+">":"Not configured",inline:true},
        {name:"Moderation channel",value:settings.moderationChannelId?"<#"+settings.moderationChannelId+">":"Not configured",inline:true},
        {name:"Moderator role",value:settings.moderatorRoleId?"<@&"+settings.moderatorRoleId+">":"Not configured",inline:true},
        {name:"Enabled categories",value:settings.enabledCategories.map(categoryLabel).join(", ")||"None",inline:false},
        {name:"Accepted uploads",value:settings.uploadTypes.join(", ")||"None",inline:true},
      ],
    );
    const upload = new ChannelSelectMenuBuilder()
      .setCustomId("archive:configure-upload")
      .setPlaceholder("Choose the media upload channel")
      .setChannelTypes(ChannelType.GuildText,ChannelType.GuildAnnouncement)
      .setMinValues(1)
      .setMaxValues(1);
    const moderation = new ChannelSelectMenuBuilder()
      .setCustomId("archive:configure-moderation")
      .setPlaceholder("Choose the moderation log channel")
      .setChannelTypes(ChannelType.GuildText,ChannelType.GuildAnnouncement)
      .setMinValues(1)
      .setMaxValues(1);
    const moderatorRole = new RoleSelectMenuBuilder()
      .setCustomId("archive:configure-moderator-role")
      .setPlaceholder("Choose the Archive moderator role")
      .setMinValues(1)
      .setMaxValues(1);
    const controls = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("archive:configure-types").setLabel("Categories & uploads").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("archive:configure-clear-upload").setLabel("Clear upload channel").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("archive:configure-clear-moderation").setLabel("Clear moderation channel").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("archive:configure-clear-moderator-role").setLabel("Clear moderator role").setStyle(ButtonStyle.Secondary),
    );
    await interaction.reply({
      embeds:[embed],
      components:[
        new ActionRowBuilder<ChannelSelectMenuBuilder>().addComponents(upload),
        new ActionRowBuilder<ChannelSelectMenuBuilder>().addComponents(moderation),
        new ActionRowBuilder<RoleSelectMenuBuilder>().addComponents(moderatorRole),
        controls,
      ],
      flags:MessageFlags.Ephemeral,
    });
  }

  private async showCollections(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) return;
    const collections = await listArchiveCollections(interaction.guildId);
    if (!collections.length) {
      await interaction.reply({ content: "No collections have been curated in this server yet. Create one with /archive action:create-collection.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embed = homeEmbed("Archive Collections", "Collections can mix all approved Archive categories. Original entry authorship remains attached to every item.", collections.slice(0, 10).map((collection) => ({
      name: `#${collection.id} · ${safeDisplay(collection.title, 150)}`,
      value: `${collection.entry_count} entries · ${collection.visibility} visibility\n${safeDisplay(collection.description, 180) || "No description"}`,
      inline: false,
    })));
    const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
      .setCustomId("archive:collection-open")
      .setPlaceholder("Open a collection")
      .addOptions(collections.slice(0, 25).map((collection) => ({ label: collection.title.slice(0, 100), value: collection.id }))));
    await interaction.reply({ embeds: [embed], components: [select], flags: MessageFlags.Ephemeral });
  }

  private async showCollectionItems(interaction: ButtonInteraction | StringSelectMenuInteraction, collectionId: string): Promise<void> {
    if (!interaction.guildId) return;
    const items = await getCollectionItems(interaction.guildId, collectionId);
    if (!items.length) {
      await interaction.reply({ content: "This collection is empty or no longer has entries visible to you.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({
      embeds: items.slice(0, 5).map(entryEmbed),
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async showTrails(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) return;
    const trails = await listArchiveTrails(interaction.guildId);
    if (!trails.length) {
      await interaction.reply({ content: "No Archive Trails have been created in this server yet.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embed = homeEmbed("Archive Trails", "Trails connect approved contributions in a curated sequence. Entry access is rechecked when opened.", trails.slice(0, 10).map((trail) => ({
      name: `#${trail.id} · ${safeDisplay(trail.title, 150)}`,
      value: `${trail.step_count} steps · by <@${trail.owner_id}>\n${safeDisplay(trail.introduction, 180) || "No introduction"}`,
      inline: false,
    })));
    const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
      new StringSelectMenuBuilder().setCustomId("archive:trail-open").setPlaceholder("Open an Archive Trail")
        .addOptions(trails.slice(0, 25).map((trail) => ({ label: trail.title.slice(0, 100), value: trail.id }))),
    );
    await interaction.reply({ embeds: [embed], components: [select], flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
  }

  private async openTrail(
    interaction: ButtonInteraction | ChatInputCommandInteraction | StringSelectMenuInteraction,
    trailId: string,
  ): Promise<void> {
    const steps = await getArchiveTrailSteps(interaction.guildId!, trailId);
    if (!steps.length) {
      await interaction.reply({ content: "This Trail has no entries visible to you in this server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({
      content: "Archive Trail · curated sequence",
      embeds: steps.slice(0, 5).map((step) => entryEmbed(step.entry).setFooter({ text: `Step ${step.step_number} · ${safeDisplay(step.explanation, 150)}` })),
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async showReportQueue(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) return;
    const member = await interaction.guild!.members.fetch(interaction.user.id);
    const global = isGlobalArchiveModerator(interaction.user.id);
    const local = await canModerateArchive(member, interaction.guildId, "server");
    if (!local && !global) {
      await interaction.reply({ content: "Archive moderator permissions are required.", flags: MessageFlags.Ephemeral });
      return;
    }
    const reports = await listArchiveReports(interaction.guildId, false);
    const globalReports = global ? await listArchiveReports(interaction.guildId, true) : [];
    const rows = [...reports, ...globalReports].slice(0, 10);
    if (!rows.length) {
      await interaction.reply({ content: "There are no pending Archive reports in your moderation scopes.", flags: MessageFlags.Ephemeral });
      return;
    }
    const first = rows[0]!;
    const scope = first.visibility === "global" ? "global" : "server";
    await interaction.reply({
      embeds: rows.slice(0, 5).map((report) => new EmbedBuilder().setColor(0xe0a33b)
        .setTitle(`Report #${report.id} · Entry #${report.entry_id}`)
        .setDescription(`**${safeDisplay(report.title)}**\n${safeDisplay(report.reason, 400)}\nReporter: <@${report.reporter_id}>`)
        .setFooter({ text: `${report.visibility} Archive · ${categoryLabel(report.archive_type)}` })),
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(`archive:report-dismiss:${first.id}:${scope}`).setLabel("Dismiss first report").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId(`archive:report-remove:${first.id}:${scope}`).setLabel("Remove reported entry").setStyle(ButtonStyle.Danger),
      )],
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }
}

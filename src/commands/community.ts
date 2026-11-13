import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  GuildScheduledEventEntityType,
  GuildScheduledEventPrivacyLevel,
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
  type TextChannel,
} from "discord.js";
import { emoji } from "../../helpers/emoji.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { homeEmbed } from "../../helpers/runtime/discord.js";
import { AniListClient } from "../../helpers/integration/anilist.js";
import { TmdbClient } from "../../helpers/integration/tmdb.js";
import {
  addRankingCandidate,
  closeDiscussion,
  closeRanking,
  createCommunitySession,
  createRanking,
  createMediaNight,
  filterMediaNightCandidates,
  sampleMediaNightCandidates,
  disableReleaseSchedule,
  getReleaseSchedule,
  saveReleaseSchedule,
  createSpoilerDiscussion,
  disableDailySchedule,
  dueDailyDeliveries,
  dueDailySchedules,
  formatActivity,
  upcomingProviderReleases,
  getCommunityHistory,
  getCommunitySession,
  listUpcomingSessions,
  markDailyDelivery,
  nextLocalOccurrence,
  prepareDailyDelivery,
  rankingResults,
  reviewDailyItem,
  reviewRankingCandidate,
  saveDailySchedule,
  setSessionRsvp,
  submitDailyItem,
  voteForRanking,
} from "../../helpers/community/community.js";
import { query, queryOne } from "../../database.js";
import { listArchiveSpotlights } from "../../helpers/archive/archive-curation.js";
import { cleanText, isGuildManager, isValidHttpsUrl, safeDisplay } from "../../helpers/security/security.js";
import {
  attachReadingDiscussion,
  listReadingNominations,
  nominateReading,
  parseReadingScheduleTime,
  READING_CATEGORIES,
  selectNextReading,
  voteForReading,
} from "../../helpers/community/community-reading.js";

const DAILY_FORMATS = [
  { name: "Question", value: "question" },
  { name: "Short quote", value: "quote" },
  { name: "Trivia", value: "trivia" },
  { name: "Recommendation", value: "recommendation" },
  { name: "Archive spotlight", value: "archive_spotlight" },
  { name: "Mystery clue", value: "mystery" },
] as const;
const ACTIVITIES = [
  { name: "Watch together", value: "watch" },
  { name: "Read together", value: "read" },
  { name: "Play together", value: "play" },
  { name: "Discuss", value: "discuss" },
] as const;

function modal(customId: string, title: string, inputs: Array<{ id: string; label: string; max?: number; required?: boolean; value?: string; paragraph?: boolean; placeholder?: string }>): ModalBuilder {
  const result = new ModalBuilder().setCustomId(customId).setTitle(title);
  for (const input of inputs.slice(0, 5)) {
    const field = new TextInputBuilder()
      .setCustomId(input.id)
      .setLabel(input.label)
      .setMaxLength(input.max ?? 200)
      .setRequired(input.required ?? true)
      .setStyle(input.paragraph ? TextInputStyle.Paragraph : TextInputStyle.Short)
      .setPlaceholder(input.placeholder || "Enter a value");
    if (input.value) field.setValue(input.value);
    result.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(field));
  }
  return result;
}

function communityHome(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const embed = homeEmbed(
    "Community",
    "A shared space for recurring contributions, media rankings, scheduled group activities and spoiler-aware discussions. Every schedule, vote and session is scoped to this Discord server.",
    [
      { name: "Daily Drop", value: "Contribute, review and schedule the daily community item.", inline: true },
      { name: "Rankings", value: "Create candidate lists and vote; one current vote per member.", inline: true },
      { name: "Sessions", value: "Plan watch, read, play and discussion meetups with RSVP and waitlists.", inline: true },
      { name: "Discussions", value: "Start spoiler-aware media threads and close them when finished.", inline: true },
      { name: "Media Night", value: "A short, family-aware media vote with locked choices and scheduled results.", inline: true },
      { name: "Release calendar", value: "Upcoming provider-dated anime airings and film releases.", inline: true },
      { name: "History", value: "Recent rankings, sessions and discussions.", inline: true },
      { name: "Spotlights", value: "Curator-selected approved Archive contributions.", inline: true },
    ],
  );
  const rows = [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("community:daily").setLabel("Daily Drop").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("community:rankings").setLabel("Rankings").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("community:sessions").setLabel("Sessions").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("community:discussions").setLabel("Discussions").setStyle(ButtonStyle.Primary),
    ),
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("community:calendar").setLabel("Release calendar").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("community:history").setLabel("History").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("community:spotlights").setLabel("Spotlights").setStyle(ButtonStyle.Secondary),
    ),
  ];
  return { embeds: [embed], components: rows };
}

export class CommunityCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("community")
    .setDescription("Run your server's Daily Drop, rankings, sessions and discussions")
    .addStringOption((option) => option.setName("action").setDescription("Community action").addChoices(
      { name: "Daily Drop setup", value: "daily-configure" },
      { name: "Submit Daily Drop item", value: "daily-submit" },
      { name: "Review Daily Drop items", value: "daily-review" },
      { name: "Create ranking", value: "ranking-create" },
      { name: "Add ranking candidate", value: "ranking-candidate" },
      { name: "Review ranking candidate", value: "ranking-review" },
      { name: "Vote in ranking", value: "ranking-vote" },
      { name: "Close ranking", value: "ranking-close" },
      { name: "Create session", value: "session-create" },
      { name: "RSVP to session", value: "session-rsvp" },
      { name: "Cancel RSVP", value: "session-withdraw" },
      { name: "Close session", value: "session-close" },
      { name: "Start discussion", value: "discussion-create" },
      { name: "Close discussion", value: "discussion-close" },
      { name: "Start Media Night", value: "media-night" },
      { name: "Preview release calendar", value: "calendar" },
      { name: "Configure release digests", value: "calendar-configure" },
      { name: "Disable release digests", value: "calendar-disable" },
      { name: "Community history", value: "history" },
      { name: "Archive spotlights", value: "spotlights" },
      { name: "Nominate a community read", value: "reading-nominate" },
      { name: "View reading nominations and vote", value: "reading-list" },
      { name: "Select the next community read", value: "reading-select" },
      { name: "Schedule a reading discussion", value: "reading-schedule" },
    ))
    .addStringOption((option) => option.setName("title").setDescription("Title or session name").setMaxLength(180))
    .addStringOption((option) => option.setName("content").setDescription("Description, question or discussion prompt").setMaxLength(1_500))
    .addStringOption((option) => option.setName("format").setDescription("Daily Drop format").addChoices(...DAILY_FORMATS))
    .addStringOption((option) => option.setName("channel").setDescription("Channel mention or ID").setMaxLength(30))
    .addStringOption((option) => option.setName("time_zone").setDescription("IANA timezone, e.g. Europe/Dublin").setMaxLength(80))
    .addStringOption((option) => option.setName("local_time").setDescription("Daily local time HH:MM").setMaxLength(5))
    .addStringOption((option) => option.setName("source_url").setDescription("HTTPS metadata link").setMaxLength(1_000))
    .addStringOption((option) => option.setName("ranking_id").setDescription("Ranking ID"))
    .addStringOption((option) => option.setName("candidate_id").setDescription("Candidate ID"))
    .addStringOption((option) => option.setName("session_id").setDescription("Session ID"))
    .addStringOption((option) => option.setName("discussion_id").setDescription("Discussion ID"))
    .addStringOption((option) => option.setName("scheduled_at").setDescription("ISO-8601 time including timezone").setMaxLength(40))
    .addStringOption((option) => option.setName("activity").setDescription("Session type").addChoices(...ACTIVITIES))
    .addIntegerOption((option) => option.setName("capacity").setDescription("Optional attendee capacity").setMinValue(2).setMaxValue(200))
    .addStringOption((option) => option.setName("media_title").setDescription("Linked media title").setMaxLength(200))
    .addStringOption((option) => option.setName("media_url").setDescription("HTTPS media link").setMaxLength(1_000))
    .addStringOption((option) => option.setName("spoiler_boundary").setDescription("Spoiler boundary, e.g. Volume 4").setMaxLength(120))
    .addStringOption((option) => option.setName("region").setDescription("Release region (two-letter code)").setMaxLength(2))
    .addStringOption((option) => option.setName("reading_category").setDescription("Community reading category").addChoices(
      ...READING_CATEGORIES.map((value) => ({ name: value.replace(/\b\w/g, (letter) => letter.toUpperCase()), value })),
    ))
    .addStringOption((option) => option.setName("reading_nomination_id").setDescription("Reading nomination ID").setMaxLength(24))
    .addStringOption((option) => option.setName("media_category").setDescription("Media Night category").addChoices(
      { name: "Anime", value: "ANIME" }, { name: "Manga", value: "MANGA" },
    ))
    .addStringOption((option) => option.setName("media_mood").setDescription("Media Night mood").addChoices(
      { name: "Any mood", value: "all" }, { name: "Cozy", value: "cozy" }, { name: "Comedy", value: "comedy" },
      { name: "Adventure", value: "adventure" }, { name: "Mystery", value: "mystery" },
      { name: "Romance", value: "romance" }, { name: "Drama", value: "drama" },
    ))
    .addIntegerOption((option) => option.setName("duration_hours").setDescription("Voting duration in hours (1–12)").setMinValue(1).setMaxValue(12))
    .addStringOption((option) => option.setName("release_cadence").setDescription("Release digest frequency").addChoices(
      { name: "Daily", value: "daily" }, { name: "Weekly", value: "weekly" },
    ))
    .addStringOption((option) => option.setName("release_categories").setDescription("Digest categories").addChoices(
      { name: "All categories", value: "anime,tv,movies" }, { name: "Anime only", value: "anime" },
      { name: "TV only", value: "tv" }, { name: "Movies only", value: "movies" },
      { name: "Anime and TV", value: "anime,tv" }, { name: "Anime and movies", value: "anime,movies" },
      { name: "TV and movies", value: "tv,movies" },
    ))
    .addIntegerOption((option) => option.setName("weekday").setDescription("Weekly digest day (0 Sunday – 6 Saturday)").setMinValue(0).setMaxValue(6));

  private readonly anilist: AniListClient;
  private readonly tmdb: TmdbClient;

  constructor(config: BotConfig) {
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.tmdb = new TmdbClient(config.tmdbBearerToken);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Community features are scoped to a Discord server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const action = interaction.options.getString("action") ?? "home";
    try {
      switch (action) {
        case "home":
          await interaction.reply({ ...communityHome(), flags: MessageFlags.Ephemeral });
          return;
        case "daily-configure": await this.configureDaily(interaction); return;
        case "daily-submit": await this.submitDaily(interaction); return;
        case "daily-review": await this.reviewDaily(interaction); return;
        case "ranking-create": {
          const title = interaction.options.getString("title");
          if (!title) throw new Error("Provide a ranking title.");
          const id = await createRanking(interaction.guildId, interaction.user.id, title, interaction.options.getString("content") ?? "", null);
          await interaction.reply({ content: `Created community ranking #${id}. Members can add candidates with /community action:add-ranking-candidate ranking_id:${id}.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "ranking-candidate": await this.addCandidate(interaction); return;
        case "ranking-review": await this.reviewCandidate(interaction); return;
        case "ranking-vote": await this.vote(interaction); return;
        case "ranking-close": await this.closeRankingCommand(interaction); return;
        case "session-create": await this.createSession(interaction); return;
        case "session-rsvp": await this.rsvp(interaction, true); return;
        case "session-withdraw": await this.rsvp(interaction, false); return;
        case "session-close": await this.closeSession(interaction); return;
        case "discussion-create": await this.createDiscussion(interaction); return;
        case "discussion-close": await this.closeDiscussionCommand(interaction); return;
        case "media-night": await this.startMediaNight(interaction); return;
        case "calendar-configure": await this.configureReleaseCalendar(interaction); return;
        case "calendar-disable": await this.disableReleaseCalendar(interaction); return;
        case "calendar": await this.showCalendar(interaction); return;
        case "history": await this.showHistory(interaction); return;
        case "spotlights": await this.showSpotlights(interaction); return;
        case "reading-nominate": await this.nominateReading(interaction); return;
        case "reading-list": await this.showReadingNominations(interaction); return;
        case "reading-select": await this.selectReading(interaction); return;
        case "reading-schedule": await this.scheduleReadingDiscussion(interaction); return;
        default: throw new Error("That community action is not available.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The community action failed.";
      const issueHash = await createInteractionIssueLog(interaction, "/community", error);
      const response = issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message;
      await interaction.reply({ content: response, flags: MessageFlags.Ephemeral }).catch(async () => {
        await interaction.followUp({ content: response, flags: MessageFlags.Ephemeral });
      });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const mediaNightVote = interaction.customId.match(/^community:media-night-vote:(\d+):(\d+)$/);
    if (mediaNightVote && interaction.guildId) {
      await voteForRanking(interaction.guildId, interaction.user.id, mediaNightVote[1]!, mediaNightVote[2]!);
      await interaction.reply({ content: "Your Media Night vote is locked in and cannot be changed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const [, action, id] = interaction.customId.split(":");
    if (!interaction.guildId) return false;
    if (action === "daily") {
      const embed = homeEmbed("Daily Drop", "The daily item is scheduled in the server timezone and is sent from the approved contributor queue.");
      await interaction.reply({
        embeds: [embed],
        components: [
          new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("community:daily-configure").setLabel("Configure schedule").setStyle(ButtonStyle.Primary),
            new ButtonBuilder().setCustomId("community:daily-submit").setLabel("Submit an item").setStyle(ButtonStyle.Success),
            new ButtonBuilder().setCustomId("community:daily-review").setLabel("Review queue").setStyle(ButtonStyle.Secondary),
            new ButtonBuilder().setCustomId("community:daily-pause").setLabel("Pause schedule").setStyle(ButtonStyle.Secondary),
          ),
        ],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "rankings") {
      const open = await query<{ id: string; title: string; description: string; status: string }>(
        "SELECT id, title, description, status FROM community_rankings WHERE guild_id = $1 AND status = 'open' ORDER BY created_at DESC LIMIT 15",
        [interaction.guildId],
      );
      await interaction.reply({
        embeds: [homeEmbed("Community Rankings", "A member can change their vote while a ranking is open. Candidate submissions are reviewed before voting.", open.map((item) => ({
          name: `#${item.id} · ${safeDisplay(item.title)}`,
          value: safeDisplay(item.description, 160) || "No description",
          inline: false,
        })))],
        components: [
          new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId("community:ranking-create").setLabel("Create ranking").setStyle(ButtonStyle.Primary),
            new ButtonBuilder().setCustomId("community:ranking-candidate").setLabel("Add candidate").setStyle(ButtonStyle.Success),
            new ButtonBuilder().setCustomId("community:ranking-vote").setLabel("Vote").setStyle(ButtonStyle.Secondary),
            new ButtonBuilder().setCustomId("community:ranking-review").setLabel("Review candidates").setStyle(ButtonStyle.Secondary),
          ),
        ],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "sessions") {
      const sessions = await listUpcomingSessions(interaction.guildId);
      const embeds = sessions.slice(0, 5).map((session) => new EmbedBuilder()
        .setColor(0x5865f2)
        .setTitle(`#${session.id} · ${session.title}`)
        .setDescription(`${formatActivity(session.activity_type as "watch" | "read" | "play" | "discuss")} · <t:${Math.floor(new Date(session.scheduled_at).getTime() / 1000)}:F>\n${session.description}`));
      await interaction.reply({
        content: sessions.length ? "Upcoming community sessions" : "No upcoming community sessions are scheduled.",
        embeds,
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId("community:session-create").setLabel("Create session").setStyle(ButtonStyle.Primary),
          new ButtonBuilder().setCustomId("community:session-rsvp").setLabel("RSVP").setStyle(ButtonStyle.Success),
        )],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "discussions") {
      await interaction.reply({
        content: "Start a media-linked discussion with a clear spoiler boundary. Lemegeton opens a dedicated thread for it.",
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId("community:discussion-create").setLabel("Start discussion").setStyle(ButtonStyle.Primary),
        )],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "calendar") {
      await this.showCalendar(interaction);
      return true;
    }
    if (action === "calendar-configure") {
      await interaction.reply({ content: "Configure the digest with /community action:calendar-configure and provide channel, time_zone, local_time and release_cadence. Choose categories, region and weekday as needed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "calendar-disable") {
      if (!isGuildManager(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await disableReleaseSchedule(interaction.guildId);
      await interaction.reply({ content: "Release digests are disabled for this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "history") {
      await this.showHistory(interaction);
      return true;
    }
    if (action === "spotlights") {
      await this.showSpotlights(interaction);
      return true;
    }
    if (action === "daily-configure") { await this.openDailyConfig(interaction); return true; }
    if (action === "daily-submit") { await this.openDailySubmit(interaction); return true; }
    if (action === "daily-review") { await this.reviewDaily(interaction); return true; }
    if (action === "daily-pause") {
      if (!isGuildManager(interaction)) { await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral }); return true; }
      await disableDailySchedule(interaction.guildId);
      await interaction.reply({ content: "Daily Drop scheduling is paused for this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "daily-approve" || action === "daily-reject") {
      if (!isGuildManager(interaction) || !id) { await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral }); return true; }
      await reviewDailyItem(interaction.guildId, id, interaction.user.id, action === "daily-approve");
      await interaction.reply({ content: action === "daily-approve" ? "Daily Drop item approved." : "Daily Drop item rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "candidate-approve" || action === "candidate-reject") {
      if (!isGuildManager(interaction) || !id) { await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral }); return true; }
      await reviewRankingCandidate(interaction.guildId, id, action === "candidate-approve");
      await interaction.reply({ content: action === "candidate-approve" ? "Ranking candidate approved." : "Ranking candidate rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "rsvp" || action === "withdraw") {
      if (!id) return false;
      const result = await setSessionRsvp(interaction.guildId, id, interaction.user.id, action === "rsvp");
      await interaction.reply({ content: action === "rsvp"
        ? result === "waitlist" ? "The session is full. You are on its waitlist." : "Your RSVP is confirmed."
        : "Your RSVP has been withdrawn. A waitlisted member is promoted when a place opens.",
        flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "daily-pause") {
      if (!isGuildManager(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await disableDailySchedule(interaction.guildId);
      await interaction.reply({ content: "Daily Drop scheduling is paused for this server.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "daily-approve" || action === "daily-reject") {
      if (!isGuildManager(interaction) || !id) {
        await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await reviewDailyItem(interaction.guildId, id, interaction.user.id, action === "daily-approve");
      await interaction.reply({ content: action === "daily-approve" ? "Daily Drop item approved." : "Daily Drop item rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "candidate-approve" || action === "candidate-reject") {
      if (!isGuildManager(interaction) || !id) {
        await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await reviewRankingCandidate(interaction.guildId, id, action === "candidate-approve");
      await interaction.reply({ content: action === "candidate-approve" ? "Ranking candidate approved." : "Ranking candidate rejected.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "rsvp" || action === "withdraw") {
      if (!id) return false;
      const result = await setSessionRsvp(interaction.guildId, id, interaction.user.id, action === "rsvp");
      await interaction.reply({ content: action === "rsvp"
        ? result === "waitlist" ? "The session is full. You are on its waitlist." : "Your RSVP is confirmed."
        : "Your RSVP has been withdrawn. If a place opened, the next waitlisted member was promoted.",
        flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "ranking-create") {
      await interaction.showModal(modal("community:ranking-create", "Create a ranking", [
        { id: "title", label: "Ranking title", max: 180 },
        { id: "description", label: "What are members ranking?", max: 800, required: false, paragraph: true },
        { id: "closes", label: "Close date (optional ISO time with timezone)", max: 40, required: false },
      ]));
      return true;
    }
    if (action === "ranking-candidate") {
      await interaction.showModal(modal("community:ranking-candidate", "Add a ranking candidate", [
        { id: "ranking_id", label: "Open ranking ID", max: 20 },
        { id: "title", label: "Candidate title", max: 200 },
        { id: "source", label: "HTTPS source link (optional)", max: 400, required: false },
      ]));
      return true;
    }
    if (action === "ranking-vote") {
      const rankings = await query<{ id: string; title: string }>(
        "SELECT id, title FROM community_rankings WHERE guild_id = $1 AND status = 'open' ORDER BY created_at DESC LIMIT 25",
        [interaction.guildId],
      );
      if (!rankings.length) {
        await interaction.reply({ content: "There are no open rankings to vote in.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
        .setCustomId("community:ranking-select")
        .setPlaceholder("Choose a ranking")
        .addOptions(rankings.map((ranking) => ({ label: ranking.title.slice(0, 100), value: ranking.id }))));
      await interaction.reply({ content: "Choose the ranking you want to vote in.", components: [select], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "ranking-review") { await this.reviewCandidate(interaction); return true; }
    if (action === "session-create") {
      await interaction.showModal(modal("community:session-create", "Create a community session", [
        { id: "title", label: "Session title", max: 180 },
        { id: "description", label: "Details / participation notes", max: 800, required: false, paragraph: true },
        { id: "activity", label: "Activity: watch, read, play or discuss", max: 16 },
        { id: "when", label: "Future date/time with timezone (ISO-8601)", max: 40, placeholder: "2026-12-12T19:00+00:00" },
        { id: "capacity", label: "Capacity (optional number)", max: 3, required: false },
      ]));
      return true;
    }
    if (action === "session-rsvp") {
      const sessions = await listUpcomingSessions(interaction.guildId);
      if (!sessions.length) {
        await interaction.reply({ content: "There are no upcoming sessions to RSVP to.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const select = new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
        .setCustomId("community:session-select:rsvp")
        .setPlaceholder("Choose a session")
        .addOptions(sessions.map((session) => ({ label: session.title.slice(0, 100), value: session.id }))));
      await interaction.reply({ content: "Choose a session to RSVP to.", components: [select], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "discussion-create") {
      await interaction.showModal(modal("community:discussion-create", "Start a media discussion", [
        { id: "title", label: "Discussion title", max: 180 },
        { id: "prompt", label: "Discussion prompt / ground rules", max: 900, paragraph: true },
        { id: "media_title", label: "Linked media title (optional)", max: 200, required: false },
        { id: "media_url", label: "HTTPS media link (optional)", max: 400, required: false },
        { id: "spoiler", label: "Spoiler boundary (e.g. Episode 8, Volume 4)", max: 120, required: false },
      ]));
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, mode] = interaction.customId.split(":");
    const id = interaction.values[0];
    if (!id) return false;
    if (action === "ranking-select") {
      const candidates = await query<{ id: string; title: string }>(
        "SELECT id, title FROM community_ranking_candidates WHERE ranking_id = $1 AND status = 'approved' ORDER BY created_at ASC LIMIT 25",
        [id],
      );
      if (!candidates.length) {
        await interaction.reply({ content: "This ranking has no approved candidates yet.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.reply({
        content: `Choose your vote in ranking #${id}. You can change it while the ranking remains open.`,
        components: [new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(new StringSelectMenuBuilder()
          .setCustomId(`community:candidate-select:${id}`)
          .setPlaceholder("Choose a candidate")
          .addOptions(candidates.map((candidate) => ({ label: candidate.title.slice(0, 100), value: candidate.id }))))],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "reading-vote") {
      await voteForReading(interaction.guildId,interaction.user.id,id);
      await interaction.reply({content:"Your community reading vote was saved. You may change it while nominations remain open.",flags:MessageFlags.Ephemeral});
      return true;
    }
    if (action === "candidate-select" && mode) {
      await voteForRanking(interaction.guildId, interaction.user.id, mode, id);
      await interaction.reply({ content: "Your vote was saved. You may change it while the ranking is open.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "session-select" && mode === "rsvp") {
      const result = await setSessionRsvp(interaction.guildId, id, interaction.user.id, true);
      await interaction.reply({ content: result === "waitlist" ? "The session is full. You have been added to its waitlist." : "Your RSVP is confirmed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [prefix, action] = interaction.customId.split(":");
    if (prefix !== "community") return false;
    try {
      if (action === "daily-configure") {
        if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required to configure Daily Drop.");
        const channelValue = interaction.fields.getTextInputValue("channel");
        const match = channelValue.match(/\d{17,20}/);
        const channel = match ? await interaction.guild!.channels.fetch(match[0]).catch(() => null) : null;
        if (!channel?.isTextBased() || !("send" in channel)) throw new Error("Choose a valid text channel in this server.");
        const timeZone = interaction.fields.getTextInputValue("timezone");
        const localTime = interaction.fields.getTextInputValue("local_time");
        const format = interaction.fields.getTextInputValue("format") as "question" | "quote" | "trivia" | "recommendation" | "archive_spotlight" | "mystery";
        const next = await saveDailySchedule(interaction.guildId, interaction.user.id, channel.id, timeZone, localTime, format);
        await interaction.reply({ content: `Daily Drop is scheduled for ${localTime} (${timeZone}). Next delivery: <t:${Math.floor(next.getTime() / 1000)}:F> in <#${channel.id}>.`, flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "daily-submit") {
        const format = interaction.fields.getTextInputValue("format") as "question" | "quote" | "trivia" | "recommendation" | "archive_spotlight" | "mystery";
        const id = await submitDailyItem(
          interaction.guildId,
          interaction.user.id,
          format,
          interaction.fields.getTextInputValue("title"),
          interaction.fields.getTextInputValue("content"),
          interaction.fields.getTextInputValue("source") || undefined,
        );
        await interaction.reply({ content: `Daily Drop item #${id} was submitted. It will not be scheduled until a server moderator approves it.`, flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "ranking-create") {
        const title = interaction.fields.getTextInputValue("title");
        const description = interaction.fields.getTextInputValue("description");
        const closeText = interaction.fields.getTextInputValue("closes").trim();
        let closesAt: Date | null = null;
        if (closeText) {
          const parsed = new Date(closeText);
          if (!Number.isFinite(parsed.getTime()) || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(closeText) || parsed.getTime() <= Date.now()) {
            throw new Error("The close time must be a future ISO-8601 date that includes a timezone offset.");
          }
          closesAt = parsed;
        }
        const id = await createRanking(interaction.guildId, interaction.user.id, title, description, closesAt);
        await interaction.reply({ content: `Ranking #${id} is open. Candidate submissions need moderator approval before they appear in voting.`, flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "ranking-candidate") {
        const id = await addRankingCandidate(
          interaction.guildId,
          interaction.fields.getTextInputValue("ranking_id"),
          interaction.user.id,
          interaction.fields.getTextInputValue("title"),
          interaction.fields.getTextInputValue("source") || undefined,
        );
        await interaction.reply({ content: `Candidate #${id} was submitted for moderator review.`, flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "session-create") {
        const activity = interaction.fields.getTextInputValue("activity").trim().toLowerCase() as "watch" | "read" | "play" | "discuss";
        if (!ACTIVITIES.some((item) => item.value === activity)) throw new Error("Choose watch, read, play or discuss for the session type.");
        const scheduledAtText = interaction.fields.getTextInputValue("when").trim();
        const scheduledAt = new Date(scheduledAtText);
        if (!Number.isFinite(scheduledAt.getTime()) || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(scheduledAtText)) {
          throw new Error("The session date/time must be ISO-8601 and include a timezone offset.");
        }
        const capacityText = interaction.fields.getTextInputValue("capacity").trim();
        const capacity = capacityText ? Number(capacityText) : undefined;
        if (capacity !== undefined && (!Number.isInteger(capacity) || capacity < 2 || capacity > 200)) {
          throw new Error("Capacity must be an integer from 2 to 200.");
        }
        const sessionId = await createCommunitySession({
          guildId: interaction.guildId,
          channelId: interaction.channelId ?? "",
          creatorId: interaction.user.id,
          title: interaction.fields.getTextInputValue("title"),
          description: interaction.fields.getTextInputValue("description"),
          activity,
          scheduledAt,
          capacity,
        });
        await interaction.reply({ content: `Community session #${sessionId} was scheduled.`, flags: MessageFlags.Ephemeral });
        const announcement = new EmbedBuilder()
          .setColor(0x5865f2)
          .setTitle(`${emoji.event} ${interaction.fields.getTextInputValue("title")}`)
          .setDescription(`${formatActivity(activity)} together · Hosted by <@${interaction.user.id}>\n${interaction.fields.getTextInputValue("description")}\n\nStarts <t:${Math.floor(scheduledAt.getTime() / 1000)}:F>\nSession ID: ${sessionId}`)
          .setFooter({ text: "RSVPs and waitlist are recorded per server." });
        const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId(`community:rsvp:${sessionId}`).setLabel("I'm going").setStyle(ButtonStyle.Success),
          new ButtonBuilder().setCustomId(`community:withdraw:${sessionId}`).setLabel("Withdraw").setStyle(ButtonStyle.Secondary),
        );
        const channel = interaction.channel;
        if (channel?.isTextBased() && "send" in channel) {
          const message = await (channel as TextChannel).send({ embeds: [announcement], components: [row], allowedMentions: { parse: [] } });
          await query("UPDATE community_sessions SET message_id = $1 WHERE id = $2 AND guild_id = $3", [message.id, sessionId, interaction.guildId]);
          try {
            const thread = await (channel as TextChannel).threads.create({
              name: `${interaction.fields.getTextInputValue("title")} · session`.slice(0, 100),
              startMessage: message.id,
              autoArchiveDuration: 1440,
              reason: "Community session discussion thread",
            });
            await query("UPDATE community_sessions SET thread_id = $1 WHERE id = $2 AND guild_id = $3", [thread.id, sessionId, interaction.guildId]);
          } catch {
            // The announcement remains usable even without public-thread permissions.
          }
          try {
            const guild = interaction.guild!;
            const event = await guild.scheduledEvents.create({
              name: cleanText(interaction.fields.getTextInputValue("title"), 100),
              scheduledStartTime: scheduledAt,
              scheduledEndTime: new Date(scheduledAt.getTime() + 60 * 60 * 1000),
              privacyLevel: GuildScheduledEventPrivacyLevel.GuildOnly,
              entityType: GuildScheduledEventEntityType.External,
              entityMetadata: { location: "Discord" },
              description: cleanText(interaction.fields.getTextInputValue("description"), 1_000),
            });
            await query("UPDATE community_sessions SET scheduled_event_id = $1 WHERE id = $2 AND guild_id = $3", [event.id, sessionId, interaction.guildId]);
          } catch {
            // Thread/announcement remains the supported fallback when event creation permissions are unavailable.
          }
        }
        return true;
      }
      if (action === "discussion-create") {
        const title = interaction.fields.getTextInputValue("title");
        const prompt = interaction.fields.getTextInputValue("prompt");
        const mediaUrl = interaction.fields.getTextInputValue("media_url");
        const id = await createSpoilerDiscussion({
          guildId: interaction.guildId,
          channelId: interaction.channelId ?? "",
          creatorId: interaction.user.id,
          title,
          prompt,
          mediaTitle: interaction.fields.getTextInputValue("media_title"),
          mediaUrl: mediaUrl || undefined,
          spoilerBoundary: interaction.fields.getTextInputValue("spoiler"),
          spoilerWarning: "Mark story spoilers clearly and respect the stated reading/watching boundary.",
        });
        const channel = interaction.channel;
        if (channel?.isTextBased() && "threads" in channel && "send" in channel) {
          const announcement = await (channel as TextChannel).send({
            embeds: [homeEmbed(`${emoji.discussion} ${title}`, `${prompt}\n\n${interaction.fields.getTextInputValue("media_title") ? `Media: ${interaction.fields.getTextInputValue("media_title")}\n` : ""}${interaction.fields.getTextInputValue("spoiler") ? `Spoiler boundary: ${interaction.fields.getTextInputValue("spoiler")}\n` : ""}Please mark spoilers and avoid discussing events beyond the stated boundary.`)],
            allowedMentions: { parse: [] },
          });
          const thread = await (channel as TextChannel).threads.create({
            name: title.slice(0, 100),
            startMessage: announcement.id,
            autoArchiveDuration: 1440,
            reason: "Community discussion thread",
          });
          await query("UPDATE community_discussions SET thread_id = $1 WHERE id = $2 AND guild_id = $3", [thread.id, id, interaction.guildId]);
          await interaction.reply({ content: `Discussion #${id} opened in <#${thread.id}>.`, flags: MessageFlags.Ephemeral });
        } else {
          await interaction.reply({ content: `Discussion #${id} was saved, but this channel cannot create public threads.`, flags: MessageFlags.Ephemeral });
        }
        return true;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The community action failed.";
      const issueHash = await createInteractionIssueLog(interaction, "/community", error, { action: "component" });
      await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  private async configureDaily(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required to configure Daily Drop.");
    const channelId = interaction.options.getString("channel")?.match(/\d{17,20}/)?.[0];
    const channel = channelId ? await interaction.guild!.channels.fetch(channelId).catch(() => null) : null;
    if (!channel?.isTextBased() || !("send" in channel)) throw new Error("Choose a valid text channel in this server.");
    const timeZone = interaction.options.getString("time_zone");
    const localTime = interaction.options.getString("local_time");
    const format = interaction.options.getString("format") as "question" | "quote" | "trivia" | "recommendation" | "archive_spotlight" | "mystery" | null;
    if (!timeZone || !localTime || !format) throw new Error("Provide channel, time_zone, local_time and format.");
    const next = await saveDailySchedule(interaction.guildId!, interaction.user.id, channel.id, timeZone, localTime, format);
    await interaction.reply({ content: `Daily Drop is scheduled for ${localTime} (${timeZone}). Next delivery: <t:${Math.floor(next.getTime() / 1000)}:F> in <#${channel.id}>.`, flags: MessageFlags.Ephemeral });
  }

  private async openDailyConfig(interaction: ButtonInteraction): Promise<void> {
    if (!isGuildManager(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required.", flags: MessageFlags.Ephemeral });
      return;
    }
    const channel = interaction.channelId ?? "";
    await interaction.showModal(modal("community:daily-configure", "Configure Daily Drop", [
      { id: "channel", label: "Destination channel mention or ID", max: 50, placeholder: channel ? `<#${channel}>` : "#channel" },
      { id: "timezone", label: "IANA timezone", max: 80, placeholder: "Europe/Dublin" },
      { id: "local_time", label: "Local delivery time (HH:MM)", max: 5, placeholder: "18:00" },
      { id: "format", label: "Daily format", max: 32, placeholder: "question, quote, trivia, recommendation, archive_spotlight or mystery" },
    ]));
  }

  private async submitDaily(interaction: ChatInputCommandInteraction): Promise<void> {
    const format = interaction.options.getString("format") as "question" | "quote" | "trivia" | "recommendation" | "mystery" | null;
    const title = interaction.options.getString("title");
    const content = interaction.options.getString("content");
    if (!format || !title || !content) throw new Error("Provide format, title and content.");
    const id = await submitDailyItem(interaction.guildId!, interaction.user.id, format, title, content, interaction.options.getString("source_url") ?? undefined);
    await interaction.reply({ content: `Daily Drop item #${id} was submitted for moderator review.`, flags: MessageFlags.Ephemeral });
  }

  private async openDailySubmit(interaction: ButtonInteraction): Promise<void> {
    await interaction.showModal(modal("community:daily-submit", "Submit a Daily Drop item", [
      { id: "format", label: "Format: question, quote, trivia, recommendation, mystery", max: 32 },
      { id: "title", label: "Item title", max: 200 },
      { id: "content", label: "Prompt / text (quotes max 280 characters)", max: 1_500, paragraph: true },
      { id: "source", label: "HTTPS source link (optional)", max: 400, required: false },
    ]));
  }

  private async reviewDaily(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    if (!interaction.guildId || !isGuildManager(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to review Daily Drop items.", flags: MessageFlags.Ephemeral });
      return;
    }
    const rows = await query<{ id: string; format: string; title: string; content: string; created_by: string }>(
      "SELECT id, format, title, content, created_by FROM community_daily_items WHERE guild_id = $1 AND status = 'pending' ORDER BY created_at ASC LIMIT 10",
      [interaction.guildId],
    );
    if (!rows.length) {
      await interaction.reply({ content: "There are no pending Daily Drop submissions.", flags: MessageFlags.Ephemeral });
      return;
    }
    const first = rows[0]!;
    await interaction.reply({
      embeds: [homeEmbed("Daily Drop review queue", "Only approved items can be scheduled.", rows.slice(0, 8).map((row) => ({
        name: `#${row.id} · ${row.format} · ${safeDisplay(row.title)}`,
        value: `${safeDisplay(row.content, 300)}\nContributor: <@${row.created_by}>`,
        inline: false,
      })))],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(`community:daily-approve:${first.id}`).setLabel("Approve first").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId(`community:daily-reject:${first.id}`).setLabel("Reject first").setStyle(ButtonStyle.Danger),
      )],
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async addCandidate(interaction: ChatInputCommandInteraction): Promise<void> {
    const rankingId = interaction.options.getString("ranking_id");
    const title = interaction.options.getString("title");
    if (!rankingId || !title) throw new Error("Provide ranking_id and title.");
    const id = await addRankingCandidate(interaction.guildId!, rankingId, interaction.user.id, title, interaction.options.getString("source_url") ?? undefined);
    await interaction.reply({ content: `Candidate #${id} is awaiting moderator review.`, flags: MessageFlags.Ephemeral });
  }

  private async reviewCandidate(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    if (!interaction.guildId || !isGuildManager(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to review ranking candidates.", flags: MessageFlags.Ephemeral });
      return;
    }
    const rows = await query<{ id: string; title: string; question: string; ranking_id: string }>(
      `SELECT c.id, c.title, r.title AS question, r.id AS ranking_id
       FROM community_ranking_candidates c JOIN community_rankings r ON r.id = c.ranking_id
       WHERE r.guild_id = $1 AND r.status = 'open' AND c.status = 'pending'
       ORDER BY c.created_at ASC LIMIT 10`,
      [interaction.guildId],
    );
    if (!rows.length) {
      await interaction.reply({ content: "There are no pending ranking candidates.", flags: MessageFlags.Ephemeral });
      return;
    }
    const first = rows[0]!;
    await interaction.reply({
      embeds: [homeEmbed("Ranking candidate review", "Approve a candidate before it appears in the public vote.", rows.map((row) => ({
        name: `#${row.id} · ${safeDisplay(row.title)}`,
        value: `Ranking #${row.ranking_id} · ${safeDisplay(row.question)}`,
        inline: false,
      })))],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(`community:candidate-approve:${first.id}`).setLabel("Approve first").setStyle(ButtonStyle.Success),
        new ButtonBuilder().setCustomId(`community:candidate-reject:${first.id}`).setLabel("Reject first").setStyle(ButtonStyle.Danger),
      )],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async vote(interaction: ChatInputCommandInteraction): Promise<void> {
    const rankingId = interaction.options.getString("ranking_id");
    const candidateId = interaction.options.getString("candidate_id");
    if (!rankingId || !candidateId) throw new Error("Provide ranking_id and candidate_id.");
    await voteForRanking(interaction.guildId!, interaction.user.id, rankingId, candidateId);
    await interaction.reply({ content: "Your vote was recorded. You can change it while the ranking is open.", flags: MessageFlags.Ephemeral });
  }

  private async closeRankingCommand(interaction: ChatInputCommandInteraction): Promise<void> {
    const rankingId = interaction.options.getString("ranking_id");
    if (!rankingId) throw new Error("Provide ranking_id.");
    await closeRanking(interaction.guildId!, rankingId, interaction.user.id, isGuildManager(interaction));
    const results = await rankingResults(interaction.guildId!, rankingId);
    await interaction.reply({
      embeds: [homeEmbed("Ranking results", "The ranking is closed. Votes are shown in descending order; ties retain earliest candidate order.", results.map((row) => ({
        name: safeDisplay(row.title),
        value: `${row.votes} vote(s)`,
        inline: true,
      })))],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async createSession(interaction: ChatInputCommandInteraction): Promise<void> {
    const title = interaction.options.getString("title");
    const when = interaction.options.getString("scheduled_at");
    const activity = interaction.options.getString("activity") as "watch" | "read" | "play" | "discuss" | null;
    if (!title || !when || !activity) throw new Error("Provide title, scheduled_at and activity.");
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(when)) throw new Error("scheduled_at must include an explicit timezone offset.");
    const scheduledAt = new Date(when);
    if (!Number.isFinite(scheduledAt.getTime())) throw new Error("scheduled_at is not a valid ISO-8601 date.");
    const sessionId = await createCommunitySession({
      guildId: interaction.guildId!,
      channelId: interaction.channelId ?? "",
      creatorId: interaction.user.id,
      title,
      description: interaction.options.getString("content") ?? "",
      activity,
      mediaTitle: interaction.options.getString("media_title") ?? undefined,
      mediaUrl: interaction.options.getString("media_url") ?? undefined,
      scheduledAt,
      capacity: interaction.options.getInteger("capacity") ?? undefined,
    });
    await interaction.reply({ content: `Community session #${sessionId} was scheduled.`, flags: MessageFlags.Ephemeral });
  }

  private async rsvp(interaction: ChatInputCommandInteraction, going: boolean): Promise<void> {
    const sessionId = interaction.options.getString("session_id");
    if (!sessionId) throw new Error("Provide session_id.");
    const result = await setSessionRsvp(interaction.guildId!, sessionId, interaction.user.id, going);
    await interaction.reply({ content: going
      ? result === "waitlist" ? "The session is full. You have been added to the waitlist." : "Your RSVP is confirmed."
      : "Your RSVP has been withdrawn. The next person on the waitlist has been promoted if a place opened.",
      flags: MessageFlags.Ephemeral });
  }

  private async closeSession(interaction: ChatInputCommandInteraction): Promise<void> {
    const id = interaction.options.getString("session_id");
    if (!id) throw new Error("Provide session_id.");
    const session = await getCommunitySession(interaction.guildId!, id);
    if (!session) throw new Error("That session was not found in this server.");
    if (session.host_id !== interaction.user.id && !isGuildManager(interaction)) throw new Error("Only the host or a server manager can close the session.");
    await query("UPDATE community_sessions SET status = 'cancelled' WHERE id = $1 AND guild_id = $2 AND status IN ('scheduled','open')", [id, interaction.guildId]);
    await interaction.reply({ content: `Community session #${id} has been cancelled.`, flags: MessageFlags.Ephemeral });
  }

  private async createDiscussion(interaction: ChatInputCommandInteraction): Promise<void> {
    const title = interaction.options.getString("title");
    const prompt = interaction.options.getString("content");
    if (!title || !prompt) throw new Error("Provide title and content for the discussion.");
    const id = await createSpoilerDiscussion({
      guildId: interaction.guildId!,
      channelId: interaction.channelId ?? "",
      creatorId: interaction.user.id,
      title,
      prompt,
      mediaTitle: interaction.options.getString("media_title") ?? undefined,
      mediaUrl: interaction.options.getString("media_url") ?? undefined,
      spoilerBoundary: interaction.options.getString("spoiler_boundary") ?? undefined,
      spoilerWarning: "Keep plot spoilers marked and respect the stated boundary.",
    });
    await interaction.reply({ content: `Discussion #${id} has been saved.`, flags: MessageFlags.Ephemeral });
  }

  private async closeDiscussionCommand(interaction: ChatInputCommandInteraction): Promise<void> {
    const id = interaction.options.getString("discussion_id");
    if (!id) throw new Error("Provide discussion_id.");
    const threadId = await closeDiscussion(interaction.guildId!, id, interaction.user.id, isGuildManager(interaction));
    if (threadId) {
      const thread = await interaction.guild!.channels.fetch(threadId).catch(() => null);
      if (thread && "setArchived" in thread) {
        await (thread as unknown as { setArchived(archived: boolean, reason?: string): Promise<unknown> }).setArchived(true, "Community discussion closed").catch(() => null);
      }
    }
    await interaction.reply({ content: `Discussion #${id} is closed.`, flags: MessageFlags.Ephemeral });
  }

  private async nominateReading(interaction: ChatInputCommandInteraction): Promise<void> {
    const title=interaction.options.getString("title");
    const category=interaction.options.getString("reading_category");
    if(!title||!category) throw new Error("Provide a title and reading_category.");
    if(!interaction.channel?.isTextBased()) throw new Error("Nominate community reads from a server text channel.");
    const id=await nominateReading({
      guildId:interaction.guildId!,
      channelId:interaction.channelId!,
      proposerId:interaction.user.id,
      title,
      category,
      sourceUrl:interaction.options.getString("source_url")??undefined,
    });
    await interaction.reply({content:`Community read nomination #${id} was saved for this server. Use /community action:reading-list to browse and vote.`,flags:MessageFlags.Ephemeral});
  }

  private async showReadingNominations(interaction: ChatInputCommandInteraction): Promise<void> {
    const nominations=await listReadingNominations(interaction.guildId!);
    if(!nominations.length){
      await interaction.reply({content:"There are no open community reading nominations in this server.",flags:MessageFlags.Ephemeral});
      return;
    }
    const fields=nominations.slice(0,10).map(item=>({
      name:"#"+item.id+" · "+safeDisplay(item.title,140),
      value:item.category+" · "+(item.vote_count??0)+" vote(s)"+(item.source_url?" · [Source]("+item.source_url+")":""),
      inline:false,
    }));
    const select=new StringSelectMenuBuilder()
      .setCustomId("community:reading-vote")
      .setPlaceholder("Choose a nominated read to vote for")
      .addOptions(nominations.slice(0,25).map(item=>({
        label:item.title.slice(0,90),
        description:item.category+" · "+(item.vote_count??0)+" vote(s)",
        value:item.id,
      })));
    await interaction.reply({
      embeds:[homeEmbed("Community Reading Club","Guild-only nominations · One active vote per member. Votes can be changed while nominations remain open.",fields)],
      components:[new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
      flags:MessageFlags.Ephemeral,
      allowedMentions:{parse:[]},
    });
  }

  private async selectReading(interaction: ChatInputCommandInteraction): Promise<void> {
    if(!isGuildManager(interaction)) throw new Error("Manage Server permission is required to select the next community read.");
    await interaction.deferReply({flags:MessageFlags.Ephemeral});
    const selected=await selectNextReading(interaction.guildId!,interaction.options.getString("reading_nomination_id")??undefined);
    const channel=interaction.channel;
    if(channel?.isTextBased()&&"send" in channel){
      await (channel as TextChannel).send({
        content:`Community read selected: **${safeDisplay(selected.title,180)}** (${selected.category}).${selected.source_url?"\nSource: "+selected.source_url:""}\nA moderator can schedule its spoiler-aware discussion using /community action:reading-schedule reading_nomination_id:${selected.id}.`,
        allowedMentions:{parse:[]},
      });
    }
    await interaction.editReply({content:`Nomination #${selected.id} was selected as this server's next community read. The remaining open nominations were closed.`});
  }

  private async scheduleReadingDiscussion(interaction: ChatInputCommandInteraction): Promise<void> {
    if(!isGuildManager(interaction)) throw new Error("Manage Server permission is required to schedule the community reading discussion.");
    const nominationId=interaction.options.getString("reading_nomination_id");
    const when=interaction.options.getString("scheduled_at");
    if(!nominationId||!when) throw new Error("Provide reading_nomination_id and scheduled_at.");
    const scheduledAt=parseReadingScheduleTime(when);
    await interaction.deferReply({flags:MessageFlags.Ephemeral});
    const row=await queryOne<{id:string;title:string;category:string;source_url:string|null;status:string}>(
      "SELECT id,title,category,source_url,status FROM community_reading_nominations WHERE id = $1 AND guild_id = $2",
      [nominationId,interaction.guildId],
    );
    if(!row||row.status!=="selected") throw new Error("Select this community read before scheduling its discussion.");
    const channel=interaction.channel;
    if(!channel?.isTextBased()||!("threads" in channel)||!("send" in channel)) throw new Error("Schedule reading discussions from a text channel that supports public threads.");
    const textChannel=channel as TextChannel;
    const announcement=await textChannel.send({
      embeds:[homeEmbed("Community Reading Club · "+safeDisplay(row.title,150),`Selected work: ${safeDisplay(row.title,180)} (${row.category})\nScheduled for <t:${Math.floor(scheduledAt.getTime()/1000)}:F>.\n\nKeep plot spoilers inside Discord spoiler tags and respect the shared reading boundary.`,row.source_url?[{name:"Source",value:"[Open metadata source]("+row.source_url+")"}]:[])],
      allowedMentions:{parse:[]},
    });
    let thread: Awaited<ReturnType<TextChannel["threads"]["create"]>>|null=null;
    try {
      thread=await textChannel.threads.create({
        name:(row.title+" · Reading Club").slice(0,100),
        startMessage:announcement.id,
        autoArchiveDuration:10080,
        reason:"Scheduled community reading discussion",
      });
      await thread.send({
        content:`Community reading discussion · ${safeDisplay(row.title,180)}\nScheduled for <t:${Math.floor(scheduledAt.getTime()/1000)}:F>.\nMark plot spoilers with Discord spoiler tags (||like this||) and keep unmarked messages within the shared reading boundary.`,
        allowedMentions:{parse:[]},
      });
      await attachReadingDiscussion({guildId:interaction.guildId!,nominationId,channelId:interaction.channelId!,threadId:thread.id,scheduledAt});
    } catch(error) {
      if(thread) await thread.delete("Could not persist the scheduled Reading Club discussion").catch(()=>undefined);
      await announcement.delete().catch(()=>undefined);
      throw error;
    }
    await interaction.editReply({content:`Reading discussion #${nominationId} created in <#${thread.id}> for <t:${Math.floor(scheduledAt.getTime()/1000)}:F>.`});
  }

  private async startMediaNight(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.channel?.isTextBased() || !("send" in interaction.channel)) {
      throw new Error("Start Media Night in a server text channel so its vote can be posted publicly.");
    }
    const category = (interaction.options.getString("media_category") ?? "ANIME") as "ANIME" | "MANGA";
    const mood = (interaction.options.getString("media_mood") ?? "all") as "all" | "cozy" | "comedy" | "adventure" | "mystery" | "romance" | "drama";
    const hours = interaction.options.getInteger("duration_hours") ?? 3;
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const candidates = filterMediaNightCandidates(await this.anilist.mediaNightCandidates(category), mood);
    const selected = sampleMediaNightCandidates(candidates, 5);
    if (selected.length < 2) {
      await interaction.editReply("AniList did not return enough distinct candidates for that mood. Try a broader mood or the full list.");
      return;
    }
    const closesAt = new Date(Date.now() + hours * 60 * 60 * 1000);
    const title = category === "ANIME" ? "Anime Media Night" : "Manga Media Night";
    const session = await createMediaNight({
      guildId: interaction.guildId!,
      channelId: interaction.channelId,
      creatorId: interaction.user.id,
      title,
      description: `${mood === "all" ? "All moods" : mood[0]!.toUpperCase() + mood.slice(1)} · ${hours} hour vote`,
      closesAt,
      candidates: selected,
    });
    const fields = session.candidates.map((candidate, index) => ({
      name: `${index + 1}. ${safeDisplay(candidate.title, 180)}`,
      value: `[AniList source](${candidate.url})${candidate.year ? ` · ${candidate.year}` : ""}`,
      inline: false,
    }));
    const message = await (interaction.channel as TextChannel).send({
      embeds: [homeEmbed(title, `Choose one title below. Votes are final and locked once cast. Voting closes <t:${Math.floor(closesAt.getTime() / 1000)}:R>. Provider-tagged adult and sensitive-content entries are excluded; this is a metadata filter, not an age rating.`, fields)],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        ...session.candidates.map((candidate) => new ButtonBuilder()
          .setCustomId(`community:media-night-vote:${session.id}:${candidate.id}`)
          .setLabel(candidate.title.slice(0, 80))
          .setStyle(ButtonStyle.Primary)),
      )],
      allowedMentions: { parse: [] },
    });
    await interaction.editReply(`Media Night #${session.id} is live in <#${interaction.channelId}>: ${message.url}`);
  }

  private async configureReleaseCalendar(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required to configure release digests.");
    const channelInput = interaction.options.getString("channel");
    const channelMatch = channelInput?.match(/^(?:<#(\d{17,20})>|(\d{17,20}))$/);
    const channelId = channelMatch?.[1] ?? channelMatch?.[2] ?? null;
    const timeZone = interaction.options.getString("time_zone");
    const localTime = interaction.options.getString("local_time");
    const cadence = interaction.options.getString("release_cadence") as "daily" | "weekly" | null;
    const categories = (interaction.options.getString("release_categories") ?? "anime,tv,movies").split(",");
    const weekday = interaction.options.getInteger("weekday") ?? 1;
    const region = interaction.options.getString("region") ?? "IE";
    if (!channelId || !timeZone || !localTime || !cadence) {
      throw new Error("Provide channel, time_zone, local_time and release_cadence. Choose release_categories and weekday for a weekly digest.");
    }
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const target = await interaction.guild!.channels.fetch(channelId);
    if (!target?.isTextBased() || !("send" in target)) throw new Error("Choose a server text channel where release digests can be posted.");
    const me = interaction.guild!.members.me;
    if (!me || !target.permissionsFor(me)?.has(["ViewChannel", "SendMessages", "EmbedLinks"])) {
      throw new Error("The bot needs View Channel, Send Messages and Embed Links in the selected digest channel.");
    }
    const next = await saveReleaseSchedule({
      guildId: interaction.guildId!,
      channelId,
      actorId: interaction.user.id,
      timeZone,
      localTime,
      cadence,
      weekday,
      categories,
      region,
    });
    await interaction.editReply(`Release digests are enabled in <#${channelId}>. Next run: <t:${Math.floor(next.getTime() / 1000)}:F>. Categories: ${categories.join(", ")} · Region: ${region.toUpperCase()}.`);
  }

  private async disableReleaseCalendar(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isGuildManager(interaction)) throw new Error("Manage Server permission is required to disable release digests.");
    await disableReleaseSchedule(interaction.guildId!);
    await interaction.reply({ content: "Release digests are disabled for this server. The on-demand calendar remains available.", flags: MessageFlags.Ephemeral });
  }

  private async showCalendar(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    const from = new Date();
    const to = new Date(from.getTime() + 14 * 24 * 60 * 60 * 1000);
    const schedule = await getReleaseSchedule(interaction.guildId!);
    const region = schedule?.region ?? "IE";
    const categories = schedule?.categories ?? ["anime", "tv", "movies"];
    const calendar = await upcomingProviderReleases(this.anilist, this.tmdb, from, to, region, categories);
    const settings = schedule?.enabled
      ? `Digest: ${schedule.cadence} · ${schedule.local_time} ${schedule.time_zone} · ${region} · ${categories.join(", ")} · <#${schedule.channel_id}>.`
      : "Automatic digests are currently disabled. A server manager can configure them with /community action:calendar-configure.";
    const providerNotice = calendar.unavailableProviders.length
      ? `Partial results. Unavailable providers: ${calendar.unavailableProviders.join(", ")}. Other returned results are still shown.\n\n`
      : "";
    const fields = calendar.results.slice(0, 12).map((item) => ({
      name: `${safeDisplay(item.title, 180)} · <t:${Math.floor(item.when.getTime() / 1000)}:R>`,
      value: `[${item.provider} source](${item.url})`,
      inline: false,
    }));
    if (!fields.length && calendar.unavailableProviders.length) {
      fields.push({ name: "Provider data unavailable", value: `No results could be retrieved from: ${calendar.unavailableProviders.join(", ")}.`, inline: false });
    } else if (!fields.length) {
      fields.push({ name: "No releases returned", value: "No provider-dated anime airings, TV episodes or movie releases were found in the selected categories for this window.", inline: false });
    }
    await interaction.reply({
      embeds: [homeEmbed("Release calendar · Next 14 days", `${providerNotice}Dates come directly from AniList and TMDB. Missing provider data is not guessed.\n\n${settings}`, fields)],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("community:calendar-configure").setLabel("Configure digests").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("community:calendar-disable").setLabel("Disable digests").setStyle(ButtonStyle.Secondary).setDisabled(!schedule?.enabled),
      )],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async showSpotlights(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    const spotlights = await listArchiveSpotlights(interaction.guildId!);
    const embeds = spotlights.slice(0, 8).map(item => new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle(safeDisplay(item.title, 250))
      .setDescription(`Archive #${item.entry_id} · ${item.archive_type} · contributed by <@${item.created_by}>`)
      .addFields(
        { name: "Curator", value: `<@${item.curator_id}>`, inline: true },
        { name: "Scope", value: item.visibility === "global" ? "Global" : "This server", inline: true },
        { name: "Ends", value: `<t:${Math.floor(new Date(item.ends_at).getTime() / 1000)}:R>`, inline: true },
        ...(item.note ? [{ name: "Note", value: safeDisplay(item.note, 500), inline: false }] : []),
      ));
    await interaction.reply({
      content: spotlights.length ? "Curated Archive highlights" : "No Archive spotlights are active for this server.",
      embeds,
      flags: MessageFlags.Ephemeral,
      allowedMentions: { parse: [] },
    });
  }

  private async showHistory(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    const history = await getCommunityHistory(interaction.guildId!);
    const fields = [
      { name: "Closed rankings", value: history.closedRankings.map((item) => `#${item.id} · ${safeDisplay(item.title)}`).join("\n") || "None yet", inline: false },
      { name: "Past sessions", value: history.pastSessions.map((item) => `#${item.id} · ${safeDisplay(item.title)} · ${item.activity_type}`).join("\n") || "None yet", inline: false },
      { name: "Recent discussions", value: history.discussions.map((item) => `#${item.id} · ${safeDisplay(item.title)} · ${item.status}`).join("\n") || "None yet", inline: false },
    ];
    await interaction.reply({ embeds: [homeEmbed("Community history", "Recent records belonging to this server.", fields)], flags: MessageFlags.Ephemeral });
  }
}

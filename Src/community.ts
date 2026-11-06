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
import type { FeatureCommand } from "../Helpers/command.js";
import type { BotConfig } from "../Helpers/config.js";
import { homeEmbed } from "../Helpers/discord.js";
import { AniListClient } from "../Helpers/anilist.js";
import { TmdbClient } from "../Helpers/tmdb.js";
import {
  addRankingCandidate,
  closeDiscussion,
  closeRanking,
  createCommunitySession,
  createRanking,
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
} from "../Helpers/community.js";
import { query, queryOne } from "../database.js";
import { cleanText, isGuildManager, isValidHttpsUrl, safeDisplay } from "../Helpers/security.js";

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
      { name: "Release calendar", value: "Upcoming provider-dated anime airings and film releases.", inline: true },
      { name: "History", value: "Recent rankings, sessions and discussions.", inline: true },
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
      { name: "Release calendar", value: "calendar" },
      { name: "Community history", value: "history" },
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
    .addStringOption((option) => option.setName("region").setDescription("Release region (two-letter code)").setMaxLength(2));

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
        case "calendar": await this.showCalendar(interaction); return;
        case "history": await this.showHistory(interaction); return;
        default: throw new Error("That community action is not available.");
      }
    } catch (error) {
      await interaction.reply({ content: error instanceof Error ? error.message : "The community action failed.", flags: MessageFlags.Ephemeral }).catch(async () => {
        await interaction.followUp({ content: error instanceof Error ? error.message : "The community action failed.", flags: MessageFlags.Ephemeral });
      });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
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
    if (action === "history") {
      await this.showHistory(interaction);
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
          .setTitle(`📅 ${interaction.fields.getTextInputValue("title")}`)
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
            embeds: [homeEmbed(`💬 ${title}`, `${prompt}\n\n${interaction.fields.getTextInputValue("media_title") ? `Media: ${interaction.fields.getTextInputValue("media_title")}\n` : ""}${interaction.fields.getTextInputValue("spoiler") ? `Spoiler boundary: ${interaction.fields.getTextInputValue("spoiler")}\n` : ""}Please mark spoilers and avoid discussing events beyond the stated boundary.`)],
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
      await interaction.reply({ content: error instanceof Error ? error.message : "The community action failed.", flags: MessageFlags.Ephemeral });
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

  private async showCalendar(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<void> {
    const from = new Date();
    const to = new Date(from.getTime() + 14 * 24 * 60 * 60 * 1000);
    const results = await upcomingProviderReleases(this.anilist, this.tmdb, from, to);
    if (!results.length) {
      await interaction.reply({ content: "No provider-dated anime airings or upcoming film releases were returned for the next 14 days. Missing provider data is not guessed.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({
      embeds: [homeEmbed("Release calendar · Next 14 days", "Dates are taken directly from AniList and TMDB and retain their provider links.", results.slice(0, 12).map((item) => ({
        name: `${safeDisplay(item.title, 180)} · <t:${Math.floor(item.when.getTime() / 1000)}:R>`,
        value: `[${item.provider} source](${item.url})`,
        inline: false,
      })))],
      flags: MessageFlags.Ephemeral,
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

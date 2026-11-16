import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelSelectMenuBuilder,
  ChannelType,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  PermissionFlagsBits,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  type ButtonInteraction,
  type ChannelSelectMenuInteraction,
  type ChatInputCommandInteraction,
  type RoleSelectMenuInteraction,
  type StringSelectMenuInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import { emoji } from "../../helpers/emoji.js";
import { homeEmbed } from "../../helpers/runtime/discord.js";
import { AniListClient } from "../../helpers/integration/anilist.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import {
  FEATURE_NAMES,
  getFeatureSettings,
  isFeatureName,
  setFeatureEnabled,
  type FeatureName,
} from "../../helpers/runtime/settings.js";
import {
  followAniListAnime,
  followAniListSubscription,
  getGuildMediaFollowSubscriptions,
  removeMediaFollowSubscription,
  getGuildMediaFollows,
  getMediaNotificationSettings,
  setMediaNotificationSettings,
  unfollowAniListAnime,
} from "../../helpers/media/media-notifications.js";
import { getGuildMediaRegion, setGuildMediaRegion } from "../../helpers/media/media-region.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import { query } from "../../database.js";
import { missingChannelPermissions, providerConfigurationChecks } from "../../helpers/runtime/server-diagnostics.js";
import {
  canConfigureGuildLeaveAction,
  getGuildRetentionSettings,
  isGuildRetentionConfigured,
  setGuildLeaveAction,
} from "../../helpers/runtime/guild-retention.js";
import { isBotModerator, isModeratorCommandGuild } from "../../helpers/commands/moderation.js";
import { createDatabaseBackup, listDatabaseBackups, verifyDatabaseBackup } from "../../helpers/runtime/database-backups.js";
import { listMediaAutomationRules, saveMediaAutomationRule, toggleMediaAutomationRule } from "../../helpers/community/community-automation.js";


type SettingsRow =
  | ActionRowBuilder<ButtonBuilder>
  | ActionRowBuilder<ChannelSelectMenuBuilder>
  | ActionRowBuilder<StringSelectMenuBuilder>;

async function mediaAutomationPanel(guildId: string): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const rules = await listMediaAutomationRules(guildId);
  const fields = rules.map(rule => ({
    name: rule.name,
    value: (rule.enabled ? "Enabled" : "Paused") + " · " + rule.action +
      " · " + rule.categories.join(", ").toUpperCase() + " · " + rule.region +
      " · <#" + rule.channel_id + ">",
    inline: false,
  }));
  const components: SettingsRow[] = [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("settings:automation:add").setLabel("Add rule").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("settings:automation:open").setLabel("Refresh").setStyle(ButtonStyle.Secondary),
    ),
  ];
  if (rules.length) {
    components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
      new StringSelectMenuBuilder().setCustomId("settings:automation:toggle").setPlaceholder("Pause or resume a rule")
        .addOptions(rules.slice(0, 25).map(rule => ({
          label: rule.name.slice(0, 100), value: rule.id,
          description: (rule.enabled ? "Enabled" : "Paused") + " · " + rule.action,
        }))),
    ));
  }
  return {
    embeds: [homeEmbed("Media Automation Studio",
      "Rules check AniList and TMDB release dates every hour. Events are deduplicated per rule; announcements can optionally open a spoiler-aware discussion and add a guild-scoped Atlas link.",
      fields.length ? fields : [{ name: "Rules", value: "No media automation rules configured." , inline: false }])],
    components,
  };
}

async function databaseBackupPanel(): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const backups = await listDatabaseBackups(5);
  const latest = backups[0];
  const fields = backups.map(backup => ({
    name: backup.id,
    value: backup.status.toUpperCase() + " · " + backup.size_bytes + " bytes · " +
      "<t:" + Math.floor(new Date(backup.created_at).getTime() / 1000) + ":R>" +
      (backup.verification_error ? " · " + backup.verification_error.slice(0, 180) : ""),
    inline: false,
  }));
  const controls = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("settings:backups:create").setLabel("Create backup").setStyle(ButtonStyle.Primary),
    ...(latest ? [new ButtonBuilder().setCustomId("settings:backups:verify:" + latest.id).setLabel("Verify latest").setStyle(ButtonStyle.Secondary)] : []),
  );
  return {
    embeds: [homeEmbed("Data & Backup Centre",
      "Backups are written to the configured private S3 bucket. Verification checks the object digest and PostgreSQL archive catalogue; this panel does not restore over a live database.",
      fields.length ? fields : [{ name: "Backup history", value: "No backups have been created." , inline: false }])],
    components: [controls],
  };
}

function mediaAutomationModal(): ModalBuilder {
  return new ModalBuilder().setCustomId("settings:automation:add").setTitle("Add media automation rule").addComponents(
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("name").setLabel("Rule name").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(100)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("categories").setLabel("Categories: anime, tv, movies").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(30).setValue("anime,tv,movies")),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("region").setLabel("Two-letter region").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(2).setValue("IE")),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("channel_id").setLabel("Destination channel ID").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(20)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(new TextInputBuilder().setCustomId("action").setLabel("Action: announce or discussion").setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(12).setValue("announce")),
  );
}

function mediaRegionModal(region: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("settings:media-region")
    .setTitle("Default media region")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder()
          .setCustomId("region")
          .setLabel("Two-letter country code")
          .setPlaceholder("IE, US, GB, JP")
          .setMinLength(2)
          .setMaxLength(2)
          .setRequired(true)
          .setValue(region),
      ),
    );
}

async function panel(guildId: string): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const [states, notifications, mediaRegion] = await Promise.all([
    getFeatureSettings(guildId),
    getMediaNotificationSettings(guildId),
    getGuildMediaRegion(guildId),
  ]);
  const channelLabel = notifications.channel_id
    ? `<#${notifications.channel_id}>`
    : "Not configured";
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle("Server settings")
    .setDescription("Manage feature availability and the media announcements sent to this server.")
    .addFields(
      ...FEATURE_NAMES.map((feature) => ({
        name: `/${feature}`,
        value: states[feature] ? "Enabled" : "Disabled",
        inline: true,
      })),
      {
        name: "Default media availability region",
        value: mediaRegion,
        inline: true,
      },
      {
        name: "Media completion notifications",
        value: [
          `Status: ${notifications.enabled ? "Enabled" : "Disabled"}`,
          `Channel: ${channelLabel}`,
          `Anime: ${notifications.include_anime ? "On" : "Off"} · Manga: ${notifications.include_manga ? "On" : "Off"}`,
          `Films: ${notifications.include_movies ? "On" : "Off"} · TV: ${notifications.include_tv ? "On" : "Off"} · Games: ${notifications.include_games ? "On" : "Off"}`,
          "Scans AniList completions and provider-dated anime, film, TV and game releases.",
        ].join("\n"),
        inline: false,
      },
    )
    .setFooter({ text: "Manage Server permission is required to change these settings." });

  const components: SettingsRow[] = [];
  for (let index = 0; index < FEATURE_NAMES.length; index += 5) {
    const row = new ActionRowBuilder<ButtonBuilder>();
    for (const feature of FEATURE_NAMES.slice(index, index + 5)) {
      row.addComponents(
        new ButtonBuilder()
          .setCustomId(`settings:toggle:${feature}`)
          .setLabel(`/${feature} · ${states[feature] ? "On" : "Off"}`)
          .setStyle(states[feature] ? ButtonStyle.Success : ButtonStyle.Secondary),
      );
    }
    components.push(row);
  }

  components.push(
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId("settings:notifications:enabled")
        .setLabel(notifications.enabled ? "Notifications On" : "Notifications Off")
        .setStyle(notifications.enabled ? ButtonStyle.Success : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:anime")
        .setLabel(`Anime ${notifications.include_anime ? "On" : "Off"}`)
        .setStyle(notifications.include_anime ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:manga")
        .setLabel(`Manga ${notifications.include_manga ? "On" : "Off"}`)
        .setStyle(notifications.include_manga ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:clear-channel")
        .setLabel("Clear channel")
        .setStyle(ButtonStyle.Danger),
      new ButtonBuilder()
        .setCustomId("settings:media-region:open")
        .setLabel("Region · " + mediaRegion)
        .setStyle(ButtonStyle.Secondary),
    ),
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId("settings:notifications:movies")
        .setLabel(`Films ${notifications.include_movies ? "On" : "Off"}`)
        .setStyle(notifications.include_movies ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:tv")
        .setLabel(`TV ${notifications.include_tv ? "On" : "Off"}`)
        .setStyle(notifications.include_tv ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:games")
        .setLabel(`Games ${notifications.include_games ? "On" : "Off"}`)
        .setStyle(notifications.include_games ? ButtonStyle.Primary : ButtonStyle.Secondary),
    ),
    new ActionRowBuilder<ChannelSelectMenuBuilder>().addComponents(
      new ChannelSelectMenuBuilder()
        .setCustomId("settings:notifications:channel")
        .setPlaceholder("Choose a media notification channel")
        .setChannelTypes(ChannelType.GuildText, ChannelType.GuildAnnouncement),
    ),
  );
  return { embeds: [embed], components };
}

async function retentionPanel(guildId: string): Promise<{
  embeds: EmbedBuilder[];
  components: ActionRowBuilder<ButtonBuilder>[];
}> {
  const settings = await getGuildRetentionSettings(guildId);
  const current = settings.leave_action === "delete"
    ? "Delete this server's Lemegeton data"
    : settings.leave_action === "retain"
      ? "Retain this server's Lemegeton data"
      : "A choice is required";
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle("Server data when Lemegeton leaves")
    .setDescription("Choose what happens to this server's stored Lemegeton data if the bot is removed. Delete permanently removes guild-owned records and uploaded assets (with failed private-object cleanup retried); Retain keeps them for a possible rejoin. Normal bot features stay locked until both this choice and the required server language are saved.")
    .addFields(
      { name: "Current choice", value: current },
      { name: "Who can choose", value: "The person who invited Lemegeton, or a member with Manage Server permission." },
    );
  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId("settings:retention:delete")
      .setLabel("Delete server data")
      .setStyle(ButtonStyle.Danger),
    new ButtonBuilder()
      .setCustomId("settings:retention:retain")
      .setLabel("Retain server data")
      .setStyle(ButtonStyle.Success),
  );
  return { embeds: [embed], components: [row] };
}

async function serverDiagnostics(
  guildId: string,
  currentChannelId: string,
  guild: NonNullable<ChatInputCommandInteraction["guild"]>,
  config: BotConfig,
): Promise<EmbedBuilder> {
  let databaseHealthy = false;
  let databaseLatency: number | null = null;
  const databaseStartedAt = Date.now();
  try {
    await query("SELECT 1 AS healthy");
    databaseHealthy = true;
    databaseLatency = Math.max(0, Date.now() - databaseStartedAt);
  } catch {
    databaseHealthy = false;
  }

  const configuredChannels = databaseHealthy
    ? await query<{ name: string; channel_id: string }>(
      "SELECT 'Current media notifications' AS name, channel_id::text AS channel_id FROM media_notification_settings WHERE guild_id = $1 AND channel_id IS NOT NULL " +
      "UNION ALL SELECT 'Archive uploads', upload_channel_id::text FROM guild_archive_settings WHERE guild_id = $1 AND upload_channel_id IS NOT NULL " +
      "UNION ALL SELECT 'Archive moderation', moderation_channel_id::text FROM guild_archive_settings WHERE guild_id = $1 AND moderation_channel_id IS NOT NULL " +
      "UNION ALL SELECT 'Custom Roles commands', command_channel_id::text FROM custom_role_guild_settings WHERE guild_id = $1 AND command_channel_id IS NOT NULL " +
      "UNION ALL SELECT 'Custom Roles logs', log_channel_id::text FROM custom_role_guild_settings WHERE guild_id = $1 AND log_channel_id IS NOT NULL " +
      "UNION ALL SELECT 'Daily Drop', channel_id::text FROM community_daily_schedules WHERE guild_id = $1 AND enabled = TRUE " +
      "UNION ALL SELECT 'Release digest', channel_id::text FROM community_release_schedules WHERE guild_id = $1 AND enabled = TRUE ORDER BY name",
      [guildId],
    )
    : [];
  const checks = [{ name: "Current channel", channel_id: currentChannelId }, ...configuredChannels];
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle("Server Check");

  let botMember: Awaited<ReturnType<typeof guild.members.fetchMe>> | null = null;
  try {
    botMember = await guild.members.fetchMe();
  } catch {
    botMember = null;
  }

  const gatewayReady = guild.client.isReady();
  const results: Array<{ name: string; status: string; detail: string }> = [
    {
      name: "PostgreSQL",
      status: databaseHealthy ? "Healthy" : "Needs attention",
      detail: databaseHealthy
        ? "SELECT 1 succeeded in " + databaseLatency + " ms."
        : "The database health query failed; configured delivery channels could not be listed.",
    },
    {
      name: "Discord gateway",
      status: gatewayReady ? "Healthy" : "Needs attention",
      detail: gatewayReady
        ? guild.client.ws.ping >= 0
          ? "Gateway is ready · " + Math.round(guild.client.ws.ping) + " ms ping."
          : "Gateway is ready; latency is unavailable."
        : "The bot client is not in the ready state.",
    },
  ];

  if (!botMember) {
    results.push({ name: "Bot membership", status: "Needs attention", detail: "The bot's server member could not be resolved; channel permissions could not be checked." });
  } else {
    for (const check of checks) {
      const channel = await guild.channels.fetch(check.channel_id).catch(() => null);
      if (!channel || channel.guildId !== guildId) {
        results.push({ name: check.name, status: "Needs attention", detail: "The configured channel is missing or inaccessible in this server." });
        continue;
      }
      const permissions = channel.permissionsFor(botMember);
      const missing = missingChannelPermissions({
        viewChannel: permissions?.has(PermissionFlagsBits.ViewChannel) ?? false,
        sendMessages: permissions?.has(PermissionFlagsBits.SendMessages) ?? false,
        embedLinks: permissions?.has(PermissionFlagsBits.EmbedLinks) ?? false,
      });
      results.push({
        name: check.name,
        status: missing.length ? "Needs attention" : "Healthy",
        detail: missing.length
          ? "Missing bot permissions: " + missing.join(", ") + "."
          : "View Channel, Send Messages and Embed Links are available.",
      });
    }
  }

  const healthy = results.filter(item => item.status === "Healthy").length;
  const attention = results.filter(item => item.status === "Needs attention").length;
  embed.setDescription(
    "**Healthy:** " + healthy + " · **Needs attention:** " + attention +
    "\nChecks include PostgreSQL, the Discord gateway, this channel and configured v3 delivery channels.",
  );
  for (const result of results) {
    embed.addFields({
      name: (result.status === "Healthy" ? "✓ " : emoji.error + " ") + result.name + " · " + result.status,
      value: result.detail,
      inline: false,
    });
  }
  if (configuredChannels.length === 0) {
    embed.addFields({
      name: "Optional channels",
      value: databaseHealthy ? "No additional delivery channels are configured." : "Database unavailable; configured delivery channels could not be listed.",
      inline: false,
    });
  }

  const providerChecks = providerConfigurationChecks({
    aniListEndpointConfigured: Boolean(config.anilistApiUrl),
    tmdbCredentialsConfigured: Boolean(config.tmdbBearerToken),
    googleBooksKeyConfigured: Boolean(config.googleBooksApiKey),
    igdbCredentialsConfigured: Boolean(config.igdbClientId && config.igdbClientSecret),
    steamKeyConfigured: Boolean(config.steamApiKey),
    objectStorageConfigured: Boolean(config.s3EndpointUrl && config.s3Bucket && config.s3AccessKeyId && config.s3SecretAccessKey),
  });
  embed.addFields({
    name: "Provider and storage configuration · not live probes",
    value: providerChecks.map(item => (item.configured ? "Configured" : "Not configured") + " · " + item.name + " — " + item.detail).join("\n").slice(0, 1024),
    inline: false,
  });
  embed.setFooter({ text: "Read-only diagnostics · Provider rows show configuration only; asset-object and scheduled-job health are not probed" });
  return embed;
}

function canManage(
  interaction: ButtonInteraction | ChatInputCommandInteraction | ChannelSelectMenuInteraction | StringSelectMenuInteraction | ModalSubmitInteraction,
): boolean {
  return interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false;
}

async function mediaFollowsPanel(guildId: string): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const [follows, subscriptions, notifications] = await Promise.all([
    getGuildMediaFollows(guildId),
    getGuildMediaFollowSubscriptions(guildId),
    getMediaNotificationSettings(guildId),
  ]);
  const legacySummary = follows.length
    ? [{
        name: "Anime episode follows · " + follows.length,
        value: follows.slice(0, 10).map(item => item.title.slice(0, 90) + " · AniList #" + item.anilist_id).join("\n")
          + (follows.length > 10 ? "\n+" + (follows.length - 10) + " more" : ""),
        inline: false,
      }]
    : [];
  const fields = [
    ...legacySummary,
    ...subscriptions.map(item => ({
      name: item.title.slice(0, 240),
      value: item.follow_type.toUpperCase() + " · " + item.target_kind + " · AniList " + item.target_id,
      inline: false,
    })),
  ].slice(0, 25);
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle("Media Follow Centre")
    .setDescription([
      "Follow AniList titles, creators, franchise relationships and genres for verified metadata changes.",
      "Anime episode schedules remain available through the legacy title-follow flow.",
      "Delivery: " + (notifications.enabled && notifications.channel_id ? "<#" + notifications.channel_id + ">" : "Disabled or no channel configured"),
      "Genre follows monitor AniList's bounded matching catalogue results; missing provider data is not inferred.",
    ].join("\n"))
    .addFields(fields.length ? fields : [{ name: "Following", value: "This server has no media follows yet.", inline: false }]);
  const components: SettingsRow[] = [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("settings:media-follows:add").setLabel("Follow anime episodes").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("settings:media-follows:subscriptions").setLabel("Follow media / creator / genre").setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId("settings:media-follows:open").setLabel("Refresh").setStyle(ButtonStyle.Secondary),
    ),
  ];
  if (follows.length) {
    components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
      new StringSelectMenuBuilder().setCustomId("settings:media-follows:remove")
        .setPlaceholder("Select an anime episode follow to remove")
        .addOptions(follows.slice(0, 25).map(item => ({
          label: item.title.slice(0, 100),
          description: "AniList #" + item.anilist_id,
          value: String(item.anilist_id),
        }))),
    ));
  }
  if (subscriptions.length) {
    components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
      new StringSelectMenuBuilder().setCustomId("settings:media-subscriptions:remove")
        .setPlaceholder("Select a metadata follow to remove")
        .addOptions(subscriptions.slice(0, 25).map(item => ({
          label: item.title.slice(0, 100),
          description: item.follow_type.toUpperCase() + " · " + item.target_kind,
          value: item.id,
        }))),
    ));
  }
  return { embeds: [embed], components };
}

export class SettingsCommand implements FeatureCommand {
  private readonly aniList: AniListClient;
  private readonly config: BotConfig;

  constructor(config: BotConfig) {
    this.config = config;
    this.aniList = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
  }

  readonly data = new SlashCommandBuilder()
    .setName("settings")
    .setDescription("Configure this server's features, data retention, notifications and diagnostics")
    .addStringOption((option) =>
      option.setName("action")
        .setDescription("Open settings or choose a settings area")
        .addChoices(
          { name: "View all settings", value: "view" },
          { name: "Toggle a feature", value: "toggle" },
          { name: "Media notifications", value: "notifications" },
          { name: "Media Follow Centre", value: "media-follows" },
          { name: "Change media region", value: "media-region" },
          { name: "Data retention when the bot leaves", value: "retention" },
          { name: "Media Automation Studio", value: "automation" },
          { name: "Data & Backup Centre", value: "data-backups" },
          { name: "Run server diagnostics", value: "diagnostics" },
        ),
    )
    .addStringOption((option) =>
      option.setName("feature")
        .setDescription("Feature environment to change")
        .addChoices(...FEATURE_NAMES.map((feature) => ({ name: `/${feature}`, value: feature }))),
    )
    .addBooleanOption((option) =>
      option.setName("enabled")
        .setDescription("Set feature availability explicitly; omit to invert its current state"),
    )
    .addStringOption((option) =>
      option.setName("region")
        .setDescription("Two-letter country code for the server's media availability region")
        .setMinLength(2)
        .setMaxLength(2),
    );

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({
        content: "Server settings are only available inside a server.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const configured = await isGuildRetentionConfigured(interaction.guildId);
    const action = interaction.options.getString("action") ?? (configured ? "view" : "retention");
    if (action === "data-backups") {
      if (!isModeratorCommandGuild(interaction.guildId, this.config.botModeratorGuildId)
        || !await isBotModerator(interaction.user.id, this.config.adminDiscordId)) {
        await interaction.reply({ content: "The Data & Backup Centre is restricted to configured bot moderators in the operations server.", flags: MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ ...await databaseBackupPanel(), flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
      return;
    }
    if (action === "retention") {
      const settings = await getGuildRetentionSettings(interaction.guildId);
      if (!canConfigureGuildLeaveAction(settings.invited_by, interaction.user.id, canManage(interaction))) {
        await interaction.reply({content:"Only the person who invited Lemegeton or a member with Manage Server permission can choose this setting.",flags:MessageFlags.Ephemeral});
        return;
      }
      await interaction.reply({ ...await retentionPanel(interaction.guildId), flags: MessageFlags.Ephemeral });
      return;
    }
    if (!configured) {
      await interaction.reply({content:"Choose the server data-retention setting before using other Lemegeton settings.",flags:MessageFlags.Ephemeral});
      return;
    }
    if (action === "automation") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to configure media automation.", flags: MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ ...await mediaAutomationPanel(interaction.guildId), flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
      return;
    }
    if (action === "media-follows") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to manage title follows.", flags: MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ ...await mediaFollowsPanel(interaction.guildId), flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
      return;
    }
    if (action === "diagnostics") {
      if (!canManage(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to run diagnostics.",flags:MessageFlags.Ephemeral});
        return;
      }
      await interaction.deferReply({flags:MessageFlags.Ephemeral});
      try {
        const guild = interaction.guild ?? await interaction.client.guilds.fetch(interaction.guildId);
        const embed = await serverDiagnostics(interaction.guildId, interaction.channelId, guild, this.config);
        await interaction.editReply({embeds:[embed]});
      } catch (error) {
        const issueHash = await createInteractionIssueLog(interaction, "/settings", error, { action: "diagnostics" });
        const message = "Server diagnostics could not be completed.";
        await interaction.editReply({content:issueHash ? message + "\n\n" + issueHashNotice(issueHash) : message});
      }
      return;
    }
    if (action === "media-region") {
      if (!canManage(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to change the media region.",flags:MessageFlags.Ephemeral});
        return;
      }
      const requestedRegion = interaction.options.getString("region");
      if (requestedRegion) {
        try {
          const savedRegion = await setGuildMediaRegion(interaction.guildId, requestedRegion, interaction.user.id);
          await interaction.reply({content:"Default media availability region saved as " + savedRegion + ".",flags:MessageFlags.Ephemeral});
        } catch (error) {
          const issueHash=await createInteractionIssueLog(interaction,"/settings",error,{action:"media-region"});
          const message=error instanceof Error ? error.message : "The media region could not be saved.";
          await interaction.reply({content:issueHash?message+"\n\n"+issueHashNotice(issueHash):message,flags:MessageFlags.Ephemeral});
        }
        return;
      }
      await interaction.showModal(mediaRegionModal(await getGuildMediaRegion(interaction.guildId)));
      return;
    }
    if (action === "toggle") {
      const feature = interaction.options.getString("feature");
      const enabled = interaction.options.getBoolean("enabled");
      if (!feature || !isFeatureName(feature)) {
        await interaction.reply({ content: "Choose a feature to change.", flags: MessageFlags.Ephemeral });
        return;
      }
      if (!canManage(interaction)) {
        await interaction.reply({
          content: "Manage Server permission is required to change feature availability.",
          flags: MessageFlags.Ephemeral,
        });
        return;
      }
      const states = await getFeatureSettings(interaction.guildId);
      await setFeatureEnabled(interaction.guildId, feature as FeatureName, enabled ?? !states[feature], interaction.user.id);
    }
    await interaction.reply({ ...await panel(interaction.guildId), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const [, section, target, recordId] = interaction.customId.split(":");
    if (!interaction.guildId) return false;
    if (section === "backups") {
      if (!isModeratorCommandGuild(interaction.guildId, this.config.botModeratorGuildId)
        || !await isBotModerator(interaction.user.id, this.config.adminDiscordId)) {
        await interaction.reply({ content: "The Backup Centre is restricted to bot moderators in the operations server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (target === "create") {
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        try {
          const backup = await createDatabaseBackup(this.config, interaction.user.id);
          await interaction.editReply("Backup " + backup.id + " uploaded and verified (" + backup.size_bytes + " bytes).");
        } catch (error) {
          await interaction.editReply(error instanceof Error ? error.message : "The database backup could not be created.");
        }
        return true;
      }
      if (target === "verify" && recordId) {
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        try {
          const backup = await verifyDatabaseBackup(recordId, this.config);
          await interaction.editReply("Backup " + backup.id + " passed digest and PostgreSQL archive-catalogue verification.");
        } catch (error) {
          await interaction.editReply(error instanceof Error ? error.message : "The database backup could not be verified.");
        }
        return true;
      }
      return false;
    }
    if (section === "automation") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to configure media automation.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (target === "add") {
        await interaction.showModal(mediaAutomationModal());
        return true;
      }
      if (target === "open") {
        await interaction.update(await mediaAutomationPanel(interaction.guildId));
        return true;
      }
      return false;
    }
    if (section === "retention") {
      if (target !== "delete" && target !== "retain") return false;
      const settings = await getGuildRetentionSettings(interaction.guildId);
      if (!canConfigureGuildLeaveAction(settings.invited_by, interaction.user.id, canManage(interaction))) {
        await interaction.reply({content:"Only the person who invited Lemegeton or a member with Manage Server permission can change this setting.",flags:MessageFlags.Ephemeral});
        return true;
      }
      await setGuildLeaveAction(interaction.guildId, target, interaction.user.id);
      await interaction.update(await retentionPanel(interaction.guildId));
      return true;
    }
    if (section !== "toggle" && section !== "notifications" && section !== "media-region" && section !== "media-follows") return false;
    if (!canManage(interaction)) {
      await interaction.reply({
        content: "Manage Server permission is required to change server settings.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }

    if (section === "media-region") {
      if (target !== "open") return false;
      await interaction.showModal(mediaRegionModal(await getGuildMediaRegion(interaction.guildId)));
      return true;
    }
    if (section === "media-follows") {
      if (target === "subscriptions") {
        const followModal = new ModalBuilder().setCustomId("settings:media-subscriptions:add").setTitle("Add a media follow");
        followModal.addComponents(
          new ActionRowBuilder<TextInputBuilder>().addComponents(
            new TextInputBuilder().setCustomId("follow_type").setLabel("Type: title, creator, franchise or category")
              .setPlaceholder("title").setRequired(true).setMaxLength(16),
          ),
          new ActionRowBuilder<TextInputBuilder>().addComponents(
            new TextInputBuilder().setCustomId("target_kind").setLabel("AniList type: ANIME, MANGA, STAFF or STUDIO")
              .setPlaceholder("ANIME").setRequired(true).setMaxLength(8),
          ),
          new ActionRowBuilder<TextInputBuilder>().addComponents(
            new TextInputBuilder().setCustomId("target").setLabel("AniList ID or genre name")
              .setPlaceholder("e.g. 21 or Fantasy").setRequired(true).setMaxLength(80),
          ),
        );
        await interaction.showModal(followModal);
        return true;
      }
      if (target === "add") {
        const followModal = new ModalBuilder().setCustomId("settings:media-follows:add").setTitle("Follow an AniList anime");
        followModal.addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
          new TextInputBuilder().setCustomId("anilist_id").setLabel("AniList anime ID")
            .setPlaceholder("e.g. 21").setRequired(true).setMaxLength(12),
        ));
        await interaction.showModal(followModal);
        return true;
      }
      if (target === "open") {
        await interaction.update(await mediaFollowsPanel(interaction.guildId));
        return true;
      }
      return false;
    }

    if (section === "toggle") {
      if (!target || !isFeatureName(target)) return false;
      const states = await getFeatureSettings(interaction.guildId);
      await setFeatureEnabled(interaction.guildId, target as FeatureName, !states[target], interaction.user.id);
      await interaction.update(await panel(interaction.guildId));
      return true;
    }

    const current = await getMediaNotificationSettings(interaction.guildId);
    if (target === "enabled" && !current.enabled && !current.channel_id) {
      await interaction.reply({
        content: "Choose a text channel first, then enable media notifications.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (target === "enabled") {
      await setMediaNotificationSettings(
        interaction.guildId,
        { enabled: !current.enabled },
        interaction.user.id,
      );
    } else if (target === "anime") {
      await setMediaNotificationSettings(
        interaction.guildId,
        { include_anime: !current.include_anime },
        interaction.user.id,
      );
    } else if (target === "manga") {
      await setMediaNotificationSettings(
        interaction.guildId,
        { include_manga: !current.include_manga },
        interaction.user.id,
      );
    } else if (target === "movies") {
      await setMediaNotificationSettings(interaction.guildId, { include_movies: !current.include_movies }, interaction.user.id);
    } else if (target === "tv") {
      await setMediaNotificationSettings(interaction.guildId, { include_tv: !current.include_tv }, interaction.user.id);
    } else if (target === "games") {
      await setMediaNotificationSettings(interaction.guildId, { include_games: !current.include_games }, interaction.user.id);
    } else if (target === "clear-channel") {
      await setMediaNotificationSettings(
        interaction.guildId,
        { channel_id: null, enabled: false },
        interaction.user.id,
      );
    } else {
      return false;
    }
    await interaction.update(await panel(interaction.guildId));
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId !== "settings:media-region" && interaction.customId !== "settings:media-follows:add" && interaction.customId !== "settings:media-subscriptions:add" && interaction.customId !== "settings:automation:add") return false;
    if (!interaction.guildId) return false;
    if (!canManage(interaction as ModalSubmitInteraction)) {
      await interaction.reply({ content: "Manage Server permission is required to change server media settings.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "settings:automation:add") {
        const rawChannelId = interaction.fields.getTextInputValue("channel_id").trim();
        if (!/^\d{17,20}$/.test(rawChannelId)) throw new Error("Enter a valid destination channel ID.");
        const guild = interaction.guild ?? await interaction.client.guilds.fetch(interaction.guildId);
        const channel = await guild.channels.fetch(rawChannelId).catch(() => null);
        if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
          throw new Error("Choose a text or announcement channel in this server.");
        }
        await saveMediaAutomationRule({
          guildId: interaction.guildId,
          actorId: interaction.user.id,
          name: interaction.fields.getTextInputValue("name"),
          channelId: channel.id,
          categories: interaction.fields.getTextInputValue("categories"),
          region: interaction.fields.getTextInputValue("region"),
          action: interaction.fields.getTextInputValue("action"),
        });
        await interaction.reply({ content: "Media automation rule saved and enabled. Its first provider check is queued.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (interaction.customId === "settings:media-subscriptions:add") {
        const subscription = await followAniListSubscription(
          interaction.guildId,
          interaction.user.id,
          interaction.fields.getTextInputValue("follow_type"),
          interaction.fields.getTextInputValue("target_kind"),
          interaction.fields.getTextInputValue("target"),
          this.aniList,
        );
        await interaction.reply({
          content: "Following " + subscription.title + " for this server. Metadata checks use AniList's verified catalogue records.",
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
      if (interaction.customId === "settings:media-follows:add") {
        const rawId = interaction.fields.getTextInputValue("anilist_id").trim();
        if (!/^\d{1,12}$/.test(rawId) || Number(rawId) < 1 || !Number.isSafeInteger(Number(rawId))) {
          throw new Error("Enter a valid positive AniList anime ID.");
        }
        const follow = await followAniListAnime(interaction.guildId, interaction.user.id, Number(rawId), this.aniList);
        const notifications = await getMediaNotificationSettings(interaction.guildId);
        const delivery = notifications.enabled && notifications.channel_id
          ? " Episode alerts will be sent to <#" + notifications.channel_id + ">."
          : " Configure and enable the media notification channel to receive alerts.";
        await interaction.reply({ content: "Following " + follow.title + " for this server." + delivery, flags: MessageFlags.Ephemeral });
        return true;
      }
      const region = await setGuildMediaRegion(
        interaction.guildId,
        interaction.fields.getTextInputValue("region"),
        interaction.user.id,
      );
      await interaction.reply({ content: "Default media availability region saved as " + region + ".", flags: MessageFlags.Ephemeral });
      return true;
    } catch (error) {
      const issueHash = await createInteractionIssueLog(interaction, "/settings", error, { action: interaction.customId });
      const message = error instanceof Error ? error.message : "The setting could not be saved.";
      await interaction.reply({ content: issueHash ? message + "\n\n" + issueHashNotice(issueHash) : message, flags: MessageFlags.Ephemeral });
      return true;
    }
  }

  async handleSelect(
    interaction: ButtonInteraction | StringSelectMenuInteraction | RoleSelectMenuInteraction | ChannelSelectMenuInteraction,
  ): Promise<boolean> {
    if (!interaction.guildId) return false;
    if (interaction.isStringSelectMenu() && interaction.customId === "settings:automation:toggle") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to manage media automation.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const ruleId = interaction.values[0];
      if (!ruleId || !/^\d+$/.test(ruleId)) return false;
      const enabled = await toggleMediaAutomationRule(interaction.guildId, ruleId);
      await interaction.update({ ...await mediaAutomationPanel(interaction.guildId), content: enabled ? "Automation rule resumed." : "Automation rule paused." });
      return true;
    }
    if (interaction.isStringSelectMenu() && interaction.customId === "settings:media-subscriptions:remove") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to manage media follows.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const subscriptionId = interaction.values[0];
      if (!subscriptionId || !/^\\d+$/.test(subscriptionId)) return false;
      const removed = await removeMediaFollowSubscription(interaction.guildId, subscriptionId);
      await interaction.update({
        ...await mediaFollowsPanel(interaction.guildId),
        content: removed ? "Media metadata follow removed." : "That media follow was no longer present.",
      });
      return true;
    }
    if (interaction.isStringSelectMenu() && interaction.customId === "settings:media-follows:remove") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to manage title follows.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const mediaId = Number(interaction.values[0]);
      if (!Number.isSafeInteger(mediaId) || mediaId < 1) return false;
      const removed = await unfollowAniListAnime(interaction.guildId, mediaId);
      await interaction.update({
        ...await mediaFollowsPanel(interaction.guildId),
        content: removed ? "Anime follow removed." : "That anime was no longer followed.",
      });
      return true;
    }
    if (!interaction.isChannelSelectMenu() || interaction.customId !== "settings:notifications:channel") return false;
    if (!canManage(interaction)) {
      await interaction.reply({
        content: "Manage Server permission is required to change notification settings.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    const selected = interaction.channels.first();
    if (!selected || (selected.type !== ChannelType.GuildText && selected.type !== ChannelType.GuildAnnouncement)) {
      await interaction.reply({
        content: "Choose a server text or announcement channel.",
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    await setMediaNotificationSettings(
      interaction.guildId,
      { channel_id: selected.id },
      interaction.user.id,
    );
    await interaction.update(await panel(interaction.guildId));
    return true;
  }

}

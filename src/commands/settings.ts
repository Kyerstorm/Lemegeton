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
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
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
import { HeadBucketCommand, S3Client } from "@aws-sdk/client-s3";
import { jobQueueChecks, missingChannelPermissions, providerConfigurationChecks } from "../../helpers/runtime/server-diagnostics.js";
import {
  canConfigureGuildLeaveAction,
  getGuildRetentionSettings,
  isGuildRetentionConfigured,
  setGuildLeaveAction,
} from "../../helpers/runtime/guild-retention.js";
import { isBotModerator, isModeratorCommandGuild } from "../../helpers/commands/moderation.js";
import { createDatabaseBackup, listDatabaseBackups, rehearseDatabaseBackup, verifyDatabaseBackup } from "../../helpers/runtime/database-backups.js";
import { listMediaAutomationRules, saveMediaAutomationRule, toggleMediaAutomationRule } from "../../helpers/community/community-automation.js";
import {
  disableReleaseSchedule,
  getReleaseSchedule,
  parseReleaseCadenceInput,
  resumeReleaseSchedule,
  saveReleaseSchedule,
  type ReleaseCategory,
  type ReleaseEntityType,
  type ReleaseSchedule,
} from "../../helpers/community/community-releases.js";


type SettingsRow =
  | ActionRowBuilder<ButtonBuilder>
  | ActionRowBuilder<ChannelSelectMenuBuilder>
  | ActionRowBuilder<StringSelectMenuBuilder>;

const DIGEST_CATEGORIES: ReleaseCategory[] = ["anime", "tv", "movies", "games"];
const DIGEST_ENTITY_TYPES: ReleaseEntityType[] = ["title", "creator", "franchise", "category", "episodes"];

function mediaDigestModal(schedule: ReleaseSchedule | null): ModalBuilder {
  const modal = new ModalBuilder()
    .setCustomId("settings:media-digest:configure")
    .setTitle("Configure media digest");
  const input = (id: string, label: string, value: string, placeholder: string, maxLength: number) => {
    const field = new TextInputBuilder()
      .setCustomId(id)
      .setLabel(label)
      .setStyle(TextInputStyle.Short)
      .setRequired(true)
      .setMaxLength(maxLength);
    if (value) field.setValue(value);
    else field.setPlaceholder(placeholder);
    return new ActionRowBuilder<TextInputBuilder>().addComponents(field);
  };
  const cadence = schedule?.cadence === "weekly"
    ? "weekly:" + ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][schedule.weekday]
    : "daily";
  modal.addComponents(
    input("channel_id", "Destination channel ID", schedule?.channel_id ?? "", "Copy the ID of a server text channel", 20),
    input("time_zone", "IANA timezone", schedule?.time_zone ?? "", "Europe/Dublin", 80),
    input("local_time", "Local send time (24-hour)", schedule?.local_time ?? "", "18:30", 5),
    input("cadence", "Cadence: daily or weekly:mon", cadence, "daily or weekly:mon", 12),
    input("region", "Release region (two-letter code)", schedule?.region ?? "", "IE", 2),
  );
  return modal;
}

async function mediaDigestPanel(guildId: string): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const [schedule, subscriptions, animeFollows] = await Promise.all([
    getReleaseSchedule(guildId),
    getGuildMediaFollowSubscriptions(guildId),
    getGuildMediaFollows(guildId),
  ]);
  const categories = schedule?.categories ?? DIGEST_CATEGORIES;
  const entityTypes = schedule?.entity_types ?? DIGEST_ENTITY_TYPES;
  const entityIds = schedule?.entity_ids ?? ["all"];
  const availableTargets = new Map<string, { label: string; description: string; value: string }>();
  for (const follow of subscriptions) {
    availableTargets.set("subscription:" + follow.id, {
      label: follow.title.slice(0, 100),
      description: follow.follow_type.toUpperCase() + " · " + follow.target_kind,
      value: "subscription:" + follow.id,
    });
  }
  for (const follow of animeFollows) {
    availableTargets.set("anime:" + follow.anilist_id, {
      label: follow.title.slice(0, 100),
      description: "Anime episode follow · AniList",
      value: "anime:" + follow.anilist_id,
    });
  }
  const selectedTargets = entityIds.filter(value => value !== "all" && value !== "none");
  const targetOptions = [
    ...selectedTargets.map(value => availableTargets.get(value) ?? {
      label: "Unavailable follow · " + value.slice(0, 80),
      description: "This follow was removed or is no longer available.",
      value,
    }),
    ...[...availableTargets.values()].filter(value => !selectedTargets.includes(value.value)),
  ].slice(0, 23);
  const selectedTargetLabel = entityIds.includes("all") ? "All current and future follows"
    : entityIds.includes("none") ? "No followed entities"
      : selectedTargets.length + " selected follow target(s)";
  const embed = new EmbedBuilder()
    .setColor(EMBED_COLOURS.primary)
    .setTitle(emoji.calendar + " Media Digest Studio")
    .setDescription(schedule
      ? [
          "Status: " + (schedule.enabled ? "Enabled" : "Paused"),
          "Destination: <#" + schedule.channel_id + ">",
          "Cadence: " + (schedule.cadence === "daily" ? "Daily" : "Weekly · " + ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][schedule.weekday]),
          "Local send time: " + schedule.local_time + " · " + schedule.time_zone,
          "Release region: " + schedule.region,
          "Media categories: " + (categories.join(", ") || "None"),
          "Followed update types: " + (entityTypes.join(", ") || "Disabled"),
          "Follow targets: " + selectedTargetLabel,
          "Next run: <t:" + Math.floor(new Date(schedule.next_run_at).getTime() / 1000) + ":F>",
        ].join("\n")
      : "No digest is configured. Configure a daily or weekly destination, local schedule, timezone and region, then choose categories and followed-entity filters.")
    .addFields({
      name: "Provider boundary",
      value: "Only provider-dated anime, film, TV and game releases are scheduled. Book publication dates are not inferred when no verified release feed is available.",
      inline: false,
    })
    .setFooter({ text: emoji.calendar + " Manage Server permission required · Digests are scoped to this server" });
  const categorySelect = new StringSelectMenuBuilder()
    .setCustomId("settings:media-digest:categories")
    .setPlaceholder("Choose release categories")
    .setMinValues(1)
    .setMaxValues(DIGEST_CATEGORIES.length)
    .setDisabled(!schedule)
    .addOptions(DIGEST_CATEGORIES.map(value => ({
      label: value === "movies" ? "Films" : value.toUpperCase() === "TV" ? "Television" : value[0]!.toUpperCase() + value.slice(1),
      value,
      default: categories.includes(value),
    })));
  const entityTypeSelect = new StringSelectMenuBuilder()
    .setCustomId("settings:media-digest:entity-types")
    .setPlaceholder("Choose followed update types")
    .setMinValues(0)
    .setMaxValues(DIGEST_ENTITY_TYPES.length)
    .setDisabled(!schedule)
    .addOptions(DIGEST_ENTITY_TYPES.map(value => ({
      label: value === "episodes" ? "Followed anime episodes" : value[0]!.toUpperCase() + value.slice(1) + " updates",
      value,
      default: entityTypes.includes(value),
    })));
  const entitySelect = new StringSelectMenuBuilder()
    .setCustomId("settings:media-digest:entities")
    .setPlaceholder("Choose followed entities")
    .setMinValues(1)
    .setMaxValues(Math.min(25, 2 + targetOptions.length))
    .setDisabled(!schedule)
    .addOptions([
      { label: "All followed entities", description: "Include current and future follows", value: "all", default: entityIds.includes("all") },
      { label: "No followed entities", description: "Include provider-dated releases only", value: "none", default: entityIds.includes("none") },
      ...targetOptions.map(option => ({ ...option, default: entityIds.includes(option.value) })),
    ]);
  const components: SettingsRow[] = [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId("settings:media-digest:configure")
        .setLabel(schedule ? "Edit digest" : "Configure digest")
        .setStyle(ButtonStyle.Primary),
      ...(schedule ? [
        new ButtonBuilder()
          .setCustomId("settings:media-digest:" + (schedule.enabled ? "disable" : "resume"))
          .setLabel(schedule.enabled ? "Pause digest" : "Resume digest")
          .setStyle(schedule.enabled ? ButtonStyle.Secondary : ButtonStyle.Success),
      ] : []),
      new ButtonBuilder().setCustomId("settings:media-digest:open").setLabel("Refresh").setEmoji(emoji.refresh).setStyle(ButtonStyle.Secondary),
    ),
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(categorySelect),
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(entityTypeSelect),
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(entitySelect),
  ];
  return { embeds: [embed], components };
}

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
      new ButtonBuilder().setCustomId("settings:automation:add").setLabel("Add rule").setEmoji(emoji.tools).setStyle(ButtonStyle.Primary),
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

async function databaseBackupPanel(config: BotConfig): Promise<{
  embeds: EmbedBuilder[];
  components: SettingsRow[];
}> {
  const backups = await listDatabaseBackups(5);
  const latest = backups[0];
  const latestVerified = backups.find(backup => backup.status === "verified");
  const fields = backups.map(backup => ({
    name: backup.id,
    value: backup.status.toUpperCase() + " · " + backup.size_bytes + " bytes · " +
      "<t:" + Math.floor(new Date(backup.created_at).getTime() / 1000) + ":R>" +
      " · Restore rehearsal: " + backup.rehearsal_status.toUpperCase() +
      (backup.rehearsal_at ? " · <t:" + Math.floor(new Date(backup.rehearsal_at).getTime() / 1000) + ":R>" : "") +
      (backup.rehearsal_error ? " · " + backup.rehearsal_error.slice(0, 140) : "") +
      (backup.verification_error ? " · " + backup.verification_error.slice(0, 140) : ""),
    inline: false,
  }));
  const controls = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("settings:backups:create").setLabel("Create backup").setEmoji(emoji.download).setStyle(ButtonStyle.Primary),
    ...(latest ? [new ButtonBuilder().setCustomId("settings:backups:verify:" + latest.id).setLabel("Verify latest").setStyle(ButtonStyle.Secondary)] : []),
    ...(config.backupRehearsalDatabase && latestVerified
      ? [new ButtonBuilder().setCustomId("settings:backups:rehearse:" + latestVerified.id).setLabel("Rehearse latest verified").setStyle(ButtonStyle.Success)]
      : []),
  );
  return {
    embeds: [homeEmbed("Data & Backup Centre",
      "Backups are stored in the configured private S3 bucket. Restore rehearsal requires a separate PostgreSQL endpoint and restores into a temporary database that is dropped after validation." +
      (config.backupRehearsalDatabase ? "" : " Set BACKUP_REHEARSAL_DATABASE_URL to a different host or port to enable the rehearsal action."),
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
    .setColor(EMBED_COLOURS.primary)
    .setTitle(emoji.settings + " Server settings")
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
    .setFooter({ text: emoji.settings + " Manage Server permission is required to change these settings." });

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
        .setLabel(`Anime ${notifications.include_anime ? "On" : "Off"}`).setEmoji(emoji.anime)
        .setStyle(notifications.include_anime ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:manga")
        .setLabel(`Manga ${notifications.include_manga ? "On" : "Off"}`).setEmoji(emoji.manga)
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
        .setLabel(`Films ${notifications.include_movies ? "On" : "Off"}`).setEmoji(emoji.movie)
        .setStyle(notifications.include_movies ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:tv")
        .setLabel(`TV ${notifications.include_tv ? "On" : "Off"}`).setEmoji(emoji.television)
        .setStyle(notifications.include_tv ? ButtonStyle.Primary : ButtonStyle.Secondary),
      new ButtonBuilder()
        .setCustomId("settings:notifications:games")
        .setLabel(`Games ${notifications.include_games ? "On" : "Off"}`).setEmoji(emoji.game)
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
    .setColor(EMBED_COLOURS.primary)
    .setTitle(emoji.warning + " Server data when Lemegeton leaves")
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


async function probeProviderEndpoint(
  name: string,
  url: string,
  init?: RequestInit,
): Promise<{ name: string; status: string; detail: string }> {
  try {
    const response = await fetch(url, { ...init, signal: AbortSignal.timeout(4_500) });
    await response.body?.cancel().catch(() => undefined);
    return {
      name,
      status: response.ok ? "Healthy" : "Needs attention",
      detail: response.ok ? "Provider responded with HTTP " + response.status + "." : "Provider returned HTTP " + response.status + ".",
    };
  } catch {
    return { name, status: "Needs attention", detail: "Provider did not respond within 4.5 seconds." };
  }
}

async function probeIgdb(config: BotConfig): Promise<{ name: string; status: string; detail: string }> {
  if (!config.igdbClientId || !config.igdbClientSecret) {
    return { name: "IGDB", status: "Not configured", detail: "Client credentials are incomplete; live probe skipped." };
  }
  try {
    const tokenUrl = new URL("https://id.twitch.tv/oauth2/token");
    tokenUrl.searchParams.set("client_id", config.igdbClientId);
    tokenUrl.searchParams.set("client_secret", config.igdbClientSecret);
    tokenUrl.searchParams.set("grant_type", "client_credentials");
    const tokenResponse = await fetch(tokenUrl, { method: "POST", signal: AbortSignal.timeout(4_500) });
    if (!tokenResponse.ok) return { name: "IGDB", status: "Needs attention", detail: "Twitch authentication returned HTTP " + tokenResponse.status + "." };
    const token = await tokenResponse.json() as { access_token?: unknown };
    if (typeof token.access_token !== "string" || !token.access_token) {
      return { name: "IGDB", status: "Needs attention", detail: "Twitch did not return an application access token." };
    }
    const response = await fetch("https://api.igdb.com/v4/games", {
      method: "POST",
      headers: {
        "Client-ID": config.igdbClientId,
        authorization: "Bearer " + token.access_token,
        "content-type": "text/plain",
      },
      body: "fields id; limit 1;",
      signal: AbortSignal.timeout(4_500),
    });
    await response.body?.cancel().catch(() => undefined);
    return {
      name: "IGDB",
      status: response.ok ? "Healthy" : "Needs attention",
      detail: response.ok ? "OAuth and games catalogue request succeeded." : "IGDB returned HTTP " + response.status + ".",
    };
  } catch {
    return { name: "IGDB", status: "Needs attention", detail: "Twitch or IGDB did not respond within the probe limit." };
  }
}

async function liveProviderChecks(config: BotConfig): Promise<Array<{ name: string; status: string; detail: string }>> {
  const checks: Promise<{ name: string; status: string; detail: string }>[] = [
    probeProviderEndpoint("AniList", config.anilistApiUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "query Diagnostics { Media(id: 1) { id } }" }),
    }),
    probeIgdb(config),
  ];
  if (config.tmdbBearerToken) {
    checks.push(probeProviderEndpoint("TMDB", "https://api.themoviedb.org/3/configuration", {
      headers: { authorization: "Bearer " + config.tmdbBearerToken, accept: "application/json" },
    }));
  } else {
    checks.push(Promise.resolve({ name: "TMDB", status: "Not configured", detail: "No bearer credentials; live probe skipped." }));
  }
  if (config.googleBooksApiKey) {
    const url = new URL("https://www.googleapis.com/books/v1/volumes");
    url.searchParams.set("q", "subject:fiction");
    url.searchParams.set("maxResults", "1");
    url.searchParams.set("key", config.googleBooksApiKey);
    checks.push(probeProviderEndpoint("Google Books", url.toString()));
  } else {
    checks.push(Promise.resolve({ name: "Google Books", status: "Not configured", detail: "No API key; live probe skipped." }));
  }
  if (config.steamApiKey) {
    const url = new URL("https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/");
    url.searchParams.set("key", config.steamApiKey);
    checks.push(probeProviderEndpoint("Steam", url.toString()));
  } else {
    checks.push(Promise.resolve({ name: "Steam", status: "Not configured", detail: "No API key; live probe skipped." }));
  }
  return Promise.all(checks);
}

async function probeAssetBucket(config: BotConfig): Promise<{ name: string; status: string; detail: string }> {
  if (!config.s3Bucket) {
    return { name: "Private asset bucket", status: "Not configured", detail: "No S3 bucket is configured." };
  }
  let client: S3Client | undefined;
  try {
    client = new S3Client({
      region: config.s3Region,
      ...(config.s3EndpointUrl ? { endpoint: config.s3EndpointUrl, forcePathStyle: true } : {}),
      ...(config.s3AccessKeyId && config.s3SecretAccessKey
        ? { credentials: { accessKeyId: config.s3AccessKeyId, secretAccessKey: config.s3SecretAccessKey } }
        : {}),
    });
    await client.send(new HeadBucketCommand({ Bucket: config.s3Bucket }), {
      abortSignal: AbortSignal.timeout(4_500),
    });
    return { name: "Private asset bucket", status: "Healthy", detail: "The configured bucket accepted a metadata access check." };
  } catch {
    return { name: "Private asset bucket", status: "Needs attention", detail: "The configured bucket could not be accessed. Check its endpoint and IAM/bucket permissions." };
  } finally {
    client?.destroy();
  }
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
    .setColor(EMBED_COLOURS.primary)
    .setTitle(emoji.stats + " Server Check");

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

  const queueSnapshots = databaseHealthy ? await query<{
    name: string;
    due_count: number;
    failed_count: number;
    stale_count: number;
  }>(
    "SELECT 'Daily Drop deliveries'::text AS name, " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT AS due_count, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT AS failed_count, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT AS stale_count " +
    "FROM community_daily_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Release digest deliveries', " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT " +
    "FROM community_release_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Anime episode follow deliveries', " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT " +
    "FROM guild_media_follow_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Media follow deliveries', " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT " +
    "FROM media_follow_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Release notification deliveries', " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT " +
    "FROM media_release_notification_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Media automation deliveries', " +
    "COUNT(*) FILTER (WHERE status = 'pending' AND next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE status = 'failed')::INT, " +
    "COUNT(*) FILTER (WHERE status = 'processing' AND claim_until < NOW())::INT " +
    "FROM community_media_automation_deliveries WHERE guild_id = $1 " +
    "UNION ALL SELECT 'Private asset cleanup'::text, " +
    "COUNT(*) FILTER (WHERE q.next_attempt_at <= NOW())::INT, " +
    "COUNT(*) FILTER (WHERE q.last_error IS NOT NULL)::INT, 0::INT " +
    "FROM media_asset_cleanup_queue q JOIN media_assets a ON a.id = q.asset_id WHERE a.guild_id = $1",
    [guildId],
  ) : [];
  results.push(...jobQueueChecks(queueSnapshots));
  const [storageProbe, liveProviders] = await Promise.all([
    probeAssetBucket(config),
    liveProviderChecks(config),
  ]);
  results.push(storageProbe, ...liveProviders);

  const healthy = results.filter(item => item.status === "Healthy").length;
  const backlog = results.filter(item => item.status === "Backlog").length;
  const attention = results.filter(item => item.status === "Needs attention").length;
  const unconfigured = results.filter(item => item.status === "Not configured").length;
  embed.setDescription(
    "**Healthy:** " + healthy + " · **Backlog:** " + backlog + " · **Needs attention:** " + attention +
    (unconfigured ? " · **Not configured:** " + unconfigured : "") +
    "\nChecks include PostgreSQL, Discord permissions, provider APIs, private storage and guild-scoped delivery queues.",
  );
  for (const result of results) {
    embed.addFields({
      name: (result.status === "Healthy" ? "✓ " : result.status === "Backlog" ? "… " : result.status === "Not configured" ? "— " : emoji.error + " ") + result.name + " · " + result.status,
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
    objectStorageConfigured: Boolean(config.s3Bucket),
  });
  embed.addFields(
    {
      name: "Provider configuration",
      value: providerChecks.map(item => (item.configured ? "Configured" : "Not configured") + " · " + item.name + " — " + item.detail).join("\n").slice(0, 1024),
      inline: false,
    },
    {
      name: "Live provider probes",
      value: liveProviders.map(item => item.status + " · " + item.name + " — " + item.detail).join("\n").slice(0, 1024),
      inline: false,
    },
  );
  embed.setFooter({ text: emoji.info + " Read-only diagnostics · Provider probes are time-bounded; counts are server-scoped" });
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
    .setColor(EMBED_COLOURS.primary)
    .setTitle(emoji.bell + " Media Follow Centre")
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
          { name: "Media Digest Studio", value: "media-digest" },
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
      await interaction.reply({ ...await databaseBackupPanel(this.config), flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
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
    if (action === "media-digest") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to configure media digests.", flags: MessageFlags.Ephemeral });
        return;
      }
      await interaction.reply({ ...await mediaDigestPanel(interaction.guildId), flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
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
      if (target === "rehearse" && recordId) {
        await interaction.deferReply({ flags: MessageFlags.Ephemeral });
        try {
          const result = await rehearseDatabaseBackup(recordId, this.config);
          await interaction.editReply("Backup " + result.backupId + " restored and validated in temporary database " +
            result.databaseName + " (" + result.tableCount + " application tables). The temporary database was dropped.");
        } catch (error) {
          await interaction.editReply(error instanceof Error ? error.message : "The database restore rehearsal failed.");
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
    if (section === "media-digest") {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to configure media digests.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (target === "configure") {
        await interaction.showModal(mediaDigestModal(await getReleaseSchedule(interaction.guildId)));
        return true;
      }
      if (target === "disable") {
        await disableReleaseSchedule(interaction.guildId);
        await interaction.update(await mediaDigestPanel(interaction.guildId));
        return true;
      }
      if (target === "resume") {
        const nextRun = await resumeReleaseSchedule(interaction.guildId);
        await interaction.update({
          ...await mediaDigestPanel(interaction.guildId),
          content: nextRun ? "Media digest resumed. Next delivery: <t:" + Math.floor(nextRun.getTime() / 1000) + ":F>." : "Configure a digest before resuming it.",
        });
        return true;
      }
      if (target === "open") {
        await interaction.update(await mediaDigestPanel(interaction.guildId));
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
    if (interaction.customId !== "settings:media-region" && interaction.customId !== "settings:media-follows:add" && interaction.customId !== "settings:media-subscriptions:add" && interaction.customId !== "settings:automation:add" && interaction.customId !== "settings:media-digest:configure") return false;
    if (!interaction.guildId) return false;
    if (!canManage(interaction as ModalSubmitInteraction)) {
      await interaction.reply({ content: "Manage Server permission is required to change server media settings.", flags: MessageFlags.Ephemeral });
      return true;
    }
    try {
      if (interaction.customId === "settings:media-digest:configure") {
        const rawChannelId = interaction.fields.getTextInputValue("channel_id").trim();
        if (!/^\d{17,20}$/.test(rawChannelId)) throw new Error("Enter a valid destination channel ID.");
        const guild = interaction.guild ?? await interaction.client.guilds.fetch(interaction.guildId);
        const channel = await guild.channels.fetch(rawChannelId).catch(() => null);
        if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
          throw new Error("Choose a text or announcement channel in this server.");
        }
        const current = await getReleaseSchedule(interaction.guildId);
        const cadence = parseReleaseCadenceInput(
          interaction.fields.getTextInputValue("cadence"),
          current?.weekday ?? 1,
        );
        const nextRun = await saveReleaseSchedule({
          guildId: interaction.guildId,
          channelId: channel.id,
          actorId: interaction.user.id,
          timeZone: interaction.fields.getTextInputValue("time_zone"),
          localTime: interaction.fields.getTextInputValue("local_time"),
          cadence: cadence.cadence,
          weekday: cadence.weekday,
          categories: current?.categories ?? DIGEST_CATEGORIES,
          entityTypes: current?.entity_types ?? DIGEST_ENTITY_TYPES,
          entityIds: current?.entity_ids ?? ["all"],
          region: interaction.fields.getTextInputValue("region"),
          enabled: true,
        });
        await interaction.reply({
          content: "Media digest saved and enabled. Next delivery: <t:" + Math.floor(nextRun.getTime() / 1000) + ":F>.",
          flags: MessageFlags.Ephemeral,
        });
        return true;
      }
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
    if (interaction.isStringSelectMenu()
      && (interaction.customId === "settings:media-digest:categories"
        || interaction.customId === "settings:media-digest:entity-types"
        || interaction.customId === "settings:media-digest:entities")) {
      if (!canManage(interaction)) {
        await interaction.reply({ content: "Manage Server permission is required to configure media digests.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const schedule = await getReleaseSchedule(interaction.guildId);
      if (!schedule) {
        await interaction.reply({ content: "Configure a media digest before choosing its categories and followed-entity filters.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const isCategories = interaction.customId === "settings:media-digest:categories";
      const isEntityTypes = interaction.customId === "settings:media-digest:entity-types";
      await saveReleaseSchedule({
        guildId: interaction.guildId,
        channelId: schedule.channel_id,
        actorId: interaction.user.id,
        timeZone: schedule.time_zone,
        localTime: schedule.local_time,
        cadence: schedule.cadence,
        weekday: schedule.weekday,
        categories: isCategories ? interaction.values : schedule.categories,
        entityTypes: isEntityTypes ? interaction.values : schedule.entity_types,
        entityIds: !isCategories && !isEntityTypes ? interaction.values : schedule.entity_ids,
        region: schedule.region,
        enabled: schedule.enabled,
      });
      await interaction.update(await mediaDigestPanel(interaction.guildId));
      return true;
    }
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

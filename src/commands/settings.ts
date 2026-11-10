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
  type ButtonInteraction,
  type ChannelSelectMenuInteraction,
  type ChatInputCommandInteraction,
  type RoleSelectMenuInteraction,
  type StringSelectMenuInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import {
  FEATURE_NAMES,
  getFeatureSettings,
  isFeatureName,
  setFeatureEnabled,
  type FeatureName,
} from "../../helpers/runtime/settings.js";
import {
  getMediaNotificationSettings,
  setMediaNotificationSettings,
} from "../../helpers/media/media-notifications.js";
import { getGuildMediaRegion, setGuildMediaRegion } from "../../helpers/media/media-region.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import { query } from "../../database.js";
import { missingChannelPermissions } from "../../helpers/runtime/server-diagnostics.js";
import {
  canConfigureGuildLeaveAction,
  getGuildRetentionSettings,
  isGuildRetentionConfigured,
  setGuildLeaveAction,
} from "../../helpers/runtime/guild-retention.js";

type SettingsRow =
  | ActionRowBuilder<ButtonBuilder>
  | ActionRowBuilder<ChannelSelectMenuBuilder>;

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
          "Scans AniList for recently finished or cancelled anime and manga.",
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
    .setDescription("Choose what should happen to this server's stored Lemegeton data if the bot is removed. Normal bot features stay locked until a choice is saved.")
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

async function serverDiagnostics(guildId: string, currentChannelId: string, guild: NonNullable<ChatInputCommandInteraction["guild"]>): Promise<EmbedBuilder> {
  const rows = await query<{ name: string; channel_id: string }>(
    `SELECT 'Current media notifications' AS name, channel_id::text AS channel_id
       FROM media_notification_settings WHERE guild_id = $1 AND channel_id IS NOT NULL
     UNION ALL
     SELECT 'Archive uploads', upload_channel_id::text
       FROM guild_archive_settings WHERE guild_id = $1 AND upload_channel_id IS NOT NULL
     UNION ALL
     SELECT 'Archive moderation', moderation_channel_id::text
       FROM guild_archive_settings WHERE guild_id = $1 AND moderation_channel_id IS NOT NULL
     UNION ALL
     SELECT 'Custom Roles commands', command_channel_id::text
       FROM custom_role_guild_settings WHERE guild_id = $1 AND command_channel_id IS NOT NULL
     UNION ALL
     SELECT 'Custom Roles logs', log_channel_id::text
       FROM custom_role_guild_settings WHERE guild_id = $1 AND log_channel_id IS NOT NULL
     UNION ALL
     SELECT 'Daily Drop', channel_id::text
       FROM community_daily_schedules WHERE guild_id = $1 AND enabled = TRUE
     UNION ALL
     SELECT 'Release digest', channel_id::text
       FROM community_release_schedules WHERE guild_id = $1 AND enabled = TRUE
     ORDER BY name`,
    [guildId],
  );
  const checks = [{ name: "Current channel", channel_id: currentChannelId }, ...rows];
  const embed = new EmbedBuilder()
    .setColor(0x5865f2)
    .setTitle("Server Check")
    .setFooter({ text: "Read-only diagnostics · No server settings were changed" });

  let botMember;
  try {
    botMember = await guild.members.fetchMe();
  } catch {
    embed.setDescription("The bot's server member could not be resolved. No channel permissions could be verified.");
    return embed;
  }

  const results: Array<{ name: string; status: string; detail: string }> = [];
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
      detail: missing.length ? "Missing bot permissions: " + missing.join(", ") + "." : "View Channel, Send Messages and Embed Links are available.",
    });
  }

  const healthy = results.filter(item => item.status === "Healthy").length;
  const attention = results.filter(item => item.status === "Needs attention").length;
  embed.setDescription(`**Healthy:** ${healthy} · **Needs attention:** ${attention}\nChecks include this channel and configured v3 notification, Archive, Custom Roles and scheduled-delivery channels.`);
  for (const result of results) {
    embed.addFields({
      name: (result.status === "Healthy" ? "✓ " : "⚠ ") + result.name + " · " + result.status,
      value: result.detail,
      inline: false,
    });
  }
  if (rows.length === 0) {
    embed.addFields({ name: "Optional channels", value: "No additional delivery channels are configured.", inline: false });
  }
  return embed;
}

function canManage(
  interaction: ButtonInteraction | ChatInputCommandInteraction | ChannelSelectMenuInteraction | ModalSubmitInteraction,
): boolean {
  return interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false;
}

export class SettingsCommand implements FeatureCommand {
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
          { name: "Change media region", value: "media-region" },
          { name: "Data retention when the bot leaves", value: "retention" },
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
    if (action === "diagnostics") {
      if (!canManage(interaction)) {
        await interaction.reply({content:"Manage Server permission is required to run diagnostics.",flags:MessageFlags.Ephemeral});
        return;
      }
      await interaction.deferReply({flags:MessageFlags.Ephemeral});
      try {
        const guild = interaction.guild ?? await interaction.client.guilds.fetch(interaction.guildId);
        const embed = await serverDiagnostics(interaction.guildId, interaction.channelId, guild);
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
    const [, section, target] = interaction.customId.split(":");
    if (!interaction.guildId) return false;
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
    if (section !== "toggle" && section !== "notifications" && section !== "media-region") return false;
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
    if (interaction.customId !== "settings:media-region") return false;
    if (!interaction.guildId) return false;
    if (!canManage(interaction as ModalSubmitInteraction)) {
      await interaction.reply({content:"Manage Server permission is required to change the media region.",flags:MessageFlags.Ephemeral});
      return true;
    }
    try {
      const region = await setGuildMediaRegion(
        interaction.guildId,
        interaction.fields.getTextInputValue("region"),
        interaction.user.id,
      );
      await interaction.reply({content:"Default media availability region saved as " + region + ".",flags:MessageFlags.Ephemeral});
      return true;
    } catch (error) {
      const issueHash=await createInteractionIssueLog(interaction,"/settings",error,{action:"media-region-modal"});
      const message=error instanceof Error ? error.message : "The media region could not be saved.";
      await interaction.reply({content:issueHash?message+"\n\n"+issueHashNotice(issueHash):message,flags:MessageFlags.Ephemeral});
      return true;
    }
  }

  async handleSelect(
    interaction: StringSelectMenuInteraction | RoleSelectMenuInteraction | ChannelSelectMenuInteraction,
  ): Promise<boolean> {
    if (!interaction.isChannelSelectMenu() || interaction.customId !== "settings:notifications:channel") return false;
    if (!interaction.guildId) return false;
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

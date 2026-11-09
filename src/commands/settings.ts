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

function canManage(
  interaction: ButtonInteraction | ChatInputCommandInteraction | ChannelSelectMenuInteraction | ModalSubmitInteraction,
): boolean {
  return interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false;
}

export class SettingsCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("settings")
    .setDescription("Configure this server's features and media notifications")
    .addStringOption((option) =>
      option.setName("action")
        .setDescription("Open settings or choose a settings area")
        .addChoices(
          { name: "View all settings", value: "view" },
          { name: "Toggle a feature", value: "toggle" },
          { name: "Media notifications", value: "notifications" },
          { name: "Change media region", value: "media-region" },
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

    const action = interaction.options.getString("action") ?? "view";
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
    if (section !== "toggle" && section !== "notifications" && section !== "media-region") return false;
    if (!interaction.guildId) return false;
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

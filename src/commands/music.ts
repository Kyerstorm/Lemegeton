import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelSelectMenuBuilder,
  ChannelType,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  PermissionFlagsBits,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChannelSelectMenuInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import { randomUUID } from "node:crypto";
import { query } from "../../database.js";
import { logger } from "../../helpers/runtime/logger.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import {
  addMusicTracker,
  cleanMusicText,
  deleteMusicTracker,
  getMusicRuntime,
  getMusicTracker,
  listMusicTrackers,
  musicReleaseKey,
  providerName,
  updateMusicTracker,
  type MusicProvider,
  type MusicTracker,
} from "../../helpers/integration/music.js";

type MusicPayload = {
  embeds: EmbedBuilder[];
  components: (ActionRowBuilder<ButtonBuilder> | ActionRowBuilder<StringSelectMenuBuilder> | ActionRowBuilder<ChannelSelectMenuBuilder>)[];
  allowedMentions: { parse: [] };
};

type MusicInteraction =
  | ChatInputCommandInteraction
  | ButtonInteraction
  | ChannelSelectMenuInteraction
  | StringSelectMenuInteraction
  | ModalSubmitInteraction;

function button(customId: string, label: string, style: ButtonStyle, disabled = false): ButtonBuilder {
  return new ButtonBuilder().setCustomId(customId).setLabel(label).setStyle(style).setDisabled(disabled);
}

function providerNames(providers: MusicProvider[]): string {
  return providers.map(providerName).join(" · ") || "No provider matched";
}

function addArtistModal(channelId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("music:add-submit:" + channelId)
    .setTitle("Track an artist")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder()
          .setCustomId("artist")
          .setLabel("Artist name or provider profile URL")
          .setPlaceholder("Artist name, Spotify artist URL, YouTube channel or SoundCloud profile")
          .setStyle(TextInputStyle.Short)
          .setRequired(true)
          .setMaxLength(200),
      ),
    );
}

function removeConfirmation(tracker: MusicTracker): MusicPayload {
  const embed = new EmbedBuilder()
    .setColor(0xed4245)
    .setTitle("Remove music tracker?")
    .setDescription(
      "Remove **" + cleanMusicText(tracker.artist_name, 180) + "** from this server?\n\n" +
      "This also deletes its stored release history. Existing Discord messages are not removed.",
    )
    .addFields({ name: "Tracker", value: tracker.id });
  return {
    embeds: [embed],
    components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        button("music:remove-confirm:" + tracker.id, "Confirm removal", ButtonStyle.Danger),
        button("music:remove-cancel:" + tracker.id, "Cancel", ButtonStyle.Secondary),
      ),
    ],
    allowedMentions: { parse: [] },
  };
}

export class MusicCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("music")
    .setDescription("Track artists and manage new music releases for this server.")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild);

  private readonly runtime;

  constructor(config: BotConfig) {
    this.runtime = getMusicRuntime(config);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Music tracking is only available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (!this.canManage(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to manage music trackers.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ ...await this.homePayload(interaction.guildId), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("music:")) return false;
    if (!this.canManage(interaction) || !interaction.guildId) {
      await interaction.reply({ content: "Manage Server permission is required to manage music trackers.", flags: MessageFlags.Ephemeral });
      return true;
    }

    const [, action, trackerId] = interaction.customId.split(":");
    if (action === "home") {
      await interaction.update(await this.homePayload(interaction.guildId));
      return true;
    }
    if (action === "add") {
      await interaction.update(this.addChannelPayload());
      return true;
    }
    if (action === "list") {
      await interaction.update(await this.listPayload(interaction.guildId));
      return true;
    }
    if (!trackerId) return false;

    if (action === "test") {
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const tracker = await getMusicTracker(interaction.guildId, trackerId);
      if (!tracker) {
        await interaction.editReply({ content: "That tracker no longer exists." });
        return true;
      }
      const releases = await this.runtime.latest(tracker);
      const release = releases[0];
      if (!release) {
        await interaction.editReply({
          embeds: [new EmbedBuilder().setColor(0xfee75c).setTitle("No release found").setDescription(
            "None of the linked providers returned a recent release. The tracker remains unchanged.",
          )],
        });
        return true;
      }
      const embed = new EmbedBuilder()
        .setColor(0x5865f2)
        .setTitle("Latest release preview")
        .setDescription("## " + cleanMusicText(release.title, 250))
        .addFields(
          { name: "Artist", value: cleanMusicText(release.artist, 200), inline: true },
          { name: "Platform", value: providerName(release.provider), inline: true },
          { name: "Release", value: "[Open release](" + release.url + ")", inline: true },
        )
        .setURL(release.url);
      if (release.release_date) embed.addFields({ name: "Released", value: cleanMusicText(release.release_date, 100), inline: true });
      if (release.image_url) embed.setThumbnail(release.image_url);
      await interaction.editReply({ embeds: [embed] });
      return true;
    }

    if (action === "pause" || action === "resume") {
      const tracker = await getMusicTracker(interaction.guildId, trackerId);
      if (!tracker) {
        await interaction.update(this.notFoundPayload());
        return true;
      }
      tracker.enabled = action === "resume";
      await updateMusicTracker(tracker);
      await this.audit(interaction, "music." + action, "tracker=" + tracker.id + ";artist=" + tracker.artist_name);
      await interaction.update(await this.detailsPayload(tracker));
      return true;
    }

    if (action === "remove") {
      const tracker = await getMusicTracker(interaction.guildId, trackerId);
      await interaction.update(tracker ? removeConfirmation(tracker) : this.notFoundPayload());
      return true;
    }

    if (action === "remove-confirm") {
      const removed = await deleteMusicTracker(interaction.guildId, trackerId);
      if (removed) await this.audit(interaction, "music.remove", "tracker=" + trackerId);
      await interaction.update({
        embeds: [new EmbedBuilder()
          .setColor(removed ? 0x57f287 : 0xfee75c)
          .setTitle(removed ? "Tracker removed" : "Tracker already removed")
          .setDescription(removed ? "The tracker and its stored release history were deleted." : "That tracker no longer exists.")],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(button("music:list", "Back to trackers", ButtonStyle.Secondary))],
        allowedMentions: { parse: [] },
      });
      return true;
    }

    if (action === "remove-cancel") {
      const tracker = await getMusicTracker(interaction.guildId, trackerId);
      await interaction.update(tracker ? await this.detailsPayload(tracker) : this.notFoundPayload());
      return true;
    }
    return false;
  }

  async handleSelect(
    interaction: StringSelectMenuInteraction | ChannelSelectMenuInteraction,
  ): Promise<boolean> {
    if (!interaction.customId.startsWith("music:")) return false;
    if (!this.canManage(interaction) || !interaction.guildId) {
      await interaction.reply({ content: "Manage Server permission is required to manage music trackers.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (interaction.isChannelSelectMenu() && interaction.customId === "music:add-channel") {
      const channelId = interaction.values[0];
      if (!channelId || !/^\d{17,20}$/.test(channelId)) {
        await interaction.reply({ content: "Select a valid text channel.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(addArtistModal(channelId));
      return true;
    }

    if (interaction.isStringSelectMenu() && interaction.customId === "music:tracker-select") {
      const trackerId = interaction.values[0];
      if (!trackerId) {
        await interaction.reply({ content: "Select a tracker to manage.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const tracker = await getMusicTracker(interaction.guildId, trackerId);
      await interaction.update(tracker ? await this.detailsPayload(tracker) : this.notFoundPayload());
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("music:add-submit:")) return false;
    if (!this.canManage(interaction) || !interaction.guildId || !interaction.guild) {
      await interaction.reply({ content: "Manage Server permission is required to manage music trackers.", flags: MessageFlags.Ephemeral });
      return true;
    }

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    const channelId = interaction.customId.slice("music:add-submit:".length);
    const artist = interaction.fields.getTextInputValue("artist").trim();
    if (!artist || artist.length > 200) {
      await interaction.editReply({ content: "Enter an artist name or a supported provider profile URL." });
      return true;
    }

    const channel = await interaction.guild.channels.fetch(channelId).catch(() => null);
    if (!channel || channel.type !== ChannelType.GuildText) {
      await interaction.editReply({ content: "That announcement channel is unavailable. Start again and choose another text channel." });
      return true;
    }
    const botMember = await interaction.guild.members.fetchMe();
    const permissions = channel.permissionsFor(botMember);
    const required = [
      PermissionFlagsBits.ViewChannel,
      PermissionFlagsBits.SendMessages,
      PermissionFlagsBits.EmbedLinks,
    ];
    const missing = required.filter(permission => !permissions?.has(permission));
    if (missing.length) {
      await interaction.editReply({ content: "I cannot publish releases in that channel. Grant View Channel, Send Messages and Embed Links, then try again." });
      return true;
    }

    if ((await listMusicTrackers(interaction.guildId)).length >= 25) {
      await interaction.editReply({ content: "This server has reached its limit of 25 music trackers. Remove one before adding another." });
      return true;
    }

    const resolved = await this.runtime.resolveArtist(artist);
    if (!resolved.providers.length) {
      const status = this.runtime.providerStatus();
      await interaction.editReply({
        embeds: [new EmbedBuilder()
          .setColor(0xed4245)
          .setTitle("Artist not resolved")
          .setDescription(
            "I could not confidently identify **" + cleanMusicText(artist, 150) + "** on a supported provider.\n\n" +
            "Use a Spotify artist URL, YouTube channel or handle, or SoundCloud profile URL. " +
            "Name search requires the corresponding provider credentials.",
          )
          .addFields(
            { name: "Spotify", value: status.spotify ? "Ready" : "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required", inline: false },
            { name: "YouTube Music", value: status.youtube ? "Ready" : "YOUTUBE_API_KEY required", inline: false },
            { name: "SoundCloud", value: status.soundcloudSearch ? "Name search ready" : "Profile URLs work without SOUNDCLOUD_CLIENT_ID", inline: false },
          )],
      });
      return true;
    }

    const tracker: MusicTracker = {
      id: randomUUID(),
      guild_id: interaction.guildId,
      channel_id: channelId,
      artist_name: artist,
      providers: resolved.providers,
      spotify_target: resolved.spotify_target,
      youtube_target: resolved.youtube_target,
      soundcloud_target: resolved.soundcloud_target,
      mention_mode: "user",
      mention_user_id: interaction.user.id,
      mention_role_id: null,
      enabled: true,
      created_by: interaction.user.id,
      created_at: new Date().toISOString(),
      last_checked_at: null,
      seen_ids: [],
    };

    const baseline = await this.runtime.latest(tracker);
    tracker.seen_ids = baseline.map(musicReleaseKey).slice(-75);
    try {
      await addMusicTracker(tracker);
      await this.audit(interaction, "music.add", "tracker=" + tracker.id + ";artist=" + tracker.artist_name + ";providers=" + tracker.providers.join(",") + ";channel=" + tracker.channel_id);
    } catch (error) {
      if (error instanceof Error && error.message === "MUSIC_TRACKER_LIMIT") {
        await interaction.editReply({ content: "This server has reached its limit of 25 music trackers. Remove one before adding another." });
        return true;
      }
      throw error;
    }

    const embed = new EmbedBuilder()
      .setColor(0x57f287)
      .setTitle("Artist tracking enabled")
      .setDescription(
        "Lemegeton will check **" + cleanMusicText(artist, 180) + "** for new releases and announce them in <#" + channelId + ">.",
      )
      .addFields(
        { name: "Platforms", value: providerNames(tracker.providers), inline: true },
        { name: "Initial history", value: baseline.length + " release(s) synchronized without notifications", inline: true },
        { name: "Tracker ID", value: tracker.id, inline: false },
      )
      .setFooter({ text: "You will be mentioned when a new release is announced. Manage this tracker from /music." });
    await interaction.editReply({ embeds: [embed] });
    return true;
  }

  private async audit(interaction: MusicInteraction, action: string, details: string): Promise<void> {
    if (!interaction.guildId) return;
    try {
      await query(
        "INSERT INTO dashboard_audit_log (guild_id, actor_id, action, details) VALUES ($1,$2,$3,$4)",
        [interaction.guildId, interaction.user.id, action, details.slice(0, 1000)],
      );
    } catch (error) {
      logger.warn("Music tracker audit event could not be recorded", {
        guildId: interaction.guildId,
        action,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
  }

  private canManage(interaction: MusicInteraction): boolean {
    return Boolean(interaction.guildId && interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild));
  }

  private async homePayload(guildId: string): Promise<MusicPayload> {
    const trackers = await listMusicTrackers(guildId);
    const active = trackers.filter(tracker => tracker.enabled).length;
    const status = this.runtime.providerStatus();
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle("Music")
      .setDescription(
        "Track artists across Spotify, YouTube Music and SoundCloud. New releases are published automatically in the channel chosen for each tracker.",
      )
      .addFields(
        { name: "Trackers", value: trackers.length + " / 25 configured\n" + active + " active", inline: true },
        { name: "Polling", value: "Every " + this.runtimeInterval() + " minutes", inline: true },
        { name: "Providers", value:
          "Spotify: " + (status.spotify ? "Ready" : "Not configured") + "\n" +
          "YouTube Music: " + (status.youtube ? "Ready" : "Not configured") + "\n" +
          "SoundCloud: " + (status.soundcloudSearch ? "Name search ready" : "Profile URLs only"), inline: false },
      )
      .setFooter({ text: "Manage Server permission required · Tracker data is isolated by server" });
    return {
      embeds: [embed],
      components: [
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          button("music:add", "Track an artist", ButtonStyle.Primary, trackers.length >= 25),
          button("music:list", "Manage trackers", ButtonStyle.Secondary, trackers.length === 0),
        ),
      ],
      allowedMentions: { parse: [] },
    };
  }

  private runtimeInterval(): number {
    return this.runtime.pollIntervalMinutes;
  }

  private addChannelPayload(): MusicPayload {
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle("Choose an announcement channel")
      .setDescription("Select the text channel where new releases for this artist should be posted.");
    const select = new ChannelSelectMenuBuilder()
      .setCustomId("music:add-channel")
      .setPlaceholder("Select a text channel")
      .setChannelTypes(ChannelType.GuildText)
      .setMinValues(1)
      .setMaxValues(1);
    return {
      embeds: [embed],
      components: [
        new ActionRowBuilder<ChannelSelectMenuBuilder>().addComponents(select),
        new ActionRowBuilder<ButtonBuilder>().addComponents(button("music:home", "Back", ButtonStyle.Secondary)),
      ],
      allowedMentions: { parse: [] },
    };
  }

  private async listPayload(guildId: string): Promise<MusicPayload> {
    const trackers = await listMusicTrackers(guildId);
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle("Music trackers")
      .setDescription(trackers.length
        ? "Choose a tracker to preview releases, pause or resume monitoring, or remove it."
        : "No trackers are configured for this server yet.");
    for (const [index, tracker] of trackers.entries()) {
      const status = tracker.enabled ? "Active" : "Paused";
      embed.addFields({
        name: (index + 1) + ". " + cleanMusicText(tracker.artist_name, 180),
        value: status + " · " + providerNames(tracker.providers) + "\nChannel: <#" + tracker.channel_id + ">",
        inline: true,
      });
    }
    const components: MusicPayload["components"] = [];
    if (trackers.length) {
      const select = new StringSelectMenuBuilder()
        .setCustomId("music:tracker-select")
        .setPlaceholder("Select a tracker")
        .setMinValues(1)
        .setMaxValues(1)
        .addOptions(trackers.map(tracker => ({
          label: cleanMusicText(tracker.artist_name, 90) || "Untitled artist",
          description: (tracker.enabled ? "Active" : "Paused") + " · " + providerNames(tracker.providers).slice(0, 70),
          value: tracker.id,
        })));
      components.push(new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select));
    }
    components.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
      button("music:add", "Track an artist", ButtonStyle.Primary, trackers.length >= 25),
      button("music:home", "Back", ButtonStyle.Secondary),
    ));
    return { embeds: [embed], components, allowedMentions: { parse: [] } };
  }

  private async detailsPayload(tracker: MusicTracker): Promise<MusicPayload> {
    const lastChecked = tracker.last_checked_at && Number.isFinite(Date.parse(tracker.last_checked_at))
      ? "<t:" + Math.floor(Date.parse(tracker.last_checked_at) / 1000) + ":R>"
      : "Not checked yet";
    const embed = new EmbedBuilder()
      .setColor(tracker.enabled ? 0x57f287 : 0xfee75c)
      .setTitle(cleanMusicText(tracker.artist_name, 220))
      .setDescription(tracker.enabled ? "This artist is being monitored for new releases." : "This tracker is paused.")
      .addFields(
        { name: "Status", value: tracker.enabled ? "Active" : "Paused", inline: true },
        { name: "Platforms", value: providerNames(tracker.providers), inline: true },
        { name: "Announcement channel", value: "<#" + tracker.channel_id + ">", inline: true },
        { name: "Notifications", value: tracker.mention_mode === "user" && tracker.mention_user_id ? "<@" + tracker.mention_user_id + ">" : "No mention", inline: true },
        { name: "Last checked", value: lastChecked, inline: true },
        { name: "Tracker ID", value: tracker.id, inline: false },
      );
    return {
      embeds: [embed],
      components: [
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          button("music:test:" + tracker.id, "Test latest release", ButtonStyle.Primary),
          button("music:" + (tracker.enabled ? "pause" : "resume") + ":" + tracker.id, tracker.enabled ? "Pause" : "Resume", ButtonStyle.Secondary),
          button("music:remove:" + tracker.id, "Remove", ButtonStyle.Danger),
          button("music:list", "Back", ButtonStyle.Secondary),
        ),
      ],
      allowedMentions: { parse: [] },
    };
  }

  private notFoundPayload(): MusicPayload {
    return {
      embeds: [new EmbedBuilder().setColor(0xfee75c).setTitle("Tracker not found").setDescription("That tracker may have been removed. Refresh the tracker list and try again.")],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(button("music:list", "Refresh trackers", ButtonStyle.Secondary))],
      allowedMentions: { parse: [] },
    };
  }
}

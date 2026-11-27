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
import { query } from "../utility/database/libsql/database.js";
import { logger } from "../../helpers/runtime/logger.js";
import { emoji, providerEmoji } from "../../helpers/emoji.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import { setProviderFooter } from "../../helpers/runtime/discord.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { MusicDiscovery } from "../../helpers/integration/music-discovery.js";
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
  const icon = customId.includes("remove") ? emoji.warning
    : customId.includes("test") ? emoji.refresh
      : customId.includes("pause") ? emoji.pause
        : customId.includes("resume") ? emoji.check
          : customId.includes("add") ? emoji.upload
            : customId.includes("list") || customId.includes("home") ? emoji.music : null;
  const result = new ButtonBuilder().setCustomId(customId).setLabel(label).setStyle(style).setDisabled(disabled);
  if (icon) result.setEmoji(icon);
  return result;
}

function safeProviderLink(value: string | null, domain: string): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && (url.hostname === domain || url.hostname.endsWith("." + domain))
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function providerNames(providers: MusicProvider[]): string {
  return providers.map(provider => providerEmoji(providerName(provider)) + " " + providerName(provider)).join(" · ") || "No provider matched";
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

function exploreArtistModal(): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("music:explore-submit")
    .setTitle("Explore an artist")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder()
          .setCustomId("artist")
          .setLabel("Artist or band name")
          .setPlaceholder("Search MusicBrainz artist catalogue")
          .setStyle(TextInputStyle.Short)
          .setRequired(true)
          .setMaxLength(100),
      ),
    );
}

function removeConfirmation(tracker: MusicTracker): MusicPayload {
  const embed = new EmbedBuilder()
    .setColor(EMBED_COLOURS.danger)
    .setTitle(emoji.warning + " Remove music tracker?")
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
    .setDescription("Explore music, browse charts and track new releases for this server.");

  private readonly runtime;
  private readonly discovery: MusicDiscovery;

  constructor(config: BotConfig) {
    this.runtime = getMusicRuntime(config);
    this.discovery = new MusicDiscovery(config);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Music tracking is only available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ ...await this.homePayload(interaction.guildId), flags: MessageFlags.Ephemeral });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("music:")) return false;
    if (!interaction.guildId) {
      await interaction.reply({ content: "Music browsing and tracking are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    const [, action, trackerId] = interaction.customId.split(":");
    const managementActions = new Set(["add", "list", "pause", "resume", "remove", "remove-confirm", "remove-cancel", "test"]);
    if (action && managementActions.has(action) && !this.canManage(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to manage music trackers.", flags: MessageFlags.Ephemeral });
      return true;
    }
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
    if (action === "explore") {
      await interaction.showModal(exploreArtistModal());
      return true;
    }
    if (action === "charts") {
      await interaction.update(this.chartsMenuPayload());
      return true;
    }
    if (action === "chart-artists" || action === "chart-tracks") {
      await interaction.deferUpdate();
      try {
        await interaction.editReply(await this.chartPayload(action === "chart-artists" ? "artists" : "tracks"));
      } catch (error) {
        await interaction.editReply({ content: error instanceof Error ? error.message : "The music chart is temporarily unavailable." });
      }
      return true;
    }
    if (action === "artist" && trackerId) {
      await interaction.deferUpdate();
      await interaction.editReply(await this.artistPayload(trackerId));
      return true;
    }
    if (action === "discography" && trackerId) {
      await interaction.deferUpdate();
      const offset = Number(interaction.customId.split(":")[3] ?? "0");
      await interaction.editReply(await this.discographyPayload(trackerId, Number.isFinite(offset) ? offset : 0));
      return true;
    }
    if (action === "setlists" && trackerId) {
      await interaction.deferUpdate();
      try {
        await interaction.editReply(await this.setlistsPayload(trackerId));
      } catch (error) {
        await interaction.editReply({ content: error instanceof Error ? error.message : "Concert setlists are temporarily unavailable." });
      }
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
          embeds: [new EmbedBuilder().setColor(EMBED_COLOURS.warning).setTitle(emoji.info + " No release found").setDescription(
            "None of the linked providers returned a recent release. The tracker remains unchanged.",
          )],
        });
        return true;
      }
      const embed = new EmbedBuilder()
        .setColor(EMBED_COLOURS.primary)
        .setTitle(emoji.music + " Latest release preview")
        .setDescription("## " + cleanMusicText(release.title, 250))
        .addFields(
          { name: "Artist", value: cleanMusicText(release.artist, 200), inline: true },
          { name: "Platform", value: providerName(release.provider), inline: true },
          { name: "Release", value: "[Open release](" + release.url + ")", inline: true },
        )
        .setURL(release.url);
      setProviderFooter(embed, providerName(release.provider), "Latest release");
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
          .setColor(removed ? EMBED_COLOURS.success : EMBED_COLOURS.warning)
          .setTitle((removed ? emoji.success : emoji.warning) + " " + (removed ? "Tracker removed" : "Tracker already removed"))
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
    if (!interaction.guildId) {
      await interaction.reply({ content: "Music browsing and tracking are available inside a server.", flags: MessageFlags.Ephemeral });
      return true;
    }

    if (interaction.isChannelSelectMenu() && !this.canManage(interaction)) {
      await interaction.reply({ content: "Manage Server permission is required to choose a tracker destination.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (interaction.isStringSelectMenu() && interaction.customId === "music:tracker-select" && !this.canManage(interaction)) {
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

    if (interaction.isStringSelectMenu() && interaction.customId === "music:artist-select") {
      const artistId = interaction.values[0];
      if (!artistId) {
        await interaction.reply({ content: "Select an artist to explore.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferUpdate();
      await interaction.editReply(await this.artistPayload(artistId));
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
    if (interaction.customId === "music:explore-submit") {
      if (!interaction.guildId) {
        await interaction.reply({ content: "Music discovery is available inside a server.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const queryText = interaction.fields.getTextInputValue("artist").trim();
      if (!queryText || queryText.length > 100) {
        await interaction.editReply({ content: "Enter an artist name up to 100 characters." });
        return true;
      }
      try {
        const artists = await this.discovery.searchArtists(queryText);
        if (!artists.length) {
          await interaction.editReply({ content: "No matching artists were found in MusicBrainz." });
          return true;
        }
        const select = new StringSelectMenuBuilder()
          .setCustomId("music:artist-select")
          .setPlaceholder("Choose an artist")
          .setMinValues(1)
          .setMaxValues(1)
          .addOptions(artists.map(artist => ({
            label: artist.name.slice(0, 100),
            description: [artist.type, artist.country, artist.disambiguation].filter(Boolean).join(" · ").slice(0, 100) || "MusicBrainz artist",
            value: artist.id,
          })));
        const embed = new EmbedBuilder()
          .setColor(EMBED_COLOURS.primary)
          .setTitle(emoji.music + " Artist results")
          .setDescription("Choose the correct artist. Disambiguation and origin are included when available.")
          .setFooter({ text: "Source: MusicBrainz" });
        await interaction.editReply({
          embeds: [embed],
          components: [new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(select)],
          allowedMentions: { parse: [] },
        });
      } catch (error) {
        await interaction.editReply({ content: error instanceof Error ? error.message : "MusicBrainz search is temporarily unavailable." });
      }
      return true;
    }
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
          .setColor(EMBED_COLOURS.danger)
          .setTitle(emoji.warning + " Artist not resolved")
          .setDescription(
            "I could not confidently identify **" + cleanMusicText(artist, 150) + "** on a supported provider.\n\n" +
            "Use a Spotify artist URL, YouTube channel or handle, or SoundCloud profile URL. " +
            "Name search requires the corresponding provider credentials.",
          )
          .addFields(
            { name: "Spotify", value: status.spotify ? "Ready" : "SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required", inline: false },
            { name: "YouTube Music", value: status.youtube ? "Ready" : "YOUTUBE_API_KEY required", inline: false },
            { name: "SoundCloud", value: status.soundcloudSearch ? "Name search ready" : "Profile URLs work without SoundCloud app credentials", inline: false },
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
      .setColor(EMBED_COLOURS.success)
      .setTitle(emoji.success + " Artist tracking enabled")
      .setDescription(
        "Lemegeton will check **" + cleanMusicText(artist, 180) + "** for new releases and announce them in <#" + channelId + ">.",
      )
      .addFields(
        { name: "Platforms", value: providerNames(tracker.providers), inline: true },
        { name: "Initial history", value: baseline.length + " release(s) synchronized without notifications", inline: true },
        { name: "Tracker ID", value: tracker.id, inline: false },
      )
      .setFooter({ text: emoji.music + " New releases · Manage this tracker from /music" });
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
    const discoveryStatus = this.discovery.providerStatus();
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Music")
      .setDescription(
        "Track artist releases, explore discographies, browse public charts and look up live setlists from one Music panel.",
      )
      .addFields(
        { name: "Trackers", value: trackers.length + " / 25 configured\n" + active + " active", inline: true },
        { name: "Polling", value: "Every " + this.runtimeInterval() + " minutes", inline: true },
        { name: "Providers", value:
          "Spotify: " + (status.spotify ? "Ready" : "Not configured") + "\n" +
          "YouTube Music: " + (status.youtube ? "Ready" : "Not configured") + "\n" +
          "SoundCloud: " + (status.soundcloudSearch ? "Name search ready" : "Profile URLs only") + "\n" +
          "MusicBrainz: " + (discoveryStatus.musicbrainz ? "Ready" : "Unavailable") + "\n" +
          "Last.fm charts: " + (discoveryStatus.lastfm ? "Ready" : "Not configured") + "\n" +
          "setlist.fm: " + (discoveryStatus.setlistfm ? "Ready" : "Not configured"), inline: false },
      )
      .setFooter({ text: emoji.settings + " Manage Server permission required · Tracker data is isolated by server" });
    return {
      embeds: [embed],
      components: [
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          button("music:add", "Track an artist", ButtonStyle.Primary, trackers.length >= 25),
          button("music:list", "Manage trackers", ButtonStyle.Secondary, trackers.length === 0),
        ),
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          button("music:explore", "Explore artists", ButtonStyle.Primary),
          button("music:charts", "Music charts", ButtonStyle.Secondary, !discoveryStatus.lastfm),
        ),
      ],
      allowedMentions: { parse: [] },
    };
  }

  private chartsMenuPayload(): MusicPayload {
    const status = this.discovery.providerStatus();
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Music charts")
      .setDescription(status.lastfm
        ? "Browse public Last.fm global charts. These rankings are provider data, not listening statistics for this server."
        : "Configure LASTFM_API_KEY to enable global artist and track charts.")
      .setFooter({ text: "Source: Last.fm" });
    return {
      embeds: [embed],
      components: [
        new ActionRowBuilder<ButtonBuilder>().addComponents(
          button("music:chart-artists", "Top artists", ButtonStyle.Primary, !status.lastfm),
          button("music:chart-tracks", "Top tracks", ButtonStyle.Secondary, !status.lastfm),
          button("music:home", "Back", ButtonStyle.Secondary),
        ),
      ],
      allowedMentions: { parse: [] },
    };
  }

  private async chartPayload(kind: "artists" | "tracks"): Promise<MusicPayload> {
    const entries = await this.discovery.charts(kind);
    const lines = entries.map((entry, index) => {
      const label = kind === "artists" ? entry.title : entry.title + " — " + entry.artist;
      const safeUrl = safeProviderLink(entry.url, "last.fm");
      const name = cleanMusicText(label, 150);
      const linked = safeUrl ? "[" + name + "](" + safeUrl + ")" : name;
      const plays = entry.playcount ? " · " + entry.playcount.toLocaleString("en-US") + " plays" : "";
      return "**" + (index + 1) + ".** " + linked + plays;
    });
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Last.fm global " + (kind === "artists" ? "artists" : "tracks"))
      .setDescription(lines.join("\n") || "No chart entries were returned.")
      .setFooter({ text: "Source: Last.fm · Public global chart" });
    return {
      embeds: [embed],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        button("music:charts", "Charts", ButtonStyle.Secondary),
        button("music:home", "Music home", ButtonStyle.Secondary),
      )],
      allowedMentions: { parse: [] },
    };
  }

  private async artistPayload(artistId: string): Promise<MusicPayload> {
    const artist = await this.discovery.artist(artistId);
    if (!artist) {
      return {
        embeds: [new EmbedBuilder().setColor(EMBED_COLOURS.warning).setTitle(emoji.warning + " Artist not found").setDescription("That MusicBrainz artist could not be loaded.")],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(button("music:explore", "Search again", ButtonStyle.Primary), button("music:home", "Back", ButtonStyle.Secondary))],
        allowedMentions: { parse: [] },
      };
    }
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(cleanMusicText(artist.name, 250))
      .setURL("https://musicbrainz.org/artist/" + artist.id)
      .setDescription(artist.disambiguation ? cleanMusicText(artist.disambiguation, 500) : "MusicBrainz artist profile")
      .addFields(
        { name: "Type", value: artist.type ?? "Unknown", inline: true },
        { name: "Country", value: artist.country ?? "Unknown", inline: true },
        { name: "Area", value: artist.beginArea ?? "Unknown", inline: true },
        { name: "Active since", value: artist.beginDate ?? "Unknown", inline: true },
        { name: "MusicBrainz ID", value: artist.id, inline: false },
      );
    setProviderFooter(embed, "MusicBrainz", "Artist profile");
    const status = this.discovery.providerStatus();
    return {
      embeds: [embed],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        button("music:discography:" + artist.id + ":0", "Discography", ButtonStyle.Primary),
        button("music:setlists:" + artist.id, "Live setlists", ButtonStyle.Secondary, !status.setlistfm),
        button("music:explore", "Search another", ButtonStyle.Secondary),
        button("music:home", "Music home", ButtonStyle.Secondary),
      )],
      allowedMentions: { parse: [] },
    };
  }

  private async discographyPayload(artistId: string, offset: number): Promise<MusicPayload> {
    const groups = await this.discovery.discography(artistId, offset);
    const lines = groups.map((group, index) => {
      const type = group.type ?? "Release";
      const secondary = group.secondaryTypes.length ? " · " + group.secondaryTypes.join(", ") : "";
      const date = group.firstReleaseDate ? " · " + group.firstReleaseDate : "";
      const url = "https://musicbrainz.org/release-group/" + group.id;
      return "**" + (offset + index + 1) + ".** [" + cleanMusicText(group.title, 180) + "](" + url + ") — " + cleanMusicText(type + secondary + date, 100);
    });
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Discography")
      .setDescription(lines.join("\n") || "No release groups were found for this artist.")
      .setFooter({ text: "Source: MusicBrainz · Editions are grouped by release group" });
    const buttons = new ActionRowBuilder<ButtonBuilder>().addComponents(
      button("music:discography:" + artistId + ":" + Math.max(0, offset - 10), "Previous", ButtonStyle.Secondary, offset <= 0),
      button("music:discography:" + artistId + ":" + (offset + 10), "Next", ButtonStyle.Secondary, groups.length < 10),
      button("music:artist:" + artistId, "Artist", ButtonStyle.Secondary),
      button("music:home", "Music home", ButtonStyle.Secondary),
    );
    return { embeds: [embed], components: [buttons], allowedMentions: { parse: [] } };
  }

  private async setlistsPayload(artistId: string): Promise<MusicPayload> {
    const setlists = await this.discovery.setlists(artistId);
    const lines = setlists.slice(0, 3).map(setlist => {
      const location = [setlist.venue, setlist.city, setlist.country].filter(Boolean).join(", ");
      const date = setlist.date ?? "Date unknown";
      const link = safeProviderLink(setlist.url, "setlist.fm");
      const title = link ? "[" + cleanMusicText(location, 180) + "](" + link + ")" : cleanMusicText(location, 180);
      const songs = setlist.songs.slice(0, 6).map((song, index) => (index + 1) + ". " + cleanMusicText(song, 60)).join("\n");
      return "**" + cleanMusicText(date, 40) + "** — " + title +
        (setlist.tour ? "\n" + cleanMusicText(setlist.tour, 120) : "") +
        (songs ? "\n" + songs : "");
    });
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Recent setlists")
      .setDescription(lines.join("\n\n") || "No setlists were found for this artist.")
      .setFooter({ text: "Source: setlist.fm" });
    return {
      embeds: [embed],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        button("music:artist:" + artistId, "Artist", ButtonStyle.Secondary),
        button("music:home", "Music home", ButtonStyle.Secondary),
      )],
      allowedMentions: { parse: [] },
    };
  }

  private runtimeInterval(): number {
    return this.runtime.pollIntervalMinutes;
  }

  private addChannelPayload(): MusicPayload {
    const embed = new EmbedBuilder()
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.calendar + " Choose an announcement channel")
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
      .setColor(EMBED_COLOURS.primary)
      .setTitle(emoji.music + " Music trackers")
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
      .setColor(tracker.enabled ? EMBED_COLOURS.success : EMBED_COLOURS.warning)
      .setTitle(emoji.music + " " + cleanMusicText(tracker.artist_name, 220))
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
      embeds: [new EmbedBuilder().setColor(EMBED_COLOURS.warning).setTitle(emoji.warning + " Tracker not found").setDescription("That tracker may have been removed. Refresh the tracker list and try again.")],
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(button("music:list", "Refresh trackers", ButtonStyle.Secondary))],
      allowedMentions: { parse: [] },
    };
  }
}

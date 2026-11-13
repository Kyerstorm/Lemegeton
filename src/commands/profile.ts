import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  SlashCommandBuilder,
  TextInputBuilder,
  TextInputStyle,
  type AutocompleteInteraction,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import { emoji } from "../../helpers/emoji.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import { AniListClient } from "../../helpers/integration/anilist.js";
import { SteamClient } from "../../helpers/integration/steam.js";
import {
  getAniListAffinity,
  getAniListLeaderboard,
  getAniListProfileAchievements,
  getLinkedProfile,
  getProfilePreferences,
  getServerTaste,
  linkAniListAccount,
  linkSteamAccount,
  unlinkAniListAccount,
  unlinkSteamAccount,
  updateProfilePreferences,
} from "../../helpers/runtime/profile.js";
import { homeEmbed } from "../../helpers/runtime/discord.js";
import { type AniListLeaderboardEntry, type AniListLeaderboardMode } from "../../helpers/runtime/anilist-leaderboard.js";
import { queryOne } from "../../database.js";
import { isDiscordSnowflake, safeDisplay } from "../../helpers/security/security.js";

interface LeaderboardSession {
  token: string;
  userId: string;
  guildId: string;
  mode: AniListLeaderboardMode;
  entries: AniListLeaderboardEntry[];
  optedIn: number;
  expiresAt: number;
}

const LEADERBOARD_PAGE_SIZE = 5;
const LEADERBOARD_SESSION_TTL_MS = 5 * 60 * 1000;
const leaderboardSessions = new Map<string, LeaderboardSession>();

const LEADERBOARD_PRESENTATION: Record<AniListLeaderboardMode, { title: string; description: string }> = {
  anime: { title: `${emoji.rankingAnime} Anime Golden Ratio`, description: "Users ranked by Average Episodes per Anime." },
  manga: { title: `${emoji.rankingManga} Manga Golden Ratio`, description: "Users ranked by Average Chapters per Manga." },
  combined: { title: `${emoji.rankingCombined} Ultimate Otaku Ranking`, description: "Users ranked by Origin-Weighted Activity Score. Origin and format splits are estimates derived from aggregate AniList statistics." },
  chapters: { title: `${emoji.rankingChapters} Most Chapters Read`, description: "Users ranked by total chapters read." },
  episodes: { title: `${emoji.rankingEpisodes} Most Episodes Watched`, description: "Users ranked by total episodes watched." },
  manga_completed: { title: `${emoji.finish} Most Manga Completed`, description: "Users ranked by total manga entries completed." },
  anime_completed: { title: `${emoji.finish} Most Anime Completed`, description: "Users ranked by total anime entries completed." },
};

function leaderboardPage(
  session: LeaderboardSession,
  page: number,
): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const config = LEADERBOARD_PRESENTATION[session.mode];
  const pageCount = Math.max(1, Math.ceil(session.entries.length / LEADERBOARD_PAGE_SIZE));
  const start = page * LEADERBOARD_PAGE_SIZE;
  const pageEntries = session.entries.slice(start, start + LEADERBOARD_PAGE_SIZE);
  const medals = [emoji.goldMedal, emoji.silverMedal, emoji.bronzeMedal];
  const fields = pageEntries.map((entry, index) => {
    const rank = start + index + 1;
    const label = medals[rank - 1] ?? `${rank}.`;
    let value: string;
    switch (session.mode) {
      case "anime":
        value = [
          `**Total Anime:** ${entry.totalAnime.toLocaleString("en-US")}`,
          `**Total Episodes Watched:** ${entry.totalEpisodes.toLocaleString("en-US")}`,
          `**Average Episodes per Anime:** ${entry.animeAverage.toFixed(2)}`,
        ].join("\n");
        break;
      case "manga":
        value = [
          `**Total Manga:** ${entry.totalManga.toLocaleString("en-US")}`,
          `**Total Chapters Read:** ${entry.totalChapters.toLocaleString("en-US")}`,
          `**Average Chapters per Manga:** ${entry.mangaAverage.toFixed(2)}`,
        ].join("\n");
        break;
      case "combined":
        value = [
          `**${emoji.manga} Manga:** ${entry.totalManga.toLocaleString("en-US")} titles, ${entry.totalChapters.toLocaleString("en-US")} chapters`,
          `**${emoji.movie} Anime:** ${entry.totalAnime.toLocaleString("en-US")} titles, ${entry.totalEpisodes.toLocaleString("en-US")} episodes`,
          `**${emoji.rankingCombined} Activity Score:** ${Math.trunc(entry.activityScore).toLocaleString("en-US")} points`,
        ].join("\n");
        break;
      case "chapters":
        value = `**Total Chapters Read:** ${entry.totalChapters.toLocaleString("en-US")}`;
        break;
      case "episodes":
        value = `**Total Episodes Watched:** ${entry.totalEpisodes.toLocaleString("en-US")}`;
        break;
      case "manga_completed":
        value = `**Total Completed:** ${entry.mangaCompleted.toLocaleString("en-US")}`;
        break;
      case "anime_completed":
        value = `**Total Completed:** ${entry.animeCompleted.toLocaleString("en-US")}`;
        break;
    }
    return {
      name: `${label} ${safeDisplay(entry.aniListName, 180)}`,
      value: `${value}\n[Open AniList profile](${entry.aniListUrl})`,
      inline: false,
    };
  });
  const embed = homeEmbed(
    `${emoji.leaderboard} ${config.title}`,
    `${config.description} (Page ${page + 1}/${pageCount})\n\n${session.optedIn.toLocaleString("en-US")} members opted in. Only current members of this server are included.`,
    fields.length ? fields : [{ name: "No data", value: "No opted-in AniList profiles were available.", inline: false }],
  ).setFooter({
    text: emoji.refreshUnicode + " Leaderboard based on live AniList statistics",
    iconURL: "https://anilist.co/img/icons/android-chrome-512x512.png",
  });
  const controls = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder()
      .setCustomId(`profile:leaderboard-page:${session.token}:${page - 1}`)
      .setLabel(emoji.chevronLeft + " Previous")
      .setEmoji(emoji.chevronLeft)
      .setStyle(ButtonStyle.Primary)
      .setDisabled(page <= 0),
    new ButtonBuilder()
      .setCustomId(`profile:leaderboard-page:${session.token}:${page + 1}`)
      .setLabel("Next " + emoji.chevronRight)
      .setEmoji(emoji.chevronRight)
      .setStyle(ButtonStyle.Primary)
      .setDisabled(page >= pageCount - 1),
  );
  return { embeds: [embed], components: [controls] };
}

function profileHome(): { embeds: EmbedBuilder[]; components: ActionRowBuilder<ButtonBuilder>[] } {
  const embed = homeEmbed(
    "Profile & Connections",
    "Connect existing AniList and Steam accounts, control what other members can see, and optionally participate in explainable shared-interest comparisons. Lemegeton does not track personal watching, reading or play progress.",
    [
      { name: "Connections", value: "AniList and Steam, independently linked per server.", inline: true },
      { name: "Privacy", value: "Public profile, provider visibility and affinity are separate settings.", inline: true },
      { name: "Server Taste", value: "Anonymous genre aggregates require at least three opted-in members.", inline: true },
    ],
  );
  return {
    embeds: [embed],
    components: [
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("profile:link-anilist").setLabel("Connect AniList").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("profile:link-steam").setLabel("Connect Steam").setStyle(ButtonStyle.Primary),
        new ButtonBuilder().setCustomId("profile:view").setLabel("View my profile").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:privacy").setLabel("Privacy settings").setStyle(ButtonStyle.Secondary),
      ),
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("profile:affinity").setLabel("Compare interests").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:taste").setLabel("Server Taste").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:unlink").setLabel("Manage connections").setStyle(ButtonStyle.Danger),
      ),
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("profile:leaderboard:anime").setLabel("Anime Golden Ratio").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:leaderboard:manga").setLabel("Manga Golden Ratio").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:leaderboard:combined").setLabel("Combined Score").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:leaderboard:chapters").setLabel("Chapters").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:leaderboard:episodes").setLabel("Episodes").setStyle(ButtonStyle.Secondary),
      ),
      new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId("profile:leaderboard:manga_completed").setLabel("Manga Completed").setStyle(ButtonStyle.Secondary),
        new ButtonBuilder().setCustomId("profile:leaderboard:anime_completed").setLabel("Anime Completed").setStyle(ButtonStyle.Secondary),
      ),
    ],
  };
}

function linkModal(kind: "anilist" | "steam"): ModalBuilder {
  const isAniList = kind === "anilist";
  return new ModalBuilder()
    .setCustomId(`profile:link:${kind}`)
    .setTitle(isAniList ? "Connect AniList" : "Connect Steam")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder()
        .setCustomId("account")
        .setLabel(isAniList ? "AniList username" : "Steam vanity name or SteamID64")
        .setStyle(TextInputStyle.Short)
        .setRequired(true)
        .setMaxLength(100)
        .setPlaceholder(isAniList ? "Your exact AniList username" : "steamcommunity.com/id/username"),
    ));
}

function affinityModal(): ModalBuilder {
  return new ModalBuilder()
    .setCustomId("profile:affinity")
    .setTitle("Compare shared media interests")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder()
        .setCustomId("member")
        .setLabel("Member mention or Discord user ID")
        .setStyle(TextInputStyle.Short)
        .setRequired(true)
        .setMaxLength(40),
    ));
}

function privacyEmbed(
  prefs: Awaited<ReturnType<typeof getProfilePreferences>>,
): EmbedBuilder {
  const state = (enabled: boolean) => enabled ? "On" : "Off";
  return homeEmbed("Profile privacy", "These settings are separate. Your profile is private by default. Affinity and Server Taste are opt-in and never enabled by connecting an account.", [
    { name: "Public profile", value: state(prefs.public_profile), inline: true },
    { name: "Show AniList", value: state(prefs.show_anilist), inline: true },
    { name: "Show Steam", value: state(prefs.show_steam), inline: true },
    { name: "Share for affinity", value: state(prefs.allow_affinity), inline: true },
    { name: "Server Taste opt-in", value: state(prefs.server_taste_opt_in), inline: true },
    { name: "AniList leaderboard", value: state(prefs.share_leaderboard), inline: true },
  ]);
}

function privacyButtons(prefs: Awaited<ReturnType<typeof getProfilePreferences>>): ActionRowBuilder<ButtonBuilder>[] {
  return [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("profile:toggle:public_profile").setLabel(`Public profile: ${prefs.public_profile ? "On" : "Off"}`).setStyle(prefs.public_profile ? ButtonStyle.Success : ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("profile:toggle:show_anilist").setLabel(`AniList: ${prefs.show_anilist ? "On" : "Off"}`).setStyle(prefs.show_anilist ? ButtonStyle.Success : ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("profile:toggle:show_steam").setLabel(`Steam: ${prefs.show_steam ? "On" : "Off"}`).setStyle(prefs.show_steam ? ButtonStyle.Success : ButtonStyle.Secondary),
    ),
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("profile:toggle:allow_affinity").setLabel(`Affinity sharing: ${prefs.allow_affinity ? "On" : "Off"}`).setStyle(prefs.allow_affinity ? ButtonStyle.Success : ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("profile:toggle:server_taste_opt_in").setLabel(`Server Taste: ${prefs.server_taste_opt_in ? "On" : "Off"}`).setStyle(prefs.server_taste_opt_in ? ButtonStyle.Success : ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("profile:toggle:share_leaderboard").setLabel(`Leaderboard: ${prefs.share_leaderboard ? "On" : "Off"}`).setStyle(prefs.share_leaderboard ? ButtonStyle.Success : ButtonStyle.Secondary),
    ),
  ];
}

export class ProfileCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("profile")
    .setDescription("Manage provider connections, profile visibility and shared interests")
    .addStringOption((option) => option.setName("action").setDescription("Profile action").addChoices(
      { name: "View a profile", value: "view" },
      { name: "Connect AniList", value: "link-anilist" },
      { name: "Connect Steam", value: "link-steam" },
      { name: "Disconnect AniList", value: "unlink-anilist" },
      { name: "Disconnect Steam", value: "unlink-steam" },
      { name: "Privacy settings", value: "privacy" },
      { name: "Compare interests", value: "affinity" },
      { name: "Server Taste", value: "taste" },
      { name: "Anime Golden Ratio leaderboard", value: "leaderboard-anime" },
      { name: "Manga Golden Ratio leaderboard", value: "leaderboard-manga" },
      { name: "Combined activity ranking", value: "leaderboard-combined" },
      { name: "Most chapters read", value: "leaderboard-chapters" },
      { name: "Most episodes watched", value: "leaderboard-episodes" },
      { name: "Most manga completed", value: "leaderboard-manga_completed" },
      { name: "Most anime completed", value: "leaderboard-anime_completed" },
    ))
    .addUserOption((option) => option.setName("member").setDescription("Member whose public profile or shared interests to view"))
    .addStringOption((option) => option.setName("account").setDescription("AniList username or Steam vanity / SteamID64").setMaxLength(100));

  private readonly anilist: AniListClient;
  private readonly steam: SteamClient;

  constructor(config: BotConfig) {
    this.anilist = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
    this.steam = new SteamClient(config.steamApiKey);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) {
      await interaction.reply({ content: "Profile connections and preferences are stored separately for each server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const action = interaction.options.getString("action") ?? "home";
    try {
      switch (action) {
        case "home":
          await interaction.reply({ ...profileHome(), flags: MessageFlags.Ephemeral });
          return;
        case "view":
          await this.displayProfile(interaction, interaction.options.getUser("member")?.id ?? interaction.user.id);
          return;
        case "link-anilist": {
          const account = interaction.options.getString("account");
          if (!account) {
            await interaction.showModal(linkModal("anilist"));
            return;
          }
          const profile = await linkAniListAccount(interaction.guildId, interaction.user.id, interaction.user.username, this.anilist, account);
          await interaction.reply({ content: `Connected AniList account [${profile.name}](${profile.url}) to this server. Public display and affinity sharing remain controlled by your privacy settings.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "link-steam": {
          const account = interaction.options.getString("account");
          if (!account) {
            await interaction.showModal(linkModal("steam"));
            return;
          }
          const profile = await linkSteamAccount(interaction.guildId, interaction.user.id, account, this.steam);
          await interaction.reply({ content: `Connected Steam account [${profile.personaName}](${profile.profileUrl}) to this server.`, flags: MessageFlags.Ephemeral });
          return;
        }
        case "unlink-anilist": {
          const removed = await unlinkAniListAccount(interaction.guildId, interaction.user.id);
          await interaction.reply({ content: removed ? "Your AniList connection was removed from this server." : "No AniList connection was registered in this server.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "unlink-steam": {
          const removed = await unlinkSteamAccount(interaction.guildId, interaction.user.id);
          await interaction.reply({ content: removed ? "Your Steam connection was removed from this server." : "No Steam connection was registered in this server.", flags: MessageFlags.Ephemeral });
          return;
        }
        case "privacy": await this.showPrivacy(interaction); return;
        case "affinity": {
          const member = interaction.options.getUser("member");
          if (!member) {
            await interaction.showModal(affinityModal());
            return;
          }
          await this.showAffinity(interaction, member.id, member.username);
          return;
        }
        case "taste": await this.showTaste(interaction); return;
        case "leaderboard-anime": await this.showLeaderboard(interaction, "anime"); return;
        case "leaderboard-manga": await this.showLeaderboard(interaction, "manga"); return;
        case "leaderboard-combined": await this.showLeaderboard(interaction, "combined"); return;
        case "leaderboard-chapters": await this.showLeaderboard(interaction, "chapters"); return;
        case "leaderboard-episodes": await this.showLeaderboard(interaction, "episodes"); return;
        case "leaderboard-manga_completed": await this.showLeaderboard(interaction, "manga_completed"); return;
        case "leaderboard-anime_completed": await this.showLeaderboard(interaction, "anime_completed"); return;
        default:
          await interaction.reply({ ...profileHome(), flags: MessageFlags.Ephemeral });
          return;
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "The profile action failed.";
      const issueHash = await createInteractionIssueLog(interaction, "/profile", error);
      const response = issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message;
      await interaction.reply({ content: response, flags: MessageFlags.Ephemeral }).catch(async () => {
        await interaction.followUp({ content: response, flags: MessageFlags.Ephemeral });
      });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, setting, pageValue] = interaction.customId.split(":");
    if (action === "leaderboard-page" && setting && pageValue !== undefined) {
      const session = leaderboardSessions.get(setting);
      if (!session || session.expiresAt <= Date.now()) {
        await interaction.reply({ content: "This leaderboard session has expired. Open it again from /profile.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (session.userId !== interaction.user.id || session.guildId !== interaction.guildId) {
        await interaction.reply({ content: "Only the member who opened this leaderboard can navigate its pages.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const page = Number(pageValue);
      const pageCount = Math.max(1, Math.ceil(session.entries.length / LEADERBOARD_PAGE_SIZE));
      if (!Number.isInteger(page) || page < 0 || page >= pageCount) {
        await interaction.reply({ content: "That leaderboard page is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update(leaderboardPage(session, page));
      return true;
    }
    if (action === "link-anilist") {
      await interaction.showModal(linkModal("anilist"));
      return true;
    }
    if (action === "link-steam") {
      await interaction.showModal(linkModal("steam"));
      return true;
    }
    if (action === "view") {
      await this.displayProfile(interaction, interaction.user.id);
      return true;
    }
    if (action === "privacy") {
      await this.showPrivacy(interaction);
      return true;
    }
    if (action === "affinity") {
      await interaction.showModal(affinityModal());
      return true;
    }
    if (action === "taste") {
      await this.showTaste(interaction);
      return true;
    }
    if (action === "leaderboard" && (setting === "anime" || setting === "manga")) {
      await this.showLeaderboard(interaction, setting);
      return true;
    }
    if (action === "unlink") {
      const [ani, steam] = await Promise.all([
        queryOne<{ anilist_username: string | null }>("SELECT anilist_username FROM users WHERE discord_id = $1 AND guild_id = $2", [interaction.user.id, interaction.guildId]),
        queryOne<{ steam_id: string }>("SELECT steam_id FROM steam_users WHERE discord_id = $1 AND guild_id = $2", [interaction.user.id, interaction.guildId]),
      ]);
      await interaction.reply({
        content: `Current links · AniList: ${ani?.anilist_username ? "connected" : "not connected"} · Steam: ${steam?.steam_id ? "connected" : "not connected"}.`,
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId("profile:unlink-anilist").setLabel("Disconnect AniList").setStyle(ButtonStyle.Danger),
          new ButtonBuilder().setCustomId("profile:unlink-steam").setLabel("Disconnect Steam").setStyle(ButtonStyle.Danger),
        )],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "unlink-anilist") {
      const removed = await unlinkAniListAccount(interaction.guildId, interaction.user.id);
      await interaction.reply({ content: removed ? "AniList disconnected for this server." : "There was no AniList connection to remove.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "unlink-steam") {
      const removed = await unlinkSteamAccount(interaction.guildId, interaction.user.id);
      await interaction.reply({ content: removed ? "Steam disconnected for this server." : "There was no Steam connection to remove.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "toggle" && setting) {
      const key = setting as "public_profile" | "show_anilist" | "show_steam" | "allow_affinity" | "server_taste_opt_in" | "share_leaderboard";
      const allowed = ["public_profile", "show_anilist", "show_steam", "allow_affinity", "server_taste_opt_in", "share_leaderboard"].includes(key);
      if (!allowed) return false;
      const current = await getProfilePreferences(interaction.guildId, interaction.user.id);
      const nextValue = !current[key];
      if (key === "share_leaderboard" && nextValue) {
        const link = await queryOne<{ anilist_username: string }>(
          "SELECT anilist_username FROM users WHERE guild_id = $1 AND discord_id = $2 AND anilist_username IS NOT NULL",
          [interaction.guildId, interaction.user.id],
        );
        if (!link) {
          await interaction.reply({ content: "Connect an AniList account before opting into the server leaderboard.", flags: MessageFlags.Ephemeral });
          return true;
        }
      }
      const updated = await updateProfilePreferences(interaction.guildId, interaction.user.id, { [key]: nextValue });
      await interaction.update({ embeds: [privacyEmbed(updated)], components: privacyButtons(updated) });
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.guildId) return false;
    const [, action, kind] = interaction.customId.split(":");
    if (action === "link" && (kind === "anilist" || kind === "steam")) {
      try {
        const account = interaction.fields.getTextInputValue("account");
        if (kind === "anilist") {
          const profile = await linkAniListAccount(interaction.guildId, interaction.user.id, interaction.user.username, this.anilist, account);
          await interaction.reply({ content: `AniList [${profile.name}](${profile.url}) is connected for this server.`, flags: MessageFlags.Ephemeral });
        } else {
          const profile = await linkSteamAccount(interaction.guildId, interaction.user.id, account, this.steam);
          await interaction.reply({ content: `Steam [${profile.personaName}](${profile.profileUrl}) is connected for this server.`, flags: MessageFlags.Ephemeral });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "The account could not be verified.";
        const issueHash = await createInteractionIssueLog(interaction, "/profile", error, { action: "account-verification" });
        await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
      }
      return true;
    }
    if (action === "affinity") {
      const raw = interaction.fields.getTextInputValue("member").replace(/[<@!>]/g, "").trim();
      if (!isDiscordSnowflake(raw)) {
        await interaction.reply({ content: "Enter a valid Discord member mention or ID.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await this.showAffinity(interaction, raw, raw);
      return true;
    }
    return false;
  }

  private async showPrivacy(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    const preferences = await getProfilePreferences(interaction.guildId!, interaction.user.id);
    await interaction.reply({
      embeds: [privacyEmbed(preferences)],
      components: privacyButtons(preferences),
      flags: MessageFlags.Ephemeral,
    });
  }

  private async displayProfile(
    interaction: ButtonInteraction | ChatInputCommandInteraction,
    targetId: string,
  ): Promise<void> {
    const ownProfile = targetId === interaction.user.id;
    const member = await interaction.guild!.members.fetch(targetId).catch(() => null);
    if (!member) {
      await interaction.reply({ content: "That member could not be found in this server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const profile = await getLinkedProfile(
      interaction.guildId!,
      targetId,
      member.user.username,
      this.anilist,
      this.steam,
      ownProfile,
    );
    if (!profile) {
      await interaction.reply({ content: "That member has not enabled a public profile in this server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const embed = new EmbedBuilder()
      .setColor(0x5865f2)
      .setTitle(`${member.user.displayName} · Media profile`)
      .setThumbnail(member.user.displayAvatarURL())
      .setDescription(ownProfile
        ? "Your private profile preview. Other members can see it only after you enable Public profile."
        : "Provider data shown here is controlled by this member's profile and provider visibility settings.")
      .addFields(
        { name: "Approved Archive contributions", value: String(profile.contributions), inline: true },
        { name: "AniList connection", value: profile.anilistUsername ? (profile.preferences.show_anilist ? (profile.anilist ? "Linked · verified" : "Linked · provider unavailable") : "Hidden by member") : "Not connected", inline: true },
        { name: "Steam connection", value: profile.steamId ? (profile.preferences.show_steam ? (profile.steam ? "Linked · verified" : "Linked · provider unavailable") : "Hidden by member") : "Not connected", inline: true },
      );
    if (profile.anilist) {
      if (profile.anilist.about) embed.addFields({ name: "About", value: profile.anilist.about.slice(0,1024), inline: false });
      embed.addFields(
        { name: "AniList", value: `[${profile.anilist.name}](${profile.anilist.url})`, inline: true },
        { name: "Anime entries", value: String(profile.anilist.anime.count), inline: true },
        { name: "Anime mean score", value: profile.anilist.anime.meanScore ? `${profile.anilist.anime.meanScore.toFixed(1)}/100` : "No score", inline: true },
        { name: "Episodes watched (AniList)", value: profile.anilist.anime.episodesWatched === null ? "Unavailable" : profile.anilist.anime.episodesWatched.toLocaleString("en-US"), inline: true },
        { name: "Manga entries", value: String(profile.anilist.manga.count), inline: true },
        { name: "Manga mean score", value: profile.anilist.manga.meanScore ? `${profile.anilist.manga.meanScore.toFixed(1)}/100` : "No score", inline: true },
        { name: "Chapters read (AniList)", value: profile.anilist.manga.chaptersRead === null ? "Unavailable" : profile.anilist.manga.chaptersRead.toLocaleString("en-US"), inline: true },
        { name: "Volumes read (AniList)", value: profile.anilist.manga.volumesRead === null ? "Unavailable" : profile.anilist.manga.volumesRead.toLocaleString("en-US"), inline: true },
        { name: "Anime formats", value: profile.anilist.anime.formats.slice(0, 5).map(item => `${item.format}: ${item.count}`).join("\n") || "Unavailable", inline: true },
        { name: "Manga formats", value: profile.anilist.manga.formats.slice(0, 5).map(item => `${item.format}: ${item.count}`).join("\n") || "Unavailable", inline: true },
        { name: "Anime genres", value: profile.anilist.anime.genres.slice(0, 5).map((item) => item.genre).join(", ") || "Unavailable", inline: false },
        { name: "Manga genres", value: profile.anilist.manga.genres.slice(0, 5).map((item) => item.genre).join(", ") || "Unavailable", inline: false },
        { name: "Anime list status", value: profile.anilist.anime.statuses.slice(0, 5).map(item => `${item.status}: ${item.count}`).join("\n") || "Unavailable", inline: true },
        { name: "Manga list status", value: profile.anilist.manga.statuses.slice(0, 5).map(item => `${item.status}: ${item.count}`).join("\n") || "Unavailable", inline: true },
      );
      const achievements = getAniListProfileAchievements(profile.anilist);
      if (achievements.length) {
        embed.addFields({
          name: "AniList milestones",
          value: achievements.map(item => `**${item.title}** — ${item.detail}`).join("\n").slice(0, 1000),
          inline: false,
        });
      }
      const favouriteLines = (items: Array<{ title: string; url: string }>) => items.map((item) => `[${item.title}](${item.url})`).join("\n").slice(0, 1000) || "No public favourites";
      embed.addFields(
        { name: "Favourite anime", value: favouriteLines(profile.anilist.favorites.anime), inline: true },
        { name: "Favourite manga", value: favouriteLines(profile.anilist.favorites.manga), inline: true },
        { name: "Favourite characters", value: profile.anilist.favorites.characters.map((item) => `[${item.name}](${item.url})`).join("\n").slice(0, 1000) || "No public favourites", inline: false },
      );
      if (profile.anilist.banner) embed.setImage(profile.anilist.banner);
      if (profile.anilist.avatar) embed.setThumbnail(profile.anilist.avatar);
    }
    if (profile.steam) {
      embed.addFields(
        { name: "Steam", value: `[${profile.steam.personaName}](${profile.steam.profileUrl})`, inline: true },
        { name: "Profile visibility", value: profile.steam.visibility, inline: true },
        { name: "Public game count", value: profile.steam.gameCount === null ? "Private / unavailable" : String(profile.steam.gameCount), inline: true },
      );
      if(profile.steam.visibility==="public"){
        if(profile.steam.totalPlaytimeMinutes!==null){
          const hours=(profile.steam.totalPlaytimeMinutes/60).toFixed(1);
          embed.addFields({name:"Public library playtime",value:hours+" hours reported by Steam",inline:true});
        }
        if(profile.steam.topGames.length){
          embed.addFields({name:"Most played games",value:profile.steam.topGames.map(game=>`[${game.name}](https://store.steampowered.com/app/${game.appId}) · ${(game.minutes/60).toFixed(1)}h`).join("\n").slice(0,1000),inline:false});
        }
        if(profile.steam.recentlyPlayed.length){
          embed.addFields({name:"Recently played",value:profile.steam.recentlyPlayed.map(game=>game.name+" · "+(game.minutes/60).toFixed(1)+"h in 2 weeks").join("\n").slice(0,900),inline:false});
        }
      }
    }
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral, allowedMentions: { parse: [] } });
  }

  private async showAffinity(
    interaction: ButtonInteraction | ChatInputCommandInteraction | ModalSubmitInteraction,
    targetId: string,
    targetName: string,
  ): Promise<void> {
    try {
      const result = await getAniListAffinity(interaction.guildId!, interaction.user.id, targetId, this.anilist);
      const embed = homeEmbed(
        "Shared media interests",
        `**${safeDisplay(result.first)}** and **${safeDisplay(result.second)}** share a ${result.percent}% weighted genre overlap across the AniList genres they have opted to share. This is an interest comparison, not a prediction about friendship or compatibility.`,
        [
          { name: "Shared anime genres", value: result.sharedAnime.join(", ") || "No shared listed genres", inline: false },
          { name: "Shared manga genres", value: result.sharedManga.join(", ") || "No shared listed genres", inline: false },
        ],
      );
      await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
    } catch (error) {
      const message = error instanceof Error ? error.message : "The comparison could not be calculated.";
      const issueHash = await createInteractionIssueLog(interaction, "/profile", error, { action: "affinity" });
      await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
    }
  }

  private async showLeaderboard(
    interaction: ButtonInteraction | ChatInputCommandInteraction,
    mode: AniListLeaderboardMode,
  ): Promise<void> {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    try {
      const members = await interaction.guild!.members.fetch();
      const result = await getAniListLeaderboard(
        interaction.guildId!,
        new Set(members.keys()),
        mode,
        this.anilist,
      );
      const now = Date.now();
      for (const [token, session] of leaderboardSessions) {
        if (session.expiresAt <= now) leaderboardSessions.delete(token);
      }
      const token = interaction.id;
      const expiresAt = now + LEADERBOARD_SESSION_TTL_MS;
      const session: LeaderboardSession = {
        token,
        userId: interaction.user.id,
        guildId: interaction.guildId!,
        mode,
        entries: result.entries,
        optedIn: result.optedIn,
        expiresAt,
      };
      leaderboardSessions.set(token, session);
      const firstPage = leaderboardPage(session, 0);
      await interaction.editReply({
        embeds: firstPage.embeds,
        components: firstPage.components,
        allowedMentions: { parse: [] },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "The AniList leaderboard is unavailable.";
      const issueHash = await createInteractionIssueLog(interaction, "/profile", error, { action: "leaderboard", mode });
      await interaction.editReply({
        content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message,
        embeds: [],
        components: [],
        allowedMentions: { parse: [] },
      });
    }
  }

  private async showTaste(interaction: ButtonInteraction | ChatInputCommandInteraction): Promise<void> {
    try {
      const taste = await getServerTaste(interaction.guildId!, this.anilist);
      const embed = homeEmbed(
        "Server Taste",
        `Anonymous provider-genre aggregate from ${taste.participants} members who opted in. No profile names, account identifiers or individual list records are shown.`,
        [
          { name: "Popular anime genres", value: taste.anime.map((item) => `${item.genre} · ${item.count} members`).join("\n") || "Unavailable", inline: true },
          { name: "Popular manga genres", value: taste.manga.map((item) => `${item.genre} · ${item.count} members`).join("\n") || "Unavailable", inline: true },
          { name: "Common anime themes", value: taste.animeTags.map((item) => `${item.tag} · ${item.count} members`).join("\n") || "Unavailable", inline: true },
          { name: "Common manga themes", value: taste.mangaTags.map((item) => `${item.tag} · ${item.count} members`).join("\n") || "Unavailable", inline: true },
        ],
      );
      await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Server Taste is unavailable.";
      const issueHash = await createInteractionIssueLog(interaction, "/profile", error, { action: "server-taste" });
      await interaction.reply({ content: issueHash ? `${message}\n\n${issueHashNotice(issueHash)}` : message, flags: MessageFlags.Ephemeral });
    }
  }
}

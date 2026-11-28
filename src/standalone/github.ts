import { EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction } from "discord.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { isBotModerator, isModeratorCommandGuild } from "../../helpers/commands/moderation.js";
import { createInteractionIssueLog, issueHashNotice } from "../../helpers/runtime/issue-logs.js";
import {
  buildGitHubActivityEmbed,
  createRecentGitHubActivity,
  getGitHubTrackerState,
  GitHubTrackerError,
  runGitHubCheck,
} from "../../helpers/runtime/github-tracker.js";
import { safeInteractionErrorMessage } from "../../helpers/commands/command-errors.js";

export class GitHubCommand implements FeatureCommand {
  constructor(private readonly config: BotConfig) {}

  readonly data = new SlashCommandBuilder()
    .setName("github")
    .setDescription("Inspect GitHub activity and the commit tracker")
    .addStringOption(option => option
      .setName("action")
      .setDescription("Choose what to do")
      .setRequired(true)
      .addChoices(
        { name: "Recent commits", value: "recent" },
        { name: "Tracker status", value: "status" },
        { name: "Check for new commits", value: "check" },
      ))
    .addIntegerOption(option => option
      .setName("count")
      .setDescription("Number of recent commits to preview (1–20)")
      .setMinValue(1)
      .setMaxValue(20)
      .setRequired(false));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!isModeratorCommandGuild(interaction.guildId, this.config.botModeratorGuildId)) {
      await interaction.reply({
        content: "This command is available only in the configured bot operations server.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }
    if (!await isBotModerator(interaction.user.id, this.config.adminDiscordId)) {
      await interaction.reply({
        content: "Only registered bot moderators can use GitHub operations.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const action = interaction.options.getString("action", true);
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    try {
      if (action === "recent") {
        const count = interaction.options.getInteger("count") ?? 10;
        const summary = await createRecentGitHubActivity(this.config, count);
        await interaction.editReply({
          embeds: [buildGitHubActivityEmbed(summary, this.config.githubRepository, this.config.githubBranch)],
        });
        return;
      }

      if (action === "status") {
        const state = await getGitHubTrackerState(this.config);
        const checkedAt = state?.last_checked_at
          ? (state.last_checked_at instanceof Date ? state.last_checked_at.getTime() : new Date(state.last_checked_at).getTime())
          : Number.NaN;
        const lastChecked = Number.isFinite(checkedAt)
          ? "<t:" + Math.floor(checkedAt / 1000) + ":R>"
          : "Not checked yet";
        const lastCommit = state?.last_sha
          ? "[\x60" + state.last_sha.slice(0, 7) + "\x60](https://github.com/" + this.config.githubRepository + "/commit/" + state.last_sha + ")"
          : "Not initialised";
        const automatic = this.config.githubUpdateChannelId && this.config.botModeratorGuildId
          ? "<#" + this.config.githubUpdateChannelId + ">"
          : "Not configured";
        const embed = new EmbedBuilder()
          .setColor(0x24292f)
          .setTitle("GitHub tracker")
          .setURL("https://github.com/" + this.config.githubRepository)
          .addFields(
            { name: "Repository", value: this.config.githubRepository, inline: true },
            { name: "Branch", value: this.config.githubBranch, inline: true },
            { name: "Polling", value: this.config.githubPollIntervalMinutes + " min", inline: true },
            { name: "Automatic announcements", value: automatic, inline: true },
            { name: "Last checked", value: lastChecked, inline: true },
            { name: "Last commit", value: lastCommit, inline: true },
          )
          .setFooter({ text: "Bot moderator operations · GitHub API" });
        if (state?.last_error) embed.addFields({ name: "Last error", value: state.last_error.slice(0, 1024), inline: false });
        await interaction.editReply({ embeds: [embed] });
        return;
      }

      if (action === "check") {
        const result = await runGitHubCheck(
          interaction.client,
          this.config,
          Boolean(this.config.githubUpdateChannelId),
        );
        if (result.kind === "initialised") {
          await interaction.editReply(
            "GitHub tracker initialised at " + (result.headSha ? result.headSha.slice(0, 7) : "the current repository head")
              + ". New commits will be grouped into consolidated activity updates.",
          );
          return;
        }
        if (result.kind === "history-reset") {
          await interaction.editReply(
            "The previous commit is no longer in recent branch history. The tracker has reset its baseline to "
              + result.headSha.slice(0, 7) + "; no older commits were replayed.",
          );
          return;
        }
        if (result.kind === "no-commits") {
          await interaction.editReply("No new commits since the last check.");
          return;
        }
        await interaction.editReply({
          content: result.published
            ? "Consolidated activity was published to <#" + this.config.githubUpdateChannelId + ">."
            : "Activity summary only. Set GITHUB_UPDATE_CHANNEL_ID to enable automatic announcements.",
          embeds: [buildGitHubActivityEmbed(result.summary, this.config.githubRepository, this.config.githubBranch)],
        });
        return;
      }

      await interaction.editReply("Choose a supported GitHub action.");
    } catch (error) {
      if (error instanceof GitHubTrackerError) {
        await interaction.editReply({ content: error.message, embeds: [] });
        return;
      }
      const issueHash = await createInteractionIssueLog(interaction, "/github", error, { action }).catch(() => null);
      const message = safeInteractionErrorMessage(error);
      await interaction.editReply(issueHash ? message + "\n\n" + issueHashNotice(issueHash) : message);
    }
  }
}

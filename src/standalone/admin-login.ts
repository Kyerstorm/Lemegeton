import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, SlashCommandBuilder,
  type ButtonInteraction, type ChatInputCommandInteraction,
} from "discord.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { isBotModerator, isModeratorCommandGuild } from "../../helpers/commands/moderation.js";
import { linkAniListAccount } from "../../helpers/runtime/profile.js";
import { queryOne } from "../../database.js";
import { AniListClient } from "../../helpers/integration/anilist.js";

const USERNAME_PATTERN = /^[A-Za-z0-9_-]{1,30}$/;

function successEmbed(targetName: string, profile: { name: string; url: string }): EmbedBuilder {
  return new EmbedBuilder().setColor(0x57f287).setTitle("AniList account updated")
    .setDescription("Connected **" + targetName + "** to [" + profile.name + "](" + profile.url + ") in this server.")
    .setFooter({ text: "Only this server's AniList connection was changed." });
}

export class AdminLoginCommand implements FeatureCommand {
  private readonly client: AniListClient;
  constructor(private readonly config: BotConfig) {
    this.client = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
  }

  readonly data = new SlashCommandBuilder().setName("adminlogin")
    .setDescription("Connect or replace a member's AniList account (bot moderators only)")
    .addUserOption(option => option.setName("member").setDescription("Member whose account to connect").setRequired(true))
    .addStringOption(option => option.setName("anilist_username").setDescription("Exact AniList username").setMinLength(1).setMaxLength(30).setRequired(true));

  private async authorize(interaction: ChatInputCommandInteraction | ButtonInteraction): Promise<boolean> {
    if (!isModeratorCommandGuild(interaction.guildId, this.config.botModeratorGuildId)) {
      await interaction.reply({ content: "This command is available only in the configured bot operations server.", flags: MessageFlags.Ephemeral });
      return false;
    }
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only bot moderators can connect another member's AniList account.", flags: MessageFlags.Ephemeral });
      return false;
    }
    return true;
  }

  private async findMember(interaction: ChatInputCommandInteraction | ButtonInteraction, userId: string) {
    const member = await interaction.guild?.members.fetch(userId).catch(() => null);
    if (!member || member.user.bot) return null;
    return member;
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!await this.authorize(interaction)) return;
    const target = interaction.options.getUser("member", true);
    const username = interaction.options.getString("anilist_username", true).trim();
    if (!USERNAME_PATTERN.test(username)) {
      await interaction.reply({ content: "Enter an AniList username using 1–30 letters, numbers, underscores or hyphens.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    try {
      const member = await this.findMember(interaction, target.id);
      if (!member) {
        await interaction.editReply("Choose a non-bot member of this server.");
        return;
      }
      const existing = await queryOne<{ anilist_username: string | null }>(
        "SELECT anilist_username FROM users WHERE discord_id = $1 AND guild_id = $2",
        [member.id, interaction.guildId],
      );
      if (existing?.anilist_username && existing.anilist_username.toLowerCase() !== username.toLowerCase()) {
        const confirmId = "adminlogin:swap:" + member.id + ":" + username + ":" + interaction.user.id;
        const embed = new EmbedBuilder().setColor(0xfee75c).setTitle("AniList account already linked")
          .setDescription("**" + (member.displayName ?? member.user.username) + "** is currently connected to **" + existing.anilist_username + "**. Confirm replacing it with **" + username + "**?")
          .setFooter({ text: "The change applies to this server only." });
        await interaction.editReply({
          embeds: [embed],
          components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
            new ButtonBuilder().setCustomId(confirmId).setLabel("Confirm account swap").setStyle(ButtonStyle.Danger),
          )],
        });
        return;
      }
      const profile = await linkAniListAccount(interaction.guildId!, member.id, member.user.username, this.client, username);
      await interaction.editReply({ embeds: [successEmbed(member.displayName ?? member.user.username, profile)], components: [] });
    } catch (error) {
      await interaction.editReply(error instanceof Error ? error.message : "The AniList account could not be connected.");
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("adminlogin:swap:")) return false;
    if (!await this.authorize(interaction)) return true;
    const parts = interaction.customId.split(":");
    const targetId = parts[2] ?? "";
    const username = parts[3] ?? "";
    const requesterId = parts[4] ?? "";
    if (parts.length !== 5 || requesterId !== interaction.user.id || !/^\d{17,20}$/.test(targetId) || !USERNAME_PATTERN.test(username)) {
      await interaction.reply({ content: "That account-swap confirmation is invalid or belongs to another moderator.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.deferUpdate();
    try {
      const member = await this.findMember(interaction, targetId);
      if (!member) {
        await interaction.editReply({ content: "That member is no longer in this server.", embeds: [], components: [] });
        return true;
      }
      const profile = await linkAniListAccount(interaction.guildId!, member.id, member.user.username, this.client, username);
      await interaction.editReply({ content: null, embeds: [successEmbed(member.displayName ?? member.user.username, profile)], components: [] });
    } catch (error) {
      await interaction.editReply({ content: error instanceof Error ? error.message : "The AniList account could not be updated.", embeds: [], components: [] });
    }
    return true;
  }
}

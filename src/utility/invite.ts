import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags,
  PermissionsBitField, SlashCommandBuilder, type ChatInputCommandInteraction,
} from "discord.js";
import type { BotConfig } from "../helpers/config.js";
import type { FeatureCommand } from "../helpers/command.js";

export class InviteCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("invite").setDescription("Get an invite link for Lemegeton");
  constructor(private readonly config: BotConfig) {}

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const permissions = new PermissionsBitField([
      "ViewChannel", "SendMessages", "ManageMessages", "EmbedLinks", "AttachFiles",
      "ReadMessageHistory", "UseExternalEmojis", "AddReactions", "ManageRoles",
    ]);
    const params = new URLSearchParams({
      client_id: this.config.applicationId,
      scope: "bot applications.commands",
      permissions: permissions.bitfield.toString(),
    });
    const url = "https://discord.com/oauth2/authorize?" + params.toString();
    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Invite Lemegeton")
      .setDescription("Add Lemegeton to a server you manage.")
      .addFields(
        { name: "Discovery", value: "Search media, browse community archives and explore recommendations.", inline: false },
        { name: "Community", value: "Run rankings, sessions, media games and server features.", inline: false },
        { name: "Integrations", value: "Connect AniList and Steam for supported profile and discovery features.", inline: false },
      );
    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setLabel("Add Lemegeton to a server").setStyle(ButtonStyle.Link).setURL(url),
    );
    await interaction.reply({ embeds: [embed], components: [row], flags: MessageFlags.Ephemeral });
  }
}

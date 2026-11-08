import { EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction } from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";

export class HelpCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("help").setDescription("Explore Lemegeton's commands and features");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Lemegeton · Help")
      .setDescription("A media discovery and community bot. Open a feature command, then use its controls to explore the available workflows.")
      .addFields(
        { name: "Media", value: "`/discover` — Search and explore anime, manga, novels, books, films, television and games.", inline: false },
        { name: "Community", value: "`/archive` — Browse and contribute to the community archive.\n`/community` — Daily Drops, rankings, sessions and discussions.", inline: false },
        { name: "Games & profiles", value: "`/play` — Source-backed media games.\n`/profile` — Connect AniList and Steam, manage privacy and compare interests.", inline: false },
        { name: "Server tools", value: "`/custom-role` — Member custom roles and server configuration.\n`/settings` — Enable or disable supported features.", inline: false },
        { name: "Support", value: "`/feedback` — Send an idea or bug report; include an issue reference when one was shown.\n`/privacy` — Read the data-use notice.\n`/planned` — Browse the development plan.\n`/log` — Inspect issue diagnostics (bot moderators).\n`/adminmoderators` — Manage bot moderators.", inline: false },
      ).setFooter({ text: "Lemegeton · Use commands in a server" });
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
  }
}

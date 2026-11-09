import {
  ActionRowBuilder, EmbedBuilder, MessageFlags, ModalBuilder, SlashCommandBuilder,
  TextInputBuilder, TextInputStyle, type ChatInputCommandInteraction, type ModalSubmitInteraction,
} from "discord.js";
import type { BotConfig } from "../../helpers/runtime/config.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";
import { AniListClient } from "../../helpers/providers/anilist.js";
import { loadingMessage } from "../../helpers/emoji.js";

function extractLinks(value: string): string[] {
  const found = [...value.matchAll(/https?:\/\/[^\s]+/gi)]
    .map((match) => match[0].replace(/[),.;]+$/g, ""));
  return [...new Set(found)];
}

export function extractAniListUsername(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname.toLowerCase() !== "anilist.co") return null;
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length < 2 || parts[0]?.toLowerCase() !== "user" || !/^[a-zA-Z0-9_-]{1,30}$/.test(parts[1] ?? "")) return null;
    return parts[1] ?? null;
  } catch {
    return null;
  }
}

function inputModal(): ModalBuilder {
  return new ModalBuilder().setCustomId("convertlinks:submit").setTitle("Convert AniList links")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("links").setLabel("Paste AniList profile links (one per line)")
        .setPlaceholder("https://anilist.co/user/username").setStyle(TextInputStyle.Paragraph)
        .setMinLength(1).setMaxLength(4000).setRequired(true),
    ));
}

export class ConvertLinksCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("convertlinks")
    .setDescription("Convert AniList profile links to numeric user URLs");

  private readonly client: AniListClient;
  constructor(config: BotConfig) {
    this.client = new AniListClient(config.anilistApiUrl, config.anilistTimeoutMs);
  }

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.showModal(inputModal());
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (interaction.customId !== "convertlinks:submit") return false;
    const links = extractLinks(interaction.fields.getTextInputValue("links"));
    if (!links.length) {
      await interaction.reply({ content: "No links were found. Paste one or more AniList profile URLs.", flags: MessageFlags.Ephemeral });
      return true;
    }

    const limited = links.slice(0, 25);
    await interaction.reply({ content: loadingMessage("Converting " + limited.length + " AniList link(s)…"), flags: MessageFlags.Ephemeral });
    const results: Array<{ input: string; output: string }> = [];
    for (let index = 0; index < limited.length; index += 1) {
      const link = limited[index] ?? "";
      const username = extractAniListUsername(link);
      if (!username) {
        results.push({ input: link, output: "Invalid AniList profile URL" });
      } else {
        try {
          const user = await this.client.getUser(username);
          results.push({
            input: link,
            output: user ? "https://anilist.co/user/" + user.id : "AniList user not found",
          });
        } catch {
          results.push({ input: link, output: "AniList lookup failed; try again later" });
        }
      }
      await interaction.editReply(loadingMessage("Converted " + (index + 1) + " of " + limited.length + " link(s)…"));
    }

    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("AniList link conversion")
      .setDescription(results.map((item, index) =>
        "**" + (index + 1) + ".** " + item.output + "\nInput: " + item.input,
      ).join("\n\n").slice(0, 4000))
      .setFooter({ text: results.length + " result(s) · Duplicate input links removed" });
    if (links.length > limited.length) {
      embed.addFields({ name: "Limit", value: "Only the first 25 unique links were processed. Run the command again for the remainder." });
    }
    await interaction.editReply({ content: null, embeds: [embed] });
    return true;
  }
}

import {
  ActionRowBuilder, EmbedBuilder, MessageFlags, SlashCommandBuilder, StringSelectMenuBuilder,
  type ChatInputCommandInteraction, type StringSelectMenuInteraction,
} from "discord.js";
import { emoji } from "../../helpers/emoji.js";
import { EMBED_COLOURS } from "../../helpers/embeds/core.js";
import type { FeatureCommand } from "../../helpers/commands/command.js";

const SECTIONS = [
  { label: "Information processed", icon: emoji.info, description: "Identifiers and feature inputs.", body: "Depending on the feature, Lemegeton may process Discord user, guild, channel, message and interaction IDs; display names and avatars; role and configuration data; search terms and URLs; provider account identifiers; archive submissions; votes, RSVPs and discussions; feedback; and diagnostic records. The bot does not provide personal watch, reading or play-progress tracking." },
  { label: "Discord access", icon: emoji.community, description: "How messages and member data are used.", body: "The bot requests the Guilds, Guild Members, Guild Messages and Message Content intents. Message events are used by supported archive-upload handling and related features; member events support Custom Roles. Slash commands and their components process the values and context needed to respond. This does not mean every message is intentionally stored as an archive." },
  { label: "Storage and retention", icon: emoji.archive, description: "Where application data is kept.", body: "The TypeScript bot stores feature records in the local libSQL database configured by LIBSQL_PATH. Archive media and Custom Role image objects use the local RocksDB object store unless a guild retains a migrated private Discord storage channel. Dashboard sessions and OAuth tokens remain server-side. Retention depends on record type and the operator schedule; do not submit passwords, access tokens or other secrets in feedback." },
  { label: "External providers", icon: emoji.globe, description: "Services used for media metadata.", body: "Media lookups may contact AniList, Google Books, TMDB and IGDB. Steam is used for supported account and game information. Hosting, database and private object-storage providers process data needed to operate the service. Each provider receives only the request data needed for that lookup or feature." },
  { label: "Security and encryption", icon: emoji.lock, description: "What encryption does and does not mean.", body: "Supported external requests use HTTPS. Local database and object-store files require host-level protection and secure backups. This is not end-to-end encryption: the bot and its operators must be able to process data required for features. Diagnostic logs redact common credential fields, but users should never include secrets in command inputs or feedback." },
  { label: "Privacy requests", icon: emoji.info, description: "Access, correction and deletion requests.", body: "There is no single self-service export or deletion command covering every store and provider. Contact the operator privately through the Support Server linked in /help. Do not post private requests or identity documents in public feedback channels. The operator will verify the request and assess the applicable rights and retention exceptions." },
] as const;

function page(index: number): EmbedBuilder {
  const section = SECTIONS[index] ?? SECTIONS[0];
  return new EmbedBuilder().setColor(EMBED_COLOURS.primary).setTitle(section.icon + " Privacy · " + section.label).setURL("https://github.com/Kyerstorm/Lemegeton/blob/lemegeton-v3/docs/legal/PRIVACY_POLICY.md")
    .setDescription(section.body).setFooter({ text: section.icon + " Lemegeton · Privacy notice · " + (index + 1) + " of " + SECTIONS.length });
}
function sectionRow(selected: number): ActionRowBuilder<StringSelectMenuBuilder> {
  return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    new StringSelectMenuBuilder().setCustomId("privacy:section").setPlaceholder("Choose a privacy section")
      .addOptions(SECTIONS.map((section, index) => ({
        label: section.label, description: section.description, value: String(index), default: selected === index, emoji: section.icon,
      }))),
  );
}
export class PrivacyCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("privacy")
    .setDescription("Read Lemegeton's privacy, data-use and encryption notice");
  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.reply({ embeds: [page(0)], components: [sectionRow(0)], flags: MessageFlags.Ephemeral });
  }
  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId !== "privacy:section") return false;
    const selected = Number(interaction.values[0]);
    if (!Number.isInteger(selected) || selected < 0 || selected >= SECTIONS.length) {
      await interaction.reply({ content: "That privacy section is no longer available.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.update({ embeds: [page(selected)], components: [sectionRow(selected)] });
    return true;
  }
}

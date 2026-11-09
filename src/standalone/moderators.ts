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
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";
import { loadingMessage } from "../helpers/emoji.js";
import { isBotModerator } from "../helpers/moderation.js";
import { query } from "../database.js";

type Moderator = Record<string, unknown> & { discord_id: string; username: string; added_by: string; created_at: Date | string };

async function getModerators(): Promise<Moderator[]> {
  return query<Moderator>(
    `SELECT discord_id::text, username, added_by::text, created_at
       FROM bot_moderators ORDER BY created_at ASC, discord_id ASC`,
  );
}

function panel(rows: Moderator[]): EmbedBuilder {
  const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("👑 Bot moderators")
    .setDescription("Bot-wide moderators can inspect diagnostic records and manage trusted bot operations.")
    .setFooter({ text: rows.length + " registered bot moderator" + (rows.length === 1 ? "" : "s") });
  if (!rows.length) {
    embed.addFields({ name: "No moderators configured", value: "The configured ADMIN_DISCORD_ID remains an administrator. Use Add to grant another moderator access." });
  } else {
    for (const row of rows.slice(0, 25)) {
      const date = row.created_at instanceof Date ? row.created_at : new Date(row.created_at);
      embed.addFields({
        name: row.username.slice(0, 200) + " · " + row.discord_id,
        value: "Added by <@" + row.added_by + "> · " + (Number.isNaN(date.getTime()) ? "date unavailable" : date.toLocaleString("en-IE")),
        inline: false,
      });
    }
    if (rows.length > 25) embed.setDescription("Showing 25 of " + rows.length + " bot moderators.");
  }
  return embed;
}

function controls(): ActionRowBuilder<ButtonBuilder>[] {
  return [
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("adminmoderators:refresh").setLabel("Refresh").setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId("adminmoderators:add").setLabel("Add moderator").setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId("adminmoderators:remove").setLabel("Remove moderator").setStyle(ButtonStyle.Danger),
    ),
    new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder().setCustomId("adminmoderators:about").setLabel("About permissions").setStyle(ButtonStyle.Secondary),
    ),
  ];
}

function moderatorModal(action: "add" | "remove"): ModalBuilder {
  return new ModalBuilder().setCustomId("adminmoderators:" + action)
    .setTitle(action === "add" ? "Add bot moderator" : "Remove bot moderator")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("user_id").setLabel("Discord user ID or mention")
        .setPlaceholder("123456789012345678 or @user").setStyle(TextInputStyle.Short)
        .setMinLength(17).setMaxLength(25).setRequired(true),
    ));
}

function parseDiscordId(value: string): string | null {
  const normalized = value.trim();
  const match = normalized.match(/^(?:<@!?(\d{17,20})>|(\d{17,20}))$/);
  return match?.[1] ?? match?.[2] ?? null;
}

export class BotModeratorsCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("adminmoderators")
    .setDescription("Manage bot-wide moderators (bot moderators only)");

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only existing bot moderators can manage this list.", flags: MessageFlags.Ephemeral });
      return;
    }
    await interaction.reply({ content: loadingMessage("Loading bot moderators…"), flags: MessageFlags.Ephemeral });
    await interaction.editReply({ content: null, embeds: [panel(await getModerators())], components: controls() });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("adminmoderators:")) return false;
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only existing bot moderators can manage this list.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const action = interaction.customId.split(":")[1];
    if (action === "add" || action === "remove") {
      await interaction.showModal(moderatorModal(action));
      return true;
    }
    if (action === "refresh") {
      await interaction.update({ content: loadingMessage("Refreshing bot moderators…"), embeds: [], components: [] });
      await interaction.editReply({ content: null, embeds: [panel(await getModerators())], components: controls() });
      return true;
    }
    if (action === "about") {
      const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("About bot moderators")
        .setDescription("Bot moderators have global permissions across all guilds.")
        .addFields(
          { name: "Access", value: "Inspect server-scoped diagnostic records with /log and manage the bot moderator list.", inline: false },
          { name: "Security", value: "Grant this access only to highly trusted people. Every diagnostic lookup remains scoped to the server where /log is run.", inline: false },
        );
      await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!["adminmoderators:add", "adminmoderators:remove"].includes(interaction.customId)) return false;
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only existing bot moderators can manage this list.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const action = interaction.customId.endsWith(":add") ? "add" : "remove";
    const userId = parseDiscordId(interaction.fields.getTextInputValue("user_id"));
    if (!userId) {
      await interaction.reply({ content: "Enter a valid 17–20 digit Discord user ID or mention.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "add") {
      await interaction.reply({ content: loadingMessage("Verifying the Discord account…"), flags: MessageFlags.Ephemeral });
      const user = await interaction.client.users.fetch(userId).catch(() => null);
      if (!user || user.bot) {
        await interaction.editReply(user ? "Bots cannot be added as bot moderators." : "That Discord user could not be found.");
        return true;
      }
      const inserted = await query<{ discord_id: string }>(
        `INSERT INTO bot_moderators (discord_id, username, added_by)
         VALUES ($1, $2, $3) ON CONFLICT (discord_id) DO NOTHING RETURNING discord_id::text`,
        [user.id, user.globalName ?? user.username, interaction.user.id],
      );
      await interaction.editReply(inserted.length
        ? "Added **" + (user.globalName ?? user.username) + "** as a bot moderator."
        : "That user is already a bot moderator.");
      return true;
    }

    if (process.env.ADMIN_DISCORD_ID?.trim() === userId) {
      await interaction.reply({ content: "The configured bot administrator cannot be removed from ADMIN_DISCORD_ID.", flags: MessageFlags.Ephemeral });
      return true;
    }
    await interaction.reply({ content: loadingMessage("Updating bot moderators…"), flags: MessageFlags.Ephemeral });
    const removed = await query<{ discord_id: string }>(
      "DELETE FROM bot_moderators WHERE discord_id = $1 RETURNING discord_id::text",
      [userId],
    );
    await interaction.editReply(removed.length ? "Removed <@" + userId + "> from bot moderators." : "That user is not a registered bot moderator.");
    return true;
  }
}

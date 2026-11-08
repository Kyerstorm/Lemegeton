import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags, ModalBuilder,
  SlashCommandBuilder, StringSelectMenuBuilder, TextInputBuilder, TextInputStyle,
  type ButtonInteraction, type ChatInputCommandInteraction, type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";
import { loadingMessage } from "../helpers/emoji.js";
import { isBotModerator } from "../helpers/moderation.js";
import { query, queryOne } from "../database.js";

type PlannedFeature = Record<string, unknown> & {
  id: string; name: string; description: string; added_date: Date | string; status: string; category: string;
};
const STATUSES = ["planned", "in_progress", "testing", "completed", "cancelled", "on_hold"] as const;
const CATEGORIES = ["Anime/Manga Features", "Gaming Features", "Social Features", "Server Management",
  "Utilities", "Performance Improvements", "Bug Fixes"] as const;

async function getFeatures(): Promise<PlannedFeature[]> {
  return query<PlannedFeature>(
    `SELECT id::text, name, description, added_date, status, category
       FROM planned_features ORDER BY added_date DESC, id DESC LIMIT 25`,
  );
}
function featureEmbed(features: PlannedFeature[]): EmbedBuilder {
  return new EmbedBuilder().setColor(0x5865f2).setTitle("Planned development")
    .setDescription(features.length ? features.map((feature, index) =>
      `**${index + 1}. ${feature.name.slice(0, 100)}** · ${feature.status.replaceAll("_", " ")}\n${feature.description.slice(0, 260)}\n_${feature.category}_`,
    ).join("\n\n").slice(0, 3900) : "There are no planned features yet.")
    .setFooter({ text: "Development plan · Latest 25 entries" });
}
function plannedControls(canManage: boolean): ActionRowBuilder<ButtonBuilder>[] {
  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("planned:refresh").setLabel("Refresh").setStyle(ButtonStyle.Secondary),
  );
  if (canManage) row.addComponents(
    new ButtonBuilder().setCustomId("planned:add").setLabel("Add").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId("planned:edit").setLabel("Edit").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("planned:remove").setLabel("Remove").setStyle(ButtonStyle.Danger),
  );
  return [row];
}
function featureModal(mode: "add" | "edit"): ModalBuilder {
  const rows = [
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("name").setLabel("Feature name").setStyle(TextInputStyle.Short).setMaxLength(100).setRequired(true)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("description").setLabel("Description").setStyle(TextInputStyle.Paragraph).setMaxLength(1500).setRequired(true)),
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("category").setLabel("Category").setStyle(TextInputStyle.Short).setMaxLength(60).setRequired(true).setValue("Utilities")),
    new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("status").setLabel("Status").setStyle(TextInputStyle.Short).setMaxLength(20).setRequired(true).setValue("planned")),
  ];
  if (mode === "edit") rows.push(new ActionRowBuilder<TextInputBuilder>().addComponents(
    new TextInputBuilder().setCustomId("feature_id").setLabel("Feature ID").setStyle(TextInputStyle.Short).setMaxLength(20).setRequired(true),
  ));
  return new ModalBuilder().setCustomId(`planned:${mode}`)
    .setTitle(mode === "add" ? "Add planned feature" : "Edit planned feature").addComponents(...rows);
}

export class PlannedCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("planned").setDescription("View the development plan");

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.reply({ content: loadingMessage("Loading the development plan…"), flags: MessageFlags.Ephemeral });
    const [features, canManage] = await Promise.all([getFeatures(), isBotModerator(interaction.user.id)]);
    await interaction.editReply({ content: null, embeds: [featureEmbed(features)], components: plannedControls(canManage) });
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("planned:")) return false;
    const action = interaction.customId.slice("planned:".length);
    if (action === "refresh") {
      const [features, canManage] = await Promise.all([getFeatures(), isBotModerator(interaction.user.id)]);
      await interaction.update({ embeds: [featureEmbed(features)], components: plannedControls(canManage) });
      return true;
    }
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only bot moderators can change the development plan.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "add" || action === "edit") {
      await interaction.showModal(featureModal(action));
      return true;
    }
    if (action === "remove") {
      const features = await getFeatures();
      if (!features.length) {
        await interaction.reply({ content: "There are no planned features to remove.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const options = features.map((feature) => ({
        label: feature.name.slice(0, 100), description: `#${feature.id} · ${feature.status}`.slice(0, 100), value: feature.id,
      }));
      await interaction.reply({
        content: "Choose the planned feature to remove.",
        components: [new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
          new StringSelectMenuBuilder().setCustomId("planned:remove-select").setPlaceholder("Select a feature").addOptions(options),
        )],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    if (interaction.customId !== "planned:remove-select") return false;
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only bot moderators can change the development plan.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const id = interaction.values[0] ?? "";
    if (!/^\d+$/.test(id)) {
      await interaction.reply({ content: "That feature selection is invalid.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const deleted = await query<{ id: string }>("DELETE FROM planned_features WHERE id = $1 RETURNING id::text", [id]);
    await interaction.update({ content: deleted.length ? `Planned feature #${id} removed.` : "That planned feature no longer exists.", embeds: [], components: [] });
    return true;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    const mode = interaction.customId === "planned:add" ? "add" : interaction.customId === "planned:edit" ? "edit" : null;
    if (!mode) return false;
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only bot moderators can change the development plan.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const name = interaction.fields.getTextInputValue("name").trim();
    const description = interaction.fields.getTextInputValue("description").trim();
    const categoryInput = interaction.fields.getTextInputValue("category").trim();
    const statusInput = interaction.fields.getTextInputValue("status").trim().toLowerCase();
    const category = CATEGORIES.find((item) => item.toLowerCase() === categoryInput.toLowerCase());
    if (!name || !description || !category || !STATUSES.includes(statusInput as typeof STATUSES[number])) {
      await interaction.reply({ content: "Provide a valid name, description, category and status.", flags: MessageFlags.Ephemeral });
      return true;
    }

    await interaction.reply({ content: loadingMessage("Saving the development plan…"), flags: MessageFlags.Ephemeral });
    if (mode === "add") {
      const created = await query<{ id: string }>(
        `INSERT INTO planned_features (name, description, added_by, status, category)
         VALUES ($1, $2, $3, $4, $5) RETURNING id::text`,
        [name, description, interaction.user.id, statusInput, category],
      );
      const featureId = created[0]?.id;
      if (featureId) {
        await query(
          `INSERT INTO feature_status_history (feature_id, old_status, new_status, changed_by)
           VALUES ($1, NULL, $2, $3)`,
          [featureId, statusInput, interaction.user.id],
        );
      }
      await interaction.editReply("The planned feature was added.");
      return true;
    }

    const id = interaction.fields.getTextInputValue("feature_id").trim();
    if (!/^\d+$/.test(id)) { await interaction.editReply("Provide a valid numeric feature ID."); return true; }
    const previous = await queryOne<{ status: string }>("SELECT status FROM planned_features WHERE id = $1", [id]);
    if (!previous) { await interaction.editReply("That planned feature no longer exists."); return true; }

    await query(
      `UPDATE planned_features SET name = $1, description = $2, category = $3, status = $4,
        last_edited = NOW(), last_edited_by = $5 WHERE id = $6`,
      [name, description, category, statusInput, interaction.user.id, id],
    );
    if (previous.status !== statusInput) {
      await query(
        `INSERT INTO feature_status_history (feature_id, old_status, new_status, changed_by)
         VALUES ($1, $2, $3, $4)`,
        [id, previous.status, statusInput, interaction.user.id],
      );
    }
    await interaction.editReply(`Planned feature #${id} was updated.`);
    return true;
  }
}

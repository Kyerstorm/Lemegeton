import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  SlashCommandBuilder,
  StringSelectMenuBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChatInputCommandInteraction,
  type ModalSubmitInteraction,
  type StringSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";
import { loadingMessage } from "../helpers/emoji.js";
import { isBotModerator } from "../helpers/moderation.js";
import { query, queryOne, transaction } from "../database.js";

type PlannedFeature = Record<string, unknown> & {
  id: string;
  name: string;
  description: string;
  added_date: Date | string;
  added_by: string;
  last_edited: Date | string | null;
  last_edited_by: string | null;
  status: string;
  category: string;
};

const STATUS = [
  { value: "planned", label: "Planned", emoji: "📋", color: 0x5865f2 },
  { value: "in_progress", label: "In Progress", emoji: "🔄", color: 0xfee75c },
  { value: "testing", label: "Testing", emoji: "🧪", color: 0xfee75c },
  { value: "completed", label: "Completed", emoji: "✅", color: 0x57f287 },
  { value: "cancelled", label: "Cancelled", emoji: "❌", color: 0xed4245 },
  { value: "on_hold", label: "On Hold", emoji: "⏸️", color: 0x99aab5 },
] as const;

const CATEGORY = [
  { value: "Anime/Manga Features", emoji: "📺" },
  { value: "Gaming Features", emoji: "🎮" },
  { value: "Social Features", emoji: "👥" },
  { value: "Server Management", emoji: "⚙️" },
  { value: "Utilities", emoji: "🔧" },
  { value: "Performance Improvements", emoji: "⚡" },
  { value: "Bug Fixes", emoji: "🐛" },
] as const;

const statusAt = (code: number) => STATUS[code - 1];
const categoryAt = (code: number) => CATEGORY[code - 1];
const statusCode = (value: string | null) => value ? STATUS.findIndex((item) => item.value === value) + 1 : 0;
const categoryCode = (value: string | null) => value ? CATEGORY.findIndex((item) => item.value === value) + 1 : 0;

function categoryFromInput(value: string): string {
  const aliases: Record<string, string> = {
    utilities: "Utilities",
    anime: "Anime/Manga Features",
    manga: "Anime/Manga Features",
    "anime/manga": "Anime/Manga Features",
    gaming: "Gaming Features",
    social: "Social Features",
    server: "Server Management",
    performance: "Performance Improvements",
    bug: "Bug Fixes",
  };
  const normalized = value.trim();
  const mapped = aliases[normalized.toLowerCase()] ?? normalized;
  return CATEGORY.find((item) => item.value.toLowerCase() === mapped.toLowerCase())?.value ?? "Utilities";
}

function statusFromInput(value: string): string {
  const normalized = value.trim().toLowerCase();
  return STATUS.find((item) => item.value === normalized)?.value ?? "planned";
}

function formatDate(value: Date | string | null): string {
  if (!value) return "Unknown";
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString("en-IE", { dateStyle: "medium", timeStyle: "short" });
}

async function getFeatureCount(status: string | null, category: string | null): Promise<number> {
  const conditions: string[] = [];
  const values: string[] = [];
  if (status) { values.push(status); conditions.push("status = $" + values.length); }
  if (category) { values.push(category); conditions.push("category = $" + values.length); }
  const where = conditions.length ? " WHERE " + conditions.join(" AND ") : "";
  const row = await queryOne<{ count: string }>("SELECT COUNT(*)::text AS count FROM planned_features" + where, values);
  return Number(row?.count ?? 0);
}

async function getFeaturePage(status: string | null, category: string | null, page: number): Promise<PlannedFeature | null> {
  const conditions: string[] = [];
  const values: Array<string | number> = [];
  if (status) { values.push(status); conditions.push("status = $" + values.length); }
  if (category) { values.push(category); conditions.push("category = $" + values.length); }
  const where = conditions.length ? " WHERE " + conditions.join(" AND ") : "";
  values.push(Math.max(0, page - 1));
  return queryOne<PlannedFeature>(
    "SELECT id::text, name, description, added_date, added_by::text, last_edited, last_edited_by::text, status, category " +
    "FROM planned_features" + where + " ORDER BY added_date DESC, id DESC LIMIT 1 OFFSET $" + values.length,
    values,
  );
}

async function getPlannedFeature(id: string): Promise<PlannedFeature | null> {
  return queryOne<PlannedFeature>(
    `SELECT id::text, name, description, added_date, added_by::text,
            last_edited, last_edited_by::text, status, category
       FROM planned_features WHERE id = $1`,
    [id],
  );
}

function stateEmbed(feature: PlannedFeature | null, page: number, total: number, status: string | null, category: string | null): EmbedBuilder {
  const statusMeta = STATUS.find((item) => item.value === feature?.status) ?? STATUS[0];
  const categoryMeta = CATEGORY.find((item) => item.value === feature?.category) ?? CATEGORY[4];
  const filters = [
    status ? "Status: " + (STATUS.find((item) => item.value === status)?.label ?? status) : null,
    category ? "Category: " + category : null,
  ].filter(Boolean);
  const embed = new EmbedBuilder()
    .setColor(status ? (STATUS.find((item) => item.value === status)?.color ?? 0x5865f2) : 0x5865f2)
    .setTitle("🚀 Planned Features" + (filters.length ? " · " + filters.join(" · ") : ""))
    .setDescription("Page " + page + "/" + Math.max(1, total) + " · " + total + " features")
    .setTimestamp();
  if (!feature) {
    embed.addFields({ name: "No features found", value: "There are no planned features matching these filters." });
  } else {
    embed.addFields(
      { name: page + ". " + feature.name.slice(0, 240), value: feature.description.slice(0, 1000) || "No description available", inline: false },
      { name: "Status", value: statusMeta.emoji + " " + statusMeta.label, inline: true },
      { name: "Category", value: categoryMeta.emoji + " " + feature.category, inline: true },
      { name: "Added", value: formatDate(feature.added_date), inline: true },
      { name: "Added by", value: "<@" + feature.added_by + ">", inline: true },
      ...(feature.last_edited ? [{ name: "Last edited", value: formatDate(feature.last_edited), inline: true }] : []),
    );
  }
  embed.setFooter({ text: "Use the arrows to browse · Changes are restricted to bot moderators" });
  return embed;
}

function pageControls(page: number, total: number, status: string | null, category: string | null, canManage: boolean): ActionRowBuilder<ButtonBuilder>[] {
  const s = statusCode(status);
  const c = categoryCode(category);
  const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("planned:previous:" + s + ":" + c + ":" + page)
      .setLabel("◀ Previous").setStyle(ButtonStyle.Secondary).setDisabled(page <= 1),
    new ButtonBuilder().setCustomId("planned:page").setLabel("Page " + page + "/" + Math.max(1, total))
      .setStyle(ButtonStyle.Primary).setDisabled(true),
    new ButtonBuilder().setCustomId("planned:next:" + s + ":" + c + ":" + page)
      .setLabel("Next ▶").setStyle(ButtonStyle.Secondary).setDisabled(page >= Math.max(1, total)),
  );
  const rows = [row];
  if (!canManage) return rows;
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("planned:reset").setLabel("Reset filters").setStyle(ButtonStyle.Secondary).setDisabled(!status && !category),
    new ButtonBuilder().setCustomId("planned:add").setLabel("Add feature").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId("planned:edit-select").setLabel("Edit feature").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("planned:remove-select").setLabel("Remove feature").setStyle(ButtonStyle.Danger),
  ));
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("planned:filters-info").setLabel("Filters below").setStyle(ButtonStyle.Secondary).setDisabled(true),
  ));
  return rows;
}

function filterControls(status: string | null, category: string | null, page: number, canManage: boolean): ActionRowBuilder<StringSelectMenuBuilder>[] {
  if (!canManage) return [];
  const s = statusCode(status);
  const c = categoryCode(category);
  const statusMenu = new StringSelectMenuBuilder()
    .setCustomId("planned:status:" + c + ":" + page)
    .setPlaceholder("Filter by status")
    .addOptions(
      { label: "All statuses", value: "0", default: s === 0 },
      ...STATUS.map((item, index) => ({ label: item.label, value: String(index + 1), default: s === index + 1 })),
    );
  const categoryMenu = new StringSelectMenuBuilder()
    .setCustomId("planned:category:" + s + ":" + page)
    .setPlaceholder("Filter by category")
    .addOptions(
      { label: "All categories", value: "0", default: c === 0 },
      ...CATEGORY.map((item, index) => ({ label: item.value, value: String(index + 1), default: c === index + 1 })),
    );
  return [
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(statusMenu),
    new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(categoryMenu),
  ];
}

function controls(page: number, total: number, status: string | null, category: string | null, canManage: boolean) {
  return [...pageControls(page, total, status, category, canManage), ...filterControls(status, category, page, canManage)];
}

function featureModal(mode: "add" | "edit", feature?: PlannedFeature): ModalBuilder {
  const customId = mode === "add" ? "planned:modal:add" : "planned:modal:edit:" + feature?.id;
  return new ModalBuilder().setCustomId(customId)
    .setTitle(mode === "add" ? "Add planned feature" : "Edit planned feature")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("name").setLabel("Feature name").setStyle(TextInputStyle.Short)
          .setMaxLength(100).setRequired(true).setValue(feature?.name ?? ""),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("description").setLabel("Feature description").setStyle(TextInputStyle.Paragraph)
          .setMaxLength(4000).setRequired(true).setValue(feature?.description ?? ""),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("category").setLabel("Category").setStyle(TextInputStyle.Short)
          .setMaxLength(60).setRequired(true).setValue(feature?.category ?? "Utilities"),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("status").setLabel("Status").setStyle(TextInputStyle.Short)
          .setMaxLength(20).setRequired(true).setValue(feature?.status ?? "planned"),
      ),
    );
}

function featureSelect(customId: string, features: PlannedFeature[], placeholder: string): ActionRowBuilder<StringSelectMenuBuilder> {
  const options = features.slice(0, 25).map((feature) => ({
    label: feature.name.slice(0, 100),
    description: ("#" + feature.id + " · " + feature.status + " · " + feature.category).slice(0, 100),
    value: feature.id,
  }));
  return new ActionRowBuilder<StringSelectMenuBuilder>().addComponents(
    new StringSelectMenuBuilder().setCustomId(customId).setPlaceholder(placeholder).addOptions(options),
  );
}

export class PlannedCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("planned").setDescription("Browse the development plan");

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    await interaction.reply({ content: loadingMessage("Loading the development plan…"), flags: MessageFlags.Ephemeral });
    await this.render(interaction, 1, null, null);
  }

  private async render(interaction: ChatInputCommandInteraction | ButtonInteraction | StringSelectMenuInteraction, page: number, status: string | null, category: string | null): Promise<void> {
    const [total, feature, canManage] = await Promise.all([
      getFeatureCount(status, category),
      getFeaturePage(status, category, page),
      isBotModerator(interaction.user.id),
    ]);
    const totalPages = Math.max(1, total);
    const safePage = Math.min(Math.max(1, page), totalPages);
    if (safePage !== page) {
      await this.render(interaction, safePage, status, category);
      return;
    }
    const payload = {
      content: null,
      embeds: [stateEmbed(feature, page, total, status, category)],
      components: controls(page, total, status, category, canManage),
    };
    if (interaction.isChatInputCommand()) await interaction.editReply(payload);
    else if (interaction.isButton() || interaction.isStringSelectMenu()) await interaction.editReply(payload);
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("planned:")) return false;
    const parts = interaction.customId.split(":");
    const action = parts[1];
    if (action === "previous" || action === "next") {
      const s = Number(parts[2]);
      const c = Number(parts[3]);
      const page = Number(parts[4]);
      if (!Number.isInteger(s) || s < 0 || s > STATUS.length || !Number.isInteger(c) || c < 0 || c > CATEGORY.length || !Number.isInteger(page)) {
        await interaction.reply({ content: "That page control has expired. Run /planned again.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update({ content: loadingMessage("Loading planned features…"), embeds: [], components: [] });
      const nextPage = action === "previous" ? Math.max(1, page - 1) : page + 1;
      await this.render(interaction, nextPage, statusAt(s)?.value ?? null, categoryAt(c)?.value ?? null);
      return true;
    }
    if (action === "reset") {
      if (!await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "Only bot moderators can change planned-feature filters.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update({ content: loadingMessage("Resetting planned-feature filters…"), embeds: [], components: [] });
      await this.render(interaction, 1, null, null);
      return true;
    }
    if (action === "add") {
      if (!await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "Only bot moderators can add planned features.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.showModal(featureModal("add"));
      return true;
    }
    if (action === "edit-select" || action === "remove-select") {
      if (!await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "Only bot moderators can manage planned features.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const features = await query<PlannedFeature>(
        `SELECT id::text, name, description, added_date, added_by::text, last_edited,
                last_edited_by::text, status, category
           FROM planned_features WHERE status = 'planned'
          ORDER BY added_date DESC, id DESC LIMIT 25`,
      );
      if (!features.length) {
        await interaction.reply({ content: action === "edit-select" ? "There are no planned features to edit." : "There are no planned features to remove.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.reply({
        content: action === "edit-select" ? "Choose a feature to edit." : "Choose a feature to remove.",
        components: [featureSelect(action === "edit-select" ? "planned:edit-choice" : "planned:remove-choice", features, "Select a planned feature")],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "confirm-remove") {
      const id = parts[2] ?? "";
      if (!/^\d+$/.test(id) || !await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "You are not authorised to remove that planned feature.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update({ content: loadingMessage("Removing planned feature…"), embeds: [], components: [] });
      const removed = await query<{ id: string }>("DELETE FROM planned_features WHERE id = $1 RETURNING id::text", [id]);
      await interaction.editReply(removed.length ? "Planned feature #" + id + " was removed." : "That planned feature no longer exists.");
      return true;
    }
    if (action === "cancel-remove") {
      await interaction.update({ content: "Removal cancelled. No changes were made.", embeds: [], components: [] });
      return true;
    }
    return false;
  }

  async handleSelect(interaction: StringSelectMenuInteraction): Promise<boolean> {
    const parts = interaction.customId.split(":");
    const action = parts[1];
    if (action === "status" || action === "category") {
      if (!await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "Only bot moderators can change planned-feature filters.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const selected = Number(interaction.values[0]);
      const other = Number(parts[2]);
      const page = Number(parts[3]);
      if (!Number.isInteger(selected) || !Number.isInteger(other) || !Number.isInteger(page)) {
        await interaction.reply({ content: "That filter has expired. Run /planned again.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const s = action === "status" ? selected : other;
      const c = action === "category" ? selected : other;
      if (s < 0 || s > STATUS.length || c < 0 || c > CATEGORY.length) {
        await interaction.reply({ content: "That filter is invalid. Run /planned again.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.update({ content: loadingMessage("Filtering planned features…"), embeds: [], components: [] });
      await this.render(interaction, 1, statusAt(s)?.value ?? null, categoryAt(c)?.value ?? null);
      return true;
    }
    if (action === "edit-choice" || action === "remove-choice") {
      if (!await isBotModerator(interaction.user.id)) {
        await interaction.reply({ content: "Only bot moderators can manage planned features.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const id = interaction.values[0] ?? "";
      if (!/^\d+$/.test(id)) {
        await interaction.reply({ content: "That feature selection is no longer available.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const feature = await getPlannedFeature(id);
      if (!feature) {
        await interaction.update({ content: "That planned feature no longer exists.", components: [] });
        return true;
      }
      if (action === "edit-choice") {
        await interaction.showModal(featureModal("edit", feature));
        return true;
      }
      const embed = new EmbedBuilder().setColor(0xfee75c).setTitle("Confirm feature removal")
        .setDescription("Remove **" + feature.name.slice(0, 200) + "**?\n\n" + feature.description.slice(0, 800));
      await interaction.update({
        content: null,
        embeds: [embed],
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId("planned:confirm-remove:" + id).setLabel("Confirm removal").setStyle(ButtonStyle.Danger),
          new ButtonBuilder().setCustomId("planned:cancel-remove").setLabel("Cancel").setStyle(ButtonStyle.Secondary),
        )],
      });
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    if (!interaction.customId.startsWith("planned:modal:")) return false;
    if (!await isBotModerator(interaction.user.id)) {
      await interaction.reply({ content: "Only bot moderators can change planned features.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const mode = interaction.customId === "planned:modal:add" ? "add" : interaction.customId.startsWith("planned:modal:edit:") ? "edit" : null;
    if (!mode) return false;
    const id = mode === "edit" ? interaction.customId.slice("planned:modal:edit:".length) : null;
    if (id !== null && !/^\d+$/.test(id)) {
      await interaction.reply({ content: "That feature edit has expired. Choose the feature again.", flags: MessageFlags.Ephemeral });
      return true;
    }
    const name = interaction.fields.getTextInputValue("name").trim();
    const description = interaction.fields.getTextInputValue("description").trim();
    const category = categoryFromInput(interaction.fields.getTextInputValue("category"));
    const status = statusFromInput(interaction.fields.getTextInputValue("status"));
    if (!name || !description) {
      await interaction.reply({ content: "Feature name and description are required.", flags: MessageFlags.Ephemeral });
      return true;
    }

    await interaction.reply({ content: loadingMessage(mode === "add" ? "Adding planned feature…" : "Updating planned feature…"), flags: MessageFlags.Ephemeral });
    if (mode === "add") {
      await transaction(async (client) => {
        const inserted = await client.query<{ id: string }>(
          `INSERT INTO planned_features (name, description, added_by, status, category)
           VALUES ($1, $2, $3, $4, $5) RETURNING id::text`,
          [name, description, interaction.user.id, status, category],
        );
        const featureId = inserted.rows[0]?.id;
        if (!featureId) throw new Error("The planned feature was not created.");
        await client.query(
          `INSERT INTO feature_status_history (feature_id, old_status, new_status, changed_by)
           VALUES ($1, NULL, $2, $3)`,
          [featureId, status, interaction.user.id],
        );
      });
    } else {
      await transaction(async (client) => {
        const previous = await client.query<{ status: string }>(
          "SELECT status FROM planned_features WHERE id = $1 FOR UPDATE",
          [id],
        );
        const oldStatus = previous.rows[0]?.status;
        if (!oldStatus) throw new Error("That planned feature no longer exists.");
        await client.query(
          `UPDATE planned_features
              SET name = $1, description = $2, category = $3, status = $4,
                  last_edited = NOW(), last_edited_by = $5
            WHERE id = $6`,
          [name, description, category, status, interaction.user.id, id],
        );
        if (oldStatus !== status) {
          await client.query(
            `INSERT INTO feature_status_history (feature_id, old_status, new_status, changed_by)
             VALUES ($1, $2, $3, $4)`,
            [id, oldStatus, status, interaction.user.id],
          );
        }
      });
    }
    await interaction.editReply(mode === "add" ? "Planned feature added successfully." : "Planned feature updated successfully.");
    return true;
  }
}

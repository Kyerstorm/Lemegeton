import { EmbedBuilder, MessageFlags, SlashCommandBuilder, type ChatInputCommandInteraction } from "discord.js";
import type { FeatureCommand } from "../helpers/command.js";

function parseUtcDateTime(date: string, time: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return null;
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null;
  const result = new Date(0);
  result.setUTCFullYear(year, month - 1, day);
  result.setUTCHours(hour, minute, 0, 0);
  if (result.getUTCFullYear() !== year || result.getUTCMonth() !== month - 1 || result.getUTCDate() !== day) return null;
  return result;
}

export class TimestampCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("timestamp")
    .setDescription("Create a Discord timestamp from a date and time")
    .addStringOption((option) => option.setName("time").setDescription("Time in 24-hour HH:MM format")
      .setMinLength(5).setMaxLength(5).setRequired(true))
    .addStringOption((option) => option.setName("date").setDescription("Date in YYYY-MM-DD format (defaults to today)")
      .setMinLength(10).setMaxLength(10).setRequired(false));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    const time = interaction.options.getString("time", true).trim();
    const date = interaction.options.getString("date")?.trim() ?? new Date().toISOString().slice(0, 10);
    const parsed = parseUtcDateTime(date, time);
    if (!parsed) {
      await interaction.reply({
        content: "Enter a real date as YYYY-MM-DD and a 24-hour time as HH:MM. Example: 2026-12-25 and 18:30.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }
    const unix = Math.floor(parsed.getTime() / 1000);
    const syntax = "<t:" + unix + ":F>";
    const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Discord timestamp")
      .setDescription("Copy this timestamp:\n" + String.fromCharCode(96, 96, 96) + "\n" + syntax + "\n" + String.fromCharCode(96, 96, 96))
      .addFields(
        { name: "Preview", value: syntax, inline: false },
        { name: "Unix", value: String.fromCharCode(96) + unix + String.fromCharCode(96), inline: true },
        { name: "Input (UTC)", value: date + " " + time, inline: true },
      )
      .setFooter({ text: "Format F · Paste the timestamp anywhere in Discord" });
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
  }
}

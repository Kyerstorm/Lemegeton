import { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, type APIEmbedField } from "discord.js";
import { EMBED_COLOURS } from "../embeds/core.js";
import { emoji, providerFooter } from "../emoji.js";

export const COLOUR = EMBED_COLOURS.primary;

export function setCommandFooter(embed: EmbedBuilder, context: string, icon = emoji.globe): EmbedBuilder {
  return embed.setFooter({ text: (icon + " Lemegeton · " + context).slice(0, 2_048) });
}

export function setProviderFooter(embed: EmbedBuilder, provider: string, context = "Source metadata"): EmbedBuilder {
  return embed.setFooter({ text: providerFooter(provider, context) });
}

export function homeEmbed(title: string, description: string, fields: APIEmbedField[] = []): EmbedBuilder {
  return setCommandFooter(
    new EmbedBuilder().setColor(COLOUR).setTitle(title.slice(0, 256))
      .setDescription(description.slice(0, 4_000)).addFields(fields.slice(0, 25)),
    "Community media",
  );
}

export function navigationButtons(
  prefix: string,
  choices: Array<{ id: string; label: string; style?: ButtonStyle; disabled?: boolean }>,
): ActionRowBuilder<ButtonBuilder> {
  const row = new ActionRowBuilder<ButtonBuilder>();
  for (const choice of choices.slice(0, 5)) {
    const button = new ButtonBuilder().setCustomId(prefix + ":" + choice.id)
      .setLabel(choice.label.slice(0, 80)).setStyle(choice.style ?? ButtonStyle.Secondary)
      .setDisabled(choice.disabled ?? false);
    const navigationIcon = /home|back/i.test(choice.id + " " + choice.label) ? emoji.back
      : /next/i.test(choice.id + " " + choice.label) ? emoji.next
        : /refresh|reload/i.test(choice.id + " " + choice.label) ? emoji.refresh : null;
    if (navigationIcon) button.setEmoji(navigationIcon);
    row.addComponents(button);
  }
  return row;
}

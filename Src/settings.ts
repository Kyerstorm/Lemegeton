import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, MessageFlags,
  PermissionFlagsBits, SlashCommandBuilder, type ButtonInteraction, type ChatInputCommandInteraction,
} from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
import { FEATURE_NAMES, getFeatureSettings, isFeatureName, setFeatureEnabled, type FeatureName } from "../Helpers/settings.js";

async function panel(guildId: string): Promise<{embeds:EmbedBuilder[];components:ActionRowBuilder<ButtonBuilder>[]}> {
  const states = await getFeatureSettings(guildId);
  const embed = new EmbedBuilder().setColor(0x5865f2).setTitle("Server feature settings")
    .setDescription("Control which Lemegeton feature environments are available in this server. Changes are guild-local and take effect immediately.")
    .addFields(FEATURE_NAMES.map(feature=>({name:`/${feature}`,value:states[feature]?"Enabled":"Disabled",inline:true})))
    .setFooter({text:"Only members with Manage Server can change these settings."});
  const components: ActionRowBuilder<ButtonBuilder>[] = [];
  for (let index = 0; index < FEATURE_NAMES.length; index += 5) {
    const row = new ActionRowBuilder<ButtonBuilder>();
    for (const feature of FEATURE_NAMES.slice(index, index + 5)) row.addComponents(new ButtonBuilder()
      .setCustomId(`settings:toggle:${feature}`).setLabel(`/${feature} · ${states[feature]?"On":"Off"}`)
      .setStyle(states[feature]?ButtonStyle.Success:ButtonStyle.Secondary));
    components.push(row);
  }
  return {embeds:[embed],components};
}

function canManage(interaction: ButtonInteraction | ChatInputCommandInteraction): boolean {
  return interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild) ?? false;
}

export class SettingsCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder().setName("settings")
    .setDescription("Configure this server's Lemegeton feature availability")
    .addStringOption(option=>option.setName("action").setDescription("Open settings or change one feature")
      .addChoices({name:"View settings",value:"view"},{name:"Toggle a feature",value:"toggle"}))
    .addStringOption(option=>option.setName("feature").setDescription("Feature environment to change")
      .addChoices(...FEATURE_NAMES.map(feature=>({name:`/${feature}`,value:feature}))))
    .addBooleanOption(option=>option.setName("enabled").setDescription("Set availability explicitly; omit to invert current state"));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guildId) { await interaction.reply({content:"Server settings are only available inside a server.",flags:MessageFlags.Ephemeral}); return; }
    const action = interaction.options.getString("action") ?? "view";
    if (action === "toggle") {
      const feature = interaction.options.getString("feature");
      const enabled = interaction.options.getBoolean("enabled");
      if (!feature || !isFeatureName(feature)) { await interaction.reply({content:"Choose a feature to change.",flags:MessageFlags.Ephemeral}); return; }
      if (!canManage(interaction)) { await interaction.reply({content:"Manage Server permission is required to change feature availability.",flags:MessageFlags.Ephemeral}); return; }
      const states = await getFeatureSettings(interaction.guildId);
      await setFeatureEnabled(interaction.guildId,feature as FeatureName,enabled ?? !states[feature],interaction.user.id);
    }
    await interaction.reply({...await panel(interaction.guildId),flags:MessageFlags.Ephemeral});
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const [,action,feature] = interaction.customId.split(":");
    if (action !== "toggle" || !feature || !isFeatureName(feature) || !interaction.guildId) return false;
    if (!canManage(interaction)) {
      await interaction.reply({content:"Manage Server permission is required to change feature availability.",flags:MessageFlags.Ephemeral});
      return true;
    }
    const states = await getFeatureSettings(interaction.guildId);
    await setFeatureEnabled(interaction.guildId,feature as FeatureName,!states[feature],interaction.user.id);
    await interaction.update(await panel(interaction.guildId));
    return true;
  }
}

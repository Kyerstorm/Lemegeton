import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelSelectMenuBuilder,
  ChannelType,
  EmbedBuilder,
  MessageFlags,
  ModalBuilder,
  PermissionFlagsBits,
  RoleSelectMenuBuilder,
  SlashCommandBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ButtonInteraction,
  type ChannelSelectMenuInteraction,
  type ChatInputCommandInteraction,
  type Guild,
  type GuildMember,
  type ModalSubmitInteraction,
  type Role,
  type RoleSelectMenuInteraction,
} from "discord.js";
import type { FeatureCommand } from "../Helpers/command.js";
import { homeEmbed } from "../Helpers/discord.js";
import {
  customRoleChannelAllowed,
  customRoleCooldownMessage,
  customRoleEligibility,
  getCustomRoleRecord,
  getCustomRoleSettings,
  HOLOGRAPHIC_COLORS,
  parseCustomRoleColor,
  saveCustomRole,
  updateCustomRole,
  updateCustomRoleSettings,
  validateCustomRoleAnchor,
  validateCustomRoleEmoji,
  validateCustomRoleName,
  type CustomRoleRecord,
  type CustomRoleSettings,
} from "../Helpers/custom-roles.js";

type SelectInteraction = RoleSelectMenuInteraction | ChannelSelectMenuInteraction;
type GuildInteraction = ChatInputCommandInteraction | ButtonInteraction | ModalSubmitInteraction | SelectInteraction;

const MAX_ROLE_COOLDOWN = 86_400;
const MEMBER_ACTIONS = [
  { id: "create", label: "Create role", style: ButtonStyle.Success },
  { id: "rename", label: "Rename", style: ButtonStyle.Secondary },
  { id: "color", label: "Change color", style: ButtonStyle.Secondary },
  { id: "wear", label: "Put on", style: ButtonStyle.Primary },
  { id: "unwear", label: "Take off", style: ButtonStyle.Secondary },
] as const;

function userCustomId(userId: string, action: string): string {
  return `custom-role:${userId}:${action}`;
}

function isManager(interaction: GuildInteraction): boolean {
  const permissions = interaction.memberPermissions;
  return Boolean(permissions?.has(PermissionFlagsBits.Administrator)
    || permissions?.has(PermissionFlagsBits.ManageGuild));
}

function canManageRoles(interaction: GuildInteraction): boolean {
  const permissions = interaction.memberPermissions;
  return Boolean(permissions?.has(PermissionFlagsBits.Administrator)
    || (permissions?.has(PermissionFlagsBits.ManageGuild) && permissions.has(PermissionFlagsBits.ManageRoles)));
}

function colorLabel(color: number | null): string {
  return color === null ? "Default" : `#${color.toString(16).padStart(6, "0").toUpperCase()}`;
}

function memberRows(userId: string, manager: boolean): ActionRowBuilder<ButtonBuilder>[] {
  const rows: ActionRowBuilder<ButtonBuilder>[] = [];
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    ...MEMBER_ACTIONS.slice(0, 3).map(action => new ButtonBuilder()
      .setCustomId(userCustomId(userId, action.id)).setLabel(action.label).setStyle(action.style)),
  ));
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    ...MEMBER_ACTIONS.slice(3).map(action => new ButtonBuilder()
      .setCustomId(userCustomId(userId, action.id)).setLabel(action.label).setStyle(action.style)),
    new ButtonBuilder().setCustomId(userCustomId(userId, "move")).setLabel("Move").setStyle(ButtonStyle.Secondary),
    ...(manager ? [new ButtonBuilder().setCustomId(userCustomId(userId, "admin"))
      .setLabel("Admin settings").setStyle(ButtonStyle.Danger)] : []),
  ));
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(userCustomId(userId, "gradient")).setLabel("Gradient").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "holographic")).setLabel("Holographic").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "icon")).setLabel("Role icon").setStyle(ButtonStyle.Secondary),
  ));
  return rows;
}

function adminRows(userId: string, settings: CustomRoleSettings): ActionRowBuilder<ButtonBuilder>[] {
  const toggle = new ButtonBuilder().setCustomId(userCustomId(userId, "toggle"))
    .setLabel(settings.enabled ? "Disable feature" : "Enable feature")
    .setStyle(settings.enabled ? ButtonStyle.Danger : ButtonStyle.Success);
  const first = new ActionRowBuilder<ButtonBuilder>().addComponents(
    toggle,
    new ButtonBuilder().setCustomId(userCustomId(userId, "anchor")).setLabel("Set anchor").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "channel")).setLabel("Set command channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "cooldown")).setLabel("Set cooldown").setStyle(ButtonStyle.Secondary),
  );
  const second = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(userCustomId(userId, "allow-role")).setLabel("Allow a role").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "remove-allowed")).setLabel("Remove allowed role").setStyle(ButtonStyle.Secondary),
  );
  const third = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(userCustomId(userId, "log-channel")).setLabel("Set log channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "clear-channel")).setLabel("Clear command channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "clear-log-channel")).setLabel("Clear log channel").setStyle(ButtonStyle.Secondary),
  );
  return [first, second, third];
}

function nameModal(userId: string, action: "create" | "rename"): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, action))
    .setTitle(action === "create" ? "Create your custom role" : "Rename your custom role")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("name").setLabel("Role name")
        .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(100),
    ));
}

function colorModal(userId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "color"))
    .setTitle("Change role color")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("color").setLabel("Hex color (for example #8B5CF6)")
        .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(7),
    ));
}

function gradientModal(userId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "gradient"))
    .setTitle("Set role gradient")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("primary").setLabel("First hex color")
          .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(7),
      ),
      new ActionRowBuilder<TextInputBuilder>().addComponents(
        new TextInputBuilder().setCustomId("secondary").setLabel("Second hex color")
          .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(7),
      ),
    );
}

function iconModal(userId: string): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "icon"))
    .setTitle("Set role emoji")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("emoji").setLabel("One standard Unicode emoji")
        .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(32),
    ));
}

function moveModal(userId: string, placement: "above" | "below"): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "move"))
    .setTitle("Move your custom role")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("placement").setLabel("Type above or below the anchor role")
        .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(5).setValue(placement),
    ));
}

function cooldownModal(userId: string, seconds: number): ModalBuilder {
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "cooldown"))
    .setTitle("Custom role cooldown")
    .addComponents(new ActionRowBuilder<TextInputBuilder>().addComponents(
      new TextInputBuilder().setCustomId("seconds").setLabel("Seconds (0 to 86400)")
        .setStyle(TextInputStyle.Short).setRequired(true).setMaxLength(5).setValue(String(seconds)),
    ));
}

function protectedRoleNames(roles: Iterable<Role>): string[] {
  const flags = [
    PermissionFlagsBits.Administrator,
    PermissionFlagsBits.ManageGuild,
    PermissionFlagsBits.ManageMessages,
    PermissionFlagsBits.ManageRoles,
    PermissionFlagsBits.KickMembers,
    PermissionFlagsBits.BanMembers,
    PermissionFlagsBits.ModerateMembers,
  ];
  return [...roles].filter(role => flags.some(flag => role.permissions.has(flag))).map(role => role.name);
}

export class CustomRoleCommand implements FeatureCommand {
  readonly data = new SlashCommandBuilder()
    .setName("custom-role")
    .setDescription("Create and manage your server custom role")
    .addStringOption(option => option.setName("action").setDescription("Custom role action").addChoices(
      { name: "Open panel", value: "home" },
      { name: "Create role", value: "create" },
      { name: "Rename role", value: "rename" },
      { name: "Change color", value: "color" },
      { name: "Set gradient", value: "gradient" },
      { name: "Set holographic style", value: "holographic" },
      { name: "Set role emoji", value: "icon" },
      { name: "Put role on", value: "wear" },
      { name: "Take role off", value: "unwear" },
      { name: "Move role", value: "move" },
      { name: "Admin settings", value: "admin" },
      { name: "Enable feature", value: "enable" },
      { name: "Disable feature", value: "disable" },
      { name: "Set anchor role", value: "anchor" },
      { name: "Set command channel", value: "channel" },
      { name: "Clear command channel", value: "clear-channel" },
      { name: "Set cooldown", value: "cooldown" },
      { name: "Allow a role", value: "allow-role" },
      { name: "Remove an allowed role", value: "remove-allowed" },
    ))
    .addStringOption(option => option.setName("name").setDescription("Name for your custom role").setMaxLength(100))
    .addStringOption(option => option.setName("color").setDescription("Hex role color, such as #8B5CF6").setMaxLength(7))
    .addStringOption(option => option.setName("secondary_color").setDescription("Second hex color for a gradient").setMaxLength(7))
    .addStringOption(option => option.setName("emoji").setDescription("One standard Unicode role emoji").setMaxLength(32))
    .addRoleOption(option => option.setName("role").setDescription("Anchor or eligibility role"))
    .addChannelOption(option => option.setName("channel").setDescription("Channel where members can use the command"))
    .addIntegerOption(option => option.setName("seconds").setDescription("Cooldown in seconds (0 to 86400)").setMinValue(0).setMaxValue(MAX_ROLE_COOLDOWN))
    .addChannelOption(option => option.setName("log_channel").setDescription("Channel for custom role audit messages"))
    .addStringOption(option => option.setName("placement").setDescription("Where custom roles sit relative to the anchor")
      .addChoices({ name: "Below anchor", value: "below" }, { name: "Above anchor", value: "above" }));

  async execute(interaction: ChatInputCommandInteraction): Promise<void> {
    if (!interaction.guild || !interaction.guildId) {
      await interaction.reply({ content: "Custom Roles are only available inside a server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const action = interaction.options.getString("action") ?? "home";
    try {
      switch (action) {
        case "home": await this.showMemberPanel(interaction, await interaction.guild.members.fetch(interaction.user.id)); return;
        case "admin": await this.showAdminPanel(interaction); return;
        case "create": {
          const name = interaction.options.getString("name");
          if (!name) { await interaction.showModal(nameModal(interaction.user.id, "create")); return; }
          await this.reportResult(interaction, await this.createRole(interaction, name));
          return;
        }
        case "rename": {
          const name = interaction.options.getString("name");
          if (!name) { await interaction.showModal(nameModal(interaction.user.id, "rename")); return; }
          await this.reportResult(interaction, await this.renameRole(interaction, name));
          return;
        }
        case "color": {
          const color = interaction.options.getString("color");
          if (!color) { await interaction.showModal(colorModal(interaction.user.id)); return; }
          await this.reportResult(interaction, await this.setRoleColor(interaction, color));
          return;
        }
        case "gradient": {
          const primary = interaction.options.getString("color");
          const secondary = interaction.options.getString("secondary_color");
          if (!primary || !secondary) { await interaction.showModal(gradientModal(interaction.user.id)); return; }
          await this.reportResult(interaction, await this.setRoleStyle(interaction, "gradient", primary, secondary));
          return;
        }
        case "holographic": await this.reportResult(interaction, await this.setRoleStyle(interaction, "holographic")); return;
        case "icon": {
          const emoji = interaction.options.getString("emoji");
          if (!emoji) { await interaction.showModal(iconModal(interaction.user.id)); return; }
          await this.reportResult(interaction, await this.setRoleIconEmoji(interaction, emoji));
          return;
        }
        case "wear": await this.reportResult(interaction, await this.wearRole(interaction)); return;
        case "unwear": await this.reportResult(interaction, await this.unwearRole(interaction)); return;
        case "move": {
          const placement = interaction.options.getString("placement");
          if (placement !== "above" && placement !== "below") {
            const settings = await getCustomRoleSettings(interaction.guildId);
            await interaction.showModal(moveModal(interaction.user.id, settings.anchor_place));
            return;
          }
          await this.reportResult(interaction, await this.moveRole(interaction, placement));
          return;
        }
        case "enable": await this.configureEnabled(interaction, true); return;
        case "disable": await this.configureEnabled(interaction, false); return;
        case "anchor": await this.configureAnchor(interaction, interaction.options.getRole("role"), interaction.options.getString("placement")); return;
        case "channel": await this.configureChannel(interaction, interaction.options.getChannel("channel")); return;
        case "clear-channel": await this.configureChannel(interaction, null); return;
        case "log-channel": await this.configureLogChannel(interaction, interaction.options.getChannel("log_channel")); return;
        case "clear-log-channel": await this.configureLogChannel(interaction, null); return;
        case "cooldown": {
          const seconds = interaction.options.getInteger("seconds");
          if (seconds === null) { await interaction.showModal(cooldownModal(interaction.user.id, 0)); return; }
          await this.configureCooldown(interaction, seconds);
          return;
        }
        case "allow-role": await this.configureAllowedRole(interaction, interaction.options.getRole("role"), true); return;
        case "remove-allowed": await this.configureAllowedRole(interaction, interaction.options.getRole("role"), false); return;
        default: await this.showMemberPanel(interaction, await interaction.guild.members.fetch(interaction.user.id));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Custom Roles could not complete that action.";
      if (interaction.replied || interaction.deferred) await interaction.followUp({ content: message, flags: MessageFlags.Ephemeral });
      else await interaction.reply({ content: message, flags: MessageFlags.Ephemeral });
    }
  }

  async handleButton(interaction: ButtonInteraction): Promise<boolean> {
    const [prefix, ownerId, action] = interaction.customId.split(":");
    if (prefix !== "custom-role" || !action) return false;
    if (ownerId !== interaction.user.id) {
      await interaction.reply({ content: "This Custom Roles panel belongs to another member. Run /custom-role to open your own.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "admin") { await this.showAdminPanel(interaction); return true; }
    if (action === "create" || action === "rename") { await interaction.showModal(nameModal(interaction.user.id, action)); return true; }
    if (action === "color") { await interaction.showModal(colorModal(interaction.user.id)); return true; }
    if (action === "gradient") { await interaction.showModal(gradientModal(interaction.user.id)); return true; }
    if (action === "holographic") { await this.reportResult(interaction, await this.setRoleStyle(interaction, "holographic")); return true; }
    if (action === "icon") { await interaction.showModal(iconModal(interaction.user.id)); return true; }
    if (action === "move") {
      const settings = await getCustomRoleSettings(interaction.guildId!);
      await interaction.showModal(moveModal(interaction.user.id, settings.anchor_place === "above" ? "below" : "above"));
      return true;
    }
    if (action === "cooldown") {
      if (!this.requireManager(interaction)) return true;
      const settings = await getCustomRoleSettings(interaction.guildId!);
      await interaction.showModal(cooldownModal(interaction.user.id, settings.cooldown_seconds));
      return true;
    }
    if (action === "anchor" || action === "allow-role" || action === "remove-allowed") {
      if (!this.requireManager(interaction)) return true;
      const menu = new RoleSelectMenuBuilder().setCustomId(userCustomId(interaction.user.id, action))
        .setPlaceholder(action === "anchor" ? "Choose the anchor role" : "Choose a server role").setMinValues(1).setMaxValues(1);
      await interaction.reply({ content: "Choose a role.", components: [new ActionRowBuilder<RoleSelectMenuBuilder>().addComponents(menu)], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "clear-channel") {
      if (!this.requireManager(interaction)) return true;
      await this.configureChannel(interaction, null);
      return true;
    }
    if (action === "clear-log-channel") {
      if (!this.requireManager(interaction)) return true;
      await this.configureLogChannel(interaction, null);
      return true;
    }
    if (action === "channel" || action === "log-channel") {
      if (!this.requireManager(interaction)) return true;
      const menu = new ChannelSelectMenuBuilder().setCustomId(userCustomId(interaction.user.id, action))
        .setPlaceholder(action === "log-channel" ? "Choose the Custom Roles log channel" : "Choose the Custom Roles command channel")
        .setMinValues(1).setMaxValues(1);
      await interaction.reply({ content: "Choose a text or announcement channel.", components: [new ActionRowBuilder<ChannelSelectMenuBuilder>().addComponents(menu)], flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "toggle") {
      if (!this.requireManager(interaction)) return true;
      const settings = await getCustomRoleSettings(interaction.guildId!);
      await this.configureEnabled(interaction, !settings.enabled);
      return true;
    }
    if (action === "wear") { await this.reportResult(interaction, await this.wearRole(interaction)); return true; }
    if (action === "unwear") { await this.reportResult(interaction, await this.unwearRole(interaction)); return true; }
    return false;
  }

  async handleSelect(interaction: RoleSelectMenuInteraction | ChannelSelectMenuInteraction): Promise<boolean> {
    const [prefix, ownerId, action] = interaction.customId.split(":");
    if (prefix !== "custom-role" || !action) return false;
    if (ownerId !== interaction.user.id) {
      await interaction.reply({ content: "This Custom Roles panel belongs to another member.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (!this.requireManager(interaction)) return true;
    if (interaction.isRoleSelectMenu()) {
      const role = await interaction.guild!.roles.fetch(interaction.values[0] ?? "");
      if (!role) { await interaction.reply({ content: "That role no longer exists.", flags: MessageFlags.Ephemeral }); return true; }
      if (action === "anchor") { await this.configureAnchor(interaction, role, "below"); return true; }
      if (action === "allow-role") { await this.configureAllowedRole(interaction, role, true); return true; }
      if (action === "remove-allowed") { await this.configureAllowedRole(interaction, role, false); return true; }
    }
    if (interaction.isChannelSelectMenu() && (action === "channel" || action === "log-channel")) {
      const channel = await interaction.guild!.channels.fetch(interaction.values[0] ?? "");
      if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
        await interaction.reply({ content: "Choose a text or announcement channel.", flags: MessageFlags.Ephemeral });
        return true;
      }
      if (action === "log-channel") await this.configureLogChannel(interaction, channel);
      else await this.configureChannel(interaction, channel);
      return true;
    }
    return false;
  }

  async handleModal(interaction: ModalSubmitInteraction): Promise<boolean> {
    const [prefix, ownerId, action] = interaction.customId.split(":");
    if (prefix !== "custom-role" || !action) return false;
    if (ownerId !== interaction.user.id) {
      await interaction.reply({ content: "This form belongs to another member.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "create" || action === "rename") {
      const name = interaction.fields.getTextInputValue("name");
      const result = action === "create" ? await this.createRole(interaction, name) : await this.renameRole(interaction, name);
      await this.reportResult(interaction, result);
      return true;
    }
    if (action === "color") {
      await this.reportResult(interaction, await this.setRoleColor(interaction, interaction.fields.getTextInputValue("color")));
      return true;
    }
    if (action === "gradient") {
      await this.reportResult(interaction, await this.setRoleStyle(
        interaction, "gradient", interaction.fields.getTextInputValue("primary"), interaction.fields.getTextInputValue("secondary"),
      ));
      return true;
    }
    if (action === "icon") {
      await this.reportResult(interaction, await this.setRoleIconEmoji(interaction, interaction.fields.getTextInputValue("emoji")));
      return true;
    }
    if (action === "move") {
      const placement = interaction.fields.getTextInputValue("placement").trim().toLowerCase();
      if (placement !== "above" && placement !== "below") {
        await interaction.reply({ content: "Type either **above** or **below**.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await this.reportResult(interaction, await this.moveRole(interaction, placement));
      return true;
    }
    if (action === "cooldown") {
      if (!this.requireManager(interaction)) return true;
      const raw = interaction.fields.getTextInputValue("seconds").trim();
      if (!/^\d+$/.test(raw) || Number(raw) > MAX_ROLE_COOLDOWN) {
        await interaction.reply({ content: "Enter a whole number from 0 to 86400 seconds.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await this.configureCooldown(interaction, Number(raw));
      return true;
    }
    return false;
  }

  private requireManager(interaction: GuildInteraction): boolean {
    if (!interaction.guildId || !isManager(interaction)) {
      void interaction.reply({ content: "Manage Server permission is required for Custom Roles administration.", flags: MessageFlags.Ephemeral });
      return false;
    }
    return true;
  }

  private async reportResult(interaction: GuildInteraction, result: { ok: boolean; message: string }): Promise<void> {
    await interaction.reply({ content: result.message, flags: MessageFlags.Ephemeral }).catch(async () => {
      if (interaction.isRepliable() && interaction.deferred) await interaction.editReply({ content: result.message });
    });
  }

  private async showMemberPanel(interaction: GuildInteraction, member: GuildMember): Promise<void> {
    const settings = await getCustomRoleSettings(member.guild.id);
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    const role = record?.role_id ? member.guild.roles.cache.get(record.role_id) ?? null : null;
    const eligible = customRoleEligibility(member, settings);
    const anchor = settings.anchor_role_id ? member.guild.roles.cache.get(settings.anchor_role_id) : null;
    const status = !settings.enabled || !anchor ? "Not configured by this server" : eligible ? "Eligible" : "Server booster or allowed role required";
    const embed = homeEmbed(
      "Custom Roles",
      "Create and style one personal server role. Eligibility and permissions are checked again whenever you use an action.",
      [
        { name: "Feature", value: settings.enabled && anchor ? "Enabled" : "Not configured", inline: true },
        { name: "Eligibility", value: status, inline: true },
        { name: "Your role", value: role ? role.name : record?.name ? `${record.name} · saved` : "Not created", inline: true },
        { name: "Color", value: `${record?.color_mode ?? "solid"} · ${colorLabel(record?.primary_color ?? null)}`, inline: true },
        { name: "Icon", value: record?.icon_emoji ?? "None", inline: true },
        { name: "Anchor", value: anchor?.name ?? "Not set", inline: true },
      ],
    );
    await interaction.reply({ embeds: [embed], components: memberRows(member.id, isManager(interaction)), flags: MessageFlags.Ephemeral });
  }

  private async showAdminPanel(interaction: GuildInteraction): Promise<void> {
    if (!this.requireManager(interaction)) return;
    const settings = await getCustomRoleSettings(interaction.guildId!);
    const anchor = settings.anchor_role_id ? interaction.guild!.roles.cache.get(settings.anchor_role_id) : null;
    const channel = settings.command_channel_id ? await interaction.guild!.channels.fetch(settings.command_channel_id).catch(() => null) : null;
    const embed = homeEmbed("Custom Roles · Server settings",
      "Manage the existing booster role feature. The bot needs Manage Roles and its top role must stay above the configured anchor.",
      [
        { name: "Status", value: settings.enabled ? "Enabled" : "Disabled", inline: true },
        { name: "Anchor", value: anchor?.name ?? "Not set", inline: true },
        { name: "Placement", value: settings.anchor_place, inline: true },
        { name: "Command channel", value: channel ? `<#${channel.id}>` : "Any channel", inline: true },
        { name: "Log channel", value: settings.log_channel_id ? `<#${settings.log_channel_id}>` : "Off", inline: true },
        { name: "Cooldown", value: settings.cooldown_seconds ? `${settings.cooldown_seconds}s` : "Off", inline: true },
        { name: "Allowed roles", value: settings.allowed_role_ids.length ? settings.allowed_role_ids.map(id => `<@&${id}>`).join(", ").slice(0, 900) : "Boosters only", inline: false },
      ],
    );
    await interaction.reply({ embeds: [embed], components: adminRows(interaction.user.id, settings), flags: MessageFlags.Ephemeral });
  }

  private async memberContext(interaction: GuildInteraction): Promise<{ member: GuildMember; settings: CustomRoleSettings } | { error: string }> {
    if (!interaction.guild || !interaction.guildId) return { error: "Custom Roles are only available inside a server." };
    const member = await interaction.guild.members.fetch(interaction.user.id);
    const settings = await getCustomRoleSettings(interaction.guildId);
    const channel = interaction.channel;
    const parentId = channel && "parentId" in channel ? channel.parentId : null;
    if (!settings.enabled || !settings.anchor_role_id || !interaction.guild.roles.cache.has(settings.anchor_role_id)) {
      return { error: "Custom Roles haven't been configured by this server yet. Ask an administrator to set an anchor role and enable the feature." };
    }
    if (!customRoleEligibility(member, settings)) return { error: "Custom Roles are for server boosters and members with an administrator-approved allowed role." };
    if (channel && !customRoleChannelAllowed(channel.id, parentId, settings)) return { error: `Custom role commands can only be used in <#${settings.command_channel_id}> and its threads.` };
    if (!member.guild.members.me?.permissions.has(PermissionFlagsBits.ManageRoles)) return { error: "I need the Manage Roles permission to manage custom roles." };
    const anchor = interaction.guild.roles.cache.get(settings.anchor_role_id);
    if (!anchor || validateCustomRoleAnchor(interaction.guild, anchor)) return { error: "The configured anchor is no longer usable. Ask an administrator to set it again." };
    return { member, settings };
  }

  private async validateName(member: GuildMember, raw: string, settings: CustomRoleSettings, ownRoleId: string | null) {
    const roles = [...member.guild.roles.cache.values()];
    const reserved = roles.filter(role => !role.managed && role.id !== ownRoleId).map(role => role.name);
    const protectedNames = protectedRoleNames(roles.filter(role => role.id !== ownRoleId));
    return validateCustomRoleName(raw, settings, reserved, protectedNames);
  }

  private async createRole(interaction: GuildInteraction, rawName: string): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const existing = await getCustomRoleRecord(member.guild.id, member.id);
    const live = existing?.role_id ? member.guild.roles.cache.get(existing.role_id) : null;
    if (live) return { ok: false, message: `Your role already exists as **${live.name}**. Use Rename or Put on from the panel.` };
    const name = rawName.trim() || existing?.name || "";
    const checked = await this.validateName(member, name, settings, existing?.role_id ?? null);
    if (checked.error || !checked.name) return { ok: false, message: checked.error ?? "Choose a role name." };
    const botMember = member.guild.members.me;
    const anchor = settings.anchor_role_id ? member.guild.roles.cache.get(settings.anchor_role_id) : null;
    if (!botMember || !anchor || anchor.position >= botMember.roles.highest.position) return { ok: false, message: "My highest role must be above the configured anchor role." };
    if (member.guild.roles.cache.size >= 250) return { ok: false, message: "This server has reached Discord's role limit, so I can't create another role." };

    let role: Role | null = null;
    try {
      const enhancedStyles = (member.guild.features as readonly string[]).includes("ENHANCED_ROLE_COLORS");
      const roleIcons = (member.guild.features as readonly string[]).includes("ROLE_ICONS");
      let colorMode = existing?.color_mode ?? "solid";
      let primaryColor = existing?.primary_color ?? null;
      let secondaryColor = existing?.secondary_color ?? null;
      let colors: { primaryColor: number; secondaryColor?: number | null; tertiaryColor?: number | null };
      if (colorMode === "holographic" && enhancedStyles) {
        [primaryColor, secondaryColor] = HOLOGRAPHIC_COLORS;
        colors = { primaryColor: HOLOGRAPHIC_COLORS[0], secondaryColor: HOLOGRAPHIC_COLORS[1], tertiaryColor: HOLOGRAPHIC_COLORS[2] };
      } else if (colorMode === "gradient" && enhancedStyles) {
        colors = { primaryColor: primaryColor ?? 0, secondaryColor: secondaryColor ?? 0, tertiaryColor: null };
      } else {
        if (colorMode !== "solid") colorMode = "solid";
        secondaryColor = null;
        colors = { primaryColor: primaryColor ?? 0, secondaryColor: null, tertiaryColor: null };
      }
      role = await member.guild.roles.create({
        name: checked.name,
        colors,
        ...(roleIcons && existing?.icon_emoji ? { unicodeEmoji: existing.icon_emoji } : {}),
        permissions: [],
        reason: `Custom Roles: custom role for ${member.user.tag} (${member.id})`,
      });
      const targetPosition = settings.anchor_place === "above" ? anchor.position + 1 : Math.max(1, anchor.position - 1);
      if (targetPosition >= botMember.roles.highest.position) {
        await role.delete("Custom Roles: requested position is above the bot role").catch(() => undefined);
        return { ok: false, message: "The configured anchor is too high for me to place a custom role safely." };
      }
      role = await role.setPosition(targetPosition, { reason: "Custom Roles: place role beside configured anchor" });
      await saveCustomRole({
        guild_id: member.guild.id,
        user_id: member.id,
        role_id: role.id,
        position_hint: role.position,
        status: "active",
        name: checked.name,
        color_mode: colorMode,
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        icon_emoji: existing?.icon_emoji ?? null,
      });
      await member.roles.add(role, "Custom Roles: assign personal role");
      await this.logEvent(member.guild, settings, `Created a custom role for <@!${member.id}>.`);
      const styleNotice = existing?.color_mode && existing.color_mode !== colorMode
        ? " Your server no longer supports the saved gradient style, so I restored a solid color."
        : "";
      return { ok: true, message: `Your custom role **${checked.name}** has been created and added to you.${styleNotice}` };
    } catch (error) {
      if (role && !await getCustomRoleRecord(member.guild.id, member.id).catch(() => null)) {
        await role.delete("Custom Roles: roll back incomplete creation").catch(() => undefined);
      }
      return { ok: false, message: error instanceof Error ? `I couldn't create your role: ${error.message}` : "I couldn't create your role. Check the bot's Manage Roles permission and hierarchy." };
    }
  }

  private async renameRole(interaction: GuildInteraction, rawName: string): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "You haven't created a custom role yet. Use Create role first." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    const checked = await this.validateName(member, rawName, settings, role.id);
    if (!checked.name || checked.error) return { ok: false, message: checked.error ?? "Choose a valid role name." };
    try {
      await role.edit({ name: checked.name, reason: "Custom Roles: member renamed their role" });
      await updateCustomRole(member.guild.id, member.id, { name: checked.name }, true);
      await this.logEvent(member.guild, settings, `<@!${member.id}> renamed their custom role.`);
      return { ok: true, message: `Your role is now called **${checked.name}**.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't rename your role: ${error.message}` : "I couldn't rename your role." };
    }
  }

  private async setRoleColor(interaction: GuildInteraction, rawColor: string): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before changing its color." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    const color = parseCustomRoleColor(rawColor);
    if (color === null) return { ok: false, message: "Enter a valid hex color, such as #8B5CF6 or #ABC." };
    try {
      await role.edit({ colors: { primaryColor: color, secondaryColor: null, tertiaryColor: null }, reason: "Custom Roles: member changed role color" });
      await updateCustomRole(member.guild.id, member.id, { color_mode: "solid", primary_color: color, secondary_color: null }, true);
      await this.logEvent(member.guild, settings, `<@!${member.id}> changed their custom role color.`);
      return { ok: true, message: `Your role color is now **${colorLabel(color)}**.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't change your role color: ${error.message}` : "I couldn't change your role color." };
    }
  }

  private async setRoleStyle(
    interaction: GuildInteraction,
    mode: "gradient" | "holographic",
    rawPrimary?: string,
    rawSecondary?: string,
  ): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    if (!(member.guild.features as readonly string[]).includes("ENHANCED_ROLE_COLORS")) {
      return { ok: false, message: "Gradient and holographic styles need Discord's Enhanced Role Styles feature (3 server boosts). Solid colors still work." };
    }
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before changing its style." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    let primaryColor: number;
    let secondaryColor: number;
    let colors: { primaryColor: number; secondaryColor: number; tertiaryColor: number | null };
    if (mode === "holographic") {
      [primaryColor, secondaryColor] = HOLOGRAPHIC_COLORS;
      colors = { primaryColor: HOLOGRAPHIC_COLORS[0], secondaryColor: HOLOGRAPHIC_COLORS[1], tertiaryColor: HOLOGRAPHIC_COLORS[2] };
    } else {
      primaryColor = rawPrimary ? parseCustomRoleColor(rawPrimary) ?? -1 : -1;
      secondaryColor = rawSecondary ? parseCustomRoleColor(rawSecondary) ?? -1 : -1;
      if (primaryColor < 0 || secondaryColor < 0) {
        return { ok: false, message: "Enter two valid hex colors, such as #8B5CF6 and #EC4899." };
      }
      colors = { primaryColor, secondaryColor, tertiaryColor: null };
    }
    try {
      await role.edit({ colors, reason: `Custom Roles: member selected ${mode} colors` });
      await updateCustomRole(member.guild.id, member.id, { color_mode: mode, primary_color: primaryColor, secondary_color: secondaryColor }, true);
      await this.logEvent(member.guild, settings, `<@!${member.id}> changed their custom role style to ${mode}.`);
      return { ok: true, message: mode === "holographic" ? "Your role now has the holographic style." : "Your role now has a two-color gradient." };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't change your role style: ${error.message}` : "I couldn't change your role style." };
    }
  }

  private async setRoleIconEmoji(interaction: GuildInteraction, rawEmoji: string): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    if (!(member.guild.features as readonly string[]).includes("ROLE_ICONS")) {
      return { ok: false, message: "Role icons need Discord's Role Icons server feature (Boost Level 2). You can still use a custom role without an icon." };
    }
    const emoji = validateCustomRoleEmoji(rawEmoji);
    if (!emoji) return { ok: false, message: "Send one standard Unicode emoji, not a custom server emoji or emoji shortcode." };
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before setting its icon." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    try {
      await role.edit({ unicodeEmoji: emoji, reason: "Custom Roles: member changed role icon" });
      await updateCustomRole(member.guild.id, member.id, { icon_emoji: emoji }, true);
      await this.logEvent(member.guild, settings, `<@!${member.id}> changed their custom role icon.`);
      return { ok: true, message: `Your role icon is now ${emoji}.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't set that role icon: ${error.message}` : "I couldn't set that role icon." };
    }
  }

  private async moveRole(
    interaction: GuildInteraction,
    placement: "above" | "below",
  ): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before moving it." };
    const role = member.guild.roles.cache.get(record.role_id);
    const anchor = settings.anchor_role_id ? member.guild.roles.cache.get(settings.anchor_role_id) : null;
    const botMember = member.guild.members.me;
    if (!role || !anchor || !botMember) return { ok: false, message: "Your role or the configured anchor is missing. Ask an administrator to check the setup." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    const targetPosition = placement === "above" ? anchor.position + 1 : Math.max(1, anchor.position - 1);
    if (targetPosition >= botMember.roles.highest.position) {
      return { ok: false, message: "I can't place your role above my highest role. Ask an administrator to move the anchor lower." };
    }
    try {
      const moved = await role.setPosition(targetPosition, { reason: "Custom Roles: member moved their personal role" });
      await updateCustomRole(member.guild.id, member.id, { position_hint: moved.position }, true);
      await this.logEvent(member.guild, settings, `<@!${member.id}> moved their custom role ${placement} the anchor.`);
      return { ok: true, message: `Your role is now positioned directly ${placement} the anchor role.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't move your role: ${error.message}` : "I couldn't move your role." };
    }
  }

  private async wearRole(interaction: GuildInteraction): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "You haven't created a custom role yet." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    if (member.roles.cache.has(role.id)) return { ok: false, message: "You're already wearing your custom role." };
    try {
      await member.roles.add(role, "Custom Roles: member put their role on");
      await this.logEvent(member.guild, settings, `<@!${member.id}> put their custom role on.`);
      return { ok: true, message: `Your role **${role.name}** is back on you.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't put your role on: ${error.message}` : "I couldn't put your role on." };
    }
  }

  private async unwearRole(interaction: GuildInteraction): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    const role = record?.role_id ? member.guild.roles.cache.get(record.role_id) : null;
    if (!role || !member.roles.cache.has(role.id)) return { ok: false, message: "You're not wearing a custom role right now." };
    try {
      await member.roles.remove(role, "Custom Roles: member took their role off");
      await this.logEvent(member.guild, settings, `<@!${member.id}> took their custom role off.`);
      return { ok: true, message: `Took **${role.name}** off you. It's still saved; use Put on to wear it again.` };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? `I couldn't take your role off: ${error.message}` : "I couldn't take your role off." };
    }
  }

  private async configureEnabled(interaction: GuildInteraction, enabled: boolean): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    if (!canManageRoles(interaction)) {
      await interaction.reply({ content: "Manage Roles permission is also required to enable Custom Roles.", flags: MessageFlags.Ephemeral });
      return;
    }
    const settings = await getCustomRoleSettings(interaction.guild.id);
    if (enabled) {
      const anchor = settings.anchor_role_id ? interaction.guild.roles.cache.get(settings.anchor_role_id) : null;
      if (!anchor) {
        await interaction.reply({ content: "Set an anchor role before enabling Custom Roles.", flags: MessageFlags.Ephemeral });
        return;
      }
      const issue = validateCustomRoleAnchor(interaction.guild, anchor);
      if (issue) {
        await interaction.reply({ content: issue, flags: MessageFlags.Ephemeral });
        return;
      }
    }
    await updateCustomRoleSettings(interaction.guild.id, { enabled });
    await interaction.reply({ content: `Custom Roles is now **${enabled ? "enabled" : "disabled"}** in this server.`, flags: MessageFlags.Ephemeral });
  }

  private async configureAnchor(interaction: GuildInteraction, role: Role | null, placement: string | null): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    if (!canManageRoles(interaction)) {
      await interaction.reply({ content: "Manage Roles permission is required to change the Custom Roles anchor.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (!role) {
      await interaction.reply({ content: "Choose the role that custom roles should sit beside.", flags: MessageFlags.Ephemeral });
      return;
    }
    const issue = validateCustomRoleAnchor(interaction.guild, role);
    if (issue) {
      await interaction.reply({ content: issue, flags: MessageFlags.Ephemeral });
      return;
    }
    const anchorPlace = placement === "above" ? "above" : "below";
    await updateCustomRoleSettings(interaction.guild.id, { anchor_role_id: role.id, anchor_place: anchorPlace });
    await interaction.reply({ content: `Custom roles will be placed directly **${anchorPlace}** ${role}.`, flags: MessageFlags.Ephemeral });
  }

  private async configureChannel(interaction: GuildInteraction, channel: unknown): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    const selected = channel && typeof channel === "object" && "id" in channel ? channel as { id: string; type?: number } : null;
    if (selected && selected.type !== ChannelType.GuildText && selected.type !== ChannelType.GuildAnnouncement) {
      await interaction.reply({ content: "Choose a text or announcement channel.", flags: MessageFlags.Ephemeral });
      return;
    }
    await updateCustomRoleSettings(interaction.guild.id, { command_channel_id: selected?.id ?? null });
    await interaction.reply({ content: selected ? `Custom role commands are now limited to <#${selected.id}> and its threads.` : "Custom role commands can now be used in any channel.", flags: MessageFlags.Ephemeral });
  }

  private async configureLogChannel(interaction: GuildInteraction, channel: unknown): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    const selected = channel && typeof channel === "object" && "id" in channel
      ? channel as { id: string; type?: number; permissionsFor?: (member: GuildMember) => { has: (permission: bigint) => boolean } }
      : null;
    if (selected && selected.type !== ChannelType.GuildText && selected.type !== ChannelType.GuildAnnouncement) {
      await interaction.reply({ content: "Choose a text or announcement channel.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (selected) {
      const botMember = interaction.guild.members.me;
      const permissions = botMember && "permissionsFor" in selected
        ? selected.permissionsFor?.(botMember)
        : null;
      const canSend = Boolean(permissions
        && permissions.has(PermissionFlagsBits.ViewChannel)
        && permissions.has(PermissionFlagsBits.SendMessages)
        && permissions.has(PermissionFlagsBits.EmbedLinks));
      if (!canSend) {
        await interaction.reply({ content: `I need View Channel, Send Messages and Embed Links in <#${selected.id}>.`, flags: MessageFlags.Ephemeral });
        return;
      }
    }
    await updateCustomRoleSettings(interaction.guild.id, { log_channel_id: selected?.id ?? null });
    await interaction.reply({
      content: selected ? `Custom Roles audit messages will be posted in <#${selected.id}>.` : "Custom Roles audit logging is now off.",
      flags: MessageFlags.Ephemeral,
    });
  }

  private async configureCooldown(interaction: GuildInteraction, seconds: number): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    if (seconds < 0 || seconds > MAX_ROLE_COOLDOWN) {
      await interaction.reply({ content: "Cooldown must be between 0 and 86400 seconds.", flags: MessageFlags.Ephemeral });
      return;
    }
    await updateCustomRoleSettings(interaction.guild.id, { cooldown_seconds: seconds });
    await interaction.reply({ content: seconds ? `Members can change their role once every **${seconds} seconds**.` : "Custom role cooldown is now off.", flags: MessageFlags.Ephemeral });
  }

  private async configureAllowedRole(interaction: GuildInteraction, role: Role | null, add: boolean): Promise<void> {
    if (!this.requireManager(interaction) || !interaction.guild) return;
    if (!role) {
      await interaction.reply({ content: "Choose a server role.", flags: MessageFlags.Ephemeral });
      return;
    }
    if (role.id === interaction.guild.id) {
      await interaction.reply({ content: "@everyone can't be an allowed role.", flags: MessageFlags.Ephemeral });
      return;
    }
    const settings = await getCustomRoleSettings(interaction.guild.id);
    const current = new Set(settings.allowed_role_ids);
    if (add) current.add(role.id); else current.delete(role.id);
    await updateCustomRoleSettings(interaction.guild.id, { allowed_role_ids: [...current] });
    await interaction.reply({ content: add ? `Members with ${role} can now use Custom Roles.` : `${role} removed from the allowed role list.`, flags: MessageFlags.Ephemeral });
  }

  private async logEvent(guild: Guild, settings: CustomRoleSettings, content: string): Promise<void> {
    if (!settings.log_channel_id) return;
    const channel = await guild.channels.fetch(settings.log_channel_id).catch(() => null);
    if (channel?.isTextBased() && "send" in channel) {
      await channel.send({ content, allowedMentions: { parse: [] } }).catch(() => undefined);
    }
  }

}

import { randomUUID } from "node:crypto";
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
  type Attachment,
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
import {archiveLegacyCustomRole,cancelCustomRolePending,confirmCustomRolePending,getPendingCustomRoleRemoval} from "../Helpers/custom-role-lifecycle.js";
import { homeEmbed } from "../Helpers/discord.js";
import { extractCustomRoleAvatarPalette, processCustomRoleIconImage, type CustomRoleIconCrop } from "../Helpers/custom-role-images.js";
import { deleteCustomRoleIconSource, readCustomRoleIconSource, storeCustomRoleIconSource } from "../Helpers/media-storage.js";
import {
  customRoleChannelAllowed,
  customRoleCooldownMessage,
  customRoleEligibility,
  addCustomRoleBlockedWord,
  clearCustomRoleSnoozes,
  deleteCustomRoleRecord,
  removeCustomRolePendingUser,
  parseCustomRoleWordList,
  planLegacyCustomRoleImport,
  removeCustomRoleBlockedWord,
  getCustomRoleIconData,
  getCustomRoleRecord,
  getCustomRoleSettings,
  listCustomRoleRecords,
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
const memberRemovalRequests = new Map<string, { targetUserId: string; reason: string; expiresAt: number }>();
type LegacyImportPreview = { guildId: string; actorId: string; takeOverIds: string[]; notQualifyingIds: string[]; expiresAt: number };
const legacyImportPreviews = new Map<string, LegacyImportPreview>();
function legacyImportKey(guildId: string, actorId: string, planId: string): string { return guildId + ":" + actorId + ":" + planId; }
function removalRequestKey(guildId: string, actorId: string, targetId: string): string { return guildId + ":" + actorId + ":" + targetId; }
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
    new ButtonBuilder().setCustomId(userCustomId(userId, "icon")).setLabel("Emoji icon").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "image")).setLabel("Image icon").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "recrop")).setLabel("Recrop image").setStyle(ButtonStyle.Secondary),
  ));
  rows.push(new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(userCustomId(userId, "palette")).setLabel("Avatar colour palette").setStyle(ButtonStyle.Secondary),
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
    new ButtonBuilder().setCustomId(userCustomId(userId, "words")).setLabel("Blocked words").setStyle(ButtonStyle.Secondary),
  );
  const third = new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId(userCustomId(userId, "log-channel")).setLabel("Set log channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "clear-channel")).setLabel("Clear command channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "clear-log-channel")).setLabel("Clear log channel").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(userCustomId(userId, "pending")).setLabel("Pending removal").setStyle(ButtonStyle.Danger),
    new ButtonBuilder().setCustomId(userCustomId(userId, "import")).setLabel("Import old roles").setStyle(ButtonStyle.Primary),
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

function wordsModal(userId: string, blockedWords: string[], removedDefaults: string[]): ModalBuilder {
  const block = new TextInputBuilder().setCustomId("block").setLabel("Block words / re-enable built-ins")
    .setStyle(TextInputStyle.Paragraph).setRequired(false).setMaxLength(500);
  const unblock = new TextInputBuilder().setCustomId("unblock").setLabel("Unblock words / disable built-ins")
    .setStyle(TextInputStyle.Paragraph).setRequired(false).setMaxLength(500);
  if (blockedWords.length) block.setValue(blockedWords.join(", ").slice(0, 500));
  if (removedDefaults.length) unblock.setValue(removedDefaults.join(", ").slice(0, 500));
  return new ModalBuilder()
    .setCustomId(userCustomId(userId, "words"))
    .setTitle("Custom role name restrictions")
    .addComponents(
      new ActionRowBuilder<TextInputBuilder>().addComponents(block),
      new ActionRowBuilder<TextInputBuilder>().addComponents(unblock),
    );
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
      { name: "Set image icon", value: "image" },
      { name: "Recrop image icon", value: "recrop" },
      { name: "Put role on", value: "wear" },
      { name: "Take role off", value: "unwear" },
      { name: "Move role", value: "move" },
      { name: "Admin settings", value: "admin" },
      { name: "View member custom role", value: "member" },
      { name: "Remove member custom role", value: "remove-member" },
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
    .addAttachmentOption(option => option.setName("image").setDescription("PNG or JPEG image for your role icon"))
    .addIntegerOption(option => option.setName("crop_x").setDescription("Crop left edge in pixels").setMinValue(0))
    .addIntegerOption(option => option.setName("crop_y").setDescription("Crop top edge in pixels").setMinValue(0))
    .addIntegerOption(option => option.setName("crop_size").setDescription("Square crop size in pixels").setMinValue(16))
    .addRoleOption(option => option.setName("role").setDescription("Anchor or eligibility role"))
    .addChannelOption(option => option.setName("channel").setDescription("Channel where members can use the command"))
    .addIntegerOption(option => option.setName("seconds").setDescription("Cooldown in seconds (0 to 86400)").setMinValue(0).setMaxValue(MAX_ROLE_COOLDOWN))
    .addChannelOption(option => option.setName("log_channel").setDescription("Channel for custom role audit messages"))
    .addUserOption(option => option.setName("member").setDescription("Member whose custom role is being managed"))
    .addStringOption(option => option.setName("reason").setDescription("Optional reason sent to a removed member").setMaxLength(500))
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
        case "member":
        case "remove-member": {
          if (!this.requireManager(interaction)) return;
          const target = interaction.options.getUser("member");
          if (!target) {
            await interaction.reply({ content: "Choose a server member with the **member** option.", flags: MessageFlags.Ephemeral });
            return;
          }
          if (action === "member") {
            await this.showManagedMemberRole(interaction, target.id);
          } else {
            await this.promptRemoveMemberRole(interaction, target.id, interaction.options.getString("reason") ?? "");
          }
          return;
        }
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
        case "image": {
          const image = interaction.options.getAttachment("image");
          if (!image) { await interaction.reply({ content: "Attach a still PNG or JPEG with the **image** option.", flags: MessageFlags.Ephemeral }); return; }
          await this.reportResult(interaction, await this.setRoleImageIcon(interaction, image, this.cropOptions(interaction)));
          return;
        }
        case "recrop": await this.reportResult(interaction, await this.recropRoleImageIcon(interaction, this.cropOptions(interaction))); return;
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
    const [prefix, ownerId, action, resourceId] = interaction.customId.split(":");
    if (prefix !== "custom-role" || !action) return false;
    if (ownerId !== interaction.user.id) {
      await interaction.reply({ content: "This Custom Roles panel belongs to another member. Run /custom-role to open your own.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "import") {
      if (!this.requireManager(interaction) || !interaction.guild) return true;
      await this.showLegacyImportPlan(interaction);
      return true;
    }
    if (action === "legacy-cancel" && resourceId && interaction.guildId) {
      if (!this.requireManager(interaction)) return true;
      legacyImportPreviews.delete(legacyImportKey(interaction.guildId, interaction.user.id, resourceId));
      await interaction.reply({ content: "Legacy import cancelled. No roles or records were changed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "legacy-takeover" || action === "legacy-archive") {
      if (!this.requireManager(interaction) || !interaction.guild || !resourceId) return true;
      const key = legacyImportKey(interaction.guild.id, interaction.user.id, resourceId);
      const preview = legacyImportPreviews.get(key);
      if (!preview || preview.expiresAt < Date.now()) {
        legacyImportPreviews.delete(key);
        await interaction.reply({ content: "That legacy import preview expired. Open Import old roles again to recheck the data.", flags: MessageFlags.Ephemeral });
        return true;
      }
      legacyImportPreviews.delete(key);
      await this.executeLegacyImport(interaction, preview, action === "legacy-archive");
      return true;
    }
    if (action === "pending") {
      if (!this.requireManager(interaction)) return true;
      const pending = interaction.guildId ? await getPendingCustomRoleRemoval(interaction.guildId) : null;
      if (!pending) {
        await interaction.reply({ content: "There are no automatic role removals waiting for approval.", flags: MessageFlags.Ephemeral });
        return true;
      }
      await interaction.reply({
        content: "This batch contains " + pending.user_ids.length + " member(s). Confirming archives their custom roles while preserving saved settings. Cancelling keeps them and asks again in 24 hours if they remain ineligible.",
        components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
          new ButtonBuilder().setCustomId(userCustomId(interaction.user.id, "pending-confirm") + ":" + pending.id)
            .setLabel("Confirm archive").setStyle(ButtonStyle.Danger),
          new ButtonBuilder().setCustomId(userCustomId(interaction.user.id, "pending-cancel") + ":" + pending.id)
            .setLabel("Cancel and snooze").setStyle(ButtonStyle.Secondary),
        )],
        flags: MessageFlags.Ephemeral,
      });
      return true;
    }
    if (action === "pending-confirm" || action === "pending-cancel") {
      if (!this.requireManager(interaction) || !interaction.guild || !resourceId) return true;
      const result = action === "pending-confirm"
        ? await confirmCustomRolePending(interaction.guild, resourceId, interaction.user.id)
        : await cancelCustomRolePending(interaction.guild, resourceId, interaction.user.id);
      await interaction.reply({ content: result, flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "palette") { await this.showAvatarPalette(interaction); return true; }
    if (action === "palette-color" && resourceId && /^[0-9a-f]{6}$/i.test(resourceId)) {
      await this.reportResult(interaction, await this.setRoleColor(interaction, "#" + resourceId));
      return true;
    }
    if (action === "member-remove-confirm" && resourceId && interaction.guildId) {
      if (!this.requireManager(interaction) || !interaction.guild) return true;
      const key = removalRequestKey(interaction.guildId, interaction.user.id, resourceId);
      const request = memberRemovalRequests.get(key);
      if (!request || request.expiresAt < Date.now()) {
        memberRemovalRequests.delete(key);
        await interaction.reply({ content: "That removal confirmation expired. Run /custom-role again to review the member's role.", flags: MessageFlags.Ephemeral });
        return true;
      }
      memberRemovalRequests.delete(key);
      const result = await this.removeManagedMemberRole(interaction, request.targetUserId, request.reason);
      await interaction.reply({ content: result.message, flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "member-remove-cancel" && resourceId && interaction.guildId) {
      if (!this.requireManager(interaction)) return true;
      memberRemovalRequests.delete(removalRequestKey(interaction.guildId, interaction.user.id, resourceId));
      await interaction.reply({ content: "Nothing was removed.", flags: MessageFlags.Ephemeral });
      return true;
    }
    if (action === "admin") { await this.showAdminPanel(interaction); return true; }
    if (action === "words") {
      if (!this.requireManager(interaction)) return true;
      const settings = await getCustomRoleSettings(interaction.guildId!);
      await interaction.showModal(wordsModal(interaction.user.id, settings.blocked_words, settings.removed_default_words));
      return true;
    }
    if (action === "create" || action === "rename") { await interaction.showModal(nameModal(interaction.user.id, action)); return true; }
    if (action === "color") { await interaction.showModal(colorModal(interaction.user.id)); return true; }
    if (action === "gradient") { await interaction.showModal(gradientModal(interaction.user.id)); return true; }
    if (action === "holographic") { await this.reportResult(interaction, await this.setRoleStyle(interaction, "holographic")); return true; }
    if (action === "icon") { await interaction.showModal(iconModal(interaction.user.id)); return true; }
    if (action === "image") { await interaction.reply({ content: "Use `/custom-role` → **Set image icon** and attach your PNG or JPEG in the **image** option.", flags: MessageFlags.Ephemeral }); return true; }
    if (action === "recrop") { await this.reportResult(interaction, await this.recropRoleImageIcon(interaction)); return true; }
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
    if (action === "words") {
      if (!this.requireManager(interaction)) return true;
      const additions = parseCustomRoleWordList(interaction.fields.getTextInputValue("block"));
      const removals = parseCustomRoleWordList(interaction.fields.getTextInputValue("unblock"));
      if (!additions.length && !removals.length) {
        await interaction.reply({ content: "Enter at least one word to block or unblock.", flags: MessageFlags.Ephemeral });
        return true;
      }
      const outcomes: string[] = [];
      for (const word of additions) {
        const result = await addCustomRoleBlockedWord(interaction.guildId!, word);
        outcomes.push(`${result.ok ? "✓" : "·"} ${result.message}`);
      }
      for (const word of removals) {
        const result = await removeCustomRoleBlockedWord(interaction.guildId!, word);
        outcomes.push(`${result.ok ? "✓" : "·"} ${result.message}`);
      }
      const renamed = await this.sweepBlockedRoleNames(interaction.guild!);
      if (renamed) outcomes.push("Renamed " + renamed + " existing custom role(s) that no longer met the name rules.");
      await interaction.reply({
        content: "**Custom role name restrictions**\n" + outcomes.join("\n").slice(0, 1800) + "\n\nThese rules are applied to new names and edits.",
        flags: MessageFlags.Ephemeral,
      });
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

  private async showLegacyImportPlan(interaction: ButtonInteraction): Promise<void> {
    const guild = interaction.guild!;
    const settings = await getCustomRoleSettings(guild.id);
    if (!settings.enabled || !settings.anchor_role_id || !guild.roles.cache.has(settings.anchor_role_id)) {
      await interaction.reply({
        content: "Configure an anchor role and enable Custom Roles before importing legacy booster roles.",
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    const plan = await planLegacyCustomRoleImport(guild);
    const planId = randomUUID();
    const preview: LegacyImportPreview = {
      guildId: guild.id,
      actorId: interaction.user.id,
      takeOverIds: plan.take_over.map(entry => entry.user_id),
      notQualifyingIds: plan.not_qualifying.map(entry => entry.user_id),
      expiresAt: Date.now() + 10 * 60_000,
    };
    legacyImportPreviews.set(legacyImportKey(guild.id, interaction.user.id, planId), preview);

    const takeOverLines = plan.take_over.slice(0, 12).map(entry =>
      "<@" + entry.user_id + "> → " + (entry.role_name ?? entry.role_id),
    );
    const notQualifyingLines = plan.not_qualifying.slice(0, 12).map(entry =>
      "<@" + entry.user_id + "> → " + (entry.role_name ?? entry.role_id) + " (" + (entry.reason ?? "not eligible") + ")",
    );
    const skippedLines = plan.skipped.slice(0, 12).map(entry =>
      (entry.role_name ?? entry.role_id) + ": " + (entry.reason ?? "skipped"),
    );
    const embed = homeEmbed(
      "Custom Roles · Legacy import preview",
      "Read-only preview of the old booster_roles table for this server. Nothing has been changed yet. The import will recheck all selected records before acting.",
      [
        { name: "Take over existing roles", value: String(plan.take_over.length), inline: true },
        { name: "No longer eligible", value: String(plan.not_qualifying.length), inline: true },
        { name: "Skipped", value: String(plan.skipped.length), inline: true },
        { name: "Will be taken over", value: takeOverLines.join("\n").slice(0, 900) || "None", inline: false },
        { name: "No longer eligible", value: notQualifyingLines.join("\n").slice(0, 900) || "None", inline: false },
        { name: "Skipped reasons", value: skippedLines.join("\n").slice(0, 900) || "None", inline: false },
      ],
    );
    const row = new ActionRowBuilder<ButtonBuilder>();
    if (plan.take_over.length) {
      row.addComponents(new ButtonBuilder()
        .setCustomId(userCustomId(interaction.user.id, "legacy-takeover") + ":" + planId)
        .setLabel("Take over eligible roles").setStyle(ButtonStyle.Success));
    }
    if (plan.not_qualifying.length) {
      row.addComponents(new ButtonBuilder()
        .setCustomId(userCustomId(interaction.user.id, "legacy-archive") + ":" + planId)
        .setLabel("Take over + archive ineligible").setStyle(ButtonStyle.Danger));
    }
    row.addComponents(new ButtonBuilder()
      .setCustomId(userCustomId(interaction.user.id, "legacy-cancel") + ":" + planId)
      .setLabel("Cancel").setStyle(ButtonStyle.Secondary));
    await interaction.reply({ embeds: [embed], components: [row], flags: MessageFlags.Ephemeral });
  }

  private async executeLegacyImport(
    interaction: ButtonInteraction,
    preview: LegacyImportPreview,
    archiveIneligible: boolean,
  ): Promise<void> {
    const guild = interaction.guild!;
    if (preview.guildId !== guild.id || preview.actorId !== interaction.user.id) {
      await interaction.reply({ content: "That import preview belongs to another administrator or server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const settings = await getCustomRoleSettings(guild.id);
    if (!settings.enabled || !settings.anchor_role_id || !guild.roles.cache.has(settings.anchor_role_id)) {
      await interaction.reply({ content: "Custom Roles is no longer configured. Nothing was imported.", flags: MessageFlags.Ephemeral });
      return;
    }

    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
    let latest;
    try {
      latest = await planLegacyCustomRoleImport(guild);
    } catch (error) {
      await interaction.editReply(error instanceof Error ? error.message : "I couldn't revalidate the legacy role data.");
      return;
    }

    const selectedTakeOvers = latest.take_over.filter(entry => preview.takeOverIds.includes(entry.user_id));
    const selectedArchives = archiveIneligible
      ? latest.not_qualifying.filter(entry => preview.notQualifyingIds.includes(entry.user_id))
      : [];
    let takenOver = 0;
    let archived = 0;
    let skipped = 0;
    const errors: string[] = [];

    const takeOver = async (entry: { user_id: string; role_id: string; role_name: string | null }) => {
      const member = await guild.members.fetch(entry.user_id).catch(() => null);
      const role = await guild.roles.fetch(entry.role_id).catch(() => null);
      if (!member || !role) {
        skipped += 1;
        return;
      }

      const primary = role.color || 0x010101;
      const roleColors = role.colors as { primaryColor?: number; secondaryColor?: number | null; tertiaryColor?: number | null } | undefined;
      const hasSecondary = typeof roleColors?.secondaryColor === "number";
      const hasTertiary = typeof roleColors?.tertiaryColor === "number";
      const mode = hasTertiary ? "holographic" : hasSecondary ? "gradient" : "solid";
      const primaryColor = roleColors?.primaryColor ?? primary;
      const secondaryColor = hasSecondary ? roleColors?.secondaryColor ?? null : null;
      const emoji = role.unicodeEmoji ?? null;

      const previousIcon = await getCustomRoleIconData(guild.id, member.id);
      await saveCustomRole({
        guild_id: guild.id,
        user_id: member.id,
        role_id: role.id,
        position_hint: role.position,
        status: "active",
        name: role.name,
        color_mode: mode,
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        icon_emoji: emoji,
      });
      await updateCustomRole(guild.id, member.id, {
        icon_png: null,
        icon_crop: null,
        icon_source_asset_id: null,
        icon_emoji: emoji,
      });
      if (previousIcon?.icon_source_asset_id) {
        await deleteCustomRoleIconSource(previousIcon.icon_source_asset_id, guild.id).catch(() => undefined);
      }

      const iconUrl = role.iconURL({ extension: "png", size: 128 });
      if (iconUrl && (guild.features as readonly string[]).includes("ROLE_ICONS")) {
        try {
          const response = await fetch(iconUrl, { signal: AbortSignal.timeout(10_000) });
          if (response.ok) {
            const original = Buffer.from(await response.arrayBuffer());
            const processed = await processCustomRoleIconImage(original);
            const assetId = await storeCustomRoleIconSource(
              guild.id,
              member.id,
              original,
              processed.sourceType === "png" ? "image/png" : "image/jpeg",
            );
            await updateCustomRole(guild.id, member.id, {
              icon_png: processed.png,
              icon_emoji: null,
              icon_crop: JSON.stringify(processed.crop),
              icon_source_asset_id: assetId,
            });
          } else {
            errors.push("Could not preserve the image icon for " + role.name + ".");
          }
        } catch {
          errors.push("Could not preserve the image icon for " + role.name + "; the Discord role itself was left unchanged.");
        }
      }
      takenOver += 1;
    };

    for (let index = 0; index < selectedTakeOvers.length; index += 1) {
      const entry = selectedTakeOvers[index]!;
      try {
        await takeOver(entry);
      } catch (error) {
        skipped += 1;
        errors.push("Skipped " + (entry.role_name ?? entry.role_id) + ": " + (error instanceof Error ? error.message : "unknown error"));
      }
      if ((index + 1) % 5 === 0 && index + 1 < selectedTakeOvers.length) await new Promise(resolve => setTimeout(resolve, 2_000));
    }

    for (let index = 0; index < selectedArchives.length; index += 1) {
      const entry = selectedArchives[index]!;
      try {
        await takeOver(entry);
        const result = await archiveLegacyCustomRole(guild, entry.user_id, interaction.user.id);
        if (result) archived += 1;
        else skipped += 1;
      } catch (error) {
        skipped += 1;
        errors.push("Could not archive " + (entry.role_name ?? entry.role_id) + ": " + (error instanceof Error ? error.message : "unknown error"));
      }
      if ((index + 1) % 5 === 0 && index + 1 < selectedArchives.length) await new Promise(resolve => setTimeout(resolve, 2_000));
    }

    await interaction.editReply(
      "Legacy import complete. Took over " + takenOver + ", archived " + archived + ", skipped " + skipped + "." +
      (errors.length ? "\n" + errors.slice(0, 8).join("\n").slice(0, 1200) : ""),
    );
    await this.logEvent(guild, settings, "Imported legacy booster roles: took over " + takenOver + ", archived " + archived + ", skipped " + skipped + ".");
  }

  private async showManagedMemberRole(
    interaction: ChatInputCommandInteraction,
    targetId: string,
  ): Promise<void> {
    const record = await getCustomRoleRecord(interaction.guildId!, targetId);
    if (!record) {
      await interaction.reply({ content: "That member has no saved Custom Role record in this server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const member = await interaction.guild!.members.fetch(targetId).catch(() => null);
    const role = record.role_id ? await interaction.guild!.roles.fetch(record.role_id).catch(() => null) : null;
    const iconData = await getCustomRoleIconData(interaction.guildId!, targetId);
    const icon = record.icon_emoji ?? (iconData?.icon_png ? "Image icon" : "None");
    const embed = homeEmbed(
      "Custom Role · Member details",
      "Guild-local role record for " + (member ? member.user.tag : targetId) + ".",
      [
        { name: "Member", value: "<@" + targetId + ">", inline: true },
        { name: "Status", value: record.status, inline: true },
        { name: "Role", value: role ? role.name + " · <@&" + role.id + ">" : record.name ?? "No live role", inline: false },
        { name: "Color style", value: record.color_mode + " · " + colorLabel(record.primary_color), inline: true },
        { name: "Secondary color", value: colorLabel(record.secondary_color), inline: true },
        { name: "Icon", value: icon, inline: true },
        { name: "Position", value: record.position_hint === null ? "Not saved" : String(record.position_hint), inline: true },
        { name: "Last changed", value: record.last_changed_at ?? "Not recorded", inline: true },
      ],
    );
    await interaction.reply({ embeds: [embed], flags: MessageFlags.Ephemeral });
  }

  private async promptRemoveMemberRole(
    interaction: ChatInputCommandInteraction,
    targetUserId: string,
    reason: string,
  ): Promise<void> {
    const record = await getCustomRoleRecord(interaction.guildId!, targetUserId);
    if (!record) {
      await interaction.reply({ content: "That member has no saved Custom Role record in this server.", flags: MessageFlags.Ephemeral });
      return;
    }
    const role = record.role_id ? await interaction.guild!.roles.fetch(record.role_id).catch(() => null) : null;
    const key = removalRequestKey(interaction.guildId!, interaction.user.id, targetUserId);
    memberRemovalRequests.set(key, { targetUserId, reason: reason.trim().slice(0, 500), expiresAt: Date.now() + 5 * 60_000 });
    await interaction.reply({
      content: "Remove " + (role ? "**" + role.name + "**" : "the saved Custom Role") + " for <@" + targetUserId + "> and delete its saved settings? This cannot be undone. " +
        (reason.trim() ? "The member will be sent the reason by DM if their DMs are open." : "No DM will be sent."),
      components: [new ActionRowBuilder<ButtonBuilder>().addComponents(
        new ButtonBuilder().setCustomId(userCustomId(interaction.user.id, "member-remove-confirm") + ":" + targetUserId)
          .setLabel("Remove role and settings").setStyle(ButtonStyle.Danger),
        new ButtonBuilder().setCustomId(userCustomId(interaction.user.id, "member-remove-cancel") + ":" + targetUserId)
          .setLabel("Cancel").setStyle(ButtonStyle.Secondary),
      )],
      flags: MessageFlags.Ephemeral,
    });
  }

  private async removeManagedMemberRole(
    interaction: ButtonInteraction,
    targetUserId: string,
    reason: string,
  ): Promise<{ ok: boolean; message: string }> {
    const guild = interaction.guild!;
    const record = await getCustomRoleRecord(guild.id, targetUserId);
    if (!record) return { ok: false, message: "That member's Custom Role record was already removed." };
    const role = record.role_id ? await guild.roles.fetch(record.role_id).catch(() => null) : null;
    if (role) {
      const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
      if (!botMember?.permissions.has(PermissionFlagsBits.ManageRoles)) {
        return { ok: false, message: "I need Manage Roles to remove that role. No record was changed." };
      }
      if (role.position >= botMember.roles.highest.position || role.managed || role.id === guild.id) {
        return { ok: false, message: "That role is managed or at/above my highest role. Nothing was changed." };
      }
      try {
        await role.delete("Custom Roles: removed by " + interaction.user.id + (reason ? " · " + reason : ""));
      } catch (error) {
        return { ok: false, message: error instanceof Error ? "Discord refused to delete the role: " + error.message : "Discord refused to delete that role. Nothing was changed." };
      }
    }
    const deleted = await deleteCustomRoleRecord(guild.id, targetUserId);
    if (!deleted) return { ok: false, message: "The Discord role was removed, but the database record could not be deleted. Check the role record before retrying." };
    if (deleted.icon_source_asset_id) {
      await deleteCustomRoleIconSource(deleted.icon_source_asset_id, guild.id).catch(() => undefined);
    }
    await clearCustomRoleSnoozes(guild.id, [targetUserId]);
    await removeCustomRolePendingUser(guild.id, targetUserId, interaction.user.id);
    const settings = await getCustomRoleSettings(guild.id);
    await this.logEvent(guild, settings, "<@" + interaction.user.id + "> removed <@" + targetUserId + ">'s Custom Role and saved settings.");
    if (reason) {
      const member = await guild.members.fetch(targetUserId).catch(() => null);
      if (member) {
        await member.send({ content: "Your Custom Role in **" + guild.name + "** was removed by a server administrator.\nReason: " + reason }).catch(() => undefined);
      }
    }
    return { ok: true, message: "Removed <@" + targetUserId + ">'s role and saved settings." };
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
        { name: "Additional blocked words", value: settings.blocked_words.join(", ").slice(0, 900) || "None", inline: false },
        { name: "Disabled built-in protections", value: settings.removed_default_words.join(", ").slice(0, 900) || "None", inline: false },
        { name: "Removal approval", value: (await getPendingCustomRoleRemoval(interaction.guildId!))?.user_ids.length.toString() ?? "None pending", inline: true },
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
      const savedIcon = roleIcons ? await getCustomRoleIconData(member.guild.id, member.id) : null;
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
        ...(savedIcon?.icon_png ? { icon: savedIcon.icon_png } : roleIcons && existing?.icon_emoji ? { unicodeEmoji: existing.icon_emoji } : {}),
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

  private async showAvatarPalette(interaction: ButtonInteraction): Promise<void> {
    const context = await this.memberContext(interaction);
    if ("error" in context) {
      await interaction.reply({ content: context.error, flags: MessageFlags.Ephemeral });
      return;
    }
    const { member } = context;
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id || !member.guild.roles.cache.has(record.role_id)) {
      await interaction.reply({ content: "Create a custom role before choosing a palette color.", flags: MessageFlags.Ephemeral });
      return;
    }
    try {
      const avatarUrl = member.displayAvatarURL({ extension: "png", size: 128 });
      const response = await fetch(avatarUrl, { signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error("Discord could not provide your avatar.");
      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.byteLength > 2 * 1024 * 1024) throw new Error("That avatar is too large to analyze safely.");
      const colors = await extractCustomRoleAvatarPalette(bytes, 10);
      if (!colors.length) throw new Error("I couldn't find enough visible colors in that avatar.");
      const rows: ActionRowBuilder<ButtonBuilder>[] = [];
      for (let index = 0; index < colors.length; index += 5) {
        const row = new ActionRowBuilder<ButtonBuilder>();
        for (const color of colors.slice(index, index + 5)) {
          const hex = color.toString(16).padStart(6, "0").toUpperCase();
          row.addComponents(new ButtonBuilder()
            .setCustomId(userCustomId(interaction.user.id, "palette-color") + ":" + hex.toLowerCase())
            .setLabel("#" + hex)
            .setStyle(ButtonStyle.Secondary));
        }
        rows.push(row);
      }
      const embed = homeEmbed(
        "Custom role · Avatar palette",
        "Choose one color sampled from your current server avatar. Applying it uses the same role-change cooldown as a manual color.",
        colors.slice(0, 10).map(color => ({
          name: "#" + color.toString(16).padStart(6, "0").toUpperCase(),
          value: "Extracted from your avatar",
          inline: true,
        })),
      );
      await interaction.reply({ embeds: [embed], components: rows, flags: MessageFlags.Ephemeral });
    } catch (error) {
      await interaction.reply({
        content: error instanceof Error ? error.message : "I couldn't extract a palette from your avatar.",
        flags: MessageFlags.Ephemeral,
      });
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

  private cropOptions(interaction: ChatInputCommandInteraction): CustomRoleIconCrop | undefined {
    const x = interaction.options.getInteger("crop_x");
    const y = interaction.options.getInteger("crop_y");
    const size = interaction.options.getInteger("crop_size");
    if (x === null && y === null && size === null) return undefined;
    if (x === null || y === null || size === null) {
      throw new Error("Supply crop_x, crop_y and crop_size together, or leave all three blank for a centre crop.");
    }
    return { x, y, size };
  }

  private async setRoleImageIcon(
    interaction: GuildInteraction,
    attachment: Attachment,
    crop?: CustomRoleIconCrop,
  ): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    if (!(member.guild.features as readonly string[]).includes("ROLE_ICONS")) {
      return { ok: false, message: "Image role icons need Discord's Role Icons server feature (Boost Level 2). You can still use a Unicode emoji icon." };
    }
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before setting its image icon." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    const maxBytes = Math.max(256 * 1024, Number(process.env.CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES || 8 * 1024 * 1024));
    if (attachment.size > maxBytes) return { ok: false, message: "That image is too large. The original upload limit is " + Math.ceil(maxBytes / (1024 * 1024)) + " MB." };

    let original: Buffer;
    try {
      const response = await fetch(attachment.url, { signal: AbortSignal.timeout(15_000) });
      if (!response.ok) return { ok: false, message: "Discord could not provide that attachment. Please upload it again." };
      original = Buffer.from(await response.arrayBuffer());
    } catch {
      return { ok: false, message: "I couldn't download that image from Discord. Please upload it again." };
    }
    const processed = await processCustomRoleIconImage(original, crop);
    const contentType = processed.sourceType === "png" ? "image/png" : "image/jpeg";
    const oldIcon = await getCustomRoleIconData(member.guild.id, member.id);
    let assetId: number | null = null;
    try {
      assetId = await storeCustomRoleIconSource(member.guild.id, member.id, original, contentType);
      await role.edit({ icon: processed.png, unicodeEmoji: null, reason: "Custom Roles: member uploaded an image icon" });
      await updateCustomRole(member.guild.id, member.id, {
        icon_png: processed.png,
        icon_emoji: null,
        icon_crop: JSON.stringify(processed.crop),
        icon_source_asset_id: assetId,
      }, true);
      if (oldIcon?.icon_source_asset_id && oldIcon.icon_source_asset_id !== assetId) {
        try {
          await deleteCustomRoleIconSource(oldIcon.icon_source_asset_id, member.guild.id);
        } catch {
          await this.logEvent(member.guild, settings, "A replaced custom role source image could not be deleted from private storage.");
        }
      }
      await this.logEvent(member.guild, settings, "<@!" + member.id + "> changed their custom role image icon.");
      return { ok: true, message: "Your image icon has been applied. The original stays in private storage so you can crop it again later." };
    } catch (error) {
      if (assetId) await deleteCustomRoleIconSource(assetId, member.guild.id).catch(() => undefined);
      if (oldIcon?.icon_png) {
        await role.edit({ icon: oldIcon.icon_png, unicodeEmoji: null, reason: "Custom Roles: roll back failed icon save" }).catch(() => undefined);
      } else if (record.icon_emoji) {
        await role.edit({ icon: null, unicodeEmoji: record.icon_emoji, reason: "Custom Roles: roll back failed icon save" }).catch(() => undefined);
      } else {
        await role.edit({ icon: null, unicodeEmoji: null, reason: "Custom Roles: roll back failed icon save" }).catch(() => undefined);
      }
      return { ok: false, message: error instanceof Error ? "I couldn't apply that image icon: " + error.message : "I couldn't apply that image icon." };
    }
  }

  private async recropRoleImageIcon(
    interaction: GuildInteraction,
    crop?: CustomRoleIconCrop,
  ): Promise<{ ok: boolean; message: string }> {
    const context = await this.memberContext(interaction);
    if ("error" in context) return { ok: false, message: context.error };
    const { member, settings } = context;
    if (!(member.guild.features as readonly string[]).includes("ROLE_ICONS")) {
      return { ok: false, message: "Image role icons need Discord's Role Icons server feature (Boost Level 2)." };
    }
    const record = await getCustomRoleRecord(member.guild.id, member.id);
    if (!record?.role_id) return { ok: false, message: "Create a custom role before recropping its icon." };
    const role = member.guild.roles.cache.get(record.role_id);
    if (!role) return { ok: false, message: "Your saved role no longer exists. Use Create role to restore it." };
    const cooldown = customRoleCooldownMessage(record, settings.cooldown_seconds);
    if (cooldown) return { ok: false, message: cooldown };
    const current = await getCustomRoleIconData(member.guild.id, member.id);
    if (!current?.icon_source_asset_id) return { ok: false, message: "There is no saved original image to crop. Upload a new image icon first." };
    const original = await readCustomRoleIconSource(current.icon_source_asset_id, member.guild.id);
    if (!original) return { ok: false, message: "The private original image is missing. Upload a new image icon to replace it." };
    let savedCrop: CustomRoleIconCrop | undefined;
    try {
      if (current.icon_crop) savedCrop = JSON.parse(current.icon_crop) as CustomRoleIconCrop;
    } catch {
      savedCrop = undefined;
    }
    const processed = await processCustomRoleIconImage(original, crop ?? savedCrop);
    try {
      await role.edit({ icon: processed.png, unicodeEmoji: null, reason: "Custom Roles: member recropped their image icon" });
      await updateCustomRole(member.guild.id, member.id, {
        icon_png: processed.png,
        icon_emoji: null,
        icon_crop: JSON.stringify(processed.crop),
      }, true);
      await this.logEvent(member.guild, settings, "<@!" + member.id + "> recropped their custom role image icon.");
      return { ok: true, message: "Your custom role image icon has been recropped." };
    } catch (error) {
      return { ok: false, message: error instanceof Error ? "I couldn't recrop that image: " + error.message : "I couldn't recrop that image." };
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
      const oldIcon = await getCustomRoleIconData(member.guild.id, member.id);
      await role.edit({ icon: null, unicodeEmoji: emoji, reason: "Custom Roles: member changed role icon" });
      await updateCustomRole(member.guild.id, member.id, { icon_emoji: emoji, icon_png: null, icon_crop: null, icon_source_asset_id: null }, true);
      if (oldIcon?.icon_source_asset_id) await deleteCustomRoleIconSource(oldIcon.icon_source_asset_id, member.guild.id).catch(() => undefined);
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

  private async sweepBlockedRoleNames(guild: Guild): Promise<number> {
    const settings = await getCustomRoleSettings(guild.id);
    const records = await listCustomRoleRecords(guild.id);
    const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
    if (!botMember?.permissions.has(PermissionFlagsBits.ManageRoles)) return 0;
    const roles = [...guild.roles.cache.values()];
    let renamed = 0;
    for (const record of records) {
      if (record.status !== "active" || !record.role_id) continue;
      const role = guild.roles.cache.get(record.role_id);
      if (!role || role.position >= botMember.roles.highest.position) continue;
      const peers = roles.filter(item => item.id !== role.id);
      const reserved = peers.filter(item => !item.managed).map(item => item.name);
      const protectedNames = protectedRoleNames(peers.filter(item =>
        item.permissions.has(PermissionFlagsBits.Administrator)
        || item.permissions.has(PermissionFlagsBits.ManageGuild)
        || item.permissions.has(PermissionFlagsBits.ManageRoles)
        || item.permissions.has(PermissionFlagsBits.ManageMessages)
        || item.permissions.has(PermissionFlagsBits.KickMembers)
        || item.permissions.has(PermissionFlagsBits.BanMembers)
        || item.permissions.has(PermissionFlagsBits.ModerateMembers),
      ));
      if (!validateCustomRoleName(role.name, settings, reserved, protectedNames).error) continue;
      const fallback = "Member Role " + record.user_id.slice(-6);
      const validFallback = validateCustomRoleName(fallback, settings, reserved, protectedNames);
      if (!validFallback.name || validFallback.error) continue;
      await role.edit({ name: validFallback.name, reason: "Custom Roles: updated name restrictions" });
      await updateCustomRole(guild.id, record.user_id, { name: validFallback.name });
      renamed += 1;
    }
    if (renamed) await this.logEvent(guild, settings, "Renamed " + renamed + " custom role(s) after an administrator changed blocked-word rules.");
    return renamed;
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

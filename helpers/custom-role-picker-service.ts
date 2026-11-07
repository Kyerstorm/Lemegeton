import {
  PermissionFlagsBits,
  type Guild,
  type GuildMember,
  type Role,
} from "discord.js";
import type { BotConfig } from "./config.js";
import { logger } from "./logger.js";
import {
  customRoleCooldownMessage,
  customRoleEligibility,
  getCustomRoleIconData,
  getCustomRoleRecord,
  getCustomRoleSettings,
  markCustomRoleMissing,
  HOLOGRAPHIC_COLORS,
  parseCustomRoleColor,
  updateCustomRole,
  validateCustomRoleEmoji,
  validateCustomRoleName,
} from "./custom-roles.js";
import {
  deleteCustomRoleIconSource,
  readCustomRoleIconSource,
  storeCustomRoleIconSource,
} from "./media-storage.js";
import {
  extractCustomRoleAvatarPalette,
  processCustomRoleIconImage,
  type CustomRoleIconCrop,
} from "./custom-role-images.js";
import { restoreCustomRoleForMember } from "./custom-role-lifecycle.js";

export interface PickerContext {
  guild: Guild;
  member: GuildMember;
  role: Role | null;
  record: NonNullable<Awaited<ReturnType<typeof getCustomRoleRecord>>>;
  settings: Awaited<ReturnType<typeof getCustomRoleSettings>>;
  iconData: Awaited<ReturnType<typeof getCustomRoleIconData>>;
}

export interface PickerResult {
  ok: boolean;
  message: string;
  notes?: string[];
}

export function pickerImageContentType(bytes: Buffer): "image/png" | "image/jpeg" | null {
  if (bytes.length >= 8 && bytes.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return "image/png";
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  return null;
}

function asDataUrl(bytes: Buffer): string {
  const type = pickerImageContentType(bytes);
  if (!type) return "";
  return "data:" + type + ";base64," + bytes.toString("base64");
}

function colorHex(color: number | null): string | null {
  return color === null ? null : "#" + color.toString(16).padStart(6, "0").toUpperCase();
}

function protectedRoleNames(roles: Iterable<Role>): string[] {
  const permissions = [
    PermissionFlagsBits.Administrator,
    PermissionFlagsBits.ManageGuild,
    PermissionFlagsBits.ManageMessages,
    PermissionFlagsBits.ManageRoles,
    PermissionFlagsBits.KickMembers,
    PermissionFlagsBits.BanMembers,
    PermissionFlagsBits.ModerateMembers,
  ];
  return [...roles].filter(role => permissions.some(permission => role.permissions.has(permission))).map(role => role.name);
}

export async function resolvePickerContext(guild: Guild, userId: string): Promise<PickerContext> {
  const member = await guild.members.fetch({ user: userId, force: true }).catch(() => null);
  if (!member) throw new Error("You're no longer in this server.");

  const settings = await getCustomRoleSettings(guild.id);
  if (!settings.enabled || !settings.anchor_role_id) throw new Error("Custom Roles are not configured in this server.");
  const anchor = await guild.roles.fetch(settings.anchor_role_id).catch(() => null);
  const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
  if (!anchor || !botMember || !botMember.permissions.has(PermissionFlagsBits.ManageRoles)
    || anchor.position >= botMember.roles.highest.position) {
    throw new Error("The Custom Roles anchor or bot role hierarchy needs administrator attention.");
  }
  if (!customRoleEligibility(member, settings)) {
    throw new Error("Custom Roles are for server boosters and members with an administrator-approved allowed role.");
  }

  let record = await getCustomRoleRecord(guild.id, member.id);
  if (!record) throw new Error("Create a custom role before opening the Color picker.");
  let role = record.role_id ? await guild.roles.fetch(record.role_id).catch(() => null) : null;
  if (!role && record.role_id) {
    await markCustomRoleMissing(guild.id, member.id, record.role_id);
    record = await getCustomRoleRecord(guild.id, member.id);
  }
  if (!role && record && (record.status === "missing" || record.status === "saved")) {
    await restoreCustomRoleForMember(member);
    record = await getCustomRoleRecord(guild.id, member.id);
    role = record?.role_id ? await guild.roles.fetch(record.role_id).catch(() => null) : null;
  }
  if (!record) throw new Error("Your custom role record is missing. Reopen /custom-role and create your role again.");
  if (role && (role.managed || role.id === guild.id || role.position >= botMember.roles.highest.position)) {
    throw new Error("I can't safely edit that role because of Discord's role hierarchy.");
  }
  if (!role && record.role_id) throw new Error("Your custom role is missing. Reopen /custom-role to restore it.");

  return {
    guild,
    member,
    role,
    record,
    settings,
    iconData: await getCustomRoleIconData(guild.id, member.id),
  };
}

async function avatarDataUrl(member: GuildMember): Promise<string | null> {
  const url = member.displayAvatarURL({ extension: "png", size: 128 });
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000), redirect: "error" });
    if (!response.ok) return null;
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!bytes.length || bytes.length > 2 * 1024 * 1024 || !pickerImageContentType(bytes)) return null;
    return asDataUrl(bytes);
  } catch {
    return null;
  }
}

export async function buildPickerState(
  context: PickerContext,
  config: BotConfig,
): Promise<Record<string, unknown>> {
  const { guild, member, role, record, settings, iconData } = context;
  let icon: Record<string, unknown> | null = null;
  const iconPng = iconData?.icon_png ?? record.icon_png ?? null;
  if (record.icon_emoji) {
    icon = { type: "emoji", value: record.icon_emoji };
  } else if (iconPng) {
    icon = { type: "image", url: asDataUrl(iconPng) };
  } else if (role?.unicodeEmoji) {
    icon = { type: "emoji", value: role.unicodeEmoji };
  }
  if (icon?.type === "image") {
    icon.has_source = Boolean(iconData?.icon_source_asset_id || iconPng);
    try {
      icon.crop = record.icon_crop ? JSON.parse(record.icon_crop) as Record<string, number> : null;
    } catch {
      icon.crop = null;
    }
  }

  const changedAt = record.last_changed_at ? new Date(record.last_changed_at).getTime() : Number.NaN;
  const nextChangeAt = Number.isFinite(changedAt) && settings.cooldown_seconds > 0
    ? Math.floor(changedAt / 1000) + settings.cooldown_seconds
    : null;
  const enhanced = guild.features.includes("ENHANCED_ROLE_COLORS");
  const icons = guild.features.includes("ROLE_ICONS");

  return {
    user: {
      id: member.id,
      name: member.displayName,
      avatar_url: await avatarDataUrl(member),
    },
    guild: {
      id: guild.id,
      name: guild.name,
      gradient: enhanced,
      icons,
      preview_enhanced: process.env.CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS === "true" && !enhanced,
      preview_icons: process.env.CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS === "true" && !icons,
    },
    role: {
      name: role?.name ?? record.name,
      status: record.status,
      mode: record.color_mode,
      primary: colorHex(record.primary_color),
      secondary: record.color_mode !== "solid" ? colorHex(record.secondary_color) : null,
      icon,
    },
    cooldown_seconds: settings.cooldown_seconds,
    next_change_at: nextChangeAt,
    name_max: 100,
    icon_source_max: config.customRoleIconSourceMaxBytes,
  };
}

export async function pickerSetName(context: PickerContext, rawName: unknown): Promise<PickerResult> {
  if (!context.role) return { ok: false, message: "Your custom role is missing. Reopen /custom-role to restore it." };
  if (typeof rawName !== "string" || rawName.length > 400) return { ok: false, message: "Role names can be at most 100 characters." };

  const roles = await context.guild.roles.fetch();
  const peers = [...roles.values()].filter(role => !role.managed && role.id !== context.role!.id);
  const checked = validateCustomRoleName(rawName, context.settings, peers.map(role => role.name), protectedRoleNames(peers));
  if (checked.error || !checked.name) return { ok: false, message: checked.error ?? "Choose a valid role name." };
  const waiting = cooldownMessage(context);
  if (waiting) return { ok: false, message: waiting };

  try {
    await context.role.edit({ name: checked.name, reason: "Custom Roles: member changed name in the web picker" });
    await updateCustomRole(context.guild.id, context.member.id, { name: checked.name }, true);
    return { ok: true, message: "Your role is now called **" + checked.name + "**." };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? "I couldn't rename your role: " + error.message : "I couldn't rename your role." };
  }
}

export async function pickerSetColor(
  context: PickerContext,
  body: Record<string, unknown>,
): Promise<PickerResult> {
  if (!context.role) return { ok: false, message: "Your custom role is missing. Reopen /custom-role to restore it." };
  const mode = body.mode;
  if (mode !== "solid" && mode !== "gradient" && mode !== "holographic") {
    return { ok: false, message: "Pick Solid, Gradient or Holographic." };
  }
  const enhanced = context.guild.features.includes("ENHANCED_ROLE_COLORS");
  if (mode !== "solid" && !enhanced) {
    return { ok: false, message: "Gradient and Holographic styles need Discord's Enhanced Role Styles feature (3 server boosts). Solid colors still work." };
  }
  const primary = mode === "holographic" ? HOLOGRAPHIC_COLORS[0] : parseCustomRoleColor(String(body.primary ?? ""));
  const secondary = mode === "holographic" ? HOLOGRAPHIC_COLORS[1]
    : mode === "gradient" ? parseCustomRoleColor(String(body.secondary ?? "")) : null;
  if (primary === null || (mode === "gradient" && secondary === null)) {
    return { ok: false, message: mode === "gradient" ? "Pick two valid hex colors." : "Pick a valid hex color." };
  }
  const waiting = cooldownMessage(context);
  if (waiting) return { ok: false, message: waiting };
  const colors = mode === "holographic"
    ? { primaryColor: HOLOGRAPHIC_COLORS[0], secondaryColor: HOLOGRAPHIC_COLORS[1], tertiaryColor: HOLOGRAPHIC_COLORS[2] }
    : mode === "gradient"
      ? { primaryColor: primary, secondaryColor: secondary, tertiaryColor: null }
      : { primaryColor: primary, secondaryColor: null, tertiaryColor: null };

  try {
    await context.role.edit({ colors, reason: "Custom Roles: member changed colors in the web picker" });
    await updateCustomRole(context.guild.id, context.member.id, {
      color_mode: mode,
      primary_color: primary,
      secondary_color: secondary,
    }, true);
    return {
      ok: true,
      message: mode === "holographic" ? "Your role is now holographic."
        : mode === "gradient" ? "Your role is now a gradient from " + colorHex(primary) + " to " + colorHex(secondary) + "."
          : "Your role color is now " + colorHex(primary) + ".",
    };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? "I couldn't change your role color: " + error.message : "I couldn't change your role color." };
  }
}

export async function pickerSetEmoji(context: PickerContext, rawEmoji: unknown): Promise<PickerResult> {
  if (!context.role) return { ok: false, message: "Your custom role is missing. Reopen /custom-role to restore it." };
  const emoji = typeof rawEmoji === "string" ? validateCustomRoleEmoji(rawEmoji) : null;
  if (!emoji) return { ok: false, message: "Send one standard Unicode emoji, not a custom server emoji or shortcode." };
  if (!context.guild.features.includes("ROLE_ICONS")) {
    return { ok: false, message: "Role icons need Discord's Role Icons server feature (Boost Level 2)." };
  }
  const waiting = cooldownMessage(context);
  if (waiting) return { ok: false, message: waiting };

  try {
    await context.role.edit({ icon: null, unicodeEmoji: emoji, reason: "Custom Roles: member changed role icon in web picker" });
    await updateCustomRole(context.guild.id, context.member.id, {
      icon_emoji: emoji,
      icon_png: null,
      icon_crop: null,
      icon_source_asset_id: null,
    }, true);
    if (context.iconData?.icon_source_asset_id) {
      await deleteCustomRoleIconSource(context.iconData.icon_source_asset_id, context.guild.id).catch(() => undefined);
    }
    return { ok: true, message: "Your role icon is now " + emoji + "." };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? "I couldn't set that role icon: " + error.message : "I couldn't set that role icon." };
  }
}

export async function pickerSetImage(
  context: PickerContext,
  original: Buffer,
  crop?: CustomRoleIconCrop,
): Promise<PickerResult> {
  if (!context.role) return { ok: false, message: "Your custom role is missing. Reopen /custom-role to restore it." };
  if (!context.guild.features.includes("ROLE_ICONS")) {
    return { ok: false, message: "Image role icons need Discord's Role Icons server feature (Boost Level 2)." };
  }
  const waiting = cooldownMessage(context);
  if (waiting) return { ok: false, message: waiting };
  const processed = await processCustomRoleIconImage(original, crop);
  let assetId: number | null = null;
  try {
    assetId = await storeCustomRoleIconSource(
      context.guild.id,
      context.member.id,
      original,
      processed.sourceType === "png" ? "image/png" : "image/jpeg",
    );
    await context.role.edit({ icon: processed.png, unicodeEmoji: null, reason: "Custom Roles: member changed image icon in web picker" });
    await updateCustomRole(context.guild.id, context.member.id, {
      icon_emoji: null,
      icon_png: processed.png,
      icon_crop: JSON.stringify(processed.crop),
      icon_source_asset_id: assetId,
    }, true);
    if (context.iconData?.icon_source_asset_id && context.iconData.icon_source_asset_id !== assetId) {
      await deleteCustomRoleIconSource(context.iconData.icon_source_asset_id, context.guild.id).catch(() => undefined);
    }
    return { ok: true, message: "Your role image icon was updated (" + processed.side + "x" + processed.side + ")." };
  } catch (error) {
    if (assetId) await deleteCustomRoleIconSource(assetId, context.guild.id).catch(() => undefined);
    if (context.iconData?.icon_png) {
      await context.role.edit({ icon: context.iconData.icon_png, unicodeEmoji: null, reason: "Custom Roles: restore previous role icon" }).catch(() => undefined);
    } else if (context.record.icon_emoji) {
      await context.role.edit({ icon: null, unicodeEmoji: context.record.icon_emoji, reason: "Custom Roles: restore previous role emoji" }).catch(() => undefined);
    } else {
      await context.role.edit({ icon: null, unicodeEmoji: null, reason: "Custom Roles: clear failed role icon" }).catch(() => undefined);
    }
    return { ok: false, message: error instanceof Error ? "I couldn't apply that image icon: " + error.message : "I couldn't apply that image icon." };
  }
}

export async function pickerRemoveIcon(context: PickerContext): Promise<PickerResult> {
  if (!context.role) return { ok: false, message: "Your custom role is missing. Reopen /custom-role to restore it." };
  const existing = Boolean(context.iconData?.icon_png || context.record.icon_emoji || context.role.unicodeEmoji || context.role.icon);
  if (!existing) return { ok: false, message: "Your role doesn't have an icon to remove." };
  const waiting = cooldownMessage(context);
  if (waiting) return { ok: false, message: waiting };
  try {
    await context.role.edit({ icon: null, unicodeEmoji: null, reason: "Custom Roles: member removed role icon in web picker" });
    await updateCustomRole(context.guild.id, context.member.id, {
      icon_emoji: null,
      icon_png: null,
      icon_crop: null,
      icon_source_asset_id: null,
    }, true);
    if (context.iconData?.icon_source_asset_id) {
      await deleteCustomRoleIconSource(context.iconData.icon_source_asset_id, context.guild.id).catch(() => undefined);
    }
    return { ok: true, message: "Your role icon was removed." };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? "I couldn't remove that role icon: " + error.message : "I couldn't remove that role icon." };
  }
}

export async function pickerIconSource(context: PickerContext): Promise<Buffer | null> {
  if (context.iconData?.icon_source_asset_id) {
    return readCustomRoleIconSource(context.iconData.icon_source_asset_id, context.guild.id);
  }
  return context.iconData?.icon_png ?? null;
}

export async function pickerPalette(context: PickerContext): Promise<number[]> {
  const url = context.member.displayAvatarURL({ extension: "png", size: 128 });
  const response = await fetch(url, { signal: AbortSignal.timeout(10_000), redirect: "error" });
  if (!response.ok) throw new Error("I couldn't download your avatar right now. Please try again.");
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!bytes.length || bytes.length > 2 * 1024 * 1024 || !pickerImageContentType(bytes)) {
    throw new Error("I couldn't read colors from your avatar.");
  }
  const colors = await extractCustomRoleAvatarPalette(bytes);
  if (!colors.length) throw new Error("I couldn't find any colors in your avatar.");
  return colors;
}

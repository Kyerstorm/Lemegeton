import { type Guild, type GuildMember } from "discord.js";
import { logger } from "./logger.js";
import {
  HOLOGRAPHIC_COLORS,
  clearCustomRoleSnoozes,
  createCustomRolePending,
  customRoleEligibility,
  customRoleSnoozedUsers,
  getCustomRoleRecord,
  getCustomRoleSettings,
  getOpenCustomRolePending,
  listCustomRoleRecords,
  markCustomRoleMissing,
  resolveCustomRolePending,
  saveCustomRole,
  snoozeCustomRoleUsers,
  updateCustomRole,
  updateCustomRolePendingUsers,
} from "./custom-roles.js";

const EVENT_BATCH_MS = 10_000;
const SNOOZE_HOURS = 24;
const RECENT_WINDOW_MS = 10 * 60_000;
type ArchiveReason = { userId: string; reason: string };

const queues = new Map<string, Map<string, string>>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const recentArchives = new Map<string, number[]>();
const locks = new Map<string, Promise<void>>();

async function withLock<T>(guildId: string, userId: string, work: () => Promise<T>): Promise<T> {
  const key = guildId + ":" + userId;
  const prior = locks.get(key) ?? Promise.resolve();
  let release!: () => void;
  const current = new Promise<void>(resolve => { release = resolve; });
  const chain = prior.then(() => current);
  locks.set(key, chain);
  await prior;
  try {
    return await work();
  } finally {
    release();
    if (locks.get(key) === chain) locks.delete(key);
  }
}

function isMissing(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { code?: number | string; status?: number };
  return Number(value.code) === 10007 || Number(value.code) === 10011 || value.status === 404;
}

async function memberOrNull(guild: Guild, userId: string): Promise<GuildMember | null> {
  try {
    return await guild.members.fetch({ user: userId, force: true });
  } catch (error) {
    if (Number((error as { code?: number } | null)?.code) === 10007 || (error as { status?: number } | null)?.status === 404) {
      return null;
    }
    throw error;
  }
}

function archiveThreshold(): number {
  const value = Number(process.env.CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD ?? 10);
  return Number.isSafeInteger(value) && value >= 0 ? value : 10;
}

function recentCount(guildId: string): number {
  const cutoff = Date.now() - RECENT_WINDOW_MS;
  const values = (recentArchives.get(guildId) ?? []).filter(value => value > cutoff);
  recentArchives.set(guildId, values);
  return values.length;
}

function noteArchives(guildId: string, count: number): void {
  const now = Date.now();
  const values = (recentArchives.get(guildId) ?? []).filter(value => value > now - RECENT_WINDOW_MS);
  for (let i = 0; i < count; i += 1) values.push(now);
  recentArchives.set(guildId, values);
}

async function audit(guild: Guild, message: string): Promise<void> {
  const settings = await getCustomRoleSettings(guild.id).catch(() => null);
  if (!settings?.log_channel_id) return;
  const channel = await guild.channels.fetch(settings.log_channel_id).catch(() => null);
  if (!channel?.isTextBased() || !("send" in channel)) return;
  await channel.send({ content: message, allowedMentions: { parse: [] } }).catch(error => {
    logger.warn("Could not post Custom Roles lifecycle log", {
      guildId: guild.id,
      reason: error instanceof Error ? error.message : "Unknown error",
    });
  });
}

async function archiveOne(guild: Guild, userId: string, reason: string): Promise<boolean> {
  return withLock(guild.id, userId, async () => {
    const settings = await getCustomRoleSettings(guild.id);
    if (!settings.enabled) return false;
    const member = await memberOrNull(guild, userId);
    if (member && customRoleEligibility(member, settings)) return false;

    const record = await getCustomRoleRecord(guild.id, userId);
    if (!record || (record.status !== "active" && record.status !== "missing")) return false;
    const role = record.role_id
      ? await guild.roles.fetch(record.role_id).catch(error => {
          if (isMissing(error)) return null;
          throw error;
        })
      : null;

    if (role) {
      const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
      if (!botMember || !botMember.permissions.has("ManageRoles")
        || role.position >= botMember.roles.highest.position) {
        logger.warn("Skipped Custom Role archive because role hierarchy or permissions are unsafe", {
          guildId: guild.id, userId, roleId: role.id,
        });
        return false;
      }
      await role.delete("Custom Roles: archived after eligibility was lost");
      await updateCustomRole(guild.id, userId, {
        role_id: null, status: "saved", name: role.name, position_hint: role.position,
      });
    } else {
      await updateCustomRole(guild.id, userId, { role_id: null, status: "saved" });
    }

    logger.info("Archived ineligible Custom Role", { guildId: guild.id, userId, reason });
    await audit(guild, "Archived the saved Custom Role for <@" + userId + "> (" + reason + ").");
    return true;
  });
}

async function postPending(guild: Guild, userIds: string[], reason: string): Promise<void> {
  await audit(
    guild,
    "Custom Roles paused " + userIds.length + " automatic removal(s) because the safety threshold (" +
      archiveThreshold() + ") was reached. Reason: " + reason +
      ". An administrator must open /custom-role → Admin settings → Pending removal to confirm or cancel.",
  );
}

async function holdForApproval(guild: Guild, candidates: ArchiveReason[], reason: string): Promise<void> {
  const existing = await getOpenCustomRolePending(guild.id);
  const ids = [...new Set(candidates.map(item => item.userId))];
  if (existing) {
    const merged = [...new Set([...existing.user_ids, ...ids])];
    if (merged.length !== existing.user_ids.length) {
      await updateCustomRolePendingUsers(existing.id, merged);
      await postPending(guild, merged, reason);
    }
    return;
  }
  const pending = await createCustomRolePending(guild.id, ids, reason);
  await postPending(guild, pending.user_ids, reason);
}

async function archiveAutomatically(guild: Guild, reasons: ArchiveReason[]): Promise<void> {
  const settings = await getCustomRoleSettings(guild.id);
  if (!settings.enabled || !reasons.length) return;
  const pending = await getOpenCustomRolePending(guild.id);
  const snoozes = await customRoleSnoozedUsers(guild.id);
  const eligibleLosses: ArchiveReason[] = [];

  for (const item of reasons) {
    if (pending?.user_ids.includes(item.userId) || snoozes.active.has(item.userId)) continue;
    const member = await memberOrNull(guild, item.userId);
    if (member && customRoleEligibility(member, settings)) continue;
    const record = await getCustomRoleRecord(guild.id, item.userId);
    if (record && (record.status === "active" || record.status === "missing")) eligibleLosses.push(item);
  }
  if (!eligibleLosses.length) return;

  const expired = eligibleLosses.filter(item => snoozes.expired.has(item.userId));
  const ordinary = eligibleLosses.filter(item => !snoozes.expired.has(item.userId));
  const mustAsk = Boolean(pending) || recentCount(guild.id) + ordinary.length > archiveThreshold();
  const ask = [...expired, ...(mustAsk ? ordinary : [])];
  const immediate = ordinary.filter(item => !ask.some(held => held.userId === item.userId));

  if (ask.length) {
    await clearCustomRoleSnoozes(guild.id, ask.map(item => item.userId));
    await holdForApproval(guild, ask, reasons.length > 1 ? "members stopped qualifying" : reasons[0]?.reason ?? "eligibility changed");
  }

  let archived = 0;
  for (let index = 0; index < immediate.length; index += 1) {
    const item = immediate[index]!;
    if (await archiveOne(guild, item.userId, item.reason)) archived += 1;
    if ((index + 1) % 5 === 0 && index + 1 < immediate.length) {
      await new Promise(resolve => setTimeout(resolve, 2_000));
    }
  }
  if (archived) noteArchives(guild.id, archived);
}

export async function getPendingCustomRoleRemoval(guildId: string) {
  return getOpenCustomRolePending(guildId);
}

export async function confirmCustomRolePending(guild: Guild, pendingId: string, actorId: string): Promise<string> {
  const pending = await getOpenCustomRolePending(guild.id);
  if (!pending || pending.id !== pendingId) return "That pending removal has already been handled or does not exist.";
  if (!await resolveCustomRolePending(pendingId, guild.id, "confirmed", actorId)) {
    return "That pending removal has already been handled.";
  }

  let archived = 0;
  let skipped = 0;
  for (let index = 0; index < pending.user_ids.length; index += 1) {
    const userId = pending.user_ids[index]!;
    try {
      if (await archiveOne(guild, userId, pending.reason)) archived += 1;
      else skipped += 1;
    } catch (error) {
      skipped += 1;
      logger.error("Confirmed Custom Role archive failed", {
        guildId: guild.id, userId, reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
    if ((index + 1) % 5 === 0 && index + 1 < pending.user_ids.length) {
      await new Promise(resolve => setTimeout(resolve, 2_000));
    }
  }
  const summary = "Confirmed by <@" + actorId + ">. Archived " + archived + " role(s); kept " + skipped +
    " because the member qualified again, the role was missing, or the bot could not safely remove it.";
  await audit(guild, summary);
  return summary;
}

export async function cancelCustomRolePending(guild: Guild, pendingId: string, actorId: string): Promise<string> {
  const pending = await getOpenCustomRolePending(guild.id);
  if (!pending || pending.id !== pendingId) return "That pending removal has already been handled or does not exist.";
  if (!await resolveCustomRolePending(pendingId, guild.id, "cancelled", actorId)) {
    return "That pending removal has already been handled.";
  }
  await snoozeCustomRoleUsers(guild.id, pending.user_ids, 24);
  const summary = "Cancelled by <@" + actorId + ">. Kept " + pending.user_ids.length +
    " role(s); Lemegeton will ask again in 24 hours if they still do not qualify.";
  await audit(guild, summary);
  return summary;
}

async function restoreSavedRole(member: GuildMember): Promise<boolean> {
  const guild = member.guild;
  const settings = await getCustomRoleSettings(guild.id);
  if (!settings.enabled || !settings.anchor_role_id || !customRoleEligibility(member, settings)) return false;

  return withLock(guild.id, member.id, async () => {
    const record = await getCustomRoleRecord(guild.id, member.id);
    if (!record || (record.status !== "saved" && record.status !== "missing")) return false;
    const existing = record.role_id ? await guild.roles.fetch(record.role_id).catch(() => null) : null;
    if (existing) {
      if (!member.roles.cache.has(existing.id)) await member.roles.add(existing, "Custom Roles: restore eligibility");
      await updateCustomRole(guild.id, member.id, { status: "active", name: existing.name });
      return true;
    }

    const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
    const anchor = await guild.roles.fetch(settings.anchor_role_id).catch(() => null);
    if (!botMember || !botMember.permissions.has("ManageRoles") || !anchor
      || anchor.position >= botMember.roles.highest.position || guild.roles.cache.size >= 250) return false;

    const enhanced = guild.features.includes("ENHANCED_ROLE_COLORS");
    const roleIcons = guild.features.includes("ROLE_ICONS");
    let mode = record.color_mode;
    let primary = record.primary_color;
    let secondary = record.secondary_color;
    let colors: { primaryColor: number; secondaryColor?: number | null; tertiaryColor?: number | null };
    if (enhanced && mode === "holographic") {
      primary = HOLOGRAPHIC_COLORS[0];
      secondary = HOLOGRAPHIC_COLORS[1];
      colors = { primaryColor: HOLOGRAPHIC_COLORS[0], secondaryColor: HOLOGRAPHIC_COLORS[1], tertiaryColor: HOLOGRAPHIC_COLORS[2] };
    } else if (enhanced && mode === "gradient") {
      colors = { primaryColor: primary ?? 0, secondaryColor: secondary ?? 0, tertiaryColor: null };
    } else {
      mode = "solid";
      secondary = null;
      colors = { primaryColor: primary ?? 0, secondaryColor: null, tertiaryColor: null };
    }

    const role = await guild.roles.create({
      name: (record.name || (member.user.username + "'s custom role")).slice(0, 100),
      permissions: [],
      colors,
      ...(roleIcons && record.icon_emoji ? { unicodeEmoji: record.icon_emoji } : {}),
      reason: "Custom Roles: restored role for " + member.id,
    });
    try {
      const target = settings.anchor_place === "above" ? anchor.position + 1 : Math.max(1, anchor.position - 1);
      if (target >= botMember.roles.highest.position) throw new Error("Role hierarchy prevents placement.");
      await role.setPosition(target, { reason: "Custom Roles: restore role position" });
      await member.roles.add(role, "Custom Roles: restore saved role");
      await saveCustomRole({
        guild_id: guild.id,
        user_id: member.id,
        role_id: role.id,
        position_hint: role.position,
        status: "active",
        name: role.name,
        color_mode: mode,
        primary_color: primary,
        secondary_color: secondary,
        icon_emoji: record.icon_emoji,
      });
      await audit(guild, "Restored <@" + member.id + ">'s saved custom role **" + role.name + "** after they qualified again.");
      return true;
    } catch (error) {
      await role.delete("Custom Roles: rollback incomplete restoration").catch(() => undefined);
      throw error;
    }
  });
}

async function queueArchive(guild: Guild, userId: string, reason: string): Promise<void> {
  const queue = queues.get(guild.id) ?? new Map<string, string>();
  queue.set(userId, reason);
  queues.set(guild.id, queue);
  if (timers.has(guild.id)) return;
  const timer = setTimeout(() => {
    timers.delete(guild.id);
    const current = queues.get(guild.id);
    queues.delete(guild.id);
    if (!current?.size) return;
    void archiveAutomatically(guild, [...current].map(([id, why]) => ({ userId: id, reason: why })))
      .catch(error => logger.error("Custom Roles event archive batch failed", {
        guildId: guild.id, reason: error instanceof Error ? error.message : "Unknown error",
      }));
  }, EVENT_BATCH_MS);
  timer.unref();
  timers.set(guild.id, timer);
}

export async function onCustomRoleMemberUpdate(oldMember: GuildMember, newMember: GuildMember): Promise<void> {
  const settings = await getCustomRoleSettings(newMember.guild.id);
  if (!settings.enabled) return;
  const oldEligible = customRoleEligibility(oldMember, settings);
  const newEligible = customRoleEligibility(newMember, settings);
  if (oldEligible && !newEligible) {
    await queueArchive(newMember.guild, newMember.id, "stopped boosting or lost the allowed role");
  } else if (!oldEligible && newEligible) {
    queues.get(newMember.guild.id)?.delete(newMember.id);
    await restoreSavedRole(newMember);
  }
}

export async function onCustomRoleMemberRemove(member: GuildMember): Promise<void> {
  const settings = await getCustomRoleSettings(member.guild.id);
  if (!settings.enabled || !await getCustomRoleRecord(member.guild.id, member.id)) return;
  await queueArchive(member.guild, member.id, "left the server");
}

export async function onCustomRoleMemberAdd(member: GuildMember): Promise<void> {
  try {
    await restoreSavedRole(member);
  } catch (error) {
    logger.warn("Could not restore saved Custom Role after member joined", {
      guildId: member.guild.id, userId: member.id,
      reason: error instanceof Error ? error.message : "Unknown error",
    });
  }
}

export async function reconcileCustomRoleGuild(guild: Guild): Promise<void> {
  const settings = await getCustomRoleSettings(guild.id);
  if (!settings.enabled) return;

  let members;
  try {
    members = await guild.members.fetch({ force: true });
  } catch (error) {
    logger.warn("Skipped Custom Roles reconciliation because member data could not be verified", {
      guildId: guild.id, reason: error instanceof Error ? error.message : "Unknown error",
    });
    return;
  }

  const records = await listCustomRoleRecords(guild.id);
  const reasons: ArchiveReason[] = [];
  for (const record of records) {
    if (record.status === "active" && record.role_id && !guild.roles.cache.has(record.role_id)) {
      await markCustomRoleMissing(guild.id, record.user_id, record.role_id);
    }
    if (record.status !== "active" && record.status !== "missing") continue;
    const member = members.get(record.user_id);
    if (!member) {
      reasons.push({ userId: record.user_id, reason: "left the server" });
    } else if (!customRoleEligibility(member, settings)) {
      reasons.push({ userId: record.user_id, reason: "no longer boosting or allowed" });
    }
  }
  if (reasons.length) await archiveAutomatically(guild, reasons);

  for (const member of members.values()) {
    try {
      await restoreSavedRole(member);
    } catch (error) {
      logger.warn("Could not restore saved Custom Role during reconciliation", {
        guildId: guild.id, userId: member.id,
        reason: error instanceof Error ? error.message : "Unknown error",
      });
    }
  }
}

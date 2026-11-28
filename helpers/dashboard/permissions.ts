import { PermissionsBitField, type Guild } from "discord.js";

export class DashboardBridgeError extends Error {
  constructor(message: string, readonly status: number = 400) {
    super(message);
    this.name = "DashboardBridgeError";
  }
}

export function isDashboardActorId(value: unknown): value is string {
  return typeof value === "string" && /^\d{17,20}$/.test(value);
}

export async function requireGuildMember(guild: Guild, actorId: string): Promise<void> {
  if (!isDashboardActorId(actorId)) {
    throw new DashboardBridgeError("A valid Discord member is required.", 403);
  }
  if (actorId === guild.ownerId) return;
  try {
    await guild.members.fetch(actorId);
  } catch {
    throw new DashboardBridgeError("Your Discord account is no longer a member of this server.", 403);
  }
}

export async function guildActorCanManage(guild: Guild, actorId: string): Promise<boolean> {
  if (!isDashboardActorId(actorId)) return false;
  if (actorId === guild.ownerId) return true;
  try {
    const member = await guild.members.fetch(actorId);
    return member.permissions.has(PermissionsBitField.Flags.ManageGuild)
      || member.permissions.has(PermissionsBitField.Flags.Administrator);
  } catch {
    return false;
  }
}

export async function requireGuildManager(guild: Guild, actorId: string): Promise<void> {
  if (!await guildActorCanManage(guild, actorId)) {
    throw new DashboardBridgeError("Manage Server or Administrator permission is required for this setting.", 403);
  }
}

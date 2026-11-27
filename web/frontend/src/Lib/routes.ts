import { isDiscordSnowflake } from "./validation";

function guildPath(guildId: string): string {
  if (!isDiscordSnowflake(guildId)) throw new TypeError("A valid Discord server ID is required.");
  return "/api/guilds/" + encodeURIComponent(guildId);
}

export const dashboardRoutes = {
  bootstrap: "/api/bootstrap",
  consent: "/api/consent",
  cookies: "/api/cookies",
  logout: "/api/logout",
  guildOverview: (guildId: string) => guildPath(guildId) + "/overview",
  guildSettings: (guildId: string) => guildPath(guildId) + "/settings",
  archiveSettings: (guildId: string) => guildPath(guildId) + "/archive-settings",
  guildCommands: (guildId: string) => guildPath(guildId) + "/commands",
  commandAccess: (guildId: string) => guildPath(guildId) + "/command-access",
  command: (guildId: string, name: string) => {
    if (!name.trim() || name.length > 100) throw new TypeError("A valid command name is required.");
    return guildPath(guildId) + "/commands/" + encodeURIComponent(name);
  },
  commandAccessFor: (guildId: string, name: string) => {
    if (!name.trim() || name.length > 100) throw new TypeError("A valid command name is required.");
    return guildPath(guildId) + "/command-access/" + encodeURIComponent(name);
  },
  guildAudit: (guildId: string) => guildPath(guildId) + "/audit",
  guildDatabase: (guildId: string) => guildPath(guildId) + "/database",
  guildAtlas: (guildId: string) => guildPath(guildId) + "/atlas",
  guildSync: (guildId: string) => guildPath(guildId) + "/sync",
  guildReset: (guildId: string) => guildPath(guildId) + "/reset",
} as const;

import type { Guild } from "../../../Types/dashboard";

export function GuildOverview({ guilds }: { guilds: Guild[] }) {
  const connected = guilds.filter(guild => guild.bot_installed).length;
  return <div className="guild-picker-overview" aria-live="polite"><strong>{connected} connected</strong><span>{guilds.length} manageable servers</span></div>;
}

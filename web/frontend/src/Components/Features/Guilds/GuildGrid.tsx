import type { Guild } from "../../../Types/dashboard";
import { Empty } from "../../UI";
import { GuildCard } from "./GuildCard";

export function GuildGrid({ guilds, onSelect }: { guilds: Guild[]; onSelect: (id: string) => void }) {
  if (!guilds.length) return <Empty>No Discord servers were returned where your account has Manage Server or Administrator permission.</Empty>;
  return <div className="server-picker-list">{guilds.map(guild => <GuildCard key={guild.id} guild={guild} onSelect={onSelect} />)}</div>;
}

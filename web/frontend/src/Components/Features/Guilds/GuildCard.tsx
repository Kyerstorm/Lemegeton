import type { Guild } from "../../../Types/dashboard";
import { Icon } from "../../Icons";
import { InviteBotAction } from "./InviteBotAction";

export function GuildCard({ guild, onSelect }: { guild: Guild; onSelect: (id: string) => void }) {
  const details = (guild.administrator ? "Administrator" : "Manage Server") + " · " + guild.id;
  const content = (
    <>
      <span className="server-picker-icon"><Icon name="server" size={17} /></span>
      <span className="server-picker-name"><strong>{guild.name}</strong><small>{details}</small></span>
      {guild.bot_installed
        ? <span className="server-picker-connected"><i className="server-state-mark" />Connected</span>
        : <InviteBotAction href={guild.invite_url} />}
    </>
  );

  return guild.bot_installed
    ? <button className="server-picker-option" type="button" onClick={() => onSelect(guild.id)}>{content}</button>
    : <div className="server-picker-option is-uninstalled">{content}</div>;
}

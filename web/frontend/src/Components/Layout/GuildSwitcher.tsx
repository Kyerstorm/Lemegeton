import { Icon } from "../Icons";
import { TextShimmerWave } from "../UI";

export interface GuildSwitcherProps {
  guildName?: string;
  connected: boolean;
  open: boolean;
  onOpen: () => void;
}

export function GuildSwitcher({ guildName, connected, open, onOpen }: GuildSwitcherProps) {
  return (
    <div className="guild-control">
      <span>SERVER</span>
      <button
        className="server-picker-trigger"
        type="button"
        onClick={onOpen}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={"Choose Discord server. Current server: " + (guildName || "none selected")}
      >
        <Icon name="server" size={15} />
        <strong>{guildName || "Choose a server"}</strong>
        {connected ? <span className="server-connection-label" aria-label="Lemegeton connected"><TextShimmerWave duration={2.2}>CONNECTED</TextShimmerWave></span> : null}
        <span className="server-picker-caret"><Icon name="chevron-down" size={13} /></span>
      </button>
    </div>
  );
}

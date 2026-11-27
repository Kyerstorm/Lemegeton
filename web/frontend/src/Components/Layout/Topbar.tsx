import { Icon } from "../Icons";
import { TextRoll, Tooltip } from "../UI";
import { GuildSwitcher } from "./GuildSwitcher";
import { MobileNavigationTrigger } from "./MobileNavigation";
import type { PageMetadata } from "./navigation";

interface TopbarUser {
  username?: string;
  global_name?: string | null;
}
interface TopbarGuild {
  name: string;
  bot_installed: boolean;
}
export interface DashboardTopbarProps {
  selectedPage: PageMetadata;
  mobileNav: boolean;
  refreshing: boolean;
  guildId: string;
  currentGuild?: TopbarGuild;
  serverPickerOpen: boolean;
  user: TopbarUser | null;
  onToggleNavigation: () => void;
  onOpenServerPicker: () => void;
  onRefresh: () => void;
}

export function Topbar({
  selectedPage,
  mobileNav,
  refreshing,
  guildId,
  currentGuild,
  serverPickerOpen,
  user,
  onToggleNavigation,
  onOpenServerPicker,
  onRefresh,
}: DashboardTopbarProps) {
  return (
    <header className="topbar">
      <MobileNavigationTrigger open={mobileNav} onToggle={onToggleNavigation} />
      <div className="breadcrumb"><span>CONTROL</span><span className="breadcrumb-divider">/</span><strong><TextRoll>{selectedPage.label}</TextRoll></strong></div>
      <div className="topbar-right">
        <GuildSwitcher guildName={currentGuild?.name} connected={Boolean(currentGuild?.bot_installed)} open={serverPickerOpen} onOpen={onOpenServerPicker} />
        <Tooltip label="Refresh dashboard">
          <button
            className={"icon-button" + (refreshing ? " spinning" : "")}
            type="button"
            onClick={onRefresh}
            aria-label="Refresh dashboard"
            disabled={!guildId || refreshing}
          >
            <Icon name="refresh" size={17} />
          </button>
        </Tooltip>
        <div className="account" aria-label="Signed-in Discord account"><span className="avatar">{(user?.global_name || user?.username || "?").slice(0, 1).toUpperCase()}</span><span className="account-copy"><strong>{user?.global_name || user?.username || "Discord account"}</strong><small>DISCORD / VERIFIED</small></span></div>
      </div>
    </header>
  );
}

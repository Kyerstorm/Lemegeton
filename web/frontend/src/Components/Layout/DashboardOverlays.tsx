import { useMemo, useState } from "react";
import { Icon } from "../Icons";
import { useDialogFocus } from "../Hooks/useDialogFocus";
import { ActivityOrb } from "../Feedback/ActivityOrb";
import { IconButton } from "../UI/IconButton";
import { ConfirmDialog } from "../Dialogs/ConfirmDialog";
import { GuildGrid } from "../Features/Guilds/GuildGrid";
import { GuildSearch } from "../Features/Guilds/GuildSearch";
import { GuildOverview } from "../Features/Guilds/GuildOverview";
import type { Guild } from "../../Types/dashboard";

interface ToastItem {
  id: number;
  message: string;
  error: boolean;
  pending?: boolean;
}
interface Confirmation {
  title: string;
  message: string;
  actionLabel: string;
  destructive?: boolean;
}
interface DashboardOverlaysProps {
  toasts: ToastItem[];
  serverPickerOpen: boolean;
  guilds: Guild[];
  confirmation: Confirmation | null;
  operationBusy: boolean;
  onDismissToast: (id: number) => void;
  onCloseServerPicker: () => void;
  onSelectGuild: (guildId: string) => void;
  onSettleConfirmation: (confirmed: boolean) => void;
}

export function DashboardOverlays({
  toasts,
  serverPickerOpen,
  guilds,
  confirmation,
  operationBusy,
  onDismissToast,
  onCloseServerPicker,
  onSelectGuild,
  onSettleConfirmation,
}: DashboardOverlaysProps) {
  const [guildSearch, setGuildSearch] = useState("");
  const serverPickerRef = useDialogFocus(serverPickerOpen, "#guild-search", onCloseServerPicker);
  const visibleGuilds = useMemo(() => {
    const query = guildSearch.trim().toLocaleLowerCase("en-US");
    return query ? guilds.filter(guild => guild.name.toLocaleLowerCase("en-US").includes(query) || guild.id.includes(query)) : guilds;
  }, [guilds, guildSearch]);

  return (
    <>
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
        {toasts.map(toast => (
          <div key={toast.id} className={"toast" + (toast.error ? " error" : "")}>
            {toast.pending ? <ActivityOrb label={toast.message} state="working" size={20} /> : <Icon name={toast.error ? "alert-circle" : "check-circle"} size={15} />}
            <span className="toast-message">
              {toast.message}
              {toast.error && toast.message.includes("GitHub issue") ? (
                <a className="toast-issue-link" href="https://github.com/Kyerstorm/Lemegeton/issues" target="_blank" rel="noopener noreferrer">
                  Open GitHub issue
                </a>
              ) : null}
            </span>
            <IconButton label="Dismiss notification" onClick={() => onDismissToast(toast.id)}><Icon name="close" size={13} /></IconButton>
          </div>
        ))}
      </div>
      {serverPickerOpen ? (
        <div className="access-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onCloseServerPicker(); }}>
          <section ref={serverPickerRef} className="access-dialog server-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="server-picker-title" tabIndex={-1}>
            <div className="access-heading">
              <div>
                <p className="eyebrow">DISCORD / YOUR SERVERS</p>
                <h2 id="server-picker-title">Choose a <span>server.</span></h2>
                <p>Connected servers are ready to configure. Servers without Lemegeton can be invited to.</p>
              </div>
              <IconButton className="access-close" label="Close server picker" onClick={onCloseServerPicker}><Icon name="close" size={16} /></IconButton>
            </div>
            <GuildSearch value={guildSearch} onChange={setGuildSearch} />
            <GuildGrid guilds={visibleGuilds} onSelect={onSelectGuild} />
            {visibleGuilds.length === 0 ? <p className="footnote">No manageable servers match this search.</p> : null}
            <div className="access-footer">
              <GuildOverview guilds={guilds} />
              <button type="button" className="command-reset" onClick={onCloseServerPicker}>Close</button>
            </div>
          </section>
        </div>
      ) : null}
      <ConfirmDialog
        open={Boolean(confirmation)}
        title={confirmation?.title || ""}
        message={confirmation?.message || ""}
        confirmLabel={confirmation?.actionLabel || "Confirm"}
        destructive={confirmation?.destructive}
        busy={operationBusy}
        onCancel={() => onSettleConfirmation(false)}
        onConfirm={() => onSettleConfirmation(true)}
      />
    </>
  );
}

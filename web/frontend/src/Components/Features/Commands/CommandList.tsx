import type { Command } from "../../../Types/dashboard";
import { Empty, Skeleton, StatusPill, Switch } from "../../UI";
import { CommandDetails } from "./CommandDetails";

export function CommandList({ commands, filteredCommands, loading, loaded, error, saving, operationBusy, accessLoading, accessSaving, guideUrl, onCopy, onOpenAccess, onToggle }: {
  commands: Command[];
  filteredCommands: Command[];
  loading: boolean;
  loaded: boolean;
  error: string;
  saving: boolean;
  operationBusy: boolean;
  accessLoading: boolean;
  accessSaving: boolean;
  guideUrl: (command: Command) => string;
  onCopy: (command: Command) => void;
  onOpenAccess: (command: Command) => void;
  onToggle: (command: Command) => void;
}) {
  return (
    <div className="command-list">
      {!loaded && loading ? (
        <div className="command-skeleton-list" role="status" aria-label="Loading registered commands">
          {Array.from({ length: 5 }, (_, index) => <article className="command-row" key={index}><div className="command-main"><Skeleton width="34%" height={11} /><Skeleton width="78%" height={8} /><div className="skeleton-inline"><Skeleton width={52} height={17} radius={5} /><Skeleton width={44} height={17} radius={5} /><Skeleton width={48} height={17} radius={5} /></div><Skeleton width={116} height={26} radius={6} /></div><Skeleton width={32} height={18} radius={99} /></article>)}
        </div>
      ) : !loaded && error ? null : !commands.length ? <Empty>No dashboard-managed commands were returned.</Empty>
        : !filteredCommands.length ? <Empty>No commands match this search and filter.</Empty>
        : filteredCommands.map(command => (
          <article className="command-row" key={command.fullname}>
            <CommandDetails command={command} guideUrl={guideUrl} onCopy={onCopy} onOpenAccess={onOpenAccess} disabled={accessLoading || accessSaving} />
            <div className="command-state"><StatusPill ok={command.enabled && !command.protected}>{command.protected ? "Protected / always on" : command.enabled ? "Enabled" : "Disabled"}</StatusPill></div>
            <Switch
              checked={Boolean(command.enabled)}
              label={"Toggle " + command.fullname}
              disabled={Boolean(command.protected) || !command.configurable || saving || operationBusy}
              onChange={() => onToggle(command)}
            />
          </article>
        ))}
    </div>
  );
}

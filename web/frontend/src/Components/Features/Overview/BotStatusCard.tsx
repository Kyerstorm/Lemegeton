import { Card, Skeleton, StatusPill, AnimatedNumber } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import { duration, gatewayStatusLabel, timestamp } from "./format";
import type { OverviewBot, OverviewSystem } from "./types";

export interface BotStatusCardProps {
  bot: OverviewBot;
  system: OverviewSystem;
  loading: boolean;
  loaded: boolean;
  error: string;
  errorStatus: number | null;
  runtimeOnline: boolean;
  onRetry: () => void;
}

export function BotStatusCard({ bot, system, loading, loaded, error, errorStatus, runtimeOnline, onRetry }: BotStatusCardProps) {
  const lastKnown = system.last_known || null;
  return (
    <Card eyebrow="PROCESS STATUS" title="Runtime signal" index="A / 04" className="panel-large">
      {error ? <SectionError message={error} status={errorStatus} onRetry={onRetry} /> : null}
      {!loaded ? loading ? <div className="runtime-skeleton" role="status" aria-label="Loading runtime status">
        <div className="runtime-body"><Skeleton width={62} height={62} radius={17} /><div className="runtime-copy"><Skeleton width="54%" height={9} /><Skeleton width="92%" height={8} /><div className="skeleton-inline"><Skeleton width={94} height={20} radius={6} /><Skeleton width={88} height={20} radius={6} /></div></div></div>
        <div className="runtime-data"><div><Skeleton width="62%" height={8} /><Skeleton width="76%" height={12} /></div><div><Skeleton width="62%" height={8} /><Skeleton width="76%" height={12} /></div><div><Skeleton width="62%" height={8} /><Skeleton width="76%" height={12} /></div></div>
      </div> : null : <>
        <div className={"runtime-body"}><div className={"runtime-mark" + (runtimeOnline ? " is-online" : "")}><span>⠿</span><i /></div><div className="runtime-copy"><p className="runtime-state">{system.status === "unknown" ? (lastKnown ? "Last known / " + String(lastKnown.status || "Unknown") : "Live status unknown") : gatewayStatusLabel(system.status, bot.ready) === "Connected" ? "Discord gateway connected" : "Discord gateway " + gatewayStatusLabel(system.status, bot.ready).toLowerCase()}</p><p className="muted">{system.status === "unknown" ? (system.reason || "The bot bridge is unreachable. Live control operations may be unavailable.") : "Dashboard HTTP availability and Discord gateway health are tracked separately."}</p><div className="runtime-flags"><StatusPill ok={Boolean(bot.ready) && system.status === "online"}>GATEWAY / {gatewayStatusLabel(system.status, bot.ready).toUpperCase()}</StatusPill><StatusPill ok={system.status !== "unknown"}>BRIDGE / {system.status === "unknown" ? "UNREACHABLE" : "CONNECTED"}</StatusPill></div></div></div>
        <div className="runtime-data"><div><small>PROCESS UPTIME</small><strong>{duration(system.uptime_seconds)}</strong></div><div><small>NODE RUNTIME</small><strong>{system.node_version || "Unavailable"}</strong></div><div><small>REGISTERED COMMANDS</small><strong><AnimatedNumber value={system.command_count ?? 0} /></strong></div></div>
        {system.status === "unknown" && lastKnown?.observed_at ? <p className="footnote compact">Last observed {timestamp(Number(lastKnown.observed_at))}. This is cached status, not a live reading.</p> : null}
      </>}
    </Card>
  );
}

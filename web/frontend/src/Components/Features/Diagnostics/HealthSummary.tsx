import { Card, Skeleton, StatusPill, AnimatedNumber } from "../../UI";
import type { SystemStatus } from "../../../Types/dashboard";
import { duration, gatewayStatusLabel, timestamp } from "../Overview/format";

export function HealthSummary({ system, loading, loaded }: {
  system: SystemStatus;
  loading: boolean;
  loaded: boolean;
}) {
  const lastKnown = system.last_known || null;
  return (
    <Card eyebrow="STATUS SNAPSHOT" title="Runtime details" index={loaded ? "LIVE" : "STATUS"}>
      {!loaded && loading ? (
        <div className="system-skeleton-rows" role="status" aria-label="Loading runtime status">
          {Array.from({ length: 7 }, (_, index) => <div className="extension-row" key={index}><Skeleton width="42%" height={9} /><Skeleton width="36%" height={9} /></div>)}
        </div>
      ) : loaded ? (
        <dl className="definition-list diagnostic-list">
          <div><dt>Dashboard bridge</dt><dd><StatusPill ok={system.status !== "unknown"}>{system.status === "unknown" ? "Unreachable" : "Responding"}</StatusPill></dd></div>
          <div><dt>Discord gateway</dt><dd><StatusPill ok={system.status === "online"}>{gatewayStatusLabel(system.status, system.ready)}</StatusPill></dd></div>
          <div><dt>Gateway latency</dt><dd>{(system.status !== "online" && system.status !== "degraded") || system.latency_ms == null ? "Unavailable" : <AnimatedNumber value={Math.round(system.latency_ms)} suffix=" ms" />}</dd></div>
          <div><dt>Connected bot guilds</dt><dd><AnimatedNumber value={system.guild_count} /></dd></div>
          <div><dt>Registered commands</dt><dd><AnimatedNumber value={system.command_count ?? system.commands?.length ?? 0} /></dd></div>
          <div><dt>Node runtime</dt><dd>{system.node_version || "Unavailable"}</dd></div>
          <div><dt>Process uptime</dt><dd>{duration(system.uptime_seconds)}</dd></div>
          <div><dt>Observation time</dt><dd>{timestamp(system.observed_at)}</dd></div>
          {lastKnown ? <><div><dt>Last-known status</dt><dd>{String(lastKnown.status || "Unknown")}</dd></div><div><dt>Last-known observation</dt><dd>{timestamp(Number(lastKnown.observed_at))}</dd></div></> : null}
        </dl>
      ) : null}
    </Card>
  );
}

import { useReducedMotion } from "motion/react";
import { BotStatusCard } from "./BotStatusCard";
import { CommandSummary } from "./CommandSummary";
import { ActivitySummary } from "./ActivitySummary";
import { ServerSummary } from "./ServerSummary";
import { Icon } from "../../Icons";
import { Button, InView, Particles, SectionHeading, Skeleton, SlidingNumber } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import { gatewayStatusDescription } from "./format";
import type { Page } from "../../Layout/navigation";

interface PageHeading {
  eyebrow: string;
  subtitle: string;
}
interface OverviewBot {
  ready?: boolean;
  latency_ms?: number | null;
  member_count?: number | null;
  guild_count?: number | null;
}
interface OverviewSystem {
  status?: string;
  reason?: string;
  guild_count?: number | null;
  command_count?: number | null;
  uptime_seconds?: number | null;
  node_version?: string;
  last_known?: Record<string, unknown> | null;
}
interface OverviewGuild {
  name: string;
  administrator?: boolean;
}
interface OverviewAuditEntry {
  action?: string;
  details?: string;
  actor_name?: string;
  actor_id?: string;
  ts?: string;
}
interface OverviewPageProps {
  selectedPage: PageHeading;
  bot: OverviewBot;
  system: OverviewSystem;
  systemLoading: boolean;
  systemLoaded: boolean;
  systemError: string;
  systemErrorStatus: number | null;
  onRetrySystem: () => void;
  updatedAt: number | null;
  loading: boolean;
  loaded: boolean;
  error: string;
  errorStatus: number | null;
  onRetry: () => void;
  runtimeStatus: string;
  commandsCount: number;
  enabled: number;
  disabled: number;
  percent: number;
  runtimeOnline: boolean;
  currentGuild?: OverviewGuild;
  guildId: string;
  user: { id: string } | null;
  audit: OverviewAuditEntry[];
  auditLoading: boolean;
  auditLoaded: boolean;
  auditError: string;
  auditErrorStatus: number | null;
  onRetryAudit: () => void;
  operationBusy: boolean;
  onNavigate: (page: Page) => void;
  onPublishCommands: () => void;
}

export function OverviewPage({
  selectedPage,
  bot,
  system,
  systemLoading,
  systemLoaded,
  systemError,
  systemErrorStatus,
  onRetrySystem,
  updatedAt,
  loading,
  loaded,
  error,
  errorStatus,
  onRetry,
  runtimeStatus,
  commandsCount,
  enabled,
  disabled,
  percent,
  runtimeOnline,
  currentGuild,
  guildId,
  user,
  audit,
  auditLoading,
  auditLoaded,
  auditError,
  auditErrorStatus,
  onRetryAudit,
  operationBusy,
  onNavigate,
  onPublishCommands,
}: OverviewPageProps) {
  const prefersReducedMotion = useReducedMotion();
  const lastKnown = system.last_known || null;
  const statusDescription = system.status === "unknown" && lastKnown?.status
    ? "Last known / " + String(lastKnown.status)
    : gatewayStatusDescription(system.status, system.reason);
  const memberCount = bot.member_count;
  const guildCount = system.guild_count ?? bot.guild_count;
  const registeredCommands = system.command_count ?? commandsCount;
  const latency = bot.latency_ms;

  return (
    <section className="page">
      <div className="overview-brand-art">
        {prefersReducedMotion === false ? (
          <img src="/brand/lemegeton-garden.gif" alt="Lemegeton typed botanical wordmark" />
        ) : (
          <span className="overview-brand-static">LEMEGETON</span>
        )}
        <div className="overview-particles">
          <Particles shape="Flower" reach={90} force={52} grain="Coarse" />
        </div>
      </div>
      <SectionHeading
        eyebrow={selectedPage.eyebrow}
        title={<>Bot <span>overview.</span></>}
        subtitle={selectedPage.subtitle}
        actions={<>
          <Button onClick={() => onNavigate("audit")}>View activity <Icon name="arrow-up-right" size={13} /></Button>
          <Button tone="primary" onClick={() => onPublishCommands()} disabled={operationBusy || !guildId}>Publish commands <Icon name="arrow-up-right" size={13} /></Button>
        </>}
      />
      {error ? <SectionError message={error} status={errorStatus} onRetry={onRetry} /> : null}

      {!loaded && loading ? (
        <div className="overview-skeleton" role="status" aria-live="polite" aria-label="Loading dashboard overview">
          <div className="status-strip skeleton-status">
            <Skeleton width={7} height={7} radius="50%" />
            <Skeleton width={105} height={8} />
            <Skeleton width="44%" height={8} />
            <Skeleton width={120} height={8} />
          </div>
          <div className="metric-grid">
            {Array.from({ length: 4 }, (_, index) => (
              <article className="metric" key={index}>
                <Skeleton width="63%" height={8} />
                <Skeleton className="metric-value-skeleton" width="42%" height={31} />
                <Skeleton width="78%" height={8} />
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {loaded ? (
        <>
          <div className="status-strip" aria-label="Bot runtime status">
            <span className={"strip-signal" + (runtimeOnline ? "" : " is-muted")} aria-hidden="true" />
            <span>{runtimeStatus}</span>
            <span className="strip-separator">/</span>
            <span>{statusDescription}</span>
            <time>{updatedAt ? "UPDATED " + new Date(updatedAt).toLocaleTimeString() : "STATUS SYNCED"}</time>
          </div>

          <InView className="overview-enter" variants={{ hidden: { opacity: 0, y: 18, filter: "blur(5px)" }, visible: { opacity: 1, y: 0, filter: "blur(0px)" } }} transition={{ duration: 0.45, ease: "easeOut" }}>
          <div className="metric-grid">
            <article className="metric">
              <div className="metric-label"><span>SERVER MEMBERS</span></div>
              <strong className="metric-value">{memberCount == null ? "—" : <SlidingNumber value={memberCount} />}</strong>
              <p>Selected Discord server</p>
            </article>
            <article className="metric">
              <div className="metric-label"><span>BOT GUILDS</span></div>
              <strong className="metric-value">{guildCount == null ? "—" : <SlidingNumber value={guildCount} />}</strong>
              <p>Connected Discord servers</p>
            </article>
            <article className="metric">
              <div className="metric-label"><span>REGISTERED COMMANDS</span></div>
              <strong className="metric-value"><SlidingNumber value={registeredCommands} /></strong>
              <p>Commands available to configure</p>
            </article>
            <article className="metric">
              <div className="metric-label"><span>GATEWAY LATENCY</span></div>
              <strong className="metric-value">{latency == null ? "—" : <><SlidingNumber value={latency} /><small> ms</small></>}</strong>
              <p>{runtimeOnline ? "Current Discord gateway" : "Live latency unavailable"}</p>
            </article>
          </div>
          </InView>

          <InView className="overview-enter" variants={{ hidden: { opacity: 0, y: 18, filter: "blur(5px)" }, visible: { opacity: 1, y: 0, filter: "blur(0px)" } }} transition={{ duration: 0.5, ease: "easeOut" }}>
          <div className="content-grid">
            <BotStatusCard
              bot={bot}
              system={system}
              loading={systemLoading}
              loaded={systemLoaded}
              error={systemError}
              errorStatus={systemErrorStatus}
              runtimeOnline={runtimeOnline}
              onRetry={onRetrySystem}
            />
            <ActivitySummary
              entries={audit}
              loading={auditLoading}
              loaded={auditLoaded}
              error={auditError}
              errorStatus={auditErrorStatus}
              onRetry={onRetryAudit}
              onNavigate={onNavigate}
            />
            <CommandSummary enabled={enabled} disabled={disabled} percent={percent} unavailable={system.status === "unknown"} />
            <ServerSummary currentGuild={currentGuild} guildId={guildId} user={user} />
          </div>
          </InView>
        </>
      ) : null}
    </section>
  );
}

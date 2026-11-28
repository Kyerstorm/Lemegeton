import { Icon } from "../../Icons";
import { Button, Card, Empty, SectionHeading, Skeleton, StatusPill } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { SystemStatus, SectionLoadState } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";

export function ExtensionsPage({ selectedPage, system, state, onLoadSystem }: {
  selectedPage: PageMetadata;
  system: SystemStatus;
  state: SectionLoadState;
  onLoadSystem: () => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Registered <span>commands.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={onLoadSystem} disabled={state.loading}>Refresh registry <Icon name="refresh" size={13} /></Button>} />
      <Card eyebrow="LIVE SLASH COMMANDS" title="Command inventory" index={String(system.command_count ?? system.commands?.length ?? 0) + " REGISTERED"}>
        {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={onLoadSystem} /> : null}
        {state.loading && !state.loaded ? (
          <div className="system-skeleton-rows" role="status" aria-label="Loading registered commands">
            {Array.from({ length: 3 }, (_, index) => <div className="extension-row" key={index}><Skeleton width="62%" height={9} /><Skeleton width={92} height={20} radius={99} /></div>)}
          </div>
        ) : system.commands?.length ? (
          <div className="extension-list">{system.commands.map(name => <div className="extension-row" key={name}><code>/{name}</code><StatusPill ok>Registered / live process</StatusPill></div>)}</div>
        ) : state.error ? null : <Empty>{system.status === "unknown" ? "The live command registry is unavailable." : "No slash commands were reported by the bot process."}</Empty>}
      </Card>
      <p className="footnote">This is the global slash-command registry reported by the live bot process. Per-server feature availability is managed under Commands; the runtime does not expose dynamic extension loading.</p>
    </section>
  );
}

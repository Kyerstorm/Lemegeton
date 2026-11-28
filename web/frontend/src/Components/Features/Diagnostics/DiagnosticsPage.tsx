import { Icon } from "../../Icons";
import { Button, Card, SectionHeading, Skeleton } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { SectionLoadState, SystemStatus } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";
import { HealthSummary } from "./HealthSummary";

export function DiagnosticsPage({ selectedPage, system, state, onLoadSystem }: {
  selectedPage: PageMetadata;
  system: SystemStatus;
  state: SectionLoadState;
  onLoadSystem: () => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Under the <span>surface.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={onLoadSystem} disabled={state.loading}>Check now <Icon name="refresh" size={13} /></Button>} />
      {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={onLoadSystem} /> : null}
      {!state.loaded && state.error ? null : (
        <div className="content-grid">
          <HealthSummary system={system} loading={state.loading} loaded={state.loaded} />
          <Card eyebrow="BOUNDARIES" title="Service availability">
            {state.loading && !state.loaded ? <div className="system-diagnostics-skeleton" role="status" aria-label="Loading service availability"><Skeleton width="82%" height={9} /><Skeleton width="100%" height={9} /><Skeleton width="74%" height={9} /><Skeleton width="91%" height={9} /></div> : (
              <>
                <div className="note-block"><strong>Two separate signals.</strong><p>Dashboard HTTP availability does not mean the Discord gateway is connected. Cached observations are labelled and never presented as live status.</p></div>
                <div className="note-block"><strong>Control operations require the bot.</strong><p>When the bridge or Discord synchronization is unavailable, command changes fail safely rather than showing false success.</p></div>
              </>
            )}
          </Card>
        </div>
      )}
    </section>
  );
}

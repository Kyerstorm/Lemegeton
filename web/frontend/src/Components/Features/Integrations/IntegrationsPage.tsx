import { Icon } from "../../Icons";
import { Button, Card, Empty, SectionHeading, Skeleton, StatusPill } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { Integration, SectionLoadState } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";

export function IntegrationsPage({ selectedPage, integrations, state, onLoad }: {
  selectedPage: PageMetadata;
  integrations: Integration[];
  state: SectionLoadState;
  onLoad: () => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Integration <span>status.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={onLoad} disabled={state.loading}>Refresh <Icon name="refresh" size={13} /></Button>} />
      <Card eyebrow="BOT-WIDE CONFIGURATION" title="Provider availability" index="BOT MODERATOR">
        {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={onLoad} /> : null}
        {!state.loaded && state.loading ? <div className="system-skeleton-rows" role="status" aria-label="Loading provider availability">{Array.from({ length: 3 }, (_, index) => <div className="extension-row" key={index}><Skeleton width="62%" height={9} /><Skeleton width={92} height={20} radius={99} /></div>)}</div> : integrations.length ? (
          <div className="extension-list">{integrations.map((item, index) => <div className="extension-row" key={(item.name || "integration") + index}><div><code>{item.name || "Integration"}</code><p className="command-description">{item.detail || "No additional details."}</p></div><StatusPill ok={Boolean(item.configured)}>{item.configured ? "Configured" : "Not configured"}</StatusPill></div>)}</div>
        ) : !state.loaded && state.error ? null : <Empty>No integration metadata was reported.</Empty>}
      </Card>
      <p className="footnote">Only configuration presence is displayed. Credential values and tokens are never returned to the browser.</p>
    </section>
  );
}

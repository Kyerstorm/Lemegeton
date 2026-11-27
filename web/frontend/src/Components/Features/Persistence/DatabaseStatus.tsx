import { Icon } from "../../Icons";
import { Button, Card, Empty, SectionHeading, Skeleton, StatusPill } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { Resource, SectionLoadState } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";

export function DatabaseStatus({ selectedPage, resources, state, onLoad }: {
  selectedPage: PageMetadata;
  resources: Resource[];
  state: SectionLoadState;
  onLoad: () => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>State that <span>survives.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={onLoad} disabled={state.loading}>Refresh <Icon name="refresh" size={13} /></Button>} />
      <Card eyebrow="PERSISTED RESOURCES" title="Storage overview">
        {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={onLoad} /> : null}
        {!state.loaded && state.loading ? <div className="database-skeleton" role="status" aria-label="Loading persisted resources">{Array.from({ length: 4 }, (_, index) => <div className="database-skeleton-row" key={index}><Skeleton width="23%" height={9} /><Skeleton width="48%" height={9} /><Skeleton width="16%" height={18} radius={99} /></div>)}</div> : resources.length ? (
          <div className="table-scroll"><table><thead><tr><th>RESOURCE</th><th>PURPOSE / DETAILS</th><th>STATE</th></tr></thead><tbody>{resources.map((row, index) => <tr key={(row.name || "resource") + index}><td>{row.name || "—"}</td><td>{row.purpose || "—"}<small>{row.detail || ""}</small></td><td><StatusPill ok={String(row.state || "").toLowerCase() === "available"}>{row.state || "Unknown"}</StatusPill></td></tr>)}</tbody></table></div>
        ) : !state.loaded && state.error ? null : <Empty>No persistence resource metadata was reported.</Empty>}
      </Card>
    </section>
  );
}

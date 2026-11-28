import { Icon } from "../../Icons";
import { Button, Card, DataTable, SectionHeading } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import { ActivityList } from "./ActivityList";
import { timeAgo } from "../Overview/format";
import type { AuditEntry, SectionLoadState } from "../../../Types/dashboard";
import type { PageMetadata } from "../../Layout/navigation";

export function AuditHistory({ selectedPage, guildId, entries, state, hasMore, onLoad, onLoadMore }: {
  selectedPage: PageMetadata;
  guildId: string;
  entries: AuditEntry[];
  state: SectionLoadState;
  hasMore: boolean;
  onLoad: (guildId: string) => void;
  onLoadMore: (guildId: string) => void;
}) {
  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Nothing <span>unaccounted.</span></>} subtitle={selectedPage.subtitle} actions={<Button onClick={() => onLoad(guildId)} disabled={state.loading}>Refresh history <Icon name="refresh" size={13} /></Button>} />
      <Card eyebrow="PERSISTED EVENTS" title="Audit trail" index="25 PER PAGE">
        {state.error ? <SectionError message={state.error} status={state.errorStatus} onRetry={() => onLoad(guildId)} /> : null}
        {state.loaded ? (
          <DataTable
            label="Server audit history"
            rows={entries}
            rowKey={(entry, index) => entry.id || (entry.ts || "event") + "-" + (entry.actor_id || "unknown") + "-" + index}
            emptyLabel="No audit events have been recorded for this server yet."
            columns={[
              { key: "action", label: "Action", render: entry => String(entry.action || "Administrative action").replaceAll("_", " ") },
              { key: "details", label: "Details", render: entry => entry.details || "No additional details" },
              { key: "actor", label: "Actor", render: entry => entry.actor_name || entry.actor_id || "Unknown account" },
              { key: "time", label: "When", render: entry => <time dateTime={entry.ts || undefined} title={entry.ts || undefined}>{timeAgo(entry.ts)}</time> },
            ]}
          />
        ) : state.loading ? <ActivityList entries={entries} loading /> : null}
        {hasMore ? (
          <Button onClick={() => onLoadMore(guildId)} disabled={state.loading}>
            Load older events <Icon name="chevron-down" size={13} />
          </Button>
        ) : null}
      </Card>
    </section>
  );
}

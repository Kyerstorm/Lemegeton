import { ActivityList } from "../Activity/ActivityList";
import { Icon } from "../../Icons";
import { Card } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import type { AuditEntry } from "../../../Types/dashboard";
import type { Page } from "../../Layout/navigation";

export function ActivitySummary({ entries, loading, loaded, error, errorStatus, onRetry, onNavigate }: {
  entries: AuditEntry[];
  loading: boolean;
  loaded: boolean;
  error: string;
  errorStatus: number | null;
  onRetry: () => void;
  onNavigate: (page: Page) => void;
}) {
  return (
    <Card eyebrow="RECENT CHANGES" title="Audit history" action={<button className="text-button" type="button" onClick={() => onNavigate("audit")}>All events <Icon name="arrow-up-right" size={13} /></button>}>
      {error ? <SectionError message={error} status={errorStatus} onRetry={onRetry} /> : null}
      {!loaded && error ? null : <ActivityList entries={entries.slice(0, 5)} loading={loading && !loaded} />}
    </Card>
  );
}

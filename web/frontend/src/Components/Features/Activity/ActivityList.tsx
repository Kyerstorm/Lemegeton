import { Icon } from "../../Icons";
import { Empty, Skeleton } from "../../UI";
import { timeAgo } from "../Overview/format";

type AuditEntry = { action?: string; details?: string; actor_name?: string; actor_id?: string; ts?: string };

export function ActivityList(props: { entries: AuditEntry[]; loading?: boolean }) {
  if (props.loading && !props.entries.length) {
    return (
      <div className="activity-list activity-list-skeleton" role="status" aria-label="Loading audit activity">
        {Array.from({ length: 4 }, (_, index) => (
          <div className="activity-row" key={index}>
            <Skeleton width={29} height={29} radius={9} />
            <div className="activity-copy"><Skeleton width="46%" height={9} /><Skeleton width="76%" height={8} /></div>
            <Skeleton width={48} height={8} />
          </div>
        ))}
      </div>
    );
  }

  if (!props.entries.length) return <Empty>No audit events have been recorded for this server yet.</Empty>;

  return (
    <div className="activity-list">
      {props.entries.map((entry, index) => (
        <div className="activity-row" key={(entry.ts || "event") + index}>
          <span className="activity-glyph"><Icon name="activity" size={14} /></span>
          <div className="activity-copy">
            <strong>{String(entry.action || "Administrative action").replaceAll("_", " ")}</strong>
            <small>{entry.details || "No additional details"} · by {entry.actor_name || entry.actor_id || "Unknown account"}</small>
          </div>
          <time className="activity-time" title={entry.ts || ""}>{timeAgo(entry.ts)}</time>
        </div>
      ))}
    </div>
  );
}

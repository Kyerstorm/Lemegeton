import { Icon } from "../../Icons";
import { Button, Card } from "../../UI";
import type { AtlasRelation } from "./types";

export function AtlasDetailPanel({ relationships, loading, onOpenNode }: {
  relationships: AtlasRelation[];
  loading: boolean;
  onOpenNode: (relation: AtlasRelation) => void;
}) {
  if (!relationships.length) return null;
  return (
    <Card eyebrow="RECORDED EDGES" title="Connections" index={relationships.length + " SHOWN"}>
      <div className="atlas-connections">
        {relationships.map((relation, index) => (
          <article className="atlas-connection" key={relation.title + relation.category + index}>
            <div className="atlas-connection-main">
              <span className={"atlas-source " + relation.sourceKind}>{relation.sourceKind.replaceAll("_", " ")}</span>
              <strong>{relation.title}</strong>
              <small>{relation.category.replaceAll("_", " ")} · {relation.relationType}</small>
              <small>Source: {relation.source}</small>
              {relation.provider && relation.providerId ? <small>Provider ID: {relation.provider}:{relation.providerId}</small> : null}
              {relation.evidence ? <small>Evidence: {relation.evidence}</small> : null}
            </div>
            <div className="atlas-connection-actions">
              <Button onClick={() => onOpenNode(relation)} disabled={loading}>Open node <Icon name="arrow-up-right" size={13} /></Button>
              {relation.url ? <a className="atlas-provider-link" href={relation.url} target="_blank" rel="noreferrer">Source record <Icon name="arrow-up-right" size={12} /></a> : null}
            </div>
          </article>
        ))}
      </div>
    </Card>
  );
}

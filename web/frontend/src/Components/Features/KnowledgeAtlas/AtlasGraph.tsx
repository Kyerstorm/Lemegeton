import { Icon } from "../../Icons";
import { Empty } from "../../UI";
import type { AtlasDisplayNode, AtlasEdge, AtlasResponse } from "./types";

export function AtlasGraph({ result, nodes, edges, positions, zoom, loading, onOpenNode, onSelectCategory }: {
  result: AtlasResponse;
  nodes: AtlasDisplayNode[];
  edges: AtlasEdge[];
  positions: Map<string, { x: number; y: number }>;
  zoom: number;
  loading: boolean;
  onOpenNode: (node: AtlasDisplayNode) => void;
  onSelectCategory: (category: string) => void;
}) {
  return (
    <>
      {nodes.length ? (
        <div className="atlas-graph" role="group" aria-label={"Multi-hop media relationships connected to " + result.root.title}>
          <div className="atlas-graph-content" style={{ transform: "scale(" + zoom / 100 + ")" }}>
            <svg className="atlas-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {edges.map((edge, index) => {
                const from = positions.get(edge.from);
                const to = positions.get(edge.to);
                return from && to ? <line key={edge.from + edge.to + edge.sourceKind + index} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={"atlas-edge " + edge.sourceKind} /> : null;
              })}
            </svg>
            <div className="atlas-root-node">
              <span className="atlas-node-category">{result.root.category.replaceAll("_", " ")}</span>
              <strong>{result.root.title}</strong>
              {result.root.url ? <a href={result.root.url} target="_blank" rel="noreferrer">Provider <Icon name="arrow-up-right" size={12} /></a> : null}
            </div>
            {nodes.map(node => (
              <button key={node.id} type="button" className={"atlas-node " + (node.sourceKind || "provider")} style={{ left: node.x + "%", top: node.y + "%" }} title={node.title + " · " + (node.relationType || "Connected media")} onClick={() => onOpenNode(node)} disabled={loading}>
                <span>LEVEL {node.depth} · {node.category.replaceAll("_", " ")}</span>
                <strong>{node.title}</strong>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <Empty>{result.graph?.truncated ? "The graph was bounded before any visible nodes remained. Adjust the filters or explore another title." : result.relationships.length ? "No connections match these filters." : "No connections have been recorded for this title yet. Explore another title or check back after supported provider relationships are indexed."}</Empty>
      )}
      {result.clusters?.length ? <div className="atlas-clusters"><span>MEDIA CLUSTERS</span>{result.clusters.map(cluster => <button type="button" key={cluster.category} onClick={() => onSelectCategory(cluster.category)}>{cluster.category.replaceAll("_", " ")} <strong>{cluster.count}</strong></button>)}</div> : null}
      {result.path?.edges.length ? <p className="atlas-path-summary">Shortest path: {result.path.nodes.map(node => node.title).join(" / ")}</p> : null}
      {result.graph?.truncated ? <p className="footnote compact">This graph reached its node limit. Explore a connected node to inspect its neighborhood.</p> : null}
      <div className="atlas-legend"><span><i className="provider" /> Provider-confirmed</span><span><i className="recommendation" /> Recommendation</span><span><i className="community" /> Community-sourced</span></div>
    </>
  );
}

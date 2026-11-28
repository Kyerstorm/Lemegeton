export type AtlasSourceKind = "provider" | "recommendation" | "community";

export interface AtlasRelation {
  title: string;
  category: string;
  url: string | null;
  relationType: string;
  source: string;
  sourceKind: AtlasSourceKind;
  provider?: string | null;
  providerId?: string | null;
  evidence?: string | null;
}

export interface AtlasNode {
  id: string;
  title: string;
  category: string;
  url: string | null;
  depth: number;
  provider?: string | null;
  providerId?: string | null;
  imageUrl?: string | null;
  sourceKind?: AtlasSourceKind;
  sourceLabel?: string;
  relationType?: string;
}

export interface AtlasEdge {
  from: string;
  to: string;
  relationType: string;
  sourceLabel: string;
  sourceKind: AtlasSourceKind;
  evidence?: string | null;
}

export interface AtlasResponse {
  root: { title: string; category: string; url: string | null; provider?: string | null; providerId?: string | null };
  relationships: AtlasRelation[];
  graph?: { rootId: string; nodes: AtlasNode[]; edges: AtlasEdge[]; truncated: boolean };
  clusters?: { category: string; nodeIds: string[]; count: number }[];
  path?: { nodes: AtlasNode[]; edges: AtlasEdge[] } | null;
}

export interface AtlasDisplayNode extends AtlasNode {
  x: number;
  y: number;
}

import { Button, Input, Select } from "../../UI";
import type { AtlasNode, AtlasResponse } from "./types";

export function AtlasFilters({
  result, categories, providers, category, setCategory, source, setSource, provider,
  setProvider, providerId, setProviderId, relationship, setRelationship, evidence,
  setEvidence, pathTarget, setPathTarget, visibleNodes, searchAtlas, filters,
  exportBusy, download, zoom, setZoom, loading,
}: {
  result: AtlasResponse;
  categories: string[];
  providers: string[];
  category: string;
  setCategory: (value: string) => void;
  source: string;
  setSource: (value: string) => void;
  provider: string;
  setProvider: (value: string) => void;
  providerId: string;
  setProviderId: (value: string) => void;
  relationship: string;
  setRelationship: (value: string) => void;
  evidence: string;
  setEvidence: (value: string) => void;
  pathTarget: string;
  setPathTarget: (value: string) => void;
  visibleNodes: AtlasNode[];
  searchAtlas: (title?: string, category?: string, url?: string | null, extra?: Record<string, string>) => Promise<void>;
  filters: () => Record<string, string>;
  exportBusy: string;
  download: (format: "json" | "svg" | "png") => Promise<void>;
  zoom: number;
  setZoom: (update: (value: number) => number) => void;
  loading: boolean;
}) {
  const findPath = () => {
    const target = visibleNodes.find(node => node.id === pathTarget);
    if (!target) return;
    void searchAtlas(result.root.title, result.root.category, result.root.url, {
      provider: result.root.provider ?? "",
      provider_id: result.root.providerId ?? "",
      target_title: target.title,
      target_category: target.category,
      target_url: target.url ?? "",
      target_provider: target.provider ?? "",
      target_provider_id: target.providerId ?? "",
      ...filters(),
    });
  };

  return (
    <div className="atlas-tools">
      <Select wrapperClassName="filter-control" label="MEDIA TYPE" value={category} onChange={event => setCategory(event.target.value)} options={[{ value: "All", label: "All categories" }, ...categories.map(item => ({ value: item, label: item.replaceAll("_", " ") }))]} />
      <Select wrapperClassName="filter-control" label="PROVENANCE" value={source} onChange={event => setSource(event.target.value)} options={[{ value: "All", label: "All sources" }, { value: "provider", label: "Provider" }, { value: "recommendation", label: "Recommendation" }, { value: "community", label: "Community" }]} />
      <Select wrapperClassName="filter-control" label="PROVIDER IDENTITY" value={provider} onChange={event => setProvider(event.target.value)} options={[{ value: "All", label: "All providers" }, ...providers.map(item => ({ value: item, label: item }))]} />
      <Input wrapperClassName="filter-control" label="PROVIDER RECORD ID" type="search" value={providerId} onChange={event => setProviderId(event.target.value)} maxLength={128} placeholder="Stable provider ID" />
      <Select wrapperClassName="filter-control" label="RELATIONSHIP" value={relationship} onChange={event => setRelationship(event.target.value)} options={[{ value: "All", label: "All relations" }, { value: "adaptation", label: "Adaptation" }, { value: "franchise", label: "Franchise" }, { value: "sequel", label: "Sequel" }, { value: "prequel", label: "Prequel" }, { value: "related", label: "Related" }, { value: "discussed in", label: "Discussed in" }, { value: "included in", label: "Included in" }]} />
      <Input wrapperClassName="filter-control atlas-evidence-filter" label="EDGE EVIDENCE" type="search" value={evidence} onChange={event => setEvidence(event.target.value)} maxLength={200} placeholder="Search evidence or source text" />
      <div className="atlas-path-tools">
        <Select wrapperClassName="filter-control" label="FIND PATH TO" value={pathTarget} onChange={event => setPathTarget(event.target.value)} options={[{ value: "", label: "Choose a connected node" }, ...visibleNodes.map(node => ({ value: node.id, label: node.title }))]} />
        <Button disabled={!pathTarget || loading} onClick={findPath}>Find shortest path</Button>
      </div>
      <div className="atlas-export-tools">
        <span>EXPORT GRAPH</span>
        <Button disabled={Boolean(exportBusy)} onClick={() => void download("json")}>{exportBusy === "json" ? "Preparing…" : "JSON"}</Button>
        <Button disabled={Boolean(exportBusy)} onClick={() => void download("svg")}>{exportBusy === "svg" ? "Preparing…" : "SVG"}</Button>
        <Button disabled={Boolean(exportBusy)} onClick={() => void download("png")}>{exportBusy === "png" ? "Preparing…" : "PNG"}</Button>
      </div>
      <div className="atlas-zoom">
        <span>ZOOM</span>
        <Button onClick={() => setZoom(value => Math.max(80, value - 10))} disabled={zoom <= 80} aria-label="Zoom out">−</Button>
        <strong>{zoom}%</strong>
        <Button onClick={() => setZoom(value => Math.min(140, value + 10))} disabled={zoom >= 140} aria-label="Zoom in">+</Button>
        <Button onClick={() => setZoom(() => 100)}>Fit</Button>
      </div>
    </div>
  );
}

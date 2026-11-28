import { Icon } from "../../Icons";
import { Button, Card, Empty, SectionHeading, Skeleton, StatusPill } from "../../UI";
import { SectionError } from "../../Feedback/SectionError";
import { ActivityOrb } from "../../Feedback/ActivityOrb";
import type { PageMetadata } from "../../Layout/navigation";
import { AtlasFilters } from "./AtlasFilters";
import { AtlasGraph } from "./AtlasGraph";
import { AtlasDetailPanel } from "./AtlasDetailPanel";
import type { AtlasDisplayNode, AtlasEdge, AtlasNode, AtlasRelation, AtlasResponse } from "./types";

export interface KnowledgeAtlasPageProps {
  selectedPage: Pick<PageMetadata, "eyebrow">;
  guildId: string;
  atlasResult: AtlasResponse | null;
  atlasTitle: string;
  setAtlasTitle: (value: string) => void;
  atlasCategory: string;
  setAtlasCategory: (value: string) => void;
  atlasLoading: boolean;
  atlasError: string;
  searchAtlas: (title?: string, mediaCategory?: string, mediaUrl?: string | null, extra?: Record<string, string>) => Promise<void>;
  atlasNodes: AtlasDisplayNode[];
  atlasVisibleEdges: AtlasEdge[];
  atlasCategories: string[];
  atlasProviders: string[];
  atlasCategoryFilter: string;
  setAtlasCategoryFilter: (value: string) => void;
  atlasSourceFilter: string;
  setAtlasSourceFilter: (value: string) => void;
  atlasProviderFilter: string;
  setAtlasProviderFilter: (value: string) => void;
  atlasProviderIdFilter: string;
  setAtlasProviderIdFilter: (value: string) => void;
  atlasRelationshipFilter: string;
  setAtlasRelationshipFilter: (value: string) => void;
  atlasEvidenceFilter: string;
  setAtlasEvidenceFilter: (value: string) => void;
  atlasPathTarget: string;
  setAtlasPathTarget: (value: string) => void;
  atlasVisibleNodes: AtlasNode[];
  atlasFilters: () => Record<string, string>;
  atlasExportBusy: string;
  downloadAtlas: (format: "json" | "svg" | "png") => Promise<void>;
  atlasZoom: number;
  setAtlasZoom: (update: (value: number) => number) => void;
  atlasNodePositions: Map<string, { x: number; y: number }>;
  atlasVisibleRelationships: AtlasRelation[];
}

export function KnowledgeAtlasPage(props: KnowledgeAtlasPageProps) {
  const { selectedPage, guildId, atlasResult, atlasTitle, setAtlasTitle, atlasCategory, setAtlasCategory, atlasLoading, atlasError, searchAtlas, atlasNodes, atlasVisibleEdges, atlasCategories, atlasProviders, atlasCategoryFilter, setAtlasCategoryFilter, atlasSourceFilter, setAtlasSourceFilter, atlasProviderFilter, setAtlasProviderFilter, atlasProviderIdFilter, setAtlasProviderIdFilter, atlasRelationshipFilter, setAtlasRelationshipFilter, atlasEvidenceFilter, setAtlasEvidenceFilter, atlasPathTarget, setAtlasPathTarget, atlasVisibleNodes, atlasFilters, atlasExportBusy, downloadAtlas, atlasZoom, setAtlasZoom, atlasNodePositions, atlasVisibleRelationships } = props;

  return (
    <section className="page">
      <SectionHeading eyebrow={selectedPage.eyebrow} title={<>Knowledge <span>Atlas.</span></>} subtitle="Follow confirmed provider relationships and server-approved community links. Select a connected node to expand another local neighborhood." actions={<StatusPill ok={Boolean(atlasResult)}>{atlasResult ? atlasResult.relationships.length + " CONNECTIONS" : "GUILD-SCOPED"}</StatusPill>} />
      <Card eyebrow="FIND A MEDIA NODE" title="Explore a title">
        <form className="atlas-search" onSubmit={event => { event.preventDefault(); void searchAtlas(); }}>
          <label className="atlas-search-title">
            <span>MEDIA TITLE</span>
            <input type="search" value={atlasTitle} onChange={event => setAtlasTitle(event.target.value)} maxLength={256} placeholder="Search a title, for example Frieren" autoComplete="off" required />
          </label>
          <label className="filter-control atlas-category">
            <span>CATEGORY</span>
            <select value={atlasCategory} onChange={event => setAtlasCategory(event.target.value)}>
              <option value="ANIME">Anime</option><option value="MANGA">Manga</option><option value="LIGHT_NOVEL">Light novel</option><option value="WEBNOVEL">Webnovel</option><option value="BOOK">Book</option><option value="MOVIE">Film</option><option value="TV">Television</option><option value="GAME">Video game</option><option value="CREATOR">Creator</option><option value="FRANCHISE">Franchise</option><option value="ARCHIVE_ENTRY">Archive entry</option><option value="ARCHIVE_COLLECTION">Archive collection</option><option value="DISCUSSION">Discussion</option><option value="ACTIVITY">Community activity</option>
            </select>
          </label>
          <Button tone="primary" type="submit" disabled={atlasLoading || !guildId}>{atlasLoading ? "Mapping…" : <>Explore connections <Icon name="arrow-up-right" size={13} /></>}</Button>
        </form>
        {atlasError ? <SectionError message={atlasError} onRetry={() => { void searchAtlas(atlasTitle, atlasCategory); }} /> : null}
      </Card>
      {atlasLoading && !atlasResult ? (
        <Card eyebrow="GRAPH PROJECTION" title="Building the local graph">
          <div className="atlas-loading-status" role="status" aria-live="polite">
            <ActivityOrb state="searching" size={20} label="Searching provider metadata" />
            <span>Searching supported sources and mapping confirmed relationships.</span>
          </div>
          <div className="atlas-graph-skeleton" aria-hidden="true"><Skeleton width={122} height={54} radius={12} /><div className="atlas-skeleton-orbit"><Skeleton width={95} height={54} radius={10} /><Skeleton width={112} height={54} radius={10} /><Skeleton width={84} height={54} radius={10} /></div><div className="atlas-skeleton-footer"><Skeleton width="72%" height={8} /><Skeleton width="48%" height={8} /></div></div>
        </Card>
      ) : null}
      {atlasResult ? (
        <>
          <Card eyebrow={"MULTI-HOP GRAPH / " + String(atlasNodes.length + 1) + " NODES"} title={atlasResult.root.title} index={atlasResult.root.category}>
            <p className="atlas-explainer">Explore up to two recorded relationship steps from this title. Every community-sourced edge is looked up within the selected server; provider facts and recommendations remain separately labelled.</p>
            <AtlasFilters
              result={atlasResult} categories={atlasCategories} providers={atlasProviders}
              category={atlasCategoryFilter} setCategory={setAtlasCategoryFilter}
              source={atlasSourceFilter} setSource={setAtlasSourceFilter}
              provider={atlasProviderFilter} setProvider={setAtlasProviderFilter}
              providerId={atlasProviderIdFilter} setProviderId={setAtlasProviderIdFilter}
              relationship={atlasRelationshipFilter} setRelationship={setAtlasRelationshipFilter}
              evidence={atlasEvidenceFilter} setEvidence={setAtlasEvidenceFilter}
              pathTarget={atlasPathTarget} setPathTarget={setAtlasPathTarget}
              visibleNodes={atlasVisibleNodes} searchAtlas={searchAtlas} filters={atlasFilters}
              exportBusy={atlasExportBusy} download={downloadAtlas} zoom={atlasZoom}
              setZoom={setAtlasZoom} loading={atlasLoading}
            />
            <AtlasGraph
              result={atlasResult} nodes={atlasNodes} edges={atlasVisibleEdges}
              positions={atlasNodePositions} zoom={atlasZoom} loading={atlasLoading}
              onOpenNode={node => { void searchAtlas(node.title, node.category, node.url, { provider: node.provider ?? "", provider_id: node.providerId ?? "" }); }}
              onSelectCategory={setAtlasCategoryFilter}
            />
          </Card>
          <AtlasDetailPanel
            relationships={atlasVisibleRelationships}
            loading={atlasLoading}
            onOpenNode={relation => { void searchAtlas(relation.title, relation.category, relation.url); }}
          />
        </>
      ) : !atlasLoading ? (
        <Card eyebrow="GRAPH PROJECTION" title="Start with a media title"><Empty>The Atlas shows direct recorded relationships for the selected title. Community relationships stay scoped to this server.</Empty></Card>
      ) : null}
    </section>
  );
}

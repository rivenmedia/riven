import type { MediaNode } from '../item-detail/SimilarRecommendations';
import type { ExploreNode } from './types';
import { DiscoverItemContent } from '../discovery/DiscoverItemContent';

export type ExploreDetailPanelProps = {
  originLabel: string;
  history: ExploreNode[];
  detailNode: ExploreNode | null;
  onBreadcrumbClick: (index: number) => void;
  selectNode: (node: ExploreNode, updateHistory?: boolean) => void;
  fetchResults: () => void;
};

function mediaToExplore(n: MediaNode): ExploreNode {
  return {
    kind: n.kind,
    id: n.id,
    label: n.label,
    source: n.kind === 'person' ? 'tmdb' : n.source || 'tmdb',
  };
}

export function ExploreDetailPanel({
  originLabel,
  history,
  detailNode,
  onBreadcrumbClick,
  selectNode,
  fetchResults,
}: ExploreDetailPanelProps) {
  const k = detailNode?.kind;
  const validKind = k === 'movie' || k === 'tv' || k === 'person';

  return (
    <>
      <aside className="explore-panel" data-slot="detail-panel">
        <div className="explore-breadcrumbs">
          {[{ label: originLabel, kind: 'origin' }, ...history].map((node, index) => {
            const isActive = index === history.length;
            return (
            <button
              key={index}
              type="button"
              className={`pill pill--${node.kind || 'origin'}${isActive ? ' pill--active' : ''}`}
              onClick={() => onBreadcrumbClick(index)}
              aria-current={isActive ? 'page' : undefined}
            >
              {node.label || (node.kind === 'origin' ? originLabel : `${node.kind} ${'id' in node ? node.id : ''}`)}
            </button>
          )})}
        </div>
      </aside>
      {!detailNode && (
        <div className="explore-detail explore-detail--empty">
          <p className="muted">Loading…</p>
        </div>
      )}
      {detailNode && !validKind && (
        <div className="explore-detail explore-detail--empty">
          <p className="muted">This item type is not supported in the graph.</p>
        </div>
      )}
      {detailNode && validKind && (
        <div
          className="explore-detail"
          key={`${detailNode.source}|${detailNode.kind}|${detailNode.id}`}
        >
          <DiscoverItemContent
            source={detailNode.source as 'tmdb' | 'tvdb'}
            kind={detailNode.kind as 'movie' | 'tv' | 'person'}
            id={detailNode.id}
            onNavigateToItem={(n) => selectNode(n, true)}
            onNavigateFromMedia={(n) => selectNode(mediaToExplore(n), true)}
            onBackFromPerson={() => onBreadcrumbClick(Math.max(0, history.length - 1))}
            onAfterLibraryAction={fetchResults}
          />
        </div>
      )}
    </>
  );
}

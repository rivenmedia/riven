import type { ExploreNode } from './types';
import { ExploreDetailPerson } from './ExploreDetailPerson';
import { ExploreDetailTvdb } from './ExploreDetailTvdb';
import { ExploreDetailTmdbMediaPanel } from './ExploreDetailTmdb';
import { CastCrew } from '../item-detail/CastCrew';
import { SimilarRecommendations } from '../item-detail/SimilarRecommendations';

export type ExploreDetailPanelProps = {
  originLabel: string;
  history: ExploreNode[];
  detailNode: ExploreNode | null;
  detailLoading: boolean;
  detailData: any;
  onBreadcrumbClick: (index: number) => void;
  selectNode: (node: ExploreNode, updateHistory?: boolean) => void;
  addItemToLibrary: (item: any, seasonNumbers?: number[] | null) => Promise<boolean>;
  fetchResults: () => void;
};

export function ExploreDetailPanel({
  originLabel,
  history,
  detailNode,
  detailLoading,
  detailData,
  onBreadcrumbClick,
  selectNode,
  addItemToLibrary,
  fetchResults,
}: ExploreDetailPanelProps) {
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
          <p className="muted">Select a card to inspect cast, recommendations, and linked entries.</p>
        </div>
      )}
      {detailLoading && (
        <div className="explore-detail explore-detail--empty">
          <p className="muted">Loading details…</p>
        </div>
      )}
      {detailData?.error && (
        <div className="explore-detail explore-detail--empty">
          <p className="muted">{detailData.error}</p>
        </div>
      )}
      {detailNode && !detailLoading && !detailData && (
        <div className="explore-detail explore-detail--empty">
          <p className="muted">No details available for this node.</p>
        </div>
      )}
      {detailData?.kind === 'person' && (
        <ExploreDetailPerson
          person={detailData.person}
          credits={detailData.credits}
          onSelectNode={selectNode}
          onBack={() => onBreadcrumbClick(Math.max(0, history.length - 1))}
        />
      )}
      {detailData?.kind === 'tvdb-tv' && (
        <ExploreDetailTvdb
          series={detailData.media}
          node={detailNode!}
          onAdd={addItemToLibrary}
          onOpen={() => {
            if (detailData.media.library_item_id) window.location.hash = `#/item/${detailData.media.library_item_id}`;
          }}
          onRefresh={fetchResults}
          onReselect={() => detailNode && selectNode(detailNode, false)}
        />
      )}
      {(detailData?.kind === 'movie' || detailData?.kind === 'tv') && (
        <>
          <ExploreDetailTmdbMediaPanel
            media={detailData.media}
            recommendations={detailData.recommendations}
            similar={detailData.similar}
            kind={detailData.kind}
            node={detailNode!}
            onAdd={addItemToLibrary}
            onOpen={() => {
              if (detailData.media.library_item_id)
                window.location.hash = `#/item/${detailData.media.library_item_id}`;
            }}
            onRefresh={fetchResults}
            onReselect={() => detailNode && selectNode(detailNode, false)}
            onPersonSelect={(p) => selectNode({ kind: 'person', id: p.id, label: p.name, source: 'tmdb' }, true)}
            onMediaSelect={(node) => selectNode(node, true)}
          />
          <CastCrew credits={detailData.media?.credits ?? null} onPersonSelect={(p) => selectNode({ kind: 'person', id: p.id, label: p.name, source: 'tmdb' }, true)} />
          <SimilarRecommendations
            data={{ recommendations: detailData.recommendations ?? [], similar: detailData.similar ?? [] }}
            onMediaSelect={(node) => selectNode(node, true)}
          />
        </>
      )}
    </>
  );
}

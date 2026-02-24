import type { ExploreNode } from './types';
import { ExploreDetailPerson } from './ExploreDetailPerson';
import { ExploreDetailTvdb } from './ExploreDetailTvdb';
import { ExploreDetailTmdb } from './ExploreDetailTmdb';

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
    <aside className="explore-panel" data-slot="detail-panel">
      <div className="section-head">
        <h2>Metadata Graph</h2>
      </div>
      <div className="explore-breadcrumbs">
        {[{ label: originLabel, kind: 'origin' }, ...history].map((node, index) => (
          <button
            key={index}
            type="button"
            className={`pill pill--${node.kind || 'origin'}`}
            onClick={() => onBreadcrumbClick(index)}
          >
            {node.label || (node.kind === 'origin' ? originLabel : `${node.kind} ${'id' in node ? node.id : ''}`)}
          </button>
        ))}
      </div>
      <div className="explore-detail">
        {!detailNode && (
          <p className="muted">Select a card to inspect cast, recommendations, and linked entries.</p>
        )}
        {detailLoading && <p className="muted">Loading details…</p>}
        {detailData?.error && <p className="muted">{detailData.error}</p>}
        {detailNode && !detailLoading && !detailData && !detailData?.error && (
          <p className="muted">No details available for this node.</p>
        )}
        {detailData?.kind === 'person' && (
          <ExploreDetailPerson
            person={detailData.person}
            credits={detailData.credits}
            onSelectNode={selectNode}
            onBack={() => history[0] && selectNode(history[0], false)}
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
          <ExploreDetailTmdb
            media={detailData.media}
            recommendations={detailData.recommendations}
            similar={detailData.similar}
            kind={detailData.kind}
            node={detailNode!}
            onAdd={addItemToLibrary}
            onOpen={() => {
              if (detailData.media.library?.library_item_id)
                window.location.hash = `#/item/${detailData.media.library.library_item_id}`;
            }}
            onRefresh={fetchResults}
            onReselect={() => detailNode && selectNode(detailNode, false)}
            onPersonSelect={(p) => selectNode({ kind: 'person', id: p.id, label: p.name, source: 'tmdb' }, true)}
            onMediaSelect={(node) => selectNode(node, true)}
          />
        )}
      </div>
    </aside>
  );
}

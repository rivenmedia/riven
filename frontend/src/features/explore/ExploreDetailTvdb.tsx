import { useState } from 'react';
import { EntityHeader } from '../item-detail/EntityHeader';
import { tvdbSeriesToEntityHeaderData } from '../item-detail/discoveryEntityHeaderMappers';
import { DetailViewActionsToolbar } from '../../shared/ui/DetailViewActionsToolbar';
import type { ExploreNode } from './types';

export type ExploreDetailTvdbProps = {
  series: any;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void | Promise<void>;
};

export function ExploreDetailTvdb({ series, node, onAdd, onOpen, onRefresh, onReselect }: ExploreDetailTvdbProps) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const [addPending, setAddPending] = useState(false);
  const seasons = (series.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const inLibrary = series.in_library && series.library_item_id;
  const headerData = tvdbSeriesToEntityHeaderData(series, String(node.id));

  const handleAdd = async () => {
    if (inLibrary) {
      onOpen();
      return;
    }
    setAddPending(true);
    try {
      const seasonNumbers =
        selectedSeasons.size > 0 && selectedSeasons.size < seasons.length
          ? Array.from(selectedSeasons).sort((a, b) => a - b)
          : null;
      const ok = await onAdd(
        { ...series, media_type: 'tv', id: node.id, indexer: 'tvdb', tvdb_id: node.id },
        seasonNumbers,
      );
      if (ok) {
        onRefresh();
        await onReselect();
      }
    } finally {
      setAddPending(false);
    }
  };

  return (
    <section className="panel">
      <div className="item-detail-panel item-detail-panel--overview">
        <EntityHeader data={headerData} />
        <DetailViewActionsToolbar aria-label="Discover — add or open in library (TVDB)">
          <button
            type="button"
            className={`btn btn--small btn--with-spinner ${inLibrary ? 'btn--secondary' : 'btn--primary'}`}
            onClick={handleAdd}
            disabled={addPending}
            aria-busy={addPending}
          >
            {addPending && !inLibrary ? (
              <>
                <span className="ui-spinner" aria-hidden />
                Adding…
              </>
            ) : inLibrary ? (
              'Open Library Item'
            ) : (
              'Add to Library'
            )}
          </button>
        </DetailViewActionsToolbar>
      </div>
      {!inLibrary && seasons.length > 0 && (
        <div className="season-selector">
          <div className="season-selector__header">
            <span className="season-selector__label">
              Seasons: {selectedSeasons.size} of {seasons.length} selected
            </span>
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={() =>
                setSelectedSeasons((prev) =>
                  prev.size === seasons.length ? new Set() : new Set(seasons.map((s: any) => s.season_number ?? s.number ?? 0)),
                )
              }
            >
              Toggle All
            </button>
          </div>
          <div className="season-selector__list">
            {seasons.map((s: any) => {
              const num = s.season_number ?? s.number ?? 0;
              return (
                <label key={num} className="season-selector__item">
                  <input
                    type="checkbox"
                    checked={selectedSeasons.has(num)}
                    onChange={(e) =>
                      setSelectedSeasons((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(num);
                        else next.delete(num);
                        return next;
                      })
                    }
                  />
                  <span>
                    {s.name || `Season ${num}`}
                    {(s.episode_count ?? s.episodes?.length) ? ` (${s.episode_count ?? s.episodes?.length} eps)` : ''}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

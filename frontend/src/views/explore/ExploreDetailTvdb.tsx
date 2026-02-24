import { useState } from 'react';
import { formatYear } from '../../services/utils';
import type { ExploreNode } from './types';

export type ExploreDetailTvdbProps = {
  series: any;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void;
};

export function ExploreDetailTvdb({ series, node, onAdd, onOpen, onRefresh, onReselect }: ExploreDetailTvdbProps) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const seasons = (series.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const posterUrl = series.poster_path
    ? series.poster_path.startsWith('http')
      ? series.poster_path
      : `https://image.tmdb.org/t/p/w500${series.poster_path}`
    : '';
  const inLibrary = series.in_library && series.library_item_id;

  const handleAdd = async () => {
    if (inLibrary) {
      onOpen();
      return;
    }
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
      onReselect();
    }
  };

  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={series.title || 'series'} />}
        <div>
          <h3>{series.title || series.name || 'Unknown'}</h3>
          <p className="muted">{[formatYear(series), series.library_state].filter(Boolean).join(' · ') || '—'}</p>
          <p className="muted">{series.overview || 'No summary available.'}</p>
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
          <div className="toolbar">
            <button type="button" className="btn btn--primary btn--small" onClick={handleAdd}>
              {inLibrary ? 'Open Library Item' : 'Add to Library'}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

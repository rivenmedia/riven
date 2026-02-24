import { useState } from 'react';
import { formatYear } from '../../services/utils';
import { CastCrew } from '../../ui/panels/CastCrew';
import { SimilarRecommendations } from '../../ui/panels/SimilarRecommendations';
import type { ExploreNode } from './types';

export type ExploreDetailTmdbProps = {
  media: any;
  recommendations: any[];
  similar: any[];
  kind: string;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void;
  onPersonSelect: (p: { id: string; name: string }) => void;
  onMediaSelect: (node: ExploreNode) => void;
};

export function ExploreDetailTmdb({
  media,
  recommendations,
  similar,
  kind,
  onAdd,
  onOpen,
  onRefresh,
  onReselect,
  onPersonSelect,
  onMediaSelect,
}: ExploreDetailTmdbProps) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const lib = media.library;
  const isInLibrary = lib?.in_library && lib?.library_item_id;
  const seasons = (media.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const posterUrl =
    media.poster_path || media.profile_path
      ? (media.poster_path?.startsWith('http') ? media.poster_path : `https://image.tmdb.org/t/p/w500${media.poster_path || media.profile_path}`)
      : '';

  const handleAdd = async () => {
    if (isInLibrary) {
      onOpen();
      return;
    }
    const seasonNumbers =
      kind === 'tv' && selectedSeasons.size > 0 && selectedSeasons.size < seasons.length
        ? Array.from(selectedSeasons).sort((a, b) => a - b)
        : null;
    const ok = await onAdd({ ...media, media_type: kind }, seasonNumbers);
    if (ok) {
      onRefresh();
      onReselect();
    }
  };

  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={media.title || media.name || 'media'} />}
        <div>
          <h3>{media.title || media.name || 'Unknown'}</h3>
          <p className="muted">
            {[kind.toUpperCase(), formatYear(media), media.vote_average ? `Rating ${Number(media.vote_average).toFixed(1)}` : null, lib?.library_state]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>
          <p className="muted">{media.overview || media.biography || 'No summary available.'}</p>
          {kind === 'tv' && !isInLibrary && seasons.length > 0 && (
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
              {isInLibrary ? 'Open Library Item' : 'Add to Library'}
            </button>
          </div>
        </div>
      </div>
      <CastCrew credits={media.credits ?? null} onPersonSelect={onPersonSelect} />
      <SimilarRecommendations data={{ recommendations, similar }} onMediaSelect={onMediaSelect} />
    </section>
  );
}

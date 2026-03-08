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

/** Media info panel only; use with CastCrew + SimilarRecommendations as siblings in ExploreDetailPanel. */
export function ExploreDetailTmdbMediaPanel({
  media,
  kind,
  onAdd,
  onOpen,
  onRefresh,
  onReselect,
}: Pick<
  ExploreDetailTmdbProps,
  'media' | 'kind' | 'onAdd' | 'onOpen' | 'onRefresh' | 'onReselect'
>) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const isInLibrary = media.in_library && media.library_item_id;
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
            {[kind.toUpperCase(), formatYear(media), media.library_state]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>
          <p className="muted detail-head__synopsis">{media.overview || media.biography || 'No summary available.'}</p>
          {kind === 'tv' && (
            <div className="detail-panel-meta">
              <dl className="detail-panel-meta__list">
                {Array.isArray(media.networks) && media.networks.length > 0 && (
                  <>
                    <dt className="detail-panel-meta__label">Network</dt>
                    <dd className="detail-panel-meta__value">
                      {media.networks.map((n: any) => n?.name).filter(Boolean).join(', ')}
                    </dd>
                  </>
                )}
                {media.number_of_seasons != null && (
                  <>
                    <dt className="detail-panel-meta__label">Seasons</dt>
                    <dd className="detail-panel-meta__value">
                      {media.number_of_seasons} season{media.number_of_seasons !== 1 ? 's' : ''}
                    </dd>
                  </>
                )}
                {media.number_of_episodes != null && (
                  <>
                    <dt className="detail-panel-meta__label">Episodes</dt>
                    <dd className="detail-panel-meta__value">
                      {media.number_of_episodes} episode{media.number_of_episodes !== 1 ? 's' : ''}
                    </dd>
                  </>
                )}
                {media.first_air_date && (
                  <>
                    <dt className="detail-panel-meta__label">First aired</dt>
                    <dd className="detail-panel-meta__value">{media.first_air_date}</dd>
                  </>
                )}
                {media.last_air_date && (
                  <>
                    <dt className="detail-panel-meta__label">Ended</dt>
                    <dd className="detail-panel-meta__value">{media.last_air_date}</dd>
                  </>
                )}
              </dl>
              <div className="media-metadata-chips">
                {Array.isArray(media.genres) &&
                  media.genres.map((g: any) =>
                    g?.name ? (
                      <span key={g.name} className="legend-chip legend-chip--genre">
                        {g.name}
                      </span>
                    ) : null,
                  )}
                {typeof media.vote_average === 'number' && !Number.isNaN(media.vote_average) && (
                  <span className="legend-chip legend-chip--rating">
                    ★ {media.vote_average.toFixed(1)}
                    {typeof media.vote_count === 'number' && media.vote_count > 0
                      ? ` (${media.vote_count} votes)`
                      : ''}
                  </span>
                )}
              </div>
            </div>
          )}
          {kind === 'movie' && (
            <div className="detail-panel-meta">
              <dl className="detail-panel-meta__list">
                {media.runtime != null && media.runtime > 0 && (
                  <>
                    <dt className="detail-panel-meta__label">Runtime</dt>
                    <dd className="detail-panel-meta__value">{media.runtime} min</dd>
                  </>
                )}
                {media.release_date && (
                  <>
                    <dt className="detail-panel-meta__label">Release date</dt>
                    <dd className="detail-panel-meta__value">{media.release_date}</dd>
                  </>
                )}
              </dl>
              <div className="media-metadata-chips">
                {Array.isArray(media.genres) &&
                  media.genres.map((g: any) =>
                    g?.name ? (
                      <span key={g.name} className="legend-chip legend-chip--genre">
                        {g.name}
                      </span>
                    ) : null,
                  )}
                {typeof media.vote_average === 'number' && !Number.isNaN(media.vote_average) && (
                  <span className="legend-chip legend-chip--rating">
                    ★ {media.vote_average.toFixed(1)}
                    {typeof media.vote_count === 'number' && media.vote_count > 0
                      ? ` (${media.vote_count} votes)`
                      : ''}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="toolbar">
        <button type="button" className="btn btn--primary btn--small" onClick={handleAdd}>
          {isInLibrary ? 'Open Library Item' : 'Add to Library'}
        </button>
      </div>
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
    </section>
  );
}

export function ExploreDetailTmdb(props: ExploreDetailTmdbProps) {
  const { media, recommendations, similar, onPersonSelect, onMediaSelect } = props;
  return (
    <>
      <ExploreDetailTmdbMediaPanel {...props} />
      <CastCrew credits={media.credits ?? null} onPersonSelect={onPersonSelect} />
      <SimilarRecommendations data={{ recommendations, similar }} onMediaSelect={onMediaSelect} />
    </>
  );
}

/**
 * TMDB tv season JSON from GET /tmdb/tv/:id/season/:n
 */
export function TmdbSeasonDetailsPanel({ data }: { data: Record<string, unknown> | null }) {
  if (!data || typeof data !== 'object') return null;

  const overview = (data.overview as string | undefined)?.trim();
  const name = (data.name as string | undefined)?.trim();
  const airDate = (data.air_date as string | undefined)?.trim();
  const epCount = data.episode_count as number | undefined;
  const vote = data.vote_average as number | undefined;
  const votes = data.vote_count as number | undefined;

  if (!overview && !name && !airDate && epCount == null && vote == null) return null;

  return (
    <div className="panel tmdb-season-details-panel">
      <div className="section-head">
        <h3>TMDB (season)</h3>
      </div>
      <div className="media-metadata-chips">
        {name && <span className="legend-chip">{name}</span>}
        {airDate && <span className="legend-chip legend-chip--date">{airDate}</span>}
        {typeof epCount === 'number' && (
          <span className="legend-chip">
            {epCount} episode{epCount !== 1 ? 's' : ''}
          </span>
        )}
        {typeof vote === 'number' && !Number.isNaN(vote) && (
          <span className="legend-chip legend-chip--rating">
            ★ {vote.toFixed(1)}
            {typeof votes === 'number' && votes > 0 ? ` (${votes} votes)` : ''}
          </span>
        )}
      </div>
      {overview ? <p className="tmdb-season-details-panel__overview">{overview}</p> : null}
    </div>
  );
}

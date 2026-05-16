/**
 * Read-only TVDB season extended payload from GET /tvdb/season/:id or series/season routes.
 */
export function TvdbSeasonDetailsPanel({ data }: { data: Record<string, unknown> | null }) {
  if (!data || typeof data !== 'object') return null;

  const translations = (data.translations as Array<{ overview?: string; language?: string }>) || [];
  const overview =
    translations.find((t) => t.overview && String(t.overview).trim())?.overview?.trim() || '';
  const name = (data.name as string | undefined)?.trim();
  const number = data.number as number | undefined;
  const year = (data.year as string | undefined)?.trim();
  const image = data.image as string | undefined;
  const seriesId = data.seriesId as number | undefined;
  const episodes = (data.episodes as unknown[])?.length;

  if (!overview && !name && number == null && !year && !image && seriesId == null && episodes == null) {
    return null;
  }

  return (
    <div className="panel tvdb-season-details-panel">
      <div className="section-head">
        <h3>TVDB (season)</h3>
      </div>
      {image && (
        <div className="tvdb-season-details-panel__poster">
          <img src={image} alt="" loading="lazy" />
        </div>
      )}
      <div className="media-metadata-chips">
        {name && <span className="legend-chip">{name}</span>}
        {number != null && <span className="legend-chip">Season {number}</span>}
        {year && <span className="legend-chip">{year}</span>}
        {typeof episodes === 'number' && (
          <span className="legend-chip">
            {episodes} episode{episodes !== 1 ? 's' : ''} (TVDB list)
          </span>
        )}
        {seriesId != null && <span className="legend-chip">TVDB series {seriesId}</span>}
      </div>
      {overview ? <p className="tvdb-season-details-panel__overview">{overview}</p> : null}
    </div>
  );
}

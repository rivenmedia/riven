const usd0 = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

function formatTmdbMoney(n: unknown): string | null {
  if (typeof n !== 'number' || n <= 0) return null;
  return usd0.format(n);
}

export function TmdbDetailsPanel({
  tmdbData,
  itemType,
  showCollectionLine,
}: {
  tmdbData: Record<string, unknown>;
  itemType: string;
  /** When the collection strip shows the set name (movies), skip duplicating the line here. */
  showCollectionLine: boolean;
}) {
  const tagline = tmdbData.tagline as string | undefined;
  const runtime = tmdbData.runtime as number | undefined;
  const releaseDate = (tmdbData.release_date || tmdbData.first_air_date) as string | undefined;
  const genres = tmdbData.genres as { name?: string }[] | undefined;
  const productionCompanies = tmdbData.production_companies as { name?: string }[] | undefined;
  const voteAverage = tmdbData.vote_average as number | undefined;
  const voteCount = tmdbData.vote_count as number | undefined;
  const belongsToCollection = tmdbData.belongs_to_collection as { name?: string } | undefined;
  const lastAirDate = tmdbData.last_air_date as string | undefined;
  const numSeasons = tmdbData.number_of_seasons as number | undefined;
  const numEpisodes = tmdbData.number_of_episodes as number | undefined;
  const status = tmdbData.status as string | undefined;
  const budget = itemType === 'movie' ? formatTmdbMoney(tmdbData.budget) : null;
  const revenue = itemType === 'movie' ? formatTmdbMoney(tmdbData.revenue) : null;
  const homepage = tmdbData.homepage as string | undefined;
  const origLang = tmdbData.original_language as string | undefined;
  const countries = tmdbData.production_countries as { name?: string }[] | undefined;
  const langs = tmdbData.spoken_languages as
    | { english_name?: string; name?: string; iso_639_1?: string }[]
    | undefined;
  const keyBlob = tmdbData.keywords as
    | { keywords?: { id: number; name: string }[]; results?: { id: number; name: string }[] }
    | undefined;
  const keywordList = keyBlob?.keywords ?? keyBlob?.results ?? [];
  const videos = (tmdbData.videos as { results?: { key?: string; name?: string; type?: string; site?: string }[] } | undefined)
    ?.results;
  const youtubeVideos = Array.isArray(videos)
    ? videos.filter((v) => v?.site === 'YouTube' && v?.key).slice(0, 8)
    : [];
  const tmdbId = tmdbData.id != null ? String(tmdbData.id) : null;

  const hasContent =
    tagline ||
    (typeof runtime === 'number' && runtime > 0) ||
    releaseDate ||
    (Array.isArray(genres) && genres.length) ||
    (Array.isArray(productionCompanies) && productionCompanies.length) ||
    (typeof voteAverage === 'number' && !Number.isNaN(voteAverage)) ||
    (showCollectionLine && Boolean(belongsToCollection?.name)) ||
    (numSeasons != null && itemType === 'show') ||
    (status && status.length > 0) ||
    budget ||
    revenue ||
    (typeof homepage === 'string' && homepage.length > 0) ||
    (origLang && origLang.length > 0) ||
    (Array.isArray(countries) && countries.some((c) => c?.name)) ||
    (Array.isArray(langs) && langs.length > 0) ||
    keywordList.length > 0 ||
    youtubeVideos.length > 0;

  if (!hasContent) return null;

  return (
    <div className="panel tmdb-details-panel">
      <div className="section-head">
        <h3>Details</h3>
      </div>
      {showCollectionLine && belongsToCollection?.name && (
        <p className="tmdb-details-collection">
          <strong>Part of collection:</strong> {belongsToCollection.name}
        </p>
      )}
      {tagline && <p className="tmdb-details-tagline">{tagline}</p>}
      <div className="media-metadata-chips">
        {typeof runtime === 'number' && runtime > 0 && (
          <span className="legend-chip legend-chip--runtime">{runtime} min</span>
        )}
        {releaseDate && (
          <span className="legend-chip legend-chip--date">{releaseDate}</span>
        )}
        {status && <span className="legend-chip">{status}</span>}
        {numSeasons != null && itemType === 'show' && (
          <span className="legend-chip legend-chip--seasons">
            {numSeasons} season{numSeasons !== 1 ? 's' : ''}
          </span>
        )}
        {numEpisodes != null && itemType === 'show' && (
          <span className="legend-chip legend-chip--episodes">
            {numEpisodes} episode{numEpisodes !== 1 ? 's' : ''}
          </span>
        )}
        {lastAirDate && itemType === 'show' && (
          <span className="legend-chip legend-chip--ended">Ended {lastAirDate}</span>
        )}
        {Array.isArray(genres) &&
          genres.map((g) =>
            g?.name ? (
              <span key={g.name} className="legend-chip legend-chip--genre">
                {g.name}
              </span>
            ) : null,
          )}
        {typeof voteAverage === 'number' && !Number.isNaN(voteAverage) && (
          <span className="legend-chip legend-chip--rating">
            ★ {voteAverage.toFixed(1)}
            {typeof voteCount === 'number' && voteCount > 0 ? ` (${voteCount} votes)` : ''}
          </span>
        )}
      </div>
      {(budget || revenue) && (
        <dl className="tmdb-details-facts">
          {budget && (
            <>
              <dt>Budget</dt>
              <dd>{budget}</dd>
            </>
          )}
          {revenue && (
            <>
              <dt>Revenue</dt>
              <dd>{revenue}</dd>
            </>
          )}
        </dl>
      )}
      {origLang && (
        <p className="tmdb-details-fact-line">
          <strong>Original language:</strong> {origLang}
        </p>
      )}
      {Array.isArray(countries) && countries.filter((c) => c?.name).length > 0 && (
        <p className="tmdb-details-fact-line">
          <strong>Production countries:</strong>{' '}
          {countries.map((c) => c.name).filter(Boolean).join(', ')}
        </p>
      )}
      {Array.isArray(langs) && langs.length > 0 && (
        <p className="tmdb-details-fact-line">
          <strong>Languages:</strong>{' '}
          {langs.map((l) => l.english_name || l.name).filter(Boolean).join(', ')}
        </p>
      )}
      {typeof homepage === 'string' && homepage.length > 0 && (
        <p className="tmdb-details-fact-line tmdb-details-homepage">
          <strong>Homepage:</strong>{' '}
          <a href={homepage} target="_blank" rel="noopener noreferrer">
            {homepage.replace(/^https?:\/\//, '')}
          </a>
        </p>
      )}
      {keywordList.length > 0 && (
        <div className="tmdb-details-keywords">
          <div className="tmdb-details-keywords__label">Keywords</div>
          <div className="media-metadata-chips">
            {keywordList.map((k) => (
              <span key={k.id} className="legend-chip legend-chip--keyword">
                {k.name}
              </span>
            ))}
          </div>
        </div>
      )}
      {youtubeVideos.length > 0 && (
        <div className="tmdb-details-videos">
          <div className="tmdb-details-videos__label">
            {youtubeVideos.length === 1 ? 'Video' : 'Videos'}
          </div>
          <ul className="tmdb-details-videos__list">
            {youtubeVideos.map((v, i) => {
              const title = (v.name || v.type || 'YouTube clip').trim();
              const typeLabel =
                v.type && v.name && v.type.trim() !== v.name.trim() ? v.type : null;
              return (
                <li key={v.key || i} className="tmdb-details-videos__item">
                  <a
                    className="tmdb-details-videos__link"
                    href={`https://www.youtube.com/watch?v=${encodeURIComponent(String(v.key))}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="tmdb-details-videos__title">{title}</span>
                  </a>
                  {typeLabel && (
                    <span className="tmdb-details-videos__type">{typeLabel}</span>
                  )}
                </li>
              );
            })}
          </ul>
          {tmdbId && (videos?.length || 0) > youtubeVideos.length && (
            <a
              className="tmdb-details-tmdb-link muted"
              href={`https://www.themoviedb.org/${itemType === 'show' ? 'tv' : 'movie'}/${tmdbId}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              More on TMDB
            </a>
          )}
        </div>
      )}
      {Array.isArray(productionCompanies) && productionCompanies.length > 0 && (
        <p className="tmdb-details-production">
          <strong>Production:</strong>{' '}
          {productionCompanies.map((c) => c?.name).filter(Boolean).join(', ')}
        </p>
      )}
    </div>
  );
}

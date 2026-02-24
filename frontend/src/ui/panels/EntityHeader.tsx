/**
 * Entity header: poster, title, meta (type, year, rating, state, genres),
 * library details, optional TMDB section. Reusable for item detail and explore.
 */

import { ReferenceLinks } from '../ReferenceLinks';

export type EntityHeaderMeta = {
  type?: string;
  year?: string;
  voteAverage?: number;
  state?: string;
  genres?: Array<{ name?: string } | string>;
};

export type EntityHeaderLibraryDetails = {
  contentRating?: string;
  country?: string;
  language?: string;
  network?: string;
  seasonsCount?: number;
  episodesCount?: number;
  itemId?: string | number;
  requestedAt?: string | number | Date | null;
  scrapedAt?: string | number | Date | null;
  refs?: {
    imdb_id?: string | null;
    tvdb_id?: string | null;
    tmdb_id?: string | null;
    type?: string | null;
  };
};

export type EntityHeaderTmdbSection = {
  tagline?: string;
  overview?: string;
  runtime?: number;
  releaseDate?: string;
  firstAirDate?: string;
  lastAirDate?: string;
  genres?: Array<{ name?: string }>;
  productionCompanies?: Array<{ name?: string }>;
  voteAverage?: number;
  voteCount?: number;
  numSeasons?: number;
  numEpisodes?: number;
};

export type EntityHeaderData = {
  posterPath?: string | null;
  title: string;
  meta?: EntityHeaderMeta;
  library?: EntityHeaderLibraryDetails;
  tmdb?: EntityHeaderTmdbSection | null;
  itemType?: string;
};

const TMDB_IMG = 'https://image.tmdb.org/t/p/w500';

function posterUrl(path: string | null | undefined): string {
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function formatDate(value: string | number | Date | null | undefined): string {
  if (value == null) return '—';
  if (value instanceof Date)
    return Number.isNaN(value.getTime())
      ? '—'
      : value.toLocaleString(undefined, {
          dateStyle: 'short',
          timeStyle: 'short',
        });
  const s = String(value).trim();
  if (!s || s === 'None') return '—';
  const d = new Date(s);
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function Chip({
  text,
  className = '',
}: {
  text: string;
  className?: string;
}) {
  return <span className={`legend-chip ${className}`.trim()}>{text}</span>;
}

function MetaRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <span className="entity-header__detail">
      <span className="entity-header__detail-label">{label}:</span>
      {typeof value === 'string' ? (
        <Chip text={value} className="legend-chip--neutral" />
      ) : (
        value
      )}
    </span>
  );
}

export function EntityHeader({ data }: { data: EntityHeaderData }) {
  const imgUrl = posterUrl(data.posterPath);
  const meta = data.meta;
  const library = data.library;
  const tmdb = data.tmdb;
  const hasTmdb =
    tmdb &&
    (tmdb.tagline ||
      tmdb.overview ||
      tmdb.runtime != null ||
      tmdb.releaseDate ||
      tmdb.firstAirDate ||
      (Array.isArray(tmdb.genres) && tmdb.genres.length) ||
      (typeof tmdb.voteAverage === 'number' && !Number.isNaN(tmdb.voteAverage)) ||
      (Array.isArray(tmdb.productionCompanies) &&
        tmdb.productionCompanies.length));

  const metaEntries: Array<{ key: string; label: string; value: React.ReactNode }> = [];
  if (hasTmdb && tmdb) {
    if (typeof tmdb.runtime === 'number' && tmdb.runtime > 0) {
      metaEntries.push({ key: 'runtime', label: 'Runtime', value: `${tmdb.runtime} min` });
    }
    if (tmdb.releaseDate || tmdb.firstAirDate) {
      metaEntries.push({
        key: 'release',
        label: data.itemType === 'show' ? 'First aired' : 'Release date',
        value: tmdb.releaseDate || tmdb.firstAirDate || '',
      });
    }
    if (tmdb.numSeasons != null && data.itemType === 'show') {
      metaEntries.push({
        key: 'seasons',
        label: 'Seasons',
        value: `${tmdb.numSeasons} season${tmdb.numSeasons !== 1 ? 's' : ''}`,
      });
    }
    if (tmdb.numEpisodes != null && data.itemType === 'show') {
      metaEntries.push({ key: 'episodes', label: 'Episodes', value: `${tmdb.numEpisodes} ep` });
    }
    if (tmdb.lastAirDate && data.itemType === 'show') {
      metaEntries.push({ key: 'ended', label: 'Ended', value: tmdb.lastAirDate });
    }
    if (typeof tmdb.voteAverage === 'number' && !Number.isNaN(tmdb.voteAverage)) {
      metaEntries.push({
        key: 'rating',
        label: 'Rating',
        value:
          typeof tmdb.voteCount === 'number' && tmdb.voteCount > 0
            ? `★ ${tmdb.voteAverage.toFixed(1)} (${tmdb.voteCount})`
            : `★ ${tmdb.voteAverage.toFixed(1)}`,
      });
    }
    if (Array.isArray(tmdb.productionCompanies) && tmdb.productionCompanies.length > 0) {
      metaEntries.push({
        key: 'studio',
        label: tmdb.productionCompanies.length === 1 ? 'Studio' : 'Studios',
        value: tmdb.productionCompanies.map((c) => c?.name).filter(Boolean).join(', '),
      });
    }
  }
  if (library) {
    if (library.contentRating) {
      metaEntries.push({ key: 'contentRating', label: 'Content rating', value: library.contentRating });
    }
    if (library.country) metaEntries.push({ key: 'country', label: 'Country', value: library.country });
    if (library.language) metaEntries.push({ key: 'language', label: 'Language', value: library.language });
    if (library.network) metaEntries.push({ key: 'network', label: 'Network', value: library.network });
    if (data.itemType === 'show') {
      const haveSeasonsFromTmdb = hasTmdb && tmdb && tmdb.numSeasons != null;
      const haveEpisodesFromTmdb = hasTmdb && tmdb && tmdb.numEpisodes != null;
      if (!haveSeasonsFromTmdb && library.seasonsCount != null) {
        metaEntries.push({
          key: 'seasons',
          label: 'Seasons',
          value: `${library.seasonsCount} season${library.seasonsCount !== 1 ? 's' : ''}`,
        });
      }
      if (!haveEpisodesFromTmdb && library.episodesCount != null) {
        metaEntries.push({ key: 'episodes', label: 'Episodes', value: `${library.episodesCount} ep` });
      }
    }
    if (library.itemId != null) {
      metaEntries.push({ key: 'itemId', label: 'Item ID', value: String(library.itemId) });
    }
    if (library.requestedAt != null) {
      metaEntries.push({ key: 'requested', label: 'Requested', value: formatDate(library.requestedAt) });
    }
    if (library.scrapedAt != null) {
      metaEntries.push({ key: 'scraped', label: 'Scraped', value: formatDate(library.scrapedAt) });
    }
  }
  if (!hasTmdb && meta?.year) {
    metaEntries.push({ key: 'year', label: 'Year', value: meta.year });
  }
  if (!hasTmdb && typeof meta?.voteAverage === 'number' && !Number.isNaN(meta.voteAverage)) {
    metaEntries.push({
      key: 'rating',
      label: 'Rating',
      value: `★ ${meta.voteAverage.toFixed(1)}`,
    });
  }

  return (
    <div className="item-detail-header">
      <div className="item-poster entity-header__poster">
        {imgUrl ? (
          <img src={imgUrl} alt={data.title || 'poster'} />
        ) : (
          <div className="muted">No artwork</div>
        )}
      </div>
      <div className="item-info entity-header__info">
        <div className="entity-header__title-row">
          <h2 className="entity-header__title">{data.title}</h2>
          {meta?.type && (
            <Chip
              text={meta.type}
              className={
                meta.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'
              }
            />
          )}
          {meta?.state != null && meta.state !== '' && (
            <Chip text={meta.state} className="state-pill" />
          )}
        </div>
        <div className="entity-header__meta-grid">
          {metaEntries.map(({ key, label, value }) => (
            <MetaRow key={key} label={label} value={value} />
          ))}
        </div>
        {hasTmdb && tmdb && (
          <div className="entity-header__synopsis">
            {tmdb.tagline && (
              <p className="entity-header__tagline">{tmdb.tagline}</p>
            )}
            {tmdb.overview && (
              <p className="entity-header__overview">{tmdb.overview}</p>
            )}
          </div>
        )}
        {library?.refs &&
          (library.refs.imdb_id || library.refs.tvdb_id || library.refs.tmdb_id) && (
            <div className="entity-header__links-row">
              <span className="entity-header__detail-label">Links:</span>
              <span className="entity-header__links">
                <ReferenceLinks {...library.refs} />
              </span>
            </div>
          )}
        {(() => {
          const genresFromTmdb =
            hasTmdb && Array.isArray(tmdb?.genres) && tmdb.genres.length > 0
              ? tmdb.genres.map((g) => g?.name).filter(Boolean) as string[]
              : null;
          const genresFromMeta =
            Array.isArray(meta?.genres) && meta.genres.length > 0
              ? meta.genres.map((g) =>
                  typeof g === 'object' && g != null && 'name' in g
                    ? (g as { name?: string }).name
                    : typeof g === 'string'
                      ? g
                      : null,
                ).filter(Boolean) as string[]
              : null;
          const genres = genresFromTmdb?.length ? genresFromTmdb : genresFromMeta;
          if (!genres?.length) return null;
          return (
            <div className="entity-header__genres-row">
              <span className="entity-header__detail-label">Genres:</span>
              <span className="entity-header__genre-chips">
                {genres.map((name) => (
                  <Chip key={name} text={name} className="legend-chip--genre" />
                ))}
              </span>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

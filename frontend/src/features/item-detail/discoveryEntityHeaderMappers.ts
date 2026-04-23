import { formatYear } from '../../shared/utils/utils';
import type { EntityHeaderData } from './EntityHeader';

/** Map TMDB detail API payload (movie or TV) to EntityHeader for discovery / explore. */
export function tmdbMediaToEntityHeaderData(media: Record<string, any>, kind: 'movie' | 'tv'): EntityHeaderData {
  const title = (media.title || media.name || 'Unknown') as string;
  const ext = (media.external_ids || {}) as Record<string, string | number | undefined>;
  const tmdbId = media.id != null ? String(media.id) : '';
  const tvdbRef = String(ext.tvdb_id ?? media.tvdb_id ?? '').trim();
  const imdbRef = String(ext.imdb_id ?? media.imdb_id ?? '').trim();

  const networks = Array.isArray(media.networks) ? media.networks.map((n: { name?: string }) => n?.name).filter(Boolean) : [];
  const networkStr = networks.length ? networks.join(', ') : undefined;

  const contentRatings = Array.isArray(media.content_ratings) ? media.content_ratings : [];
  const usRating = contentRatings.find((r: { iso_3166_1?: string }) => r?.iso_3166_1 === 'US');
  const anyRating = contentRatings[0] as { rating?: string } | undefined;
  const contentRating = kind === 'tv' ? (usRating as { rating?: string } | undefined)?.rating || anyRating?.rating : undefined;

  const itemType = kind === 'tv' ? 'show' : 'movie';

  const tmdb: EntityHeaderData['tmdb'] = {
    tagline: media.tagline as string | undefined,
    overview: media.overview as string | undefined,
    runtime: typeof media.runtime === 'number' ? media.runtime : undefined,
    releaseDate: media.release_date as string | undefined,
    firstAirDate: media.first_air_date as string | undefined,
    lastAirDate: media.last_air_date as string | undefined,
    genres: media.genres as Array<{ name?: string }> | undefined,
    productionCompanies: (media.production_companies || media.productions) as Array<{ name?: string }> | undefined,
    voteAverage: typeof media.vote_average === 'number' ? media.vote_average : undefined,
    voteCount: typeof media.vote_count === 'number' ? media.vote_count : undefined,
    numSeasons: typeof media.number_of_seasons === 'number' ? media.number_of_seasons : undefined,
    numEpisodes: typeof media.number_of_episodes === 'number' ? media.number_of_episodes : undefined,
  };

  const hasTmdbText =
    tmdb.overview ||
    tmdb.tagline ||
    (tmdb.runtime != null && tmdb.runtime > 0) ||
    tmdb.releaseDate ||
    tmdb.firstAirDate ||
    (Array.isArray(tmdb.genres) && tmdb.genres.length) ||
    (Array.isArray(tmdb.productionCompanies) && tmdb.productionCompanies.length) ||
    (typeof tmdb.voteAverage === 'number' && !Number.isNaN(tmdb.voteAverage)) ||
    tmdb.numSeasons != null ||
    tmdb.numEpisodes != null;

  const library: EntityHeaderData['library'] = {
    network: networkStr,
    contentRating,
    country: (media.origin_country && media.origin_country[0]) as string | undefined,
    language: (media.original_language as string | undefined) || undefined,
  };

  if (imdbRef || tmdbId || tvdbRef) {
    library.refs = {
      imdb_id: imdbRef || null,
      tmdb_id: tmdbId || null,
      tvdb_id: tvdbRef || null,
      type: kind,
    };
  }

  const hasLibrary =
    library.network || library.contentRating || library.country || library.language || library.refs;

  return {
    posterPath: (media.poster_path || media.profile_path) as string | null,
    title,
    itemType,
    meta: {
      type: kind,
      year: formatYear(media) || undefined,
      voteAverage: typeof media.vote_average === 'number' ? media.vote_average : undefined,
      state: media.library_state as string | undefined,
      genres: media.genres as EntityHeaderData['meta'] extends { genres?: infer G } ? G : never,
    },
    library: hasLibrary ? library : undefined,
    tmdb: hasTmdbText ? tmdb : null,
  };
}

/** Map TVDB series detail payload to EntityHeader for discovery / explore. */
export function tvdbSeriesToEntityHeaderData(series: Record<string, any>, tvdbId: string): EntityHeaderData {
  const title = (series.name || series.title || 'Unknown') as string;
  const seasons = Array.isArray(series.seasons) ? series.seasons.filter((s: any) => (s.season_number ?? s.number ?? 0) > 0) : [];
  const numSeasons = typeof series.seasons_count === 'number' ? series.seasons_count : seasons.length;

  const tmdb: NonNullable<EntityHeaderData['tmdb']> = {
    overview: (series.overview as string) || undefined,
    firstAirDate: (series.first_aired || series.aired) as string | undefined,
    lastAirDate: (series.last_aired as string) || undefined,
    genres: Array.isArray(series.genres) ? (series.genres as Array<{ name?: string }>) : undefined,
  };
  if (typeof numSeasons === 'number' && numSeasons > 0) tmdb.numSeasons = numSeasons;
  if (typeof series.average_runtime === 'number' && series.average_runtime > 0) tmdb.runtime = series.average_runtime;
  if (typeof series.total_episodes === 'number' && series.total_episodes > 0) {
    tmdb.numEpisodes = series.total_episodes;
  } else if (Array.isArray(series.seasons)) {
    const ne = (series.seasons as any[]).reduce((a, s) => a + (s.episode_count || s.episodes?.length || 0), 0);
    if (ne > 0) tmdb.numEpisodes = ne;
  }

  const networkName = series.original_network?.name || series.latest_network?.name;
  const statusName = series.status;
  const contentRatingFromStatus =
    statusName && typeof statusName === 'object' && statusName && 'name' in statusName
      ? String((statusName as { name?: string }).name || '')
      : typeof statusName === 'string'
        ? statusName
        : undefined;
  const library: EntityHeaderData['library'] = {
    network: networkName,
    contentRating: (typeof series.rating === 'string' ? series.rating : undefined) || contentRatingFromStatus,
    country: (series.default_country || series.country) as string | undefined,
    language: (series.default_language || series.original_language) as string | undefined,
    refs: { tvdb_id: String(tvdbId), tmdb_id: null, imdb_id: null, type: 'tv' },
  };

  const hasTmdb =
    tmdb.overview ||
    tmdb.firstAirDate ||
    tmdb.lastAirDate ||
    (tmdb.genres && tmdb.genres.length) ||
    tmdb.numSeasons != null ||
    tmdb.numEpisodes != null ||
    tmdb.runtime != null;

  return {
    posterPath: (series.poster_path || series.image) as string | null,
    title,
    itemType: 'show',
    meta: {
      type: 'tv',
      year: formatYear(series) || (series.year != null ? String(series.year) : undefined),
      state: series.library_state as string | undefined,
      genres: series.genres as EntityHeaderData['meta'] extends { genres?: infer G } ? G : never,
    },
    library,
    tmdb: hasTmdb ? tmdb : null,
  };
}

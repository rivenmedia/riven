import { useCallback, useEffect, useRef, useState } from 'react';
import { ViewLayout, ViewHeader } from '../components/ui/PagePrimitives';
import { BackButton } from '../ui/BackButton';
import { EntityHeader } from '../ui/panels/EntityHeader';
import type { EntityHeaderData } from '../ui/panels/EntityHeader';
import { CastCrew } from '../ui/panels/CastCrew';
import { Streams } from '../ui/panels/Streams';
import { MediaMetadata } from '../ui/panels/MediaMetadata';
import { SimilarRecommendations } from '../ui/panels/SimilarRecommendations';
import { apiDelete, apiFetch, apiGet, apiPost, getStreamUrl } from '../services/api';
import { annotateLibraryStatus } from '../services/libraryStatus';
import { notify } from '../services/notify';
import {
  formatBytes,
  formatEpisodeDisplayTitle,
  formatShortDate,
} from '../services/utils';
import type { AppRoute } from '../app/routeTypes';

type ManualSessionParsedFile = {
  file_id: number;
  filename: string;
  filesize: number;
  download_url?: string | null;
  parsed_metadata?: Record<string, unknown> | null;
};

type ManualSession = {
  session_id: string;
  item_id: number;
  media_type: 'movie' | 'tv' | null;
  tmdb_id?: string | null;
  tvdb_id?: string | null;
  imdb_id?: string | null;
  torrent_id: number | string;
  // We don't need the full shape of these on the client yet
  torrent_info: unknown;
  containers: unknown;
  parsed_files?: ManualSessionParsedFile[] | null;
  expires_at: string;
};

function buildEntityHeaderData(
  item: Record<string, unknown>,
  tmdbData: Record<string, unknown> | null | undefined,
  tvdbData: Record<string, unknown> | null | undefined,
): EntityHeaderData {
  const type = (item.type as string) ?? 'media';
  const seasons = item.seasons as { number?: number; episodes?: unknown[] }[] | undefined;
  const seasonsCount = seasons?.length;
  const episodesCount = seasons?.reduce((acc, s) => acc + (s.episodes?.length ?? 0), 0);
  const tvdbOverview = (tvdbData?.overview as string) || undefined;
  const tmdbSection: EntityHeaderData['tmdb'] = tmdbData
    ? {
        tagline: tmdbData.tagline as string | undefined,
        overview: (tmdbData.overview as string) || tvdbOverview,
        runtime: tmdbData.runtime as number | undefined,
        releaseDate: tmdbData.release_date as string | undefined,
        firstAirDate: tmdbData.first_air_date as string | undefined,
        lastAirDate: tmdbData.last_air_date as string | undefined,
        genres: tmdbData.genres as Array<{ name?: string }> | undefined,
        productionCompanies: tmdbData.production_companies as Array<{ name?: string }> | undefined,
        voteAverage: tmdbData.vote_average as number | undefined,
        voteCount: tmdbData.vote_count as number | undefined,
        numSeasons: tmdbData.number_of_seasons as number | undefined,
        numEpisodes: tmdbData.number_of_episodes as number | undefined,
      }
    : tvdbOverview
      ? {
          overview: tvdbOverview,
          firstAirDate: (tvdbData?.first_aired ?? tvdbData?.aired) as string | undefined,
        }
      : null;
  return {
    posterPath: (item.poster_path as string) ?? null,
    title: formatEpisodeDisplayTitle(item as any),
    itemType: type,
    meta: {
      type,
      year: item.year != null ? String(item.year) : undefined,
      voteAverage: (tmdbData?.vote_average as number) ?? undefined,
      state: (item.state as string) ?? undefined,
      genres: (item.genres as EntityHeaderData['meta'] extends { genres?: infer G } ? G : never) ?? undefined,
    },
    library: {
      contentRating: item.content_rating as string | undefined,
      country: item.country as string | undefined,
      language: (item.language as string) || (item.original_language as string) || undefined,
      network: item.network as string | undefined,
      seasonsCount,
      episodesCount,
      itemId: item.id as string | number | undefined,
      requestedAt: item.requested_at as string | number | Date | null | undefined,
      scrapedAt: item.scraped_at as string | number | Date | null | undefined,
      refs: item.imdb_id || item.tvdb_id || item.tmdb_id
        ? {
            imdb_id: item.imdb_id as string,
            tvdb_id: item.tvdb_id as string,
            tmdb_id: item.tmdb_id as string,
            type: item.type as string,
          }
        : undefined,
    },
    tmdb: tmdbSection,
  };
}

function TmdbDetailsPanel({
  tmdbData,
  itemType,
}: {
  tmdbData: Record<string, unknown>;
  itemType: string;
}) {
  const overview = tmdbData.overview as string | undefined;
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

  const hasContent =
    overview ||
    tagline ||
    (typeof runtime === 'number' && runtime > 0) ||
    releaseDate ||
    (Array.isArray(genres) && genres.length) ||
    (Array.isArray(productionCompanies) && productionCompanies.length) ||
    (typeof voteAverage === 'number' && !Number.isNaN(voteAverage)) ||
    belongsToCollection?.name ||
    (numSeasons != null && itemType === 'show');

  if (!hasContent) return null;

  return (
    <div className="panel tmdb-details-panel">
      <div className="section-head">
        <h3>Details</h3>
      </div>
      {belongsToCollection?.name && (
        <p className="tmdb-details-collection">
          <strong>Part of collection:</strong> {belongsToCollection.name}
        </p>
      )}
      {tagline && <p className="tmdb-details-tagline">{tagline}</p>}
      {overview && <p className="tmdb-details-overview">{overview}</p>}
      <div className="media-metadata-chips">
        {typeof runtime === 'number' && runtime > 0 && (
          <span className="legend-chip legend-chip--runtime">{runtime} min</span>
        )}
        {releaseDate && (
          <span className="legend-chip legend-chip--date">{releaseDate}</span>
        )}
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
      {Array.isArray(productionCompanies) && productionCompanies.length > 0 && (
        <p className="tmdb-details-production">
          <strong>Production:</strong>{' '}
          {productionCompanies.map((c) => c?.name).filter(Boolean).join(', ')}
        </p>
      )}
    </div>
  );
}

function ManualScrapeModal({
  itemId,
  item,
  onClose,
  onSuccess,
}: {
  itemId: string;
  item: { type?: string } | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  type Mode = 'magnet' | 'pick';
  type Step = 'input' | 'session';

  const [mode, setMode] = useState<Mode>('magnet');
  const [step, setStep] = useState<Step>('input');
  const [magnet, setMagnet] = useState('');
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeStreams, setScrapeStreams] = useState<
    Record<string, { infohash: string; raw_title: string; rank?: number; is_cached?: boolean }>
  >({});
  const [pickLoading, setPickLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [manualSession, setManualSession] = useState<ManualSession | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const mediaType = item?.type === 'movie' ? 'movie' : 'tv';
  const isMovie = mediaType === 'movie';

  useEffect(() => {
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
    };
  }, []);

  const searchScrapers = async () => {
    if (!itemId) return;
    setScrapeLoading(true);
    setScrapeStreams({});
    const res = await apiGet('/scrape', { item_id: itemId, media_type: mediaType });
    setScrapeLoading(false);
    if (!res.ok) {
      notify(res.error || 'Scrape failed', 'error');
      return;
    }
    const streams = (
      res.data as {
        streams?: Record<
          string,
          { infohash: string; raw_title: string; rank?: number; is_cached?: boolean }
        >;
      }
    )?.streams ?? {};
    setScrapeStreams(streams);
    if (Object.keys(streams).length === 0) notify('No streams found', 'warning');
  };

  const startSessionWithMagnet = async (magnetUri: string) => {
    setSessionLoading(true);
    try {
      const params = new URLSearchParams({ magnet: magnetUri, item_id: String(itemId) });
      const response = await apiFetch<Record<string, unknown>>(
        `/scrape/start_session?${params.toString()}`,
        { method: 'POST' },
      );
      if (!response.ok) {
        notify(response.error || 'Failed to start manual session', 'error');
        return;
      }

      const raw = response.data;
      if (!raw || typeof raw !== 'object') {
        notify('Manual session did not return a payload', 'error');
        return;
      }

      // Normalize: backend may return snake_case (session_id, parsed_files) or camelCase
      const session: ManualSession = {
        session_id: (raw.session_id as string) ?? (raw.sessionId as string) ?? '',
        item_id: (raw.item_id as number) ?? (raw.itemId as number) ?? 0,
        media_type: (raw.media_type as ManualSession['media_type']) ?? (raw.mediaType as ManualSession['media_type']) ?? null,
        tmdb_id: (raw.tmdb_id as string | null) ?? (raw.tmdbId as string | null) ?? null,
        tvdb_id: (raw.tvdb_id as string | null) ?? (raw.tvdbId as string | null) ?? null,
        imdb_id: (raw.imdb_id as string | null) ?? (raw.imdbId as string | null) ?? null,
        torrent_id: (raw.torrent_id as number | string) ?? (raw.torrentId as number | string) ?? '',
        torrent_info: raw.torrent_info ?? raw.torrentInfo ?? null,
        containers: raw.containers ?? null,
        parsed_files: (raw.parsed_files ?? raw.parsedFiles ?? null) as ManualSession['parsed_files'],
        expires_at: (raw.expires_at as string) ?? (raw.expiresAt as string) ?? '',
      };

      if (!session.session_id) {
        notify('Manual session did not return a session ID', 'error');
        return;
      }

      const parsedFiles = (session.parsed_files ?? []) as ManualSessionParsedFile[];
      const defaultSelection =
        parsedFiles.length > 0 ? [parsedFiles[0].file_id].filter((id): id is number => !!id) : [];

      setManualSession(session);
      setSelectedFileIds(defaultSelection);
      setStep('session');
      notify('Manual scrape session started. Select files to download.', 'success');
    } finally {
      setSessionLoading(false);
    }
  };

  const handleStartMagnet = async () => {
    const m = magnet.trim();
    if (!m) {
      notify('Paste a magnet URI first', 'warning');
      return;
    }
    await startSessionWithMagnet(m);
  };

  const handlePickStream = async (e: React.MouseEvent, infohash: string) => {
    e.preventDefault();
    e.stopPropagation();
    setPickLoading(true);
    try {
      const magnetUri = `magnet:?xt=urn:btih:${infohash}`;
      await startSessionWithMagnet(magnetUri);
    } finally {
      setPickLoading(false);
    }
  };

  const streamList = Object.entries(scrapeStreams).sort(
    ([, a], [, b]) => (b.rank ?? 0) - (a.rank ?? 0),
  );

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose}>
      <header>
        <h2>Manual Scrape</h2>
        <button type="button" onClick={onClose} data-action="close">
          &times;
        </button>
      </header>
      <div className="modal-body manual-scrape-modal">
        {step === 'input' && (
          <>
            <div className="manual-scrape-modes" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'magnet'}
                className={mode === 'magnet' ? 'active' : ''}
                onClick={() => setMode('magnet')}
              >
                Paste magnet link
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === 'pick'}
                className={mode === 'pick' ? 'active' : ''}
                onClick={() => {
                  setMode('pick');
                  void searchScrapers();
                }}
              >
                Pick from scrapers
              </button>
            </div>

            {mode === 'magnet' && (
              <>
                <label>Magnet URL</label>
                <textarea
                  data-slot="magnet"
                  placeholder="Paste magnet link..."
                  value={magnet}
                  onChange={(e) => setMagnet(e.target.value)}
                />
                <button
                  type="button"
                  data-action="start-session"
                  onClick={handleStartMagnet}
                  disabled={sessionLoading}
                >
                  {sessionLoading ? 'Starting…' : 'Start Session'}
                </button>
              </>
            )}

            {mode === 'pick' && (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={searchScrapers}
                  disabled={scrapeLoading}
                >
                  {scrapeLoading ? 'Searching…' : 'Search scrapers'}
                </button>
                {streamList.length > 0 && (
                  <div className="manual-scrape-stream-list" data-slot="stream-options">
                    <label>Pick a stream</label>
                    <ul>
                      {streamList.map(([ih, s]) => (
                        <li key={ih}>
                          <button
                            type="button"
                            className="manual-scrape-stream-option"
                            onClick={(e) => handlePickStream(e, ih)}
                            disabled={pickLoading || sessionLoading}
                            title={s.raw_title}
                          >
                            <span className="stream-title">{s.raw_title}</span>
                            <span className="stream-meta">
                              {typeof s.rank === 'number' && (
                                <span className="stream-rank">rank {s.rank}</span>
                              )}
                              {s.is_cached != null && (
                                <span className="stream-cached">
                                  {s.is_cached ? '✓ cached' : 'uncached'}
                                </span>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {step === 'session' && manualSession && (
          <ManualSessionStep
            session={manualSession}
            isMovie={isMovie}
            selectedFileIds={selectedFileIds}
            setSelectedFileIds={setSelectedFileIds}
            onClose={onClose}
            onSuccess={onSuccess}
            onReset={() => {
              setManualSession(null);
              setSelectedFileIds([]);
              setStep('input');
            }}
          />
        )}
      </div>
    </dialog>
  );
}

type ManualSessionStepProps = {
  session: ManualSession;
  isMovie: boolean;
  selectedFileIds: number[];
  setSelectedFileIds: (ids: number[]) => void;
  onClose: () => void;
  onSuccess: () => void;
  onReset: () => void;
};

function ManualSessionStep({
  session,
  isMovie,
  selectedFileIds,
  setSelectedFileIds,
  onClose,
  onSuccess,
  onReset,
}: ManualSessionStepProps) {
  const [submitting, setSubmitting] = useState(false);

  const parsedFiles = (session.parsed_files ?? []) as ManualSessionParsedFile[];

  const handleStartDownload = async () => {
    if (!selectedFileIds.length) {
      notify('Select at least one file', 'warning');
      return;
    }

    setSubmitting(true);

    const byId = new Map<number, ManualSessionParsedFile>();
    for (const pf of parsedFiles) {
      if (typeof pf.file_id === 'number') {
        byId.set(pf.file_id, pf);
      }
    }

    const selected = selectedFileIds
      .map((id) => byId.get(id))
      .filter((pf): pf is ManualSessionParsedFile => !!pf);

    if (!selected.length) {
      notify('Selected files are no longer available', 'error');
      setSubmitting(false);
      return;
    }

    const filesRoot: Record<
      string,
      { file_id: number; filename: string; filesize: number; download_url?: string | null }
    > = {};

    for (const pf of selected) {
      if (typeof pf.file_id !== 'number') continue;
      filesRoot[String(pf.file_id)] = {
        file_id: pf.file_id,
        filename: pf.filename,
        filesize: pf.filesize,
        download_url: pf.download_url ?? null,
      };
    }

    const selectRes = await apiPost(`/scrape/session/${session.session_id}`, {
      action: 'select_files',
      files: { root: filesRoot },
    });

    if (!selectRes.ok) {
      notify(selectRes.error || 'Failed to select files', 'error');
      setSubmitting(false);
      return;
    }

    let updatePayload: any;

    if (isMovie) {
      const pf = selected[0];
      updatePayload = {
        action: 'update_attributes',
        file_data: {
          file_id: pf.file_id,
          filename: pf.filename,
          filesize: pf.filesize,
          download_url: pf.download_url ?? undefined,
        },
      };
    } else {
      const rootShow: Record<
        number,
        Record<
          number,
          { file_id: number; filename: string; filesize: number; download_url?: string | null }
        >
      > = {};

      for (const pf of selected) {
        const meta = (pf.parsed_metadata ?? {}) as Record<string, unknown>;
        const seasonRaw =
          (meta.season as number | string | undefined) ??
          (meta.season_number as number | string | undefined);
        let seasonNum =
          typeof seasonRaw === 'string' ? parseInt(seasonRaw, 10) : seasonRaw ?? 1;
        if (!seasonNum || Number.isNaN(seasonNum)) {
          seasonNum = 1;
        }

        let episodeRaw: number | string | undefined;
        const episodesField = (meta as any).episodes as unknown;
        if (Array.isArray(episodesField) && episodesField.length > 0) {
          episodeRaw = episodesField[0] as number | string;
        } else {
          episodeRaw =
            (meta.episode as number | string | undefined) ??
            (meta.episode_number as number | string | undefined);
        }

        let episodeNum =
          typeof episodeRaw === 'string' ? parseInt(episodeRaw, 10) : episodeRaw ?? pf.file_id;
        if (!episodeNum || Number.isNaN(episodeNum)) {
          episodeNum = pf.file_id;
        }

        const seasonKey = seasonNum as number;
        const episodeKey = episodeNum as number;

        if (!rootShow[seasonKey]) {
          rootShow[seasonKey] = {};
        }

        rootShow[seasonKey][episodeKey] = {
          file_id: pf.file_id,
          filename: pf.filename,
          filesize: pf.filesize,
          download_url: pf.download_url ?? undefined,
        };
      }

      updatePayload = {
        action: 'update_attributes',
        file_data: {
          root: rootShow,
        },
      };
    }

    const updateRes = await apiPost(`/scrape/session/${session.session_id}`, updatePayload);

    if (!updateRes.ok) {
      notify(updateRes.error || 'Failed to start manual download', 'error');
      setSubmitting(false);
      return;
    }

    void apiPost(`/scrape/session/${session.session_id}`, { action: 'complete' });

    notify('Manual download started', 'success');
    setSubmitting(false);
    onClose();
    onSuccess();
  };

  const handleAbort = async () => {
    setSubmitting(true);
    const res = await apiPost(`/scrape/session/${session.session_id}`, { action: 'abort' });
    if (!res.ok) {
      notify(res.error || 'Failed to abort session', 'error');
      setSubmitting(false);
      return;
    }
    notify('Manual session aborted', 'success');
    setSubmitting(false);
    onReset();
  };

  const files = parsedFiles;

  return (
    <div className="manual-scrape-session-step">
      <h3>Select files to download</h3>
      {files.length === 0 ? (
        <p className="muted">No files returned for this torrent.</p>
      ) : (
        <ul className="manual-scrape-file-list">
          {files.map((pf) => {
            const checked = selectedFileIds.includes(pf.file_id);
            const controlType = isMovie ? 'radio' : 'checkbox';
            const labelParts = [`${pf.filename}`, `(${formatBytes(pf.filesize)})`];

            return (
              <li key={pf.file_id}>
                <label>
                  <input
                    type={controlType}
                    name="manual-session-file"
                    checked={checked}
                    onChange={() => {
                      if (isMovie) {
                        setSelectedFileIds([pf.file_id]);
                      } else if (checked) {
                        setSelectedFileIds(selectedFileIds.filter((id) => id !== pf.file_id));
                      } else {
                        setSelectedFileIds([...selectedFileIds, pf.file_id]);
                      }
                    }}
                  />
                  <span>{labelParts.join(' ')}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}
      <div className="manual-scrape-session-actions">
        <button
          type="button"
          className="btn btn--primary"
          onClick={handleStartDownload}
          disabled={submitting || !files.length}
        >
          {submitting ? 'Starting…' : 'Start Download'}
        </button>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={handleAbort}
          disabled={submitting}
        >
          Cancel Session
        </button>
      </div>
    </div>
  );
}

async function executeItemAction(action: string, itemId: string) {
  const ids = [String(itemId)];
  switch (action) {
    case 'retry':
      return apiPost('/items/retry', { ids });
    case 'reset':
      return apiPost('/items/reset', { ids });
    case 'pause':
      return apiPost('/items/pause', { ids });
    case 'unpause':
      return apiPost('/items/unpause', { ids });
    case 'reindex':
      return apiPost('/items/reindex', { item_id: Number(itemId) });
    case 'remove':
      return apiDelete('/items/remove', { ids });
    default:
      return { ok: false, status: 0, data: null, error: `Unknown action ${action}` };
  }
}

function mediaTypeForScrape(item: any): 'movie' | 'tv' {
  return item.type === 'movie' ? 'movie' : 'tv';
}

async function runAutoScrape(item: any) {
  return apiPost('/scrape/auto', {
    media_type: mediaTypeForScrape(item),
    item_id: Number(item.id),
  });
}

type EpisodeLike = {
  id?: string;
  number?: number;
  title?: string;
  state?: string;
  parent_title?: string;
  season_number?: number | null;
  episode_number?: number | null;
  aired_at?: string;
  poster_path?: string | null;
  network?: string | null;
  content_rating?: string | null;
  media_metadata?: {
    video?: { resolution_width?: number; resolution_height?: number };
    quality_source?: string | null;
  } | null;
  filesystem_entry?: { file_size?: number | null } | null;
};
type SeasonLike = { number?: number; episodes?: EpisodeLike[] };
type ShowLike = { type: string; title?: string; poster_path?: string | null; seasons?: SeasonLike[] };

type TvdbCharacterEntry = {
  people_type?: string;
  person_name?: string;
  name?: string;
  person_img_url?: string | null;
};

function EpisodeCastCrewList({ characters }: { characters: TvdbCharacterEntry[] }) {
  const byType = characters.reduce<Record<string, TvdbCharacterEntry[]>>((acc, c) => {
    const type = c.people_type || 'Other';
    if (!acc[type]) acc[type] = [];
    acc[type].push(c);
    return acc;
  }, {});
  const order = ['Director', 'Writer', 'Guest Star', 'Star', 'Cast', 'Other'];
  const types = [...new Set([...order.filter((t) => byType[t]), ...Object.keys(byType)])];
  return (
    <dl className="cast-crew-dl episode-cast-crew__dl">
      {types.flatMap((type) => {
        const list = byType[type] ?? [];
        if (!list.length) return [];
        return [
          <dt key={`${type}-dt`}>{type}</dt>,
          <dd key={`${type}-dd`} className="pill-list-wrap">
            <div className="pill-list">
              {list.map((c, i) => {
                const label = c.name
                  ? `${c.person_name ?? 'Unknown'} (${c.name})`
                  : (c.person_name ?? 'Unknown');
                return (
                  <span
                    key={c.person_name && c.name ? `${c.person_name}-${c.name}-${i}` : i}
                    className="pill pill--text"
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          </dd>,
        ];
      })}
    </dl>
  );
}

function isInLibrary(state: string): boolean {
  const s = (state || '').toString();
  return s === 'Completed' || s === 'Symlinked' || s === 'Downloaded' || s === 'Scraped';
}

function episodeQualityLabel(ep: EpisodeLike): string {
  const meta = ep.media_metadata;
  if (!meta) return '';
  const parts: string[] = [];
  const v = meta.video;
  if (v?.resolution_height) parts.push(`${v.resolution_height}p`);
  if (meta.quality_source) parts.push(meta.quality_source);
  return parts.join(' ');
}

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';
function posterUrl(item: { poster_path?: string | null }): string {
  const path = item?.poster_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function SeasonsEpisodes({
  item,
  refresh,
}: {
  item: ShowLike;
  refresh: () => void;
}) {
  const seasons = item?.seasons;
  const [activeSeasonIdx, setActiveSeasonIdx] = useState(0);

  if (item.type !== 'show' || !seasons?.length) return null;

  const sortedSeasons = [...seasons]
    .filter((s) => (s.number ?? 0) > 0)
    .sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
  if (!sortedSeasons.length) return null;

  const season = sortedSeasons[activeSeasonIdx];
  const episodes = season?.episodes ?? [];
  const sortedEps = [...episodes].sort(
    (a, b) => (a.episode_number ?? a.number ?? 0) - (b.episode_number ?? b.number ?? 0),
  );
  const showTitle = item.title ?? '';

  return (
    <div className="panel show-seasons-episodes">
      <div className="section-head">
        <h3>Seasons &amp; Episodes</h3>
      </div>
      <div className="season-tabs" role="tablist">
        {sortedSeasons.map((s, idx) => (
          <button
            key={s.number}
            type="button"
            role="tab"
            aria-selected={idx === activeSeasonIdx}
            className={`season-tab ${idx === activeSeasonIdx ? 'season-tab--active' : ''}`}
            onClick={() => setActiveSeasonIdx(idx)}
          >
            Season {s.number ?? 0}
            {s.episodes?.length ? ` (${s.episodes.length})` : ''}
          </button>
        ))}
      </div>
      <div className="show-episodes-list media-list">
        {sortedEps.length === 0 ? (
          <p className="muted">No episodes in this season.</p>
        ) : (
          sortedEps.map((ep) => {
            const state = (ep.state || '').toString();
            const inLib = isInLibrary(state);
            const hasFile =
              inLib ||
              (ep.filesystem_entry?.file_size != null && ep.filesystem_entry.file_size > 0);
            const epForDisplay = {
              ...ep,
              type: 'episode' as const,
              parent_title: ep.parent_title ?? showTitle,
              season_number: ep.season_number ?? season?.number ?? null,
              episode_number: ep.episode_number ?? ep.number ?? null,
            };

            const handleRetry = async () => {
              const res = await apiPost('/items/retry', { ids: [String(ep.id)] });
              if (!res.ok) {
                notify(res.error || 'Retry failed', 'error');
                return;
              }
              notify('Episode queued for retry', 'success');
              refresh();
            };

            return (
              <div key={ep.id ?? ep.number} className="media-list__row show-episode-row">
                <span
                  className={`episode-file-indicator episode-file-indicator--${hasFile ? 'has-file' : 'missing'}`}
                  title={hasFile ? 'File available' : 'No file'}
                  aria-hidden
                >
                  {hasFile ? '✓' : '○'}
                </span>
                <div className="media-list__poster">
                  <img
                    src={posterUrl(ep.poster_path ? ep : { poster_path: item.poster_path }) || undefined}
                    alt=""
                    loading="lazy"
                  />
                </div>
                <div className="media-list__main">
                  <a className="media-list__title" href={`#/item/${ep.id}`}>
                    {formatEpisodeDisplayTitle(epForDisplay as any)}
                  </a>
                  <div className="media-list__meta">
                    <span className="legend-chip legend-chip--tv">TV</span>
                    <span
                      className={`legend-chip ${inLib ? 'legend-chip--in-library' : 'legend-chip--missing'}`}
                    >
                      {inLib ? 'In library' : state || 'Missing'}
                    </span>
                    {formatShortDate(ep.aired_at) && (
                      <span className="legend-chip">Aired: {formatShortDate(ep.aired_at)}</span>
                    )}
                    {ep.network && (
                      <span className="legend-chip">Network: {ep.network}</span>
                    )}
                    {ep.content_rating && (
                      <span className="legend-chip">Rating: {ep.content_rating}</span>
                    )}
                    {episodeQualityLabel(ep) && (
                      <span className="legend-chip">Quality: {episodeQualityLabel(ep)}</span>
                    )}
                    {ep.filesystem_entry?.file_size != null &&
                      ep.filesystem_entry.file_size > 0 && (
                        <span className="legend-chip">
                          Size: {formatBytes(ep.filesystem_entry.file_size)}
                        </span>
                      )}
                  </div>
                </div>
                <div className="media-list__actions">
                  {ep.id && (state === 'Requested' || state === 'Failed') && (
                    <button
                      type="button"
                      className="btn btn--small btn--secondary"
                      onClick={handleRetry}
                    >
                      Retry
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default function ItemDetailView({ route }: { route: AppRoute }) {
  const itemId = route.param;
  const [item, setItem] = useState<any>(null);
  const [tmdbData, setTmdbData] = useState<Record<string, unknown> | null>(null);
  const [tvdbData, setTvdbData] = useState<Record<string, unknown> | null>(null);
  const [streamData, setStreamData] = useState<any>(null);
  const [metadata, setMetadata] = useState<Record<string, unknown> | null>(null);
  const [similarData, setSimilarData] = useState<{ recommendations: any[]; similar: any[] } | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'streams' | 'playback'>('overview');
  const [showManualScrape, setShowManualScrape] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!itemId) return;
    setLoading(true);
    const [itemRes, streamRes, metadataRes] = await Promise.all([
      apiGet(`/items/${itemId}`, { media_type: 'item', extended: true }),
      apiGet(`/items/${itemId}/streams`),
      apiGet(`/items/${itemId}/metadata`),
    ]);
    if (!itemRes.ok || !itemRes.data) {
      setError(itemRes.error || 'Item not found.');
      setItem(null);
      setLoading(false);
      return;
    }
    const it = itemRes.data;
    setItem(it);
    setStreamData(streamRes.ok ? streamRes.data : null);
    setMetadata(metadataRes.ok ? metadataRes.data : null);

    let tmdb: Record<string, unknown> | null = null;
    let tvdb: Record<string, unknown> | null = null;
    if (it.type === 'movie' && it.tmdb_id) {
      const r = await apiGet(`/tmdb/movie/${it.tmdb_id}`);
      if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
    } else if (it.type === 'show') {
      if (it.tmdb_id) {
        const r = await apiGet(`/tmdb/tv/${it.tmdb_id}`);
        if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
      }
      if (it.tvdb_id) {
        const r = await apiGet(`/tvdb/series/${it.tvdb_id}`);
        if (r.ok && r.data) tvdb = r.data as Record<string, unknown>;
      }
    } else if (
      it.type === 'episode' &&
      it.show_id != null &&
      it.season_number != null &&
      it.episode_number != null
    ) {
      const showRes = await apiGet(`/items/${it.show_id}`, { media_type: 'item' });
      const show = showRes.ok ? showRes.data : null;
      if (show?.tmdb_id) {
        const r = await apiGet(
          `/tmdb/tv/${show.tmdb_id}/season/${it.season_number}/episode/${it.episode_number}`,
        );
        if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
      }
      if (show?.tvdb_id) {
        const tvdbRes = await apiGet(
          `/tvdb/series/${show.tvdb_id}/season/${it.season_number}/episode/${it.episode_number}`,
        );
        if (tvdbRes.ok && tvdbRes.data) tvdb = tvdbRes.data as Record<string, unknown>;
      }
    }
    setTmdbData(tmdb);
    setTvdbData(tvdb);

    if ((it.type === 'movie' || it.type === 'show') && tmdb) {
      const kind = it.type === 'movie' ? 'movie' : 'tv';
      const toCard = (entry: any) => ({
        ...entry,
        id: String(entry.id),
        title: entry.title || entry.name || 'Unknown',
        media_type: kind,
        tmdb_id: entry.id,
      });
      let rec = ((tmdb.recommendations as any)?.results || []).map(toCard);
      let sim = ((tmdb.similar as any)?.results || []).map(toCard);
      await annotateLibraryStatus([...rec, ...sim]);
      setSimilarData({ recommendations: rec, similar: sim });
    } else {
      setSimilarData(null);
    }
    setError(null);
    setLoading(false);
  }, [itemId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!itemId) {
    return (
      <ViewLayout className="view-item-detail" view="item-detail">
        <p className="muted">No item ID provided.</p>
      </ViewLayout>
    );
  }

  if (loading && !item) {
    return (
      <ViewLayout className="view-item-detail" view="item-detail">
        <p className="muted">Loading…</p>
      </ViewLayout>
    );
  }

  if (error || !item) {
    return (
      <ViewLayout className="view-item-detail" view="item-detail">
        <p className="muted">{error || 'Item not found.'}</p>
      </ViewLayout>
    );
  }

  const returnRoute =
    (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('riven_return_route')) || 'library';
  const returnLabels: Record<string, string> = {
    library: '← Back to Library',
    movies: '← Back to Movies',
    shows: '← Back to TV Shows',
    episodes: '← Back to TV Episodes',
  };
  const isEpisode = item.type === 'episode';
  const showId = isEpisode && item.show_id != null ? String(item.show_id) : null;
  const isShow = item.type === 'show';

  const state = (item.state || '').toString();
  const showPause =
    state !== 'Paused' && state !== 'Completed' && state !== 'Failed';
  const showResume = state === 'Paused';

  const handleAction = async (action: string) => {
    if (action === 'manual-scrape') {
      setShowManualScrape(true);
      return;
    }
    if (action === 'auto-scrape') {
      const response = await runAutoScrape(item);
      if (!response.ok) {
        notify(response.error || 'Auto scrape failed', 'error');
        return;
      }
      notify('Auto scrape triggered', 'success');
      refresh();
      return;
    }
    if (action === 'remove') {
      if (!window.confirm(`Remove "${item.title}" from library?`)) return;
    }
    const response = await executeItemAction(action, itemId);
    if (!response.ok) {
      notify(response.error || `Action failed: ${action}`, 'error');
      return;
    }
    notify((response.data as any)?.message || `${action} complete`, 'success');
    if (action === 'remove') {
      window.location.hash = '#/library';
      return;
    }
    refresh();
  };

  const credits = tmdbData?.credits as Record<string, unknown> | undefined;
  const episodeCharacters = (tvdbData?.characters as TvdbCharacterEntry[] | undefined) ?? [];

  return (
    <ViewLayout className="view-item-detail" view="item-detail">
      <ViewHeader
        title="Library Item"
        subtitle="Inspect metadata, stream state, and backend action controls."
      />
      <div>
        <BackButton
          label={showId ? '← Back to Show' : returnLabels[returnRoute] || '← Back'}
          href={showId ? `#/item/${showId}` : `#/${returnRoute}`}
        />
      </div>

      <div className="item-detail-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'overview'}
          className={`item-detail-tab ${activeTab === 'overview' ? 'item-detail-tab--active' : ''}`}
          data-tab="overview"
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        {!isShow && (
          <>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'streams'}
              className={`item-detail-tab ${activeTab === 'streams' ? 'item-detail-tab--active' : ''}`}
              data-tab="streams"
              onClick={() => setActiveTab('streams')}
            >
              Streams / VFS
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'playback'}
              className={`item-detail-tab ${activeTab === 'playback' ? 'item-detail-tab--active' : ''}`}
              data-tab="playback"
              onClick={() => setActiveTab('playback')}
            >
              Playback
            </button>
          </>
        )}
      </div>

      <div className="item-layout">
        <div className="item-main">
          {activeTab === 'overview' && (
            <div className="item-detail-panel item-detail-panel--overview" role="tabpanel">
              <EntityHeader data={buildEntityHeaderData(item, tmdbData, tvdbData)} />
              <div className="item-actions-bar">
                <button
                  type="button"
                  className="btn btn--small btn--primary"
                  onClick={() => handleAction('auto-scrape')}
                >
                  Auto Scrape
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={() => handleAction('manual-scrape')}
                >
                  Manual Scrape
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={() => handleAction('retry')}
                >
                  Retry
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={() => handleAction('reset')}
                >
                  Reset
                </button>
                {showPause && (
                  <button
                    type="button"
                    className="btn btn--small btn--warning"
                    onClick={() => handleAction('pause')}
                  >
                    Pause
                  </button>
                )}
                {showResume && (
                  <button
                    type="button"
                    className="btn btn--small btn--secondary"
                    onClick={() => handleAction('unpause')}
                  >
                    Resume
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={() => handleAction('reindex')}
                >
                  Reindex
                </button>
                <button
                  type="button"
                  className="btn btn--small btn--danger"
                  onClick={() => handleAction('remove')}
                >
                  Remove
                </button>
              </div>
              {isEpisode && episodeCharacters.length > 0 && (
                <div className="panel episode-cast-crew">
                  <div className="section-head">
                    <h3>Cast &amp; Crew</h3>
                  </div>
                  <EpisodeCastCrewList characters={episodeCharacters} />
                </div>
              )}
              <SeasonsEpisodes item={item as ShowLike} refresh={refresh} />
              <CastCrew credits={credits ?? null} exploreLinkBase="#/explore" />
              {tmdbData && item.type === 'show' && (
                <TmdbDetailsPanel tmdbData={tmdbData} itemType={item.type} />
              )}
              {similarData && (item.type === 'movie' || item.type === 'show') && (
                <SimilarRecommendations
                  data={similarData}
                  exploreLinkBase="#/explore"
                />
              )}
            </div>
          )}

          {activeTab === 'streams' && !isShow && (
            <div className="item-detail-panel item-detail-panel--streams" role="tabpanel">
              <MediaMetadata metadata={metadata} />
              <Streams
                data={streamData || {}}
                itemId={itemId}
                onRefresh={refresh}
              />
            </div>
          )}

          {activeTab === 'playback' && !isShow && (
            <div className="item-detail-panel item-detail-panel--playback" role="tabpanel">
              <div className="panel item-video">
                <h3>Playback</h3>
                <video controls src={getStreamUrl(itemId)} />
              </div>
            </div>
          )}
        </div>
      </div>

      {showManualScrape && (
        <ManualScrapeModal
          itemId={itemId}
          item={item}
          onClose={() => setShowManualScrape(false)}
          onSuccess={refresh}
        />
      )}
    </ViewLayout>
  );
}

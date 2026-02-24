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

function buildEntityHeaderData(
  item: Record<string, unknown>,
  tmdbData: Record<string, unknown> | null | undefined,
): EntityHeaderData {
  const type = (item.type as string) ?? 'media';
  const seasons = item.seasons as { number?: number; episodes?: unknown[] }[] | undefined;
  const seasonsCount = seasons?.length;
  const episodesCount = seasons?.reduce((acc, s) => acc + (s.episodes?.length ?? 0), 0);
  return {
    posterPath: (item.poster_path as string) ?? null,
    title: formatEpisodeDisplayTitle(item as any),
    itemType: type,
    meta: {
      type,
      year: item.year != null ? String(item.year) : undefined,
      voteAverage: tmdbData?.vote_average as number | undefined,
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
    tmdb: tmdbData
      ? {
          tagline: tmdbData.tagline as string | undefined,
          overview: tmdbData.overview as string | undefined,
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
      : null,
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
  onClose,
  onSuccess,
}: {
  itemId: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [magnet, setMagnet] = useState('');
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
    };
  }, []);

  const handleStart = async () => {
    const m = magnet.trim();
    if (!m) {
      notify('Paste a magnet URI first', 'warning');
      return;
    }
    const params = new URLSearchParams({ magnet: m, item_id: String(itemId) });
    const response = await apiFetch(`/scrape/start_session?${params.toString()}`, {
      method: 'POST',
    });
    if (!response.ok) {
      notify(response.error || 'Failed to start manual session', 'error');
      return;
    }
    notify('Manual scrape session started', 'success');
    onClose();
    onSuccess();
  };

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose}>
      <header>
        <h2>Manual Scrape</h2>
        <button type="button" onClick={onClose} data-action="close">
          &times;
        </button>
      </header>
      <div className="modal-body">
        <label>Magnet URL</label>
        <textarea
          data-slot="magnet"
          placeholder="Paste magnet link..."
          value={magnet}
          onChange={(e) => setMagnet(e.target.value)}
        />
        <button type="button" data-action="start-session" onClick={handleStart}>
          Start Session
        </button>
      </div>
    </dialog>
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
    if (it.type === 'movie' && it.tmdb_id) {
      const r = await apiGet(`/tmdb/movie/${it.tmdb_id}`);
      if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
    } else if (it.type === 'show' && it.tmdb_id) {
      const r = await apiGet(`/tmdb/tv/${it.tmdb_id}`);
      if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
    } else if (
      it.type === 'episode' &&
      it.show_id != null &&
      it.season_number != null &&
      it.episode_number != null
    ) {
      const showRes = await apiGet(`/items/${it.show_id}`);
      if (showRes.ok && showRes.data?.tmdb_id) {
        const r = await apiGet(
          `/tmdb/tv/${showRes.data.tmdb_id}/season/${it.season_number}/episode/${it.episode_number}`,
        );
        if (r.ok && r.data) tmdb = r.data as Record<string, unknown>;
      }
    }
    setTmdbData(tmdb);

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
              <EntityHeader data={buildEntityHeaderData(item, tmdbData)} />
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
              <SeasonsEpisodes item={item as ShowLike} refresh={refresh} />
              <CastCrew credits={credits ?? null} exploreLinkBase="#/explore" />
              {tmdbData && (
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
          onClose={() => setShowManualScrape(false)}
          onSuccess={refresh}
        />
      )}
    </ViewLayout>
  );
}

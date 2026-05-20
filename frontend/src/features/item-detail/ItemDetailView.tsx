import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout } from '../../shared/ui/PagePrimitives';
import { EntityHeader } from './EntityHeader';
import type { EntityHeaderData } from './EntityHeader';
import { CastCrew } from './CastCrew';
import { Streams, episodeHasStreamOverride, type StreamsData } from './Streams';
import { MediaMetadata } from './MediaMetadata';
import { SimilarRecommendations } from './SimilarRecommendations';
import { CollectionFranchiseStrip } from './CollectionFranchiseStrip';
import { TmdbDetailsPanel } from './TmdbDetailsPanel';
import { ShowSeasonHierarchy, SeasonEpisodeRows, type EpisodeLike, type ShowLike } from './ShowSeasonHierarchy';
import { TvdbSeasonDetailsPanel } from './TvdbSeasonDetailsPanel';
import { TmdbSeasonDetailsPanel } from './TmdbSeasonDetailsPanel';
import {
  MediaOverviewTabStrip,
  MediaOverviewTabPanel,
  mediaOverviewTabDefinitions,
  type MediaOverviewTabId,
} from './MediaOverviewTabs';
import { creditsHaveContent } from './creditsUtils';
import { DetailViewActionsToolbar } from '../../shared/ui/DetailViewActionsToolbar';
import { apiDelete, apiGet, apiPost, getStreamUrl } from '../../shared/api/api';
import { annotateLibraryStatus } from '../library/libraryStatus';
import { readLibraryReturnRoute } from '../../shared/navigation/libraryReturnRoute';
import { notify } from '../../shared/notifications/notify';
import { formatEpisodeDisplayTitle } from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import { buildHash } from '../../shared/routing/router';
import { getDebridProviderLabel } from './debridProvider';

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
      debridProvider: getDebridProviderLabel(
        item.filesystem_entry as { provider?: string | null } | null | undefined,
      ),
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

const LIBRARY_MEDIA_OVERVIEW_PANEL_ID = 'library-item-media-overview-panel';

const PROCESSED_LIBRARY_STATES = new Set([
  'Scraped',
  'Downloaded',
  'Symlinked',
  'Completed',
  'PartiallyCompleted',
  'Failed',
  'Paused',
]);

function hasVerifiedPinnedStream(
  streamData: StreamsData | null | undefined,
  itemType: string,
): boolean {
  if (!streamData || itemType === 'show') return false;
  if (streamData.active_stream?.infohash) return true;
  return Boolean(streamData.season_active_stream?.infohash);
}

const RETURN_HASH: Record<string, string> = {
  library: '#/library',
  movies: '#/movies',
  shows: '#/shows',
  episodes: '#/episodes',
};

const RETURN_NAMES: Record<string, string> = {
  library: 'Library',
  movies: 'Movies',
  shows: 'TV Shows',
  episodes: 'TV Episodes',
};

function LibraryItemBreadcrumbs({
  returnRoute,
  item,
  showId,
  showTitle,
  seasonId,
  seasonLabel,
  activeTab,
  onGoOverview,
}: {
  returnRoute: string;
  item: Record<string, unknown>;
  showId: string | null;
  showTitle: string | null;
  seasonId: string | null;
  seasonLabel: string | null;
  activeTab: 'overview' | 'streams' | 'playback';
  onGoOverview: () => void;
}) {
  const listKey = returnRoute in RETURN_HASH ? returnRoute : 'library';
  const listHref = RETURN_HASH[listKey];
  const listLabel = RETURN_NAMES[listKey];
  const isShow = item.type === 'show';
  const isEpisode = item.type === 'episode';
  const isSeason = item.type === 'season';
  const onStreamsOrPlayback = !isShow && activeTab !== 'overview';
  const subViewLabel =
    activeTab === 'streams' ? 'Streams / VFS' : activeTab === 'playback' ? 'Playback' : null;
  const titleLabel = formatEpisodeDisplayTitle(item as any);
  const crumbShowLabel =
    showTitle?.trim() ||
    (typeof item.parent_title === 'string' && item.parent_title.trim()
      ? (item.parent_title as string).trim()
      : showId
        ? 'Show'
        : null);
  const seasonCrumbLabel =
    seasonLabel?.trim() ||
    (item.season_number != null ? `Season ${item.season_number}` : null);

  return (
    <nav className="item-detail-breadcrumbs" aria-label="Breadcrumb">
      <div className="explore-breadcrumbs">
        <a className="pill pill--origin" href={listHref}>
          {listLabel}
        </a>
        {isSeason && showId && crumbShowLabel ? (
          <a className="pill pill--tv" href={`#/item/${showId}`}>
            {crumbShowLabel}
          </a>
        ) : null}
        {isEpisode && showId && crumbShowLabel ? (
          <a className="pill pill--tv" href={`#/item/${showId}`}>
            {crumbShowLabel}
          </a>
        ) : null}
        {isEpisode && seasonId && seasonCrumbLabel ? (
          <a className="pill pill--tv" href={`#/item/${seasonId}`}>
            {seasonCrumbLabel}
          </a>
        ) : null}
        {onStreamsOrPlayback && subViewLabel ? (
          <>
            <button type="button" className="pill pill--text" onClick={onGoOverview}>
              {titleLabel}
            </button>
            <span className="pill pill--active" aria-current="page">
              {subViewLabel}
            </span>
          </>
        ) : (
          <span className="pill pill--active" aria-current="page">
            {titleLabel}
          </span>
        )}
      </div>
    </nav>
  );
}

export default function ItemDetailView({ route }: { route: AppRoute }) {
  const itemId = route.param;
  const [item, setItem] = useState<any>(null);
  const [tmdbData, setTmdbData] = useState<Record<string, unknown> | null>(null);
  const [tvdbData, setTvdbData] = useState<Record<string, unknown> | null>(null);
  const [tmdbSeasonData, setTmdbSeasonData] = useState<Record<string, unknown> | null>(null);
  const [tvdbSeasonData, setTvdbSeasonData] = useState<Record<string, unknown> | null>(null);
  const [streamData, setStreamData] = useState<any>(null);
  const [metadata, setMetadata] = useState<Record<string, unknown> | null>(null);
  const [similarData, setSimilarData] = useState<{ recommendations: any[]; similar: any[] } | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'streams' | 'playback'>('overview');
  const [overviewSubTab, setOverviewSubTab] = useState<MediaOverviewTabId>('details');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkingAvailability, setCheckingAvailability] = useState(false);

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
    let tmdbSeason: Record<string, unknown> | null = null;
    let tvdbSeason: Record<string, unknown> | null = null;

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
    } else if (it.type === 'season') {
      const showRes = await apiGet(`/items/${it.show_id}`, { media_type: 'item' });
      const show = showRes.ok ? showRes.data : null;
      if (it.tvdb_id) {
        const r = await apiGet(`/tvdb/season/${it.tvdb_id}`);
        if (r.ok && r.data) tvdbSeason = r.data as Record<string, unknown>;
      } else if (show?.tvdb_id != null && (it.season_number != null || it.number != null)) {
        const sn = Number(it.season_number ?? it.number);
        const r = await apiGet(`/tvdb/series/${show.tvdb_id}/season/${sn}`);
        if (r.ok && r.data) tvdbSeason = r.data as Record<string, unknown>;
      }
      if (show?.tmdb_id != null && (it.number != null || it.season_number != null)) {
        const sn = it.number ?? it.season_number;
        const r = await apiGet(`/tmdb/tv/${show.tmdb_id}/season/${sn}`);
        if (r.ok && r.data) tmdbSeason = r.data as Record<string, unknown>;
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
    setTmdbSeasonData(tmdbSeason);
    setTvdbSeasonData(tvdbSeason);

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
      try {
        await annotateLibraryStatus([...rec, ...sim]);
      } catch {
        /* list still works without in-library chip */
      }
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

  useEffect(() => {
    setOverviewSubTab('details');
  }, [itemId]);

  useEffect(() => {
    const tab = route.query?.tab;
    if (tab === 'streams' || tab === 'playback' || tab === 'overview') {
      setActiveTab(tab);
    } else {
      setActiveTab('overview');
    }
  }, [itemId, route.query?.tab]);

  const showCollectionTab =
    item &&
    item.type === 'movie' &&
    item.tmdb_id &&
    (tmdbData?.belongs_to_collection as { id?: number } | null | undefined)?.id != null;

  const mediaOverviewTabs = useMemo(
    () => mediaOverviewTabDefinitions(Boolean(showCollectionTab)),
    [showCollectionTab],
  );

  useEffect(() => {
    if (!showCollectionTab && overviewSubTab === 'collection') {
      setOverviewSubTab('details');
    }
  }, [showCollectionTab, overviewSubTab]);

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

  const returnRoute = readLibraryReturnRoute() ?? 'library';
  const isEpisode = item.type === 'episode';
  const isSeason = item.type === 'season';
  const isShow = item.type === 'show';
  const isTitleMedia = item.type === 'movie' || item.type === 'show';

  const breadcrumbShowId =
    isEpisode && item.show_id != null
      ? String(item.show_id)
      : isSeason && item.show_id != null
        ? String(item.show_id)
        : null;
  const breadcrumbShowTitle =
    (typeof item.parent_title === 'string' && item.parent_title.trim()
      ? item.parent_title.trim()
      : null) || null;
  const breadcrumbSeasonId =
    isEpisode && item.season_id != null ? String(item.season_id) : null;
  const breadcrumbSeasonLabel =
    item.season_number != null ? `Season ${item.season_number}` : null;

  const tmdbHeader = isSeason ? tmdbSeasonData : tmdbData;
  const tvdbHeader = isSeason ? tvdbSeasonData : tvdbData;

  const hasPlaybackSource =
    item.filesystem_entry &&
    typeof (item.filesystem_entry as { file_size?: number }).file_size === 'number' &&
    (item.filesystem_entry as { file_size?: number }).file_size! > 0;

  const debridProviderLabel = getDebridProviderLabel(
    item.filesystem_entry as { provider?: string | null } | null | undefined,
  );

  const state = (item.state || '').toString();
  const showPause =
    state !== 'Paused' && state !== 'Completed' && state !== 'Failed';
  const showResume = state === 'Paused';
  const showCheckAvailability =
    !isShow &&
    PROCESSED_LIBRARY_STATES.has(state) &&
    hasVerifiedPinnedStream(streamData as StreamsData | null, String(item.type));

  const episodeStreamOverride =
    isEpisode && episodeHasStreamOverride(streamData as StreamsData | null);

  const handleAction = async (action: string) => {
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

  const handleCheckAvailability = async () => {
    if (!itemId || checkingAvailability) return;
    setCheckingAvailability(true);
    try {
      const response = await apiPost(`/items/${itemId}/check_availability`, {});
      const data = response.data as {
        available?: boolean;
        primary_service?: string | null;
        services?: Array<{ service: string; available: boolean; error?: string | null }>;
        error?: string;
      } | null;
      if (!response.ok) {
        notify(response.error || data?.error || 'Availability check failed', 'error');
        return;
      }
      if (data?.available) {
        const svc = data.primary_service ? ` on ${data.primary_service}` : '';
        notify(`Stream is cached${svc}`, 'success');
      } else {
        const detail =
          data?.services
            ?.map((s) => `${s.service}: ${s.available ? 'cached' : s.error || 'not cached'}`)
            .join(' · ') || 'Not cached on any debrid service';
        notify(detail, 'warning');
      }
    } finally {
      setCheckingAvailability(false);
    }
  };

  const credits = tmdbData?.credits as Record<string, unknown> | undefined;
  const episodeCharacters = (tvdbData?.characters as TvdbCharacterEntry[] | undefined) ?? [];

  return (
    <ViewLayout className="view-item-detail" view="item-detail">
      <LibraryItemBreadcrumbs
        returnRoute={returnRoute}
        item={item}
        showId={breadcrumbShowId}
        showTitle={breadcrumbShowTitle}
        seasonId={breadcrumbSeasonId}
        seasonLabel={breadcrumbSeasonLabel}
        activeTab={activeTab}
        onGoOverview={() => setActiveTab('overview')}
      />

      {!isShow && (
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
        </div>
      )}

      <div className="item-layout">
        <div className="item-main">
          {activeTab === 'overview' && (
            <div className="item-detail-panel item-detail-panel--overview" role="tabpanel">
              <EntityHeader data={buildEntityHeaderData(item, tmdbHeader, tvdbHeader)} />
              <DetailViewActionsToolbar aria-label="Library item actions">
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
                  onClick={() => handleAction('retry')}
                >
                  Retry
                </button>
                {showCheckAvailability && (
                  <button
                    type="button"
                    className="btn btn--small btn--secondary"
                    disabled={checkingAvailability}
                    onClick={() => void handleCheckAvailability()}
                  >
                    {checkingAvailability ? 'Checking…' : 'Check availability'}
                  </button>
                )}
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
              </DetailViewActionsToolbar>
              {isEpisode && episodeCharacters.length > 0 && (
                <div className="panel episode-cast-crew">
                  <div className="section-head">
                    <h3>Cast &amp; Crew</h3>
                  </div>
                  <EpisodeCastCrewList characters={episodeCharacters} />
                </div>
              )}
              {isTitleMedia && (
                <>
                  <MediaOverviewTabStrip
                    value={overviewSubTab}
                    onChange={setOverviewSubTab}
                    panelId={LIBRARY_MEDIA_OVERVIEW_PANEL_ID}
                    ariaLabel="Library item sections"
                    tabs={mediaOverviewTabs}
                  />
                  <MediaOverviewTabPanel id={LIBRARY_MEDIA_OVERVIEW_PANEL_ID}>
                    {overviewSubTab === 'details' && (
                      <>
                        <ShowSeasonHierarchy item={item} refresh={refresh} />
                        {tmdbData && (item.type === 'movie' || item.type === 'show') && (
                          <TmdbDetailsPanel
                            tmdbData={tmdbData}
                            itemType={item.type}
                            showCollectionLine={item.type !== 'movie'}
                          />
                        )}
                        {!tmdbData && item.type === 'movie' && (
                          <p className="muted media-overview-tabpanel__empty">
                            No TMDB details for this title.
                          </p>
                        )}
                        {!tmdbData && item.type === 'show' && !((item as ShowLike).seasons?.length) && (
                          <p className="muted media-overview-tabpanel__empty">
                            No season list and no TMDB data for this show.
                          </p>
                        )}
                      </>
                    )}
                    {overviewSubTab === 'collection' &&
                      showCollectionTab &&
                      tmdbData &&
                      item.tmdb_id && (
                        <CollectionFranchiseStrip
                          collectionId={Number(
                            (tmdbData.belongs_to_collection as { id: number }).id,
                          )}
                          currentTmdbId={String(item.tmdb_id)}
                          belongsHint={
                            tmdbData.belongs_to_collection as {
                              id?: number;
                              name?: string;
                              poster_path?: string | null;
                            }
                          }
                        />
                      )}
                    {overviewSubTab === 'cast' &&
                      (creditsHaveContent(credits) ? (
                        <CastCrew credits={credits ?? null} exploreLinkBase="#/explore" />
                      ) : (
                        <p className="muted media-overview-tabpanel__empty">
                          No cast or crew from TMDB.
                        </p>
                      ))}
                    {overviewSubTab === 'recommendations' && (
                      similarData && (similarData.recommendations?.length ?? 0) > 0 ? (
                        <SimilarRecommendations
                          data={similarData}
                          exploreLinkBase="#/explore"
                          variant="recommendations"
                        />
                      ) : (
                        <p className="muted media-overview-tabpanel__empty">
                          No recommendations from TMDB.
                        </p>
                      )
                    )}
                    {overviewSubTab === 'similar' && (
                      similarData && (similarData.similar?.length ?? 0) > 0 ? (
                        <SimilarRecommendations
                          data={similarData}
                          exploreLinkBase="#/explore"
                          variant="similar"
                        />
                      ) : (
                        <p className="muted media-overview-tabpanel__empty">No similar titles from TMDB.</p>
                      )
                    )}
                  </MediaOverviewTabPanel>
                </>
              )}
              {!isTitleMedia && item.type === 'episode' && (
                <CastCrew credits={credits ?? null} exploreLinkBase="#/explore" />
              )}
              {!isTitleMedia && item.type === 'season' && (
                <>
                  <div className="panel season-stream-coverage">
                    <div className="section-head">
                      <h3>Streams &amp; coverage</h3>
                    </div>
                    <p className="muted">
                      <strong>Season-level streams</strong> ({item.streams_count ?? 0} available) are
                      often whole-season packs. <strong>Per-episode counts</strong> in the list below
                      reflect scrapes targeted at individual episodes. Episodes can inherit season
                      streams when they have none of their own.
                    </p>
                  </div>
                  <TvdbSeasonDetailsPanel data={tvdbSeasonData} />
                  <TmdbSeasonDetailsPanel data={tmdbSeasonData} />
                  <div className="panel show-seasons-episodes">
                    <div className="section-head">
                      <h3>Episodes</h3>
                    </div>
                    <div className="show-episodes-list media-list">
                      <SeasonEpisodeRows
                        episodes={(item.episodes as EpisodeLike[]) || []}
                        showTitle={breadcrumbShowTitle || (item.parent_title as string) || 'Show'}
                        showPosterPath={item.poster_path as string | null | undefined}
                        seasonNumber={(item.number ?? item.season_number) as number | null | undefined}
                        refresh={refresh}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === 'streams' && !isShow && (
            <div className="item-detail-panel item-detail-panel--streams" role="tabpanel">
              <MediaMetadata metadata={metadata} providerLabel={debridProviderLabel} />
              {episodeStreamOverride ? (
                <div className="item-detail-stream-override-warning" role="status">
                  <strong>Episode stream override</strong>
                  <p>
                    This episode is pinned to a different stream than the season pack. Playback
                    and symlinks use the episode torrent below. To inherit the season stream again,
                    choose <strong>Use season stream</strong> on the season row, or{' '}
                    {breadcrumbSeasonId ? (
                      <a href={buildHash('item', breadcrumbSeasonId, { tab: 'streams' })}>
                        manage streams on the season
                      </a>
                    ) : (
                      'manage streams on the season'
                    )}
                    .
                  </p>
                </div>
              ) : null}
              <Streams
                data={streamData || {}}
                itemId={itemId}
                item={item}
                onRefresh={refresh}
              />
            </div>
          )}

          {activeTab === 'playback' && !isShow && (
            <div className="item-detail-panel item-detail-panel--playback" role="tabpanel">
              <div className="panel item-video">
                <h3>Playback</h3>
                {hasPlaybackSource ? (
                  <video controls src={getStreamUrl(itemId)} />
                ) : (
                  <p className="muted">No media file on this item yet.</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

    </ViewLayout>
  );
}

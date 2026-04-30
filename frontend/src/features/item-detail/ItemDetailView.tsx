import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader } from '../../shared/ui/PagePrimitives';
import { BackButton } from '../../shared/ui/BackButton';
import { EntityHeader } from './EntityHeader';
import type { EntityHeaderData } from './EntityHeader';
import { CastCrew } from './CastCrew';
import { Streams } from './Streams';
import { MediaMetadata } from './MediaMetadata';
import { SimilarRecommendations } from './SimilarRecommendations';
import { CollectionFranchiseStrip } from './CollectionFranchiseStrip';
import { TmdbDetailsPanel } from './TmdbDetailsPanel';
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
import { notify } from '../../shared/notifications/notify';
import {
  formatBytes,
  formatEpisodeDisplayTitle,
  formatShortDate,
} from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';

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

const LIBRARY_MEDIA_OVERVIEW_PANEL_ID = 'library-item-media-overview-panel';

export default function ItemDetailView({ route }: { route: AppRoute }) {
  const itemId = route.param;
  const [item, setItem] = useState<any>(null);
  const [tmdbData, setTmdbData] = useState<Record<string, unknown> | null>(null);
  const [tvdbData, setTvdbData] = useState<Record<string, unknown> | null>(null);
  const [streamData, setStreamData] = useState<any>(null);
  const [metadata, setMetadata] = useState<Record<string, unknown> | null>(null);
  const [similarData, setSimilarData] = useState<{ recommendations: any[]; similar: any[] } | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'streams' | 'playback'>('overview');
  const [overviewSubTab, setOverviewSubTab] = useState<MediaOverviewTabId>('details');
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
  const isTitleMedia = item.type === 'movie' || item.type === 'show';

  const state = (item.state || '').toString();
  const showPause =
    state !== 'Paused' && state !== 'Completed' && state !== 'Failed';
  const showResume = state === 'Paused';

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
                        <SeasonsEpisodes item={item as ShowLike} refresh={refresh} />
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
              {!isTitleMedia && (
                <>
                  <SeasonsEpisodes item={item as ShowLike} refresh={refresh} />
                  <CastCrew credits={credits ?? null} exploreLinkBase="#/explore" />
                </>
              )}
            </div>
          )}

          {activeTab === 'streams' && !isShow && (
            <div className="item-detail-panel item-detail-panel--streams" role="tabpanel">
              <MediaMetadata metadata={metadata} />
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
                <video controls src={getStreamUrl(itemId)} />
              </div>
            </div>
          )}
        </div>
      </div>

    </ViewLayout>
  );
}

import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import {
  formatBytes,
  formatEpisodeDisplayTitle,
  formatShortDate,
} from '../../shared/utils/utils';
import { getDebridProviderLabel } from './debridProvider';

export type EpisodeLike = {
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
  streams_count?: number;
  blacklisted_streams_count?: number;
  media_metadata?: {
    video?: { resolution_width?: number; resolution_height?: number };
    quality_source?: string | null;
  } | null;
  filesystem_entry?: { file_size?: number | null; provider?: string | null } | null;
};

export type SeasonLike = {
  id?: string;
  number?: number;
  episodes?: EpisodeLike[];
};

export type ShowLike = { type: string; title?: string; poster_path?: string | null; seasons?: SeasonLike[] };

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';

function posterUrl(item: { poster_path?: string | null }): string {
  const path = item?.poster_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
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

function EpisodeMetaChip({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={`legend-chip ${className}`.trim()}>{children}</span>;
}

function EpisodeStatusChips({ inLib, state }: { inLib: boolean; state: string }) {
  return (
    <div className="episode-meta-row">
      <EpisodeMetaChip className="legend-chip--tv">TV</EpisodeMetaChip>
      <EpisodeMetaChip className={inLib ? 'legend-chip--in-library' : 'legend-chip--missing'}>
        {inLib ? 'In library' : state || 'Missing'}
      </EpisodeMetaChip>
    </div>
  );
}

function EpisodeDetailMetaChips({
  ep,
  inLib,
  state,
}: {
  ep: EpisodeLike;
  inLib: boolean;
  state: string;
}) {
  const debridLabel = getDebridProviderLabel(ep.filesystem_entry);
  const aired = formatShortDate(ep.aired_at);
  const quality = episodeQualityLabel(ep);
  const fileSize =
    ep.filesystem_entry?.file_size != null && ep.filesystem_entry.file_size > 0
      ? formatBytes(ep.filesystem_entry.file_size)
      : null;

  return (
    <div className="episode-meta-columns">
      <div className="episode-meta-column">
        {aired && <EpisodeMetaChip>Aired: {aired}</EpisodeMetaChip>}
        {fileSize && <EpisodeMetaChip>Size: {fileSize}</EpisodeMetaChip>}
      </div>
      <div className="episode-meta-column">
        {ep.content_rating && <EpisodeMetaChip>Rating: {ep.content_rating}</EpisodeMetaChip>}
        {debridLabel && <EpisodeMetaChip>Debrid: {debridLabel}</EpisodeMetaChip>}
      </div>
      <div className="episode-meta-column">
        {quality && <EpisodeMetaChip>Quality: {quality}</EpisodeMetaChip>}
        <EpisodeStatusChips inLib={inLib} state={state} />
      </div>
    </div>
  );
}

function EpisodeMainContent({
  ep,
  inLib,
  state,
  titleHref,
  title,
}: {
  ep: EpisodeLike;
  inLib: boolean;
  state: string;
  titleHref: string;
  title: string;
}) {
  return (
    <div className="media-list__main">
      <a className="media-list__title" href={titleHref}>
        {title}
      </a>
      <EpisodeDetailMetaChips ep={ep} inLib={inLib} state={state} />
    </div>
  );
}

function EpisodeStreamCountPills({
  streamsCount,
  blacklistedCount,
}: {
  streamsCount?: number;
  blacklistedCount?: number;
}) {
  const available = streamsCount ?? 0;
  const blacklisted = blacklistedCount ?? 0;
  return (
    <div className="show-episode-stream-counts" aria-label="Scraped stream counts">
      <span className="stream-count-pill stream-count-pill--available" title="Non-blacklisted streams">
        Available: {available}
      </span>
      <span className="stream-count-pill stream-count-pill--blacklisted" title="Blacklisted streams">
        Blacklisted: {blacklisted}
      </span>
    </div>
  );
}

/**
 * Expandable season rows for a TV show library item (replaces season tabs).
 */
export function ShowSeasonHierarchy({ item, refresh }: { item: ShowLike; refresh: () => void }) {
  const seasons = item?.seasons;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const sortedSeasons = useMemo(() => {
    if (!seasons?.length) return [];
    return [...seasons]
      .filter((s) => (s.number ?? 0) > 0)
      .sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
  }, [seasons]);

  const toggleSeason = useCallback((key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  if (item.type !== 'show' || !sortedSeasons.length) return null;

  const showTitle = item.title ?? '';

  return (
    <div className="panel show-seasons-episodes">
      <div className="section-head">
        <h3>Seasons &amp; Episodes</h3>
      </div>
      <div className="show-season-accordion" role="list">
        {sortedSeasons.map((s) => {
          const sid = s.id != null ? String(s.id) : `n-${s.number ?? 0}`;
          const isOpen = Boolean(expanded[sid]);
          const episodes = s.episodes ?? [];
          const sortedEps = [...episodes].sort(
            (a, b) => (a.episode_number ?? a.number ?? 0) - (b.episode_number ?? b.number ?? 0),
          );

          return (
            <div key={sid} className="show-season-block" role="listitem">
              <div className="show-season-block__header-row">
                <button
                  type="button"
                  className="show-season-block__header"
                  aria-expanded={isOpen}
                  onClick={() => toggleSeason(sid)}
                >
                  <span className="show-season-block__chevron" aria-hidden>
                    {isOpen ? '▼' : '▶'}
                  </span>
                  <span className="show-season-block__title">
                    Season {s.number ?? 0}
                    {sortedEps.length ? ` (${sortedEps.length} episodes)` : ''}
                  </span>
                </button>
                {s.id && (
                  <a className="btn btn--small btn--secondary show-season-block__page-link" href={`#/item/${s.id}`}>
                    Season page
                  </a>
                )}
              </div>
              {isOpen && (
                <div className="show-season-block__body show-episodes-list media-list">
                  {sortedEps.length === 0 ? (
                    <p className="muted show-season-block__empty">No episodes in this season.</p>
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
                        season_number: ep.season_number ?? s.number ?? null,
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
                          <EpisodeMainContent
                            ep={ep}
                            inLib={inLib}
                            state={state}
                            titleHref={`#/item/${ep.id}`}
                            title={formatEpisodeDisplayTitle(epForDisplay as any)}
                          />
                          <EpisodeStreamCountPills
                            streamsCount={ep.streams_count}
                            blacklistedCount={ep.blacklisted_streams_count}
                          />
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
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Episode list for a single season (library season detail page). */
export function SeasonEpisodeRows({
  episodes,
  showTitle,
  showPosterPath,
  seasonNumber,
  refresh,
}: {
  episodes: EpisodeLike[];
  showTitle: string;
  showPosterPath?: string | null;
  seasonNumber?: number | null;
  refresh: () => void;
}) {
  const sortedEps = [...episodes].sort(
    (a, b) => (a.episode_number ?? a.number ?? 0) - (b.episode_number ?? b.number ?? 0),
  );

  if (!sortedEps.length) {
    return <p className="muted">No episodes in this season.</p>;
  }

  return (
    <>
      {sortedEps.map((ep) => {
        const state = (ep.state || '').toString();
        const inLib = isInLibrary(state);
        const hasFile =
          inLib || (ep.filesystem_entry?.file_size != null && ep.filesystem_entry.file_size > 0);
        const epForDisplay = {
          ...ep,
          type: 'episode' as const,
          parent_title: ep.parent_title ?? showTitle,
          season_number: ep.season_number ?? seasonNumber ?? null,
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
                src={posterUrl(ep.poster_path ? ep : { poster_path: showPosterPath }) || undefined}
                alt=""
                loading="lazy"
              />
            </div>
            <EpisodeMainContent
              ep={ep}
              inLib={inLib}
              state={state}
              titleHref={`#/item/${ep.id}`}
              title={formatEpisodeDisplayTitle(epForDisplay as any)}
            />
            <EpisodeStreamCountPills
              streamsCount={ep.streams_count}
              blacklistedCount={ep.blacklisted_streams_count}
            />
            <div className="media-list__actions">
              {ep.id && (state === 'Requested' || state === 'Failed') && (
                <button type="button" className="btn btn--small btn--secondary" onClick={handleRetry}>
                  Retry
                </button>
              )}
            </div>
          </div>
        );
      })}
    </>
  );
}

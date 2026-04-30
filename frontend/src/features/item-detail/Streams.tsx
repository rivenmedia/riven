/**
 * Streams panel: list streams with blacklist/unblacklist, reset, search scrapers, paste magnet.
 * Highlights the pinned (active) stream. Click a non-blacklisted row to switch.
 */

import { useState } from 'react';
import { apiFetch, apiGet, apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import { formatBytes } from '../../shared/utils/utils';

export type StreamsData = {
  streams?: unknown[];
  blacklisted_streams?: unknown[];
  active_stream?: { id: number | string; infohash: string } | null;
};

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
  torrent_info: unknown;
  containers: unknown;
  parsed_files?: ManualSessionParsedFile[] | null;
  expires_at: string;
};

type CandidateStream = {
  infohash: string;
  raw_title: string;
  rank?: number;
  is_cached?: boolean;
  resolution?: string;
};

type ManualSessionStepProps = {
  session: ManualSession;
  isMovie: boolean;
  selectedFileIds: number[];
  setSelectedFileIds: (ids: number[]) => void;
  onClose: () => void;
  onSuccess: () => void;
  onReset: () => void;
};

function resolutionClass(res: string): string {
  const r = res.toLowerCase();
  if (r === '4k' || r === '2160p' || r === '2160') return 'legend-chip--res-4k';
  if (r === '1080p' || r === '1080') return 'legend-chip--res-1080p';
  if (r === '720p' || r === '720') return 'legend-chip--res-720p';
  if (r === '480p' || r === '480' || r === '576p') return 'legend-chip--res-sd';
  return 'legend-chip--res-unknown';
}

function ResolutionPill({ resolution }: { resolution: string }) {
  return (
    <span className={`legend-chip ${resolutionClass(resolution)}`}>
      {resolution.toUpperCase()}
    </span>
  );
}

function rankBackground(rank: number, maxRank: number): string {
  if (!maxRank || maxRank <= 0) return '';
  const ratio = Math.min(rank / maxRank, 1);
  const alpha = Math.round(ratio * 12);
  return `rgba(10, 126, 164, 0.${alpha.toString().padStart(2, '0')})`;
}

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
      if (typeof pf.file_id === 'number') byId.set(pf.file_id, pf);
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
        if (!seasonNum || Number.isNaN(seasonNum)) seasonNum = 1;

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
        if (!episodeNum || Number.isNaN(episodeNum)) episodeNum = pf.file_id;

        const seasonKey = seasonNum as number;
        const episodeKey = episodeNum as number;
        if (!rootShow[seasonKey]) rootShow[seasonKey] = {};
        rootShow[seasonKey][episodeKey] = {
          file_id: pf.file_id,
          filename: pf.filename,
          filesize: pf.filesize,
          download_url: pf.download_url ?? undefined,
        };
      }
      updatePayload = { action: 'update_attributes', file_data: { root: rootShow } };
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

  return (
    <div className="manual-scrape-session-step">
      <h3>Select files to download</h3>
      {parsedFiles.length === 0 ? (
        <p className="muted">No files returned for this torrent.</p>
      ) : (
        <ul className="manual-scrape-file-list">
          {parsedFiles.map((pf) => {
            const checked = selectedFileIds.includes(pf.file_id);
            const controlType = isMovie ? 'radio' : 'checkbox';
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
                  <span>
                    {pf.filename} ({formatBytes(pf.filesize)})
                  </span>
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
          disabled={submitting || !parsedFiles.length}
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

export interface StreamsProps {
  data: StreamsData;
  itemId: string;
  item?: { type?: string } | null;
  onRefresh: () => void;
}

export function Streams({ data, itemId, item, onRefresh }: StreamsProps) {
  const [activatingStreamId, setActivatingStreamId] = useState<number | null>(null);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [candidateStreams, setCandidateStreams] = useState<Record<string, CandidateStream>>({});
  const [sessionData, setSessionData] = useState<ManualSession | null>(null);
  const [selectedFileIds, setSelectedFileIds] = useState<number[]>([]);
  const [pickLoading, setPickLoading] = useState(false);
  const [showMagnetInput, setShowMagnetInput] = useState(false);
  const [magnet, setMagnet] = useState('');
  const [sessionLoading, setSessionLoading] = useState(false);

  const mediaType = item?.type === 'movie' ? 'movie' : 'tv';
  const isMovie = mediaType === 'movie';

  const merged = [
    ...(data.streams || []),
    ...(data.blacklisted_streams || []).map((stream: any) => ({
      ...stream,
      blacklisted: true,
    })),
  ];
  const mergedSorted = [...merged].sort((a: any, b: any) => {
    const aBl = a.blacklisted ? 1 : 0;
    const bBl = b.blacklisted ? 1 : 0;
    if (aBl !== bBl) return aBl - bBl;
    return (b.rank ?? 0) - (a.rank ?? 0);
  });
  const activeStream = data.active_stream ?? null;
  const maxRank = mergedSorted.reduce((m: number, s: any) => Math.max(m, s.rank ?? 0), 0);

  const handleReset = async () => {
    const response = await apiPost(`/items/${itemId}/streams/reset`);
    if (!response.ok) {
      notify(response.error || 'Failed to reset streams', 'error');
      return;
    }
    notify('Streams reset', 'success');
    onRefresh();
  };

  const handleBlacklist = async (stream: any) => {
    const path = stream.blacklisted
      ? `/items/${itemId}/streams/${stream.id}/unblacklist`
      : `/items/${itemId}/streams/${stream.id}/blacklist`;
    const response = await apiPost(path);
    if (!response.ok) {
      notify(response.error || 'Failed to update stream blacklist', 'error');
      return;
    }
    notify('Stream updated', 'success');
    onRefresh();
  };

  const handleActivate = async (stream: any) => {
    if (stream.blacklisted || typeof stream.id !== 'number') return;
    const isPinned =
      activeStream &&
      (String(stream.id) === String(activeStream.id) || stream.infohash === activeStream.infohash);
    if (isPinned) return;
    if (activatingStreamId !== null) return;

    setActivatingStreamId(stream.id);
    const response = await apiPost(`/items/${itemId}/streams/${stream.id}/activate`);
    setActivatingStreamId(null);
    if (!response.ok) {
      notify(response.error || 'Failed to switch stream', 'error');
      return;
    }
    notify('Active stream updated', 'success');
    onRefresh();
  };

  const searchScrapers = async () => {
    setScrapeLoading(true);
    setCandidateStreams({});
    const res = await apiGet('/scrape', { item_id: itemId, media_type: mediaType });
    setScrapeLoading(false);
    if (!res.ok) {
      notify(res.error || 'Scrape failed', 'error');
      return;
    }
    const streams =
      (
        res.data as {
          streams?: Record<string, CandidateStream>;
        }
      )?.streams ?? {};
    setCandidateStreams(streams);
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
      const session: ManualSession = {
        session_id: (raw.session_id as string) ?? (raw.sessionId as string) ?? '',
        item_id: (raw.item_id as number) ?? (raw.itemId as number) ?? 0,
        media_type:
          (raw.media_type as ManualSession['media_type']) ??
          (raw.mediaType as ManualSession['media_type']) ??
          null,
        tmdb_id: (raw.tmdb_id as string | null) ?? (raw.tmdbId as string | null) ?? null,
        tvdb_id: (raw.tvdb_id as string | null) ?? (raw.tvdbId as string | null) ?? null,
        imdb_id: (raw.imdb_id as string | null) ?? (raw.imdbId as string | null) ?? null,
        torrent_id:
          (raw.torrent_id as number | string) ?? (raw.torrentId as number | string) ?? '',
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
        parsedFiles.length > 0
          ? [parsedFiles[0].file_id].filter((id): id is number => !!id)
          : [];
      setSessionData(session);
      setSelectedFileIds(defaultSelection);
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
    setShowMagnetInput(false);
    setMagnet('');
  };

  const handlePickCandidate = async (infohash: string) => {
    setPickLoading(true);
    try {
      await startSessionWithMagnet(`magnet:?xt=urn:btih:${infohash}`);
    } finally {
      setPickLoading(false);
    }
  };

  const candidateList = (Object.entries(candidateStreams) as [string, CandidateStream][]).sort(
    ([, a], [, b]) => (b.rank ?? 0) - (a.rank ?? 0),
  );

  return (
    <div className="panel item-streams">
      <div className="section-head">
        <h3>Streams ({mergedSorted.length})</h3>
        <div style={{ display: 'flex', gap: '0.4rem' }}>
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={() => setShowMagnetInput((v) => !v)}
          >
            Paste Magnet
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={searchScrapers}
            disabled={scrapeLoading}
          >
            {scrapeLoading ? 'Searching…' : 'Search Scrapers'}
          </button>
          <button
            type="button"
            className="btn btn--secondary btn--small"
            onClick={handleReset}
          >
            Reset Streams
          </button>
        </div>
      </div>

      {showMagnetInput && (
        <div className="stream-magnet-input">
          <textarea
            placeholder="Paste magnet link…"
            value={magnet}
            onChange={(e) => setMagnet(e.target.value)}
          />
          <button
            type="button"
            className="btn btn--primary btn--small"
            onClick={handleStartMagnet}
            disabled={sessionLoading}
          >
            {sessionLoading ? 'Starting…' : 'Start Session'}
          </button>
        </div>
      )}

      {mergedSorted.length === 0 ? (
        <p className="muted">No streams stored for this item.</p>
      ) : (
        mergedSorted.map((stream: any) => {
          const isPinned =
            activeStream &&
            (String(stream.id) === String(activeStream.id) ||
              stream.infohash === activeStream.infohash);

          const resolution = stream.resolution as string | undefined;
          const cached =
            typeof stream.is_cached === 'boolean'
              ? stream.is_cached
              : typeof stream.cached === 'boolean'
                ? stream.cached
                : null;

          const isBlacklisted = Boolean(stream.blacklisted);
          const isActivating = activatingStreamId === stream.id;
          const rowClickable = !isBlacklisted && !isActivating;
          const bg =
            !isBlacklisted && typeof stream.rank === 'number'
              ? rankBackground(stream.rank, maxRank)
              : undefined;

          return (
            <div
              key={stream.id ?? stream.infohash}
              role={rowClickable ? 'button' : undefined}
              tabIndex={rowClickable ? 0 : undefined}
              className={`stream-row ${isPinned ? 'stream-row--pinned' : ''} ${
                isBlacklisted ? 'stream-row--blacklisted' : 'stream-row--clickable'
              } ${isActivating ? 'stream-row--activating' : ''}`}
              style={bg ? { background: bg } : undefined}
              onClick={() => rowClickable && handleActivate(stream)}
              onKeyDown={(e) => {
                if (!rowClickable) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleActivate(stream);
                }
              }}
            >
              <div className="stream-row__main">
                <div className="stream-row__title">
                  {stream.raw_title || stream.infohash || `Stream ${stream.id}`}
                </div>
                <div className="stream-row__meta">
                  {typeof stream.rank === 'number' && (
                    <span className="legend-chip legend-chip--rank">Rank {stream.rank}</span>
                  )}
                  {resolution && <ResolutionPill resolution={resolution} />}
                  {cached !== null && (
                    <span
                      className={`legend-chip ${cached ? 'legend-chip--cached' : 'legend-chip--uncached'}`}
                    >
                      {cached ? 'Cached' : 'Uncached'}
                    </span>
                  )}
                  {typeof stream.lev_ratio === 'number' && (
                    <span className="legend-chip legend-chip--score">
                      Score {stream.lev_ratio.toFixed(2)}
                    </span>
                  )}
                </div>
              </div>
              <div
                className="stream-row__actions"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                {isActivating && (
                  <span className="muted" style={{ fontSize: '0.75rem' }}>
                    Switching…
                  </span>
                )}
                {isPinned && (
                  <span className="stream-row__pinned-badge" aria-label="Currently pinned stream">
                    Pinned
                  </span>
                )}
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={() => handleBlacklist(stream)}
                >
                  {stream.blacklisted ? 'Unblacklist' : 'Blacklist'}
                </button>
              </div>
            </div>
          );
        })
      )}

      {candidateList.length > 0 && (
        <div className="stream-candidates">
          <div className="stream-candidates__header">Scraped Candidates</div>
          {candidateList.map(([ih, s]: [string, CandidateStream]) => (
            <div
              key={ih}
              role="button"
              tabIndex={0}
              className="stream-row stream-row--clickable stream-row--candidate"
              onClick={() => !pickLoading && !sessionLoading && handlePickCandidate(ih)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  if (!pickLoading && !sessionLoading) handlePickCandidate(ih);
                }
              }}
            >
              <div className="stream-row__main">
                <div className="stream-row__title">{s.raw_title || ih}</div>
                <div className="stream-row__meta">
                  {s.resolution && <ResolutionPill resolution={s.resolution} />}
                  {s.is_cached != null && (
                    <span
                      className={`legend-chip ${s.is_cached ? 'legend-chip--cached' : 'legend-chip--uncached'}`}
                    >
                      {s.is_cached ? 'Cached' : 'Uncached'}
                    </span>
                  )}
                  {typeof s.rank === 'number' && (
                    <span className="legend-chip legend-chip--rank">Rank {s.rank}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {sessionData && (
        <dialog open className="modal">
          <header>
            <h2>Select Files</h2>
            <button type="button" onClick={() => setSessionData(null)} data-action="close">
              &times;
            </button>
          </header>
          <div className="modal-body">
            <ManualSessionStep
              session={sessionData}
              isMovie={isMovie}
              selectedFileIds={selectedFileIds}
              setSelectedFileIds={setSelectedFileIds}
              onClose={() => setSessionData(null)}
              onSuccess={() => {
                setSessionData(null);
                setCandidateStreams({});
                onRefresh();
              }}
              onReset={() => {
                setSessionData(null);
                setSelectedFileIds([]);
              }}
            />
          </div>
        </dialog>
      )}
    </div>
  );
}

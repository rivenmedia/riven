/**
 * Streams panel: list streams with blacklist/unblacklist, reset; highlights the pinned (active) stream.
 */

import { apiPost } from '../../services/api';
import { notify } from '../../services/notify';

export type StreamsData = {
  streams?: unknown[];
  blacklisted_streams?: unknown[];
  active_stream?: { id: number | string; infohash: string } | null;
};

export interface StreamsProps {
  data: StreamsData;
  itemId: string;
  onRefresh: () => void;
}

export function Streams({ data, itemId, onRefresh }: StreamsProps) {
  const merged = [
    ...(data.streams || []),
    ...(data.blacklisted_streams || []).map((stream: any) => ({
      ...stream,
      blacklisted: true,
    })),
  ];
  const mergedSorted = [...merged].sort(
    (a: any, b: any) => (b.rank ?? 0) - (a.rank ?? 0),
  );
  const activeStream = data.active_stream ?? null;

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

  return (
    <div className="panel item-streams">
      <div className="section-head">
        <h3>Streams ({mergedSorted.length})</h3>
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={handleReset}
        >
          Reset Streams
        </button>
      </div>
      {mergedSorted.length === 0 ? (
        <p className="muted">No streams stored for this item.</p>
      ) : (
        mergedSorted.map((stream: any) => {
          const isPinned =
            activeStream &&
            (String(stream.id) === String(activeStream.id) ||
              stream.infohash === activeStream.infohash);

          const resolution = stream.resolution;
          const cached =
            typeof stream.is_cached === 'boolean'
              ? stream.is_cached
              : typeof stream.cached === 'boolean'
                ? stream.cached
                : null;

          return (
            <div
              key={stream.id ?? stream.infohash}
              className={`stream-row ${isPinned ? 'stream-row--pinned' : ''}`}
            >
              <div className="stream-row__main">
                <div className="stream-row__title">
                  {stream.raw_title || stream.infohash || `Stream ${stream.id}`}
                </div>
                <div className="stream-row__meta">
                  {typeof stream.rank === 'number' && <span>rank {stream.rank}</span>}
                  {resolution && <span>{resolution}</span>}
                  {cached !== null && <span>{cached ? 'cached' : 'uncached'}</span>}
                  {typeof stream.lev_ratio === 'number' && (
                    <span>score {stream.lev_ratio.toFixed(2)}</span>
                  )}
                </div>
              </div>
              <div className="stream-row__actions">
                {isPinned && (
                  <span
                    className="stream-row__pinned-badge"
                    aria-label="Currently pinned stream"
                  >
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
    </div>
  );
}

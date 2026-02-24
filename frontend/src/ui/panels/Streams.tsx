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
        <h3>Streams ({merged.length})</h3>
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={handleReset}
        >
          Reset Streams
        </button>
      </div>
      {merged.length === 0 ? (
        <p className="muted">No streams stored for this item.</p>
      ) : (
        merged.map((stream: any) => {
          const isPinned =
            activeStream &&
            (String(stream.id) === String(activeStream.id) ||
              stream.infohash === activeStream.infohash);
          return (
            <div
              key={stream.id ?? stream.infohash}
              className={`stream-row ${isPinned ? 'stream-row--pinned' : ''}`}
            >
              <span className="stream-row__title">
                {stream.raw_title || stream.infohash || `Stream ${stream.id}`}
              </span>
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
          );
        })
      )}
    </div>
  );
}

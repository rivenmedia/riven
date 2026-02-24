import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader } from '../components/ui/PagePrimitives';
import { MediaGrid } from '../ui/MediaGrid';
import { MediaTypeToggle, type MediaTypeValue } from '../ui/MediaTypeToggle';
import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import { getMediaKind } from '../services/utils';
import type { AppRoute } from '../app/routeTypes';

async function addToLibrary(item: any): Promise<boolean> {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return false;
  const body =
    kind === 'movie'
      ? { tmdb_ids: [String(item.id)], media_type: 'movie' }
      : { tmdb_ids: [String(item.id)], media_type: 'tv' };
  const res = await apiPost('/items/add', body);
  if (!res.ok) {
    notify(res.error || 'Failed to add item', 'error');
    return false;
  }
  notify(`Added "${item.title || item.name}"`, 'success');
  return true;
}

function toExplore(item: any) {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return;
  sessionStorage.setItem(
    'riven_explore_seed',
    JSON.stringify({ kind, id: String(item.id) }),
  );
  window.location.hash = '#/explore';
}

export default function TrendingView({ route }: { route: AppRoute }) {
  const [mediaType, setMediaType] = useState<MediaTypeValue>('movie');
  const [timeWindow, setTimeWindow] = useState<'day' | 'week'>('day');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrending = useCallback(async () => {
    setLoading(true);
    const type = mediaType === 'all' ? 'movie' : mediaType;
    const response = await apiGet(
      `/trending/tmdb/${type}/${timeWindow}`,
    );
    if (!response.ok) {
      setError(response.error || 'Failed to fetch trending media.');
      setItems([]);
      setLoading(false);
      return;
    }
    setItems(response.data?.results || []);
    setError(null);
    setLoading(false);
  }, [mediaType, timeWindow]);

  useEffect(() => {
    fetchTrending();
  }, [fetchTrending]);

  const getActions = (item: any) => {
    const actions: Array<{ label: string; onClick?: (item: any) => void; tone?: string }> = [];
    if (item.in_library && item.library_item_id) {
      actions.push({
        label: 'Open',
        tone: 'secondary',
        onClick: () => {
          window.location.hash = `#/item/${item.library_item_id}`;
        },
      });
    } else if (getMediaKind(item) !== 'person') {
      actions.push({
        label: 'Add',
        tone: 'primary',
        onClick: async () => {
          const added = await addToLibrary(item);
          if (added) fetchTrending();
        },
      });
    }
    actions.push({
      label: 'Graph',
      tone: 'secondary',
      onClick: () => toExplore(item),
    });
    return actions;
  };

  return (
    <ViewLayout className="view-trending" view="trending">
      <ViewHeader
        title="Trending"
        subtitle="Monitor what is hot on TMDB and push content into your library."
      />
      <form
        className="toolbar toolbar--trending"
        onSubmit={(e) => {
          e.preventDefault();
          fetchTrending();
        }}
      >
        <MediaTypeToggle
          value={mediaType}
          includeAll={false}
          onChange={(v) => setMediaType(v)}
        />
        <select
          value={timeWindow}
          onChange={(e) =>
            setTimeWindow(e.target.value as 'day' | 'week')
          }
        >
          <option value="day">Today</option>
          <option value="week">This Week</option>
        </select>
        <button className="btn btn--primary" type="submit">
          Refresh
        </button>
      </form>
      {loading ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="empty-state">{error}</p>
      ) : items.length === 0 ? (
        <p className="empty-state">No trending entries were returned.</p>
      ) : (
        <MediaGrid
          items={items}
          href={null}
          onSelect={(_item, _e) => toExplore(_item)}
          actions={getActions}
        />
      )}
    </ViewLayout>
  );
}

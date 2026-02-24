import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader } from '../components/ui/PagePrimitives';
import { LibraryFilterBar, type LibraryFilterState } from '../ui/LibraryFilterBar';
import { MediaGrid } from '../ui/MediaGrid';
import { MediaList } from '../ui/MediaList';
import { apiDelete, apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import type { AppRoute } from '../app/routeTypes';

const RETURN_ROUTE_KEY = 'riven_return_route';

function normalizeLibraryItem(item: any) {
  return {
    ...item,
    media_type: item.type === 'show' ? 'tv' : item.type,
    in_library: true,
    library_item_id: item.id,
  };
}

async function runAction(action: string, id: string) {
  const ids = [String(id)];
  switch (action) {
    case 'retry':
      return apiPost('/items/retry', { ids });
    case 'reset':
      return apiPost('/items/reset', { ids });
    case 'pause':
      return apiPost('/items/pause', { ids });
    case 'unpause':
      return apiPost('/items/unpause', { ids });
    case 'remove':
      return apiDelete('/items/remove', { ids });
    default:
      return { ok: false, error: `Unknown action: ${action}` };
  }
}

function createActionButtons(
  item: any,
  refresh: () => void,
): Array<{ label: string; onClick?: (item: any) => void; tone?: string }> {
  const pauseLabel = item.state === 'Paused' ? 'Unpause' : 'Pause';
  const pauseAction = item.state === 'Paused' ? 'unpause' : 'pause';
  return [
    {
      label: 'Retry',
      tone: 'secondary',
      onClick: async () => {
        const res = await runAction('retry', item.id);
        if (!res.ok) {
          notify(res.error || 'Retry failed', 'error');
          return;
        }
        notify(`Retried "${item.title}"`, 'success');
        refresh();
      },
    },
    {
      label: pauseLabel,
      tone: 'warning',
      onClick: async () => {
        const res = await runAction(pauseAction, item.id);
        if (!res.ok) {
          notify(res.error || `${pauseLabel} failed`, 'error');
          return;
        }
        notify(`${pauseLabel}d "${item.title}"`, 'success');
        refresh();
      },
    },
    {
      label: 'Reset',
      tone: 'secondary',
      onClick: async () => {
        if (!window.confirm(`Reset "${item.title}" to initial state?`)) return;
        const res = await runAction('reset', item.id);
        if (!res.ok) {
          notify(res.error || 'Reset failed', 'error');
          return;
        }
        notify(`Reset "${item.title}"`, 'success');
        refresh();
      },
    },
    {
      label: 'Remove',
      tone: 'danger',
      onClick: async () => {
        if (!window.confirm(`Remove "${item.title}" from library?`)) return;
        const res = await runAction('remove', item.id);
        if (!res.ok) {
          notify(res.error || 'Remove failed', 'error');
          return;
        }
        notify(`Removed "${item.title}"`, 'warning');
        refresh();
      },
    },
  ];
}

const TITLE_MAP: Record<string, string> = {
  library: 'Library',
  movies: 'Movies',
  shows: 'TV Shows',
  episodes: 'TV Episodes',
};

export default function LibraryView({ route }: { route: AppRoute }) {
  try {
    sessionStorage.setItem(RETURN_ROUTE_KEY, route.name);
  } catch (_) {}

  const forcedType =
    route.name === 'movies'
      ? 'movie'
      : route.name === 'shows'
        ? 'show'
        : route.name === 'episodes'
          ? 'episode'
          : '';
  const useListView = route.name === 'library' || route.name === 'episodes';
  const defaultSort = route.name === 'episodes' ? 'date_desc' : 'date_desc';

  const [filters, setFilters] = useState<LibraryFilterState>({
    search: route.query?.search ?? '',
    state: route.query?.state ?? '',
    sort: route.query?.sort ?? defaultSort,
    limit: Number(route.query?.limit || 24) || 24,
  });
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [items, setItems] = useState<any[]>([]);
  const [states, setStates] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStates = useCallback(async () => {
    const res = await apiGet('/items/states');
    if (res.ok && res.data?.states) {
      setStates(res.data.states);
    }
  }, []);

  useEffect(() => {
    fetchStates();
  }, [fetchStates]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    const params = {
      page,
      limit: filters.limit,
      search: filters.search || undefined,
      sort: filters.sort,
      type: forcedType || undefined,
      states: filters.state || undefined,
    };
    const res = await apiGet('/items', params);
    if (!res.ok) {
      setError(res.error || 'Failed to load library.');
      setItems([]);
      setLoading(false);
      return;
    }
    setTotalPages(res.data?.total_pages ?? 1);
    setItems((res.data?.items || []).map(normalizeLibraryItem));
    setError(null);
    setLoading(false);
  }, [page, filters, forcedType]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleFilterChange = useCallback((next: LibraryFilterState) => {
    setFilters(next);
    setPage(1);
  }, []);

  const subtitle =
    route.name === 'episodes'
      ? 'TV episodes only.'
      : forcedType
        ? `Filtered by ${forcedType === 'movie' ? 'movies' : 'TV shows'}.`
        : 'Manage your local media queue, statuses, and backend actions.';

  return (
    <ViewLayout
      className={`view-library ${route.name === 'movies' ? 'view-movies' : ''} ${route.name === 'shows' ? 'view-shows' : ''} ${route.name === 'episodes' ? 'view-episodes' : ''}`}
      view={route.name}
    >
      <ViewHeader
        title={<h1>{TITLE_MAP[route.name] ?? 'Library'}</h1>}
        subtitle={<p>{subtitle}</p>}
      />
      <LibraryFilterBar
        value={filters}
        onChange={handleFilterChange}
        autoApply
        showApplyButton={false}
        searchDebounceMs={350}
        stateOptions={
          <>
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </>
        }
      />
      {loading ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="empty-state">{error}</p>
      ) : items.length === 0 ? (
        <p className="empty-state">No items matched the current filters.</p>
      ) : useListView ? (
        <div className="media-list-wrap">
          <MediaList
            items={items}
            href={(item) => `#/item/${item.id}`}
            actions={(item) => createActionButtons(item, fetchItems)}
            showPoster
          />
        </div>
      ) : (
        <MediaGrid
          items={items}
          href={(item) => `#/item/${item.id}`}
          actions={(item) => createActionButtons(item, fetchItems)}
        />
      )}
      {totalPages > 1 && (
        <div className="pagination-bar">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </button>
        </div>
      )}
    </ViewLayout>
  );
}

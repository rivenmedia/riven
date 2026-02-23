import { apiDelete, apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import * as statusTracker from '../services/statusTracker';
import { attachLibraryFilterBar } from '../ui/libraryFilterBar';
import { renderMediaGrid } from '../ui/mediaGrid';
import { renderMediaList } from '../ui/mediaList';

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

function createActionButtons(item: any, refresh: () => void) {
  const pauseLabel = item.state === 'Paused' ? 'Unpause' : 'Pause';
  const pauseAction = item.state === 'Paused' ? 'unpause' : 'pause';
  return [
    {
      label: 'Retry',
      tone: 'secondary' as const,
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
      tone: 'warning' as const,
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
      tone: 'secondary' as const,
      onClick: async () => {
        const confirmed = window.confirm(`Reset "${item.title}" to initial state?`);
        if (!confirmed) return;
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
      tone: 'danger' as const,
      onClick: async () => {
        const confirmed = window.confirm(`Remove "${item.title}" from library?`);
        if (!confirmed) return;
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

function renderPagination(
  container: HTMLElement | null,
  page: number,
  totalPages: number,
  onPageChange: (p: number) => void,
) {
  if (!container) return;
  container.innerHTML = '';
  if (totalPages <= 1) return;

  const prev = document.createElement('button');
  prev.className = 'btn btn--secondary';
  prev.type = 'button';
  prev.textContent = 'Previous';
  prev.disabled = page <= 1;
  prev.addEventListener('click', () => onPageChange(page - 1));
  container.appendChild(prev);

  const label = document.createElement('span');
  label.textContent = `Page ${page} / ${totalPages}`;
  container.appendChild(label);

  const next = document.createElement('button');
  next.className = 'btn btn--secondary';
  next.type = 'button';
  next.textContent = 'Next';
  next.disabled = page >= totalPages;
  next.addEventListener('click', () => onPageChange(page + 1));
  container.appendChild(next);
}

const RETURN_ROUTE_KEY = 'riven_return_route';

export async function load(route: { name: string; query?: Record<string, string> }, container: HTMLElement) {
  try {
    sessionStorage.setItem(RETURN_ROUTE_KEY, route.name);
  } catch (_) {}

  const forcedType =
    route.name === 'movies' ? 'movie' : route.name === 'shows' ? 'show' : route.name === 'episodes' ? 'episode' : '';
  const useListView = route.name === 'library' || route.name === 'episodes';
  const titleMap: Record<string, string> = {
    library: 'Library',
    movies: 'Movies',
    shows: 'TV Shows',
    episodes: 'TV Episodes',
  };
  const defaultSort = route.name === 'episodes' ? 'date_desc' : 'date_desc';

  const titleElement = container.querySelector<HTMLElement>('[data-slot="title"]');
  const subtitleElement = container.querySelector<HTMLElement>('[data-slot="subtitle"]');
  const gridElement = container.querySelector<HTMLElement>('[data-slot="grid"]');
  const listElement = container.querySelector<HTMLElement>('[data-slot="list"]');
  const emptyElement = container.querySelector<HTMLElement>('[data-slot="empty"]');
  const paginationElement = container.querySelector<HTMLElement>('[data-slot="pagination"]');
  const filterForm = container.querySelector<HTMLFormElement>('[data-slot="filters"]');

  if (titleElement) titleElement.textContent = titleMap[route.name] ?? 'Library';
  if (subtitleElement) {
    if (route.name === 'episodes') subtitleElement.textContent = 'TV episodes only.';
    else if (forcedType)
      subtitleElement.textContent = `Filtered by ${forcedType === 'movie' ? 'movies' : 'TV shows'}.`;
    else subtitleElement.textContent = 'Manage your local media queue, statuses, and backend actions.';
  }

  if (gridElement) gridElement.hidden = useListView;
  if (listElement) listElement.hidden = !useListView;

  let page = 1;
  let totalPages = 1;
  const filters = {
    search: route.query?.search ?? '',
    state: route.query?.state ?? '',
    sort: route.query?.sort ?? defaultSort,
    limit: Number(route.query?.limit || 24) || 24,
  };

  const statesRes = await apiGet('/items/states');
  const states = statesRes.ok ? statesRes.data?.states || [] : [];
  const stateSelect = filterForm?.querySelector<HTMLSelectElement>('[data-slot="state"]');
  if (stateSelect) {
    stateSelect.innerHTML = '<option value="">All states</option>';
    states.forEach((state) => {
      const option = document.createElement('option');
      option.value = state;
      option.textContent = state;
      stateSelect.appendChild(option);
    });
    if (filters.state && states.includes(filters.state)) stateSelect.value = filters.state;
  }

  const searchInput = filterForm?.querySelector<HTMLInputElement>('[data-slot="search"]');
  const sortSelect = filterForm?.querySelector<HTMLSelectElement>('[data-slot="sort"]');
  const limitSelect = filterForm?.querySelector<HTMLSelectElement>('[data-slot="limit"]');
  if (searchInput) searchInput.value = filters.search;
  if (sortSelect) sortSelect.value = filters.sort;
  if (limitSelect) limitSelect.value = String(filters.limit);

  async function fetchItems() {
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
      if (gridElement) gridElement.innerHTML = '';
      if (listElement) listElement.innerHTML = '';
      if (emptyElement) {
        emptyElement.hidden = false;
        emptyElement.textContent = res.error || 'Failed to load library.';
      }
      return;
    }

    totalPages = res.data?.total_pages ?? 1;
    const items = (res.data?.items || []).map(normalizeLibraryItem);

    if (useListView && listElement) {
      renderMediaList(listElement, items, {
        href: (item) => `#/item/${item.id}`,
        actions: (item) => createActionButtons(item, fetchItems),
        showPoster: true,
      });
    } else if (gridElement) {
      renderMediaGrid(gridElement, items, {
        href: (item) => `#/item/${item.id}`,
        actions: (item) => createActionButtons(item, fetchItems),
      });
    }

    if (emptyElement) {
      const hasItems = items.length > 0;
      emptyElement.hidden = hasItems;
      if (!hasItems) emptyElement.textContent = 'No items matched the current filters.';
    }

    renderPagination(paginationElement, page, totalPages, (nextPage) => {
      if (nextPage < 1 || nextPage > totalPages) return;
      page = nextPage;
      fetchItems();
    });
    statusTracker.setTracked(useListView ? listElement : gridElement, 'library');
  }

  attachLibraryFilterBar(filterForm, {
    initial: filters,
    autoApply: true,
    showApplyButton: false,
    searchDebounceMs: 350,
    onChange: (next) => {
      filters.search = next.search;
      filters.state = next.state;
      filters.sort = next.sort;
      filters.limit = next.limit;
      page = 1;
      fetchItems();
    },
  });

  await fetchItems();
}

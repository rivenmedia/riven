import { apiDelete, apiGet, apiPost } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';
import { notify } from '../notify.js';

function normalizeLibraryItem(item) {
  return {
    ...item,
    media_type: item.type === 'show' ? 'tv' : item.type,
    in_library: true,
    library_item_id: item.id,
  };
}

async function runAction(action, id) {
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

function createActionButtons(item, refresh) {
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
      tone: 'danger',
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

function renderPagination(container, page, totalPages, onPageChange) {
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

export async function load(route, container) {
  const forcedType = route.name === 'movies' ? 'movie' : route.name === 'shows' ? 'show' : '';
  const titleMap = {
    library: 'Library',
    movies: 'Movies',
    shows: 'TV Shows',
  };

  const titleElement = container.querySelector('[data-slot="title"]');
  const subtitleElement = container.querySelector('[data-slot="subtitle"]');
  const gridElement = container.querySelector('[data-slot="grid"]');
  const emptyElement = container.querySelector('[data-slot="empty"]');
  const paginationElement = container.querySelector('[data-slot="pagination"]');
  const filterForm = container.querySelector('[data-slot="filters"]');
  const searchInput = container.querySelector('[data-slot="search"]');
  const stateSelect = container.querySelector('[data-slot="state"]');
  const sortSelect = container.querySelector('[data-slot="sort"]');
  const limitSelect = container.querySelector('[data-slot="limit"]');

  if (titleElement) titleElement.textContent = titleMap[route.name] || 'Library';
  if (subtitleElement && forcedType) {
    subtitleElement.textContent = `Filtered by ${forcedType === 'movie' ? 'movies' : 'TV shows'}.`;
  }

  let page = 1;
  let totalPages = 1;
  const filters = {
    search: '',
    state: '',
    sort: 'date_desc',
    limit: 24,
  };

  const statesRes = await apiGet('/items/states');
  const states = statesRes.ok ? statesRes.data?.states || [] : [];
  if (stateSelect) {
    stateSelect.innerHTML = '<option value="">All states</option>';
    states.forEach((state) => {
      const option = document.createElement('option');
      option.value = state;
      option.textContent = state;
      stateSelect.appendChild(option);
    });
  }

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
      if (emptyElement) {
        emptyElement.hidden = false;
        emptyElement.textContent = res.error || 'Failed to load library.';
      }
      return;
    }

    totalPages = res.data?.total_pages || 1;
    const items = (res.data?.items || []).map(normalizeLibraryItem);
    if (gridElement) {
      gridElement.innerHTML = '';
      items.forEach((item) => {
        gridElement.appendChild(
          renderMediaCard(item, {
            href: `#/item/${item.id}`,
            actions: createActionButtons(item, fetchItems),
          }),
        );
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
  }

  if (filterForm) {
    filterForm.addEventListener('submit', (event) => {
      event.preventDefault();
      filters.search = searchInput?.value?.trim() || '';
      filters.state = stateSelect?.value || '';
      filters.sort = sortSelect?.value || 'date_desc';
      filters.limit = Number(limitSelect?.value || 24);
      page = 1;
      fetchItems();
    });
  }

  await fetchItems();
}

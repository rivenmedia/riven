/**
 * Library view - items grid with filters
 */

import { apiGet, apiPost, apiDelete } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';

function extractYear(airedAt) {
  if (!airedAt) return 'N/A';
  const y = new Date(airedAt).getFullYear();
  return isNaN(y) ? 'N/A' : y;
}

function transformItem(item) {
  return {
    id: item.id,
    riven_id: item.id,
    title: item.title,
    poster_path: item.poster_path,
    media_type: item.type,
    year: extractYear(item.aired_at),
    type: item.type,
    state: item.state,
  };
}

export async function load(route, container) {
  const typeFilter = route.name === 'movies' ? 'movie' : route.name === 'shows' ? 'show' : '';
  const title = route.name === 'movies' ? 'Movies' : route.name === 'shows' ? 'TV Shows' : 'Library';

  const titleEl = container.querySelector('[data-slot="title"]');
  if (titleEl) titleEl.textContent = title;

  const grid = container.querySelector('[data-slot="grid"]');
  const pagination = container.querySelector('[data-slot="pagination"]');
  const filters = container.querySelector('[data-slot="filters"]');
  const searchInput = container.querySelector('[data-slot="search"]');
  const typeSelect = container.querySelector('[data-slot="type"]');

  let page = 1;
  let search = '';
  let type = typeFilter;
  let totalPages = 1;

  async function fetchItems() {
    const params = { page, limit: 24 };
    if (search) params.search = search;
    if (type) params.type = type;
    const res = await apiGet('/items', params);
    if (!res.ok) return;
    const data = res.data;
    totalPages = data?.total_pages || 1;
    const items = (data?.items || []).map(transformItem);
    renderGrid(grid, items);
    renderPagination(pagination, page, totalPages, (p) => {
      page = p;
      fetchItems();
    });
  }

  if (filters) {
    filters.onsubmit = (e) => {
      e.preventDefault();
      search = searchInput?.value?.trim() || '';
      type = typeSelect?.value || typeFilter;
      page = 1;
      fetchItems();
    };
  }

  await fetchItems();
}

function renderGrid(grid, items) {
  if (!grid) return;
  grid.innerHTML = '';
  items.forEach((item) => {
    const card = renderMediaCard(item, `#/item/${item.id}`, {
      actions: [
        { label: 'Retry', onClick: () => runItemAction('retry', item.id, () => fetchItems()) },
        { label: 'Delete', onClick: () => runItemAction('delete', item.id, () => fetchItems()) },
      ],
    });
    grid.appendChild(card);
  });
}

async function runItemAction(action, id, refresh) {
  const ids = [String(id)];
  let res;
  if (action === 'retry') {
    res = await apiPost('/items/retry', { ids });
  } else if (action === 'delete') {
    if (!confirm('Delete this item?')) return;
    res = await apiDelete('/items/remove', { ids });
  } else return;
  if (res?.ok) refresh();
}

function renderPagination(container, page, totalPages, onPageChange) {
  if (!container || totalPages <= 1) {
    if (container) container.innerHTML = '';
    return;
  }
  container.innerHTML = '';
  if (page > 1) {
    const prev = document.createElement('button');
    prev.textContent = 'Previous';
    prev.onclick = () => onPageChange(page - 1);
    container.appendChild(prev);
  }
  const span = document.createElement('span');
  span.textContent = `Page ${page} of ${totalPages}`;
  container.appendChild(span);
  if (page < totalPages) {
    const next = document.createElement('button');
    next.textContent = 'Next';
    next.onclick = () => onPageChange(page + 1);
    container.appendChild(next);
  }
}

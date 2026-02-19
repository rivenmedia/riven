/**
 * Explore view - search TMDB/TVDB
 */

import { apiGet } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';
import { apiPost } from '../api.js';

export async function load(route, container) {
  const grid = container.querySelector('[data-slot="grid"]');
  const form = container.querySelector('[data-slot="search-form"]');
  const queryInput = container.querySelector('[data-slot="query"]');
  const sourceSelect = container.querySelector('[data-slot="source"]');
  const typeSelect = container.querySelector('[data-slot="type"]');

  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const q = queryInput?.value?.trim();
      if (!q) return;
      const source = sourceSelect?.value || 'tmdb';
      const type = typeSelect?.value || 'movie';
      grid.innerHTML = '<p>Searching...</p>';
      let path;
      if (source === 'tmdb') {
        path = type === 'movie' ? '/search/tmdb/movie' : '/search/tmdb/tv';
      } else {
        path = '/search/tvdb';
      }
      const res = await apiGet(path, source === 'tvdb' ? { query: q } : { query: q });
      if (!res.ok) {
        grid.innerHTML = '<p>Search failed</p>';
        return;
      }
      const items = res.data?.results || [];
      renderDiscoveryGrid(grid, items, type === 'movie' ? 'tmdb' : 'tvdb');
    };
  }
  grid.innerHTML = '<p>Enter a search query above</p>';
}

function renderDiscoveryGrid(grid, items, indexer) {
  grid.innerHTML = '';
  items.forEach((item) => {
    const wrap = document.createElement('div');
    wrap.className = 'discovery-card-wrap';
    const card = renderMediaCard(item, 'javascript:void(0)');
    wrap.appendChild(card);
    const canAdd = (indexer === 'tmdb' && item.media_type === 'movie') || indexer === 'tvdb';
    if (canAdd) {
      const addBtn = document.createElement('button');
      addBtn.textContent = 'Add to Library';
      addBtn.className = 'add-btn';
      addBtn.onclick = (e) => {
        e.preventDefault();
        addToLibrary(item, indexer);
      };
      wrap.appendChild(addBtn);
    }
    grid.appendChild(wrap);
  });
}

async function addToLibrary(item, indexer) {
  const body =
    indexer === 'tmdb'
      ? { tmdb_ids: [item.id], media_type: 'movie' }
      : { tvdb_ids: [item.id], media_type: 'tv' };
  const res = await apiPost('/items/add', body);
  if (res.ok) alert('Added to library!');
  else alert('Failed to add');
}

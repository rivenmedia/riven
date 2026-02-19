/**
 * Trending view - TMDB trending
 */

import { apiGet } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';

export async function load(route, container) {
  const grid = container.querySelector('[data-slot="grid"]');
  const tabs = container.querySelector('[data-slot="tabs"]');

  let currentTab = 'movie-day';

  async function fetchTrending(type, window) {
    const res = await apiGet(`/trending/tmdb/${type}/${window}`);
    if (!res.ok) return;
    const items = res.data?.results || [];
    grid.innerHTML = '';
    items.forEach((item) => {
      grid.appendChild(renderMediaCard(item, `#/item/${item.id}`));
    });
  }

  if (tabs) {
    tabs.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.onclick = () => {
        currentTab = btn.dataset.tab;
        const [type, window] = currentTab.split('-');
        fetchTrending(type, window);
      };
    });
  }

  await fetchTrending('movie', 'day');
}

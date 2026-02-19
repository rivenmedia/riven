import { apiGet, apiPost } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';
import { notify } from '../notify.js';
import { getMediaKind } from '../utils.js';

async function addToLibrary(item) {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return;
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

function toExplore(item) {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return;
  sessionStorage.setItem(
    'riven_explore_seed',
    JSON.stringify({ kind, id: String(item.id) }),
  );
  window.location.hash = '#/explore';
}

export async function load(route, container) {
  const controls = container.querySelector('[data-slot="controls"]');
  const typeSelect = container.querySelector('[data-slot="media-type"]');
  const windowSelect = container.querySelector('[data-slot="window"]');
  const grid = container.querySelector('[data-slot="grid"]');
  const empty = container.querySelector('[data-slot="empty"]');

  const state = {
    mediaType: 'movie',
    window: 'day',
  };

  async function fetchTrending() {
    const response = await apiGet(`/trending/tmdb/${state.mediaType}/${state.window}`);
    if (!response.ok) {
      if (grid) grid.innerHTML = '';
      if (empty) {
        empty.hidden = false;
        empty.textContent = response.error || 'Failed to fetch trending media.';
      }
      return;
    }

    const items = response.data?.results || [];
    if (grid) {
      grid.innerHTML = '';
      items.forEach((item) => {
        const actions = [];
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

        grid.appendChild(
          renderMediaCard(item, {
            onSelect: () => toExplore(item),
            actions,
          }),
        );
      });
    }

    if (empty) {
      empty.hidden = items.length > 0;
      if (!items.length) empty.textContent = 'No trending entries were returned.';
    }
  }

  if (controls) {
    controls.addEventListener('submit', (event) => {
      event.preventDefault();
      state.mediaType = typeSelect?.value || 'movie';
      state.window = windowSelect?.value || 'day';
      fetchTrending();
    });
  }

  await fetchTrending();
}

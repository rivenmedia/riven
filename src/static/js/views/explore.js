import { apiGet, apiPost } from '../api.js';
import { renderMediaCard } from '../components/media_card.js';
import { notify } from '../notify.js';
import { formatYear, getMediaKind, sortByPopularity, toCsv } from '../utils.js';

function toCardItem(entry, fallbackKind = null) {
  const kind = fallbackKind || getMediaKind(entry);
  return {
    ...entry,
    id: String(entry.id),
    title: entry.title || entry.name || 'Unknown',
    media_type: kind === 'mixed' ? entry.media_type : kind,
    year:
      entry.year ||
      (entry.release_date ? String(entry.release_date).slice(0, 4) : '') ||
      (entry.first_air_date ? String(entry.first_air_date).slice(0, 4) : ''),
  };
}

async function annotateLibraryStatus(items) {
  const media = items.filter((item) => {
    const kind = getMediaKind(item);
    return kind === 'movie' || kind === 'tv';
  });

  if (!media.length) return items;

  const tmdbIds = [];
  const tvdbIds = [];
  media.forEach((item) => {
    if (item.indexer === 'tvdb') {
      tvdbIds.push(String(item.tvdb_id || item.id));
      return;
    }
    tmdbIds.push(String(item.tmdb_id || item.id));
    if (item.tvdb_id) tvdbIds.push(String(item.tvdb_id));
  });

  const res = await apiGet('/items/library/status', {
    tmdb_ids: toCsv(tmdbIds),
    tvdb_ids: toCsv(tvdbIds),
  });
  if (!res.ok) return items;

  media.forEach((item) => {
    const tmdbKey = String(item.tmdb_id || item.id);
    const tvdbKey = String(item.tvdb_id || item.id);
    const status =
      (item.indexer === 'tvdb' ? res.data?.tvdb?.[tvdbKey] : null) ||
      res.data?.tmdb?.[tmdbKey] ||
      res.data?.tvdb?.[tvdbKey];
    if (!status) return;
    item.in_library = Boolean(status.in_library);
    item.library_item_id = status.library_item_id || null;
    item.library_state = status.library_state || null;
  });

  return items;
}

async function addItemToLibrary(item) {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return false;

  let payload;
  if (kind === 'movie') {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'movie' };
  } else if (item.indexer === 'tvdb') {
    payload = { tvdb_ids: [String(item.tvdb_id || item.id)], media_type: 'tv' };
  } else {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'tv' };
  }

  const res = await apiPost('/items/add', payload);
  if (!res.ok) {
    notify(res.error || 'Failed to add media', 'error');
    return false;
  }

  notify(`Added "${item.title || item.name}" to library`, 'success');
  return true;
}

function renderPagination(container, page, totalPages, onChange) {
  if (!container) return;
  container.innerHTML = '';
  if (totalPages <= 1) return;

  const prev = document.createElement('button');
  prev.type = 'button';
  prev.className = 'btn btn--secondary btn--small';
  prev.textContent = 'Previous';
  prev.disabled = page <= 1;
  prev.addEventListener('click', () => onChange(page - 1));
  container.appendChild(prev);

  const label = document.createElement('span');
  label.textContent = `Page ${page} / ${totalPages}`;
  container.appendChild(label);

  const next = document.createElement('button');
  next.type = 'button';
  next.className = 'btn btn--secondary btn--small';
  next.textContent = 'Next';
  next.disabled = page >= totalPages;
  next.addEventListener('click', () => onChange(page + 1));
  container.appendChild(next);
}

function renderBreadcrumbs(container, history, onSelect) {
  if (!container) return;
  container.innerHTML = '';
  if (!history.length) return;

  history.forEach((node, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pill';
    button.textContent = node.label || `${node.kind} ${node.id}`;
    button.addEventListener('click', () => onSelect(index));
    container.appendChild(button);
  });
}

function renderDetailCards(title, items, target, onSelect) {
  if (!items.length) return;

  const section = document.createElement('section');
  section.className = 'panel';
  const heading = document.createElement('h3');
  heading.textContent = title;
  section.appendChild(heading);

  const grid = document.createElement('div');
  grid.className = 'detail-link-grid';
  items.forEach((item) => {
    grid.appendChild(
      renderMediaCard(item, {
        compact: true,
        onSelect: () =>
          onSelect({
            kind: getMediaKind(item),
            id: String(item.id),
            label: item.title || item.name,
            source: item.indexer || 'tmdb',
          }),
      }),
    );
  });

  section.appendChild(grid);
  target.appendChild(section);
}

function renderCastPills(title, cast, target, onSelectPerson) {
  if (!cast.length) return;
  const section = document.createElement('section');
  section.className = 'panel';
  const heading = document.createElement('h3');
  heading.textContent = title;
  section.appendChild(heading);

  const list = document.createElement('div');
  list.className = 'pill-list';
  cast.forEach((person) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pill';
    button.textContent = person.name;
    button.addEventListener('click', () =>
      onSelectPerson({
        kind: 'person',
        id: String(person.id),
        label: person.name,
        source: 'tmdb',
      }),
    );
    list.appendChild(button);
  });
  section.appendChild(list);
  target.appendChild(section);
}

function renderDetailHeader(detail, kind, onAction) {
  const wrap = document.createElement('section');
  wrap.className = 'panel';

  const head = document.createElement('div');
  head.className = 'detail-head';
  const image = document.createElement('img');
  const poster = detail.poster_path || detail.profile_path || '';
  image.src = poster ? (poster.startsWith('http') ? poster : `https://image.tmdb.org/t/p/w500${poster}`) : '';
  image.alt = detail.title || detail.name || 'media';

  const right = document.createElement('div');
  const title = document.createElement('h3');
  title.textContent = detail.title || detail.name || 'Unknown';
  right.appendChild(title);

  const meta = document.createElement('p');
  const bits = [
    kind === 'person' ? detail.known_for_department : kind.toUpperCase(),
    formatYear(detail),
    detail.vote_average ? `Rating ${Number(detail.vote_average).toFixed(1)}` : null,
    detail.library?.library_state || detail.library_state || null,
  ].filter(Boolean);
  meta.className = 'muted';
  meta.textContent = bits.join(' · ') || '—';
  right.appendChild(meta);

  const overview = document.createElement('p');
  overview.textContent = detail.overview || detail.biography || 'No summary available.';
  overview.className = 'muted';
  right.appendChild(overview);

  const actionRow = document.createElement('div');
  actionRow.className = 'toolbar';
  const actionButton = document.createElement('button');
  actionButton.type = 'button';
  actionButton.className = 'btn btn--primary btn--small';
  actionButton.textContent = onAction.label;
  actionButton.addEventListener('click', onAction.onClick);
  actionRow.appendChild(actionButton);
  right.appendChild(actionRow);

  head.appendChild(image);
  head.appendChild(right);
  wrap.appendChild(head);
  return wrap;
}

export async function load(route, container) {
  const form = container.querySelector('[data-slot="search-form"]');
  const sourceSelect = container.querySelector('[data-slot="source"]');
  const modeSelect = container.querySelector('[data-slot="mode"]');
  const typeSelect = container.querySelector('[data-slot="type"]');
  const queryInput = container.querySelector('[data-slot="query"]');
  const grid = container.querySelector('[data-slot="grid"]');
  const empty = container.querySelector('[data-slot="empty"]');
  const pagination = container.querySelector('[data-slot="pagination"]');
  const resultTitle = container.querySelector('[data-slot="results-title"]');
  const detail = container.querySelector('[data-slot="detail"]');
  const breadcrumbs = container.querySelector('[data-slot="breadcrumbs"]');

  const state = {
    source: 'tmdb',
    mode: 'search',
    type: 'movie',
    query: '',
    page: 1,
    totalPages: 1,
    history: [],
  };

  function syncControls() {
    if (sourceSelect) sourceSelect.value = state.source;
    if (modeSelect) modeSelect.value = state.mode;
    if (typeSelect) typeSelect.value = state.type;
    if (queryInput) queryInput.value = state.query;
  }

  async function fetchResults() {
    if (resultTitle) resultTitle.textContent = 'Loading…';
    if (grid) grid.innerHTML = '';
    if (empty) empty.hidden = true;

    let response;
    if (state.source === 'tvdb') {
      if (!state.query) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = 'TVDB search requires a query.';
        }
        return;
      }

      response = await apiGet('/search/tvdb', {
        query: state.query,
        limit: 20,
        offset: (state.page - 1) * 20,
      });
    } else if (state.mode === 'discover') {
      if (state.type === 'all') {
        response = await apiGet('/trending/tmdb/all/week');
      } else {
        response = await apiGet(`/discover/tmdb/${state.type}`, { page: state.page });
      }
    } else if (state.type === 'all') {
      response = await apiGet('/search/tmdb/multi', {
        query: state.query,
        page: state.page,
        include_people: true,
      });
    } else {
      response = await apiGet(`/search/tmdb/${state.type}`, {
        query: state.query,
        page: state.page,
      });
    }

    if (!response?.ok) {
      if (empty) {
        empty.hidden = false;
        empty.textContent = response?.error || 'Search failed.';
      }
      if (resultTitle) resultTitle.textContent = 'Results';
      return;
    }

    const items = (response.data?.results || []).map((entry) => toCardItem(entry));
    state.totalPages = Number(response.data?.total_pages || 1);
    if (resultTitle) resultTitle.textContent = `Results (${response.data?.total_results || items.length})`;

    if (grid) {
      grid.innerHTML = '';
      items.forEach((item) => {
        const kind = getMediaKind(item);
        const actions = [];

        if ((kind === 'movie' || kind === 'tv') && item.in_library && item.library_item_id) {
          actions.push({
            label: 'Open',
            tone: 'secondary',
            onClick: () => {
              window.location.hash = `#/item/${item.library_item_id}`;
            },
          });
        } else if (kind === 'movie' || kind === 'tv') {
          actions.push({
            label: 'Add',
            tone: 'primary',
            onClick: async () => {
              const ok = await addItemToLibrary(item);
              if (ok) fetchResults();
            },
          });
        }

        grid.appendChild(
          renderMediaCard(item, {
            onSelect: () => {
              if (kind === 'movie' || kind === 'tv' || kind === 'person') {
                selectNode({
                  kind,
                  id: String(item.id),
                  label: item.title || item.name,
                  source: item.indexer || 'tmdb',
                });
              }
            },
            actions,
          }),
        );
      });
    }

    if (empty) {
      empty.hidden = items.length > 0;
      if (!items.length) empty.textContent = 'No results.';
    }

    renderPagination(pagination, state.page, state.totalPages, (nextPage) => {
      if (nextPage < 1 || nextPage > state.totalPages) return;
      state.page = nextPage;
      fetchResults();
    });
  }

  async function selectNode(node, updateHistory = true) {
    if (updateHistory) {
      const last = state.history[state.history.length - 1];
      const lastKey = `${last?.source || 'tmdb'}:${last?.kind}:${last?.id}`;
      const nextKey = `${node.source || 'tmdb'}:${node.kind}:${node.id}`;
      if (!last || lastKey !== nextKey) {
        state.history.push(node);
      }
    }

    renderBreadcrumbs(breadcrumbs, state.history, (index) => {
      state.history = state.history.slice(0, index + 1);
      const target = state.history[index];
      selectNode(target, false);
    });

    if (!detail) return;
    detail.innerHTML = '<p class="muted">Loading details…</p>';

    if (node.kind === 'person') {
      const [personRes, creditsRes] = await Promise.all([
        apiGet(`/tmdb/person/${node.id}`),
        apiGet(`/tmdb/person/${node.id}/combined_credits`),
      ]);
      if (!personRes.ok || !creditsRes.ok) {
        detail.innerHTML = `<p class="muted">${personRes.error || creditsRes.error || 'Failed to load person.'}</p>`;
        return;
      }

      const person = personRes.data || {};
      const credits = [...(creditsRes.data?.cast || []), ...(creditsRes.data?.crew || [])]
        .map((entry) => toCardItem(entry))
        .filter((entry, index, arr) => arr.findIndex((candidate) => candidate.id === entry.id && getMediaKind(candidate) === getMediaKind(entry)) === index);

      await annotateLibraryStatus(credits);
      const rankedCredits = sortByPopularity(credits).slice(0, 24);

      detail.innerHTML = '';
      detail.appendChild(
        renderDetailHeader(person, 'person', {
          label: 'Back to Results',
          onClick: () => {
            const root = state.history[0];
            if (root) selectNode(root, false);
          },
        }),
      );
      renderDetailCards('Known Works', rankedCredits, detail, selectNode);
      return;
    }

    if (node.source === 'tvdb' && node.kind === 'tv') {
      const [tvdbRes, statusRes] = await Promise.all([
        apiGet(`/tvdb/series/${node.id}`),
        apiGet('/items/library/status', { tvdb_ids: String(node.id) }),
      ]);
      if (!tvdbRes.ok) {
        detail.innerHTML = `<p class="muted">${tvdbRes.error || 'Failed to load TVDB details.'}</p>`;
        return;
      }

      const series = tvdbRes.data || {};
      const status = statusRes.data?.tvdb?.[String(node.id)] || null;
      series.in_library = Boolean(status?.in_library);
      series.library_item_id = status?.library_item_id || null;
      series.library_state = status?.library_state || null;
      series.poster_path = series.image || series.poster_path;
      series.title = series.name || series.title;

      detail.innerHTML = '';
      detail.appendChild(
        renderDetailHeader(series, 'tv', {
          label:
            series.in_library && series.library_item_id
              ? 'Open Library Item'
              : 'Add to Library',
          onClick: async () => {
            if (series.in_library && series.library_item_id) {
              window.location.hash = `#/item/${series.library_item_id}`;
              return;
            }
            const ok = await addItemToLibrary({
              ...series,
              media_type: 'tv',
              id: node.id,
              indexer: 'tvdb',
              tvdb_id: node.id,
            });
            if (!ok) return;
            await fetchResults();
            await selectNode(node, false);
          },
        }),
      );
      return;
    }

    const detailRes = await apiGet(`/tmdb/${node.kind}/${node.id}`);
    if (!detailRes.ok) {
      detail.innerHTML = `<p class="muted">${detailRes.error || 'Failed to load media details.'}</p>`;
      return;
    }

    const media = detailRes.data || {};
    const recommendations = (media.recommendations?.results || []).map((entry) =>
      toCardItem(entry, node.kind),
    );
    const similar = (media.similar?.results || []).map((entry) =>
      toCardItem(entry, node.kind),
    );
    await annotateLibraryStatus(recommendations);
    await annotateLibraryStatus(similar);

    detail.innerHTML = '';
    detail.appendChild(
      renderDetailHeader(media, node.kind, {
        label:
          media.library?.in_library && media.library?.library_item_id
            ? 'Open Library Item'
            : 'Add to Library',
        onClick: async () => {
          if (media.library?.in_library && media.library?.library_item_id) {
            window.location.hash = `#/item/${media.library.library_item_id}`;
            return;
          }
          const ok = await addItemToLibrary({ ...media, media_type: node.kind });
          if (!ok) return;
          await fetchResults();
          await selectNode(node, false);
        },
      }),
    );

    const cast = (media.credits?.cast || []).slice(0, 18);
    renderCastPills('Cast', cast, detail, selectNode);
    renderDetailCards('Recommendations', recommendations.slice(0, 12), detail, selectNode);
    renderDetailCards('Similar', similar.slice(0, 12), detail, selectNode);
  }

  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      state.source = sourceSelect?.value || 'tmdb';
      state.mode = modeSelect?.value || 'search';
      state.type = typeSelect?.value || 'movie';
      state.query = queryInput?.value?.trim() || '';
      state.page = 1;

      if (state.mode === 'search' && !state.query && state.source === 'tmdb') {
        notify('Enter a query for TMDB search', 'warning');
      }

      fetchResults();
    });
  }

  const seedRaw = sessionStorage.getItem('riven_explore_seed');
  if (seedRaw) {
    sessionStorage.removeItem('riven_explore_seed');
    try {
      const seed = JSON.parse(seedRaw);
      if (seed?.kind && seed?.id) {
        state.source = 'tmdb';
        state.mode = 'discover';
        state.type = seed.kind === 'tv' ? 'tv' : 'movie';
        syncControls();
        fetchResults();
        selectNode({
          kind: seed.kind,
          id: String(seed.id),
          label: seed.label || `${seed.kind} ${seed.id}`,
          source: seed.source || 'tmdb',
        });
        return;
      }
    } catch {
      // ignore malformed seed
    }
  }

  syncControls();
  await fetchResults();
}

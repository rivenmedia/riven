import { renderMediaCard } from '../ui/mediaCard';
import { createMediaTypeToggle } from '../ui/mediaTypeToggle';
import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import { replaceRoute } from '../services/router';
import * as statusTracker from '../services/statusTracker';
import { formatYear, getMediaKind, sortByPopularity, toCsv } from '../services/utils';

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

function parsePositiveInt(value, fallback = 1) {
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseNode(raw) {
  if (!raw) return null;
  const [source, kind, id] = String(raw).split('|');
  if (!id || !kind) return null;
  return {
    source: source || 'tmdb',
    kind,
    id: String(id),
    label: `${kind} ${id}`,
  };
}

function serializeNode(node) {
  if (!node?.id || !node?.kind) return '';
  return `${node.source || 'tmdb'}|${node.kind}|${node.id}`;
}

function parseTrail(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((node) => ({
        source: node?.source || 'tmdb',
        kind: node?.kind,
        id: node?.id ? String(node.id) : null,
        label: node?.label || `${node?.kind || 'node'} ${node?.id || ''}`.trim(),
      }))
      .filter((node) => node.kind && node.id);
  } catch {
    return [];
  }
}

function buildRouteQuery(state) {
  const query: {
    source: string;
    mode: string;
    type: string;
    q?: string;
    page?: number;
    node?: string;
    trail?: string;
  } = {
    source: state.source,
    mode: state.mode,
    type: state.type,
    q: state.query || undefined,
    page: state.page > 1 ? state.page : undefined,
  };

  if (state.history.length) {
    const latest = state.history[state.history.length - 1];
    query.node = serializeNode(latest);
    query.trail = JSON.stringify(state.history.slice(-12));
  }

  return query;
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

async function addItemToLibrary(item, seasonNumbers = null) {
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

  if (kind === 'tv' && seasonNumbers && seasonNumbers.length > 0) {
    const scrapePayload: {
      media_type: 'tv';
      season_numbers: number[];
      tvdb_id?: string;
      tmdb_id?: string;
    } = {
      media_type: 'tv',
      season_numbers: seasonNumbers,
    };
    if (item.indexer === 'tvdb') {
      scrapePayload.tvdb_id = String(item.tvdb_id || item.id);
    } else {
      scrapePayload.tmdb_id = String(item.tmdb_id || item.id);
    }
    const scrapeRes = await apiPost('/scrape/auto', scrapePayload);
    if (!scrapeRes.ok) {
      notify(`Added to library but failed to start season scrape: ${scrapeRes.error}`, 'warning');
      return true;
    }
    notify(`Added "${item.title || item.name}" — scraping ${seasonNumbers.length} season(s)`, 'success');
    return true;
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

function getOriginLabel(state) {
  if (state.mode === 'discover') {
    return state.type === 'all' ? 'Trending' : `Discover — ${state.type === 'movie' ? 'Movies' : 'TV'}`;
  }
  return state.source === 'tvdb' ? 'TVDB Search' : 'Search Results';
}

function renderBreadcrumbs(container, originLabel, history, onSelect) {
  if (!container) return;
  container.innerHTML = '';

  const items = [{ label: originLabel, kind: 'origin' }, ...history];
  items.forEach((node, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'pill pill--' + (node.kind || 'origin');
    button.textContent = node.label || (node.kind === 'origin' ? originLabel : `${node.kind} ${node.id}`);
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

function getSeasonNumber(s) {
  return s.season_number ?? s.number ?? null;
}

function buildSeasonSelector(seasons) {
  if (!seasons || !seasons.length) return null;

  const filtered = seasons.filter((s) => getSeasonNumber(s) > 0);
  if (!filtered.length) return null;

  const selected = new Set<number>(filtered.map((s) => getSeasonNumber(s) as number));

  const container = document.createElement('div');
  container.className = 'season-selector';

  const header = document.createElement('div');
  header.className = 'season-selector__header';
  const label = document.createElement('span');
  label.className = 'season-selector__label';
  const updateLabel = () => {
    label.textContent = `Seasons: ${selected.size} of ${filtered.length} selected`;
  };
  updateLabel();

  const toggleAll = document.createElement('button');
  toggleAll.type = 'button';
  toggleAll.className = 'btn btn--secondary btn--small';
  toggleAll.textContent = 'Toggle All';
  toggleAll.addEventListener('click', () => {
    const allSelected = selected.size === filtered.length;
    filtered.forEach((s) => {
      if (allSelected) selected.delete(getSeasonNumber(s));
      else selected.add(getSeasonNumber(s));
    });
    (container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>).forEach((cb) => {
      cb.checked = !allSelected;
    });
    updateLabel();
  });

  header.appendChild(label);
  header.appendChild(toggleAll);
  container.appendChild(header);

  const list = document.createElement('div');
  list.className = 'season-selector__list';
  filtered.forEach((season) => {
    const num = getSeasonNumber(season);
    const row = document.createElement('label');
    row.className = 'season-selector__item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.value = String(num);
    cb.addEventListener('change', () => {
      if (cb.checked) selected.add(num);
      else selected.delete(num);
      updateLabel();
    });
    const text = document.createElement('span');
    text.textContent = season.name || `Season ${num}`;
    const epCount = season.episode_count || season.episodes?.length;
    if (epCount) {
      text.textContent += ` (${epCount} eps)`;
    }
    row.appendChild(cb);
    row.appendChild(text);
    list.appendChild(row);
  });
  container.appendChild(list);

  return {
    element: container,
    getSelected: () => Array.from(selected).sort((a, b) => a - b),
    isPartial: () => selected.size > 0 && selected.size < filtered.length,
    totalSeasons: filtered.length,
  };
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

  let seasonSelector = null;
  if (kind === 'tv' && detail.seasons) {
    seasonSelector = buildSeasonSelector(detail.seasons);
    if (seasonSelector) {
      right.appendChild(seasonSelector.element);
    }
  }

  const actionRow = document.createElement('div');
  actionRow.className = 'toolbar';
  const actionButton = document.createElement('button');
  actionButton.type = 'button';
  actionButton.className = 'btn btn--primary btn--small';
  actionButton.textContent = onAction.label;
  actionButton.addEventListener('click', () => {
    if (seasonSelector && onAction.seasonSelector) {
      onAction.onClick(seasonSelector);
    } else {
      onAction.onClick(null);
    }
  });
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
  const toggleContainer = container.querySelector('[data-slot="media-type-toggle"]');
  const queryInput = container.querySelector('[data-slot="query"]');
  const grid = container.querySelector('[data-slot="grid"]');
  const empty = container.querySelector('[data-slot="empty"]');
  const pagination = container.querySelector('[data-slot="pagination"]');
  const resultTitle = container.querySelector('[data-slot="results-title"]');
  const detail = container.querySelector('[data-slot="detail"]');
  const breadcrumbs = container.querySelector('[data-slot="breadcrumbs"]');
  const exploreLayout = container.querySelector('.explore-layout');
  const exploreResults = container.querySelector('.explore-results');

  const state = {
    source: 'tmdb',
    mode: 'search',
    type: 'movie',
    query: '',
    page: 1,
    totalPages: 1,
    history: [],
  };

  function normalizeStateFromRoute() {
    const query = route.query || {};
    state.source = query.source === 'tvdb' ? 'tvdb' : 'tmdb';
    state.mode = query.mode === 'discover' ? 'discover' : 'search';
    state.type = ['movie', 'tv', 'all'].includes(query.type) ? query.type : 'movie';
    state.query = query.q || '';
    state.page = parsePositiveInt(query.page, 1);
    state.history = parseTrail(query.trail);

    if (!state.history.length) {
      const node = parseNode(query.node);
      if (node) state.history = [node];
    }

    if (state.source === 'tvdb') {
      state.mode = 'search';
      if (state.type === 'all') state.type = 'tv';
    }
  }

  function syncRouteState() {
    replaceRoute('explore', null, buildRouteQuery(state));
  }

  function updateLayoutFocus() {
    const focused = state.history.length > 0;
    if (exploreLayout) {
      exploreLayout.classList.toggle('explore-layout--detail-focused', focused);
      exploreLayout.classList.toggle('explore-layout--results-only', !focused);
    }
  }

  const mediaTypeToggle =
    toggleContainer &&
    createMediaTypeToggle({
      container: toggleContainer,
      value: state.type,
      includeAll: true,
      onChange(value) {
        state.type = value;
        if (state.source === 'tvdb' && value === 'all') state.type = 'tv';
        syncRouteState();
        fetchResults();
      },
    });

  function syncControls() {
    if (sourceSelect) sourceSelect.value = state.source;
    if (modeSelect) modeSelect.value = state.mode;
    if (mediaTypeToggle) mediaTypeToggle.setValue(state.type);
    if (queryInput) queryInput.value = state.query;

    if (modeSelect) {
      modeSelect.disabled = state.source === 'tvdb';
    }
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
      syncRouteState();
      fetchResults();
    });

    syncRouteState();
    updateLayoutFocus();
    statusTracker.setTracked(grid, 'explore');
  }

  function handleBreadcrumbClick(clickedIndex) {
    if (clickedIndex === 0) {
      state.history = [];
      syncRouteState();
      updateLayoutFocus();
      renderBreadcrumbs(breadcrumbs, getOriginLabel(state), state.history, handleBreadcrumbClick);
      if (detail) {
        detail.innerHTML = '<p class="muted">Select a card to inspect cast, recommendations, and linked entries.</p>';
      }
      return;
    }
    const historyIndex = clickedIndex - 1;
    state.history = state.history.slice(0, historyIndex + 1);
    const target = state.history[historyIndex];
    selectNode(target, false);
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

    renderBreadcrumbs(breadcrumbs, getOriginLabel(state), state.history, handleBreadcrumbClick);
    updateLayoutFocus();

    syncRouteState();

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
      syncRouteState();
      statusTracker.setTracked(
        [{ container: grid, type: 'explore' }, { container: detail, type: 'explore' }],
        undefined,
      );
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
      const tvdbInLibrary = series.in_library && series.library_item_id;
      detail.appendChild(
        renderDetailHeader(series, 'tv', {
          label: tvdbInLibrary ? 'Open Library Item' : 'Add to Library',
          seasonSelector: !tvdbInLibrary,
          onClick: async (seasonSelector) => {
            if (tvdbInLibrary) {
              window.location.hash = `#/item/${series.library_item_id}`;
              return;
            }
            const seasonNumbers = seasonSelector?.isPartial() ? seasonSelector.getSelected() : null;
            const ok = await addItemToLibrary(
              {
                ...series,
                media_type: 'tv',
                id: node.id,
                indexer: 'tvdb',
                tvdb_id: node.id,
              },
              seasonNumbers,
            );
            if (!ok) return;
            await fetchResults();
            await selectNode(node, false);
          },
        }),
      );
      syncRouteState();
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
    const isInLibrary = media.library?.in_library && media.library?.library_item_id;
    detail.appendChild(
      renderDetailHeader(media, node.kind, {
        label: isInLibrary ? 'Open Library Item' : 'Add to Library',
        seasonSelector: node.kind === 'tv' && !isInLibrary,
        onClick: async (seasonSelector) => {
          if (isInLibrary) {
            window.location.hash = `#/item/${media.library.library_item_id}`;
            return;
          }
          const seasonNumbers = seasonSelector?.isPartial() ? seasonSelector.getSelected() : null;
          const ok = await addItemToLibrary({ ...media, media_type: node.kind }, seasonNumbers);
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
    syncRouteState();
    statusTracker.setTracked(
      [{ container: grid, type: 'explore' }, { container: detail, type: 'explore' }],
      undefined,
    );
  }

  if (form) {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      state.source = sourceSelect?.value || 'tmdb';
      state.mode = modeSelect?.value || 'search';
      state.type = mediaTypeToggle?.getValue() || 'movie';
      state.query = queryInput?.value?.trim() || '';
      state.page = 1;
      state.history = [];

      if (state.source === 'tvdb') {
        state.mode = 'search';
        if (state.type === 'all') state.type = 'tv';
      }

      if (state.mode === 'search' && !state.query && state.source === 'tmdb') {
        notify('Enter a query for TMDB search', 'warning');
      }

      syncRouteState();
      fetchResults();
    });
  }

  normalizeStateFromRoute();

  const seedRaw = sessionStorage.getItem('riven_explore_seed');
  if (seedRaw && !state.history.length && !state.query) {
    sessionStorage.removeItem('riven_explore_seed');
    try {
      const seed = JSON.parse(seedRaw);
      if (seed?.kind && seed?.id) {
        state.source = 'tmdb';
        state.mode = 'discover';
        state.type = seed.kind === 'tv' ? 'tv' : 'movie';
        state.page = 1;
        state.history = [
          {
            kind: seed.kind,
            id: String(seed.id),
            label: seed.label || `${seed.kind} ${seed.id}`,
            source: seed.source || 'tmdb',
          },
        ];
        syncControls();
        syncRouteState();
        fetchResults();
        selectNode(state.history[0], false);
        return;
      }
    } catch {
      // ignore malformed seed
    }
  }

  syncControls();
  await fetchResults();

  if (state.history.length) {
    await selectNode(state.history[state.history.length - 1], false);
  }
}

import { apiDelete, apiFetch, apiGet, apiPost, getStreamUrl } from '../services/api';
import { notify } from '../services/notify';
import { formatDate, formatEpisodeDisplayTitle, formatYear } from '../services/utils';
import { renderBackButton } from '../ui/backButton';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';

function posterUrl(item: { poster_path?: string | null }): string {
  const path = item?.poster_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function createChip(text: string, className = ''): HTMLSpanElement {
  const span = document.createElement('span');
  span.className = `legend-chip ${className}`.trim();
  span.textContent = text;
  return span;
}

type EpisodeLike = {
  id?: string;
  number?: number;
  title?: string;
  state?: string;
  parent_title?: string;
  season_number?: number | null;
  episode_number?: number | null;
  aired_at?: string;
  poster_path?: string | null;
};
type SeasonLike = { number?: number; episodes?: EpisodeLike[] };
type ShowLike = { type: string; title?: string; poster_path?: string | null; seasons?: SeasonLike[] };

function isInLibrary(state: string): boolean {
  const s = (state || '').toString();
  return s === 'Completed' || s === 'Symlinked' || s === 'Downloaded' || s === 'Scraped';
}

function renderSeasonsEpisodes(
  host: HTMLElement | null,
  item: ShowLike,
  refresh: () => void,
): void {
  if (!host) return;
  const seasons = item?.seasons;
  if (item.type !== 'show' || !seasons?.length) {
    host.innerHTML = '';
    return;
  }

  const sortedSeasons = [...seasons].filter((s) => (s.number ?? 0) > 0).sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
  if (!sortedSeasons.length) {
    host.innerHTML = '';
    return;
  }

  const panel = document.createElement('div');
  panel.className = 'panel show-seasons-episodes';

  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Seasons &amp; Episodes</h3>';
  panel.appendChild(head);

  const seasonTabs = document.createElement('div');
  seasonTabs.className = 'season-tabs';
  seasonTabs.setAttribute('role', 'tablist');
  sortedSeasons.forEach((season, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `season-tab ${idx === 0 ? 'season-tab--active' : ''}`;
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
    btn.dataset.seasonIndex = String(idx);
    const num = season.number ?? 0;
    const epCount = season.episodes?.length ?? 0;
    btn.textContent = `Season ${num}${epCount ? ` (${epCount})` : ''}`;
    seasonTabs.appendChild(btn);
  });
  panel.appendChild(seasonTabs);

  const episodeListHost = document.createElement('div');
  episodeListHost.className = 'show-episodes-list';
  panel.appendChild(episodeListHost);

  function renderEpisodeList(seasonIndex: number): void {
    const season = sortedSeasons[seasonIndex];
    const episodes = season?.episodes ?? [];
    const sortedEps = [...episodes].sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
    const showTitle = item.title ?? '';

    episodeListHost.innerHTML = '';
    if (!sortedEps.length) {
      episodeListHost.innerHTML = '<p class="muted">No episodes in this season.</p>';
      return;
    }

    episodeListHost.classList.add('media-list');

    sortedEps.forEach((ep) => {
      const row = document.createElement('div');
      row.className = 'media-list__row show-episode-row';
      const state = (ep.state || '').toString();
      const inLib = isInLibrary(state);

      const epForDisplay: EpisodeLike & { type: string } = {
        ...ep,
        type: 'episode',
        parent_title: ep.parent_title ?? showTitle,
        season_number: ep.season_number ?? season?.number ?? null,
        episode_number: ep.episode_number ?? ep.number ?? null,
      };

      const poster = document.createElement('div');
      poster.className = 'media-list__poster';
      const img = document.createElement('img');
      img.alt = '';
      img.loading = 'lazy';
      const src = posterUrl(ep.poster_path ? ep : { poster_path: item.poster_path });
      if (src) img.src = src;
      poster.appendChild(img);
      row.appendChild(poster);

      const main = document.createElement('div');
      main.className = 'media-list__main';

      const link = document.createElement('a');
      link.className = 'media-list__title';
      link.href = `#/item/${ep.id}`;
      link.textContent = formatEpisodeDisplayTitle(epForDisplay);
      main.appendChild(link);

      const meta = document.createElement('div');
      meta.className = 'media-list__meta';
      meta.appendChild(createChip('TV', 'legend-chip--tv'));
      meta.appendChild(
        createChip(inLib ? 'In library' : state || 'Missing', inLib ? 'legend-chip--in-library' : 'legend-chip--missing'),
      );
      const year = formatYear(epForDisplay);
      if (year) meta.appendChild(createChip(year));
      main.appendChild(meta);

      row.appendChild(main);

      const actions = document.createElement('div');
      actions.className = 'media-list__actions';
      if (ep.id && (state === 'Requested' || state === 'Failed')) {
        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'btn btn--small btn--secondary';
        retryBtn.textContent = 'Retry';
        retryBtn.addEventListener('click', async () => {
          const res = await apiPost('/items/retry', { ids: [String(ep.id)] });
          if (!res.ok) {
            notify(res.error || 'Retry failed', 'error');
            return;
          }
          notify('Episode queued for retry', 'success');
          refresh();
        });
        actions.appendChild(retryBtn);
      }
      row.appendChild(actions);
      episodeListHost.appendChild(row);
    });
  }

  seasonTabs.querySelectorAll<HTMLButtonElement>('.season-tab').forEach((btn, idx) => {
    btn.addEventListener('click', () => {
      seasonTabs.querySelectorAll('.season-tab').forEach((b, i) => {
        b.classList.toggle('season-tab--active', i === idx);
        b.setAttribute('aria-selected', String(i === idx));
      });
      renderEpisodeList(idx);
    });
  });

  renderEpisodeList(0);
  host.innerHTML = '';
  host.appendChild(panel);
}

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function mediaTypeForScrape(item) {
  if (item.type === 'movie') return 'movie';
  return 'tv';
}

function toPosterUrl(path) {
  if (!path) return '';
  return path.startsWith('http') ? path : `https://image.tmdb.org/t/p/w500${path}`;
}

async function runAction(action, itemId) {
  const ids = [String(itemId)];
  switch (action) {
    case 'retry':
      return apiPost('/items/retry', { ids });
    case 'reset':
      return apiPost('/items/reset', { ids });
    case 'pause':
      return apiPost('/items/pause', { ids });
    case 'unpause':
      return apiPost('/items/unpause', { ids });
    case 'reindex':
      return apiPost('/items/reindex', { item_id: Number(itemId) });
    case 'remove':
      return apiDelete('/items/remove', { ids });
    default:
      return {
        ok: false,
        status: 0,
        data: null,
        error: `Unknown action ${action}`,
      };
  }
}

async function runAutoScrape(item) {
  return apiPost('/scrape/auto', {
    media_type: mediaTypeForScrape(item),
    item_id: Number(item.id),
  });
}

function openManualScrapeModal(itemId, refresh) {
  const template = document.getElementById('manual-scrape-modal-tpl') as HTMLTemplateElement | null;
  if (!template) return;

  const clone = template.content.cloneNode(true) as DocumentFragment;
  const dialog = clone.querySelector('dialog');
  const magnetInput = clone.querySelector('[data-slot="magnet"]') as HTMLTextAreaElement | null;
  const startButton = clone.querySelector('[data-action="start-session"]');
  const closeButton = clone.querySelector('[data-action="close"]');

  if (!dialog || !startButton || !closeButton) return;

  const close = () => {
    dialog.close();
    dialog.remove();
  };

  closeButton.addEventListener('click', close);
  startButton.addEventListener('click', async () => {
    const magnet = magnetInput?.value?.trim();
    if (!magnet) {
      notify('Paste a magnet URI first', 'warning');
      return;
    }
    const params = new URLSearchParams({ magnet, item_id: String(itemId) });
    const response = await apiFetch(`/scrape/start_session?${params.toString()}`, {
      method: 'POST',
    });
    if (!response.ok) {
      notify(response.error || 'Failed to start manual session', 'error');
      return;
    }
    notify('Manual scrape session started', 'success');
    close();
    refresh();
  });

  document.body.appendChild(dialog);
  dialog.showModal();
}

function renderHeader(item, slots) {
  const { poster, info } = slots;
  if (poster) {
    poster.innerHTML = '';
    const imageUrl = toPosterUrl(item.poster_path);
    if (imageUrl) {
      const image = document.createElement('img');
      image.src = imageUrl;
      image.alt = item.title || 'poster';
      poster.appendChild(image);
    } else {
      poster.innerHTML = '<div class="muted">No artwork</div>';
    }
  }

  if (info) {
    info.innerHTML = `
      <h2>${formatEpisodeDisplayTitle(item)}</h2>
      <div class="meta-line">
        <span class="legend-chip ${item.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'}">${item.type}</span>
        <span class="legend-chip">${item.state || 'Unknown'}</span>
        ${item.year ? `<span class="legend-chip">${item.year}</span>` : ''}
      </div>
      <dl>
        <dt>Item ID</dt><dd>${item.id}</dd>
        <dt>TMDB</dt><dd>${item.tmdb_id || '—'}</dd>
        <dt>TVDB</dt><dd>${item.tvdb_id || '—'}</dd>
        <dt>IMDB</dt><dd>${item.imdb_id || '—'}</dd>
        <dt>Requested</dt><dd>${formatDate(item.requested_at)}</dd>
        <dt>Scraped</dt><dd>${formatDate(item.scraped_at)}</dd>
      </dl>
    `;
  }
}

function renderMetadata(metadataHost: HTMLElement | null, metadata: Record<string, unknown> | null) {
  if (!metadataHost) return;
  if (!metadata) {
    metadataHost.innerHTML = '<p class="muted">No metadata payload available.</p>';
    return;
  }
  const entries = Object.entries(metadata).filter(
    ([k]) => k !== 'belongs_to_collection' && k !== 'parts',
  );
  const dl = document.createElement('dl');
  dl.className = 'metadata-dl';
  entries.forEach(([key, value]) => {
    if (value == null) return;
    const dt = document.createElement('dt');
    dt.textContent = key.replace(/_/g, ' ');
    const dd = document.createElement('dd');
    if (typeof value === 'object' && !Array.isArray(value) && value !== null) {
      dd.textContent = JSON.stringify(value);
    } else {
      dd.textContent = String(value);
    }
    dl.appendChild(dt);
    dl.appendChild(dd);
  });
  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Media Metadata</h3>';
  const rawToggle = document.createElement('button');
  rawToggle.type = 'button';
  rawToggle.className = 'btn btn--small btn--secondary';
  rawToggle.textContent = 'Show raw JSON';
  const pre = document.createElement('pre');
  pre.className = 'json-output';
  pre.hidden = true;
  pre.textContent = JSON.stringify(metadata, null, 2);
  rawToggle.addEventListener('click', () => {
    pre.hidden = !pre.hidden;
    rawToggle.textContent = pre.hidden ? 'Show raw JSON' : 'Hide raw JSON';
  });
  head.appendChild(rawToggle);
  metadataHost.innerHTML = '';
  metadataHost.appendChild(head);
  metadataHost.appendChild(dl);
  metadataHost.appendChild(pre);
}

function renderStreams(streamHost, streams, itemId, refresh) {
  if (!streamHost) return;
  const merged = [
    ...(streams?.streams || []),
    ...(streams?.blacklisted_streams || []).map((stream) => ({ ...stream, blacklisted: true })),
  ];

  streamHost.innerHTML = `
    <div class="section-head">
      <h3>Streams (${merged.length})</h3>
      <button type="button" class="btn btn--secondary btn--small" data-action="reset-streams">Reset Streams</button>
    </div>
  `;

  const resetButton = streamHost.querySelector('[data-action="reset-streams"]');
  if (resetButton) {
    resetButton.addEventListener('click', async () => {
      const response = await apiPost(`/items/${itemId}/streams/reset`);
      if (!response.ok) {
        notify(response.error || 'Failed to reset streams', 'error');
        return;
      }
      notify('Streams reset', 'success');
      refresh();
    });
  }

  if (!merged.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'No streams stored for this item.';
    streamHost.appendChild(empty);
    return;
  }

  merged.forEach((stream) => {
    const row = document.createElement('div');
    row.className = 'stream-row';
    const title = document.createElement('span');
    title.textContent = stream.raw_title || stream.infohash || `Stream ${stream.id}`;
    row.appendChild(title);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn--small btn--secondary';
    button.textContent = stream.blacklisted ? 'Unblacklist' : 'Blacklist';
    button.addEventListener('click', async () => {
      const path = stream.blacklisted
        ? `/items/${itemId}/streams/${stream.id}/unblacklist`
        : `/items/${itemId}/streams/${stream.id}/blacklist`;
      const response = await apiPost(path);
      if (!response.ok) {
        notify(response.error || 'Failed to update stream blacklist', 'error');
        return;
      }
      notify('Stream updated', 'success');
      refresh();
    });
    row.appendChild(button);
    streamHost.appendChild(row);
  });
}

function renderVideo(videoHost, itemId, item) {
  if (!videoHost) return;
  videoHost.innerHTML = '';
  if (item.type !== 'movie' && item.type !== 'episode') return;

  const heading = document.createElement('h3');
  heading.textContent = 'Playback';
  videoHost.appendChild(heading);

  const video = document.createElement('video');
  video.controls = true;
  video.src = getStreamUrl(itemId);
  videoHost.appendChild(video);
}

export async function load(route, container) {
  const itemId = route.param;
  if (!itemId) {
    container.innerHTML = '<p class="muted">No item ID provided.</p>';
    return;
  }

  const [itemResponse, streamResponse, metadataResponse] = await Promise.all([
    apiGet(`/items/${itemId}`, { media_type: 'item', extended: true }),
    apiGet(`/items/${itemId}/streams`),
    apiGet(`/items/${itemId}/metadata`),
  ]);

  if (!itemResponse.ok || !itemResponse.data) {
    container.innerHTML = `<p class="muted">${itemResponse.error || 'Item not found.'}</p>`;
    return;
  }

  const item = itemResponse.data;
  const slots = {
    back: container.querySelector<HTMLElement>('[data-slot="back"]'),
    poster: container.querySelector('[data-slot="poster"]'),
    info: container.querySelector('[data-slot="info"]'),
    actions: container.querySelector('[data-slot="actions"]'),
    streams: container.querySelector('[data-slot="streams"]'),
    video: container.querySelector('[data-slot="video"]'),
    metadata: container.querySelector('[data-slot="metadata"]'),
  };

  const returnRoute =
    (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('riven_return_route')) || 'library';
  const returnLabels: Record<string, string> = {
    library: '← Back to Library',
    movies: '← Back to Movies',
    shows: '← Back to TV Shows',
    episodes: '← Back to TV Episodes',
  };
  const isEpisode = item.type === 'episode';
  const showId = isEpisode && item.show_id != null ? String(item.show_id) : null;
  renderBackButton(slots.back, {
    label: showId ? '← Back to Show' : returnLabels[returnRoute] || '← Back',
    href: showId ? `#/item/${showId}` : `#/${returnRoute}`,
  });

  const refresh = () => load(route, container);
  renderHeader(item, slots);
  const metadata = metadataResponse.ok ? metadataResponse.data : null;
  const collectionBlock = container.querySelector<HTMLElement>('[data-slot="collection-block"]');
  const seasonsNote = container.querySelector<HTMLElement>('[data-slot="seasons-note"]');
  if (collectionBlock && item.type === 'movie' && metadata && typeof metadata === 'object' && metadata.belongs_to_collection) {
    const col = metadata.belongs_to_collection as { id?: number; name?: string };
    if (col?.name) {
      collectionBlock.innerHTML = `<div class="panel"><p><strong>Part of collection:</strong> ${escapeHtml(col.name)}</p></div>`;
    }
  }
  if (seasonsNote && (item.type === 'show' || item.type === 'episode')) {
    renderSeasonsEpisodes(seasonsNote, item as ShowLike, refresh);
  }
  renderMetadata(slots.metadata, metadata);
  renderStreams(slots.streams, streamResponse.data || {}, itemId, refresh);
  renderVideo(slots.video, itemId, item);

  const tabBar = container.querySelector<HTMLElement>('[data-slot="tab-bar"]');
  const panelOverview = container.querySelector<HTMLElement>('[data-slot="panel-overview"]');
  const panelStreams = container.querySelector<HTMLElement>('[data-slot="panel-streams"]');
  const panelPlayback = container.querySelector<HTMLElement>('[data-slot="panel-playback"]');
  const panels = [
    { id: 'overview', el: panelOverview },
    { id: 'streams', el: panelStreams },
    { id: 'playback', el: panelPlayback },
  ];
  tabBar?.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      tabBar?.querySelectorAll('[data-tab]').forEach((b) => {
        b.classList.remove('item-detail-tab--active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('item-detail-tab--active');
      btn.setAttribute('aria-selected', 'true');
      panels.forEach((p) => {
        if (p.el) p.el.hidden = p.id !== tab;
      });
    });
  });
  panels.forEach((p) => {
    if (p.el) p.el.hidden = p.id !== 'overview';
  });

  if (slots.actions) {
    const state = (item.state || '').toString();
    const showPause = state !== 'Paused' && state !== 'Completed' && state !== 'Failed';
    const showResume = state === 'Paused';
    const tooltips: Record<string, string> = {
      'auto-scrape': 'Trigger automatic torrent search and download for this item.',
      'manual-scrape': 'Search and pick a torrent manually (paste magnet or search).',
      retry: 'Retry from current step; re-queue the item.',
      reset: 'Reset to initial state, blacklist current stream, and re-download.',
      pause: 'Pause processing and cancel current jobs.',
      unpause: 'Resume processing (only when paused).',
      reindex: 'Reindex to pick up new season & episode releases.',
      remove: 'Remove from library (DB, jobs, and library refresh).',
    };
    const buttons: { key: string; label: string; tone: string; show?: boolean }[] = [
      { key: 'auto-scrape', label: 'Auto Scrape', tone: 'primary' },
      { key: 'manual-scrape', label: 'Manual Scrape', tone: 'secondary' },
      { key: 'retry', label: 'Retry', tone: 'secondary' },
      { key: 'reset', label: 'Reset', tone: 'secondary' },
      { key: 'pause', label: 'Pause', tone: 'warning', show: showPause },
      { key: 'unpause', label: 'Resume', tone: 'secondary', show: showResume },
      { key: 'reindex', label: 'Reindex', tone: 'secondary' },
      { key: 'remove', label: 'Remove', tone: 'danger' },
    ].filter((b) => b.show !== false);

    slots.actions.innerHTML = buttons
      .map(
        (button) =>
          `<button type="button" class="btn btn--small btn--${button.tone}" data-action="${button.key}" title="${escapeHtml(tooltips[button.key] ?? '')}">${button.label}</button>`,
      )
      .join('');

    slots.actions.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const action = button.dataset.action;
        if (!action) return;

        if (action === 'manual-scrape') {
          openManualScrapeModal(itemId, refresh);
          return;
        }

        if (action === 'auto-scrape') {
          const response = await runAutoScrape(item);
          if (!response.ok) {
            notify(response.error || 'Auto scrape failed', 'error');
            return;
          }
          notify('Auto scrape triggered', 'success');
          refresh();
          return;
        }

        if (action === 'remove') {
          const confirmed = window.confirm(`Remove "${item.title}" from library?`);
          if (!confirmed) return;
        }

        const response = await runAction(action, itemId);
        if (!response.ok) {
          notify(response.error || `Action failed: ${action}`, 'error');
          return;
        }

        notify(response.data?.message || `${action} complete`, 'success');
        if (action === 'remove') {
          window.location.hash = '#/library';
          return;
        }
        refresh();
      });
    });
  }
}

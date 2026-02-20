import { apiDelete, apiFetch, apiGet, apiPost, getStreamUrl } from '../services/api';
import { notify } from '../services/notify';
import { formatDate } from '../services/utils';

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
      <h2>${item.title || 'Unknown'}</h2>
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

function renderMetadata(metadataHost, metadata) {
  if (!metadataHost) return;
  if (!metadata) {
    metadataHost.innerHTML = '<p class="muted">No metadata payload available.</p>';
    return;
  }
  metadataHost.innerHTML = `
    <div class="section-head"><h3>Media Metadata</h3></div>
    <pre class="json-output">${JSON.stringify(metadata, null, 2)}</pre>
  `;
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
    poster: container.querySelector('[data-slot="poster"]'),
    info: container.querySelector('[data-slot="info"]'),
    actions: container.querySelector('[data-slot="actions"]'),
    streams: container.querySelector('[data-slot="streams"]'),
    video: container.querySelector('[data-slot="video"]'),
    metadata: container.querySelector('[data-slot="metadata"]'),
  };

  const refresh = () => load(route, container);
  renderHeader(item, slots);
  renderMetadata(slots.metadata, metadataResponse.ok ? metadataResponse.data : null);
  renderStreams(slots.streams, streamResponse.data || {}, itemId, refresh);
  renderVideo(slots.video, itemId, item);

  if (slots.actions) {
    const buttons = [
      { key: 'auto-scrape', label: 'Auto Scrape', tone: 'primary' },
      { key: 'manual-scrape', label: 'Manual Scrape', tone: 'secondary' },
      { key: 'retry', label: 'Retry', tone: 'secondary' },
      { key: 'reset', label: 'Reset', tone: 'secondary' },
      { key: 'pause', label: 'Pause', tone: 'warning' },
      { key: 'unpause', label: 'Unpause', tone: 'secondary' },
      { key: 'reindex', label: 'Reindex', tone: 'secondary' },
      { key: 'remove', label: 'Remove', tone: 'danger' },
    ];

    slots.actions.innerHTML = buttons
      .map(
        (button) =>
          `<button type="button" class="btn btn--small btn--${button.tone}" data-action="${button.key}">${button.label}</button>`,
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

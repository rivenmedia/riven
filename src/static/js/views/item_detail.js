/**
 * Item detail view - metadata, actions, streams, video player
 */

import { apiGet, apiPost, apiDelete, apiFetch, getStreamUrl } from '../api.js';

export async function load(route, container) {
  const id = route.param;
  if (!id) return;

  const [itemRes, streamsRes] = await Promise.all([
    apiGet(`/items/${id}`),
    apiGet(`/items/${id}/streams`),
  ]);

  if (!itemRes.ok || !itemRes.data) {
    container.innerHTML = '<p>Item not found</p>';
    return;
  }

  const item = itemRes.data;
  const streams = [...(streamsRes.data?.streams || []), ...(streamsRes.data?.blacklisted_streams || []).map((s) => ({ ...s, blacklisted: true }))];

  const header = container.querySelector('[data-slot="header"]');
  const poster = container.querySelector('[data-slot="poster"]');
  const info = container.querySelector('[data-slot="info"]');
  const actionsBar = container.querySelector('[data-slot="actions"]');
  const streamsEl = container.querySelector('[data-slot="streams"]');
  const videoEl = container.querySelector('[data-slot="video"]');

  if (poster) {
    const img = document.createElement('img');
    img.src = item.poster_path
      ? (item.poster_path.startsWith('http') ? item.poster_path : 'https://image.tmdb.org/t/p/w500' + item.poster_path)
      : '';
    img.alt = item.title;
    poster.appendChild(img);
  }

  if (info) {
    info.innerHTML = `
      <h1>${item.title || 'Unknown'}</h1>
      <p>${item.type} · ${item.state || ''}</p>
      <p>${item.overview || ''}</p>
    `;
  }

  if (actionsBar) {
    actionsBar.innerHTML = `
      <button data-action="auto-scrape">Auto Scrape</button>
      <button data-action="manual-scrape">Manual Scrape</button>
      <button data-action="retry">Retry</button>
      <button data-action="reset">Reset</button>
      <button data-action="pause">Pause</button>
      <button data-action="unpause">Unpause</button>
      <button data-action="reindex">Reindex</button>
      <button data-action="delete" class="secondary">Delete</button>
    `;
    actionsBar.querySelectorAll('[data-action]').forEach((btn) => {
      const action = btn.dataset.action;
      if (action === 'manual-scrape') {
        btn.onclick = () => openManualScrapeModal(id, item, () => load(route, container));
      } else if (action === 'auto-scrape') {
        btn.onclick = () => runAutoScrape(id, item, () => load(route, container));
      } else {
        btn.onclick = () => runAction(action, id, () => load(route, container));
      }
    });
  }

  if (streamsEl) {
    streamsEl.innerHTML = '<h3>Streams</h3>';
    const resetBtn = document.createElement('button');
    resetBtn.textContent = 'Reset Streams';
    resetBtn.onclick = async () => {
      await apiPost(`/items/${id}/streams/reset`);
      load(route, container);
    };
    streamsEl.appendChild(resetBtn);
    streams.forEach((s) => {
      const row = document.createElement('div');
      row.className = 'stream-row';
      row.innerHTML = `<span>${s.raw_title || s.infohash}</span>`;
      const blacklistBtn = document.createElement('button');
      blacklistBtn.textContent = s.blacklisted ? 'Unblacklist' : 'Blacklist';
      blacklistBtn.onclick = async () => {
        const path = s.blacklisted
          ? `/items/${id}/streams/${s.id}/unblacklist`
          : `/items/${id}/streams/${s.id}/blacklist`;
        await apiPost(path);
        load(route, container);
      };
      row.appendChild(blacklistBtn);
      streamsEl.appendChild(row);
    });
  }

  if (videoEl && (item.type === 'movie' || item.type === 'episode')) {
    const video = document.createElement('video');
    video.controls = true;
    video.src = getStreamUrl(id);
    videoEl.appendChild(video);
  }
}

async function runAutoScrape(itemId, item, refresh) {
  const mediaType = item.type === 'show' || item.type === 'season' || item.type === 'episode' ? 'tv' : 'movie';
  const res = await apiPost('/scrape/auto', { media_type: mediaType, item_id: itemId });
  if (res.ok) refresh();
  else alert(res.data?.detail || 'Auto scrape failed');
}

function openManualScrapeModal(itemId, item, refresh) {
  const tpl = document.getElementById('manual-scrape-modal-tpl');
  if (!tpl) return;
  const clone = tpl.content.cloneNode(true);
  const dialog = clone.querySelector('dialog');
  const magnetInput = clone.querySelector('[data-slot="magnet"]');
  const startBtn = clone.querySelector('[data-action="start-session"]');
  const closeBtn = clone.querySelector('[data-action="close"]');

  const close = () => {
    dialog.close();
    dialog.remove();
  };

  closeBtn.onclick = close;
  startBtn.onclick = async () => {
    const magnet = magnetInput?.value?.trim();
    if (!magnet) {
      alert('Paste a magnet link');
      return;
    }
    const params = new URLSearchParams({ magnet, item_id: itemId });
    const res = await apiFetch(`/scrape/start_session?${params}`, { method: 'POST' });
    if (res.ok) {
      close();
      refresh();
    } else {
      alert(res.data?.detail || 'Failed to start session');
    }
  };

  document.body.appendChild(dialog);
  dialog.showModal();
}

async function runAction(action, id, refresh) {
  const ids = [String(id)];
  let res;
  switch (action) {
    case 'retry':
      res = await apiPost('/items/retry', { ids });
      break;
    case 'reset':
      res = await apiPost('/items/reset', { ids });
      break;
    case 'pause':
      res = await apiPost('/items/pause', { ids });
      break;
    case 'unpause':
      res = await apiPost('/items/unpause', { ids });
      break;
    case 'reindex':
      res = await apiPost('/items/reindex', { ids });
      break;
    case 'delete':
      if (!confirm('Delete this item?')) return;
      res = await apiDelete('/items/remove', { ids });
      if (res.ok) window.location.hash = '#/library';
      return;
    default:
      return;
  }
  if (res.ok) refresh();
}

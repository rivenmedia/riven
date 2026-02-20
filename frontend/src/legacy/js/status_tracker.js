/**
 * Tracks media cards on the page and periodically refreshes their status from the backend,
 * updating only the status tags in the DOM without re-rendering.
 */

import { apiGet } from './api.js';
import { updateMediaCardStatus } from './components/media_card.js';
import { toCsv } from './utils.js';

const POLL_INTERVAL_MS = 5_000;

/** @type {Map<string, { element: Element, type: 'explore' | 'library', tmdbId?: string, tvdbId?: string, indexer?: string, itemId?: string }>} */
const tracked = new Map();
/** @type {ReturnType<typeof setInterval> | null} */
let intervalId = null;

function entryKey(entry) {
  if (entry.indexer === 'tvdb' && entry.tvdbId) return `tvdb:${entry.tvdbId}`;
  return `tmdb:${entry.tmdbId || ''}`;
}

function buildEntry(cardEl, type) {
  const tmdbId = cardEl.dataset.tmdbId?.trim();
  const tvdbId = cardEl.dataset.tvdbId?.trim();
  const indexer = cardEl.dataset.indexer?.trim() || 'tmdb';
  const mediaType = cardEl.dataset.mediaType?.trim();

  if ((tmdbId || tvdbId) && (mediaType === 'movie' || mediaType === 'tv')) {
    return { element: cardEl, type, tmdbId, tvdbId, indexer };
  }
  return null;
}

async function refreshStatus(entries) {
  const tmdbIds = [...new Set(entries.map((e) => e.tmdbId).filter(Boolean))];
  const tvdbIds = [...new Set(entries.map((e) => e.tvdbId).filter(Boolean))];
  if (!tmdbIds.length && !tvdbIds.length) return;

  const res = await apiGet('/items/library/status', {
    tmdb_ids: toCsv(tmdbIds),
    tvdb_ids: toCsv(tvdbIds),
  });
  if (!res.ok) return;

  const tmdb = res.data?.tmdb || {};
  const tvdb = res.data?.tvdb || {};

  entries.forEach((entry) => {
    const status =
      (entry.indexer === 'tvdb' && entry.tvdbId ? tvdb[entry.tvdbId] : null) ||
      (entry.tmdbId ? tmdb[entry.tmdbId] : null) ||
      (entry.tvdbId ? tvdb[entry.tvdbId] : null);
    if (!status) return;
    updateMediaCardStatus(entry.element, {
      state: status.library_state ?? null,
      in_library: Boolean(status.in_library),
      library_item_id: status.library_item_id ?? null,
    });
  });
}

function tick() {
  const list = [...tracked.values()];
  if (!list.length) return;
  refreshStatus(list);
}

export function clear() {
  tracked.clear();
}

/**
 * Register trackable media cards for status refresh.
 * @param {Element | Array<{ container: Element, type: 'explore' | 'library' }>} containerOrList - Single container, or list of { container, type } to track multiple areas (e.g. grid + detail panel)
 * @param {'explore' | 'library'} [type] - Required when first arg is a single container
 */
export function setTracked(containerOrList, type) {
  tracked.clear();

  const list = Array.isArray(containerOrList)
    ? containerOrList
    : containerOrList
      ? [{ container: containerOrList, type }]
      : [];

  list.forEach(({ container, type: t }) => {
    if (!container || !t) return;
    const cards = container.querySelectorAll('[data-media-card="1"]');
    cards.forEach((card) => {
      const entry = buildEntry(card, t);
      if (entry) {
        const key = entryKey(entry);
        tracked.set(key, entry);
      }
    });
  });
}

export function start() {
  if (intervalId) return;
  intervalId = setInterval(tick, POLL_INTERVAL_MS);
}

export function stop() {
  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }
  clear();
}

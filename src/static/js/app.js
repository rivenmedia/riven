/**
 * App entry - Alpine appState, router, view loading
 */

import { hasKey, setKey, logout, validateKey } from './auth.js';
import { parseRoute, getTemplateId } from './router.js';
import * as libraryView from './views/library.js';
import * as dashboardView from './views/dashboard.js';
import * as vfsStatsView from './views/vfs_stats.js';
import * as exploreView from './views/explore.js';
import * as trendingView from './views/trending.js';
import * as itemDetailView from './views/item_detail.js';
import * as calendarView from './views/calendar.js';
import * as mountView from './views/mount.js';

const VIEW_LOADERS = {
  library: libraryView,
  movies: libraryView,
  shows: libraryView,
  explore: exploreView,
  trending: trendingView,
  dashboard: dashboardView,
  'vfs-stats': vfsStatsView,
  item: itemDetailView,
  calendar: calendarView,
  mount: mountView,
};

function loadView(route) {
  const container = document.getElementById('view-container');
  if (!container) return;
  const tplId = getTemplateId(route.name);
  const tpl = document.getElementById(tplId);
  if (!tpl) return;
  container.innerHTML = '';
  container.appendChild(tpl.content.cloneNode(true));
  const loader = VIEW_LOADERS[route.name] || libraryView;
  if (loader.load) loader.load(route, container);
}

window.appState = function () {
  return {
    hasKey: hasKey(),
    apiKey: '',
    error: '',
    loading: false,
    async submitKey() {
      this.error = '';
      this.loading = true;
      const ok = await validateKey(this.apiKey.trim());
      this.loading = false;
      if (ok) {
        setKey(this.apiKey.trim());
        this.hasKey = true;
        window.location.hash = '#/library';
        loadView(parseRoute());
      } else {
        this.error = 'Invalid API key';
      }
    },
    logout,
  };
};

function onHashChange() {
  const route = parseRoute();
  if (window.Alpine?.store?.route) window.Alpine.store('route').current = route;
  if (!hasKey()) return;
  loadView(route);
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.Alpine?.store) window.Alpine.store('route', { current: parseRoute() });
  if (hasKey()) {
    const appEl = document.getElementById('view-app');
    if (appEl) appEl.style.display = '';
    onHashChange();
  }
  window.addEventListener('hashchange', onHashChange);
});

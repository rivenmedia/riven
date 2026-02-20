/**
 * App entry - Alpine app state + hash view loader.
 */

import { hasKey, setKey, logout, validateKey } from './auth.js';
import { getTemplateId, parseRoute } from './router.js';
import * as statusTracker from './status_tracker.js';
import * as calendarView from './views/calendar.js';
import * as dashboardView from './views/dashboard.js';
import * as exploreView from './views/explore.js';
import * as inspectorView from './views/inspector.js';
import * as itemDetailView from './views/item_detail.js';
import * as libraryView from './views/library.js';
import * as mountView from './views/mount.js';
import * as settingsView from './views/settings.js';
import * as trendingView from './views/trending.js';
import * as vfsStatsView from './views/vfs_stats.js';

const VIEW_LOADERS = {
  library: libraryView,
  movies: libraryView,
  shows: libraryView,
  explore: exploreView,
  trending: trendingView,
  dashboard: dashboardView,
  inspector: inspectorView,
  settings: settingsView,
  'vfs-stats': vfsStatsView,
  item: itemDetailView,
  calendar: calendarView,
  mount: mountView,
};

function applyRouteTheme(route) {
  const body = document.body;
  if (!body) return;

  if (route.name === 'movies') {
    body.dataset.mediaContext = 'movie';
    return;
  }
  if (route.name === 'shows') {
    body.dataset.mediaContext = 'tv';
    return;
  }
  body.dataset.mediaContext = 'mixed';
}

async function loadView(route) {
  const container = document.getElementById('view-container');
  if (!container) return;

  statusTracker.clear();

  const templateId = getTemplateId(route.name);
  const template = document.getElementById(templateId);
  if (!template) return;

  container.innerHTML = '';
  container.appendChild(template.content.cloneNode(true));
  applyRouteTheme(route);

  const loader = VIEW_LOADERS[route.name] || libraryView;
  if (loader?.load) {
    await loader.load(route, container);
  }
}

window.appState = function appState() {
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
      if (!ok) {
        this.error = 'Invalid API key';
        return;
      }

      setKey(this.apiKey.trim());
      this.hasKey = true;
      window.location.hash = '#/library';
      await loadView(parseRoute());
    },
    logout,
  };
};

async function onHashChange() {
  const route = parseRoute();
  if (window.Alpine?.store?.route) {
    window.Alpine.store('route').current = route;
  }
  if (!hasKey()) return;
  await loadView(route);
}

document.addEventListener('DOMContentLoaded', async () => {
  if (window.Alpine?.store) {
    window.Alpine.store('route', { current: parseRoute() });
  }

  if (hasKey()) {
    const appElement = document.getElementById('view-app');
    if (appElement) appElement.style.display = '';
    await onHashChange();
  }

  window.addEventListener('hashchange', onHashChange);
  statusTracker.start();
});

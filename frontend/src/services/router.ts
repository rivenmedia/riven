/**
 * Hash router - parse route and map templates.
 */

export const ROUTES = {
  library: 'view-library',
  movies: 'view-movies',
  shows: 'view-shows',
  explore: 'view-explore',
  trending: 'view-trending',
  dashboard: 'view-dashboard',
  'dashboard-services': 'view-dashboard-services',
  'dashboard-states': 'view-dashboard-states',
  'dashboard-releases': 'view-dashboard-releases',
  inspector: 'view-inspector',
  settings: 'view-settings',
  'vfs-stats': 'view-vfs-stats',
  calendar: 'view-calendar',
  mount: 'view-mount',
  item: 'view-item-detail',
};

const DEFAULT_ROUTE = 'library';

function splitHash(rawHash) {
  const normalized = rawHash.replace(/^#/, '').trim();
  const cleaned = normalized.startsWith('/') ? normalized.slice(1) : normalized;
  const [pathPart, queryPart = ''] = cleaned.split('?');
  return { pathPart, queryPart };
}

function parseQuery(queryPart) {
  const query = {};
  const params = new URLSearchParams(queryPart || '');
  params.forEach((value, key) => {
    query[key] = value;
  });
  return query;
}

function buildQueryString(query = {}) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    params.set(key, String(value));
  });
  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}

export function buildHash(route, param = null, query = {}) {
  const safeRoute = route && ROUTES[route] ? route : DEFAULT_ROUTE;
  const path = param
    ? `/${safeRoute}/${encodeURIComponent(String(param))}`
    : `/${safeRoute}`;
  return `#${path}${buildQueryString(query)}`;
}

export function parseRoute() {
  const { pathPart, queryPart } = splitHash(window.location.hash);
  const segments = pathPart.split('/').filter(Boolean);
  const name = segments[0] && ROUTES[segments[0]] ? segments[0] : DEFAULT_ROUTE;
  const param = segments[1] ? decodeURIComponent(segments[1]) : null;
  const query = parseQuery(queryPart);
  return {
    name,
    param,
    segments,
    query,
    path: pathPart || DEFAULT_ROUTE,
  };
}

export function getTemplateId(routeName) {
  return ROUTES[routeName] || ROUTES[DEFAULT_ROUTE];
}

export function navigateTo(route, param = null, query = {}) {
  window.location.hash = buildHash(route, param, query);
}

export function replaceRoute(route, param = null, query = {}) {
  const hash = buildHash(route, param, query);
  const nextUrl = `${window.location.pathname}${window.location.search}${hash}`;
  window.history.replaceState(null, '', nextUrl);
}

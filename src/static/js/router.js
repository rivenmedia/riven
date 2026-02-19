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
  inspector: 'view-inspector',
  settings: 'view-settings',
  'vfs-stats': 'view-vfs-stats',
  calendar: 'view-calendar',
  mount: 'view-mount',
  item: 'view-item-detail',
};

const DEFAULT_ROUTE = 'library';

export function parseRoute() {
  const raw = window.location.hash.replace(/^#/, '').trim();
  const cleaned = raw.startsWith('/') ? raw.slice(1) : raw;
  const segments = cleaned.split('/').filter(Boolean);
  const name = segments[0] && ROUTES[segments[0]] ? segments[0] : DEFAULT_ROUTE;
  const param = segments[1] || null;
  return {
    name,
    param,
    segments,
    path: cleaned || DEFAULT_ROUTE,
  };
}

export function getTemplateId(routeName) {
  return ROUTES[routeName] || ROUTES[DEFAULT_ROUTE];
}

export function navigateTo(route, param = '') {
  const hash = param ? `#/${route}/${param}` : `#/${route}`;
  window.location.hash = hash;
}

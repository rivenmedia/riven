/**
 * Hash router - parse route and dispatch to view
 */

const ROUTES = {
  library: 'view-library',
  movies: 'view-movies',
  shows: 'view-shows',
  explore: 'view-explore',
  trending: 'view-trending',
  dashboard: 'view-dashboard',
  'vfs-stats': 'view-vfs-stats',
  calendar: 'view-calendar',
  mount: 'view-mount',
  item: 'view-item-detail',
};

export function parseRoute() {
  const hash = window.location.hash.slice(1) || 'library';
  const [name, param] = hash.split('/').filter(Boolean);
  return { name: name || 'library', param };
}

export function getTemplateId(routeName) {
  if (routeName === 'item') return 'view-item-detail';
  return ROUTES[routeName] || 'view-library';
}

export function navigateTo(route, param = '') {
  const hash = param ? `#/${route}/${param}` : `#/${route}`;
  window.location.hash = hash;
}

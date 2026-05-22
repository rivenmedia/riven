export const DOWNLOADER_OWNERS = new Set([
  'realdebrid',
  'alldebrid',
  'debridlink',
  'torbox',
]);

export const SCRAPER_OWNERS = new Set([
  'torrentio',
  'comet',
  'mediafusion',
  'aiostreams',
  'jackett',
  'prowlarr',
  'zilean',
  'rarbg',
  'orionoid',
]);

export const OWNER_SORT_PRIORITY = [
  'realdebrid',
  'alldebrid',
  'debridlink',
  'torbox',
  'torrentio',
  'comet',
  'mediafusion',
  'aiostreams',
  'jackett',
  'prowlarr',
  'zilean',
  'rarbg',
  'orionoid',
  'tmdb',
  'tvdb',
  'trakt',
  'plex',
  'overseerr',
];

export function ownerSortKey(owner: string): [number, string] {
  const idx = OWNER_SORT_PRIORITY.indexOf(owner);
  return [idx === -1 ? OWNER_SORT_PRIORITY.length : idx, owner];
}

export function sortOwnerKeys(keys: Iterable<string>): string[] {
  return [...keys].sort((a, b) => {
    const [ai, as] = ownerSortKey(a);
    const [bi, bs] = ownerSortKey(b);
    if (ai !== bi) return ai - bi;
    return as.localeCompare(bs);
  });
}

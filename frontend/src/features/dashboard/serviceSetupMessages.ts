/** Copy for runtime fallback modes (see GET `/services` → `mock_vfs`, `console_updater`). */

export const MOCK_VFS_NOTICE =
  'FUSE (pyfuse3) is not available — Riven is using an in-memory VFS inventory only. The Mount explorer still works; there is no real kernel mount. Install the fuse extra and pyfuse3 to use RivenVFS on disk.';

export const CONSOLE_UPDATER_NOTICE =
  'No Plex, Jellyfin, or Emby updater is configured — library refresh requests are logged only (console updater). Configure an updater under Settings → Updaters if you want your media server libraries to refresh automatically.';

const LABELS: Record<string, string> = {
  realdebrid: 'Real-Debrid',
  alldebrid: 'AllDebrid',
  debridlink: 'Debrid-Link',
  torbox: 'TorBox',
  torrentio: 'Torrentio',
  aiostreams: 'AIOStreams',
  comet: 'Comet',
  jackett: 'Jackett',
  mediafusion: 'Mediafusion',
  orionoid: 'Orionoid',
  prowlarr: 'Prowlarr',
  rarbg: 'RARBG',
  zilean: 'Zilean',
  overseerr: 'Overseerr',
  plexwatchlist: 'Plex watchlist',
  listrr: 'Listrr',
  mdblist: 'MDBList',
  traktcontent: 'Trakt',
  indexer: 'Indexer',
  post_processing: 'Post-processing',
  subtitle: 'Subtitles',
  notifications: 'Notifications',
  filesystem: 'Filesystem (VFS)',
  plexupdater: 'Plex library refresh',
  jellyfinupdater: 'Jellyfin library refresh',
  embyupdater: 'Emby library refresh',
  console: 'Console updater',
  consoleupdater: 'Console updater',
};

function normalizeKey(serviceKey: string): string {
  return serviceKey.toLowerCase().replace(/\s+/g, '');
}

export function humanizeServiceKey(serviceKey: string): string {
  const k = normalizeKey(serviceKey);
  if (LABELS[k]) return LABELS[k];
  return k
    .replace(/_/g, ' ')
    .replace(/\b([a-z])/g, (m) => m.toUpperCase());
}

/** Labels for EventManager queue `emitted_by` on the Activity downloader pipeline. */
const QUEUE_SOURCE_LABELS: Record<string, string> = {
  statetransition: 'Pipeline',
  retrylibrary: 'Library retry',
  scheduler: 'Scheduled',
  downloader: 'Downloader re-queue',
  retryitem: 'Retry',
  manual: 'Manual',
};

export function humanizeQueueSource(source: string): string {
  const k = normalizeKey(source);
  if (QUEUE_SOURCE_LABELS[k]) return QUEUE_SOURCE_LABELS[k];
  return humanizeServiceKey(source);
}

export type ParsedServicesResponse = {
  services: Record<string, boolean>;
  mockVfs: boolean;
  consoleUpdater: boolean;
};

/** Supports wrapped `{ services, mock_vfs, console_updater }` and legacy flat maps. */
export function parseServicesResponse(data: unknown): ParsedServicesResponse {
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const o = data as Record<string, unknown>;
    if (o.services && typeof o.services === 'object' && !Array.isArray(o.services)) {
      return {
        services: o.services as Record<string, boolean>,
        mockVfs: Boolean(o.mock_vfs),
        consoleUpdater: Boolean(o.console_updater),
      };
    }
    return {
      services: data as Record<string, boolean>,
      mockVfs: false,
      consoleUpdater: false,
    };
  }
  return { services: {}, mockVfs: false, consoleUpdater: false };
}

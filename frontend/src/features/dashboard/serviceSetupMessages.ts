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

export const KANBAN_COLUMN_ORDER = [
  'added',
  'scrape',
  'download',
  'symlink',
  'update',
  'finish',
] as const;

export type KanbanColumnId = (typeof KANBAN_COLUMN_ORDER)[number];

/** Columns rendered on the Activity Kanban board (excludes Added). */
export const ACTIVITY_KANBAN_COLUMNS = KANBAN_COLUMN_ORDER.filter(
  (col): col is Exclude<KanbanColumnId, 'added'> => col !== 'added',
);

export const KANBAN_COLUMN_LABELS: Record<KanbanColumnId, { short: string; tooltip: string }> =
  {
    added: { short: 'Added', tooltip: 'Indexing / queued for metadata' },
    scrape: { short: 'Scrape', tooltip: 'Finding torrents' },
    download: { short: 'Download', tooltip: 'Debrid download' },
    symlink: { short: 'Symlink', tooltip: 'Symlink to library' },
    update: { short: 'Update', tooltip: 'Library metadata refresh' },
    finish: { short: 'Done', tooltip: 'Post-processing' },
  };

/** Activity board display columns (merged backend kanban columns). */
export const ACTIVITY_DISPLAY_COLUMNS = [
  'prepare',
  'download',
  'library',
  'finish',
] as const;

export type ActivityDisplayColumnId = (typeof ACTIVITY_DISPLAY_COLUMNS)[number];

export const DISPLAY_COLUMN_LABELS: Record<
  ActivityDisplayColumnId,
  { short: string; tooltip: string }
> = {
  prepare: {
    short: 'Prepare',
    tooltip: 'Indexing metadata and scraping torrents',
  },
  download: {
    short: 'Download',
    tooltip: 'Debrid download',
  },
  library: {
    short: 'Library',
    tooltip: 'Symlink to library and media server refresh',
  },
  finish: {
    short: 'Done',
    tooltip: 'Post-processing and recently finished',
  },
};

export function mapBackendKanbanColumn(col: KanbanColumnId): ActivityDisplayColumnId {
  switch (col) {
    case 'added':
    case 'scrape':
      return 'prepare';
    case 'download':
      return 'download';
    case 'symlink':
    case 'update':
      return 'library';
    case 'finish':
    default:
      return 'finish';
  }
}

export function aggregateDisplayColumnCounts(
  backend: Partial<Record<KanbanColumnId, number>>,
): Record<ActivityDisplayColumnId, number> {
  const added = backend.added ?? 0;
  const scrape = backend.scrape ?? 0;
  const download = backend.download ?? 0;
  const symlink = backend.symlink ?? 0;
  const update = backend.update ?? 0;
  const finish = backend.finish ?? 0;
  return {
    prepare: added + scrape,
    download,
    library: symlink + update,
    finish,
  };
}

export type PipelineCardStatus =
  | 'running'
  | 'pending'
  | 'failed'
  | 'completed'
  | 'deferred';

export type PipelineCardLike = {
  state?: string | null;
  in_flight: boolean;
  actively_running?: boolean;
  deferred: boolean;
  pipeline_phase: string;
  activity?: string | null;
  run_at?: string | null;
  completion_detail?: string | null;
  completion_outcome?: string | null;
  failure_service?: string | null;
  emitted_by?: string | null;
};

const RUNNING_STEP_LABEL: Record<string, string> = {
  symlinking: 'Symlink',
  updating: 'Library refresh',
  post_processing: 'Post-processing',
  downloading: 'Download',
  scraping: 'Scrape',
  indexing: 'Index',
};

function humanizeActivity(activity: string): string {
  return activity.replace(/\b(realdebrid|alldebrid|debridlink|torbox)\b/gi, (key) =>
    humanizeServiceKey(key.toLowerCase()),
  );
}

/** Running in-flight subtext with a clear step label (Library column can mix symlink / refresh / post-process). */
export function formatRunningStepSubtext(phase: string, activity?: string | null): string {
  const label = RUNNING_STEP_LABEL[phase];
  const detail = activity?.trim() ? humanizeActivity(activity) : null;
  if (label && detail) return `${label} — ${detail}`;
  if (label) return label;
  if (detail) return detail;
  return pipelinePhaseTooltip(phase);
}

export function deriveRecentlyFinishedSubtext(item: PipelineCardLike): string {
  const failed =
    item.completion_outcome === 'failed' || item.state === 'Failed';
  if (failed) {
    const where = item.failure_service || item.emitted_by;
    const why = item.completion_detail?.trim() || 'Failed';
    if (where) {
      return `${humanizeServiceKey(where)}: ${why}`;
    }
    return why;
  }
  const detail = item.completion_detail?.trim();
  if (detail) return humanizeActivity(detail);
  return 'Finished';
}

export function deriveCardStatus(item: PipelineCardLike): PipelineCardStatus {
  if (item.pipeline_phase === 'recently_finished') {
    if (item.completion_outcome === 'failed' || item.state === 'Failed') {
      return 'failed';
    }
    return 'completed';
  }
  if (item.state === 'Failed') return 'failed';
  if (
    item.deferred &&
    (item.pipeline_phase === 'queued_download_deferred' || item.activity?.trim())
  ) {
    return 'deferred';
  }
  if (item.in_flight && item.actively_running) return 'running';
  return 'pending';
}

export function deriveCardStatusLabel(status: PipelineCardStatus): string {
  switch (status) {
    case 'running':
      return 'Running';
    case 'failed':
      return 'Failed';
    case 'completed':
      return 'Completed';
    case 'deferred':
      return 'Deferred';
    default:
      return 'Pending';
  }
}

export function deriveCardStatusShort(status: PipelineCardStatus): string {
  switch (status) {
    case 'running':
      return 'Run';
    case 'failed':
      return 'Fail';
    case 'completed':
      return 'Ok';
    case 'deferred':
      return 'Def';
    default:
      return 'Wait';
  }
}

/** Plain-text subtext when a live React countdown is not used. */
export function deriveCardSubtextPlain(item: PipelineCardLike): string {
  if (item.pipeline_phase === 'recently_finished') {
    return deriveRecentlyFinishedSubtext(item);
  }

  const activity = item.activity?.trim();
  if (item.in_flight && item.actively_running) {
    return formatRunningStepSubtext(item.pipeline_phase, activity);
  }

  if (activity) {
    return humanizeActivity(activity);
  }

  if (item.in_flight) {
    return pipelinePhaseTooltip(item.pipeline_phase);
  }

  if (item.deferred) {
    return pipelinePhaseTooltip(item.pipeline_phase);
  }

  return pipelinePhaseTooltip(item.pipeline_phase);
}

export function deriveCardStatusTooltip(item: PipelineCardLike): string {
  const parts: string[] = [pipelinePhaseTooltip(item.pipeline_phase)];
  const activity = item.activity?.trim();
  if (activity) {
    parts.push(
      activity.replace(/\b(realdebrid|alldebrid|debridlink|torbox)\b/gi, (key) =>
        humanizeServiceKey(key.toLowerCase()),
      ),
    );
  }
  if (item.state === 'Failed') parts.push('Item failed');
  if (item.emitted_by) parts.push(`Source: ${humanizeQueueSource(item.emitted_by)}`);
  return parts.join(' — ');
}

const PIPELINE_PHASE_SHORT: Record<string, string> = {
  indexing: '…',
  scraping: '…',
  downloading: '…',
  symlinking: '…',
  updating: '…',
  post_processing: '…',
  queued_index: 'Wait',
  queued_scrape: 'Due',
  queued_download: 'Due',
  queued_download_deferred: 'Def',
  queued_symlink: 'Due',
  queued_update: 'Due',
  queued_post_process: 'Due',
  queued_other: 'Wait',
  recently_finished: 'Done',
};

const PIPELINE_PHASE_TOOLTIP: Record<string, string> = {
  indexing: 'Indexing metadata',
  scraping: 'Scraping torrents',
  downloading: 'Downloading on debrid',
  symlinking: 'Creating library symlink',
  updating: 'Updating media server library',
  post_processing: 'Post-processing',
  queued_index: 'Queued for indexing',
  queued_scrape: 'Queued for scrape (ready)',
  queued_download: 'Queued for download (ready)',
  queued_download_deferred: 'Deferred — waiting for slot or cooldown',
  queued_symlink: 'Queued for symlink',
  queued_update: 'Queued for library update',
  queued_post_process: 'Queued for post-processing',
  queued_other: 'Queued',
  recently_finished: 'Finished — left the pipeline',
};

export function pipelinePhaseShort(phase: string): string {
  return PIPELINE_PHASE_SHORT[phase] ?? 'Wait';
}

export function pipelinePhaseTooltip(phase: string): string {
  return PIPELINE_PHASE_TOOLTIP[phase] ?? phase;
}

export function queueSourceShort(source: string): string {
  const full = humanizeQueueSource(source);
  if (full.length <= 6) return full;
  const k = normalizeKey(source);
  const map: Record<string, string> = {
    statetransition: 'Pipe',
    retrylibrary: 'Retry',
    scheduler: 'Sched',
    downloader: 'Re-Q',
    manual: 'Man',
    api: 'API',
  };
  return map[k] ?? full.slice(0, 4);
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

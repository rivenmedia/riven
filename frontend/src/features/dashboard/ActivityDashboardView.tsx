import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { KpiCardHeading } from '../../shared/ui/KpiInfoTip';
import { apiGet } from '../../shared/api/api';
import {
  formatEpisodeDisplayTitle,
  formatRelativeSeconds,
  getMediaKind,
  mediaLabel,
  parseApiDate,
  secondsSinceApiDate,
} from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import { humanizeQueueSource, humanizeServiceKey } from './serviceSetupMessages';

/** /downloader_status only — do not poll /stats or /rate_limits here (see 24b0bb67, 8e28cd26). */
const STATUS_POLL_MS = 3000;
/** Match backend _RECENT_JOBS_MAX_AGE — hide stale rows between polls. */
const RECENT_JOB_MAX_AGE_SEC = 120;
/** DB-vs-queue backlog hint is for post-restart context; hide after this long on the page. */
const DB_BACKLOG_HINT_VISIBLE_MS = 60_000;

const DOWNLOADER_KEYS = ['realdebrid', 'alldebrid', 'debridlink', 'torbox'] as const;

const QUEUE_SOURCE_CHART_COLORS = [
  'hsl(220 70% 58%)',
  'hsl(152 42% 42%)',
  'hsl(38 82% 52%)',
  'hsl(0 62% 55%)',
  'hsl(270 55% 62%)',
  'hsl(190 55% 48%)',
];

const DOWNLOADER_KPI_TIPS = {
  queueSources:
    'Why items are in the downloader queue (deduped by item): pipeline scrape, downloader re-queue, library retry, etc.',
  scrapedDb:
    'Scraped in the database but not necessarily in the live download queue yet. A Riven restart or Retry Active Library re-queues them over time.',
  deferred:
    'In the event queue with a future run time—waiting on downloader spacing, provider cooldown, or pause.',
  queuedDue:
    'In the event queue and due now—next in line when the downloader slot is free (can be many).',
  downloading:
    'Actively running on the downloader worker (usually 0 or 1).',
  downloaderEmitted:
    'Queued events emitted by the downloader service (often re-queues after deferral).',
} as const;

/** 0° = top, clockwise positive */
function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function pieSlicePath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  if (endDeg - startDeg <= 0.01) return '';
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function QueueSourcesPieChart({ entries }: { entries: [string, number][] }) {
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (total <= 0) return <p className="muted queue-sources-pie__empty">—</p>;

  const cx = 50;
  const cy = 50;
  const r = 42;
  let angle = -90;

  const slices = entries.map(([source, count], index) => {
    const sweep = (count / total) * 360;
    const start = angle;
    const end = angle + sweep;
    angle = end;
    const fullCircle = entries.length === 1 || sweep >= 359.995;
    return {
      source,
      count,
      fullCircle,
      path: fullCircle ? null : pieSlicePath(cx, cy, r, start, end),
      color: QUEUE_SOURCE_CHART_COLORS[index % QUEUE_SOURCE_CHART_COLORS.length],
      label: humanizeQueueSource(source),
      pct: Math.round((count / total) * 100),
    };
  });

  const ariaLabel = slices.map((s) => `${s.label} ${s.count}`).join(', ');

  return (
    <div className="queue-sources-pie">
      <svg
        className="queue-sources-pie__chart"
        viewBox="0 0 100 100"
        role="img"
        aria-label={`Queue sources: ${ariaLabel}`}
      >
        {slices.map((slice) =>
          slice.fullCircle ? (
            <circle
              key={slice.source}
              cx={cx}
              cy={cy}
              r={r}
              fill={slice.color}
              stroke="var(--panel, #18181b)"
              strokeWidth={0.6}
            >
              <title>
                {slice.label}: {slice.count.toLocaleString()} ({slice.pct}%)
              </title>
            </circle>
          ) : slice.path ? (
            <path
              key={slice.source}
              d={slice.path}
              fill={slice.color}
              stroke="var(--panel, #18181b)"
              strokeWidth={0.6}
            >
              <title>
                {slice.label}: {slice.count.toLocaleString()} ({slice.pct}%)
              </title>
            </path>
          ) : null,
        )}
      </svg>
      <ul className="queue-sources-pie__legend">
        {slices.map((slice) => (
          <li key={slice.source} className="queue-sources-pie__legend-item">
            <span className="queue-sources-pie__swatch" style={{ background: slice.color }} />
            <span className="queue-sources-pie__label">{slice.label}</span>
            <span className="queue-sources-pie__meta muted">
              {slice.count.toLocaleString()}
              <span className="queue-sources-pie__pct"> ({slice.pct}%)</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type ServiceStatus = {
  key: string;
  available: boolean;
  cooldown_until: string | null;
};

type InFlightItem = {
  id: number;
  title: string;
  type: string;
  parent_title?: string | null;
  season_number?: number | null;
  episode_number?: number | null;
  state?: string | null;
};

type QueuedItem = InFlightItem & {
  run_at: string;
  queued_at: string;
  scraped_at?: string | null;
  deferred: boolean;
  wait_seconds: number;
  emitted_by: string;
};

type LastJob = {
  item: InFlightItem | null;
  completed_at: string | null;
  outcome: 'success' | 'deferred' | 'failed' | 'skipped' | null;
  detail?: string | null;
  service?: string | null;
};

type DownloaderStatus = {
  paused: boolean;
  pause_until: string | null;
  min_job_interval_seconds: number;
  queue: {
    scraped_queued: number;
    scraped_ready?: number;
    deferred: number;
    total_queued?: number;
    downloader_emitted: number;
    queue_by_source?: Record<string, number>;
    next_ready_at: string | null;
    queue_truncated?: boolean;
    scraped_in_library?: number;
  };
  services: ServiceStatus[];
  in_flight_total?: number;
  in_flight_items: InFlightItem[];
  queued_items: QueuedItem[];
  recent_jobs: LastJob[];
};

function inFlightDisplayTitle(item: InFlightItem): string {
  if (item.type === 'episode') {
    return formatEpisodeDisplayTitle(item);
  }
  if (item.type === 'season' && item.parent_title != null && item.season_number != null) {
    return `${item.parent_title} S${String(item.season_number).padStart(2, '0')}`;
  }
  return item.title || `Item ${item.id}`;
}

function mediaTypeTagClass(item: InFlightItem): string {
  const kind = getMediaKind(item);
  if (kind === 'movie' || kind === 'tv') return `media-tag media-tag--${kind}`;
  return 'media-tag media-tag--neutral';
}

function mediaTypeTagLabel(item: InFlightItem): string {
  const kind = getMediaKind(item);
  if (kind === 'movie' || kind === 'tv') return mediaLabel(item);
  return item.type;
}

function outcomePillClass(outcome: LastJob['outcome']): string {
  return `pill downloader-outcome downloader-outcome--${outcome ?? 'unknown'}`;
}

function queueWaitLabel(item: QueuedItem): string {
  if (item.deferred) {
    return `Starts ${formatRelativeSeconds(item.wait_seconds, 'future')}`;
  }
  return `Waiting ${formatRelativeSeconds(item.wait_seconds, 'past')}`;
}

type PipelineQueuePhase = 'downloading' | 'due' | 'deferred';

type PipelineQueueEntry =
  | { phase: 'downloading'; item: InFlightItem }
  | { phase: 'queued'; item: QueuedItem };

function pipelinePhase(item: QueuedItem): PipelineQueuePhase {
  return item.deferred ? 'deferred' : 'due';
}

function pipelineStatusPillClass(phase: PipelineQueuePhase): string {
  return `pill downloader-queue-status downloader-queue-status--${phase}`;
}

function pipelineStatusLabel(phase: PipelineQueuePhase): string {
  switch (phase) {
    case 'downloading':
      return 'Downloading';
    case 'deferred':
      return 'Deferred';
    default:
      return 'Due';
  }
}

function compareQueuedItems(a: QueuedItem, b: QueuedItem): number {
  const phaseOrder = (item: QueuedItem) => (item.deferred ? 1 : 0);
  const phaseDiff = phaseOrder(a) - phaseOrder(b);
  if (phaseDiff !== 0) return phaseDiff;
  const aAt = parseApiDate(a.run_at)?.getTime() ?? 0;
  const bAt = parseApiDate(b.run_at)?.getTime() ?? 0;
  return aAt - bAt;
}

function PipelineQueueRow({ entry }: { entry: PipelineQueueEntry }) {
  if (entry.phase === 'downloading') {
    const item = entry.item;
    return (
      <div className="media-list__row downloader-in-flight-row downloader-queue-row">
        <span className={mediaTypeTagClass(item)}>{mediaTypeTagLabel(item)}</span>
        <span className={pipelineStatusPillClass('downloading')}>
          {pipelineStatusLabel('downloading')}
        </span>
        <div className="downloader-queue-row__main">
          <a className="downloader-in-flight-row__title" href={`#/item/${item.id}`}>
            {inFlightDisplayTitle(item)}
          </a>
        </div>
        {item.state && (
          <span className="downloader-in-flight-row__state muted">{item.state}</span>
        )}
      </div>
    );
  }

  return <QueueRow item={entry.item} />;
}

function QueueRow({ item }: { item: QueuedItem }) {
  return (
    <div className="media-list__row downloader-in-flight-row downloader-queue-row">
      <span className={mediaTypeTagClass(item)}>{mediaTypeTagLabel(item)}</span>
      <span className={pipelineStatusPillClass(pipelinePhase(item))}>
        {pipelineStatusLabel(pipelinePhase(item))}
      </span>
      <div className="downloader-queue-row__main">
        <a className="downloader-in-flight-row__title" href={`#/item/${item.id}`}>
          {inFlightDisplayTitle(item)}
        </a>
        {item.scraped_at && (
          <span className="muted downloader-queue-row__sub">
            Scraped{' '}
            {formatRelativeSeconds(secondsSinceApiDate(item.scraped_at) ?? 0, 'past')}
          </span>
        )}
      </div>
      <span className="downloader-in-flight-row__state muted">
        <span className="pill pill--muted downloader-queue-emitted">
          {humanizeQueueSource(item.emitted_by)}
        </span>
        {' · '}
        {queueWaitLabel(item)}
      </span>
    </div>
  );
}

function outcomeLabel(outcome: LastJob['outcome']): string {
  switch (outcome) {
    case 'success':
      return 'Success';
    case 'deferred':
      return 'Deferred';
    case 'failed':
      return 'Failed';
    case 'skipped':
      return 'Skipped';
    default:
      return '—';
  }
}

function formatCountdown(iso: string | null): string {
  if (!iso) return '—';
  const target = parseApiDate(iso)?.getTime();
  if (target == null || !Number.isFinite(target)) return '—';
  const sec = Math.max(0, Math.round((target - Date.now()) / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return `${min}m ${rem}s`;
  const hr = Math.floor(min / 60);
  const minRem = min % 60;
  return `${hr}h ${minRem}m`;
}

function formatElapsedSeconds(seconds: number): string {
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return rem > 0 ? `${min}m ${rem}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const minRem = min % 60;
  return minRem > 0 ? `${hr}h ${minRem}m` : `${hr}h`;
}

function LiveCountdown({ iso }: { iso: string }) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [iso]);

  return <strong className="downloader-live-countdown">{formatCountdown(iso)}</strong>;
}

function LiveElapsed({ iso }: { iso: string }) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [iso]);

  const age = secondsSinceApiDate(iso);
  if (age == null) return <>—</>;
  return <span className="downloader-live-elapsed">{formatElapsedSeconds(age)}</span>;
}

function dedupeQueuedItems(items: QueuedItem[]): QueuedItem[] {
  const byId = new Map<number, QueuedItem>();
  for (const item of items) {
    const prev = byId.get(item.id);
    if (!prev) {
      byId.set(item.id, item);
      continue;
    }
    byId.set(item.id, compareQueuedItems(item, prev) <= 0 ? item : prev);
  }
  return [...byId.values()];
}

function normalizeDownloaderStatus(raw: DownloaderStatus | null | undefined): DownloaderStatus | null {
  if (!raw || typeof raw !== 'object') return null;

  const queue = raw.queue ?? {
    scraped_queued: 0,
    scraped_ready: 0,
    deferred: 0,
    total_queued: 0,
    downloader_emitted: 0,
    next_ready_at: null,
    queue_truncated: false,
  };

  return {
    paused: Boolean(raw.paused),
    pause_until: raw.pause_until ?? null,
    min_job_interval_seconds: Number(raw.min_job_interval_seconds) || 0,
    queue: {
      scraped_queued: Number(queue.scraped_queued) || 0,
      scraped_ready: Number(queue.scraped_ready) || 0,
      deferred: Number(queue.deferred) || 0,
      total_queued: Number(queue.total_queued) || 0,
      downloader_emitted: Number(queue.downloader_emitted) || 0,
      queue_by_source:
        queue.queue_by_source && typeof queue.queue_by_source === 'object'
          ? queue.queue_by_source
          : {},
      next_ready_at: queue.next_ready_at ?? null,
      queue_truncated: Boolean(queue.queue_truncated),
      scraped_in_library: Number(queue.scraped_in_library) || 0,
    },
    services: Array.isArray(raw.services) ? raw.services : [],
    in_flight_total:
      typeof raw.in_flight_total === 'number'
        ? raw.in_flight_total
        : Array.isArray(raw.in_flight_items)
          ? raw.in_flight_items.length
          : 0,
    in_flight_items: Array.isArray(raw.in_flight_items)
      ? raw.in_flight_items
      : Array.isArray((raw as { in_flight_item_ids?: number[] }).in_flight_item_ids)
        ? (raw as { in_flight_item_ids: number[] }).in_flight_item_ids.map((id) => ({
            id,
            title: `Item ${id}`,
            type: 'unknown',
          }))
        : [],
    queued_items: Array.isArray(raw.queued_items) ? raw.queued_items : [],
    recent_jobs: Array.isArray(raw.recent_jobs) ? raw.recent_jobs : [],
  };
}

export default function ActivityDashboardView(_props: { route: AppRoute }) {
  const [status, setStatus] = useState<DownloaderStatus | null>(null);
  const [scrapedDbCount, setScrapedDbCount] = useState<number | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const pageOpenedAtRef = useRef(Date.now());
  const [showDbBacklogHint, setShowDbBacklogHint] = useState(true);

  useEffect(() => {
    const elapsed = Date.now() - pageOpenedAtRef.current;
    const remaining = DB_BACKLOG_HINT_VISIBLE_MS - elapsed;
    if (remaining <= 0) {
      setShowDbBacklogHint(false);
      return undefined;
    }
    const id = window.setTimeout(() => setShowDbBacklogHint(false), remaining);
    return () => window.clearTimeout(id);
  }, []);

  const loadStatus = useCallback(async () => {
    const res = await apiGet<DownloaderStatus>('/downloader_status');
    if (res.ok && res.data) {
      const normalized = normalizeDownloaderStatus(res.data);
      setStatus(normalized);
      setScrapedDbCount(normalized?.queue.scraped_in_library ?? null);
      setPipelineError(null);
    } else {
      setStatus(null);
      setPipelineError(res.error || 'Failed to load download pipeline');
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    const id = window.setInterval(() => void loadStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [loadStatus]);

  const [clockTick, setClockTick] = useState(0);

  useEffect(() => {
    const needsLiveClock =
      Boolean(status?.queue?.next_ready_at) ||
      (status?.paused && Boolean(status.pause_until));
    if (!needsLiveClock) return undefined;
    const id = window.setInterval(() => setClockTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [status?.queue?.next_ready_at, status?.paused, status?.pause_until]);

  const pipelineBanner = useMemo(() => {
    if (!status) return null;
    void clockTick;
    if (status.paused) {
      return {
        modifier: 'paused',
        title: 'Downloader paused',
        detail: `All providers cooling down — resumes in ${formatCountdown(status.pause_until)}`,
      };
    }
    return {
      modifier: 'ok',
      title: 'Downloader active',
      detail: `Job spacing: ${(status.min_job_interval_seconds ?? 0).toFixed(2)}s between runs`,
    };
  }, [status, clockTick]);

  /** Downloading first, then due, then deferred (soonest run_at within each band). */
  const pipelineQueueEntries = useMemo((): PipelineQueueEntry[] => {
    if (!status) return [];

    const seenInFlight = new Set<number>();
    const entries: PipelineQueueEntry[] = [];
    for (const item of status.in_flight_items ?? []) {
      if (seenInFlight.has(item.id)) continue;
      seenInFlight.add(item.id);
      entries.push({ phase: 'downloading', item });
    }

    const queued = dedupeQueuedItems(status.queued_items ?? []).sort(compareQueuedItems);
    for (const item of queued) {
      entries.push({ phase: 'queued', item });
    }

    return entries;
  }, [status]);

  const dbBacklogHint = useMemo(() => {
    if (!showDbBacklogHint || !status?.queue) return null;
    const inDb = status.queue.scraped_in_library ?? 0;
    const inQueue = status.queue.total_queued ?? 0;
    if (inDb > inQueue + 50) {
      return `${inDb.toLocaleString()} scraped items are in the database but not in the live download queue (common after a restart). Restart Riven to re-queue up to 500, or use Retry Active Library on the Overview dashboard.`;
    }
    return null;
  }, [showDbBacklogHint, status?.queue]);

  const queueSourceEntries = useMemo(() => {
    const raw = status?.queue?.queue_by_source;
    if (!raw || typeof raw !== 'object') return [];
    return Object.entries(raw)
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1]);
  }, [status?.queue?.queue_by_source]);

  const recentJobsForDisplay = useMemo(() => {
    const inFlightIds = new Set((status?.in_flight_items ?? []).map((item) => item.id));
    const filtered = (status?.recent_jobs ?? []).filter((job) => {
      if (!job.item || !job.completed_at || inFlightIds.has(job.item.id)) return false;
      const age = secondsSinceApiDate(job.completed_at);
      return age != null && age <= RECENT_JOB_MAX_AGE_SEC;
    });
    // API is newest-first; show oldest at top so new completions appear at the bottom.
    return filtered.slice().reverse();
  }, [status?.recent_jobs, status?.in_flight_items]);

  return (
    <ViewLayout className="view-dashboard view-dashboard-activity" view="dashboard-activity">
      <ViewHeader
        title="Activity"
        subtitle="Download pipeline and queue status"
      />

      {pipelineError && (
        <Panel>
          <p className="downloader-status__error">{pipelineError}</p>
        </Panel>
      )}

      <Panel title="Download pipeline">
        {pipelineBanner && status && (
          <div
            className={`downloader-status-banner downloader-status-banner--${pipelineBanner.modifier}`}
          >
            <strong>{pipelineBanner.title}</strong>
            <span className="downloader-status-banner__detail">{pipelineBanner.detail}</span>
          </div>
        )}

        <div className="downloader-status-services">
          {DOWNLOADER_KEYS.map((key) => {
            const svc = status?.services.find((s) => s.key === key);
            const enabled = svc != null;

            return (
              <article key={key} className="downloader-card downloader-status-card">
                <div className="downloader-card__head">
                  <strong>{humanizeServiceKey(key)}</strong>
                  <span
                    className={
                      enabled
                        ? svc?.available
                          ? 'service-row__status--up'
                          : 'service-row__status--down'
                        : 'muted'
                    }
                  >
                    {!enabled ? 'Off' : svc?.available ? 'Available' : 'Cooldown'}
                  </span>
                </div>
              </article>
            );
          })}
        </div>

        <section
          className="kpi-grid activity-pipeline-kpis"
          aria-label="Downloader pipeline"
        >
          <article className="kpi-card kpi-card--queue-sources">
            <KpiCardHeading
              label="Queue sources"
              description={DOWNLOADER_KPI_TIPS.queueSources}
            />
            <QueueSourcesPieChart entries={queueSourceEntries} />
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="In library (DB)"
              description={DOWNLOADER_KPI_TIPS.scrapedDb}
            />
            <p className="kpi-value">{scrapedDbCount ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Deferred"
              description={DOWNLOADER_KPI_TIPS.deferred}
            />
            <p className="kpi-value">{status?.queue?.deferred ?? '—'}</p>
            {status?.queue?.next_ready_at && (
              <p className="kpi-sub">
                Next deferred → queued (due) in{' '}
                <LiveCountdown iso={status.queue.next_ready_at} />
              </p>
            )}
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Queued (due)"
              description={DOWNLOADER_KPI_TIPS.queuedDue}
            />
            <p className="kpi-value">{status?.queue?.scraped_ready ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Downloading"
              description={DOWNLOADER_KPI_TIPS.downloading}
            />
            <p className="kpi-value">
              {status != null
                ? (status.in_flight_total ?? status.in_flight_items?.length ?? 0)
                : '—'}
            </p>
          </article>
        </section>

        {dbBacklogHint && (
          <p className="muted downloader-status__hint downloader-status__hint--warn">
            {dbBacklogHint}
          </p>
        )}

        {recentJobsForDisplay.length > 0 && (
          <div className="activity-pipeline-subpanel">
            <h3 className="activity-pipeline-subpanel__title">Recently processed</h3>
            <div className="downloader-recent-jobs-list">
              {recentJobsForDisplay.map((job) => (
                <div key={`${job.item!.id}-${job.completed_at}`} className="downloader-recent-job">
                  <div className="media-list__row downloader-in-flight-row downloader-queue-row downloader-last-job-row">
                    <span className={outcomePillClass(job.outcome)}>
                      {outcomeLabel(job.outcome)}
                    </span>
                    <div className="downloader-queue-row__main">
                      <a
                        className="downloader-in-flight-row__title"
                        href={`#/item/${job.item!.id}`}
                      >
                        {inFlightDisplayTitle(job.item!)}
                      </a>
                      {job.detail && (
                        <span className="muted downloader-queue-row__sub">{job.detail}</span>
                      )}
                    </div>
                    <span className="downloader-in-flight-row__state muted">
                      <LiveElapsed iso={job.completed_at!} />
                      {job.service ? ` · ${humanizeServiceKey(job.service)}` : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {pipelineQueueEntries.length > 0 && (
          <div className="activity-pipeline-subpanel">
            <h3 className="activity-pipeline-subpanel__title">Queue</h3>
            {status?.queue?.queue_truncated && (
              <p className="muted downloader-status__hint">
                Showing {status.queued_items.length} of{' '}
                {(status.queue.total_queued ?? status.queued_items.length).toLocaleString()}{' '}
                queued jobs (downloading always shown).
              </p>
            )}
            {(status?.in_flight_total ?? 0) > (status?.in_flight_items?.length ?? 0) && (
              <p className="muted downloader-status__hint">
                Downloading: showing {status.in_flight_items.length} of{' '}
                {status.in_flight_total}.
              </p>
            )}
            <div className="downloader-in-flight-list">
              {pipelineQueueEntries.map((entry) => (
                <PipelineQueueRow
                  key={`${entry.phase}-${entry.item.id}`}
                  entry={entry}
                />
              ))}
            </div>
          </div>
        )}

      </Panel>
    </ViewLayout>
  );
}

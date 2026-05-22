import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { KpiCardHeading } from '../../shared/ui/KpiInfoTip';
import {
  LiveCountdownToIso,
  LiveElapsedIso,
  LiveServerCountdown,
  secondsUntilRunAt,
} from '../../shared/ui/LiveTimer';
import { resolveKanbanSubtextKind } from './pipelineKanbanSubtext';
import { apiGet, apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import {
  formatCompactPipelineTitle,
  getMediaKind,
  mediaLabel,
  parseApiDate,
} from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import {
  ACTIVITY_DISPLAY_COLUMNS,
  DISPLAY_COLUMN_LABELS,
  aggregateDisplayColumnCounts,
  deriveCardStatus,
  deriveCardStatusLabel,
  deriveCardStatusShort,
  deriveCardStatusTooltip,
  deriveCardSubtextPlain,
  mapBackendKanbanColumn,
  type ActivityDisplayColumnId,
  type KanbanColumnId,
  type PipelineCardStatus,
} from './serviceSetupMessages';
import { OverflowMarquee } from '../../shared/ui/OverflowMarquee';
import { ServiceRateLimitCard } from '../../shared/rateLimits/ServiceRateLimitCard';
import { sortOwnerKeys } from '../../shared/rateLimits/owners';
import type { LimiterSnapshot } from '../../shared/rateLimits/types';

const STATUS_POLL_MS = 3000;

const KPI_TIPS = {
  indexedDb: 'Items in the library database waiting to be scraped.',
  scrapedDb:
    'Items with torrents found but not necessarily in the live queue (common after restart).',
  deferred: 'Queued with a future run time — downloader spacing or cooldown.',
} as const;

type ServiceStatus = {
  key: string;
  available: boolean;
  cooldown_until: string | null;
};

type PipelineItem = {
  id: number | null;
  content_title?: string | null;
  title: string;
  type: string;
  parent_title?: string | null;
  season_number?: number | null;
  episode_number?: number | null;
  state?: string | null;
  activity?: string | null;
  kanban_column: KanbanColumnId;
  pipeline_phase: string;
  in_flight: boolean;
  actively_running: boolean;
  deferred: boolean;
  reorderable: boolean;
  run_at?: string | null;
  queued_at?: string | null;
  scraped_at?: string | null;
  emitted_by?: string | null;
  completion_detail?: string | null;
  completion_outcome?: string | null;
  failure_service?: string | null;
  sort_rank: number;
};

type ActivityStatus = {
  pipeline: {
    queue: {
      total_queued: number;
      total_items: number;
      deferred: number;
      queue_truncated: boolean;
      scraped_not_in_queue?: number;
      next_ready_in_seconds?: number | null;
      columns: Record<KanbanColumnId, number>;
    };
    items: PipelineItem[];
  };
  downloader: {
    paused: boolean;
    pause_until: string | null;
    min_job_interval_seconds: number;
    services: ServiceStatus[];
    scraper_services: string[];
    rate_limits: LimiterSnapshot[];
    initialized: boolean;
  };
  library_backlog: {
    indexed: number;
    scraped: number;
    requested: number;
  };
};

function mediaTypeTagClass(item: PipelineItem): string {
  const kind = getMediaKind(item);
  if (kind === 'movie' || kind === 'tv') return `media-tag media-tag--${kind}`;
  return 'media-tag media-tag--neutral';
}

function mediaTypeTagLabel(item: PipelineItem): string {
  const kind = getMediaKind(item);
  if (kind === 'movie' || kind === 'tv') return mediaLabel(item);
  return item.type;
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

function DoubleChevronUpIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M7 15l5-5 5 5M7 9l5-5 5 5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DoubleChevronDownIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M7 9l5 5 5-5M7 15l5 5 5-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CancelIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M6 6l12 12M18 6L6 18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M4 4v6h6M20 20v-6h-6M5 19a9 9 0 0014-7.5M19 5a9 9 0 00-14 7.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type QueueCardAction = 'prioritize' | 'deprioritize' | 'dequeue' | 'retry_failed';

function KanbanCardActionOverlay({
  itemId,
  queueActionId,
  mode,
  onAction,
}: {
  itemId: number;
  queueActionId: number | null;
  mode: 'queue' | 'retry_failed';
  onAction: (itemId: number, action: QueueCardAction) => void;
}) {
  const busy = queueActionId === itemId;
  if (mode === 'retry_failed') {
    return (
      <div className="activity-kanban__card-actions" role="group" aria-label="Retry failed job">
        <button
          type="button"
          className="downloader-queue-reorder-btn downloader-queue-reorder-btn--retry"
          title="Retry from the step that failed"
          aria-label="Retry failed job"
          disabled={busy}
          onClick={() => onAction(itemId, 'retry_failed')}
        >
          <RetryIcon />
        </button>
      </div>
    );
  }
  return (
    <div className="activity-kanban__card-actions" role="group" aria-label="Queue actions">
      <button
        type="button"
        className="downloader-queue-reorder-btn"
        title="Move up in column"
        aria-label="Prioritize"
        disabled={busy}
        onClick={() => onAction(itemId, 'prioritize')}
      >
        <DoubleChevronUpIcon />
      </button>
      <button
        type="button"
        className="downloader-queue-reorder-btn"
        title="Move down in column"
        aria-label="Deprioritize"
        disabled={busy}
        onClick={() => onAction(itemId, 'deprioritize')}
      >
        <DoubleChevronDownIcon />
      </button>
      <button
        type="button"
        className="downloader-queue-reorder-btn downloader-queue-reorder-btn--cancel"
        title="Remove from queue (item may be re-queued later)"
        aria-label="Dequeue"
        disabled={busy}
        onClick={() => onAction(itemId, 'dequeue')}
      >
        <CancelIcon />
      </button>
    </div>
  );
}

function KanbanSubtext({
  children,
  title,
}: {
  children: ReactNode;
  title?: string;
}) {
  return (
    <OverflowMarquee className="activity-kanban__subtext" title={title}>
      {children}
    </OverflowMarquee>
  );
}

function KanbanPhaseSubtext({ item }: { item: PipelineItem }) {
  const text = deriveCardSubtextPlain(item);
  return <KanbanSubtext title={text}>{text}</KanbanSubtext>;
}

/** Ticks every second so countdown can hand off to phase subtext without a blank frame. */
function KanbanDueCountdownSubtext({ item }: { item: PipelineItem }) {
  const [, setTick] = useState(0);
  const runAt = item.run_at;

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [runAt]);

  const until = runAt ? secondsUntilRunAt(runAt) : null;
  if (until != null && until <= 0) {
    return <KanbanPhaseSubtext item={item} />;
  }

  const countdown = runAt ? <LiveCountdownToIso iso={runAt} /> : null;
  if (countdown == null) {
    return <KanbanPhaseSubtext item={item} />;
  }

  return <KanbanSubtext>{countdown}</KanbanSubtext>;
}

function KanbanCardSubtext({ item }: { item: PipelineItem }) {
  switch (resolveKanbanSubtextKind(item)) {
    case 'pool_wait':
      return (
        <KanbanSubtext title="Submitted to worker pool">Waiting for worker</KanbanSubtext>
      );
    case 'activity': {
      const text = deriveCardSubtextPlain(item);
      return <KanbanSubtext title={text}>{text}</KanbanSubtext>;
    }
    case 'countdown':
      return item.run_at ? (
        <KanbanDueCountdownSubtext item={item} />
      ) : (
        <KanbanPhaseSubtext item={item} />
      );
    case 'recently_finished':
      return item.run_at ? (
        <KanbanSubtext>
          Finished <LiveElapsedIso iso={item.run_at} className="activity-kanban__subtext-timer" />{' '}
          ago
        </KanbanSubtext>
      ) : (
        <KanbanPhaseSubtext item={item} />
      );
    case 'next':
      return <KanbanPhaseSubtext item={item} />;
    case 'phase':
    default:
      return <KanbanPhaseSubtext item={item} />;
  }
}

function KanbanStatusPill({ item, status }: { item: PipelineItem; status: PipelineCardStatus }) {
  const tip = deriveCardStatusTooltip(item);
  return (
    <span
      className={`activity-kanban__status-pill activity-kanban__status-pill--${status}`}
      title={tip}
      aria-label={deriveCardStatusLabel(status)}
    >
      {deriveCardStatusShort(status)}
    </span>
  );
}

function KanbanCard({
  item,
  queueActionId,
  onQueueAction,
}: {
  item: PipelineItem;
  queueActionId: number | null;
  onQueueAction: (itemId: number, action: QueueCardAction) => void;
}) {
  const title =
    item.id != null ? formatCompactPipelineTitle(item) : item.content_title || item.title;
  const cardStatus = deriveCardStatus(item);
  const failedDone =
    item.pipeline_phase === 'recently_finished' &&
    (item.completion_outcome === 'failed' || item.state === 'Failed');
  const queueActionable = item.reorderable && item.id != null;
  const retryActionable = failedDone && item.id != null;
  const overlayMode = retryActionable ? 'retry_failed' : 'queue';
  const showOverlay = queueActionable || retryActionable;

  return (
    <article
      className={`activity-kanban__card${item.in_flight ? ' activity-kanban__card--in-flight' : ''}${cardStatus === 'failed' ? ' activity-kanban__card--failed' : ''}${cardStatus === 'completed' ? ' activity-kanban__card--completed' : ''}${cardStatus === 'deferred' ? ' activity-kanban__card--deferred' : ''}${showOverlay ? ' activity-kanban__card--actionable' : ''}`}
    >
      <span className={mediaTypeTagClass(item)}>{mediaTypeTagLabel(item)}</span>
      <div className="activity-kanban__card-main">
        <div className="activity-kanban__card-head">
          {item.id != null ? (
            <a className="activity-kanban__title" href={`#/item/${item.id}`} title={title}>
              {title}
            </a>
          ) : (
            <span className="activity-kanban__title activity-kanban__title--static" title={title}>
              {title}
            </span>
          )}
        </div>
        <KanbanCardSubtext item={item} />
      </div>
      <div className="activity-kanban__card-aside">
        <KanbanStatusPill item={item} status={cardStatus} />
      </div>
      {showOverlay && (
        <KanbanCardActionOverlay
          itemId={item.id!}
          queueActionId={queueActionId}
          mode={overlayMode}
          onAction={onQueueAction}
        />
      )}
    </article>
  );
}

function normalizeActivityStatus(raw: unknown): ActivityStatus | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const pipeline = (o.pipeline ?? {}) as Record<string, unknown>;
  const queue = (pipeline.queue ?? {}) as Record<string, unknown>;
  const cols = (queue.columns ?? {}) as Record<string, unknown>;
  const downloader = (o.downloader ?? {}) as Record<string, unknown>;
  const backlog = (o.library_backlog ?? {}) as Record<string, unknown>;

  const backendColumns = {
    added: Number(cols.added) || 0,
    scrape: Number(cols.scrape) || 0,
    download: Number(cols.download) || 0,
    symlink: Number(cols.symlink) || 0,
    update: Number(cols.update) || 0,
    finish: Number(cols.finish) || 0,
  } as Record<KanbanColumnId, number>;

  const items: PipelineItem[] = Array.isArray(pipeline.items)
    ? (pipeline.items as Record<string, unknown>[]).map((row, index) => {
        const backendCol = (
          ['added', 'scrape', 'download', 'symlink', 'update', 'finish'] as const
        ).includes(row.kanban_column as KanbanColumnId)
          ? (row.kanban_column as KanbanColumnId)
          : 'finish';
        return {
          id: row.id != null ? Number(row.id) : null,
          content_title: row.content_title as string | null | undefined,
          title: String(row.title ?? row.content_title ?? 'Unknown'),
          type: String(row.type ?? 'unknown'),
          parent_title: row.parent_title as string | null | undefined,
          season_number: row.season_number as number | null | undefined,
          episode_number: row.episode_number as number | null | undefined,
          state: row.state as string | null | undefined,
          activity: row.activity as string | null | undefined,
          kanban_column: backendCol,
          pipeline_phase: String(row.pipeline_phase ?? 'queued_other'),
        in_flight: Boolean(row.in_flight),
        actively_running: Boolean(row.actively_running),
        deferred: Boolean(row.deferred),
          reorderable: Boolean(row.reorderable),
          run_at: row.run_at as string | null | undefined,
          queued_at: row.queued_at as string | null | undefined,
          scraped_at: row.scraped_at as string | null | undefined,
          emitted_by: row.emitted_by as string | null | undefined,
          completion_detail: row.completion_detail as string | null | undefined,
          completion_outcome: row.completion_outcome as string | null | undefined,
          failure_service: row.failure_service as string | null | undefined,
          sort_rank: Number(row.sort_rank) || index,
        };
      })
    : [];

  return {
    pipeline: {
      queue: {
        total_queued: Number(queue.total_queued) || 0,
        total_items: Number(queue.total_items) || 0,
        deferred: Number(queue.deferred) || 0,
        queue_truncated: Boolean(queue.queue_truncated),
        scraped_not_in_queue: Number(queue.scraped_not_in_queue) || 0,
        next_ready_in_seconds:
          queue.next_ready_in_seconds != null &&
          Number.isFinite(Number(queue.next_ready_in_seconds))
            ? Number(queue.next_ready_in_seconds)
            : null,
        columns: backendColumns,
      },
      items,
    },
    downloader: {
      paused: Boolean(downloader.paused),
      pause_until: (downloader.pause_until as string | null) ?? null,
      min_job_interval_seconds: Number(downloader.min_job_interval_seconds) || 0,
      services: Array.isArray(downloader.services)
        ? (downloader.services as ServiceStatus[])
        : [],
      scraper_services: Array.isArray(downloader.scraper_services)
        ? (downloader.scraper_services as string[])
        : [],
      rate_limits: Array.isArray(downloader.rate_limits)
        ? (downloader.rate_limits as LimiterSnapshot[])
        : [],
      initialized: Boolean(downloader.initialized),
    },
    library_backlog: {
      indexed: Number(backlog.indexed) || 0,
      scraped: Number(backlog.scraped) || 0,
      requested: Number(backlog.requested) || 0,
    },
  };
}

export default function ActivityDashboardView(_props: { route: AppRoute }) {
  const [status, setStatus] = useState<ActivityStatus | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [queueActionId, setQueueActionId] = useState<number | null>(null);
  const loadStatus = useCallback(async () => {
    const res = await apiGet<ActivityStatus>('/activity_status');
    if (res.ok && res.data) {
      setStatus(normalizeActivityStatus(res.data));
      setPipelineError(null);
    } else {
      setStatus(null);
      setPipelineError(res.error || 'Failed to load pipeline status');
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    const id = window.setInterval(() => void loadStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [loadStatus]);

  const runQueueAction = useCallback(
    async (itemId: number, action: QueueCardAction) => {
      setQueueActionId(itemId);
      try {
        const path =
          action === 'prioritize'
            ? '/pipeline_queue/prioritize'
            : action === 'deprioritize'
              ? '/pipeline_queue/deprioritize'
              : action === 'dequeue'
                ? '/pipeline_queue/dequeue'
                : '/pipeline_queue/retry_failed';
        const res = await apiPost(path, { item_id: itemId });
        if (!res.ok) {
          const fallback =
            action === 'dequeue'
              ? 'Could not dequeue item'
              : action === 'retry_failed'
                ? 'Could not retry failed item'
                : 'Could not reorder queue item';
          notify(res.error || fallback, 'error');
          return;
        }
        const message =
          action === 'prioritize'
            ? 'Moved up in queue'
            : action === 'deprioritize'
              ? 'Moved down in queue'
              : action === 'dequeue'
                ? 'Removed from queue'
                : 'Retry queued';
        notify(message, 'success');
        await loadStatus();
      } finally {
        setQueueActionId(null);
      }
    },
    [loadStatus],
  );

  const limitersByOwner = useMemo(() => {
    const map: Record<string, LimiterSnapshot[]> = {};
    for (const lim of status?.downloader.rate_limits ?? []) {
      if (!map[lim.owner]) map[lim.owner] = [];
      map[lim.owner].push(lim);
    }
    for (const rows of Object.values(map)) {
      rows.sort((a, b) => a.label.localeCompare(b.label));
    }
    return map;
  }, [status?.downloader.rate_limits]);

  const enabledDownloaderServices = useMemo(
    () => status?.downloader.services ?? [],
    [status?.downloader.services],
  );

  const enabledScraperKeys = useMemo(
    () => sortOwnerKeys(status?.downloader.scraper_services ?? []),
    [status?.downloader.scraper_services],
  );

  const [clockTick, setClockTick] = useState(0);

  useEffect(() => {
    const needsLiveClock =
      (status?.pipeline.queue?.next_ready_in_seconds != null &&
        (status.pipeline.queue.deferred ?? 0) > 0) ||
      (status?.downloader.paused && Boolean(status.downloader.pause_until));
    if (!needsLiveClock) return undefined;
    const id = window.setInterval(() => setClockTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [
    status?.pipeline.queue?.next_ready_in_seconds,
    status?.pipeline.queue?.deferred,
    status?.downloader.paused,
    status?.downloader.pause_until,
  ]);

  const displayColumnCounts = useMemo(
    () =>
      status?.pipeline.queue.columns
        ? aggregateDisplayColumnCounts(status.pipeline.queue.columns)
        : null,
    [status?.pipeline.queue.columns],
  );

  const itemsByColumn = useMemo(() => {
    const grouped = Object.fromEntries(
      ACTIVITY_DISPLAY_COLUMNS.map((col) => [col, [] as PipelineItem[]]),
    ) as Record<ActivityDisplayColumnId, PipelineItem[]>;

    for (const item of status?.pipeline.items ?? []) {
      const col = mapBackendKanbanColumn(item.kanban_column);
      grouped[col].push(item);
    }

    for (const col of ACTIVITY_DISPLAY_COLUMNS) {
      grouped[col].sort((a, b) => a.sort_rank - b.sort_rank);
    }

    return grouped;
  }, [status?.pipeline.items]);

  const pipelineBanner = useMemo(() => {
    if (!status?.downloader.initialized) return null;
    void clockTick;
    if (status.downloader.paused) {
      return {
        modifier: 'paused',
        title: 'Downloader paused',
        detail: `Resumes in ${formatCountdown(status.downloader.pause_until)}`,
      };
    }
    return {
      modifier: 'ok',
      title: 'Downloader active',
      detail: `Job spacing: ${(status.downloader.min_job_interval_seconds ?? 0).toFixed(2)}s`,
    };
  }, [status?.downloader, clockTick]);

  const scrapedNotInQueue = status?.pipeline.queue.scraped_not_in_queue ?? 0;

  return (
    <ViewLayout className="view-dashboard view-dashboard-activity" view="dashboard-activity">
      <ViewHeader title="Activity" subtitle="Pipeline and queue status" />

      {pipelineError && (
        <Panel>
          <p className="downloader-status__error">{pipelineError}</p>
        </Panel>
      )}

      <Panel className="panel--activity-pipeline">
        {pipelineBanner && (
          <div
            className={`downloader-status-banner downloader-status-banner--${pipelineBanner.modifier}`}
          >
            <strong>{pipelineBanner.title}</strong>
            <span className="downloader-status-banner__detail">{pipelineBanner.detail}</span>
          </div>
        )}

        <section className="activity-kpi-strip kpi-grid" aria-label="Pipeline and services">
          <article className="kpi-card">
            <KpiCardHeading label="Indexed (DB)" description={KPI_TIPS.indexedDb} />
            <p className="kpi-value">{status?.library_backlog.indexed ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading label="Scraped (DB)" description={KPI_TIPS.scrapedDb} />
            <p className="kpi-value">{status?.library_backlog.scraped ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading label="Deferred" description={KPI_TIPS.deferred} />
            <p className="kpi-value">{status?.pipeline.queue.deferred ?? '—'}</p>
            {status?.pipeline.queue.next_ready_in_seconds != null &&
              status.pipeline.queue.deferred > 0 && (
                <p className="kpi-sub">
                  Next due{' '}
                  <LiveServerCountdown
                    initialSeconds={status.pipeline.queue.next_ready_in_seconds}
                  />
                </p>
              )}
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Live queue"
              description="Items visible in the pipeline board (may be truncated)."
            />
            <p className="kpi-value">{status?.pipeline.queue.total_items ?? '—'}</p>
          </article>
          {enabledDownloaderServices.map((svc) => (
            <ServiceRateLimitCard
              key={svc.key}
              ownerKey={svc.key}
              limiters={limitersByOwner[svc.key] ?? []}
              statusLabel={svc.available ? 'Available' : 'Cooldown'}
              statusClassName={
                svc.available ? 'service-row__status--up' : 'service-row__status--down'
              }
            />
          ))}
          {enabledScraperKeys.map((key) => (
            <ServiceRateLimitCard
              key={key}
              ownerKey={key}
              limiters={limitersByOwner[key] ?? []}
              statusLabel="Active"
              statusClassName="service-row__status--up"
            />
          ))}
        </section>

        <div className="activity-kanban-wrap">
          <div className="activity-kanban" role="list" aria-label="Pipeline board">
            {ACTIVITY_DISPLAY_COLUMNS.map((col) => {
              const label = DISPLAY_COLUMN_LABELS[col];
              const cards = itemsByColumn[col];
              const count = displayColumnCounts?.[col] ?? cards.length;
              return (
                <section
                  key={col}
                  className="activity-kanban__column"
                  role="listitem"
                  aria-label={label.tooltip}
                >
                  <header className="activity-kanban__header" title={label.tooltip}>
                    <span>{label.short}</span>
                    <span className="activity-kanban__count">{count}</span>
                  </header>
                  <div className="activity-kanban__body">
                    {col === 'prepare' && scrapedNotInQueue > 0 && (
                      <p
                        className="activity-kanban__scraped-backlog"
                        title="Library items (Indexed, Scraped, Downloaded, etc.) not in the live pipeline yet. Startup should re-queue them into Prepare/Download/Library — not the Done column. If this stays high, use Retry Active Library on Overview."
                      >
                        <span className="activity-kanban__scraped-backlog-value">
                          +{scrapedNotInQueue.toLocaleString()}
                        </span>
                        <span className="activity-kanban__scraped-backlog-label">
                          not in live queue
                        </span>
                      </p>
                    )}
                    {cards.length === 0 &&
                    !(col === 'prepare' && scrapedNotInQueue > 0) ? (
                      <p className="muted activity-kanban__empty">—</p>
                    ) : (
                      cards.map((item) => (
                        <KanbanCard
                          key={
                            item.id != null
                              ? `${col}-${item.id}`
                              : `${col}-${item.content_title}-${item.sort_rank}`
                          }
                          item={item}
                          queueActionId={queueActionId}
                          onQueueAction={runQueueAction}
                        />
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </Panel>
    </ViewLayout>
  );
}

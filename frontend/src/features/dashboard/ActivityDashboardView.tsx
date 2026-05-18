import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { KpiCardHeading } from '../../shared/ui/KpiInfoTip';
import { apiGet } from '../../shared/api/api';
import {
  formatBytes as formatBytesUtil,
  formatEpisodeDisplayTitle,
  formatRelativeSeconds,
  secondsSinceApiDate,
} from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import { humanizeServiceKey } from './serviceSetupMessages';
import { useRateLimits } from '../../shared/rateLimits/useRateLimits';
import { RateLimitsPanel } from '../../shared/rateLimits/RateLimitsPanel';
import type { LimiterSnapshot } from '../../shared/rateLimits/types';

const STATUS_POLL_MS = 3000;
const USER_INFO_POLL_MS = 60_000;

const DOWNLOADER_KEYS = ['realdebrid', 'alldebrid', 'debridlink', 'torbox'] as const;

const DOWNLOADER_KPI_TIPS = {
  scrapedQueued:
    'Items in the Scraped state sitting in the event queue, ready for the downloader to pick up when a debrid slot is free.',
  deferred:
    'Queued jobs whose run time is still in the future—often waiting on downloader cooldown, rate limits, or scheduled spacing between runs.',
  scrapedDb:
    'Total library items (movies and episodes) currently in the Scraped state in the database—scraped and waiting to download.',
  inFlight:
    'Items the downloader service is actively working on right now (add to debrid, poll status, etc.).',
} as const;

function getDownloaderExpiryWarning(service: {
  premium_status?: string;
  premium_days_left?: number | null;
}): { text: string; modifier: 'expired' | 'soon' } | null {
  if (service.premium_status === 'free') {
    return { text: 'Premium expired', modifier: 'expired' };
  }
  const days = service.premium_days_left;
  if (days == null || days >= 30) return null;
  const text =
    days <= 0 ? 'Subscription expired' : `Expires in ${days} day${days === 1 ? '' : 's'}`;
  return { text, modifier: 'soon' };
}

function summarizeRateLimits(limiters: LimiterSnapshot[]) {
  let openBreakers = 0;
  let stressed = 0;
  for (const l of limiters) {
    if (l.breaker_state === 'OPEN' || l.breaker_state === 'HALF_OPEN') {
      openBreakers += 1;
    }
    if (
      l.utilization_pct >= l.warn_at_pct ||
      (l.priority === 'scarce' && l.next_token_in_seconds > 30)
    ) {
      stressed += 1;
    }
  }
  return { total: limiters.length, openBreakers, stressed };
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
    deferred: number;
    downloader_emitted: number;
    next_ready_at: string | null;
    scraped_in_library?: number;
  };
  services: ServiceStatus[];
  in_flight_items: InFlightItem[];
  queued_items: QueuedItem[];
  last_job: LastJob | null;
};

type UserInfoRow = {
  service: string;
  premium_status?: string;
  premium_days_left?: number | null;
  username?: string | null;
  total_downloaded_bytes?: number | null;
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

function inFlightTypeClass(type: string): string {
  if (type === 'movie') return 'pill--movie';
  if (type === 'episode' || type === 'season' || type === 'show') return 'pill--tv';
  return '';
}

function queueWaitLabel(item: QueuedItem): string {
  if (item.deferred) {
    return `Starts ${formatRelativeSeconds(item.wait_seconds, 'future')}`;
  }
  return `Waiting ${formatRelativeSeconds(item.wait_seconds, 'past')}`;
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
  const target = new Date(iso).getTime();
  if (!Number.isFinite(target)) return '—';
  const sec = Math.max(0, Math.round((target - Date.now()) / 1000));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

function normalizeDownloaderStatus(raw: DownloaderStatus | null | undefined): DownloaderStatus | null {
  if (!raw || typeof raw !== 'object') return null;

  const queue = raw.queue ?? {
    scraped_queued: 0,
    deferred: 0,
    downloader_emitted: 0,
    next_ready_at: null,
  };

  return {
    paused: Boolean(raw.paused),
    pause_until: raw.pause_until ?? null,
    min_job_interval_seconds: Number(raw.min_job_interval_seconds) || 0,
    queue: {
      scraped_queued: Number(queue.scraped_queued) || 0,
      deferred: Number(queue.deferred) || 0,
      downloader_emitted: Number(queue.downloader_emitted) || 0,
      next_ready_at: queue.next_ready_at ?? null,
      scraped_in_library: Number(queue.scraped_in_library) || 0,
    },
    services: Array.isArray(raw.services) ? raw.services : [],
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
    last_job: raw.last_job ?? null,
  };
}

export default function ActivityDashboardView(_props: { route: AppRoute }) {
  const { limiters, error: rateLimitError } = useRateLimits();
  const [status, setStatus] = useState<DownloaderStatus | null>(null);
  const [userByService, setUserByService] = useState<Record<string, UserInfoRow>>({});
  const [scrapedDbCount, setScrapedDbCount] = useState<number | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const rateSummary = useMemo(() => summarizeRateLimits(limiters), [limiters]);

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

  const loadUserInfo = useCallback(async () => {
    const res = await apiGet<{ services: UserInfoRow[] }>('/downloader_user_info');
    if (!res.ok || !res.data?.services) return;

    const map: Record<string, UserInfoRow> = {};
    for (const row of res.data.services) {
      if (row.service) map[row.service] = row;
    }
    setUserByService(map);
  }, []);

  useEffect(() => {
    void loadStatus();
    const id = window.setInterval(() => void loadStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [loadStatus]);

  useEffect(() => {
    void loadUserInfo();
    const id = window.setInterval(() => void loadUserInfo(), USER_INFO_POLL_MS);
    return () => window.clearInterval(id);
  }, [loadUserInfo]);

  const pipelineBanner = useMemo(() => {
    if (!status) return null;
    if (status.paused) {
      return {
        modifier: 'paused',
        title: 'Downloader paused',
        detail: `All providers cooling down — resumes in ${formatCountdown(status.pause_until)}`,
      };
    }
    const anyOpen = limiters.some(
      (l) => l.breaker_state === 'OPEN' || l.breaker_state === 'HALF_OPEN',
    );
    if (anyOpen) {
      return {
        modifier: 'warning',
        title: 'Circuit breaker open',
        detail: 'Some API calls are failing fast; jobs may defer until recovery.',
      };
    }
    return {
      modifier: 'ok',
      title: 'Downloader active',
      detail: `Job spacing: ${(status.min_job_interval_seconds ?? 0).toFixed(2)}s between runs`,
    };
  }, [status, limiters]);

  const loadError = rateLimitError || pipelineError;

  return (
    <ViewLayout className="view-dashboard view-dashboard-activity" view="dashboard-activity">
      <ViewHeader
        title="Activity"
        subtitle="Rate limits, circuit breakers, and download pipeline"
      />

      {loadError && (
        <Panel>
          <p className="downloader-status__error">{loadError}</p>
        </Panel>
      )}

      <section className="kpi-grid activity-rate-kpis">
        <article className="kpi-card">
          <KpiCardHeading
            label="Rate limiters"
            description="Registered token buckets and circuit breakers across downloaders, scrapers, and APIs."
          />
          <p className="kpi-value">{rateSummary.total || '—'}</p>
        </article>
        <article className="kpi-card">
          <KpiCardHeading
            label="Open breakers"
            description="Limits where the circuit breaker is open or half-open after repeated failures."
          />
          <p className="kpi-value">{rateSummary.openBreakers}</p>
        </article>
        <article className="kpi-card">
          <KpiCardHeading
            label="Stressed limits"
            description="Limits near capacity, scarce tokens, or elevated utilization."
          />
          <p className="kpi-value">{rateSummary.stressed}</p>
        </article>
        <article className="kpi-card">
          <KpiCardHeading
            label="In flight"
            description={DOWNLOADER_KPI_TIPS.inFlight}
          />
          <p className="kpi-value">{status?.in_flight_items?.length ?? '—'}</p>
        </article>
      </section>

      <Panel title="Rate limits">
        <p className="muted downloader-status__hint rate-limits-panel__scope">
          Limiters with token or circuit-breaker activity in the last 30 minutes.
        </p>
        <RateLimitsPanel limiters={limiters} />
      </Panel>

      <Panel title="Download pipeline">
        {pipelineBanner && status && (
          <div
            className={`downloader-status-banner downloader-status-banner--${pipelineBanner.modifier}`}
          >
            <strong>{pipelineBanner.title}</strong>
            <span>{pipelineBanner.detail}</span>
          </div>
        )}

        <div className="downloader-status-services">
          {DOWNLOADER_KEYS.map((key) => {
            const svc = status?.services.find((s) => s.key === key);
            const user = userByService[key];
            const enabled = svc != null;
            const expiry = user ? getDownloaderExpiryWarning(user) : null;

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

                {enabled && svc && (
                  <dl className="downloader-card__meta">
                    {user?.username && (
                      <>
                        <dt>Account</dt>
                        <dd>{user.username}</dd>
                      </>
                    )}
                    {user?.premium_status && (
                      <>
                        <dt>Premium</dt>
                        <dd>{user.premium_status}</dd>
                      </>
                    )}
                    {expiry && (
                      <>
                        <dt>Subscription</dt>
                        <dd className={`downloader-expiry--${expiry.modifier}`}>{expiry.text}</dd>
                      </>
                    )}
                    {user?.total_downloaded_bytes != null && (
                      <>
                        <dt>Downloaded</dt>
                        <dd>{formatBytesUtil(user.total_downloaded_bytes) || '—'}</dd>
                      </>
                    )}
                    {svc.cooldown_until && (
                      <>
                        <dt>Cooldown until</dt>
                        <dd>{new Date(svc.cooldown_until).toLocaleString()}</dd>
                      </>
                    )}
                  </dl>
                )}

                {!enabled && <p className="muted">Not initialized</p>}
              </article>
            );
          })}
        </div>

        <section className="kpi-grid activity-pipeline-kpis">
          <article className="kpi-card">
            <KpiCardHeading
              label="Scraped in queue"
              description={DOWNLOADER_KPI_TIPS.scrapedQueued}
            />
            <p className="kpi-value">{status?.queue?.scraped_queued ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Deferred jobs"
              description={DOWNLOADER_KPI_TIPS.deferred}
            />
            <p className="kpi-value">{status?.queue?.deferred ?? '—'}</p>
          </article>
          <article className="kpi-card">
            <KpiCardHeading
              label="Scraped in library (DB)"
              description={DOWNLOADER_KPI_TIPS.scrapedDb}
            />
            <p className="kpi-value">{scrapedDbCount ?? '—'}</p>
          </article>
        </section>

        {status?.queue?.next_ready_at && (
          <p className="muted downloader-status__hint">
            Next deferred job ready: {new Date(status.queue.next_ready_at).toLocaleString()}
          </p>
        )}

        {status?.last_job?.item && status.last_job.completed_at && (
          <div className="activity-pipeline-subpanel">
            <h3 className="activity-pipeline-subpanel__title">Last processed</h3>
            <div className="media-list__row downloader-last-job-row">
              <span
                className={`pill downloader-outcome--${status.last_job.outcome ?? 'unknown'}`}
              >
                {outcomeLabel(status.last_job.outcome)}
              </span>
              <a
                className="downloader-in-flight-row__title"
                href={`#/item/${status.last_job.item.id}`}
              >
                {inFlightDisplayTitle(status.last_job.item)}
              </a>
              <span className="downloader-in-flight-row__state muted">
                {(() => {
                  const age = secondsSinceApiDate(status.last_job.completed_at);
                  const label = age != null ? formatRelativeSeconds(age, 'past') : '—';
                  return label;
                })()}
                {status.last_job.service
                  ? ` · ${humanizeServiceKey(status.last_job.service)}`
                  : ''}
              </span>
            </div>
            {status.last_job.detail && (
              <p className="muted downloader-last-job-row__detail">{status.last_job.detail}</p>
            )}
          </div>
        )}

        {status && (status.queued_items?.length ?? 0) > 0 && (
          <div className="activity-pipeline-subpanel">
            <h3 className="activity-pipeline-subpanel__title">Queue</h3>
            <div className="downloader-in-flight-list">
              {status.queued_items.map((item) => (
                <div key={item.id} className="media-list__row downloader-in-flight-row">
                  <span className={`pill ${inFlightTypeClass(item.type)}`}>{item.type}</span>
                  <div className="downloader-queue-row__main">
                    <a className="downloader-in-flight-row__title" href={`#/item/${item.id}`}>
                      {inFlightDisplayTitle(item)}
                    </a>
                    {item.scraped_at && (
                      <span className="muted downloader-queue-row__sub">
                        Scraped{' '}
                        {formatRelativeSeconds(
                          secondsSinceApiDate(item.scraped_at) ?? 0,
                          'past',
                        )}
                      </span>
                    )}
                  </div>
                  <span className="downloader-in-flight-row__state muted">
                    {queueWaitLabel(item)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {status && (status.in_flight_items?.length ?? 0) > 0 && (
          <div className="activity-pipeline-subpanel">
            <h3 className="activity-pipeline-subpanel__title">In flight</h3>
            <div className="downloader-in-flight-list">
              {status.in_flight_items.map((item) => (
                <div key={item.id} className="media-list__row downloader-in-flight-row">
                  <span className={`pill ${inFlightTypeClass(item.type)}`}>{item.type}</span>
                  <a className="downloader-in-flight-row__title" href={`#/item/${item.id}`}>
                    {inFlightDisplayTitle(item)}
                  </a>
                  {item.state && (
                    <span className="downloader-in-flight-row__state muted">{item.state}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </ViewLayout>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiGet, type ApiResult } from '../../shared/api/api';
import { formatBytes as formatBytesUtil } from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import { humanizeServiceKey } from './serviceSetupMessages';

const POLL_MS = 3000;

const DOWNLOADER_KEYS = ['realdebrid', 'alldebrid', 'debridlink', 'torbox'] as const;

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

type BreakerStatus = {
  domain: string;
  state: string;
  failures: number;
};

type ServiceStatus = {
  key: string;
  available: boolean;
  cooldown_until: string | null;
  breaker: BreakerStatus | null;
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
  };
  services: ServiceStatus[];
  in_flight_item_ids: number[];
};

type UserInfoRow = {
  service: string;
  premium_status?: string;
  premium_days_left?: number | null;
  username?: string | null;
  total_downloaded_bytes?: number | null;
};

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
    },
    services: Array.isArray(raw.services) ? raw.services : [],
    in_flight_item_ids: Array.isArray(raw.in_flight_item_ids)
      ? raw.in_flight_item_ids
      : [],
  };
}

function breakerClass(state: string): string {
  const s = state.toUpperCase();
  if (s === 'OPEN') return 'downloader-status__breaker--open';
  if (s === 'HALF_OPEN') return 'downloader-status__breaker--half';
  return 'downloader-status__breaker--closed';
}

export default function DownloaderDashboardView(_props: { route: AppRoute }) {
  const [status, setStatus] = useState<DownloaderStatus | null>(null);
  const [userByService, setUserByService] = useState<Record<string, UserInfoRow>>({});
  const [scrapedDbCount, setScrapedDbCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [statusRes, userRes, statsRes] = await Promise.allSettled([
      apiGet<DownloaderStatus>('/downloader_status'),
      apiGet<{ services: UserInfoRow[] }>('/downloader_user_info'),
      apiGet<Record<string, unknown>>('/stats'),
    ]);

    if (statusRes.status === 'fulfilled') {
      const res = statusRes.value as ApiResult<DownloaderStatus>;
      if (res.ok && res.data) {
        setStatus(normalizeDownloaderStatus(res.data));
        setError(null);
      } else {
        setStatus(null);
        setError(res.error || 'Failed to load downloader status');
      }
    } else {
      const msg =
        statusRes.reason instanceof Error
          ? statusRes.reason.message
          : 'Failed to load downloader status';
      setStatus(null);
      setError(msg);
    }

    if (userRes.status === 'fulfilled') {
      const res = userRes.value as ApiResult<{ services: UserInfoRow[] }>;
      const map: Record<string, UserInfoRow> = {};
      if (res.ok && res.data?.services) {
        for (const row of res.data.services) {
          if (row.service) map[row.service] = row;
        }
      }
      setUserByService(map);
    }

    if (statsRes.status === 'fulfilled') {
      const res = statsRes.value as ApiResult<Record<string, unknown>>;
      if (res.ok && res.data) {
        const states = res.data.states as Record<string, unknown> | undefined;
        const scraped = states?.Scraped;
        const n = typeof scraped === 'number' ? scraped : Number(scraped ?? 0);
        setScrapedDbCount(Number.isFinite(n) ? n : null);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const banner = useMemo(() => {
    if (!status) return null;
    if (status.paused) {
      return {
        modifier: 'paused',
        title: 'Downloader paused',
        detail: `All providers cooling down — resumes in ${formatCountdown(status.pause_until)}`,
      };
    }
    const anyOpen = (status.services ?? []).some((s) => s.breaker?.state === 'OPEN');
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
  }, [status]);

  return (
    <ViewLayout className="view-dashboard view-dashboard-downloader" view="dashboard-downloader">
      <ViewHeader
        title="Downloader"
        subtitle="Live pipeline status, rate limits, and debrid health"
      />

      {error && (
        <Panel>
          <p className="downloader-status__error">{error}</p>
        </Panel>
      )}

      {banner && status && (
        <div
          className={`downloader-status-banner downloader-status-banner--${banner.modifier}`}
        >
          <strong>{banner.title}</strong>
          <span>{banner.detail}</span>
        </div>
      )}

      <section className="kpi-grid">
        <article className="kpi-card">
          <h3>Scraped in queue</h3>
          <p className="kpi-value">{status?.queue?.scraped_queued ?? '—'}</p>
        </article>
        <article className="kpi-card">
          <h3>Deferred jobs</h3>
          <p className="kpi-value">{status?.queue?.deferred ?? '—'}</p>
        </article>
        <article className="kpi-card">
          <h3>Scraped in library (DB)</h3>
          <p className="kpi-value">{scrapedDbCount ?? '—'}</p>
        </article>
        <article className="kpi-card">
          <h3>In flight</h3>
          <p className="kpi-value">{status?.in_flight_item_ids?.length ?? 0}</p>
        </article>
      </section>

      {status?.queue?.next_ready_at && (
        <p className="muted downloader-status__hint">
          Next deferred job ready: {new Date(status.queue.next_ready_at).toLocaleString()}
        </p>
      )}

      {status && (status.in_flight_item_ids?.length ?? 0) > 0 && (
        <Panel title="In flight">
          <ul className="downloader-status__in-flight">
            {status.in_flight_item_ids.map((id) => (
              <li key={id}>
                <a href={`#/item/${id}`}>Item {id}</a>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Debrid services">
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
                    {svc.breaker && (
                      <>
                        <dt>Circuit breaker</dt>
                        <dd>
                          <span className={breakerClass(svc.breaker.state)}>
                            {svc.breaker.state}
                          </span>
                          {svc.breaker.failures > 0 && (
                            <span className="muted"> ({svc.breaker.failures} failures)</span>
                          )}
                        </dd>
                      </>
                    )}
                  </dl>
                )}

                {!enabled && <p className="muted">Not initialized</p>}
              </article>
            );
          })}
        </div>
      </Panel>
    </ViewLayout>
  );
}

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiGet, apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import { formatBytes as formatBytesUtil, formatEpisodeDisplayTitle } from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import ActivityDashboardView from './ActivityDashboardView';
import RateLimitsDashboardView from './RateLimitsDashboardView';
import {
  CONSOLE_UPDATER_NOTICE,
  MOCK_VFS_NOTICE,
  humanizeServiceKey,
  parseServicesResponse,
  type ParsedServicesResponse,
} from './serviceSetupMessages';

const PIPELINE_ORDER = ['Requested', 'Indexed', 'Scraped', 'Downloaded', 'Symlinked', 'Completed'];
const OTHER_STATES_LEADING = ['Ongoing', 'PartiallyCompleted', 'Failed', 'Paused'];
const OTHER_STATES = ['Unknown', 'Unreleased', ...OTHER_STATES_LEADING];

/** Strip / orderedCounts left-to-right: Ongoing…Paused, then Unknown/Unreleased, then pipeline */
const STATE_ORDER = [...OTHER_STATES_LEADING, 'Unknown', 'Unreleased', ...PIPELINE_ORDER];

type StateDistScope = 'movies' | 'episodes';

/** Minimum fraction of strip width for zero-count segments when total > 0 (renormalized after). */
const STATE_SEGMENT_MIN_FRAC = 0.008;

function countsFromStatsDict(dict: Record<string, unknown> | undefined): Record<string, number> {
  const out: Record<string, number> = {};
  if (!dict || typeof dict !== 'object') return out;
  for (const key of STATE_ORDER) {
    const v = dict[key];
    const n = typeof v === 'number' ? v : Number(v ?? 0);
    out[key] = Number.isFinite(n) ? n : 0;
  }
  return out;
}

function orderedCounts(dict: Record<string, number>): number[] {
  return STATE_ORDER.map((name) => Number(dict[name] ?? 0));
}

/** Percents summing to ~100; equal slices when total is zero. */
function segmentPercents(counts: number[]): number[] {
  const n = counts.length;
  if (n === 0) return [];
  const total = counts.reduce((a, b) => a + b, 0);
  if (total === 0) return counts.map(() => 100 / n);
  const weights = counts.map((c) => (c === 0 ? STATE_SEGMENT_MIN_FRAC : c));
  const sum = weights.reduce((a, b) => a + b, 0);
  return weights.map((w) => (w / sum) * 100);
}

function scopeMediaTypes(scope: StateDistScope): string[] {
  return scope === 'movies' ? ['movie'] : ['episode'];
}

function libraryHashForScope(scope: StateDistScope, state: string): string {
  const q = `state=${encodeURIComponent(state)}`;
  return scope === 'movies' ? `#/movies?${q}` : `#/episodes?${q}`;
}

const SERVICE_CATEGORIES: Record<string, string> = {
  overseerr: 'Content',
  plexwatchlist: 'Content',
  listrr: 'Content',
  mdblist: 'Content',
  traktcontent: 'Content',
  trakt: 'Content',
  realdebrid: 'Downloaders',
  alldebrid: 'Downloaders',
  debridlink: 'Downloaders',
  torbox: 'Downloaders',
  prowlarr: 'Scrapers',
  jackett: 'Scrapers',
  aiostreams: 'Scrapers',
  comet: 'Scrapers',
  mediafusion: 'Scrapers',
  orionoid: 'Scrapers',
  rarbg: 'Scrapers',
  torrentio: 'Scrapers',
  zilean: 'Scrapers',
  indexer: 'Indexers',
  indexerservice: 'Indexers',
  updater: 'Updaters',
  plexupdater: 'Updaters',
  jellyfinupdater: 'Updaters',
  embyupdater: 'Updaters',
  consoleupdater: 'Updaters',
  console: 'Updaters',
  filesystem: 'Filesystem',
  filesystemservice: 'Filesystem',
  postprocessing: 'Post-processing',
  post_processing: 'Post-processing',
  subtitle: 'Post-processing',
  notificationservice: 'Notifications',
  notifications: 'Notifications',
  naming_service: 'Filesystem',
  library_profile_matcher: 'Library',
};

const CATEGORY_ORDER = [
  'Content',
  'Downloaders',
  'Scrapers',
  'Indexers',
  'Updaters',
  'Filesystem',
  'Post-processing',
  'Library',
  'Notifications',
  'Other',
];

const STATE_ITEMS_LIMIT = 25;
const YEAR_ITEMS_LIMIT = 25;

/** Min column width (px); row scrolls horizontally when `n * min + gaps` exceeds container. */
const RELEASE_BAR_MIN_COL_PX = 44;
/** Gap between bars in px (~0.4rem); keep in sync with `.release-bars` `gap`. */
const RELEASE_BARS_GAP_PX = 7;

/**
 * Years from earliest library release through max(current calendar year, newest in data).
 * Missing years get count 0 (empty bars); order ascending so latest year is on the right.
 */
function buildReleaseYearSeries(mediaYearReleases: unknown): { year: number; count: number }[] {
  const currentYear = new Date().getFullYear();
  const byYear = new Map<number, number>();
  const rows = Array.isArray(mediaYearReleases) ? mediaYearReleases : [];
  for (const raw of rows) {
    if (raw == null || typeof raw !== 'object') continue;
    const entry = raw as { year?: unknown; count?: unknown };
    if (entry.year === undefined || entry.year === null) continue;
    const y =
      typeof entry.year === 'number' && Number.isFinite(entry.year)
        ? Math.trunc(entry.year)
        : parseInt(String(entry.year), 10);
    if (!Number.isFinite(y)) continue;
    const cRaw = entry.count;
    const c =
      typeof cRaw === 'number' && Number.isFinite(cRaw)
        ? cRaw
        : Number(cRaw ?? 0);
    const cn =
      Number.isFinite(c) ? Math.max(0, Math.round(c as number)) : 0;
    byYear.set(y, (byYear.get(y) ?? 0) + cn);
  }

  let minYear: number;
  let maxYear: number;
  const keys = [...byYear.keys()];
  if (!keys.length) {
    minYear = currentYear;
    maxYear = currentYear;
  } else {
    minYear = Math.min(...keys);
    maxYear = Math.max(currentYear, Math.max(...keys));
    if (maxYear < minYear) maxYear = minYear;
  }

  const out: { year: number; count: number }[] = [];
  for (let year = minYear; year <= maxYear; year += 1) {
    out.push({ year, count: byYear.get(year) ?? 0 });
  }
  return out;
}

/** Fixed order; aligned with backend downloader keys and GET `/services` map. */
const DASHBOARD_DOWNLOADER_KEYS = ['realdebrid', 'alldebrid', 'debridlink', 'torbox'] as const;

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

type StateListItem = {
  id: number;
  title?: string;
  parent_title?: string;
  type?: string;
  year?: number | null;
  season_number?: number | null;
  episode_number?: number | null;
};

function formatBytesDash(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '—';
  return formatBytesUtil(bytes) || '—';
}

function displayTitle(item: StateListItem): string {
  if (item.type === 'episode') return formatEpisodeDisplayTitle(item as any);
  return item.title ?? `Item ${item.id}`;
}

export default function DashboardView({ route }: { route: AppRoute }) {
  const name = route.name;

  if (name === 'dashboard') {
    return <DashboardOverview route={route} />;
  }
  if (name === 'dashboard-services') {
    return <DashboardServices route={route} />;
  }
  if (name === 'dashboard-states') {
    return <DashboardStates route={route} />;
  }
  if (name === 'dashboard-releases') {
    return <DashboardReleases route={route} />;
  }
  if (name === 'dashboard-rate-limits') {
    return <RateLimitsDashboardView route={route} />;
  }
  if (name === 'dashboard-activity' || name === 'dashboard-downloader') {
    return <ActivityDashboardView route={route} />;
  }

  return (
    <ViewLayout className="view-dashboard" view="dashboard">
      <p className="muted">Unknown dashboard view.</p>
    </ViewLayout>
  );
}

function DashboardOverview({ route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [downloader, setDownloader] = useState<Record<string, unknown>>({});
  const [servicesInfo, setServicesInfo] = useState<ParsedServicesResponse>({
    services: {},
    mockVfs: false,
    consoleUpdater: false,
  });
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [statsRes, downloaderRes, servicesRes] = await Promise.allSettled([
      apiGet('/stats'),
      apiGet('/downloader_user_info'),
      apiGet('/services'),
    ]);

    if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
      setStats(statsRes.value.data || {});
    } else {
      setStats({});
    }

    if (downloaderRes.status === 'fulfilled' && downloaderRes.value.ok) {
      setDownloader(downloaderRes.value.data || {});
    } else {
      setDownloader({});
    }

    if (servicesRes.status === 'fulfilled' && servicesRes.value.ok) {
      setServicesInfo(parseServicesResponse(servicesRes.value.data));
    } else {
      setServicesInfo({ services: {}, mockVfs: false, consoleUpdater: false });
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRetry = async () => {
    const response = await apiPost('/items/retry_library');
    if (!response.ok) {
      notify(response.error || 'Retry request failed', 'error');
      return;
    }
    notify((response.data as any)?.message || 'Retry request submitted', 'success');
    await fetchData();
  };

  if (loading) return <ViewLayout className="view-dashboard view-dashboard--overview" view="dashboard"><p className="muted">Loading…</p></ViewLayout>;

  const total = Number(stats?.total_items || 0);
  const statesObj = stats?.states as Record<string, number> | undefined;
  const completed = Number(statesObj?.Completed ?? 0);
  const completionRate = total ? ((completed / total) * 100).toFixed(1) : '0.0';

  const showFallbackWarnings = servicesInfo.mockVfs || servicesInfo.consoleUpdater;

  const kpis = [
    { title: 'Total Items', value: total.toLocaleString(), sub: 'All media entries' },
    { title: 'Movies', value: Number(stats?.total_movies || 0).toLocaleString(), sub: 'Movie records' },
    { title: 'Shows', value: Number(stats?.total_shows || 0).toLocaleString(), sub: 'TV show records' },
    { title: 'Completion', value: `${completionRate}%`, sub: `Completed ${completed.toLocaleString()} / ${total.toLocaleString()}` },
    { title: 'Incomplete', value: Number(stats?.incomplete_items || 0).toLocaleString(), sub: 'Needs processing' },
    { title: 'Symlinks', value: Number(stats?.total_symlinks || 0).toLocaleString(), sub: 'Mounted output links' },
  ];

  const userInfos = ((downloader as { services?: unknown[] }).services || []) as Record<string, unknown>[];
  const userByService = Object.fromEntries(
    userInfos.filter((u) => u && typeof u === 'object' && typeof (u as { service?: unknown }).service === 'string').map((u) => [(u as { service: string }).service, u]),
  ) as Record<string, Record<string, unknown>>;

  const downloaderRows = DASHBOARD_DOWNLOADER_KEYS.map((key) => ({
    key,
    user: userByService[key],
    enabled: Boolean(servicesInfo.services[key]),
  }));

  const activity = (stats?.activity || {}) as Record<string, number>;
  const activityEntries = Object.entries(activity)
    .map(([date, count]) => ({ date, count: Number(count || 0), timestamp: new Date(date).getTime() }))
    .filter((e) => Number.isFinite(e.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp)
    .slice(-30);
  const maxCount = Math.max(...activityEntries.map((e) => e.count), 1);
  const width = 620;
  const height = 220;
  const padding = 24;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  return (
    <ViewLayout className="view-dashboard view-dashboard--overview" view="dashboard">
      <ViewHeader
        title="Dashboard — Overview"
        subtitle="Key metrics, downloaders, and request activity."
        actions={
          <button type="button" className="btn btn--warning" onClick={handleRetry}>
            Retry Active Library
          </button>
        }
      />
      {showFallbackWarnings ? (
        <Panel className="dashboard-runtime-warnings">
          <div className="section-head">
            <h2>Fallback integrations</h2>
            <a href="#/dashboard-services" className="dashboard-runtime-warnings__link">
              Services
            </a>
          </div>
          <p className="dashboard-runtime-warnings__lead muted">
            Riven is running with placeholder behavior for the items below. This is expected in some dev setups; add
            real integrations in Settings when you need full behavior.
          </p>
          <ul className="runtime-warning-list">
            {servicesInfo.mockVfs ? (
              <li key="mock-vfs" className="runtime-warning-list__item">
                <strong>Mock VFS</strong>
                <span className="runtime-warning-list__body">{MOCK_VFS_NOTICE}</span>
              </li>
            ) : null}
            {servicesInfo.consoleUpdater ? (
              <li key="console-updater" className="runtime-warning-list__item">
                <strong>Console updater</strong>
                <span className="runtime-warning-list__body">{CONSOLE_UPDATER_NOTICE}</span>
              </li>
            ) : null}
          </ul>
        </Panel>
      ) : null}
      <section className="kpi-grid">
        {kpis.map((k) => (
          <article key={k.title} className="kpi-card">
            <h3>{k.title}</h3>
            <p className="kpi-value">{k.value}</p>
            <p className="kpi-sub">{k.sub}</p>
          </article>
        ))}
      </section>
      <div className="split-grid">
        <Panel>
          <div className="section-head">
            <h2>Downloader Accounts</h2>
          </div>
          {downloaderRows.map(({ key, user: service, enabled }) => {
              const expiryWarning = service ? getDownloaderExpiryWarning(service as { premium_status?: string; premium_days_left?: number | null }) : null;
              const email =
                service?.email != null ? String(service.email).replace(/(.{3}).*@/, '$1***@') : null;
              const displayName = service
                ? String(service.username || email || 'Unknown account')
                : '—';
              const expires =
                service?.premium_expires_at != null
                  ? new Date(String(service.premium_expires_at)).toLocaleDateString()
                  : '—';
              const daysLeft =
                service?.premium_days_left != null ? `${service.premium_days_left} days` : '—';
              return (
                <div key={key} className="downloader-card">
                  <div className="downloader-card__head">
                    <strong>{humanizeServiceKey(key)}</strong>
                    <span
                      className={`service-row__status ${enabled ? 'service-row__status--up' : 'service-row__status--down'}`}
                    >
                      {enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {expiryWarning ? (
                      <span className={`downloader-warning downloader-warning--${expiryWarning.modifier}`}>
                        {expiryWarning.text}
                      </span>
                    ) : null}
                    {service?.premium_status != null ? (
                      <span
                        className={`service-row__status ${service.premium_status === 'premium' ? 'service-row__status--up' : 'service-row__status--down'}`}
                      >
                        {String(service.premium_status)}
                      </span>
                    ) : null}
                  </div>
                  <dl className="downloader-card__meta">
                    <dt>Account</dt>
                    <dd>{displayName}</dd>
                    <dt>Expires</dt>
                    <dd>{expires}</dd>
                    <dt>Days left</dt>
                    <dd>{daysLeft}</dd>
                    {service?.points != null && (
                      <>
                        <dt>Points</dt>
                        <dd>{String(service.points)}</dd>
                      </>
                    )}
                    {service?.total_downloaded_bytes != null && (
                      <>
                        <dt>Downloaded</dt>
                        <dd>{formatBytesDash(service.total_downloaded_bytes as number)}</dd>
                      </>
                    )}
                    {service?.cooldown_until != null && (
                      <>
                        <dt>Cooldown until</dt>
                        <dd>{new Date(String(service.cooldown_until)).toLocaleString()}</dd>
                      </>
                    )}
                  </dl>
                </div>
              );
            })}
        </Panel>
        <Panel>
          <div className="section-head">
            <h2>Request Activity (30d)</h2>
          </div>
          {!activityEntries.length ? (
            <p className="muted">No request activity found.</p>
          ) : (
            <div className="chart-wrap">
              <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Activity line chart">
                <defs>
                  <linearGradient id="activityFillGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="rgba(74,133,255,0.55)" />
                    <stop offset="100%" stopColor="rgba(74,133,255,0.05)" />
                  </linearGradient>
                </defs>
                <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} className="chart-axis" />
                <line x1={padding} y1={padding} x2={padding} y2={height - padding} className="chart-axis" />
                <path
                  d={activityEntries
                    .map((e, i) => {
                      const x = padding + (activityEntries.length === 1 ? chartWidth / 2 : (i / (activityEntries.length - 1)) * chartWidth);
                      const y = padding + chartHeight - (e.count / maxCount) * chartHeight;
                      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
                    })
                    .join(' ') + ` L ${(padding + chartWidth).toFixed(2)} ${(height - padding).toFixed(2)} L ${padding.toFixed(2)} ${(height - padding).toFixed(2)} Z`}
                  fill="url(#activityFillGradient)"
                />
                <path
                  d={activityEntries
                    .map((e, i) => {
                      const x = padding + (activityEntries.length === 1 ? chartWidth / 2 : (i / (activityEntries.length - 1)) * chartWidth);
                      const y = padding + chartHeight - (e.count / maxCount) * chartHeight;
                      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
                    })
                    .join(' ')}
                  className="chart-line"
                />
                {activityEntries.map((e, i) => {
                  const x = padding + (activityEntries.length === 1 ? chartWidth / 2 : (i / (activityEntries.length - 1)) * chartWidth);
                  const y = padding + chartHeight - (e.count / maxCount) * chartHeight;
                  return <circle key={e.date} cx={x.toFixed(2)} cy={y.toFixed(2)} r={3} className="chart-point"><title>{e.date}: {e.count}</title></circle>;
                })}
              </svg>
              <div className="chart-meta">
                <span>{activityEntries[0]?.date}</span>
                <strong>Peak: {maxCount}</strong>
                <span>{activityEntries[activityEntries.length - 1]?.date}</span>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </ViewLayout>
  );
}

function DashboardServices({ route }: { route: AppRoute }) {
  const [servicesInfo, setServicesInfo] = useState<ParsedServicesResponse>({
    services: {},
    mockVfs: false,
    consoleUpdater: false,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet('/services').then((res) => {
      setServicesInfo(parseServicesResponse(res.data));
      setLoading(false);
    });
  }, []);

  const services = servicesInfo.services;
  const showFallbackWarnings = servicesInfo.mockVfs || servicesInfo.consoleUpdater;

  const byCategory = new Map<string, [string, boolean][]>();
  for (const [name, status] of Object.entries(services)) {
    const key = name.toLowerCase().replace(/\s+/g, '');
    const category = SERVICE_CATEGORIES[key] ?? 'Other';
    if (!byCategory.has(category)) byCategory.set(category, []);
    byCategory.get(category)!.push([name, Boolean(status)]);
  }
  for (const entries of byCategory.values()) {
    entries.sort(([a], [b]) => a.localeCompare(b));
  }
  const orderedCategories = CATEGORY_ORDER.filter((c) => byCategory.has(c));

  return (
    <ViewLayout className="view-dashboard view-dashboard--services" view="dashboard-services">
      <ViewHeader title="Dashboard — Services" subtitle="Backend service status by category." />
      {loading ? (
        <p className="muted">Loading…</p>
      ) : orderedCategories.length === 0 ? (
        <p className="muted">No services payload.</p>
      ) : (
        <>
          {showFallbackWarnings ? (
            <Panel className="dashboard-runtime-warnings dashboard-runtime-warnings--inline">
              <h3 className="runtime-warning-inline__title">Fallback mode</h3>
              <ul className="runtime-warning-list">
                {servicesInfo.mockVfs ? (
                  <li key="mock-vfs" className="runtime-warning-list__item">
                    <strong>Mock VFS</strong>
                    <span className="runtime-warning-list__body">{MOCK_VFS_NOTICE}</span>
                  </li>
                ) : null}
                {servicesInfo.consoleUpdater ? (
                  <li key="console-updater" className="runtime-warning-list__item">
                    <strong>Console updater</strong>
                    <span className="runtime-warning-list__body">{CONSOLE_UPDATER_NOTICE}</span>
                  </li>
                ) : null}
              </ul>
            </Panel>
          ) : null}
          <div className="services-sections">
            {orderedCategories.map((category) => (
              <section key={category} className="services-section">
                <h3 className="services-section__title">{category}</h3>
                <div className="services-items">
                  {(byCategory.get(category)!).map(([name, isUp]) => (
                    <div
                      key={`${category}-${name}`}
                      className={`services-item ${isUp ? '' : 'services-item--down'}`}
                    >
                      <div className="services-item__row">
                        <span className="services-item__name" title={name}>
                          {humanizeServiceKey(name)}
                        </span>
                        <span
                          className={`service-row__status ${isUp ? 'service-row__status--up' : 'service-row__status--down'}`}
                        >
                          {isUp ? 'UP' : 'DOWN'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </ViewLayout>
  );
}

function StateDistributionSection({
  title,
  scope,
  countsDict,
  expanded,
  compactStrip,
  onToggleExpand,
  onCategoryPick,
}: {
  title: string;
  scope: StateDistScope;
  countsDict: Record<string, number>;
  expanded: boolean;
  compactStrip: boolean;
  onToggleExpand: () => void;
  onCategoryPick: (stateName: string) => void;
}) {
  const counts = orderedCounts(countsDict);
  const percents = segmentPercents(counts);
  const maxCount = Math.max(...counts, 1);

  const rowClass = [
    'state-dist-row',
    compactStrip ? 'state-dist-row--compact-strip' : '',
    expanded ? 'state-dist-row--expanded' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section className={rowClass}>
      <div className="state-dist-row__head">
        <button
          type="button"
          className="state-dist-row__toggle"
          aria-expanded={expanded}
          aria-controls={`state-dist-breakdown-${scope}`}
          id={`state-dist-heading-${scope}`}
          onClick={onToggleExpand}
        >
          <span className="state-dist-row__title">{title}</span>
          <span className="state-dist-row__chevron" aria-hidden>
            {expanded ? '▼' : '▶'}
          </span>
        </button>
      </div>
      <div className="state-dist__track-wrap">
        <div className="state-dist__track" role="group" aria-labelledby={`state-dist-heading-${scope}`}>
          {STATE_ORDER.map((name, i) => (
            <button
              key={name}
              type="button"
              className="state-dist__segment"
              style={{
                flexGrow: percents[i],
                flexBasis: 0,
                flexShrink: 1,
                minWidth: counts[i] === 0 ? 6 : 3,
              }}
              data-state={name}
              title={`${name}: ${counts[i].toLocaleString()}`}
              aria-label={`${name}: ${counts[i].toLocaleString()} items`}
              onClick={(e) => {
                e.stopPropagation();
                onCategoryPick(name);
              }}
            />
          ))}
        </div>
      </div>

      {expanded ? (
        <div
          className="state-dist-breakdown"
          id={`state-dist-breakdown-${scope}`}
          role="region"
          aria-labelledby={`state-dist-heading-${scope}`}
        >
          <div className="state-dist-breakdown__group">
            {PIPELINE_ORDER.map((name) => {
              const idx = STATE_ORDER.indexOf(name);
              const c = counts[idx];
              const pct =
                maxCount && c > 0 ? Math.max((c / maxCount) * 100, 6) : c === 0 ? 2 : 0;
              return (
                <button
                  key={name}
                  type="button"
                  className="state-dist-breakdown-row state-dist-breakdown-row--pipeline"
                  data-state={name}
                  onClick={() => onCategoryPick(name)}
                >
                  <span className="state-dist-breakdown-row__label">{name}</span>
                  <span className="state-dist-breakdown-row__count">{c.toLocaleString()}</span>
                  <span className="state-dist-breakdown-row__track">
                    <span
                      className="state-dist-breakdown-row__fill"
                      style={{ width: `${pct}%` }}
                      data-state={name}
                    />
                  </span>
                </button>
              );
            })}
          </div>
          <div className="state-dist-breakdown__group state-dist-breakdown__group--other">
            {OTHER_STATES.map((name) => {
              const idx = STATE_ORDER.indexOf(name);
              const c = counts[idx];
              const pct =
                maxCount && c > 0 ? Math.max((c / maxCount) * 100, 6) : c === 0 ? 2 : 0;
              return (
                <button
                  key={name}
                  type="button"
                  className="state-dist-breakdown-row state-dist-breakdown-row--other"
                  data-state={name}
                  onClick={() => onCategoryPick(name)}
                >
                  <span className="state-dist-breakdown-row__label">{name}</span>
                  <span className="state-dist-breakdown-row__count">{c.toLocaleString()}</span>
                  <span className="state-dist-breakdown-row__track">
                    <span
                      className="state-dist-breakdown-row__fill"
                      style={{ width: `${pct}%` }}
                      data-state={name}
                    />
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DashboardStates({ route: _route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [expanded, setExpanded] = useState<StateDistScope | null>(null);
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [selectedScope, setSelectedScope] = useState<StateDistScope | null>(null);
  const [stateItems, setStateItems] = useState<StateListItem[]>([]);
  const [stateTotal, setStateTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [retryingIds, setRetryingIds] = useState<Set<string | number>>(new Set());
  const [retryingAll, setRetryingAll] = useState(false);

  useEffect(() => {
    apiGet('/stats').then((res) => {
      setStats(res.data || {});
      setLoading(false);
    });
  }, []);

  const handleCategoryClick = useCallback(async (scope: StateDistScope, state: string) => {
    setSelectedScope(scope);
    setSelectedState(state);
    setItemsLoading(true);
    const res = await apiGet('/items', {
      states: [state],
      type: scopeMediaTypes(scope),
      limit: STATE_ITEMS_LIMIT,
      page: 1,
    });
    setStateItems((res.data?.items ?? []) as StateListItem[]);
    setStateTotal(res.data?.total_items ?? 0);
    setItemsLoading(false);
  }, []);

  /** Expand this row's breakdown whenever a strip or breakdown category is activated. */
  const pickCategoryFromStrip = useCallback(
    (scope: StateDistScope, stateName: string) => {
      setExpanded(scope);
      void handleCategoryClick(scope, stateName);
    },
    [handleCategoryClick],
  );

  const retryItem = useCallback(async (id: string | number) => {
    setRetryingIds((prev) => new Set(prev).add(id));
    const res = await apiPost('/items/retry', { ids: [String(id)] });
    setRetryingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (!res.ok) {
      notify(res.error || 'Retry failed', 'error');
    } else {
      notify('Item queued for retry', 'success');
    }
  }, []);

  const retryAllFailed = useCallback(async () => {
    if (!stateItems.length) return;
    setRetryingAll(true);
    const ids = stateItems.map((i) => String(i.id));
    const res = await apiPost('/items/retry', { ids });
    setRetryingAll(false);
    if (!res.ok) {
      notify(res.error || 'Retry all failed', 'error');
    } else {
      notify(`${ids.length} item(s) queued for retry`, 'success');
    }
  }, [stateItems]);

  const isFailed = selectedState === 'Failed';

  const moviesCounts = countsFromStatsDict(stats.states_movies as Record<string, unknown> | undefined);
  const episodesCounts = countsFromStatsDict(
    (stats.states_episodes ?? stats.states_shows) as Record<string, unknown> | undefined,
  );

  const scopeLabel =
    selectedScope === 'movies' ? 'Movies' : selectedScope === 'episodes' ? 'TV episodes' : '';

  return (
    <ViewLayout className="view-dashboard view-dashboard--states" view="dashboard-states">
      <ViewHeader
        title="Dashboard — State Distribution"
        subtitle="Movies and TV episodes by pipeline state."
      />
      <Panel>
        <div className="section-head">
          <h2>State Distribution</h2>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div className="state-dist">
            <StateDistributionSection
              title="Movies"
              scope="movies"
              countsDict={moviesCounts}
              expanded={expanded === 'movies'}
              compactStrip={expanded !== null && expanded !== 'movies'}
              onToggleExpand={() => setExpanded((e) => (e === 'movies' ? null : 'movies'))}
              onCategoryPick={(stateName) => pickCategoryFromStrip('movies', stateName)}
            />
            <StateDistributionSection
              title="TV Episodes"
              scope="episodes"
              countsDict={episodesCounts}
              expanded={expanded === 'episodes'}
              compactStrip={expanded !== null && expanded !== 'episodes'}
              onToggleExpand={() => setExpanded((e) => (e === 'episodes' ? null : 'episodes'))}
              onCategoryPick={(stateName) => pickCategoryFromStrip('episodes', stateName)}
            />
          </div>
        )}
      </Panel>
      <Panel>
        <div className="section-head">
          <h3>
            {selectedState && selectedScope
              ? `${scopeLabel} — ${selectedState}`
              : 'Items by category'}
          </h3>
          {isFailed && stateItems.length > 0 && (
            <button
              type="button"
              className="btn btn--primary btn--small"
              onClick={retryAllFailed}
              disabled={retryingAll}
            >
              {retryingAll ? 'Retrying…' : `Retry all ${stateItems.length} shown`}
            </button>
          )}
        </div>
        <div className="state-items-list">
          {!selectedState || !selectedScope ? (
            <p className="muted">Click a segment or breakdown row to list titles.</p>
          ) : null}
          {selectedState && selectedScope && itemsLoading ? <p className="muted">Loading…</p> : null}
          {selectedState && selectedScope && !itemsLoading && stateItems.length === 0 ? (
            <>
              <p className="muted">No items in this state.</p>
              <p className="state-items-footer">
                <a href={libraryHashForScope(selectedScope, selectedState)}>View in library</a>
              </p>
            </>
          ) : null}
          {selectedState && selectedScope && !itemsLoading && stateItems.length > 0 ? (
            <>
              <table className="state-items-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Year</th>
                    {isFailed && <th></th>}
                  </tr>
                </thead>
                <tbody>
                  {stateItems.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <a href={`#/item/${item.id}`}>{displayTitle(item)}</a>
                      </td>
                      <td>
                        <span
                          className={`legend-chip ${item.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'}`}
                        >
                          {item.type ?? '—'}
                        </span>
                      </td>
                      <td>{item.year != null ? item.year : '—'}</td>
                      {isFailed && (
                        <td>
                          <button
                            type="button"
                            className="btn btn--secondary btn--small"
                            disabled={retryingIds.has(item.id)}
                            onClick={() => void retryItem(item.id)}
                          >
                            {retryingIds.has(item.id) ? '…' : 'Retry'}
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="state-items-footer">
                <a href={libraryHashForScope(selectedScope, selectedState)}>
                  View in library
                </a>{' '}
                ({stateTotal.toLocaleString()} in {selectedState})
              </p>
            </>
          ) : null}
        </div>
      </Panel>
    </ViewLayout>
  );
}

function DashboardReleases({ route: _route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [yearItems, setYearItems] = useState<StateListItem[]>([]);
  const [yearTotal, setYearTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);
  const releaseBarsWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet('/stats').then((res) => {
      setStats(res.data || {});
      setLoading(false);
    });
  }, []);

  const handleYearClick = useCallback(async (year: number) => {
    setSelectedYear(year);
    setItemsLoading(true);
    const res = await apiGet('/items', { year, limit: YEAR_ITEMS_LIMIT, page: 1 });
    setYearItems((res.data?.items ?? []) as StateListItem[]);
    setYearTotal(res.data?.total_items ?? 0);
    setItemsLoading(false);
  }, []);

  const releases = useMemo(
    () => buildReleaseYearSeries(stats?.media_year_releases),
    [stats?.media_year_releases],
  );

  const maxCount = useMemo(
    () => Math.max(...releases.map((e) => e.count), 1),
    [releases],
  );

  const barCount = releases.length;
  const gridMinWidthPx =
    Math.max(1, barCount) * RELEASE_BAR_MIN_COL_PX + Math.max(0, barCount - 1) * RELEASE_BARS_GAP_PX;

  useLayoutEffect(() => {
    if (loading) return;
    const el = releaseBarsWrapRef.current;
    if (!el) return;
    el.scrollLeft = el.scrollWidth - el.clientWidth;
  }, [loading, barCount, gridMinWidthPx]);

  return (
    <ViewLayout className="view-dashboard view-dashboard--releases" view="dashboard-releases">
      <ViewHeader title="Dashboard — Releases by Year" subtitle="Library content by release year." />
      <Panel className="panel--release-years">
        <div className="section-head">
          <h2>Releases by Year</h2>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div ref={releaseBarsWrapRef} className="release-bars-wrap">
            <div
              className="release-bars"
              style={{
                gridTemplateColumns: `repeat(${barCount}, minmax(${RELEASE_BAR_MIN_COL_PX}px, 1fr))`,
                width: `max(100%, ${gridMinWidthPx}px)`,
              }}
            >
              {releases.map((entry) => {
                const isEmpty = entry.count === 0;
                const fillPct = isEmpty
                  ? undefined
                  : Math.max((entry.count / maxCount) * 100, 8);
                return (
                  <button
                    key={entry.year}
                    type="button"
                    className={`release-bar release-bar--clickable${isEmpty ? ' release-bar--empty' : ''}`}
                    onClick={() => handleYearClick(entry.year)}
                    aria-label={`${entry.year}${isEmpty ? ', no items' : `, ${entry.count} items`}`}
                  >
                    <div className="release-bar__track">
                      {isEmpty ? (
                        <div className="release-bar__fill release-bar__fill--zero" aria-hidden />
                      ) : (
                        <div
                          className="release-bar__fill"
                          style={{ height: `${fillPct}%` }}
                        />
                      )}
                    </div>
                    <span className="release-bar__year">{entry.year}</span>
                    <span className={`release-bar__value${isEmpty ? ' release-bar__value--empty' : ''}`}>
                      {isEmpty ? '—' : entry.count.toLocaleString()}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </Panel>
      <Panel>
        <div className="section-head">
          <h3>{selectedYear ? `Items in release year: ${selectedYear}` : 'Items by release year'}</h3>
        </div>
        <div className="state-items-list">
          {!selectedYear && <p className="muted">Click a year above to list items.</p>}
          {selectedYear && itemsLoading && <p className="muted">Loading…</p>}
          {selectedYear && !itemsLoading && yearItems.length === 0 && <><p className="muted">No items for this year.</p><p className="state-items-footer"><a href={`#/library?year=${selectedYear}`}>View all media</a></p></>}
          {selectedYear && !itemsLoading && yearItems.length > 0 && (
            <>
              <table className="state-items-table">
                <thead><tr><th>Title</th><th>Type</th><th>Year</th></tr></thead>
                <tbody>
                  {yearItems.map((item) => (
                    <tr key={item.id}>
                      <td><a href={`#/item/${item.id}`}>{displayTitle(item)}</a></td>
                      <td><span className={`legend-chip ${item.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'}`}>{item.type ?? '—'}</span></td>
                      <td>{item.year != null ? item.year : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="state-items-footer">
                <a href={`#/library?year=${selectedYear}`}>View all media</a> ({yearTotal} in {selectedYear})
              </p>
            </>
          )}
        </div>
      </Panel>
    </ViewLayout>
  );
}

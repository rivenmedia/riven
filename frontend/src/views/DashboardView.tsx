import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import { formatBytes as formatBytesUtil, formatEpisodeDisplayTitle } from '../services/utils';
import type { AppRoute } from '../app/routeTypes';

const PIPELINE_ORDER = ['Requested', 'Indexed', 'Scraped', 'Downloaded', 'Symlinked', 'Completed'];
const OTHER_STATES = ['Unknown', 'Unreleased', 'Ongoing', 'PartiallyCompleted', 'Failed', 'Paused'];

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
  prowlarr: 'Scrapers',
  jackett: 'Scrapers',
  aiostreams: 'Scrapers',
  comet: 'Scrapers',
  mediafusion: 'Scrapers',
  orionoid: 'Scrapers',
  rarbg: 'Scrapers',
  torrentio: 'Scrapers',
  zilean: 'Scrapers',
  indexerservice: 'Indexers',
  updater: 'Updaters',
  filesystemservice: 'Filesystem',
  postprocessing: 'Post-processing',
  notificationservice: 'Notifications',
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

  return (
    <ViewLayout className="view-dashboard" view="dashboard">
      <p className="muted">Unknown dashboard view.</p>
    </ViewLayout>
  );
}

function DashboardOverview({ route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [downloader, setDownloader] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    const [statsRes, downloaderRes] = await Promise.all([
      apiGet('/stats'),
      apiGet('/downloader_user_info'),
    ]);
    setStats(statsRes.data || {});
    setDownloader(downloaderRes.data || {});
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

  const kpis = [
    { title: 'Total Items', value: total.toLocaleString(), sub: 'All media entries' },
    { title: 'Movies', value: Number(stats?.total_movies || 0).toLocaleString(), sub: 'Movie records' },
    { title: 'Shows', value: Number(stats?.total_shows || 0).toLocaleString(), sub: 'TV show records' },
    { title: 'Completion', value: `${completionRate}%`, sub: `Completed ${completed.toLocaleString()} / ${total.toLocaleString()}` },
    { title: 'Incomplete', value: Number(stats?.incomplete_items || 0).toLocaleString(), sub: 'Needs processing' },
    { title: 'Symlinks', value: Number(stats?.total_symlinks || 0).toLocaleString(), sub: 'Mounted output links' },
  ];

  const services = (downloader as any)?.services || [];

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
          {!services.length ? (
            <p className="muted">No downloader service information.</p>
          ) : (
            services.map((service: any) => {
              const warning =
                service.premium_status === 'free'
                  ? 'Premium expired'
                  : service.premium_days_left != null && service.premium_days_left <= 7
                    ? `Expires in ${service.premium_days_left} day${service.premium_days_left === 1 ? '' : 's'}`
                    : null;
              const email = service.email ? String(service.email).replace(/(.{3}).*@/, '$1***@') : null;
              const displayName = service.username || email || 'Unknown account';
              const expires = service.premium_expires_at != null ? new Date(service.premium_expires_at).toLocaleDateString() : '—';
              const daysLeft = service.premium_days_left != null ? `${service.premium_days_left} days` : '—';
              return (
                <div key={service.service} className="downloader-card">
                  <div className="downloader-card__head">
                    <strong>{service.service}</strong>
                    {warning && <span className={`downloader-warning ${service.premium_status === 'free' ? 'downloader-warning--expired' : 'downloader-warning--soon'}`}>{warning}</span>}
                    <span className={`service-row__status ${service.premium_status === 'premium' ? 'service-row__status--up' : 'service-row__status--down'}`}>{service.premium_status}</span>
                  </div>
                  <dl className="downloader-card__meta">
                    <dt>Account</dt><dd>{displayName}</dd>
                    <dt>Expires</dt><dd>{expires}</dd>
                    <dt>Days left</dt><dd>{daysLeft}</dd>
                    {service.points != null && <><dt>Points</dt><dd>{String(service.points)}</dd></>}
                    {service.total_downloaded_bytes != null && <><dt>Downloaded</dt><dd>{formatBytesDash(service.total_downloaded_bytes)}</dd></>}
                    {service.cooldown_until != null && <><dt>Cooldown until</dt><dd>{new Date(service.cooldown_until).toLocaleString()}</dd></>}
                  </dl>
                </div>
              );
            })
          )}
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
  const [services, setServices] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet('/services').then((res) => {
      setServices(res.data || {});
      setLoading(false);
    });
  }, []);

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
      <Panel>
        <div className="section-head">
          <h2>Services</h2>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : orderedCategories.length === 0 ? (
          <p className="muted">No services payload.</p>
        ) : (
          <table className="services-table">
            <thead>
              <tr>
                <th className="services-table__category">Category</th>
                <th className="services-table__name">Service</th>
                <th className="services-table__status">Status</th>
              </tr>
            </thead>
            <tbody>
              {orderedCategories.flatMap((category) =>
                (byCategory.get(category)!).map(([name, isUp], i) => (
                  <tr key={name} className="service-row">
                    {i === 0 && <td className="services-table__category" rowSpan={byCategory.get(category)!.length}>{category}</td>}
                    <td className="services-table__name">{name}</td>
                    <td className="services-table__status">
                      <span className={`service-row__status ${isUp ? 'service-row__status--up' : 'service-row__status--down'}`}>{isUp ? 'UP' : 'DOWN'}</span>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        )}
      </Panel>
    </ViewLayout>
  );
}

function DashboardStates({ route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [stateItems, setStateItems] = useState<StateListItem[]>([]);
  const [stateTotal, setStateTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);

  useEffect(() => {
    apiGet('/stats').then((res) => {
      setStats(res.data || {});
      setLoading(false);
    });
  }, []);

  const handleStateClick = useCallback(async (state: string) => {
    setSelectedState(state);
    setItemsLoading(true);
    const res = await apiGet('/items', { states: [state], limit: STATE_ITEMS_LIMIT, page: 1 });
    setStateItems((res.data?.items ?? []) as StateListItem[]);
    setStateTotal(res.data?.total_items ?? 0);
    setItemsLoading(false);
  }, []);

  const states = (stats?.states || {}) as Record<string, number>;
  const getCount = (name: string) => Number(states[name] ?? 0);

  return (
    <ViewLayout className="view-dashboard view-dashboard--states" view="dashboard-states">
      <ViewHeader title="Dashboard — State Distribution" subtitle="Items by pipeline and other states." />
      <Panel>
        <div className="section-head">
          <h2>State Distribution</h2>
        </div>
        <div className="state-pipeline">
          <div className="state-pipeline__row">
            {PIPELINE_ORDER.map((name, i) => (
              <span key={name}>
                {i > 0 && <span className="state-pipeline__arrow" aria-hidden>→</span>}
                <button type="button" className="state-pipeline__node" onClick={() => handleStateClick(name)}>
                  <span className="state-pipeline__label">{name}</span>
                  <span className="state-pipeline__count">{getCount(name)}</span>
                </button>
              </span>
            ))}
          </div>
          <div className="state-pipeline__row state-pipeline__row--other">
            <span className="state-pipeline__other-label">Other</span>
            {OTHER_STATES.map((name) => (
              <button key={name} type="button" className="state-pipeline__node state-pipeline__node--other" onClick={() => handleStateClick(name)}>
                <span className="state-pipeline__label">{name}</span>
                <span className="state-pipeline__count">{getCount(name)}</span>
              </button>
            ))}
          </div>
        </div>
      </Panel>
      <Panel>
        <div className="section-head">
          <h3>{selectedState ? `Items in state: ${selectedState}` : 'Items in state'}</h3>
        </div>
        <div className="state-items-list">
          {!selectedState && <p className="muted">Click a state above to list items.</p>}
          {selectedState && itemsLoading && <p className="muted">Loading…</p>}
          {selectedState && !itemsLoading && stateItems.length === 0 && <><p className="muted">No items in this state.</p><p className="state-items-footer"><a href={`#/library?state=${encodeURIComponent(selectedState)}`}>View all media</a></p></>}
          {selectedState && !itemsLoading && stateItems.length > 0 && (
            <>
              <table className="state-items-table">
                <thead><tr><th>Title</th><th>Type</th><th>Year</th></tr></thead>
                <tbody>
                  {stateItems.map((item) => (
                    <tr key={item.id}>
                      <td><a href={`#/item/${item.id}`}>{displayTitle(item)}</a></td>
                      <td><span className={`legend-chip ${item.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'}`}>{item.type ?? '—'}</span></td>
                      <td>{item.year != null ? item.year : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="state-items-footer">
                <a href={`#/library?state=${encodeURIComponent(selectedState)}`}>View all media</a> ({stateTotal} in {selectedState})
              </p>
            </>
          )}
        </div>
      </Panel>
    </ViewLayout>
  );
}

function DashboardReleases({ route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [yearItems, setYearItems] = useState<StateListItem[]>([]);
  const [yearTotal, setYearTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);

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

  const releases = ((stats?.media_year_releases || []) as { year?: number; count?: number }[])
    .map((e) => ({ year: e?.year, count: Number(e?.count || 0) }))
    .filter((e) => Number.isFinite(e.year) && e.count! > 0)
    .sort((a, b) => a.year! - b.year!)
    .slice(-18);
  const maxCount = Math.max(...releases.map((e) => e.count), 1);

  return (
    <ViewLayout className="view-dashboard view-dashboard--releases" view="dashboard-releases">
      <ViewHeader title="Dashboard — Releases by Year" subtitle="Library content by release year." />
      <Panel>
        <div className="section-head">
          <h2>Releases by Year</h2>
        </div>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : !releases.length ? (
          <p className="muted">No release-year data available.</p>
        ) : (
          <div className="release-bars">
            {releases.map((entry) => (
              <button key={entry.year} type="button" className="release-bar release-bar--clickable" onClick={() => handleYearClick(entry.year!)}>
                <div className="release-bar__track">
                  <div className="release-bar__fill" style={{ height: `${Math.max((entry.count! / maxCount) * 100, 6)}%` }} />
                </div>
                <span className="release-bar__year">{entry.year}</span>
                <span className="release-bar__value">{entry.count}</span>
              </button>
            ))}
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

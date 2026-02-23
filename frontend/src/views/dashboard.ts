import type { AppRoute } from '../app/routeTypes';
import { apiGet, apiPost } from '../services/api';
import { formatEpisodeDisplayTitle } from '../services/utils';
import { notify } from '../services/notify';

function renderKpis(container, stats) {
  if (!container) return;
  const total = Number(stats?.total_items || 0);
  const completed = Number(stats?.states?.Completed || 0);
  const completionRate = total ? ((completed / total) * 100).toFixed(1) : '0.0';

  const cards = [
    { title: 'Total Items', value: total.toLocaleString(), sub: 'All media entries' },
    {
      title: 'Movies',
      value: Number(stats?.total_movies || 0).toLocaleString(),
      sub: 'Movie records',
    },
    {
      title: 'Shows',
      value: Number(stats?.total_shows || 0).toLocaleString(),
      sub: 'TV show records',
    },
    {
      title: 'Completion',
      value: `${completionRate}%`,
      sub: `Completed ${completed.toLocaleString()} / ${total.toLocaleString()}`,
    },
    {
      title: 'Incomplete',
      value: Number(stats?.incomplete_items || 0).toLocaleString(),
      sub: 'Needs processing',
    },
    {
      title: 'Symlinks',
      value: Number(stats?.total_symlinks || 0).toLocaleString(),
      sub: 'Mounted output links',
    },
  ];

  container.innerHTML = cards
    .map(
      (item) => `
        <article class="kpi-card">
          <h3>${item.title}</h3>
          <p class="kpi-value">${item.value}</p>
          <p class="kpi-sub">${item.sub}</p>
        </article>
      `,
    )
    .join('');
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

function renderServiceList(container, services) {
  if (!container) return;
  if (!services || typeof services !== 'object') {
    container.innerHTML = '<p class="muted">No services payload.</p>';
    return;
  }

  const byCategory = new Map<string, [string, boolean][]>();
  for (const [name, status] of Object.entries(services) as [string, boolean][]) {
    const key = name.toLowerCase().replace(/\s+/g, '');
    const category = SERVICE_CATEGORIES[key] ?? 'Other';
    if (!byCategory.has(category)) byCategory.set(category, []);
    byCategory.get(category)!.push([name, Boolean(status)]);
  }

  for (const entries of byCategory.values()) {
    entries.sort(([a], [b]) => a.localeCompare(b));
  }

  const orderedCategories = CATEGORY_ORDER.filter((cat) => byCategory.has(cat));
  const rows: string[] = [];
  for (const category of orderedCategories) {
    const entries = byCategory.get(category)!;
    entries.forEach(([name, isUp], i) => {
      const categoryCell =
        i === 0
          ? `<td class="services-table__category" rowspan="${entries.length}">${category}</td>`
          : '';
      const statusClass = isUp
        ? 'service-row__status--up'
        : 'service-row__status--down';
      rows.push(`
        <tr class="service-row">
          ${categoryCell}
          <td class="services-table__name">${name}</td>
          <td class="services-table__status">
            <span class="service-row__status ${statusClass}">${isUp ? 'UP' : 'DOWN'}</span>
          </td>
        </tr>
      `);
    });
  }

  container.innerHTML = `
    <table class="services-table">
      <thead>
        <tr>
          <th class="services-table__category">Category</th>
          <th class="services-table__name">Service</th>
          <th class="services-table__status">Status</th>
        </tr>
      </thead>
      <tbody>
        ${rows.join('')}
      </tbody>
    </table>
  `;
}

function premiumWarning(service: {
  premium_status?: string;
  premium_days_left?: number | null;
}): string {
  if (service.premium_status === 'free') {
    return '<span class="downloader-warning downloader-warning--expired">Premium expired</span>';
  }
  const days = service.premium_days_left;
  if (days != null && days <= 7) {
    return `<span class="downloader-warning downloader-warning--soon">Expires in ${days} day${days === 1 ? '' : 's'}</span>`;
  }
  return '';
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let u = 0;
  let n = bytes;
  while (n >= 1024 && u < units.length - 1) {
    n /= 1024;
    u += 1;
  }
  return `${n.toFixed(u ? 2 : 0)} ${units[u]}`;
}

function renderDownloaderInfo(container, downloaderResponse) {
  if (!container) return;
  const services = downloaderResponse?.services || [];
  if (!services.length) {
    container.innerHTML = '<p class="muted">No downloader service information.</p>';
    return;
  }

  container.innerHTML = services
    .map(
      (service) => {
        const warning = premiumWarning(service);
        const email = service.email ? String(service.email).replace(/(.{3}).*@/, '$1***@') : null;
        const displayName = service.username || email || 'Unknown account';
        const expires =
          service.premium_expires_at != null
            ? new Date(service.premium_expires_at).toLocaleDateString()
            : '—';
        const daysLeft =
          service.premium_days_left != null ? `${service.premium_days_left} days` : '—';
        const points = service.points != null ? String(service.points) : '—';
        const downloaded = formatBytes(service.total_downloaded_bytes);
        const cooldown =
          service.cooldown_until != null
            ? new Date(service.cooldown_until).toLocaleString()
            : null;
        return `
      <div class="downloader-card">
        <div class="downloader-card__head">
          <strong>${service.service}</strong>
          ${warning}
          <span class="service-row__status ${
            service.premium_status === 'premium'
              ? 'service-row__status--up'
              : 'service-row__status--down'
          }">${service.premium_status}</span>
        </div>
        <dl class="downloader-card__meta">
          <dt>Account</dt><dd>${displayName}</dd>
          <dt>Expires</dt><dd>${expires}</dd>
          <dt>Days left</dt><dd>${daysLeft}</dd>
          ${service.points != null ? `<dt>Points</dt><dd>${points}</dd>` : ''}
          ${service.total_downloaded_bytes != null ? `<dt>Downloaded</dt><dd>${downloaded}</dd>` : ''}
          ${cooldown ? `<dt>Cooldown until</dt><dd>${cooldown}</dd>` : ''}
        </dl>
      </div>
    `;
      },
    )
    .join('');
}

// Main pipeline order (left → right) from state_transition flow
const PIPELINE_ORDER = [
  'Requested',
  'Indexed',
  'Scraped',
  'Downloaded',
  'Symlinked',
  'Completed',
];
const OTHER_STATES = [
  'Unknown',
  'Unreleased',
  'Ongoing',
  'PartiallyCompleted',
  'Failed',
  'Paused',
];

function renderStatePipeline(container, stats, onNodeClick: (state: string) => void) {
  if (!container) return;
  const states = stats?.states || {};
  const getCount = (name: string) => Number(states[name] ?? 0);

  const pipelineNodes = PIPELINE_ORDER.map(
    (name, i) => `
    ${i > 0 ? '<span class="state-pipeline__arrow" aria-hidden="true">→</span>' : ''}
    <button type="button" class="state-pipeline__node" data-state="${name}">
      <span class="state-pipeline__label">${name}</span>
      <span class="state-pipeline__count">${getCount(name)}</span>
    </button>
  `,
  ).join('');

  const otherNodes = OTHER_STATES.map(
    (name) => `
    <button type="button" class="state-pipeline__node state-pipeline__node--other" data-state="${name}">
      <span class="state-pipeline__label">${name}</span>
      <span class="state-pipeline__count">${getCount(name)}</span>
    </button>
  `,
  ).join('');

  container.innerHTML = `
    <div class="state-pipeline">
      <div class="state-pipeline__row">${pipelineNodes}</div>
      <div class="state-pipeline__row state-pipeline__row--other">
        <span class="state-pipeline__other-label">Other</span>
        ${otherNodes}
      </div>
    </div>
  `;

  container.querySelectorAll<HTMLButtonElement>('.state-pipeline__node').forEach((btn) => {
    btn.addEventListener('click', () => onNodeClick(btn.dataset.state!));
  });
}

function renderActivityChart(container, stats) {
  if (!container) return;
  const activity = stats?.activity || {};
  const entries = Object.entries(activity)
    .map(([date, count]) => ({
      date,
      count: Number(count || 0),
      timestamp: new Date(date).getTime(),
    }))
    .filter((entry) => Number.isFinite(entry.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp)
    .slice(-30);

  if (!entries.length) {
    container.innerHTML = '<p class="muted">No request activity found.</p>';
    return;
  }

  const maxCount = Math.max(...entries.map((entry) => entry.count), 1);
  const width = 620;
  const height = 220;
  const padding = 24;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const points = entries.map((entry, index) => {
    const x =
      padding + (entries.length === 1 ? chartWidth / 2 : (index / (entries.length - 1)) * chartWidth);
    const y = padding + chartHeight - (entry.count / maxCount) * chartHeight;
    return { ...entry, x, y };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(' ');

  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(2)} ${(height - padding).toFixed(2)} L ${points[0].x.toFixed(2)} ${(height - padding).toFixed(2)} Z`;

  const firstDate = entries[0]?.date || '';
  const lastDate = entries[entries.length - 1]?.date || '';

  container.innerHTML = `
    <div class="chart-wrap">
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Activity line chart">
        <defs>
          <linearGradient id="activityFillGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="rgba(74,133,255,0.55)" />
            <stop offset="100%" stop-color="rgba(74,133,255,0.05)" />
          </linearGradient>
        </defs>
        <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" class="chart-axis" />
        <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${height - padding}" class="chart-axis" />
        <path d="${areaPath}" fill="url(#activityFillGradient)"></path>
        <path d="${linePath}" class="chart-line"></path>
        ${points
          .map(
            (point) => `
              <circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="3" class="chart-point">
                <title>${point.date}: ${point.count}</title>
              </circle>
            `,
          )
          .join('')}
      </svg>
      <div class="chart-meta">
        <span>${firstDate}</span>
        <strong>Peak: ${maxCount}</strong>
        <span>${lastDate}</span>
      </div>
    </div>
  `;
}

function renderReleaseChart(
  container: HTMLElement | null,
  stats: Record<string, unknown>,
  onYearClick?: (year: number) => void,
) {
  if (!container) return;
  const releases = (stats?.media_year_releases || []) as { year?: number; count?: number }[];
  const normalized = releases
    .map((entry) => ({
      year: entry?.year,
      count: Number(entry?.count || 0),
    }))
    .filter((entry) => Number.isFinite(entry.year) && entry.count > 0)
    .sort((a, b) => a.year - b.year)
    .slice(-18);

  if (!normalized.length) {
    container.innerHTML = '<p class="muted">No release-year data available.</p>';
    return;
  }

  const maxCount = Math.max(...normalized.map((entry) => entry.count), 1);
  container.innerHTML = `
    <div class="release-bars">
      ${normalized
        .map((entry) => {
          const height = Math.max((entry.count / maxCount) * 100, 6);
          const clickable = onYearClick ? ' release-bar--clickable' : '';
          return `
            <button type="button" class="release-bar${clickable}" data-year="${entry.year}">
              <div class="release-bar__track">
                <div class="release-bar__fill" style="height:${height}%"></div>
              </div>
              <span class="release-bar__year">${entry.year}</span>
              <span class="release-bar__value">${entry.count}</span>
            </button>
          `;
        })
        .join('')}
    </div>
  `;

  if (onYearClick) {
    container.querySelectorAll<HTMLButtonElement>('.release-bar[data-year]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const y = Number(btn.dataset.year);
        if (Number.isFinite(y)) onYearClick(y);
      });
    });
  }
}

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

const STATE_ITEMS_LIMIT = 25;

type StateListItem = {
  id: number;
  title?: string;
  parent_title?: string;
  type?: string;
  year?: number | null;
  season_number?: number | null;
  episode_number?: number | null;
};

function displayTitle(item: StateListItem): string {
  if (item.type === "episode") return formatEpisodeDisplayTitle(item);
  return item.title ?? `Item ${item.id}`;
}

function typePillHtml(type: string | undefined): string {
  if (!type) return "—";
  const chipClass = type === "movie" ? "legend-chip--movie" : "legend-chip--tv";
  return `<span class="legend-chip ${chipClass}">${escapeHtml(type)}</span>`;
}

function renderStateItemsList(
  titleEl: Element | null,
  listEl: Element | null,
  state: string,
  items: StateListItem[],
  totalItems: number,
) {
  if (!listEl) return;
  const libraryUrl = `#/library?state=${encodeURIComponent(state)}`;
  if (titleEl) titleEl.textContent = `Items in state: ${state}`;
  if (!items.length) {
    listEl.innerHTML = `
      <p class="muted">No items in this state.</p>
      <p class="state-items-footer"><a href="${libraryUrl}">View all media</a></p>
    `;
    return;
  }
  listEl.innerHTML = `
    <table class="state-items-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Type</th>
          <th>Year</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) =>
              `<tr>
                <td><a href="#/item/${item.id}">${escapeHtml(displayTitle(item))}</a></td>
                <td>${typePillHtml(item.type)}</td>
                <td>${item.year != null ? item.year : '—'}</td>
              </tr>`,
          )
          .join('')}
      </tbody>
    </table>
    <p class="state-items-footer">
      <a href="${libraryUrl}">View all media</a> (${totalItems} in ${state})
    </p>
  `;
}

function renderYearItemsList(
  titleEl: Element | null,
  listEl: Element | null,
  year: number,
  items: StateListItem[],
  totalItems: number,
) {
  if (!listEl) return;
  const libraryUrl = `#/library?year=${year}`;
  if (titleEl) titleEl.textContent = `Items in release year: ${year}`;
  if (!items.length) {
    listEl.innerHTML = `
      <p class="muted">No items for this year.</p>
      <p class="state-items-footer"><a href="${libraryUrl}">View all media</a></p>
    `;
    return;
  }
  listEl.innerHTML = `
    <table class="state-items-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Type</th>
          <th>Year</th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) =>
              `<tr>
                <td><a href="#/item/${item.id}">${escapeHtml(displayTitle(item))}</a></td>
                <td>${typePillHtml(item.type)}</td>
                <td>${item.year != null ? item.year : '—'}</td>
              </tr>`,
          )
          .join('')}
      </tbody>
    </table>
    <p class="state-items-footer">
      <a href="${libraryUrl}">View all media</a> (${totalItems} in ${year})
    </p>
  `;
}

const YEAR_ITEMS_LIMIT = 25;

function bindYearItemsInline(container: HTMLElement): (year: number) => Promise<void> {
  const titleEl = container.querySelector('[data-slot="year-items-title"]');
  const listEl = container.querySelector('[data-slot="year-items-list"]');

  return async function showItemsForYear(year: number) {
    if (!listEl) return;
    if (titleEl) titleEl.textContent = `Items in release year: ${year}`;
    listEl.innerHTML = '<p class="muted">Loading…</p>';

    const res = await apiGet('/items', { year, limit: YEAR_ITEMS_LIMIT, page: 1 });
    if (!res.ok) {
      listEl.innerHTML = `<p class="muted">${res.error || 'Failed to load items.'}</p>`;
      return;
    }
    const items = (res.data?.items ?? []) as StateListItem[];
    const totalItems = res.data?.total_items ?? items.length;
    renderYearItemsList(titleEl, listEl, year, items, totalItems);
  };
}

function bindStateItemsInline(container: HTMLElement): (state: string) => Promise<void> {
  const stateItemsTitle = container.querySelector('[data-slot="state-items-title"]');
  const stateItemsList = container.querySelector('[data-slot="state-items-list"]');

  return async function showItemsForState(state: string) {
    if (!stateItemsList) return;
    if (stateItemsTitle) stateItemsTitle.textContent = `Items in state: ${state}`;
    stateItemsList.innerHTML = '<p class="muted">Loading…</p>';

    const res = await apiGet('/items', { states: [state], limit: STATE_ITEMS_LIMIT, page: 1 });
    if (!res.ok) {
      stateItemsList.innerHTML = `<p class="muted">${res.error || 'Failed to load items.'}</p>`;
      return;
    }
    const items = res.data?.items ?? [];
    const totalItems = res.data?.total_items ?? items.length;
    renderStateItemsList(stateItemsTitle, stateItemsList, state, items, totalItems);
  };
}

function bindRetryButton(route: AppRoute, container: HTMLElement) {
  const retryButton = container.querySelector('[data-action="retry-library"]');
  if (retryButton) {
    retryButton.addEventListener('click', async () => {
      const response = await apiPost('/items/retry_library');
      if (!response.ok) {
        notify(response.error || 'Retry request failed', 'error');
        return;
      }
      notify(response.data?.message || 'Retry request submitted', 'success');
      await load(route, container);
    });
  }
}

export async function load(route: AppRoute, container: HTMLElement) {
  const name = route.name;

  if (name === 'dashboard') {
    const [statsRes, downloaderRes] = await Promise.all([
      apiGet('/stats'),
      apiGet('/downloader_user_info'),
    ]);
    const stats = statsRes.data || {};
    renderKpis(container.querySelector('[data-slot="kpis"]'), stats);
    renderDownloaderInfo(container.querySelector('[data-slot="downloader-info"]'), downloaderRes.data || {});
    renderActivityChart(container.querySelector('[data-slot="activity-chart"]'), stats);
    bindRetryButton(route, container);
    return;
  }

  if (name === 'dashboard-services') {
    const servicesRes = await apiGet('/services');
    renderServiceList(container.querySelector('[data-slot="services-list"]'), servicesRes.data || {});
    return;
  }

  if (name === 'dashboard-states') {
    const statsRes = await apiGet('/stats');
    const stats = statsRes.data || {};
    const showItemsForState = bindStateItemsInline(container);
    renderStatePipeline(container.querySelector('[data-slot="state-pipeline"]'), stats, showItemsForState);
    return;
  }

  if (name === 'dashboard-releases') {
    const statsRes = await apiGet('/stats');
    const stats = statsRes.data || {};
    const showItemsForYear = bindYearItemsInline(container);
    renderReleaseChart(
      container.querySelector('[data-slot="release-chart"]'),
      stats,
      showItemsForYear,
    );
    return;
  }
}

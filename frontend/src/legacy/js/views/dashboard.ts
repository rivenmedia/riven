import { apiGet, apiPost } from '../api';
import { notify } from '../notify';

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

function renderServiceList(container, services) {
  if (!container) return;
  if (!services || typeof services !== 'object') {
    container.innerHTML = '<p class="muted">No services payload.</p>';
    return;
  }

  const rows = Object.entries(services)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, status]) => {
      const isUp = Boolean(status);
      return `
        <div class="service-row">
          <strong>${name}</strong>
          <span class="service-row__status ${
            isUp ? 'service-row__status--up' : 'service-row__status--down'
          }">
            ${isUp ? 'UP' : 'DOWN'}
          </span>
        </div>
      `;
    })
    .join('');

  container.innerHTML = `<div class="service-list">${rows}</div>`;
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
      (service) => `
      <div class="service-row">
        <div>
          <strong>${service.service}</strong>
          <p class="muted">${service.username || service.email || 'Unknown account'}</p>
        </div>
        <span class="service-row__status ${
          service.premium_status === 'premium'
            ? 'service-row__status--up'
            : 'service-row__status--down'
        }">
          ${service.premium_status}
        </span>
      </div>
    `,
    )
    .join('');
}

function renderStateBars(container, stats) {
  if (!container) return;
  const states = stats?.states || {};
  const entries = Object.entries(states);
  const maxValue = Math.max(...entries.map(([, value]) => Number(value || 0)), 1);

  container.innerHTML = `
    <div class="state-bar-list">
      ${entries
        .map(([name, value]) => {
          const count = Number(value || 0);
          const width = Math.max((count / maxValue) * 100, 2);
          return `
            <div class="state-bar">
              <span>${name}</span>
              <div class="state-bar__track">
                <span class="state-bar__fill" style="width:${width}%"></span>
              </div>
              <strong>${count}</strong>
            </div>
          `;
        })
        .join('')}
    </div>
  `;
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

function renderReleaseChart(container, stats) {
  if (!container) return;
  const releases = (stats?.media_year_releases || [])
    .map((entry) => ({
      year: entry?.year,
      count: Number(entry?.count || 0),
    }))
    .filter((entry) => Number.isFinite(entry.year) && entry.count > 0)
    .sort((a, b) => a.year - b.year)
    .slice(-18);

  if (!releases.length) {
    container.innerHTML = '<p class="muted">No release-year data available.</p>';
    return;
  }

  const maxCount = Math.max(...releases.map((entry) => entry.count), 1);
  container.innerHTML = `
    <div class="release-bars">
      ${releases
        .map((entry) => {
          const height = Math.max((entry.count / maxCount) * 100, 6);
          return `
            <div class="release-bar">
              <div class="release-bar__track">
                <div class="release-bar__fill" style="height:${height}%"></div>
              </div>
              <span class="release-bar__year">${entry.year}</span>
              <span class="release-bar__value">${entry.count}</span>
            </div>
          `;
        })
        .join('')}
    </div>
  `;
}

export async function load(route, container) {
  const [statsRes, servicesRes, downloaderRes] = await Promise.all([
    apiGet('/stats'),
    apiGet('/services'),
    apiGet('/downloader_user_info'),
  ]);

  renderKpis(container.querySelector('[data-slot="kpis"]'), statsRes.data || {});
  renderServiceList(
    container.querySelector('[data-slot="services-list"]'),
    servicesRes.data || {},
  );
  renderDownloaderInfo(
    container.querySelector('[data-slot="downloader-info"]'),
    downloaderRes.data || {},
  );
  renderStateBars(container.querySelector('[data-slot="state-bars"]'), statsRes.data || {});
  renderActivityChart(container.querySelector('[data-slot="activity-chart"]'), statsRes.data || {});
  renderReleaseChart(container.querySelector('[data-slot="release-chart"]'), statsRes.data || {});

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

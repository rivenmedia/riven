import { apiGet, apiPost } from '../api.js';
import { notify } from '../notify.js';

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

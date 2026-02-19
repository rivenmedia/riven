/**
 * Dashboard view - stats, services, downloader
 */

import { apiGet, apiPost } from '../api.js';

export async function load(route, container) {
  const [statsRes, servicesRes, downloaderRes] = await Promise.all([
    apiGet('/stats'),
    apiGet('/services'),
    apiGet('/downloader_user_info'),
  ]);

  const kpis = container.querySelector('[data-slot="kpis"]');
  if (kpis) {
    const s = statsRes.data;
    const items = [
      { title: 'Total Items', value: s?.total_items?.toLocaleString(), sub: 'All indexed items' },
      { title: 'Completed', value: s?.states?.Completed?.toLocaleString(), sub: 'Fully processed' },
      { title: 'Incomplete', value: s?.incomplete_items?.toLocaleString(), sub: 'Pending', tone: 'warning' },
      {
        title: 'Completion Rate',
        value: s?.total_items
          ? ((s?.states?.Completed || 0) / s.total_items * 100).toFixed(1) + '%'
          : '0%',
        sub: 'Completed / Total',
      },
    ];
    kpis.innerHTML = items
      .map(
        (i) => `
      <div class="kpi-card">
        <h4>${i.title}</h4>
        <p class="kpi-value">${i.value ?? '—'}</p>
        <p class="kpi-sub">${i.sub}</p>
      </div>
    `
      )
      .join('');
  }

  const servicesList = container.querySelector('[data-slot="services-list"]');
  if (servicesList && servicesRes.data) {
    servicesList.innerHTML = Object.entries(servicesRes.data)
      .map(([name, status]) => `<p><strong>${name}</strong>: ${status?.initialized ? 'Ready' : '—'}</p>`)
      .join('');
  }

  const downloaderInfo = container.querySelector('[data-slot="downloader-info"]');
  if (downloaderInfo && downloaderRes.data) {
    const d = downloaderRes.data;
    downloaderInfo.innerHTML = `
      <p><strong>Service</strong>: ${d?.service ?? '—'}</p>
      <p><strong>User</strong>: ${d?.username ?? d?.email ?? '—'}</p>
      <p><strong>Status</strong>: ${d?.premium_status ?? '—'}</p>
    `;
  }

  const retryBtn = container.querySelector('[data-action="retry-library"]');
  if (retryBtn) {
    retryBtn.onclick = async () => {
      const res = await apiPost('/items/retry_library');
      if (res?.ok) load(route, container);
    };
  }
}

/**
 * VFS Stats view
 */

import { apiGet } from '../api.js';

export async function load(route, container) {
  const res = await apiGet('/vfs_stats');
  const tableEl = container.querySelector('[data-slot="table"]');
  if (!tableEl) return;
  if (!res.ok || !res.data?.stats) {
    tableEl.innerHTML = '<p>No VFS stats available</p>';
    return;
  }
  const stats = res.data.stats;
  tableEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Opener</th>
          <th>Metrics</th>
        </tr>
      </thead>
      <tbody>
        ${Object.entries(stats)
          .map(
            ([name, data]) => `
          <tr>
            <td>${name}</td>
            <td><pre>${JSON.stringify(data, null, 2)}</pre></td>
          </tr>
        `
          )
          .join('')}
      </tbody>
    </table>
  `;
}

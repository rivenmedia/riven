import { apiGet } from '../api.js';

export async function load(route, container) {
  const response = await apiGet('/vfs_stats');
  const tableHost = container.querySelector('[data-slot="table"]');
  if (!tableHost) return;

  if (!response.ok || !response.data?.stats) {
    tableHost.innerHTML = '<p class="muted">No VFS stats available.</p>';
    return;
  }

  const stats = response.data.stats;
  tableHost.innerHTML = `
    <table class="table">
      <thead>
        <tr>
          <th>Opener</th>
          <th>Metrics</th>
        </tr>
      </thead>
      <tbody>
        ${Object.entries(stats)
          .map(
            ([name, metrics]) => `
              <tr>
                <td><strong>${name}</strong></td>
                <td><pre class="json-output">${JSON.stringify(metrics, null, 2)}</pre></td>
              </tr>
            `,
          )
          .join('')}
      </tbody>
    </table>
  `;
}

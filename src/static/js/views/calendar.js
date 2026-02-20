import { apiGet } from '../api.js';
import { formatDate } from '../utils.js';

export async function load(route, container) {
  const content = container.querySelector('[data-slot="content"]');
  if (!content) return;

  const response = await apiGet('/calendar');
  if (!response.ok) {
    content.innerHTML = `<p class="muted">${response.error || 'Failed to load calendar.'}</p>`;
    return;
  }

  const values = Object.values(response.data?.data || {});
  const sorted = values
    .filter((entry) => entry?.aired_at)
    .sort((a, b) => new Date(a.aired_at).getTime() - new Date(b.aired_at).getTime());

  if (!sorted.length) {
    content.innerHTML = '<p class="muted">No calendar data available.</p>';
    return;
  }

  content.innerHTML = `
    <table class="table">
      <thead>
        <tr>
          <th>Airs</th>
          <th>Title</th>
          <th>Type</th>
          <th>State</th>
        </tr>
      </thead>
      <tbody>
        ${sorted
          .map((entry) => {
            const isMovie = entry.item_type === 'movie';
            const chipClass = isMovie ? 'legend-chip--movie' : 'legend-chip--tv';
            return `
              <tr>
                <td>${formatDate(entry.aired_at)}</td>
                <td>${entry.show_title || 'Unknown'}</td>
                <td><span class="legend-chip ${chipClass}">${entry.item_type}</span></td>
                <td>${entry.last_state || 'Unknown'}</td>
              </tr>
            `;
          })
          .join('')}
      </tbody>
    </table>
  `;
}

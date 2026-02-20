import { apiGet } from '../api';
import { formatDate } from '../utils';

interface CalendarEntry {
  aired_at?: string;
  show_title?: string;
  item_type?: string;
  last_state?: string;
}

export async function load(route: unknown, container: HTMLElement) {
  const content = container.querySelector('[data-slot="content"]');
  if (!content) return;

  const response = await apiGet('/calendar');
  if (!response.ok) {
    content.innerHTML = `<p class="muted">${response.error || 'Failed to load calendar.'}</p>`;
    return;
  }

  const values = Object.values(
    (response.data as { data?: Record<string, CalendarEntry> })?.data || {},
  ) as CalendarEntry[];
  const sorted = values
    .filter((entry): entry is CalendarEntry & { aired_at: string } => Boolean(entry?.aired_at))
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

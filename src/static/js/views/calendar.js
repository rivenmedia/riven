/**
 * Calendar view
 */

import { apiGet } from '../api.js';

export async function load(route, container) {
  const content = container.querySelector('[data-slot="content"]');
  const res = await apiGet('/calendar');
  if (!res.ok || !content) return;
  const data = res.data?.data || [];
  content.innerHTML = data.length
    ? `<pre>${JSON.stringify(data, null, 2)}</pre>`
    : '<p>No calendar data</p>';
}

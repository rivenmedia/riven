/**
 * Mount view - VFS mount listing
 */

import { apiGet } from '../api.js';

export async function load(route, container) {
  const content = container.querySelector('[data-slot="content"]');
  const res = await apiGet('/mount');
  if (!res.ok || !content) return;
  const data = res.data?.data || [];
  content.innerHTML = data.length
    ? `<pre>${JSON.stringify(data, null, 2)}</pre>`
    : '<p>No mount data</p>';
}

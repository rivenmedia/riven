import { apiFetch, apiGet } from '../api.js';
import { notify } from '../notify.js';

const QUICK_ENDPOINTS = [
  '/health',
  '/services',
  '/stats',
  '/events',
  '/vfs_stats',
  '/logs',
  '/downloader_user_info',
];

function pretty(data) {
  if (data === null || data === undefined) return '';
  if (typeof data === 'string') return data;
  return JSON.stringify(data, null, 2);
}

export async function load(route, container) {
  const quickHost = container.querySelector('[data-slot="quick-endpoints"]');
  const quickOutput = container.querySelector('[data-slot="quick-output"]');
  const form = container.querySelector('[data-slot="endpoint-form"]');
  const methodSelect = container.querySelector('[data-slot="method"]');
  const pathInput = container.querySelector('[data-slot="path"]');
  const bodyInput = container.querySelector('[data-slot="body"]');
  const runnerOutput = container.querySelector('[data-slot="runner-output"]');

  if (quickHost) {
    quickHost.innerHTML = QUICK_ENDPOINTS.map(
      (path) =>
        `<button type="button" class="btn btn--secondary btn--small" data-path="${path}">${path}</button>`,
    ).join('');

    quickHost.querySelectorAll('[data-path]').forEach((button) => {
      button.addEventListener('click', async () => {
        const path = button.dataset.path;
        if (!path || !quickOutput) return;
        quickOutput.textContent = 'Loading…';
        const response = await apiGet(path);
        quickOutput.textContent = pretty(response.data || { error: response.error });
      });
    });
  }

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const method = (methodSelect?.value || 'GET').toUpperCase();
      const path = (pathInput?.value || '').trim();
      if (!path) {
        notify('Path is required', 'warning');
        return;
      }

      const options = { method };
      if (method !== 'GET') {
        const rawBody = bodyInput?.value?.trim();
        if (rawBody) {
          try {
            options.body = rawBody;
          } catch {
            notify('Invalid request body', 'error');
            return;
          }
        } else {
          options.body = '{}';
        }
      }

      if (runnerOutput) runnerOutput.textContent = 'Running…';
      const response = await apiFetch(path, options);
      if (runnerOutput) {
        runnerOutput.textContent = pretty({
          ok: response.ok,
          status: response.status,
          error: response.error,
          data: response.data,
        });
      }
    });
  }
}

import { apiFetch, apiGet } from '../api.js';
import { notify } from '../notify.js';

const QUICK_ENDPOINTS = [
  '/health',
  '/services',
  '/stats',
  '/events',
  '/vfs_stats',
  '/downloader_user_info',
];

const LOG_ROW_HEIGHT = 26;
const LOG_OVERSCAN = 14;

function pretty(data) {
  if (data === null || data === undefined) return '';
  if (typeof data === 'string') return data;
  return JSON.stringify(data, null, 2);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function createVirtualLogList(host) {
  host.innerHTML = `
    <p class="muted" data-role="empty" hidden>No logs matched.</p>
    <div class="virtual-list" data-role="viewport">
      <div class="virtual-list__spacer" data-role="spacer"></div>
      <div class="virtual-list__content" data-role="content"></div>
    </div>
  `;

  const empty = host.querySelector('[data-role="empty"]');
  const viewport = host.querySelector('[data-role="viewport"]');
  const spacer = host.querySelector('[data-role="spacer"]');
  const content = host.querySelector('[data-role="content"]');
  const state = { rows: [] };
  let rafId = null;

  function renderWindow() {
    if (!viewport || !spacer || !content) return;
    const total = state.rows.length;
    spacer.style.height = `${total * LOG_ROW_HEIGHT}px`;

    const scrollTop = viewport.scrollTop;
    const visibleRows = Math.ceil(viewport.clientHeight / LOG_ROW_HEIGHT);
    const start = Math.max(Math.floor(scrollTop / LOG_ROW_HEIGHT) - LOG_OVERSCAN, 0);
    const end = Math.min(start + visibleRows + LOG_OVERSCAN * 2, total);
    const slice = state.rows.slice(start, end);

    content.style.transform = `translateY(${start * LOG_ROW_HEIGHT}px)`;
    content.innerHTML = slice
      .map(
        (row) => `
          <div class="log-row" title="${escapeHtml(row.raw)}">
            <span class="muted">#${row.index}</span> ${escapeHtml(row.raw)}
          </div>
        `,
      )
      .join('');
  }

  function scheduleRender() {
    if (rafId !== null) return;
    rafId = window.requestAnimationFrame(() => {
      rafId = null;
      renderWindow();
    });
  }

  viewport?.addEventListener('scroll', scheduleRender);

  return {
    setRows(rows) {
      state.rows = rows;
      if (empty) empty.hidden = rows.length > 0;
      if (viewport) viewport.hidden = rows.length === 0;
      if (viewport) viewport.scrollTop = 0;
      renderWindow();
    },
  };
}

export async function load(route, container) {
  const quickHost = container.querySelector('[data-slot="quick-endpoints"]');
  const quickOutput = container.querySelector('[data-slot="quick-output"]');
  const form = container.querySelector('[data-slot="endpoint-form"]');
  const methodSelect = container.querySelector('[data-slot="method"]');
  const pathInput = container.querySelector('[data-slot="path"]');
  const bodyInput = container.querySelector('[data-slot="body"]');
  const runnerOutput = container.querySelector('[data-slot="runner-output"]');
  const logSearch = container.querySelector('[data-slot="log-search"]');
  const logMeta = container.querySelector('[data-slot="log-meta"]');
  const logContainer = container.querySelector('[data-slot="log-container"]');
  const refreshLogsButton = container.querySelector('[data-action="refresh-logs"]');
  const virtualLogs = logContainer ? createVirtualLogList(logContainer) : null;
  const logState = {
    all: [],
    filtered: [],
    query: '',
  };

  function renderLogs() {
    const needle = logState.query.toLowerCase();
    logState.filtered = logState.all
      .map((raw, index) => ({ raw: String(raw), index: index + 1 }))
      .filter((row) => !needle || row.raw.toLowerCase().includes(needle));

    virtualLogs?.setRows(logState.filtered);
    if (logMeta) {
      logMeta.textContent = `${logState.filtered.length.toLocaleString()} / ${logState.all.length.toLocaleString()} lines`;
    }
  }

  async function fetchLogs() {
    if (logMeta) logMeta.textContent = 'Loading logs…';
    const response = await apiGet('/logs');
    if (!response.ok) {
      if (logMeta) logMeta.textContent = response.error || 'Failed to fetch logs.';
      virtualLogs?.setRows([]);
      return;
    }
    logState.all = response.data?.logs || [];
    renderLogs();
  }

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

  if (logSearch) {
    logSearch.addEventListener('input', () => {
      logState.query = logSearch.value || '';
      renderLogs();
    });
  }

  if (refreshLogsButton) {
    refreshLogsButton.addEventListener('click', () => {
      fetchLogs();
    });
  }

  await fetchLogs();
}

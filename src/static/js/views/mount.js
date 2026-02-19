import { apiGet } from '../api.js';

const ROW_HEIGHT = 34;
const OVERSCAN = 10;

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function buildVirtualList(host) {
  host.innerHTML = `
    <p class="muted" data-role="empty" hidden>No matching mounted files.</p>
    <div class="virtual-list" data-role="viewport">
      <div class="virtual-list__spacer" data-role="spacer"></div>
      <div class="virtual-list__content" data-role="content"></div>
    </div>
  `;

  const empty = host.querySelector('[data-role="empty"]');
  const viewport = host.querySelector('[data-role="viewport"]');
  const spacer = host.querySelector('[data-role="spacer"]');
  const content = host.querySelector('[data-role="content"]');
  const state = { items: [] };

  let rafId = null;

  function renderWindow() {
    if (!viewport || !spacer || !content) return;
    const total = state.items.length;
    spacer.style.height = `${total * ROW_HEIGHT}px`;

    const scrollTop = viewport.scrollTop;
    const visibleRows = Math.ceil(viewport.clientHeight / ROW_HEIGHT);
    const start = Math.max(Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN, 0);
    const end = Math.min(start + visibleRows + OVERSCAN * 2, total);
    const slice = state.items.slice(start, end);

    content.style.transform = `translateY(${start * ROW_HEIGHT}px)`;
    content.innerHTML = slice
      .map(
        (entry) => `
          <div class="mount-row">
            <strong title="${escapeHtml(entry.name)}">${escapeHtml(entry.name)}</strong>
            <span class="muted" title="${escapeHtml(entry.path)}">${escapeHtml(entry.path)}</span>
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
    setItems(items) {
      state.items = items;
      if (empty) empty.hidden = items.length > 0;
      if (viewport) viewport.hidden = items.length === 0;
      if (viewport) viewport.scrollTop = 0;
      renderWindow();
    },
  };
}

export async function load(route, container) {
  const searchInput = container.querySelector('[data-slot="search"]');
  const stats = container.querySelector('[data-slot="stats"]');
  const content = container.querySelector('[data-slot="content"]');
  if (!content) return;

  const response = await apiGet('/mount');
  if (!response.ok) {
    content.innerHTML = `<p class="muted">${response.error || 'Failed to load mount data.'}</p>`;
    return;
  }

  const files = response.data?.files || {};
  const entries = Object.entries(files).map(([name, path]) => ({
    name,
    path,
  }));

  const virtualList = buildVirtualList(content);

  function renderList(query = '') {
    const needle = query.trim().toLowerCase();
    const filtered = entries.filter((entry) =>
      !needle ||
      entry.name.toLowerCase().includes(needle) ||
      entry.path.toLowerCase().includes(needle),
    );

    if (!filtered.length) {
      virtualList.setItems([]);
      if (stats) {
        stats.textContent = `0 / ${entries.length.toLocaleString()} files`;
      }
      return;
    }

    virtualList.setItems(filtered);
    if (stats) {
      stats.textContent = `${filtered.length.toLocaleString()} / ${entries.length.toLocaleString()} files`;
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderList(searchInput.value);
    });
  }

  renderList('');
}

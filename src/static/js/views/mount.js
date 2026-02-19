import { apiGet } from '../api.js';

export async function load(route, container) {
  const searchInput = container.querySelector('[data-slot="search"]');
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

  function renderList(query = '') {
    const needle = query.trim().toLowerCase();
    const filtered = entries.filter((entry) =>
      !needle ||
      entry.name.toLowerCase().includes(needle) ||
      entry.path.toLowerCase().includes(needle),
    );

    if (!filtered.length) {
      content.innerHTML = '<p class="muted">No matching mounted files.</p>';
      return;
    }

    content.innerHTML = `
      <div class="mount-list">
        ${filtered
          .slice(0, 1500)
          .map(
            (entry) => `
              <div class="mount-row">
                <strong>${entry.name}</strong>
                <span class="muted">${entry.path}</span>
              </div>
            `,
          )
          .join('')}
      </div>
    `;
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      renderList(searchInput.value);
    });
  }

  renderList('');
}

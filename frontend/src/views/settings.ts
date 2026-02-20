import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';

function renderGroups(container, settings, filter = '') {
  if (!container) return;

  const keys = Object.keys(settings || {})
    .sort()
    .filter((key) => key.toLowerCase().includes(filter.toLowerCase()));

  if (!keys.length) {
    container.innerHTML = '<p class="muted">No settings groups matched the filter.</p>';
    return;
  }

  container.innerHTML = keys
    .map((key) => {
      const value = settings[key];
      return `
        <details class="settings-group" open>
          <summary>${key}</summary>
          <div class="settings-group__body">
            <textarea data-slot="value" data-key="${key}">${JSON.stringify(value, null, 2)}</textarea>
            <div class="toolbar">
              <button type="button" class="btn btn--primary btn--small" data-action="save-group" data-key="${key}">
                Save ${key}
              </button>
            </div>
          </div>
        </details>
      `;
    })
    .join('');
}

export async function load(route, container) {
  const groupsHost = container.querySelector('[data-slot="groups"]');
  const filterInput = container.querySelector('[data-slot="filter"]');
  const reloadButton = container.querySelector('[data-action="reload-from-disk"]');
  const saveButton = container.querySelector('[data-action="save-to-disk"]');

  const state = {
    settings: {},
    filter: '',
  };

  async function fetchSettings() {
    const response = await apiGet('/settings/get/all');
    if (!response.ok) {
      if (groupsHost) {
        groupsHost.innerHTML = `<p class="muted">${response.error || 'Failed to fetch settings.'}</p>`;
      }
      return false;
    }
    state.settings = response.data || {};
    renderGroups(groupsHost, state.settings, state.filter);
    wireGroupActions();
    return true;
  }

  function wireGroupActions() {
    if (!groupsHost) return;
    groupsHost.querySelectorAll('[data-action="save-group"]').forEach((button) => {
      button.addEventListener('click', async () => {
        const key = button.dataset.key;
        if (!key) return;

        const textarea = groupsHost.querySelector(`textarea[data-key="${key}"]`);
        if (!textarea) return;

        let parsed;
        try {
          parsed = JSON.parse(textarea.value);
        } catch {
          notify(`Invalid JSON for "${key}"`, 'error');
          return;
        }

        const response = await apiPost(`/settings/set/${key}`, {
          [key]: parsed,
        });
        if (!response.ok) {
          notify(response.error || `Failed to save ${key}`, 'error');
          return;
        }
        notify(`Saved "${key}"`, 'success');
      });
    });
  }

  if (filterInput) {
    filterInput.addEventListener('input', () => {
      state.filter = filterInput.value || '';
      renderGroups(groupsHost, state.settings, state.filter);
      wireGroupActions();
    });
  }

  if (reloadButton) {
    reloadButton.addEventListener('click', async () => {
      const response = await apiGet('/settings/load');
      if (!response.ok) {
        notify(response.error || 'Failed to reload settings', 'error');
        return;
      }
      notify(response.data?.message || 'Settings reloaded from disk', 'success');
      await fetchSettings();
    });
  }

  if (saveButton) {
    saveButton.addEventListener('click', async () => {
      const response = await apiPost('/settings/save');
      if (!response.ok) {
        notify(response.error || 'Failed to save settings', 'error');
        return;
      }
      notify(response.data?.message || 'Settings written to disk', 'success');
    });
  }

  await fetchSettings();
}

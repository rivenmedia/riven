import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import type { AppRoute } from '../app/routeTypes';

export default function SettingsView({ route }: { route: AppRoute }) {
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    const response = await apiGet('/settings/get/all');
    if (!response.ok) {
      setError(response.error || 'Failed to fetch settings.');
      setLoading(false);
      return false;
    }
    setSettings(response.data || {});
    setError(null);
    setLoading(false);
    return true;
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleReload = async () => {
    const response = await apiGet('/settings/load');
    if (!response.ok) {
      notify(response.error || 'Failed to reload settings', 'error');
      return;
    }
    notify(response.data?.message || 'Settings reloaded from disk', 'success');
    await fetchSettings();
  };

  const handleSaveToDisk = async () => {
    const response = await apiPost('/settings/save');
    if (!response.ok) {
      notify(response.error || 'Failed to save settings', 'error');
      return;
    }
    notify(response.data?.message || 'Settings written to disk', 'success');
  };

  const handleSaveGroup = async (key: string, valueStr: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(valueStr);
    } catch {
      notify(`Invalid JSON for "${key}"`, 'error');
      return;
    }
    const response = await apiPost(`/settings/set/${key}`, { [key]: parsed });
    if (!response.ok) {
      notify(response.error || `Failed to save ${key}`, 'error');
      return;
    }
    notify(`Saved "${key}"`, 'success');
  };

  const keys = Object.keys(settings)
    .sort()
    .filter((key) =>
      key.toLowerCase().includes(filter.toLowerCase()),
    );

  return (
    <ViewLayout className="view-settings" view="settings">
      <ViewHeader
        title="Settings"
        subtitle="Edit settings by logical groups and persist directly through API."
        actions={
          <>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleReload}
            >
              Reload
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={handleSaveToDisk}
            >
              Save File
            </button>
          </>
        }
      />
      <div className="toolbar toolbar--settings">
        <input
          type="search"
          placeholder="Filter groups (e.g. filesystem, ranking)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      {loading ? (
        <p className="muted">Loading settings…</p>
      ) : error ? (
        <p className="muted">{error}</p>
      ) : !keys.length ? (
        <p className="muted">No settings groups matched the filter.</p>
      ) : (
        <div className="settings-groups">
          {keys.map((key) => (
            <SettingsGroup
              key={key}
              groupKey={key}
              value={settings[key]}
              onSave={(valueStr) => handleSaveGroup(key, valueStr)}
            />
          ))}
        </div>
      )}
    </ViewLayout>
  );
}

function SettingsGroup({
  groupKey,
  value,
  onSave,
}: {
  groupKey: string;
  value: unknown;
  onSave: (valueStr: string) => void;
}) {
  const [localValue, setLocalValue] = useState(
    () => JSON.stringify(value, null, 2),
  );

  useEffect(() => {
    setLocalValue(JSON.stringify(value, null, 2));
  }, [value]);

  return (
    <details className="settings-group" open>
      <summary>{groupKey}</summary>
      <div className="settings-group__body">
        <textarea
          value={localValue}
          onChange={(e) => setLocalValue(e.target.value)}
        />
        <div className="toolbar">
          <button
            type="button"
            className="btn btn--primary btn--small"
            onClick={() => onSave(localValue)}
          >
            Save {groupKey}
          </button>
        </div>
      </div>
    </details>
  );
}

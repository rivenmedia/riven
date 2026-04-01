import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader } from '../../shared/ui/PagePrimitives';
import { apiGet, apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import type { AppRoute } from '../../app/routeTypes';

import { SettingsGroupForm } from './components/SettingsGroupForm';
import {
  buildGroupSchema,
  type JsonSchema,
} from './schema/settingsSchema';

export default function SettingsView({ route }: { route: AppRoute }) {
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [schema, setSchema] = useState<JsonSchema | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);
  const [activeGroupKey, setActiveGroupKey] = useState<string | null>(null);

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

  const fetchSchemaForAllTopLevelKeys = useCallback(async (keys: string[]) => {
    if (!keys.length) return;
    const response = await apiGet('/settings/schema/keys', {
      keys: keys.join(','),
      title: 'RivenSettings',
    });
    if (!response.ok) {
      setSchema(null);
      setSchemaError(response.error || 'Failed to fetch settings schema.');
      return;
    }
    setSchema((response.data as JsonSchema) || null);
    setSchemaError(null);
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  useEffect(() => {
    const topKeys = Object.keys(settings).sort();
    fetchSchemaForAllTopLevelKeys(topKeys);
  }, [fetchSchemaForAllTopLevelKeys, settings]);

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

  const handleSaveGroupJson = async (key: string, valueStr: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(valueStr);
    } catch {
      notify(`Invalid JSON for "${key}"`, 'error');
      return;
    }
    await handleSaveGroupValue(key, parsed);
  };

  const handleSaveGroupValue = async (key: string, value: unknown) => {
    const response = await apiPost('/settings/set/all', { [key]: value });
    if (!response.ok) {
      notify(response.error || `Failed to save ${key}`, 'error');
      return;
    }
    notify(`Saved "${key}"`, 'success');
    await fetchSettings();
  };

  const keys = useMemo(
    () =>
      Object.keys(settings)
        .sort()
        .filter((key) => key.toLowerCase().includes(filter.toLowerCase())),
    [filter, settings],
  );

  useEffect(() => {
    if (!keys.length) {
      setActiveGroupKey(null);
      return;
    }
    if (activeGroupKey && keys.includes(activeGroupKey)) return;
    setActiveGroupKey(keys[0]);
  }, [activeGroupKey, keys]);

  const activeValue = activeGroupKey ? settings[activeGroupKey] : undefined;
  const activeSchema = useMemo(() => {
    if (!activeGroupKey) return null;
    if (!schema) return null;
    return buildGroupSchema(schema, activeGroupKey);
  }, [activeGroupKey, schema]);

  const activeDescription = useMemo(() => {
    if (!activeGroupKey) return null;
    if (!schema) return null;
    const properties = schema.properties;
    if (!properties || typeof properties !== 'object') return null;
    const s = (properties as Record<string, any>)[activeGroupKey];
    if (!s || typeof s !== 'object') return null;
    if (typeof s.description === 'string' && s.description.trim()) return s.description;
    return null;
  }, [activeGroupKey, schema]);

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
      {schemaError ? (
        <p className="muted">{schemaError}</p>
      ) : null}
      {loading ? (
        <p className="muted">Loading settings…</p>
      ) : error ? (
        <p className="muted">{error}</p>
      ) : !keys.length ? (
        <p className="muted">No settings groups matched the filter.</p>
      ) : (
        <div className="settings-layout">
          <aside className="settings-sidebar">
            <div className="settings-sidebar__list">
              {keys.map((key) => {
                const isActive = key === activeGroupKey;
                return (
                  <button
                    key={key}
                    type="button"
                    className={`settings-sidebar__item${isActive ? ' is-active' : ''}`}
                    onClick={() => setActiveGroupKey(key)}
                  >
                    {key}
                  </button>
                );
              })}
            </div>
          </aside>
          <section className="settings-editor">
            {activeGroupKey ? (
              <SettingsEditor
                groupKey={activeGroupKey}
                value={activeValue}
                groupSchema={activeSchema}
                description={activeDescription}
                onSaveJson={(valueStr) =>
                  handleSaveGroupJson(activeGroupKey, valueStr)
                }
                onSaveValue={(value) =>
                  handleSaveGroupValue(activeGroupKey, value)
                }
              />
            ) : (
              <p className="muted">Select a settings group.</p>
            )}
          </section>
        </div>
      )}
    </ViewLayout>
  );
}

function SettingsEditor({
  groupKey,
  value,
  groupSchema,
  description,
  onSaveJson,
  onSaveValue,
}: {
  groupKey: string;
  value: unknown;
  groupSchema: JsonSchema | null;
  description: string | null;
  onSaveJson: (valueStr: string) => void;
  onSaveValue: (value: unknown) => Promise<void> | void;
}) {
  const [localValue, setLocalValue] = useState(
    () => JSON.stringify(value, null, 2),
  );

  useEffect(() => {
    setLocalValue(JSON.stringify(value, null, 2));
  }, [value]);

  return (
    <div className="settings-editor__inner">
      <div className="settings-editor__header">
        <div>
          <div className="settings-editor__title">{groupKey}</div>
          <div className="settings-editor__subtitle muted">
            {description
              ? description
              : 'Edit this settings group. Changes validate against the backend schema.'}
          </div>
        </div>
      </div>
      <div className="settings-editor__body">
        <SettingsGroupForm
          groupKey={groupKey}
          value={value}
          schema={groupSchema}
          onSave={onSaveValue}
          jsonFallback={
            <>
              <textarea
                value={localValue}
                onChange={(e) => setLocalValue(e.target.value)}
              />
              <div className="toolbar">
                <button
                  type="button"
                  className="btn btn--primary btn--small"
                  onClick={() => onSaveJson(localValue)}
                >
                  Save {groupKey}
                </button>
              </div>
            </>
          }
        />
      </div>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { ViewLayout, ViewHeader } from '../../shared/ui/PagePrimitives';
import { apiGet, apiPost } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import type { AppRoute } from '../../app/routeTypes';

import { SettingsGroupForm } from './components/SettingsGroupForm';
import { formatSettingsKeyLabel, formatSettingsRouteLabel } from './formatSettingsLabel';
import {
  buildGeneralSchema,
  buildGroupSchema,
  buildNestedPropertySchema,
  buildScalarSubsetGroupSchema,
  isTopLevelObjectGroup,
  nestedObjectChildKeys,
  type JsonSchema,
} from './schema/settingsSchema';

const GENERAL_GROUP_KEY = '__general';

type SettingsNavItem = { id: string; depth: 0 | 1; label: string };

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

  const { generalKeys, objectKeys } = useMemo(() => {
    const general: string[] = [];
    const objects: string[] = [];
    for (const [k, v] of Object.entries(settings)) {
      if (isTopLevelObjectGroup(v)) objects.push(k);
      else general.push(k);
    }
    general.sort();
    objects.sort();
    return { generalKeys: general, objectKeys: objects };
  }, [settings]);

  useEffect(() => {
    const topKeys = [...generalKeys, ...objectKeys].sort();
    if (!topKeys.length) return;
    fetchSchemaForAllTopLevelKeys(topKeys);
  }, [fetchSchemaForAllTopLevelKeys, generalKeys, objectKeys]);

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

  const jsonRouteLabel = (key: string) => {
    if (key === GENERAL_GROUP_KEY) return 'General';
    return formatSettingsRouteLabel(key);
  };

  const handleSaveGroupJson = async (key: string, valueStr: string) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(valueStr);
    } catch {
      notify(`Invalid JSON for "${jsonRouteLabel(key)}"`, 'error');
      return;
    }
    await handleSaveGroupValue(key, parsed);
  };

  const handleSaveGroupValue = async (key: string, value: unknown) => {
    if (
      key === GENERAL_GROUP_KEY &&
      value &&
      typeof value === 'object' &&
      !Array.isArray(value)
    ) {
      const response = await apiPost('/settings/set/all', value as Record<string, unknown>);
      if (!response.ok) {
        notify(response.error || 'Failed to save General', 'error');
        return;
      }
      notify('Saved "General"', 'success');
      await fetchSettings();
      return;
    }

    const dot = key.indexOf('.');
    if (dot > 0) {
      const top = key.slice(0, dot);
      const sub = key.slice(dot + 1);
      if (objectKeys.includes(top) && sub) {
        const response = await apiPost('/settings/set/all', {
          [top]: { [sub]: value },
        });
        if (!response.ok) {
          notify(
            response.error || `Failed to save ${formatSettingsRouteLabel(`${top}.${sub}`)}`,
            'error',
          );
          return;
        }
        notify(`Saved "${formatSettingsRouteLabel(`${top}.${sub}`)}"`, 'success');
        await fetchSettings();
        return;
      }
    }

    if (objectKeys.includes(key)) {
      const currentTop = settings[key];
      const merged =
        currentTop &&
        typeof currentTop === 'object' &&
        !Array.isArray(currentTop) &&
        value &&
        typeof value === 'object' &&
        !Array.isArray(value)
          ? { ...(currentTop as Record<string, unknown>), ...(value as Record<string, unknown>) }
          : value;
      const response = await apiPost('/settings/set/all', { [key]: merged });
      if (!response.ok) {
        notify(response.error || `Failed to save ${formatSettingsKeyLabel(key)}`, 'error');
        return;
      }
      notify(`Saved "${formatSettingsKeyLabel(key)}"`, 'success');
      await fetchSettings();
      return;
    }

    const response = await apiPost('/settings/set/all', { [key]: value });
    if (!response.ok) {
      notify(response.error || `Failed to save ${formatSettingsKeyLabel(key)}`, 'error');
      return;
    }
    notify(`Saved "${formatSettingsKeyLabel(key)}"`, 'success');
    await fetchSettings();
  };

  const objectNestedMap = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const T of objectKeys) {
      const data = settings[T] as Record<string, unknown> | undefined;
      const groupSch = schema ? buildGroupSchema(schema, T) : null;
      m.set(T, nestedObjectChildKeys(groupSch, data));
    }
    return m;
  }, [objectKeys, schema, settings]);

  /** When filter matches a rank-1 name or a rank-2 key, we reveal that group’s nested rows. */
  const filterExpandTops = useMemo(() => {
    const out = new Set<string>();
    const q = filter.trim().toLowerCase();
    if (!q) return out;
    for (const T of objectKeys) {
      const nested = objectNestedMap.get(T) || [];
      if (
        T.toLowerCase().includes(q) ||
        formatSettingsKeyLabel(T).toLowerCase().includes(q)
      ) {
        out.add(T);
        continue;
      }
      for (const sub of nested) {
        if (
          sub.toLowerCase().includes(q) ||
          formatSettingsKeyLabel(sub).toLowerCase().includes(q) ||
          `${T}.${sub}`.toLowerCase().includes(q)
        ) {
          out.add(T);
          break;
        }
      }
    }
    return out;
  }, [filter, objectKeys, objectNestedMap]);

  const navItems = useMemo((): SettingsNavItem[] => {
    const q = filter.trim().toLowerCase();
    const shouldShowRank2 = (T: string, nested: string[]) => {
      if (nested.length === 0) return false;
      if (activeGroupKey === T) return true;
      if (activeGroupKey && activeGroupKey.startsWith(`${T}.`)) return true;
      if (q) {
        if (T.toLowerCase().includes(q) || formatSettingsKeyLabel(T).toLowerCase().includes(q)) {
          return true;
        }
        if (filterExpandTops.has(T)) return true;
      }
      return false;
    };

    const out: SettingsNavItem[] = [];
    if (generalKeys.length) {
      out.push({ id: GENERAL_GROUP_KEY, depth: 0, label: 'General' });
    }
    for (const T of objectKeys) {
      const nested = objectNestedMap.get(T) || [];
      out.push({ id: T, depth: 0, label: formatSettingsKeyLabel(T) });
      if (shouldShowRank2(T, nested)) {
        for (const sub of nested) {
          out.push({ id: `${T}.${sub}`, depth: 1, label: formatSettingsKeyLabel(sub) });
        }
      }
    }
    return out;
  }, [activeGroupKey, filter, filterExpandTops, generalKeys, objectKeys, objectNestedMap]);

  const filteredNavItems = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return navItems;
    return navItems.filter((item) => {
      if (item.id === GENERAL_GROUP_KEY) return 'general'.includes(q);
      if (item.depth === 0 && filterExpandTops.has(item.id)) return true;
      const top = item.depth === 1 ? item.id.slice(0, item.id.indexOf('.')) : item.id;
      return (
        item.id.toLowerCase().includes(q) ||
        item.label.toLowerCase().includes(q) ||
        top.toLowerCase().includes(q)
      );
    });
  }, [filter, filterExpandTops, navItems]);

  const navIds = useMemo(() => filteredNavItems.map((i) => i.id), [filteredNavItems]);

  useEffect(() => {
    if (!navIds.length) {
      setActiveGroupKey(null);
      return;
    }
    if (activeGroupKey && navIds.includes(activeGroupKey)) return;
    setActiveGroupKey(navIds[0]);
  }, [activeGroupKey, navIds]);

  const generalSchema = useMemo(
    () => buildGeneralSchema(schema, generalKeys),
    [generalKeys, schema],
  );

  const activeValue = useMemo(() => {
    if (!activeGroupKey) return undefined;
    if (activeGroupKey === GENERAL_GROUP_KEY) {
      const out: Record<string, unknown> = {};
      for (const k of generalKeys) out[k] = settings[k];
      return out;
    }
    const dot = activeGroupKey.indexOf('.');
    if (dot > 0) {
      const top = activeGroupKey.slice(0, dot);
      const sub = activeGroupKey.slice(dot + 1);
      if (!objectKeys.includes(top)) return undefined;
      const parent = settings[top];
      if (!isTopLevelObjectGroup(parent)) return undefined;
      return (parent as Record<string, unknown>)[sub];
    }
    const top = activeGroupKey;
    if (!objectKeys.includes(top)) return undefined;
    const parent = settings[top];
    if (!isTopLevelObjectGroup(parent)) return undefined;
    const obj = parent as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (!isTopLevelObjectGroup(v)) out[k] = v;
    }
    return out;
  }, [activeGroupKey, generalKeys, objectKeys, settings]);

  const activeSchema = useMemo(() => {
    if (!activeGroupKey || !schema) return null;
    if (activeGroupKey === GENERAL_GROUP_KEY) return generalSchema;
    const dot = activeGroupKey.indexOf('.');
    if (dot > 0) {
      const top = activeGroupKey.slice(0, dot);
      const sub = activeGroupKey.slice(dot + 1);
      if (objectKeys.includes(top) && sub) {
        return buildNestedPropertySchema(schema, top, sub);
      }
    }
    if (!objectKeys.includes(activeGroupKey)) return null;
    const groupSch = buildGroupSchema(schema, activeGroupKey);
    const groupData = settings[activeGroupKey] as Record<string, unknown> | undefined;
    return buildScalarSubsetGroupSchema(groupSch, groupData);
  }, [activeGroupKey, generalSchema, objectKeys, schema, settings]);

  const activeDescription = useMemo(() => {
    if (!activeGroupKey) return null;
    if (activeGroupKey === GENERAL_GROUP_KEY) {
      return 'Scalar and other non-object top-level options. Nested configuration blocks appear as separate categories.';
    }
    if (!schema) return null;
    const dot = activeGroupKey.indexOf('.');
    if (dot > 0) {
      const top = activeGroupKey.slice(0, dot);
      const sub = activeGroupKey.slice(dot + 1);
      if (objectKeys.includes(top) && sub) {
        const groupSch = buildGroupSchema(schema, top);
        const subSch = groupSch?.properties?.[sub] as JsonSchema | undefined;
        if (subSch && typeof subSch === 'object' && typeof subSch.description === 'string') {
          const d = subSch.description.trim();
          if (d) return d;
        }
        return null;
      }
    }
    if (objectKeys.includes(activeGroupKey)) {
      const properties = schema.properties;
      if (!properties || typeof properties !== 'object') return null;
      const s = (properties as Record<string, JsonSchema>)[activeGroupKey];
      if (!s || typeof s !== 'object') return null;
      if (typeof s.description === 'string' && s.description.trim()) return s.description;
      return 'Simple fields on this group. Nested objects are listed in the sidebar.';
    }
    return null;
  }, [activeGroupKey, objectKeys, schema]);

  const activeGroupLabel = useMemo(() => {
    if (!activeGroupKey) return '';
    if (activeGroupKey === GENERAL_GROUP_KEY) return 'General';
    return formatSettingsRouteLabel(activeGroupKey);
  }, [activeGroupKey]);

  const isParentObjectScalarEmpty =
    !!activeGroupKey &&
    activeGroupKey !== GENERAL_GROUP_KEY &&
    !activeGroupKey.includes('.') &&
    objectKeys.includes(activeGroupKey) &&
    activeSchema === null;

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
          placeholder="Filter categories (e.g. general, content)"
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
      ) : !filteredNavItems.length ? (
        <p className="muted">No settings categories matched the filter.</p>
      ) : (
        <div className="settings-layout">
          <aside className="settings-sidebar">
            <div className="settings-sidebar__list">
              {filteredNavItems.map((item) => {
                const isActive = item.id === activeGroupKey;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`settings-sidebar__item${item.depth === 1 ? ' settings-sidebar__item--nested' : ''}${isActive ? ' is-active' : ''}`}
                    onClick={() => setActiveGroupKey(item.id)}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </aside>
          <section className="settings-editor">
            {activeGroupKey ? (
              <SettingsEditor
                groupKey={activeGroupKey}
                groupLabel={activeGroupLabel}
                value={activeValue}
                groupSchema={activeSchema}
                description={activeDescription}
                noSchemaSlot={
                  isParentObjectScalarEmpty ? (
                    <p className="muted">
                      Every field in <strong>{formatSettingsKeyLabel(activeGroupKey)}</strong> is a
                      nested object. Use the nested items in the sidebar to edit those sections.
                    </p>
                  ) : undefined
                }
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
  groupLabel,
  value,
  groupSchema,
  description,
  noSchemaSlot,
  onSaveJson,
  onSaveValue,
}: {
  groupKey: string;
  groupLabel: string;
  value: unknown;
  groupSchema: JsonSchema | null;
  description: string | null;
  noSchemaSlot?: ReactNode;
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
          <div className="settings-editor__title">{groupLabel}</div>
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
          groupLabel={groupLabel}
          value={value}
          schema={groupSchema}
          onSave={onSaveValue}
          noSchemaSlot={noSchemaSlot}
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
                  Save {groupLabel}
                </button>
              </div>
            </>
          }
        />
      </div>
    </div>
  );
}

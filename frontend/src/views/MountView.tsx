import { useCallback, useEffect, useState, useMemo } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiGet } from '../services/api';
import type { AppRoute } from '../app/routeTypes';

interface MountEntry {
  name: string;
  path: string;
}

export default function MountView({ route }: { route: AppRoute }) {
  const [entries, setEntries] = useState<MountEntry[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMount = useCallback(async () => {
    const response = await apiGet('/mount');
    if (!response.ok) {
      setError(response.error || 'Failed to load mount data.');
      setEntries([]);
      setLoading(false);
      return;
    }
    const files = response.data?.files ?? {};
    setEntries(
      Object.entries(files).map(([name, path]) => ({
        name,
        path: String(path),
      })),
    );
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchMount();
  }, [fetchMount]);

  const needle = search.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      !needle
        ? entries
        : entries.filter(
            (e) =>
              e.name.toLowerCase().includes(needle) ||
              e.path.toLowerCase().includes(needle),
          ),
    [entries, needle],
  );

  return (
    <ViewLayout className="view-mount" view="mount">
      <ViewHeader
        title="Mounted Files"
        subtitle="Current VFS mount inventory exposed by the backend filesystem service."
      />
      <Panel className="mount-panel">
        <div className="toolbar toolbar--mount">
          <input
            type="search"
            placeholder="Filter by file/path"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="mount-stats">
          {loading
            ? 'Loading…'
            : `${filtered.length.toLocaleString()} / ${entries.length.toLocaleString()} files`}
        </div>
        {error ? (
          <p className="muted">{error}</p>
        ) : filtered.length === 0 ? (
          <p className="muted">No matching mounted files.</p>
        ) : (
          <div className="mount-list">
            {filtered.map((entry) => (
              <div key={entry.name} className="mount-row">
                <strong title={entry.name}>{entry.name}</strong>
                <span className="muted" title={entry.path}>
                  {entry.path}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </ViewLayout>
  );
}

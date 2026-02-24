import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiGet } from '../services/api';
import type { AppRoute } from '../app/routeTypes';

export default function VfsStatsView({ route }: { route: AppRoute }) {
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    const response = await apiGet('/vfs_stats');
    if (!response.ok || !response.data?.stats) {
      setStats(null);
      setError('No VFS stats available.');
      return;
    }
    setStats(response.data.stats as Record<string, unknown>);
    setError(null);
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return (
    <ViewLayout className="view-vfs-stats" view="vfs-stats">
      <ViewHeader
        title="VFS Statistics"
        subtitle="Runtime statistics for mounted VFS opener operations."
      />
      <Panel>
        {error ? (
          <p className="muted">{error}</p>
        ) : stats && Object.keys(stats).length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Opener</th>
                <th>Metrics</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats).map(([name, metrics]) => (
                <tr key={name}>
                  <td>
                    <strong>{name}</strong>
                  </td>
                  <td>
                    <pre className="json-output">
                      {JSON.stringify(metrics, null, 2)}
                    </pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No VFS stats available.</p>
        )}
      </Panel>
    </ViewLayout>
  );
}

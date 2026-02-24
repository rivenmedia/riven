import { useCallback, useEffect, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../components/ui/PagePrimitives';
import { apiFetch, apiGet } from '../services/api';
import { notify } from '../services/notify';
import type { AppRoute } from '../app/routeTypes';

const QUICK_ENDPOINTS = [
  '/health',
  '/services',
  '/stats',
  '/events',
  '/vfs_stats',
  '/downloader_user_info',
];

function pretty(data: unknown): string {
  if (data === null || data === undefined) return '';
  if (typeof data === 'string') return data;
  return JSON.stringify(data, null, 2);
}

export default function InspectorView({ route }: { route: AppRoute }) {
  const [quickOutput, setQuickOutput] = useState('');
  const [runnerOutput, setRunnerOutput] = useState('');
  const [method, setMethod] = useState('GET');
  const [path, setPath] = useState('');
  const [body, setBody] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [logSearch, setLogSearch] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    setLogsLoading(true);
    const response = await apiGet('/logs');
    if (!response.ok) {
      setLogs([]);
      setLogsLoading(false);
      return;
    }
    setLogs(response.data?.logs ?? []);
    setLogsLoading(false);
  }, []);

  useEffect(() => {
    fetchLogs();
    const id = setInterval(fetchLogs, 5000);
    return () => clearInterval(id);
  }, [fetchLogs]);

  const filteredLogs = logSearch.trim()
    ? logs
        .map((raw, index) => ({ raw: String(raw), index: index + 1 }))
        .filter((row) =>
          row.raw.toLowerCase().includes(logSearch.toLowerCase()),
        )
        .reverse()
    : logs
        .map((raw, index) => ({ raw: String(raw), index: index + 1 }))
        .reverse();

  const handleQuickEndpoint = async (endpointPath: string) => {
    setQuickOutput('Loading…');
    const response = await apiGet(endpointPath);
    setQuickOutput(pretty(response.data ?? { error: response.error }));
  };

  const handleRunnerSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const pathTrimmed = path.trim();
    if (!pathTrimmed) {
      notify('Path is required', 'warning');
      return;
    }
    const options: RequestInit & { body?: BodyInit } = { method };
    if (method !== 'GET') {
      const rawBody = body.trim();
      options.body = rawBody || '{}';
    }
    setRunnerOutput('Running…');
    const response = await apiFetch(pathTrimmed, options);
    setRunnerOutput(
      pretty({
        ok: response.ok,
        status: response.status,
        error: response.error,
        data: response.data,
      }),
    );
  };

  return (
    <ViewLayout className="view-inspector" view="inspector">
      <ViewHeader
        title="Inspector"
        subtitle="Inspect backend internals, logs, and arbitrary API endpoint responses."
      />
      <div className="split-grid">
        <Panel>
          <div className="section-head">
            <h2>Quick Endpoints</h2>
          </div>
          <div className="quick-endpoints">
            {QUICK_ENDPOINTS.map((endpointPath) => (
              <button
                key={endpointPath}
                type="button"
                className="btn btn--secondary btn--small"
                onClick={() => handleQuickEndpoint(endpointPath)}
              >
                {endpointPath}
              </button>
            ))}
          </div>
          <pre className="json-output">{quickOutput || '\n'}</pre>
        </Panel>
        <Panel>
          <div className="section-head">
            <h2>Endpoint Runner</h2>
          </div>
          <form
            className="endpoint-form"
            onSubmit={handleRunnerSubmit}
          >
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="DELETE">DELETE</option>
            </select>
            <input
              type="text"
              placeholder="/stats"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
            <textarea
              placeholder='{"example":"payload"}'
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <button className="btn btn--primary" type="submit">
              Run
            </button>
          </form>
          <pre className="json-output">{runnerOutput || '\n'}</pre>
        </Panel>
      </div>
      <Panel>
        <div className="section-head">
          <h2>Logs (Virtualized)</h2>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={fetchLogs}
            >
              Refresh
            </button>
          </div>
        </div>
        <div className="log-toolbar">
          <input
            type="search"
            placeholder="Filter logs"
            value={logSearch}
            onChange={(e) => setLogSearch(e.target.value)}
          />
        </div>
        <div className="log-meta">
          {logsLoading
            ? 'Loading logs…'
            : `${filteredLogs.length.toLocaleString()} / ${logs.length.toLocaleString()} lines`}
        </div>
        <div className="log-container">
          {filteredLogs.length === 0 ? (
            <p className="muted">No logs matched.</p>
          ) : (
            <div className="log-list">
              {filteredLogs.map((row) => (
                <div
                  key={`${row.index}-${row.raw.slice(0, 40)}`}
                  className="log-row"
                  title={row.raw}
                >
                  <span className="muted">#{row.index}</span> {row.raw}
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>
    </ViewLayout>
  );
}

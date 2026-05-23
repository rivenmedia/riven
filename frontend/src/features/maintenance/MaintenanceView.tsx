import { useCallback, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiFetch } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import type { AppRoute } from '../../app/routeTypes';

interface TvScrapeCandidate {
  item_id: number;
  item_type: 'show' | 'season';
  title: string;
  reason: string;
  episode_count: number;
  streamless_count: number;
  streamless_ratio: number;
  recommended_reset: 'show' | 'season';
  show_id: number | null;
  details: string;
}

interface AnalyzeResponse {
  summary: { candidates: number; shows: number; seasons: number };
  candidates: TvScrapeCandidate[];
}

interface ApplyResponse {
  message: string;
  reset_ids: number[];
  requeued_count: number;
}

const REASON_LABELS: Record<string, string> = {
  empty_season: 'Empty season',
  sparse_season: 'Sparse season, no streams',
  streamless_majority: 'Majority missing streams',
  streamless_show: 'Multiple seasons need pack retry',
  incomplete_pack_scrape: 'Per-episode scrape, no season pack',
  incomplete_pack_show: 'Retry show pack scrape + download',
};

function formatPercent(ratio: number): string {
  if (ratio <= 0) return '—';
  return `${Math.round(ratio * 100)}%`;
}

export default function MaintenanceView({ route: _route }: { route: AppRoute }) {
  const [analyzing, setAnalyzing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [candidates, setCandidates] = useState<TvScrapeCandidate[]>([]);
  const [summary, setSummary] = useState<AnalyzeResponse['summary'] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [lastApply, setLastApply] = useState<ApplyResponse | null>(null);

  const runAnalyze = useCallback(async () => {
    setAnalyzing(true);
    setLastApply(null);
    const response = await apiFetch<AnalyzeResponse>('/maintenance/tv-scrape/analyze');
    setAnalyzing(false);

    if (!response.ok || !response.data) {
      notify(response.error || 'Analysis failed', 'error');
      return;
    }

    setCandidates(response.data.candidates);
    setSummary(response.data.summary);
    setSelected(new Set(response.data.candidates.map((c) => c.item_id)));
    notify(
      `Found ${response.data.summary.candidates} candidate(s)`,
      response.data.summary.candidates > 0 ? 'info' : 'success',
    );
  }, []);

  const allSelected = useMemo(
    () => candidates.length > 0 && selected.size === candidates.length,
    [candidates.length, selected.size],
  );

  const toggleAll = useCallback(() => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(candidates.map((c) => c.item_id)));
    }
  }, [allSelected, candidates]);

  const toggleOne = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleApply = useCallback(async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) {
      notify('Select at least one item', 'warning');
      return;
    }

    const confirmed = window.confirm(
      `Reset ${ids.length} show/season item(s)? This clears streams and scrape state, then re-queues pack scrape work for affected titles.`,
    );
    if (!confirmed) return;

    setApplying(true);
    setLastApply(null);
    const response = await apiFetch<ApplyResponse>('/maintenance/tv-scrape/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_ids: ids, requeue: true }),
    });
    setApplying(false);

    if (!response.ok || !response.data) {
      notify(response.error || 'Cleanup failed', 'error');
      return;
    }

    setLastApply(response.data);
    notify(response.data.message || 'Cleanup complete', 'success');
    void runAnalyze();
  }, [selected, runAnalyze]);

  return (
    <ViewLayout className="view-maintenance" view="maintenance">
      <ViewHeader
        title="Maintenance"
        subtitle="Analyze library health and apply targeted cleanup without editing the database by hand."
      />

      <Panel>
        <h2 className="panel-section-title">TV scrape health</h2>
        <p className="panel-hint">
          Finds broken pack-scrape states: episodes missing streams after a pack attempt,
          per-episode scraping without a season/show pack, or empty seasons. Reset
          clears scrape state so the pipeline can retry show/season pack scrape and
          pack download.
        </p>
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={analyzing}
            onClick={() => void runAnalyze()}
          >
            {analyzing ? 'Analyzing…' : summary ? 'Re-analyze' : 'Analyze'}
          </button>
          <button
            type="button"
            className="btn btn--danger"
            disabled={applying || selected.size === 0}
            onClick={() => void handleApply()}
          >
            {applying ? 'Applying…' : `Apply cleanup (${selected.size})`}
          </button>
        </div>

        {summary && (
          <p className="maintenance-summary">
            Found <strong>{summary.candidates}</strong> candidate(s):{' '}
            {summary.shows} show row(s), {summary.seasons} season row(s).
          </p>
        )}

        {candidates.length > 0 ? (
          <div className="maintenance-table-wrap">
            <table className="maintenance-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      checked={allSelected}
                      aria-label="Select all"
                      onChange={toggleAll}
                    />
                  </th>
                  <th>Title</th>
                  <th>Type</th>
                  <th>Issue</th>
                  <th>Episodes</th>
                  <th>Indiv. scraped</th>
                  <th>Reset</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((row) => (
                  <tr key={row.item_id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(row.item_id)}
                        aria-label={`Select ${row.title}`}
                        onChange={() => toggleOne(row.item_id)}
                      />
                    </td>
                    <td>
                      <div className="maintenance-title">{row.title}</div>
                      <div className="maintenance-details">{row.details}</div>
                    </td>
                    <td>{row.item_type}</td>
                    <td>{REASON_LABELS[row.reason] ?? row.reason}</td>
                    <td>{row.episode_count}</td>
                    <td>
                      {row.streamless_count}
                      {row.streamless_ratio > 0
                        ? ` (${formatPercent(row.streamless_ratio)})`
                        : ''}
                    </td>
                    <td>{row.recommended_reset}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : summary ? (
          !analyzing && (
            <p className="panel-hint">No TV scrape issues detected.</p>
          )
        ) : (
          !analyzing && (
            <p className="panel-hint">Click Analyze to scan your library.</p>
          )
        )}

        {lastApply && (
          <pre className="json-output maintenance-summary-output">
            {JSON.stringify(lastApply, null, 2)}
          </pre>
        )}
      </Panel>
    </ViewLayout>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiGet } from '../../shared/api/api';
import { formatBytes } from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';

interface StreamStat {
  path: string;
  filename: string;
  original_filename: string;
  file_size: number;
  position: number;
  progress_pct: number;
  provider: string;
  bytes_transferred: number;
  download_speed_bps: number;
  is_streaming: boolean;
  connections: number;
}

interface CacheStat {
  hits: number;
  misses: number;
  bytes_from_cache: number;
  bytes_written: number;
  evictions: number;
  total_bytes?: number;
  entries?: number;
}

interface VfsStatsData {
  streams: Record<string, StreamStat>;
  cache: CacheStat;
}

function formatSpeed(bps: number): string {
  if (bps <= 0) return '0 B/s';
  return `${formatBytes(bps)}/s`;
}

function hitRate(cache: CacheStat): string {
  const hits = cache.hits ?? 0;
  const misses = cache.misses ?? 0;
  const total = hits + misses;
  if (total === 0) return '—';
  return `${((hits / total) * 100).toFixed(1)}%`;
}

function ProgressBar({ pct }: { pct: number }) {
  const clamped = Math.min(100, Math.max(0, pct));
  return (
    <div style={{ background: 'var(--surface-2, #2a2a2a)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
      <div
        style={{
          width: `${clamped}%`,
          height: '100%',
          background: 'var(--accent, #5b8ef0)',
          transition: 'width 1s linear',
        }}
      />
    </div>
  );
}

function StreamCard({ stat }: { stat: StreamStat }) {
  return (
    <div style={{ padding: '1rem', borderRadius: 6, background: 'var(--surface-1, #1e1e1e)', marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
        <div>
          <strong style={{ fontSize: '0.95rem' }}>{stat.filename}</strong>
          <div style={{ fontSize: '0.78rem', opacity: 0.6, marginTop: 2 }}>{stat.path}</div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: '1rem' }}>
          <span
            style={{
              fontSize: '0.75rem',
              padding: '2px 8px',
              borderRadius: 99,
              background: stat.is_streaming ? 'var(--green, #4caf50)' : 'var(--surface-3, #333)',
              color: stat.is_streaming ? '#fff' : 'inherit',
            }}
          >
            {stat.is_streaming ? 'Streaming' : 'Idle'}
          </span>
          <div style={{ fontSize: '0.78rem', opacity: 0.6, marginTop: 4 }}>{stat.provider}</div>
        </div>
      </div>

      <ProgressBar pct={stat.progress_pct} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: '0.5rem',
          marginTop: '0.75rem',
          fontSize: '0.82rem',
        }}
      >
        <Metric label="Progress" value={`${stat.progress_pct}%`} />
        <Metric label="Position" value={formatBytes(stat.position)} />
        <Metric label="File size" value={formatBytes(stat.file_size)} />
        <Metric label="Downloaded" value={formatBytes(stat.bytes_transferred)} />
        <Metric label="Speed" value={formatSpeed(stat.download_speed_bps)} />
        <Metric label="Connections" value={String(stat.connections)} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ opacity: 0.55, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ fontVariantNumeric: 'tabular-nums' }}>{value || '—'}</div>
    </div>
  );
}

function CachePanel({ cache }: { cache: CacheStat }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
        gap: '0.6rem',
        fontSize: '0.85rem',
      }}
    >
      <Metric label="Hit rate" value={hitRate(cache)} />
      <Metric label="Hits" value={(cache.hits ?? 0).toLocaleString()} />
      <Metric label="Misses" value={(cache.misses ?? 0).toLocaleString()} />
      <Metric label="Bytes served from cache" value={formatBytes(cache.bytes_from_cache ?? 0)} />
      <Metric label="Bytes written to cache" value={formatBytes(cache.bytes_written ?? 0)} />
      <Metric label="Evictions" value={(cache.evictions ?? 0).toLocaleString()} />
      {cache.total_bytes != null && <Metric label="Cache size" value={formatBytes(cache.total_bytes)} />}
      {cache.entries != null && <Metric label="Cache entries" value={String(cache.entries)} />}
    </div>
  );
}

const POLL_INTERVAL_MS = 3000;

export default function VfsStatsView({ route }: { route: AppRoute }) {
  const [data, setData] = useState<VfsStatsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStats = useCallback(async () => {
    const response = await apiGet('/vfs_stats');
    if (!response.ok || !response.data) {
      setError('VFS stats unavailable.');
      return;
    }
    setData(response.data as VfsStatsData);
    setError(null);
  }, []);

  useEffect(() => {
    fetchStats();
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchStats]);

  const streams = data ? Object.values(data.streams) : [];
  const cache = data?.cache ?? null;

  return (
    <ViewLayout className="view-vfs-stats" view="vfs-stats">
      <ViewHeader
        title="VFS Statistics"
        subtitle="Live streaming sessions and chunk-cache metrics. Refreshes every 3 seconds."
      />

      {cache && (
        <Panel>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '1rem' }}>Cache Metrics</h2>
          <CachePanel cache={cache} />
        </Panel>
      )}

      <Panel>
        <h2 style={{ marginBottom: '0.75rem', fontSize: '1rem' }}>Active Streams</h2>
        {error ? (
          <p className="muted">{error}</p>
        ) : streams.length === 0 ? (
          <p className="muted">No active streams.</p>
        ) : (
          streams.map((s) => <StreamCard key={s.path + s.original_filename} stat={s} />)
        )}
      </Panel>
    </ViewLayout>
  );
}

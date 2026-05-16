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

interface VfsLibraryStat {
  total_bytes: number;
  movies_bytes: number;
  tv_bytes: number;
}

interface ThroughputStat {
  network_bytes_ingested: number;
  client_bytes_served_warm: number;
  client_bytes_served_cold: number;
  client_warm_byte_ratio: number | null;
}

interface ThroughputSample {
  t: number;
  networkBps: number;
  warmBps: number;
  coldBps: number;
}

interface VfsStatsData {
  streams: Record<string, StreamStat>;
  cache: CacheStat;
  library: VfsLibraryStat;
  throughput: ThroughputStat;
}

function formatSpeed(bps: number): string {
  if (bps <= 0) return '0 B/s';
  return `${formatBytes(bps)}/s`;
}

function chunkGetSuccessRate(cache: CacheStat): string {
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

function ThroughputLineChart({ series }: { series: ThroughputSample[] }) {
  const w = 720;
  const h = 168;
  const padL = 6;
  const padR = 6;
  const padT = 10;
  const padB = 6;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  if (series.length === 0) {
    return (
      <p className="muted" style={{ margin: '0.5rem 0 0', fontSize: '0.82rem' }}>
        Chart builds after a few refreshes (3s polling). Current totals are above.
      </p>
    );
  }

  let maxV = 1;
  for (const s of series) {
    maxV = Math.max(maxV, s.networkBps, s.warmBps, s.coldBps);
  }

  const n = series.length;
  const xAt = (i: number) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (v: number) => padT + plotH - (v / maxV) * plotH;

  const pointsFor = (key: keyof Pick<ThroughputSample, 'networkBps' | 'warmBps' | 'coldBps'>): string =>
    series.map((s, i) => `${xAt(i)},${yAt(s[key])}`).join(' ');

  return (
    <svg
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-label="Throughput over recent polls"
      style={{ display: 'block', marginTop: '0.75rem' }}
    >
      <line
        x1={padL}
        y1={padT + plotH}
        x2={padL + plotW}
        y2={padT + plotH}
        stroke="var(--surface-3, #444)"
        strokeWidth={1}
      />
      <polyline
        fill="none"
        stroke="var(--amber, #e6a23c)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={pointsFor('networkBps')}
      />
      <polyline
        fill="none"
        stroke="var(--green, #4caf50)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={pointsFor('warmBps')}
      />
      <polyline
        fill="none"
        stroke="var(--accent, #5b8ef0)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={pointsFor('coldBps')}
      />
    </svg>
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

/** 0° = top, clockwise positive */
function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function pieSlicePath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  if (endDeg - startDeg <= 0.01) return '';
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function LibraryPanel({ library }: { library: VfsLibraryStat }) {
  const { total_bytes, movies_bytes, tv_bytes } = library;
  const videoSplit = movies_bytes + tv_bytes;
  const moviePctOfSplit = videoSplit > 0 ? (movies_bytes / videoSplit) * 100 : 0;
  const tvPctOfSplit = videoSplit > 0 ? (tv_bytes / videoSplit) * 100 : 0;
  const otherBytes = Math.max(0, total_bytes - movies_bytes - tv_bytes);

  const cx = 50;
  const cy = 50;
  const r = 38;
  let a0 = -90;
  const movieEnd = a0 + (360 * moviePctOfSplit) / 100;
  const moviePath = videoSplit > 0 ? pieSlicePath(cx, cy, r, a0, movieEnd) : '';
  const tvPath =
    videoSplit > 0 && tv_bytes > 0 ? pieSlicePath(cx, cy, r, movieEnd, a0 + 360) : '';

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '1.5rem 2.5rem',
        alignItems: 'flex-start',
        justifyContent: 'flex-start',
      }}
    >
      <div style={{ flex: '0 1 auto', minWidth: 0, maxWidth: 'min(28rem, 100%)' }}>
        <h2 style={{ margin: '0 0 0.75rem', fontSize: '1rem' }}>Library in VFS</h2>
        <Metric label="Total VFS (video files)" value={formatBytes(total_bytes)} />
        {otherBytes > 0 && (
          <p style={{ margin: '0.6rem 0 0', fontSize: '0.78rem', opacity: 0.65 }}>
            Other / unlinked in DB: {formatBytes(otherBytes)} (
            {total_bytes > 0 ? ((otherBytes / total_bytes) * 100).toFixed(1) : '0'}% of total)
          </p>
        )}
      </div>

      <div
        style={{
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'nowrap',
          flex: '0 1 auto',
        }}
      >
        {videoSplit > 0 ? (
          <svg width={140} height={140} viewBox="0 0 100 100" aria-label="Movies versus TV by size">
            {moviePath && (
              <path d={moviePath} fill="var(--accent, #5b8ef0)" stroke="var(--surface-1, #1a1a1a)" strokeWidth={0.5} />
            )}
            {tvPath && (
              <path d={tvPath} fill="var(--green, #4caf50)" stroke="var(--surface-1, #1a1a1a)" strokeWidth={0.5} />
            )}
          </svg>
        ) : (
          <p className="muted" style={{ margin: 0, maxWidth: 220 }}>
            No movie or episode files in the VFS yet (sizes are split by linked library type).
          </p>
        )}
        {videoSplit > 0 && (
          <div style={{ fontSize: '0.82rem', lineHeight: 1.6 }}>
            <div>
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: 'var(--accent, #5b8ef0)',
                  marginRight: 8,
                  verticalAlign: 'middle',
                }}
              />
              Movies{' '}
              <span style={{ opacity: 0.85, fontVariantNumeric: 'tabular-nums' }}>
                {moviePctOfSplit.toFixed(1)}% · {formatBytes(movies_bytes)}
              </span>
            </div>
            <div>
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: 'var(--green, #4caf50)',
                  marginRight: 8,
                  verticalAlign: 'middle',
                }}
              />
              TV (episodes){' '}
              <span style={{ opacity: 0.85, fontVariantNumeric: 'tabular-nums' }}>
                {tvPctOfSplit.toFixed(1)}% · {formatBytes(tv_bytes)}
              </span>
            </div>
            <div style={{ marginTop: 6, opacity: 0.55, fontSize: '0.75rem' }}>
              Percentages are by movie + TV bytes only.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function cacheReadAmplification(cache: CacheStat): string {
  const w = cache.bytes_written ?? 0;
  const r = cache.bytes_from_cache ?? 0;
  if (w <= 0) return '—';
  return `${(r / w).toFixed(2)}×`;
}

function CachePanel({ cache }: { cache: CacheStat }) {
  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
          gap: '0.6rem',
          fontSize: '0.85rem',
        }}
      >
        <Metric label="Chunk get success" value={chunkGetSuccessRate(cache)} />
        <Metric label="Chunk get hits" value={(cache.hits ?? 0).toLocaleString()} />
        <Metric label="Chunk get misses" value={(cache.misses ?? 0).toLocaleString()} />
        <Metric label="Bytes read (chunk cache)" value={formatBytes(cache.bytes_from_cache ?? 0)} />
        <Metric label="Bytes written (chunk cache)" value={formatBytes(cache.bytes_written ?? 0)} />
        <Metric label="Read / write ratio" value={cacheReadAmplification(cache)} />
        <Metric label="Evictions" value={(cache.evictions ?? 0).toLocaleString()} />
        {cache.total_bytes != null && <Metric label="Cache size on disk" value={formatBytes(cache.total_bytes)} />}
        {cache.entries != null && <Metric label="Cache entries" value={String(cache.entries)} />}
      </div>
      <p style={{ margin: '0.65rem 0 0', fontSize: '0.75rem', opacity: 0.55, lineHeight: 1.45 }}>
        Chunk metrics count disk cache <code style={{ fontSize: '0.85em' }}>get</code>/<code style={{ fontSize: '0.85em' }}>put</code>{' '}
        operations. After a fresh download, <code style={{ fontSize: '0.85em' }}>get</code>s still register as hits—use{' '}
        <strong>Data origin</strong> above for true warm (disk-only) vs cold (needed network for this read) client bytes.
      </p>
    </div>
  );
}

function ThroughputPanel({ tp, series }: { tp: ThroughputStat; series: ThroughputSample[] }) {
  const warmPct =
    tp.client_warm_byte_ratio != null ? `${(tp.client_warm_byte_ratio * 100).toFixed(1)}%` : '—';
  const clientTotal = (tp.client_bytes_served_warm ?? 0) + (tp.client_bytes_served_cold ?? 0);

  return (
    <div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: '0.6rem',
          fontSize: '0.85rem',
        }}
      >
        <Metric label="Network ingress (cumulative)" value={formatBytes(tp.network_bytes_ingested)} />
        <Metric label="Client bytes (warm)" value={formatBytes(tp.client_bytes_served_warm)} />
        <Metric label="Client bytes (cold)" value={formatBytes(tp.client_bytes_served_cold)} />
        <Metric label="Warm share of client reads" value={warmPct} />
        <Metric label="Client bytes (total)" value={formatBytes(clientTotal)} />
      </div>
      <p style={{ margin: '0.65rem 0 0', fontSize: '0.75rem', opacity: 0.55, lineHeight: 1.45 }}>
        <strong>Warm</strong>: read satisfied as <code style={{ fontSize: '0.85em' }}>cache_hit</code> (already on disk for
        that request). <strong>Cold</strong>: playback body path, header/footer scans, etc. Chart shows average B/s since the
        last poll (3s window).
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '0.35rem', fontSize: '0.78rem', opacity: 0.85 }}>
        <span>
          <span style={{ color: 'var(--amber, #e6a23c)', fontWeight: 600 }}>—</span> Network
        </span>
        <span>
          <span style={{ color: 'var(--green, #4caf50)', fontWeight: 600 }}>—</span> Warm to client
        </span>
        <span>
          <span style={{ color: 'var(--accent, #5b8ef0)', fontWeight: 600 }}>—</span> Cold to client
        </span>
      </div>
      <ThroughputLineChart series={series} />
    </div>
  );
}

const POLL_INTERVAL_MS = 3000;
const THROUGHPUT_HISTORY_MAX = 120;

export default function VfsStatsView({ route }: { route: AppRoute }) {
  const [data, setData] = useState<VfsStatsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [throughputSeries, setThroughputSeries] = useState<ThroughputSample[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastThroughputRef = useRef<ThroughputStat | null>(null);
  const lastPerfRef = useRef<number | null>(null);

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

  useEffect(() => {
    const raw = data?.throughput;
    if (!raw) return;

    const now = performance.now();
    const prev = lastThroughputRef.current;
    const prevT = lastPerfRef.current;

    if (prev !== null && prevT !== null) {
      const dt = (now - prevT) / 1000;
      if (dt > 0) {
        const dNet = raw.network_bytes_ingested - prev.network_bytes_ingested;
        const dWarm = raw.client_bytes_served_warm - prev.client_bytes_served_warm;
        const dCold = raw.client_bytes_served_cold - prev.client_bytes_served_cold;
        if (dNet >= 0 && dWarm >= 0 && dCold >= 0) {
          setThroughputSeries((buf) => {
            const next = [
              ...buf,
              {
                t: Date.now(),
                networkBps: dNet / dt,
                warmBps: dWarm / dt,
                coldBps: dCold / dt,
              },
            ];
            return next.length > THROUGHPUT_HISTORY_MAX ? next.slice(-THROUGHPUT_HISTORY_MAX) : next;
          });
        }
      }
    }

    lastThroughputRef.current = raw;
    lastPerfRef.current = now;
  }, [data]);

  const streams = data ? Object.values(data.streams) : [];
  const cache = data?.cache ?? null;
  const library = data?.library ?? null;
  const throughput = data?.throughput ?? null;

  return (
    <ViewLayout className="view-vfs-stats" view="vfs-stats">
      <ViewHeader
        title="VFS Statistics"
        subtitle="Library size, data origin (warm vs cold reads), chunk-cache metrics, live streams. Refreshes every 3 seconds."
      />

      {library && (
        <Panel>
          <LibraryPanel library={library} />
        </Panel>
      )}

      {throughput && (
        <Panel>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '1rem' }}>Data origin (VFS-wide)</h2>
          <ThroughputPanel tp={throughput} series={throughputSeries} />
        </Panel>
      )}

      {cache && (
        <Panel>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '1rem' }}>Chunk cache (disk)</h2>
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

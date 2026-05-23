import { useCallback, useEffect, useRef, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { PieChart, type PieChartSlice } from '../../shared/ui/PieChart';
import { apiGet } from '../../shared/api/api';
import { formatBytes } from '../../shared/utils/utils';
import { humanizeServiceKey } from '../dashboard/serviceSetupMessages';
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

interface VfsProviderSlice {
  provider: string;
  file_count: number;
  bytes: number;
}

interface VfsProviderDistribution {
  total_files: number;
  slices: VfsProviderSlice[];
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
  providers: VfsProviderDistribution;
}

const PROVIDER_CHART_COLORS: Record<string, string> = {
  realdebrid: 'var(--amber, #e6a23c)',
  torbox: 'var(--green, #4caf50)',
  alldebrid: 'var(--accent, #5b8ef0)',
  debridlink: '#c678dd',
};

const PROVIDER_CHART_FALLBACK_COLORS = [
  'var(--accent, #5b8ef0)',
  'var(--green, #4caf50)',
  'var(--amber, #e6a23c)',
  '#c678dd',
  '#56b6c2',
];

function providerChartColor(provider: string, index: number): string {
  return PROVIDER_CHART_COLORS[provider] ?? PROVIDER_CHART_FALLBACK_COLORS[index % PROVIDER_CHART_FALLBACK_COLORS.length];
}

function providerChartLabel(provider: string): string {
  if (provider === 'unknown') return 'Unknown';
  return humanizeServiceKey(provider);
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

const CHART_WINDOW = 50;

function ThroughputLineChart({ series }: { series: ThroughputSample[] }) {
  const w = 720;
  const h = 94;
  const padL = 6;
  const padR = 6;
  const padT = 10;
  const padB = 6;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const windowSeries = series.slice(-CHART_WINDOW);
  const n = windowSeries.length;
  const slots = CHART_WINDOW;

  let maxV = 1;
  for (const s of windowSeries) {
    maxV = Math.max(maxV, s.networkBps, s.warmBps, s.coldBps);
  }

  const xAt = (i: number) => {
    const slot = slots - n + i;
    return padL + (slot / (slots - 1)) * plotW;
  };
  const yAt = (v: number) => padT + plotH - (v / maxV) * plotH;

  const pointsFor = (key: keyof Pick<ThroughputSample, 'networkBps' | 'warmBps' | 'coldBps'>): string =>
    windowSeries.map((s, i) => `${xAt(i)},${yAt(s[key])}`).join(' ');

  return (
    <div style={{ marginTop: '0.75rem' }}>
      <svg
        width="100%"
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        aria-label="Throughput over recent polls"
        style={{ display: 'block' }}
      >
        <line
          x1={padL}
          y1={padT + plotH}
          x2={padL + plotW}
          y2={padT + plotH}
          stroke="var(--surface-3, #444)"
          strokeWidth={1}
        />
        {n > 0 && (
          <>
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
          </>
        )}
      </svg>
      {n === 0 && (
        <p className="muted" style={{ margin: '0.35rem 0 0', fontSize: '0.82rem' }}>
          Chart builds after a few refreshes (3s polling). Current totals are above.
        </p>
      )}
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

function LibraryPanel({
  library,
  providers,
}: {
  library: VfsLibraryStat;
  providers: VfsProviderDistribution;
}) {
  const { total_bytes, movies_bytes, tv_bytes } = library;
  const otherBytes = Math.max(0, total_bytes - movies_bytes - tv_bytes);

  const typeSlices: PieChartSlice[] = [];
  if (movies_bytes > 0) {
    typeSlices.push({
      id: 'movies',
      label: 'Movies',
      value: movies_bytes,
      color: 'var(--accent, #5b8ef0)',
      subtext: formatBytes(movies_bytes),
    });
  }
  if (tv_bytes > 0) {
    typeSlices.push({
      id: 'tv',
      label: 'TV (episodes)',
      value: tv_bytes,
      color: 'var(--green, #4caf50)',
      subtext: formatBytes(tv_bytes),
    });
  }

  const providerSlices: PieChartSlice[] = providers.slices
    .filter((s) => s.file_count > 0)
    .map((s, i) => ({
      id: s.provider,
      label: providerChartLabel(s.provider),
      value: s.file_count,
      color: providerChartColor(s.provider, i),
      subtext:
        s.file_count === 1 ? '1 file' : `${s.file_count.toLocaleString()} files`,
    }));

  const pieColumnStyle = {
    flex: '1 1 0',
    minWidth: 'min(12rem, 100%)',
    display: 'flex',
    justifyContent: 'center',
  } as const;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'flex-start',
        gap: '1rem 1.5rem',
        width: '100%',
      }}
    >
      <div
        style={{
          flex: '0 1 auto',
          minWidth: 0,
          maxWidth: 'min(14rem, 100%)',
          display: 'flex',
          justifyContent: 'flex-start',
        }}
      >
        <div style={{ minWidth: 0, maxWidth: '100%' }}>
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1rem' }}>Library in VFS</h2>
          <Metric label="Total VFS (video files)" value={formatBytes(total_bytes)} />
          {otherBytes > 0 && (
            <p style={{ margin: '0.6rem 0 0', fontSize: '0.78rem', opacity: 0.65 }}>
              Other / unlinked in DB: {formatBytes(otherBytes)} (
              {total_bytes > 0 ? ((otherBytes / total_bytes) * 100).toFixed(1) : '0'}% of total)
            </p>
          )}
        </div>
      </div>

      <div style={pieColumnStyle}>
        <PieChart
          slices={typeSlices}
          ariaLabel="Movies versus TV by size"
          footnote="Percentages are by movie + TV bytes only."
          emptyMessage="No movie or episode files in the VFS yet (sizes are split by linked library type)."
        />
      </div>

      <div style={pieColumnStyle}>
        <PieChart
          slices={providerSlices}
          ariaLabel="Debrid provider distribution by file count"
          footnote="By file count in VFS."
          emptyMessage="No video files in the VFS yet."
        />
      </div>
    </div>
  );
}

function ChunkCacheMetrics({ cache }: { cache: CacheStat }) {
  const evictions = cache.evictions ?? 0;

  return (
    <div style={{ minWidth: 0, width: '100%' }}>
      <h3 style={{ margin: '0 0 0.6rem', fontSize: '0.88rem', fontWeight: 600 }}>Chunk cache (disk)</h3>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          gap: '0.55rem 1rem',
          fontSize: '0.85rem',
        }}
      >
        <Metric label="Hit rate" value={chunkGetSuccessRate(cache)} />
        <Metric label="Served from cache" value={formatBytes(cache.bytes_from_cache ?? 0)} />
        {cache.total_bytes != null && <Metric label="Size on disk" value={formatBytes(cache.total_bytes)} />}
        {cache.entries != null && (
          <Metric label="Cached chunks" value={(cache.entries ?? 0).toLocaleString()} />
        )}
        {evictions > 0 && <Metric label="Evictions" value={evictions.toLocaleString()} />}
      </div>
    </div>
  );
}

function ThroughputLegendItem({
  color,
  label,
  title,
}: {
  color: string;
  label: string;
  title: string;
}) {
  return (
    <span title={title} style={{ cursor: 'help' }}>
      <span style={{ color, fontWeight: 600 }}>—</span> {label}
    </span>
  );
}

function DataOriginPanel({
  tp,
  series,
  cache,
}: {
  tp: ThroughputStat;
  series: ThroughputSample[];
  cache: CacheStat | null;
}) {
  const warm = tp.client_bytes_served_warm ?? 0;
  const cold = tp.client_bytes_served_cold ?? 0;
  const clientTotal = warm + cold;

  const clientSlices: PieChartSlice[] = [];
  if (warm > 0) {
    clientSlices.push({
      id: 'cached',
      label: 'Cached',
      value: warm,
      color: 'var(--green, #4caf50)',
      subtext: formatBytes(warm),
      tooltip: 'Read satisfied as cache_hit (already on disk for that request).',
    });
  }
  if (cold > 0) {
    clientSlices.push({
      id: 'uncached',
      label: 'Uncached',
      value: cold,
      color: 'var(--accent, #5b8ef0)',
      subtext: formatBytes(cold),
      tooltip: 'Playback body path, header/footer scans, and other non-cache_hit paths.',
    });
  }

  const columnStyle = {
    flex: '1 1 0',
    minWidth: 'min(14rem, 100%)',
    display: 'flex',
    justifyContent: 'center',
  } as const;

  return (
    <div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          gap: '1rem 1.5rem',
          width: '100%',
        }}
      >
        <div style={{ ...columnStyle, alignItems: 'center' }}>
          <PieChart
            slices={clientSlices}
            ariaLabel="Cached versus uncached client bytes served"
            footnote="By cumulative client bytes since mount."
            emptyMessage="No client reads recorded yet."
          />
        </div>

        <div
          style={{
            ...columnStyle,
            flex: '0 1 auto',
            flexDirection: 'column',
            alignItems: 'flex-start',
            justifyContent: 'flex-start',
          }}
        >
          <h3 style={{ margin: '0 0 0.6rem', fontSize: '0.88rem', fontWeight: 600 }}>Network</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem', fontSize: '0.85rem' }}>
            <Metric label="Ingress (cumulative)" value={formatBytes(tp.network_bytes_ingested)} />
            <Metric label="Client bytes (total)" value={formatBytes(clientTotal)} />
          </div>
        </div>

        {cache != null && (
          <div style={{ ...columnStyle, justifyContent: 'flex-start' }}>
            <ChunkCacheMetrics cache={cache} />
          </div>
        )}
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '1rem',
          marginTop: '0.75rem',
          fontSize: '0.78rem',
          opacity: 0.85,
        }}
      >
        <ThroughputLegendItem
          color="var(--amber, #e6a23c)"
          label="Network"
          title="HTTP body bytes ingested from providers. Chart: average B/s per 3s poll."
        />
        <ThroughputLegendItem
          color="var(--green, #4caf50)"
          label="Cached (warm)"
          title="Client bytes served warm (cache_hit). Chart: average B/s per 3s poll."
        />
        <ThroughputLegendItem
          color="var(--accent, #5b8ef0)"
          label="Uncached (cold)"
          title="Client bytes served via cold paths. Chart: average B/s per 3s poll."
        />
      </div>
      <ThroughputLineChart series={series} />
    </div>
  );
}

const POLL_INTERVAL_MS = 3000;
const THROUGHPUT_HISTORY_MAX = CHART_WINDOW;

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
  const providers = data?.providers ?? null;
  const throughput = data?.throughput ?? null;

  return (
    <ViewLayout className="view-vfs-stats" view="vfs-stats">
      <ViewHeader
        title="VFS Statistics"
        subtitle="Library size, VFS cache (cached vs uncached reads, chunk cache), live streams. Refreshes every 3 seconds."
      />

      {library && providers && (
        <Panel>
          <LibraryPanel library={library} providers={providers} />
        </Panel>
      )}

      {throughput && (
        <Panel>
          <h2 style={{ marginBottom: '0.75rem', fontSize: '1rem' }}>VFS Cache</h2>
          <DataOriginPanel tp={throughput} series={throughputSeries} cache={cache} />
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

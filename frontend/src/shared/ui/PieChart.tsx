export type PieChartSlice = {
  id: string;
  label: string;
  value: number;
  color: string;
  subtext?: string;
  tooltip?: string;
};

export type PieChartProps = {
  slices: PieChartSlice[];
  size?: number;
  ariaLabel: string;
  footnote?: string;
  emptyMessage?: string;
};

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

function PieLegendRow({
  color,
  label,
  pct,
  subtext,
  tooltip,
}: {
  color: string;
  label: string;
  pct: number;
  subtext?: string;
  tooltip?: string;
}) {
  return (
    <div
      style={{ marginBottom: '0.35rem', cursor: tooltip ? 'help' : undefined }}
      title={tooltip}
    >
      <div style={{ fontSize: '0.82rem', lineHeight: 1.35, fontVariantNumeric: 'tabular-nums' }}>
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            borderRadius: 2,
            background: color,
            marginRight: 8,
            verticalAlign: 'middle',
            flexShrink: 0,
          }}
        />
        {label} {pct.toFixed(1)}%
      </div>
      {subtext != null && subtext !== '' && (
        <div
          style={{
            marginLeft: 18,
            fontSize: '0.75rem',
            lineHeight: 1.3,
            opacity: 0.65,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {subtext}
        </div>
      )}
    </div>
  );
}

export function PieChart({
  slices,
  size = 140,
  ariaLabel,
  footnote,
  emptyMessage = 'No data yet.',
}: PieChartProps) {
  const active = slices.filter((s) => s.value > 0);
  const total = active.reduce((sum, s) => sum + s.value, 0);

  if (total <= 0) {
    return (
      <p className="muted" style={{ margin: 0, maxWidth: 220, fontSize: '0.82rem' }}>
        {emptyMessage}
      </p>
    );
  }

  const cx = 50;
  const cy = 50;
  const r = 38;
  let angle = -90;
  const paths: { id: string; d: string; color: string }[] = [];
  for (const slice of active) {
    const sweep = (360 * slice.value) / total;
    const end = angle + sweep;
    const d = pieSlicePath(cx, cy, r, angle, end);
    if (d) paths.push({ id: slice.id, d, color: slice.color });
    angle = end;
  }

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'center',
        flexWrap: 'nowrap',
        flex: '0 1 auto',
      }}
    >
      <svg width={size} height={size} viewBox="0 0 100 100" aria-label={ariaLabel} style={{ flexShrink: 0 }}>
        {paths.map((p) => (
          <path
            key={p.id}
            d={p.d}
            fill={p.color}
            stroke="var(--surface-1, #1a1a1a)"
            strokeWidth={0.5}
          />
        ))}
      </svg>
      <div style={{ minWidth: 0 }}>
        {active.map((slice) => (
          <PieLegendRow
            key={slice.id}
            color={slice.color}
            label={slice.label}
            pct={(slice.value / total) * 100}
            subtext={slice.subtext}
            tooltip={slice.tooltip}
          />
        ))}
        {footnote != null && footnote !== '' && (
          <div style={{ marginTop: 4, opacity: 0.55, fontSize: '0.75rem', lineHeight: 1.35 }}>{footnote}</div>
        )}
      </div>
    </div>
  );
}

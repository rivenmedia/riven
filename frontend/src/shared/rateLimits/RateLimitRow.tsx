import type { LimiterSnapshot } from './types';

function barModifier(lim: LimiterSnapshot): string {
  if (lim.breaker_state === 'OPEN' || lim.breaker_state === 'HALF_OPEN') {
    return 'rate-limit-bar--critical';
  }
  if (lim.utilization_pct >= lim.warn_at_pct) {
    return lim.priority === 'scarce' ? 'rate-limit-bar--critical' : 'rate-limit-bar--warn';
  }
  return 'rate-limit-bar--ok';
}

function formatWait(seconds: number): string {
  if (seconds <= 0) return '';
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

export function RateLimitRow({ lim }: { lim: LimiterSnapshot }) {
  const wait =
    lim.next_token_in_seconds > 0
      ? formatWait(lim.next_token_in_seconds)
      : lim.breaker_recovery_in_seconds > 0
        ? formatWait(lim.breaker_recovery_in_seconds)
        : '';

  return (
    <div className="rate-limit-row">
      <div className="rate-limit-row__head">
        <span className="rate-limit-row__label">{lim.label}</span>
        <span
          className={`rate-limit-row__breaker rate-limit-row__breaker--${lim.breaker_state.toLowerCase()}`}
        >
          {lim.breaker_state}
        </span>
      </div>
      <div className="rate-limit-bar">
        <div
          className={`rate-limit-bar__fill ${barModifier(lim)}`}
          style={{ width: `${Math.min(100, lim.utilization_pct)}%` }}
        />
      </div>
      <p className="muted rate-limit-row__meta">
        {lim.tokens.toFixed(1)} / {lim.capacity} capacity
        {wait ? ` · ready in ${wait}` : ''}
        {lim.breaker_failures > 0 ? ` · ${lim.breaker_failures} failures` : ''}
      </p>
    </div>
  );
}

import type { LimiterSnapshot } from './types';
import { RateLimitBar } from './RateLimitBar';
import { formatRateLimitWait } from './rateLimitBar';

export function RateLimitRow({ lim }: { lim: LimiterSnapshot }) {
  const wait =
    lim.next_token_in_seconds > 0
      ? formatRateLimitWait(lim.next_token_in_seconds)
      : lim.breaker_recovery_in_seconds > 0
        ? formatRateLimitWait(lim.breaker_recovery_in_seconds)
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
      <RateLimitBar lim={lim} />
      <p className="muted rate-limit-row__meta">
        {lim.tokens.toFixed(1)} / {lim.capacity} capacity
        {wait ? ` · ready in ${wait}` : ''}
        {lim.breaker_failures > 0 ? ` · ${lim.breaker_failures} failures` : ''}
      </p>
    </div>
  );
}

import type { LimiterSnapshot } from './types';
import { RateLimitBar } from './RateLimitBar';
import { formatRateLimitWait } from './rateLimitBar';

type Props = {
  limiters: LimiterSnapshot[];
};

function waitLabel(lim: LimiterSnapshot): string {
  if (lim.next_token_in_seconds > 0) {
    return formatRateLimitWait(lim.next_token_in_seconds);
  }
  if (lim.breaker_recovery_in_seconds > 0) {
    return formatRateLimitWait(lim.breaker_recovery_in_seconds);
  }
  return '';
}

export function MiniRateLimitBars({ limiters }: Props) {
  if (!limiters.length) return null;

  return (
    <div className="mini-rate-limits">
      {limiters.map((lim) => {
        const wait = waitLabel(lim);
        return (
          <div key={lim.key} className="mini-rate-limit">
            <div className="mini-rate-limit__head">
              <span className="mini-rate-limit__label">{lim.label}</span>
              <span
                className={`mini-rate-limit__breaker mini-rate-limit__breaker--${lim.breaker_state.toLowerCase()}`}
              >
                {lim.breaker_state}
              </span>
            </div>
            <RateLimitBar lim={lim} size="mini" />
            {wait ? (
              <span className="mini-rate-limit__wait muted">ready in {wait}</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

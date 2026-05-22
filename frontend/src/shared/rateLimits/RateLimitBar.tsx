import type { LimiterSnapshot } from './types';
import { rateLimitBarModifier } from './rateLimitBar';

type Props = {
  lim: LimiterSnapshot;
  size?: 'default' | 'mini';
};

export function RateLimitBar({ lim, size = 'default' }: Props) {
  return (
    <div className={`rate-limit-bar${size === 'mini' ? ' rate-limit-bar--mini' : ''}`}>
      <div
        className={`rate-limit-bar__fill ${rateLimitBarModifier(lim)}`}
        style={{ width: `${Math.min(100, lim.utilization_pct)}%` }}
      />
    </div>
  );
}

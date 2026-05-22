import type { LimiterSnapshot } from './types';

export function rateLimitBarModifier(lim: LimiterSnapshot): string {
  if (lim.breaker_state === 'OPEN' || lim.breaker_state === 'HALF_OPEN') {
    return 'rate-limit-bar--critical';
  }
  if (lim.utilization_pct >= lim.warn_at_pct) {
    return lim.priority === 'scarce' ? 'rate-limit-bar--critical' : 'rate-limit-bar--warn';
  }
  return 'rate-limit-bar--ok';
}

export function formatRateLimitWait(seconds: number): string {
  if (seconds <= 0) return '';
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem}s`;
}

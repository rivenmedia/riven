import { humanizeServiceKey } from '../../features/dashboard/serviceSetupMessages';
import { MiniRateLimitBars } from './MiniRateLimitBars';
import type { LimiterSnapshot } from './types';

type Props = {
  ownerKey: string;
  limiters: LimiterSnapshot[];
  statusLabel?: string;
  statusClassName?: string;
};

export function ServiceRateLimitCard({
  ownerKey,
  limiters,
  statusLabel,
  statusClassName,
}: Props) {
  return (
    <article className="downloader-card downloader-status-card service-rate-limit-card">
      <div className="downloader-card__head">
        <strong>{humanizeServiceKey(ownerKey)}</strong>
        {statusLabel ? (
          <span className={statusClassName ?? 'service-row__status--up'}>{statusLabel}</span>
        ) : null}
      </div>
      {limiters.length > 0 ? (
        <MiniRateLimitBars limiters={limiters} />
      ) : (
        <p className="muted mini-rate-limits__empty">No recent API usage</p>
      )}
    </article>
  );
}

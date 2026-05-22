import { useMemo } from 'react';
import type { LimiterSnapshot } from './types';
import { RateLimitRow } from './RateLimitRow';
import { humanizeServiceKey } from '../../features/dashboard/serviceSetupMessages';
import { DOWNLOADER_OWNERS, ownerSortKey } from './owners';

type Props = {
  limiters: LimiterSnapshot[];
  filterOwners?: Set<string>;
  groupByOwner?: boolean;
};

export function RateLimitsPanel({
  limiters,
  filterOwners,
  groupByOwner = true,
}: Props) {
  const filtered = useMemo(() => {
    if (!filterOwners) return limiters;
    return limiters.filter((l) => filterOwners.has(l.owner));
  }, [limiters, filterOwners]);

  const warn = useMemo(() => {
    return filtered.some(
      (l) =>
        l.breaker_state === 'OPEN' ||
        l.utilization_pct >= l.warn_at_pct ||
        (l.priority === 'scarce' && l.next_token_in_seconds > 30),
    );
  }, [filtered]);

  const grouped = useMemo(() => {
    if (!groupByOwner) return { '': filtered };
    const map: Record<string, LimiterSnapshot[]> = {};
    for (const l of filtered) {
      const o = l.owner || 'other';
      if (!map[o]) map[o] = [];
      map[o].push(l);
    }
    for (const rows of Object.values(map)) {
      rows.sort((a, b) => a.label.localeCompare(b.label));
    }
    return map;
  }, [filtered, groupByOwner]);

  const sortedOwners = useMemo(() => {
    return Object.keys(grouped).sort((a, b) => {
      const [ai, as] = ownerSortKey(a);
      const [bi, bs] = ownerSortKey(b);
      if (ai !== bi) return ai - bi;
      return as.localeCompare(bs);
    });
  }, [grouped]);

  if (!filtered.length) {
    return (
      <p className="muted">
        No rate limiters with activity in the last 30 minutes.
      </p>
    );
  }

  return (
    <div className="rate-limits-panel">
      {warn && (
        <p className="downloader-status__hint rate-limits-panel__warn">
          One or more limits are near capacity or the circuit breaker is open.
        </p>
      )}
      {sortedOwners.map((owner) => {
        const rows = grouped[owner];
        return (
          <section key={owner || 'all'} className="rate-limits-panel__section">
            {owner && groupByOwner && (
              <h4 className="rate-limits-panel__owner">{humanizeServiceKey(owner)}</h4>
            )}
            {rows.map((lim) => (
              <RateLimitRow key={lim.key} lim={lim} />
            ))}
          </section>
        );
      })}
    </div>
  );
}

export { DOWNLOADER_OWNERS } from './owners';

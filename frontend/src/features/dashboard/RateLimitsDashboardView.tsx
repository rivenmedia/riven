import { useMemo } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { KpiCardHeading } from '../../shared/ui/KpiInfoTip';
import type { AppRoute } from '../../app/routeTypes';
import { useRateLimits } from '../../shared/rateLimits/useRateLimits';
import { RateLimitsPanel } from '../../shared/rateLimits/RateLimitsPanel';
import type { LimiterSnapshot } from '../../shared/rateLimits/types';

/** Only this page polls GET /rate_limits; Activity must not call useRateLimits. */
function summarizeRateLimits(limiters: LimiterSnapshot[]) {
  let openBreakers = 0;
  let stressed = 0;
  for (const l of limiters) {
    if (l.breaker_state === 'OPEN' || l.breaker_state === 'HALF_OPEN') {
      openBreakers += 1;
    }
    if (
      l.utilization_pct >= l.warn_at_pct ||
      (l.priority === 'scarce' && l.next_token_in_seconds > 30)
    ) {
      stressed += 1;
    }
  }
  return { total: limiters.length, openBreakers, stressed };
}

export default function RateLimitsDashboardView(_props: { route: AppRoute }) {
  const { limiters, error: rateLimitError } = useRateLimits();
  const rateSummary = useMemo(() => summarizeRateLimits(limiters), [limiters]);

  return (
    <ViewLayout className="view-dashboard view-dashboard-rate-limits" view="dashboard-rate-limits">
      <ViewHeader
        title="Rate limits"
        subtitle="Token buckets and circuit breakers across downloaders, scrapers, and APIs"
      />

      {rateLimitError && (
        <Panel>
          <p className="downloader-status__error">{rateLimitError}</p>
        </Panel>
      )}

      <section className="kpi-grid rate-limits-kpis">
        <article className="kpi-card">
          <KpiCardHeading
            label="Rate limiters"
            description="Registered token buckets and circuit breakers across downloaders, scrapers, and APIs."
          />
          <p className="kpi-value">{rateSummary.total || '—'}</p>
        </article>
        <article className="kpi-card">
          <KpiCardHeading
            label="Open breakers"
            description="Limits where the circuit breaker is open or half-open after repeated failures."
          />
          <p className="kpi-value">{rateSummary.openBreakers}</p>
        </article>
        <article className="kpi-card">
          <KpiCardHeading
            label="Stressed limits"
            description="Limits near capacity, scarce tokens, or elevated utilization."
          />
          <p className="kpi-value">{rateSummary.stressed}</p>
        </article>
      </section>

      <Panel title="Rate limits">
        <p className="muted downloader-status__hint rate-limits-panel__scope">
          Limiters with token or circuit-breaker activity in the last 30 minutes.
        </p>
        <RateLimitsPanel limiters={limiters} />
      </Panel>
    </ViewLayout>
  );
}

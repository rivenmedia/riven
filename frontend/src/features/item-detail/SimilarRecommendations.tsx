/**
 * Similar & Recommendations panel. Two sections as card grids. Explore or library mode.
 */

import { buildHash, buildExploreNodeUrl } from '../../shared/routing/router';
import { getMediaKind } from '../../shared/utils/utils';
import { MediaCard } from '../library/MediaCard';

export type SimilarRecommendationsData = {
  recommendations?: unknown[];
  similar?: unknown[];
};

export type MediaNode = {
  kind: string;
  id: string;
  label?: string;
  source?: string;
};

export interface SimilarRecommendationsOptions {
  onMediaSelect?: (node: MediaNode) => void;
  exploreLinkBase?: string;
  trail?: Array<{ source?: string; kind: string; id: string; label?: string }>;
}

export interface SimilarRecommendationsProps extends SimilarRecommendationsOptions {
  data: SimilarRecommendationsData | null | undefined;
  maxRecommendations?: number;
  maxSimilar?: number;
  /** default: show both sections; item overview tabs pass a single section */
  variant?: 'all' | 'recommendations' | 'similar';
}

function Section({
  title,
  items,
  options,
  showTitle = true,
}: {
  title: string;
  items: any[];
  options: SimilarRecommendationsOptions;
  /** when false, tab label replaces the in-panel heading (library item sub-tabs) */
  showTitle?: boolean;
}) {
  if (!items.length) return null;
  const { onMediaSelect, exploreLinkBase, trail } = options;

  return (
    <section className="panel">
      {showTitle && <h3>{title}</h3>}
      <div className="detail-link-grid">
        {items.map((item: any) => {
          const kind = getMediaKind(item);
          const node: MediaNode = {
            kind,
            id: String(item.id),
            label: item.title || item.name,
            source: item.indexer || 'tmdb',
          };
          let href: string | null = null;
          if (!onMediaSelect && exploreLinkBase) {
            if (item.library_item_id != null) {
              href = buildHash('item', String(item.library_item_id));
            } else {
              href = buildExploreNodeUrl(node, trail);
            }
          }
          return (
            <MediaCard
              key={item.id}
              item={item}
              compact
              href={href ?? undefined}
              onSelect={
                onMediaSelect
                  ? () => onMediaSelect(node)
                  : undefined
              }
            />
          );
        })}
      </div>
    </section>
  );
}

export function SimilarRecommendations({
  data,
  maxRecommendations = 12,
  maxSimilar = 12,
  variant = 'all',
  ...options
}: SimilarRecommendationsProps) {
  if (!data) return null;

  const recommendations = (data.recommendations ?? []).slice(
    0,
    maxRecommendations,
  ) as any[];
  const similar = (data.similar ?? []).slice(0, maxSimilar) as any[];

  if (variant === 'recommendations') {
    return (
      <Section
        title="Recommendations"
        items={recommendations}
        options={options}
        showTitle={false}
      />
    );
  }
  if (variant === 'similar') {
    return <Section title="Similar" items={similar} options={options} showTitle={false} />;
  }

  const recSection = (
    <Section title="Recommendations" items={recommendations} options={options} />
  );
  const simSection = (
    <Section title="Similar" items={similar} options={options} />
  );

  if (!recommendations.length && !similar.length) return null;

  return (
    <>
      {recSection}
      {simSection}
    </>
  );
}

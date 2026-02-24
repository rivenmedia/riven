/**
 * Similar & Recommendations panel. Two sections as card grids. Explore or library mode.
 */

import { buildHash, buildExploreNodeUrl } from '../../services/router';
import { getMediaKind } from '../../services/utils';
import { MediaCard } from '../MediaCard';

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
}

function Section({
  title,
  items,
  options,
}: {
  title: string;
  items: any[];
  options: SimilarRecommendationsOptions;
}) {
  if (!items.length) return null;
  const { onMediaSelect, exploreLinkBase, trail } = options;

  return (
    <section className="panel">
      <h3>{title}</h3>
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
  ...options
}: SimilarRecommendationsProps) {
  if (!data) return null;

  const recommendations = (data.recommendations ?? []).slice(
    0,
    maxRecommendations,
  ) as any[];
  const similar = (data.similar ?? []).slice(0, maxSimilar) as any[];

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

import { MediaCard, type MediaAction } from './MediaCard';

export interface MediaGridAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

export interface MediaGridProps {
  items: any[];
  href?: string | null | ((item: any) => string | null);
  actions?: (item: any) => MediaGridAction[];
  compact?: boolean;
  onSelect?: (item: any, event: React.MouseEvent) => void;
  className?: string;
}

export function MediaGrid({
  items,
  href = '#/item',
  actions,
  compact = false,
  onSelect,
  className = '',
}: MediaGridProps) {
  return (
    <div className={`media-grid ${className}`.trim()}>
      {items.map((item) => {
        const itemHref =
          typeof href === 'function' ? href(item) : href ? `${href}/${item.id}` : null;
        return (
          <MediaCard
            key={item.id ?? item.tmdb_id ?? item.tvdb_id ?? Math.random()}
            item={item}
            href={itemHref}
            actions={actions?.(item) ?? []}
            compact={compact}
            onSelect={onSelect ?? undefined}
          />
        );
      })}
    </div>
  );
}

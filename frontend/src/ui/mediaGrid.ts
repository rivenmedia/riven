import { renderMediaCard } from './mediaCard';

export interface MediaGridAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

export interface RenderMediaGridOptions {
  href?: string | null | ((item: any) => string | null);
  actions?: (item: any) => MediaGridAction[];
  compact?: boolean;
  onSelect?: (item: any, event: Event) => void;
}

/**
 * Render a grid of media cards. Uses existing renderMediaCard; options passed per item.
 */
export function renderMediaGrid(
  container: HTMLElement | null,
  items: any[],
  options: RenderMediaGridOptions = {},
): void {
  if (!container) return;
  const { href = `#/item`, actions, compact = false, onSelect } = options;

  container.innerHTML = '';
  container.classList.add('media-grid');

  items.forEach((item) => {
    const itemHref = typeof href === 'function' ? href(item) : (href ? `${href}/${item.id}` : null);
    const card = renderMediaCard(item, {
      href: itemHref,
      actions: actions?.(item) ?? [],
      compact,
      onSelect: onSelect ?? null,
    });
    container.appendChild(card);
  });
}

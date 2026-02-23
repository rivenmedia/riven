import { formatEpisodeDisplayTitle, formatYear, getMediaKind, mediaLabel } from '../services/utils';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';

export interface MediaListAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

export interface RenderMediaListOptions {
  /** e.g. (item) => `#/item/${item.id}` */
  href?: (item: any) => string | null;
  actions?: (item: any) => MediaListAction[];
  /** Show poster thumb on the left */
  showPoster?: boolean;
}

function posterUrl(item: any): string {
  const path = item?.poster_path || item?.profile_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function createChip(text: string, className = ''): HTMLSpanElement {
  const span = document.createElement('span');
  span.className = `legend-chip ${className}`.trim();
  span.textContent = text;
  return span;
}

/**
 * Render a linear list of media rows (poster thumb, title, type chip, state, year, link).
 * Uses episode display format "Show — S01E04 — Title" when item.type === 'episode'.
 */
export function renderMediaList(
  container: HTMLElement | null,
  items: any[],
  options: RenderMediaListOptions = {},
): void {
  if (!container) return;
  const { href = (item) => `#/item/${item.id}`, actions, showPoster = true } = options;

  container.innerHTML = '';
  container.classList.add('media-list');

  items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'media-list__row';
    const kind = getMediaKind(item);

    if (showPoster) {
      const poster = document.createElement('div');
      poster.className = 'media-list__poster';
      const img = document.createElement('img');
      img.alt = '';
      img.loading = 'lazy';
      const src = posterUrl(item);
      if (src) img.src = src;
      poster.appendChild(img);
      row.appendChild(poster);
    }

    const main = document.createElement('div');
    main.className = 'media-list__main';

    const link = document.createElement('a');
    link.className = 'media-list__title';
    link.textContent = formatEpisodeDisplayTitle(item);
    const itemHref = href(item);
    if (itemHref) link.href = itemHref;
    main.appendChild(link);

    const meta = document.createElement('div');
    meta.className = 'media-list__meta';
    meta.appendChild(createChip(mediaLabel(item), kind === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'));
    if (item?.state) meta.appendChild(createChip(item.state));
    const year = formatYear(item);
    if (year) meta.appendChild(createChip(year));
    main.appendChild(meta);

    row.appendChild(main);

    if (actions?.(item)?.length) {
      const actionBar = document.createElement('div');
      actionBar.className = 'media-list__actions';
      actions(item).forEach(({ label, onClick, tone = 'secondary' }) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `btn btn--small btn--${tone}`;
        btn.textContent = label;
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          onClick?.(item);
        });
        actionBar.appendChild(btn);
      });
      row.appendChild(actionBar);
    }

    container.appendChild(row);
  });
}

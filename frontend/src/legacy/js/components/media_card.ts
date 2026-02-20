import { formatYear, getMediaKind, mediaLabel } from '../utils';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w500';

interface MediaAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

interface RenderCardOptions {
  href?: string | null;
  onSelect?: ((item: any, event: Event) => void) | null;
  actions?: MediaAction[];
  compact?: boolean;
}

function posterUrl(item: any): string {
  const path = item?.poster_path || item?.profile_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function createTag(label: string, className = ''): HTMLSpanElement {
  const tag = document.createElement('span');
  tag.className = `media-tag ${className}`.trim();
  tag.textContent = label;
  return tag;
}

export function renderMediaCard(item: any, options: RenderCardOptions = {}): HTMLElement {
  const { href = null, onSelect = null, actions = [], compact = false } = options;
  const kind = getMediaKind(item);

  const card = document.createElement('article');
  card.className = `media-card media-card--${kind} ${compact ? 'media-card--compact' : ''}`.trim();
  card.dataset.mediaCard = '1';
  if (item?.tmdb_id != null) card.dataset.tmdbId = String(item.tmdb_id);
  if (item?.tvdb_id != null) card.dataset.tvdbId = String(item.tvdb_id);
  if (item?.library_item_id != null) card.dataset.libraryItemId = String(item.library_item_id);
  if (item?.id != null) card.dataset.itemId = String(item.id);
  if (item?.indexer) card.dataset.indexer = String(item.indexer);
  if (kind === 'movie' || kind === 'tv') card.dataset.mediaType = kind;

  const trigger = document.createElement(href ? 'a' : 'button') as
    | HTMLAnchorElement
    | HTMLButtonElement;
  trigger.className = 'media-card__trigger';
  if (href && trigger instanceof HTMLAnchorElement) {
    trigger.href = href;
  } else if (trigger instanceof HTMLButtonElement) {
    trigger.type = 'button';
  }

  if (onSelect) {
    trigger.addEventListener('click', (event) => {
      if (href) event.preventDefault();
      onSelect(item, event);
    });
  }

  const title = item?.title || item?.name || 'Unknown';
  const poster = document.createElement('div');
  poster.className = 'media-card__poster';
  const placeholder = document.createElement('div');
  placeholder.className = 'media-card__placeholder';
  placeholder.textContent = (title || '?').slice(0, 1).toUpperCase();
  const img = document.createElement('img');
  img.alt = title;
  img.loading = 'lazy';
  const hasPoster = posterUrl(item);
  placeholder.hidden = !!hasPoster;
  img.addEventListener('load', () => {
    placeholder.hidden = true;
  });
  img.addEventListener('error', () => {
    img.remove();
    placeholder.hidden = false;
  });
  poster.appendChild(placeholder);
  poster.appendChild(img);
  if (hasPoster) img.src = hasPoster;

  const body = document.createElement('div');
  body.className = 'media-card__body';
  const heading = document.createElement('h3');
  heading.className = 'media-card__title';
  heading.textContent = title;
  body.appendChild(heading);

  const tags = document.createElement('div');
  tags.className = 'media-card__tags';
  tags.appendChild(createTag(mediaLabel(item), `media-tag--${kind}`));

  const year = formatYear(item);
  if (year) tags.appendChild(createTag(year, 'media-tag--neutral'));

  const stateTag = item?.state ? createTag(item.state, 'media-tag--state') : null;
  if (stateTag) tags.appendChild(stateTag);
  const libraryTag = item?.in_library ? createTag('In Library', 'media-tag--library') : null;
  if (libraryTag) tags.appendChild(libraryTag);
  body.appendChild(tags);

  if (item?.overview || item?.biography) {
    const summary = document.createElement('p');
    summary.className = 'media-card__summary';
    summary.textContent = item.overview || item.biography;
    body.appendChild(summary);
  }

  trigger.appendChild(poster);
  trigger.appendChild(body);
  card.appendChild(trigger);

  if (actions.length) {
    const footer = document.createElement('div');
    footer.className = 'media-card__actions';
    actions.forEach(({ label, onClick, tone = 'neutral' }) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `btn btn--small btn--${tone}`;
      button.textContent = label;
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick?.(item);
      });
      footer.appendChild(button);
    });
    card.appendChild(footer);
  }

  return card;
}

/**
 * Update only the status/library tags and action button on an existing card (for live refresh).
 * When in_library becomes true, replaces "Add" with "Open" that navigates to the library item.
 * @param {Element} cardEl - The .media-card element
 * @param {{ state?: string | null, in_library?: boolean, library_item_id?: string | null }} status
 */
export function updateMediaCardStatus(
  cardEl: Element | null | undefined,
  status: { state?: string | null; in_library?: boolean; library_item_id?: string | null },
): void {
  const tags = cardEl?.querySelector('.media-card__tags');
  if (!tags) return;

  let stateTag = tags.querySelector('.media-tag--state');
  let libraryTag = tags.querySelector('.media-tag--library');

  if (status.state != null && status.state !== '') {
    if (!stateTag) {
      stateTag = createTag(status.state, 'media-tag--state');
      tags.appendChild(stateTag);
    } else {
      stateTag.textContent = status.state;
    }
  } else if (stateTag) {
    stateTag.remove();
  }

  if (status.in_library) {
    if (!libraryTag) {
      libraryTag = createTag('In Library', 'media-tag--library');
      tags.appendChild(libraryTag);
    }
  } else if (libraryTag) {
    libraryTag.remove();
  }

  const footer = cardEl?.querySelector('.media-card__actions');
  if (!footer || !status.in_library || !status.library_item_id) return;

  const addBtn =
    footer.querySelector('.btn--primary') ||
    (Array.from(footer.querySelectorAll('button')) as HTMLButtonElement[]).find(
      (b) => b.textContent?.trim() === 'Add',
    );
  if (!addBtn) return;

  const openBtn = document.createElement('button');
  openBtn.type = 'button';
  openBtn.className = 'btn btn--small btn--secondary';
  openBtn.textContent = 'Open';
  openBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    window.location.hash = `#/item/${status.library_item_id}`;
  });
  addBtn.replaceWith(openBtn);
}

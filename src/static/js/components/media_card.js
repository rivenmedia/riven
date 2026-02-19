import { formatYear, getMediaKind, mediaLabel } from '../utils.js';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w500';

function posterUrl(item) {
  const path = item?.poster_path || item?.profile_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function createTag(label, className = '') {
  const tag = document.createElement('span');
  tag.className = `media-tag ${className}`.trim();
  tag.textContent = label;
  return tag;
}

export function renderMediaCard(item, options = {}) {
  const { href = null, onSelect = null, actions = [], compact = false } = options;
  const kind = getMediaKind(item);

  const card = document.createElement('article');
  card.className = `media-card media-card--${kind} ${compact ? 'media-card--compact' : ''}`.trim();

  const trigger = document.createElement(href ? 'a' : 'button');
  trigger.className = 'media-card__trigger';
  if (href) {
    trigger.href = href;
  } else {
    trigger.type = 'button';
  }

  if (onSelect) {
    trigger.addEventListener('click', (event) => {
      if (href) event.preventDefault();
      onSelect(item, event);
    });
  }

  const poster = document.createElement('div');
  poster.className = 'media-card__poster';
  const img = document.createElement('img');
  const title = item?.title || item?.name || 'Unknown';
  img.src = posterUrl(item);
  img.alt = title;
  img.loading = 'lazy';
  img.addEventListener('error', () => {
    img.remove();
    placeholder.hidden = false;
  });
  poster.appendChild(img);

  const placeholder = document.createElement('div');
  placeholder.className = 'media-card__placeholder';
  placeholder.textContent = (title || '?').slice(0, 1).toUpperCase();
  placeholder.hidden = !!img.src;
  poster.appendChild(placeholder);

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

  if (item?.state) tags.appendChild(createTag(item.state, 'media-tag--state'));
  if (item?.in_library) tags.appendChild(createTag('In Library', 'media-tag--library'));
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

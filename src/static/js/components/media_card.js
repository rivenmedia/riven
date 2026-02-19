/**
 * Media card component - clone template and fill
 */

const TMDB_IMG = 'https://image.tmdb.org/t/p/w500';

export function renderMediaCard(item, href, options = {}) {
  const { actions = [] } = options;
  const tpl = document.getElementById('media-card-tpl');
  let card;
  if (!tpl) {
    const a = document.createElement('a');
    a.href = href;
    a.className = 'media-card';
    a.innerHTML = `
      <div class="media-card-poster">
        <img src="${item.poster_path || ''}" alt="${item.title}" loading="lazy" onerror="this.style.display='none'">
        <div class="media-card-placeholder" style="display:${item.poster_path ? 'none' : 'flex'}">?</div>
      </div>
      <div class="media-card-body">
        <h3>${item.title || 'Unknown'}</h3>
        <p class="media-card-meta">${item.year || ''} · ${item.media_type || item.type || ''}</p>
      </div>
    `;
    card = a;
  } else {
    const clone = tpl.content.cloneNode(true);
    card = clone.querySelector('.media-card');
    card.href = href;
    const poster = clone.querySelector('[data-slot="poster"]');
    if (poster) {
      poster.src = item.poster_path ? (item.poster_path.startsWith('http') ? item.poster_path : TMDB_IMG + item.poster_path) : '';
      poster.alt = item.title;
    }
    const titleEl = clone.querySelector('[data-slot="title"]');
    if (titleEl) titleEl.textContent = item.title || 'Unknown';
    const metaEl = clone.querySelector('[data-slot="meta"]');
    if (metaEl) metaEl.textContent = [item.year, item.media_type || item.type].filter(Boolean).join(' · ');
  }

  if (actions.length) {
    const wrap = document.createElement('div');
    wrap.className = 'media-card-wrap';
    wrap.appendChild(card);
    const actionsEl = document.createElement('div');
    actionsEl.className = 'media-card-actions';
    actions.forEach(({ label, onClick }) => {
      const btn = document.createElement('button');
      btn.textContent = label;
      btn.className = 'media-card-action-btn';
      btn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      };
      actionsEl.appendChild(btn);
    });
    wrap.appendChild(actionsEl);
    return wrap;
  }
  return card;
}

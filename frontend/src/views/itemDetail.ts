import { apiDelete, apiFetch, apiGet, apiPost, getStreamUrl } from '../services/api';
import { notify } from '../services/notify';
import {
  formatBytes,
  formatDate,
  formatEpisodeDisplayTitle,
  formatShortDate,
} from '../services/utils';
import { renderBackButton } from '../ui/backButton';
import { renderReferenceLinks } from '../ui/referenceLinks';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';

function posterUrl(item: { poster_path?: string | null }): string {
  const path = item?.poster_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function createChip(text: string, className = ''): HTMLSpanElement {
  const span = document.createElement('span');
  span.className = `legend-chip ${className}`.trim();
  span.textContent = text;
  return span;
}

type EpisodeLike = {
  id?: string;
  number?: number;
  title?: string;
  state?: string;
  parent_title?: string;
  season_number?: number | null;
  episode_number?: number | null;
  aired_at?: string;
  poster_path?: string | null;
  network?: string | null;
  content_rating?: string | null;
  media_metadata?: {
    video?: { resolution_width?: number; resolution_height?: number };
    quality_source?: string | null;
  } | null;
  filesystem_entry?: { file_size?: number | null } | null;
};
type SeasonLike = { number?: number; episodes?: EpisodeLike[] };
type ShowLike = { type: string; title?: string; poster_path?: string | null; seasons?: SeasonLike[] };

function isInLibrary(state: string): boolean {
  const s = (state || '').toString();
  return s === 'Completed' || s === 'Symlinked' || s === 'Downloaded' || s === 'Scraped';
}

function episodeQualityLabel(ep: EpisodeLike): string {
  const meta = ep.media_metadata;
  if (!meta) return '';
  const parts: string[] = [];
  const v = meta.video;
  if (v?.resolution_height) parts.push(`${v.resolution_height}p`);
  if (meta.quality_source) parts.push(meta.quality_source);
  return parts.join(' ');
}

function renderSeasonsEpisodes(
  host: HTMLElement | null,
  item: ShowLike,
  refresh: () => void,
): void {
  if (!host) return;
  const seasons = item?.seasons;
  if (item.type !== 'show' || !seasons?.length) {
    host.innerHTML = '';
    return;
  }

  const sortedSeasons = [...seasons].filter((s) => (s.number ?? 0) > 0).sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
  if (!sortedSeasons.length) {
    host.innerHTML = '';
    return;
  }

  const panel = document.createElement('div');
  panel.className = 'panel show-seasons-episodes';

  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Seasons &amp; Episodes</h3>';
  panel.appendChild(head);

  const seasonTabs = document.createElement('div');
  seasonTabs.className = 'season-tabs';
  seasonTabs.setAttribute('role', 'tablist');
  sortedSeasons.forEach((season, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `season-tab ${idx === 0 ? 'season-tab--active' : ''}`;
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
    btn.dataset.seasonIndex = String(idx);
    const num = season.number ?? 0;
    const epCount = season.episodes?.length ?? 0;
    btn.textContent = `Season ${num}${epCount ? ` (${epCount})` : ''}`;
    seasonTabs.appendChild(btn);
  });
  panel.appendChild(seasonTabs);

  const episodeListHost = document.createElement('div');
  episodeListHost.className = 'show-episodes-list';
  panel.appendChild(episodeListHost);

  function renderEpisodeList(seasonIndex: number): void {
    const season = sortedSeasons[seasonIndex];
    const episodes = season?.episodes ?? [];
    const sortedEps = [...episodes].sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
    const showTitle = item.title ?? '';

    episodeListHost.innerHTML = '';
    if (!sortedEps.length) {
      episodeListHost.innerHTML = '<p class="muted">No episodes in this season.</p>';
      return;
    }

    episodeListHost.classList.add('media-list');

    sortedEps.forEach((ep) => {
      const row = document.createElement('div');
      row.className = 'media-list__row show-episode-row';
      const state = (ep.state || '').toString();
      const inLib = isInLibrary(state);
      const hasFile = inLib || (ep.filesystem_entry?.file_size != null && ep.filesystem_entry.file_size > 0);

      const fileIndicator = document.createElement('span');
      fileIndicator.className = `episode-file-indicator episode-file-indicator--${hasFile ? 'has-file' : 'missing'}`;
      fileIndicator.setAttribute('title', hasFile ? 'File available' : 'No file');
      fileIndicator.setAttribute('aria-hidden', 'true');
      fileIndicator.innerHTML = hasFile
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
      row.appendChild(fileIndicator);

      const epForDisplay: EpisodeLike & { type: string } = {
        ...ep,
        type: 'episode',
        parent_title: ep.parent_title ?? showTitle,
        season_number: ep.season_number ?? season?.number ?? null,
        episode_number: ep.episode_number ?? ep.number ?? null,
      };

      const poster = document.createElement('div');
      poster.className = 'media-list__poster';
      const img = document.createElement('img');
      img.alt = '';
      img.loading = 'lazy';
      const src = posterUrl(ep.poster_path ? ep : { poster_path: item.poster_path });
      if (src) img.src = src;
      poster.appendChild(img);
      row.appendChild(poster);

      const main = document.createElement('div');
      main.className = 'media-list__main';

      const link = document.createElement('a');
      link.className = 'media-list__title';
      link.href = `#/item/${ep.id}`;
      link.textContent = formatEpisodeDisplayTitle(epForDisplay);
      main.appendChild(link);

      const meta = document.createElement('div');
      meta.className = 'media-list__meta';
      meta.appendChild(createChip('TV', 'legend-chip--tv'));
      meta.appendChild(
        createChip(inLib ? 'In library' : state || 'Missing', inLib ? 'legend-chip--in-library' : 'legend-chip--missing'),
      );
      const aired = formatShortDate(ep.aired_at);
      if (aired) meta.appendChild(createChip(`Aired: ${aired}`));
      if (ep.network) meta.appendChild(createChip(`Network: ${ep.network}`));
      if (ep.content_rating) meta.appendChild(createChip(`Rating: ${ep.content_rating}`));
      const quality = episodeQualityLabel(ep);
      if (quality) meta.appendChild(createChip(`Quality: ${quality}`));
      const fileSize = ep.filesystem_entry?.file_size;
      if (fileSize != null && fileSize > 0) {
        const sizeStr = formatBytes(fileSize);
        if (sizeStr) meta.appendChild(createChip(`Size: ${sizeStr}`));
      }
      main.appendChild(meta);

      row.appendChild(main);

      const actions = document.createElement('div');
      actions.className = 'media-list__actions';
      if (ep.id && (state === 'Requested' || state === 'Failed')) {
        const retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'btn btn--small btn--secondary';
        retryBtn.textContent = 'Retry';
        retryBtn.addEventListener('click', async () => {
          const res = await apiPost('/items/retry', { ids: [String(ep.id)] });
          if (!res.ok) {
            notify(res.error || 'Retry failed', 'error');
            return;
          }
          notify('Episode queued for retry', 'success');
          refresh();
        });
        actions.appendChild(retryBtn);
      }
      row.appendChild(actions);
      episodeListHost.appendChild(row);
    });
  }

  seasonTabs.querySelectorAll<HTMLButtonElement>('.season-tab').forEach((btn, idx) => {
    btn.addEventListener('click', () => {
      seasonTabs.querySelectorAll('.season-tab').forEach((b, i) => {
        b.classList.toggle('season-tab--active', i === idx);
        b.setAttribute('aria-selected', String(i === idx));
      });
      renderEpisodeList(idx);
    });
  });

  renderEpisodeList(0);
  host.innerHTML = '';
  host.appendChild(panel);
}

function escapeHtml(s: string): string {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function renderTmdbDetails(
  host: HTMLElement | null,
  tmdbData: Record<string, unknown> | null | undefined,
  itemType: string,
) {
  if (!host) return;
  host.innerHTML = '';
  if (!tmdbData) return;
  const hasOverview = typeof tmdbData.overview === 'string' && tmdbData.overview.length > 0;
  const tagline = tmdbData.tagline as string | undefined;
  const runtime = tmdbData.runtime as number | undefined;
  const releaseDate = tmdbData.release_date as string | undefined;
  const genres = tmdbData.genres as { id?: number; name?: string }[] | undefined;
  const productionCompanies = tmdbData.production_companies as { name?: string }[] | undefined;
  const voteAverage = tmdbData.vote_average as number | undefined;
  const voteCount = tmdbData.vote_count as number | undefined;
  const belongsToCollection = tmdbData.belongs_to_collection as { id?: number; name?: string } | undefined;
  const firstAirDate = tmdbData.first_air_date as string | undefined;
  const lastAirDate = tmdbData.last_air_date as string | undefined;
  const numSeasons = tmdbData.number_of_seasons as number | undefined;
  const numEpisodes = tmdbData.number_of_episodes as number | undefined;

  if (
    !hasOverview &&
    !tagline &&
    runtime == null &&
    !releaseDate &&
    !firstAirDate &&
    !(Array.isArray(genres) && genres.length) &&
    !(Array.isArray(productionCompanies) && productionCompanies.length) &&
    voteAverage == null &&
    !belongsToCollection?.name &&
    numSeasons == null
  ) {
    return;
  }

  const panel = document.createElement('div');
  panel.className = 'panel tmdb-details-panel';
  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Details</h3>';
  panel.appendChild(head);

  if (belongsToCollection?.name) {
    const p = document.createElement('p');
    p.className = 'tmdb-details-collection';
    p.innerHTML = `<strong>Part of collection:</strong> ${escapeHtml(belongsToCollection.name)}`;
    panel.appendChild(p);
  }
  if (tagline) {
    const p = document.createElement('p');
    p.className = 'tmdb-details-tagline';
    p.textContent = tagline;
    panel.appendChild(p);
  }
  if (hasOverview) {
    const p = document.createElement('p');
    p.className = 'tmdb-details-overview';
    p.textContent = tmdbData.overview as string;
    panel.appendChild(p);
  }
  const metaRow = document.createElement('div');
  metaRow.className = 'media-metadata-chips';
  if (typeof runtime === 'number' && runtime > 0) {
    metaRow.appendChild(createChip(`${runtime} min`, 'legend-chip--runtime'));
  }
  const dateStr = releaseDate || firstAirDate;
  if (dateStr) {
    metaRow.appendChild(createChip(dateStr, 'legend-chip--date'));
  }
  if (numSeasons != null && itemType === 'show') {
    metaRow.appendChild(createChip(`${numSeasons} season${numSeasons !== 1 ? 's' : ''}`, 'legend-chip--seasons'));
  }
  if (numEpisodes != null && itemType === 'show') {
    metaRow.appendChild(createChip(`${numEpisodes} episode${numEpisodes !== 1 ? 's' : ''}`, 'legend-chip--episodes'));
  }
  if (lastAirDate && itemType === 'show') {
    metaRow.appendChild(createChip(`Ended ${lastAirDate}`, 'legend-chip--ended'));
  }
  if (Array.isArray(genres) && genres.length) {
    genres.forEach((g) => {
      const name = g?.name;
      if (name) metaRow.appendChild(createChip(name, 'legend-chip--genre'));
    });
  }
  if (typeof voteAverage === 'number' && !Number.isNaN(voteAverage)) {
    const voteStr = typeof voteCount === 'number' && voteCount > 0
      ? `★ ${voteAverage.toFixed(1)} (${voteCount} votes)`
      : `★ ${voteAverage.toFixed(1)}`;
    metaRow.appendChild(createChip(voteStr, 'legend-chip--rating'));
  }
  if (metaRow.childNodes.length) panel.appendChild(metaRow);
  if (Array.isArray(productionCompanies) && productionCompanies.length) {
    const names = productionCompanies.map((c) => c?.name).filter(Boolean).join(', ');
    if (names) {
      const p = document.createElement('p');
      p.className = 'tmdb-details-production';
      p.innerHTML = `<strong>Production:</strong> ${escapeHtml(names)}`;
      panel.appendChild(p);
    }
  }
  host.appendChild(panel);
}

function mediaTypeForScrape(item) {
  if (item.type === 'movie') return 'movie';
  return 'tv';
}

function toPosterUrl(path) {
  if (!path) return '';
  return path.startsWith('http') ? path : `https://image.tmdb.org/t/p/w500${path}`;
}

async function runAction(action, itemId) {
  const ids = [String(itemId)];
  switch (action) {
    case 'retry':
      return apiPost('/items/retry', { ids });
    case 'reset':
      return apiPost('/items/reset', { ids });
    case 'pause':
      return apiPost('/items/pause', { ids });
    case 'unpause':
      return apiPost('/items/unpause', { ids });
    case 'reindex':
      return apiPost('/items/reindex', { item_id: Number(itemId) });
    case 'remove':
      return apiDelete('/items/remove', { ids });
    default:
      return {
        ok: false,
        status: 0,
        data: null,
        error: `Unknown action ${action}`,
      };
  }
}

async function runAutoScrape(item) {
  return apiPost('/scrape/auto', {
    media_type: mediaTypeForScrape(item),
    item_id: Number(item.id),
  });
}

function openManualScrapeModal(itemId, refresh) {
  const template = document.getElementById('manual-scrape-modal-tpl') as HTMLTemplateElement | null;
  if (!template) return;

  const clone = template.content.cloneNode(true) as DocumentFragment;
  const dialog = clone.querySelector('dialog');
  const magnetInput = clone.querySelector('[data-slot="magnet"]') as HTMLTextAreaElement | null;
  const startButton = clone.querySelector('[data-action="start-session"]');
  const closeButton = clone.querySelector('[data-action="close"]');

  if (!dialog || !startButton || !closeButton) return;

  const close = () => {
    dialog.close();
    dialog.remove();
  };

  closeButton.addEventListener('click', close);
  startButton.addEventListener('click', async () => {
    const magnet = magnetInput?.value?.trim();
    if (!magnet) {
      notify('Paste a magnet URI first', 'warning');
      return;
    }
    const params = new URLSearchParams({ magnet, item_id: String(itemId) });
    const response = await apiFetch(`/scrape/start_session?${params.toString()}`, {
      method: 'POST',
    });
    if (!response.ok) {
      notify(response.error || 'Failed to start manual session', 'error');
      return;
    }
    notify('Manual scrape session started', 'success');
    close();
    refresh();
  });

  document.body.appendChild(dialog);
  dialog.showModal();
}

function renderHeader(
  item: Record<string, unknown>,
  slots: { poster?: Element | null; info?: Element | null },
  tmdbData?: Record<string, unknown> | null,
) {
  const { poster, info } = slots;
  if (poster) {
    poster.innerHTML = '';
    const imageUrl = toPosterUrl(item.poster_path as string);
    if (imageUrl) {
      const image = document.createElement('img');
      image.src = imageUrl;
      image.alt = (item.title as string) || 'poster';
      poster.appendChild(image);
    } else {
      poster.innerHTML = '<div class="muted">No artwork</div>';
    }
  }

  if (info) {
    info.innerHTML = '';
    const h2 = document.createElement('h2');
    h2.textContent = formatEpisodeDisplayTitle(item);
    info.appendChild(h2);

    const metaLine = document.createElement('div');
    metaLine.className = 'meta-line';
    metaLine.appendChild(
      createChip(
        (item.type as string) ?? 'media',
        item.type === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv',
      ),
    );
    if (item.year) metaLine.appendChild(createChip(String(item.year)));
    const voteAvg = tmdbData?.vote_average;
    if (typeof voteAvg === 'number' && !Number.isNaN(voteAvg)) {
      metaLine.appendChild(createChip(`★ ${voteAvg.toFixed(1)}`, 'legend-chip--rating'));
    }
    info.appendChild(metaLine);

    const stateLine = document.createElement('div');
    stateLine.className = 'item-info__state-line';
    const stateLabel = document.createElement('span');
    stateLabel.className = 'item-info__state-label';
    stateLabel.textContent = 'State:';
    stateLine.appendChild(stateLabel);
    stateLine.appendChild(createChip(item.state || 'Unknown', 'state-pill'));
    info.appendChild(stateLine);

    const genres = item.genres as unknown;
    if (Array.isArray(genres) && genres.length) {
      const genreWrap = document.createElement('div');
      genreWrap.className = 'item-info__genres';
      const genreDt = document.createElement('span');
      genreDt.className = 'item-info__genres-label';
      genreDt.textContent = 'Genres: ';
      genreWrap.appendChild(genreDt);
      genres.forEach((g) => {
        const name = typeof g === 'object' && g != null && 'name' in g ? (g as { name?: string }).name : String(g);
        if (name) genreWrap.appendChild(createChip(name, 'legend-chip--genre'));
      });
      info.appendChild(genreWrap);
    }

    const dl = document.createElement('dl');
    if (item.content_rating) {
      dl.appendChild(document.createElement('dt')).textContent = 'Content rating';
      dl.appendChild(document.createElement('dd')).textContent = String(item.content_rating);
    }
    if (item.country) {
      dl.appendChild(document.createElement('dt')).textContent = 'Country';
      dl.appendChild(document.createElement('dd')).textContent = String(item.country);
    }
    if (item.language || item.original_language) {
      dl.appendChild(document.createElement('dt')).textContent = 'Language';
      dl.appendChild(document.createElement('dd')).textContent = String(item.language || item.original_language || '');
    }
    if (item.network) {
      dl.appendChild(document.createElement('dt')).textContent = 'Network';
      dl.appendChild(document.createElement('dd')).textContent = String(item.network);
    }
    if (item.type === 'show' && item.seasons) {
      const seasons = item.seasons as { number?: number; episodes?: unknown[] }[];
      const totalEps = seasons.reduce((acc, s) => acc + (s.episodes?.length ?? 0), 0);
      dl.appendChild(document.createElement('dt')).textContent = 'Seasons';
      dl.appendChild(document.createElement('dd')).textContent = String(seasons.length);
      dl.appendChild(document.createElement('dt')).textContent = 'Episodes';
      dl.appendChild(document.createElement('dd')).textContent = String(totalEps);
    }
    const refLinks = renderReferenceLinks({
      imdb_id: item.imdb_id,
      tvdb_id: item.tvdb_id,
      tmdb_id: item.tmdb_id,
      type: item.type,
    });
    const hasLinks = refLinks.querySelector('.reference-links__link');
    if (hasLinks) {
      dl.appendChild(document.createElement('dt')).textContent = 'Links';
      dl.appendChild(document.createElement('dd')).appendChild(refLinks);
    }
    dl.appendChild(document.createElement('dt')).textContent = 'Item ID';
    dl.appendChild(document.createElement('dd')).textContent = String(item.id);
    dl.appendChild(document.createElement('dt')).textContent = 'Requested';
    dl.appendChild(document.createElement('dd')).textContent = formatDate(item.requested_at);
    dl.appendChild(document.createElement('dt')).textContent = 'Scraped';
    dl.appendChild(document.createElement('dd')).textContent = formatDate(item.scraped_at);
    info.appendChild(dl);
  }
}

function renderCastCrew(
  host: HTMLElement | null,
  tmdbData: Record<string, unknown> | null | undefined,
): void {
  if (!host) return;
  host.innerHTML = '';
  if (!tmdbData) return;
  const credits = tmdbData.credits as
    | {
        cast?: { name?: string; character?: string }[];
        crew?: { name?: string; job?: string }[];
        guest_stars?: { name?: string; character?: string }[];
      }
    | undefined;
  if (!credits) return;
  const cast = credits.cast ?? [];
  const crew = credits.crew ?? [];
  const guestStars = credits.guest_stars ?? [];
  const directors = crew.filter((c) => c.job === 'Director').map((c) => c.name || '').filter(Boolean);
  const castList = cast.length ? cast : guestStars;
  const topCast = castList
    .slice(0, 12)
    .map((c) => (c.character ? `${c.name} (${c.character})` : c.name || ''));
  if (directors.length === 0 && topCast.length === 0) return;

  const panel = document.createElement('div');
  panel.className = 'panel cast-crew-panel';
  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Cast &amp; Crew</h3>';
  panel.appendChild(head);
  const dl = document.createElement('dl');
  dl.className = 'cast-crew-dl';
  if (directors.length) {
    dl.appendChild(document.createElement('dt')).textContent = 'Directors';
    dl.appendChild(document.createElement('dd')).textContent = directors.join(', ');
  }
  if (topCast.length) {
    dl.appendChild(document.createElement('dt')).textContent = 'Cast';
    dl.appendChild(document.createElement('dd')).textContent = topCast.join(', ');
  }
  panel.appendChild(dl);
  host.appendChild(panel);
}

const MEDIA_METADATA_IS_TAGS: [key: string, label: string][] = [
  ['is_remastered', 'Remastered'],
  ['is_proper', 'Proper'],
  ['is_repack', 'Repack'],
  ['is_remux', 'Remux'],
  ['is_upscaled', 'Upscaled'],
  ['is_directors_cut', "Director's Cut"],
  ['is_extended', 'Extended'],
];

function renderMetadata(metadataHost: HTMLElement | null, metadata: Record<string, unknown> | null) {
  if (!metadataHost) return;
  if (!metadata) {
    metadataHost.innerHTML = '<p class="muted">No media metadata available.</p>';
    return;
  }
  const filename = typeof metadata.filename === 'string' ? metadata.filename : '';
  const video = metadata.video as Record<string, unknown> | undefined;
  const qualitySource = metadata.quality_source as string | undefined;
  const w = video?.resolution_width as number | undefined;
  const h = video?.resolution_height as number | undefined;
  const resolutionLabel = video?.resolution_label as string | undefined;
  const resolutionChip =
    w && h ? `${w}×${h}` : resolutionLabel || '';

  const head = document.createElement('div');
  head.className = 'section-head';
  head.innerHTML = '<h3>Media Metadata</h3>';
  const rawToggle = document.createElement('button');
  rawToggle.type = 'button';
  rawToggle.className = 'btn btn--small btn--secondary';
  rawToggle.textContent = 'Show raw JSON';
  const pre = document.createElement('pre');
  pre.className = 'json-output';
  pre.hidden = true;
  pre.textContent = JSON.stringify(metadata, null, 2);
  rawToggle.addEventListener('click', () => {
    pre.hidden = !pre.hidden;
    rawToggle.textContent = pre.hidden ? 'Show raw JSON' : 'Hide raw JSON';
  });
  head.appendChild(rawToggle);

  const main = document.createElement('div');
  main.className = 'media-metadata-main';
  const filenameEl = document.createElement('div');
  filenameEl.className = 'media-metadata-filename';
  filenameEl.textContent = filename || '—';
  filenameEl.setAttribute('title', filename || '');
  main.appendChild(filenameEl);

  const chipsRow = document.createElement('div');
  chipsRow.className = 'media-metadata-chips';
  MEDIA_METADATA_IS_TAGS.forEach(([key, label]) => {
    if (metadata[key] === true) chipsRow.appendChild(createChip(label, 'legend-chip--tag'));
  });
  if (qualitySource) chipsRow.appendChild(createChip(qualitySource, 'legend-chip--quality'));
  if (resolutionChip) chipsRow.appendChild(createChip(resolutionChip, 'legend-chip--resolution'));
  main.appendChild(chipsRow);

  metadataHost.innerHTML = '';
  metadataHost.appendChild(head);
  metadataHost.appendChild(main);
  metadataHost.appendChild(pre);
}

function renderStreams(streamHost, streams, itemId, refresh) {
  if (!streamHost) return;
  const merged = [
    ...(streams?.streams || []),
    ...(streams?.blacklisted_streams || []).map((stream) => ({ ...stream, blacklisted: true })),
  ];

  streamHost.innerHTML = `
    <div class="section-head">
      <h3>Streams (${merged.length})</h3>
      <button type="button" class="btn btn--secondary btn--small" data-action="reset-streams">Reset Streams</button>
    </div>
  `;

  const resetButton = streamHost.querySelector('[data-action="reset-streams"]');
  if (resetButton) {
    resetButton.addEventListener('click', async () => {
      const response = await apiPost(`/items/${itemId}/streams/reset`);
      if (!response.ok) {
        notify(response.error || 'Failed to reset streams', 'error');
        return;
      }
      notify('Streams reset', 'success');
      refresh();
    });
  }

  if (!merged.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'No streams stored for this item.';
    streamHost.appendChild(empty);
    return;
  }

  merged.forEach((stream) => {
    const row = document.createElement('div');
    row.className = 'stream-row';
    const title = document.createElement('span');
    title.textContent = stream.raw_title || stream.infohash || `Stream ${stream.id}`;
    row.appendChild(title);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn--small btn--secondary';
    button.textContent = stream.blacklisted ? 'Unblacklist' : 'Blacklist';
    button.addEventListener('click', async () => {
      const path = stream.blacklisted
        ? `/items/${itemId}/streams/${stream.id}/unblacklist`
        : `/items/${itemId}/streams/${stream.id}/blacklist`;
      const response = await apiPost(path);
      if (!response.ok) {
        notify(response.error || 'Failed to update stream blacklist', 'error');
        return;
      }
      notify('Stream updated', 'success');
      refresh();
    });
    row.appendChild(button);
    streamHost.appendChild(row);
  });
}

function renderVideo(videoHost, itemId, item) {
  if (!videoHost) return;
  videoHost.innerHTML = '';
  if (item.type !== 'movie' && item.type !== 'episode') return;

  const heading = document.createElement('h3');
  heading.textContent = 'Playback';
  videoHost.appendChild(heading);

  const video = document.createElement('video');
  video.controls = true;
  video.src = getStreamUrl(itemId);
  videoHost.appendChild(video);
}

export async function load(route, container) {
  const itemId = route.param;
  if (!itemId) {
    container.innerHTML = '<p class="muted">No item ID provided.</p>';
    return;
  }

  const [itemResponse, streamResponse, metadataResponse] = await Promise.all([
    apiGet(`/items/${itemId}`, { media_type: 'item', extended: true }),
    apiGet(`/items/${itemId}/streams`),
    apiGet(`/items/${itemId}/metadata`),
  ]);

  if (!itemResponse.ok || !itemResponse.data) {
    container.innerHTML = `<p class="muted">${itemResponse.error || 'Item not found.'}</p>`;
    return;
  }

  const item = itemResponse.data;
  let tmdbData: Record<string, unknown> | null = null;
  if (item.type === 'movie' && item.tmdb_id) {
    const r = await apiGet(`/tmdb/movie/${item.tmdb_id}`);
    if (r.ok && r.data) tmdbData = r.data as Record<string, unknown>;
  } else if (item.type === 'show' && item.tmdb_id) {
    const r = await apiGet(`/tmdb/tv/${item.tmdb_id}`);
    if (r.ok && r.data) tmdbData = r.data as Record<string, unknown>;
  } else if (
    item.type === 'episode' &&
    item.show_id != null &&
    item.season_number != null &&
    item.episode_number != null
  ) {
    const showRes = await apiGet(`/items/${item.show_id}`);
    if (showRes.ok && showRes.data?.tmdb_id) {
      const r = await apiGet(
        `/tmdb/tv/${showRes.data.tmdb_id}/season/${item.season_number}/episode/${item.episode_number}`,
      );
      if (r.ok && r.data) tmdbData = r.data as Record<string, unknown>;
    }
  }

  const slots = {
    back: container.querySelector<HTMLElement>('[data-slot="back"]'),
    poster: container.querySelector('[data-slot="poster"]'),
    info: container.querySelector('[data-slot="info"]'),
    actions: container.querySelector('[data-slot="actions"]'),
    streams: container.querySelector('[data-slot="streams"]'),
    video: container.querySelector('[data-slot="video"]'),
    metadata: container.querySelector('[data-slot="metadata"]'),
    castCrew: container.querySelector<HTMLElement>('[data-slot="cast-crew"]'),
    tmdbDetails: container.querySelector<HTMLElement>('[data-slot="tmdb-details"]'),
  };

  const returnRoute =
    (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('riven_return_route')) || 'library';
  const returnLabels: Record<string, string> = {
    library: '← Back to Library',
    movies: '← Back to Movies',
    shows: '← Back to TV Shows',
    episodes: '← Back to TV Episodes',
  };
  const isEpisode = item.type === 'episode';
  const showId = isEpisode && item.show_id != null ? String(item.show_id) : null;
  renderBackButton(slots.back, {
    label: showId ? '← Back to Show' : returnLabels[returnRoute] || '← Back',
    href: showId ? `#/item/${showId}` : `#/${returnRoute}`,
  });

  const refresh = () => load(route, container);
  renderHeader(item, slots, tmdbData);
  renderCastCrew(slots.castCrew, tmdbData);
  renderTmdbDetails(slots.tmdbDetails, tmdbData, item.type);
  const metadata = metadataResponse.ok ? metadataResponse.data : null;
  const seasonsNote = container.querySelector<HTMLElement>('[data-slot="seasons-note"]');
  if (seasonsNote && (item.type === 'show' || item.type === 'episode')) {
    renderSeasonsEpisodes(seasonsNote, item as ShowLike, refresh);
  }
  renderMetadata(slots.metadata, metadata);
  const isShow = item.type === 'show';
  if (!isShow) {
    renderStreams(slots.streams, streamResponse.data || {}, itemId, refresh);
    renderVideo(slots.video, itemId, item);
  }

  const tabBar = container.querySelector<HTMLElement>('[data-slot="tab-bar"]');
  const panelOverview = container.querySelector<HTMLElement>('[data-slot="panel-overview"]');
  const panelStreams = container.querySelector<HTMLElement>('[data-slot="panel-streams"]');
  const panelPlayback = container.querySelector<HTMLElement>('[data-slot="panel-playback"]');
  if (isShow) {
    tabBar?.querySelectorAll<HTMLButtonElement>('[data-tab="streams"], [data-tab="playback"]').forEach((btn) => btn.remove());
    panelStreams?.remove();
    panelPlayback?.remove();
  }
  const panels = [
    { id: 'overview', el: panelOverview },
    ...(isShow ? [] : [{ id: 'streams', el: panelStreams }, { id: 'playback', el: panelPlayback }]),
  ];
  const hasTabs = panels.length >= 1;
  if (!hasTabs) {
    tabBar?.remove();
    if (panelOverview) panelOverview.hidden = false;
  } else {
    tabBar?.querySelectorAll<HTMLButtonElement>('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        tabBar?.querySelectorAll('[data-tab]').forEach((b) => {
          b.classList.remove('item-detail-tab--active');
          b.setAttribute('aria-selected', 'false');
        });
        btn.classList.add('item-detail-tab--active');
        btn.setAttribute('aria-selected', 'true');
        panels.forEach((p) => {
          if (p.el) p.el.hidden = p.id !== tab;
        });
      });
    });
    panels.forEach((p) => {
      if (p.el) p.el.hidden = p.id !== 'overview';
    });
  }

  if (slots.actions) {
    const state = (item.state || '').toString();
    const showPause = state !== 'Paused' && state !== 'Completed' && state !== 'Failed';
    const showResume = state === 'Paused';
    const tooltips: Record<string, string> = {
      'auto-scrape': 'Trigger automatic torrent search and download for this item.',
      'manual-scrape': 'Search and pick a torrent manually (paste magnet or search).',
      retry: 'Retry from current step; re-queue the item.',
      reset: 'Reset to initial state, blacklist current stream, and re-download.',
      pause: 'Pause processing and cancel current jobs.',
      unpause: 'Resume processing (only when paused).',
      reindex: 'Reindex to pick up new season & episode releases.',
      remove: 'Remove from library (DB, jobs, and library refresh).',
    };
    const buttons: { key: string; label: string; tone: string; show?: boolean }[] = [
      { key: 'auto-scrape', label: 'Auto Scrape', tone: 'primary' },
      { key: 'manual-scrape', label: 'Manual Scrape', tone: 'secondary' },
      { key: 'retry', label: 'Retry', tone: 'secondary' },
      { key: 'reset', label: 'Reset', tone: 'secondary' },
      { key: 'pause', label: 'Pause', tone: 'warning', show: showPause },
      { key: 'unpause', label: 'Resume', tone: 'secondary', show: showResume },
      { key: 'reindex', label: 'Reindex', tone: 'secondary' },
      { key: 'remove', label: 'Remove', tone: 'danger' },
    ].filter((b) => b.show !== false);

    slots.actions.innerHTML = buttons
      .map(
        (button) =>
          `<button type="button" class="btn btn--small btn--${button.tone}" data-action="${button.key}" title="${escapeHtml(tooltips[button.key] ?? '')}">${button.label}</button>`,
      )
      .join('');

    slots.actions.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', async () => {
        const action = button.dataset.action;
        if (!action) return;

        if (action === 'manual-scrape') {
          openManualScrapeModal(itemId, refresh);
          return;
        }

        if (action === 'auto-scrape') {
          const response = await runAutoScrape(item);
          if (!response.ok) {
            notify(response.error || 'Auto scrape failed', 'error');
            return;
          }
          notify('Auto scrape triggered', 'success');
          refresh();
          return;
        }

        if (action === 'remove') {
          const confirmed = window.confirm(`Remove "${item.title}" from library?`);
          if (!confirmed) return;
        }

        const response = await runAction(action, itemId);
        if (!response.ok) {
          notify(response.error || `Action failed: ${action}`, 'error');
          return;
        }

        notify(response.data?.message || `${action} complete`, 'success');
        if (action === 'remove') {
          window.location.hash = '#/library';
          return;
        }
        refresh();
      });
    });
  }
}

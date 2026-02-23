export function getMediaKind(item) {
  const raw = (item?.media_type || item?.type || '').toLowerCase();
  if (raw === 'show' || raw === 'tv' || raw === 'season' || raw === 'episode') {
    return 'tv';
  }
  if (raw === 'movie') {
    return 'movie';
  }
  if (raw === 'person') {
    return 'person';
  }
  return 'mixed';
}

export function mediaLabel(item) {
  const kind = getMediaKind(item);
  if (kind === 'tv') return 'TV';
  if (kind === 'movie') return 'Movie';
  if (kind === 'person') return 'Person';
  return 'Media';
}

/** Format episode for display: "Show Name — S01E04 — Episode Title" */
export function formatEpisodeDisplayTitle(item: {
  type?: string;
  parent_title?: string;
  season_number?: number | null;
  episode_number?: number | null;
  title?: string;
  name?: string;
}): string {
  if (item?.type !== 'episode') return item?.title || item?.name || 'Unknown';
  const show = item.parent_title || '';
  const s = item.season_number != null ? String(item.season_number).padStart(2, '0') : '??';
  const e = item.episode_number != null ? String(item.episode_number).padStart(2, '0') : '??';
  const title = item.title || item.name || '';
  if (!show && !title) return `S${s}E${e}`;
  const parts = [show, `S${s}E${e}`, title].filter(Boolean);
  return parts.join(' — ');
}

export function formatYear(item) {
  if (item?.year) return String(item.year);
  if (item?.release_date) return String(item.release_date).slice(0, 4);
  if (item?.first_air_date) return String(item.first_air_date).slice(0, 4);
  if (item?.aired_at && item.aired_at !== 'None') {
    const date = new Date(item.aired_at);
    if (!Number.isNaN(date.getTime())) return String(date.getFullYear());
  }
  return '';
}

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

export function toCsv(ids = []) {
  return ids.map((id) => String(id).trim()).filter(Boolean).join(',');
}

export function sortByPopularity(items = []) {
  return [...items].sort((a, b) => Number(b?.popularity || 0) - Number(a?.popularity || 0));
}

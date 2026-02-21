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

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
  const aired = parseApiDate(item?.aired_at);
  if (aired) return String(aired.getFullYear());
  return '';
}

/** Parse API datetime (often UTC without Z) so we can show it in local time. */
export function parseApiDate(value: string | number | Date | null | undefined): Date | null {
  if (value == null) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const s = String(value).trim();
  if (!s || s === 'None') return null;
  let toParse = s;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(s)) {
    toParse = s.replace(' ', 'T');
    if (!/Z|[+-]\d{2}:?\d{2}$/.test(toParse)) toParse += 'Z';
  }
  const date = new Date(toParse);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Seconds elapsed since an API timestamp (null if unparseable). */
export function secondsSinceApiDate(
  value: string | number | Date | null | undefined,
): number | null {
  const date = parseApiDate(value);
  if (!date) return null;
  return Math.max(0, (Date.now() - date.getTime()) / 1000);
}

export function formatDate(value: string | number | Date | null | undefined): string {
  const date = parseApiDate(value);
  if (!date) return '—';
  return date.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

export function formatShortDate(value: string | number | Date | null | undefined): string {
  const date = parseApiDate(value);
  if (!date) return '';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let u = 0;
  let n = bytes;
  while (n >= 1024 && u < units.length - 1) {
    n /= 1024;
    u += 1;
  }
  return `${n.toFixed(u ? 2 : 0)} ${units[u]}`;
}

export function toCsv(ids = []) {
  return ids.map((id) => String(id).trim()).filter(Boolean).join(',');
}

export function sortByPopularity(items = []) {
  return [...items].sort((a, b) => Number(b?.popularity || 0) - Number(a?.popularity || 0));
}

/** Human-readable relative time from a duration in seconds (past or future). */
export function formatRelativeSeconds(
  seconds: number,
  direction: 'past' | 'future' = 'past',
): string {
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 45) return direction === 'future' ? 'soon' : 'just now';
  if (sec < 60) {
    return direction === 'future' ? `in ${sec}s` : `${sec}s ago`;
  }
  const min = Math.floor(sec / 60);
  if (min < 60) {
    const label = min === 1 ? '1m' : `${min}m`;
    return direction === 'future' ? `in ${label}` : `${label} ago`;
  }
  const hr = Math.floor(min / 60);
  if (hr < 48) {
    const label = hr === 1 ? '1h' : `${hr}h`;
    return direction === 'future' ? `in ${label}` : `${label} ago`;
  }
  const day = Math.floor(hr / 24);
  const label = day === 1 ? '1d' : `${day}d`;
  return direction === 'future' ? `in ${label}` : `${label} ago`;
}

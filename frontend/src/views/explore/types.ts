import { getMediaKind } from '../../services/utils';

export type ExploreNode = {
  source: string;
  kind: string;
  id: string;
  label?: string;
};

export function parseNode(raw: string | undefined): ExploreNode | null {
  if (!raw) return null;
  const [source, kind, id] = String(raw).split('|');
  if (!id || !kind) return null;
  return {
    source: source || 'tmdb',
    kind,
    id: String(id),
    label: `${kind} ${id}`,
  };
}

export function serializeNode(node: ExploreNode): string {
  return `${node.source || 'tmdb'}|${node.kind}|${node.id}`;
}

export function parseTrail(raw: string | undefined): ExploreNode[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((n: any) => ({
        source: n?.source || 'tmdb',
        kind: n?.kind,
        id: n?.id ? String(n.id) : null,
        label: n?.label || `${n?.kind || 'node'} ${n?.id || ''}`.trim(),
      }))
      .filter((n: any) => n.kind && n.id);
  } catch {
    return [];
  }
}

export function toCardItem(entry: any, fallbackKind: string | null = null): any {
  const kind = fallbackKind || getMediaKind(entry);
  return {
    ...entry,
    id: String(entry.id),
    title: entry.title || entry.name || 'Unknown',
    media_type: kind === 'mixed' ? entry.media_type : kind,
    year:
      entry.year ||
      (entry.release_date ? String(entry.release_date).slice(0, 4) : '') ||
      (entry.first_air_date ? String(entry.first_air_date).slice(0, 4) : ''),
  };
}

export function parsePositiveInt(value: unknown, fallback = 1): number {
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function buildRouteQuery(state: {
  source: string;
  mode: string;
  type: string;
  window?: string;
  query?: string;
  page?: number;
  history: ExploreNode[];
  trendingMode?: boolean;
}): Record<string, string> {
  const query: Record<string, string> = {
    source: state.source,
    mode: state.mode,
    type: state.type,
    q: state.query || '',
    page: state.page && state.page > 1 ? String(state.page) : '',
  };
  if (state.mode === 'discover' && state.window && (state.type === 'all' || state.trendingMode)) {
    query.window = state.window;
  }
  if (state.history.length > 0) {
    const latest = state.history[state.history.length - 1];
    query.node = serializeNode(latest);
    query.trail = JSON.stringify(state.history.slice(-12));
  }
  return Object.fromEntries(Object.entries(query).filter(([, v]) => v !== '' && v != null));
}

export function getOriginLabel(state: {
  mode: string;
  type: string;
  window?: string;
  source: string;
  trendingMode?: boolean;
}): string {
  if (state.mode === 'discover') {
    if (state.type === 'all' || state.trendingMode) {
      const period = state.window === 'day' ? 'Today' : 'This Week';
      return state.type === 'all' ? `Trending — ${period}` : `Trending — ${state.type === 'movie' ? 'Movies' : 'TV'} — ${period}`;
    }
    return `Discover — ${state.type === 'movie' ? 'Movies' : 'TV'}`;
  }
  return state.source === 'tvdb' ? 'TVDB Search' : 'Search Results';
}

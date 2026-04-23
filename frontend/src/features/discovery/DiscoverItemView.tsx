import { useCallback, useMemo } from 'react';
import { ViewLayout } from '../../shared/ui/PagePrimitives';
import { BackButton } from '../../shared/ui/BackButton';
import { buildDiscoverItemHash } from '../../shared/routing/router';
import type { AppRoute } from '../../app/routeTypes';
import type { MediaNode } from '../item-detail/SimilarRecommendations';
import type { ExploreNode } from '../explore/types';
import { DiscoverItemContent } from './DiscoverItemContent';

const DISCOVER_BACK_KEY = 'riven_discover_back_hash';

function parseDiscoverSegments(segments: string[]): { source: 'tmdb' | 'tvdb'; kind: 'movie' | 'tv' | 'person'; id: string } | null {
  if (segments[0] !== 'discover-item' || segments.length < 4) return null;
  const source = segments[1];
  const k = segments[2];
  const id = decodeURIComponent(segments[3] || '');
  if (!id) return null;
  if (source === 'tvdb') {
    if (k !== 'tv') return null;
    return { source: 'tvdb', kind: 'tv', id };
  }
  if (source === 'tmdb' && (k === 'movie' || k === 'tv' || k === 'person')) {
    return { source: 'tmdb', kind: k, id };
  }
  return null;
}

export default function DiscoverItemView({ route }: { route: AppRoute }) {
  const parsed = useMemo(
    () => (route.name === 'discover-item' ? parseDiscoverSegments(route.segments) : null),
    [route.name, route.path],
  );

  const backHref =
    typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(DISCOVER_BACK_KEY) || '#/search' : '#/search';

  const navigateToItem = useCallback(
    (node: ExploreNode) => {
      if (node.source === 'tvdb' || (node as any).indexer === 'tvdb') {
        window.location.hash = buildDiscoverItemHash('tvdb', 'tv', String(node.id));
        return;
      }
      const k = node.kind as 'movie' | 'tv' | 'person';
      window.location.hash = buildDiscoverItemHash('tmdb', k, String(node.id));
    },
    [],
  );

  const navigateFromMedia = useCallback((n: MediaNode) => {
    if (n.kind === 'person') {
      window.location.hash = buildDiscoverItemHash('tmdb', 'person', n.id);
      return;
    }
    if (n.source === 'tvdb') {
      window.location.hash = buildDiscoverItemHash('tvdb', 'tv', n.id);
      return;
    }
    const k = n.kind as 'movie' | 'tv';
    window.location.hash = buildDiscoverItemHash('tmdb', k, n.id);
  }, []);

  if (!parsed) {
    return (
      <ViewLayout className="view-discover-item" view="discover-item">
        <p className="empty-state">Invalid discover URL.</p>
        <BackButton href={backHref} label="← Back to Search" />
      </ViewLayout>
    );
  }

  return (
    <ViewLayout className="view-discover-item" view="discover-item">
      <div className="view-header" style={{ marginBottom: '1rem' }}>
        <BackButton href={backHref} label="← Back to Search" />
      </div>
      <DiscoverItemContent
        key={parsed.id + parsed.kind + parsed.source}
        source={parsed.source}
        kind={parsed.kind}
        id={parsed.id}
        onNavigateToItem={navigateToItem}
        onNavigateFromMedia={navigateFromMedia}
        onBackFromPerson={() => { window.location.hash = backHref; }}
      />
    </ViewLayout>
  );
}

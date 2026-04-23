import { useCallback, useEffect, useRef, useState } from 'react';
import { ViewLayout, ViewHeader } from '../../shared/ui/PagePrimitives';
import { apiGet } from '../../shared/api/api';
import { buildDiscoverItemHash, replaceRoute } from '../../shared/routing/router';
import { SEARCH_DEBOUNCE_MS } from '../../shared/constants/searchDebounce';
import { getMediaKind } from '../../shared/utils/utils';
import type { AppRoute } from '../../app/routeTypes';
import { parsePositiveInt } from '../explore/types';

const TVDB_PAGE_SIZE = 20;
const DISCOVER_BACK_KEY = 'riven_discover_back_hash';

export type DiscoverySearchHit = {
  key: string;
  source: 'tmdb' | 'tvdb';
  kind: 'movie' | 'tv' | 'person';
  id: string;
  title: string;
  subline: string;
  posterUrl: string;
  extraNote?: string;
  popularity?: number;
};

function posterThumb(item: { poster_path?: string; profile_path?: string }, kind: string): string {
  const path = item.poster_path || item.profile_path;
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `https://image.tmdb.org/t/p/w92${path.replace(/^https?:\/\/image\.tmdb\.org\/t\/p\/w\d+/, '') || path}`;
}

function mergeResults(
  tmdbResults: any[],
  tvdbResults: any[],
): DiscoverySearchHit[] {
  const hits: DiscoverySearchHit[] = [];
  const seenTvdbFromTmdb = new Set<string>();

  for (const item of tmdbResults) {
    const mt = (item.media_type as string) || getMediaKind(item) || 'movie';
    if (mt === 'person') {
      hits.push({
        key: `tmdb-person-${item.id}`,
        source: 'tmdb',
        kind: 'person',
        id: String(item.id),
        title: item.name || item.title || 'Unknown',
        subline: [item.known_for_department, item.popularity != null ? `popularity ${Number(item.popularity).toFixed(0)}` : null]
          .filter(Boolean)
          .join(' · ') || 'Person',
        posterUrl: posterThumb(item, 'person'),
        popularity: item.popularity != null ? Number(item.popularity) : undefined,
      });
      continue;
    }
    if (item.tvdb_id) {
      seenTvdbFromTmdb.add(String(item.tvdb_id));
    }
    const kind: 'movie' | 'tv' = mt === 'tv' || mt === 'show' ? 'tv' : 'movie';
    hits.push({
      key: `tmdb-${kind}-${item.id}`,
      source: 'tmdb',
      kind,
      id: String(item.id),
      title: item.title || 'Unknown',
      subline: [item.year, item.vote_average != null ? `★ ${Number(item.vote_average).toFixed(1)}` : null]
        .filter(Boolean)
        .join(' · '),
      posterUrl: posterThumb(item, kind),
      popularity: item.popularity != null ? Number(item.popularity) : undefined,
    });
  }

  for (const item of tvdbResults) {
    const id = String(item.id ?? item.tvdb_id ?? '');
    if (!id) continue;
    if (seenTvdbFromTmdb.has(id)) continue;
    const title = item.title || item.name || 'Unknown';
    const y = item.year;
    const poster = item.poster_path ? String(item.poster_path) : '';
    hits.push({
      key: `tvdb-tv-${id}`,
      source: 'tvdb',
      kind: 'tv',
      id,
      title,
      subline: [y != null && y !== '' ? String(y).slice(0, 4) : null].filter(Boolean).join(' · ') || 'TV (TVDB)',
      posterUrl: poster,
    });
  }

  return hits;
}

export default function DiscoverySearchView({ route }: { route: AppRoute }) {
  const [localQ, setLocalQ] = useState(route.query?.q || '');
  const [committedQ, setCommittedQ] = useState(route.query?.q || '');
  const page = parsePositiveInt(route.query?.page, 1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hits, setHits] = useState<DiscoverySearchHit[]>([]);
  const [totalTmdb, setTotalTmdb] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const localQRef = useRef(localQ);
  localQRef.current = localQ;

  useEffect(() => {
    setLocalQ(route.query?.q || '');
    setCommittedQ(route.query?.q || '');
  }, [route.query?.q]);

  const syncUrl = useCallback(
    (q: string, nextPage: number) => {
      const query: Record<string, string> = {
        q: q.trim(),
        page: nextPage > 1 ? String(nextPage) : '',
      };
      replaceRoute('search', null, Object.fromEntries(Object.entries(query).filter(([, v]) => v !== '')));
    },
    [],
  );

  const scheduleSync = useCallback(
    (q: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        setCommittedQ(q.trim());
        syncUrl(q, 1);
      }, SEARCH_DEBOUNCE_MS);
    },
    [syncUrl],
  );

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  useEffect(() => {
    if (!committedQ.trim()) {
      setHits([]);
      setError(null);
      setLoading(false);
      setTotalTmdb(0);
      setTotalPages(1);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      const q = committedQ.trim();
      const tmdbP = apiGet('/search/tmdb/multi', { query: q, page, include_people: true });
      const tvdbP = apiGet('/search/tvdb', {
        query: q,
        type: 'series',
        limit: TVDB_PAGE_SIZE,
        offset: (page - 1) * TVDB_PAGE_SIZE,
      });
      const [tmdbRes, tvdbRes] = await Promise.all([tmdbP, tvdbP]);
      if (cancelled) return;
      if (!tmdbRes.ok) {
        setError(tmdbRes.error || 'Search failed');
        setHits([]);
        setLoading(false);
        return;
      }
      const tmdbList = tmdbRes.data?.results || [];
      const tvdbList = tvdbRes.ok && tvdbRes.data?.results ? tvdbRes.data.results : [];
      if (!tvdbRes.ok) {
        // Still show TMDB; TVDB optional
        console.warn('TVDB search failed', tvdbRes.error);
      }
      setTotalTmdb(Number(tmdbRes.data?.total_results ?? tmdbList.length));
      setTotalPages(Math.max(1, Number(tmdbRes.data?.total_pages || 1)));
      setHits(mergeResults(tmdbList, Array.isArray(tvdbList) ? tvdbList : []));
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [committedQ, page]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    const q = localQRef.current.trim();
    setCommittedQ(q);
    syncUrl(q, 1);
  };

  const goPage = (next: number) => {
    syncUrl(committedQ, next);
  };

  const onRowClick = (hit: DiscoverySearchHit) => {
    try {
      sessionStorage.setItem(DISCOVER_BACK_KEY, window.location.hash || '#/search');
    } catch {
      // ignore
    }
    if (hit.source === 'tmdb' && (hit.kind === 'movie' || hit.kind === 'tv' || hit.kind === 'person')) {
      window.location.hash = buildDiscoverItemHash('tmdb', hit.kind, hit.id);
    } else {
      window.location.hash = buildDiscoverItemHash('tvdb', 'tv', hit.id);
    }
  };

  return (
    <ViewLayout className="view-discovery-search" view="search">
      <ViewHeader
        title="Search"
        subtitle="Find movies, TV, and people on TMDB and TV (merged results; TMDB is preferred when both match)."
      />
      <form className="discovery-search__form" onSubmit={onSubmit}>
        <input
          className="discovery-search__input"
          type="search"
          placeholder="Search movies, TV shows, people…"
          value={localQ}
          onChange={(e) => {
            setLocalQ(e.target.value);
            scheduleSync(e.target.value);
          }}
          autoComplete="off"
        />
        <button className="btn btn--primary" type="submit">
          Search
        </button>
      </form>
      {committedQ.trim() && (
        <p className="discovery-search__meta">
          {loading
            ? 'Searching…'
            : error
              ? error
              : `About ${hits.length} result(s) (TMDB page ${page}: ~${totalTmdb} TMDB total)`}
        </p>
      )}
      {committedQ.trim() && !loading && !error && (
        <div className="discovery-search__list">
          {hits.length === 0 ? (
            <p className="empty-state">No results.</p>
          ) : (
            hits.map((h) => (
              <button
                key={h.key}
                type="button"
                className="discovery-search__row"
                onClick={() => onRowClick(h)}
              >
                {h.posterUrl ? (
                  <img
                    className={h.kind === 'person' ? 'discovery-search__thumb discovery-search__thumb--person' : 'discovery-search__thumb'}
                    src={h.posterUrl}
                    alt=""
                  />
                ) : (
                  <div
                    className={h.kind === 'person' ? 'discovery-search__thumb discovery-search__thumb--person' : 'discovery-search__thumb'}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', color: 'var(--text-2)' }}
                  >
                    {h.kind === 'person' ? 'P' : h.kind === 'tv' ? 'TV' : 'M'}
                  </div>
                )}
                <div className="discovery-search__body">
                  <p className="discovery-search__title">{h.title}</p>
                  <p className="discovery-search__line2">
                    {h.subline}
                    {h.extraNote ? ` · ${h.extraNote}` : ''}
                  </p>
                </div>
                <div className="discovery-search__chips">
                  <span className={`discovery-search__chip ${h.source === 'tmdb' ? 'discovery-search__chip--tmdb' : 'discovery-search__chip--tvdb'}`}>
                    {h.source === 'tmdb' ? 'TMDB' : 'TVDB'}
                  </span>
                  <span className="discovery-search__chip">
                    {h.kind === 'person' ? 'Person' : h.kind === 'tv' ? 'TV' : 'Movie'}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      )}
      {totalPages > 1 && committedQ.trim() && !loading && !error && (
        <div className="pagination-bar" style={{ marginTop: '1rem' }}>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={page <= 1}
            onClick={() => goPage(page - 1)}
          >
            Previous
          </button>
          <span>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={page >= totalPages}
            onClick={() => goPage(page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </ViewLayout>
  );
}

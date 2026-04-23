import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ViewLayout, ViewHeader } from '../../shared/ui/PagePrimitives';
import { apiGet } from '../../shared/api/api';
import { notify } from '../../shared/notifications/notify';
import { replaceRoute } from '../../shared/routing/router';
import { annotateLibraryStatus } from '../library/libraryStatus';
import { getMediaKind, toCsv } from '../../shared/utils/utils';
import { addDiscoverItemToLibrary } from '../discovery/discoverItemLibrary';
import type { AppRoute } from '../../app/routeTypes';
import {
  type ExploreNode,
  parseNode,
  parseTrail,
  buildRouteQuery,
  getOriginLabel,
  parsePositiveInt,
  toCardItem,
} from './types';
import { SEARCH_DEBOUNCE_MS } from '../../shared/constants/searchDebounce';
import { ExploreToolbar } from './ExploreToolbar';
import { ExploreResults } from './ExploreResults';
import { ExploreDetailPanel } from './ExploreDetailPanel';

const POLL_STATUS_MS = 5000;

export default function ExploreView({ route }: { route: AppRoute }) {
  const baseRoute: 'explore' | 'search' = route.name === 'search' ? 'search' : 'explore';
  const query = route.query || {};
  const [source, setSource] = useState<'tmdb' | 'tvdb'>(query.source === 'tvdb' ? 'tvdb' : 'tmdb');
  const [mode, setMode] = useState<'search' | 'discover'>(query.mode === 'discover' ? 'discover' : 'search');
  const [mediaType, setMediaType] = useState<'movie' | 'tv' | 'all'>(
    ['movie', 'tv', 'all'].includes(query.type) ? (query.type as 'movie' | 'tv' | 'all') : 'movie',
  );
  const [timeWindow, setTimeWindow] = useState<'day' | 'week'>(query.window === 'day' ? 'day' : 'week');
  const [trendingMode, setTrendingMode] = useState(!!query.window);
  const [searchInput, setSearchInput] = useState(query.q || '');
  const [searchQuery, setSearchQuery] = useState(query.q || '');
  const searchInputRef = useRef(searchInput);
  searchInputRef.current = searchInput;
  const [page, setPage] = useState(parsePositiveInt(query.page, 1));
  const [totalPages, setTotalPages] = useState(1);
  const [history, setHistory] = useState<ExploreNode[]>(() => {
    const trail = parseTrail(query.trail);
    if (trail.length) return trail;
    const node = parseNode(query.node);
    return node ? [node] : [];
  });

  const [items, setItems] = useState<any[]>([]);
  const [detailNode, setDetailNode] = useState<ExploreNode | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultsTitle, setResultsTitle] = useState('Results');

  const statusPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchRequestIdRef = useRef(0);

  const routeQueryKey = route.name === baseRoute ? JSON.stringify(route.query || {}) : '';
  const prevRouteQueryKeyRef = useRef(routeQueryKey);
  useEffect(() => {
    if (route.name !== baseRoute || routeQueryKey === prevRouteQueryKeyRef.current) return;
    prevRouteQueryKeyRef.current = routeQueryKey;
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = null;
    }
    const q = route.query || {};
    const trail = parseTrail(q.trail);
    const nodeFromQuery = parseNode(q.node);
    const nextHistory = trail.length ? trail : nodeFromQuery ? [nodeFromQuery] : [];
    setSource(q.source === 'tvdb' ? 'tvdb' : 'tmdb');
    setMode(q.mode === 'discover' ? 'discover' : 'search');
    setMediaType((['movie', 'tv', 'all'].includes(q.type) ? q.type : 'movie') as 'movie' | 'tv' | 'all');
    setTimeWindow(q.window === 'day' ? 'day' : 'week');
    setTrendingMode(!!q.window);
    const nextQ = q.q || '';
    setSearchInput(nextQ);
    setSearchQuery(nextQ);
    setPage(parsePositiveInt(q.page, 1));
    setHistory(nextHistory);
    setTotalPages(1);
    setItems([]);
    setDetailNode(null);
    setResultsError(null);
    setResultsTitle('Results');
    didRestoreHistory.current = false;
  }, [route.name, routeQueryKey, baseRoute]);

  useEffect(
    () => () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    },
    [],
  );

  const scheduleCommittedSearch = useCallback((value: string) => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      searchDebounceRef.current = null;
      setSearchQuery(value);
      setPage(1);
      setHistory([]);
      setDetailNode(null);
    }, SEARCH_DEBOUNCE_MS);
  }, []);

  /** Use searchInputRef for `q` when no override so URL never lags behind what the user typed (avoids route effect clobbering the box). */
  const syncRoute = useCallback(
    (queryOverride?: string) => {
      const q = queryOverride !== undefined ? queryOverride : searchInputRef.current;
      replaceRoute(
        baseRoute,
        null,
        buildRouteQuery({ source, mode, type: mediaType, window: timeWindow, query: q, page, history, trendingMode }),
      );
    },
    [baseRoute, source, mode, mediaType, timeWindow, page, history, trendingMode],
  );

  const fetchResults = useCallback(
    async (queryOverride?: string) => {
      const effectiveQuery = queryOverride !== undefined ? queryOverride : searchQuery;
      const requestId = ++fetchRequestIdRef.current;

      setResultsLoading(true);
      setResultsError(null);
      setResultsTitle('Loading…');

      let response: any;

      if (source === 'tvdb') {
        if (!effectiveQuery.trim()) {
          if (requestId !== fetchRequestIdRef.current) return;
          setResultsError('TVDB search requires a query.');
          setItems([]);
          setResultsLoading(false);
          return;
        }
        response = await apiGet('/search/tvdb', { query: effectiveQuery, limit: 20, offset: (page - 1) * 20 });
      } else if (mode === 'discover') {
        const useTrending = mediaType === 'all' || trendingMode;
        if (useTrending) {
          const type = mediaType === 'all' ? 'movie' : mediaType;
          response = await apiGet(`/trending/tmdb/${type}/${timeWindow}`);
        } else {
          response = await apiGet(`/discover/tmdb/${mediaType}`, { page });
        }
      } else if (mediaType === 'all') {
        response = await apiGet('/search/tmdb/multi', { query: effectiveQuery, page, include_people: true });
      } else {
        response = await apiGet(`/search/tmdb/${mediaType}`, { query: effectiveQuery, page });
      }

      if (requestId !== fetchRequestIdRef.current) return;

      if (!response?.ok) {
        setResultsError(response?.error || 'Search failed.');
        setItems([]);
        setResultsTitle('Results');
        setResultsLoading(false);
        return;
      }

      const rawItems = response.data?.results || [];
      const cardItems = rawItems.map((entry: any) => toCardItem(entry));
      const annotated = await annotateLibraryStatus(cardItems);

      if (requestId !== fetchRequestIdRef.current) return;

      setItems(annotated);
      setTotalPages(Number(response.data?.total_pages || 1));
      setResultsTitle(`Results (${response.data?.total_results ?? annotated.length})`);
      setResultsLoading(false);
      syncRoute();
    },
    [source, mode, mediaType, timeWindow, trendingMode, searchQuery, page, syncRoute],
  );

  const didRestoreHistory = useRef(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await fetchResults();
      if (cancelled) return;
    })();
    return () => { cancelled = true; };
  }, [fetchResults]);

  const statusIdsKey = useMemo(() => {
    const ids = { tmdb: new Set<string>(), tvdb: new Set<string>() };
    items.forEach((item) => {
      const k = getMediaKind(item);
      if (k === 'movie' || k === 'tv') {
        if (item.indexer === 'tvdb' && (item.tvdb_id || item.id)) ids.tvdb.add(String(item.tvdb_id || item.id));
        else if (item.tmdb_id || item.id) {
          ids.tmdb.add(String(item.tmdb_id || item.id));
          // TV shows are stored by tvdb_id in the library; include it so the poll can find them
          if (k === 'tv' && item.tvdb_id) ids.tvdb.add(String(item.tvdb_id));
        }
      }
    });
    return `${toCsv([...ids.tmdb].sort())}|${toCsv([...ids.tvdb].sort())}`;
  }, [items]);

  const lastStatusIdsKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!statusIdsKey || statusIdsKey === '|') return;
    if (lastStatusIdsKeyRef.current === statusIdsKey) return;
    lastStatusIdsKeyRef.current = statusIdsKey;
    const [tmdbCsv, tvdbCsv] = statusIdsKey.split('|');

    const poll = async () => {
      const res = await apiGet('/items/library/status', { tmdb_ids: tmdbCsv || undefined, tvdb_ids: tvdbCsv || undefined });
      if (!res.ok) return;
      const tmdb = res.data?.tmdb || {};
      const tvdb = res.data?.tvdb || {};
      const resolveStatus = (item: any) => {
        if (item.indexer === 'tvdb') return tvdb[String(item.tvdb_id || item.id)];
        const fromTmdb = tmdb[String(item.tmdb_id || item.id)];
        const fromTvdb = item.tvdb_id ? tvdb[String(item.tvdb_id)] : null;
        return fromTvdb?.in_library ? fromTvdb : fromTmdb;
      };
      setItems((prev) =>
        prev.map((item) => {
          const k = getMediaKind(item);
          if (k !== 'movie' && k !== 'tv') return item;
          const status = resolveStatus(item);
          if (!status) return item;
          return { ...item, in_library: Boolean(status.in_library), library_item_id: status.library_item_id ?? null, state: status.library_state ?? item.state };
        }),
      );
    };

    poll();
    statusPollRef.current = setInterval(poll, POLL_STATUS_MS);
    return () => {
      if (statusPollRef.current) {
        clearInterval(statusPollRef.current);
        statusPollRef.current = null;
      }
    };
  }, [statusIdsKey]);

  const selectNode = useCallback(
    (node: ExploreNode, updateHistory = true) => {
      if (updateHistory) {
        setHistory((prev) => {
          const last = prev[prev.length - 1];
          const lastKey = last ? `${last.source}:${last.kind}:${last.id}` : '';
          const nextKey = `${node.source}:${node.kind}:${node.id}`;
          if (last && lastKey === nextKey) return prev;
          return [...prev, node];
        });
      }
      setDetailNode(node);
      syncRoute();
    },
    [syncRoute],
  );

  useEffect(() => {
    if (history.length === 0 || detailNode !== null || didRestoreHistory.current) return;
    didRestoreHistory.current = true;
    selectNode(history[history.length - 1], false);
  }, [history, detailNode, selectNode]);

  const handleBreadcrumbClick = useCallback(
    (clickedIndex: number) => {
      if (clickedIndex === 0) {
        setHistory([]);
        setDetailNode(null);
        syncRoute();
        return;
      }
      const newHistory = history.slice(0, clickedIndex);
      setHistory(newHistory);
      const target = newHistory[newHistory.length - 1];
      if (target) selectNode(target, false);
    },
    [history, selectNode, syncRoute],
  );

  const handleFormSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current);
        searchDebounceRef.current = null;
      }
      const q = searchInput.trim();
      setSearchQuery(q);
      setPage(1);
      setHistory([]);
      setDetailNode(null);
      if (source === 'tvdb' && mediaType === 'all') setMediaType('tv');
      if (mode === 'search' && !q && source === 'tmdb') {
        notify('Enter a query for TMDB search', 'warning');
      }
      fetchResults(q);
    },
    [source, mode, mediaType, searchInput, fetchResults],
  );

  const handleMediaTypeChange = useCallback(
    (v: 'movie' | 'tv' | 'all') => {
      setMediaType(v);
      if (source === 'tvdb' && v === 'all') setMediaType('tv');
      if (mode === 'discover' && v === 'all') setTrendingMode(true);
      syncRoute();
      setPage(1);
      fetchResults();
    },
    [source, mode, syncRoute, fetchResults],
  );

  const handleTimeWindowChange = useCallback(
    (v: 'day' | 'week') => {
      setTimeWindow(v);
      setTrendingMode(true);
      syncRoute();
      setPage(1);
      fetchResults();
    },
    [syncRoute, fetchResults],
  );

  useEffect(() => {
    const seedRaw = typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('riven_explore_seed') : null;
    if (seedRaw && !history.length && !searchQuery) {
      try {
        const seed = JSON.parse(seedRaw);
        if (seed?.kind && seed?.id) {
          sessionStorage.removeItem('riven_explore_seed');
          setSource('tmdb');
          setMode('discover');
          setMediaType(seed.kind === 'tv' ? 'tv' : 'movie');
          setPage(1);
          const node: ExploreNode = { kind: seed.kind, id: String(seed.id), label: seed.label || `${seed.kind} ${seed.id}`, source: seed.source || 'tmdb' };
          setHistory([node]);
          replaceRoute(baseRoute, null, buildRouteQuery({ source: 'tmdb', mode: 'discover', type: seed.kind === 'tv' ? 'tv' : 'movie', query: '', page: 1, history: [node] }));
          fetchResults();
          selectNode(node, false);
        }
      } catch {
        // ignore
      }
    }
  }, []);

  const originLabel = getOriginLabel({ mode, type: mediaType, window: timeWindow, source, trendingMode });
  const showTrendingWindow = mode === 'discover' && (mediaType === 'all' || trendingMode);

  const getGridActions = useCallback(
    (item: any) => {
      const kind = getMediaKind(item);
      const actions: Array<{ label: string; onClick?: (item: any) => void; tone?: string }> = [];
      if ((kind === 'movie' || kind === 'tv') && item.in_library && item.library_item_id) {
        actions.push({
          label: 'Open',
          tone: 'secondary',
          onClick: () => { window.location.hash = `#/item/${item.library_item_id}`; },
        });
      } else if (kind === 'movie' || kind === 'tv') {
        actions.push({
          label: 'Add',
          tone: 'primary',
          onClick: async () => {
            const ok = await addDiscoverItemToLibrary(item);
            if (ok) fetchResults();
          },
        });
      }
      return actions;
    },
    [fetchResults],
  );

  const handleCardSelect = useCallback((item: any) => {
    const kind = getMediaKind(item);
    if (kind === 'movie' || kind === 'tv' || kind === 'person') {
      selectNode(
        { kind, id: String(item.id), label: item.title || item.name, source: item.indexer || 'tmdb' },
        true,
      );
    }
  }, [selectNode]);

  return (
    <ViewLayout
      className={baseRoute === 'search' ? 'view-search view-explore' : 'view-explore'}
      view={baseRoute}
    >
      <ViewHeader
        title={baseRoute === 'search' ? 'Search' : 'Discovery Graph'}
        subtitle={
          baseRoute === 'search'
            ? <p>Search TMDB/TVDB metadata graph (movies, TV, people).</p>
            : <p>Traverse TMDB/TVDB metadata across movies, TV shows, cast and related works.</p>
        }
      />
      <ExploreToolbar
        source={source}
        mode={mode}
        mediaType={mediaType}
        timeWindow={timeWindow}
        trendingMode={trendingMode}
        searchQuery={searchInput}
        onSourceChange={setSource}
        onModeChange={(v) => {
          setMode(v);
          if (v === 'discover' && mediaType === 'all') setTrendingMode(true);
        }}
        onMediaTypeChange={handleMediaTypeChange}
        onTimeWindowChange={handleTimeWindowChange}
        onSearchQueryChange={(v) => {
          setSearchInput(v);
          setMode('search');
          setTrendingMode(false);
          scheduleCommittedSearch(v);
        }}
        onSubmit={handleFormSubmit}
        showTrendingWindow={showTrendingWindow}
      />
      <div className="explore-layout">
        {history.length === 0 && (
          <ExploreResults
            resultsTitle={resultsTitle}
            totalPages={totalPages}
            page={page}
            loading={resultsLoading}
            error={resultsError}
            items={items}
            onPagePrev={() => setPage((p) => Math.max(1, p - 1))}
            onPageNext={() => setPage((p) => Math.min(totalPages, p + 1))}
            onCardSelect={handleCardSelect}
            getGridActions={getGridActions}
          />
        )}
        {history.length > 0 && (
          <ExploreDetailPanel
            originLabel={originLabel}
            history={history}
            detailNode={detailNode}
            onBreadcrumbClick={handleBreadcrumbClick}
            selectNode={selectNode}
            fetchResults={fetchResults}
          />
        )}
      </div>
    </ViewLayout>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ViewLayout, ViewHeader } from '../../components/ui/PagePrimitives';
import { apiGet, apiPost } from '../../services/api';
import { notify } from '../../services/notify';
import { replaceRoute } from '../../services/router';
import { annotateLibraryStatus } from '../../services/libraryStatus';
import { getMediaKind, sortByPopularity, toCsv } from '../../services/utils';
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
import { ExploreToolbar } from './ExploreToolbar';
import { ExploreResults } from './ExploreResults';
import { ExploreDetailPanel } from './ExploreDetailPanel';

const POLL_STATUS_MS = 5000;

async function addItemToLibrary(item: any, seasonNumbers: number[] | null = null): Promise<boolean> {
  const kind = getMediaKind(item);
  if (kind !== 'movie' && kind !== 'tv') return false;

  let payload: any;
  if (kind === 'movie') {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'movie' };
  } else if (item.indexer === 'tvdb') {
    payload = { tvdb_ids: [String(item.tvdb_id || item.id)], media_type: 'tv' };
  } else {
    payload = { tmdb_ids: [String(item.tmdb_id || item.id)], media_type: 'tv' };
  }

  const res = await apiPost('/items/add', payload);
  if (!res.ok) {
    notify(res.error || 'Failed to add media', 'error');
    return false;
  }

  if (kind === 'tv' && seasonNumbers && seasonNumbers.length > 0) {
    const scrapePayload: any = {
      media_type: 'tv',
      season_numbers: seasonNumbers,
    };
    if (item.indexer === 'tvdb') {
      scrapePayload.tvdb_id = String(item.tvdb_id || item.id);
    } else {
      scrapePayload.tmdb_id = String(item.tmdb_id || item.id);
    }
    const scrapeRes = await apiPost('/scrape/auto', scrapePayload);
    if (!scrapeRes.ok) {
      notify(`Added to library but failed to start season scrape: ${scrapeRes.error}`, 'warning');
      return true;
    }
    notify(`Added "${item.title || item.name}" — scraping ${seasonNumbers.length} season(s)`, 'success');
    return true;
  }

  notify(`Added "${item.title || item.name}" to library`, 'success');
  return true;
}

export default function ExploreView({ route }: { route: AppRoute }) {
  const query = route.query || {};
  const [source, setSource] = useState<'tmdb' | 'tvdb'>(query.source === 'tvdb' ? 'tvdb' : 'tmdb');
  const [mode, setMode] = useState<'search' | 'discover'>(query.mode === 'discover' ? 'discover' : 'search');
  const [mediaType, setMediaType] = useState<'movie' | 'tv' | 'all'>(
    ['movie', 'tv', 'all'].includes(query.type) ? (query.type as 'movie' | 'tv' | 'all') : 'movie',
  );
  const [timeWindow, setTimeWindow] = useState<'day' | 'week'>(query.window === 'day' ? 'day' : 'week');
  const [trendingMode, setTrendingMode] = useState(!!query.window);
  const [searchQuery, setSearchQuery] = useState(query.q || '');
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
  const [detailData, setDetailData] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [resultsTitle, setResultsTitle] = useState('Results');

  const statusPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const routeQueryKey = route.name === 'explore' ? JSON.stringify(route.query || {}) : '';
  const prevRouteQueryKeyRef = useRef(routeQueryKey);
  useEffect(() => {
    if (route.name !== 'explore' || routeQueryKey === prevRouteQueryKeyRef.current) return;
    prevRouteQueryKeyRef.current = routeQueryKey;
    const q = route.query || {};
    const trail = parseTrail(q.trail);
    const nodeFromQuery = parseNode(q.node);
    const nextHistory = trail.length ? trail : nodeFromQuery ? [nodeFromQuery] : [];
    setSource(q.source === 'tvdb' ? 'tvdb' : 'tmdb');
    setMode(q.mode === 'discover' ? 'discover' : 'search');
    setMediaType((['movie', 'tv', 'all'].includes(q.type) ? q.type : 'movie') as 'movie' | 'tv' | 'all');
    setTimeWindow(q.window === 'day' ? 'day' : 'week');
    setTrendingMode(!!q.window);
    setSearchQuery(q.q || '');
    setPage(parsePositiveInt(q.page, 1));
    setHistory(nextHistory);
    setTotalPages(1);
    setItems([]);
    setDetailNode(null);
    setDetailData(null);
    setResultsError(null);
    setResultsTitle('Results');
    didRestoreHistory.current = false;
  }, [route.name, routeQueryKey]);

  const syncRoute = useCallback(() => {
    replaceRoute('explore', null, buildRouteQuery({ source, mode, type: mediaType, window: timeWindow, query: searchQuery, page, history, trendingMode }));
  }, [source, mode, mediaType, timeWindow, searchQuery, page, history, trendingMode]);

  const fetchResults = useCallback(async () => {
    setResultsLoading(true);
    setResultsError(null);
    setResultsTitle('Loading…');

    let response: any;

    if (source === 'tvdb') {
      if (!searchQuery.trim()) {
        setResultsError('TVDB search requires a query.');
        setItems([]);
        setResultsLoading(false);
        return;
      }
      response = await apiGet('/search/tvdb', { query: searchQuery, limit: 20, offset: (page - 1) * 20 });
    } else if (mode === 'discover') {
      const useTrending = mediaType === 'all' || trendingMode;
      if (useTrending) {
        const type = mediaType === 'all' ? 'movie' : mediaType;
        response = await apiGet(`/trending/tmdb/${type}/${timeWindow}`);
      } else {
        response = await apiGet(`/discover/tmdb/${mediaType}`, { page });
      }
    } else if (mediaType === 'all') {
      response = await apiGet('/search/tmdb/multi', { query: searchQuery, page, include_people: true });
    } else {
      response = await apiGet(`/search/tmdb/${mediaType}`, { query: searchQuery, page });
    }

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
    setItems(annotated);
    setTotalPages(Number(response.data?.total_pages || 1));
    setResultsTitle(`Results (${response.data?.total_results ?? annotated.length})`);
    setResultsLoading(false);
    syncRoute();
  }, [source, mode, mediaType, timeWindow, trendingMode, searchQuery, page, syncRoute]);

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
        else if (item.tmdb_id || item.id) ids.tmdb.add(String(item.tmdb_id || item.id));
      }
    });
    if (detailData?.id && (detailData.media_type === 'movie' || detailData.media_type === 'tv' || getMediaKind(detailData) === 'tv')) {
      if (detailData.tmdb_id || detailData.id) ids.tmdb.add(String(detailData.tmdb_id || detailData.id));
      if (detailData.tvdb_id) ids.tvdb.add(String(detailData.tvdb_id));
    }
    return `${toCsv([...ids.tmdb].sort())}|${toCsv([...ids.tvdb].sort())}`;
  }, [items, detailData]);

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
      setItems((prev) =>
        prev.map((item) => {
          const k = getMediaKind(item);
          if (k !== 'movie' && k !== 'tv') return item;
          const status =
            item.indexer === 'tvdb' && item.tvdb_id ? tvdb[String(item.tvdb_id)] : tmdb[String(item.tmdb_id || item.id)] || tvdb[String(item.tvdb_id || item.id)];
          if (!status) return item;
          return { ...item, in_library: Boolean(status.in_library), library_item_id: status.library_item_id ?? null, state: status.library_state ?? item.state };
        }),
      );
      setDetailData((d: any) => {
        if (!d || (getMediaKind(d) !== 'movie' && getMediaKind(d) !== 'tv')) return d;
        const key = d.indexer === 'tvdb' ? String(d.tvdb_id || d.id) : String(d.tmdb_id || d.id);
        const status = d.indexer === 'tvdb' ? tvdb[key] : tmdb[key] || tvdb[String(d.tvdb_id)];
        if (!status) return d;
        return { ...d, in_library: Boolean(status.in_library), library_item_id: status.library_item_id, library_state: status.library_state };
      });
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
    async (node: ExploreNode, updateHistory = true) => {
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
      setDetailLoading(true);
      setDetailData(null);

      if (node.kind === 'person') {
        try {
          const personRes = await apiGet(`/tmdb/person/${node.id}`);
          if (!personRes.ok) {
            setDetailData({ error: personRes.error || 'Failed to load person.' });
            setDetailLoading(false);
            return;
          }
          const person = personRes.data || {};
          let rawCredits: any[] = [];
          if (person.combined_credits?.cast || person.combined_credits?.crew) {
            rawCredits = [...(person.combined_credits.cast || []), ...(person.combined_credits.crew || [])];
          } else {
            const creditsRes = await apiGet(`/tmdb/person/${node.id}/combined_credits`);
            if (creditsRes.ok && creditsRes.data) {
              rawCredits = [...(creditsRes.data.cast || []), ...(creditsRes.data.crew || [])];
            }
          }
          const credits = rawCredits
            .map((entry: any) => toCardItem(entry))
            .filter((entry: any, index: number, arr: any[]) => arr.findIndex((c: any) => c.id === entry.id && getMediaKind(c) === getMediaKind(entry)) === index);
          const annotated = await annotateLibraryStatus(credits);
          const ranked = sortByPopularity(annotated).slice(0, 24);
          setDetailData({ kind: 'person', person, credits: ranked });
        } catch (e) {
          setDetailData({ error: e instanceof Error ? e.message : 'Failed to load person.' });
        }
        setDetailLoading(false);
        syncRoute();
        return;
      }

      if (node.source === 'tvdb' && node.kind === 'tv') {
        const [tvdbRes, statusRes] = await Promise.all([
          apiGet(`/tvdb/series/${node.id}`),
          apiGet('/items/library/status', { tvdb_ids: String(node.id) }),
        ]);
        if (!tvdbRes.ok) {
          setDetailData({ error: tvdbRes.error || 'Failed to load TVDB details.' });
          setDetailLoading(false);
          return;
        }
        const series = tvdbRes.data || {};
        const status = statusRes.data?.tvdb?.[String(node.id)] || null;
        setDetailData({
          kind: 'tvdb-tv',
          media: {
            ...series,
            in_library: Boolean(status?.in_library),
            library_item_id: status?.library_item_id ?? null,
            library_state: status?.library_state ?? null,
            poster_path: series.image || series.poster_path,
            title: series.name || series.title,
          },
        });
        setDetailLoading(false);
        syncRoute();
        return;
      }

      const detailRes = await apiGet(`/tmdb/${node.kind}/${node.id}`);
      if (!detailRes.ok) {
        setDetailData({ error: detailRes.error || 'Failed to load media details.' });
        setDetailLoading(false);
        return;
      }
      const media = detailRes.data || {};
      const recommendations = (media.recommendations?.results || []).map((entry: any) => toCardItem(entry, node.kind));
      const similar = (media.similar?.results || []).map((entry: any) => toCardItem(entry, node.kind));
      await annotateLibraryStatus(recommendations);
      await annotateLibraryStatus(similar);
      setDetailData({ kind: node.kind, media, recommendations, similar });
      setDetailLoading(false);
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
        setDetailData(null);
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
      setPage(1);
      setHistory([]);
      setDetailNode(null);
      setDetailData(null);
      if (source === 'tvdb' && mediaType === 'all') setMediaType('tv');
      if (mode === 'search' && !searchQuery.trim() && source === 'tmdb') {
        notify('Enter a query for TMDB search', 'warning');
      }
      fetchResults();
    },
    [source, mode, mediaType, searchQuery, fetchResults],
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
          replaceRoute('explore', null, buildRouteQuery({ source: 'tmdb', mode: 'discover', type: seed.kind === 'tv' ? 'tv' : 'movie', query: '', page: 1, history: [node] }));
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
            const ok = await addItemToLibrary(item);
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
    <ViewLayout className="view-explore" view="explore">
      <ViewHeader
        title="Discovery Graph"
        subtitle={<p>Traverse TMDB/TVDB metadata across movies, TV shows, cast and related works.</p>}
      />
      <ExploreToolbar
        source={source}
        mode={mode}
        mediaType={mediaType}
        timeWindow={timeWindow}
        trendingMode={trendingMode}
        searchQuery={searchQuery}
        onSourceChange={setSource}
        onModeChange={(v) => {
          setMode(v);
          if (v === 'discover' && mediaType === 'all') setTrendingMode(true);
        }}
        onMediaTypeChange={handleMediaTypeChange}
        onTimeWindowChange={handleTimeWindowChange}
        onSearchQueryChange={(v) => {
          setSearchQuery(v);
          setMode('search');
          setTrendingMode(false);
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
            detailLoading={detailLoading}
            detailData={detailData}
            onBreadcrumbClick={handleBreadcrumbClick}
            selectNode={selectNode}
            addItemToLibrary={addItemToLibrary}
            fetchResults={fetchResults}
          />
        )}
      </div>
    </ViewLayout>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import { ViewLayout, ViewHeader } from '../components/ui/PagePrimitives';
import { MediaGrid } from '../ui/MediaGrid';
import { MediaTypeToggle, type MediaTypeValue } from '../ui/MediaTypeToggle';
import { CastCrew } from '../ui/panels/CastCrew';
import { SimilarRecommendations } from '../ui/panels/SimilarRecommendations';
import { apiGet, apiPost } from '../services/api';
import { notify } from '../services/notify';
import { replaceRoute } from '../services/router';
import { annotateLibraryStatus } from '../services/libraryStatus';
import { formatYear, getMediaKind, sortByPopularity, toCsv } from '../services/utils';
import type { AppRoute } from '../app/routeTypes';

type ExploreNode = {
  source: string;
  kind: string;
  id: string;
  label?: string;
};

function parseNode(raw: string | undefined): ExploreNode | null {
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

function serializeNode(node: ExploreNode): string {
  return `${node.source || 'tmdb'}|${node.kind}|${node.id}`;
}

function parseTrail(raw: string | undefined): ExploreNode[] {
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

function toCardItem(entry: any, fallbackKind: string | null = null): any {
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

function parsePositiveInt(value: unknown, fallback = 1): number {
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function buildRouteQuery(state: {
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

function getOriginLabel(state: {
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

const POLL_STATUS_MS = 5000;

export default function ExploreView({ route }: { route: AppRoute }) {
  const query = route.query || {};
  const [source, setSource] = useState<'tmdb' | 'tvdb'>(query.source === 'tvdb' ? 'tvdb' : 'tmdb');
  const [mode, setMode] = useState<'search' | 'discover'>(query.mode === 'discover' ? 'discover' : 'search');
  const [mediaType, setMediaType] = useState<MediaTypeValue>(['movie', 'tv', 'all'].includes(query.type) ? (query.type as MediaTypeValue) : 'movie');
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

  const syncRoute = useCallback(() => {
    replaceRoute('explore', null, buildRouteQuery({
      source,
      mode,
      type: mediaType,
      window: timeWindow,
      query: searchQuery,
      page,
      history,
      trendingMode,
    }));
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
      response = await apiGet('/search/tvdb', {
        query: searchQuery,
        limit: 20,
        offset: (page - 1) * 20,
      });
    } else if (mode === 'discover') {
      const useTrending = mediaType === 'all' || trendingMode;
      if (useTrending) {
        const type = mediaType === 'all' ? 'movie' : mediaType;
        response = await apiGet(`/trending/tmdb/${type}/${timeWindow}`);
      } else {
        response = await apiGet(`/discover/tmdb/${mediaType}`, { page });
      }
    } else if (mediaType === 'all') {
      response = await apiGet('/search/tmdb/multi', {
        query: searchQuery,
        page,
        include_people: true,
      });
    } else {
      response = await apiGet(`/search/tmdb/${mediaType}`, {
        query: searchQuery,
        page,
      });
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
      if (cancelled || didRestoreHistory.current) return;
      if (history.length > 0) {
        didRestoreHistory.current = true;
        selectNode(history[history.length - 1], false);
      }
    })();
    return () => { cancelled = true; };
  }, [fetchResults]);

  // Status polling for grid/detail cards
  useEffect(() => {
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
    if (ids.tmdb.size === 0 && ids.tvdb.size === 0) return;

    const poll = async () => {
      const res = await apiGet('/items/library/status', {
        tmdb_ids: toCsv(Array.from(ids.tmdb)),
        tvdb_ids: toCsv(Array.from(ids.tvdb)),
      });
      if (!res.ok) return;
      const tmdb = res.data?.tmdb || {};
      const tvdb = res.data?.tvdb || {};
      setItems((prev) => {
        const next = prev.map((item) => {
          const k = getMediaKind(item);
          if (k !== 'movie' && k !== 'tv') return item;
          const status = item.indexer === 'tvdb' && item.tvdb_id ? tvdb[String(item.tvdb_id)] : tmdb[String(item.tmdb_id || item.id)] || tvdb[String(item.tvdb_id || item.id)];
          if (!status) return item;
          return { ...item, in_library: Boolean(status.in_library), library_item_id: status.library_item_id ?? null, state: status.library_state ?? item.state };
        });
        return next;
      });
      if (detailData && (getMediaKind(detailData) === 'movie' || getMediaKind(detailData) === 'tv')) {
        const key = detailData.indexer === 'tvdb' ? String(detailData.tvdb_id || detailData.id) : String(detailData.tmdb_id || detailData.id);
        const status = detailData.indexer === 'tvdb' ? tvdb[key] : tmdb[key] || tvdb[String(detailData.tvdb_id)];
        if (status) setDetailData((d: any) => d ? { ...d, in_library: Boolean(status.in_library), library_item_id: status.library_item_id, library_state: status.library_state } : d);
      }
    };

    poll();
    statusPollRef.current = setInterval(poll, POLL_STATUS_MS);
    return () => {
      if (statusPollRef.current) clearInterval(statusPollRef.current);
    };
  }, [items, detailData]);

  const selectNode = useCallback(async (node: ExploreNode, updateHistory = true) => {
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
      const [personRes, creditsRes] = await Promise.all([
        apiGet(`/tmdb/person/${node.id}`),
        apiGet(`/tmdb/person/${node.id}/combined_credits`),
      ]);
      if (!personRes.ok || !creditsRes.ok) {
        setDetailData({ error: personRes.error || creditsRes.error || 'Failed to load person.' });
        setDetailLoading(false);
        return;
      }
      const person = personRes.data || {};
      const credits = [...(creditsRes.data?.cast || []), ...(creditsRes.data?.crew || [])]
        .map((entry: any) => toCardItem(entry))
        .filter((entry: any, index: number, arr: any[]) => arr.findIndex((c: any) => c.id === entry.id && getMediaKind(c) === getMediaKind(entry)) === index);
      const annotated = await annotateLibraryStatus(credits);
      const ranked = sortByPopularity(annotated).slice(0, 24);
      setDetailData({ kind: 'person', person, credits: ranked });
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
    setDetailData({
      kind: node.kind,
      media,
      recommendations,
      similar,
    });
    setDetailLoading(false);
    syncRoute();
  }, [syncRoute]);

  const handleBreadcrumbClick = useCallback((clickedIndex: number) => {
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
  }, [history, selectNode, syncRoute]);

  const handleFormSubmit = useCallback((e: React.FormEvent) => {
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
  }, [source, mode, mediaType, searchQuery, fetchResults]);

  // Init from route (e.g. seed from sessionStorage)
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
          const node: ExploreNode = {
            kind: seed.kind,
            id: String(seed.id),
            label: seed.label || `${seed.kind} ${seed.id}`,
            source: seed.source || 'tmdb',
          };
          setHistory([node]);
          replaceRoute('explore', null, buildRouteQuery({
            source: 'tmdb',
            mode: 'discover',
            type: seed.kind === 'tv' ? 'tv' : 'movie',
            query: '',
            page: 1,
            history: [node],
          }));
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

  const getGridActions = (item: any) => {
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
  };

  const handleCardSelect = (item: any) => {
    const kind = getMediaKind(item);
    if (kind === 'movie' || kind === 'tv' || kind === 'person') {
      selectNode({
        kind,
        id: String(item.id),
        label: item.title || item.name,
        source: item.indexer || 'tmdb',
      }, true);
    }
  };

  return (
    <ViewLayout className="view-explore" view="explore">
      <ViewHeader
        title="Discovery Graph"
        subtitle={
          <p>Traverse TMDB/TVDB metadata across movies, TV shows, cast and related works.</p>
        }
      />
      <form className="toolbar toolbar--explore" onSubmit={handleFormSubmit}>
        <select value={source} onChange={(e) => setSource(e.target.value as 'tmdb' | 'tvdb')}>
          <option value="tmdb">TMDB</option>
          <option value="tvdb">TVDB</option>
        </select>
        <select value={mode} onChange={(e) => { setMode(e.target.value as 'search' | 'discover'); if (e.target.value === 'discover' && mediaType === 'all') setTrendingMode(true); }}>
          <option value="search">Search</option>
          <option value="discover">Discover</option>
        </select>
        <MediaTypeToggle
          value={mediaType}
          includeAll
          onChange={(v) => {
            setMediaType(v);
            if (source === 'tvdb' && v === 'all') setMediaType('tv');
            if (mode === 'discover' && v === 'all') setTrendingMode(true);
            syncRoute();
            setPage(1);
            fetchResults();
          }}
        />
        {showTrendingWindow && (
          <select value={timeWindow} onChange={(e) => { setTimeWindow(e.target.value as 'day' | 'week'); setTrendingMode(true); syncRoute(); setPage(1); fetchResults(); }}>
            <option value="day">Today</option>
            <option value="week">This Week</option>
          </select>
        )}
        <input
          type="search"
          placeholder="Search title / person / keywords"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setMode('search');
            setTrendingMode(false);
          }}
        />
        <button className="btn btn--primary" type="submit">Load</button>
      </form>

      <div className={`explore-layout explore-layout--results-only ${history.length > 0 ? 'explore-layout--detail-focused' : ''}`}>
        <section className="explore-results">
          <div className="section-head">
            <h2>{resultsTitle}</h2>
            {totalPages > 1 && (
              <div className="pagination-bar pagination-bar--inline">
                <button type="button" className="btn btn--secondary btn--small" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Previous</button>
                <span>Page {page} / {totalPages}</span>
                <button type="button" className="btn btn--secondary btn--small" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Next</button>
              </div>
            )}
          </div>
          {resultsLoading ? (
            <p className="muted">Loading…</p>
          ) : resultsError ? (
            <p className="empty-state">{resultsError}</p>
          ) : items.length === 0 ? (
            <p className="empty-state">No results.</p>
          ) : (
            <MediaGrid
              items={items}
              href={null}
              onSelect={handleCardSelect}
              actions={getGridActions}
              className="media-grid--dense"
            />
          )}
        </section>

        <aside className="explore-panel" data-slot="detail-panel">
          <div className="section-head">
            <h2>Metadata Graph</h2>
          </div>
          <div className="explore-breadcrumbs">
            {[{ label: originLabel, kind: 'origin' }, ...history].map((node, index) => (
              <button
                key={index}
                type="button"
                className={`pill pill--${node.kind || 'origin'}`}
                onClick={() => handleBreadcrumbClick(index)}
              >
                {node.label || (node.kind === 'origin' ? originLabel : `${node.kind} ${'id' in node ? node.id : ''}`)}
              </button>
            ))}
          </div>
          <div className="explore-detail">
            {!detailNode && (
              <p className="muted">Select a card to inspect cast, recommendations, and linked entries.</p>
            )}
            {detailLoading && <p className="muted">Loading details…</p>}
            {detailData?.error && <p className="muted">{detailData.error}</p>}
            {detailData?.kind === 'person' && (
              <ExploreDetailPerson
                person={detailData.person}
                credits={detailData.credits}
                onSelectNode={selectNode}
                onBack={() => history[0] && selectNode(history[0], false)}
              />
            )}
            {detailData?.kind === 'tvdb-tv' && (
              <ExploreDetailTvdb
                series={detailData.media}
                node={detailNode!}
                onAdd={addItemToLibrary}
                onOpen={() => { if (detailData.media.library_item_id) window.location.hash = `#/item/${detailData.media.library_item_id}`; }}
                onRefresh={fetchResults}
                onReselect={() => detailNode && selectNode(detailNode, false)}
              />
            )}
            {detailData?.kind === 'movie' || detailData?.kind === 'tv' ? (
              <ExploreDetailTmdb
                media={detailData.media}
                recommendations={detailData.recommendations}
                similar={detailData.similar}
                kind={detailData.kind}
                node={detailNode!}
                onAdd={addItemToLibrary}
                onOpen={() => { if (detailData.media.library?.library_item_id) window.location.hash = `#/item/${detailData.media.library.library_item_id}`; }}
                onRefresh={fetchResults}
                onReselect={() => detailNode && selectNode(detailNode, false)}
                onPersonSelect={(p) => selectNode({ kind: 'person', id: p.id, label: p.name, source: 'tmdb' }, true)}
                onMediaSelect={(node) => selectNode(node, true)}
              />
            ) : null}
          </div>
        </aside>
      </div>
    </ViewLayout>
  );
}

function ExploreDetailPerson({
  person,
  credits,
  onSelectNode,
  onBack,
}: {
  person: any;
  credits: any[];
  onSelectNode: (node: ExploreNode, updateHistory?: boolean) => void;
  onBack: () => void;
}) {
  const poster = person.poster_path || person.profile_path || '';
  const posterUrl = poster ? (poster.startsWith('http') ? poster : `https://image.tmdb.org/t/p/w500${poster}`) : '';
  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={person.name || 'person'} />}
        <div>
          <h3>{person.name || 'Unknown'}</h3>
          <p className="muted">
            {[person.known_for_department, person.vote_average ? `Rating ${Number(person.vote_average).toFixed(1)}` : null].filter(Boolean).join(' · ') || '—'}
          </p>
          <p className="muted">{person.biography || person.overview || 'No summary available.'}</p>
          <div className="toolbar">
            <button type="button" className="btn btn--primary btn--small" onClick={onBack}>Back to Results</button>
          </div>
        </div>
      </div>
      <h3>Known Works</h3>
      <div className="detail-link-grid">
        <MediaGrid
          items={credits.slice(0, 24)}
          href={null}
          onSelect={(item: any) => onSelectNode({ kind: getMediaKind(item), id: String(item.id), label: item.title || item.name, source: item.indexer || 'tmdb' }, true)}
        />
      </div>
    </section>
  );
}

function ExploreDetailTvdb({
  series,
  node,
  onAdd,
  onOpen,
  onRefresh,
  onReselect,
}: {
  series: any;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void;
}) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const seasons = (series.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const posterUrl = series.poster_path ? (series.poster_path.startsWith('http') ? series.poster_path : `https://image.tmdb.org/t/p/w500${series.poster_path}`) : '';
  const inLibrary = series.in_library && series.library_item_id;

  const handleAdd = async () => {
    if (inLibrary) {
      onOpen();
      return;
    }
    const seasonNumbers = selectedSeasons.size > 0 && selectedSeasons.size < seasons.length
      ? Array.from(selectedSeasons).sort((a, b) => a - b)
      : null;
    const ok = await onAdd(
      { ...series, media_type: 'tv', id: node.id, indexer: 'tvdb', tvdb_id: node.id },
      seasonNumbers,
    );
    if (ok) {
      onRefresh();
      onReselect();
    }
  };

  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={series.title || 'series'} />}
        <div>
          <h3>{series.title || series.name || 'Unknown'}</h3>
          <p className="muted">
            {[formatYear(series), series.library_state].filter(Boolean).join(' · ') || '—'}
          </p>
          <p className="muted">{series.overview || 'No summary available.'}</p>
          {!inLibrary && seasons.length > 0 && (
            <div className="season-selector">
              <div className="season-selector__header">
                <span className="season-selector__label">Seasons: {selectedSeasons.size} of {seasons.length} selected</span>
                <button type="button" className="btn btn--secondary btn--small" onClick={() => setSelectedSeasons((prev) => prev.size === seasons.length ? new Set() : new Set(seasons.map((s: any) => s.season_number ?? s.number ?? 0)))}>Toggle All</button>
              </div>
              <div className="season-selector__list">
                {seasons.map((s: any) => {
                  const num = s.season_number ?? s.number ?? 0;
                  return (
                    <label key={num} className="season-selector__item">
                      <input
                        type="checkbox"
                        checked={selectedSeasons.has(num)}
                        onChange={(e) => setSelectedSeasons((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(num); else next.delete(num);
                          return next;
                        })}
                      />
                      <span>{s.name || `Season ${num}`}{(s.episode_count ?? s.episodes?.length) ? ` (${s.episode_count ?? s.episodes?.length} eps)` : ''}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
          <div className="toolbar">
            <button type="button" className="btn btn--primary btn--small" onClick={handleAdd}>
              {inLibrary ? 'Open Library Item' : 'Add to Library'}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function ExploreDetailTmdb({
  media,
  recommendations,
  similar,
  kind,
  node,
  onAdd,
  onOpen,
  onRefresh,
  onReselect,
  onPersonSelect,
  onMediaSelect,
}: {
  media: any;
  recommendations: any[];
  similar: any[];
  kind: string;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void;
  onPersonSelect: (p: { id: string; name: string }) => void;
  onMediaSelect: (node: ExploreNode) => void;
}) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const lib = media.library;
  const isInLibrary = lib?.in_library && lib?.library_item_id;
  const seasons = (media.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const posterUrl = (media.poster_path || media.profile_path) ? (media.poster_path?.startsWith('http') ? media.poster_path : `https://image.tmdb.org/t/p/w500${media.poster_path || media.profile_path}`) : '';

  const handleAdd = async () => {
    if (isInLibrary) {
      onOpen();
      return;
    }
    const seasonNumbers = kind === 'tv' && selectedSeasons.size > 0 && selectedSeasons.size < seasons.length
      ? Array.from(selectedSeasons).sort((a, b) => a - b)
      : null;
    const ok = await onAdd({ ...media, media_type: kind }, seasonNumbers);
    if (ok) {
      onRefresh();
      onReselect();
    }
  };

  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={media.title || media.name || 'media'} />}
        <div>
          <h3>{media.title || media.name || 'Unknown'}</h3>
          <p className="muted">
            {[kind.toUpperCase(), formatYear(media), media.vote_average ? `Rating ${Number(media.vote_average).toFixed(1)}` : null, lib?.library_state].filter(Boolean).join(' · ') || '—'}
          </p>
          <p className="muted">{media.overview || media.biography || 'No summary available.'}</p>
          {kind === 'tv' && !isInLibrary && seasons.length > 0 && (
            <div className="season-selector">
              <div className="season-selector__header">
                <span className="season-selector__label">Seasons: {selectedSeasons.size} of {seasons.length} selected</span>
                <button type="button" className="btn btn--secondary btn--small" onClick={() => setSelectedSeasons((prev) => prev.size === seasons.length ? new Set() : new Set(seasons.map((s: any) => s.season_number ?? s.number ?? 0)))}>Toggle All</button>
              </div>
              <div className="season-selector__list">
                {seasons.map((s: any) => {
                  const num = s.season_number ?? s.number ?? 0;
                  return (
                    <label key={num} className="season-selector__item">
                      <input type="checkbox" checked={selectedSeasons.has(num)} onChange={(e) => setSelectedSeasons((prev) => { const next = new Set(prev); if (e.target.checked) next.add(num); else next.delete(num); return next; })} />
                      <span>{s.name || `Season ${num}`}{(s.episode_count ?? s.episodes?.length) ? ` (${s.episode_count ?? s.episodes?.length} eps)` : ''}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
          <div className="toolbar">
            <button type="button" className="btn btn--primary btn--small" onClick={handleAdd}>
              {isInLibrary ? 'Open Library Item' : 'Add to Library'}
            </button>
          </div>
        </div>
      </div>
      <CastCrew credits={media.credits ?? null} onPersonSelect={onPersonSelect} />
      <SimilarRecommendations
        data={{ recommendations, similar }}
        onMediaSelect={onMediaSelect}
      />
    </section>
  );
}

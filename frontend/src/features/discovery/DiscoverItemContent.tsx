import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiGet } from '../../shared/api/api';
import { annotateLibraryStatus } from '../library/libraryStatus';
import { getMediaKind, sortByPopularity } from '../../shared/utils/utils';
import type { MediaNode } from '../item-detail/SimilarRecommendations';
import type { ExploreNode } from '../explore/types';
import { toCardItem } from '../explore/types';
import { ExploreDetailPerson } from '../explore/ExploreDetailPerson';
import { ExploreDetailTvdb } from '../explore/ExploreDetailTvdb';
import { ExploreDetailTmdb } from '../explore/ExploreDetailTmdb';
import { addDiscoverItemToLibrary } from './discoverItemLibrary';

const POLL_STATUS_MS = 5000;

export type DiscoverItemContentProps = {
  source: 'tmdb' | 'tvdb';
  kind: 'movie' | 'tv' | 'person';
  id: string;
  onNavigateToItem: (node: ExploreNode) => void;
  onNavigateFromMedia: (n: MediaNode) => void;
  onBackFromPerson: () => void;
  /** e.g. refetch the explore result grid after a successful add. */
  onAfterLibraryAction?: () => void;
};

export function DiscoverItemContent({
  source,
  kind,
  id,
  onNavigateToItem,
  onNavigateFromMedia,
  onBackFromPerson,
  onAfterLibraryAction,
}: DiscoverItemContentProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<any>(null);
  const mediaRef = useRef<any>(null);
  const kindRef = useRef<string>('');
  if (detailData?.media) mediaRef.current = detailData.media;
  if (detailData?.kind) kindRef.current = detailData.kind;

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDetailData(null);

    if (source === 'tmdb' && kind === 'person') {
      try {
        const personRes = await apiGet(`/tmdb/person/${id}`);
        if (!personRes.ok) {
          setError(personRes.error || 'Failed to load person.');
          setLoading(false);
          return;
        }
        const person = personRes.data || {};
        let rawCredits: any[] = [];
        if (person.combined_credits?.cast || person.combined_credits?.crew) {
          rawCredits = [...(person.combined_credits.cast || []), ...(person.combined_credits.crew || [])];
        } else {
          const creditsRes = await apiGet(`/tmdb/person/${id}/combined_credits`);
          if (creditsRes.ok && creditsRes.data) {
            rawCredits = [...(creditsRes.data.cast || []), ...(creditsRes.data.crew || [])];
          }
        }
        const credits = rawCredits
          .map((entry: any) => toCardItem(entry))
          .filter(
            (entry: any, index: number, arr: any[]) =>
              arr.findIndex((c: any) => c.id === entry.id && getMediaKind(c) === getMediaKind(entry)) === index,
          );
        const annotated = await annotateLibraryStatus(credits);
        const ranked = sortByPopularity(annotated).slice(0, 24);
        setDetailData({ kind: 'person', person, credits: ranked });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load person.');
      }
      setLoading(false);
      return;
    }

    if (source === 'tvdb' && kind === 'tv') {
      const [tvdbRes, statusRes] = await Promise.all([
        apiGet(`/tvdb/series/${id}`),
        apiGet('/items/library/status', { tvdb_ids: String(id) }),
      ]);
      if (!tvdbRes.ok) {
        setError(tvdbRes.error || 'Failed to load TVDB details.');
        setLoading(false);
        return;
      }
      const series = tvdbRes.data || {};
      const status = statusRes.data?.tvdb?.[String(id)] || null;
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
      setLoading(false);
      return;
    }

    if (source === 'tmdb' && (kind === 'movie' || kind === 'tv')) {
      const detailRes = await apiGet(`/tmdb/${kind}/${id}`);
      if (!detailRes.ok) {
        setError(detailRes.error || 'Failed to load media details.');
        setLoading(false);
        return;
      }
      const media = detailRes.data || {};
      const recommendations = (media.recommendations?.results || []).map((entry: any) => toCardItem(entry, kind));
      const similar = (media.similar?.results || []).map((entry: any) => toCardItem(entry, kind));
      await annotateLibraryStatus(recommendations);
      await annotateLibraryStatus(similar);
      if (kind === 'tv' && !media.tvdb_id && media.external_ids?.tvdb_id) {
        media.tvdb_id = String(media.external_ids.tvdb_id);
      }
      if (media.library) {
        media.in_library = Boolean(media.library.in_library);
        media.library_item_id = media.library.library_item_id ?? null;
        media.library_state = media.library.library_state ?? null;
      }
      setDetailData({ kind, media, recommendations, similar });
      setLoading(false);
      return;
    }

    setError('Invalid item type for this view.');
    setLoading(false);
  }, [source, kind, id]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const statusPollKey = useMemo(() => {
    if (!detailData || detailData.kind === 'person') return null;
    const m = detailData.media;
    if (!m) return null;
    if (detailData.kind === 'tvdb-tv' || m.indexer === 'tvdb') {
      return `tvdb:${String(m.tvdb_id || m.id || '')}`;
    }
    if (detailData.kind === 'movie' || detailData.kind === 'tv') {
      return `t:${String(m.tmdb_id || m.id)}|v:${m.tvdb_id || ''}`;
    }
    return null;
  }, [detailData?.kind, detailData?.media?.tmdb_id, detailData?.media?.tvdb_id, detailData?.media?.id]);

  useEffect(() => {
    if (!statusPollKey) return;
    const poll = async () => {
      const m = mediaRef.current;
      if (!m) return;
      const k = getMediaKind(m);
      if (k !== 'movie' && k !== 'tv') return;
      const dk = kindRef.current;
      const tmdbIds =
        dk === 'tvdb-tv' || m.indexer === 'tvdb' ? undefined : m.tmdb_id || m.id ? String(m.tmdb_id || m.id) : undefined;
      const tvdbIds =
        dk === 'tvdb-tv' || m.indexer === 'tvdb'
          ? String(m.tvdb_id || m.id)
          : m.tvdb_id
            ? String(m.tvdb_id)
            : undefined;
      const res = await apiGet('/items/library/status', { tmdb_ids: tmdbIds, tvdb_ids: tvdbIds });
      if (!res.ok) return;
      setDetailData((d: any) => {
        if (!d?.media) return d;
        const dm = d.media;
        const kk = getMediaKind(dm);
        if (kk !== 'movie' && kk !== 'tv') return d;
        const tmdb = res.data?.tmdb || {};
        const tvdb = res.data?.tvdb || {};
        const resolve = () => {
          if (dm.indexer === 'tvdb' || d.kind === 'tvdb-tv') return tvdb[String(dm.tvdb_id || dm.id)];
          const fromTmdb = tmdb[String(dm.tmdb_id || dm.id)];
          const fromTvdb = dm.tvdb_id ? tvdb[String(dm.tvdb_id)] : null;
          return fromTvdb?.in_library ? fromTvdb : fromTmdb;
        };
        const st = resolve();
        if (!st) return d;
        return {
          ...d,
          media: {
            ...dm,
            in_library: Boolean(st.in_library),
            library_item_id: st.library_item_id ?? null,
            library_state: st.library_state ?? null,
          },
        };
      });
    };
    const interval = setInterval(poll, POLL_STATUS_MS);
    poll();
    return () => clearInterval(interval);
  }, [statusPollKey]);

  const afterGridRefresh = useCallback(() => {
    onAfterLibraryAction?.();
  }, [onAfterLibraryAction]);

  const tmdbNode: ExploreNode = {
    source: 'tmdb',
    kind: detailData?.kind === 'movie' || detailData?.kind === 'tv' ? detailData.kind : kind,
    id,
    label: detailData?.media?.title || detailData?.media?.name || '',
  };

  if (loading) {
    return <p className="muted">Loading…</p>;
  }
  if (error) {
    return <p className="empty-state">{error}</p>;
  }
  if (detailData?.kind === 'person') {
    return (
      <ExploreDetailPerson
        person={detailData.person}
        credits={detailData.credits}
        onSelectNode={onNavigateToItem}
        onBack={onBackFromPerson}
      />
    );
  }
  if (detailData?.kind === 'tvdb-tv') {
    return (
      <ExploreDetailTvdb
        series={detailData.media}
        node={{ source: 'tvdb', kind: 'tv', id, label: detailData.media?.title || detailData.media?.name }}
        onAdd={addDiscoverItemToLibrary}
        onOpen={() => {
          if (detailData.media.library_item_id) {
            window.location.hash = `#/item/${detailData.media.library_item_id}`;
          }
        }}
        onRefresh={afterGridRefresh}
        onReselect={loadDetail}
      />
    );
  }
  if (detailData?.kind === 'movie' || detailData?.kind === 'tv') {
    return (
      <ExploreDetailTmdb
        media={detailData.media}
        recommendations={detailData.recommendations}
        similar={detailData.similar}
        kind={detailData.kind}
        node={tmdbNode}
        onAdd={addDiscoverItemToLibrary}
        onOpen={() => {
          if (detailData.media.library_item_id) {
            window.location.hash = `#/item/${detailData.media.library_item_id}`;
          }
        }}
        onRefresh={afterGridRefresh}
        onReselect={loadDetail}
        onPersonSelect={(p) => onNavigateToItem({ kind: 'person', id: String(p.id), label: p.name, source: 'tmdb' })}
        onMediaSelect={onNavigateFromMedia}
      />
    );
  }
  return <p className="muted">No details available for this item.</p>;
}

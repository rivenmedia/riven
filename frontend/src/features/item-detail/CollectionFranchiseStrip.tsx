/**
 * Horizontal strip of other films in a TMDB collection. Fails soft if the API errors.
 */

import { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../../shared/api/api';
import { annotateLibraryStatus } from '../library/libraryStatus';
import { buildDiscoverItemHash, buildHash } from '../../shared/routing/router';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w185';

export type BelongsToCollection = {
  id?: number;
  name?: string;
  poster_path?: string | null;
};

type CollectionPart = {
  id: number;
  title: string;
  poster_path?: string | null;
  release_date?: string;
};

type CollectionResponse = {
  name?: string;
  parts?: CollectionPart[];
};

function partYear(d?: string) {
  if (!d) return '';
  const y = d.slice(0, 4);
  return /^\d{4}$/.test(y) ? y : '';
}

export function CollectionFranchiseStrip({
  collectionId,
  currentTmdbId,
  belongsHint,
}: {
  collectionId: number;
  currentTmdbId: string;
  belongsHint?: BelongsToCollection | null;
}) {
  const [payload, setPayload] = useState<CollectionResponse | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setUnavailable(false);
    setPayload(null);
    try {
      const r = await apiGet(`/tmdb/collection/${collectionId}`);
      if (!r.ok || !r.data) {
        setUnavailable(true);
        return;
      }
      const data = r.data as CollectionResponse;
      const partList = data.parts;
      if (Array.isArray(partList) && partList.length) {
        const cards = partList.map((p) => ({
          id: p.id,
          title: p.title,
          media_type: 'movie' as const,
          tmdb_id: p.id,
        }));
        try {
          await annotateLibraryStatus(cards);
        } catch {
          /* keep strip without library chips */
        }
        type Annotated = (typeof cards)[number] & {
          library_item_id?: number | null;
          in_library?: boolean;
          library_state?: string | null;
        };
        const byId = new Map<number, Annotated>(
          cards.map((c) => [c.id, c as Annotated]),
        );
        const parts = partList.map((p) => {
          const a = byId.get(p.id);
          return {
            ...p,
            library_item_id: a?.library_item_id ?? null,
            in_library: a?.in_library,
            library_state: a?.library_state,
          };
        });
        setPayload({ ...data, parts });
        return;
      }
      setPayload(data);
    } catch {
      setUnavailable(true);
    } finally {
      setLoading(false);
    }
  }, [collectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const name = payload?.name || belongsHint?.name;
  const parts = (payload?.parts as CollectionPart[] | undefined) ?? [];
  const currentId = String(currentTmdbId);

  if (loading) {
    return (
      <div className="panel collection-franchise-strip collection-franchise-strip--loading">
        <div className="section-head">
          <h3>{name || 'Collection'}</h3>
        </div>
        <p className="muted collection-franchise-strip__status">Loading collection…</p>
      </div>
    );
  }

  if (unavailable) {
    if (!name) return null;
    return (
      <div className="panel collection-franchise-strip">
        <div className="section-head">
          <h3>Collection</h3>
        </div>
        <p className="muted collection-franchise-strip__status">
          <strong>{name}</strong> — other titles in this set are unavailable right now.
        </p>
      </div>
    );
  }

  if (!name && parts.length === 0) return null;

  return (
    <div className="panel collection-franchise-strip">
      <div className="section-head">
        <h3>{name || 'Collection'}</h3>
      </div>
      {parts.length > 0 && (
        <div className="collection-franchise-scroll">
          {parts.map((p) => {
            const isCurrent = String(p.id) === currentId;
            const href = buildDiscoverItemHash('tmdb', 'movie', String(p.id));
            const inLib = (p as { library_item_id?: number | null }).library_item_id;
            const year = partYear(p.release_date);
            const inner = (
              <>
                <div className="collection-franchise-card__img-wrap">
                  {p.poster_path ? (
                    <img
                      src={`${TMDB_IMG}${p.poster_path}`}
                      alt=""
                      className="collection-franchise-card__img"
                    />
                  ) : (
                    <div className="collection-franchise-card__img collection-franchise-card__img--ph" />
                  )}
                </div>
                <div className="collection-franchise-card__text">
                  <span className="collection-franchise-card__title">{p.title}</span>
                  {year ? (
                    <span className="collection-franchise-card__year">{year}</span>
                  ) : null}
                </div>
                {inLib != null && (
                  <span className="legend-chip legend-chip--in-library">In library</span>
                )}
                {isCurrent && <span className="legend-chip">Current</span>}
              </>
            );
            if (isCurrent) {
              return (
                <div
                  key={p.id}
                  className="collection-franchise-card collection-franchise-card--current"
                >
                  {inner}
                </div>
              );
            }
            return (
              <a
                key={p.id}
                className="collection-franchise-card"
                href={inLib != null ? buildHash('item', String(inLib)) : href}
              >
                {inner}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}

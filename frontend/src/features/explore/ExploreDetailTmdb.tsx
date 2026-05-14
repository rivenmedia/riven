import { useEffect, useMemo, useState } from 'react';
import { CastCrew } from '../item-detail/CastCrew';
import { CollectionFranchiseStrip } from '../item-detail/CollectionFranchiseStrip';
import { EntityHeader } from '../item-detail/EntityHeader';
import { tmdbMediaToEntityHeaderData } from '../item-detail/discoveryEntityHeaderMappers';
import {
  MediaOverviewTabPanel,
  MediaOverviewTabStrip,
  mediaOverviewTabDefinitions,
  type MediaOverviewTabId,
} from '../item-detail/MediaOverviewTabs';
import { SimilarRecommendations } from '../item-detail/SimilarRecommendations';
import { TmdbDetailsPanel } from '../item-detail/TmdbDetailsPanel';
import { creditsHaveContent } from '../item-detail/creditsUtils';
import { DetailViewActionsToolbar } from '../../shared/ui/DetailViewActionsToolbar';
import type { ExploreNode } from './types';

const DISCOVER_TMDB_OVERVIEW_PANEL_ID = 'discover-tmdb-media-overview-panel';

export type ExploreDetailTmdbProps = {
  media: any;
  recommendations: any[];
  similar: any[];
  kind: string;
  node: ExploreNode;
  onAdd: (item: any, seasons?: number[] | null) => Promise<boolean>;
  onOpen: () => void;
  onRefresh: () => void;
  onReselect: () => void | Promise<void>;
  onPersonSelect: (p: { id: string; name: string }) => void;
  onMediaSelect: (node: ExploreNode) => void;
};

export function ExploreDetailTmdb({
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
}: ExploreDetailTmdbProps) {
  const [selectedSeasons, setSelectedSeasons] = useState<Set<number>>(new Set());
  const [overviewSubTab, setOverviewSubTab] = useState<MediaOverviewTabId>('details');
  const [addPending, setAddPending] = useState(false);

  const isInLibrary = media.in_library && media.library_item_id;
  const seasons = (media.seasons || []).filter((s: any) => (s.season_number ?? s.number ?? 0) > 0);
  const mediaKind = kind === 'tv' || kind === 'movie' ? kind : 'movie';
  const headerData = tmdbMediaToEntityHeaderData(media, mediaKind);
  const tmdbIdStr = String(media.tmdb_id ?? media.id ?? node.id);
  const showCollectionTab =
    kind === 'movie' && media.belongs_to_collection?.id != null && Boolean(tmdbIdStr);

  const mediaOverviewTabs = useMemo(
    () => mediaOverviewTabDefinitions(showCollectionTab),
    [showCollectionTab],
  );

  useEffect(() => {
    setOverviewSubTab('details');
  }, [node.id, kind]);

  useEffect(() => {
    if (!showCollectionTab && overviewSubTab === 'collection') {
      setOverviewSubTab('details');
    }
  }, [showCollectionTab, overviewSubTab]);

  const handleAdd = async () => {
    if (isInLibrary) {
      onOpen();
      return;
    }
    setAddPending(true);
    try {
      const seasonNumbers =
        kind === 'tv' && selectedSeasons.size > 0 && selectedSeasons.size < seasons.length
          ? Array.from(selectedSeasons).sort((a, b) => a - b)
          : null;
      const ok = await onAdd({ ...media, media_type: kind }, seasonNumbers);
      if (ok) {
        onRefresh();
        await onReselect();
      }
    } finally {
      setAddPending(false);
    }
  };

  const similarData = { recommendations, similar };

  return (
    <div className="item-detail-panel item-detail-panel--overview">
      <EntityHeader data={headerData} />
      <DetailViewActionsToolbar aria-label="Discover — add or open in library">
        <button
          type="button"
          className={`btn btn--small btn--with-spinner ${isInLibrary ? 'btn--secondary' : 'btn--primary'}`}
          onClick={handleAdd}
          disabled={addPending}
          aria-busy={addPending}
        >
          {addPending && !isInLibrary ? (
            <>
              <span className="ui-spinner" aria-hidden />
              Adding…
            </>
          ) : isInLibrary ? (
            'Open Library Item'
          ) : (
            'Add to Library'
          )}
        </button>
      </DetailViewActionsToolbar>

      <MediaOverviewTabStrip
        value={overviewSubTab}
        onChange={setOverviewSubTab}
        panelId={DISCOVER_TMDB_OVERVIEW_PANEL_ID}
        ariaLabel="Discover title sections"
        tabs={mediaOverviewTabs}
      />
      <MediaOverviewTabPanel id={DISCOVER_TMDB_OVERVIEW_PANEL_ID}>
        {overviewSubTab === 'details' && (
          <>
            {kind === 'tv' && !isInLibrary && seasons.length > 0 && (
              <div className="season-selector">
                <div className="season-selector__header">
                  <span className="season-selector__label">
                    Seasons: {selectedSeasons.size} of {seasons.length} selected
                  </span>
                  <button
                    type="button"
                    className="btn btn--secondary btn--small"
                    onClick={() =>
                      setSelectedSeasons((prev) =>
                        prev.size === seasons.length
                          ? new Set()
                          : new Set(seasons.map((s: any) => s.season_number ?? s.number ?? 0)),
                      )
                    }
                  >
                    Toggle All
                  </button>
                </div>
                <div className="season-selector__list">
                  {seasons.map((s: any) => {
                    const num = s.season_number ?? s.number ?? 0;
                    return (
                      <label key={num} className="season-selector__item">
                        <input
                          type="checkbox"
                          checked={selectedSeasons.has(num)}
                          onChange={(e) =>
                            setSelectedSeasons((prev) => {
                              const next = new Set(prev);
                              if (e.target.checked) next.add(num);
                              else next.delete(num);
                              return next;
                            })
                          }
                        />
                        <span>
                          {s.name || `Season ${num}`}
                          {s.episode_count ?? s.episodes?.length
                            ? ` (${s.episode_count ?? s.episodes?.length} eps)`
                            : ''}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
            <TmdbDetailsPanel
              tmdbData={media as Record<string, unknown>}
              itemType={kind === 'tv' ? 'show' : 'movie'}
              showCollectionLine={kind !== 'movie'}
            />
          </>
        )}
        {overviewSubTab === 'collection' && showCollectionTab && (
          <CollectionFranchiseStrip
            collectionId={Number(media.belongs_to_collection.id)}
            currentTmdbId={tmdbIdStr}
            belongsHint={media.belongs_to_collection}
          />
        )}
        {overviewSubTab === 'cast' &&
          (creditsHaveContent(media.credits) ? (
            <CastCrew credits={media.credits ?? null} onPersonSelect={onPersonSelect} />
          ) : (
            <p className="muted media-overview-tabpanel__empty">No cast or crew from TMDB.</p>
          ))}
        {overviewSubTab === 'recommendations' &&
          ((recommendations?.length ?? 0) > 0 ? (
            <SimilarRecommendations
              data={similarData}
              onMediaSelect={onMediaSelect}
              variant="recommendations"
            />
          ) : (
            <p className="muted media-overview-tabpanel__empty">No recommendations from TMDB.</p>
          ))}
        {overviewSubTab === 'similar' &&
          ((similar?.length ?? 0) > 0 ? (
            <SimilarRecommendations
              data={similarData}
              onMediaSelect={onMediaSelect}
              variant="similar"
            />
          ) : (
            <p className="muted media-overview-tabpanel__empty">No similar titles from TMDB.</p>
          ))}
      </MediaOverviewTabPanel>
    </div>
  );
}

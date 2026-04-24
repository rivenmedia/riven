import type { ReactNode } from 'react';

/**
 * Shared tab strip + panel shell for title (movie/show) detail.
 * Used by library item overview and discover TMDB title view.
 */

export type MediaOverviewTabId =
  | 'details'
  | 'collection'
  | 'cast'
  | 'recommendations'
  | 'similar';

const BASE_DEFS: ReadonlyArray<[MediaOverviewTabId, string]> = [
  ['details', 'Details'],
  ['cast', 'Cast & crew'],
  ['recommendations', 'Recommendations'],
  ['similar', 'Similar'],
];

/** Include Collection tab only when the title belongs to a TMDB collection (movies). */
export function mediaOverviewTabDefinitions(
  includeCollection: boolean,
): ReadonlyArray<[MediaOverviewTabId, string]> {
  if (!includeCollection) return BASE_DEFS;
  return [
    ['details', 'Details'],
    ['collection', 'Collection'],
    ['cast', 'Cast & crew'],
    ['recommendations', 'Recommendations'],
    ['similar', 'Similar'],
  ];
}

/** @deprecated use mediaOverviewTabDefinitions(false) */
export const MEDIA_OVERVIEW_TAB_DEFS = BASE_DEFS;

export function MediaOverviewTabStrip({
  value,
  onChange,
  panelId,
  ariaLabel = 'Title sections',
  tabs = BASE_DEFS,
}: {
  value: MediaOverviewTabId;
  onChange: (id: MediaOverviewTabId) => void;
  panelId: string;
  /** `role="tablist"` label */
  ariaLabel?: string;
  tabs?: ReadonlyArray<[MediaOverviewTabId, string]>;
}) {
  return (
    <div
      className="media-overview-subtabs"
      role="tablist"
      aria-label={ariaLabel}
    >
      {tabs.map(([id, label]) => (
        <button
          key={id}
          type="button"
          role="tab"
          className={`media-overview-subtab ${value === id ? 'media-overview-subtab--active' : ''}`}
          data-subtab={id}
          aria-selected={value === id}
          aria-controls={panelId}
          onClick={() => onChange(id)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function MediaOverviewTabPanel({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  return (
    <div
      className="media-overview-tabpanel"
      role="tabpanel"
      id={id}
      aria-label="Title information"
    >
      {children}
    </div>
  );
}

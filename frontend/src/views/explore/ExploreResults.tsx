import { MediaGrid } from '../../ui/MediaGrid';

export type ExploreResultsProps = {
  resultsTitle: string;
  totalPages: number;
  page: number;
  loading: boolean;
  error: string | null;
  items: any[];
  onPagePrev: () => void;
  onPageNext: () => void;
  onCardSelect: (item: any) => void;
  getGridActions: (item: any) => Array<{ label: string; onClick?: (item: any) => void; tone?: string }>;
};

export function ExploreResults({
  resultsTitle,
  totalPages,
  page,
  loading,
  error,
  items,
  onPagePrev,
  onPageNext,
  onCardSelect,
  getGridActions,
}: ExploreResultsProps) {
  return (
    <section className="explore-results">
      <div className="section-head">
        <h2>{resultsTitle}</h2>
        {totalPages > 1 && (
          <div className="pagination-bar pagination-bar--inline">
            <button type="button" className="btn btn--secondary btn--small" disabled={page <= 1} onClick={onPagePrev}>
              Previous
            </button>
            <span>
              Page {page} / {totalPages}
            </span>
            <button type="button" className="btn btn--secondary btn--small" disabled={page >= totalPages} onClick={onPageNext}>
              Next
            </button>
          </div>
        )}
      </div>
      {loading ? (
        <p className="muted">Loading…</p>
      ) : error ? (
        <p className="empty-state">{error}</p>
      ) : items.length === 0 ? (
        <p className="empty-state">No results.</p>
      ) : (
        <MediaGrid
          items={items}
          href={null}
          onSelect={onCardSelect}
          actions={getGridActions}
          className="media-grid--dense"
        />
      )}
    </section>
  );
}

import {
  formatEpisodeDisplayTitle,
  formatYear,
  getMediaKind,
  mediaLabel,
} from '../services/utils';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w92';

export interface MediaListAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

export interface MediaListProps {
  items: any[];
  href?: (item: any) => string | null;
  actions?: (item: any) => MediaListAction[];
  showPoster?: boolean;
  className?: string;
}

function posterUrl(item: any): string {
  const path = item?.poster_path || item?.profile_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

export function MediaList({
  items,
  href = (item) => `#/item/${item.id}`,
  actions,
  showPoster = true,
  className = '',
}: MediaListProps) {
  return (
    <div className={`media-list ${className}`.trim()}>
      {items.map((item) => {
        const kind = getMediaKind(item);
        const itemHref = href(item);
        return (
          <div key={item.id ?? item.tmdb_id ?? Math.random()} className="media-list__row">
            {showPoster && (
              <div className="media-list__poster">
                <img
                  src={posterUrl(item) || undefined}
                  alt=""
                  loading="lazy"
                />
              </div>
            )}
            <div className="media-list__main">
              {itemHref ? (
                <a className="media-list__title" href={itemHref}>
                  {formatEpisodeDisplayTitle(item)}
                </a>
              ) : (
                <span className="media-list__title">
                  {formatEpisodeDisplayTitle(item)}
                </span>
              )}
              <div className="media-list__meta">
                <span
                  className={`legend-chip ${kind === 'movie' ? 'legend-chip--movie' : 'legend-chip--tv'}`.trim()}
                >
                  {mediaLabel(item)}
                </span>
                {item?.state && <span className="legend-chip">{item.state}</span>}
                {formatYear(item) && (
                  <span className="legend-chip">{formatYear(item)}</span>
                )}
              </div>
            </div>
            {actions?.(item)?.length ? (
              <div className="media-list__actions">
                {actions(item).map(({ label, onClick, tone = 'secondary' }) => (
                  <button
                    key={label}
                    type="button"
                    className={`btn btn--small btn--${tone}`}
                    onClick={(e) => {
                      e.preventDefault();
                      onClick?.(item);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

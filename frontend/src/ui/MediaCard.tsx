import { useState } from 'react';
import {
  formatYear,
  formatEpisodeDisplayTitle,
  getMediaKind,
  mediaLabel,
} from '../services/utils';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w500';

export interface MediaAction {
  label: string;
  onClick?: (item: any) => void;
  tone?: string;
}

export interface MediaCardProps {
  item: any;
  href?: string | null;
  onSelect?: (item: any, event: React.MouseEvent) => void;
  actions?: MediaAction[];
  compact?: boolean;
}

function posterUrl(item: any): string {
  const path = item?.poster_path || item?.profile_path;
  if (!path) return '';
  return path.startsWith('http') ? path : `${TMDB_IMG}${path}`;
}

function Tag({ label, className = '' }: { label: string; className?: string }) {
  return (
    <span className={`media-tag ${className}`.trim()}>
      {label}
    </span>
  );
}

export function MediaCard({
  item,
  href = null,
  onSelect,
  actions = [],
  compact = false,
}: MediaCardProps) {
  const kind = getMediaKind(item);
  const title = formatEpisodeDisplayTitle(item);
  const posterSrc = posterUrl(item);
  const [imgFailed, setImgFailed] = useState(false);
  const showImg = posterSrc && !imgFailed;

  const handleTriggerClick = (e: React.MouseEvent) => {
    if (onSelect) {
      if (href) e.preventDefault();
      onSelect(item, e);
    }
  };

  const dataAttrs: Record<string, string> = { 'data-media-card': '1' };
  if (item?.tmdb_id != null) dataAttrs['data-tmdb-id'] = String(item.tmdb_id);
  if (item?.tvdb_id != null) dataAttrs['data-tvdb-id'] = String(item.tvdb_id);
  if (item?.library_item_id != null)
    dataAttrs['data-library-item-id'] = String(item.library_item_id);
  if (item?.id != null) dataAttrs['data-item-id'] = String(item.id);
  if (item?.indexer) dataAttrs['data-indexer'] = String(item.indexer);
  if (kind === 'movie' || kind === 'tv') dataAttrs['data-media-type'] = kind;

  const triggerContent = (
    <>
      <div className="media-card__poster">
        {showImg && (
          <img
            src={posterSrc}
            alt={title}
            loading="lazy"
            onLoad={() => setImgFailed(false)}
            onError={() => setImgFailed(true)}
          />
        )}
        <div className="media-card__placeholder" hidden={!!showImg}>
          {(title || '?').slice(0, 1).toUpperCase()}
        </div>
      </div>
      <div className="media-card__body">
        <h3 className="media-card__title">{title}</h3>
        <div className="media-card__tags">
          <Tag label={mediaLabel(item)} className={`media-tag--${kind}`} />
          {formatYear(item) ? (
            <Tag label={formatYear(item)} className="media-tag--neutral" />
          ) : null}
          {item?.state ? (
            <Tag label={item.state} className="media-tag--state" />
          ) : null}
          {item?.in_library ? (
            <Tag label="In Library" className="media-tag--library" />
          ) : null}
        </div>
        {(item?.overview || item?.biography) && (
          <p className="media-card__summary">
            {item.overview || item.biography}
          </p>
        )}
      </div>
    </>
  );

  return (
    <article
      className={`media-card media-card--${kind} ${compact ? 'media-card--compact' : ''}`.trim()}
      {...dataAttrs}
    >
      {href ? (
        <a
          className="media-card__trigger"
          href={href}
          onClick={handleTriggerClick}
        >
          {triggerContent}
        </a>
      ) : (
        <button
          type="button"
          className="media-card__trigger"
          onClick={handleTriggerClick}
        >
          {triggerContent}
        </button>
      )}
      {actions.length > 0 && (
        <div className="media-card__actions">
          {actions.map(({ label, onClick, tone = 'neutral' }) => (
            <button
              key={label}
              type="button"
              className={`btn btn--small btn--${tone}`}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onClick?.(item);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

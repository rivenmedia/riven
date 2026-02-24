import { getMediaKind } from '../../services/utils';
import { MediaGrid } from '../../ui/MediaGrid';
import type { ExploreNode } from './types';

export type ExploreDetailPersonProps = {
  person: any;
  credits: any[];
  onSelectNode: (node: ExploreNode, updateHistory?: boolean) => void;
  onBack: () => void;
};

export function ExploreDetailPerson({ person, credits, onSelectNode, onBack }: ExploreDetailPersonProps) {
  const poster = person.poster_path || person.profile_path || '';
  const posterUrl = poster ? (poster.startsWith('http') ? poster : `https://image.tmdb.org/t/p/w500${poster}`) : '';
  return (
    <section className="panel">
      <div className="detail-head">
        {posterUrl && <img src={posterUrl} alt={person.name || 'person'} />}
        <div>
          <h3>{person.name || 'Unknown'}</h3>
          <p className="muted">
            {[person.known_for_department, person.vote_average ? `Rating ${Number(person.vote_average).toFixed(1)}` : null]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>
          <p className="muted">{person.biography || person.overview || 'No summary available.'}</p>
          <div className="toolbar">
            <button type="button" className="btn btn--primary btn--small" onClick={onBack}>
              Back to Results
            </button>
          </div>
        </div>
      </div>
      <h3>Known Works</h3>
      <MediaGrid
        className="detail-link-grid"
        items={credits.slice(0, 24)}
        href={null}
        onSelect={(item: any) =>
          onSelectNode(
            { kind: getMediaKind(item), id: String(item.id), label: item.title || item.name, source: item.indexer || 'tmdb' },
            true,
          )
        }
      />
    </section>
  );
}

/**
 * Cast & Crew panel: directors and cast as pills. Explore mode (onPersonSelect) or library mode (links).
 */

import { buildExploreNodeUrl } from '../../services/router';

export type CreditsInput = {
  cast?: { id?: number; name?: string; character?: string }[];
  crew?: { id?: number; name?: string; job?: string }[];
  guest_stars?: { id?: number; name?: string; character?: string }[];
};

export interface CastCrewProps {
  credits: CreditsInput | null | undefined;
  maxCast?: number;
  maxDirectors?: number;
  onPersonSelect?: (person: { id: string; name: string }) => void;
  exploreLinkBase?: string;
  trail?: Array<{
    source?: string;
    kind: string;
    id: string;
    label?: string;
  }>;
}

export function CastCrew({
  credits,
  maxCast = 18,
  maxDirectors = 20,
  onPersonSelect,
  exploreLinkBase,
  trail,
}: CastCrewProps) {
  if (!credits) return null;

  const cast = credits.cast ?? [];
  const crew = credits.crew ?? [];
  const guestStars = credits.guest_stars ?? [];
  const directors = crew
    .filter((c) => c.job === 'Director')
    .map((c) => ({ id: c.id, name: c.name || '' }))
    .filter((d) => d.name && d.id != null);
  const castList = cast.length ? cast : guestStars;
  const topCast = castList
    .filter((c) => c.id != null && c.name)
    .slice(0, maxCast) as Array<{
    id: number;
    name: string;
    character?: string;
  }>;
  const directorsForPills = directors.slice(0, maxDirectors);

  if (directorsForPills.length === 0 && topCast.length === 0) return null;

  function PillList({
    label,
    people,
  }: {
    label: string;
    people: Array<{
      id: number;
      name: string;
      character?: string;
    }>;
  }) {
    if (!people.length) return null;
    return (
      <dl className="cast-crew-dl">
        <dt>{label}</dt>
        <dd className="pill-list-wrap">
          <div className="pill-list">
            {people.map((person) => {
              const text = person.character
                ? `${person.name} (${person.character})`
                : person.name;
              if (onPersonSelect) {
                return (
                  <button
                    key={person.id}
                    type="button"
                    className="pill"
                    onClick={() =>
                      onPersonSelect({ id: String(person.id), name: person.name })
                    }
                  >
                    {text}
                  </button>
                );
              }
              if (exploreLinkBase) {
                return (
                  <a
                    key={person.id}
                    className="pill pill--link"
                    href={buildExploreNodeUrl(
                      { kind: 'person', id: String(person.id), label: person.name },
                      trail,
                    )}
                  >
                    {text}
                  </a>
                );
              }
              return (
                <span key={person.id} className="pill pill--text">
                  {text}
                </span>
              );
            })}
          </div>
        </dd>
      </dl>
    );
  }

  return (
    <div className="panel cast-crew-panel">
      <div className="section-head">
        <h3>Cast &amp; Crew</h3>
      </div>
      {directorsForPills.length > 0 && (
        <PillList label="Directors" people={directorsForPills} />
      )}
      {topCast.length > 0 && <PillList label="Cast" people={topCast} />}
    </div>
  );
}

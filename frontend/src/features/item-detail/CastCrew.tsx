/**
 * Cast & crew: grid with headshots, crew grouped by department, progressive disclosure.
 */

import { useMemo, useState } from 'react';
import { buildExploreNodeUrl } from '../../shared/routing/router';

const TMDB_IMG = 'https://image.tmdb.org/t/p/w185';
const VISIBLE_CAST = 12;
const VISIBLE_PER_DEPT = 6;

export type CastEntry = {
  id?: number;
  name?: string;
  character?: string;
  profile_path?: string | null;
  order?: number;
};

export type CrewEntry = {
  id?: number;
  name?: string;
  job?: string;
  department?: string;
  profile_path?: string | null;
};

export type CreditsInput = {
  cast?: CastEntry[];
  crew?: CrewEntry[];
  guest_stars?: CastEntry[];
};

const DEPT_ORDER = [
  'Directing',
  'Writing',
  'Production',
  'Camera',
  'Art',
  'Sound',
  'Visual Effects',
  'Editing',
  'Costume & Make-Up',
  'Lighting',
  'Crew',
];

function personInitials(name: string) {
  const p = name.trim().split(/\s+/).filter(Boolean);
  if (!p.length) return '?';
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return (p[0][0] + p[p.length - 1][0]).toUpperCase();
}

function PersonAvatar({
  name,
  profilePath,
  className,
}: {
  name: string;
  profilePath?: string | null;
  className?: string;
}) {
  const [broken, setBroken] = useState(!profilePath);
  const src = profilePath ? `${TMDB_IMG}${profilePath}` : null;
  if (broken || !src) {
    return (
      <div className={`cast-crew-avatar cast-crew-avatar--ph ${className || ''}`} aria-hidden>
        {personInitials(name)}
      </div>
    );
  }
  return (
    <img
      className={`cast-crew-avatar ${className || ''}`}
      src={src}
      alt=""
      loading="lazy"
      onError={() => setBroken(true)}
    />
  );
}

function sortDepartments(a: string, b: string) {
  const ia = DEPT_ORDER.indexOf(a);
  const ib = DEPT_ORDER.indexOf(b);
  if (ia === -1 && ib === -1) return a.localeCompare(b);
  if (ia === -1) return 1;
  if (ib === -1) return -1;
  return ia - ib;
}

type GroupedCrew = Array<{
  department: string;
  people: Array<{
    id: number;
    name: string;
    profile_path?: string | null;
    jobs: string[];
  }>;
}>;

function groupCrew(crew: CrewEntry[]): GroupedCrew {
  const byDept = new Map<string, Map<number, { name: string; profile_path?: string | null; jobs: Set<string> }>>();

  for (const c of crew) {
    if (c == null || c.id == null || !c.name) continue;
    const dept = (c.department || 'Crew').trim() || 'Crew';
    if (!byDept.has(dept)) byDept.set(dept, new Map());
    const m = byDept.get(dept)!;
    if (!m.has(c.id)) {
      m.set(c.id, { name: c.name, profile_path: c.profile_path, jobs: new Set() });
    }
    const row = m.get(c.id)!;
    if (c.profile_path) row.profile_path = c.profile_path;
    if (c.job) row.jobs.add(c.job);
  }

  return [...byDept.entries()]
    .map(([department, peopleMap]) => ({
      department,
      people: [...peopleMap.entries()].map(([id, p]) => ({
        id,
        name: p.name,
        profile_path: p.profile_path,
        jobs: [...p.jobs].sort(),
      })),
    }))
    .filter((d) => d.people.length)
    .sort((a, b) => sortDepartments(a.department, b.department));
}

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
  maxCast: maxCastLimit = 500,
  maxDirectors: _maxDirectors = 20,
  onPersonSelect,
  exploreLinkBase,
  trail,
}: CastCrewProps) {
  void _maxDirectors;
  const [castExpanded, setCastExpanded] = useState(false);
  const [crewExpanded, setCrewExpanded] = useState(false);

  const castRaw = useMemo(() => {
    if (!credits) return [] as CastEntry[];
    return credits.cast?.length ? credits.cast : credits.guest_stars ?? [];
  }, [credits]);

  const crew = credits?.crew ?? [];

  const castList = useMemo(
    () =>
      castRaw
        .filter((c): c is CastEntry & { id: number; name: string } => c.id != null && Boolean(c.name))
        .sort((a, b) => (a.order ?? 99) - (b.order ?? 99)),
    [castRaw],
  );

  const groupedCrew = useMemo(() => groupCrew(crew), [crew]);

  const visibleCap = Math.min(
    maxCastLimit,
    castExpanded ? castList.length : Math.min(VISIBLE_CAST, maxCastLimit),
  );
  const topCast = castList.slice(0, visibleCap);
  const hasCrewOverflow = groupedCrew.some((d) => d.people.length > VISIBLE_PER_DEPT);

  if (!credits) return null;
  if (topCast.length === 0 && groupedCrew.length === 0) return null;

  function PersonNameLink({
    id,
    name,
  }: {
    id: number;
    name: string;
  }) {
    if (onPersonSelect) {
      return (
        <button
          type="button"
          className="cast-crew-name-btn"
          onClick={() => onPersonSelect({ id: String(id), name })}
        >
          {name}
        </button>
      );
    }
    if (exploreLinkBase) {
      return (
        <a
          className="cast-crew-name-link"
          href={buildExploreNodeUrl(
            { kind: 'person', id: String(id), label: name },
            trail,
          )}
        >
          {name}
        </a>
      );
    }
    return <span className="cast-crew-name-text">{name}</span>;
  }

  return (
    <div className="panel cast-crew-panel">
      <div className="section-head">
        <h3>Cast &amp; Crew</h3>
      </div>
      {topCast.length > 0 && (
        <div className="cast-crew-block">
          <h4 className="cast-crew-block__title">Cast</h4>
          <div className="cast-crew-grid">
            {topCast.map((person) => (
              <div key={person.id} className="cast-crew-card">
                <PersonAvatar name={person.name!} profilePath={person.profile_path} />
                <div className="cast-crew-card__body">
                  <div className="cast-crew-card__name">
                    <PersonNameLink id={person.id} name={person.name!} />
                  </div>
                  {person.character && (
                    <div className="cast-crew-card__sub">{person.character}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
          {castList.length > VISIBLE_CAST && !castExpanded && (
            <button
              type="button"
              className="btn btn--small btn--secondary cast-crew-more"
              onClick={() => setCastExpanded(true)}
            >
              Show all cast ({castList.length})
            </button>
          )}
          {castList.length > VISIBLE_CAST && castExpanded && (
            <button
              type="button"
              className="btn btn--small btn--secondary cast-crew-more"
              onClick={() => setCastExpanded(false)}
            >
              Show less
            </button>
          )}
        </div>
      )}
      {groupedCrew.map(({ department, people }) => {
        const vis = crewExpanded ? people : people.slice(0, VISIBLE_PER_DEPT);
        return (
          <div key={department} className="cast-crew-block cast-crew-block--dept">
            <h4 className="cast-crew-block__title">{department}</h4>
            <div className="cast-crew-grid cast-crew-grid--crew">
              {vis.map((p) => (
                <div key={p.id} className="cast-crew-card cast-crew-card--crew">
                  <PersonAvatar name={p.name} profilePath={p.profile_path} />
                  <div className="cast-crew-card__body">
                    <div className="cast-crew-card__name">
                      <PersonNameLink id={p.id} name={p.name} />
                    </div>
                    {p.jobs.length > 0 && (
                      <div className="cast-crew-card__sub">{p.jobs.join(' · ')}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {hasCrewOverflow && !crewExpanded && (
        <button
          type="button"
          className="btn btn--small btn--secondary cast-crew-more"
          onClick={() => setCrewExpanded(true)}
        >
          Show all crew
        </button>
      )}
      {crewExpanded && hasCrewOverflow && (
        <button
          type="button"
          className="btn btn--small btn--secondary cast-crew-more"
          onClick={() => setCrewExpanded(false)}
        >
          Show less crew
        </button>
      )}
    </div>
  );
}

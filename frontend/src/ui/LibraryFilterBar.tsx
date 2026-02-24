import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Library filter bar: search, state, sort, limit. Controlled component with optional auto-apply.
 */

export interface LibraryFilterState {
  search: string;
  state: string;
  sort: string;
  limit: number;
}

export interface LibraryFilterBarProps {
  value: LibraryFilterState;
  onChange: (filters: LibraryFilterState) => void;
  searchDebounceMs?: number;
  autoApply?: boolean;
  showApplyButton?: boolean;
  stateOptions?: React.ReactNode;
}

const SORT_OPTIONS = [
  { value: 'date_desc', label: 'Newest requested' },
  { value: 'date_asc', label: 'Oldest requested' },
  { value: 'title_asc', label: 'Title A-Z' },
  { value: 'title_desc', label: 'Title Z-A' },
];

const LIMIT_OPTIONS = [
  { value: 24, label: '24 / page' },
  { value: 48, label: '48 / page' },
  { value: 96, label: '96 / page' },
];

export function LibraryFilterBar({
  value,
  onChange,
  searchDebounceMs = 350,
  autoApply = true,
  showApplyButton = false,
  stateOptions,
}: LibraryFilterBarProps) {
  const [localSearch, setLocalSearch] = useState(value.search);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalSearch(value.search);
  }, [value.search]);

  const apply = useCallback(() => {
    onChange({
      ...value,
      search: localSearch.trim(),
    });
  }, [value, localSearch, onChange]);

  const scheduleApply = useCallback(() => {
    if (searchDebounceMs <= 0) {
      apply();
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null;
      apply();
    }, searchDebounceMs);
  }, [searchDebounceMs, apply]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    apply();
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalSearch(e.target.value);
    if (autoApply) scheduleApply();
  };

  const handleStateChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = { ...value, state: e.target.value };
    onChange(next);
  };

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = { ...value, sort: e.target.value };
    onChange(next);
  };

  const handleLimitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = { ...value, limit: Number(e.target.value) || 24 };
    onChange(next);
  };

  return (
    <form
      className="toolbar toolbar--library"
      onSubmit={handleSubmit}
    >
      <input
        data-slot="search"
        type="search"
        placeholder="Search title or imdb/tmdb/tvdb id"
        value={localSearch}
        onChange={handleSearchChange}
      />
      <select data-slot="state" value={value.state} onChange={handleStateChange}>
        {stateOptions}
      </select>
      <select data-slot="sort" value={value.sort} onChange={handleSortChange}>
        {SORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select data-slot="limit" value={value.limit} onChange={handleLimitChange}>
        {LIMIT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {showApplyButton && (
        <button className="btn btn--primary" type="submit">
          Apply
        </button>
      )}
    </form>
  );
}

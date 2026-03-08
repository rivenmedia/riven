/**
 * Media type toggle: Movies | TV [, All]. Controlled component.
 */

export type MediaTypeValue = 'movie' | 'tv' | 'all';

export interface MediaTypeToggleProps {
  value?: MediaTypeValue;
  includeAll?: boolean;
  onChange?: (value: MediaTypeValue) => void;
}

const OPTIONS: { value: MediaTypeValue; label: string }[] = [
  { value: 'movie', label: 'Movies' },
  { value: 'tv', label: 'TV' },
  { value: 'all', label: 'All' },
];

export function MediaTypeToggle({
  value = 'movie',
  includeAll = false,
  onChange,
}: MediaTypeToggleProps) {
  const options = includeAll ? OPTIONS : OPTIONS.slice(0, 2);
  return (
    <div
      className="media-type-toggle"
      role="group"
      aria-label="Media type"
    >
      {options.map(({ value: v, label }) => (
        <button
          key={v}
          type="button"
          className={`media-type-toggle__btn ${value === v ? 'is-active' : ''}`}
          data-value={v}
          onClick={() => onChange?.(v)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

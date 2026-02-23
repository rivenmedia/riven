/**
 * Attach behavior to a library filter form: sync DOM with state, optional auto-apply on change.
 * Does not create DOM; expects form with data-slot="search", "state", "sort", "limit".
 */

export interface LibraryFilterState {
  search: string;
  state: string;
  sort: string;
  limit: number;
}

export interface AttachLibraryFilterBarOptions {
  /** Initial filter state (will sync to DOM) */
  initial: LibraryFilterState;
  /** Called when filters change (after apply or on change if autoApply). Reset page to 1 when calling. */
  onChange: (filters: LibraryFilterState) => void;
  /** Debounce search input by this many ms (0 = no debounce). Default 350. */
  searchDebounceMs?: number;
  /** If true, onChange is called on every control change (no need to click Apply). Default true. */
  autoApply?: boolean;
  /** If true, show and keep the Apply button (still useful with autoApply for explicit refresh). Default false when autoApply. */
  showApplyButton?: boolean;
}

function getFormElements(form: HTMLFormElement | null) {
  if (!form) return null;
  return {
    search: form.querySelector<HTMLInputElement>('[data-slot="search"]'),
    state: form.querySelector<HTMLSelectElement>('[data-slot="state"]'),
    sort: form.querySelector<HTMLSelectElement>('[data-slot="sort"]'),
    limit: form.querySelector<HTMLSelectElement>('[data-slot="limit"]'),
    applyBtn: form.querySelector<HTMLButtonElement>('button[type="submit"]'),
  };
}

function readFilters(el: ReturnType<typeof getFormElements>): LibraryFilterState | null {
  if (!el?.sort?.value) return null;
  return {
    search: el.search?.value?.trim() ?? '',
    state: el.state?.value ?? '',
    sort: el.sort?.value ?? 'date_desc',
    limit: Number(el.limit?.value || 24) || 24,
  };
}

function writeFilters(el: ReturnType<typeof getFormElements> | null, f: LibraryFilterState): void {
  if (!el) return;
  if (el.search) el.search.value = f.search;
  if (el.state) el.state.value = f.state;
  if (el.sort) el.sort.value = f.sort;
  if (el.limit) el.limit.value = String(f.limit);
}

/**
 * Attach filter bar behavior to the given form element.
 * Returns a function to update filter state from outside (e.g. from route query).
 */
export function attachLibraryFilterBar(
  form: HTMLFormElement | null,
  options: AttachLibraryFilterBarOptions,
): (filters: LibraryFilterState) => void {
  const {
    initial,
    onChange,
    searchDebounceMs = 350,
    autoApply = true,
    showApplyButton = false,
  } = options;

  const el = getFormElements(form);
  if (!el) return () => {};

  writeFilters(el, initial);

  if (el.applyBtn) el.applyBtn.style.display = showApplyButton ? '' : 'none';

  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

  function apply(): void {
    const next = readFilters(el);
    if (next) onChange(next);
  }

  function scheduleSearchApply(): void {
    if (searchDebounceMs <= 0) {
      apply();
      return;
    }
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      searchDebounceTimer = null;
      apply();
    }, searchDebounceMs);
  }

  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    apply();
  });

  if (autoApply) {
    el.search?.addEventListener('input', scheduleSearchApply);
    el.search?.addEventListener('change', scheduleSearchApply);
    el.state?.addEventListener('change', apply);
    el.sort?.addEventListener('change', apply);
    el.limit?.addEventListener('change', apply);
  }

  return (filters: LibraryFilterState) => {
    writeFilters(el, filters);
  };
}

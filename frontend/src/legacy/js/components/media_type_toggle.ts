/**
 * Media type toggle component: Movies | TV [, All].
 * Renders a segmented control and calls onChange when the selection changes.
 *
 * @param {Object} options
 * @param {HTMLElement} options.container - Parent to append the toggle to
 * @param {'movie'|'tv'|'all'} [options.value='movie'] - Initial value
 * @param {boolean} [options.includeAll=false] - If true, show a third "All" segment (explore only)
 * @param {(value: 'movie'|'tv'|'all') => void} [options.onChange] - Called when user selects a different type
 * @returns {{ setValue: (v: 'movie'|'tv'|'all') => void, getValue: () => 'movie'|'tv'|'all', element: HTMLElement }}
 */
export function createMediaTypeToggle({ container, value = 'movie', includeAll = false, onChange }) {
  const wrap = document.createElement('div');
  wrap.className = 'media-type-toggle';
  wrap.setAttribute('role', 'group');
  wrap.setAttribute('aria-label', 'Media type');

  const buttons = [
    { value: 'movie', label: 'Movies' },
    { value: 'tv', label: 'TV' },
    ...(includeAll ? [{ value: 'all', label: 'All' }] : []),
  ].map(({ value: v, label }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'media-type-toggle__btn';
    btn.textContent = label;
    btn.dataset.value = v;
    return btn;
  });

  buttons.forEach((btn) => wrap.appendChild(btn));

  function setActive(val) {
    const v = ['movie', 'tv', 'all'].includes(val) ? val : 'movie';
    buttons.forEach((btn) => btn.classList.toggle('is-active', btn.dataset.value === v));
  }

  function getValue() {
    const active = buttons.find((b) => b.classList.contains('is-active'));
    return (active?.dataset.value === 'tv' ? 'tv' : active?.dataset.value === 'all' ? 'all' : 'movie');
  }

  function handleClick(e) {
    const btn = e.target.closest('.media-type-toggle__btn');
    if (!btn) return;
    const v = (btn.dataset.value === 'tv' ? 'tv' : btn.dataset.value === 'all' ? 'all' : 'movie');
    if (getValue() === v) return;
    setActive(v);
    onChange?.(v);
  }

  wrap.addEventListener('click', handleClick);
  setActive(value);

  if (container) container.appendChild(wrap);

  return {
    element: wrap,
    setValue(v) {
      setActive(v);
    },
    getValue,
  };
}

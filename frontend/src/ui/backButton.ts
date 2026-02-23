/**
 * Render a "Back" button for item detail (or any view) that either goes history.back() or to a stored list route.
 */

export interface BackButtonOptions {
  /** Label, e.g. "← Back to Library" */
  label?: string;
  /** If set, navigate to this hash (e.g. #/library). Otherwise use history.back(). */
  href?: string | null;
  /** Click handler; if provided, href is still set but handler can preventDefault and do custom nav. */
  onClick?: (e: MouseEvent) => void;
}

export function renderBackButton(
  container: HTMLElement | null,
  options: BackButtonOptions = {},
): void {
  if (!container) return;
  const { label = '← Back', href, onClick } = options;

  container.innerHTML = '';
  const btn = document.createElement(href ? 'a' : 'button');
  btn.className = 'btn btn--secondary back-button';
  btn.textContent = label;
  if (href && btn instanceof HTMLAnchorElement) btn.href = href;
  if (btn instanceof HTMLButtonElement) btn.type = 'button';

  btn.addEventListener('click', (e) => {
    if (onClick) {
      onClick(e as MouseEvent);
      return;
    }
    if (href && (e as MouseEvent).ctrlKey === false && (e as MouseEvent).metaKey === false) {
      e.preventDefault();
      window.location.hash = href;
      return;
    }
    if (!href) {
      e.preventDefault();
      window.history.back();
    }
  });

  container.appendChild(btn);
}

/**
 * Back button for item detail or any view: navigates to href or history.back().
 */

export interface BackButtonProps {
  /** e.g. "← Back to Library" */
  label?: string;
  /** If set, navigate to this hash (e.g. #/library). Otherwise use history.back(). */
  href?: string | null;
  onClick?: (e: React.MouseEvent) => void;
}

export function BackButton({
  label = '← Back',
  href,
  onClick,
}: BackButtonProps) {
  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      onClick(e);
      return;
    }
    if (href && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      window.location.hash = href;
      return;
    }
    if (!href) {
      e.preventDefault();
      window.history.back();
    }
  };

  if (href) {
    return (
      <a
        className="btn btn--secondary back-button"
        href={href}
        onClick={handleClick}
      >
        {label}
      </a>
    );
  }
  return (
    <button type="button" className="btn btn--secondary back-button" onClick={handleClick}>
      {label}
    </button>
  );
}

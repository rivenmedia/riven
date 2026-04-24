/**
 * Groups primary actions for a title/detail view (library scrape controls, discover add, etc.).
 */

import type { ReactNode } from 'react';

export function DetailViewActionsToolbar({
  'aria-label': ariaLabel,
  children,
}: {
  'aria-label': string;
  children: ReactNode;
}) {
  return (
    <div className="detail-view-actions-toolbar" role="toolbar" aria-label={ariaLabel}>
      <div className="detail-view-actions-toolbar__inner">{children}</div>
    </div>
  );
}

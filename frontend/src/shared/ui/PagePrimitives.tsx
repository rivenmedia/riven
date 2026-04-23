import type { ReactNode } from "react";
import { useId } from "react";

function joinClasses(...parts: Array<string | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

interface ViewLayoutProps {
  view: string;
  className?: string;
  children: ReactNode;
}

export function ViewLayout({ view, className, children }: ViewLayoutProps) {
  return (
    <section className={joinClasses("view", className)} data-view={view}>
      {children}
    </section>
  );
}

interface ViewHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function ViewHeader({ title, subtitle, actions }: ViewHeaderProps) {
  return (
    <header className="view-header">
      <div>
        {typeof title === "string" ? <h1>{title}</h1> : title}
        {subtitle
          ? typeof subtitle === "string"
            ? <p>{subtitle}</p>
            : subtitle
          : null}
      </div>
      {actions ? <div className="header-actions">{actions}</div> : null}
    </header>
  );
}

interface PanelProps {
  className?: string;
  children: ReactNode;
}

export function Panel({ className, children }: PanelProps) {
  return <section className={joinClasses("panel", className)}>{children}</section>;
}

interface CollapsiblePanelProps {
  className?: string;
  title: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function CollapsiblePanel({
  className,
  title,
  actions,
  defaultOpen = false,
  children,
}: CollapsiblePanelProps) {
  const bodyId = useId();
  return (
    <details className={joinClasses("panel", "collapsible-panel", className)} open={defaultOpen}>
      <summary className="collapsible-panel__summary" aria-controls={bodyId}>
        <div className="collapsible-panel__title">
          {typeof title === "string" ? <h2>{title}</h2> : title}
        </div>
        <div className="collapsible-panel__right">
          {actions ? <div className="collapsible-panel__actions">{actions}</div> : null}
          <span className="collapsible-panel__chevron" aria-hidden="true" />
        </div>
      </summary>
      <div className="collapsible-panel__body" id={bodyId}>
        {children}
      </div>
    </details>
  );
}

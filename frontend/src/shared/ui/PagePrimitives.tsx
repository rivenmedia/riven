import type { ReactNode } from "react";

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

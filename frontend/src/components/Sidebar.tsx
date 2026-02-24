import type { AppRoute, RouteName } from "../app/routeTypes";

interface SidebarProps {
  currentRoute: RouteName;
  isMobileOpen: boolean;
  onNavigate: () => void;
  route: AppRoute | null;
  onLogout: () => void;
}

interface NavLink {
  hash: string;
  label: string;
  route: RouteName;
  /** When route is explore, optional predicate to mark this sub-link active from query. */
  isActive?: (query: Record<string, string>) => boolean;
  /** Indent as sub-item under the section. */
  nested?: boolean;
}

interface NavSection {
  title: string;
  links: NavLink[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    title: "Library",
    links: [
      { hash: "#/library", label: "All Media", route: "library" },
      { hash: "#/movies", label: "Movies", route: "movies", nested: true },
      { hash: "#/shows", label: "TV Shows", route: "shows", nested: true },
      { hash: "#/episodes", label: "TV Episodes", route: "episodes", nested: true },
    ],
  },
  {
    title: "Discovery",
    links: [
      {
        hash: "#/explore",
        label: "Discover",
        route: "explore",
        isActive: (q) => !q.mode,
      },
      {
        hash: "#/explore?mode=discover&type=movie",
        label: "Discover — Movies",
        route: "explore",
        nested: true,
        isActive: (q) => q.mode === "discover" && q.type === "movie",
      },
      {
        hash: "#/explore?mode=discover&type=tv",
        label: "Discover — TV",
        route: "explore",
        nested: true,
        isActive: (q) => q.mode === "discover" && q.type === "tv",
      },
      {
        hash: "#/explore?mode=discover&type=all&window=day",
        label: "Trending — Today",
        route: "explore",
        nested: true,
        isActive: (q) => q.mode === "discover" && q.type === "all" && q.window === "day",
      },
      {
        hash: "#/explore?mode=discover&type=all&window=week",
        label: "Trending — This Week",
        route: "explore",
        nested: true,
        isActive: (q) => q.mode === "discover" && q.type === "all" && (q.window === "week" || !q.window),
      },
    ],
  },
  {
    title: "Dashboard",
    links: [
      { hash: "#/dashboard", label: "Overview", route: "dashboard" },
      { hash: "#/dashboard-services", label: "Services", route: "dashboard-services", nested: true },
      { hash: "#/dashboard-states", label: "State Distribution", route: "dashboard-states", nested: true },
      { hash: "#/dashboard-releases", label: "Releases by Year", route: "dashboard-releases", nested: true },
    ],
  },
  {
    title: "System",
    links: [
      { hash: "#/inspector", label: "Inspector", route: "inspector" },
      { hash: "#/vfs-stats", label: "VFS Stats", route: "vfs-stats" },
      { hash: "#/calendar", label: "Calendar", route: "calendar" },
      { hash: "#/mount", label: "Mount", route: "mount" },
      { hash: "#/settings", label: "Settings", route: "settings" },
    ],
  },
];

function isLinkActive(link: NavLink, currentRoute: RouteName, route: AppRoute | null): boolean {
  if (currentRoute !== link.route) return false;
  if (link.isActive && route?.query) return link.isActive(route.query);
  return true;
}

export default function Sidebar({
  currentRoute,
  isMobileOpen,
  onNavigate,
  route,
  onLogout,
}: SidebarProps) {
  return (
    <nav
      className={["app-sidebar", isMobileOpen ? "app-sidebar--mobile-open" : ""]
        .filter(Boolean)
        .join(" ")}
      id="app-sidebar-nav"
    >
      <div className="sidebar-brand">
        <a className="sidebar-logo" href="#/library" onClick={onNavigate}>
          Riven
        </a>
        <p className="sidebar-subtitle">Media Control Center</p>
      </div>

      <div className="sidebar-legend">
        <span className="legend-chip legend-chip--movie">Movie</span>
        <span className="legend-chip legend-chip--tv">TV</span>
      </div>

      <div className="sidebar-sections">
        {NAV_SECTIONS.map((section) => (
          <section className="sidebar-section" key={section.title}>
            <span className="sidebar-section-title">{section.title}</span>
            <ul>
              {section.links.map((link) => (
                <li key={link.hash}>
                  <a
                    className={[
                      link.nested ? "sidebar-link--nested" : "",
                      isLinkActive(link, currentRoute, route) ? "active" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    href={link.hash}
                    onClick={onNavigate}
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="sidebar-footer">
        <button
          className="btn btn--danger btn--block"
          onClick={() => {
            onNavigate();
            onLogout();
          }}
          type="button"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

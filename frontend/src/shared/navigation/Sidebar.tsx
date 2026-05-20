import type { AppRoute, RouteName } from "../../app/routeTypes";
import { readLibraryReturnRoute } from "./libraryReturnRoute";

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
    title: "Dashboard",
    links: [
      { hash: "#/dashboard", label: "Overview", route: "dashboard" },
      { hash: "#/dashboard-services", label: "Services", route: "dashboard-services" },
      { hash: "#/dashboard-states", label: "State Distribution", route: "dashboard-states" },
      { hash: "#/dashboard-releases", label: "Releases by Year", route: "dashboard-releases" },
      { hash: "#/dashboard-activity", label: "Activity", route: "dashboard-activity" },
      { hash: "#/dashboard-rate-limits", label: "Rate limits", route: "dashboard-rate-limits" },
      { hash: "#/calendar", label: "Calendar", route: "calendar" },
    ],
  },
  {
    title: "Library",
    links: [
      { hash: "#/library", label: "All Media", route: "library" },
      { hash: "#/movies", label: "Movies", route: "movies" },
      { hash: "#/shows", label: "TV Shows", route: "shows" },
      { hash: "#/episodes", label: "TV Episodes", route: "episodes" },
    ],
  },
  {
    title: "Discovery",
    links: [
      {
        hash: "#/search",
        label: "Search",
        route: "search",
      },
      {
        hash: "#/explore?mode=discover&type=movie",
        label: "Discover — Movies",
        route: "explore",
        isActive: (q) => q.mode === "discover" && q.type === "movie",
      },
      {
        hash: "#/explore?mode=discover&type=tv",
        label: "Discover — TV",
        route: "explore",
        isActive: (q) => q.mode === "discover" && q.type === "tv",
      },
      {
        hash: "#/explore?mode=discover&type=all&window=day",
        label: "Trending — Today",
        route: "explore",
        isActive: (q) => q.mode === "discover" && q.type === "all" && q.window === "day",
      },
      {
        hash: "#/explore?mode=discover&type=all&window=week",
        label: "Trending — This Week",
        route: "explore",
        isActive: (q) => q.mode === "discover" && q.type === "all" && (q.window === "week" || !q.window),
      },
    ],
  },
  {
    title: "VFS",
    links: [
      { hash: "#/vfs-stats", label: "Stats", route: "vfs-stats" },
      { hash: "#/mount", label: "Mount", route: "mount" },
    ],
  },
  {
    title: "System",
    links: [
      { hash: "#/inspector", label: "Inspector & Logs", route: "inspector" },
      { hash: "#/settings", label: "Settings", route: "settings" },
      { hash: "#/backup", label: "Backup & Restore", route: "backup" },
    ],
  },
];

function effectiveHighlightRouteForLink(link: NavLink, currentRoute: RouteName): RouteName {
  if (
    currentRoute === "item" &&
    (link.route === "library" ||
      link.route === "movies" ||
      link.route === "shows" ||
      link.route === "episodes")
  ) {
    return readLibraryReturnRoute() ?? "library";
  }
  return currentRoute;
}

function isLinkActive(link: NavLink, currentRoute: RouteName, route: AppRoute | null): boolean {
  // Treat the Explore "search" mode as equivalent to the Search page so the nav highlight
  // remains correct if the user is on #/explore without ?mode=discover.
  if (link.route === "search" && currentRoute === "explore") {
    const mode = route?.query?.mode;
    return mode !== "discover";
  }
  const effectiveRoute = effectiveHighlightRouteForLink(link, currentRoute);
  if (effectiveRoute !== link.route) return false;
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
        <a className="sidebar-logo" href="#/dashboard" onClick={onNavigate}>
          Riven
        </a>
        <p className="sidebar-subtitle">Media Control Center</p>
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

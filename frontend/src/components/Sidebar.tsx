import type { RouteName } from "../app/routeTypes";

interface SidebarProps {
  currentRoute: RouteName;
  onLogout: () => void;
}

interface NavLink {
  hash: string;
  label: string;
  route: RouteName;
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
      { hash: "#/movies", label: "Movies", route: "movies" },
      { hash: "#/shows", label: "TV Shows", route: "shows" },
    ],
  },
  {
    title: "Discovery",
    links: [
      { hash: "#/explore", label: "Discovery Graph", route: "explore" },
      { hash: "#/trending", label: "Trending", route: "trending" },
    ],
  },
  {
    title: "System",
    links: [
      { hash: "#/dashboard", label: "Dashboard", route: "dashboard" },
      { hash: "#/inspector", label: "Inspector", route: "inspector" },
      { hash: "#/vfs-stats", label: "VFS Stats", route: "vfs-stats" },
      { hash: "#/calendar", label: "Calendar", route: "calendar" },
      { hash: "#/mount", label: "Mount", route: "mount" },
      { hash: "#/settings", label: "Settings", route: "settings" },
    ],
  },
];

export default function Sidebar({ currentRoute, onLogout }: SidebarProps) {
  return (
    <nav className="app-sidebar">
      <div className="sidebar-brand">
        <a className="sidebar-logo" href="#/library">
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
                    className={currentRoute === link.route ? "active" : ""}
                    href={link.hash}
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
          onClick={onLogout}
          type="button"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

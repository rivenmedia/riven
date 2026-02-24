import { useEffect, useMemo, useState } from "react";
import { hasKey, logout, setKey, validateKey } from "../services/auth";
import { parseRoute, replaceRoute } from "../services/router";
import LoginView from "../components/LoginView";
import ManualScrapeModalTemplate from "../components/ManualScrapeModalTemplate";
import Sidebar from "../components/Sidebar";
import ViewHost from "../components/ViewHost";
import type { AppRoute, RouteName } from "./routeTypes";

/** Redirect legacy #/trending to graph with Trending — This Week filter. */
function normalizeRoute(parsed: AppRoute): AppRoute {
  if (parsed.name === "trending") {
    replaceRoute("explore", null, { mode: "discover", type: "all", window: "week" });
    return parseRoute() as AppRoute;
  }
  return parsed;
}

const DEFAULT_HASH = "#/library";
const MOBILE_MEDIA_QUERY = "(max-width: 1080px)";
const MOBILE_SIDEBAR_WIDTH_PX = 300;
const MOBILE_SWIPE_EDGE_PX = 24;
const MOBILE_SWIPE_MIN_DISTANCE_PX = 60;
const MOBILE_SWIPE_MAX_VERTICAL_DELTA_PX = 90;

const ROUTE_TITLES: Record<RouteName, string> = {
  library: "All Media",
  movies: "Movies",
  shows: "TV Shows",
  episodes: "TV Episodes",
  explore: "Discover",
  trending: "Trending",
  dashboard: "Overview",
  "dashboard-services": "Services",
  "dashboard-states": "State Distribution",
  "dashboard-releases": "Releases by Year",
  inspector: "Inspector",
  settings: "Settings",
  "vfs-stats": "VFS Stats",
  item: "Item Details",
  calendar: "Calendar",
  mount: "Mount",
};

function getMobileRouteTitle(route: AppRoute): string {
  if (route.name === "explore") {
    const { mode, type, window: timeWindow } = route.query;
    if (mode === "discover" && type === "movie") {
      return "Discover - Movies";
    }
    if (mode === "discover" && type === "tv") {
      return "Discover - TV";
    }
    if (mode === "discover" && type === "all" && timeWindow === "day") {
      return "Trending - Today";
    }
    if (mode === "discover" && type === "all" && (!timeWindow || timeWindow === "week")) {
      return "Trending - This Week";
    }
  }
  return ROUTE_TITLES[route.name] || ROUTE_TITLES.library;
}

function applyRouteTheme(routeName: RouteName) {
  const body = document.body;
  if (!body) {
    return;
  }

  if (routeName === "movies") {
    body.dataset.mediaContext = "movie";
    return;
  }

  if (routeName === "shows") {
    body.dataset.mediaContext = "tv";
    return;
  }

  body.dataset.mediaContext = "mixed";
}

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean>(() => hasKey());
  const [route, setRoute] = useState<AppRoute>(() => normalizeRoute(parseRoute() as AppRoute));
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);

  const routeName = useMemo<RouteName>(() => route?.name || "library", [route]);
  const mobileRouteTitle = useMemo(() => getMobileRouteTitle(route), [route]);

  useEffect(() => {
    function handleHashChange() {
      setRoute(normalizeRoute(parseRoute() as AppRoute));
      setIsMobileSidebarOpen(false);
    }

    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  useEffect(() => {
    if (authenticated && !window.location.hash) {
      window.location.hash = DEFAULT_HASH;
      setRoute(parseRoute() as AppRoute);
    }
  }, [authenticated]);

  useEffect(() => {
    applyRouteTheme(authenticated ? routeName : "library");
  }, [authenticated, routeName]);

  useEffect(() => {
    const mediaQuery = window.matchMedia(MOBILE_MEDIA_QUERY);
    function handleViewportChange(event: MediaQueryListEvent) {
      if (!event.matches) {
        setIsMobileSidebarOpen(false);
      }
    }

    mediaQuery.addEventListener("change", handleViewportChange);
    return () => {
      mediaQuery.removeEventListener("change", handleViewportChange);
    };
  }, []);

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    let touchStartX = 0;
    let touchStartY = 0;
    let swipeAction: "open" | "close" | null = null;

    function handleTouchStart(event: TouchEvent) {
      if (!window.matchMedia(MOBILE_MEDIA_QUERY).matches || event.touches.length !== 1) {
        swipeAction = null;
        return;
      }

      const touch = event.touches[0];
      touchStartX = touch.clientX;
      touchStartY = touch.clientY;

      if (!isMobileSidebarOpen && touchStartX <= MOBILE_SWIPE_EDGE_PX) {
        swipeAction = "open";
        return;
      }

      if (isMobileSidebarOpen && touchStartX <= MOBILE_SIDEBAR_WIDTH_PX + MOBILE_SWIPE_EDGE_PX) {
        swipeAction = "close";
        return;
      }

      swipeAction = null;
    }

    function handleTouchEnd(event: TouchEvent) {
      if (!swipeAction || !window.matchMedia(MOBILE_MEDIA_QUERY).matches || event.changedTouches.length !== 1) {
        swipeAction = null;
        return;
      }

      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - touchStartX;
      const deltaY = Math.abs(touch.clientY - touchStartY);
      if (deltaY > MOBILE_SWIPE_MAX_VERTICAL_DELTA_PX) {
        swipeAction = null;
        return;
      }

      if (swipeAction === "open" && deltaX >= MOBILE_SWIPE_MIN_DISTANCE_PX) {
        setIsMobileSidebarOpen(true);
      } else if (swipeAction === "close" && deltaX <= -MOBILE_SWIPE_MIN_DISTANCE_PX) {
        setIsMobileSidebarOpen(false);
      }

      swipeAction = null;
    }

    function handleTouchCancel() {
      swipeAction = null;
    }

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("touchcancel", handleTouchCancel, { passive: true });
    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("touchcancel", handleTouchCancel);
    };
  }, [authenticated, isMobileSidebarOpen]);

  useEffect(() => {
    if (
      !authenticated ||
      !isMobileSidebarOpen ||
      !window.matchMedia(MOBILE_MEDIA_QUERY).matches
    ) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsMobileSidebarOpen(false);
      }
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [authenticated, isMobileSidebarOpen]);

  async function handleLogin(apiKey: string): Promise<void> {
    setLoading(true);
    setError("");
    const valid = await validateKey(apiKey);
    setLoading(false);

    if (!valid) {
      setError("Invalid API key");
      return;
    }

    setKey(apiKey);
    setAuthenticated(true);
    window.location.hash = DEFAULT_HASH;
    setRoute(parseRoute() as AppRoute);
  }

  function handleLogout(): void {
    logout();
  }

  function toggleMobileSidebar(): void {
    setIsMobileSidebarOpen((open) => !open);
  }

  function closeMobileSidebar(): void {
    setIsMobileSidebarOpen(false);
  }

  return (
    <div id="app">
      {authenticated ? (
        <div className="app-shell" id="view-app">
          <Sidebar
            currentRoute={routeName}
            isMobileOpen={isMobileSidebarOpen}
            onLogout={handleLogout}
            onNavigate={closeMobileSidebar}
            route={route}
          />
          <main className="app-main">
            <div className="mobile-topbar">
              <button
                aria-controls="app-sidebar-nav"
                aria-expanded={isMobileSidebarOpen}
                aria-label={isMobileSidebarOpen ? "Close navigation menu" : "Open navigation menu"}
                className="btn btn--secondary btn--small mobile-sidebar-toggle"
                onClick={toggleMobileSidebar}
                type="button"
              >
                <span
                  aria-hidden="true"
                  className={[
                    "mobile-sidebar-toggle__icon",
                    isMobileSidebarOpen ? "is-open" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                />
                <span>{isMobileSidebarOpen ? "Close" : "Menu"}</span>
              </button>
              <strong className="mobile-topbar__title">{mobileRouteTitle}</strong>
            </div>
            <ViewHost route={route} />
          </main>
        </div>
      ) : (
        <LoginView error={error} loading={loading} onSubmit={handleLogin} />
      )}
      {authenticated ? (
        <button
          aria-hidden={!isMobileSidebarOpen}
          aria-label="Close navigation menu"
          className={[
            "mobile-sidebar-backdrop",
            isMobileSidebarOpen ? "is-visible" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={closeMobileSidebar}
          tabIndex={isMobileSidebarOpen ? 0 : -1}
          type="button"
        />
      ) : null}

      <ManualScrapeModalTemplate />
      <div aria-live="polite" className="toast-root" id="toast-root" />
    </div>
  );
}

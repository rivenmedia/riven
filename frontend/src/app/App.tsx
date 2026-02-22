import { useEffect, useMemo, useState } from "react";
import { hasKey, logout, setKey, validateKey } from "../services/auth";
import { parseRoute, replaceRoute } from "../services/router";
import * as statusTracker from "../services/statusTracker";
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

  useEffect(() => {
    function handleHashChange() {
      setRoute(normalizeRoute(parseRoute() as AppRoute));
      setIsMobileSidebarOpen(false);
    }

    window.addEventListener("hashchange", handleHashChange);
    statusTracker.start();

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
      statusTracker.stop();
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
            <button
              aria-controls="app-sidebar-nav"
              aria-expanded={isMobileSidebarOpen}
              aria-label={isMobileSidebarOpen ? "Hide navigation menu" : "Show navigation menu"}
              className="btn btn--secondary btn--small mobile-sidebar-toggle"
              onClick={toggleMobileSidebar}
              type="button"
            >
              {isMobileSidebarOpen ? "Hide menu" : "Show menu"}
            </button>
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

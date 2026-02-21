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

  const routeName = useMemo<RouteName>(() => route?.name || "library", [route]);

  useEffect(() => {
    function handleHashChange() {
      setRoute(normalizeRoute(parseRoute() as AppRoute));
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

  return (
    <div id="app">
      {authenticated ? (
        <div className="app-shell" id="view-app">
          <Sidebar currentRoute={routeName} route={route} onLogout={handleLogout} />
          <main className="app-main">
            <ViewHost route={route} />
          </main>
        </div>
      ) : (
        <LoginView error={error} loading={loading} onSubmit={handleLogin} />
      )}

      <ManualScrapeModalTemplate />
      <div aria-live="polite" className="toast-root" id="toast-root" />
    </div>
  );
}

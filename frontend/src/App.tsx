import { useEffect, useMemo, useState } from "react";
import { hasKey, logout, setKey, validateKey } from "./legacy/js/auth.js";
import { parseRoute } from "./legacy/js/router.js";
import * as statusTracker from "./legacy/js/status_tracker.js";
import LegacyScaffold from "./components/LegacyScaffold";
import LoginView from "./components/LoginView";
import Sidebar from "./components/Sidebar";
import ViewHost from "./components/ViewHost";
import type { AppRoute, RouteName } from "./types";

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
  const [route, setRoute] = useState<AppRoute>(() => parseRoute() as AppRoute);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  const routeName = useMemo<RouteName>(() => route?.name || "library", [route]);

  useEffect(() => {
    function handleHashChange() {
      setRoute(parseRoute() as AppRoute);
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
          <Sidebar currentRoute={routeName} onLogout={handleLogout} />
          <main className="app-main">
            <ViewHost route={route} />
          </main>
        </div>
      ) : (
        <LoginView error={error} loading={loading} onSubmit={handleLogin} />
      )}

      <LegacyScaffold />
      <div aria-live="polite" className="toast-root" id="toast-root" />
    </div>
  );
}

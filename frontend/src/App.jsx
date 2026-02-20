import { useEffect, useMemo, useState } from "react";
import { hasKey, logout, setKey, validateKey } from "../../src/static/js/auth.js";
import { parseRoute } from "../../src/static/js/router.js";
import * as statusTracker from "../../src/static/js/status_tracker.js";
import LegacyScaffold from "./components/LegacyScaffold.jsx";
import LoginView from "./components/LoginView.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ViewHost from "./components/ViewHost.jsx";

const DEFAULT_HASH = "#/library";

function applyRouteTheme(routeName) {
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
  const [authenticated, setAuthenticated] = useState(() => hasKey());
  const [route, setRoute] = useState(() => parseRoute());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const routeName = useMemo(() => route?.name || "library", [route]);

  useEffect(() => {
    function handleHashChange() {
      setRoute(parseRoute());
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
      setRoute(parseRoute());
    }
  }, [authenticated]);

  useEffect(() => {
    applyRouteTheme(authenticated ? routeName : "library");
  }, [authenticated, routeName]);

  async function handleLogin(apiKey) {
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
    setRoute(parseRoute());
  }

  function handleLogout() {
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
        <LoginView
          error={error}
          loading={loading}
          onSubmit={handleLogin}
        />
      )}

      <LegacyScaffold />
      <div aria-live="polite" className="toast-root" id="toast-root" />
    </div>
  );
}

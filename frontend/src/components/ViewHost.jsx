import { useEffect, useMemo, useRef } from "react";
import * as statusTracker from "../../../src/static/js/status_tracker.js";
import { VIEW_LOADERS } from "../viewLoaders.js";
import { VIEW_TEMPLATES } from "../viewTemplates.js";

function getTemplateHtml(routeName) {
  return VIEW_TEMPLATES[routeName] || VIEW_TEMPLATES.library;
}

function getViewLoader(routeName) {
  return VIEW_LOADERS[routeName] || VIEW_LOADERS.library;
}

export default function ViewHost({ route }) {
  const hostRef = useRef(null);
  const loadVersionRef = useRef(0);

  const routeKey = useMemo(
    () => `${route?.name || "library"}|${route?.param || ""}|${JSON.stringify(route?.query || {})}`,
    [route],
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host) {
      return;
    }

    loadVersionRef.current += 1;
    const loadVersion = loadVersionRef.current;

    statusTracker.clear();
    host.innerHTML = getTemplateHtml(route?.name);

    const loader = getViewLoader(route?.name);
    Promise.resolve(loader?.load?.(route, host)).catch((error) => {
      if (loadVersion !== loadVersionRef.current) {
        return;
      }
      console.error("Failed to load route view:", error);
      host.innerHTML = `
        <section class="view">
          <p class="error-msg">Failed to load this view.</p>
        </section>
      `;
    });
  }, [route, routeKey]);

  return <div className="view-host" id="view-container" ref={hostRef} />;
}

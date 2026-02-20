import { useEffect, useMemo, useRef } from "react";
import * as statusTracker from "../../../src/static/js/status_tracker.js";
import { VIEW_LOADERS } from "../viewLoaders";
import { VIEW_TEMPLATES } from "../viewTemplates";
import type { AppRoute, RouteName, ViewLoaderModule } from "../types";

function getTemplateHtml(routeName: RouteName): string {
  return VIEW_TEMPLATES[routeName] || VIEW_TEMPLATES.library;
}

function getViewLoader(routeName: RouteName): ViewLoaderModule {
  return VIEW_LOADERS[routeName] || VIEW_LOADERS.library;
}

interface ViewHostProps {
  route: AppRoute;
}

export default function ViewHost({ route }: ViewHostProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const loadVersionRef = useRef<number>(0);

  const routeKey = useMemo(
    () =>
      `${route.name || "library"}|${route.param || ""}|${JSON.stringify(route.query || {})}`,
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
    host.innerHTML = getTemplateHtml(route.name);

    const loader = getViewLoader(route.name);
    Promise.resolve(loader?.load?.(route, host)).catch((error: unknown) => {
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

import type { RouteName } from "../../app/routeTypes";

/** Session key: last library list route visited (set by Library views). */
export const LIBRARY_RETURN_ROUTE_KEY = "riven_return_route";

export type LibraryListRoute = Extract<
  RouteName,
  "library" | "movies" | "shows" | "episodes"
>;

const VALID = new Set<string>(["library", "movies", "shows", "episodes"]);

/** Route used for breadcrumbs / sidebar when deep-linked into `#/item/:id`. */
export function readLibraryReturnRoute(): LibraryListRoute | null {
  try {
    const raw = sessionStorage.getItem(LIBRARY_RETURN_ROUTE_KEY);
    if (raw && VALID.has(raw)) {
      return raw as LibraryListRoute;
    }
  } catch {
    /* ignore */
  }
  return null;
}

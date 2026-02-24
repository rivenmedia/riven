import type { ComponentType } from "react";

export type RouteName =
  | "library"
  | "movies"
  | "shows"
  | "episodes"
  | "explore"
  | "trending"
  | "dashboard"
  | "dashboard-services"
  | "dashboard-states"
  | "dashboard-releases"
  | "inspector"
  | "settings"
  | "vfs-stats"
  | "item"
  | "calendar"
  | "mount";

export interface AppRoute {
  name: RouteName;
  param: string | null;
  segments: string[];
  query: Record<string, string>;
  path: string;
}

/** Props for React route view components. */
export interface ViewComponentProps {
  route: AppRoute;
}

/** React component type for a route view. */
export type ViewComponent = ComponentType<ViewComponentProps>;

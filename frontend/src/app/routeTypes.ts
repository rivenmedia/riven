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

export interface ViewLoaderModule {
  load?: (route: AppRoute, container: HTMLElement) => Promise<void> | void;
}

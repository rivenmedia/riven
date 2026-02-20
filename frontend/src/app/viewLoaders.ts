import * as calendarView from "../views/calendar";
import * as dashboardView from "../views/dashboard";
import * as exploreView from "../views/explore";
import * as inspectorView from "../views/inspector";
import * as itemDetailView from "../views/itemDetail";
import * as libraryView from "../views/library";
import * as mountView from "../views/mount";
import * as settingsView from "../views/settings";
import * as trendingView from "../views/trending";
import * as vfsStatsView from "../views/vfsStats";
import type { RouteName, ViewLoaderModule } from "./routeTypes";

export const VIEW_LOADERS: Record<RouteName, ViewLoaderModule> = {
  library: libraryView as ViewLoaderModule,
  movies: libraryView as ViewLoaderModule,
  shows: libraryView as ViewLoaderModule,
  explore: exploreView as ViewLoaderModule,
  trending: trendingView as ViewLoaderModule,
  dashboard: dashboardView as ViewLoaderModule,
  inspector: inspectorView as ViewLoaderModule,
  settings: settingsView as ViewLoaderModule,
  "vfs-stats": vfsStatsView as ViewLoaderModule,
  item: itemDetailView as ViewLoaderModule,
  calendar: calendarView as ViewLoaderModule,
  mount: mountView as ViewLoaderModule,
};

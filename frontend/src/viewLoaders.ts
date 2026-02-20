import * as calendarView from "./legacy/js/views/calendar";
import * as dashboardView from "./legacy/js/views/dashboard";
import * as exploreView from "./legacy/js/views/explore";
import * as inspectorView from "./legacy/js/views/inspector";
import * as itemDetailView from "./legacy/js/views/item_detail";
import * as libraryView from "./legacy/js/views/library";
import * as mountView from "./legacy/js/views/mount";
import * as settingsView from "./legacy/js/views/settings";
import * as trendingView from "./legacy/js/views/trending";
import * as vfsStatsView from "./legacy/js/views/vfs_stats";
import type { RouteName, ViewLoaderModule } from "./types";

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

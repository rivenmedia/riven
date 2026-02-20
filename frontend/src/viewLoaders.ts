import * as calendarView from "../../src/static/js/views/calendar.js";
import * as dashboardView from "../../src/static/js/views/dashboard.js";
import * as exploreView from "../../src/static/js/views/explore.js";
import * as inspectorView from "../../src/static/js/views/inspector.js";
import * as itemDetailView from "../../src/static/js/views/item_detail.js";
import * as libraryView from "../../src/static/js/views/library.js";
import * as mountView from "../../src/static/js/views/mount.js";
import * as settingsView from "../../src/static/js/views/settings.js";
import * as trendingView from "../../src/static/js/views/trending.js";
import * as vfsStatsView from "../../src/static/js/views/vfs_stats.js";
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

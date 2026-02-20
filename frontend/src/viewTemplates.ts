import calendarTemplate from "../../src/templates/views/calendar.html?raw";
import dashboardTemplate from "../../src/templates/views/dashboard.html?raw";
import exploreTemplate from "../../src/templates/views/explore.html?raw";
import inspectorTemplate from "../../src/templates/views/inspector.html?raw";
import itemDetailTemplate from "../../src/templates/views/item_detail.html?raw";
import libraryTemplate from "../../src/templates/views/library.html?raw";
import mountTemplate from "../../src/templates/views/mount.html?raw";
import settingsTemplate from "../../src/templates/views/settings.html?raw";
import trendingTemplate from "../../src/templates/views/trending.html?raw";
import vfsStatsTemplate from "../../src/templates/views/vfs_stats.html?raw";
import type { RouteName } from "./types";

export const VIEW_TEMPLATES: Record<RouteName, string> = {
  library: libraryTemplate,
  movies: libraryTemplate,
  shows: libraryTemplate,
  explore: exploreTemplate,
  trending: trendingTemplate,
  dashboard: dashboardTemplate,
  inspector: inspectorTemplate,
  settings: settingsTemplate,
  "vfs-stats": vfsStatsTemplate,
  item: itemDetailTemplate,
  calendar: calendarTemplate,
  mount: mountTemplate,
};

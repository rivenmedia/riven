import type { ComponentType } from 'react';
import type { AppRoute, RouteName, ViewComponentProps } from './routeTypes';
import SettingsView from '../views/SettingsView';
import TrendingView from '../views/TrendingView';
import CalendarView from '../views/CalendarView';
import MountView from '../views/MountView';
import VfsStatsView from '../views/VfsStatsView';
import InspectorView from '../views/InspectorView';
import LibraryView from '../views/LibraryView';
import ItemDetailView from '../views/ItemDetailView';
import ExploreView from '../views/ExploreView';
import DashboardView from '../views/DashboardView';

export type { ViewComponentProps };

export const ROUTE_VIEWS: Record<
  RouteName,
  ComponentType<ViewComponentProps>
> = {
  library: LibraryView,
  movies: LibraryView,
  shows: LibraryView,
  episodes: LibraryView,
  explore: ExploreView,
  trending: TrendingView,
  dashboard: DashboardView,
  'dashboard-services': DashboardView,
  'dashboard-states': DashboardView,
  'dashboard-releases': DashboardView,
  inspector: InspectorView,
  settings: SettingsView,
  'vfs-stats': VfsStatsView,
  item: ItemDetailView,
  calendar: CalendarView,
  mount: MountView,
};

export function getViewComponent(routeName: RouteName): ComponentType<ViewComponentProps> {
  return ROUTE_VIEWS[routeName] ?? LibraryView;
}

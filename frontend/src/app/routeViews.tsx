import type { ComponentType } from 'react';
import type { AppRoute, RouteName, ViewComponentProps } from './routeTypes';
import SettingsView from '../features/settings/SettingsView';
import TrendingView from '../features/trending/TrendingView';
import CalendarView from '../features/calendar/CalendarView';
import MountView from '../features/mount/MountView';
import VfsStatsView from '../features/vfs/VfsStatsView';
import InspectorView from '../features/inspector/InspectorView';
import LibraryView from '../features/library/LibraryView';
import ItemDetailView from '../features/item-detail/ItemDetailView';
import ExploreView from '../features/explore';
import DiscoverySearchView from '../features/discovery/DiscoverySearchView';
import DashboardView from '../features/dashboard/DashboardView';
import DiscoverItemView from '../features/discovery/DiscoverItemView';

export type { ViewComponentProps };

export const ROUTE_VIEWS: Record<
  RouteName,
  ComponentType<ViewComponentProps>
> = {
  library: LibraryView,
  movies: LibraryView,
  shows: LibraryView,
  episodes: LibraryView,
  search: DiscoverySearchView,
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
  'discover-item': DiscoverItemView,
};

export function getViewComponent(routeName: RouteName): ComponentType<ViewComponentProps> {
  return ROUTE_VIEWS[routeName] ?? LibraryView;
}

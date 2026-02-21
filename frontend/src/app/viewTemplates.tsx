import { renderToStaticMarkup } from "react-dom/server";
import { Panel, ViewHeader, ViewLayout } from "../components/ui/PagePrimitives";
import type { RouteName } from "./routeTypes";

function LibraryTemplate() {
  return (
    <ViewLayout className="view-library" view="library">
      <ViewHeader
        subtitle={
          <p data-slot="subtitle">
            Manage your local media queue, statuses, and backend actions.
          </p>
        }
        title={<h1 data-slot="title">Library</h1>}
      />

      <form className="toolbar toolbar--library" data-slot="filters">
        <input
          data-slot="search"
          placeholder="Search title or imdb/tmdb/tvdb id"
          type="search"
        />
        <select data-slot="state"></select>
        <select data-slot="sort">
          <option value="date_desc">Newest requested</option>
          <option value="date_asc">Oldest requested</option>
          <option value="title_asc">Title A-Z</option>
          <option value="title_desc">Title Z-A</option>
        </select>
        <select data-slot="limit">
          <option value="24">24 / page</option>
          <option value="48">48 / page</option>
          <option value="96">96 / page</option>
        </select>
        <button className="btn btn--primary" type="submit">
          Apply
        </button>
      </form>

      <div className="media-grid" data-slot="grid"></div>
      <p className="empty-state" data-slot="empty" hidden>
        No items matched the current filters.
      </p>
      <div className="pagination-bar" data-slot="pagination"></div>
    </ViewLayout>
  );
}

function ExploreTemplate() {
  return (
    <ViewLayout className="view-explore" view="explore">
      <ViewHeader
        subtitle={
          <p>
            Traverse TMDB/TVDB metadata across movies, TV shows, cast and
            related works.
          </p>
        }
        title="Discovery Graph"
      />

      <form className="toolbar toolbar--explore" data-slot="search-form">
        <select data-slot="source">
          <option value="tmdb">TMDB</option>
          <option value="tvdb">TVDB</option>
        </select>
        <select data-slot="mode">
          <option value="search">Search</option>
          <option value="discover">Discover</option>
        </select>
        <div data-slot="media-type-toggle"></div>
        <div data-slot="trending-window-wrap" className="toolbar-group" hidden>
          <select data-slot="window">
            <option value="day">Today</option>
            <option value="week">This Week</option>
          </select>
        </div>
        <input
          data-slot="query"
          placeholder="Search title / person / keywords"
          type="search"
        />
        <button className="btn btn--primary" type="submit">
          Load
        </button>
      </form>

      <div className="explore-layout explore-layout--results-only">
        <section className="explore-results">
          <div className="section-head">
            <h2 data-slot="results-title">Results</h2>
            <div
              className="pagination-bar pagination-bar--inline"
              data-slot="pagination"
            ></div>
          </div>
          <div className="media-grid media-grid--dense" data-slot="grid"></div>
          <p className="empty-state" data-slot="empty" hidden>
            No results.
          </p>
        </section>

        <aside className="explore-panel" data-slot="detail-panel">
          <div className="section-head">
            <h2>Metadata Graph</h2>
          </div>
          <div className="explore-breadcrumbs" data-slot="breadcrumbs"></div>
          <div className="explore-detail" data-slot="detail">
            <p className="muted">
              Select a card to inspect cast, recommendations, and linked
              entries.
            </p>
          </div>
        </aside>
      </div>
    </ViewLayout>
  );
}

function TrendingTemplate() {
  return (
    <ViewLayout className="view-trending" view="trending">
      <ViewHeader
        subtitle="Monitor what is hot on TMDB and push content into your library."
        title="Trending"
      />

      <form className="toolbar toolbar--trending" data-slot="controls">
        <div data-slot="media-type-toggle"></div>
        <select data-slot="window">
          <option value="day">Today</option>
          <option value="week">This Week</option>
        </select>
        <button className="btn btn--primary" type="submit">
          Refresh
        </button>
      </form>

      <div className="media-grid" data-slot="grid"></div>
      <p className="empty-state" data-slot="empty" hidden>
        No trending entries were returned.
      </p>
    </ViewLayout>
  );
}

function DashboardTemplate() {
  return (
    <ViewLayout className="view-dashboard" view="dashboard">
      <ViewHeader
        actions={
          <button className="btn btn--warning" data-action="retry-library">
            Retry Active Library
          </button>
        }
        subtitle="Backend health, queue activity, services, and operational metrics."
        title="Dashboard"
      />

      <section className="kpi-grid" data-slot="kpis"></section>

      <div className="split-grid">
        <Panel>
          <div className="section-head">
            <h2>Services</h2>
          </div>
          <div data-slot="services-list"></div>
        </Panel>

        <Panel>
          <div className="section-head">
            <h2>Downloader Accounts</h2>
          </div>
          <div data-slot="downloader-info"></div>
        </Panel>
      </div>

      <Panel>
        <div className="section-head">
          <h2>State Distribution</h2>
        </div>
        <div data-slot="state-bars"></div>
      </Panel>

      <div className="split-grid">
        <Panel>
          <div className="section-head">
            <h2>Request Activity (30d)</h2>
          </div>
          <div data-slot="activity-chart"></div>
        </Panel>
        <Panel>
          <div className="section-head">
            <h2>Releases by Year</h2>
          </div>
          <div data-slot="release-chart"></div>
        </Panel>
      </div>
    </ViewLayout>
  );
}

function InspectorTemplate() {
  return (
    <ViewLayout className="view-inspector" view="inspector">
      <ViewHeader
        subtitle="Inspect backend internals, logs, and arbitrary API endpoint responses."
        title="Inspector"
      />

      <div className="split-grid">
        <Panel>
          <div className="section-head">
            <h2>Quick Endpoints</h2>
          </div>
          <div className="quick-endpoints" data-slot="quick-endpoints"></div>
          <pre className="json-output" data-slot="quick-output"></pre>
        </Panel>

        <Panel>
          <div className="section-head">
            <h2>Endpoint Runner</h2>
          </div>
          <form className="endpoint-form" data-slot="endpoint-form">
            <select data-slot="method">
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="DELETE">DELETE</option>
            </select>
            <input data-slot="path" placeholder="/stats" type="text" />
            <textarea
              data-slot="body"
              placeholder='{"example":"payload"}'
            ></textarea>
            <button className="btn btn--primary" type="submit">
              Run
            </button>
          </form>
          <pre className="json-output" data-slot="runner-output"></pre>
        </Panel>
      </div>

      <Panel>
        <div className="section-head">
          <h2>Logs (Virtualized)</h2>
          <div className="toolbar">
            <button
              className="btn btn--secondary btn--small"
              data-action="refresh-logs"
              type="button"
            >
              Refresh
            </button>
          </div>
        </div>
        <div className="log-toolbar">
          <input data-slot="log-search" placeholder="Filter logs" type="search" />
        </div>
        <div className="log-meta" data-slot="log-meta"></div>
        <div data-slot="log-container"></div>
      </Panel>
    </ViewLayout>
  );
}

function SettingsTemplate() {
  return (
    <ViewLayout className="view-settings" view="settings">
      <ViewHeader
        actions={
          <>
            <button className="btn btn--secondary" data-action="reload-from-disk">
              Reload
            </button>
            <button className="btn btn--primary" data-action="save-to-disk">
              Save File
            </button>
          </>
        }
        subtitle="Edit settings by logical groups and persist directly through API."
        title="Settings"
      />

      <div className="toolbar toolbar--settings">
        <input
          data-slot="filter"
          placeholder="Filter groups (e.g. filesystem, ranking)"
          type="search"
        />
      </div>

      <div className="settings-groups" data-slot="groups"></div>
    </ViewLayout>
  );
}

function VfsStatsTemplate() {
  return (
    <ViewLayout className="view-vfs-stats" view="vfs-stats">
      <ViewHeader
        subtitle="Runtime statistics for mounted VFS opener operations."
        title="VFS Statistics"
      />
      <Panel>
        <div data-slot="table"></div>
      </Panel>
    </ViewLayout>
  );
}

function ItemDetailTemplate() {
  return (
    <ViewLayout className="view-item-detail" view="item-detail">
      <ViewHeader
        subtitle="Inspect metadata, stream state, and backend action controls."
        title="Library Item"
      />

      <div className="item-layout">
        <div className="item-main">
          <div className="item-detail-header" data-slot="header">
            <div className="item-poster" data-slot="poster"></div>
            <div className="item-info" data-slot="info"></div>
          </div>
          <div className="item-actions-bar" data-slot="actions"></div>
          <div className="panel" data-slot="metadata"></div>
          <div className="panel item-streams" data-slot="streams"></div>
          <div className="panel item-video" data-slot="video"></div>
        </div>
      </div>
    </ViewLayout>
  );
}

function CalendarTemplate() {
  return (
    <ViewLayout className="view-calendar" view="calendar">
      <ViewHeader
        subtitle="Upcoming or recently aired entries from your managed media graph."
        title="Release Calendar"
      />
      <Panel>
        <div data-slot="content"></div>
      </Panel>
    </ViewLayout>
  );
}

function MountTemplate() {
  return (
    <ViewLayout className="view-mount" view="mount">
      <ViewHeader
        subtitle="Current VFS mount inventory exposed by the backend filesystem service."
        title="Mounted Files"
      />
      <Panel className="mount-panel">
        <div className="toolbar toolbar--mount">
          <input data-slot="search" placeholder="Filter by file/path" type="search" />
        </div>
        <div className="mount-stats" data-slot="stats"></div>
        <div data-slot="content"></div>
      </Panel>
    </ViewLayout>
  );
}

const LIBRARY_TEMPLATE = renderToStaticMarkup(<LibraryTemplate />);
const EXPLORE_TEMPLATE = renderToStaticMarkup(<ExploreTemplate />);
const TRENDING_TEMPLATE = renderToStaticMarkup(<TrendingTemplate />);
const DASHBOARD_TEMPLATE = renderToStaticMarkup(<DashboardTemplate />);
const INSPECTOR_TEMPLATE = renderToStaticMarkup(<InspectorTemplate />);
const SETTINGS_TEMPLATE = renderToStaticMarkup(<SettingsTemplate />);
const VFS_STATS_TEMPLATE = renderToStaticMarkup(<VfsStatsTemplate />);
const ITEM_DETAIL_TEMPLATE = renderToStaticMarkup(<ItemDetailTemplate />);
const CALENDAR_TEMPLATE = renderToStaticMarkup(<CalendarTemplate />);
const MOUNT_TEMPLATE = renderToStaticMarkup(<MountTemplate />);

export const VIEW_TEMPLATES: Record<RouteName, string> = {
  library: LIBRARY_TEMPLATE,
  movies: LIBRARY_TEMPLATE,
  shows: LIBRARY_TEMPLATE,
  explore: EXPLORE_TEMPLATE,
  trending: TRENDING_TEMPLATE,
  dashboard: DASHBOARD_TEMPLATE,
  inspector: INSPECTOR_TEMPLATE,
  settings: SETTINGS_TEMPLATE,
  "vfs-stats": VFS_STATS_TEMPLATE,
  item: ITEM_DETAIL_TEMPLATE,
  calendar: CALENDAR_TEMPLATE,
  mount: MOUNT_TEMPLATE,
};

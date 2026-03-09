# Riven documentation index

Backend API reference and architecture docs for Riven. Use this index to find the right doc for each area.

| Doc | Description |
|-----|-------------|
| [API Overview](api-overview.md) | Base URL, auth, and list of all API routers with prefixes. |
| [Items](api-items.md) | Media items API: list/search, add, reset, retry, remove, pause, unpause, streams (get/blacklist/pin/refresh), reindex, aliases, metadata. |
| [Scraping](scraping.md) | Scraping backend flow, GET/POST scrape endpoints, auto scrape, manual session (start_session, session actions), parse titles; includes request/response and DB samples. |
| [VFS](vfs.md) | Virtual filesystem: FUSE mount, path generation, library profiles, when files appear/disappear, open/read flow, chunk cache, settings. |
| [Discover / TMDB / TVDB](api-discover.md) | Discover, search, trending, and TMDB/TVDB detail endpoints (movies, TV, people, credits); normalized responses and library status. |
| [Default / Misc](api-default.md) | Health, downloader user info, API key, services, Trakt OAuth, stats, logs, events, mount, upload_logs, calendar, vfs_stats, debug bundle. |
| [Database](api-database.md) | Database backup, restore, download backup file, clean snapshots. |
| [Settings](api-settings.md) | Settings schema, load/save, get/set by path or in bulk. |
| [Stream](api-stream.md) | Stream file by item ID, HLS playlist/segments, SSE event types. |
| [Webhooks](api-webhooks.md) | Overseerr webhook payload and behavior. |
| [WebSocket](api-ws.md) | WebSocket by topic; auth note. |

# API Overview

Base URL: **`/api/v1`**

All endpoints under `/api/v1` (except `/api/v1/` and WebSocket) require API key authentication via header `x-api-key` or query param `api_key`.

---

## Root

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/` | Root; returns `{ "message": "Riven is running!", "version": "<version>" }` |

---

## Routers (prefixes)

| Prefix | Doc | Description |
|--------|-----|-------------|
| *(none)* | [api-default.md](api-default.md) | Health, stats, services, calendar, logs, mount, debug, Trakt OAuth, generate API key |
| `/items` | [api-items.md](api-items.md) | Media items CRUD, search, add, reset, retry, remove, pause, unpause, streams, reindex, aliases, metadata |
| `/scrape` | [scraping.md](scraping.md) | Get streams, auto scrape, manual session, parse titles, Overseerr requests |
| `/discover`* | [api-discover.md](api-discover.md) | TMDB/TVDB discover, search, details, credits, trending |
| `/database` | [api-database.md](api-database.md) | Backup, restore, download backup, clean snapshots |
| `/settings` | [api-settings.md](api-settings.md) | Schema, load, save, get/set settings |
| `/stream` | [api-stream.md](api-stream.md) | Stream file by item ID, HLS playlist/segments, SSE event types |
| `/webhook` | [api-webhooks.md](api-webhooks.md) | Overseerr webhook |
| `/ws` | [api-ws.md](api-ws.md) | WebSocket by topic (different auth: `resolve_ws_api_key`) |

\* Discover router has no prefix; its routes are mounted at `/api/v1/` with paths like `/discover/tmdb/movie`, `/search/tmdb/movie`, `/tmdb/movie/{id}`, etc.

---

## Common patterns

- **ID list body**: Many POST/DELETE endpoints accept `{ "ids": ["1", "2", "3"] }` (array of string IDs; parsed as integers).
- **Message response**: `{ "message": "..." }`.
- **Errors**: `404` (not found), `400` (bad request), `412` (precondition failed, e.g. service not initialized), `503` (service unavailable).

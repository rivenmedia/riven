# Items API

Base path: **`/api/v1/items`**

Media items (movies, shows, seasons, episodes), streams, and item lifecycle.

---

## GET `/api/v1/items/states`

Returns the list of pipeline states.

**Response:** `{ "success": true, "states": ["Requested", "Indexed", "Scraped", ...] }`

---

## GET `/api/v1/items`

Search/list media items with filters and pagination.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Items per page (≥1) |
| `page` | int | 1 | Page number |
| `type` | list | — | Filter by `movie`, `show`, `season`, `episode`, `anime` |
| `states` | list | — | Filter by state name(s), or `All` |
| `sort` | list | — | `title_asc`, `title_desc`, `date_asc`, `date_desc` (one per type) |
| `search` | str | — | Search by title or `tt...` (IMDB), `tmdb_<id>`, `tvdb_<id>` |
| `year` | int | — | Filter by release year |
| `extended` | bool | false | Include extended item details |

**Response:** `{ "success": true, "items": [...], "page": 1, "limit": 50, "total_items": N, "total_pages": M }`

---

## POST `/api/v1/items/add`

Add media items by TMDB or TVDB ID.

**Body:**
```json
{
  "media_type": "movie" | "tv",
  "tmdb_ids": ["438631", "123"],
  "tvdb_ids": ["12345"]
}
```
- `media_type`: required.
- For movie: at least one `tmdb_id`.
- For tv: at least one of `tmdb_ids` or `tvdb_ids`.

**Response:** `{ "message": "..." }`

---

## GET `/api/v1/items/library/status`

Check whether given TMDB/TVDB IDs exist in the library.

**Query params:** `tmdb_ids` (comma-separated), `tvdb_ids` (comma-separated).

**Response:** Object keyed by external ID with `in_library`, `library_item_id`, `library_state`, `library_type`, `library_title`, etc.

---

## GET `/api/v1/items/{id}`

Get a single media item by ID.

**Query params:** `media_type` (optional, for polymorphic load), `extended` (bool).

**Response:** Item object (dict). 404 if not found.

---

## POST `/api/v1/items/reset`

Reset items to initial state; blacklists active stream, triggers media server refresh.

**Body:** `{ "ids": ["1", "2"] }`

**Response:** `{ "message": "...", "ids": [1, 2] }`

---

## POST `/api/v1/items/retry`

Re-queue items for processing (clears scrape cooldown, re-adds event).

**Body:** `{ "ids": ["1", "2"] }`

**Response:** `{ "message": "...", "ids": [1, 2] }`

---

## POST `/api/v1/items/retry_library`

Retry all library items that failed to download. No body.

**Response:** `{ "message": "...", "ids": [ ... ] }`

---

## DELETE `/api/v1/items/remove`

Permanently remove movies or shows (and all children). Only movie/show types allowed.

**Body:** `{ "ids": ["1", "2"] }`

**Response:** `{ "message": "...", "ids": [1, 2] }`

---

## GET `/api/v1/items/{item_id}/streams`

Get streams and blacklisted streams for an item. For episodes with no streams, uses parent season’s streams.

**Response:**
```json
{
  "message": "...",
  "streams": [{ "id": 1, "infohash": "...", "raw_title": "...", "parsed_title": "...", "rank": 90, "lev_ratio": 1.0, "resolution": "1080p", "is_cached": false }],
  "blacklisted_streams": [...],
  "active_stream": { ... } | null
}
```

---

## POST `/api/v1/items/{item_id}/streams/{stream_id}/blacklist`

Blacklist a stream for the item.

**Response:** `{ "message": "..." }`

---

## POST `/api/v1/items/{item_id}/streams/{stream_id}/unblacklist`

Remove a stream from the item’s blacklist.

**Response:** `{ "message": "..." }`

---

## POST `/api/v1/items/{item_id}/streams/reset`

Reset all streams for the item.

**Response:** `{ "message": "..." }`

---

## POST `/api/v1/items/{item_id}/streams/refresh`

Re-scrape and merge new streams into the item (manual mode, no bucket limit). See [scraping.md](scraping.md).

**Response:** `{ "message": "Added N new stream(s)..." }` or no new streams.

---

## POST `/api/v1/items/{item_id}/streams/{stream_id}/pin`

Pin a stream as the active stream for the item.

**Response:** `{ "message": "..." }`

---

## POST `/api/v1/items/pause`

Pause items (and their children) from being processed.

**Body:** `{ "ids": ["1", "2"] }`

**Response:** `{ "message": "...", "ids": [1, 2] }`

---

## POST `/api/v1/items/unpause`

Unpause items to resume processing.

**Body:** `{ "ids": ["1", "2"] }`

**Response:** `{ "message": "...", "ids": [1, 2] }`

---

## POST `/api/v1/items/reindex`

Reindex a movie or show to pick up new seasons/episodes (runs indexer).

**Body:** `{ "item_id": 123 }` or `{ "tvdb_id": "..." }` (and optional `tmdb_id`).

**Response:** `{ "message": "..." }`

---

## GET `/api/v1/items/{item_id}/aliases`

Get aliases for the item (e.g. for scraping).

**Response:** `{ "aliases": { "<lang>": ["title1", "title2"], ... } }`

---

## GET `/api/v1/items/{item_id}/metadata`

Get metadata for the item.

**Response:** MediaMetadata object (title, type, poster, year, etc.).

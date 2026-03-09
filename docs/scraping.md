# Scraping: Backend Process & API

Backend perspective on how scraping works, the HTTP API, and how to use it (including for a frontend rework).

---

## Overview

**Scraping** finds torrent streams for a media item (movie, show, season, episode) by querying configured scraper services (Torrentio, Prowlarr, Jackett, Comet, etc.). Results are parsed with RTN (Release Title Normalizer), ranked, filtered by item type and settings, then either returned via API or fed into the pipeline (download → symlink → completed).

- **Manual scrape**: User-triggered; returns streams for display/selection; can optionally start a "manual session" to pick files from a chosen torrent and trigger download.
- **Auto scrape**: Enqueues the item (or specific seasons) into the pipeline; scraping runs in the background via the event manager; new streams are merged into the item and the pipeline continues (Downloader → Symlinker → etc.).
- **Refresh streams**: Re-scrapes an existing item and merges new streams into it (no pipeline; manual mode, no bucket limit).

---

## Backend Process (Behind the Scenes)

### 1. Scraper services

- **Location**: `program/services/scrapers/`
- **Entrypoint**: `Scraping` in `program/services/scrapers/__init__.py` aggregates all scraper services.
- **Services** (when enabled in settings): AIOStreams, Comet, Jackett, Mediafusion, Orionoid, Prowlarr, Rarbg, Torrentio, Zilean.
- **Base contract** (`program/services/scrapers/base.py`): Each `ScraperService` implements:
  - `validate() -> bool` (can we use this scraper?)
  - `scrape(item: MediaItem) -> dict[str, str]` → infohash → raw title.

`Scraping` keeps only `initialized_services` (those that passed `validate()`). At least one must be initialized or the scraping system is considered unavailable (412 from API).

### 2. Single scrape run (sync)

- **Method**: `Scraping.scrape(item, verbose_logging=True, manual=False) -> dict[str, Stream]`
- **Steps**:
  1. Run all initialized scraper services **in parallel** (`ThreadPoolExecutor`), each returning `dict[str, str]` (infohash → raw title).
  2. Merge all raw results into one `dict[str, str]`.
  3. **Parse & rank** via `parse_results()` in `program/services/scrapers/shared.py`:
     - Uses RTN with effective ranking settings (including overrides from request/context).
     - For each infohash/title: rank, filter by item type (movie vs show/season/episode), resolution/year/country/dubbed anime, etc. `manual=True` bypasses most content filters.
     - Apply bucket limit (keep top N per bucket; manual mode uses bucket_limit=0).
  4. Return `dict[infohash, Stream]` (program `Stream` wraps RTN `Torrent`).

So "behind the scenes": parallel HTTP (or similar) calls to each scraper → raw titles → single RTN parse/rank/filter step → deduplicated, sorted streams.

### 3. Streaming scrape (for SSE)

- **Method**: `Scraping.scrape_streaming(item, manual=False)` → generator `(service_name, dict[str, Stream])`.
- Same as above, but each service runs in a thread and **as soon as one finishes** its results are merged into the cumulative raw results, `parse_results()` is run on the cumulative set, and the generator yields `(service_name, parsed_streams)`. So the API can send SSE events per service without waiting for all services.

### 4. Auto scrape and the pipeline

- **Trigger**: `POST /api/v1/scrape/auto` with body `{ media_type, item_id | tmdb_id | tvdb_id | imdb_id, season_numbers?, ... }`.
- **Flow**:
  1. **Resolve item**: `resolve_media_item()` (by id or external ids; can create and index a new item from TMDB/TVDB/IMDB if not found).
  2. **Optional season selection** (TV only): If `season_numbers` is provided, only those seasons are unscoped; others are paused. Events are emitted only for the selected seasons (and their episodes).
  3. **Enqueue**: `di[Program].em.add_event(Event("API", item.id, overrides=overrides))` (and per season/episode when using `season_numbers`).
  4. **Pipeline** (`program/state_transition.py`): When the event is processed and the item is in `Indexed` state, the next step is **Scraping**. For a **Show**, the pipeline first submits the show (pack scrape), then each season, then each episode; for **Season**, it submits the season then episodes; for **Episode** or **Movie**, it submits the single item. Whether an item is submitted is gated by `scraping.should_submit(item)` (cooldown after `scraped_at`, `scraped_times`, `max_failed_attempts`).
  5. **Scraping.run()**: Calls `scrape()`, merges **new** streams (not already on item or blacklisted), updates `scraped_at` / `scraped_times`, increments `failed_attempts` if no new streams, optionally marks Failed after `max_failed_attempts`, then yields the item for the next pipeline step (Downloader, etc.).

So "auto scrape" does **not** return streams to the client; it enqueues work and the actual scrape happens asynchronously in the pipeline.

### 5. Item resolution (shared)

- **Function**: `resolve_media_item(session, item_id=None, tmdb_id=None, tvdb_id=None, imdb_id=None, media_type=None, raise_on_not_found=True)` in `routers/secure/scrape.py`.
- **Behavior**:
  - If `item_id`: load by primary key.
  - Else if any of `tmdb_id` / `tvdb_id` / `imdb_id`: try `get_item_by_external_id`.
  - If still not found and external ids present: **create** a new item (movie by `tmdb_id`, tv by `tvdb_id`, or by `imdb_id`), run the **Indexer** once to fetch metadata, persist, then return the new item.
- Used by: scrape GET, start_session, auto_scrape, session update_attributes. So the frontend can call with e.g. `tmdb_id` + `media_type` without an existing library item (backend will create and index it).

---

## HTTP API (Scrape Router)

Base path: **`/api/v1/scrape`**. All endpoints require API key (via header or query). Unless noted, success responses are JSON.

### GET `/api/v1/scrape` — Get streams for an item

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `item_id` | int | Library item ID (optional if other ids given) |
| `tmdb_id` | str | TMDB ID (use with `media_type=movie`) |
| `tvdb_id` | str | TVDB ID (use with `media_type=tv`) |
| `imdb_id` | str | IMDB ID |
| `media_type` | `movie` \| `tv` | Required when using tmdb_id/tvdb_id without item_id |
| `custom_title` | str | Override title for search (not persisted) |
| `custom_imdb_id` | str | Override IMDB id for search (not persisted) |
| `ranking_overrides` | JSON | e.g. `{"resolutions": ["1080p"]}` |
| `stream` | bool | If `true`, return **SSE** stream of results as each scraper completes |
| `min_filesize_override` | int | Min filesize (MB) |
| `max_filesize_override` | int | Max filesize (MB) |

**Identification:** At least one of: `item_id`, or `(tmdb_id, media_type=movie)`, or `(tvdb_id, media_type=tv)`, or `imdb_id`. For SSE (`stream=true`) you must provide a valid combination; otherwise 400.

**Sync response (default):**  
`200` → `{ "message": "...", "streams": { "<infohash>": { "infohash", "raw_title", "parsed_title", "parsed_data", "rank", "lev_ratio", "is_cached" }, ... } }`

**SSE response (`stream=true`):**  
`Content-Type: text/event-stream`. Events are JSON objects with:

- `event`: `"start"` \| `"progress"` \| `"streams"` \| `"complete"` \| `"error"`
- `service`: scraper name (when applicable)
- `message`: human-readable string
- `streams`: optional dict of infohash → same stream shape (incremental on `"streams"`, full on `"complete"`)
- `total_streams`, `services_completed`, `total_services`: progress

**Errors:** 400 (invalid params), 404 (item not found), 412 (scraping services not initialized).

---

## Data samples (API payloads & responses)

### GET `/api/v1/scrape` — Sync response

```json
{
  "message": "Manually scraped streams for item Dune (2021)",
  "streams": {
    "a1b2c3d4e5f6789012345678901234567890abcd": {
      "infohash": "a1b2c3d4e5f6789012345678901234567890abcd",
      "raw_title": "Dune.2021.2160p.UHD.BluRay.x265-HDR.DTS-HD.MA.7.1",
      "parsed_title": "Dune 2021 2160p UHD BluRay x265 HDR",
      "parsed_data": {
        "resolution": "2160p",
        "quality": "bluray",
        "codec": "x265",
        "year": 2021,
        "season": null,
        "episodes": null,
        "dubbed": false,
        "country": null
      },
      "rank": 92,
      "lev_ratio": 1.0,
      "is_cached": true
    }
  }
}
```

`parsed_data` is RTN's `ParsedData` (resolution, quality, codec, year, season, episodes, dubbed, country, etc.). Keys may vary by RTN version.

### GET `/api/v1/scrape?stream=true` — SSE events

Each event is one line: `data: <json>\n\n`.

**Start:**
```json
{"event":"start","service":null,"message":"Starting scrape for Dune (2021)","streams":null,"total_streams":0,"services_completed":0,"total_services":4}
```

**Progress (service finished, no new streams):**
```json
{"event":"progress","service":"Rarbg","message":"Rarbg completed","streams":null,"total_streams":12,"services_completed":1,"total_services":4}
```

**New streams from one service:**
```json
{"event":"streams","service":"Torrentio","message":"Torrentio found 5 new streams","streams":{"abc...":{"infohash":"abc...","raw_title":"Dune.2021...","parsed_title":"Dune 2021 ...","parsed_data":{...},"rank":90,"lev_ratio":1.0,"is_cached":false}},"total_streams":17,"services_completed":2,"total_services":4}
```

**Complete:**
```json
{"event":"complete","service":null,"message":"Scraping complete. Found 23 total streams.","streams":{...},"total_streams":23,"services_completed":4,"total_services":4}
```

**Error:**
```json
{"event":"error","service":null,"message":"Item not found","streams":null,"total_streams":0,"services_completed":0,"total_services":0}
```

### POST `/api/v1/scrape/auto` — Request body

```json
{
  "media_type": "tv",
  "item_id": 42,
  "season_numbers": [1, 2]
}
```

Or by external id (creates item if missing):

```json
{
  "media_type": "movie",
  "tmdb_id": "438631",
  "min_filesize_override": 2000,
  "max_filesize_override": 25000
}
```

### POST `/api/v1/scrape/start_session` — Response

```json
{
  "message": "Started manual scraping session",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": 12,
  "media_type": "tv",
  "tmdb_id": null,
  "tvdb_id": "12345",
  "imdb_id": "tt0944947",
  "torrent_id": "ABC123XYZ",
  "torrent_info": {
    "id": "ABC123XYZ",
    "name": "Show.S01.1080p.BluRay.x264-GROUP",
    "status": "downloaded",
    "infohash": "a1b2c3d4e5f6...",
    "progress": 100,
    "bytes": 15728640000,
    "files": {}
  },
  "containers": {
    "infohash": "a1b2c3d4e5f6...",
    "files": [
      {"file_id": 4, "filename": "Show.S01E01.1080p.mkv", "filesize": 1572864000, "download_url": "https://..."},
      {"file_id": 5, "filename": "Show.S01E02.1080p.mkv", "filesize": 1523456789, "download_url": "https://..."}
    ],
    "torrent_id": "ABC123XYZ",
    "torrent_info": null
  },
  "parsed_files": [
    {"file_id": 4, "filename": "Show.S01E01.1080p.mkv", "filesize": 1572864000, "download_url": "https://...", "parsed_metadata": {"season": 1, "episode": 1, "resolution": "1080p"}},
    {"file_id": 5, "filename": "Show.S01E02.1080p.mkv", "filesize": 1523456789, "download_url": null, "parsed_metadata": {"season": 1, "episode": 2, "resolution": "1080p"}}
  ],
  "expires_at": "2025-03-09T12:35:00.000000"
}
```

### POST `/api/v1/scrape/session/{session_id}` — Request bodies

**select_files** (file_id → file info; keys are string IDs):

```json
{
  "action": "select_files",
  "files": {
    "4": {"filename": "Show.S01E01.1080p.mkv", "filesize": 1572864000},
    "5": {"filename": "Show.S01E02.1080p.mkv", "filesize": 1523456789}
  }
}
```

**update_attributes — movie** (single file):

```json
{
  "action": "update_attributes",
  "file_data": {
    "file_id": 4,
    "filename": "Movie.2021.1080p.mkv",
    "filesize": 2500000000,
    "download_url": "https://..."
  }
}
```

**update_attributes — TV show** (season → episode → file; keys are string numbers in JSON):

```json
{
  "action": "update_attributes",
  "file_data": {
    "1": {
      "1": {"file_id": 4, "filename": "Show.S01E01.1080p.mkv", "filesize": 1572864000, "download_url": "https://..."},
      "2": {"file_id": 5, "filename": "Show.S01E02.1080p.mkv", "filesize": 1523456789, "download_url": "https://..."}
    },
    "2": {
      "1": {"file_id": 8, "filename": "Show.S02E01.1080p.mkv", "filesize": 1600000000, "download_url": "https://..."}
    }
  }
}
```

**abort / complete:**

```json
{"action": "abort"}
```
```json
{"action": "complete"}
```

### POST `/api/v1/scrape/parse` — Request & response

**Request:**
```json
["Dune.2021.2160p.UHD.BluRay.x265-HDR", "Show.S01E01.1080p.WEB-DL.x264"]
```

**Response:**
```json
{
  "message": "Parsed torrent titles",
  "data": [
    {"raw_title": "Dune.2021.2160p.UHD.BluRay.x265-HDR", "resolution": "2160p", "quality": "bluray", "codec": "x265", "year": 2021, ...},
    {"raw_title": "Show.S01E01.1080p.WEB-DL.x264", "resolution": "1080p", "season": 1, "episode": 1, ...}
  ]
}
```

Exact keys in each object come from PTT (parse_title); typically resolution, quality, codec, year, season, episode, etc.

---

## Database (scraping-related)

### MediaItem (relevant columns)

| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | Item id used in API |
| `type` | enum | `movie`, `show`, `season`, `episode`, `mediaitem` |
| `scraped_at` | datetime \| null | Last time scraping ran for this item |
| `scraped_times` | int | Number of scrape runs (used for backoff) |
| `failed_attempts` | int | Consecutive runs with no new streams; triggers Failed after `max_failed_attempts` |
| `imdb_id`, `tmdb_id`, `tvdb_id` | str \| null | Used by scrapers and item resolution |

Relations: `streams` (many-to-many via StreamRelation), `blacklisted_streams` (many-to-many via StreamBlacklistRelation).

**Example row (movie):**
```
id=7, type='movie', title='Dune', scraped_at='2025-03-09 10:00:00', scraped_times=2, failed_attempts=0, imdb_id='tt1160419', tmdb_id='438631'
```

### Stream

| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | Stream id (e.g. for pin/unpin) |
| `infohash` | str | Torrent infohash (unique key in API stream dict) |
| `raw_title` | str | Original release title |
| `parsed_title` | str | RTN normalized title |
| `rank` | int | RTN rank (higher = better match) |
| `lev_ratio` | float | Title match ratio |
| `resolution` | str \| null | e.g. `1080p`, `2160p` |
| `is_cached` | bool | Whether debrid reports cached |

**Example row:**
```
id=101, infohash='a1b2c3d4e5f6789012345678901234567890abcd', raw_title='Dune.2021.2160p.UHD.BluRay.x265-HDR', parsed_title='Dune 2021 2160p UHD BluRay x265 HDR', rank=92, lev_ratio=1.0, resolution='2160p', is_cached=1
```

### StreamRelation

Links a media item to a stream (item has this stream available).

| Column | Type |
|--------|------|
| `id` | int PK |
| `parent_id` | int FK → MediaItem.id |
| `child_id` | int FK → Stream.id |

**Example:** `parent_id=7, child_id=101` → movie 7 has stream 101.

### StreamBlacklistRelation

Links a media item to a stream the user has blacklisted (won't be suggested again).

| Column | Type |
|--------|------|
| `id` | int PK |
| `media_item_id` | int FK → MediaItem.id |
| `stream_id` | int FK → Stream.id |

**Example:** `media_item_id=7, stream_id=99` → stream 99 is blacklisted for item 7.

### Scraping sessions (in-memory only)

Sessions from `POST /scrape/start_session` are **not** stored in the DB. They live in `scraping_session_manager.sessions` (dict by `session_id`), expire after 5 minutes, and are cleared on abort/complete.

---

### POST `/api/v1/scrape/auto` — Trigger auto scrape (pipeline)

**Body (JSON):**

```json
{
  "media_type": "movie" | "tv",
  "item_id": 123,           // optional
  "tmdb_id": "...",        // optional
  "tvdb_id": "...",        // optional
  "imdb_id": "...",        // optional
  "season_numbers": [1,2], // optional; TV only
  "ranking_overrides": { ... },
  "min_filesize_override": 0,
  "max_filesize_override": 0
}
```

**Behavior:** Resolves (or creates) the item; if TV and `season_numbers` is set, only those seasons are unscoped and get events; then enqueues pipeline event(s). Returns immediately with a message; no stream list.

**Response:** `200` → `{ "message": "Started auto scrape for ..." }` (or season-specific message).

**Errors:** 400 (e.g. not a show when using season_numbers), 404 (item not found), 412 (services not initialized).

---

### POST `/api/v1/scrape/start_session` — Start manual scrape session (pick files from one torrent)

Used when the user has chosen a **magnet** (e.g. from GET `/scrape` results) and wants to select which files to download for that torrent.

**Query params:**  
`magnet` (required), `min_filesize_override`, `max_filesize_override`, and the same item identification as GET `/scrape`: `item_id`, or `tmdb_id`/`tvdb_id`/`imdb_id` + `media_type`.

**Flow:**

1. Extract infohash from magnet.
2. Resolve item via `resolve_media_item`.
3. **Resolve torrent**: instant availability check on the downloader (debrid); if not cached or no files, temporarily add torrent and probe; if still no valid files, 400.
4. Create a **scraping session** (in-memory, 5‑minute TTL), add torrent to downloader, attach container (file list) to session.
5. Return session id, item id, media type, ids, `torrent_id`, `torrent_info`, `containers`, `parsed_files`, `expires_at`.

**Response:** `200` → `StartSessionResponse` (session_id, item_id, media_type, tmdb_id, tvdb_id, imdb_id, torrent_id, torrent_info, containers, parsed_files, expires_at).

**Errors:** 400 (invalid magnet or torrent not cached), 404 (item not found), 412 (services not initialized), 500 (e.g. add_torrent failure).

---

### POST `/api/v1/scrape/session/{session_id}` — Session action

**Body:** `{ "action": "select_files" | "update_attributes" | "abort" | "complete", "files": {...}, "file_data": {...} }`

- **select_files**: `files` is a map of file_id → `{ filename, filesize }` (same structure as in session containers). Backend calls downloader to select those files; stores selection on session. Returns `download_type`: `"cached"` or `"uncached"`.
- **update_attributes**: `file_data` is either a single file (movie) or a nested structure season → episode → file (show). Backend builds file ids and active seasons, then calls `downloader.start_manual_download(item, stream, file_ids)`, updates season/episode states (pause/unpause), commits and emits an event for downstream (symlinker/filesystem). This is the "confirm and download" step.
- **abort**: Remove session and delete the torrent from the downloader.
- **complete**: Only allowed when session has `torrent_id` and `selected_files`; marks session complete and removes it.

**Errors:** 404 (session not found or expired), 400 (e.g. missing body for action).

---

### POST `/api/v1/scrape/parse` — Parse torrent titles (utility)

**Body:** `["title1", "title2", ...]`  
**Response:** `{ "message": "...", "data": [ { "raw_title", ...parsed fields } ] }`.  
No auth change; useful for debugging or UI tooling.

---

### POST `/api/v1/scrape/overseerr/requests` — Overseerr import

Fetches requests from Overseerr and enqueues new ones into the pipeline. Filter/take query params. 412 if Overseerr not enabled. Separate from the "scrape streams" flow; included under the same router.

---

## Items router (streams)

- **POST `/api/v1/items/{item_id}/streams/refresh`**  
  Re-scrapes the item (manual mode, no bucket limit), merges **new** streams into the item, commits. Returns a message with count. Does **not** enqueue pipeline. Good for "refresh streams" in the UI without re-running full auto scrape.

- **POST `/api/v1/items/{item_id}/streams/reset`**  
  Resets streams for the item (and related state). See items API for full semantics.

---

## Using the API to Rework the Frontend

1. **"Search scrapers" / manual stream list**  
   - **GET `/api/v1/scrape`** with `item_id` (or `tmdb_id`/`media_type` for movies, `tvdb_id`/`media_type` for tv).  
   - Use `stream=true` to show results **as they arrive** (SSE): subscribe to events, on `streams`/`complete` merge into local state and render.  
   - Use `ranking_overrides`, `min_filesize_override`, `max_filesize_override` for user preferences without changing global settings.

2. **"Pick from scrapers" → choose torrent → pick files**  
   - After user picks a magnet from the stream list, call **POST `/api/v1/scrape/start_session`** with `magnet` and same item identification.  
   - Use returned `containers` / `parsed_files` to show file tree; user selects files.  
   - **POST `/api/v1/scrape/session/{session_id}`** with `action: "select_files"` and `files` map.  
   - Then **POST same** with `action: "update_attributes"` and `file_data` (movie: one file; show: season → episode → file) to start the actual download and update item state.  
   - Optionally **POST** `action: "complete"` when done, or **abort** to cancel.

3. **"Auto scrape" (background pipeline)**  
   - **POST `/api/v1/scrape/auto`** with `media_type` and either `item_id` or external ids. For TV, add `season_numbers` to scrape only selected seasons.  
   - No stream list in response; poll **GET `/api/v1/items/{item_id}`** (or streams/metadata) and/or use WebSocket/events to see state changes (Scraped → Downloaded → etc.).

4. **Refresh streams without re-running pipeline**  
   - **POST `/api/v1/items/{item_id}/streams/refresh`** to fetch new streams and merge into the item. Then reload item/streams in the UI.

5. **Custom title / IMDB override**  
   - GET `/api/v1/scrape` supports `custom_title` and `custom_imdb_id` so the user can search under a different title or IMDB id without changing library metadata.

6. **New item from discover**  
   - You can call **POST `/api/v1/scrape/auto`** with only `tmdb_id`/`media_type` or `tvdb_id`/`media_type`; backend will create and index the item then enqueue scraping (same as current explore flow).

---

## Settings that affect scraping

- **Scraping**: which services are enabled, `bucket_limit`, `max_failed_attempts`, `after_2` / `after_5` / `after_10` (hours before retry), `dubbed_anime_only`, etc.
- **Ranking (RTN)**: resolutions, custom ranks; can be overridden per request via `ranking_overrides` where supported (GET `/scrape`, auto_scrape body).
- **Overrides**: `min_filesize_override` / `max_filesize_override` are applied during parse_results and container resolution when provided.

---

## Summary table

| Goal | Endpoint | Notes |
|-----|----------|--------|
| Get stream list for an item | GET `/api/v1/scrape` | Use `stream=true` for SSE |
| Trigger background scrape | POST `/api/v1/scrape/auto` | No stream list returned |
| Start "pick files" from magnet | POST `/api/v1/scrape/start_session` | Then session actions |
| Select files / apply & download / abort | POST `/api/v1/scrape/session/{id}` | select_files → update_attributes → complete |
| Refresh streams on existing item | POST `/api/v1/items/{id}/streams/refresh` | Merge only; no pipeline |
| Parse titles (utility) | POST `/api/v1/scrape/parse` | Body: array of title strings |

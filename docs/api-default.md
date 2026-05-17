# Default / Misc API

Routes are mounted at **`/api/v1`** (no prefix). Health, stats, services, calendar, logs, mount, debug, Trakt OAuth, API key.

---

## GET `/api/v1/health`

**Response:** `{ "message": "True" | "False" }` — whether the program is initialized.

---

## GET `/api/v1/downloader_user_info`

User info from all initialized downloader services (Real-Debrid, AllDebrid, etc.).

**Response:**
```json
{
  "services": [
    {
      "service": "realdebrid",
      "username": "...",
      "email": "...",
      "user_id": 123,
      "premium_status": "premium",
      "premium_expires_at": "2025-12-01T00:00:00",
      "premium_days_left": 90,
      "points": null,
      "total_downloaded_bytes": null,
      "cooldown_until": null
    }
  ]
}
```

**Errors:** 503 if no downloader initialized.

---

## GET `/api/v1/downloader_status`

Operational downloader status: circuit breakers, per-service cooldowns, event-queue depth, and in-flight jobs. Does not include account/premium fields (see `/downloader_user_info`).

**Response:**
```json
{
  "paused": false,
  "pause_until": null,
  "min_job_interval_seconds": 0.2,
  "queue": {
    "scraped_queued": 42,
    "deferred": 10,
    "downloader_emitted": 8,
    "next_ready_at": "2026-05-16T15:27:57"
  },
  "services": [
    {
      "key": "torbox",
      "available": true,
      "cooldown_until": null,
      "breaker": { "domain": "api.torbox.app", "state": "CLOSED", "failures": 0 }
    }
  ],
  "in_flight_items": [
    {
      "id": 12345,
      "title": "Example Movie",
      "type": "movie",
      "parent_title": null,
      "season_number": null,
      "episode_number": null,
      "state": "Scraped"
    }
  ],
  "queued_items": [
    {
      "id": 99,
      "title": "Example Show",
      "type": "episode",
      "parent_title": "Example Show",
      "season_number": 1,
      "episode_number": 4,
      "state": "Scraped",
      "run_at": "2026-05-16T15:30:00",
      "queued_at": "2026-05-16T15:25:00",
      "scraped_at": "2026-05-16T15:20:00",
      "deferred": false,
      "wait_seconds": 300.0,
      "emitted_by": "StateTransition"
    }
  ],
  "last_job": {
    "item": {
      "id": 88,
      "title": "Previous Movie",
      "type": "movie",
      "state": "Downloaded"
    },
    "completed_at": "2026-05-16T15:28:00",
    "outcome": "success",
    "detail": null,
    "service": "torbox"
  }
}
```

`queued_items` lists downloader-relevant events in the event queue (Scraped state or emitted by Downloader), up to 50 rows, with wait timing. `last_job` is the most recent completed downloader run (in-memory only; cleared on restart).

**Errors:** 503 if no downloader initialized.

---

## POST `/api/v1/generateapikey`

Generate a new API key, save it to settings, and return it.

**Response:** `{ "message": "<new_api_key>" }`

---

## GET `/api/v1/services`

**Response:** `{ "services": { "<service_key>": true|false, ... }, "mock_vfs": bool, "console_updater": bool }` — per-integration status plus flags when the in-memory VFS or console-only updater is active. Older clients may still receive a flat map only (no `services` wrapper); the UI accepts both shapes.

---

## GET `/api/v1/trakt/oauth/initiate`

**Response:** `{ "auth_url": "https://..." }` — URL for user to authorize Trakt.

**Errors:** 404 if Trakt service not found.

---

## GET `/api/v1/trakt/oauth/callback`

**Query:** `code` — OAuth code from Trakt redirect.

**Response:** `{ "message": "OAuth token obtained successfully" }`

**Errors:** 404 if Trakt API key not in settings; 400 if token exchange fails.

---

## GET `/api/v1/stats`

Aggregated library statistics.

**Response:**
```json
{
  "total_items": 1000,
  "total_movies": 200,
  "total_shows": 50,
  "total_seasons": 200,
  "total_episodes": 550,
  "total_symlinks": 750,
  "incomplete_items": 100,
  "states": { "Requested": 5, "Indexed": 10, "Scraped": 20, ... },
  "activity": { "2025-03-01": 3, "2025-03-02": 1 },
  "media_year_releases": [{ "year": 2024, "count": 50 }, ...]
}
```

---

## GET `/api/v1/logs`

Read the current log file.

**Response:** `{ "logs": ["line1", "line2", ...] }`

**Errors:** 404 if no log file handler; 500 on read error.

---

## GET `/api/v1/events`

Event manager state (e.g. for debugging).

**Response:** `{ "events": { "<event_type>": [item_id, ...], ... } }`

---

## GET `/api/v1/mount`

List all files in the Riven VFS mount directory. See [vfs.md](vfs.md) for how the VFS works.

**Response:** `{ "files": { "<filename>": "<absolute_path>", ... } }`

---

## POST `/api/v1/upload_logs`

Upload the current log file to paste.c-net.org.

**Response:** `{ "success": true, "url": "https://paste.c-net.org/..." }`

**Errors:** 500 if log file not found or upload fails.

---

## GET `/api/v1/calendar`

Calendar of library items (by date).

**Response:** `{ "data": { "<date_int_key>": { ...item data by date... }, ... } }`

---

## GET `/api/v1/vfs_stats`

VFS statistics: active streams and cache metrics. See [vfs.md](vfs.md) for how the VFS works.

**Response:**
```json
{
  "streams": { "<path:fh>": { ...per-stream stats... } },
  "cache": { ...chunk-cache metrics... }
}
```

**Errors:** Requires filesystem service with `riven_vfs`.

---

## POST `/api/v1/debug`

Generate a debug bundle: upload logs, create DB backup, return system info.

**Response:**
```json
{
  "success": true,
  "log_url": "https://paste.c-net.org/...",
  "db_backup_filename": "riven_20250309_120000.sql",
  "system_info": {
    "platform": "...",
    "python_version": "3.12",
    "cpu_count": 8,
    "load_avg": [...],
    "memory": "16.00G",
    "swap": "2.00G",
    "disk": "500.00G"
  },
  "errors": []
}
```

`errors` lists any failures (e.g. upload or backup failed).

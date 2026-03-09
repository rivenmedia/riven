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

## POST `/api/v1/generateapikey`

Generate a new API key, save it to settings, and return it.

**Response:** `{ "message": "<new_api_key>" }`

---

## GET `/api/v1/services`

**Response:** `{ "<service_key>": true|false, ... }` — e.g. `indexer`, `scraping`, `downloader`, `prowlarr`, `torrentio`, etc.

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

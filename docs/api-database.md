# Database API

Base path: **`/api/v1/database`**

Backup, restore, download, and clean database snapshots. Snapshots are stored under `./data/db_snapshot/`.

---

## POST `/api/v1/database/backup`

Create a backup of the database.

**Response:**
```json
{
  "success": true,
  "message": "Database backup created successfully",
  "filename": "riven_20250309_120000.sql"
}
```

**Errors:** 500 if backup fails.

---

## GET `/api/v1/database/backup/download/{filename}`

Download a backup file by name. Use the `filename` returned from `/backup`.

**Path:** `filename` — must end with `.sql`; no path traversal (`/`, `\`, `..`).

**Response:** File download (`application/sql`).

**Errors:** 400 invalid filename/type; 404 file not found.

---

## POST `/api/v1/database/restore`

Restore the database from a backup.

**Body (form):** Either:
- `filename`: name of an existing file in the `db_snapshot` folder, or
- `file`: upload a `.sql` file.

Provide only one of `filename` or `file`. If neither is provided, restores from `latest.sql`.

**Response:**
```json
{
  "success": true,
  "message": "Database restored successfully from <source>"
}
```

**Errors:** 400 if both or invalid file; 404 if named file not found; 500 if restore fails.

---

## DELETE `/api/v1/database/backup/clean`

Delete snapshot file(s).

**Query:** `filename` (optional) — if provided, deletes only that snapshot; otherwise deletes all.

**Response:**
```json
{
  "success": true,
  "message": "Deleted snapshot: x.sql" | "Deleted N snapshot(s)",
  "deleted_files": ["a.sql", "b.sql"]
}
```

**Errors:** 400 invalid filename; 500 if clean fails.

---

## Library backup bundles (CSV + ZIP)

Human-readable library backups for migration and disaster recovery. Bundles are built **on disk** under `./data/backups/` (temp CSVs → ZIP → delete temp). Video files are not included; pinned streams are restored via debrid re-activation.

### POST `/api/v1/database/export/bundle`

Create a backup bundle ZIP.

**Query:**
- `include_settings` (default `true`) — include `settings.json`
- `redact_secrets` (default `false`) — mask API keys/tokens in settings

**Response:**
```json
{
  "success": true,
  "message": "Backup bundle created",
  "filename": "riven-backup_20260519_120000.riven-backup.zip",
  "manifest": { "format_version": 1, "counts": { "movies": 10, "tv_shows": 5 } }
}
```

### GET `/api/v1/database/export/download/{filename}`

Download a bundle ZIP. Filename must end with `.zip` or `.riven-backup.zip`.

**Response:** `application/zip` file download.

### POST `/api/v1/database/import/bundle`

Import library titles and pinned streams (additive; does not wipe the database).

**Body (multipart/form):**
- `file` — backup bundle ZIP (required)
- `restore_settings` (default `false`)
- `skip_existing_titles` (default `true`)
- `restore_pins` (default `true`)

**Response:**
```json
{
  "success": true,
  "message": "Import complete: +2 movies, +1 shows, 5 pins restored, 0 pins failed",
  "added_movies": 2,
  "added_shows": 1,
  "skipped_titles": 10,
  "pins_restored": 5,
  "pins_failed": 0,
  "errors": []
}
```

### DELETE `/api/v1/database/export/clean`

Delete bundle ZIP file(s) from `./data/backups/`.

**Query:** `filename` (optional) — delete one file, or all bundles if omitted.

### Bundle layout (format_version `1`)

| Path | Description |
|------|-------------|
| `manifest.json` | Version, counts, file list, warnings |
| `library/movies.csv` | `title,year,imdb_id` |
| `library/tv-shows.csv` | `title,year,imdb_id` |
| `library/pinned-episodes.csv` | Season/episode pins metadata |
| `streams/{provider}.csv` | Pinned streams per debrid provider |
| `settings.json` | Optional full settings export |

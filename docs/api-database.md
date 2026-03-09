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
